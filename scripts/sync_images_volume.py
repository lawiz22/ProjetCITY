"""Sync static/images with a persistent Railway volume.

When RAILWAY_VOLUME_MOUNT_PATH is set, this script:
  1. Copies any NEW files from the baked-in static/images/ to the volume
     (files already in the volume are NOT overwritten — production wins).
  2. Replaces static/images/ with a symlink to the volume.

This ensures photos uploaded in production survive redeploys, while
new photos committed to git are also carried over.

Run BEFORE gunicorn starts (add to deploy.startCommand in railway.json).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = PROJECT_ROOT / "static" / "images"


def main() -> None:
    mount_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    if not mount_path:
        print("[sync_images] No RAILWAY_VOLUME_MOUNT_PATH set — skipping volume sync.")
        return

    volume_images = Path(mount_path)
    volume_images.mkdir(parents=True, exist_ok=True)

    # If static/images is already a symlink pointing to the volume, skip copy
    if IMAGES_DIR.is_symlink():
        target = IMAGES_DIR.resolve()
        if target == volume_images.resolve():
            print(f"[sync_images] Symlink already in place → {volume_images}")
            return
        # Symlink points elsewhere — remove it and redo
        IMAGES_DIR.unlink()

    # Step 1: Copy new files from baked-in images to volume (don't overwrite)
    if IMAGES_DIR.is_dir() and not IMAGES_DIR.is_symlink():
        copied = 0
        skipped = 0
        for src_file in IMAGES_DIR.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(IMAGES_DIR)
            dest = volume_images / rel
            if dest.exists():
                skipped += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_file), str(dest))
            copied += 1

        print(f"[sync_images] Synced {copied} new file(s) to volume, {skipped} already present.")

        # Remove the baked-in directory so we can symlink
        shutil.rmtree(str(IMAGES_DIR))
    elif not IMAGES_DIR.exists():
        print("[sync_images] No baked-in static/images/ found — using volume as-is.")

    # Step 2: Create symlink  static/images → volume
    IMAGES_DIR.symlink_to(volume_images)
    print(f"[sync_images] Symlink created: static/images → {volume_images}")


if __name__ == "__main__":
    main()
