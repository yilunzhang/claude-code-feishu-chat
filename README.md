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

## Notes

- **Non-text messages** (images, files, cards) arrive through the same channel; `content`
  is a pre-rendered text representation (e.g. `[image]`, an extracted caption, or raw card
  JSON).
- **Multiple sessions sharing one lark-cli config share the bot identity.** If two sessions
  run the bridge at once, both receive *and* reply to every message — you'll see duplicate
  bot replies.
- **Your own replies aren't echoed back.** Feishu filters self-messages, so there's no
  feedback loop.

See [`SKILL.md`](./SKILL.md) for the full instructions Claude Code follows.
