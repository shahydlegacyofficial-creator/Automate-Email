"""Google Play screenshots from the emulator captures in docs/android-screenshots.

Phone: Play allows a long side of at most twice the short side; the 1080 x 2400 captures are 2.22:1. Instead of cropping
off the app's navigation bar, each capture gets narrow side margins in its own background colour: 1200 x 2400 (exactly 2:1).

Tablets and Chromebooks: Play wants exactly 16:9 or 9:16 with each side 1080-7680 px. The emulator captures them at those
sizes already (screenshots.sh), so they are only checked and copied.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "android-screenshots"
IMAGES = ROOT / "fastlane" / "metadata" / "android" / "en-US" / "images"
OUT = IMAGES / "phoneScreenshots"
ORDER = ["light-dashboard", "light-compose", "light-automation-running", "light-agents", "light-recipients",
         "dark-compose", "light-signature", "light-welcome"]   # Play shows up to 8
LARGE_ORDER = ["light-dashboard", "light-compose", "light-automation-running", "light-agents", "light-recipients",
               "dark-compose", "light-signature"]
LARGE = {"tablet-7in": "sevenInchScreenshots", "tablet-10in": "tenInchScreenshots",
         "chromebook": "chromebookScreenshots"}   # fastlane has no Chromebook folder; uploaded by hand


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
    for device, folder in LARGE.items():
        if not (SRC / device).is_dir():
            continue
        out = IMAGES / folder
        out.mkdir(exist_ok=True)
        for old in out.glob("*.png"):
            old.unlink()
        for i, name in enumerate(LARGE_ORDER, 1):
            shot = Image.open(SRC / device / f"{name}.png").convert("RGB")
            w, h = shot.size
            assert max(w, h) * 9 == min(w, h) * 16 and 1080 <= min(w, h) and max(w, h) <= 7680, (device, name, shot.size)
            path = out / f"{i:02d}-{name}.png"
            shot.save(path, optimize=True)
            print(f"{folder}/{path.name}", shot.size)


if __name__ == "__main__":
    main()
