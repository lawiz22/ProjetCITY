"""Generate thumbnails for all existing photos in the project.

Scans all entity photo directories and creates thumb_{filename}.jpg
for any original that doesn't already have a thumbnail.

Usage:
    python scripts/generate_thumbnails.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]

THUMB_MAX_SIZE = (400, 400)
THUMB_QUALITY = 80


def generate_thumbnail(original_path: Path) -> Path | None:
    """Create a JPEG thumbnail next to the original."""
    original_path = Path(original_path)
    if not original_path.is_file():
        return None
    thumb_path = original_path.parent / f"thumb_{original_path.stem}.jpg"
    if thumb_path.exists() and thumb_path.stat().st_size > 0:
        return thumb_path
    try:
        with Image.open(original_path) as img:
            img = img.convert("RGB")
            img.thumbnail(THUMB_MAX_SIZE, Image.LANCZOS)
            img.save(thumb_path, "JPEG", quality=THUMB_QUALITY, optimize=True)
        return thumb_path
    except Exception as exc:
        print(f"  Thumbnail error for {original_path}: {exc}")
        return None

IMAGES_ROOT = PROJECT_ROOT / "static" / "images"

ENTITY_DIRS = [
    IMAGES_ROOT / "cities",
    IMAGES_ROOT / "events",
    IMAGES_ROOT / "persons",
    IMAGES_ROOT / "monuments",
    IMAGES_ROOT / "legends",
    IMAGES_ROOT / "countries",
    IMAGES_ROOT / "regions",
    IMAGES_ROOT / "annotations",
]

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def main() -> None:
    created = 0
    skipped = 0
    failed = 0
    total = 0

    for entity_dir in ENTITY_DIRS:
        if not entity_dir.exists():
            continue
        label = entity_dir.name
        dir_created = 0
        for photo_file in sorted(entity_dir.rglob("*")):
            if not photo_file.is_file():
                continue
            if photo_file.suffix.lower() not in EXTENSIONS:
                continue
            if photo_file.name.startswith("thumb_"):
                continue
            total += 1
            thumb_path = photo_file.parent / f"thumb_{photo_file.stem}.jpg"
            if thumb_path.exists() and thumb_path.stat().st_size > 0:
                skipped += 1
                continue
            result = generate_thumbnail(photo_file)
            if result:
                created += 1
                dir_created += 1
            else:
                failed += 1
                print(f"  FAIL: {photo_file.relative_to(IMAGES_ROOT)}")
        if dir_created:
            print(f"  {label}: {dir_created} thumbnails created")

    print(f"\nDone. {total} originals found, {created} thumbs created, {skipped} already existed, {failed} failed.")


if __name__ == "__main__":
    main()
