# feishu-chat

A [Claude Code](https://claude.com/claude-code) skill that bridges a running Claude Code
session to **Feishu/Lark**, so you can talk to the session from your phone or the Feishu
desktop app by DMing a bot — no terminal required.

## How it works

```
You (Feishu DM)  ──►  lark-cli bot  ──►  Claude Code session  ──►  reply in the same DM thread
```

When you run `/feishu-chat`, the session:

1. Verifies `lark-cli` is configured (both the **bot** and **user** identities are available).
2. Starts a persistent listener on Feishu's `im.message.receive_v1` event.
3. Sends you a "bridge active" DM from the bot to confirm the channel end-to-end.

From then on, every message you DM the bot lands in the session as if you'd typed it into
Claude Code directly, and the reply comes back threaded in the same DM. Incoming messages
are treated as normal user input — same reasoning, same tools, same safety rules. The
bridge is a transport, not a privilege escalation.

## Prerequisites

- [Claude Code](https://claude.com/claude-code)
- `lark-cli`, configured with a bot and your user identity:

  ```bash
  npx @larksuite/cli@latest install
  lark-cli config init --new
  lark-cli auth login --recommend
  ```

## Install

Clone the repo and symlink it into your Claude Code skills directory:

```bash
git clone git@github.com:yilunzhang/claude-code-feishu-chat.git
ln -s "$(pwd)/claude-code-feishu-chat" ~/.claude/skills/feishu-chat
```

Claude Code loads the skill from `~/.claude/skills/feishu-chat/SKILL.md` (resolved through
the symlink), so the repo can live anywhere you like.

## Usage

In any Claude Code session:

```
/feishu-chat
```

Then open Feishu, find the bot's DM, and start chatting. To stop, tell the session
"stop the feishu listener" — or just end the session, since the listener is torn down
with it.

## Rich messages

Feishu messages are not just text, and the bridge handles the common shapes:

| You send | What happens |
|---|---|
| Plain text | delivered as-is |
| **Image + text** | the session downloads the image and actually looks at it — whether it arrives as one rich `post` or as a caption plus a separate attachment |
| A **quoted reply** | the session fetches the message you quoted, so "this one" and "加了" still make sense |
| **Files** | downloaded on demand and read |
| Forwards, cards, shared events | fetched raw so the session can see what they are |

The pre-rendered text arrives in the event itself; anything heavier (image bytes, the body
of a quoted message) is fetched on demand with `lark-cli`, so the common text-only case
costs no extra round trip.

## Reply footer

Every reply ends with the same strip Claude Code shows in the terminal:

```
────────────
🧠 148K · Opus 5 · xhigh
```

Context tokens used, model, reasoning effort — so from your phone you can see how full the
context is and which model answered. It's computed by [`bin/footer.py`](./bin/footer.py)
from the session transcript. If it can't determine a trustworthy value it prints nothing
and the reply goes out without a footer: a wrong context number is worse than no number.
The count can lag by about a turn, since Claude Code writes the transcript asynchronously.

## Notes

- **Multiple sessions sharing one lark-cli config share the bot identity.** If two sessions
  run the bridge at once, both receive *and* reply to every message — you'll see duplicate
  bot replies.
- **Your own replies aren't echoed back.** Feishu filters self-messages, so there's no
  feedback loop.

See [`SKILL.md`](./SKILL.md) for the full instructions Claude Code follows.
