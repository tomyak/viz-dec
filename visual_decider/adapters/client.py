from urllib.parse import urlparse

import httpx


class Client:
    def __init__(self, url="http://127.0.0.1:8765"):
        p = urlparse(url)
        if (
            p.scheme != "http"
            or p.hostname not in ("127.0.0.1", "localhost", "::1")
            or p.username
            or p.password
            or p.path not in ("", "/")
            or p.query
            or p.fragment
        ):
            raise ValueError("Only loopback HTTP endpoints are allowed")
        _ = p.port  # Reject malformed ports before constructing a request.
        self.url = url.rstrip("/")

    def call(self, tool, **payload):
        with httpx.Client(timeout=3600, trust_env=False, follow_redirects=False) as client:
            try:
                r = client.post(f"{self.url}/{tool}", json=payload)
            except httpx.ConnectError as e:
                raise RuntimeError(
                    f"Local visual-decider service is unavailable at {self.url}. "
                    "Shared HTTP mode was selected, so its model service "
                    "must be running. Start visual-decider-http with your configured --root."
                ) from e
            if not r.is_success:
                raise RuntimeError(f"Local engine returned HTTP {r.status_code}: {r.text[:500]}")
            return r.json()
