from __future__ import annotations

from pathlib import Path
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    candidates = [
        root / "app" / "assets" / "icon.png",
        root / "app" / "icon.png",
    ]
    src = next((path for path in candidates if path.exists()), None)
    dst = root / "app" / "assets" / "icon.ico"
    if not dst.parent.exists():
        dst = root / "app" / "icon.ico"

    if src is None:
        print("[icon] icon.png not found at app/assets/icon.png or app/icon.png")
        print("[icon] skipping .ico generation")
        return 0

    try:
        from PIL import Image
    except Exception as exc:
        print(f"[icon] Pillow import failed: {exc}")
        return 1

    img = Image.open(src).convert("RGBA")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(dst, format="ICO", sizes=sizes)
    print(f"[icon] source: {src}")
    print(f"[icon] generated: {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
