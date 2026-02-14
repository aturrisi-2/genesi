"""
DOCUMENT SELECTOR - Genesi Core v2
Seleziona documenti rilevanti per una query utente.
Logica: filename match > type match > "ultimo" > default ultimi 2.
Max 2 documenti iniettati per query.
"""

import logging
from typing import List, Dict, Any
from core.document_memory import load_document, reinforce_document
from core.log import log

logger = logging.getLogger(__name__)

_MAX_INJECTED = 2

# Type aliases for matching
_TYPE_KEYWORDS = {
    "pdf": ["pdf"],
    "image": ["immagine", "foto", "screenshot", "schermata"],
    "text": ["testo", "file di testo", "txt", "codice"],
}


def resolve_documents(message: str, user_id: str,
                      active_doc_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Select the most relevant documents for a user query.

    Priority:
    1. Explicit filename match
    2. Type match (pdf, immagine, foto)
    3. "ultimo" / "più recente" → most recent
    4. Default → last 2 documents (by insertion order)

    Args:
        message: User message
        user_id: User ID
        active_doc_ids: List of active document IDs (most recent last)

    Returns:
        List of document dicts (max 2)
    """
    if not active_doc_ids:
        return []

    # Load all documents, filter by status
    all_docs = []
    for doc_id in active_doc_ids:
        doc = load_document(doc_id)
        if doc:
            all_docs.append(doc)

    if not all_docs:
        return []

    # Prefer active docs; if none, include passive; exclude archived
    docs = [d for d in all_docs if d.get("status", "active") == "active"]
    if not docs:
        docs = [d for d in all_docs if d.get("status", "active") != "archived"]

    if not docs:
        return []

    msg_lower = message.lower()
    selected = []

    # 1. Explicit filename match
    for doc in docs:
        fname = doc.get("filename", "").lower()
        # Check if any significant part of the filename appears in the message
        fname_base = fname.rsplit(".", 1)[0] if "." in fname else fname
        if fname_base and len(fname_base) > 2 and fname_base in msg_lower:
            selected.append(doc)

    if selected:
        selected = selected[:_MAX_INJECTED]
        log("DOCUMENTS_SELECTED", ids=[d["doc_id"] for d in selected], reason="filename_match")
        return _reinforce_selected(selected)

    # 2. Type match
    for type_key, keywords in _TYPE_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            type_matches = [d for d in docs if d.get("type") == type_key]
            if type_matches:
                selected = type_matches[:_MAX_INJECTED]
                log("DOCUMENTS_SELECTED", ids=[d["doc_id"] for d in selected], reason="type_match")
                return _reinforce_selected(selected)

    # 3. "ultimo" / "più recente" → most recent
    recency_keywords = ["ultimo", "ultima", "più recente", "piu recente", "appena caricato",
                        "appena caricata"]
    if any(kw in msg_lower for kw in recency_keywords):
        selected = [docs[-1]]  # docs are ordered oldest→newest (active_doc_ids order)
        log("DOCUMENTS_SELECTED", ids=[d["doc_id"] for d in selected], reason="recency")
        return _reinforce_selected(selected)

    # 4. "confronta" / "compara" → last 2
    compare_keywords = ["confronta", "compara", "differenze", "confronto", "paragona",
                        "paragone", "similitudini"]
    if any(kw in msg_lower for kw in compare_keywords) and len(docs) >= 2:
        selected = docs[-2:]
        log("DOCUMENTS_SELECTED", ids=[d["doc_id"] for d in selected], reason="comparison")
        return _reinforce_selected(selected)

    # 5. Default → last 2 documents
    selected = docs[-_MAX_INJECTED:]
    log("DOCUMENTS_SELECTED", ids=[d["doc_id"] for d in selected], reason="default")
    return _reinforce_selected(selected)


def _reinforce_selected(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reinforce all selected documents (bump importance + access count)."""
    for doc in docs:
        try:
            reinforce_document(doc["doc_id"])
        except Exception:
            pass
    return docs
