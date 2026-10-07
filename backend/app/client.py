"""Small async public endpoint client, based on bjrsti/fotmob.

No token forging, proxy rotation, cookies, or challenge bypass is performed.
"""
import asyncio
import copy
import json
import re
import time
from collections import OrderedDict

import httpx

from .errors import (
    APIError, AccessDeniedError, InvalidResponseError, NetworkError,
    NotFoundError, RateLimitError, RequestTimeoutError,
)
from .models import Query

BASE_URL = "https://www.fotmob.com"


class FotmobClient:
    def __init__(self, *, transport=None, cache_seconds=15):
        self.transport = transport
        self.cache_seconds = cache_seconds
        self.cache = OrderedDict()
        self.build_id = None
        self.build_fetched = 0.0

    @staticmethod
    def check(response):
        status = response.status_code
        if status == 404:
            raise NotFoundError("FotMob に指定されたデータが見つかりませんでした")
        if status == 429:
            raise RateLimitError("FotMob の取得制限に達しました。しばらく待って再取得してください", retry_after=response.headers.get("retry-after"))
        if status in (401, 403):
            raise AccessDeniedError("FotMob がアクセスを拒否しました。デモへ切り替えるか、時間をおいて再取得してください")
        if status >= 400:
            raise APIError(f"FotMob が HTTP {status} を返しました")

    async def request_json(self, client, path, params=None):
        response = await client.get(path, params=params)
        self.check(response)
        try:
            value = response.json()
        except (ValueError, json.JSONDecodeError):
            raise InvalidResponseError("FotMob の応答を JSON として読み取れませんでした")
        if not isinstance(value, dict):
            raise InvalidResponseError("FotMob の応答形式が変更されています")
        return value

    async def get_build_id(self, client, force=False):
        if self.build_id and not force and time.monotonic() - self.build_fetched < 600:
            return self.build_id
        response = await client.get("/")
        self.check(response)
        found = re.search(r'"buildId"\s*:\s*"([A-Za-z0-9_-]+)"', response.text)
        if not found:
            raise InvalidResponseError("FotMob のページ構造が変更され、試合データを取得できませんでした")
        self.build_id, self.build_fetched = found[1], time.monotonic()
        return self.build_id

    async def get_match(self, client, match_id):
        # Refresh once for a stale Next.js deploy. Denials and limits are never retried.
        for attempt in range(2):
            build = await self.get_build_id(client, force=attempt > 0)
            try:
                redirect = await self.request_json(client, f"/_next/data/{build}/match/{match_id}.json")
                props = redirect.get("pageProps")
                if not isinstance(props, dict):
                    raise InvalidResponseError("FotMob の試合応答に pageProps がありません")
                # Current deployments may render the legacy match route directly
                # instead of redirecting it to the canonical slug page.
                if isinstance(props.get("general"), dict) and props["general"].get("matchId"):
                    return props
                target = props.get("__N_REDIRECT", "")
                if not isinstance(target, str):
                    raise InvalidResponseError("FotMob の試合リダイレクト形式が変更されています")
                slug = target.split("#", 1)[0].removeprefix("/matches/")
                if not target.startswith("/matches/") or not re.fullmatch(r"[a-zA-Z0-9_/-]+", slug) or ".." in slug:
                    raise NotFoundError("FotMob に指定された試合が見つかりませんでした")
                data = await self.request_json(client, f"/_next/data/{build}/matches/{slug}.json")
                props = data.get("pageProps")
                if not isinstance(props, dict) or not props.get("general"):
                    raise InvalidResponseError("FotMob の試合応答に general がありません")
                return props
            except NotFoundError:
                if attempt:
                    raise

    async def fetch(self, query: Query):
        key = (query.kind, query.id, query.date, query.timezone)
        cached = self.cache.get(key)
        if cached and time.monotonic() - cached[0] < self.cache_seconds:
            self.cache.move_to_end(key)
            return copy.deepcopy(cached[1]), cached[2]
        try:
            async with asyncio.timeout(query.timeout):
                async with httpx.AsyncClient(base_url=BASE_URL, timeout=query.timeout, transport=self.transport,
                                            follow_redirects=True, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/html"}) as client:
                    if query.kind == "match":
                        data = await self.get_match(client, query.id)
                    elif query.kind == "date":
                        data = await self.request_json(client, "/api/data/matches", {"date": query.date.replace("-", ""), "timezone": query.timezone})
                    elif query.kind == "team":
                        data = await self.request_json(client, "/api/data/teams", {"id": query.id})
                    else:
                        data = await self.request_json(client, "/api/data/leagues", {"id": query.id, "tab": "overview"})
        except (TimeoutError, httpx.TimeoutException):
            raise RequestTimeoutError(f"{query.timeout:g} 秒以内に FotMob の応答がありませんでした")
        except httpx.RequestError:
            raise NetworkError("FotMob に接続できませんでした。ネットワーク接続を確認してください")
        from datetime import datetime, timezone
        fetched_at = datetime.now(timezone.utc).isoformat()
        self.cache[key] = (time.monotonic(), copy.deepcopy(data), fetched_at)
        while len(self.cache) > 128:
            self.cache.popitem(last=False)
        return data, fetched_at
