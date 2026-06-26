"""Image vision fallback: dict/str result handling + weak-OCR heuristic.

Regression for the prod bug: describe_image() returns a dict → wrapper used to
crash on .strip(); and garbage-with-letters OCR was not flagged weak. Mocked
vision — no API call."""

from __future__ import annotations

import pytest

import core.operational_memory.image_describer as idmod
from core.operational_memory.image_describer import _looks_weak_ocr, describe_image_file


@pytest.mark.parametrize("text,expected", [
    ("lo) Qa a 7 LJ ac SUL IU qll i O mM aN Ee n msi] © O o = 6 E © U c 6 a 4 ce mo nd O 2 6 = bilanciamento DN 32 ,", True),
    ("| 101 oueld ip a]on]eA 9]/2ep 2 uo e Baul} SULL SSUdAd ZL 313A", True),
    ("", True),
    ("BDF 200x150 BM Dietro area ristoro cantiere 1 Manca BDF e da rifare foro cartongesso", False),
    ("TransPort PT878 Misura Portata Pressione Pa Temperatura Acqua Valvola DN125", False),
    ("V27 L0 FC FREDDO Manca manopola valvola bilanciamento DN32", False),
])
def test_looks_weak_ocr(text, expected):
    assert _looks_weak_ocr(text) is expected


@pytest.mark.asyncio
async def test_describe_image_file_dict_result(monkeypatch, tmp_path):
    f = tmp_path / "p.jpg"; f.write_bytes(b"\xff\xd8\xff")
    async def fake(path):
        return {"description": "V27 L0 FC FREDDO manca manopola valvola bilanciamento DN32"}
    monkeypatch.setattr("core.image_vision_service.describe_image", fake)
    out = await describe_image_file(str(f))
    assert out["image_status"] == "image_described"
    assert "manopola" in out["text"]


@pytest.mark.asyncio
async def test_describe_image_file_str_result(monkeypatch, tmp_path):
    f = tmp_path / "p.jpg"; f.write_bytes(b"\xff\xd8\xff")
    async def fake(path):
        return "descrizione stringa valida"
    monkeypatch.setattr("core.image_vision_service.describe_image", fake)
    out = await describe_image_file(str(f))
    assert out["image_status"] == "image_described"
    assert out["text"] == "descrizione stringa valida"


@pytest.mark.asyncio
async def test_describe_image_file_dict_no_description(monkeypatch, tmp_path):
    f = tmp_path / "p.jpg"; f.write_bytes(b"\xff\xd8\xff")
    async def fake(path):
        return {"unexpected": "field"}
    monkeypatch.setattr("core.image_vision_service.describe_image", fake)
    out = await describe_image_file(str(f))
    assert out["image_status"] == "image_no_content"   # no crash, controlled fallback


@pytest.mark.asyncio
async def test_describe_image_file_missing(tmp_path):
    out = await describe_image_file(str(tmp_path / "gone.jpg"))
    assert out["image_status"] == "missing"
