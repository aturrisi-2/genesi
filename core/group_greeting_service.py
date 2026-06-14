"""
GENESI — Group Greeting Service (platform-independent)

Servizio universale per i saluti giornalieri nei gruppi (Telegram, WhatsApp, futuri):
1. Estrae automaticamente nome e città dei membri dai messaggi (LLM gpt-4o-mini,
   con pre-filtro regex per evitare chiamate inutili).
2. Costruisce un saluto personalizzato per nome, con meteo locale se la città
   è nota e un breve commento stagionale.
3. Isolamento rigoroso: i profili del gruppo familiare usano la chiave
   `group_member_profile:family:{platform}:{platform_user_id}`, quelli dei
   gruppi esterni `group_member_profile:ext:{platform}:{platform_user_id}`.
   I due namespace non vengono MAI mischiati.

Tutte le funzioni sono fail-silent: un'eccezione viene loggata ma non
interrompe mai il flusso del bot.
"""

import json
import os
import re
import time
from datetime import datetime
from typing import Optional

import httpx

from core.log import log
from core.storage import storage

try:
    from zoneinfo import ZoneInfo
    _TZ_ROME = ZoneInfo("Europe/Rome")
except Exception:  # pragma: no cover
    _TZ_ROME = None

import logging
logger = logging.getLogger(__name__)

OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
OPENWEATHER_CURRENT = "https://api.openweathermap.org/data/2.5/weather"

# Pre-filtro: chiamiamo l'LLM solo se il messaggio sembra contenere una città
_CITY_HINT_RE = re.compile(
    r"\b(vengo\s+da|arrivo\s+da|abito\s+a|abito\s+in|vivo\s+a|vivo\s+in|"
    r"sono\s+a|sono\s+in|sto\s+a|sto\s+in|mi\s+trovo\s+a|mi\s+trovo\s+in|"
    r"torno\s+da|rientro\s+da|parto\s+per|sono\s+di|"
    r"mi\s+sono\s+trasferit[oa]|ci\s+siamo\s+trasferit)\b",
    re.IGNORECASE,
)

# Validazione del nome città estratto dall'LLM
_CITY_VALID_RE = re.compile(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’ .\-]{1,39}$")
_CITY_STOPWORDS = {
    "casa", "qui", "lì", "là", "vacanza", "vacanze", "ferie", "lavoro",
    "ufficio", "giro", "letto", "palestra", "scuola", "mare", "montagna",
    "campagna", "centro", "città", "paese", "italia", "estero", "viaggio",
    "macchina", "auto", "treno", "aereo", "ospedale", "chiesa", "spiaggia",
}

# Parole che NON possono comparire in un nome di città (ausiliari/verbi/avverbi):
# bloccano frasi estratte per sbaglio come "Ha Toppato", "Sono Tornato".
_CITY_NONPLACE_TOKENS = {
    "ha", "ho", "hai", "hanno", "abbiamo", "avete", "è", "e", "sei", "sono",
    "siamo", "siete", "sta", "stai", "sto", "stanno", "va", "vai", "vado",
    "toppato", "tornato", "tornata", "arrivato", "arrivata", "partito", "partita",
    "andato", "andata", "fatto", "fatta", "preso", "presa", "detto", "stato", "stata",
    "molto", "poco", "tanto", "sempre", "mai", "già", "ancora", "forse", "quasi",
}

# Cache validazione geografica (city_lower -> bool). Evita riconvalidare la stessa città.
_CITY_GEO_CACHE: dict[str, bool] = {}


async def _city_exists_geo(city: str) -> bool:
    """Valida che la stringa sia un VERO luogo, via OpenWeather geocoding. Cache in-memory.
    Fail-open: se la chiave OpenWeather manca o c'è un errore di rete, NON scarta
    (per non perdere città reali durante un'indisponibilità del servizio)."""
    key = (city or "").strip().lower()
    if not key:
        return False
    if key in _CITY_GEO_CACHE:
        return _CITY_GEO_CACHE[key]
    if not OPENWEATHER_API_KEY or OPENWEATHER_API_KEY == "test-key":
        return True  # nessuna validazione possibile → non scartare
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://api.openweathermap.org/geo/1.0/direct",
                params={"q": city, "limit": 1, "appid": OPENWEATHER_API_KEY},
            )
        ok = r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) > 0
    except Exception as e:
        log("GROUP_GREETING_GEO_VALIDATE_FAIL", city=city, error=str(e)[:120])
        return True  # errore rete → fail-open
    if len(_CITY_GEO_CACHE) < 2000:
        _CITY_GEO_CACHE[key] = ok
    return ok

_CITY_EXTRACT_PROMPT = """\
Sei un estrattore di informazioni. Ricevi un messaggio scritto da un membro di un gruppo chat.
Devi capire se la persona che scrive dichiara la PROPRIA città (dove vive, abita o si trova adesso).

REGOLE:
- Estrai la città SOLO se è chiaramente riferita a chi scrive (es. "abito a Catania", "vivo a Palermo", "sono a Milano per lavoro", "vengo da Roma").
- NON estrarre città riferite ad altre persone (es. "mia sorella vive a Torino" → niente).
- NON estrarre se c'è una negazione (es. "non vivo più a Roma" → niente).
- NON estrarre luoghi generici (casa, mare, ufficio, palestra...) — solo veri nomi di città o paesi/comuni.
- Se la persona dice dove si trova temporaneamente (es. "sono a Milano per lavoro"), estrai comunque la città.

Rispondi SOLO con JSON, senza altro testo:
{"city": "NomeCittà"} se hai trovato la città di chi scrive, altrimenti {"city": ""}
"""

_FAMILY_GREETING_PROMPT = """\
Sei Genesi, un'AI che fa parte di un gruppo chat familiare. Un familiare ha appena salutato il gruppo e tu rispondi al suo saluto.
REGOLE ASSOLUTE:
- Massimo 2 frasi, calde e naturali, come farebbe un familiare affettuoso (NON da assistente formale).
- Usa SEMPRE il nome della persona nella risposta.
- Il saluto deve corrispondere al momento: "morning" → buongiorno, "evening" → buonasera/buonanotte, "holiday" → auguri.
- Se ti vengono forniti dati meteo della sua città, inseriscili con naturalezza in un breve commento (es. "a Catania oggi c'è il sole, 24 gradi: giornata perfetta!").
- Se NON hai dati meteo, NON menzionare il meteo e NON dire che non lo conosci: fai invece un breve commento legato alla stagione o al giorno della settimana.
- Niente domande di ritorno, niente "che bello!", niente intro elaborati, niente roleplay (mai "Ahoy", "Capitano" ecc.).
- Non usare mai la parola "capisco".
- Se è segnalato che la persona si è svegliata/scritta tardi rispetto al resto del gruppo, aggiungi una battuta affettuosa e scherzosa sul ritardo.
Rispondi SOLO con il testo del saluto, senza virgolette."""

_EXTERNAL_GREETING_PROMPT = """\
Sei Genesi, un'assistente AI educata presente in un gruppo chat. Un membro del gruppo ha appena salutato e tu rispondi al suo saluto.
REGOLE ASSOLUTE:
- Massimo 2 frasi, cordiali e professionali ma non fredde.
- Usa SEMPRE il nome della persona nella risposta.
- Il saluto deve corrispondere al momento: "morning" → buongiorno, "evening" → buonasera/buonanotte, "holiday" → auguri.
- Se ti vengono forniti dati meteo della sua città, inseriscili con naturalezza in un breve commento.
- Se NON hai dati meteo, NON menzionare il meteo e NON dire che non lo conosci: fai invece un breve commento legato alla stagione o al giorno della settimana.
- Niente domande di ritorno, niente roleplay, niente emoji eccessive (max 1).
- Non usare mai la parola "capisco".
Rispondi SOLO con il testo del saluto, senza virgolette."""

_WEEKDAYS_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_MONTHS_IT = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
              "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _season_it(month: int) -> str:
    if month in (12, 1, 2):
        return "inverno"
    if month in (3, 4, 5):
        return "primavera"
    if month in (6, 7, 8):
        return "estate"
    return "autunno"


def _strip_json_fences(raw: str) -> str:
    clean = (raw or "").strip()
    if clean.startswith("```"):
        parts = clean.split("```")
        if len(parts) >= 2:
            clean = parts[1]
        if clean.startswith("json"):
            clean = clean[4:]
    return clean.strip()


class GroupGreetingService:
    """Saluto giornaliero di gruppo, identico su tutte le piattaforme."""

    def __init__(self):
        # Dedup in-memory: evita doppie chiamate LLM sullo stesso messaggio
        # (es. hook per-messaggio + hook nel flusso saluto)
        self._recent_extracts: dict[str, float] = {}

    # ── Storage keys (ISOLATION: family e ext non si mischiano MAI) ─────────

    @staticmethod
    def _profile_key(platform_user_id: str, platform: str, is_family_group: bool) -> str:
        scope = "family" if is_family_group else "ext"
        return f"group_member_profile:{scope}:{platform}:{platform_user_id}"

    # ── Estrazione info membro ───────────────────────────────────────────────

    async def extract_and_save_member_info(
        self,
        platform_user_id: str,
        first_name: str,
        message: str,
        platform: str,
        group_id: str,
        is_family_group: bool,
    ) -> None:
        """Estrae nome e città dal messaggio e li salva nel profilo membro.

        Fail-silent: qualsiasi eccezione viene loggata e ignorata.
        """
        try:
            platform_user_id = str(platform_user_id or "").strip()
            if not platform_user_id:
                return

            key = self._profile_key(platform_user_id, platform, is_family_group)
            profile = await storage.load(key, default={}) or {}
            if not isinstance(profile, dict):
                profile = {}

            changed = False
            now = int(time.time())

            if first_name and profile.get("name") != first_name:
                profile["name"] = first_name
                changed = True
            if profile.get("platform") != platform:
                profile["platform"] = platform
                changed = True
            if group_id and profile.get("group_id") != str(group_id):
                profile["group_id"] = str(group_id)
                changed = True
            if profile.get("is_family_group") != bool(is_family_group):
                profile["is_family_group"] = bool(is_family_group)
                changed = True
            # Aggiorna last_seen al massimo ogni 10 minuti per ridurre le scritture
            if now - int(profile.get("last_seen", 0) or 0) > 600:
                profile["last_seen"] = now
                changed = True

            # ── Estrazione città (regex gate + LLM) ─────────────────────────
            text = (message or "").strip()
            city = ""
            if text and _CITY_HINT_RE.search(text):
                dedup_key = f"{platform}:{platform_user_id}:{hash(text)}"
                last = self._recent_extracts.get(dedup_key, 0.0)
                if time.time() - last > 60:
                    self._recent_extracts[dedup_key] = time.time()
                    # Pulizia periodica della cache dedup
                    if len(self._recent_extracts) > 500:
                        cutoff = time.time() - 300
                        self._recent_extracts = {
                            k: v for k, v in self._recent_extracts.items() if v > cutoff
                        }
                    city = await self._extract_city_llm(text)

            if city:
                city = city.strip().title()
                if profile.get("city") != city:
                    profile["city"] = city
                    profile["city_updated_at"] = now
                    changed = True
                    log("GROUP_GREETING_CITY_SAVED",
                        platform=platform, user=platform_user_id,
                        name=first_name, city=city,
                        family=is_family_group)
                # Bridge verso lo storage legacy per-membro (telegram_group_memory),
                # così anche i vecchi percorsi (get_member_city) vedono la città.
                await self._save_city_legacy(platform, platform_user_id, city)

            if changed:
                await storage.save(key, profile)

        except Exception as e:
            log("GROUP_GREETING_EXTRACT_ERROR",
                platform=platform, user=str(platform_user_id), error=str(e)[:200])

    async def _extract_city_llm(self, message: str) -> str:
        """Chiede a gpt-4o-mini di estrarre la città dichiarata da chi scrive."""
        try:
            from core.llm_service import llm_service
            raw = await llm_service._call_model(
                "openai/gpt-4o-mini",
                _CITY_EXTRACT_PROMPT,
                f"Messaggio: {message[:500]}",
                user_id="group-greeting",
                route="memory",
            )
            if not raw:
                return ""
            parsed = json.loads(_strip_json_fences(raw))
            city = str(parsed.get("city", "") or "").strip()
            if not city:
                return ""
            if not _CITY_VALID_RE.match(city):
                return ""
            if city.lower() in _CITY_STOPWORDS:
                return ""
            # Scarta frasi/verbi travestiti da città ("Ha Toppato", "Sono Tornato")
            tokens = [t for t in re.split(r"[\s'’.\-]+", city.lower()) if t]
            if any(t in _CITY_NONPLACE_TOKENS for t in tokens):
                log("GROUP_GREETING_CITY_REJECTED", city=city, reason="nonplace_token")
                return ""
            # Validazione "mondo reale": deve risolvere a un luogo esistente
            if not await _city_exists_geo(city):
                log("GROUP_GREETING_CITY_REJECTED", city=city, reason="not_geocodable")
                return ""
            return city
        except Exception as e:
            log("GROUP_GREETING_CITY_LLM_ERROR", error=str(e)[:200])
            return ""

    @staticmethod
    async def _save_city_legacy(platform: str, platform_user_id: str, city: str) -> None:
        """Salva la città anche nel profilo membro legacy (telegram_group_memory)."""
        try:
            from core.telegram_group_memory import save_member_city, stable_hash
            if platform == "telegram":
                await save_member_city(int(platform_user_id), city)
            else:
                await save_member_city(stable_hash(platform_user_id), city)
        except Exception as e:
            log("GROUP_GREETING_LEGACY_CITY_ERROR",
                platform=platform, user=str(platform_user_id), error=str(e)[:200])

    # ── Roster di gruppo (TUTTI i membri, non solo chi scrive) ───────────────
    # Comportamento GLOBALE: ogni volta che arriva un messaggio di gruppo con la
    # lista partecipanti (qualsiasi piattaforma), Genesi memorizza il roster
    # completo del gruppo. Così conosce anche i membri silenziosi.

    @staticmethod
    def _roster_key(platform: str, group_id: str) -> str:
        return f"group_roster:{platform}:{group_id}"

    async def update_group_roster(
        self,
        platform: str,
        group_id: str,
        participants: list,
        is_family_group: bool = False,
    ) -> int:
        """Salva/aggiorna il roster COMPLETO dei membri del gruppo dal payload
        partecipanti. Dedup per id. Fail-silent. Ritorna il numero di membri noti."""
        try:
            group_id = str(group_id or "").strip()
            if not group_id or not participants:
                return 0
            key = self._roster_key(platform, group_id)
            data = await storage.load(key, default={}) or {}
            members = data.get("members") if isinstance(data, dict) else None
            if not isinstance(members, dict):
                members = {}
            now = int(time.time())
            for p in participants:
                pid = (p.get("id") if isinstance(p, dict) else getattr(p, "id", "")) or ""
                pname = (p.get("name") if isinstance(p, dict) else getattr(p, "name", "")) or ""
                is_me = (p.get("is_me") if isinstance(p, dict) else getattr(p, "is_me", False))
                pid = str(pid).strip()
                pname = str(pname).strip()
                if not pid or is_me:
                    continue
                norm_id = pid.split("@")[0].replace("+", "").strip()
                if not norm_id:
                    continue
                entry = members.get(norm_id) or {}
                # Non sovrascrivere un nome corretto dall'utente
                if pname and not entry.get("name_locked"):
                    entry["name"] = pname
                entry["last_seen"] = now
                members[norm_id] = entry
            await storage.save(key, {
                "members": members, "platform": platform, "group_id": group_id,
                "is_family_group": bool(is_family_group), "updated_at": now,
            })
            log("GROUP_ROSTER_UPDATED", platform=platform, group=group_id, members=len(members))
            return len(members)
        except Exception as e:
            log("GROUP_ROSTER_UPDATE_ERROR", platform=platform,
                group=str(group_id), error=str(e)[:160])
            return 0

    async def get_group_roster(self, platform: str, group_id: str) -> list[dict]:
        """Ritorna [{id, name, last_seen}] di TUTTI i membri noti del gruppo."""
        try:
            key = self._roster_key(platform, str(group_id))
            data = await storage.load(key, default={}) or {}
            members = data.get("members", {}) if isinstance(data, dict) else {}
            out = []
            if isinstance(members, dict):
                for mid, e in members.items():
                    e = e or {}
                    out.append({"id": mid, "name": e.get("name", ""),
                                "last_seen": e.get("last_seen", 0)})
            return out
        except Exception as e:
            log("GROUP_ROSTER_READ_ERROR", platform=platform,
                group=str(group_id), error=str(e)[:160])
            return []

    # ── Lettura profilo ──────────────────────────────────────────────────────

    async def get_member_profile(
        self, platform_user_id: str, platform: str = "", is_family_group: Optional[bool] = None
    ) -> dict:
        """Ritorna il profilo membro: {name, city, platform, last_seen, ...}.

        Se is_family_group non è specificato, cerca prima nel namespace family
        e poi in quello ext (senza mai unirli).
        """
        try:
            platform_user_id = str(platform_user_id or "").strip()
            if not platform_user_id:
                return {}
            platforms = [platform] if platform else ["telegram", "whatsapp"]
            scopes = [is_family_group] if is_family_group is not None else [True, False]
            for fam in scopes:
                for plat in platforms:
                    key = self._profile_key(platform_user_id, plat, fam)
                    profile = await storage.load(key, default={}) or {}
                    if isinstance(profile, dict) and profile:
                        return profile
            return {}
        except Exception as e:
            log("GROUP_GREETING_PROFILE_ERROR", user=str(platform_user_id), error=str(e)[:200])
            return {}

    # ── Meteo ────────────────────────────────────────────────────────────────

    @staticmethod
    async def _get_weather_snippet(city: str) -> str:
        """Meteo corrente compatto per la città ('cielo sereno, 24°C'). Fail-silent."""
        if not city or not OPENWEATHER_API_KEY or OPENWEATHER_API_KEY == "test-key":
            return ""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    OPENWEATHER_CURRENT,
                    params={"q": city, "appid": OPENWEATHER_API_KEY,
                            "units": "metric", "lang": "it"},
                )
            if resp.status_code != 200:
                log("GROUP_GREETING_WEATHER_FAIL", city=city, status=resp.status_code)
                return ""
            data = resp.json()
            desc = data.get("weather", [{}])[0].get("description", "")
            temp = data.get("main", {}).get("temp")
            if temp is None:
                return ""
            return f"{desc}, {round(temp)}°C" if desc else f"{round(temp)}°C"
        except Exception as e:
            log("GROUP_GREETING_WEATHER_FAIL", city=city, error=str(e)[:200])
            return ""

    # ── Saluto personalizzato ────────────────────────────────────────────────

    async def build_personalized_greeting(
        self,
        platform_user_id: str,
        first_name: str,
        greeting_category: str,
        platform: str,
        group_id: str,
        is_family_group: bool,
        is_late_wakeup: bool = False,
    ) -> str:
        """Costruisce il saluto personalizzato (nome + meteo locale + commento).

        Ritorna sempre una stringa non vuota: in caso di errore usa un
        fallback deterministico.
        """
        name = (first_name or "").strip() or "amico"
        try:
            # 1. Città: prima dal profilo universale, poi dal legacy telegram
            profile = await self.get_member_profile(
                platform_user_id, platform=platform, is_family_group=is_family_group
            )
            city = (profile.get("city") or "").strip()
            if not city:
                try:
                    from core.telegram_group_memory import get_member_city, stable_hash
                    if platform == "telegram":
                        city = await get_member_city(int(platform_user_id)) or ""
                    else:
                        city = await get_member_city(stable_hash(str(platform_user_id))) or ""
                except Exception:
                    city = ""

            # 2. Meteo locale (solo se città nota)
            weather = await self._get_weather_snippet(city) if city else ""

            # 3. Contesto temporale per il commento stagionale
            now = datetime.now(_TZ_ROME) if _TZ_ROME else datetime.now()
            weekday = _WEEKDAYS_IT[now.weekday()]
            date_str = f"{weekday} {now.day} {_MONTHS_IT[now.month]}"
            season = _season_it(now.month)

            # 4. Generazione LLM
            system_prompt = _FAMILY_GREETING_PROMPT if is_family_group else _EXTERNAL_GREETING_PROMPT
            ctx_lines = [
                f"Nome della persona: {name}",
                f"Tipo di saluto ricevuto: {greeting_category or 'general'}",
                f"Oggi è {date_str} ({season}).",
            ]
            if city and weather:
                ctx_lines.append(f"Città della persona: {city}. Meteo attuale a {city}: {weather}.")
            elif city:
                ctx_lines.append(f"Città della persona: {city} (meteo non disponibile: NON menzionarlo).")
            else:
                ctx_lines.append("Città non nota (NON menzionare il meteo).")
            if is_late_wakeup:
                ctx_lines.append("Nota: il resto del gruppo si è già salutato da un po' — "
                                 "questa persona arriva in ritardo: fai una battuta affettuosa sul ritardo.")
            user_msg = "\n".join(ctx_lines) + "\n\nScrivi ora il saluto personalizzato."

            reply = ""
            try:
                from core.llm_service import llm_service
                reply = await llm_service._call_model(
                    "openai/gpt-4o-mini",
                    system_prompt,
                    user_msg,
                    user_id="group-greeting",
                    route="memory",
                ) or ""
                reply = reply.strip().strip('"').strip()
            except Exception as le:
                log("GROUP_GREETING_LLM_ERROR", error=str(le)[:200])
                reply = ""

            if not reply:
                reply = self._fallback_greeting(name, greeting_category, city, weather)

            log("GROUP_GREETING_BUILT",
                platform=platform, user=str(platform_user_id), name=name,
                category=greeting_category, city=city or "-",
                weather=bool(weather), family=is_family_group,
                late=is_late_wakeup, length=len(reply))
            return reply

        except Exception as e:
            log("GROUP_GREETING_BUILD_ERROR",
                platform=platform, user=str(platform_user_id), error=str(e)[:200])
            return self._fallback_greeting(name, greeting_category, "", "")

    @staticmethod
    def _fallback_greeting(name: str, category: str, city: str, weather: str) -> str:
        """Saluto deterministico se l'LLM non risponde."""
        if category == "evening":
            base, wish = f"Buonasera {name}!", "Buona serata a te."
        elif category == "holiday":
            base, wish = f"Tanti auguri {name}!", "Buona festa a te e a tutti!"
        elif category == "morning":
            base, wish = f"Buongiorno {name}!", "Ti auguro una splendida giornata."
        else:
            base, wish = f"Ciao {name}!", "Che bello sentirti."
        if city and weather:
            return f"{base} A {city} in questo momento abbiamo {weather}. {wish}"
        return f"{base} {wish}"


# Singleton
group_greeting_service = GroupGreetingService()
