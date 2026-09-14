#!/usr/bin/env python3
"""Local proxy to a VPC-internal Cloud Run service, with the caller's gcloud identity token.

Equivalent to `gcloud run services proxy`, for machines whose gcloud cannot install that
component (apt-managed installs).  Every request to http://localhost:<port> is forwarded to
the service URL with `Authorization: Bearer <gcloud auth print-identity-token>`; the token
is refreshed before it expires.  Nothing else is added or rewritten.  Standard library only.

    scripts/run-proxy.py --service tariff-web --project tariff-order-parsing --region asia-south1 --port 3000

Run it where the service is reachable (a VM inside the project, since ingress is internal)
and tunnel the port to your browser over SSH.  The identity is whatever `gcloud auth list`
shows as active — sign in as the reviewer first.
"""

from __future__ import annotations

import argparse
import http.client
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


class TokenSource:
    def __init__(self, command: list[str], ttl_seconds: int = 50 * 60) -> None:
        self.command = command
        self.ttl = ttl_seconds
        self._token: str | None = None
        self._minted = 0.0

    def get(self) -> str:
        if self._token is None or time.time() - self._minted > self.ttl:
            out = subprocess.run(self.command, check=True, capture_output=True, text=True)
            self._token = out.stdout.strip()
            self._minted = time.time()
            if not self._token:
                raise RuntimeError("identity token command returned nothing; is a gcloud account active?")
        return self._token


def make_handler(target: str, tokens: TokenSource):
    parts = urlsplit(target)
    secure = parts.scheme == "https"
    host = parts.netloc

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _forward(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
            headers["Host"] = host
            headers["Authorization"] = f"Bearer {tokens.get()}"
            if body is not None:
                headers["Content-Length"] = str(len(body))
            conn = (http.client.HTTPSConnection if secure else http.client.HTTPConnection)(host, timeout=120)
            try:
                conn.request(self.command, self.path, body=body, headers=headers)
                resp = conn.getresponse()
                data = resp.read()
                self.send_response(resp.status, resp.reason)
                for k, v in resp.getheaders():
                    if k.lower() in HOP_BY_HOP:
                        continue
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:  # noqa: BLE001 - report to the browser, keep serving
                msg = f"proxy error: {type(e).__name__}: {e}".encode()
                self.send_response(502)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
            finally:
                conn.close()

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _forward

        def log_message(self, fmt, *args):  # noqa: ANN001
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    return Handler


def service_url(service: str, project: str, region: str) -> str:
    out = subprocess.run(
        [
            "gcloud",
            "run",
            "services",
            "describe",
            service,
            "--project",
            project,
            "--region",
            region,
            "--format=value(status.url)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    url = out.stdout.strip()
    if not url:
        raise SystemExit(f"could not resolve the URL of service {service!r}")
    return url


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--service", default="tariff-web")
    ap.add_argument("--project", default="tariff-order-parsing")
    ap.add_argument("--region", default="asia-south1")
    ap.add_argument("--port", type=int, default=3000)
    ap.add_argument("--target", help="override the service URL (testing)")
    ap.add_argument(
        "--token-command",
        default="gcloud auth print-identity-token",
        help="command whose stdout is the bearer token (default: gcloud auth print-identity-token)",
    )
    args = ap.parse_args(argv)
    target = args.target or service_url(args.service, args.project, args.region)
    tokens = TokenSource(args.token_command.split())
    tokens.get()  # fail early if no identity is available
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(target, tokens))
    print(f"proxying http://127.0.0.1:{args.port} -> {target} (identity from: {args.token_command})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
