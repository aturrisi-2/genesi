"""
GROUP CONTEXT — Genesi Core
Porta il contesto di gruppo/piattaforma lungo tutta la pipeline conversazionale.
Tutti i campi sono opzionali: se non forniti il comportamento resta invariato.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class GroupContext:
    platform: str = "web"           # "telegram", "whatsapp", "web"
    group_id: str = ""              # slug identificativo, es. "casa_turrisi"
    group_name: str = ""            # nome leggibile, es. "Casa Turrisi"
    member_count: Optional[int] = None


def build_group_prompt_block(ctx: Optional["GroupContext"]) -> str:
    """
    Costruisce il blocco da iniettare nel system prompt.
    Ritorna stringa vuota se il contesto non è significativo → nessuna regressione.
    """
    if not ctx:
        return ""
    if not ctx.group_id and not ctx.group_name and ctx.platform == "web":
        return ""

    lines = ["CONTESTO GRUPPO:"]

    if ctx.platform and ctx.platform != "web":
        lines.append(f"- Piattaforma: {ctx.platform.capitalize()}")

    if ctx.group_name:
        lines.append(f"- Gruppo: {ctx.group_name}")
    elif ctx.group_id:
        lines.append(f"- Gruppo: {ctx.group_id}")

    if ctx.member_count is not None:
        lines.append(f"- Membri presenti: {ctx.member_count}")

    tone = _infer_tone(ctx)
    if tone:
        lines.append(f"- Tono da usare: {tone}")

    return "\n".join(lines)


def _infer_tone(ctx: "GroupContext") -> str:
    combined = f"{ctx.group_id} {ctx.group_name}".lower()

    if any(k in combined for k in ["casa", "turrisi", "famiglia", "family", "home"]):
        return "familiare e affettuoso, come con persone care"
    if any(k in combined for k in ["swift", "dev", "tech", "lavoro", "work", "code", "coding"]):
        return "professionale e tecnico, preciso"
    if any(k in combined for k in ["prova", "test", "sandbox"]):
        return "naturale e diretto, senza cerimonie"
    return ""
