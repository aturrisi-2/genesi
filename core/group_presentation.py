"""
Presentazione di Genesi quando entra in un gruppo — UNICA, GLOBALE, AUTONOMA.

Principio: niente codice hardcoded per piattaforma. La presentazione avviene
in un solo punto, valido per Telegram, WhatsApp e Meta. Il "ricordo" di quali
gruppi sono già stati salutati è il registry condiviso `birthday:known_groups`:
- gruppo MAI visto  → Genesi si presenta e lo registra (atomico-first, anti-doppione)
- gruppo già noto    → nessuna presentazione (evita auto-intro fuori contesto)

Trigger possibili (entrambi passano da qui e si deduplicano tra loro):
  1. Evento di join della piattaforma (veloce, ma può saltare durante i reconnect)
  2. Primo messaggio che Genesi processa nel gruppo (garanzia robusta)

Così un singhiozzo di rete non fa più perdere la presentazione, e aggiungere una
nuova piattaforma significa solo chiamare `maybe_present_in_group(...)`.
"""
from __future__ import annotations

from typing import Optional

from core.log import log


# Parole nel nome del gruppo che indicano un contesto familiare → tono affettuoso.
_FAMILY_HINTS = (
    "famiglia", "famigliar", "familiar", "casa", "turrisi", "torrisi",
    "parenti", "fratelli", "nipoti", "cugini", "zii", "nonni", "genitori",
)


def infer_family_tone(group_name: str) -> bool:
    """Deduce dal NOME del gruppo se il tono dev'essere familiare (autonomo, no ID hardcoded)."""
    g = (group_name or "").lower()
    return any(h in g for h in _FAMILY_HINTS)


def _visible_names(participants: Optional[list]) -> list[str]:
    """Estrae i nomi visibili dei partecipanti (esclusa Genesi e i duplicati)."""
    out: list[str] = []
    for p in participants or []:
        try:
            if isinstance(p, dict):
                if p.get("is_me"):
                    continue
                name = (p.get("name") or "").strip()
            else:
                if getattr(p, "is_me", False):
                    continue
                name = (getattr(p, "name", "") or "").strip()
        except Exception:
            continue
        if name and name not in out:
            out.append(name)
    return out[:25]


async def _already_known(platform: str, group_id_int: int) -> bool:
    from core.birthday_service import get_known_groups
    known = await get_known_groups()
    for g in known:
        if g.get("chat_id") == group_id_int and g.get("platform") == platform:
            return True
    return False


async def forget_group(platform: str, group_id_int: int) -> bool:
    """
    Dimentica un gruppo: lo rimuove dal registry così una futura riaggiunta fa
    ripartire la presentazione da zero. Chiamato quando Genesi viene rimossa da
    un gruppo. Ferma anche i saluti proattivi verso un gruppo in cui non è più.
    """
    try:
        from core.birthday_service import get_known_groups, _known_groups_key
        from core.storage import storage
        known = await get_known_groups()
        kept = [g for g in known
                if not (g.get("chat_id") == group_id_int and g.get("platform") == platform)]
        if len(kept) != len(known):
            await storage.save(_known_groups_key(), kept)
            try:
                await storage.delete(f"group_title:{group_id_int}")
            except Exception:
                pass
            log("GROUP_FORGOTTEN", platform=platform, group=group_id_int)
            return True
        return False
    except Exception as e:
        log("GROUP_FORGET_ERROR", platform=platform, error=str(e))
        return False


async def maybe_present_in_group(
    platform: str,
    group_id_int: int,
    group_name: str,
    participants: Optional[list] = None,
    adder_name: str = "",
    is_family: Optional[bool] = None,
) -> Optional[str]:
    """
    Se è la PRIMA volta che Genesi incontra questo gruppo, ritorna il testo di
    presentazione (generato dall'LLM) e registra il gruppo. Altrimenti None.

    `participants`: lista di {id, name, is_me} (WhatsApp) o admin Telegram normalizzati.
    `adder_name`: chi ha aggiunto Genesi, se noto.
    `is_family`: forza il tono; se None viene dedotto dal nome del gruppo.
    """
    try:
        # FASE 0 — modalità passiva: nessuna auto-presentazione spontanea quando
        # Genesi viene aggiunta a un gruppo. Il gruppo viene comunque registrato
        # più sotto solo se si procede; qui usciamo prima senza inviare nulla.
        from core import automation_flags
        if not automation_flags.flag_enabled("group_auto_presentation"):
            log("AUTOMATION_SKIPPED", flag="group_auto_presentation",
                platform=platform, group=group_id_int)
            return None

        if await _already_known(platform, group_id_int):
            return None

        # Registra SUBITO (prima della chiamata LLM lenta): chiude la finestra di
        # doppia presentazione in caso di messaggi concorrenti nello stesso gruppo.
        from core.birthday_service import register_known_group
        await register_known_group(group_id_int, platform, title=group_name)

        if is_family is None:
            is_family = infer_family_tone(group_name)
        names = _visible_names(participants)

        platform_label = {
            "telegram": "Telegram",
            "whatsapp": "WhatsApp",
            "messenger": "Messenger",
            "instagram": "Instagram",
        }.get(platform, platform)

        ctx = (
            f"Sei appena entrata nel gruppo {platform_label} chiamato \"{group_name}\""
            + (f", aggiunta da {adder_name}" if adder_name else "") + ".\n"
            + (f"Persone presenti nel gruppo: {', '.join(names)}.\n" if names else "")
            + ("Questo è un gruppo della tua FAMIGLIA: tono affettuoso e caloroso, da familiare.\n"
               if is_family else
               "Gruppo nuovo: tono cordiale, simpatico e garbato, da ospite educata.\n")
        )
        prompt = (
            "Sei Genesi, assistente AI italiana con una personalità calorosa. Scrivi il tuo "
            "PRIMISSIMO messaggio in un gruppo a cui sei appena stata aggiunta. REGOLE:\n"
            "- Se sai chi ti ha aggiunta, ringrazialo per nome\n"
            "- Saluta per nome le persone che riconosci tra i presenti, con piacere genuino\n"
            "- Deduci il contesto dal nome del gruppo e fai un cenno simpatico e pertinente\n"
            "- Presentati in UNA frase dicendo cosa sai fare (chiacchierare, dare il meteo, "
            "le notizie, ricordare le cose importanti, capire foto, vocali e video)\n"
            "- Massimo 4 frasi, niente elenchi puntati, 1-2 emoji al massimo, italiano naturale"
        )

        intro = ""
        try:
            from core.llm_service import llm_service
            intro = await llm_service._call_model(
                "openai/gpt-4o-mini", prompt, ctx,
                user_id=f"group_join_{platform}_{group_id_int}", route="memory",
            )
        except Exception as e:
            log("GROUP_PRESENT_LLM_ERROR", platform=platform, error=str(e))

        if not intro or not intro.strip():
            thanks = f"Grazie {adder_name} per avermi aggiunta! " if adder_name else "Ciao a tutti! "
            intro = (
                f"{thanks}Sono Genesi 😊 Posso chiacchierare con voi, darvi meteo e notizie, "
                "ricordare le cose importanti e capire foto, vocali e video. Felice di essere qui!"
            )

        intro = intro.strip()
        log("GROUP_PRESENTED", platform=platform, group=group_id_int,
            name=group_name[:40], family=is_family, people=len(names))
        return intro
    except Exception as e:
        log("GROUP_PRESENT_ERROR", platform=platform, error=str(e))
        return None
