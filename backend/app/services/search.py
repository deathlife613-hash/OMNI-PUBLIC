"""Replaceable web-search adapters. Disabled unless OMNI_SEARCH_PROVIDER is set.
Results are untrusted text: callers must label them as such and never treat them as instructions."""
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx


class SearchError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind, self.message = kind, message


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchProvider(ABC):
    name: str

    @abstractmethod
    async def search(self, query: str, limit: int) -> list[SearchResult]: ...


def _clean(results: list[SearchResult]) -> list[SearchResult]:
    out = []
    for r in results:
        if r.url.startswith(("http://", "https://")):
            out.append(SearchResult(r.title.strip()[:200], r.url, r.snippet.strip()[:500]))
    return out


async def _get_json(method: str, url: str, transport, timeout: float, **kw) -> dict:
    try:
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as c:
            r = await c.request(method, url, **kw)
    except httpx.TimeoutException:
        raise SearchError("timeout", "The search service timed out.") from None
    except httpx.HTTPError:
        raise SearchError("unavailable", "Could not reach the search service.") from None
    if r.status_code in (401, 403):
        raise SearchError("auth", "The search service rejected the API key.")
    if r.status_code in (429, 432, 433):
        raise SearchError("rate_limit", "The search service's free allowance is used up or rate limited. Try later.")
    if r.status_code >= 400:
        raise SearchError("unavailable", f"The search service returned an error ({r.status_code}).")
    try:
        return r.json()
    except ValueError:
        raise SearchError("unavailable", "The search service returned an unreadable response.") from None


class TavilySearch(SearchProvider):
    """https://docs.tavily.com — free plan: 1,000 credits/month, no card (verified 2026-10-20). One basic search = 1 credit."""

    name = "tavily"

    def __init__(self, api_key: str, timeout: float = 15, transport=None):
        self.api_key, self.timeout, self.transport = api_key, timeout, transport

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        data = await _get_json(
            "POST", "https://api.tavily.com/search", self.transport, self.timeout,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"query": query, "max_results": limit, "search_depth": "basic"},
        )
        return _clean([SearchResult(x.get("title", ""), x.get("url", ""), x.get("content", "")) for x in data.get("results", [])][:limit])


class SearxngSearch(SearchProvider):
    """Self-hosted SearXNG (free software). Needs the JSON format enabled on your instance."""

    name = "searxng"

    def __init__(self, base_url: str, timeout: float = 15, transport=None):
        self.base_url, self.timeout, self.transport = base_url.rstrip("/"), timeout, transport

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        data = await _get_json("GET", f"{self.base_url}/search", self.transport, self.timeout, params={"q": query, "format": "json"})
        return _clean([SearchResult(x.get("title", ""), x.get("url", ""), x.get("content", "")) for x in data.get("results", [])][:limit])


def build_search(settings, transport=None) -> SearchProvider:
    p = settings.search_provider.lower()
    if not p:
        raise SearchError("disabled", "Web search is not configured. Set OMNI_SEARCH_PROVIDER (tavily or searxng).")
    if p == "tavily":
        if not settings.search_api_key:
            raise SearchError("not_configured", "Tavily needs OMNI_SEARCH_API_KEY.")
        return TavilySearch(settings.search_api_key, transport=transport)
    if p == "searxng":
        if not settings.search_base_url:
            raise SearchError("not_configured", "SearXNG needs OMNI_SEARCH_BASE_URL.")
        return SearxngSearch(settings.search_base_url, transport=transport)
    raise SearchError("unsupported", f"Unknown search provider '{settings.search_provider}'.")


class SearchGuard:
    """Caches repeat queries (in memory) and enforces a daily cap so the free allowance isn't burned."""

    def __init__(self):
        self.cache: dict[str, tuple[float, list[SearchResult]]] = {}
        self.cache_hits = 0
        self.searches = 0

    def get(self, key: str, now: float, ttl: float):
        hit = self.cache.get(key)
        if hit and now - hit[0] < ttl:
            self.cache_hits += 1
            return hit[1]
        return None

    def put(self, key: str, now: float, results: list[SearchResult]) -> None:
        if len(self.cache) > 200:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = (now, results)
