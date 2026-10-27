#!/usr/bin/env bash
# Installs the debug build on the emulator and captures each screen in both themes.
set -euo pipefail
PKG=com.legacyai.emailstudio
ACT=com.travelessence.emailstudio.MainActivity
OUT=../docs/android-screenshots
mkdir -p "$OUT"
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell pm grant $PKG android.permission.POST_NOTIFICATIONS || true

shot() {   # file-name screen theme [extra args...]
  local name=$1 screen=$2 theme=$3; shift 3
  adb shell am start -W -n $PKG/$ACT --activity-clear-task --es screen "$screen" --ez demo true --es theme "$theme" "$@" > /dev/null
  sleep 5
  adb exec-out screencap -p > "$OUT/$name.png"
  echo "captured $name"
}

for theme in light dark; do
  shot "$theme-dashboard" Dashboard $theme
  shot "$theme-compose" Compose $theme
  shot "$theme-recipients" Recipients $theme
  shot "$theme-outlook" Outlook $theme
  shot "$theme-settings" Settings $theme
done
shot light-more More light
shot light-quicksend QuickSend light
shot light-history History light
shot light-signature Signature light
shot dark-signature Signature dark
shot light-agents Agents light --ez agents true
shot dark-agents Agents dark --ez agents true
shot light-welcome Dashboard light --ez welcome true

# End-to-end: a real MCP client talks to the phone's AI-agent server (through adb port forwarding).
shot light-agent-check Dashboard light --ez demo true --es agent_token ci-agent-token
adb forward tcp:18765 tcp:8765
python3 scripts/agent_check.py http://127.0.0.1:18765/mcp ci-agent-token 2>&1 | tee "$OUT/agent-check.txt"
grep -q "AGENT CHECK PASSED" "$OUT/agent-check.txt"

# Start a simulated campaign (10 s interval) and capture it mid-run.
shot light-automation-start Automation light --ez start_campaign true
sleep 14
adb exec-out screencap -p > "$OUT/light-automation-running.png"
adb shell cmd statusbar expand-notifications || true
sleep 2
adb exec-out screencap -p > "$OUT/notification.png"
adb shell cmd statusbar collapse || true
sleep 50
adb exec-out screencap -p > "$OUT/light-automation-done.png"
shot dark-automation Automation dark

# Large screens for the Play listing: the same emulator, resized. Sizes are exact 9:16 / 16:9, as Play requires.
large() {   # folder size density
  adb shell wm size "$2"; adb shell wm density "$3"
  adb shell pm clear $PKG > /dev/null   # fresh sample data, not what the tests above left behind
  adb shell pm grant $PKG android.permission.POST_NOTIFICATIONS || true
  sleep 4
  OUT=../docs/android-screenshots/$1; mkdir -p "$OUT"
  shot light-dashboard Dashboard light
  shot light-compose Compose light
  shot light-recipients Recipients light
  shot light-agents Agents light --ez agents true
  shot dark-compose Compose dark
  shot light-signature Signature light
  shot light-automation-start Automation light --ez start_campaign true
  sleep 14
  adb exec-out screencap -p > "$OUT/light-automation-running.png"
  sleep 50   # let the campaign finish before the next size
}
large tablet-7in 1080x1920 280
large tablet-10in 2560x1440 320
large chromebook 1920x1080 240
adb shell wm size reset; adb shell wm density reset
OUT=../docs/android-screenshots
file "$OUT"/*/*.png || true

adb logcat -d -s AndroidRuntime:E > "$OUT/crash-log.txt" || true
ls -la "$OUT"
