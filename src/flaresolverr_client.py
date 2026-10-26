from __future__ import annotations

import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def solve_cloudflare(endpoint: str, *, timeout_seconds: int = 24) -> tuple[str, str] | None:
    """Ask local FlareSolverr for clearance only; never forward ChatGPT account cookies."""
    parsed_url = urlsplit(endpoint)
    if (
        parsed_url.scheme != "http"
        or parsed_url.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed_url.username is not None
        or parsed_url.password is not None
    ):
        raise ValueError("FlareSolverr endpoint must be local HTTP")

    url = endpoint.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    timeout_seconds = max(1, min(timeout_seconds, 30))
    body = json.dumps(
        {
            "cmd": "request.get",
            "url": "https://chatgpt.com/",
            "maxTimeout": timeout_seconds * 1000,
            "returnOnlyCookies": True,
        }
    ).encode("utf-8")
    request = Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urlopen(request, timeout=timeout_seconds + 5) as response:
        raw = response.read(128 * 1024 + 1)
    if len(raw) > 128 * 1024:
        raise ValueError("FlareSolverr response exceeded limit")
    result: object = json.loads(raw)
    if not isinstance(result, dict) or result.get("status") != "ok":
        return None
    solution = result.get("solution")
    if not isinstance(solution, dict) or solution.get("status") != 200:
        return None
    user_agent = solution.get("userAgent")
    cookies = solution.get("cookies")
    if (
        not isinstance(user_agent, str)
        or not 20 <= len(user_agent) <= 512
        or "\n" in user_agent
        or "\r" in user_agent
        or not isinstance(cookies, list)
    ):
        return None
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        value = cookie.get("value")
        if (
            cookie.get("name") == "cf_clearance"
            and cookie.get("domain") in {"chatgpt.com", ".chatgpt.com"}
            and isinstance(value, str)
            and 0 < len(value) <= 4096
        ):
            return value, user_agent
    return None
