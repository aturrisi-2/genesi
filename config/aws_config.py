"""
AWS BEDROCK CONFIGURATION
Configurazione e client per AWS Bedrock Image Generation
Supporta Stable Diffusion XL e Amazon Titan Image Generator
"""

import boto3
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AWSBedrockConfig:
    """
    Gestione configurazione AWS Bedrock per image generation
    
    Variabili d'ambiente richieste:
    - AWS_REGION: AWS region (default: eu-west-1)
    - AWS_ACCESS_KEY_ID: AWS access key
    - AWS_SECRET_ACCESS_KEY: AWS secret key
    - AWS_S3_BUCKET: S3 bucket per salvare immagini (default: genesi-generated-images)
    - BEDROCK_MODEL: Model ID (default: stability.stable-diffusion-xl-v0)
    """
    
    # Model IDs disponibili su AWS Bedrock
    AVAILABLE_MODELS = {
        "stable-diffusion-xl": "stability.stable-diffusion-xl-v1",
        "titan-image-generator": "amazon.titan-image-generator-v1",
    }
    
    # Configurazione di default
    DEFAULT_CONFIG = {
        "region": "eu-west-1",
        "s3_bucket": "genesi-generated-images",
        "default_model": "stability.stable-diffusion-xl-v1",
        "default_width": 512,
        "default_height": 512,
        "default_steps": 30,
        "default_guidance_scale": 7.5,
    }
    
    def __init__(self):
        """Inizializza configurazione e client AWS"""
        
        # Carica da environment
        self.region = os.getenv("AWS_REGION", self.DEFAULT_CONFIG["region"])
        self.access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.bucket_name = os.getenv("AWS_S3_BUCKET", self.DEFAULT_CONFIG["s3_bucket"])
        self.model_id = os.getenv("BEDROCK_MODEL", self.DEFAULT_CONFIG["default_model"])
        
        # Validazioni
        self._validate_config()
        
        # Client initialization
        try:
            self.bedrock_runtime = boto3.client(
                'bedrock-runtime',
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            )
            logger.info(f"✅ Bedrock Runtime initialized - region={self.region}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Bedrock Runtime: {e}")
            self.bedrock_runtime = None
        
        try:
            self.s3_client = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            )
            logger.info(f"✅ S3 client initialized - bucket={self.bucket_name}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize S3 client: {e}")
            self.s3_client = None
    
    def _validate_config(self):
        """Valida configurazione richiesta"""
        
        if not self.access_key:
            logger.warning("⚠️ AWS_ACCESS_KEY_ID non configurato - Bedrock sarà offline")
        
        if not self.secret_key:
            logger.warning("⚠️ AWS_SECRET_ACCESS_KEY non configurato - Bedrock sarà offline")
        
        if self.model_id not in self.AVAILABLE_MODELS.values():
            logger.warning(f"⚠️ Model ID non riconosciuto: {self.model_id}")
            logger.info(f"   Modelli disponibili: {list(self.AVAILABLE_MODELS.keys())}")
        
        logger.info(f"AWS Bedrock Config: region={self.region}, model={self.model_id}")
    
    def is_configured(self) -> bool:
        """Verifica se AWS Bedrock è configurato correttamente"""
        return (
            self.access_key is not None and
            self.secret_key is not None and
            self.bedrock_runtime is not None and
            self.s3_client is not None
        )
    
    def get_runtime_client(self):
        """Ritorna Bedrock Runtime client"""
        return self.bedrock_runtime
    
    def get_s3_client(self):
        """Ritorna S3 client"""
        return self.s3_client
    
    def get_model_id(self) -> str:
        """Ritorna model ID configurato"""
        return self.model_id
    
    def get_bucket_name(self) -> str:
        """Ritorna S3 bucket name"""
        return self.bucket_name
    
    def get_region(self) -> str:
        """Ritorna AWS region"""
        return self.region


# Singleton globale - istanza unica di configurazione
try:
    bedrock_config = AWSBedrockConfig()
except Exception as e:
    logger.error(f"Failed to initialize AWS Bedrock config: {e}")
    bedrock_config = None
