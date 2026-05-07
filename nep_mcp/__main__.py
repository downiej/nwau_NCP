"""Local dev entrypoint.

Usage:
    python -m nep_mcp                  # stdio transport (for MCP clients like Claude Desktop)
    python -m nep_mcp --http           # streamable-http on 127.0.0.1:8000
    python -m nep_mcp --http --port 9000

The HTTP mode is the same transport Azure Functions hosts in production, so
exercising it locally gives confidence the deployed server will behave the same.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .server import _eager_load, mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nep-mcp", description=__doc__)
    parser.add_argument("--http", action="store_true", help="Run streamable-http instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    _eager_load()

    if args.http:
        # FastMCP wires host/port via its settings object.
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
