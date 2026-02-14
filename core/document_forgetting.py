"""
DOCUMENT FORGETTING ENGINE - Genesi Core v2
Decay automatico dell'importanza dei documenti.
Documenti non usati perdono rilevanza nel tempo.
Non elimina mai documenti — solo aggiorna status.
"""

import logging
from datetime import datetime
from core.document_memory import get_user_documents, _save_doc, _compute_status
from core.log import log

logger = logging.getLogger(__name__)

_DECAY_RATE = 0.5  # importance points lost per day of inactivity


def apply_decay(user_id: str) -> int:
    """
    Apply time-based decay to all documents for a user.
    importance_score -= days_since_last_access * 0.5
    Clamp to 0. Update status accordingly.

    Returns number of documents updated.
    """
    docs = get_user_documents(user_id)
    if not docs:
        return 0

    now = datetime.utcnow()
    updated = 0

    for doc in docs:
        last_accessed = doc.get("last_accessed_at") or doc.get("created_at")
        if not last_accessed:
            continue

        try:
            last_dt = datetime.fromisoformat(last_accessed)
        except (ValueError, TypeError):
            continue

        days = (now - last_dt).total_seconds() / 86400
        if days < 1:
            continue  # No decay within first day

        old_score = doc.get("importance_score", 50)
        new_score = max(0, old_score - days * _DECAY_RATE)

        if abs(new_score - old_score) < 0.01:
            continue  # No meaningful change

        old_status = doc.get("status", "active")
        new_status = _compute_status(new_score)

        doc["importance_score"] = round(new_score, 2)
        doc["status"] = new_status

        try:
            _save_doc(doc)
            updated += 1

            log("DOCUMENT_DECAY_APPLIED", doc_id=doc["doc_id"],
                old_score=old_score, new_score=round(new_score, 2),
                days_inactive=round(days, 1))

            if new_status != old_status:
                log("DOCUMENT_STATUS_CHANGED", doc_id=doc["doc_id"],
                    old_status=old_status, new_status=new_status)

        except Exception as e:
            logger.error("DOCUMENT_DECAY_SAVE_ERROR doc_id=%s error=%s",
                         doc["doc_id"], str(e))

    return updated
