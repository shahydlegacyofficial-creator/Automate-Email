"""Tiny UI driver for the emulator (uiautomator): tap an element by its text, scrolling down until it is visible.

    python3 ui.py tap "Start sending" [--last] [--scroll 6]
    python3 ui.py has "Campaign complete"        exit code 0 when the text is on screen
"""

import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


def adb(*args):
    return subprocess.run(["adb", *args], capture_output=True, text=True).stdout


def nodes():
    for _ in range(5):
        adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
        xml = adb("exec-out", "cat", "/sdcard/ui.xml")
        if "<hierarchy" in xml:
            return ET.fromstring(xml[xml.index("<hierarchy"):]).iter("node")
        time.sleep(1)
    sys.exit("could not read the screen")


def find(text, last):
    wanted = text.casefold()
    height = int(re.search(r"(\d+)x(\d+)", adb("shell", "wm", "size").splitlines()[-1]).group(2))
    hits = []
    for n in nodes():
        if wanted in (n.get("text", "").casefold(), n.get("content-desc", "").casefold()):
            x1, y1, x2, y2 = map(int, re.findall(r"\d+", n.get("bounds")))
            if y2 > y1 and y2 < height - 150:       # fully visible above the navigation bar
                hits.append(((x1 + x2) // 2, (y1 + y2) // 2))
    return (hits[-1] if last else hits[0]) if hits else None


def main():
    cmd, text, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
    last = "--last" in rest
    scrolls = int(rest[rest.index("--scroll") + 1]) if "--scroll" in rest else 0
    for attempt in range(scrolls + 1):
        hit = find(text, last)
        if hit:
            if cmd == "tap":
                adb("shell", "input", "tap", str(hit[0]), str(hit[1]))
            print(f"{cmd} {text!r}: found at {hit}")
            return
        if attempt < scrolls:
            adb("shell", "input", "swipe", "540", "1700", "540", "1000", "600")
            time.sleep(1)
    print(f"{cmd} {text!r}: not found")
    sys.exit(1)


if __name__ == "__main__":
    main()
