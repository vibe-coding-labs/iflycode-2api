"""CLI interface for iFlyCode proxy."""

import logging
import sys

import click

log = logging.getLogger("iflycode-proxy")

AGENT_VERSION = "3.4.2"


def _get_db_and_router():
    """Load the default database and credential router."""
    from iflycode_proxy.db import Database
    db = Database()
    router = db.get_credential_router()
    return db, router


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx, verbose: bool):
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@cli.command()
@click.option("-H", "--host", default="0.0.0.0", help="Bind host")
@click.option("-p", "--port", default=40419, help="Bind port")
@click.option("--service", is_flag=True, help="Run as daemon (auto-restart on crash)")
@click.pass_context
def serve(ctx, host: str, port: int, service: bool):
    import uvicorn
    from iflycode_proxy.db import Database
    from iflycode_proxy.server import create_app

    if service:
        from iflycode_proxy.daemon import run_supervisor

        def _run_server(**kwargs):
            db = Database()
            router = db.get_credential_router()
            app = create_app(router, db=db)
            uvicorn.run(app, host=kwargs["host"], port=kwargs["port"],
                        log_level="debug" if kwargs.get("verbose") else "info")

        click.echo(f"Starting iFlyCode Proxy as daemon on http://{host}:{port}")
        click.echo(f"  Log file: ~/.iflycode-proxy/daemon.log")
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
        click.echo(f"  Log: ~/.iflycode-proxy/daemon.log")
    else:
        click.echo("Daemon not running")


@cli.command()
def version():
    click.echo("iFlyCode Proxy v1.0.0")
    click.echo(f"  Agent fingerprint: iFlyCode {AGENT_VERSION}")
    click.echo(f"  Default port: 40419")


if __name__ == "__main__":
    cli()


@cli.command()
@click.argument("message", nargs=-1, required=True)
@click.option("-m", "--model", default="iflycode-default", help="Model name")
@click.option("-s", "--stream", is_flag=True, help="Stream output")
@click.option("--max-tokens", default=4096, help="Max tokens")
def chat(message, model, stream, max_tokens):
    """Send a chat message and print the response."""
    import json
    from iflycode_proxy.db import Database
    from iflycode_proxy.credential_router import CredentialRouter

    db = Database()
    router = db.get_credential_router()
    if not router.list_accounts():
        click.echo("No accounts configured. Add one via the web UI.")
        return

    client = router.get_client(None)
    messages = [{"role": "user", "content": " ".join(message)}]
    body = {"stream": stream}
    if model:
        body["modelCode"] = model

    if stream:
        click.echo("--- streaming response ---")
        with client.chat_stream(messages, body) as resp:
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(payload)
                        choices = chunk.get("choices", [])
                        if choices:
                            content = choices[0].get("delta", {}).get("content", "")
                            click.echo(content, nl=False)
                    except json.JSONDecodeError:
                        continue
        click.echo()
    else:
        resp = client.chat(messages, body)
        data = resp.json()
        choices = data.get("choices", [])
        if choices:
            click.echo(choices[0].get("message", {}).get("content", ""))
        else:
            click.echo(str(data))


@cli.command()
def models():
    """List available upstream models."""
    db, router = _get_db_and_router()
    accounts = router.list_accounts()
    if not accounts:
        click.echo("No accounts configured.")
        return
    for acc in accounts:
        models_data = db.get_account_models(acc["account_id"])
        if models_data:
            click.echo(f"Account: {acc['account_id']}")
            for m in models_data:
                click.echo(f"  {m.get('modelCode', '?')} — {m.get('modelName', '?')}")
        else:
            click.echo(f"Account: {acc['account_id']} — no models available")


@cli.command()
def check():
    """Validate all account credentials."""
    db, router = _get_db_and_router()
    accounts = router.list_accounts()
    if not accounts:
        click.echo("No accounts configured.")
        return

    click.echo(f"Checking {len(accounts)} account(s)...")
    valid_count = 0
    for acc in accounts:
        is_valid = db.validate_account(acc["account_id"])
        status = "✅ valid" if is_valid else "❌ invalid"
        click.echo(f"  {acc['account_id']}: {status}")
        if is_valid:
            valid_count += 1
    click.echo(f"\n{valid_count}/{len(accounts)} accounts valid")


@cli.command()
def whoami():
    """Show the current default account info."""
    db, router = _get_db_and_router()
    accounts = router.list_accounts()
    if not accounts:
        click.echo("No accounts configured.")
        return
    default = db.get_default_account()
    if default:
        click.echo(f"Default account: {default.get('account_id', '?')}")
        click.echo(f"  API Key: {default.get('api_key', '?')[:12]}...")
        click.echo(f"  User ID: {default.get('user_id', '?')}")
    click.echo(f"\nTotal accounts: {len(accounts)}")
