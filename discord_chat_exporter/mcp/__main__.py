"""Entry point for ``python -m discord_chat_exporter.mcp``."""

from __future__ import annotations

import sys


def main() -> None:
    from discord_chat_exporter.mcp.server import mcp

    transport = "stdio"
    port = 8000

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--transport" and i + 1 < len(args):
            transport = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        else:
            i += 1

    if transport == "http":
        mcp.run(transport="http", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
