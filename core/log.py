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


import os

LOG_FILE = "genesi.log"

def log(tag: str, **kwargs):
    parts = [f"[{_ts()}] {tag}"]
    for k, v in kwargs.items():
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
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except Exception:
        pass
