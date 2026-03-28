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
FB_CONFIG_KEY  = "facebook:config"
FB_SESSION_KEY = "facebook:session"
FB_PENDING_KEY = "facebook:pending_posts"
FB_LOG_KEY     = "facebook:interaction_log"

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
                return False
            await self._context.add_cookies(cookies)
            return True
        except Exception as e:
            logger.debug("FACEBOOK_LOAD_SESSION_FAIL err=%s", e)
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

    async def import_session_from_json(self, cookies: list) -> bool:
        """
        Importa cookies da JSON esterno (es. da estensione Cookie-Editor).
        Utile per il seeding iniziale da VPS senza display.
        """
        try:
            await storage.save(FB_SESSION_KEY, {
                "cookies":  cookies,
                "saved_at": datetime.utcnow().isoformat(),
                "source":   "manual_import",
            })
            _slog("FACEBOOK_SESSION_IMPORTED", count=len(cookies))
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
        Cerca il gruppo su Facebook, legge i post recenti.
        Ritorna lista di dict: {author, text, timestamp, url}.
        """
        posts = []
        try:
            # Cerca il gruppo tramite la barra di ricerca
            await self._page.goto("https://www.facebook.com/", timeout=20000)
            await self._human_delay(2, 4)

            # Usa la search bar
            search_box = await self._page.query_selector('input[placeholder*="Cerca"]')
            if not search_box:
                search_box = await self._page.query_selector('[aria-label*="Cerca"]')
            if search_box:
                await search_box.click()
                await self._type_humanlike(search_box, group_name)
                await self._human_delay(1, 2)
                await self._page.keyboard.press("Enter")
                await self._human_delay(2, 4)

                # Clicca su "Gruppi" nei risultati
                groups_tab = await self._page.query_selector('[data-key="groups"]')
                if groups_tab:
                    await groups_tab.click()
                    await self._human_delay(1.5, 3)

                # Clicca sul primo risultato
                first_result = await self._page.query_selector('[data-testid="search_result"] a')
                if first_result:
                    await first_result.click()
                    await self._human_delay(3, 5)
                else:
                    # Fallback: cerca nell'href
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
        """Naviga al gruppo e posta il contenuto."""
        result = {"success": False, "post_url": "", "error": ""}
        try:
            # Naviga al gruppo (stessa logica di read_group_feed)
            await self._page.goto("https://www.facebook.com/", timeout=20000)
            await self._human_delay(2, 5)

            # Cerca il gruppo
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

    async def post_to_timeline(self, content: str, mention: str = "") -> dict:
        """
        Posta sulla bacheca personale di Giada.
        Se mention è specificato (es. 'Alfio Turrisi'), tenta di taggare la persona.
        """
        result = {"success": False, "post_url": "", "error": ""}
        try:
            await self._page.goto("https://www.facebook.com/", timeout=20000)
            await self._human_delay(2, 4)

            # Trova il box "Cosa stai pensando?" sulla home
            write_box = await self._page.query_selector('[aria-label*="Cosa stai pensando"]')
            if not write_box:
                write_box = await self._page.query_selector('[data-testid="status-attachment-mentions-input"]')
            if not write_box:
                # Prova a cliccare il placeholder che apre il dialog
                placeholder = await self._page.query_selector('[role="button"][tabindex="0"]')
                if placeholder:
                    await placeholder.click()
                    await self._human_delay(1, 2)
                    write_box = await self._page.query_selector('[role="textbox"][contenteditable="true"]')

            if not write_box:
                result["error"] = "Box bacheca non trovato"
                return result

            await write_box.click()
            await self._human_delay(0.5, 1.5)

            # Se c'è una menzione, inserisci @nome per attivare il tag
            if mention:
                full_content = f"@{mention} {content}"
                # Digita @ + nome per far apparire i suggerimenti di tag
                await self._type_humanlike(write_box, f"@{mention}")
                await self._human_delay(1.5, 3)
                # Cerca il suggerimento nella dropdown e cliccalo
                suggestion = await self._page.query_selector('[role="option"]')
                if suggestion:
                    await suggestion.click()
                    await self._human_delay(0.5, 1)
                    # Aggiungi il resto del testo
                    await self._type_humanlike(write_box, f" {content}")
                else:
                    # Nessun suggerimento trovato, scrivi tutto senza tag
                    await self._type_humanlike(write_box, f" {content}")
            else:
                await self._type_humanlike(write_box, content)

            await self._human_delay(2, 4)

            # Pubblica
            publish_btn = await self._page.query_selector('[aria-label="Pubblica"]')
            if not publish_btn:
                publish_btn = await self._page.query_selector('button[type="submit"]')
            if publish_btn:
                await publish_btn.click()
                await self._human_delay(3, 5)
                result["success"] = True
                result["post_url"] = self._page.url
                _slog("FACEBOOK_TIMELINE_POSTED", chars=len(content), mention=mention or "none")
            else:
                result["error"] = "Bottone Pubblica non trovato"
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
        try:
            data = await storage.load(FB_PENDING_KEY, default={"posts": []})
            posts = data.get("posts", [])
            for p in posts:
                if p.get("id") == post_id and p.get("status") == "pending":
                    ok = await self._ensure_browser()
                    if not ok:
                        return {"success": False, "error": "Browser non disponibile"}
                    await self.load_session()
                    if p.get("group") == "timeline":
                        result = await self.post_to_timeline(p["content"], mention=p.get("mention", ""))
                    else:
                        result = await self.post_to_group(p["group"], p["content"])
                    p["status"]      = "published" if result["success"] else "failed"
                    p["published_at"] = datetime.utcnow().isoformat()
                    p["post_url"]    = result.get("post_url", "")
                    p["error"]       = result.get("error", "")
                    await storage.save(FB_PENDING_KEY, data)
                    if result["success"]:
                        await self._record_interaction("post_published",
                            group=p["group"], content_preview=p["content"][:200])
                        await self.save_session()
                    return result
            return {"success": False, "error": "Post non trovato o già processato"}
        except Exception as e:
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
