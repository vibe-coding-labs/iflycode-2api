"""In-memory session activity tracker.

Tracks active Claude Code / OpenAI sessions per account user_id.
A session is "active" if it has been seen within the TTL window.

Reference: JoyCodeProxy pkg/proxy/sessions.go

Usage:
    from iflycode_proxy.sessions import record_session, get_active_sessions

    # On each API request
    record_session("user-abc", "session-xyz")

    # Returns count of active sessions for user
    count = get_active_sessions("user-abc")

    # Health check
    stats = session_stats()
"""

from __future__ import annotations

import threading
import time

_SESSION_TTL = 60.0  # seconds before a session goes idle
_CLEANUP_INTERVAL = 30.0  # seconds between cleanup passes

# user_id -> session_id -> last_seen_time
_sessions: dict[str, dict[str, float]] = {}
_lock = threading.Lock()
_last_cleanup = time.time()


def record_session(user_id: str, session_id: str):
    """Record or refresh a session activity timestamp."""
    if not user_id or not session_id:
        return
    _lazy_cleanup()
    with _lock:
        bucket = _sessions.get(user_id)
        if bucket is None:
            bucket = {}
            _sessions[user_id] = bucket
        bucket[session_id] = time.time()


def get_active_sessions(user_id: str) -> int:
    """Return the number of distinct active sessions for a user.

    Sessions older than _SESSION_TTL are considered inactive.
    """
    _lazy_cleanup()
    with _lock:
        bucket = _sessions.get(user_id)
        if not bucket:
            return 0
        now = time.time()
        count = 0
        for sid, last_seen in list(bucket.items()):
            if now - last_seen < _SESSION_TTL:
                count += 1
            else:
                del bucket[sid]
        return count


def session_stats() -> dict:
    """Return summary stats about tracked sessions.

    Returns: {
        "total_users": int,
        "total_sessions": int,
        "active_sessions": int,
    }
    """
    _lazy_cleanup()
    with _lock:
        now = time.time()
        users = len(_sessions)
        total = sum(len(b) for b in _sessions.values())
        active = sum(
            1 for bucket in _sessions.values()
            for last_seen in bucket.values()
            if now - last_seen < _SESSION_TTL
        )
        return {
            "total_users": users,
            "total_sessions": total,
            "active_sessions": active,
        }


def get_all_active_counts() -> dict[str, int]:
    """Return dict of user_id -> active_session_count."""
    _lazy_cleanup()
    with _lock:
        now = time.time()
        result = {}
        for uid, bucket in _sessions.items():
            count = 0
            for last_seen in list(bucket.values()):
                if now - last_seen < _SESSION_TTL:
                    count += 1
            if count > 0:
                result[uid] = count
        return result


def _lazy_cleanup():
    """Periodic cleanup of expired sessions (runs inline, called on access)."""
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    with _lock:
        cutoff = now - _SESSION_TTL
        expired_users = []
        for uid, bucket in _sessions.items():
            expired_sids = [sid for sid, ts in bucket.items() if ts < cutoff]
            for sid in expired_sids:
                del bucket[sid]
            if not bucket:
                expired_users.append(uid)
        for uid in expired_users:
            del _sessions[uid]