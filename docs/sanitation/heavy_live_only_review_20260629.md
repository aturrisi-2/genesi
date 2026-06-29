<!-- DOCUMENTATION ONLY -->
<!-- DO NOT APPLY WITHOUT HUMAN APPROVAL -->

# Heavy Live-only Review - 2026-06-29

**DOCUMENTATION ONLY. DO NOT APPLY WITHOUT HUMAN APPROVAL.**

# Genesi heavy live-only owner review

## Sintesi
- LEGACY_HEAVY_PROBABLE: 18
- KEEP_WEB_TTS_STT: 2
- KEEP_MEDIA_OCR: 5
- FEATURE_FROZEN: 2
- UNKNOWN_OWNER: 3

## Dettaglio
- `torch` live=2.2.2 staging=no class=LEGACY_HEAVY_PROBABLE refs=15 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `tensorflow` live=2.21.0 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `TTS` live=0.22.0 staging=no class=KEEP_WEB_TTS_STT refs=20 can_stay_out=UNKNOWN
  - KEEP/REVIEW; verify owner. `ctranslate2` is used by faster-whisper STT Web and is in staging; `TTS` is live-only and may be legacy Coqui TTS rather than current Web TTS provider.
- `gruut` live=2.2.3 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `nvidia-cublas-cu12` live=12.1.3.1 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `nvidia-cuda-cupti-cu12` live=12.1.105 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `nvidia-cuda-nvrtc-cu12` live=12.1.105 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `nvidia-cuda-runtime-cu12` live=12.1.105 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `nvidia-cudnn-cu12` live=8.9.2.26 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `nvidia-cufft-cu12` live=11.0.2.54 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `nvidia-curand-cu12` live=10.3.2.106 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `nvidia-cusolver-cu12` live=11.4.5.107 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `nvidia-cusparse-cu12` live=12.1.0.106 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `nvidia-nccl-cu12` live=2.19.3 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `nvidia-nvjitlink-cu12` live=12.9.86 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `nvidia-nvtx-cu12` live=12.1.105 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `triton` live=2.2.0 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `f5-tts` live=1.1.15 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `bitsandbytes` live=0.49.1 staging=no class=LEGACY_HEAVY_PROBABLE refs=0 can_stay_out=YES
  - Heavy ML/audio stack; live-only or legacy likely. Do not remove from production; keep out of refined until owner review.
- `facenet-pytorch` live=2.6.0 staging=no class=KEEP_MEDIA_OCR refs=1 can_stay_out=UNKNOWN
  - KEEP; needed/likely for face/media/OCR runtime. Can stay outside refined only if feature owner accepts reduced media/face capability.
- `ctranslate2` live=4.8.0 staging=4.8.0 class=KEEP_WEB_TTS_STT refs=0 can_stay_out=YES
  - KEEP/REVIEW; verify owner. `ctranslate2` is used by faster-whisper STT Web and is in staging; `TTS` is live-only and may be legacy Coqui TTS rather than current Web TTS provider.
- `onnxruntime` live=1.26.0 staging=1.27.0 class=KEEP_MEDIA_OCR refs=0 can_stay_out=YES
  - KEEP; needed/likely for face/media/OCR runtime. Can stay outside refined only if feature owner accepts reduced media/face capability.
- `playwright` live=1.58.0 staging=no class=FEATURE_FROZEN refs=5 can_stay_out=YES
  - Browser automation/social/admin legacy; do not include in runtime refined without explicit owner review.
- `selenium` live=no staging=no class=FEATURE_FROZEN refs=0 can_stay_out=YES
  - Browser automation/social/admin legacy; do not include in runtime refined without explicit owner review.
- `pandas` live=1.5.3 staging=no class=UNKNOWN_OWNER refs=0 can_stay_out=UNKNOWN
  - Data/ML dependency; not in refined staging. Needs owner review before removal or inclusion.
- `sklearn` live=no staging=no class=UNKNOWN_OWNER refs=0 can_stay_out=UNKNOWN
  - Data/ML dependency; not in refined staging. Needs owner review before removal or inclusion.
- `pyarrow` live=23.0.0 staging=no class=UNKNOWN_OWNER refs=0 can_stay_out=UNKNOWN
  - Data/ML dependency; not in refined staging. Needs owner review before removal or inclusion.
- `opencv-python` live=4.13.0.92 staging=4.11.0.86 class=KEEP_MEDIA_OCR refs=2 can_stay_out=YES
  - KEEP; needed/likely for face/media/OCR runtime. Can stay outside refined only if feature owner accepts reduced media/face capability.
- `opencv-python-headless` live=no staging=4.11.0.86 class=KEEP_MEDIA_OCR refs=2 can_stay_out=YES
  - KEEP; needed/likely for face/media/OCR runtime. Can stay outside refined only if feature owner accepts reduced media/face capability.
- `cv2` live=no staging=no class=KEEP_MEDIA_OCR refs=2 can_stay_out=YES
  - KEEP; needed/likely for face/media/OCR runtime. Can stay outside refined only if feature owner accepts reduced media/face capability.


---

# Genesi heavy live-only action plan

## Decisioni immediate
- Non rimuovere nulla dal venv production.
- Non modificare requirements repo.
- Non reinserire heavy nel refined staging senza owner review.

## Azioni future
1. Confermare owner feature per media/OCR/face: `onnxruntime`, `opencv`, `facenet-pytorch` legacy vs InsightFace attuale.
2. Confermare stato TTS/STT Web: `ctranslate2`, `faster-whisper`, `TTS`, `gruut`.
3. Confermare se training/evolution/lab richiede ancora `torch`, `tensorflow`, `nvidia-*`, `triton`, `f5-tts`, `bitsandbytes`.
4. Confermare browser automation/social: `playwright`, `selenium`.
5. Solo dopo owner review, creare staging v3 e test offline completi.

## Stop gate
Qualunque rimozione o reinstallazione heavy richiede approvazione umana, backup/rollback e nessuno switch automatico.

