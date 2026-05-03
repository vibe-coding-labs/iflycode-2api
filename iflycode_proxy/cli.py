"""CLI interface for iFlyCode proxy."""

import logging
import sys

import click

log = logging.getLogger("iflycode-proxy")

AGENT_VERSION = "3.4.2"


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
