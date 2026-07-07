"""Context window truncation for long conversations.

Prevents context window exceeded errors by proactively truncating
early messages when estimated tokens exceed the threshold.

Reference: JoyCodeProxy pkg/anthropic/truncate.go
"""

import json
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("iflycode-2api.truncate")

# Upstream model context window size estimate
CONTEXT_WINDOW_SIZE = 196608
# Safety margin: start truncation at 85% of context window
PREEMPTIVE_THRESHOLD_RATIO = 0.85
# Rough approximation: 1 token ≈ 3.5 bytes for mixed Chinese/English
BYTES_PER_TOKEN = 3.5
# Maximum truncation rounds
MAX_TRUNCATION_ROUNDS = 5


def estimate_tokens(messages: List[Dict[str, Any]]) -> int:
    """Rough token count estimate for messages list."""
    total_bytes = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total_bytes += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total_bytes += len(block.get("text", ""))
    if total_bytes == 0:
        return 0
    return int(total_bytes / BYTES_PER_TOKEN)


def truncate_messages(messages: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Truncate early messages when conversation is too long.

    Keeps the first message + a truncation notice + the last portion.
    Removes ~40% of messages each round.
    """
    n = len(messages)
    if n <= 4:
        return None

    keep_first = 1
    keep_last = int(n * 0.6)
    if keep_last < 4:
        keep_last = 4
    cut_end = n - keep_last
    if cut_end <= keep_first:
        keep_last = 2
        cut_end = n - keep_last
        if cut_end <= keep_first:
            return None

    # Ensure cut_end lands on a user message (even index for user/assistant pairs)
    if cut_end % 2 != 0:
        cut_end += 1
    if cut_end >= n:
        return None

    removed = cut_end - keep_first
    notice = "[System: Earlier conversation messages have been auto-truncated to fit within the model's context window. Some earlier context is now missing. Continue with the remaining conversation.]"

    truncated = list(messages[:keep_first])
    truncated.append({"role": "assistant", "content": notice})
    truncated.extend(messages[cut_end:])

    log.warning("auto-truncated messages for context limit",
                extra={"original_count": n, "truncated_count": len(truncated), "removed": removed})

    return truncated


def preemptive_truncate(messages: List[Dict[str, Any]]) -> int:
    """Check if messages exceed context limit and proactively truncate.

    Returns number of truncation rounds performed, or -1 if failed.
    """
    window = float(CONTEXT_WINDOW_SIZE)
    threshold = int(window * PREEMPTIVE_THRESHOLD_RATIO)

    rounds = 0
    current = messages
    while rounds < MAX_TRUNCATION_ROUNDS:
        estimated = estimate_tokens(current)
        if estimated <= threshold:
            if rounds > 0:
                log.info("preemptive truncation complete",
                         extra={"rounds": rounds, "estimated_tokens": estimated, "threshold": threshold})
            return rounds

        truncated = truncate_messages(current)
        if truncated is None:
            log.warning("preemptive truncation: cannot truncate further",
                        extra={"estimated_tokens": estimated, "threshold": threshold, "rounds": rounds})
            return -1
        current = truncated
        rounds += 1

    if estimate_tokens(current) > threshold:
        log.warning("preemptive truncation exhausted rounds without reaching threshold")
        return -1
    return rounds