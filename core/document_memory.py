"""
DOCUMENT MEMORY - Genesi Core v3
Persistenza documenti caricati per utente.
Salva/carica documenti in memory/documents/.
Auto-summary e auto-title via llm_service (con fallback OpenRouter).
Decay: documenti non usati da X giorni vengono archiviati.
"""

import json
import os
import re
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from core.log import log

logger = logging.getLogger(__name__)

_DOCUMENTS_DIR = "memory/documents"
os.makedirs(_DOCUMENTS_DIR, exist_ok=True)

_SUMMARY_THRESHOLD = 4000


def _doc_path(doc_id: str) -> str:
    return os.path.join(_DOCUMENTS_DIR, f"{doc_id}.json")


def _sanitize_filename(filename: str) -> str:
    """Rimuove codici tecnici dal nome file, lascia solo parole significative."""
    name = os.path.splitext(filename)[0]
    # Rimuove pattern tipo "Mod 07.69-SM_MEC_239.00", numeri isolati
    name = re.sub(r'\b[A-Z]{2,5}[\d._\-]+\d+\b', '', name)
    name = re.sub(r'\b\d+[\d._\-]*\d*\b', '', name)
    name = re.sub(r'[_\-\.]+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:50] if name else filename[:30]


async def _generate_title(content: str, filename: str, file_type: str) -> str:
    """
    Genera un titolo breve (max 6 parole) basato sul contenuto del documento.
    Usa llm_service per beneficiare del fallback OpenRouter.
    """
    try:
        from core.llm_service import llm_service
        sys_prompt = (
            "Sei un archivista. Genera UN SOLO titolo breve in italiano (max 6 parole, max 50 caratteri) "
            "che descriva il CONTENUTO del documento. NON usare il nome del file originale. "
            "Solo il titolo, niente altro. Esempi: 'Specifiche tecniche radiatore', "
            "'Fattura forniture marzo', 'Lista terminali meccanici torre 1', 'Foto paesaggio montagna'."
        )
        preview = content[:600] if content else ""
        hint = f"Tipo file: {file_type}.\nContenuto:\n{preview}"
        title = await llm_service._call_with_protection(
            "gpt-4o-mini", sys_prompt, hint, route="doc_title"
        )
        if title:
            return title.strip()[:60]
    except Exception as e:
        logger.warning("DOCUMENT_TITLE_ERROR filename=%s error=%s", filename, str(e))
    return _sanitize_filename(filename)


async def _generate_summary(content: str, filename: str) -> str:
    """Generate a summary for large documents using llm_service (with OpenRouter fallback)."""
    try:
        from core.llm_service import llm_service
        text_for_summary = content[:6000]
        sys_prompt = (
            "Sei un analizzatore di documenti. "
            "Genera un riassunto conciso in italiano del documento fornito. "
            "Massimo 5 frasi. Includi i punti chiave e i dati principali."
        )
        user_msg = f"Riassumi questo documento ({filename}):\n\n{text_for_summary}"
        summary = await llm_service._call_with_protection(
            "gpt-4o-mini", sys_prompt, user_msg, route="doc_summary"
        )
        if summary:
            log("DOCUMENT_SUMMARY_GENERATED", filename=filename, summary_len=len(summary.strip()))
            return summary.strip()
    except Exception as e:
        logger.error("DOCUMENT_SUMMARY_ERROR filename=%s error=%s", filename, str(e))
    # Fallback: first 500 chars as summary
    return content[:500] + "..."


async def save_document(doc_id: str, user_id: str, filename: str,
                        file_type: str, content: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save document to memory/documents/{doc_id}.json.
    Auto-generates title always + summary if content > 4000 chars.
    Returns the full document dict.
    """
    # Auto-title (sempre)
    title = await _generate_title(content, filename, file_type)

    # Auto-summary per documenti grandi
    summary = ""
    if content and len(content) > _SUMMARY_THRESHOLD:
        summary = await _generate_summary(content, filename)

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "doc_id": doc_id,
        "filename": filename,
        "title": title,
        "type": file_type,
        "content": content,
        "summary": summary,
        "meta": meta,
        "created_at": now,
        "user_id": user_id,
        "last_accessed_at": now,
        "access_count": 0,
        "importance_score": 50,
        "status": "active",
    }

    path = _doc_path(doc_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        log("DOCUMENT_SAVED", doc_id=doc_id, user_id=user_id, filename=filename,
            title=title, type=file_type)
        log("DOCUMENT_ACTIVATED", user_id=user_id, doc_id=doc_id, title=title)
        return doc
    except Exception as e:
        logger.error("DOCUMENT_SAVE_ERROR doc_id=%s error=%s", doc_id, str(e))
        raise


def load_document(doc_id: str) -> Optional[Dict[str, Any]]:
    """Load document by doc_id. Returns None if not found."""
    path = _doc_path(doc_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("DOCUMENT_LOAD_ERROR doc_id=%s error=%s", doc_id, str(e))
        return None


def _save_doc(doc: Dict[str, Any]) -> None:
    """Write document dict back to disk."""
    path = _doc_path(doc["doc_id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def _compute_status(score: float) -> str:
    """Compute status from importance_score."""
    if score > 70:
        return "active"
    elif score >= 30:
        return "passive"
    else:
        return "archived"


def reinforce_document(doc_id: str) -> None:
    """
    Reinforce a document when it is used in a query.
    importance_score += 10, access_count += 1, last_accessed_at = now.
    """
    doc = load_document(doc_id)
    if not doc:
        return
    doc["importance_score"] = min(100, doc.get("importance_score", 50) + 10)
    doc["access_count"] = doc.get("access_count", 0) + 1
    doc["last_accessed_at"] = datetime.now(timezone.utc).isoformat()
    old_status = doc.get("status", "active")
    doc["status"] = _compute_status(doc["importance_score"])
    try:
        _save_doc(doc)
        log("DOCUMENT_REINFORCED", doc_id=doc_id, score=doc["importance_score"],
            access_count=doc["access_count"])
        if doc["status"] != old_status:
            log("DOCUMENT_STATUS_CHANGED", doc_id=doc_id,
                old_status=old_status, new_status=doc["status"])
    except Exception as e:
        logger.error("DOCUMENT_REINFORCE_ERROR doc_id=%s error=%s", doc_id, str(e))


def get_user_documents(user_id: str) -> List[Dict[str, Any]]:
    """Get all documents for a user (most recent first)."""
    docs = []
    try:
        for fname in os.listdir(_DOCUMENTS_DIR):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(_DOCUMENTS_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                if doc.get("user_id") == user_id:
                    docs.append(doc)
            except Exception:
                continue
    except Exception as e:
        logger.error("DOCUMENT_LIST_ERROR user_id=%s error=%s", user_id, str(e))
    docs.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return docs


def decay_and_forget(user_id: str, inactive_days: int = 14, min_score: int = 25) -> List[str]:
    """
    Abbassa importance_score dei documenti non usati da inactive_days giorni.
    Archivia (status=archived) quelli con score < min_score.
    Ritorna lista dei doc_id archiviati.
    """
    now = datetime.now(timezone.utc)
    archived = []
    for doc in get_user_documents(user_id):
        last_str = doc.get("last_accessed_at") or doc.get("created_at", "")
        try:
            last_dt = datetime.fromisoformat(last_str.rstrip("Z"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            days_idle = (now - last_dt).days
        except Exception:
            continue

        if days_idle >= inactive_days:
            # Decay proporzionale ai cicli di inattività
            decay_amount = (days_idle // inactive_days) * 15
            old_score = doc.get("importance_score", 50)
            new_score = max(0, old_score - decay_amount)
            doc["importance_score"] = new_score
            doc["status"] = _compute_status(new_score)
            try:
                _save_doc(doc)
                log("DOCUMENT_DECAYED", doc_id=doc["doc_id"], days_idle=days_idle,
                    old_score=old_score, new_score=new_score, status=doc["status"])
                if doc["status"] == "archived":
                    archived.append(doc["doc_id"])
                    log("DOCUMENT_ARCHIVED", doc_id=doc["doc_id"], filename=doc.get("filename", "?"))
            except Exception as e:
                logger.error("DOCUMENT_DECAY_ERROR doc_id=%s error=%s", doc["doc_id"], str(e))

    return archived
