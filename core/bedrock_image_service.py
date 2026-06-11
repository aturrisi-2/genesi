"""
AWS BEDROCK IMAGE SERVICE
Servizio per generazione immagini via AWS Bedrock Stable Diffusion
Supporta: generazione, salvamento S3, caching, cost tracking, rate limiting
"""

import asyncio
import json
import base64
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
from botocore.exceptions import ClientError

from config.aws_config import bedrock_config
from core.log import log
from core.storage import storage

logger = logging.getLogger(__name__)


class BedrockImageService:
    """
    Servizio image generation via AWS Bedrock
    
    Features:
    - Generazione immagini Stable Diffusion XL
    - Salvamento automatico su S3
    - Caching risultati per prompt identici
    - Cost tracking per utente
    - Rate limiting per sicurezza
    """
    
    # Cost tracking
    COST_PER_IMAGE_USD = 0.002  # AWS Bedrock Stable Diffusion pricing
    
    # Rate limiting
    IMAGES_PER_USER_PER_DAY = 10
    IMAGES_PER_USER_PER_HOUR = 3
    
    # Configurazione generazione
    DEFAULT_CONFIG = {
        "width": 512,
        "height": 512,
        "steps": 30,
        "guidance_scale": 7.5,
        "sampler": "K_DPMPP_2M",
        "signed_url_ttl_seconds": 3600,
        "cache_ttl_minutes": 50,
    }
    
    def __init__(self):
        """Inizializza il servizio"""
        
        if not bedrock_config or not bedrock_config.is_configured():
            logger.warning("❌ AWS Bedrock non configurato - servizio in fallback mode")
            self.enabled = False
        else:
            self.enabled = True
            self.runtime = bedrock_config.get_runtime_client()
            self.s3 = bedrock_config.get_s3_client()
            self.bucket = bedrock_config.get_bucket_name()
            self.model_id = bedrock_config.get_model_id()
            self.region = bedrock_config.get_region()
            logger.info(f"✅ Bedrock Image Service initialized - model={self.model_id}")

    def _build_payload(self, prompt: str, width: int, height: int, steps: int, guidance_scale: float, seed: Optional[int]) -> Dict[str, Any]:
        """
        Costruisce il payload Bedrock in base al modello configurato.
        Supporta:
        - SDXL legacy (stability.stable-diffusion-xl-*)
        - Stability Image Core/Ultra (stability.stable-image-*)
        """
        model = (self.model_id or "").lower()

        # Nuovi modelli Stability Image (Core/Ultra)
        if "stable-image" in model:
            payload = {
                "prompt": prompt,
                "output_format": "png",
            }
            if seed is not None:
                payload["seed"] = int(seed)
            return payload

        # Modelli Amazon Titan/Nova (text-to-image)
        if model.startswith("amazon.titan-image-generator") or model.startswith("amazon.nova-canvas"):
            image_cfg: Dict[str, Any] = {
                "numberOfImages": 1,
                "height": height,
                "width": width,
                "cfgScale": guidance_scale,
            }
            if seed is not None:
                image_cfg["seed"] = int(seed)

            return {
                "taskType": "TEXT_IMAGE",
                "textToImageParams": {
                    "text": prompt,
                },
                "imageGenerationConfig": image_cfg,
            }

        # SDXL legacy
        return {
            "text_prompts": [
                {
                    "text": prompt,
                    "weight": 1.0
                }
            ],
            "cfg_scale": guidance_scale,
            "seed": seed if seed is not None else 0,
            "steps": min(max(steps, 20), 150),
            "height": height,
            "width": width,
            "sampler": self.DEFAULT_CONFIG["sampler"]
        }

    def _extract_image_base64(self, response: Dict[str, Any]) -> Optional[str]:
        """Estrae l'immagine base64 dai formati risposta Stability legacy e moderni."""
        if not isinstance(response, dict):
            return None

        # Stability Image Core/Ultra format
        images = response.get("images")
        if isinstance(images, list) and images:
            img = images[0]
            if isinstance(img, str) and img.strip():
                return img

        # SDXL legacy format
        artifacts = response.get("artifacts")
        if isinstance(artifacts, list) and artifacts:
            first = artifacts[0] or {}
            if isinstance(first, dict):
                img = first.get("base64")
                if isinstance(img, str) and img.strip():
                    return img

        return None
    
    async def generate_image(
        self,
        prompt: str,
        user_id: Optional[str] = None,
        width: int = 512,
        height: int = 512,
        steps: int = 30,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None
    ) -> Optional[str]:
        """
        Genera immagine usando AWS Bedrock Stable Diffusion
        
        Args:
            prompt: Descrizione immagine da generare
            user_id: ID utente (per rate limiting e tracking)
            width: Larghezza immagine (512, 768, 1024)
            height: Altezza immagine
            steps: Passi generazione (20-150, default 30)
            guidance_scale: Fedeltà al prompt (default 7.5)
            seed: Seed per riproducibilità (opzionale)
        
        Returns:
            URL S3 immagine pubblica o None se fallisce
        """
        
        try:
            # Validazioni input
            if not prompt or len(prompt.strip()) < 2:
                logger.warning("BEDROCK_ERROR: Prompt troppo corto")
                return None
            
            # Bedrock textToImageParams.text ha limite di 512 caratteri
            if len(prompt) > 512:
                logger.warning("BEDROCK_PROMPT_TRUNCATED original_len=%d", len(prompt))
                prompt = prompt[:512]
            
            # Validazione dimensioni
            valid_widths = [512, 768, 1024]
            if width not in valid_widths:
                logger.warning(f"Invalid width {width}, defaulting to 512")
                width = 512
            if height not in valid_widths:
                height = 512
            
            # Check cache per prompt identico
            cache_url = await self._check_cache(prompt)
            if cache_url:
                logger.info(f"Cache hit for prompt: {prompt[:50]}...")
                log("BEDROCK_CACHE_HIT", prompt_len=len(prompt))
                return cache_url

            # Check rate limiting (conta solo le generazioni reali, non i cache hit)
            if user_id:
                if not await self._check_rate_limit(user_id):
                    logger.warning(f"Rate limit exceeded for user {user_id}")
                    return None
            
            log("BEDROCK_IMAGE_START", 
                prompt_len=len(prompt), 
                width=width, 
                height=height,
                steps=steps)
            
            if not self.enabled:
                logger.error("Bedrock non abilitato")
                log("BEDROCK_DISABLED")
                return None
            
            # Prepara payload per Bedrock (model-aware)
            payload = self._build_payload(
                prompt=prompt,
                width=width,
                height=height,
                steps=steps,
                guidance_scale=guidance_scale,
                seed=seed,
            )
            
            # Chiama Bedrock (async wrapper intorno a sync boto3)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self._invoke_bedrock,
                payload
            )
            
            if not response:
                log("BEDROCK_RESPONSE_EMPTY")
                return None
            
            # Estrai immagine dal response (legacy + new Stability formats)
            image_base64 = self._extract_image_base64(response)
            if not image_base64:
                logger.error("No image in Bedrock response")
                log("BEDROCK_NO_ARTIFACTS")
                return None
            
            # Salva su S3
            s3_url = await self._save_to_s3(image_base64, prompt)
            
            if not s3_url:
                log("BEDROCK_S3_SAVE_FAILED")
                return None
            
            # Cache il risultato
            await self._cache_result(prompt, s3_url)
            
            # Track generazione
            if user_id:
                await self._increment_rate_limit(user_id)
                await self._track_generation(user_id, prompt, success=True)
            
            log("BEDROCK_IMAGE_SUCCESS", 
                s3_url=s3_url,
                prompt_len=len(prompt),
                cost_usd=self.COST_PER_IMAGE_USD)
            
            return s3_url
        
        except Exception as e:
            logger.error(f"Image generation failed: {e}", exc_info=True)
            log("BEDROCK_IMAGE_ERROR", error=str(e)[:200])
            
            if user_id:
                await self._track_generation(user_id, prompt, success=False)
            
            return None
    
    def _invoke_bedrock(self, payload: Dict[str, Any]) -> Optional[Dict]:
        """
        Chiama Bedrock API (sync).
        Eseguito in executor per non bloccare event loop.
        """
        try:
            response = self.runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps(payload),
                contentType="application/json",
                accept="application/json"
            )
            
            response_body = json.loads(response["body"].read())
            logger.info("✅ Bedrock invoked successfully")
            return response_body
        
        except Exception as e:
            logger.error(f"❌ Bedrock API error: {e}")
            return None
    
    async def _save_to_s3(self, image_base64: str, prompt: str) -> Optional[str]:
        """
        Salva immagine decodificata da base64 su S3
        Ritorna URL pubblico della risorsa
        """
        try:
            # Decoda base64
            try:
                image_bytes = base64.b64decode(image_base64)
            except Exception as e:
                logger.error(f"Base64 decode failed: {e}")
                return None
            
            if len(image_bytes) == 0:
                logger.error("Image bytes is empty")
                return None
            
            # Genera nome file sicuro
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            prompt_slug = prompt[:30].replace(" ", "_").lower()
            prompt_slug = "".join(c for c in prompt_slug if c.isalnum() or c == "_")
            filename = f"bedrock/{timestamp}_{prompt_slug}.png"
            
            # Upload su S3 (async wrapper)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._upload_s3_sync,
                image_bytes,
                filename
            )
            
            # Genera URL accessibile (preferibilmente presigned per bucket privati)
            try:
                s3_url = self.s3.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={"Bucket": self.bucket, "Key": filename},
                    ExpiresIn=self.DEFAULT_CONFIG["signed_url_ttl_seconds"],
                )
            except Exception:
                # Fallback URL diretto (funziona solo se oggetto pubblico)
                s3_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{filename}"
            
            logger.info(f"✅ Image saved to S3: {filename}")
            log("IMAGE_SAVED_S3", url=s3_url, size_bytes=len(image_bytes))
            
            return s3_url
        
        except Exception as e:
            logger.error(f"S3 save failed: {e}", exc_info=True)
            log("BEDROCK_S3_ERROR", error=str(e)[:200])
            return None
    
    def _upload_s3_sync(self, image_bytes: bytes, filename: str):
        """
        Upload sync a S3 - eseguito in executor
        """
        base_params = {
            "Bucket": self.bucket,
            "Key": filename,
            "Body": image_bytes,
            "ContentType": "image/png",
            "ServerSideEncryption": "AES256",
            "CacheControl": "max-age=31536000",
        }

        try:
            # Primo tentativo: compatibilità con bucket che supportano ACL
            self.s3.put_object(
                ACL="public-read",
                **base_params,
            )
            logger.info(f"S3 upload success: {filename}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "AccessControlListNotSupported":
                logger.warning("S3 bucket ACL disabled, retrying upload without ACL: %s", filename)
                self.s3.put_object(**base_params)
                logger.info(f"S3 upload success (no ACL): {filename}")
                return
            logger.error(f"S3 put_object failed: {e}")
            raise
        except Exception as e:
            logger.error(f"S3 put_object failed: {e}")
            raise
    
    async def _check_rate_limit(self, user_id: str) -> bool:
        """
        Verifica rate limiting per utente
        Limiti: 3/ora, 10/giorno
        """
        try:
            now = datetime.utcnow()
            today = now.strftime("%Y-%m-%d")
            this_hour = now.strftime("%Y-%m-%d-%H")
            
            # Check daily limit
            daily_key = f"bedrock:limit:daily:{user_id}:{today}"
            daily_count = await storage.load(daily_key, default=0)
            
            if daily_count >= self.IMAGES_PER_USER_PER_DAY:
                logger.warning(f"Daily limit reached for {user_id}: {daily_count}/{self.IMAGES_PER_USER_PER_DAY}")
                log("BEDROCK_DAILY_LIMIT", user_id=user_id, count=daily_count)
                return False
            
            # Check hourly limit
            hourly_key = f"bedrock:limit:hourly:{user_id}:{this_hour}"
            hourly_count = await storage.load(hourly_key, default=0)
            
            if hourly_count >= self.IMAGES_PER_USER_PER_HOUR:
                logger.warning(f"Hourly limit reached for {user_id}: {hourly_count}/{self.IMAGES_PER_USER_PER_HOUR}")
                log("BEDROCK_HOURLY_LIMIT", user_id=user_id, count=hourly_count)
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # Default: allow on error (fail open)
            return True

    async def _increment_rate_limit(self, user_id: str) -> None:
        """Incrementa i contatori solo dopo una generazione riuscita."""
        try:
            now = datetime.utcnow()
            today = now.strftime("%Y-%m-%d")
            this_hour = now.strftime("%Y-%m-%d-%H")

            daily_key = f"bedrock:limit:daily:{user_id}:{today}"
            hourly_key = f"bedrock:limit:hourly:{user_id}:{this_hour}"

            daily_count = await storage.load(daily_key, default=0)
            hourly_count = await storage.load(hourly_key, default=0)

            await storage.save(daily_key, daily_count + 1)
            await storage.save(hourly_key, hourly_count + 1)
        except Exception as e:
            logger.error(f"Rate limit increment failed: {e}")
    
    async def _check_cache(self, prompt: str) -> Optional[str]:
        """
        Verifica cache per prompt identico (non rigenera stessa immagine)
        Cache durata: 7 giorni
        """
        try:
            # Hash il prompt come chiave
            prompt_hash = hashlib.sha256(prompt.lower().encode()).hexdigest()[:16]
            cache_key = f"bedrock:cache:{prompt_hash}"
            
            cached = await storage.load(cache_key, default=None)
            
            if cached:
                # Verifica scadenza cache: breve per evitare URL presigned scaduti
                cached_time = datetime.fromisoformat(cached.get("timestamp", ""))
                age = datetime.utcnow() - cached_time

                if age < timedelta(minutes=self.DEFAULT_CONFIG["cache_ttl_minutes"]):
                    logger.info(f"Cache hit: {prompt_hash}")
                    return cached.get("url")
            
            return None
        
        except Exception as e:
            logger.debug(f"Cache check failed: {e}")
            return None
    
    async def _cache_result(self, prompt: str, url: str):
        """Salva risultato in cache"""
        try:
            prompt_hash = hashlib.sha256(prompt.lower().encode()).hexdigest()[:16]
            cache_key = f"bedrock:cache:{prompt_hash}"
            
            await storage.save(cache_key, {
                "url": url,
                "prompt": prompt[:100],
                "timestamp": datetime.utcnow().isoformat()
            })
        
        except Exception as e:
            logger.debug(f"Cache save failed: {e}")
    
    async def _track_generation(self, user_id: str, prompt: str, success: bool):
        """
        Traccia generazioni per cost tracking e analytics
        """
        try:
            timestamp = datetime.utcnow().isoformat()
            cost = self.COST_PER_IMAGE_USD if success else 0
            
            # Salva record
            track_key = f"bedrock:tracking:{user_id}:{timestamp}"
            await storage.save(track_key, {
                "prompt": prompt[:100],
                "success": success,
                "cost_usd": cost,
                "timestamp": timestamp
            })
            
            # Aggiorna totale costo utente
            total_cost_key = f"bedrock:cost:total:{user_id}"
            current = await storage.load(total_cost_key, default=0)
            await storage.save(total_cost_key, current + cost)
            
            log("BEDROCK_TRACKED", 
                user_id=user_id, 
                success=success, 
                cost=cost)
        
        except Exception as e:
            logger.debug(f"Tracking failed: {e}")
    
    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Ritorna statistiche utente per image generation
        """
        try:
            total_cost_key = f"bedrock:cost:total:{user_id}"
            total_cost = await storage.load(total_cost_key, default=0)
            
            today = datetime.utcnow().strftime("%Y-%m-%d")
            daily_key = f"bedrock:limit:daily:{user_id}:{today}"
            daily_count = await storage.load(daily_key, default=0)
            
            return {
                "total_images_generated": int(total_cost / self.COST_PER_IMAGE_USD) if self.COST_PER_IMAGE_USD > 0 else 0,
                "total_cost_usd": round(total_cost, 4),
                "images_today": daily_count,
                "daily_limit": self.IMAGES_PER_USER_PER_DAY,
                "remaining_today": max(0, self.IMAGES_PER_USER_PER_DAY - daily_count)
            }
        
        except Exception as e:
            logger.error(f"Stats retrieval failed: {e}")
            return {}


# Singleton globale
try:
    bedrock_image_service = BedrockImageService()
except Exception as e:
    logger.error(f"Failed to initialize Bedrock Image Service: {e}")
    bedrock_image_service = None
