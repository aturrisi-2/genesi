"""
Gestisce il contesto dei documenti caricati dall'utente.
Comportamento NotebookLM: risponde basandosi sulle fonti caricate con citazioni.
Lazy load da disco: se cache vuota post-restart, ripristina da document_memory.
"""
import hashlib
import logging
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass
from core.log import log

logger = logging.getLogger(__name__)

@dataclass
class DocumentSource:
    doc_id: str
    filename: str
    content: str
    content_preview: str
    upload_time: str
    file_type: str
    char_count: int

class DocumentContextManager:
    MAX_DOCS_PER_USER = 5
    MAX_CONTEXT_CHARS = 8000

    def __init__(self):
        self._user_documents: Dict[str, List[DocumentSource]] = {}

    def add_document(self, user_id: str, filename: str, content: str, file_type: str = "unknown") -> DocumentSource:
        doc_id = hashlib.md5(f"{user_id}{filename}{datetime.now().isoformat()}".encode()).hexdigest()[:8]
        doc = DocumentSource(
            doc_id=doc_id,
            filename=filename,
            content=content,
            content_preview=content[:200] + "..." if len(content) > 200 else content,
            upload_time=datetime.now().isoformat(),
            file_type=file_type,
            char_count=len(content)
        )
        if user_id not in self._user_documents:
            self._user_documents[user_id] = []
        if len(self._user_documents[user_id]) >= self.MAX_DOCS_PER_USER:
            removed = self._user_documents[user_id].pop(0)
            log("DOCUMENT_EVICTED", user=user_id, doc=removed.filename)
        self._user_documents[user_id].append(doc)
        log("DOCUMENT_ADDED", user=user_id, doc_id=doc_id, file=filename, chars=len(content))
        return doc

    def _try_restore_from_disk(self, user_id: str) -> None:
        """
        Se la cache per user_id è vuota, ripristina i documenti da disco.
        Carica da document_memory, filtra status active/passive, popola la cache.
        """
        if self._user_documents.get(user_id):
            return  # cache già popolata
        try:
            from core.document_memory import get_user_documents
            disk_docs = get_user_documents(user_id)
            restored = []
            for d in disk_docs:
                if d.get("status", "active") not in ("active", "passive"):
                    continue
                # Usa title come filename se disponibile (più leggibile)
                display_name = d.get("title") or d.get("filename", "?")
                ds = DocumentSource(
                    doc_id=d.get("doc_id", ""),
                    filename=display_name,
                    content=d.get("content", ""),
                    content_preview=(d.get("content", "")[:200] + "...") if len(d.get("content", "")) > 200 else d.get("content", ""),
                    upload_time=d.get("created_at", datetime.now().isoformat()),
                    file_type=d.get("type", "unknown"),
                    char_count=len(d.get("content", "")),
                )
                restored.append(ds)
                if len(restored) >= self.MAX_DOCS_PER_USER:
                    break
            if restored:
                self._user_documents[user_id] = restored
                log("DOCUMENT_CTX_RESTORED", user=user_id, count=len(restored))
        except Exception as e:
            logger.warning("DOCUMENT_CTX_RESTORE_ERROR user=%s error=%s", user_id, str(e))

    def get_relevant_context(self, user_id: str, query: str) -> Optional[str]:
        self._try_restore_from_disk(user_id)
        docs = self._user_documents.get(user_id, [])
        if not docs:
            return None
        doc = docs[0] if len(docs) == 1 else self._find_most_relevant(docs, query)
        context = self._extract_relevant_section(doc.content, query)
        return self._format_context(doc, context)

    def has_documents(self, user_id: str) -> bool:
        self._try_restore_from_disk(user_id)
        return bool(self._user_documents.get(user_id))

    def list_documents(self, user_id: str) -> List[dict]:
        return [{"doc_id": d.doc_id, "filename": d.filename, "preview": d.content_preview, "chars": d.char_count}
                for d in self._user_documents.get(user_id, [])]

    def clear_documents(self, user_id: str):
        self._user_documents.pop(user_id, None)
        log("DOCUMENTS_CLEARED", user=user_id)

    def _extract_relevant_section(self, content: str, query: str, max_chars: int = 4000) -> str:
        if len(content) <= max_chars:
            return content
        query_words = set(query.lower().split())
        paragraphs = content.split('\n\n')
        scored = sorted([(len(query_words & set(p.lower().split())), p) for p in paragraphs], reverse=True)
        result = ""
        for _, para in scored:
            if len(result) + len(para) > max_chars:
                break
            result += para + "\n\n"
        return result.strip() or content[:max_chars]

    def _find_most_relevant(self, docs: List[DocumentSource], query: str) -> DocumentSource:
        query_words = set(query.lower().split())
        return max(docs, key=lambda d: len(query_words & set(d.content.lower().split())), default=docs[-1])

    def _format_context(self, doc: DocumentSource, relevant_content: str) -> str:
        return f"""[DOCUMENTO CARICATO: {doc.filename}]
Tipo: {doc.file_type} | Caratteri totali: {doc.char_count}

CONTENUTO RILEVANTE:
{relevant_content}

[Fine documento: {doc.filename}]
Rispondi basandoti su questo documento. Cita esplicitamente il nome del file nella risposta."""

_document_context_manager = None

def get_document_context_manager() -> DocumentContextManager:
    global _document_context_manager
    if _document_context_manager is None:
        _document_context_manager = DocumentContextManager()
    return _document_context_manager
