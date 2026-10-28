#!/usr/bin/env bash
# Records the screen while a user runs a campaign: the video Google Play asks for to justify FOREGROUND_SERVICE_SPECIAL_USE.
# Writes docs/play/fgs-demo-raw.mp4 and fgs-demo-events.txt (seconds into the video, event); captions are added afterwards
# by scripts/make_fgs_video.py.
set -euo pipefail
PKG=com.legacyai.emailstudio
ACT=com.travelessence.emailstudio.MainActivity
OUT=../docs/play
mkdir -p "$OUT"
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell pm clear $PKG > /dev/null
adb shell pm grant $PKG android.permission.POST_NOTIFICATIONS
adb shell settings put system show_touches 1
# A freshly booted emulator's launcher is slow: let it settle so no "isn't responding" dialog lands in the video.
adb shell input keyevent KEYCODE_HOME; sleep 20
python3 scripts/ui.py settle -; sleep 3; python3 scripts/ui.py settle -
adb shell am start -W -n $PKG/$ACT --es screen Dashboard --ez demo true --es theme light --ei interval 10 > /dev/null
sleep 6

ui() { python3 scripts/ui.py "$@"; }
adb shell screenrecord --bit-rate 8000000 --time-limit 180 /sdcard/fgs-demo.mp4 &
REC=$!
T0=$(date +%s.%N)
: > "$OUT/fgs-demo-events.txt"
mark() { echo "$(python3 -c "import time; print(f'{time.time() - $T0:.1f}')") $1" | tee -a "$OUT/fgs-demo-events.txt"; }

mark intro;        sleep 5
ui tap Compose --last;     mark compose;     sleep 5
ui tap Recipients --last;  mark recipients;  sleep 5
ui tap Automation --last;  mark automation;  sleep 3
ui tap "Start sending" --scroll 6; mark confirm; sleep 5
ui tap Start;      mark started;     sleep 14
adb shell input keyevent KEYCODE_HOME; mark background; sleep 6
adb shell cmd statusbar expand-notifications; mark notification; sleep 12
mark running       # the shade stays open: progress counts up, then the notification goes away
for _ in $(seq 1 60); do   # until the campaign ends and the service stops itself
  adb shell dumpsys activity services $PKG | grep -q CampaignService || break
  sleep 2
done
mark finished;     sleep 8
adb shell cmd statusbar collapse
adb shell am start -n $PKG/$ACT > /dev/null; mark reopened; sleep 6
mark end

adb shell pkill -INT screenrecord || true
wait $REC || true
sleep 2
adb pull /sdcard/fgs-demo.mp4 "$OUT/fgs-demo-raw.mp4"
adb shell settings put system show_touches 0
ls -la "$OUT"
