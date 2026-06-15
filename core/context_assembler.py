"""
CONTEXT ASSEMBLER - Genesi Cognitive System
Costruisce contesto strutturato dalla memoria per il prompt LLM.
Unico punto di assemblaggio: profilo, relazione, episodi, latent state.
Nessun fallback silenzioso — se il contesto non viene costruito, errore esplicito.
"""

import logging
from typing import Dict, Any, List
from core.cognitive_memory_engine import CognitiveMemoryEngine
from core.storage import storage
from core.chat_memory import chat_memory
from core.document_memory import load_document
from core.document_selector import resolve_documents
from core.log import log as _structured_log

logger = logging.getLogger(__name__)

cognitive_engine = CognitiveMemoryEngine()


# Gender inference dai personal facts
import re as _re

_GF_F = _re.compile(r"""(?i)su[ao] (sorella|madre|mamma|moglie|figlia|nonna|zia|cugina|cognata|nuora|fidanzata) (\w{3,})""")
_GF_M = _re.compile(r"""(?i)su[ao] (fratello|padre|pap[aoà]|marito|figlio|nonno|zio|cugino|cognato|genero|fidanzato) (\w{3,})""")
_GFN_F = _re.compile(r"""(?i)su[ao] (sorella|madre|mamma|moglie|figlia|nonna|zia|cugina|cognata|nuora|fidanzata)""")
_GFN_M = _re.compile(r"""(?i)su[ao] (fratello|padre|pap[aoà]|marito|figlio|nonno|zio|cugino|cognato|genero|fidanzato)""")
_GF_LABEL = {"F": "femminile - usa aggettivi/pronomi al femminile", "M": "maschile - usa aggettivi/pronomi al maschile"}
_GF_STOP = {"quattro","cinque","sei","tre","due","anni","mesi","giorni","fa","scorso","volta","molto","poco","ogni","stato","stata"}


def _build_gender_map_from_facts(facts: list) -> list:
    seen = set()
    result = []
    for fact in facts:
        text = fact.get("text", "")
        for pat, g in ((_GF_F, "F"), (_GF_M, "M")):
            for m in pat.finditer(text):
                rel, name = m.group(1).lower(), m.group(2)
                if not name[0].isupper() or name.lower() in _GF_STOP:
                    continue
                key = name + g
                if key in seen:
                    continue
                seen.add(key)
                result.append(rel + " " + name + ": " + _GF_LABEL[g])
        for pat, g in ((_GFN_F, "F"), (_GFN_M, "M")):
            for m in pat.finditer(text):
                rel = m.group(1).lower()
                key = rel + g
                if key in seen:
                    continue
                seen.add(key)
                result.append(rel + " dell'utente: " + _GF_LABEL[g])
    return result


class ContextAssembler:
    """
    Assembla contesto strutturato dalla memoria per il prompt LLM.
    Riceve memory_brain e latent_state_engine come dipendenze.
    """

    def __init__(self, memory_brain, latent_state_engine):
        self.memory_brain = memory_brain
        self.latent_state_engine = latent_state_engine

    async def build(self, user_id: str, user_message: str, platform: str = "") -> Dict[str, Any]:
        """
        Costruisce contesto completo per LLM.
        NON chiama update_brain — quello e' gia' fatto dal proactor.

        platform="widget" → esclude storico conversazioni personali (past_conversations,
        emotional_trend) per evitare contaminazione di nomi da altre piattaforme (Telegram ecc.)

        Returns:
            dict con: summary, long_term_profile, relational_state, recent_episodes, memory_v2, current_message
        """
        is_widget = (platform == "widget")
        import asyncio
        
        # Load from persistent storage - use asyncio.run for sync wrapper
        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, we need to handle this differently
            # For now, use direct storage access for compatibility
            profile = storage._storage.get(f"profile:{user_id}", {})
            relational_state = storage._storage.get(f"relational_state:{user_id}", {})
            recent_episodes = storage._storage.get(f"episodes:{user_id}", [])
            # For latent_state, create a new event loop
            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.latent_state_engine.load(user_id))
                    latent_state = future.result()
            except RuntimeError:
                # Fallback if threading fails
                latent_state = {}
        except RuntimeError:
            # No event loop, safe to use asyncio.run
            profile = asyncio.run(storage.load(f"profile:{user_id}", default={}))
            relational_state = asyncio.run(storage.load(f"relational_state:{user_id}", default={}))
            recent_episodes = asyncio.run(storage.load(f"episodes:{user_id}", default=[]))
            latent_state = asyncio.run(self.latent_state_engine.load(user_id))

        logger.info("CONTEXT_ASSEMBLER_LOADED user=%s", user_id)

        context = {}

        if profile:
            context['profile'] = profile
            context['long_term_profile'] = profile  # Required field for tests
            logger.info("PROFILE_LOADED user_id=%s", user_id)

        if relational_state:
            context['relational_state'] = relational_state
        else:
            context['relational_state'] = {}  # Ensure field exists

        if recent_episodes:
            context['recent_episodes'] = recent_episodes
        else:
            context['recent_episodes'] = []  # Ensure field exists

        if latent_state:
            context['latent_state'] = latent_state
        else:
            context['latent_state'] = {}  # Ensure field exists

        # Add memory_v2 structure - FASE 6: memory_v2 Stabilizzazione
        # memory_v2.profile è una vista derivata da long_term_profile:{user_id}
        from core.brain_state import brain_state
        brain_state.load_from_storage(user_id)
        profile = await storage.load(f"long_term_profile:{user_id}", default={})
        
        # NORMALIZZAZIONE STRUTTURA PIATTA per memory_v2
        def _normalize_profile(profile: dict) -> dict:
            normalized = dict(profile)
            
            # Spouse: se dict → estrarre name
            spouse = normalized.get("spouse")
            if isinstance(spouse, dict):
                normalized["spouse"] = spouse.get("name")
            
            # Pets: se dict complesso → mantenere solo nome
            pets = normalized.get("pets")
            if isinstance(pets, dict):
                normalized["pets"] = pets.get("name")
            
            return normalized
        
        profile = _normalize_profile(profile)
        
        context['memory_v2'] = {
            'profile': profile,  # Vista derivata da long_term_profile (normalizzata)
            'relational_state': brain_state.relational_state,
            'traits': brain_state.traits
        }
        
        # Mai None, mai coroutine
        if not context['memory_v2']['profile']:
            context['memory_v2']['profile'] = {}
        if not context['memory_v2']['relational_state']:
            context['memory_v2']['relational_state'] = {}
        if not context['memory_v2']['traits']:
            context['memory_v2']['traits'] = {}

        summary = self._summarize_profile(profile)

        if not summary or not summary.strip():
            summary = "No relevant memory found."

        # Global cross-conversation insights (fail-silent)
        try:
            from core.global_memory_service import global_memory_service
            insights = await global_memory_service.get_insights(user_id)
            if insights:
                insights_block = "\n".join(f"• {i}" for i in insights)
                context["global_insights"] = insights_block
                summary += f"\n[PATTERN OSSERVATI NEL TEMPO]\n{insights_block}"
        except Exception:
            pass

        # Episodic memory: eventi personali specifici (fail-silent)
        try:
            from core.episode_memory import episode_memory as _em
            # Passa current_emotion per mood-congruent retrieval
            _current_emotion = context.get("current_emotion", None)
            relevant_episodes = await _em.get_relevant(user_id, user_message, limit=3,
                                                       current_emotion=_current_emotion)
            if relevant_episodes:
                ep_lines = []
                for ep in relevant_episodes:
                    line = f"• {ep['text']}"
                    if ep.get('event_date'):
                        line += f" ({ep['event_date']})"
                    # Evento futuro con data passata → suggerisci follow-up
                    if ep.get('is_future') and ep.get('event_date'):
                        try:
                            from datetime import date as _date
                            if _date.fromisoformat(ep['event_date']) <= _date.today():
                                line += " [puoi chiedere com'è andata]"
                        except Exception:
                            pass
                    ep_lines.append(line)
                episodes_block = "\n".join(ep_lines)
                context["personal_episodes"] = episodes_block
                summary += f"\n[EPISODI PERSONALI RICORDATI]\n{episodes_block}"
                # Marca episodi usati in background
                import asyncio as _aio_ep
                for ep in relevant_episodes:
                    _aio_ep.create_task(_em.mark_used(user_id, ep['id']))
        except Exception as _ep_exc:
            logging.getLogger(__name__).warning("EPISODE_CONTEXT_ERROR user=%s err=%s", user_id, _ep_exc)

        # Personal facts: fatti appresi dalla conversazione (abitudini, preferenze, familiari...)
        try:
            from core.personal_facts_service import personal_facts_service as _pfs
            relevant_pf = await _pfs.get_relevant(user_id, user_message, limit=8)
            if not relevant_pf:
                # Fallback: inject most recent 5 facts regardless of topic match
                all_pf = await _pfs.get_all(user_id)
                relevant_pf = sorted(all_pf, key=lambda f: f.get("saved_at", ""), reverse=True)[:5]
            if relevant_pf:
                pf_lines = [f"• {pf['text']}" for pf in relevant_pf]
                pf_block = "\n".join(pf_lines)
                context["personal_facts"] = pf_block
                summary += f"\n[FATTI PERSONALI APPRESI]\n{pf_block}"
                try:
                    _gmap = _build_gender_map_from_facts(relevant_pf)
                    if _gmap:
                        _gh = chr(10) + "[GENERE PERSONE MENZIONATE (usa accordo grammaticale corretto)]" + chr(10)
                        summary += _gh + chr(10).join("  " + e for e in _gmap)
                except Exception:
                    pass
        except Exception:
            pass

        # Past conversation summaries: cosa è stato discusso nelle sessioni precedenti (fail-silent)
        # WIDGET: escluso — lo storico può contenere nomi da Telegram/WhatsApp e altri canali personali
        if not is_widget:
            try:
                from core.conversation_summary_service import conv_summary_service
                past_block = await conv_summary_service.get_context_block(user_id)
                if past_block:
                    context["past_conversations"] = past_block
                    summary += f"\n[CONVERSAZIONI PRECEDENTI]\n{past_block}"
            except Exception:
                pass

        # Emotional history: andamento emotivo recente (fail-silent)
        # WIDGET: escluso — il trend può essere influenzato da conversazioni di gruppo con altri utenti
        if not is_widget:
            try:
                from core.emotional_memory import get_emotion_trend_summary as _get_trend
                trend = await _get_trend(user_id)
                if trend:
                    context["emotional_trend"] = trend
                    summary += f"\n[ANDAMENTO EMOTIVO RECENTE]\n{trend}"
            except Exception:
                pass

        # Behavioral memory: stile interazione appreso (fail-silent)
        try:
            from core.behavioral_memory import behavioral_memory as _bm
            beh_snippet = _bm.get_context_snippet(user_id)
            if beh_snippet:
                context["behavioral_style"] = beh_snippet
                summary += f"\n[STILE INTERAZIONE APPRESO]\n{beh_snippet}"
        except Exception:
            pass

        # Predictive hint: tendenza prossimo turno (fail-silent, shadow phase per primi 12 turni)
        # Soppresso per telegram_group: il predictive è basato su chat personali e
        # inietta argomenti stantii (es. "Leo ha la febbre") in risposte di gruppo non correlate.
        if platform != "telegram_group":
            try:
                from core.predictive_engine import predictive_engine as _pe
                pred_hint = await _pe.get_context_hint(user_id)
                if pred_hint:
                    context["predictive_hint"] = pred_hint
                    summary += f"\n{pred_hint}"
            except Exception:
                pass

        # Few-shot lessons from training engine (fail-silent)
        try:
            from core.training_engine import training_engine as _te
            lessons_block = await _te.get_context_lessons(user_message)
            if lessons_block:
                context["training_lessons"] = lessons_block
                summary += f"\n{lessons_block}"
        except Exception:
            pass

        # Famiglia dal gruppo Telegram: iniettato nel contesto privato del proprietario (fail-silent)
        try:
            from core.telegram_group_memory import get_family_context_block
            family_block = await get_family_context_block(user_id)
            if family_block:
                context["family_group"] = family_block
                summary += f"\n{family_block}"
        except Exception:
            pass

        # Giorni speciali italiani: iniezione fail-silent (presente in tutti i route)
        try:
            from datetime import datetime as _dt
            from zoneinfo import ZoneInfo as _ZI
            from core.tool_services import get_italian_day_events as _gide
            _now = _dt.now(tz=_ZI("Europe/Rome"))
            _events = _gide(_now)
            if _events:
                _label = ", ".join(_events)
                context["special_day"] = _label
                summary += f"\n[GIORNO SPECIALE] Oggi è {_label}."
        except Exception:
            pass

        context["summary"] = summary
        context["current_message"] = user_message

        logger.info("CONTEXT_ASSEMBLED user=%s summary_len=%d", user_id, len(summary))
        return context

    def _summarize_profile(self, profile):
        """
        Costruisce riassunto compatto (max ~300 token) per il system prompt LLM.
        Include tutti i campi identitari noti.
        """
        parts = []
        if profile.get('name'):
            parts.append(f"L'utente si chiama {profile['name']}")
        if profile.get('profession'):
            parts.append(f"Lavora come {profile['profession']}")
        if profile.get('spouse'):
            parts.append(f"Il coniuge si chiama {profile['spouse']}")
        # Children
        children = profile.get('children', [])
        if children:
            names = [c['name'] if isinstance(c, dict) else str(c) for c in children]
            parts.append(f"Figli: {', '.join(names)}")
        # Pets
        pets = profile.get('pets', [])
        if pets:
            pet_descs = []
            for p in pets:
                if isinstance(p, dict):
                    pet_descs.append(f"{p.get('name', '?')} ({p.get('type', '?')})")
            if pet_descs:
                parts.append(f"Animali: {', '.join(pet_descs)}")
        # Interests (legacy flat list)
        interests = profile.get('interests', [])
        if interests and isinstance(interests, list):
            parts.append(f"Interessi: {', '.join(interests)}")
        # Preferences (categorized dict)
        preferences = profile.get('preferences', {})
        if isinstance(preferences, dict):
            if preferences.get('music'):
                parts.append(f"Musica preferita: {', '.join(preferences['music'])}")
            if preferences.get('food'):
                parts.append(f"Cibo preferito: {', '.join(preferences['food'])}")
            if preferences.get('general'):
                parts.append(f"Preferenze: {', '.join(preferences['general'])}")
        elif isinstance(preferences, list) and preferences:
            parts.append(f"Preferenze: {', '.join(preferences)}")
        # Traits
        traits = profile.get('traits', [])
        if traits:
            parts.append(f"Tratti: {', '.join(traits)}")
        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# CONVERSATION CONTEXT — thread continuity for LLM
# ═══════════════════════════════════════════════════════════════

# Topic detection keywords (Italian)
_TOPIC_MAP = {
    "famiglia": ["moglie", "marito", "figlio", "figlia", "figli", "madre", "padre",
                 "fratello", "sorella", "famiglia", "rita", "genitori", "nonno", "nonna"],
    "lavoro": ["lavoro", "ufficio", "collega", "capo", "professione", "progetto",
               "cliente", "riunione", "stipendio"],
    "salute": ["salute", "dottore", "ospedale", "dolore", "malattia", "medicina",
               "terapia", "visita"],
    "emozioni": ["triste", "felice", "arrabbiato", "ansioso", "paura", "solo",
                 "stanco", "preoccupato", "contento", "nervoso"],
    "animali": ["cane", "gatto", "gatta", "animale", "animali", "rio", "luna"],
    "interessi": ["musica", "film", "libro", "sport", "cucina", "viaggio",
                  "gioco", "hobby"],
    "identita'": ["chiamo", "nome", "sono", "anni", "vivo", "abito"],
}


def detect_topic(message: str, history: List[Dict] = None) -> str:
    """Detect current conversation topic from message + recent history."""
    # Combine current message with last 2 user messages for topic continuity
    texts = [message.lower()]
    if history:
        for entry in history[-2:]:
            texts.append(entry.get("user_message", "").lower())
    combined = " ".join(texts)

    scores = {}
    for topic, keywords in _TOPIC_MAP.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[topic] = score

    if scores:
        return max(scores, key=scores.get)
    return "conversazione libera"


# Argomenti che meritano la ricerca SEMANTICA nei manuali clinici (RAG vettoriale,
# più preciso ma con una chiamata embedding). Esclusi i termini puramente interrogativi
# ("cosa", "come", "perché"...) che da soli non indicano un argomento di conoscenza.
_KB_TOPIC_KW = (
    "sintomi", "sintomo", "cura", "curare", "rimedio", "rimedi", "malattia", "malato",
    "dolore", "fa male", "ho male", "mal di", "febbre", "tosse", "raffreddore",
    "influenza", "nausea", "vomito", "vomita", "diarrea", "prurito", "gonfio", "sangue",
    "pressione", "diabete", "allergia", "infezione", "infiammazione", "medicin",
    "farmac", "stomaco", "gola", "schiena", "petto", "respir", "svenut", "svenim",
    "ansia", "panico", "depress", "insonnia", "stress", "emicrania", "cefalea",
    "primo soccorso", "soccorso", "ustione", "ferita", "ferito", "frattura", "trauma",
    "veterinar", "cucciolo", "parassit", "vaccin", "zecca", "pulci",
)


def build_conversation_context(user_id: str, current_message: str,
                                profile: Dict[str, Any], conversation_id: str = None,
                                assembled_summary: str = None, force_manuals: bool = False) -> str:
    """
    Builds structured conversation context for LLM:
    A) Last 15 messages (user/assistant alternating)
    B) Stable identity summary
    C) Current topic detection
    """
    sections = []

    # --- A) Chat history thread ---
    thread_lines = []
    history = []
    
    if conversation_id:
        try:
            from api.conversations import _load_conv
            conv = _load_conv(user_id, conversation_id)
            if conv and "messages" in conv:
                msgs = conv["messages"][-15:]
                for m in msgs:
                    if m.get("role") == "user":
                        thread_lines.append(f"Utente: {m.get('content', '')}")
                        history.append({"user_message": m.get('content', '')})
                    elif m.get("role") in ("assistant", "genesi", "system", "model"):
                        thread_lines.append(f"Genesi: {m.get('content', '')}")
                        if history:
                            history[-1]["system_response"] = m.get('content', '')
        except Exception as e:
            logger.error(f"Error loading conversation {conversation_id}: {e}")

    # Fallback and topic detection history
    if not thread_lines:
        history = chat_memory.get_messages(user_id, limit=15)
        if history:
            for entry in history:
                user_msg = entry.get("user_message", "")
                sys_resp = entry.get("system_response", "")
                if user_msg:
                    thread_lines.append(f"Utente: {user_msg}")
                if sys_resp:
                    thread_lines.append(f"Genesi: {sys_resp}")
                    
    if thread_lines:
        sections.append("CONVERSAZIONE RECENTE:\n" + "\n".join(thread_lines))

    # --- B) Stable identity summary ---
    if assembled_summary:
        sections.append("MEMORIA E PROFILO DELL'UTENTE:\n" + assembled_summary)
    else:
        assembler = ContextAssembler(None, None)
        profile_summary = assembler._summarize_profile(profile)
        if profile_summary:
            sections.append("INFORMAZIONI STABILI SULL'UTENTE:\n" + profile_summary)

    # --- C) Topic detection ---
    topic = detect_topic(current_message, history)
    sections.append(f"TEMA CORRENTE DELLA CONVERSAZIONE: {topic}")

    # --- D) Collegamento Neurale: se è una continuazione esplicita, inietta FILO DIRETTO ---
    neural_link = _detect_continuation(current_message, history)
    if neural_link:
        sections.append(neural_link)
    else:
        # --- D2) Narrative continuity: link last 2 user messages if related ---
        continuity = _detect_narrative_continuity(current_message, history)
        if continuity:
            sections.append(continuity)

    # --- E) Active document context ---
    doc_section = _inject_document_context(user_id, current_message, profile)
    if doc_section:
        sections.append(doc_section)

    # --- E2) System manuals context (autonomo) ---
    # Gate: consulta i manuali (ricerca vettoriale = chiamata embedding) SOLO quando il
    # messaggio è una vera richiesta di conoscenza/aiuto, non per le chiacchiere di gruppo.
    # Evita ~500ms di latenza per ogni "si", "perché", "anche noi" → niente risposte stantie.
    def _looks_like_knowledge_query(msg: str) -> bool:
        m = (msg or "").split("[")[0].strip()  # togli le annotazioni [GRUPPO...]/[Contenuto...]
        if len(m) < 12:
            return False
        ml = m.lower()
        if "?" in m:
            return True
        kw = ("come si", "come faccio", "come posso", "cosa", "perche", "quando", "quanto",
              "quale", "spiega", "spiegami", "consiglio", "consigli", "aiuto", "significa",
              "differenza", "che fare", "cosa fare",
              "sintomi", "sintomo", "cura", "curare", "rimedio", "rimedi", "malattia", "malato",
              "dolore", "fa male", "ho male", "mal di", "febbre", "tosse", "raffreddore",
              "influenza", "nausea", "vomito", "diarrea", "prurito", "gonfio", "sangue",
              "pressione", "diabete", "allergia", "infezione", "infiammazione", "medicin",
              "farmac", "testa", "pancia", "stomaco", "gola", "schiena", "petto", "cuore",
              "respir", "occhi", "orecchi", "denti", "gamba", "braccio", "pelle",
              "ansia", "panico", "stress", "depress", "insonnia", "dormire", "tristezza",
              "primo soccorso", "soccorso", "svenut", "ustione", "ferita", "veterinar",
              "cane", "gatto", "cucciolo", "animale", "parassit", "vaccin", "zecca", "pulci")
        return any(k in ml for k in kw)

    def _has_kb_topic(msg: str) -> bool:
        """Vero se il messaggio tocca un argomento da knowledge base (salute, veterinaria,
        psicologia, primo soccorso): merita la ricerca SEMANTICA, più precisa."""
        ml = (msg or "").split("[")[0].strip().lower()
        if len(ml) < 8:
            return False
        return any(k in ml for k in _KB_TOPIC_KW)

    def _inject_keyword_manuals() -> bool:
        """Ricerca keyword nei manuali (zero latenza). Fallback quando il RAG non pesca."""
        try:
            from core.manual_service import manual_service
            snip = manual_service.search(current_message, limit_chars=3000)
            if snip:
                sections.append(f"[MANUALI_SISTEMA_CONTESTO]\n{snip}\n[/MANUALI_SISTEMA_CONTESTO]\n"
                                f"ISTRUZIONE: Se rilevante, rispondi attingendo autonomamente dai manuali sopra.")
                logger.info("MANUAL_CONTEXT_INJECTED len=%d", len(snip))
                return True
        except Exception as me:
            logger.warning("MANUAL_CONTEXT_ERROR err=%s", me)
        return False

    # CONSULTAZIONE MANUALI — due livelli:
    #  • route di conoscenza (force_manuals) o argomento medico/vet/psico → RAG SEMANTICO
    #    sui 139k chunk (preciso: "mal di testa" → "Approccio alla cefalea"/"Emicrania").
    #  • domanda generica con "?" senza argomento KB → ricerca keyword (zero latenza extra).
    if force_manuals or _has_kb_topic(current_message):
        _injected = False
        try:
            from core.vector_memory import search_sync as _vsearch
            _good = [h for h in _vsearch(current_message, top_k=4) if h.get("score", 0) >= 0.04]
            if _good:
                _parts, _tot = [], 0
                for h in _good:
                    seg = ("[%s] %s" % (h.get("title") or "Manuale", (h.get("text") or "").strip()))[:1200]
                    _parts.append(seg)
                    _tot += len(seg)
                    if _tot >= 3000:
                        break
                _snippet = "\n\n".join(_parts)
                sections.append(
                    f"[MANUALI_SISTEMA_CONTESTO]\n{_snippet}\n[/MANUALI_SISTEMA_CONTESTO]\n"
                    f"ISTRUZIONE: Se pertinente, rispondi attingendo a queste informazioni dei manuali clinici. "
                    f"Parla con parole tue, MAI citare nomi di file o numeri di pagina. "
                    f"Per sintomi importanti o persistenti, ricorda con delicatezza di sentire un medico."
                )
                logger.info("MANUAL_CONTEXT_INJECTED_VEC chunks=%d len=%d top=%.3f",
                            len(_good), len(_snippet), _good[0]["score"])
                _injected = True
        except Exception as _ve:
            logger.warning("MANUAL_CONTEXT_VEC_ERROR err=%s", _ve)
        if not _injected:
            _inject_keyword_manuals()
    elif _looks_like_knowledge_query(current_message):
        _inject_keyword_manuals()

    return "\n\n".join(sections)


# ═══════════════════════════════════════════════════════════════
# COLLEGAMENTO NEURALE — rileva continuazione esplicita e inietta
# l'ultima risposta come FILO DIRETTO nel contesto LLM
# ═══════════════════════════════════════════════════════════════

import re as _re_cont

# Messaggi che sono esplicitamente una richiesta di continuazione
_CONTINUATION_PATTERNS = _re_cont.compile(
    r"^(continua\.?|puoi approfondire\??|approfondisci\.?|spiega(mi)? meglio\.?|"
    r"dimmi di più\.?|e (poi|quindi|allora)\??|come arrivi a (questa |questa )?conclusione\??|"
    r"perché\??|e come\??|e quindi\??|ma quindi\??|e poi\??|interessante\.?\s*(puoi)?\s*(approfondire|continuare|spiegare)?\??|"
    r"non (mi è|è) chiaro\.?|puoi chiarire\??|chiariscimi\.?|spiegami\.?|"
    r"sì,?\s*(ma)?\s*(come|perché|cosa intendi)\??|va bene,?\s*ma\s*(quindi|poi)\??|"
    r"mi stai dicendo che\??|quindi stai dicendo\??|in che senso\??|"
    r"questo mi fa pensare\.?\s*(continua\.?)?)$",
    _re_cont.IGNORECASE
)


def _detect_continuation(current_message: str, history: List[Dict]) -> str:
    """
    Se il messaggio è una continuazione esplicita, inietta l'ultima risposta
    di Genesi come FILO DIRETTO — istruisce l'LLM a non perdere il filo.
    """
    if not _CONTINUATION_PATTERNS.match(current_message.strip()):
        return ""
    if not history:
        return ""

    # Cerca l'ultima risposta di Genesi
    last_genesi = ""
    for entry in reversed(history):
        resp = entry.get("system_response", "")
        if resp and len(resp) > 20:
            last_genesi = resp
            break

    if not last_genesi:
        return ""

    # Tronca se troppo lunga
    preview = last_genesi[:400] + ("..." if len(last_genesi) > 400 else "")

    return (
        f"COLLEGAMENTO NEURALE — FILO DIRETTO OBBLIGATORIO:\n"
        f"Stavi dicendo: \"{preview}\"\n"
        f"L'utente dice: \"{current_message}\"\n"
        f"DEVI continuare ESATTAMENTE da dove ti eri fermata — stessa conversazione, stesso argomento, stessa profondità.\n"
        f"NON ricominciare da capo. NON cambiare tema. NON rispondere con frasi generiche.\n"
        f"Se l'utente dice 'continua' → sviluppa il punto precedente ulteriormente.\n"
        f"Se chiede 'perché/come' → spiega il ragionamento che ha portato a quella risposta."
    )


# ═══════════════════════════════════════════════════════════════
# NARRATIVE CONTINUITY — semantic linking of last 2 user messages
# ═══════════════════════════════════════════════════════════════

# Semantic clusters: words that indicate related topics
_SEMANTIC_CLUSTERS = {
    "stanchezza": {"stanco", "stanca", "dormito", "dormire", "sonno", "insonne",
                   "insonnia", "esausto", "esausta", "sveglio", "sveglia",
                   "riposo", "riposare", "sfinito", "sfinita", "spossato"},
    "tristezza": {"triste", "piango", "piangere", "lacrime", "depresso", "depressa",
                  "giù", "giu", "abbattuto", "abbattuta", "sconsolato", "male",
                  "infelice", "soffro", "soffrire", "dolore"},
    "ansia": {"ansioso", "ansiosa", "ansia", "preoccupato", "preoccupata",
              "paura", "panico", "agitato", "agitata", "nervoso", "nervosa",
              "stress", "stressato", "stressata", "tensione"},
    "lavoro": {"lavoro", "ufficio", "capo", "collega", "colleghi", "riunione",
               "progetto", "scadenza", "licenziato", "licenziata", "stipendio",
               "carriera", "promozione"},
    "relazioni": {"moglie", "marito", "fidanzato", "fidanzata", "partner",
                  "litigato", "litigio", "separazione", "divorzio", "amore",
                  "relazione", "coppia"},
    "salute": {"male", "dolore", "malato", "malata", "medico", "dottore",
               "ospedale", "febbre", "testa", "stomaco", "schiena"},
    "solitudine": {"solo", "sola", "solitudine", "isolato", "isolata",
                   "nessuno", "abbandonato", "abbandonata"},
}


def _detect_narrative_continuity(current_message: str, history: List[Dict]) -> str:
    """
    If last 2 user messages share a semantic cluster, return a continuity directive
    that forces the LLM to integrate them causally.
    """
    if not history:
        return ""

    # Get last user message from history
    prev_user_msgs = [e.get("user_message", "") for e in history if e.get("user_message")]
    if not prev_user_msgs:
        return ""

    last_user_msg = prev_user_msgs[-1].lower()
    current_lower = current_message.lower()

    # Find shared semantic clusters
    shared_clusters = []
    for cluster_name, keywords in _SEMANTIC_CLUSTERS.items():
        last_has = any(kw in last_user_msg for kw in keywords)
        current_has = any(kw in current_lower for kw in keywords)
        if last_has and current_has:
            shared_clusters.append(cluster_name)

    if shared_clusters:
        return (f"CONTINUITA' NARRATIVA OBBLIGATORIA:\n"
                f"L'utente ha appena detto: \"{prev_user_msgs[-1]}\"\n"
                f"Ora dice: \"{current_message}\"\n"
                f"Questi messaggi sono collegati (tema: {', '.join(shared_clusters)}).\n"
                f"DEVI collegare causalmente i due messaggi nella risposta.\n"
                f"NON trattarli come messaggi separati. NON usare fallback generico.")

    return ""


# ═══════════════════════════════════════════════════════════════
# DOCUMENT CONTEXT — inject active document into LLM context
# ═══════════════════════════════════════════════════════════════

_DOCUMENT_TRIGGERS = [
    "file", "documento", "immagine", "foto", "caricato", "caricata",
    "trascrivi", "riassumi", "riassunto", "cosa dice", "cosa c'è scritto",
    "cosa c'era scritto", "cosa c'e' scritto", "cosa c'era",
    "leggi", "analizza", "contenuto", "testo", "pdf",
    "screenshot", "schermata", "allegato",
    "cosa vedi", "cosa si vede", "descrivi", "estrai",
    "confronta", "compara", "differenze", "confronto",
]


def is_document_reference(message: str) -> bool:
    """Check if user message references an uploaded document."""
    msg_lower = message.lower()
    return any(trigger in msg_lower for trigger in _DOCUMENT_TRIGGERS)


# Marker del wrapper di gruppo (vedi telegram_bot._group_msg / api/chat).
_GROUP_CTX_TAIL_RE = _re.compile(r"\s*\[GRUPPO(?:\s+FAMILIARE)?:.*", _re.DOTALL | _re.IGNORECASE)


def extract_current_user_text(message: str) -> str:
    """Estrae il testo realmente scritto dall'utente da un wrapper di gruppo.

    Il path di gruppo (telegram_bot._group_msg, api/chat) costruisce un prompt che
    inizia con [IDENTITÀ ASSOLUTA: ...] e racchiude il messaggio reale in
    [MESSAGGIO ATTUALE ...]\\n<Nome>: <testo>\\n[FINE MESSAGGIO ATTUALE], seguito dal
    group_ctx con lo storico del gruppo. Passare questo blob intero alla logica
    testuale a valle (is_document_reference, chat_memory) inquina tutto: parole come
    "foto"/"immagine" nello storico falsano il gate documenti e il wrapper viene
    salvato come user_message. Questa funzione isola il solo testo dell'utente.

    Fallback: se non c'è il blocco [MESSAGGIO ATTUALE], rimuove solo il group_ctx.
    """
    if not message:
        return ""
    # Directive-only: nessun testo utente reale (es. azione di sistema sui volti).
    if "[NESSUN NUOVO MESSAGGIO" in message:
        return ""
    if "[MESSAGGIO ATTUALE" not in message:
        return _GROUP_CTX_TAIL_RE.sub("", message).strip()
    seg = message.split("[MESSAGGIO ATTUALE", 1)[1]
    # Scarta l'header del marker fino al primo ']'.
    if "]" in seg:
        seg = seg.split("]", 1)[1]
    # Tronca al fine-blocco o al successivo blocco tra parentesi quadre.
    for _stop in ("[FINE MESSAGGIO ATTUALE]", "\n["):
        _i = seg.find(_stop)
        if _i != -1:
            seg = seg[:_i]
    seg = seg.strip()
    # Variante emoji: "[MESSAGGIO ATTUALE — Nome]: <testo>" → resta ": <testo>".
    seg = _re.sub(r"^\s*:\s*", "", seg)
    # Variante standard: "<Nome>: <testo>" → rimuove il prefisso del nome.
    seg = _re.sub(r"^[^\n:]{1,40}:\s*", "", seg, count=1)
    return seg.strip()


def _format_doc_block(doc: Dict[str, Any], is_most_recent: bool = False) -> str:
    """Format a single document as a [DOCUMENT_CONTEXT] block (max 2000 chars content)."""
    raw_content = doc.get("content", "")
    summary = doc.get("summary", "")

    if len(raw_content) > 2000 and summary:
        content_section = (f"RIASSUNTO:\n{summary}\n\n"
                           f"PRIMI 2000 CARATTERI:\n{raw_content[:2000]}")
    elif len(raw_content) > 2000:
        content_section = raw_content[:2000] + "\n[...contenuto troncato...]"
    else:
        content_section = raw_content

    recency_tag = " (PIÙ RECENTE)" if is_most_recent else ""
    return (f"[DOCUMENT_CONTEXT{recency_tag}]\n"
            f"filename: {doc.get('filename', '?')}\n"
            f"type: {doc.get('type', '?')}\n"
            f"content:\n<<<\n{content_section}\n>>>\n"
            f"[/DOCUMENT_CONTEXT]")


def _inject_document_context(user_id: str, message: str,
                              profile: Dict[str, Any]) -> str:
    """
    If user has active documents and message references them,
    select relevant docs and inject their content into LLM context.
    Supports multi-document (max 2 per query).
    """
    # Support both new active_documents list and legacy active_document_id
    active_docs = profile.get("active_documents", [])
    if not active_docs:
        old_id = profile.get("active_document_id")
        if old_id:
            active_docs = [old_id]

    if not active_docs:
        return ""

    # I più recenti sono in fondo — invertiamo per dargli priorità nel selector
    active_docs_recent_first = list(reversed(active_docs))

    # GATE: NON iniettare a ogni turno. Inietta SOLO se:
    #  (a) il messaggio referenzia esplicitamente un documento/foto, OPPURE
    #  (b) il doc più recente è stato caricato da poco (finestra post-upload).
    # Senza questo gate il selector di default re-iniettava gli ultimi 2 doc a OGNI
    # messaggio (immagine vecchia re-iniettata 9×) → LLM perdeva la domanda reale
    # e/o forzava "rispondi sui file" su messaggi non correlati.
    _DOC_FRESH_WINDOW = 180  # secondi: finestra "appena caricato"
    # Riferimento valutato SOLO sul testo reale dell'utente: nei gruppi il messaggio
    # arriva wrappato con lo storico, dove parole come "foto"/"immagine" di turni
    # passati facevano risultare _references=True a ogni turno → SKIP non scattava mai.
    _references = is_document_reference(extract_current_user_text(message))
    _fresh = False
    _most_recent_id = active_docs_recent_first[0] if active_docs_recent_first else None
    if _most_recent_id and not _references:
        try:
            import re as _re_doc, time as _time_doc, calendar as _cal_doc
            _m = _re_doc.search(r'_(\d{14})_', _most_recent_id)
            if _m:
                # timestamp nel doc_id è UTC (datetime.utcnow in upload.py) → timegm
                _up = _cal_doc.timegm(_time_doc.strptime(_m.group(1), "%Y%m%d%H%M%S"))
                _fresh = (_time_doc.time() - _up) <= _DOC_FRESH_WINDOW
        except Exception:
            _fresh = False
    if not _references and not _fresh:
        _structured_log("DOCUMENT_CONTEXT_SKIP", user_id=user_id,
                        reason="no_reference_not_fresh", most_recent=_most_recent_id)
        return ""

    # Use document selector to pick relevant docs
    selected = resolve_documents(message, user_id, active_docs_recent_first)
    if not selected:
        return ""

    # GLOBALE (tutte le piattaforme): se il doc più recente è APPENA stato caricato,
    # l'utente si riferisce a QUELLO, non alle immagini precedenti. Inietta solo il più
    # recente, a meno che non chieda esplicitamente un confronto tra più file. Senza
    # questo, una nuova foto "tirava dentro" le foto vecchie in modo divergente tra
    # piattaforme (dipendeva da quanti doc storici esistevano per quel user_id).
    if _fresh and _most_recent_id:
        _wants_compare = bool(_re.search(
            r'\b(confront|compar|differenz|entramb|tutte le|le due|le altre|quella di prima|precedent)',
            extract_current_user_text(message).lower(),
        ))
        if not _wants_compare:
            selected = [d for d in selected if d.get("doc_id") == _most_recent_id] or selected[:1]

    # Il primo nella lista è il più recente (dopo il reverse)
    most_recent_id = active_docs_recent_first[0] if active_docs_recent_first else None

    # Build context blocks — più recente per primo
    blocks = []
    for i, doc in enumerate(selected):
        is_most_recent = (doc.get("doc_id") == most_recent_id)
        blocks.append(_format_doc_block(doc, is_most_recent=is_most_recent))
        logger.info("DOCUMENT_CONTEXT_INJECTED doc_id=%s type=%s recent=%s",
                    doc.get("doc_id"), doc.get("type"), is_most_recent)
        _structured_log("DOCUMENT_CONTEXT_INJECTED", doc_id=doc.get("doc_id"),
                        doc_type=doc.get("type"), most_recent=is_most_recent)

    doc_count = len(selected)
    instruction = (
        f"ISTRUZIONE: L'utente si riferisce a {'questi file' if doc_count > 1 else 'questo file'}. "
        f"Rispondi usando il contenuto {'dei file' if doc_count > 1 else 'del file'} sopra. "
        f"NON dire che non hai accesso al file. HAI il contenuto. "
        f"NON rispondere con frasi generiche. USA i dati {'dei file' if doc_count > 1 else 'del file'}. "
        f"Il file contrassegnato come (PIÙ RECENTE) è quello caricato per ultimo — dagli priorità se l'utente non specifica quale. "
        f"Se l'utente chiede di confrontare più file o immagini, usa tutti quelli disponibili qui sopra."
    )

    return "\n\n".join(blocks) + "\n\n" + instruction
