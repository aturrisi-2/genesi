<!-- DOCUMENTATION ONLY -->
<!-- DO NOT APPLY WITHOUT HUMAN APPROVAL -->

# ONNX Model Review - 2026-06-29

**DOCUMENTATION ONLY. DO NOT APPLY WITHOUT HUMAN APPROVAL.**

# Genesi ONNX model owner review

## Metadata
- path: `/opt/genesi/models/leonardo-epoch=2024-step=996300.onnx`
- exists: True
- size_bytes: 63511038
- size_human: 60.6 MB
- mtime_epoch: 1772365077
- mode: 0o664
- owner_uid_gid: 1000:1000
- sha256: `e693ab78e13790d7440ecaad8f886570ca2b2918af5f8c7bf700d509f0629361`
- git_tracked: True

## Reference search
```text
scripts/sensory_skills_test.py:51:                        '/opt/piper/voices/it_IT-paola-medium.onnx',
core/tts_provider.py:66:        self.model = os.getenv("PIPER_MODEL", f"/opt/piper/voices/{model}.onnx")
core/tts_provider.py:67:        self.config = os.getenv("PIPER_CONFIG", f"/opt/piper/voices/{model}.onnx.json")
tts/piper_tts.py:15:PIPER_MODEL = os.getenv("PIPER_MODEL", "/opt/piper/voices/it_IT-paola-medium.onnx")
tts/piper_tts.py:16:PIPER_CONFIG = os.getenv("PIPER_CONFIG", "/opt/piper/voices/it_IT-paola-medium.onnx.json")
core/instagram_publisher.py:542:        piper_model = os.getenv("PIPER_MODEL", "/opt/piper/voices/it_IT-paola-medium.onnx")

```

## Classification
- final_category: `ORPHAN_MODEL`
- reason: no direct filename references found; only generic ONNX/Piper references found
- recommendation: `NON_TOCCARE`; archive/removal only after owner confirmation, manifest and backup.

## Constraints
- No delete.
- No move.
- No model load.
- No production change.


## Important
The ONNX model is tracked by Git and must not be removed or archived without owner confirmation, manifest, backup, and a dedicated approval gate.
