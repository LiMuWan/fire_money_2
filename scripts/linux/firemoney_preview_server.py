"""Serve the generated FireMoney preview HTML on Linux hosts."""

from __future__ import annotations

import argparse
import http.server
from http.server import ThreadingHTTPServer
from pathlib import Path


class Utf8HtmlRequestHandler(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path: str) -> str:
        content_type = super().guess_type(path)
        if content_type == "text/html":
            return "text/html; charset=utf-8"
        return content_type


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve FireMoney preview files.")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--directory",
        default=str(Path("client") / "desktop" / "preview"),
    )
    args = parser.parse_args()

    handler = lambda *handler_args, **handler_kwargs: Utf8HtmlRequestHandler(
        *handler_args,
        directory=args.directory,
        **handler_kwargs,
    )
    with ReusableThreadingHTTPServer((args.bind, args.port), handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
