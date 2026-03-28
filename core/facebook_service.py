"""
FACEBOOK SERVICE — Genesi
Integrazione Facebook per partecipazione attiva nei gruppi.

Modalità operative:
  semi  — Genesi propone post → admin approva → posta. Risponde a commenti in auto.
  full  — Genesi fa tutto: crea post, risponde, segue persone, entra in conversazioni.

Human mimicry: ritardi casuali, typing carattere per carattere, nessuna azione notturna.
Fail-silent su ogni errore — il heartbeat non blocca mai il processo principale.

Session persistence:
  - Login manuale iniziale tramite browser headful (admin panel).
  - Cookie salvati in storage, riusati a ogni heartbeat con browser headless.
"""

import asyncio
import json
import logging
import os
import random
import uuid
from datetime import datetime, time as dtime
from typing import Optional

from core.log import log as _slog
from core.storage import storage

logger = logging.getLogger("genesi")

# ── Configurazione ─────────────────────────────────────────────────────────────
FB_CONFIG_KEY   = "facebook:config"
FB_SESSION_KEY  = "facebook:session"
FB_PENDING_KEY  = "facebook:pending_posts"
FB_REPLIES_KEY  = "facebook:pending_replies"   # risposte in attesa approvazione
FB_LOG_KEY      = "facebook:interaction_log"
FB_LIKES_KEY    = "facebook:seen_likes"        # like già visti per post

MAX_LOG_ENTRIES   = 300
MAX_PENDING       = 50
_NIGHT_START      = 0    # ora inizio no-activity
_NIGHT_END        = 7    # ora fine no-activity

_DEFAULT_CONFIG = {
    "mode":                   "semi",      # "semi" | "full"
    "enabled":                False,
    "account_email":          "",
    "groups":                 ["Sei di Imola se..."],
    "heartbeat_interval_min": 7200,        # 2 ore
    "heartbeat_interval_max": 14400,       # 4 ore
    "max_posts_per_day":      2,
    "max_comments_per_hb":    5,
    "post_prompt_style":      "locale",    # "locale" | "tech" | "relazionale"
}

# Stili di post per il prompt LLM
_POST_PROMPTS = {
    "locale": (
        "Sei Giada, una persona di Imola che partecipa a un gruppo Facebook locale. "
        "Scrivi un post corto (2-3 righe max), in italiano colloquiale, autentico, "
        "contestualizzato agli ultimi argomenti discussi nel gruppo. "
        "Usa un tono amichevole e diretto. Niente maiuscole formali all'inizio, "
        "qualche abbreviazione tipica dei social (x = per, cmq, nn, ecc.). "
        "NON fare il professore. NON usare liste puntate. NON essere prolisso."
    ),
    "tech": (
        "Sei Giada, appassionata di tecnologia e AI. "
        "Scrivi un post conciso su un tema tech o digitale, "
        "in italiano, tono conversazionale."
    ),
    "relazionale": (
        "Sei Giada, una persona empatica e curiosa. "
        "Scrivi un post che inviti alla conversazione, in italiano colloquiale."
    ),
    "timeline": (
        "Sei Giada, una ragazza di Imola con una vita normale. "
        "Scrivi un post per la tua bacheca Facebook personale (1-3 righe), "
        "come se stessi condividendo un pensiero, un'esperienza della giornata, "
        "o una domanda per i tuoi amici. Tono spontaneo, colloquiale, autentico. "
        "Puoi usare emoji con moderazione. NON sembrare un bot o un sito di notizie."
    ),
}

_COMMENT_PROMPT = (
    "Sei Giada, una persona di Imola che partecipa a un gruppo Facebook. "
    "Hai letto questo post e i commenti esistenti. "
    "Scrivi UN commento breve (1-2 righe), naturale, in italiano colloquiale. "
    "Porta un contributo reale (aneddoto, domanda, opinione) — non solo 'che bello!'. "
    "Niente emoji eccessivi. Non presentarti mai come AI."
)


class FacebookService:
    """
    Servizio Facebook per Genesi.
    Tutti i metodi pubblici sono fail-silent.
    """

    def __init__(self):
        self._pw          = None   # playwright instance
        self._browser     = None
        self._context     = None
        self._page        = None
        self._running     = False  # lock anti-concorrenza heartbeat
        self._hb_count    = 0
        self._posts_today = 0
        self._today_date  = datetime.utcnow().date()

    # ════════════════════════════════════════════════════════════════════════
    # Config helpers
    # ════════════════════════════════════════════════════════════════════════

    async def _load_config(self) -> dict:
        cfg = await storage.load(FB_CONFIG_KEY, default={})
        if not isinstance(cfg, dict):
            cfg = {}
        return {**_DEFAULT_CONFIG, **cfg}

    async def _save_config(self, cfg: dict) -> None:
        await storage.save(FB_CONFIG_KEY, cfg)

    async def set_mode(self, mode: str) -> bool:
        """Cambia la modalità operativa. Ritorna True se ok."""
        if mode not in ("semi", "full"):
            return False
        cfg = await self._load_config()
        cfg["mode"] = mode
        cfg["mode_changed_at"] = datetime.utcnow().isoformat()
        await self._save_config(cfg)
        _slog("FACEBOOK_MODE_CHANGED", mode=mode)
        return True

    async def set_enabled(self, enabled: bool) -> None:
        cfg = await self._load_config()
        cfg["enabled"] = enabled
        await self._save_config(cfg)
        _slog("FACEBOOK_ENABLED", enabled=enabled)

    async def add_group(self, group_name: str) -> None:
        cfg = await self._load_config()
        if group_name not in cfg["groups"]:
            cfg["groups"].append(group_name)
            await self._save_config(cfg)

    async def remove_group(self, group_name: str) -> None:
        cfg = await self._load_config()
        cfg["groups"] = [g for g in cfg["groups"] if g != group_name]
        await self._save_config(cfg)

    # ════════════════════════════════════════════════════════════════════════
    # Browser lifecycle
    # ════════════════════════════════════════════════════════════════════════

    async def _ensure_browser(self, headless: bool = True) -> bool:
        """Avvia Playwright se non già attivo. Fail-silent: ritorna False se fallisce."""
        try:
            if self._browser and self._browser.is_connected():
                return True
            from playwright.async_api import async_playwright
            try:
                from playwright_stealth import stealth_async
                self._stealth = stealth_async
            except ImportError:
                self._stealth = None

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1366,768",
                ],
            )
            self._context = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1366, "height": 768},
                locale="it-IT",
                timezone_id="Europe/Rome",
            )
            # Maschera navigator.webdriver
            await self._context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            self._page = await self._context.new_page()
            if self._stealth:
                await self._stealth(self._page)
            return True
        except Exception as e:
            _slog("FACEBOOK_BROWSER_START_FAIL", err_type=type(e).__name__, err=str(e)[:200])
            logger.warning("FACEBOOK_BROWSER_START_FAIL err=%s(%s)", type(e).__name__, e)
            return False

    async def _reset_browser_context(self) -> None:
        """
        Chiude il context corrente e ne apre uno nuovo (stesso browser).
        Usato prima di ogni approvazione manuale per avere un context pulito
        senza cookie residui accumulati dalla sessione precedente.
        """
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            self._context = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1366, "height": 768},
                locale="it-IT",
                timezone_id="Europe/Rome",
            )
            await self._context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            self._page = await self._context.new_page()
            if self._stealth:
                await self._stealth(self._page)
            _slog("FACEBOOK_CONTEXT_RESET")
        except Exception as e:
            _slog("FACEBOOK_CONTEXT_RESET_FAIL", err=str(e)[:200])

    async def close_browser(self) -> None:
        """Chiude browser e libera risorse. Chiamato allo shutdown."""
        try:
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._context = None
        self._page    = None
        self._pw      = None

    # ════════════════════════════════════════════════════════════════════════
    # Session persistence
    # ════════════════════════════════════════════════════════════════════════

    async def load_session(self) -> bool:
        """Inietta cookies salvati nel context. Ritorna True se cookies trovati."""
        try:
            sess = await storage.load(FB_SESSION_KEY, default={})
            cookies = sess.get("cookies", [])
            if not cookies:
                _slog("FACEBOOK_LOAD_SESSION_EMPTY")
                return False
            # Normalizza in caso siano stati salvati in vecchio formato Firefox
            normalized = [self._normalize_cookie(c) for c in cookies]
            await self._context.add_cookies(normalized)
            _slog("FACEBOOK_LOAD_SESSION_OK", count=len(normalized))
            return True
        except Exception as e:
            _slog("FACEBOOK_LOAD_SESSION_FAIL", err_type=type(e).__name__, err=str(e)[:200])
            return False

    async def save_session(self) -> None:
        """Serializza cookies del context corrente e li salva."""
        try:
            cookies = await self._context.cookies()
            await storage.save(FB_SESSION_KEY, {
                "cookies":  cookies,
                "saved_at": datetime.utcnow().isoformat(),
            })
        except Exception as e:
            logger.debug("FACEBOOK_SAVE_SESSION_FAIL err=%s", e)

    @staticmethod
    def _normalize_cookie(c: dict) -> dict:
        """
        Converte un cookie da formato Firefox/Cookie-Editor a formato Playwright.
        Firefox:   expirationDate (float), sameSite "no_restriction", campi extra
        Playwright: expires (float), sameSite "None"|"Lax"|"Strict", solo campi noti
        """
        _sameSite_map = {
            "no_restriction": "None",
            "lax":            "Lax",
            "strict":         "Strict",
            "none":           "None",
        }
        result: dict = {
            "name":     c.get("name", ""),
            "value":    c.get("value", ""),
            "domain":   c.get("domain", ""),
            "path":     c.get("path", "/"),
            "secure":   bool(c.get("secure", False)),
            "httpOnly": bool(c.get("httpOnly", False)),
        }
        # expires: Playwright vuole Unix timestamp float
        exp = c.get("expires") or c.get("expirationDate")
        if exp is not None:
            result["expires"] = float(exp)
        # sameSite
        ss_raw = str(c.get("sameSite", "None")).lower()
        result["sameSite"] = _sameSite_map.get(ss_raw, "None")
        return result

    async def import_session_from_json(self, cookies: list) -> bool:
        """
        Importa cookies da JSON esterno (es. da estensione Cookie-Editor).
        Normalizza automaticamente dal formato Firefox a quello Playwright.
        """
        try:
            normalized = [self._normalize_cookie(c) for c in cookies]
            await storage.save(FB_SESSION_KEY, {
                "cookies":  normalized,
                "saved_at": datetime.utcnow().isoformat(),
                "source":   "manual_import",
            })
            _slog("FACEBOOK_SESSION_IMPORTED", count=len(normalized))
            return True
        except Exception as e:
            logger.warning("FACEBOOK_IMPORT_SESSION_FAIL err=%s", e)
            return False

    async def is_logged_in(self) -> bool:
        """Verifica se la sessione è autenticata navigando su facebook.com."""
        try:
            if self._page is None:
                _slog("FACEBOOK_IS_LOGGED_IN_FAIL", reason="page_is_None")
                return False
            await self._page.goto("https://www.facebook.com/", timeout=20000)
            await asyncio.sleep(2)
            url = self._page.url
            _slog("FACEBOOK_IS_LOGGED_IN_URL", url=url[:120])
            # Se redirect a /login → non loggato
            if "/login" in url or "/checkpoint" in url:
                _slog("FACEBOOK_IS_LOGGED_IN_FAIL", reason="redirect_login", url=url[:120])
                return False
            # Controlla presenza nav bar (indicatore login)
            nav = await self._page.query_selector('[aria-label="Facebook"]')
            logged = nav is not None
            _slog("FACEBOOK_IS_LOGGED_IN_RESULT", logged=logged, nav_found=(nav is not None))
            return logged
        except Exception as e:
            _slog("FACEBOOK_IS_LOGGED_IN_EXCEPTION", err_type=type(e).__name__, err=str(e)[:200])
            return False

    async def manual_login_session(self) -> dict:
        """
        Avvia browser headful per login manuale dell'admin.
        Fa polling ogni 5s per max 5 minuti. Quando rileva login → salva sessione.
        NOTA: richiede display sul VPS (Xvfb) o va eseguito localmente.
        """
        try:
            ok = await self._ensure_browser(headless=False)
            if not ok:
                return {"success": False, "message": "Impossibile avviare il browser."}
            await self._page.goto("https://www.facebook.com/login", timeout=20000)
            # Polling 5s × 60 = 5 minuti
            for _ in range(60):
                await asyncio.sleep(5)
                if await self.is_logged_in():
                    await self.save_session()
                    _slog("FACEBOOK_MANUAL_LOGIN_OK")
                    return {"success": True, "message": "Login completato. Sessione salvata."}
            return {"success": False, "message": "Timeout: login non rilevato entro 5 minuti."}
        except Exception as e:
            return {"success": False, "message": f"Errore: {e}"}

    # ════════════════════════════════════════════════════════════════════════
    # Human mimicry
    # ════════════════════════════════════════════════════════════════════════

    async def _human_delay(self, min_s: float = 2.0, max_s: float = 8.0) -> None:
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def _type_humanlike(self, locator, text: str) -> None:
        """Digita carattere per carattere con delay random tra keystroke."""
        for char in text:
            await locator.type(char, delay=random.randint(50, 220))

    def _is_night_window(self) -> bool:
        """Ritorna True se siamo nella finestra notturna (00-07)."""
        h = datetime.now().hour
        return h < _NIGHT_END or h >= 23

    def _reset_daily_counter(self) -> None:
        today = datetime.utcnow().date()
        if today != self._today_date:
            self._posts_today = 0
            self._today_date  = today

    # ════════════════════════════════════════════════════════════════════════
    # Feed reading
    # ════════════════════════════════════════════════════════════════════════

    async def read_group_feed(self, group_name: str, max_posts: int = 8) -> list:
        """
        Legge i post recenti di un gruppo.
        group_name può essere un URL diretto (https://www.facebook.com/groups/ID)
        oppure un nome da cercare.
        Ritorna lista di dict: {author, text, timestamp, url}.
        """
        posts = []
        try:
            # Naviga direttamente se è un URL
            if group_name.startswith("http") or group_name.startswith("/groups/"):
                group_url = group_name if group_name.startswith("http") else f"https://www.facebook.com{group_name}"
                await self._page.goto(group_url, timeout=20000)
                await self._human_delay(2, 4)
            else:
                # Cerca il gruppo tramite la barra di ricerca
                await self._page.goto("https://www.facebook.com/", timeout=20000)
                await self._human_delay(2, 4)

                search_box = await self._page.query_selector('input[placeholder*="Cerca"]')
                if not search_box:
                    search_box = await self._page.query_selector('[aria-label*="Cerca"]')
                if search_box:
                    await search_box.click()
                    await self._type_humanlike(search_box, group_name)
                    await self._human_delay(1, 2)
                    await self._page.keyboard.press("Enter")
                    await self._human_delay(2, 4)

                    groups_tab = await self._page.query_selector('[data-key="groups"]')
                    if groups_tab:
                        await groups_tab.click()
                        await self._human_delay(1.5, 3)

                    first_result = await self._page.query_selector('[data-testid="search_result"] a')
                    if first_result:
                        await first_result.click()
                        await self._human_delay(3, 5)
                    else:
                        links = await self._page.query_selector_all("a[href*='/groups/']")
                        if links:
                            await links[0].click()
                            await self._human_delay(3, 5)

            # Raccogli i post visibili
            post_elements = await self._page.query_selector_all('[data-pagelet*="FeedUnit"]')
            if not post_elements:
                post_elements = await self._page.query_selector_all('[role="article"]')

            for el in post_elements[:max_posts]:
                try:
                    text_el = await el.query_selector('[data-ad-comet-preview="message"], [dir="auto"]')
                    text = await text_el.inner_text() if text_el else ""
                    author_el = await el.query_selector('a[href*="/profile"], strong a, h2 a')
                    author = await author_el.inner_text() if author_el else "Anonimo"
                    link_el = await el.query_selector('a[href*="/posts/"], a[href*="/permalink/"]')
                    url = await link_el.get_attribute("href") if link_el else ""
                    if text.strip():
                        posts.append({
                            "author": author.strip()[:60],
                            "text":   text.strip()[:400],
                            "url":    url or "",
                            "group":  group_name,
                        })
                except Exception:
                    continue

            _slog("FACEBOOK_FEED_READ", group=group_name, posts_found=len(posts))
        except Exception as e:
            logger.warning("FACEBOOK_FEED_READ_FAIL group=%s err=%s(%s)",
                           group_name, type(e).__name__, e)
        return posts

    # ════════════════════════════════════════════════════════════════════════
    # LLM content generation
    # ════════════════════════════════════════════════════════════════════════

    async def _generate_post_content(self, group_name: str, feed_context: list, style: str = "locale") -> str:
        """Genera testo del post via LLM contestualizzato al feed del gruppo."""
        try:
            from core.llm_service import llm_service
            context_text = "\n".join(
                f"- {p['author']}: {p['text'][:150]}"
                for p in feed_context[:6]
            ) if feed_context else "(feed non disponibile)"

            system = _POST_PROMPTS.get(style, _POST_PROMPTS["locale"])
            user_msg = (
                f"Gruppo Facebook: '{group_name}'\n\n"
                f"Ultimi post nel gruppo:\n{context_text}\n\n"
                "Scrivi UN post originale per questo gruppo (2-3 righe max)."
            )
            result = await llm_service._call_model(
                "openai/gpt-4o-mini", system, user_msg,
                user_id="facebook_system", route="memory",
            )
            return (result or "").strip()
        except Exception as e:
            logger.debug("FACEBOOK_GENERATE_POST_FAIL err=%s", e)
            return ""

    async def _generate_reply(self, post_text: str, comment_author: str, comment_text: str) -> str:
        """Genera risposta a un commento ricevuto su un post di Giada."""
        try:
            from core.llm_service import llm_service
            system = (
                "Sei Giada, una ragazza di Imola. Qualcuno ha commentato un tuo post su Facebook. "
                "Rispondi al commento in modo naturale, caldo, in italiano colloquiale (1-2 righe max). "
                "Sii autentica: ringrazia se è un complimento, rispondi con curiosità se è una domanda, "
                "continua la conversazione se è un'opinione. "
                "Niente emoji eccessivi. Non presentarti mai come AI."
            )
            user_msg = (
                f"Tuo post:\n{post_text[:200]}\n\n"
                f"Commento di {comment_author}:\n{comment_text[:200]}\n\n"
                "Scrivi UNA risposta breve e naturale."
            )
            result = await llm_service._call_model(
                "openai/gpt-4o-mini", system, user_msg,
                user_id="facebook_system", route="memory",
            )
            return (result or "").strip()
        except Exception as e:
            logger.debug("FACEBOOK_GENERATE_REPLY_FAIL err=%s", e)
            return ""

    async def _generate_like_thanks(self, new_likes: int) -> str:
        """Genera un commento di ringraziamento per i nuovi mi piace ricevuti."""
        try:
            from core.llm_service import llm_service
            system = (
                "Sei Giada, una ragazza di Imola. Il tuo post ha ricevuto dei mi piace. "
                "Scrivi UN commento di ringraziamento breve (1 riga), genuino, in italiano colloquiale. "
                "NON dire 'grazie per il mi piace'. Sii naturale, come farebbe una persona vera. "
                "Puoi usare un emoji con moderazione."
            )
            user_msg = f"Hai ricevuto {new_likes} nuovi mi piace sul post. Ringrazia in modo spontaneo."
            result = await llm_service._call_model(
                "openai/gpt-4o-mini", system, user_msg,
                user_id="facebook_system", route="memory",
            )
            return (result or "").strip()
        except Exception:
            return ""

    async def _generate_comment(self, post_text: str, existing_comments: list) -> str:
        """Genera commento rilevante per un post."""
        try:
            from core.llm_service import llm_service
            existing_text = "\n".join(f"- {c}" for c in existing_comments[:5]) if existing_comments else "(nessun commento)"
            user_msg = (
                f"Post:\n{post_text[:300]}\n\n"
                f"Commenti esistenti:\n{existing_text}\n\n"
                "Scrivi UN commento breve (1-2 righe)."
            )
            result = await llm_service._call_model(
                "openai/gpt-4o-mini", _COMMENT_PROMPT, user_msg,
                user_id="facebook_system", route="memory",
            )
            return (result or "").strip()
        except Exception as e:
            logger.debug("FACEBOOK_GENERATE_COMMENT_FAIL err=%s", e)
            return ""

    # ════════════════════════════════════════════════════════════════════════
    # Post actions
    # ════════════════════════════════════════════════════════════════════════

    async def post_to_group(self, group_name: str, content: str) -> dict:
        """Naviga al gruppo e posta il contenuto. group_name può essere URL o nome."""
        result = {"success": False, "post_url": "", "error": ""}
        try:
            if group_name.startswith("http") or group_name.startswith("/groups/"):
                group_url = group_name if group_name.startswith("http") else f"https://www.facebook.com{group_name}"
                await self._page.goto(group_url, timeout=20000)
                await self._human_delay(2, 5)
            else:
                await self._page.goto("https://www.facebook.com/", timeout=20000)
                await self._human_delay(2, 5)

                search_box = await self._page.query_selector('input[placeholder*="Cerca"]')
                if not search_box:
                    search_box = await self._page.query_selector('[aria-label*="Cerca"]')
                if not search_box:
                    result["error"] = "Search box non trovata"
                    return result

                await search_box.click()
                await self._type_humanlike(search_box, group_name)
                await self._human_delay(1, 2)
                await self._page.keyboard.press("Enter")
                await self._human_delay(2, 4)

                links = await self._page.query_selector_all("a[href*='/groups/']")
                if not links:
                    result["error"] = "Gruppo non trovato"
                    return result
                await links[0].click()
                await self._human_delay(3, 6)

            # Trova il box "Scrivi qualcosa"
            write_box = await self._page.query_selector('[aria-label*="Scrivi qualcosa"]')
            if not write_box:
                write_box = await self._page.query_selector('[data-testid="status-attachment-mentions-input"]')
            if not write_box:
                write_box = await self._page.query_selector('[role="textbox"]')
            if not write_box:
                result["error"] = "Box post non trovato"
                return result

            await write_box.click()
            await self._human_delay(1, 2)
            await self._type_humanlike(write_box, content)
            await self._human_delay(2, 4)

            # Clicca Pubblica
            publish_btn = await self._page.query_selector('[aria-label="Pubblica"]')
            if not publish_btn:
                publish_btn = await self._page.query_selector('button[type="submit"]')
            if publish_btn:
                await publish_btn.click()
                await self._human_delay(3, 5)
                result["success"] = True
                result["post_url"] = self._page.url
                _slog("FACEBOOK_POSTED", group=group_name, chars=len(content))
            else:
                result["error"] = "Bottone Pubblica non trovato"
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"
            logger.warning("FACEBOOK_POST_FAIL err=%s", result["error"])
        return result

    async def _dismiss_blocking_dialogs(self) -> None:
        """
        Chiude popup bloccanti di Facebook (es. 'unione pubblico', cookie consent, ecc.)
        prima di interagire con la pagina. Fail-silent.
        """
        try:
            # Prova prima Escape — chiude la maggior parte dei dialog
            await self._page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

            # Cerca pulsanti di chiusura comuni nei dialog
            close_selectors = [
                '[aria-label="Chiudi"]',
                '[aria-label="Close"]',
                '[aria-label="Non ora"]',
                '[aria-label="Ignora"]',
                'div[role="dialog"] [role="button"][aria-label]',  # primo button con label nel dialog
            ]
            for sel in close_selectors:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn:
                        await btn.click(timeout=3000)
                        await asyncio.sleep(0.5)
                        _slog("FACEBOOK_DIALOG_DISMISSED", selector=sel)
                        break
                except Exception:
                    continue
        except Exception:
            pass

    async def post_to_timeline(self, content: str, mention: str = "") -> dict:
        """
        Posta sulla bacheca personale di Giada.
        Se mention è specificato (es. 'Alfio Turrisi'), tenta di taggare la persona.
        """
        result = {"success": False, "post_url": "", "error": ""}
        try:
            await self._page.goto("https://www.facebook.com/", timeout=20000)
            await self._human_delay(2, 4)

            # 1. Clicca il pulsante "A cosa stai pensando?" via JS per bypassare overlay
            open_btn = await self._page.query_selector(
                '[aria-label="Crea un post"] [role="button"]:not([aria-label])'
            )
            if not open_btn:
                open_btn = await self._page.query_selector('[aria-label="Crea un post"] [role="button"]')
            if not open_btn:
                result["error"] = "Pulsante apertura post non trovato"
                return result

            # Usa JS click per bypassare overlay che intercetta eventi pointer
            await self._page.evaluate('btn => btn.click()', open_btn)
            await self._human_delay(1.5, 2.5)

            # 2. Chiudi popup "unione pubblico" (aria-label="Non ora" o "Ok")
            for dismiss_label in ('Non ora', 'Ok'):
                dismiss_btn = await self._page.query_selector(f'[aria-label="{dismiss_label}"]')
                if dismiss_btn:
                    try:
                        await self._page.evaluate('b => b.click()', dismiss_btn)
                        await asyncio.sleep(0.8)
                        _slog("FACEBOOK_POPUP_DISMISSED", label=dismiss_label)
                    except Exception:
                        pass
                    break

            await self._human_delay(0.5, 1.5)

            # 3. Trova il textbox nel dialog di composizione
            write_box = await self._page.query_selector('[role="textbox"][contenteditable="true"]')
            if not write_box:
                result["error"] = "Textbox composizione non trovato"
                return result

            await self._page.evaluate('el => el.focus()', write_box)
            await self._human_delay(0.5, 1)

            # 4. Testo (con menzione opzionale)
            if mention:
                await self._type_humanlike(write_box, f"@{mention}")
                await self._human_delay(1.5, 3)
                suggestion = await self._page.query_selector('[role="option"]')
                if suggestion:
                    await self._page.evaluate('el => el.click()', suggestion)
                    await self._human_delay(0.5, 1)
                    await self._type_humanlike(write_box, f" {content}")
                else:
                    await self._type_humanlike(write_box, f" {content}")
            else:
                await self._type_humanlike(write_box, content)

            await self._human_delay(2, 4)

            # 5. Pubblica
            publish_btn = await self._page.query_selector('[aria-label="Pubblica"]')
            if not publish_btn:
                publish_btn = await self._page.query_selector('[aria-label="Posta"]')
            if not publish_btn:
                result["error"] = "Bottone Pubblica non trovato"
                return result

            await self._page.evaluate('btn => btn.click()', publish_btn)
            await self._human_delay(3, 5)
            result["success"] = True
            result["post_url"] = self._page.url
            _slog("FACEBOOK_TIMELINE_POSTED", chars=len(content), mention=mention or "none")
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"
            logger.warning("FACEBOOK_TIMELINE_POST_FAIL err=%s", result["error"])
        return result

    async def read_timeline_feed(self, max_posts: int = 5) -> list:
        """
        Legge i post recenti dal feed personale di Giada (home Facebook).
        Utile come contesto per generare post sulla bacheca.
        """
        posts = []
        try:
            await self._page.goto("https://www.facebook.com/", timeout=20000)
            await self._human_delay(2, 4)
            # Scrolla un po' per caricare i post
            await self._page.mouse.wheel(0, 800)
            await self._human_delay(1, 2)

            post_elements = await self._page.query_selector_all('[role="article"]')
            for el in post_elements[:max_posts]:
                try:
                    text_el = await el.query_selector('[dir="auto"]')
                    text = await text_el.inner_text() if text_el else ""
                    author_el = await el.query_selector('h2 a, strong a')
                    author = await author_el.inner_text() if author_el else ""
                    if text.strip() and len(text.strip()) > 10:
                        posts.append({
                            "author": author.strip()[:60],
                            "text":   text.strip()[:300],
                            "group":  "timeline",
                        })
                except Exception:
                    continue
        except Exception as e:
            logger.debug("FACEBOOK_TIMELINE_FEED_FAIL err=%s", e)
        return posts

    async def comment_on_post(self, post_url: str, comment: str) -> bool:
        """Naviga al post e pubblica un commento."""
        try:
            if not post_url:
                return False
            full_url = post_url if post_url.startswith("http") else f"https://www.facebook.com{post_url}"
            await self._page.goto(full_url, timeout=20000)
            await self._human_delay(2, 4)

            comment_box = await self._page.query_selector('[aria-label*="commento"]')
            if not comment_box:
                comment_box = await self._page.query_selector('[data-testid*="comment"] [role="textbox"]')
            if not comment_box:
                return False

            await comment_box.click()
            await self._human_delay(0.5, 1.5)
            await self._type_humanlike(comment_box, comment)
            await self._human_delay(1, 2)
            await self._page.keyboard.press("Enter")
            await self._human_delay(2, 3)
            _slog("FACEBOOK_COMMENT_POSTED", url=post_url[:60], chars=len(comment))
            return True
        except Exception as e:
            logger.debug("FACEBOOK_COMMENT_FAIL err=%s", e)
            return False

    # ════════════════════════════════════════════════════════════════════════
    # Pending posts (semi-auto flow)
    # ════════════════════════════════════════════════════════════════════════
    # Risposta ai commenti sui propri post
    # ════════════════════════════════════════════════════════════════════════

    async def _get_own_user_id(self) -> str:
        """Legge l'ID utente Facebook dai cookie salvati (c_user)."""
        try:
            sess = await storage.load(FB_SESSION_KEY, default={})
            for c in sess.get("cookies", []):
                if c.get("name") == "c_user":
                    return str(c.get("value", ""))
        except Exception:
            pass
        return ""

    @staticmethod
    def _clean_post_url(url: str) -> str:
        """Rimuove parametri extra dall'URL del post (comment_id, __cft__, __tn__, ecc.)."""
        import urllib.parse as up
        try:
            p = up.urlparse(url)
            qs = up.parse_qs(p.query, keep_blank_values=True)
            # Tieni solo i parametri rilevanti per identificare il post
            keep = {k: v for k, v in qs.items() if k in ("story_fbid", "id", "v")}
            clean_query = up.urlencode(keep, doseq=True)
            return up.urlunparse((p.scheme, p.netloc, p.path, "", clean_query, ""))
        except Exception:
            return url

    async def read_own_recent_post_urls(self, max_posts: int = 5) -> list:
        """
        Naviga al profilo di Giada e restituisce gli URL dei post recenti (senza comment_id).
        """
        urls = []
        try:
            user_id = await self._get_own_user_id()
            profile_url = (
                f"https://www.facebook.com/profile.php?id={user_id}"
                if user_id else "https://www.facebook.com/"
            )
            await self._page.goto(profile_url, timeout=20000)
            await self._human_delay(2, 4)

            # Trova link ai singoli post (permalink o /posts/)
            links = await self._page.evaluate('''() => {
                const anchors = document.querySelectorAll('a[href*="/posts/"], a[href*="story_fbid="]');
                return [...anchors].map(a => a.href);
            }''')
            seen = set()
            for url in links:
                if not url or "facebook.com" not in url:
                    continue
                clean = self._clean_post_url(url)
                if clean not in seen:
                    seen.add(clean)
                    urls.append(clean)
                if len(urls) >= max_posts:
                    break
            _slog("FACEBOOK_OWN_POSTS_FOUND", count=len(urls))
        except Exception as e:
            logger.debug("FACEBOOK_OWN_POSTS_FAIL err=%s", e)
        return urls

    async def read_post_comments(self, post_url: str) -> list:
        """
        Naviga a un post e restituisce i commenti: [{author, text, element_id}].
        Esclude i commenti già di Giada (risposte già date).
        """
        comments = []
        try:
            full_url = post_url if post_url.startswith("http") else f"https://www.facebook.com{post_url}"
            await self._page.goto(full_url, timeout=20000)
            await self._human_delay(2, 4)

            # Espandi commenti se c'è un pulsante "Visualizza altri commenti"
            for _ in range(2):
                more_btn = await self._page.query_selector(
                    '[aria-label*="Visualizza altri commenti"], [aria-label*="commenti precedenti"]'
                )
                if more_btn:
                    await self._page.evaluate('b => b.click()', more_btn)
                    await asyncio.sleep(1)
                else:
                    break

            # Facebook: i commenti sono [role="article"] con aria-label "Commento di X"
            raw = await self._page.evaluate("""() => {
                return Array.from(document.querySelectorAll('[role="article"]'))
                    .filter(a => {
                        const lbl = a.getAttribute('aria-label') || '';
                        return lbl.startsWith('Commento di') || lbl.startsWith('Comment by');
                    })
                    .map(a => {
                        // Autore dall'aria-label: "Commento di Alfio Turrisi 11 minuti fa"
                        const lbl = a.getAttribute('aria-label') || '';
                        const authorMatch = lbl.match(/^(?:Commento di|Comment by)\\s+(.+?)\\s+\\d/);
                        const author = authorMatch ? authorMatch[1] : '';
                        // Testo: cerca dir=auto nel commento, prendi il più lungo
                        const dirEls = Array.from(a.querySelectorAll('[dir="auto"]'));
                        const texts = dirEls.map(e => e.textContent.trim()).filter(t => t.length > 1);
                        const text = texts.sort((a,b) => b.length-a.length)[0] || '';
                        return { author, text: text.substring(0, 300) };
                    })
                    .filter(c => c.author && c.text);
            }""")

            # Filtra: tieni solo commenti non di Giada, marca quelli già risposti per commento specifico
            giada_names = {"giada genesi", "giada", "g.genesi"}
            replied_keys = set()   # chiave = author|text[:50] — per commento specifico, non per autore
            result_list = []
            for c in raw:
                author_lower = c["author"].lower()
                if any(g in author_lower for g in giada_names):
                    # Commento di Giada → segna il commento PRECEDENTE come già risposto
                    if result_list:
                        prev = result_list[-1]
                        replied_keys.add(f"{prev['author']}|{prev['text'][:50]}")
                else:
                    result_list.append({"author": c["author"], "text": c["text"], "post_url": full_url})

            # Rimuovi solo i commenti specifici già risposti (altri dello stesso autore passano)
            comments = [c for c in result_list if f"{c['author']}|{c['text'][:50]}" not in replied_keys]
            _slog("FACEBOOK_POST_COMMENTS", url=post_url[:80], total=len(raw), unreplied=len(comments))
        except Exception as e:
            logger.debug("FACEBOOK_READ_COMMENTS_FAIL url=%s err=%s", post_url[:60], e)
        return comments

    async def reply_to_comments_on_own_posts(self, mode: str = "semi", max_replies: int = 3) -> int:
        """
        Legge i post recenti di Giada, trova commenti senza risposta e risponde in auto.
        Le risposte ai commenti sono sempre automatiche (sia semi che full).
        I nuovi mi piace vengono ringraziati automaticamente.
        """
        count = 0
        try:
            replied_log = await storage.load("facebook:replied_comments", default={"ids": []})
            replied_ids = set(replied_log.get("ids", []))

            post_urls = await self.read_own_recent_post_urls(max_posts=4)
            if not post_urls:
                _slog("FACEBOOK_REPLY_SKIP", reason="no_own_posts_found")
                return 0

            for post_url in post_urls:
                if count >= max_replies:
                    break

                # Like detection: ringrazia i nuovi mi piace in auto
                post_id = post_url.split("story_fbid=")[-1][:20] if "story_fbid=" in post_url else post_url[-20:]
                new_likes = await self.check_new_likes(post_url, post_id)
                if new_likes > 0:
                    like_reply = await self._generate_like_thanks(new_likes)
                    if like_reply:
                        ok = await self._post_reply_to_comment(post_url, "__likes__", like_reply)
                        if ok:
                            _slog("FACEBOOK_LIKE_THANKS_SENT", post=post_url[:60],
                                  new_likes=new_likes, chars=len(like_reply))

                # Risposte ai commenti — sempre automatiche
                comments = await self.read_post_comments(post_url)
                post_text = ""
                try:
                    post_text_el = await self._page.query_selector('[dir="auto"]')
                    if post_text_el:
                        post_text = (await post_text_el.inner_text())[:200]
                except Exception:
                    pass

                for comment in comments:
                    if count >= max_replies:
                        break
                    comment_id = f"{comment['author']}|{comment['text'][:50]}|{post_url}"
                    if comment_id in replied_ids:
                        continue

                    reply_text = await self._generate_reply(post_text, comment["author"], comment["text"])
                    if not reply_text:
                        continue

                    ok = await self._post_reply_to_comment(post_url, comment["author"], reply_text)
                    if ok:
                        count += 1
                        replied_ids.add(comment_id)
                        await self._record_interaction("comment_replied",
                            author=comment["author"], content_preview=reply_text[:100])
                        _slog("FACEBOOK_REPLY_SENT", author=comment["author"],
                              post=post_url[:60], chars=len(reply_text))
                        # Metti mi piace al commento (pagina già aperta)
                        await self._human_delay(1, 2)
                        await self._like_comment(comment["author"])
                        await self._human_delay(10, 25)

            await storage.save("facebook:replied_comments", {"ids": list(replied_ids)[-500:]})
        except Exception as e:
            logger.warning("FACEBOOK_REPLY_ERROR err=%s(%s)", type(e).__name__, e)
        return count

    async def _post_reply_to_comment(self, post_url: str, target_author: str, reply_text: str) -> bool:
        """
        Naviga al post e inserisce una risposta DIRETTA al commento di target_author
        (usa il pulsante 'Rispondi' sul commento specifico).
        Se target_author è '__likes__' posta come commento generico.
        """
        try:
            full_url = post_url if post_url.startswith("http") else f"https://www.facebook.com{post_url}"
            await self._page.goto(full_url, timeout=20000)
            await self._human_delay(2, 3)

            reply_box = None

            if target_author != "__likes__":
                # Trova il commento specifico di target_author e clicca "Rispondi"
                articles = await self._page.query_selector_all('[role="article"]')
                for art in articles:
                    lbl = await art.get_attribute("aria-label") or ""
                    if target_author.lower() in lbl.lower() and "Commento di" in lbl:
                        # Clicca "Rispondi" dentro questo article
                        rispondi = await art.query_selector('[aria-label="Rispondi al commento"]')
                        if not rispondi:
                            rispondi = await art.query_selector('[aria-label*="Rispondi"]')
                        if rispondi:
                            await self._page.evaluate('el => el.click()', rispondi)
                            await self._human_delay(0.8, 1.5)
                            # Il textbox di risposta appare dentro o sotto l'article
                            reply_box = await self._page.query_selector('[role="textbox"][contenteditable="true"]')
                        break

            if not reply_box:
                # Fallback: usa il box commento principale (per __likes__ o se non trova Rispondi)
                activate_btn = await self._page.query_selector('[aria-label="Lascia un commento"][role="button"]')
                if activate_btn:
                    await self._page.evaluate('el => el.click()', activate_btn)
                    await self._human_delay(0.8, 1.5)
                reply_box = await self._page.query_selector('[aria-label="Scrivi un commento…"]')
                if not reply_box:
                    reply_box = await self._page.query_selector('[role="textbox"][contenteditable="true"]')

            if not reply_box:
                _slog("FACEBOOK_REPLY_BOX_NOT_FOUND", post_url=post_url[:60], author=target_author)
                return False

            await self._page.evaluate('el => el.focus()', reply_box)
            await self._human_delay(0.5, 1)
            await self._type_humanlike(reply_box, reply_text)
            await self._human_delay(1, 2)

            submit_btn = await self._page.query_selector('[aria-label="Pubblica commento"]')
            if not submit_btn:
                submit_btn = await self._page.query_selector('[aria-label="Invia commento"]')
            if submit_btn:
                await self._page.evaluate('el => el.click()', submit_btn)
            else:
                await self._page.keyboard.press("Enter")
            await self._human_delay(2, 3)
            return True
        except Exception as e:
            _slog("FACEBOOK_POST_REPLY_FAIL", err_type=type(e).__name__, err=str(e)[:150])
            return False

    async def _like_comment(self, target_author: str) -> bool:
        """
        Mette mi piace al commento di target_author sulla pagina corrente.
        Presuppone che la pagina sia già caricata sul post.
        """
        try:
            articles = await self._page.query_selector_all('[role="article"]')
            for art in articles:
                lbl = await art.get_attribute("aria-label") or ""
                if target_author.lower() in lbl.lower() and "Commento di" in lbl:
                    # Cerca il pulsante Mi piace dentro questo commento
                    like_btn = await art.query_selector('[aria-label="Mi piace al commento"]')
                    if not like_btn:
                        like_btn = await art.query_selector('[aria-label*="Mi piace"]')
                    if like_btn:
                        await self._page.evaluate('el => el.click()', like_btn)
                        await self._human_delay(0.5, 1.2)
                        _slog("FACEBOOK_COMMENT_LIKED", author=target_author)
                        return True
            return False
        except Exception as e:
            logger.debug("FACEBOOK_LIKE_COMMENT_FAIL author=%s err=%s", target_author, e)
            return False

    # ════════════════════════════════════════════════════════════════════════
    # Like detection
    # ════════════════════════════════════════════════════════════════════════

    async def read_post_like_count(self, post_url: str) -> int:
        """
        Legge il totale di reazioni sul post principale + sui commenti interni.
        Naviga al post se necessario (riusa la pagina se già caricata).
        """
        try:
            full_url = post_url if post_url.startswith("http") else f"https://www.facebook.com{post_url}"
            if self._page.url.rstrip("/") != full_url.rstrip("/"):
                await self._page.goto(full_url, timeout=20000)
                await self._human_delay(1, 2)

            total = await self._page.evaluate("""() => {
                let count = 0;
                // Reazioni sul post principale
                document.querySelectorAll(
                    '[aria-label*=\"Mi piace:\"], [aria-label*=\"Tutte le reazioni:\"], ' +
                    '[aria-label*=\"reazioni\"], [aria-label*=\"reaction\"]'
                ).forEach(btn => {
                    const m = (btn.getAttribute('aria-label') || '').match(/\\d+/);
                    if (m) count += parseInt(m[0]);
                });
                // Reazioni sui singoli commenti (articles interni)
                document.querySelectorAll('[role="article"]').forEach(art => {
                    art.querySelectorAll(
                        '[aria-label*=\"Mi piace:\"], [aria-label*=\"reazioni\"], [aria-label*=\"reaction\"]'
                    ).forEach(btn => {
                        const m = (btn.getAttribute('aria-label') || '').match(/\\d+/);
                        if (m) count += parseInt(m[0]);
                    });
                });
                return count;
            }""")
            return total
        except Exception:
            return 0

    async def check_new_likes(self, post_url: str, post_id: str) -> int:
        """
        Confronta il like count attuale con quello visto l'ultima volta.
        Ritorna il numero di NUOVI like (delta). Aggiorna il contatore salvato.
        """
        try:
            data = await storage.load(FB_LIKES_KEY, default={})
            prev = data.get(post_id, 0)
            current = await self.read_post_like_count(post_url)
            delta = max(0, current - prev)
            data[post_id] = current
            # Tieni max 200 post tracciati
            if len(data) > 200:
                keys = list(data.keys())
                for k in keys[:len(data) - 200]:
                    del data[k]
            await storage.save(FB_LIKES_KEY, data)
            if delta > 0:
                _slog("FACEBOOK_NEW_LIKES", post_id=post_id, delta=delta, total=current)
            return delta
        except Exception:
            return 0

    # ════════════════════════════════════════════════════════════════════════
    # Pending replies (semi-auto)
    # ════════════════════════════════════════════════════════════════════════

    async def queue_pending_reply(self, post_url: str, comment_author: str,
                                   comment_text: str, reply_text: str) -> str:
        """Accoda una risposta a un commento per approvazione admin."""
        try:
            data = await storage.load(FB_REPLIES_KEY, default={"replies": []})
            replies = data.get("replies", [])
            reply_id = str(uuid.uuid4())[:8]
            replies.append({
                "id":             reply_id,
                "post_url":       post_url,
                "comment_author": comment_author,
                "comment_text":   comment_text[:200],
                "reply_text":     reply_text,
                "status":         "pending",
                "created_at":     datetime.utcnow().isoformat(),
            })
            data["replies"] = replies[-MAX_PENDING:]
            await storage.save(FB_REPLIES_KEY, data)
            _slog("FACEBOOK_REPLY_QUEUED", id=reply_id, author=comment_author)
            return reply_id
        except Exception as e:
            logger.debug("FACEBOOK_QUEUE_REPLY_FAIL err=%s", e)
            return ""

    async def approve_pending_reply(self, reply_id: str) -> dict:
        """Approva e pubblica una risposta pending."""
        _slog("FACEBOOK_APPROVE_REPLY_START", reply_id=reply_id)
        try:
            data = await storage.load(FB_REPLIES_KEY, default={"replies": []})
            target = next((r for r in data.get("replies", [])
                           if r.get("id") == reply_id and r.get("status") == "pending"), None)
            if not target:
                return {"success": False, "error": "Risposta non trovata o già processata"}

            ok = await self._ensure_browser()
            if not ok:
                return {"success": False, "error": "Browser non disponibile"}
            await self.load_session()

            sent = await self._post_reply_to_comment(
                target["post_url"], target["comment_author"], target["reply_text"]
            )
            target["status"]       = "sent" if sent else "failed"
            target["processed_at"] = datetime.utcnow().isoformat()
            await storage.save(FB_REPLIES_KEY, data)

            _slog("FACEBOOK_APPROVE_REPLY_RESULT", reply_id=reply_id, sent=sent)
            if sent:
                # Marca il commento come già risposto
                replied_log = await storage.load("facebook:replied_comments", default={"ids": []})
                cid = f"{target['comment_author']}|{target['post_url']}"
                ids = replied_log.get("ids", [])
                if cid not in ids:
                    ids.append(cid)
                await storage.save("facebook:replied_comments", {"ids": ids[-500:]})
                await self._record_interaction("comment_replied",
                    author=target["comment_author"], content_preview=target["reply_text"][:100])
            return {"success": sent, "error": "" if sent else "Impossibile postare"}
        except Exception as e:
            _slog("FACEBOOK_APPROVE_REPLY_EXCEPTION", reply_id=reply_id, err=str(e)[:150])
            return {"success": False, "error": str(e)}

    async def reject_pending_reply(self, reply_id: str) -> bool:
        """Rifiuta una risposta pending."""
        try:
            data = await storage.load(FB_REPLIES_KEY, default={"replies": []})
            for r in data.get("replies", []):
                if r.get("id") == reply_id:
                    r["status"] = "rejected"
                    r["processed_at"] = datetime.utcnow().isoformat()
                    await storage.save(FB_REPLIES_KEY, data)
                    # Marca come già "gestito" per non riproporre
                    replied_log = await storage.load("facebook:replied_comments", default={"ids": []})
                    cid = f"{r['comment_author']}|{r['post_url']}"
                    ids = replied_log.get("ids", [])
                    if cid not in ids:
                        ids.append(cid)
                    await storage.save("facebook:replied_comments", {"ids": ids[-500:]})
                    return True
            return False
        except Exception:
            return False

    async def get_pending_replies(self) -> list:
        """Ritorna le risposte in stato pending."""
        try:
            data = await storage.load(FB_REPLIES_KEY, default={"replies": []})
            return [r for r in data.get("replies", []) if r.get("status") == "pending"]
        except Exception:
            return []

    # ════════════════════════════════════════════════════════════════════════

    async def queue_pending_post(self, content: str, group: str, mention: str = "") -> str:
        """Accoda un post in attesa di approvazione. Ritorna l'id generato."""
        try:
            data = await storage.load(FB_PENDING_KEY, default={"posts": []})
            posts = data.get("posts", [])
            post_id = str(uuid.uuid4())[:8]
            posts.append({
                "id":         post_id,
                "content":    content,
                "group":      group,
                "mention":    mention,
                "status":     "pending",
                "created_at": datetime.utcnow().isoformat(),
            })
            data["posts"] = posts[-MAX_PENDING:]
            await storage.save(FB_PENDING_KEY, data)
            _slog("FACEBOOK_POST_QUEUED", id=post_id, group=group, chars=len(content))
            return post_id
        except Exception as e:
            logger.debug("FACEBOOK_QUEUE_FAIL err=%s", e)
            return ""

    async def approve_pending_post(self, post_id: str) -> dict:
        """Recupera, posta e aggiorna il status del post pending."""
        _slog("FACEBOOK_APPROVE_START", post_id=post_id)
        try:
            data = await storage.load(FB_PENDING_KEY, default={"posts": []})
            posts = data.get("posts", [])
            target = next((p for p in posts if p.get("id") == post_id and p.get("status") == "pending"), None)
            if not target:
                _slog("FACEBOOK_APPROVE_NOT_FOUND", post_id=post_id,
                      total_posts=len(posts))
                return {"success": False, "error": "Post non trovato o già processato"}

            group = target.get("group", "")
            _slog("FACEBOOK_APPROVE_POSTING", post_id=post_id, group=group,
                  chars=len(target.get("content", "")))

            ok = await self._ensure_browser()
            if not ok:
                return {"success": False, "error": "Browser non disponibile"}

            # Ricrea sempre il context per avere un browser pulito con la sessione originale
            await self._reset_browser_context()
            await self.load_session()

            # Verifica login prima di tentare il post
            logged = await self.is_logged_in()
            if not logged:
                _slog("FACEBOOK_APPROVE_NOT_LOGGED_IN", post_id=post_id)
                return {"success": False, "error": "Sessione Facebook scaduta — reimporta i cookie dall'admin panel"}

            if group == "timeline":
                result = await self.post_to_timeline(target["content"], mention=target.get("mention", ""))
            else:
                result = await self.post_to_group(group, target["content"])

            _slog("FACEBOOK_APPROVE_RESULT", post_id=post_id, group=group,
                  success=result.get("success"), error=result.get("error", "")[:100])

            target["status"]       = "published" if result["success"] else "failed"
            target["published_at"] = datetime.utcnow().isoformat()
            target["post_url"]     = result.get("post_url", "")
            target["error"]        = result.get("error", "")
            await storage.save(FB_PENDING_KEY, data)
            if result["success"]:
                await self._record_interaction("post_published",
                    group=group, content_preview=target["content"][:200])
                # NON salvare la sessione qui: Facebook riduce i cookie durante il posting
                # e save_session() sovrascriverebbe la sessione originale con una incompleta
            return result
        except Exception as e:
            _slog("FACEBOOK_APPROVE_EXCEPTION", post_id=post_id,
                  err_type=type(e).__name__, err=str(e)[:200])
            logger.warning("FACEBOOK_APPROVE_FAIL err=%s", e)
            return {"success": False, "error": str(e)}

    async def reject_pending_post(self, post_id: str) -> bool:
        """Segna il post come rifiutato."""
        try:
            data = await storage.load(FB_PENDING_KEY, default={"posts": []})
            for p in data.get("posts", []):
                if p.get("id") == post_id:
                    p["status"] = "rejected"
                    p["rejected_at"] = datetime.utcnow().isoformat()
                    await storage.save(FB_PENDING_KEY, data)
                    return True
            return False
        except Exception:
            return False

    async def get_pending_posts(self) -> list:
        """Ritorna la lista dei post in stato 'pending'."""
        try:
            data = await storage.load(FB_PENDING_KEY, default={"posts": []})
            return [p for p in data.get("posts", []) if p.get("status") == "pending"]
        except Exception:
            return []

    # ════════════════════════════════════════════════════════════════════════
    # Interaction logging + learning
    # ════════════════════════════════════════════════════════════════════════

    async def _record_interaction(self, itype: str, **kwargs) -> None:
        """Logga un'interazione e la invia al lab_feedback_cycle."""
        try:
            data = await storage.load(FB_LOG_KEY, default={"interactions": []})
            interactions = data.get("interactions", [])
            entry = {
                "ts":   datetime.utcnow().isoformat(),
                "type": itype,
                **{k: str(v)[:200] for k, v in kwargs.items()},
            }
            interactions.append(entry)
            data["interactions"] = interactions[-MAX_LOG_ENTRIES:]
            data["updated_at"]   = datetime.utcnow().isoformat()
            await storage.save(FB_LOG_KEY, data)

            # Feed al sistema di apprendimento
            try:
                from core.lab_feedback_cycle import lab_feedback_cycle
                obs_map = {
                    "post_published":   ("facebook_post",    f"Post pubblicato in '{kwargs.get('group','?')}': {kwargs.get('content_preview','')[:150]}"),
                    "comment_posted":   ("facebook_comment", f"Commento postato: {kwargs.get('content_preview','')[:150]}"),
                    "comment_received": ("facebook_social",  f"Commento ricevuto nel gruppo '{kwargs.get('group','?')}': {kwargs.get('content_preview','')[:150]}"),
                    "post_rejected":    ("facebook_feedback", f"Post rifiutato dall'admin — topic: {kwargs.get('group','?')}"),
                }
                if itype in obs_map:
                    cat, obs_text = obs_map[itype]
                    lab_feedback_cycle.record_observation(
                        category=obs_text,
                        observation=obs_text,
                        source=f"facebook_{itype}",
                    )
            except Exception:
                pass
        except Exception as e:
            logger.debug("FACEBOOK_RECORD_FAIL err=%s", e)

    # ════════════════════════════════════════════════════════════════════════
    # Status
    # ════════════════════════════════════════════════════════════════════════

    async def get_status(self) -> dict:
        """Ritorna lo stato corrente del servizio."""
        cfg = await self._load_config()
        data = await storage.load(FB_LOG_KEY, default={"interactions": []})
        interactions = data.get("interactions", [])
        by_type: dict = {}
        for i in interactions:
            t = i.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        pending = await self.get_pending_posts()
        sess = await storage.load(FB_SESSION_KEY, default={})
        return {
            "enabled":          cfg.get("enabled", False),
            "mode":             cfg.get("mode", "semi"),
            "groups":           cfg.get("groups", []),
            "mentions":         cfg.get("mentions", []),
            "heartbeat_count":  self._hb_count,
            "session_saved_at": sess.get("saved_at"),
            "has_session":      bool(sess.get("cookies")),
            "pending_count":    len(pending),
            "interactions":     {"total": len(interactions), "by_type": by_type},
            "night_window":     self._is_night_window(),
        }

    # ════════════════════════════════════════════════════════════════════════
    # Heartbeat — ciclo principale
    # ════════════════════════════════════════════════════════════════════════

    async def heartbeat(self) -> dict:
        """
        Ciclo principale di attività Facebook.
        Fail-silent: non solleva mai eccezioni.
        """
        if self._running:
            return {"skipped": True, "reason": "heartbeat già in corso"}

        result = {"hb": self._hb_count, "actions": [], "skipped": False}
        self._running = True
        try:
            cfg = await self._load_config()

            if not cfg.get("enabled", False):
                result["skipped"] = True
                result["reason"]  = "disabled"
                return result

            if self._is_night_window():
                result["skipped"] = True
                result["reason"]  = "night_window"
                _slog("FACEBOOK_SKIP_NIGHT")
                return result

            self._reset_daily_counter()
            if self._posts_today >= cfg.get("max_posts_per_day", 2):
                result["skipped"] = True
                result["reason"]  = "daily_limit_reached"
                return result

            # Avvia browser e carica sessione
            _slog("FACEBOOK_HB_BROWSER_START")
            ok = await self._ensure_browser(headless=True)
            _slog("FACEBOOK_HB_BROWSER_RESULT", ok=ok,
                  browser_connected=(self._browser.is_connected() if self._browser else False),
                  page_is_none=(self._page is None))
            if not ok:
                result["skipped"] = True
                result["reason"]  = "browser_unavailable"
                return result

            sess_ok = await self.load_session()
            _slog("FACEBOOK_HB_SESSION_LOADED", session_ok=sess_ok)
            if not await self.is_logged_in():
                result["skipped"] = True
                result["reason"]  = "not_logged_in"
                _slog("FACEBOOK_NOT_LOGGED_IN")
                return result

            self._hb_count += 1
            mode   = cfg.get("mode", "semi")
            style  = cfg.get("post_prompt_style", "locale")
            groups = cfg.get("groups", [])

            for group in groups:
                await self._human_delay(3, 7)
                is_timeline = (group == "timeline")

                # 1. Leggi il feed
                if is_timeline:
                    feed = await self.read_timeline_feed(max_posts=5)
                    post_style = "timeline"
                else:
                    feed = await self.read_group_feed(group, max_posts=8)
                    post_style = style
                result["actions"].append(f"feed_read:{group}({len(feed)})")

                # 2. Genera post
                target_label = "bacheca personale" if is_timeline else group
                content = await self._generate_post_content(target_label, feed, post_style)
                if not content:
                    continue

                # Menzioni: se configurate, passale al post bacheca
                mentions = cfg.get("mentions", [])
                mention = random.choice(mentions) if mentions and is_timeline else ""

                if mode == "semi":
                    # Accoda per approvazione admin
                    display_group = group
                    post_id = await self.queue_pending_post(content, display_group, mention=mention)
                    result["actions"].append(f"post_queued:{post_id}")
                    _slog("FACEBOOK_POST_QUEUED_HB", group=display_group, id=post_id)
                elif mode == "full":
                    # Posta direttamente
                    if is_timeline:
                        post_result = await self.post_to_timeline(content, mention=mention)
                    else:
                        post_result = await self.post_to_group(group, content)
                    if post_result["success"]:
                        self._posts_today += 1
                        await self._record_interaction("post_published",
                            group=group, content_preview=content[:200])
                        result["actions"].append(f"posted:{group}")
                    await self._human_delay(30, 60)  # pausa tra post e commenti

                    # 3. Commenta su post rilevanti (full-auto, solo gruppi non bacheca)
                    if not is_timeline:
                        max_comments = cfg.get("max_comments_per_hb", 5)
                        commented = 0
                        for post in feed[:max_comments]:
                            if not post.get("url"):
                                continue
                            await self._human_delay(10, 30)
                            comment = await self._generate_comment(post["text"], [])
                            if comment:
                                ok = await self.comment_on_post(post["url"], comment)
                                if ok:
                                    commented += 1
                                    await self._record_interaction("comment_posted",
                                        group=group, content_preview=comment[:200])
                        if commented:
                            result["actions"].append(f"comments:{group}({commented})")

            # Rispondi ai commenti + controlla like (rispetta modalità)
            await self._human_delay(5, 10)
            n_replies = await self.reply_to_comments_on_own_posts(mode=mode, max_replies=3)
            if n_replies:
                action_label = "replies_queued" if mode == "semi" else "replies_sent"
                result["actions"].append(f"{action_label}:{n_replies}")

            # Aggiorna sessione
            await self.save_session()

            # Aggiorna timestamp heartbeat
            cfg["last_heartbeat"] = datetime.utcnow().isoformat()
            await self._save_config(cfg)
            _slog("FACEBOOK_HEARTBEAT_DONE", hb=self._hb_count, actions=len(result["actions"]))

        except Exception as e:
            logger.warning("FACEBOOK_HEARTBEAT_ERROR err=%s(%s)", type(e).__name__, e)
            result["error"] = str(e)
        finally:
            self._running = False

        return result


facebook_service = FacebookService()
