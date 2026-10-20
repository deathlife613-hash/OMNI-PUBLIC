"""Drives the real UI in headless Chromium against e2e/server.py. Exits non-zero on any failure."""
import sys

from playwright.sync_api import expect, sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
results = []
SKILL = {
    "name": "tidy-notes", "version": "1.0.0", "description": "Rewrites rough notes into a tidy bullet list.",
    "trigger": "When the user pastes messy notes", "inputs": [{"name": "text", "type": "string"}],
    "prompt_template": "Rewrite these notes as short bullet points:\n{{text}}",
    "tests": [{"inputs": {"text": "buy milk"}, "expect_contains": ["buy milk"]}],
}


def step(name, fn):
    try:
        fn()
        results.append((name, "PASS", ""))
    except Exception as e:  # noqa: BLE001
        results.append((name, "FAIL", str(e).splitlines()[0][:160]))


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    dlg = []
    page.on("dialog", lambda d: (dlg.append(d.message), d.accept()))

    step("dashboard shows backend connected", lambda: expect(page.get_by_role("status").first).to_contain_text("Backend connected", timeout=10000))
    step("dashboard shows usage + quick actions", lambda: (expect(page.get_by_text("Usage (since restart)")).to_be_visible(), expect(page.get_by_role("button", name="New chat")).to_be_visible()))

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

    def memory():
        page.get_by_role("button", name="Memory", exact=True).click()
        page.get_by_label("New memory", exact=True).fill("My cat is named Pixel")
        page.get_by_role("button", name="Add", exact=True).click()
        expect(page.get_by_text("My cat is named Pixel")).to_be_visible(timeout=5000)
    step("memory: add and list", memory)

    def memory_secret():
        page.get_by_label("New memory", exact=True).fill("password: hunter2")
        page.get_by_role("button", name="Add", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("never stores secrets", timeout=5000)
    step("memory: secret refused with clear message", memory_secret)

    def tools():
        page.get_by_role("button", name="Tools", exact=True).click()
        page.get_by_label("Expression", exact=True).fill("2+3*4")
        page.get_by_role("button", name="=").click()
        expect(page.get_by_role("status").filter(has_text="14")).to_be_visible(timeout=5000)
        page.get_by_label("Task title", exact=True).fill("Pay rent")
        page.get_by_role("button", name="Add", exact=True).click()
        expect(page.get_by_text("Pay rent")).to_be_visible(timeout=5000)
    step("tools: calculator and task", tools)

    def delete_task():
        page.get_by_role("button", name="Delete").first.click()
        expect(page.get_by_text("Pay rent")).to_have_count(0, timeout=5000)
    step("tools: delete asks confirmation then deletes", lambda: (delete_task(), None if any("permanently" in m for m in dlg) else (_ for _ in ()).throw(AssertionError("no confirm dialog"))))


    def agents_plain():
        page.get_by_role("button", name="Agents", exact=True).click()
        page.get_by_label("Agent goal", exact=True).fill("plan my week")
        page.get_by_role("button", name="Start", exact=True).click()
        expect(page.get_by_text("Status: succeeded")).to_be_visible(timeout=15000)
        expect(page.get_by_text("Plan: step one.").first).to_be_visible()
        expect(page.get_by_text("Team summary: done.")).to_be_visible()
    step("agents: goal runs plan -> step -> summary", agents_plain)

    def agents_coding():
        page.get_by_label("Agent goal", exact=True).fill("change the code")
        page.get_by_role("button", name="Start", exact=True).click()
        expect(page.get_by_role("heading", name="Waiting for your approval")).to_be_visible(timeout=15000)
        expect(page.locator("pre.diff").first).to_contain_text("+print('v2')")
    step("agents: coding step shows a diff awaiting approval (file untouched)", agents_coding)

    def agents_approve_revert():
        page.get_by_role("button", name="Approve & write file").click()
        expect(page.get_by_role("heading", name="Waiting for your approval")).to_have_count(0, timeout=10000)
        page.get_by_role("button", name="change the code").click()
        expect(page.get_by_role("button", name="Revert")).to_be_visible(timeout=10000)
        page.get_by_role("button", name="src/app.py").click()
        expect(page.get_by_label("src/app.py")).to_contain_text("v2")
        page.get_by_role("button", name="Revert").click()
        page.get_by_role("button", name="src/app.py").click()
        expect(page.get_by_label("src/app.py")).to_contain_text("v1", timeout=10000)
    step("agents: approve writes file, revert restores it", agents_approve_revert)

    def skills_flow():
        import json as _j
        page.get_by_role("button", name="Skills", exact=True).click()
        page.get_by_label("Skill manifest JSON", exact=True).fill(_j.dumps(SKILL))
        page.get_by_role("button", name="Stage manifest").click()
        expect(page.get_by_text("Validation passed")).to_be_visible(timeout=10000)
        expect(page.get_by_text("not approved")).to_be_visible()
        page.get_by_role("button", name="Approve & activate").click()
        expect(page.get_by_text("active 1.0.0")).to_be_visible(timeout=10000)
        page.get_by_label("tidy-notes text", exact=True).fill("buy milk")
        page.get_by_role("button", name="Run", exact=True).click()
        expect(page.get_by_text("- skill output")).to_be_visible(timeout=10000)
        page.get_by_role("button", name="Disable").click()
        expect(page.get_by_text("disabled")).to_be_visible(timeout=10000)
    step("skills: stage -> validate -> approve -> run -> disable", skills_flow)

    def skills_blocked():
        import json as _j
        bad = dict(SKILL, name="net-skill", permissions={"network": True, "files": False, "use_memories": False})
        page.get_by_label("Skill manifest JSON", exact=True).fill(_j.dumps(bad))
        page.get_by_role("button", name="Stage manifest").click()
        expect(page.get_by_text("Validation failed")).to_be_visible(timeout=10000)
        expect(page.get_by_role("region", name="Skill net-skill").get_by_role("button", name="Approve & activate")).to_have_count(0)
    step("skills: network-requesting skill cannot be approved", skills_blocked)

    def settings_theme():
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_label("Theme", exact=True).select_option("light")
        assert page.evaluate("document.documentElement.dataset.theme") == "light"
    step("settings: theme switch", settings_theme)
    step("settings: security shows token state", lambda: expect(page.get_by_text("Not required (development only)")).to_be_visible())
    step("settings: audit shows tool activity", lambda: expect(page.get_by_text("calculator").first).to_be_visible(timeout=5000))

    def backup_roundtrip():
        page.get_by_role("button", name="Memory", exact=True).click()
        with page.expect_download() as d:
            page.get_by_role("button", name="Download backup").click()
        assert d.value.suggested_filename.startswith("omni-backup-")
    step("memory: backup downloads", backup_roundtrip)

    page.set_viewport_size({"width": 375, "height": 700})
    step("mobile width: no horizontal overflow", lambda: (page.get_by_role("button", name="Dashboard", exact=True).click(), None if page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1") else (_ for _ in ()).throw(AssertionError("overflow"))))
    step("no uncaught page errors", lambda: None if not errors else (_ for _ in ()).throw(AssertionError(errors[0])))
    b.close()

for name, res, why in results:
    print(f"{res}  {name}" + (f"  -- {why}" if why else ""))
print(f"{sum(r == 'PASS' for _, r, _ in results)}/{len(results)} passed")
sys.exit(0 if all(r == "PASS" for _, r, _ in results) else 1)
