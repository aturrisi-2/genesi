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


def _make_doc(doc_id, filename, file_type, content="test content",
              status="active", importance_score=50):
    return {
        "doc_id": doc_id,
        "filename": filename,
        "type": file_type,
        "content": content,
        "summary": "",
        "meta": {},
        "created_at": "2026-01-01T00:00:00",
        "user_id": "test_user",
        "last_accessed_at": "2026-01-01T00:00:00",
        "access_count": 0,
        "importance_score": importance_score,
        "status": status,
    }


DOC_A = _make_doc("doc_a", "report.pdf", "pdf", "Report content A")
DOC_B = _make_doc("doc_b", "foto_vacanza.jpg", "image", "Image description B")
DOC_C = _make_doc("doc_c", "notes.txt", "text", "Text notes C")


class TestDocumentSelector:

    @patch("core.document_selector.reinforce_document")
    @patch("core.document_selector.load_document")
    def test_filename_match(self, mock_load, mock_reinforce):
        mock_load.side_effect = lambda did: {"doc_a": DOC_A, "doc_b": DOC_B, "doc_c": DOC_C}.get(did)
        result = resolve_documents("cosa dice il report?", "user1", ["doc_a", "doc_b", "doc_c"])
        assert len(result) == 1
        assert result[0]["doc_id"] == "doc_a"

    @patch("core.document_selector.reinforce_document")
    @patch("core.document_selector.load_document")
    def test_type_match_image(self, mock_load, mock_reinforce):
        mock_load.side_effect = lambda did: {"doc_a": DOC_A, "doc_b": DOC_B, "doc_c": DOC_C}.get(did)
        result = resolve_documents("descrivi l'immagine", "user1", ["doc_a", "doc_b", "doc_c"])
        assert len(result) == 1
        assert result[0]["type"] == "image"

    @patch("core.document_selector.reinforce_document")
    @patch("core.document_selector.load_document")
    def test_type_match_pdf(self, mock_load, mock_reinforce):
        mock_load.side_effect = lambda did: {"doc_a": DOC_A, "doc_b": DOC_B, "doc_c": DOC_C}.get(did)
        result = resolve_documents("leggi il pdf", "user1", ["doc_a", "doc_b", "doc_c"])
        assert len(result) == 1
        assert result[0]["type"] == "pdf"

    @patch("core.document_selector.reinforce_document")
    @patch("core.document_selector.load_document")
    def test_recency_ultimo(self, mock_load, mock_reinforce):
        mock_load.side_effect = lambda did: {"doc_a": DOC_A, "doc_b": DOC_B, "doc_c": DOC_C}.get(did)
        result = resolve_documents("riassumi l'ultimo file", "user1", ["doc_a", "doc_b", "doc_c"])
        assert len(result) == 1
        assert result[0]["doc_id"] == "doc_c"  # last in list = most recent

    @patch("core.document_selector.reinforce_document")
    @patch("core.document_selector.load_document")
    def test_comparison_selects_two(self, mock_load, mock_reinforce):
        mock_load.side_effect = lambda did: {"doc_a": DOC_A, "doc_b": DOC_B, "doc_c": DOC_C}.get(did)
        result = resolve_documents("confronta i documenti", "user1", ["doc_a", "doc_b", "doc_c"])
        assert len(result) == 2

    @patch("core.document_selector.reinforce_document")
    @patch("core.document_selector.load_document")
    def test_default_last_two(self, mock_load, mock_reinforce):
        mock_load.side_effect = lambda did: {"doc_a": DOC_A, "doc_b": DOC_B, "doc_c": DOC_C}.get(did)
        result = resolve_documents("analizza il contenuto", "user1", ["doc_a", "doc_b", "doc_c"])
        assert len(result) == 2
        assert result[0]["doc_id"] == "doc_b"
        assert result[1]["doc_id"] == "doc_c"

    @patch("core.document_selector.load_document")
    def test_empty_list(self, mock_load):
        result = resolve_documents("riassumi", "user1", [])
        assert result == []

    @patch("core.document_selector.reinforce_document")
    @patch("core.document_selector.load_document")
    def test_single_doc(self, mock_load, mock_reinforce):
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


# ═══════════════════════════════════════════════════════════════
# Test: _compute_status
# ═══════════════════════════════════════════════════════════════

from core.document_memory import _compute_status


class TestComputeStatus:
    def test_high_score_active(self):
        assert _compute_status(80) == "active"

    def test_boundary_71_active(self):
        assert _compute_status(71) == "active"

    def test_boundary_70_passive(self):
        assert _compute_status(70) == "passive"

    def test_mid_score_passive(self):
        assert _compute_status(50) == "passive"

    def test_boundary_30_passive(self):
        assert _compute_status(30) == "passive"

    def test_boundary_29_archived(self):
        assert _compute_status(29) == "archived"

    def test_zero_archived(self):
        assert _compute_status(0) == "archived"


# ═══════════════════════════════════════════════════════════════
# Test: Status filtering in document_selector
# ═══════════════════════════════════════════════════════════════

DOC_ARCHIVED = _make_doc("doc_arch", "old.pdf", "pdf", "Old content",
                          status="archived", importance_score=10)
DOC_PASSIVE = _make_doc("doc_pass", "medium.pdf", "pdf", "Medium content",
                         status="passive", importance_score=40)


class TestStatusFiltering:

    @patch("core.document_selector.reinforce_document")
    @patch("core.document_selector.load_document")
    def test_archived_excluded(self, mock_load, mock_reinforce):
        mock_load.side_effect = lambda did: {
            "doc_a": DOC_A, "doc_arch": DOC_ARCHIVED
        }.get(did)
        result = resolve_documents("analizza", "user1", ["doc_arch", "doc_a"])
        doc_ids = [d["doc_id"] for d in result]
        assert "doc_arch" not in doc_ids
        assert "doc_a" in doc_ids

    @patch("core.document_selector.reinforce_document")
    @patch("core.document_selector.load_document")
    def test_passive_used_when_no_active(self, mock_load, mock_reinforce):
        mock_load.side_effect = lambda did: {
            "doc_pass": DOC_PASSIVE, "doc_arch": DOC_ARCHIVED
        }.get(did)
        result = resolve_documents("analizza", "user1", ["doc_arch", "doc_pass"])
        assert len(result) == 1
        assert result[0]["doc_id"] == "doc_pass"

    @patch("core.document_selector.reinforce_document")
    @patch("core.document_selector.load_document")
    def test_all_archived_returns_empty(self, mock_load, mock_reinforce):
        mock_load.side_effect = lambda did: {
            "doc_arch": DOC_ARCHIVED
        }.get(did)
        result = resolve_documents("analizza", "user1", ["doc_arch"])
        assert result == []


# ═══════════════════════════════════════════════════════════════
# Test: Forgetting engine decay
# ═══════════════════════════════════════════════════════════════

from core.document_forgetting import apply_decay, _DECAY_RATE
from datetime import datetime, timedelta


class TestForgettingEngine:

    @patch("core.document_forgetting._save_doc")
    @patch("core.document_forgetting.get_user_documents")
    def test_decay_after_10_days(self, mock_get, mock_save):
        ten_days_ago = (datetime.utcnow() - timedelta(days=10)).isoformat()
        doc = _make_doc("d1", "test.pdf", "pdf")
        doc["last_accessed_at"] = ten_days_ago
        doc["importance_score"] = 50
        mock_get.return_value = [doc]
        updated = apply_decay("user1")
        assert updated == 1
        # 50 - 10*0.5 = 45
        assert doc["importance_score"] == 45.0
        assert doc["status"] == "passive"  # 30-70 range

    @patch("core.document_forgetting._save_doc")
    @patch("core.document_forgetting.get_user_documents")
    def test_decay_clamps_to_zero(self, mock_get, mock_save):
        old = (datetime.utcnow() - timedelta(days=200)).isoformat()
        doc = _make_doc("d1", "test.pdf", "pdf")
        doc["last_accessed_at"] = old
        doc["importance_score"] = 50
        mock_get.return_value = [doc]
        apply_decay("user1")
        assert doc["importance_score"] == 0
        assert doc["status"] == "archived"

    @patch("core.document_forgetting._save_doc")
    @patch("core.document_forgetting.get_user_documents")
    def test_no_decay_within_first_day(self, mock_get, mock_save):
        recent = datetime.utcnow().isoformat()
        doc = _make_doc("d1", "test.pdf", "pdf")
        doc["last_accessed_at"] = recent
        doc["importance_score"] = 50
        mock_get.return_value = [doc]
        updated = apply_decay("user1")
        assert updated == 0
        assert doc["importance_score"] == 50

    @patch("core.document_forgetting._save_doc")
    @patch("core.document_forgetting.get_user_documents")
    def test_status_transition_active_to_passive(self, mock_get, mock_save):
        days_ago = (datetime.utcnow() - timedelta(days=60)).isoformat()
        doc = _make_doc("d1", "test.pdf", "pdf", importance_score=80)
        doc["last_accessed_at"] = days_ago
        doc["status"] = "active"
        mock_get.return_value = [doc]
        apply_decay("user1")
        # 80 - 60*0.5 = 50 → passive
        assert doc["importance_score"] == 50.0
        assert doc["status"] == "passive"

    @patch("core.document_forgetting._save_doc")
    @patch("core.document_forgetting.get_user_documents")
    def test_empty_docs_returns_zero(self, mock_get, mock_save):
        mock_get.return_value = []
        assert apply_decay("user1") == 0


# ═══════════════════════════════════════════════════════════════
# Test: Reinforcement
# ═══════════════════════════════════════════════════════════════

from core.document_memory import reinforce_document


class TestReinforcement:

    @patch("core.document_memory._save_doc")
    @patch("core.document_memory.load_document")
    def test_reinforce_bumps_score(self, mock_load, mock_save):
        doc = _make_doc("d1", "test.pdf", "pdf")
        doc["importance_score"] = 50
        doc["access_count"] = 0
        mock_load.return_value = doc
        reinforce_document("d1")
        assert doc["importance_score"] == 60
        assert doc["access_count"] == 1

    @patch("core.document_memory._save_doc")
    @patch("core.document_memory.load_document")
    def test_reinforce_caps_at_100(self, mock_load, mock_save):
        doc = _make_doc("d1", "test.pdf", "pdf", importance_score=95)
        doc["access_count"] = 5
        mock_load.return_value = doc
        reinforce_document("d1")
        assert doc["importance_score"] == 100

    @patch("core.document_memory._save_doc")
    @patch("core.document_memory.load_document")
    def test_reinforce_updates_status_to_active(self, mock_load, mock_save):
        doc = _make_doc("d1", "test.pdf", "pdf", importance_score=65)
        doc["status"] = "passive"
        doc["access_count"] = 2
        mock_load.return_value = doc
        reinforce_document("d1")
        # 65 + 10 = 75 → active
        assert doc["importance_score"] == 75
        assert doc["status"] == "active"

    @patch("core.document_memory.load_document")
    def test_reinforce_missing_doc_noop(self, mock_load):
        mock_load.return_value = None
        reinforce_document("nonexistent")  # Should not raise
