"""Minimal Python client for the CiteGuard-CN HTTP API.

No third-party dependency: stdlib urllib only. Intended for scripts, notebooks
and the Word/browser integrations to share one request/response contract.

    >>> from citeguard.client import CiteGuardClient
    >>> c = CiteGuardClient("http://127.0.0.1:8010")
    >>> c.health()["version"]
    >>> r = c.check_support("该方法平均提升 2.3%。", "平均提升 2.1%。")
    >>> r.label, r.confidence
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


class CiteGuardError(RuntimeError):
    """Raised when the API returns a non-2xx response or invalid JSON."""

    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass
class SupportResult:
    label: str
    confidence: float | None
    reason: str
    audit: dict[str, Any] = field(default_factory=dict)
    numeric: dict[str, Any] = field(default_factory=dict)
    prompt_version: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class CiteGuardClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8010", *, timeout: float = 120.0,
                 api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key

    # -- transport ---------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "User-Agent": "citeguard-client/0.9"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(detail)
            except Exception:
                parsed = {}
            raise CiteGuardError(parsed.get("error") or parsed.get("detail") or detail,
                                 status=exc.code, code=parsed.get("code")) from exc
        except urllib.error.URLError as exc:
            raise CiteGuardError(f"无法连接 {self.base_url}: {exc.reason}") from exc
        try:
            return json.loads(body)
        except Exception as exc:
            raise CiteGuardError("服务返回的不是 JSON") from exc

    # -- endpoints ---------------------------------------------------------
    def health(self) -> dict[str, Any]:
        return self._request("GET", "/api/health")

    def check_support(self, claim: str, evidence: str) -> SupportResult:
        data = self._request("POST", "/api/support/check", {"claim": claim, "evidence": evidence})
        if data.get("ok") is False:
            raise CiteGuardError(data.get("error", "核验失败"), code=data.get("code"))
        return SupportResult(
            label=str(data.get("label") or ""),
            confidence=data.get("confidence"),
            reason=str(data.get("reason") or ""),
            audit=data.get("audit") or {},
            numeric=data.get("numeric") or {},
            prompt_version=str(data.get("prompt_version") or ""),
            raw=data,
        )

    def check_support_batch(self, items: list[dict[str, str]]) -> list[dict[str, Any]]:
        data = self._request("POST", "/api/support/batch", {"items": items})
        if data.get("ok") is False:
            raise CiteGuardError(data.get("error", "批量核验失败"), code=data.get("code"))
        return list(data.get("results") or [])


def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="CiteGuard-CN 命令行客户端")
    ap.add_argument("--base-url", default="http://127.0.0.1:8010")
    ap.add_argument("--claim")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--evidence-file")
    args = ap.parse_args(argv)
    client = CiteGuardClient(args.base_url)
    if not args.claim:
        print(json.dumps(client.health(), ensure_ascii=False, indent=2))
        return 0
    evidence = args.evidence
    if args.evidence_file:
        evidence = open(args.evidence_file, encoding="utf-8").read()
    result = client.check_support(args.claim, evidence)
    print(json.dumps(result.raw, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
