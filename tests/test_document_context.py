import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.document_context_manager import DocumentContextManager

def test_add_and_retrieve():
    mgr = DocumentContextManager()
    doc = mgr.add_document("u1", "test.pdf", "Il gatto si chiama Micio.", "pdf")
    assert doc.doc_id is not None
    assert mgr.has_documents("u1")

def test_context_contains_filename():
    mgr = DocumentContextManager()
    mgr.add_document("u1", "report.pdf", "Contenuto importante del documento.", "pdf")
    ctx = mgr.get_relevant_context("u1", "cosa dice il documento?")
    assert "report.pdf" in ctx

def test_max_docs_eviction():
    mgr = DocumentContextManager()
    mgr.MAX_DOCS_PER_USER = 2
    for i in range(3):
        mgr.add_document("u1", f"doc{i}.pdf", f"contenuto {i}", "pdf")
    assert len(mgr.list_documents("u1")) == 2

def test_clear():
    mgr = DocumentContextManager()
    mgr.add_document("u1", "test.pdf", "contenuto", "pdf")
    mgr.clear_documents("u1")
    assert not mgr.has_documents("u1")

def test_no_docs_returns_none():
    mgr = DocumentContextManager()
    assert mgr.get_relevant_context("vuoto", "domanda") is None

if __name__ == "__main__":
    test_add_and_retrieve()
    test_context_contains_filename()
    test_max_docs_eviction()
    test_clear()
    test_no_docs_returns_none()
    print("✅ All document context tests passed")
