#!/usr/bin/env python3
"""Stop-hook guard for the follow-up queue.

Sessions that surface adjacent work tend to mention it once, in the final
summary, and then end. This refuses that ending: if the session's own prose
says it deferred something, and nothing was written to ``.kiro/queue/``, the
Stop is blocked once with an instruction to record it.

Fires at most once per session — ``stop_hook_active`` plus a per-session
sentinel — so the worst case for a false positive is one extra turn in which
the model says there was nothing to queue.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from pathlib import Path

# Phrases that mean "this session found work it is not doing". Matched against
# assistant prose only (never thinking blocks, tool inputs, or file contents),
# so ordinary occurrences of these words inside the repo's docs don't trip it.
DEFERRAL_SIGNALS = re.compile(
    r"""
      follow[-\s]?up
    | follow[-\s]?on
    | out\s+of\s+scope
    | (?:outside|beyond)\s+(?:the\s+)?scope
    | (?:separate|fresh|another|future|next|new)\s+session
    | handled?\s+separately
    | tracked?\s+separately
    | address(?:ed)?\s+separately
    | (?:worth|should)\s+revisit
    | revisit\s+later
    | left\s+(?:un)?(?:addressed|fixed|done)
    | not\s+addressed\s+here
    | for\s+a\s+later\s+pass
    | in\s+a\s+later\s+pass
    | deferred?\s+(?:to|for|until)
    | known\s+limitation
    | pre[-\s]?existing\s+(?:issue|problem|bug)
    | someone\s+should
    | we\s+should\s+(?:also|later|eventually)
    """,
    re.IGNORECASE | re.VERBOSE,
)

BLOCK_REASON = (
    "This session's summary defers work to a later session, but nothing was "
    "written to .kiro/queue/.\n\n"
    "Follow-up surfaced mid-session must be recorded before the session ends "
    "— see the Follow-up Queue rule in CLAUDE.md. Do one of these, then "
    "finish:\n"
    "  1. Run the kiro-queue-add skill to record each deferred item with "
    "verifiable evidence, a resume command, and live context paths.\n"
    "  2. If the deferral phrasing was incidental and there is genuinely no "
    "adjacent work to record, say so explicitly in one line and stop.\n\n"
    "Do not queue: work already tracked in .kiro/steering/roadmap.md or a "
    "spec's tasks.md, and anything only meaningful inside this conversation."
)


def assistant_prose(transcript: Path) -> str:
    """Concatenate assistant text blocks; skip thinking, tools, and results."""
    chunks: list[str] = []
    try:
        with transcript.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                content = entry.get("message", {}).get("content")
                if isinstance(content, str):
                    chunks.append(content)
                elif isinstance(content, list):
                    chunks.extend(
                        block.get("text", "")
                        for block in content
                        if isinstance(block, dict) and block.get("type") == "text"
                    )
    except OSError:
        return ""
    return "\n".join(chunks)


def wrote_to_queue(transcript: Path) -> bool:
    """True if any tool call in this session targeted a .kiro/queue/ item."""
    try:
        raw = transcript.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    for match in re.finditer(r"\.kiro/queue/([^\"'\s\\]*)", raw):
        target = match.group(1)
        # The contract file itself doesn't count as recording an item.
        if target and not target.startswith("README"):
            return True
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    # Already continuing because of a stop hook — never chain.
    if payload.get("stop_hook_active"):
        return 0

    session_id = str(payload.get("session_id", ""))
    sentinel = Path(os.environ.get("TMPDIR", "/tmp")) / f"queue-guard-{session_id}"
    if session_id and sentinel.exists():
        return 0

    transcript = Path(payload.get("transcript_path", ""))
    if not transcript.is_file():
        return 0

    root = Path(payload.get("cwd") or Path(__file__).resolve().parents[2])
    if not (root / ".kiro" / "queue").is_dir():
        return 0

    if not DEFERRAL_SIGNALS.search(assistant_prose(transcript)):
        return 0
    if wrote_to_queue(transcript):
        return 0

    if session_id:
        with contextlib.suppress(OSError):
            sentinel.touch()

    json.dump({"decision": "block", "reason": BLOCK_REASON}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
