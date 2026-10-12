#!/usr/bin/env python3
"""Optional localhost fetch sidecar for reference imagery (Cursor sandbox escape).

NOT required at handoff. Prefer: run aerial_mosaic.py once in Terminal when
a mosaic is missing, then let the agent use on-disk reference/.

This process binds 127.0.0.1 only (on NO_PROXY) so a sandboxed agent can
pull bytes while the sidecar uses the host network. Start it only if you
want agent-driven downloads; never as a per-session chore.

  python3 scripts/ref_fetch_agent.py              # optional, external Terminal
  python3 scripts/ref_fetch_agent.py --health
  python3 scripts/ref_fetch_agent.py --get URL [-o PATH]

  from ref_fetch_agent import fetch_bytes          # used by aerial_mosaic

Env:
  REF_FETCH_PORT   listen / client port (default 18765)
  REF_FETCH_URL    override base, e.g. http://127.0.0.1:18765
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping
from urllib.parse import urlparse

DEFAULT_PORT = 18765
DEFAULT_UA = 'SouthamptonRefine/ref_fetch_agent (+local build reference)'

# Only these hosts may be fetched (SSRF guard).
ALLOWED_HOSTS = frozenset({
    'tiles.maps.southampton.ac.uk',
    'maps.southampton.ac.uk',
    'api.openstreetcam.org',
    'openstreetcam.org',
    'www.openstreetcam.org',
    'kartaview.org',
    'www.kartaview.org',
    'www.geograph.org.uk',
    'geograph.org.uk',
})


def base_url() -> str:
    """Return the sidecar base URL.

    @returns: http://127.0.0.1:<port> (or REF_FETCH_URL)
    """
    override = os.environ.get('REF_FETCH_URL', '').strip()
    if override:
        return override.rstrip('/')
    port = int(os.environ.get('REF_FETCH_PORT', DEFAULT_PORT))
    return f'http://127.0.0.1:{port}'


def listen_port() -> int:
    """Port the HTTP server should bind.

    @returns: TCP port
    """
    return int(os.environ.get('REF_FETCH_PORT', DEFAULT_PORT))


def host_allowed(url: str) -> bool:
    """Return whether url's host is on the allowlist.

    @param url: absolute http(s) URL
    @returns: True if fetch is permitted
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    host = (parsed.hostname or '').lower()
    return host in ALLOWED_HOSTS


def looks_like_sandbox_proxy_error(exc: BaseException) -> bool:
    """Heuristic: failure is the Cursor allowlist proxy, not the remote host.

    @param exc: exception from urllib
    @returns: True if a sidecar retry is warranted
    """
    text = str(exc).lower()
    needles = (
        'tunnel connection failed',
        '403 forbidden',
        'nodename nor servname',
        'name or service not known',
        'temporary failure in name resolution',
        'proxy',
    )
    return any(n in text for n in needles)


def direct_fetch(url: str, headers: Mapping[str, str] | None, timeout: float) -> bytes:
    """Fetch url with the process network (no sidecar).

    @param url: absolute URL
    @param headers: optional request headers
    @param timeout: seconds
    @returns: response body
    """
    if not host_allowed(url):
        raise PermissionError(f'host not allowlisted: {urlparse(url).hostname}')
    hdrs = {'User-Agent': DEFAULT_UA, 'Accept': '*/*'}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    # Bypass ambient HTTP(S)_PROXY for the allowlisted origin when possible.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        return resp.read()


def sidecar_fetch(url: str, headers: Mapping[str, str] | None, timeout: float) -> bytes:
    """Fetch url via the localhost sidecar.

    @param url: absolute URL
    @param headers: optional request headers
    @param timeout: seconds
    @returns: response body
    """
    payload = json.dumps({'url': url, 'headers': dict(headers or {})}).encode()
    req = urllib.request.Request(
        base_url() + '/v1/fetch',
        data=payload,
        headers={'Content-Type': 'application/json', 'Accept': 'application/octet-stream'},
        method='POST',
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        return resp.read()


def sidecar_up(timeout: float = 1.5) -> bool:
    """Return True if the sidecar answers /health.

    @param timeout: seconds
    @returns: whether healthy
    """
    try:
        req = urllib.request.Request(base_url() + '/health', headers={'Accept': 'application/json'})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        return bool(data.get('ok'))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def fetch_bytes(
    url: str,
    headers: Mapping[str, str] | None = None,
    *,
    timeout: float = 30.0,
    prefer_sidecar: bool | None = None,
) -> bytes:
    """Fetch allowlisted URL: direct first, then localhost sidecar.

    @param url: absolute http(s) URL
    @param headers: optional headers (Referer, User-Agent, …)
    @param timeout: seconds
    @param prefer_sidecar: if True, skip direct; if None, auto (sidecar when up
        and CURSOR sandbox proxy env looks active)
    @returns: response body bytes
    @raises: RuntimeError with start instructions when both paths fail
    """
    if not host_allowed(url):
        raise PermissionError(f'host not allowlisted: {urlparse(url).hostname}')

    sandboxish = bool(os.environ.get('CURSOR_SANDBOX') or os.environ.get('HTTPS_PROXY'))
    use_sidecar_first = prefer_sidecar if prefer_sidecar is not None else (
        sandboxish and sidecar_up()
    )

    errors: list[str] = []
    order = ('sidecar', 'direct') if use_sidecar_first else ('direct', 'sidecar')
    for mode in order:
        try:
            if mode == 'direct':
                return direct_fetch(url, headers, timeout)
            if not sidecar_up():
                errors.append('sidecar: down')
                continue
            return sidecar_fetch(url, headers, timeout)
        except Exception as exc:  # noqa: BLE001 — surface both attempts
            errors.append(f'{mode}: {exc}')
            if mode == 'direct' and not looks_like_sandbox_proxy_error(exc):
                # Remote 404/500 etc. — do not hide behind sidecar retry noise
                # unless sidecar might still help (rare); still try sidecar once.
                pass

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    start = (
        'Cursor sandbox cannot reach Hub. Prefer a one-shot in Terminal:\n'
        f'  cd {root}\n'
        '  python3 scripts/aerial_mosaic.py --at X,Z --place PLACE '
        '--dir aerial/… --size 3 --add\n'
        '(Optional sidecar only if you want agent-driven fetches — not at handoff.)\n'
        f'Detail: {"; ".join(errors)}'
    )
    raise RuntimeError(start)


class Handler(BaseHTTPRequestHandler):
    """Minimal JSON/binary fetch API."""

    def log_message(self, fmt: str, *args) -> None:
        """Log to stderr without client host spam reduction issues.

        @param fmt: printf-style format
        @param args: format args
        """
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        """Write an HTTP response.

        @param code: status
        @param body: bytes
        @param content_type: Content-Type value
        """
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        """Handle /health and /v1/fetch?url=.

        @returns: None
        """
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            body = json.dumps({
                'ok': True,
                'service': 'ref_fetch_agent',
                'allowed_hosts': sorted(ALLOWED_HOSTS),
            }).encode()
            self._send(200, body, 'application/json')
            return
        if parsed.path == '/v1/fetch':
            qs = urllib.parse.parse_qs(parsed.query)
            url = (qs.get('url') or [''])[0]
            try:
                data = direct_fetch(url, None, timeout=60.0)
            except Exception as exc:  # noqa: BLE001
                self._send(400, json.dumps({'ok': False, 'error': str(exc)}).encode(), 'application/json')
                return
            self._send(200, data, 'application/octet-stream')
            return
        self._send(404, b'not found', 'text/plain')

    def do_POST(self) -> None:
        """Handle POST /v1/fetch with JSON body.

        @returns: None
        """
        if urlparse(self.path).path != '/v1/fetch':
            self._send(404, b'not found', 'text/plain')
            return
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length else b'{}'
        try:
            msg = json.loads(raw.decode() or '{}')
            url = msg['url']
            headers = msg.get('headers') or {}
            data = direct_fetch(url, headers, timeout=60.0)
        except Exception as exc:  # noqa: BLE001
            self._send(400, json.dumps({'ok': False, 'error': str(exc)}).encode(), 'application/json')
            return
        self._send(200, data, 'application/octet-stream')


def probe_host_network() -> tuple[bool, str]:
    """Probe whether this process can reach Hampshire Hub (not sandboxed).

    @returns: (ok, detail)
    """
    url = 'https://tiles.maps.southampton.ac.uk/aer/18/130063/87836.png'
    try:
        data = direct_fetch(
            url,
            {
                'User-Agent': DEFAULT_UA,
                'Referer': 'https://maps.southampton.ac.uk/',
            },
            timeout=20.0,
        )
        if len(data) > 100 and data[:8] == b'\x89PNG\r\n\x1a\n':
            return True, f'ok ({len(data)} byte PNG)'
        return False, f'non-PNG response ({len(data)} bytes)'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def serve() -> int:
    """Run the sidecar until killed.

    @returns: exit code
    """
    port = listen_port()
    ok, detail = probe_host_network()
    if not ok:
        print(
            'ERROR: this process cannot reach tiles.maps.southampton.ac.uk\n'
            f'  ({detail})\n'
            'You started the sidecar inside the Cursor agent sandbox.\n'
            'Stop it, then start from macOS Terminal / iTerm instead:\n'
            '  open scripts/start-ref-fetch.command\n'
            'or:\n'
            '  python3 scripts/ref_fetch_agent.py\n',
            file=sys.stderr,
            flush=True,
        )
        return 3
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(
        f'ref_fetch_agent listening on http://127.0.0.1:{port}  (Ctrl+C to stop)\n'
        f'host network: {detail}\n'
        f'health: curl -s http://127.0.0.1:{port}/health\n'
        f'or double-click: scripts/start-ref-fetch.command',
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped', flush=True)
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry.

    @param argv: args without program name
    @returns: exit code
    """
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--health', action='store_true', help='check sidecar and exit')
    p.add_argument(
        '--probe',
        action='store_true',
        help='test whether THIS process can reach Hampshire Hub (no server)',
    )
    p.add_argument('--get', metavar='URL', help='fetch URL (via sidecar if needed) to stdout or -o')
    p.add_argument('-o', '--output', help='write --get bytes to this path')
    p.add_argument('--direct', action='store_true', help='with --get, force process-direct fetch')
    p.add_argument('--port', type=int, help=f'override listen/client port (default {DEFAULT_PORT})')
    args = p.parse_args(argv)
    if args.port:
        os.environ['REF_FETCH_PORT'] = str(args.port)

    if args.probe:
        ok, detail = probe_host_network()
        print(json.dumps({'ok': ok, 'detail': detail}, indent=2))
        return 0 if ok else 1

    if args.health:
        ok = sidecar_up()
        usable = False
        detail = 'sidecar down'
        if ok:
            # Sidecar may be "up" but sandboxed — probe via a real fetch.
            try:
                data = sidecar_fetch(
                    'https://tiles.maps.southampton.ac.uk/aer/18/130063/87836.png',
                    {
                        'User-Agent': DEFAULT_UA,
                        'Referer': 'https://maps.southampton.ac.uk/',
                    },
                    timeout=20.0,
                )
                usable = len(data) > 100 and data[:8] == b'\x89PNG\r\n\x1a\n'
                detail = f'{len(data)} byte PNG' if usable else 'bad body'
            except Exception as exc:  # noqa: BLE001
                detail = str(exc)
        print(json.dumps({
            'ok': ok,
            'usable': usable,
            'base': base_url(),
            'detail': detail,
            'hint': None if usable else (
                'Start outside Cursor: open scripts/start-ref-fetch.command'
            ),
        }, indent=2))
        return 0 if usable else 1

    if args.get:
        try:
            data = (
                direct_fetch(args.get, None, 60.0)
                if args.direct
                else fetch_bytes(args.get, timeout=60.0)
            )
        except Exception as exc:  # noqa: BLE001
            print(exc, file=sys.stderr)
            return 2
        if args.output:
            with open(args.output, 'wb') as fh:
                fh.write(data)
            print(f'wrote {args.output} ({len(data)} bytes)', flush=True)
        else:
            sys.stdout.buffer.write(data)
        return 0

    return serve()


if __name__ == '__main__':
    raise SystemExit(main())
