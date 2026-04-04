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


def _copy_baked_in_assets(source_dir: Path, volume_images: Path) -> None:
    """Copy baked-in files (flags, logos, SVGs) from source_dir to the volume."""
    if not source_dir.is_dir():
        return
    for item in source_dir.rglob("*"):
        if item.is_file():
            rel = item.relative_to(source_dir)
            dest = volume_images / rel
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item), str(dest))
                print(f"[sync_images]   copied {rel}")


def main() -> None:
    mount_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    if not mount_path:
        print("[sync_images] No RAILWAY_VOLUME_MOUNT_PATH set — skipping volume sync.")
        return

    volume_images = Path(mount_path)
    volume_images.mkdir(parents=True, exist_ok=True)

    # Ensure essential subdirectories exist on the volume
    for subdir in ("cities", "countries", "regions", "events", "persons", "monuments", "flags", "flags/countries", "flags/regions", "annotations"):
        (volume_images / subdir).mkdir(parents=True, exist_ok=True)

    # Already symlinked correctly — still sync baked-in assets then return
    if IMAGES_DIR.is_symlink():
        target = IMAGES_DIR.resolve()
        if target == volume_images.resolve():
            print(f"[sync_images] Symlink already in place → {volume_images}")
            # Sync baked-in flags from a temp extraction if available
            # (Nixpacks extracts code fresh each deploy but symlink persists from volume)
            # Flags are already on the volume if they were copied previously.
            return
        IMAGES_DIR.unlink()

    # Copy baked-in static assets (flags, logos, SVGs) to the volume
    if IMAGES_DIR.is_dir() and not IMAGES_DIR.is_symlink():
        _copy_baked_in_assets(IMAGES_DIR, volume_images)
        shutil.rmtree(str(IMAGES_DIR))

    # Create symlink: static/images → volume
    IMAGES_DIR.symlink_to(volume_images)
    print(f"[sync_images] Symlink created: static/images → {volume_images}")


if __name__ == "__main__":
    main()
