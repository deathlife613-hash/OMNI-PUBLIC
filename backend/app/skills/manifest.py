"""Declarative skills: a validated prompt template + input schema + declared permissions + tests.
Skills contain NO code and cannot execute anything, so they cannot touch files, the network, secrets,
logging, approvals or the model router. Validation here is the gate before a human sees them."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.memory import looks_like_secret

NAME_RE = r"^[a-z][a-z0-9-]{2,39}$"
SEMVER_RE = r"^\d{1,3}\.\d{1,3}\.\d{1,3}$"
PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]{0,31})\s*\}\}")
FORBIDDEN = [
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)",
    r"disable (the )?(log|logging|audit)", r"\bbypass\b", r"paid (model|provider|plan)",
    r"\bapi[ _-]?key", r"system prompt", r"grant (yourself|itself)", r"\bpermission", r"\bconfirmation\b",
    r"reveal (your|the) (instructions|prompt)",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InputField(_Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    type: Literal["string", "number"] = "string"
    required: bool = True
    max_length: int = Field(default=2000, ge=1, le=4000)


class Permissions(_Strict):
    network: bool = False
    files: bool = False
    use_memories: bool = False


class SkillTest(_Strict):
    inputs: dict[str, str | int | float] = {}
    expect_contains: list[str] = Field(default=[], max_length=10)
    expect_not_contains: list[str] = Field(default=[], max_length=10)


class Manifest(_Strict):
    name: str = Field(pattern=NAME_RE)
    version: str = Field(pattern=SEMVER_RE)
    description: str = Field(min_length=10, max_length=300)
    trigger: str = Field(min_length=3, max_length=200)
    inputs: list[InputField] = Field(default=[], max_length=8)
    prompt_template: str = Field(min_length=10, max_length=4000)
    permissions: Permissions = Permissions()
    max_output_tokens: int = Field(default=400, ge=50, le=800)
    resources: list[str] = Field(default=[], max_length=0)  # no external resources exist in this deployment
    tests: list[SkillTest] = Field(min_length=1, max_length=8)
    changelog: str = Field(default="", max_length=500)


def render(m: Manifest, values: dict) -> str:
    """Substitute inputs into the template. Values are data, bounded and type-checked."""
    fields = {f.name: f for f in m.inputs}
    for f in m.inputs:
        if f.required and f.name not in values:
            raise ValueError(f"Missing input '{f.name}'.")
    extra = set(values) - set(fields)
    if extra:
        raise ValueError(f"Unknown input(s): {', '.join(sorted(extra))}.")
    out = {}
    for k, v in values.items():
        f = fields[k]
        if f.type == "number":
            try:
                float(v)
            except (TypeError, ValueError):
                raise ValueError(f"Input '{k}' must be a number.") from None
        s = str(v)
        if len(s) > f.max_length:
            raise ValueError(f"Input '{k}' is too long (max {f.max_length}).")
        out[k] = s
    return PLACEHOLDER.sub(lambda mo: out.get(mo.group(1), ""), m.prompt_template)


def static_checks(m: Manifest) -> dict:
    errors, warnings = [], []
    if m.permissions.network or m.permissions.files:
        errors.append("Skills cannot request network or file access in this deployment.")
    used = set(PLACEHOLDER.findall(m.prompt_template))
    declared = {f.name for f in m.inputs}
    if used - declared:
        errors.append(f"Template uses undeclared inputs: {', '.join(sorted(used - declared))}.")
    if declared - used:
        warnings.append(f"Declared inputs never used: {', '.join(sorted(declared - used))}.")
    blob = " ".join([m.prompt_template, m.description, m.trigger, m.changelog])
    for pat in FORBIDDEN:
        if re.search(pat, blob, re.I):
            errors.append(f"Text matches a forbidden pattern ({pat}).")
    if looks_like_secret(blob):
        errors.append("The manifest contains something that looks like a secret.")
    return {"errors": errors, "warnings": warnings}


def run_tests(m: Manifest) -> list[dict]:
    """Deterministic: render the template for each test and check expectations. No model, no network."""
    results = []
    for i, t in enumerate(m.tests):
        try:
            text = render(m, dict(t.inputs))
            bad = [s for s in t.expect_contains if s not in text] + [s for s in t.expect_not_contains if s in text]
            results.append({"test": i, "passed": not bad, "detail": ("failed expectation: " + ", ".join(bad)) if bad else "ok"})
        except ValueError as e:
            results.append({"test": i, "passed": False, "detail": str(e)})
    return results


def validate(m: Manifest) -> dict:
    checks = static_checks(m)
    tests = run_tests(m)
    ok = not checks["errors"] and all(t["passed"] for t in tests)
    return {"ok": ok, **checks, "tests": tests}


def semver(v: str) -> tuple[int, int, int]:
    a, b, c = v.split(".")
    return int(a), int(b), int(c)


def permissions_expanded(old: Permissions, new: Permissions) -> bool:
    return any(getattr(new, k) and not getattr(old, k) for k in ("network", "files", "use_memories"))
