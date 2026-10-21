"""Replaceable web-search adapters. Disabled unless OMNI_SEARCH_PROVIDER is set.
Results are untrusted text: callers must label them as such and never treat them as instructions."""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, unquote, urlparse

import httpx

USER_AGENT = "OMNI/1.0 (personal assistant; https://github.com/deathlife613-hash/omni-public)"


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


async def _fetch(method: str, url: str, transport, timeout: float, **kw) -> httpx.Response:
    kw.setdefault("headers", {})
    kw["headers"] = {"User-Agent": USER_AGENT, **kw["headers"]}
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
    return r


async def _get_json(method: str, url: str, transport, timeout: float, **kw) -> dict:
    r = await _fetch(method, url, transport, timeout, **kw)
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


class _DdgParser(HTMLParser):
    """Pulls result links + snippets out of html.duckduckgo.com/html/ (an unofficial, scraped page)."""

    def __init__(self):
        super().__init__()
        self.items: list[dict] = []
        self._field: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "a" and "result__a" in cls:
            self.items.append({"url": a.get("href") or "", "title": "", "snippet": ""})
            self._field = "title"
        elif "result__snippet" in cls and self.items:
            self._field = "snippet"

    def handle_endtag(self, tag):
        if tag in ("a", "td", "div", "span"):
            self._field = None

    def handle_data(self, data):
        if self._field and self.items:
            self.items[-1][self._field] += data


def _ddg_url(href: str) -> str:
    """DuckDuckGo wraps result links as //duckduckgo.com/l/?uddg=<encoded target>."""
    if href.startswith("//"):
        href = "https:" + href
    q = parse_qs(urlparse(href).query)
    return unquote(q["uddg"][0]) if "uddg" in q else href


class DuckDuckGoSearch(SearchProvider):
    """No signup, no key. Scrapes DuckDuckGo's HTML endpoint: unofficial, may be rate limited or blocked
    from datacenter IPs, and can break if DuckDuckGo changes the page. Use `auto` for a fallback."""

    name = "duckduckgo"

    def __init__(self, timeout: float = 15, transport=None):
        self.timeout, self.transport = timeout, transport

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        r = await _fetch(
            "POST", "https://html.duckduckgo.com/html/", self.transport, self.timeout, data={"q": query}
        )
        # DuckDuckGo answers 202 (or a challenge page) when it suspects automation.
        if r.status_code == 202 or "anomaly" in r.text[:5000].lower():
            raise SearchError("rate_limit", "DuckDuckGo is limiting automated searches right now. Try later.")
        parser = _DdgParser()
        parser.feed(r.text)
        results = [SearchResult(i["title"], _ddg_url(i["url"]), i["snippet"]) for i in parser.items]
        results = _clean(results)[:limit]
        if not results:
            raise SearchError("unavailable", "DuckDuckGo returned no parsable results (the page format may have changed).")
        return results


_TAGS = re.compile(r"<[^>]+>")


class WikipediaSearch(SearchProvider):
    """Official MediaWiki search API: free, no key, reliable - but encyclopedia articles only."""

    name = "wikipedia"

    def __init__(self, timeout: float = 15, transport=None):
        self.timeout, self.transport = timeout, transport

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        data = await _get_json(
            "GET", "https://en.wikipedia.org/w/api.php", self.transport, self.timeout,
            params={"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json", "utf8": 1},
        )
        out = []
        for x in data.get("query", {}).get("search", [])[:limit]:
            title = x.get("title", "")
            snippet = _TAGS.sub("", x.get("snippet", "")).replace("&quot;", '"').replace("&amp;", "&")
            out.append(SearchResult(title, "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_")), snippet))
        return _clean(out)


class FallbackSearch(SearchProvider):
    """Tries providers in order; moves on only when one fails with a SearchError."""

    name = "auto"

    def __init__(self, providers: list[SearchProvider]):
        self.providers = providers
        self.last_used: str | None = None

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        last: SearchError | None = None
        for p in self.providers:
            try:
                results = await p.search(query, limit)
            except SearchError as e:
                last = e
                continue
            if results:
                self.last_used = p.name
                return results
        raise last or SearchError("unavailable", "No search source returned results.")


def build_search(settings, transport=None) -> SearchProvider:
    p = settings.search_provider.lower()
    if not p:
        raise SearchError("disabled", "Web search is disabled (OMNI_SEARCH_PROVIDER is empty).")
    if p == "duckduckgo":
        return DuckDuckGoSearch(transport=transport)
    if p == "wikipedia":
        return WikipediaSearch(transport=transport)
    if p == "auto":
        return FallbackSearch([DuckDuckGoSearch(transport=transport), WikipediaSearch(transport=transport)])
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
