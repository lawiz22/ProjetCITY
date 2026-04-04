"""Ensure static/images points to the persistent Railway volume.

When RAILWAY_VOLUME_MOUNT_PATH is set, this script replaces
static/images/ with a symlink to the volume so photos survive redeploys.

Run BEFORE gunicorn starts (deploy.startCommand in railway.json).
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

    # Already symlinked correctly — nothing to do
    if IMAGES_DIR.is_symlink():
        target = IMAGES_DIR.resolve()
        if target == volume_images.resolve():
            print(f"[sync_images] Symlink already in place → {volume_images}")
            return
        IMAGES_DIR.unlink()

    # Ensure essential subdirectories exist on the volume
    for subdir in ("cities", "countries", "regions", "events", "persons", "monuments", "flags", "annotations"):
        (volume_images / subdir).mkdir(parents=True, exist_ok=True)

    # Copy non-photo static assets (logos, SVGs) if they exist baked-in
    if IMAGES_DIR.is_dir() and not IMAGES_DIR.is_symlink():
        for item in IMAGES_DIR.iterdir():
            if item.is_file():
                dest = volume_images / item.name
                if not dest.exists():
                    shutil.copy2(str(item), str(dest))
        shutil.rmtree(str(IMAGES_DIR))

    # Create symlink: static/images → volume
    IMAGES_DIR.symlink_to(volume_images)
    print(f"[sync_images] Symlink created: static/images → {volume_images}")


if __name__ == "__main__":
    main()
