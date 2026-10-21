# OMNI release checklist (v1.0.0-rc1)

Honest status. **PASS** = automated test or scripted run actually passed (Google Colab, Python 3.13, Node 20, headless
Chromium). **NOT TESTED** = never executed. **NOT IMPLEMENTED** = not built. Nothing is marked PASS from reading code.

## Spec acceptance criteria (section 14)
### Basic operation
| Criterion | Result |
|---|---|
| App starts with documented commands (`uvicorn`) | PASS (Colab, real server) |
| Frontend ↔ backend communicate | PASS (e2e, headless browser) |
| Health checks work | PASS |
| Errors presented clearly | PASS (tests + e2e for secret refusal, provider/search/quota errors) |
### AI
| Criterion | Result |
|---|---|
| A configured free hosted model answers a message | PASS — reported from a Colab run 2026-10-20 (Groq; test ok, 11 models, 421 ms; streamed replies from allam-2-7b and openai/gpt-oss-120b). Not re-run by me in this session |
| Model request made by backend, not frontend | PASS (architecture + tests; frontend never receives keys) |
| Secrets never in bundles/logs | PASS for status/provider APIs and error messages (tests); bundle not grepped for keys — NOT TESTED |
| Unavailable model / exhausted quota → useful error | PASS (mocked 429/402/5xx/timeout) |
| Manual free fallback works only when available | NOT IMPLEMENTED (OpenRouter `:free` is a manual alternative provider; no automatic fallback by design) |
| No paid provider contacted by default | PASS (paid models blocked before any HTTP call; test) |
| Non-AI features work when every provider is unavailable | PASS (test) |
### Memory
| Criterion | Result |
|---|---|
| Conversations survive restarts (persistent storage) | PASS (test with new app object, same DB file) |
| Memories viewed/edited/deleted | PASS (tests + e2e add/list) |
| Export and restore | PASS (API tests, e2e download); restore UI NOT TESTED in browser |
### Voice
| Criterion | Result |
|---|---|
| Voice input works in a supported environment | **NOT TESTED** (no microphone in test environment) |
| Speech output can be disabled | NOT TESTED in browser (logic only) |
| Text interface usable if voice fails | PASS (voice is a separate component; e2e ran in a browser without speech support) |
### Tools
| Criterion | Result |
|---|---|
| Tools validate inputs | PASS |
| Restricted operations require permission | PASS (confirm flag, approvals) |
| Destructive operations require confirmation | PASS (API + e2e) |
| Unauthorized filesystem access blocked | PASS (traversal, symlink, secret names, type allowlist) |
### Deployment
| Criterion | Result |
|---|---|
| Env variables documented | PASS (`.env.example`, `docs/DEPLOYMENT.md`) |
| Secrets excluded from VCS | PASS by `.gitignore`; no key ever entered in this project |
| Database persistence documented | PASS (honest warning about ephemeral hosts) |
| App can be migrated using the guide | NOT TESTED (backup/restore API tested; no real migration performed) |
| Free-tier limitations documented honestly | PASS (`docs/FREE_SERVICES_RESEARCH.md`; many providers only secondarily sourced — see its notes) |
| Docker image builds / compose works | **NOT TESTED** |
| Real deployment | **NOT TESTED** |
### Quality
| Criterion | Result |
|---|---|
| Automated tests run successfully | PASS (153 backend, 7 frontend unit, 19 browser e2e steps) |
| Failures logged safely | PASS (audit log has no arguments/secrets) |
| No fake success messages | PASS to the extent tested; unavailable metrics shown as unavailable |
| README has complete setup guide | PASS |

## Agent acceptance tests (section 10A-F)
| Criterion | Result |
|---|---|
| Bounded steps and model calls | PASS |
| Quota exhaustion pauses without losing state | PASS |
| Parallel execution respects limits | NOT APPLICABLE — parallel execution NOT IMPLEMENTED (sequential only) |
| Agents cannot escape the workspace | PASS |
| Coding changes show a diff and can be rejected | PASS |
| Dangerous commands require approval/constrained | PASS by absence: no command execution exists |
| New skills tested and inactive until approved | PASS |
| Skill permissions cannot be self-expanded | PASS |
| Failed tests reported as failures | PASS (skill tests); "run project tests" NOT IMPLEMENTED |
| Useful with only one free model configured | PASS by design (one model, sequential) |

## Known gaps / not built
- Wake word; local Whisper; Ollama & Hugging Face adapters; automatic provider fallback; conversation summarization;
  Markdown/code rendering with copy buttons in chat (plain text + Copy button only); PWA install; hosted-DB backend;
  parallel agents; command execution / test running / Git integration; code-executing skills; Testing/DevOps agents.
- Plan-JSON reliability of the free model for agents is unknown until tried with a real model.
- Reminders only fire while the app is open.

## How to verify yourself (≈10 minutes)
1. `docs/DEPLOYMENT.md` → run locally per README.
2. Add your Groq key to `.env` (server only). Chat → Test connection → Choose model → send a message.
3. Memory tab: add a memory, ask about it in chat. Download a backup, restore it.
4. Tools: add a reminder 1 minute ahead; keep the tab open.
5. Agents: set `OMNI_WORKSPACE_DIR` to a throwaway folder; give a coding goal; review the diff; approve; revert.
