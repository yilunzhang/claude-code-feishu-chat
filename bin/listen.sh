#!/usr/bin/env bash
# feishu-chat listener. Claude Code runs this as a plugin monitor
# (monitors/monitors.json) the first time /feishu-chat is invoked, and keeps it
# for the lifetime of the session. Every stdout line reaches the agent as a
# notification, so this prints exactly one NDJSON line per incoming message.
#
# --timeout 0        disable lark-cli's own consume window
# --quiet            drop the "[event] ready" / "[source] connected" preamble
# tail -f /dev/null  hold stdin open: a background process has no tty, and
#                    lark-cli exits as soon as it sees EOF on stdin
# grep --line-buffered
#                    keep message events only, and stop pipe buffering from
#                    delaying them by minutes

cleanup() { pkill -P $$ 2>/dev/null; }
trap 'cleanup; exit 143' TERM INT HUP
trap cleanup EXIT

tail -f /dev/null \
  | lark-cli event consume im.message.receive_v1 --as bot --quiet --timeout 0 2>/dev/null \
  | grep --line-buffered '"type":"im.message.receive_v1"' &
wait
