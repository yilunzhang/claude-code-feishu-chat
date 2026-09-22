#!/usr/bin/env bash
# feishu-chat listener. Claude Code runs this as a plugin monitor
# (monitors/monitors.json) the first time /feishu-chat is invoked, and keeps it
# for the lifetime of the session. Every stdout line reaches the agent as a
# notification, so this prints exactly one NDJSON line per incoming message.
#
# --timeout 0        disable lark-cli's own consume window
# --quiet            drop the "[event] ready" / "[source] connected" preamble
# exec 3< <(tail -f /dev/null)
#                    hold stdin open: a background process has no tty, and
#                    lark-cli exits as soon as it sees EOF on stdin
# grep --line-buffered
#                    keep message events only, and stop pipe buffering from
#                    delaying them by minutes

# Account selection: if the working directory holds a .feishu-chat file, its
# content is the lark-cli profile name to listen under; no file means the
# default profile. An unusable name is an error, not a silent fallback —
# listening on the wrong app is exactly the failure this file exists to prevent.
PROFILE_ARGS=()
if [ -f .feishu-chat ]; then
  PROFILE=$(sed -e '1!d' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' .feishu-chat)
  case "$PROFILE" in
    ''|*[!A-Za-z0-9._-]*)
      echo "feishu-chat: .feishu-chat must contain exactly one lark-cli profile name, got '$PROFILE'" >&2
      exit 2 ;;
  esac
  PROFILE_ARGS=(--profile "$PROFILE")
fi

# Collect every descendant first, then kill them in one go: the real lark-cli
# process sits under its node wrapper, so killing only direct children would
# orphan it and leave a consumer running with nobody reading it.
descendants() { local c; for c in $(pgrep -P "$1"); do printf '%s ' "$c"; descendants "$c"; done; }
cleanup() { local kids; kids=$(descendants $$); [ -n "$kids" ] && kill $kids 2>/dev/null; }
trap 'cleanup; exit 143' TERM INT HUP
trap cleanup EXIT

# The stdin holder is opened by this script itself (exec + process
# substitution), so tail is a direct child that cleanup can always reach. It is
# deliberately not a pipeline stage: bash 3.2's `wait` on a pipeline waits for
# every stage, and tail never ends.
exec 3< <(tail -f /dev/null)
lark-cli event consume im.message.receive_v1 --as bot --quiet --timeout 0 "${PROFILE_ARGS[@]}" \
  <&3 2>/dev/null \
  | grep --line-buffered '"type":"im.message.receive_v1"' &
# The job is lark-cli | grep; grep ends when lark-cli's stdout closes, so a
# consumer that dies (bad profile, auth gone, bus down) ends the script instead
# of leaving the monitor "running" with nobody listening.
wait $!
echo "feishu-chat: lark-cli consumer exited" >&2
exit 1
