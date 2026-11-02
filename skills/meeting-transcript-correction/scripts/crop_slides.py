# created: 2026-11-02 14:33:54
"""Crop projector-screen photos and upscale them for OCR / image reading.

The camera photo usually contains a bright screen surrounded by dark room. This
script does not try to detect the screen automatically: pass a normalized box
(or pixel box) measured once per photo series. It then upscales with Lanczos so
small slide labels become readable, and can split the crop into tiles to work
around tools that downscale long images.

Usage:
    python crop_slides.py images/*.jpg --out crops --box 0.28,0.36,0.76,0.71 --scale 3
    python crop_slides.py images/17.jpg --out crops --box 0.30,0.40,0.75,0.70 --scale 4 --tiles 2x1

Box format: "left,top,right,bottom"; values in [0, 1] are normalized to the
image size, otherwise they are treated as pixels. --tiles is "<rows>x<cols>";
2x1 means top/bottom halves, 1x2 means left/right halves.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def parse_box(text: str, width: int, height: int) -> tuple[int, int, int, int]:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        raise SystemExit(f"--box needs 4 values, got {text!r}")
    values = [float(p) for p in parts]
    if all(0.0 <= v <= 1.0 for v in values):
        left, top, right, bottom = (
            int(values[0] * width),
            int(values[1] * height),
            int(values[2] * width),
            int(values[3] * height),
        )
    else:
        left, top, right, bottom = (int(v) for v in values)
    left, top = max(0, left), max(0, top)
    right, bottom = min(width, right), min(height, bottom)
    if right <= left or bottom <= top:
        raise SystemExit(f"empty crop box after clamping: {(left, top, right, bottom)}")
    return left, top, right, bottom


def parse_tiles(text: str) -> tuple[int, int]:
    if not text:
        return 1, 1
    try:
        rows_text, cols_text = text.lower().split("x")
        rows, cols = int(rows_text), int(cols_text)
    except ValueError as exc:
        raise SystemExit(f"--tiles must look like 2x1 or 1x2, got {text!r}") from exc
    if rows < 1 or cols < 1:
        raise SystemExit("--tiles values must be positive")
    return rows, cols


def main() -> None:
    parser = argparse.ArgumentParser(description="Crop and upscale slide photos for OCR")
    parser.add_argument("images", nargs="+", help="input image paths")
    parser.add_argument("--out", default="crops", help="output directory (default: crops)")
    parser.add_argument(
        "--box",
        default="0.28,0.36,0.76,0.71",
        help="crop box left,top,right,bottom; normalized if all in [0,1] (default: 0.28,0.36,0.76,0.71)",
    )
    parser.add_argument("--scale", type=float, default=3.0, help="upscale factor (default: 3)")
    parser.add_argument(
        "--tiles",
        default="",
        help="optional split, <rows>x<cols>; 2x1 = top/bottom, 1x2 = left/right",
    )
    parser.add_argument(
        "--max-side",
        type=int,
        default=2400,
        help="cap for the longest output side; <=0 disables (default: 2400)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, cols = parse_tiles(args.tiles)

    written = []
    for name in args.images:
        src = Path(name)
        if not src.is_file():
            print(f"[skip] not a file: {src}")
            continue
        with Image.open(src) as image:
            width, height = image.size
            left, top, right, bottom = parse_box(args.box, width, height)
            crop = image.crop((left, top, right, bottom)).convert("RGB")

        tile_width = crop.width // cols
        tile_height = crop.height // rows
        for row in range(rows):
            for col in range(cols):
                tile = crop.crop(
                    (
                        col * tile_width,
                        row * tile_height,
                        crop.width if col == cols - 1 else (col + 1) * tile_width,
                        crop.height if row == rows - 1 else (row + 1) * tile_height,
                    )
                )
                new_size = (round(tile.width * args.scale), round(tile.height * args.scale))
                if args.max_side > 0 and max(new_size) > args.max_side:
                    ratio = args.max_side / max(new_size)
                    new_size = (max(1, round(new_size[0] * ratio)), max(1, round(new_size[1] * ratio)))
                tile = tile.resize(new_size, Image.LANCZOS)

                suffix = f"_r{row + 1}c{col + 1}" if rows * cols > 1 else ""
                dst = out_dir / f"{src.stem}{suffix}.png"
                tile.save(dst)
                written.append(dst)
                print(f"{src} -> {dst} ({tile.width}x{tile.height})")

    if not written:
        raise SystemExit("no output written")
    print(f"\n{len(written)} file(s) written to {out_dir.resolve()}")


if __name__ == "__main__":
    main()
