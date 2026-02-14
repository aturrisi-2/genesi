"""
Tests for Document Query system:
- Document reference detection
- Document selector (filename, type, recency, comparison, default)
- Multi-document context injection
- Active documents list management
"""

import pytest
import json
import os
import tempfile
from unittest.mock import patch, MagicMock

# ═══════════════════════════════════════════════════════════════
# Test: is_document_reference
# ═══════════════════════════════════════════════════════════════

from core.context_assembler import is_document_reference


class TestDocumentReferenceDetection:
    def test_file_trigger(self):
        assert is_document_reference("cosa c'è nel file?")

    def test_documento_trigger(self):
        assert is_document_reference("leggi il documento")

    def test_immagine_trigger(self):
        assert is_document_reference("descrivi l'immagine")

    def test_riassumi_trigger(self):
        assert is_document_reference("riassumi")

    def test_trascrivi_trigger(self):
        assert is_document_reference("trascrivi")

    def test_estrai_trigger(self):
        assert is_document_reference("estrai i dati")

    def test_confronta_trigger(self):
        assert is_document_reference("confronta i due documenti")

    def test_no_trigger(self):
        assert not is_document_reference("come stai?")

    def test_no_trigger_weather(self):
        assert not is_document_reference("che tempo fa a Roma?")

    def test_cosa_dice(self):
        assert is_document_reference("cosa dice il documento?")

    def test_pdf_trigger(self):
        assert is_document_reference("apri il pdf")


# ═══════════════════════════════════════════════════════════════
# Test: resolve_documents
# ═══════════════════════════════════════════════════════════════

from core.document_selector import resolve_documents


def _make_doc(doc_id, filename, file_type, content="test content"):
    return {
        "doc_id": doc_id,
        "filename": filename,
        "type": file_type,
        "content": content,
        "summary": "",
        "meta": {},
        "created_at": "2026-01-01T00:00:00",
        "user_id": "test_user",
    }


DOC_A = _make_doc("doc_a", "report.pdf", "pdf", "Report content A")
DOC_B = _make_doc("doc_b", "foto_vacanza.jpg", "image", "Image description B")
DOC_C = _make_doc("doc_c", "notes.txt", "text", "Text notes C")


class TestDocumentSelector:

    @patch("core.document_selector.load_document")
    def test_filename_match(self, mock_load):
        mock_load.side_effect = lambda did: {"doc_a": DOC_A, "doc_b": DOC_B, "doc_c": DOC_C}.get(did)
        result = resolve_documents("cosa dice il report?", "user1", ["doc_a", "doc_b", "doc_c"])
        assert len(result) == 1
        assert result[0]["doc_id"] == "doc_a"

    @patch("core.document_selector.load_document")
    def test_type_match_image(self, mock_load):
        mock_load.side_effect = lambda did: {"doc_a": DOC_A, "doc_b": DOC_B, "doc_c": DOC_C}.get(did)
        result = resolve_documents("descrivi l'immagine", "user1", ["doc_a", "doc_b", "doc_c"])
        assert len(result) == 1
        assert result[0]["type"] == "image"

    @patch("core.document_selector.load_document")
    def test_type_match_pdf(self, mock_load):
        mock_load.side_effect = lambda did: {"doc_a": DOC_A, "doc_b": DOC_B, "doc_c": DOC_C}.get(did)
        result = resolve_documents("leggi il pdf", "user1", ["doc_a", "doc_b", "doc_c"])
        assert len(result) == 1
        assert result[0]["type"] == "pdf"

    @patch("core.document_selector.load_document")
    def test_recency_ultimo(self, mock_load):
        mock_load.side_effect = lambda did: {"doc_a": DOC_A, "doc_b": DOC_B, "doc_c": DOC_C}.get(did)
        result = resolve_documents("riassumi l'ultimo file", "user1", ["doc_a", "doc_b", "doc_c"])
        assert len(result) == 1
        assert result[0]["doc_id"] == "doc_c"  # last in list = most recent

    @patch("core.document_selector.load_document")
    def test_comparison_selects_two(self, mock_load):
        mock_load.side_effect = lambda did: {"doc_a": DOC_A, "doc_b": DOC_B, "doc_c": DOC_C}.get(did)
        result = resolve_documents("confronta i documenti", "user1", ["doc_a", "doc_b", "doc_c"])
        assert len(result) == 2

    @patch("core.document_selector.load_document")
    def test_default_last_two(self, mock_load):
        mock_load.side_effect = lambda did: {"doc_a": DOC_A, "doc_b": DOC_B, "doc_c": DOC_C}.get(did)
        result = resolve_documents("analizza il contenuto", "user1", ["doc_a", "doc_b", "doc_c"])
        assert len(result) == 2
        assert result[0]["doc_id"] == "doc_b"
        assert result[1]["doc_id"] == "doc_c"

    @patch("core.document_selector.load_document")
    def test_empty_list(self, mock_load):
        result = resolve_documents("riassumi", "user1", [])
        assert result == []

    @patch("core.document_selector.load_document")
    def test_single_doc(self, mock_load):
        mock_load.return_value = DOC_A
        result = resolve_documents("analizza", "user1", ["doc_a"])
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════
# Test: _format_doc_block
# ═══════════════════════════════════════════════════════════════

from core.context_assembler import _format_doc_block


class TestFormatDocBlock:
    def test_short_content(self):
        doc = _make_doc("d1", "test.txt", "text", "Hello world")
        block = _format_doc_block(doc)
        assert "[DOCUMENT_CONTEXT]" in block
        assert "filename: test.txt" in block
        assert "Hello world" in block
        assert "[/DOCUMENT_CONTEXT]" in block

    def test_long_content_truncated(self):
        doc = _make_doc("d1", "big.pdf", "pdf", "x" * 5000)
        block = _format_doc_block(doc)
        assert "[...contenuto troncato...]" in block
        # Should not contain full 5000 chars
        assert len(block) < 4000

    def test_long_content_with_summary(self):
        doc = _make_doc("d1", "big.pdf", "pdf", "x" * 5000)
        doc["summary"] = "This is a summary."
        block = _format_doc_block(doc)
        assert "RIASSUNTO:" in block
        assert "This is a summary." in block
        assert "PRIMI 2000 CARATTERI:" in block


# ═══════════════════════════════════════════════════════════════
# Test: active_documents list management
# ═══════════════════════════════════════════════════════════════

class TestActiveDocumentsList:
    def test_max_five_enforced(self):
        """Simulate adding 6 docs — oldest should be removed."""
        active_docs = ["d1", "d2", "d3", "d4", "d5"]
        new_id = "d6"
        if new_id not in active_docs:
            active_docs.append(new_id)
        while len(active_docs) > 5:
            active_docs.pop(0)
        assert len(active_docs) == 5
        assert "d1" not in active_docs
        assert "d6" in active_docs

    def test_no_duplicates(self):
        active_docs = ["d1", "d2", "d3"]
        new_id = "d2"
        if new_id not in active_docs:
            active_docs.append(new_id)
        assert len(active_docs) == 3

    def test_migration_from_old_field(self):
        """Legacy active_document_id should be migrated."""
        profile = {"active_document_id": "old_doc"}
        active_docs = profile.get("active_documents", [])
        old_id = profile.pop("active_document_id", None)
        if old_id and old_id not in active_docs:
            active_docs.append(old_id)
        assert active_docs == ["old_doc"]
        assert "active_document_id" not in profile


# ═══════════════════════════════════════════════════════════════
# Test: _inject_document_context multi-doc
# ═══════════════════════════════════════════════════════════════

from core.context_assembler import _inject_document_context


class TestMultiDocInjection:

    @patch("core.context_assembler.resolve_documents")
    def test_single_doc_injection(self, mock_resolve):
        mock_resolve.return_value = [DOC_A]
        profile = {"active_documents": ["doc_a"]}
        result = _inject_document_context("user1", "riassumi il file", profile)
        assert "[DOCUMENT_CONTEXT]" in result
        assert "report.pdf" in result
        assert "questo documento" in result

    @patch("core.context_assembler.resolve_documents")
    def test_multi_doc_injection(self, mock_resolve):
        mock_resolve.return_value = [DOC_A, DOC_B]
        profile = {"active_documents": ["doc_a", "doc_b"]}
        result = _inject_document_context("user1", "confronta i file", profile)
        assert result.count("[DOCUMENT_CONTEXT]") == 2
        assert "questi documenti" in result
        assert "confronto" in result.lower() or "differenze" in result.lower() or "similitudini" in result.lower()

    @patch("core.context_assembler.resolve_documents")
    def test_no_docs_no_injection(self, mock_resolve):
        profile = {}
        result = _inject_document_context("user1", "riassumi il file", profile)
        assert result == ""

    @patch("core.context_assembler.resolve_documents")
    def test_no_reference_no_injection(self, mock_resolve):
        profile = {"active_documents": ["doc_a"]}
        result = _inject_document_context("user1", "come stai?", profile)
        assert result == ""

    @patch("core.context_assembler.resolve_documents")
    def test_legacy_active_document_id(self, mock_resolve):
        mock_resolve.return_value = [DOC_A]
        profile = {"active_document_id": "doc_a"}
        result = _inject_document_context("user1", "leggi il file", profile)
        assert "[DOCUMENT_CONTEXT]" in result
