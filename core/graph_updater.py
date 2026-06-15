"""
GRAPH UPDATER — Motore di auto-aggiornamento del Knowledge Graph di Genesi.

Questo modulo è la coscienza viva del sistema:
  1. Watchdog su core/ e api/: quando un file .py cambia, marca i nodi corrispondenti
     come "recently_modified" nel JSON e aggiorna l'HTML.
  2. Psychological state sync: dopo ogni N turni di conversazione, legge lo stato
     psicologico reale (latent_state, global_insights, episodi, relational_state)
     e aggiorna il JSON con valori live.
  3. Growth events: ogni nuovo insight, episodio, o shift relazionale viene registrato
     come nodo/evento nel JSON — il grafo cresce assieme a Genesi.
  4. Introspection API: get_self_context() restituisce una stringa pronta per
     l'iniezione nel prompt LLM, permettendo a Genesi di ragionare sulla propria struttura.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("genesi")

_GRAPH_JSON = Path("genesi_graph.json")
_GRAPH_HTML = Path("genesi_graph.html")
_GROWTH_LOG = Path("memory/graph_growth_log.json")

# Debounce: non aggiornare più di 1 volta ogni 5 secondi per code changes
_CODE_DEBOUNCE_S = 5
# Psychological state: max 1 aggiornamento ogni 60 secondi
_PSY_DEBOUNCE_S = 60

# Ogni quanti turni aggiornare il psychological state (oltre al debounce time)
PSY_UPDATE_EVERY_N_TURNS = 20


class GraphUpdater:
    """
    Motore di auto-aggiornamento del Knowledge Graph di Genesi.
    Singleton — usa la variabile globale `graph_updater`.
    """

    def __init__(self):
        self._graph_data: Optional[Dict] = None
        self._last_code_update: float = 0.0
        self._last_psy_update: float = 0.0
        self._pending_code_change: bool = False
        self._observer = None
        self._turn_counter: int = 0
        self._lock = asyncio.Lock()

    # ── I/O ────────────────────────────────────────────────────────────────────

    def _load_graph(self) -> Dict:
        """Carica il JSON dal disco (con cache in-memory)."""
        if self._graph_data is not None:
            return self._graph_data
        try:
            self._graph_data = json.loads(_GRAPH_JSON.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("GRAPH_UPDATER load error: %s", e)
            self._graph_data = {"meta": {}, "nodes": [], "edges": []}
        return self._graph_data

    def _save_graph(self, data: Dict) -> None:
        """Salva il JSON su disco e aggiorna la cache."""
        try:
            _GRAPH_JSON.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._graph_data = data
            logger.info("GRAPH_UPDATER json_saved nodes=%d edges=%d",
                        len(data.get("nodes", [])), len(data.get("edges", [])))
        except Exception as e:
            logger.error("GRAPH_UPDATER save_error: %s", e)

    def _append_growth_event(self, event_type: str, description: str,
                              affects_nodes: List[str], data: Dict = None) -> None:
        """Aggiunge un growth event al log persistente."""
        try:
            _GROWTH_LOG.parent.mkdir(parents=True, exist_ok=True)
            events: List = []
            if _GROWTH_LOG.exists():
                try:
                    events = json.loads(_GROWTH_LOG.read_text(encoding="utf-8"))
                except Exception:
                    events = []
            events.append({
                "ts": datetime.utcnow().isoformat(),
                "event_type": event_type,
                "description": description,
                "affects_nodes": affects_nodes,
                "data": data or {},
            })
            # Mantieni ultimi 500 eventi
            if len(events) > 500:
                events = events[-500:]
            _GROWTH_LOG.write_text(
                json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.debug("GRAPH_UPDATER growth_log_error: %s", e)

    # ── CODE WATCHER ────────────────────────────────────────────────────────────

    def start_code_watcher(self) -> None:
        """Avvia watchdog per monitorare i cambiamenti ai file .py."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            updater_ref = self

            class _PyHandler(FileSystemEventHandler):
                def on_modified(self, event):
                    if not event.is_directory and event.src_path.endswith(".py"):
                        updater_ref._schedule_code_update(event.src_path)

                def on_created(self, event):
                    if not event.is_directory and event.src_path.endswith(".py"):
                        updater_ref._schedule_code_update(event.src_path)

            handler = _PyHandler()
            self._observer = Observer()
            for watch_dir in ("core", "api", "auth"):
                if os.path.isdir(watch_dir):
                    self._observer.schedule(handler, watch_dir, recursive=False)
            self._observer.start()
            logger.info("GRAPH_UPDATER code_watcher_started watching=core,api,auth")
        except Exception as e:
            logger.warning("GRAPH_UPDATER code_watcher_error: %s", e)
        # Riconciliazione startup: il watchdog NON vede i cambi avvenuti durante un
        # deploy (git pull + restart: i file cambiano mentre l'osservatore è spento).
        # Confrontiamo l'mtime dei file-sorgente con l'ultimo avvio registrato e
        # marchiamo i nodi modificati nel frattempo → ogni deploy si riflette nel grafo.
        try:
            self._reconcile_code_changes_on_startup()
        except Exception as e:
            logger.debug("GRAPH_UPDATER startup_reconcile_error: %s", e)

    def _reconcile_code_changes_on_startup(self) -> None:
        """Marca i nodi i cui file sono cambiati dall'ultimo avvio (cattura i deploy)."""
        graph = self._load_graph()
        rt = graph.setdefault("runtime_state", {})
        prev = rt.get("last_startup_ts")  # epoch float dell'avvio precedente
        now = time.time()
        now_iso = datetime.utcnow().isoformat()
        rt["last_startup_ts"] = now

        if not prev:
            # Primo avvio tracciato: fissa solo la baseline, niente marcatura di massa.
            self._save_graph(graph)
            return

        changed_nodes: List[str] = []
        files_changed: set = set()
        for node in graph.get("nodes", []):
            nf = node.get("file") or ""
            if not nf:
                continue
            # "core/proactor.py:182" → "core/proactor.py"
            path = nf.split(":")[0]
            try:
                if os.path.isfile(path) and os.path.getmtime(path) > prev:
                    node.setdefault("runtime_state", {})
                    node["runtime_state"]["last_modified"] = now_iso
                    node["runtime_state"]["recently_changed"] = True
                    changed_nodes.append(node["id"])
                    files_changed.add(path)
            except Exception:
                continue

        if changed_nodes:
            rt["last_code_update"] = now_iso
            rt.setdefault("recent_changes", [])
            rt["recent_changes"] = (
                [{"file": f, "ts": now_iso,
                  "nodes": [n["id"] for n in graph["nodes"]
                            if (n.get("file") or "").split(":")[0] == f]}
                 for f in sorted(files_changed)]
                + rt["recent_changes"]
            )[:20]
            logger.info("GRAPH_UPDATER startup_reconcile files=%d nodes=%d",
                        len(files_changed), len(changed_nodes))
        self._save_graph(graph)

    def stop_code_watcher(self) -> None:
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=3)
            except Exception:
                pass

    def _schedule_code_update(self, file_path: str) -> None:
        """Schedulare un aggiornamento del grafo per un file cambiato."""
        now = time.time()
        if now - self._last_code_update < _CODE_DEBOUNCE_S:
            self._pending_code_change = True
            return
        self._last_code_update = now
        self._pending_code_change = False

        # Lancia aggiornamento in background (thread watchdog → asyncio)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._update_for_code_change(file_path), loop
                )
        except Exception as e:
            logger.debug("GRAPH_UPDATER schedule_error: %s", e)

    async def _update_for_code_change(self, file_path: str) -> None:
        """Aggiorna i nodi corrispondenti al file cambiato."""
        async with self._lock:
            try:
                # Normalizza path (es. core/proactor.py)
                rel_path = Path(file_path).as_posix()
                for prefix in ("./", "/opt/genesi/"):
                    if rel_path.startswith(prefix):
                        rel_path = rel_path[len(prefix):]

                graph = self._load_graph()
                now_iso = datetime.utcnow().isoformat()
                changed_nodes = []

                for node in graph.get("nodes", []):
                    nf = node.get("file") or ""
                    # Match su path parziale (es. "core/proactor.py" in "core/proactor.py:182")
                    if nf and rel_path.split("/")[-1] in nf:
                        node.setdefault("runtime_state", {})
                        node["runtime_state"]["last_modified"] = now_iso
                        node["runtime_state"]["recently_changed"] = True
                        changed_nodes.append(node["id"])

                if changed_nodes:
                    # Aggiorna timestamp globale
                    graph.setdefault("runtime_state", {})
                    graph["runtime_state"]["last_code_update"] = now_iso
                    graph["runtime_state"].setdefault("recent_changes", [])
                    graph["runtime_state"]["recent_changes"] = (
                        [{
                            "file": rel_path,
                            "ts": now_iso,
                            "nodes": changed_nodes,
                        }] + graph["runtime_state"]["recent_changes"]
                    )[:20]  # mantieni ultimi 20

                    self._save_graph(graph)
                    self._append_growth_event(
                        "code_change",
                        f"File modificato: {rel_path} ({len(changed_nodes)} nodi aggiornati)",
                        changed_nodes,
                        {"file": rel_path},
                    )
                    logger.info("GRAPH_UPDATER code_change file=%s nodes=%s",
                                rel_path, changed_nodes)
            except Exception as e:
                logger.error("GRAPH_UPDATER code_update_error: %s", e)

    # ── PSYCHOLOGICAL STATE SYNC ────────────────────────────────────────────────

    async def update_psychological_state(self, user_id: str) -> None:
        """
        Sincronizza lo stato psicologico reale nel JSON.
        Chiamato ogni PSY_UPDATE_EVERY_N_TURNS turni da api/chat.py.
        Fail-silent — non blocca mai la risposta all'utente.
        """
        now = time.time()
        if now - self._last_psy_update < _PSY_DEBOUNCE_S:
            return
        self._last_psy_update = now

        async with self._lock:
            try:
                await self._do_psy_update(user_id)
            except Exception as e:
                logger.debug("GRAPH_UPDATER psy_update_error user=%s: %s", user_id, e)

    async def _do_psy_update(self, user_id: str) -> None:
        """Esegue l'aggiornamento psicologico effettivo."""
        from core.storage import storage

        graph = self._load_graph()
        now_iso = datetime.utcnow().isoformat()
        psy_snapshot: Dict[str, Any] = {"user_id": user_id, "updated_at": now_iso}
        growth_events: List[Dict] = []

        # 1. Latent state (vettore 5D)
        try:
            latent = await storage.load(f"latent_state:{user_id}", default={})
            if latent:
                dims = {k: round(latent.get(k, 0), 3)
                        for k in ("attachment", "curiosity", "emotional_resonance",
                                  "stability", "relational_energy")}
                psy_snapshot["latent_dimensions"] = dims
                # Aggiorna nodo latent_5d con valori reali
                for node in graph.get("nodes", []):
                    if node["id"] == "latent_5d":
                        prev = node.get("runtime_state", {}).get("current_values", {})
                        node.setdefault("runtime_state", {})["current_values"] = dims
                        node["runtime_state"]["updated_at"] = now_iso
                        # Rileva shift significativi (>0.10 in qualsiasi dimensione)
                        for k, v in dims.items():
                            old = prev.get(k, 0.45)
                            if abs(v - old) > 0.10:
                                growth_events.append({
                                    "type": "latent_shift",
                                    "dimension": k,
                                    "old": old, "new": v,
                                    "delta": round(v - old, 3),
                                })
        except Exception as e:
            logger.debug("GRAPH_UPDATER latent_read_error: %s", e)

        # 2. Relational state
        try:
            rel = await storage.load(f"relational_state:{user_id}", default={})
            current_rel = rel.get("state", rel.get("current_state", "NEUTRAL"))
            psy_snapshot["relational_state"] = current_rel
            for node in graph.get("nodes", []):
                if node["id"] == "relational_enum":
                    prev_rel = node.get("runtime_state", {}).get("current_state")
                    node.setdefault("runtime_state", {})["current_state"] = current_rel
                    node["runtime_state"]["updated_at"] = now_iso
                    if prev_rel and prev_rel != current_rel:
                        growth_events.append({
                            "type": "relational_shift",
                            "from": prev_rel, "to": current_rel,
                        })
        except Exception as e:
            logger.debug("GRAPH_UPDATER relational_read_error: %s", e)

        # 3. Global insights count
        try:
            gi = await storage.load(f"global_insights:{user_id}", default={})
            insights = gi.get("insights", [])
            psy_snapshot["global_insights_count"] = len(insights)
            psy_snapshot["global_insights_sample"] = insights[:3]
            for node in graph.get("nodes", []):
                if node["id"] == "global_memory":
                    prev_count = node.get("runtime_state", {}).get("insights_count", 0)
                    node.setdefault("runtime_state", {})["insights_count"] = len(insights)
                    node["runtime_state"]["sample"] = insights[:2]
                    if len(insights) > prev_count:
                        growth_events.append({
                            "type": "new_insight",
                            "count": len(insights),
                            "new_insights": insights[prev_count:],
                        })
        except Exception as e:
            logger.debug("GRAPH_UPDATER insights_read_error: %s", e)

        # 4. Episode count
        try:
            from core.storage import storage as _st
            ep = await _st.load(f"episodes:{user_id}", default=[])
            psy_snapshot["episode_count"] = len(ep)
            for node in graph.get("nodes", []):
                if node["id"] == "episode_memory":
                    node.setdefault("runtime_state", {})["episode_count"] = len(ep)
        except Exception as e:
            logger.debug("GRAPH_UPDATER episodes_read_error: %s", e)

        # 5. Personal facts count
        try:
            pf = await storage.load(f"personal_facts:{user_id}", default={})
            facts = pf.get("facts", pf) if isinstance(pf, dict) else []
            fact_count = len(facts) if isinstance(facts, list) else len(pf)
            psy_snapshot["personal_facts_count"] = fact_count
            for node in graph.get("nodes", []):
                if node["id"] == "personal_facts":
                    node.setdefault("runtime_state", {})["facts_count"] = fact_count
        except Exception as e:
            logger.debug("GRAPH_UPDATER facts_read_error: %s", e)

        # 6. Emotional trend (ultimi 3 stati)
        try:
            from core.emotional_memory import emotional_memory as _em
            recent = await _em.get_recent_emotions(user_id, n=3)
            if recent:
                psy_snapshot["recent_emotions"] = [
                    {"emotion": r.get("emotion"), "intensity": r.get("intensity")}
                    for r in recent
                ]
        except Exception as e:
            logger.debug("GRAPH_UPDATER emotions_read_error: %s", e)

        # Aggiorna runtime_state globale del grafo
        graph.setdefault("runtime_state", {})
        graph["runtime_state"]["psychological_snapshot"] = psy_snapshot
        graph["runtime_state"]["last_psy_update"] = now_iso

        # Aggiorna nodo psy_self_awareness con metadati sullo stato
        for node in graph.get("nodes", []):
            if node["id"] == "psy_self_awareness":
                node.setdefault("runtime_state", {})
                node["runtime_state"]["last_introspection"] = now_iso
                node["runtime_state"]["snapshot_summary"] = {
                    k: psy_snapshot.get(k)
                    for k in ("latent_dimensions", "relational_state", "global_insights_count",
                              "episode_count", "personal_facts_count")
                }

        self._save_graph(graph)

        # Log growth events
        for ev in growth_events:
            self._append_growth_event(
                ev["type"],
                self._describe_growth_event(ev),
                self._nodes_for_growth_event(ev),
                ev,
            )
            logger.info("GRAPH_GROWTH event=%s user=%s data=%s",
                        ev["type"], user_id, ev)

        logger.info("GRAPH_UPDATER psy_synced user=%s latent=%s rel=%s insights=%d",
                    user_id,
                    psy_snapshot.get("latent_dimensions", {}),
                    psy_snapshot.get("relational_state", "?"),
                    psy_snapshot.get("global_insights_count", 0))

    @staticmethod
    def _describe_growth_event(ev: Dict) -> str:
        t = ev.get("type")
        if t == "latent_shift":
            d = "+" if ev["delta"] > 0 else ""
            return (f"Shift latente: {ev['dimension']} {d}{ev['delta']:.3f} "
                    f"({ev['old']:.3f} → {ev['new']:.3f})")
        if t == "relational_shift":
            return f"Cambio stato relazionale: {ev['from']} → {ev['to']}"
        if t == "new_insight":
            return f"Nuovi insight consolidati: {ev.get('count', 0)} totali"
        return str(ev)

    @staticmethod
    def _nodes_for_growth_event(ev: Dict) -> List[str]:
        t = ev.get("type")
        if t == "latent_shift":
            dim_map = {
                "attachment": "psy_attachment",
                "curiosity": "psy_curiosity",
                "emotional_resonance": "psy_emotional_res",
                "stability": "psy_stability",
                "relational_energy": "psy_relational_e",
            }
            return ["latent_5d", dim_map.get(ev.get("dimension", ""), "latent_5d")]
        if t == "relational_shift":
            return ["relational_enum", "relational_state_engine"]
        if t == "new_insight":
            return ["global_memory", "key_global_insights", "psy_self_awareness"]
        return []

    # ── TURN COUNTER ───────────────────────────────────────────────────────────

    async def on_turn(self, user_id: str) -> None:
        """
        Chiamato ad ogni turno di conversazione da api/chat.py.
        Schedula SEMPRE l'aggiornamento psicologico: `update_psychological_state` si
        auto-limita a 1/60s (_PSY_DEBOUNCE_S), quindi non c'è spam. Il vecchio gate a
        N turni non era affidabile — `_turn_counter` è in-memory e si azzera ad ogni
        restart, perciò con poche conversazioni per finestra la soglia (20) non veniva
        mai raggiunta e last_psy_update restava None (grafo mai aggiornato).
        """
        self._turn_counter += 1
        asyncio.create_task(self.update_psychological_state(user_id))

    # ── INTROSPECTION API ──────────────────────────────────────────────────────

    def get_self_context(self, query_tags: Optional[List[str]] = None) -> str:
        """
        Restituisce una stringa pronta per l'iniezione nel prompt LLM.
        Se query_tags è fornito (es. ["grief_detection", "group_consciousness"]),
        filtra solo i nodi rilevanti.
        Genesi usa questo per ragionare sulla propria struttura interna.
        """
        try:
            graph = self._load_graph()
            nodes = graph.get("nodes", [])
            edges = graph.get("edges", [])
            rt = graph.get("runtime_state", {})

            # Filtra nodi per tag se specificato
            if query_tags:
                nodes = [
                    n for n in nodes
                    if any(t in (n.get("psy") or n.get("psychological_tags", [])) for t in query_tags)
                ]
            # Costruisci mappa nodi per lookups veloci
            node_map = {n["id"]: n for n in nodes}
            relevant_ids = set(node_map.keys())

            lines = ["[INTROSPEZIONE SISTEMA — GENESI KNOWLEDGE GRAPH]"]
            lines.append(f"Versione: {graph.get('meta', {}).get('version', '1.0.0')}")

            # Stato psicologico corrente
            snap = rt.get("psychological_snapshot", {})
            if snap:
                lines.append("\n=== STATO PSICOLOGICO CORRENTE ===")
                ld = snap.get("latent_dimensions")
                if ld:
                    lines.append("Dimensioni latenti:")
                    for k, v in ld.items():
                        bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
                        lines.append(f"  {k:<22} {bar} {v:.3f}")
                rel = snap.get("relational_state")
                if rel:
                    lines.append(f"Stato relazionale: {rel}")
                gi = snap.get("global_insights_count")
                if gi is not None:
                    lines.append(f"Insight consolidati: {gi}")
                ep = snap.get("episode_count")
                if ep is not None:
                    lines.append(f"Episodi personali: {ep}")

            # Nodi rilevanti
            if nodes:
                lines.append("\n=== MODULI RILEVANTI ===")
                for node in nodes[:20]:  # max 20 per non esplodere il context
                    nid = node["id"]
                    layer = node.get("layer", "?")
                    ntype = node.get("type", "?")
                    label = node.get("label", nid)
                    desc = (node.get("desc") or node.get("description") or "")[:100]
                    rs = node.get("runtime_state", {})
                    state_str = ""
                    if rs.get("recently_changed"):
                        state_str = " [⚡ MODIFICATO RECENTEMENTE]"
                    elif rs.get("current_values"):
                        state_str = f" [valori: {rs['current_values']}]"
                    elif rs.get("current_state"):
                        state_str = f" [stato: {rs['current_state']}]"
                    lines.append(f"• [{layer}/{ntype}] {label}{state_str}")
                    if desc:
                        lines.append(f"  → {desc}")

                    # Connessioni uscenti rilevanti
                    out_edges = [
                        e for e in edges
                        if e.get("from") == nid and e.get("to") in relevant_ids
                    ][:3]
                    for e in out_edges:
                        target = node_map.get(e.get("to", ""), {})
                        lines.append(f"  --[{e.get('rel','?')}]--> {target.get('label', e.get('to', '?'))}")

            # Recent changes
            recent = rt.get("recent_changes", [])[:3]
            if recent:
                lines.append("\n=== MODIFICHE RECENTI AL CODICE ===")
                for ch in recent:
                    lines.append(f"• {ch.get('file', '?')} ({ch.get('ts', '?')[:10]})")

            return "\n".join(lines)
        except Exception as e:
            return f"[INTROSPEZIONE NON DISPONIBILE: {e}]"

    def get_recent_growth_events(self, n: int = 10) -> List[Dict]:
        """Ritorna gli ultimi N growth events."""
        try:
            if _GROWTH_LOG.exists():
                events = json.loads(_GROWTH_LOG.read_text(encoding="utf-8"))
                return events[-n:]
        except Exception:
            pass
        return []

    def get_graph_summary(self) -> Dict:
        """Ritorna un riassunto compatto del grafo per API/admin."""
        try:
            graph = self._load_graph()
            rt = graph.get("runtime_state", {})
            snap = rt.get("psychological_snapshot", {})
            return {
                "nodes": len(graph.get("nodes", [])),
                "edges": len(graph.get("edges", [])),
                "version": graph.get("meta", {}).get("version", "?"),
                "last_code_update": rt.get("last_code_update"),
                "last_psy_update": rt.get("last_psy_update"),
                "relational_state": snap.get("relational_state"),
                "latent_dimensions": snap.get("latent_dimensions"),
                "global_insights_count": snap.get("global_insights_count"),
                "episode_count": snap.get("episode_count"),
                "recent_changes": rt.get("recent_changes", [])[:5],
            }
        except Exception as e:
            return {"error": str(e)}


# Singleton globale
graph_updater = GraphUpdater()
