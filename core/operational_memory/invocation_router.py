"""FASE 7 — Explicit Invocation Router.

Decide whether an incoming chat message is addressed to Genesi. Default is
SILENT: Genesi never answers unless explicitly invoked. The decision is fully
deterministic — no LLM, no heuristics about "intent to talk". Genesi answers
only when:
  * named/tagged (e.g. "Genesi, ..." or "@genesi ..."),
  * a configured command prefix is used (e.g. "/genesi ..."),
  * the message arrives in a direct chat (if the project allows it),
  * an authorized trigger phrase is present.

Everything here is generic and configurable per project — no chat/platform/
profession token is hardcoded."""

from __future__ import annotations

import re

from core.operational_memory.models import InvocationConfig, InvocationDecision


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _strip_leading(text: str, token: str) -> str:
    """Remove a leading name/tag/command token (and a following separator)."""
    pattern = re.compile(rf"^\s*{re.escape(token)}\b[\s,:;>\-—]*", re.IGNORECASE)
    return pattern.sub("", text, count=1).strip()


def _default_query_if_empty(query: str) -> str:
    # Bare invocation ("Genesi", "Genesi?") defaults to the general briefing.
    return query if re.search(r"\w", query or "") else "fammi il punto"


def is_invoked(
    text: str,
    config: InvocationConfig | None = None,
    is_dm: bool = False,
) -> InvocationDecision:
    config = config or InvocationConfig()
    message = _norm(text)
    if not message:
        return InvocationDecision(respond=False, mode="silent", reason="messaggio vuoto")

    lowered = message.lower()

    # 1. Command prefix (highest precedence, explicit).
    for prefix in config.command_prefixes:
        prefix_norm = prefix.strip().lower()
        if prefix_norm and lowered.startswith(prefix_norm):
            query = _default_query_if_empty(message[len(prefix):].strip())
            return InvocationDecision(respond=True, mode="command", query=query, reason=f"comando esplicito '{prefix}'")

    # 2. Tag / name mention.
    for name in config.bot_names:
        name_norm = name.strip().lower()
        if not name_norm:
            continue
        # @tag anywhere
        tag = f"@{name_norm}"
        if tag in lowered:
            query = _default_query_if_empty(re.sub(rf"@{re.escape(name_norm)}", "", message, flags=re.IGNORECASE).strip())
            return InvocationDecision(respond=True, mode="tag", query=query, reason=f"tag @{name}")
        # leading name ("Genesi, ...") or whole-word mention
        if re.match(rf"^\s*{re.escape(name_norm)}\b", lowered):
            query = _default_query_if_empty(_strip_leading(message, name))
            return InvocationDecision(respond=True, mode="name", query=query, reason=f"nome '{name}' a inizio messaggio")

    # 3. Authorized trigger phrases (exact, generic).
    for trigger in config.authorized_triggers:
        trigger_norm = trigger.strip().lower()
        if trigger_norm and trigger_norm in lowered:
            return InvocationDecision(respond=True, mode="trigger", query=message, reason=f"trigger autorizzato '{trigger}'")

    # 4. Direct message channel.
    if is_dm and config.respond_in_dm:
        return InvocationDecision(respond=True, mode="dm", query=_default_query_if_empty(message), reason="messaggio diretto")

    # Default: stay silent.
    return InvocationDecision(respond=False, mode="silent", reason="nessuna invocazione esplicita")
