---
name: feishu-chat
version: 1.2.1
description: Bridge the current Claude Code session to Feishu/Lark so the user can chat with this session from their phone or Feishu desktop via DM to the lark-cli bot. The listener on `im.message.receive_v1` runs as a plugin monitor for the whole session; each incoming Feishu message arrives as a task notification and you reply via `lark-cli im +messages-reply`. Handles rich messages (post / image+text / quoted replies / files) by fetching the raw message with lark-cli, and stamps each reply with a context/model/effort footer. Invoke this skill whenever the user asks to "start the feishu bridge", "listen for feishu/lark messages", "chat with this session from my phone", "talk via feishu", "open the lark channel", or just runs `/feishu-chat`. Use it proactively if the user mentions wanting to control or message this session from outside the terminal via Feishu/Lark.
---

# Feishu Chat

Run a session-long Feishu listener. The user DMs the `lark-cli` bot from their phone/desktop; each message lands here as a notification from the listener task, and you reply via the CLI. Each reply appears in the same DM thread.

## Which lark-cli account

One machine can hold several lark-cli profiles — several apps/bots, even different tenants. The listener and every command in this skill must use the **same** one, or messages arrive on an app nobody is replying from.

The rule: if the session's working directory contains a `.feishu-chat` file, its content is the profile name (one token, e.g. `personal`). `bin/listen.sh` reads it and listens under that profile, and you pass `--profile <name>` on every lark-cli call. No file means the default profile and no flag. Every snippet below starts with a one-line prelude that derives `$P` from the file — keep that line in each command. A bare `$P` without the prelude expands to nothing and silently drops to the default profile, which is exactly the failure the file prevents.

To bind a directory to an account: `echo personal > .feishu-chat` in that directory, then start a new session there.

## Step 1 — Verify lark-cli is ready

Run a single status probe. If both identities (`bot` and `user`) are available, proceed. Otherwise, surface the install path and stop — don't try to auto-install without the user's go-ahead.

```bash
P=$(tr -d '[:space:]' < .feishu-chat 2>/dev/null); P=${P:+--profile $P}
echo "profile: ${P:-default}"
lark-cli auth status $P 2>/dev/null \
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

## Step 2 — Confirm the listener is running

You don't arm the listener yourself. This folder is also a Claude Code plugin (`.claude-plugin/plugin.json`), and its `monitors/monitors.json` makes Claude Code run `bin/listen.sh` as a **plugin monitor** the first time this skill is invoked. It runs in the session's working directory, which is how it finds `.feishu-chat`. A plugin monitor has no deadline — it lives until the session ends. That is the point: the Monitor tool caps every watch at 30 minutes and interrupts you to re-arm it; a plugin monitor does not.

Check it is up: a task described **"feishu message stream"** should be listed in `/tasks` (the harness may also have printed a notice that the monitor started). Its stdout lines reach you as notifications, one per incoming message, exactly as a Monitor's would.

If there is no such task, the plugin part didn't load. Plugin monitors run only in interactive CLI sessions, and only when the folder was discovered as a plugin — `claude plugin list` must show `feishu-chat@skills-dir`, which requires the `.claude-plugin/` manifest under `~/.claude/skills/feishu-chat/`. Tell the user rather than improvising. As a stopgap you can arm `~/.claude/skills/feishu-chat/bin/listen.sh` with the Monitor tool, but that watch expires after 30 minutes and you will be asked to re-arm it.

What `bin/listen.sh` runs, so you can reason about it:

```
lark-cli event consume im.message.receive_v1 --as bot --quiet --timeout 0 [--profile <name>] < <(tail -f /dev/null) 2>/dev/null | grep --line-buffered '"type":"im.message.receive_v1"'
```

- `--timeout 0` — lark-cli's own timeout disabled; otherwise the consumer exits after its default window and you miss messages.
- `< <(tail -f /dev/null)` — background tasks have no tty stdin; without this the CLI sees EOF on stdin and shuts down immediately. The script opens it once for itself (`exec 3< <(tail -f /dev/null)`) rather than as a pipeline stage, so that the script notices when the consumer dies: if lark-cli exits (unknown profile, auth gone, bus down) the script exits too, and you get a "script failed" notification instead of a listener that looks alive with nobody consuming.
- `[--profile <name>]` — present only when `.feishu-chat` names a profile; see "Which lark-cli account".
- `--quiet` — drops the `[event] ready`, `[source] feishu-websocket: connected` preamble that would otherwise spam notifications.
- `grep --line-buffered '"type":"im.message.receive_v1"'` — belt-and-suspenders filter so only message events reach the agent; `--line-buffered` is essential or pipe buffering delays events by minutes.

## Step 3 — Open the channel (send the user a "ready" DM)

Pull the user's `open_id` from the auth state and have the bot send the first message. This both confirms the bridge end-to-end and creates the P2P chat if one didn't exist.

```bash
P=$(tr -d '[:space:]' < .feishu-chat 2>/dev/null); P=${P:+--profile $P}
USER_OPEN_ID=$(lark-cli auth status $P | jq -r '.identities.user.openId')
lark-cli im +messages-send $P --as bot --user-id "$USER_OPEN_ID" \
  --text "Feishu bridge active in $(basename "$PWD"). Send any message and I'll reply here."
```

Tell the user the bridge is up and to look for the bot's DM in Feishu.

## Step 4 — Read each incoming message

Every listener notification is one NDJSON line. The envelope carries more than just text:

```
{"type":"im.message.receive_v1","event_id":"...","message_id":"om_...","chat_id":"oc_...",
 "sender_id":"ou_...","message_type":"post","content":"<pre-rendered text>",
 "reply_to":"om_...","root_id":"...","mentions":[{"id":"ou_...","key":"@_user_1","name":"..."}]}
```

`content` is **pre-rendered by lark-cli**, not raw Feishu JSON. A `post` (Feishu's rich-text type — "image + text", bold, and links all arrive as this) comes through as readable text with resource handles inline:

```
![Image](img_v3_0214j_ab2e0227-...)
运行以后有这个提示，但是命令行提示
OK: Profile "hab-alt" added
```

An `image` or `file` message instead renders as a tag:

```
<file key="file_v3_0014q_e1d4271c-..." name="report.pdf"/>
```

Both forms are verified against live messages. Don't pattern-match on one of them — to pull handles out of any shape, scan `content` for `(?:img|file)_[A-Za-z0-9_-]+`, which catches both.

So the text is usually already usable. What `content` does **not** contain: the bytes of any image or file, and the body of any quoted message. Fetch those yourself — see Step 5.

**Decide per message, from the envelope, not by guessing:**

| Envelope says | What it means | Do |
|---|---|---|
| `message_type == "text"`, no `reply_to` | plain message | reply directly, no fetch |
| `message_type` is `post` / `image` / `file` | rich text, image, or attachment | fetch resources if the content matters (5a) |
| `reply_to` is present | user quoted an earlier message | fetch the quoted message (5b) |
| `message_type` is anything else | `merge_forward`, `interactive`, `share_*`, … | fetch raw to see what it is (5c) |

**One user action can arrive as several messages.** Sending a picture with a caption often lands as a `text` event and a separate `file`/`image` event, back to back, rather than one `post`. If a bare attachment shows up right after a message that reads like it's about an attachment ("这张图是什么颜色？"), they're almost certainly the same thought — answer once, considering both, instead of replying twice and treating the image as contextless.

Treat the text as if the user typed it into Claude Code directly — same reasoning, same tool use, same safety rules. The bridge is a transport, not a privilege escalation.

## Step 5 — Fetch what the envelope doesn't carry

All three recipes use the **bot** identity, because the bot is the party that received the message, and the same profile as the listener (`$P` from `.feishu-chat`) — a different app's bot isn't in the conversation and gets nothing back.

### 5a — Images and files

The handles are in `content`. The prefix tells you which `--type` to pass — `img_*` → `image`, `file_*` → `file` — but it does **not** tell you what the content actually is: an image sent as an attachment gets a `file_*` key. Download one per handle:

```bash
P=$(tr -d '[:space:]' < .feishu-chat 2>/dev/null); P=${P:+--profile $P}
lark-cli im +messages-resources-download $P \
  --message-id om_xxx --file-key img_v3_xxx --type image \
  --output ./feishu-img --as bot
```

Then **read `data.saved_path` from the returned JSON and open that path** — lark-cli appends an extension based on the response's content type, so the file does not land where you asked. Verified: `--output ./probe-img` produced `probe-img.jpg`. Opening the path you passed in fails with a confusing "no such file".

Once you have the local path, view the image with the Read tool as you would any other image. That is what makes "image + a question about it" work — you see the picture, not a placeholder.

**Don't trust the extension to tell you what the file is.** An image sent as an attachment (rather than inline) arrives as `message_type: "file"`, and the download lands as `.bin` — verified: a PNG came back as `e2e-dl.bin`. Judge by content, not by suffix; `file <path>` will tell you. If it's an image, read it as one regardless of what it's called.

`--output` must be **cwd-relative**; absolute paths and `..` are rejected. `--type` must match the key's prefix: `image` for `img_*`, `file` for `file_*`.

### 5b — Quoted / replied-to messages

When `reply_to` is set, the user is pointing at an earlier message whose text is **not** in `content`. Their message is often meaningless without it ("这个是小号", "加了"). Fetch it:

```bash
P=$(tr -d '[:space:]' < .feishu-chat 2>/dev/null); P=${P:+--profile $P}
lark-cli im +messages-mget $P --message-ids om_xxx --no-reactions --as bot
```

Use the **`reply_to` value** as the id, not the incoming `message_id`. If the quoted message itself contains `img_*`/`file_*` handles, download them with `--message-id` set to the **quoted** message's id — resources hang off the message they were sent in.

### 5c — Anything unfamiliar

Same `mget` call, with the incoming `message_id`. It returns the full record — `msg_type`, `content`, `sender`, `mentions`, `reply_to` — which is enough to tell a `merge_forward` (a bundle of forwarded messages) from a `share_calendar_event` or an `interactive` card. Read it and respond to what's actually there.

If a type is genuinely not something you can act on, say so in the reply rather than silently ignoring the message — from the user's phone, silence and failure look identical.

## Step 6 — Reply, with a footer

Compute the footer, then send it as part of the reply:

```bash
P=$(tr -d '[:space:]' < .feishu-chat 2>/dev/null); P=${P:+--profile $P}
FOOTER=$(python3 ~/.claude/skills/feishu-chat/bin/footer.py 2>/dev/null)
lark-cli im +messages-reply $P --as bot \
  --message-id om_xxx \
  --markdown "$(cat <<'FEISHU_REPLY_EOF'
<your reply text>
FEISHU_REPLY_EOF
)$FOOTER"
```

The heredoc delimiter has to be something your reply text will never contain on a line by itself. Plain `EOF` is a real hazard here: if the reply happens to include a line reading `EOF`, the message is silently truncated there and the remainder is executed as shell commands — with exit status still `0`, so nothing looks wrong. Keep the long delimiter.

That path is where the standard install puts it (`~/.claude/skills/feishu-chat` symlinked at the repo). If you installed elsewhere, use your own path — and note `$CLAUDE_PLUGIN_ROOT` is **not** set for a symlinked skill, so don't reach for it.

The footer renders as a rule plus one line, matching what feishu-bridge shows:

```
────────────
🧠 148K · Opus 5 · xhigh
```

It reports context tokens used, the model, and the reasoning effort, so the user can see from their phone how full the context is and which model answered — the thing you cannot tell from a chat bubble.

Rules for the footer:

- **Append it to the last message you send for a turn**, not to every intermediate one — same as the terminal, where the strip appears once per turn.
- **If `footer.py` prints nothing, send the reply without it.** It stays silent whenever it cannot determine a trustworthy value. A footer is decoration; a *wrong* context number is worse than none, because the user will act on it.
- **Don't hand-write or estimate the numbers.** If the helper is silent, the honest output is no footer.

Prefer `--markdown` over `--text` for anything with structure — Feishu renders it. Use `--text` for short plain replies.

Use the **incoming `message_id`** (not `chat_id`) so the reply threads correctly. `+messages-reply` keeps the call-and-response visible in the Feishu UI; `+messages-send` creates a fresh top-level message and loses that connection.

The listener keeps streaming. Don't re-arm after each reply.

## Stopping

The user can ask "stop the feishu listener" — call `TaskStop` on the "feishu message stream" task. Otherwise it runs until the session ends: a plugin monitor is tied to the session and exits with it. If it exits early you are told: the harness posts a task notification that the "feishu message stream" script failed, with its exit code. Neither re-invoking `/feishu-chat` nor `/reload-plugins` restarts an exited plugin monitor; the way back is a new session, with the Monitor-tool stopgap from Step 2 in the meantime.

## Things to watch for

- **Fetch on demand, not reflexively.** A `post` whose text is self-contained needs no download. Fetch when the content actually bears on the answer — an image the user is asking about, a quote you can't interpret without.
- **Multiple sessions on the same lark-cli profile share the same bot identity.** If two sessions both run this skill at once under the same profile, both receive every message AND both reply — the user sees two bot messages. Coordinate via `/inter-session` if you intentionally run multiple bridges.
- **Replies are not echoed back through the listener** — Feishu filters self-messages, so you won't feedback-loop on your own replies.
- **The listener's stdout is the only event channel.** Errors on stderr (websocket disconnects, etc.) don't trigger notifications. If a long stretch goes quiet, ask the user to send a test ping; if nothing arrives, check `/tasks` for whether the listener task is still running and `lark-cli event status` for daemon health.
- **The context number can lag by about one turn.** It is read from the transcript, which Claude Code writes asynchronously. It's a gauge, not an invoice.
