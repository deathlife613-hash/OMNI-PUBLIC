"""Drives the real UI in headless Chromium against e2e/server.py. Exits non-zero on any failure.

Usage:  python e2e/ui_test.py [URL] [--only agents,skills,...]
Groups: dashboard chat memory tools agents skills settings backup mobile
On any failure it writes e2e-artifacts/ (full error, screenshot, page text/HTML, API state, trace.zip) and prints
the first failure's details, so one run is enough to see WHICH control failed and what the backend looked like.
Every run uses unique names (RUN suffix) so a re-run against the same server cannot collide with older data;
start a fresh server anyway (`fuser -k 8765/tcp`) for a clean DB.
"""
import json
import os
import re
import sys
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ARGS = [a for a in sys.argv[1:]]
ONLY = set()
if "--only" in ARGS:
    i = ARGS.index("--only")
    ONLY = set(ARGS[i + 1].split(","))
    del ARGS[i : i + 2]
URL = ARGS[0] if ARGS else "http://127.0.0.1:8765"
ARTIFACTS = Path(os.environ.get("E2E_ARTIFACTS", "e2e-artifacts"))
RUN = uuid.uuid4().hex[:6]  # hex has no 'o', so goals below never accidentally contain "code"
GOAL_PLAN = f"plan my week {RUN}"
GOAL_CODE = f"change the code {RUN}"
MEMORY = f"My cat is named Pixel {RUN}"
TASK = f"Pay rent {RUN}"


def wanted(group: str) -> bool:
    return not ONLY or group in ONLY


results = []
failures = []  # (name, full detail)
SKILL = {
    "name": f"tidy-notes-{RUN}", "version": "1.0.0", "description": "Rewrites rough notes into a tidy bullet list.",
    "trigger": "When the user pastes messy notes", "inputs": [{"name": "text", "type": "string"}],
    "prompt_template": "Rewrite these notes as short bullet points:\n{{text}}",
    "tests": [{"inputs": {"text": "buy milk"}, "expect_contains": ["buy milk"]}],
}


PAGE = None  # set once the browser is up
CURRENT = "dashboard"


def section(g: str) -> None:
    global CURRENT
    CURRENT = g


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]


def diagnose(name: str, detail: str) -> None:
    """Capture everything needed to tell which control failed and what the backend held at that moment."""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    parts = [f"STEP: {name}", f"URL: {PAGE.url if PAGE else '?'}", "", "FULL ERROR:", detail, ""]
    try:
        parts += ["PAGE TEXT (first 3000 chars):", PAGE.inner_text("body")[:3000], ""]
        (ARTIFACTS / f"{slug(name)}.html").write_text(PAGE.content())
        PAGE.screenshot(path=str(ARTIFACTS / f"{slug(name)}.png"), full_page=True)
    except Exception as e:  # noqa: BLE001
        parts.append(f"(could not capture page: {e})")
    for api in ("/api/status", "/api/skills", "/api/agents/tasks", "/api/agents/approvals"):
        try:
            r = PAGE.request.get(URL + api)
            parts += [f"GET {api} -> {r.status}", r.text()[:2500], ""]
        except Exception as e:  # noqa: BLE001
            parts.append(f"GET {api} failed: {e}")
    (ARTIFACTS / f"{slug(name)}.txt").write_text("\n".join(parts))


def step(name, fn):
    if not wanted(CURRENT):
        return
    try:
        fn()
        results.append((name, "PASS", ""))
    except Exception as e:  # noqa: BLE001
        detail = str(e)
        short = " | ".join(line.strip() for line in detail.splitlines() if line.strip())[:600]  # keeps the Playwright call log
        results.append((name, "FAIL", short))
        failures.append((name, detail))
        diagnose(name, detail)


with sync_playwright() as p:
    b = p.chromium.launch()
    context = b.new_context()
    context.set_default_timeout(10000)  # fail in 10 s with the Playwright call log instead of hanging 30 s
    context.tracing.start(screenshots=True, snapshots=True)
    page = context.new_page()
    PAGE = page
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    dlg = []
    page.on("dialog", lambda d: (dlg.append(d.message), d.accept()))

    section("dashboard")
    step("dashboard shows backend connected", lambda: expect(page.get_by_role("status").first).to_contain_text("Backend connected", timeout=10000))
    step("dashboard shows usage + quick actions", lambda: (expect(page.get_by_text("Usage (since restart)")).to_be_visible(), expect(page.get_by_role("button", name="New chat")).to_be_visible()))

    section("chat")
    def chat():
        page.get_by_role("button", name="Chat", exact=True).click()
        page.get_by_label("Message", exact=True).fill("hello omni")
        page.get_by_role("button", name="Send").click()
        expect(page.locator(".bubble.assistant .text").first).to_have_text("Hello from OMNI", timeout=10000)
        expect(page.locator(".bubble.user .text").first).to_have_text("hello omni")
    step("chat: send message, streamed reply saved & shown", chat)

    def chat_search():
        page.get_by_label("Search the web for this message", exact=False).check()
        page.get_by_label("Message", exact=True).fill("news")
        page.get_by_role("button", name="Send").click()
        expect(page.get_by_role("link", name="Title A")).to_be_visible(timeout=10000)
    step("chat: web search shows source link", chat_search)

    step("chat: conversation listed in sidebar", lambda: expect(page.locator(".side li").first).to_contain_text("hello omni"))
    step("chat: test connection", lambda: (page.get_by_role("button", name="Test connection").click(), expect(page.get_by_text("Connected —")).to_be_visible(timeout=10000)))

    section("memory")
    def memory():
        page.get_by_role("button", name="Memory", exact=True).click()
        page.get_by_label("New memory", exact=True).fill(MEMORY)
        page.get_by_role("button", name="Add", exact=True).click()
        expect(page.get_by_text(MEMORY)).to_be_visible(timeout=5000)
    step("memory: add and list", memory)

    def memory_secret():
        page.get_by_label("New memory", exact=True).fill("password: hunter2")
        page.get_by_role("button", name="Add", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("never stores secrets", timeout=5000)
    step("memory: secret refused with clear message", memory_secret)

    section("tools")
    def tools():
        page.get_by_role("button", name="Tools", exact=True).click()
        page.get_by_label("Expression", exact=True).fill("2+3*4")
        page.get_by_role("button", name="=").click()
        expect(page.get_by_role("status").filter(has_text="14")).to_be_visible(timeout=5000)
        page.get_by_label("Task title", exact=True).fill(TASK)
        page.get_by_role("button", name="Add", exact=True).click()
        expect(page.get_by_text(TASK)).to_be_visible(timeout=5000)
    step("tools: calculator and task", tools)

    def delete_task():
        page.locator("li").filter(has_text=TASK).get_by_role("button", name="Delete").click()
        expect(page.get_by_text(TASK)).to_have_count(0, timeout=5000)
    step("tools: delete asks confirmation then deletes", lambda: (delete_task(), None if any("permanently" in m for m in dlg) else (_ for _ in ()).throw(AssertionError("no confirm dialog"))))


    section("agents")
    def agents_plain():
        page.get_by_role("button", name="Agents", exact=True).click()
        page.get_by_label("Agent goal", exact=True).fill(GOAL_PLAN)
        page.get_by_role("button", name="Start", exact=True).click()
        expect(page.get_by_text("Status: succeeded")).to_be_visible(timeout=15000)
        expect(page.get_by_text("Plan: step one.").first).to_be_visible()
        expect(page.get_by_text("Team summary: done.")).to_be_visible()
    step("agents: goal runs plan -> step -> summary", agents_plain)

    def agents_coding():
        page.get_by_label("Agent goal", exact=True).fill(GOAL_CODE)
        page.get_by_role("button", name="Start", exact=True).click()
        expect(page.get_by_role("heading", name="Waiting for your approval")).to_be_visible(timeout=15000)
        expect(page.locator("pre.diff").first).to_contain_text("+print('v2')")
    step("agents: coding step shows a diff awaiting approval (file untouched)", agents_coding)

    def task_row(goal):
        """The exact task's title button: scoped to the Tasks list and filtered by this run's unique goal text."""
        return page.locator('section[aria-label="Tasks"] li').filter(has_text=goal).get_by_role("button", name=goal)

    def agents_approve_revert():
        page.get_by_role("button", name="Approve & write file").click()
        expect(page.get_by_role("heading", name="Waiting for your approval")).to_have_count(0, timeout=10000)
        task_row(GOAL_CODE).click()
        expect(page.get_by_role("button", name="Revert")).to_be_visible(timeout=10000)
        page.get_by_role("button", name="src/app.py").click()
        expect(page.get_by_label("src/app.py")).to_contain_text("v2")
        page.get_by_role("button", name="Revert").click()
        page.get_by_role("button", name="src/app.py").click()
        expect(page.get_by_label("src/app.py")).to_contain_text("v1", timeout=10000)
    step("agents: approve writes file, revert restores it", agents_approve_revert)

    section("skills")
    def skills_flow():
        name = SKILL["name"]
        page.get_by_role("button", name="Skills", exact=True).click()
        page.get_by_label("Skill manifest JSON", exact=True).fill(json.dumps(SKILL))
        page.get_by_role("button", name="Stage manifest").click()
        sk = page.get_by_role("region", name=f"Skill {name}")  # this run's skill card only
        expect(sk.get_by_text("Validation passed")).to_be_visible(timeout=10000)
        expect(sk.get_by_text("not approved")).to_be_visible()
        sk.get_by_role("button", name="Approve & activate").click()
        expect(sk.get_by_text(f"active {SKILL['version']}")).to_be_visible(timeout=10000)
        sk.get_by_label(f"{name} text", exact=True).fill("buy milk")
        sk.get_by_role("button", name="Run", exact=True).click()
        expect(sk.get_by_text("- skill output")).to_be_visible(timeout=10000)
        sk.get_by_role("button", name="Disable").click()
        expect(sk.get_by_text("disabled")).to_be_visible(timeout=10000)
    step("skills: stage -> validate -> approve -> run -> disable", skills_flow)

    def skills_blocked():
        bad = dict(SKILL, name=f"net-skill-{RUN}", permissions={"network": True, "files": False, "use_memories": False})
        page.get_by_label("Skill manifest JSON", exact=True).fill(json.dumps(bad))
        page.get_by_role("button", name="Stage manifest").click()
        expect(page.get_by_text("Validation failed")).to_be_visible(timeout=10000)
        expect(page.get_by_role("region", name=f"Skill net-skill-{RUN}").get_by_role("button", name="Approve & activate")).to_have_count(0)
    step("skills: network-requesting skill cannot be approved", skills_blocked)

    section("settings")
    def settings_theme():
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_label("Theme", exact=True).select_option("light")
        assert page.evaluate("document.documentElement.dataset.theme") == "light"
    step("settings: theme switch", settings_theme)
    step("settings: security shows token state", lambda: expect(page.get_by_text("Not required (development only)")).to_be_visible())
    step("settings: audit shows tool activity", lambda: expect(page.get_by_text("calculator").first).to_be_visible(timeout=5000))

    section("backup")
    def backup_roundtrip():
        page.get_by_role("button", name="Memory", exact=True).click()
        with page.expect_download() as d:
            page.get_by_role("button", name="Download backup").click()
        assert d.value.suggested_filename.startswith("omni-backup-")
    step("memory: backup downloads", backup_roundtrip)

    section("mobile")
    page.set_viewport_size({"width": 375, "height": 700})
    step("mobile width: no horizontal overflow", lambda: (page.get_by_role("button", name="Dashboard", exact=True).click(), None if page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1") else (_ for _ in ()).throw(AssertionError("overflow"))))
    step("no uncaught page errors", lambda: None if not errors else (_ for _ in ()).throw(AssertionError(errors[0])))
    context.tracing.stop(path=str(ARTIFACTS / "trace.zip") if failures else None)
    if failures:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
    b.close()

for name, res, why in results:
    print(f"{res}  {name}" + (f"  -- {why}" if why else ""))
print(f"{sum(r == 'PASS' for _, r, _ in results)}/{len(results)} passed")
if failures:
    print(f"\n--- first failure in detail (all artifacts in {ARTIFACTS}/) ---")
    print(failures[0][0])
    print(failures[0][1][:2500])
    txt = ARTIFACTS / f"{slug(failures[0][0])}.txt"
    if txt.exists():
        print("\n--- backend/page state at that moment ---")
        print(txt.read_text().split("PAGE TEXT", 1)[-1][:3500])
sys.exit(0 if all(r == "PASS" for _, r, _ in results) else 1)
