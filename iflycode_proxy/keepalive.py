"""Keepalive service — periodically validates and refreshes account credentials.

Reference: JoyCodeProxy pkg/keepalive/keepalive.go

Uses the iFlyCode /api/starspark/v1/chat/user/valid endpoint to verify token
validity. Failed accounts get a longer backoff interval (4x) to avoid hammering
the upstream.
"""

import logging
import threading
import time
from typing import Callable, Optional

log = logging.getLogger("iflycode-proxy.keepalive")

# Default schedule
_DEFAULT_CHECK_INTERVAL = 600  # 10 minutes between rounds
_DEFAULT_REFRESH_TTL = 3600  # 1 hour before re-checking a valid account


class KeepaliveService:
    """Background service that periodically validates stored account credentials."""

    def __init__(self, get_stale_fn: Callable, set_status_fn: Callable,
                 validate_fn: Callable[[str], bool],
                 check_interval: int = _DEFAULT_CHECK_INTERVAL,
                 refresh_ttl: int = _DEFAULT_REFRESH_TTL,
                 backoff_multiplier: int = 4):
        """
        Args:
            get_stale_fn: callable() -> list[dict] with account_id keys
            set_status_fn: callable(account_id, valid: bool, error: str)
            validate_fn: callable(account_id) -> bool
            check_interval: seconds between rounds
            refresh_ttl: seconds before re-checking a valid account
            backoff_multiplier: multiplier for failed account backoff
        """
        self._get_stale = get_stale_fn
        self._set_status = set_status_fn
        self._validate = validate_fn
        self._check_interval = check_interval
        self._refresh_ttl = refresh_ttl
        self._backoff_multiplier = backoff_multiplier
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # In-memory cache: account_id -> (valid, error, checked_at)
        self._cache: dict[str, tuple[Optional[bool], str, float]] = {}
        self._cache_lock = threading.Lock()

    # -- Public API --

    def start(self):
        """Start the background keepalive loop."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                         name="keepalive")
        self._thread.start()
        log.info("Keepalive started (interval=%ds, ttl=%ds, backoff=%dx)",
                  self._check_interval, self._refresh_ttl, self._backoff_multiplier)

    def stop(self):
        """Stop the keepalive loop."""
        self._running = False
        self._stop_event.set()
        log.info("Keepalive stopped")

    def get_cached_status(self, account_id: str) -> dict:
        """Get the cached credential status for an account.

        Returns dict with: valid (bool|None), error (str), age_seconds (float).
        """
        with self._cache_lock:
            entry = self._cache.get(account_id)
        if entry is None:
            return {"valid": None, "error": "", "age_seconds": -1}
        return {
            "valid": entry[0],
            "error": entry[1],
            "age_seconds": time.time() - entry[2],
        }

    def get_all_cached_statuses(self) -> dict[str, dict]:
        """Get cached statuses for all tracked accounts."""
        with self._cache_lock:
            now = time.time()
            return {
                aid: {
                    "valid": v[0],
                    "error": v[1],
                    "age_seconds": now - v[2],
                }
                for aid, v in self._cache.items()
            }

    def trigger_immediate_check(self, account_id: str) -> Optional[bool]:
        """Force an immediate credential check for a single account.

        Returns True (valid), False (invalid), or None (not found / error).
        """
        if not account_id:
            return None
        valid = self._validate(account_id)
        error = ""
        if not valid:
            # Retry once for transient failures
            import time
            time.sleep(1)
            valid = self._validate(account_id)
            if not valid:
                error = "credential check failed"
        self._set_status(account_id, valid, error)
        with self._cache_lock:
            self._cache[account_id] = (valid, error, time.time())
        return valid

    # -- Internal --

    def _run_loop(self):
        """Background loop: check stale accounts every check_interval."""
        # Do an initial check immediately on start
        self._check_round()

        while not self._stop_event.wait(self._check_interval):
            self._check_round()

    def _check_round(self):
        """One round of stale-account checks."""
        try:
            stale = self._get_stale(self._refresh_ttl, self._backoff_multiplier)
        except Exception as e:
            log.warning("Keepalive: get_stale failed: %s", e)
            return

        if not stale:
            return

        log.info("Keepalive: checking %d stale accounts", len(stale))

        valid_count = 0
        failed_count = 0

        for i, acc in enumerate(stale):
            account_id = acc.get("account_id") or acc.get("id", "")
            if not account_id:
                continue

            log.debug("Keepalive: checking %s (%d/%d)", account_id, i + 1, len(stale))

            try:
                valid = self._validate(account_id)
                error = ""
                if not valid:
                    error = "credential validation failed"

                self._set_status(account_id, valid, error)
                with self._cache_lock:
                    self._cache[account_id] = (valid, error, time.time())

                if valid:
                    valid_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                log.warning("Keepalive: validation error for %s: %s", account_id, e)
                failed_count += 1

            # Stagger checks to avoid bursts
            if i < len(stale) - 1:
                time.sleep(2)

        if valid_count or failed_count:
            log.info("Keepalive: round done — %d valid, %d failed", valid_count, failed_count)