"""Google Play phone screenshots from the emulator captures in docs/android-screenshots.

Play allows a long side of at most twice the short side; the 1080 x 2400 captures are 2.22:1. Instead of cropping off the
app's navigation bar, each capture gets narrow side margins in its own background colour: 1200 x 2400 (exactly 2:1).
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "android-screenshots"
OUT = ROOT / "fastlane" / "metadata" / "android" / "en-US" / "images" / "phoneScreenshots"
ORDER = ["light-dashboard", "light-compose", "light-automation-running", "light-agents", "light-recipients",
         "dark-compose", "light-signature", "light-welcome"]   # Play shows up to 8


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    for i, name in enumerate(ORDER, 1):
        shot = Image.open(SRC / f"{name}.png").convert("RGB")
        w, h = shot.size
        target_w = max(w, (h + 1) // 2)
        canvas = Image.new("RGB", (target_w, h), shot.getpixel((2, h // 2)))
        canvas.paste(shot, ((target_w - w) // 2, 0))
        path = OUT / f"{i:02d}-{name}.png"
        canvas.save(path, optimize=True)
        print(path.name, canvas.size)


if __name__ == "__main__":
    main()
