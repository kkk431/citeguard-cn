"""万方开放平台客户端（可选数据源）。

只在配置了 ``WANFANG_APP_KEY`` 时启用。鉴权头是 ``X-App-Key``，必须走 HTTPS；
接口需要账号订阅「万方文献检索」，未订阅时平台返回 403 ``AUTH_NOT_SUBSCRIBED``，
这里转成带申请链接的异常，便于产品里给出可操作的提示，而不是静默失败。

文档：https://ai.wfdata.com/api-detail?id=17
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from . import config

SEARCH_PATH = "/openwanfang/getQuery"
DOC_PATH = "/openwanfang/getDoc"
TRIAL_URL = "https://ai.wfdata.com/api-detail?id=17"

#: 检索返回字段（按平台文档可用的题录字段裁剪）。
SEARCH_FIELDS = [
    "Id",
    "Title",
    "Creator",
    "Abstract",
    "Keywords",
    "DOI",
    "PublishYear",
    "PeriodicalTitle",
    "Volum",
    "Issue",
    "Page",
    "Type",
    "Language",
]


class WanfangError(RuntimeError):
    """万方接口不可用或返回异常。"""


class WanfangNotSubscribed(WanfangError):
    """App Key 有效，但没有订阅对应接口。"""


class WanfangNotConfigured(WanfangError):
    """没有配置 App Key。"""


def available() -> bool:
    return bool(config.WANFANG_APP_KEY)


_CALL_LOCK = threading.Lock()
_LAST_CALL = 0.0
_MIN_INTERVAL = 0.30  # 平台限流 4 req/s，留余量


def _throttle() -> None:
    global _LAST_CALL
    with _CALL_LOCK:
        wait = _MIN_INTERVAL - (time.monotonic() - _LAST_CALL)
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL = time.monotonic()


def _post(path: str, payload: dict[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
    if not config.WANFANG_APP_KEY:
        raise WanfangNotConfigured("未配置 WANFANG_APP_KEY")
    url = config.WANFANG_BASE + path
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "X-App-Key": config.WANFANG_APP_KEY},
        method="POST",
    )
    _throttle()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        if exc.code == 429:
            time.sleep(0.6)
            _throttle()
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = response.read()
            except urllib.error.HTTPError as retry_exc:
                raw = retry_exc.read()
                exc = retry_exc
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            data = {}
        if data.get("code") == "AUTH_NOT_SUBSCRIBED" or exc.code == 403:
            message = data.get("message") or "尚未订阅万方接口"
            raise WanfangNotSubscribed(
                f"{message}（在 {TRIAL_URL} 申请试用/订阅后即可使用）"
            ) from exc
        raise WanfangError(f"万方接口 HTTP {exc.code}: {raw[:200]!r}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise WanfangError(f"万方接口连接失败: {exc}") from exc

    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise WanfangError(f"万方接口返回非 JSON: {raw[:200]!r}") from exc


def search(
    query: str,
    *,
    collections: tuple[str, ...] = ("OpenPeriodicalChi",),
    rows: int = 10,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """按平台查询语法检索题录，返回 ``records`` 列表。"""

    if not query.strip():
        return []
    payload = {
        "collections": list(collections),
        "query": query,
        "rows": max(1, min(int(rows), 50)),
        "returned_fields": fields or SEARCH_FIELDS,
    }
    data = _post(SEARCH_PATH, payload)
    documents = data.get("documents") or data.get("records") or []
    records: list[dict[str, Any]] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        resource_type = str(document.get("resourceType") or "")
        payload_fields = document.get(resource_type)
        if not isinstance(payload_fields, dict):
            payload_fields = document.get("Periodical") or document.get("fields") or {}
        record = dict(payload_fields)
        record.setdefault("resourceType", resource_type)
        record.setdefault("uid", document.get("uid", ""))
        records.append(record)
    return records


def get_doc(collection: str, doc_id: str) -> dict[str, Any]:
    data = _post(DOC_PATH, {"collection": collection, "doc_id": doc_id})
    return data.get("record") or data.get("data") or data


def record_to_candidate_fields(record: dict[str, Any]) -> dict[str, Any]:
    """把万方题录转成产品内部 Candidate 所需字段（不带来源判断）。"""

    def first(*keys: str) -> str:
        for key in keys:
            value = record.get(key)
            if value not in (None, "", []):
                if isinstance(value, list):
                    return "; ".join(str(v) for v in value)
                return str(value)
        return ""

    year = first("PublishYear", "Year")
    try:
        year_int: int | None = int(str(year)[:4]) if year else None
    except ValueError:
        year_int = None

    def join_cjk_list(*keys: str) -> str:
        """作者等多值字段：保留全部含中文的条目，用分号连接。"""

        for key in keys:
            value = record.get(key)
            if isinstance(value, list):
                items = [str(v).strip() for v in value if str(v).strip()]
                if items:
                    return "; ".join(items)
            elif value not in (None, "", []):
                return str(value).strip()
        return ""

    def first_list(*keys: str) -> str:
        """取第一个可用值；列表优先选含中文的条目（万方会把英文题名放在同列）。"""

        for key in keys:
            value = record.get(key)
            if isinstance(value, list) and value:
                items = [str(v).strip() for v in value if v not in (None, "")]
                if not items:
                    continue
                for item in items:
                    if re.search(r"[\u4e00-\u9fff]", item):
                        return item
                return items[0]
            if value not in (None, "", []):
                return str(value).strip()
        return ""

    doc_id = first("Id", "id")
    kind = str(record.get("resourceType") or record.get("Type") or "").lower()
    prefix = {
        "periodical": "periodical",
        "thesis": "thesis",
        "conference": "conference",
        "patent": "patent",
        "standard": "standard",
        "law": "claw",
        "achievement": "cstad",
    }.get(kind, "paper")
    return {
        "title": first_list("Title", "title"),
        "doi": first_list("DOI", "Doi", "doi"),
        "year": year_int,
        "authors": join_cjk_list("Creator", "Authors"),
        "venue": first_list("PeriodicalTitle", "Venue"),
        "volume": first_list("Volum", "Volume"),
        "issue": first_list("Issue"),
        "pages": first_list("Page", "Pages"),
        "abstract": first_list("Abstract"),
        "url": f"https://d.wanfangdata.com.cn/{prefix}/{doc_id}" if doc_id else "",
    }
