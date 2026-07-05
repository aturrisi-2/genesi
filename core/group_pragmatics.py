"""
Policy pragmatica globale per messaggi di gruppo.

La policy separa due decisioni che non vanno confuse:
- se Genesi deve intervenire (gate, gia' gestito da group_reactivity/Baileys);
- con quale postura deve rispondere quando interviene.

Vale per Telegram e WhatsApp: nei gruppi Genesi non deve assumere che pronomi,
auguri, condoglianze o congratulazioni siano rivolti a lei solo perche' e' nel
gruppo. Se interviene autonomamente parla come osservatrice discreta, non come
destinataria umana del messaggio.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from core.group_reactivity import detect_autonomous_group_trigger, is_emoji_only_or_reaction


POSTURE_DIRECT_ASSISTANT = "direct_assistant"
POSTURE_DRAFT_HELPER = "draft_helper"
POSTURE_ASSISTANT_OBSERVER = "assistant_observer"
POSTURE_NEUTRAL_SUPPORT = "neutral_support"
POSTURE_SILENT = "silent"


_GENESI_RE = re.compile(r"\b(?:genesi|@genesi\w*|genesiai_bot)\b", re.IGNORECASE)
_DRAFT_HELPER_RE = re.compile(
    r"\b(?:"
    r"rispondi\s+(?:in\s+modo\s+\w+\s+)?(?:a|alla|al|quest[ao])|"
    r"aiutami\s+a\s+rispondere|"
    r"come\s+(?:posso|potrei|dovrei)\s+rispondere|"
    r"mi\s+(?:scrivi|prepari|formuli)\s+(?:una\s+)?risposta|"
    r"fammi\s+(?:una\s+)?bozza|"
    r"scrivi\s+(?:una\s+)?risposta|"
    r"bozza\s+(?:di\s+)?risposta"
    r")\b",
    re.IGNORECASE,
)
_ASSISTIVE_REQUEST_RE = re.compile(
    r"\b(?:cosa\s+ne\s+pensi|che\s+ne\s+pensi|puoi|riesci|mi\s+aiuti|aiutami|"
    r"spiegami|dimmi|continua|approfondisci|riassumi|consigliami|secondo\s+te)\b",
    re.IGNORECASE,
)
_GROUP_ADDRESS_RE = re.compile(r"\b(?:ragazzi|tutti|tutte|voi|ci|noi|gruppo)\b", re.IGNORECASE)
_HUMAN_ADDRESS_RE = re.compile(
    r"\b(?:ti|te|tu|tua|tuo|tue|tuoi|vi|vostra|vostro|grazie|auguri|"
    r"mi\s+dispiace|complimenti|bravissim[oaie]|brav[oaie])\b",
    re.IGNORECASE,
)
_INSUFFICIENT_CONTEXT_RE = re.compile(
    r"\b(?:questa\s+perdita|questo\s+momento|momento\s+difficile|situazione\s+delicata|"
    r"ti\s+siamo\s+vicini|vi\s+siamo\s+vicini|mi\s+dispiace)\b",
    re.IGNORECASE,
)

_FORBIDDEN_OBSERVER_PATTERNS = (
    r"\bgrazie\s+(?:di\s+cuore\s+)?per\s+gli\s+auguri\b",
    r"\bgrazie\s+(?:di\s+cuore\s+)?per\s+il\s+sostegno\b",
    r"\bil\s+tuo\s+sostegno\s+significa\s+molto\b",
    r"\be'? un momento difficile per me\b",
    r"\bla tua vicinanza mi aiuta\b",
    r"\bsono felice per me\b",
    r"\bsono felicissim[oa]\b",
    r"\bsono felice,\s*grazie\b",
    r"\bmi avete fatto felice\b",
    r"\bgrazie,\s*[^.!\n]{0,40}\b(?:la tua vicinanza|il tuo supporto|il tuo sostegno)\b",
)
_FORBIDDEN_OBSERVER_RE = re.compile("|".join(_FORBIDDEN_OBSERVER_PATTERNS), re.IGNORECASE)
_DRAFT_COMPLIANT_RE = re.compile(
    r"\b(?:puoi\s+rispondere\s+cos[iì]|se\s+vuoi\s+(?:una\s+)?risposta|"
    r"potresti\s+(?:rispondere|scrivere)|ti\s+suggerisco\s+di\s+rispondere|"
    r"una\s+bozza|bozza\s*:|risposta\s+sobria)\b",
    re.IGNORECASE,
)
_DIRECT_REPLY_TO_DRAFT_RE = re.compile(
    r"^\s*(?:mi\s+dispiace|sono\s+vicin[oa]|ti\s+sono\s+vicin[oa]|un\s+abbraccio|"
    r"capisco\s+il\s+dolore|grazie\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GroupMessageRole:
    directed_to_genesi: bool = False
    addressed_to_human: bool = False
    addressed_to_group: bool = False
    social_event: bool = False
    delicate_event: bool = False
    asks_genesi_to_draft_reply: bool = False
    insufficient_context: bool = False
    recommended_response_posture: str = POSTURE_SILENT
    confidence: float = 0.0
    reason: str = "silent"

    @property
    def non_direct_observer(self) -> bool:
        return self.recommended_response_posture in {
            POSTURE_ASSISTANT_OBSERVER,
            POSTURE_NEUTRAL_SUPPORT,
        }


def classify_group_message_role(
    text: str,
    *,
    bot_mentioned: bool = False,
    reply_to_genesi: bool = False,
    has_media: bool = False,
) -> GroupMessageRole:
    """Classifica la postura pragmatica di un messaggio di gruppo."""
    raw = (text or "").strip()
    if not raw:
        return GroupMessageRole(
            insufficient_context=True,
            recommended_response_posture=POSTURE_SILENT,
            confidence=0.95,
            reason="empty_or_media_only",
        )
    if is_emoji_only_or_reaction(raw):
        return GroupMessageRole(
            addressed_to_group=True,
            recommended_response_posture=POSTURE_SILENT,
            confidence=0.95,
            reason="emoji_only",
        )

    explicit = bool(bot_mentioned or reply_to_genesi or _GENESI_RE.search(raw))
    asks_draft = bool(_DRAFT_HELPER_RE.search(raw))
    trigger = detect_autonomous_group_trigger(raw, has_media=has_media)
    social = bool(trigger and trigger.get("topic") == "positive_social")
    delicate = bool(trigger and trigger.get("topic") == "delicate_support")
    human_addressed = bool(_HUMAN_ADDRESS_RE.search(raw)) and not explicit
    group_addressed = bool(_GROUP_ADDRESS_RE.search(raw))
    insufficient = bool(_INSUFFICIENT_CONTEXT_RE.search(raw)) and not explicit

    if explicit and asks_draft:
        return GroupMessageRole(
            directed_to_genesi=True,
            addressed_to_human=False,
            addressed_to_group=group_addressed,
            social_event=social,
            delicate_event=delicate,
            asks_genesi_to_draft_reply=True,
            insufficient_context=False,
            recommended_response_posture=POSTURE_DRAFT_HELPER,
            confidence=0.92,
            reason="explicit_draft_request",
        )

    if explicit or reply_to_genesi:
        return GroupMessageRole(
            directed_to_genesi=True,
            addressed_to_human=False,
            addressed_to_group=group_addressed,
            social_event=social,
            delicate_event=delicate,
            asks_genesi_to_draft_reply=False,
            insufficient_context=False,
            recommended_response_posture=POSTURE_DIRECT_ASSISTANT,
            confidence=0.88,
            reason="explicit_direct_assistant",
        )

    if delicate:
        return GroupMessageRole(
            addressed_to_human=True,
            addressed_to_group=group_addressed,
            delicate_event=True,
            insufficient_context=insufficient or human_addressed,
            recommended_response_posture=POSTURE_NEUTRAL_SUPPORT if (insufficient or human_addressed) else POSTURE_ASSISTANT_OBSERVER,
            confidence=0.82,
            reason="autonomous_delicate_observer",
        )

    if social:
        return GroupMessageRole(
            addressed_to_human=True,
            addressed_to_group=group_addressed,
            social_event=True,
            insufficient_context=False,
            recommended_response_posture=POSTURE_ASSISTANT_OBSERVER,
            confidence=0.82,
            reason="autonomous_social_observer",
        )

    if _ASSISTIVE_REQUEST_RE.search(raw):
        return GroupMessageRole(
            addressed_to_group=group_addressed,
            recommended_response_posture=POSTURE_SILENT,
            confidence=0.55,
            reason="assistive_words_without_genesi",
        )

    return GroupMessageRole(
        addressed_to_human=human_addressed,
        addressed_to_group=group_addressed or not human_addressed,
        insufficient_context=insufficient,
        recommended_response_posture=POSTURE_SILENT,
        confidence=0.7,
        reason="human_or_group_message",
    )


def group_pragmatic_prompt(role: GroupMessageRole, sender_name: str = "") -> str:
    """Restituisce un blocco di istruzioni da iniettare nel prompt gruppo."""
    sender = sender_name or "chi scrive"
    base = (
        "[POLICY PRAGMATICA GRUPPO: Prima interpreta il ruolo del messaggio. "
        "Non assumere che tu/te/ti/tua/tuo/voi/grazie/auguri/mi dispiace siano rivolti a Genesi. "
        "Se il messaggio non menziona Genesi, non e' reply a Genesi e non chiede chiaramente aiuto al bot, "
        "trattalo come interazione tra umani o messaggio al gruppo. Non impersonare il destinatario umano. "
        "Le righe storiche '→ Genesi:' sono memoria del gruppo, non uno stile da imitare.]\n"
    )
    if role.recommended_response_posture == POSTURE_DRAFT_HELPER:
        return (
            base +
            "[POSTURA: draft_helper. L'utente sta chiedendo a Genesi di formulare una risposta. "
            "Produci una bozza o un consiglio, per esempio 'Puoi rispondere cosi: ...'. "
            "Non rispondere come se la frase citata fosse rivolta a te.]\n"
        )
    if role.recommended_response_posture == POSTURE_DIRECT_ASSISTANT:
        return (
            base +
            f"[POSTURA: direct_assistant. Il messaggio e' rivolto a Genesi da {sender}; "
            "rispondi direttamente come assistente del gruppo, senza impersonare altri membri.]\n"
        )
    if role.recommended_response_posture == POSTURE_NEUTRAL_SUPPORT:
        return (
            base +
            "[POSTURA: neutral_support. Sembra un evento delicato tra persone del gruppo, ma il contesto e' incompleto. "
            "Se rispondi, parla con discrezione come osservatrice: 'Non conosco bene il contesto...' o "
            "'Da quello che leggo sembra...'. Non dire grazie per il sostegno, non parlare come persona colpita.]\n"
        )
    if role.recommended_response_posture == POSTURE_ASSISTANT_OBSERVER:
        event = "sociale" if role.social_event else "delicato"
        return (
            base +
            f"[POSTURA: assistant_observer. Questo e' un evento {event} osservabile nel gruppo. "
            "Se intervieni, unisciti o sostieni con discrezione come Genesi, senza appropriarti del ruolo umano. "
            "Per auguri/congratulazioni non dire 'grazie'; per lutto/supporto non dire che il sostegno e' per te.]\n"
        )
    return base + "[POSTURA: silent. Se non c'e' una ragione forte per intervenire, resta silenziosa.]\n"


# --------------------------------------------------------------------------- #
# Anti-leak: rimuove dal testo di risposta i marker di contesto interno che il
# LLM ha erroneamente ricopiato nell'output (context leak). Platform-independent:
# usato sia da Telegram sia da WhatsApp per evitare divergenze (WA prima ne era
# sprovvisto → prompt grezzo inviato in chat). Fonte unica di verità.
# --------------------------------------------------------------------------- #

# Marker con parentesi quadra dei blocchi iniettati in build_group_context() e
# nei wrapper di gruppo (telegram_bot / whatsapp_bot). Il match è per RIGA: una
# riga che contiene uno di questi token è interamente scartata.
LEAKED_CONTEXT_MARKERS: tuple[str, ...] = (
    '[INFO GRUPPO', '[CONTEGGIO MEMBRI', '[LISTA DETTAGLIATA MEMBRI',
    '[⚠️', '[MEMORIA EPISODICA', '[DINAMICHE DELLA FAMIGLIA',
    '[RIEPILOGO DISCUSSIONI', '[COSA SO DI ', '[IDENTITÀ ASSOLUTA',
    '[MESSAGGIO ATTUALE', '[FINE MESSAGGIO', '[GRUPPO FAMILIARE',
    '[GRUPPO ESTERNO', '[ISTRUZIONE PRIORITARIA',
    '[DISCUSSIONE IN CORSO', '[FINE DISCUSSIONE', '[RISPOSTE RECENTI',
    '[FINE RISPOSTE', '[CONTESTO FAMIGLIA', '[CONTESTO SPECIFICO',
    '[COERENZA CONVERSAZIONALE', '[ATTENZIONE ASSOLUTA', '[POSTURA',
    '[REGOLE ASSOLUTE', '[NON copiare', '[📅', '[CONTESTO TEMPORALE',
    'COERENZA:', 'GUARDIA:', 'REGOLE ASSOLUTE:',
)

# Frasi parafrasate del contesto interno (l'LLM ripete il senso SENZA le
# parentesi, quindi i marker sopra non bastano). Match a livello di FRASE.
LEAKED_CONTEXT_PHRASES: tuple[str, ...] = (
    'account secondari', 'albero genealogico', 'non allucinare',
    'non confonderli', 'membri del gruppo', 'assistente AI del gruppo',
    'entra nel discorso già informata',
)


def strip_leaked_context_markers(reply: str) -> tuple[str, bool]:
    """Rimuove prefisso 'Genesi:' + righe con marker interni + frasi parafrasate
    di contesto. Ritorna (testo_pulito, changed). Non solleva mai. Generico."""
    import re as _re

    original = reply or ""
    out = _re.sub(r'^\s*Genesi\s*:\s*', '', original, flags=_re.IGNORECASE)
    out = '\n'.join(
        line for line in out.split('\n')
        if not any(m in line for m in LEAKED_CONTEXT_MARKERS)
    ).strip()
    if any(p.lower() in out.lower() for p in LEAKED_CONTEXT_PHRASES):
        kept = [
            s for s in _re.split(r'(?<=[.!?])\s+', out)
            if not any(p.lower() in s.lower() for p in LEAKED_CONTEXT_PHRASES)
        ]
        out = ' '.join(kept).strip()
    return out, (out != original)


def sanitize_group_observer_response(response: str, role: GroupMessageRole) -> tuple[str, bool]:
    """
    Fallback difensivo anti-impersonificazione.

    Se l'output di un intervento autonomo parla come destinatario umano di auguri,
    lutto o sostegno, lo sostituisce con una formulazione neutra riusabile.
    """
    text = (response or "").strip()
    if not text or not role.non_direct_observer:
        return response, False
    if not _FORBIDDEN_OBSERVER_RE.search(text):
        return response, False

    if role.delicate_event:
        return (
            "Non conosco bene il contesto, ma sembra un momento delicato. "
            "Meglio restare vicini con parole semplici e rispettose."
        ), True
    if role.social_event:
        return "Mi unisco con discrezione a questo momento bello del gruppo.", True
    return "Da quello che leggo, meglio rispondere con discrezione e rispetto.", True


def _draft_fallback(role: GroupMessageRole) -> str:
    if role.delicate_event or role.insufficient_context:
        return (
            "Puoi rispondere così: «Ti sono vicino/a in questo momento difficile. "
            "Un abbraccio sincero.»"
        )
    if role.social_event:
        return "Puoi rispondere così: «Che bella notizia, sono davvero felice per te.»"
    return "Puoi rispondere così: «Grazie per avermelo detto. Ti rispondo con calma appena posso.»"


def enforce_group_pragmatic_response(response: str, role: GroupMessageRole) -> tuple[str, bool, str]:
    """
    Rende vincolante la postura pragmatica dopo la generazione.

    Ritorna (testo, changed, reason). Il caller deve loggare reason quando
    changed=True. Mantiene `sanitize_group_observer_response()` come API storica
    per i soli casi observer/neutral_support.
    """
    text = (response or "").strip()
    if role.recommended_response_posture == POSTURE_DRAFT_HELPER:
        if not text:
            return _draft_fallback(role), True, "empty_output"
        if _DRAFT_COMPLIANT_RE.search(text) and not _DIRECT_REPLY_TO_DRAFT_RE.search(text):
            return response, False, ""
        return _draft_fallback(role), True, "non_compliant_output"

    safe, changed = sanitize_group_observer_response(response, role)
    if changed:
        return safe, True, "impersonation_output"
    return response, False, ""
