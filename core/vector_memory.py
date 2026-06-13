"""
Memoria vettoriale (RAG) per Genesi — sqlite-vec + OpenAI embeddings.

Leggera per il VPS: un singolo file SQLite su SSD (data/vectors.db), nessun
servizio extra. Indicizza i manuali (memory/manuals/*.json) per ricerca
SEMANTICA, con i tag di contesto (ambience) per pescare nel posto giusto.

Embedding: OpenAI text-embedding-3-small (multilingue IT+EN, costo irrisorio).
Le query vengono embeddate al volo (con cache) e cercate localmente in sqlite-vec.
"""
from __future__ import annotations

import os
import json
import glob
import sqlite3
import hashlib
import logging
import asyncio
from typing import Optional

import httpx

try:
    from core.log import log
except Exception:  # pragma: no cover
    def log(*a, **k):
        pass

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join("data", "vectors.db")
_MANUALS_DIR = "memory/manuals"
_EMBED_MODEL = "text-embedding-3-small"
_EMBED_DIM = 1536
_EMBED_URL = "https://api.openai.com/v1/embeddings"

# Cache in-memory degli embedding delle query (stessa domanda → niente seconda chiamata API)
_QUERY_CACHE: dict[str, list[float]] = {}
_QUERY_CACHE_MAX = 500


def _connect() -> sqlite3.Connection:
    import sqlite_vec
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    db = sqlite3.connect(_DB_PATH)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    return db


def _ensure_schema(db: sqlite3.Connection):
    db.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(emb float[{_EMBED_DIM}])"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS chunks_meta ("
        "rowid INTEGER PRIMARY KEY, source_file TEXT, title TEXT, text TEXT, "
        "url TEXT, ambience TEXT, source_tag TEXT)"
    )
    db.execute("CREATE TABLE IF NOT EXISTS index_state (k TEXT PRIMARY KEY, v TEXT)")
    db.commit()


async def _embed(texts: list[str], api_key: str) -> list[list[float]]:
    """Embedda una lista di testi in batch. Ritorna lista di vettori."""
    out: list[list[float]] = []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=90) as client:
        for i in range(0, len(texts), 256):
            batch = [t[:8000] for t in texts[i:i + 256]]
            last_err = None
            for attempt in range(4):  # resilienza su build lunghi (centinaia di batch)
                try:
                    r = await client.post(_EMBED_URL, headers=headers,
                                          json={"model": _EMBED_MODEL, "input": batch})
                    r.raise_for_status()
                    out.extend(d["embedding"] for d in r.json()["data"])
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    await asyncio.sleep(2 * (attempt + 1))
            if last_err:
                raise last_err
    return out


def _manuals_signature() -> str:
    """Firma dell'insieme manuali (nomi + dimensioni + mtime) per build idempotente."""
    parts = []
    for fp in sorted(glob.glob(os.path.join(_MANUALS_DIR, "*.json"))):
        st = os.stat(fp)
        parts.append(f"{os.path.basename(fp)}:{st.st_size}:{int(st.st_mtime)}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


async def build_index(force: bool = False) -> dict:
    """
    (Ri)costruisce l'indice vettoriale dai manuali. Idempotente: salta se i manuali
    non sono cambiati (firma). Ritorna {built: bool, chunks: int}.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        log("VECTOR_BUILD_SKIP", reason="no_openai_key")
        return {"built": False, "chunks": 0, "reason": "no_key"}

    sig = _manuals_signature()
    db = _connect()
    _ensure_schema(db)
    cur = db.execute("SELECT v FROM index_state WHERE k='manuals_sig'").fetchone()
    if not force and cur and cur[0] == sig:
        n = db.execute("SELECT COUNT(*) FROM chunks_meta").fetchone()[0]
        db.close()
        return {"built": False, "chunks": n, "reason": "unchanged"}

    # Raccogli tutti i chunk
    rows = []  # (text, meta)
    for fp in sorted(glob.glob(os.path.join(_MANUALS_DIR, "*.json"))):
        sf = os.path.basename(fp)
        try:
            data = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            data = data.get("sections") or data.get("chunks") or data.get("items") or [data]
        if not isinstance(data, list):
            continue
        for ch in data:
            if isinstance(ch, str):
                ch = {"text": ch, "title": sf}
            elif not isinstance(ch, dict):
                continue
            txt = (ch.get("text") or "").strip()
            if len(txt) < 30:
                continue
            title = ch.get("title") or sf
            # Testo da embeddare: titolo + testo (il titolo italiano aiuta il retrieval)
            embed_text = f"{title}\n{txt}"
            rows.append((embed_text, {
                "source_file": sf, "title": title, "text": txt,
                "url": ch.get("url", ""), "ambience": ch.get("ambience", ""),
                "source_tag": ch.get("source", ""),
            }))

    if not rows:
        db.close()
        return {"built": False, "chunks": 0, "reason": "no_chunks"}

    import sqlite_vec
    log("VECTOR_BUILD_START", chunks=len(rows), files=len(set(m["source_file"] for _, m in rows)))

    # Reset tabelle
    db.execute("DELETE FROM vec_chunks")
    db.execute("DELETE FROM chunks_meta")
    db.commit()

    # STREAMING: embedda un batch alla volta e scrivi subito (RAM piatta, niente 6GB in memoria)
    BATCH = 256
    idx = 0
    for i in range(0, len(rows), BATCH):
        chunk_rows = rows[i:i + BATCH]
        embs = await _embed([r[0] for r in chunk_rows], api_key)  # _embed gestisce retry
        for (_, meta), emb in zip(chunk_rows, embs):
            idx += 1
            db.execute("INSERT INTO vec_chunks(rowid, emb) VALUES (?, ?)",
                       [idx, sqlite_vec.serialize_float32(emb)])
            db.execute("INSERT INTO chunks_meta(rowid, source_file, title, text, url, ambience, source_tag) "
                       "VALUES (?,?,?,?,?,?,?)",
                       [idx, meta["source_file"], meta["title"], meta["text"],
                        meta["url"], meta["ambience"], meta["source_tag"]])
        db.commit()
        if (i // BATCH) % 50 == 0:
            log("VECTOR_BUILD_PROGRESS", done=idx, total=len(rows))

    db.execute("INSERT OR REPLACE INTO index_state(k, v) VALUES ('manuals_sig', ?)", [sig])
    db.commit()
    db.close()
    log("VECTOR_BUILD_DONE", chunks=idx)
    return {"built": True, "chunks": idx}


async def search(query: str, top_k: int = 5, ambience: Optional[str] = None) -> list[dict]:
    """
    Ricerca semantica. Ritorna i chunk più pertinenti: [{title,text,url,ambience,score}].
    Se `ambience` è impostato, privilegia quel contesto (es. 'psicologico_relazionale').
    """
    if not query or not query.strip():
        return []
    if not os.path.exists(_DB_PATH):
        return []
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return []
    try:
        qkey = query.strip().lower()[:200]
        if qkey in _QUERY_CACHE:
            qemb = _QUERY_CACHE[qkey]
        else:
            qemb = (await _embed([query.strip()], api_key))[0]
            if len(_QUERY_CACHE) < _QUERY_CACHE_MAX:
                _QUERY_CACHE[qkey] = qemb

        import sqlite_vec
        db = _connect()
        # prende più candidati e poi applica eventuale filtro ambience.
        # sqlite-vec richiede il vincolo 'k = ?' sulla KNN; il JOIN va in subquery.
        k = top_k * 4 if ambience else top_k
        rows = db.execute(
            "SELECT m.title, m.text, m.url, m.ambience, m.source_tag, v.distance "
            "FROM (SELECT rowid, distance FROM vec_chunks WHERE emb MATCH ? AND k = ?) v "
            "JOIN chunks_meta m ON m.rowid = v.rowid ORDER BY v.distance",
            [sqlite_vec.serialize_float32(qemb), k],
        ).fetchall()
        db.close()

        results = [{
            "title": r[0], "text": r[1], "url": r[2],
            "ambience": r[3], "source": r[4], "score": round(1.0 - r[5], 4),
        } for r in rows]

        if ambience:
            pref = [x for x in results if x["ambience"] == ambience]
            rest = [x for x in results if x["ambience"] != ambience]
            results = (pref + rest)[:top_k]
        else:
            results = results[:top_k]
        return results
    except Exception as e:
        log("VECTOR_SEARCH_ERROR", error=str(e))
        return []


def _embed_one_sync(text: str, api_key: str) -> Optional[list[float]]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=30) as client:
        r = client.post(_EMBED_URL, headers=headers,
                        json={"model": _EMBED_MODEL, "input": [text[:8000]]})
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]


def search_sync(query: str, top_k: int = 5, ambience: Optional[str] = None) -> list[dict]:
    """Versione SINCRONA di search() per contesti non-async (es. context_assembler)."""
    if not query or not query.strip() or not os.path.exists(_DB_PATH):
        return []
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return []
    try:
        qkey = query.strip().lower()[:200]
        qemb = _QUERY_CACHE.get(qkey)
        if qemb is None:
            qemb = _embed_one_sync(query.strip(), api_key)
            if qemb and len(_QUERY_CACHE) < _QUERY_CACHE_MAX:
                _QUERY_CACHE[qkey] = qemb
        if not qemb:
            return []
        import sqlite_vec
        db = _connect()
        k = top_k * 4 if ambience else top_k
        rows = db.execute(
            "SELECT m.title, m.text, m.url, m.ambience, m.source_tag, v.distance "
            "FROM (SELECT rowid, distance FROM vec_chunks WHERE emb MATCH ? AND k = ?) v "
            "JOIN chunks_meta m ON m.rowid = v.rowid ORDER BY v.distance",
            [sqlite_vec.serialize_float32(qemb), k],
        ).fetchall()
        db.close()
        results = [{"title": r[0], "text": r[1], "url": r[2], "ambience": r[3],
                    "source": r[4], "score": round(1.0 - r[5], 4)} for r in rows]
        if ambience:
            pref = [x for x in results if x["ambience"] == ambience]
            rest = [x for x in results if x["ambience"] != ambience]
            results = (pref + rest)[:top_k]
        else:
            results = results[:top_k]
        return results
    except Exception as e:
        log("VECTOR_SEARCH_SYNC_ERROR", error=str(e))
        return []


async def stats() -> dict:
    try:
        if not os.path.exists(_DB_PATH):
            return {"indexed": 0}
        db = _connect()
        _ensure_schema(db)
        n = db.execute("SELECT COUNT(*) FROM chunks_meta").fetchone()[0]
        db.close()
        return {"indexed": n}
    except Exception:
        return {"indexed": 0}
