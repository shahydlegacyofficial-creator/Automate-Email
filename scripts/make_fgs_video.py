"""Builds the Google Play foreground-service demo video from the emulator recording.

Input:  docs/play/fgs-demo-raw.mp4 and docs/play/fgs-demo-events.txt (written by android/scripts/fgs_demo.sh)
Output: docs/play/fgs-demo.mp4 - 1920 x 1080, the phone recording on the left, an explanation of each step on the right,
        with an opening and a closing card. Needs ffmpeg and Pillow.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PLAY = ROOT / "docs" / "play"
FONTS = Path("/usr/share/fonts/opentype/inter")
W, H = 1920, 1080
PHONE_H = 960
PHONE_X, PHONE_Y = 190, 60
TEXT_X = 760
BG_TOP, BG_BOTTOM = (8, 54, 66), (10, 30, 44)
ACCENT = (64, 214, 214)
INTRO, OUTRO = 12, 14

CAPTIONS = {
    "intro": ("Legacy AI Email Studio", "The app is open on its dashboard: six recipients and one email ready to go."),
    "compose": ("1 · The user writes the email", "One email for everyone. Fields like {first_name} are filled in for each recipient."),
    "recipients": ("2 · The user chooses the recipients", "Six recipients in this demo."),
    "automation": ("3 · The user reviews the campaign", "Including the wait between emails: 10 seconds in this demo, 60 seconds by default."),
    "confirm": ("4 · The user starts the campaign", "The user taps Start sending and confirms. This tap is what starts the foreground service."),
    "started": ("5 · One email at a time", "The app sends to one recipient, waits the chosen interval, then sends to the next, with live progress."),
    "background": ("6 · The user leaves the app", "Back on the home screen. The foreground service keeps the campaign's schedule running."),
    "notification": ("7 · Always visible to the user", "While it runs, the service shows an ongoing notification with live progress and Pause and Stop buttons, so the user can pause or stop at any time."),
    "running": ("8 · Still sending in the background", "The remaining emails go out one at a time while the app is not on screen. Watch the count go up."),
    "finished": ("9 · The service stops itself", "After the last email the service stops and removes its notification. Only a short \"Campaign complete\" notice is left."),
    "reopened": ("Back in the app", "The campaign summary: every recipient was sent their own email."),
}

INTRO_TEXT = (
    "Foreground service: FOREGROUND_SERVICE_SPECIAL_USE",
    [
        "Legacy AI Email Studio sends an email campaign the user starts: the same email to each recipient, one recipient "
        "at a time, waiting a fixed interval the user chooses between emails (60 seconds by default).",
        "A campaign can last several hours. The foreground service keeps that schedule running while the app is in the "
        "background or the screen is off, and shows its progress in a notification.",
        "This recording uses the app's Simulation mode, so no real email is sent, and a 10-second interval to keep the video short.",
    ],
)
OUTRO_TEXT = (
    "Summary",
    [
        "Starts only when the user taps Start sending (or approves a campaign their AI agent asked to start).",
        "Shows an ongoing notification with progress, Pause and Stop for the whole campaign.",
        "Ends by itself when the last email is sent, or when the user stops it.",
        "Why special use: no other type fits. dataSync is limited to 6 hours a day and is for transferring data, and the "
        "work cannot be deferred to WorkManager because the user-chosen interval between emails is part of the task.",
    ],
)


def font(weight, size):
    return ImageFont.truetype(str(FONTS / f"Inter-{weight}.otf"), size)


def wrap(draw, text, fnt, width):
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=fnt) <= width:
            line = test
        else:
            lines.append(line)
            line = word
    return lines + [line] if line else lines


def background():
    img = Image.new("RGB", (W, H))
    top, bottom = BG_TOP, BG_BOTTOM
    for y in range(H):
        t = y / (H - 1)
        ImageDraw.Draw(img).line([(0, y), (W, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return img


def phone_slot(img, phone_w):
    d = ImageDraw.Draw(img)
    pad = 14
    d.rounded_rectangle([PHONE_X - pad, PHONE_Y - pad, PHONE_X + phone_w + pad, PHONE_Y + PHONE_H + pad],
                        radius=40, fill=(4, 12, 18), outline=(60, 90, 100), width=2)


def caption_frame(title, body, step_hint, phone_w):
    img = background()
    phone_slot(img, phone_w)
    d = ImageDraw.Draw(img)
    width = W - TEXT_X - 120
    d.text((TEXT_X, 140), "FOREGROUND SERVICE DEMO", font=font("SemiBold", 26), fill=ACCENT)
    y = 210
    for line in wrap(d, title, font("Bold", 64), width):
        d.text((TEXT_X, y), line, font=font("Bold", 64), fill="white")
        y += 80
    y += 30
    for line in wrap(d, body, font("Regular", 40), width):
        d.text((TEXT_X, y), line, font=font("Regular", 40), fill=(214, 230, 234))
        y += 56
    d.text((TEXT_X, H - 120), step_hint, font=font("Regular", 26), fill=(130, 165, 175))
    return img


def card(heading, paragraphs):
    img = background()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([120, 110, 196, 186], radius=18, fill=ACCENT)
    d.polygon([(138, 150), (182, 128), (166, 172), (156, 156)], fill=BG_BOTTOM)
    d.text((220, 112), "Legacy AI Email Studio", font=font("Bold", 52), fill="white")
    d.text((220, 176), "Google Play · foreground service declaration", font=font("Regular", 28), fill=ACCENT)
    y = 290
    for line in wrap(d, heading, font("Bold", 48), W - 240):
        d.text((120, y), line, font=font("Bold", 48), fill="white")
        y += 64
    y += 24
    for para in paragraphs:
        lines = wrap(d, para, font("Regular", 36), W - 300)
        d.ellipse([124, y + 16, 138, y + 30], fill=ACCENT)
        for line in lines:
            d.text((160, y), line, font=font("Regular", 36), fill=(214, 230, 234))
            y += 50
        y += 22
    return img


def probe(path, entry):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", entry,
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True).stdout
    return out.split()


def main():
    global PLAY
    if len(sys.argv) > 1:
        PLAY = Path(sys.argv[1])
    raw = PLAY / "fgs-demo-raw.mp4"
    events = [(float(t), name) for t, name in (l.split() for l in (PLAY / "fgs-demo-events.txt").read_text().split("\n") if l.strip())]
    vw, vh = map(int, probe(raw, "stream=width,height"))
    phone_w = round(vw * PHONE_H / vh / 2) * 2
    end = next(t for t, n in events if n == "end")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        slides = [(card(*INTRO_TEXT), INTRO)]
        captioned = [(t, n) for t, n in events if n in CAPTIONS]
        steps = len(captioned)
        for i, (t, name) in enumerate(captioned):
            nxt = captioned[i + 1][0] if i + 1 < steps else end
            hint = "Recorded on an Android emulator · the white dots show the user's taps"
            slides.append((caption_frame(*CAPTIONS[name], hint, phone_w), max(nxt - t, 0.5)))
        lead = captioned[0][0]   # the recording before the first caption is shown with the first caption too
        slides[1] = (slides[1][0], slides[1][1] + lead)
        slides.append((card(*OUTRO_TEXT), OUTRO))

        listing = []
        for i, (img, dur) in enumerate(slides):
            p = tmp / f"s{i:02d}.png"
            img.save(p)
            listing += [f"file '{p}'", f"duration {dur:.2f}"]
        listing.append(f"file '{tmp / f's{len(slides) - 1:02d}.png'}'")   # concat demuxer needs the last file twice
        (tmp / "slides.txt").write_text("\n".join(listing) + "\n")

        out = PLAY / "fgs-demo.mp4"
        total = INTRO + end + OUTRO
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "concat", "-safe", "0", "-i", str(tmp / "slides.txt"),
            "-i", str(raw),
            "-filter_complex",
            f"[0:v]fps=30,format=yuv420p[bg];"
            f"[1:v]fps=30,scale={phone_w}:{PHONE_H},setsar=1,trim=0:{end:.2f},setpts=PTS-STARTPTS+{INTRO}/TB[ph];"
            f"[bg][ph]overlay={PHONE_X}:{PHONE_Y}:eof_action=pass:enable='between(t,{INTRO},{INTRO + end:.2f})'[v]",
            "-map", "[v]", "-t", f"{total:.2f}",
            "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(out),
        ]
        subprocess.run(cmd, check=True)
        print(out, f"{total:.0f} s")


if __name__ == "__main__":
    sys.exit(main())
