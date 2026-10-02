"""Package the existing Console logo for phone home screens, without redrawing it."""
from pathlib import Path
from PIL import Image


PROJECT = Path(__file__).resolve().parents[1]
BACKGROUND = (255, 255, 255, 255)
FOREGROUND_RATIO = 0.72
SIZES = (180, 192, 512)


def main():
    with Image.open(PROJECT / "codex-resource-icon-256.png") as opened:
        logo = opened.convert("RGBA")
    bounds = logo.getchannel("A").getbbox()
    if not bounds:
        raise ValueError("The existing Console logo is empty.")
    logo = logo.crop(bounds)
    for size in SIZES:
        side = round(size * FOREGROUND_RATIO)
        ratio = side / max(logo.size)
        artwork = logo.resize((round(logo.width * ratio), round(logo.height * ratio)), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), BACKGROUND)
        canvas.alpha_composite(artwork, ((size - artwork.width) // 2, (size - artwork.height) // 2))
        canvas.convert("RGB").save(PROJECT / "phone" / f"phone-icon-{size}.png", optimize=True)
    print("Packaged original Console artwork: 180, 192, 512; opaque white background; 72% foreground.")


if __name__ == "__main__":
    main()
