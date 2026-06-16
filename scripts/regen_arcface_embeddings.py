"""One-off: rebuild ArcFace .npy embeddings from stored registration jpgs.

Reads each data/faces/<name>.json (image_path + description_in_image with [INDEX:N])
and calls compute_and_save_embeddings to (re)create the <name>.npy embedding.

Use after the VGGFace2->ArcFace migration, or whenever the embedding format changes
(e.g. raw .embedding -> normed_embedding). Pass --purge to delete existing .npy first
so the rebuild is clean (compute_and_save_embeddings APPENDS, so mixing formats must
be avoided — always --purge when the embedding format changed).

Usage:
    python scripts/regen_arcface_embeddings.py [--purge]
"""
import os
import sys
import json
import glob
import asyncio

# Run from the repo root regardless of cwd.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
os.chdir(_REPO_ROOT)

from core.biometric_service import compute_and_save_embeddings, FACES_DIR  # noqa: E402


async def main(purge: bool) -> None:
    if purge:
        removed = 0
        for npy in glob.glob(os.path.join(FACES_DIR, "*.npy")):
            try:
                os.remove(npy)
                removed += 1
            except OSError as e:
                print("PURGE_ERROR", npy, e)
        print(f"PURGED {removed} stale .npy")

    jsons = sorted(glob.glob(os.path.join(FACES_DIR, "*.json")))
    ok = fail = 0
    for jp in jsons:
        try:
            with open(jp, encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:  # noqa: BLE001
            print("SKIP_BAD_JSON", jp, e)
            continue
        name = meta.get("name")
        img = meta.get("image_path")
        hint = meta.get("description_in_image", "")
        if not name or not img:
            print("SKIP_NO_NAME_OR_IMG", jp)
            continue
        if not os.path.exists(img):
            print("SKIP_MISSING_IMG", name, img)
            fail += 1
            continue
        saved = await compute_and_save_embeddings(name, img, description_hint=hint)
        npy = os.path.join(FACES_DIR, name.strip().lower().replace(" ", "_") + ".npy")
        if saved and os.path.exists(npy):
            print("OK", name, "->", os.path.basename(npy))
            ok += 1
        else:
            print("FAIL_NO_FACE", name, img)
            fail += 1
    print(f"DONE ok={ok} fail={fail} total={len(jsons)}")


if __name__ == "__main__":
    asyncio.run(main(purge="--purge" in sys.argv))
