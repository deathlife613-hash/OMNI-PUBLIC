"""In-process counters (reset on restart). Only measured values; token counts
appear only when the provider reported them."""
from collections import Counter


class UsageTracker:
    def __init__(self) -> None:
        self.requests = 0
        self.errors: Counter[str] = Counter()
        self.latency_ms_total = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.token_reports = 0  # how many requests reported usage

    def record_success(self, latency_ms: int, prompt: int | None, completion: int | None) -> None:
        self.requests += 1
        self.latency_ms_total += latency_ms
        if prompt is not None or completion is not None:
            self.token_reports += 1
            self.prompt_tokens += prompt or 0
            self.completion_tokens += completion or 0

    def record_error(self, kind: str) -> None:
        self.requests += 1
        self.errors[kind] += 1

    def snapshot(self) -> dict:
        ok = self.requests - sum(self.errors.values())
        return {
            "requests": self.requests,
            "successful": ok,
            "errors": dict(self.errors),
            "rate_limit_events": self.errors.get("rate_limit", 0) + self.errors.get("quota", 0),
            "avg_latency_ms": (self.latency_ms_total // ok) if ok else None,
            "tokens": {
                "prompt": self.prompt_tokens,
                "completion": self.completion_tokens,
                "requests_reporting_usage": self.token_reports,
                "note": "Only counts what the provider reported.",
            },
            "since_restart": True,
        }
