#!/usr/bin/env python3
"""Read-only production edge and API security audit with JSON evidence."""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def fetch(url: str, *, method: str = "GET", headers: dict[str, str] | None = None):
    request_headers = {"User-Agent": "Mozilla/5.0 DrumToScoreOpsAudit/1.0"}
    request_headers.update(headers or {})
    request = Request(url, method=method, headers=request_headers)
    try:
        response = build_opener(NoRedirect).open(request, timeout=20)
    except HTTPError as error:
        response = error
    body = response.read(256_000)
    return (
        response.status,
        {key.casefold(): value for key, value in response.headers.items()},
        body,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", default="https://drumtoscore.com/")
    parser.add_argument(
        "--api-health", default="https://drumtoscore.com/api/v1/health/ready"
    )
    args = parser.parse_args()
    checks: dict[str, dict[str, object]] = {}

    def record(name: str, passed: bool, evidence: object) -> None:
        checks[name] = {"passed": passed, "evidence": evidence}

    status, headers, _ = fetch(args.web)
    record("web_https", status == 200, {"status": status})
    expected_headers = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "strict-origin-when-cross-origin",
    }
    observed = {name: headers.get(name) for name in expected_headers}
    record("web_security_headers", observed == expected_headers, observed)
    hsts = headers.get("strict-transport-security", "")
    record(
        "web_hsts",
        "max-age=31536000" in hsts,
        {"strictTransportSecurity": hsts or None},
    )

    parsed_web = urlparse(args.web)
    insecure_url = parsed_web._replace(scheme="http").geturl()
    status, redirect_headers, _ = fetch(insecure_url)
    location = redirect_headers.get("location", "")
    record(
        "http_redirect",
        status in {301, 302, 307, 308} and location.startswith("https://"),
        {"status": status, "location": location},
    )

    redirect_probe = urljoin(args.web, "/projects/demo-groove?tour=1")
    www_probe = redirect_probe.replace("://drumtoscore.com", "://www.drumtoscore.com")
    status, www_headers, _ = fetch(www_probe)
    record(
        "canonical_www_redirect",
        status == 301 and www_headers.get("location") == redirect_probe,
        {"status": status, "location": www_headers.get("location")},
    )

    status, _, body = fetch(args.api_health)
    readiness = json.loads(body) if body else {}
    dependencies_ok = readiness.get("status") == "ready" and all(
        item.get("status") == "ok" for item in readiness.get("checks", {}).values()
    )
    record("api_readiness", status == 200 and dependencies_ok, readiness)

    api_root = args.api_health.split("/health/ready", 1)[0]
    status, _, _ = fetch(urljoin(api_root + "/", "projects"))
    record("unauthorized_projects_denied", status == 401, {"status": status})
    status, cors_headers, _ = fetch(
        urljoin(api_root + "/", "projects"),
        method="OPTIONS",
        headers={
            "Origin": "https://attacker.invalid",
            "Access-Control-Request-Method": "POST",
        },
    )
    record(
        "hostile_cors_denied",
        status >= 400 and "access-control-allow-origin" not in cors_headers,
        {
            "status": status,
            "allowOrigin": cors_headers.get("access-control-allow-origin"),
        },
    )

    hostname = parsed_web.hostname or "drumtoscore.com"
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with (
        socket.create_connection((hostname, 443), timeout=20) as raw,
        context.wrap_socket(raw, server_hostname=hostname) as secure,
    ):
        certificate = secure.getpeercert()
        protocol = secure.version()
    expires = datetime.strptime(
        certificate["notAfter"], "%b %d %H:%M:%S %Y %Z"
    ).replace(tzinfo=timezone.utc)
    days_remaining = (expires - datetime.now(timezone.utc)).days
    record(
        "tls_certificate",
        protocol in {"TLSv1.2", "TLSv1.3"} and days_remaining >= 14,
        {
            "protocol": protocol,
            "expiresAt": expires.isoformat(),
            "daysRemaining": days_remaining,
        },
    )

    result = {
        "schemaVersion": 1,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "readOnly": True,
        "cardOrPaidServiceUsed": False,
        "passed": all(item["passed"] for item in checks.values()),
        "checks": checks,
    }
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
