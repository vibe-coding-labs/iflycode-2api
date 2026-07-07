# iFlyCode Proxy Service Mode (进程守护 + 自动重启)

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** 添加 `--service` 启动模式，当代理进程意外退出时自动重启，确保服务持续可用。

**Architecture:** 用户执行 `iflycode-2api serve --service` → CLI 以 supervisor 角色启动子进程运行实际 uvicorn 服务 → 监控子进程退出事件 → 非正常退出时自动重启（指数退避 + 最大重试） → 正常退出（SIGTERM/SIGINT）时 supervisor 也退出。supervisor 自身通过 double-fork 守护化，脱离终端。

**Tech Stack:** Python 3.12, click 8.2, uvicorn 0.34, os/signal 标准库

**Risks:**
- 快速崩溃循环可能占用大量资源 → 缓解：指数退避（1s→2s→4s→8s→max 30s）+ 连续崩溃 10 次后放弃
- 守护进程日志不可见 → 缓解：写入独立日志文件（`~/.iflycode-2api/daemon.log`）
- PID 文件冲突 → 缓解：启动时检测并清理 stale PID 文件

---

### Task 1: 创建 daemon.py 进程守护模块

**Depends on:** None
**Files:**
- Create: `iflycode_proxy/daemon.py`

- [ ] **Step 1: 创建 daemon.py — 实现进程守护 supervisor**

```python
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
              f"Stop it first: iflycode-2api serve --stop-service")
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
```

- [ ] **Step 2: 验证 daemon 模块导入正常**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -c "from iflycode_proxy.daemon import run_supervisor, stop_service, get_service_status; print('daemon module OK')"`
Expected:
  - Exit code: 0
  - Output contains: "daemon module OK"

- [ ] **Step 3: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add iflycode_proxy/daemon.py && git commit -m "feat(daemon): add process supervisor with auto-restart and exponential backoff"`

---

### Task 2: 集成 daemon 模式到 CLI

**Depends on:** Task 1
**Files:**
- Modify: `iflycode_proxy/cli.py:23-45`

- [ ] **Step 1: 修改 CLI serve 命令 — 添加 --service / --stop-service 选项**

文件: `iflycode_proxy/cli.py:23-45`（替换整个 serve 命令 + 添加 stop_service 命令）

```python
@cli.command()
@click.option("-H", "--host", default="0.0.0.0", help="Bind host")
@click.option("-p", "--port", default=40419, help="Bind port")
@click.option("--service", is_flag=True, help="Run as daemon (auto-restart on crash)")
@click.pass_context
def serve(ctx, host: str, port: int, service: bool):
    from iflycode_proxy.db import Database
    from iflycode_proxy.server import create_app

    if service:
        from iflycode_proxy.daemon import run_supervisor

        def _run_server(**kwargs):
            db = Database()
            router = db.get_credential_router()
            app = create_app(router, db=db)
            import uvicorn
            uvicorn.run(app, host=kwargs["host"], port=kwargs["port"],
                        log_level="debug" if kwargs.get("verbose") else "info")

        click.echo(f"Starting iFlyCode Proxy as daemon on http://{host}:{port}")
        click.echo(f"  Log file: ~/.iflycode-2api/daemon.log")
        click.echo(f"  Stop with: iflycode-proxy stop-service")
        run_supervisor(_run_server, host=host, port=port, verbose=ctx.obj.get("verbose"))
        return

    db = Database()
    router = db.get_credential_router()
    app = create_app(router, db=db)

    click.echo(f"\niFlyCode Proxy v1.0.0 — http://{host}:{port}")
    click.echo(f"  Agent fingerprint: iFlyCode 3.4.2")
    click.echo(f"  Endpoints:")
    click.echo(f"    POST /v1/chat/completions  — OpenAI compatible chat")
    click.echo(f"    GET  /v1/models            — Available models")
    click.echo(f"    GET  /api/health           — Health check")
    click.echo(f"    GET  /api/accounts         — Account management\n")

    log_level = "debug" if ctx.obj.get("verbose") else "info"
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level=log_level)


@cli.command("stop-service")
def stop_service_cmd():
    """Stop the running daemon service."""
    from iflycode_proxy.daemon import stop_service
    stop_service()


@cli.command("service-status")
def service_status_cmd():
    """Check daemon service status."""
    from iflycode_proxy.daemon import get_service_status
    pid = get_service_status()
    if pid:
        click.echo(f"Daemon running (PID {pid})")
        click.echo(f"  Log: ~/.iflycode-2api/daemon.log")
    else:
        click.echo("Daemon not running")
```

- [ ] **Step 2: 验证 CLI 子命令注册**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -m iflycode_proxy.cli --help`
Expected:
  - Exit code: 0
  - Output contains: "serve" and "stop-service" and "service-status"

- [ ] **Step 3: 验证 serve --help 显示 --service 选项**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -m iflycode_proxy.cli serve --help`
Expected:
  - Exit code: 0
  - Output contains: "--service"

- [ ] **Step 4: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add iflycode_proxy/cli.py && git commit -m "feat(cli): add --service daemon mode with stop-service and service-status commands"`
