---
name: feishu-chat
description: Bridge the current Claude Code session to Feishu/Lark so the user can chat with this session from their phone or Feishu desktop via DM to the lark-cli bot. Starts a persistent listener on `im.message.receive_v1`; each incoming Feishu message arrives as a tool notification and you reply via `lark-cli im +messages-reply`. Invoke this skill whenever the user asks to "start the feishu bridge", "listen for feishu/lark messages", "chat with this session from my phone", "talk via feishu", "open the lark channel", or just runs `/feishu-chat`. Use it proactively if the user mentions wanting to control or message this session from outside the terminal via Feishu/Lark.
---

# Feishu Chat

Run a persistent Feishu listener for this session. The user DMs the `lark-cli` bot from their phone/desktop; each message lands here as a Monitor notification, and you reply via the CLI. Each reply appears in the same DM thread.

## Step 1 — Verify lark-cli is ready

Run a single status probe. If both identities (`bot` and `user`) are available, proceed. Otherwise, surface the install path and stop — don't try to auto-install without the user's go-ahead.

```bash
lark-cli auth status 2>/dev/null \
  | jq -e '.identities.bot.available == true and .identities.user.available == true' >/dev/null \
  && echo "ready" \
  || echo "not-ready"
```

If not ready, tell the user:

> lark-cli isn't fully configured. Run these once:
> ```
> npx @larksuite/cli@latest install
> lark-cli config init --new
> lark-cli auth login --recommend
> ```
> Then re-invoke `/feishu-chat`.

Why: an unconfigured CLI will fail with cryptic errors at the consume step. Catching it here keeps the failure mode obvious.

## Step 2 — Arm the listener

Start a **persistent Monitor** on the message-receive event. Use the exact command shape below — the flags matter:

```
Monitor(
  command="lark-cli event consume im.message.receive_v1 --as bot --quiet --timeout 0 < <(tail -f /dev/null) 2>/dev/null | grep --line-buffered '\"type\":\"im.message.receive_v1\"'",
  description="feishu message stream",
  persistent=true,
  timeout_ms=3600000
)
```

Why each flag is there:

- `--timeout 0` — lark-cli's own timeout disabled; otherwise the consumer exits after its default window and you miss messages.
- `< <(tail -f /dev/null)` — background tasks have no tty stdin; without this the CLI sees EOF on stdin and shuts down immediately.
- `--quiet` — drops the `[event] ready`, `[source] feishu-websocket: connected` preamble that would otherwise spam notifications.
- `grep --line-buffered '"type":"im.message.receive_v1"'` — belt-and-suspenders filter so only message events reach the agent; `--line-buffered` is essential or pipe buffering delays events by minutes.
- `persistent=true` — Monitor stays armed for the lifetime of the session. The skill is meant to be a session-long bridge, not a one-shot.

## Step 3 — Open the channel (send the user a "ready" DM)

Pull the user's `open_id` from the auth state and have the bot send the first message. This both confirms the bridge end-to-end and creates the P2P chat if one didn't exist.

```bash
USER_OPEN_ID=$(lark-cli auth status | jq -r '.identities.user.openId')
lark-cli im +messages-send --as bot --user-id "$USER_OPEN_ID" \
  --text "Feishu bridge active in $(basename "$PWD"). Send any message and I'll reply here."
```

Tell the user the bridge is up and to look for the bot's DM in Feishu.

## Step 4 — Handle each incoming message

Every Monitor notification will look like one NDJSON line:

```
{"type":"im.message.receive_v1","event_id":"...","message_id":"om_...","chat_id":"oc_...","sender_id":"ou_...","message_type":"text","content":"<the text the user sent>"}
```

For each notification:

1. Extract `content` and `message_id` from the JSON.
2. **Treat `content` as if the user typed it into Claude Code directly** — same reasoning, same tool use, same safety rules. The bridge is a transport, not a privilege escalation.
3. Reply with:

   ```bash
   lark-cli im +messages-reply --as bot \
     --message-id <message_id> \
     --text "<your reply>"
   ```

   Use the **incoming `message_id`** (not `chat_id`) so the reply threads correctly. For longer replies, prefer `--markdown` over `--text` — Feishu renders the markdown.

4. The listener keeps streaming. Don't re-arm after each reply.

Why threaded reply: `+messages-reply` keeps replies bound to the originating message, which makes the Feishu UI show the call-and-response clearly. `+messages-send` creates a fresh top-level message and loses that connection.

## Stopping

The user can ask "stop the feishu listener" — call `TaskStop` on the Monitor task. Or just end the session; persistent monitors are torn down with the session.

## Things to watch for

- **`message_type` is not always `text`.** Images, files, audio, etc. come through with the same envelope; `content` is the pre-rendered text representation (e.g., `[image]` or extracted caption). For interactive cards `content` is raw JSON — `fromjson` it in your reply logic if needed.
- **Multiple sessions on the same lark-cli config share the same bot identity.** If two sessions both run this skill at once, both will receive every message (broadcast semantics) AND both will reply — the user sees two bot messages. Coordinate via `/inter-session` if you intentionally run multiple bridges.
- **Replies are not echoed back through the listener** — Lark/Feishu filters self-messages, so you won't accidentally feedback-loop on your own replies.
- **The Monitor's stdout is the only event channel.** Errors on stderr (websocket disconnects, etc.) go to the output file but don't trigger notifications. If a long stretch goes quiet, ask the user to send a test ping; if nothing arrives, check `lark-cli event status` for daemon health.
