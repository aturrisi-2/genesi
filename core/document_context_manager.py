"""
Gestisce il contesto dei documenti caricati dall'utente.
Comportamento NotebookLM: risponde basandosi sulle fonti caricate con citazioni.
"""
import hashlib
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass

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
            print(f"DOCUMENT_EVICTED user={user_id} doc={removed.filename}")
        self._user_documents[user_id].append(doc)
        print(f"DOCUMENT_ADDED user={user_id} doc_id={doc_id} file={filename} chars={len(content)}")
        return doc

    def get_relevant_context(self, user_id: str, query: str) -> Optional[str]:
        docs = self._user_documents.get(user_id, [])
        if not docs:
            return None
        doc = docs[0] if len(docs) == 1 else self._find_most_relevant(docs, query)
        context = self._extract_relevant_section(doc.content, query)
        return self._format_context(doc, context)

    def has_documents(self, user_id: str) -> bool:
        return bool(self._user_documents.get(user_id))

    def list_documents(self, user_id: str) -> List[dict]:
        return [{"doc_id": d.doc_id, "filename": d.filename, "preview": d.content_preview, "chars": d.char_count}
                for d in self._user_documents.get(user_id, [])]

    def clear_documents(self, user_id: str):
        self._user_documents.pop(user_id, None)
        print(f"DOCUMENTS_CLEARED user={user_id}")

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
