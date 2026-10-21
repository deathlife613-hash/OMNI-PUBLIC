import asyncio
import json

import httpx
import pytest

from app.services.search import SearchError, SearxngSearch, TavilySearch, build_search
from app.core.config import Settings
from tests.conftest import FakeProvider, FakeSearch


def run(coro):
    return asyncio.run(coro)


def tavily(handler):
    return TavilySearch("KEY", transport=httpx.MockTransport(handler))


def test_tavily_request_and_parsing():
    seen = {}

    def h(req):
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"results": [
            {"title": "T", "url": "https://x.example", "content": "c" * 900},
            {"title": "bad", "url": "javascript:alert(1)", "content": "x"},
        ]})

    res = run(tavily(h).search("hello", 3))
    assert seen["auth"] == "Bearer KEY" and seen["body"]["max_results"] == 3
    assert len(res) == 1 and res[0].url == "https://x.example" and len(res[0].snippet) == 500  # unsafe URL dropped, text bounded


@pytest.mark.parametrize("status,kind", [(401, "auth"), (429, "rate_limit"), (432, "rate_limit"), (500, "unavailable")])
def test_tavily_errors_map_clearly(status, kind):
    with pytest.raises(SearchError) as e:
        run(tavily(lambda r: httpx.Response(status, json={})).search("q", 3))
    assert e.value.kind == kind and "KEY" not in e.value.message


def test_timeout_maps():
    def h(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(SearchError) as e:
        run(tavily(h).search("q", 3))
    assert e.value.kind == "timeout"


def test_searxng_parsing():
    def h(req):
        assert req.url.params["format"] == "json" and req.url.params["q"] == "cats"
        return httpx.Response(200, json={"results": [{"title": "Cats", "url": "https://c.example", "content": "meow"}]})

    res = run(SearxngSearch("https://s.example/", transport=httpx.MockTransport(h)).search("cats", 5))
    assert res[0].title == "Cats"


def test_build_search_states():
    with pytest.raises(SearchError) as e:
        build_search(Settings(_env_file=None, search_provider=""))
    assert e.value.kind == "disabled"
    with pytest.raises(SearchError) as e:
        build_search(Settings(_env_file=None, search_provider="tavily"))
    assert e.value.kind == "not_configured"
    assert build_search(Settings(_env_file=None, search_provider="tavily", search_api_key="k")).name == "tavily"


def test_search_endpoint_disabled_by_default(make_client):
    c = make_client()
    r = c.post("/api/search", json={"query": "x"})
    assert r.status_code == 503 and r.json()["detail"]["kind"] == "disabled"
    assert c.get("/api/search/status").json()["configured"] is False


def test_search_endpoint_returns_sources_and_caches(make_client):
    fake = FakeSearch()
    c = make_client(search=fake)
    for _ in range(3):
        assert c.post("/api/search", json={"query": "Same Query"}).json()["results"][0]["url"] == "https://a.example/x"
    assert fake.calls == 1  # repeats served from cache
    st = c.get("/api/search/status").json()
    assert st["used_today"] == 1 and st["cache_hits"] == 2


def test_daily_cap_blocks_without_calling_provider(make_client):
    fake = FakeSearch()
    c = make_client(search=fake, search_daily_cap=2)
    for q in ("a", "b"):
        assert c.post("/api/search", json={"query": q}).status_code == 200
    r = c.post("/api/search", json={"query": "c"})
    assert r.status_code == 409 and r.json()["detail"]["kind"] == "daily_cap"
    assert fake.calls == 2


def test_failed_search_is_not_counted(make_client):
    c = make_client(search=FakeSearch(error=SearchError("rate_limit", "used up")))
    assert c.post("/api/search", json={"query": "q"}).status_code == 502
    assert c.get("/api/search/status").json()["used_today"] == 0


def _events(text):
    out = []
    for block in text.strip().split("\n\n"):
        ev, data = block.split("\n", 1)
        out.append((ev[7:], json.loads(data[6:])))
    return out


def chat(c, use_search, text="latest news"):
    cid = c.post("/api/conversations", json={}).json()["id"]
    return _events(c.post(f"/api/conversations/{cid}/messages", json={"content": text, "use_search": use_search}).text)


def test_chat_with_search_injects_results_as_untrusted_and_returns_sources(make_client):
    prov = FakeProvider()
    c2 = make_client(provider=prov, search=FakeSearch(), ai_model="m1")
    evs = chat(c2, True)
    system = prov.calls[0][0][0].content
    assert "UNTRUSTED" in system and "https://a.example/x" in system
    assert evs[-1][0] == "done" and evs[-1][1]["sources"] == [{"title": "Title A", "url": "https://a.example/x"}]


def test_chat_without_search_toggle_never_searches(make_client):
    prov, fake = FakeProvider(), FakeSearch()
    c = make_client(provider=prov, search=fake, ai_model="m1")
    evs = chat(c, False)
    assert fake.calls == 0 and "Web search results retrieved" not in prov.calls[0][0][0].content
    assert evs[-1][1]["sources"] == []


def test_chat_search_failure_is_reported_and_chat_still_answers(make_client):
    c = make_client(provider=FakeProvider(), search=FakeSearch(error=SearchError("rate_limit", "used up")), ai_model="m1")
    evs = chat(c, True)
    kinds = [e for e, _ in evs]
    assert kinds[0] == "notice" and "without web results" in evs[0][1]["message"]
    assert kinds[-1] == "done" and evs[-1][1]["sources"] == []


def test_chat_search_when_not_configured_is_reported(make_client):
    c = make_client(provider=FakeProvider(), ai_model="m1")
    evs = chat(c, True)
    assert evs[0][0] == "notice" and evs[0][1]["kind"] == "disabled" and evs[-1][0] == "done"


def test_search_routes_require_auth(make_client):
    c = make_client(access_token="tok")
    assert c.post("/api/search", json={"query": "x"}).status_code == 401
    assert c.get("/api/search/status").status_code == 401


# ---- no-signup search (DuckDuckGo scrape, Wikipedia API, auto fallback) ----
import httpx  # noqa: E402

from app.services.search import DuckDuckGoSearch, FallbackSearch, WikipediaSearch  # noqa: E402

DDG_HTML = """
<div class="result"><h2><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa%3Fx%3D1&rut=abc">Example <b>A</b></a></h2>
<a class="result__snippet" href="x">First snippet <b>text</b></a></div>
<div class="result"><h2><a class="result__a" href="javascript:alert(1)">Bad link</a></h2>
<a class="result__snippet">ignored</a></div>
<div class="result"><h2><a class="result__a" href="https://direct.example.org/b">Direct B</a></h2>
<a class="result__snippet">Second snippet</a></div>
"""


def run_(coro):
    import asyncio

    return asyncio.run(coro)


def test_duckduckgo_parses_results_decodes_redirects_and_drops_non_http():
    seen = {}

    def handler(req: httpx.Request):
        seen["method"], seen["body"], seen["ua"] = req.method, req.content.decode(), req.headers["user-agent"]
        return httpx.Response(200, text=DDG_HTML)

    res = run_(DuckDuckGoSearch(transport=httpx.MockTransport(handler)).search("hello world", 5))
    assert [r.url for r in res] == ["https://example.com/a?x=1", "https://direct.example.org/b"]
    assert res[0].title == "Example A" and res[0].snippet == "First snippet text"
    assert seen["method"] == "POST" and "q=hello+world" in seen["body"] and "OMNI" in seen["ua"]


def test_duckduckgo_challenge_and_format_change_are_reported_not_faked():
    with pytest.raises(SearchError) as e:
        run_(DuckDuckGoSearch(transport=httpx.MockTransport(lambda r: httpx.Response(202, text=""))).search("q", 5))
    assert e.value.kind == "rate_limit"
    with pytest.raises(SearchError) as e:
        run_(DuckDuckGoSearch(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>nothing</html>"))).search("q", 5))
    assert e.value.kind == "unavailable"


def test_wikipedia_results_have_clean_snippets_and_encoded_urls():
    def handler(req):
        assert req.url.params["srsearch"] == "alan turing" and req.url.params["action"] == "query"
        return httpx.Response(200, json={"query": {"search": [
            {"title": "Alan Turing", "snippet": 'English <span class="searchmatch">mathematician</span> &amp; more'},
            {"title": "Turing (disambiguation)", "snippet": "x"},
        ]}})

    res = run_(WikipediaSearch(transport=httpx.MockTransport(handler)).search("alan turing", 5))
    assert res[0].url == "https://en.wikipedia.org/wiki/Alan_Turing" and res[0].snippet == "English mathematician & more"
    assert res[1].url.endswith("Turing_%28disambiguation%29")


def test_auto_falls_back_only_on_failure_and_reports_when_all_fail():
    good = FakeSearch()
    bad = FakeSearch(error=SearchError("rate_limit", "blocked"))
    both_bad = FallbackSearch([bad, FakeSearch(error=SearchError("unavailable", "down"))])
    f = FallbackSearch([bad, good])
    assert run_(f.search("q", 3))[0].url == "https://a.example/x" and f.last_used == "fakesearch"
    assert bad.calls == 1 and good.calls == 1
    primary_ok = FakeSearch()
    run_(FallbackSearch([primary_ok, good]).search("q", 3))
    assert good.calls == 1  # second provider untouched when the first succeeds
    with pytest.raises(SearchError) as e:
        run_(both_bad.search("q", 3))
    assert e.value.kind == "unavailable"


def test_search_works_out_of_the_box_by_default_setting():
    assert Settings(_env_file=None).search_provider == "auto"
    assert build_search(Settings(_env_file=None)).name == "auto"
    assert build_search(Settings(_env_file=None, search_provider="duckduckgo")).name == "duckduckgo"
