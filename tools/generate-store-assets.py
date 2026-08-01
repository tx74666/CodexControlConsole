import argparse
from pathlib import Path

from PIL import Image


ASSETS = {
    "StoreLogo.png": (50, 50, 0.82),
    "Square44x44Logo.png": (44, 44, 0.82),
    "Square150x150Logo.png": (150, 150, 0.82),
    "Square310x310Logo.png": (310, 310, 0.78),
    "Wide310x150Logo.png": (310, 150, 0.76),
}


def render(source, destination, width, height, scale):
    maximum_width = max(1, round(width * scale))
    maximum_height = max(1, round(height * scale))
    icon = source.copy()
    icon.thumbnail((maximum_width, maximum_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(icon, ((width - icon.width) // 2, (height - icon.height) // 2))
    canvas.save(destination, format="PNG", optimize=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--listing-output", type=Path)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    with Image.open(args.source) as opened:
        source = opened.convert("RGBA")
    for name, (width, height, scale) in ASSETS.items():
        render(source, args.output / name, width, height, scale)
    if args.listing_output:
        args.listing_output.mkdir(parents=True, exist_ok=True)
        render(source, args.listing_output / "StoreLogo300x300.png", 300, 300, 0.82)


if __name__ == "__main__":
    main()
