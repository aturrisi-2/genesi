"""
DOCUMENT MEMORY - Genesi Core v2
Persistenza documenti caricati per utente.
Salva/carica documenti in memory/documents/.
Auto-summary per documenti > 4000 chars.
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from core.log import log

logger = logging.getLogger(__name__)

_DOCUMENTS_DIR = "memory/documents"
os.makedirs(_DOCUMENTS_DIR, exist_ok=True)

_SUMMARY_THRESHOLD = 4000


def _doc_path(doc_id: str) -> str:
    return os.path.join(_DOCUMENTS_DIR, f"{doc_id}.json")


async def _generate_summary(content: str, filename: str) -> str:
    """Generate a summary for large documents using LLM."""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        # Take first 6000 chars for summary generation
        text_for_summary = content[:6000]
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "Sei un analizzatore di documenti. "
                    "Genera un riassunto conciso in italiano del documento fornito. "
                    "Massimo 5 frasi. Includi i punti chiave e i dati principali."
                )},
                {"role": "user", "content": f"Riassumi questo documento ({filename}):\n\n{text_for_summary}"},
            ],
            max_tokens=300,
        )
        summary = response.choices[0].message.content.strip()
        log("DOCUMENT_SUMMARY_GENERATED", filename=filename, summary_len=len(summary))
        return summary
    except Exception as e:
        logger.error("DOCUMENT_SUMMARY_ERROR filename=%s error=%s", filename, str(e))
        # Fallback: first 500 chars as summary
        return content[:500] + "..."


async def save_document(doc_id: str, user_id: str, filename: str,
                        file_type: str, content: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save document to memory/documents/{doc_id}.json.
    Auto-generates summary if content > 4000 chars.
    Returns the full document dict.
    """
    # Auto-summary for large documents
    summary = ""
    if content and len(content) > _SUMMARY_THRESHOLD:
        summary = await _generate_summary(content, filename)

    doc = {
        "doc_id": doc_id,
        "filename": filename,
        "type": file_type,
        "content": content,
        "summary": summary,
        "meta": meta,
        "created_at": datetime.utcnow().isoformat(),
        "user_id": user_id,
    }

    path = _doc_path(doc_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        log("DOCUMENT_SAVED", doc_id=doc_id, user_id=user_id, filename=filename, type=file_type)
        log("DOCUMENT_ACTIVATED", user_id=user_id, doc_id=doc_id, filename=filename)
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


def get_user_documents(user_id: str) -> list:
    """Get all documents for a user (most recent first)."""
    docs = []
    try:
        for fname in os.listdir(_DOCUMENTS_DIR):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(_DOCUMENTS_DIR, fname)
            with open(path, "r", encoding="utf-8") as f:
                doc = json.load(f)
            if doc.get("user_id") == user_id:
                docs.append(doc)
    except Exception as e:
        logger.error("DOCUMENT_LIST_ERROR user_id=%s error=%s", user_id, str(e))
    docs.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return docs
