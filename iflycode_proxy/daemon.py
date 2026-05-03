"""Process guardian — auto-restart the proxy server on unexpected exit."""

import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("iflycode-proxy.daemon")

_MAX_RESTARTS = 10
_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 30.0
_PID_DIR = Path.home() / ".iflycode-proxy"
_PID_FILE = _PID_DIR / "daemon.pid"
_LOG_FILE = _PID_DIR / "daemon.log"


def _write_pid() -> None:
    _PID_DIR.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(os.getpid()))


def _remove_pid() -> None:
    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _is_stale_pid() -> bool:
    """Check if a stale PID file exists and the process is gone."""
    if not _PID_FILE.exists():
        return False
    try:
        old_pid = int(_PID_FILE.read_text().strip())
        os.kill(old_pid, 0)
        return False  # process still alive
    except (ValueError, ProcessLookupError):
        return True
    except PermissionError:
        return False  # process exists but not ours


def _setup_logging() -> None:
    _PID_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(_LOG_FILE)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger("iflycode-proxy").addHandler(handler)
    logging.getLogger("iflycode-proxy.daemon").setLevel(logging.DEBUG)


def _daemonize() -> None:
    """Double-fork to detach from terminal."""
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    os.setsid()

    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    sys.stdout.flush()
    sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, sys.stdin.fileno())
    os.close(devnull)


def run_supervisor(
    serve_fn,
    host: str = "0.0.0.0",
    port: int = 40419,
    verbose: bool = False,
) -> None:
    """Run as supervisor — spawn child process, auto-restart on crash."""

    if _PID_FILE.exists() and not _is_stale_pid():
        print(f"Daemon already running (PID {_PID_FILE.read_text().strip()}). "
              f"Stop it first: iflycode-proxy stop-service")
        sys.exit(1)

    _PID_DIR.mkdir(parents=True, exist_ok=True)
    _daemonize()
    _write_pid()
    _setup_logging()

    log.info("Supervisor started (PID %d), watching port %d", os.getpid(), port)

    restarts = 0
    backoff = _INITIAL_BACKOFF

    def _sigterm(signum, frame):
        log.info("Supervisor received SIGTERM, shutting down")
        _remove_pid()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    while restarts < _MAX_RESTARTS:
        child_pid = os.fork()
        if child_pid == 0:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            try:
                serve_fn(host=host, port=port, verbose=verbose)
            except Exception as e:
                log.error("Child process crashed: %s", e)
                sys.exit(1)
            sys.exit(0)

        log.info("Started child process (PID %d)", child_pid)
        _, status = os.waitpid(child_pid, 0)
        exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
        signaled = os.WIFSIGNALED(status)

        if signaled:
            sig = os.WTERMSIG(status)
            log.warning("Child killed by signal %d", sig)
        else:
            log.warning("Child exited with code %d", exit_code)

        if exit_code == 0 and not signaled:
            log.info("Child exited normally, supervisor shutting down")
            break

        restarts += 1
        log.warning("Restarting in %.1fs (attempt %d/%d)", backoff, restarts, _MAX_RESTARTS)
        time.sleep(backoff)
        backoff = min(backoff * 2, _MAX_BACKOFF)

    if restarts >= _MAX_RESTARTS:
        log.error("Max restarts (%d) reached, giving up", _MAX_RESTARTS)

    _remove_pid()
    log.info("Supervisor exiting")


def stop_service() -> bool:
    """Stop the running daemon supervisor."""
    if not _PID_FILE.exists():
        print("No daemon running")
        return False

    try:
        pid = int(_PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to daemon (PID {pid})")
        for _ in range(20):
            try:
                os.kill(pid, 0)
                time.sleep(0.25)
            except ProcessLookupError:
                print("Daemon stopped")
                _remove_pid()
                return True
        print("Daemon did not stop, force killing")
        os.kill(pid, signal.SIGKILL)
        _remove_pid()
        return True
    except ProcessLookupError:
        print("Daemon process not found, cleaning up stale PID file")
        _remove_pid()
        return False
    except PermissionError:
        print(f"Permission denied to stop PID {pid}")
        return False


def get_service_status() -> Optional[int]:
    """Return daemon PID if running, else None."""
    if not _PID_FILE.exists():
        return None
    try:
        pid = int(_PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError):
        _remove_pid()
        return None
    except PermissionError:
        return pid
