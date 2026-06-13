# core/log.py
# Logger strutturato per Genesi.
# Formato: [ISO_TIMESTAMP] TAG key=value key=value
# Leggibile in tempo reale via journalctl -u genesi -f -o short-iso

from datetime import datetime


def _ts() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


def _trunc(s: str, max_len: int = 80) -> str:
    s = s.replace("\n", " ").strip()
    return s[:max_len] + "..." if len(s) > max_len else s


# Chiavi sensibili da mascherare SEMPRE nei log (sicurezza: niente segreti in chiaro)
_SECRET_HINTS = ("token", "secret", "password", "passwd", "refresh", "api_key", "apikey",
                 "access_token", "client_secret", "authorization", "credential", "private_key")


def _redact(obj, _depth: int = 0):
    """Maschera ricorsivamente i valori delle chiavi sensibili in dict/list."""
    if _depth > 6:
        return obj
    try:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if isinstance(k, str) and any(h in k.lower() for h in _SECRET_HINTS):
                    out[k] = "<redacted>"
                else:
                    out[k] = _redact(v, _depth + 1)
            return out
        if isinstance(obj, (list, tuple)):
            return type(obj)(_redact(x, _depth + 1) for x in obj)
    except Exception:
        return obj
    return obj


import os

LOG_FILE = "genesi.log"
_MAX_LOG_BYTES = 50 * 1024 * 1024  # rotazione a 50MB
_write_count = 0


def _rotate_if_needed():
    """Rotazione per dimensione: tiene un backup (.1) e riparte. Evita log enormi."""
    try:
        if os.path.getsize(LOG_FILE) > _MAX_LOG_BYTES:
            bak = LOG_FILE + ".1"
            try:
                if os.path.exists(bak):
                    os.remove(bak)
            except Exception:
                pass
            os.rename(LOG_FILE, bak)
    except Exception:
        pass


def log(tag: str, **kwargs):
    parts = [f"[{_ts()}] {tag}"]
    for k, v in kwargs.items():
        # Sicurezza: maschera segreti (chiavi tipo token/secret, anche annidate in dict/list)
        if isinstance(k, str) and any(h in k.lower() for h in _SECRET_HINTS):
            v = "<redacted>"
        elif isinstance(v, (dict, list, tuple)):
            v = _redact(v)
        if isinstance(v, str) and " " in v:
            parts.append(f'{k}="{_trunc(v)}"')
        elif isinstance(v, str):
            parts.append(f"{k}={_trunc(v)}")
        elif isinstance(v, bool):
            parts.append(f"{k}={'true' if v else 'false'}")
        elif isinstance(v, float):
            parts.append(f"{k}={v:.3f}")
        else:
            parts.append(f"{k}={v}")
    
    log_line = " ".join(parts)
    print(log_line, flush=True)
    
    # Scrittura su file persistente per Auditor
    global _write_count
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
        _write_count += 1
        if _write_count % 500 == 0:
            _rotate_if_needed()
    except Exception:
        pass
