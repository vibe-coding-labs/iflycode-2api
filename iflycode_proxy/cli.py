"""CLI interface for iFlyCode proxy."""

import logging
import sys

import click

log = logging.getLogger("iflycode-proxy")


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
@click.option("-p", "--port", default=9090, help="Bind port")
@click.pass_context
def serve(ctx, host: str, port: int):
    import uvicorn
    from iflycode_proxy.db import Database
    from iflycode_proxy.server import create_app

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


if __name__ == "__main__":
    cli()
