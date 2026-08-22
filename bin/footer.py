#!/usr/bin/env python3
"""Print the per-reply footer: "─────── / 🧠 <K> · <model> · <effort>".

Called by the feishu-chat skill just before it sends a reply, so the Feishu
message carries the same context/model/effort strip that feishu-bridge shows.

Contract: prints the footer (leading newline included) on stdout, or prints
NOTHING if it cannot be determined. Never fails, never prints a partial or
guessed value -- a footer is decoration, and a wrong number is worse than no
number. Exit status is always 0.

Inputs, both from the environment Claude Code exports into Bash:
  CLAUDE_CODE_SESSION_ID  -> locates the session transcript
  CLAUDE_EFFORT           -> reasoning effort, shown verbatim

Assumptions (single-user personal bridge; revisit if that changes):
  - The transcript is JSONL under ~/.claude/projects/<munged-cwd>/<session-id>.jsonl.
    We glob on the session id so we never have to model the cwd munging.
  - Token counts come from the newest `type == "assistant"` record. During a turn
    that record is the step that issued the last tool call, so the count is
    current rather than lagging a turn.
"""
import json
import os
import pathlib

SEP = "─" * 12          # 12x BOX DRAWINGS LIGHT HORIZONTAL (a literal rule, not markdown ---)
TAIL = 262144                # read at most 256KiB from the end; a single record stays well under that
MODEL_CAP = 32
EFFORT_CAP = 16
MAX_TOKENS = 100_000_000     # sanity ceiling (real windows are <=1M); above this, treat as garbage

NAMES = {
    "claude-opus-5": "Opus 5",
    "claude-opus-4-8": "Opus 4.8",
    "claude-sonnet-5": "Sonnet 5",
    "claude-fable-5": "Fable 5",
}


def pretty_model(mid):
    if not isinstance(mid, str) or not mid or mid == "<synthetic>":
        return None
    if mid in NAMES:
        return NAMES[mid]
    if mid.startswith("claude-haiku-4-5"):
        return "Haiku 4.5"
    if mid.startswith("claude-"):
        mid = mid[len("claude-"):]
    return mid[:MODEL_CAP]


def find_transcript():
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid or "/" in sid or sid in (".", ".."):
        return None
    # Glob by session id across every project dir -- no need to know how cwd is munged.
    # Deliberately NO most-recently-modified fallback: with several sessions running it
    # would silently attribute another session's context to this reply.
    hits = sorted(pathlib.Path(os.path.expanduser("~/.claude/projects")).glob("*/%s.jsonl" % sid))
    return str(hits[0]) if hits else None


def read_tail_lines(path):
    """Last <=TAIL bytes, split on b'\\n', each line decoded strictly.

    Strict decode (no errors="ignore"): a truncated multi-byte sequence or a
    corrupt byte drops the whole line. errors="ignore" would instead delete the
    bad byte and could "repair" 9\\xff9999 into a believable 99999.
    """
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - TAIL))
        raw = f.read(TAIL)
    out = []
    for bline in raw.split(b"\n"):
        try:
            out.append(bline.decode("utf-8"))
        except UnicodeDecodeError:
            continue
    return out


def read_turn_meter(path):
    """Newest assistant record -> {"tokens", "model"}, else None.

    The newest `type == "assistant"` record is authoritative: if it is present
    but unusable, return None rather than walking back to an older record. An
    older record's token count is stale, and pairing it with the current model
    and effort produces a footer that looks right and isn't.
    """
    for line in reversed(read_tail_lines(path)):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue                      # half-written or garbage line: not a record
        if not isinstance(o, dict) or o.get("type") != "assistant":
            continue                      # user/system/tool records: skip transparently
        m = o.get("message")
        if isinstance(m, dict) and m.get("model") == "<synthetic>":
            continue                      # synthetic markers carry usage but aren't real turns
        # --- from here this record is authoritative; unusable means None, not fallback ---
        if not isinstance(m, dict) or m.get("role") != "assistant":
            return None
        usage = m.get("usage")
        if not isinstance(usage, dict):
            return None
        tok = 0
        for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            v = usage.get(key)
            # bool is a subclass of int, so `"input_tokens": true` would otherwise add 1
            if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                tok += v
        tok = int(tok)
        return {"tokens": tok, "model": m.get("model")} if tok > 0 else None
    return None


def clean(s):
    """Drop characters that would break the footer's single-line layout or the argv
    it is passed in: C0 controls, DEL, NEL/LS/PS (str.splitlines() breaks on those
    too), and lone surrogates."""
    if not isinstance(s, str):
        return ""
    return "".join(c for c in s
                   if not (ord(c) < 0x20 or ord(c) == 0x7F
                           or ord(c) in (0x85, 0x2028, 0x2029)
                           or 0xD800 <= ord(c) <= 0xDFFF))


def format_footer(meter, effort=None):
    if not meter:
        return ""
    tok = meter.get("tokens")
    if not isinstance(tok, int) or tok <= 0 or tok > MAX_TOKENS:
        return ""
    segs = ["\U0001f9e0 %dK" % max(1, round(tok / 1000))]   # max(1,..) so we never print "0K"
    pm = pretty_model(meter.get("model"))
    if pm:
        pm = clean(pm)
        if pm:
            segs.append(pm)
    if isinstance(effort, str):
        eff = clean(effort)[:EFFORT_CAP]
        if eff:
            segs.append(eff)
    return "\n" + SEP + "\n" + " · ".join(segs)


def main():
    try:
        tp = find_transcript()
        if not tp:
            return ""
        return format_footer(read_turn_meter(tp), effort=os.environ.get("CLAUDE_EFFORT"))
    except Exception:
        return ""                         # fail open: no footer beats a wrong footer


if __name__ == "__main__":
    print(main(), end="")
