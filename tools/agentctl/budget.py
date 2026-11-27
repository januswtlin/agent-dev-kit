"""Estimate this month's GitHub Actions spend and decide where heavy CI jobs run.

GitHub bills each job rounded up to a whole minute, at a per-minute price that
depends on the runner. Self-hosted runners are free. This module estimates the
month-to-date cost from job records and, when it nears the plan's allowance,
moves the heavy jobs (the ones that execute pull request code) to the
self-hosted runner in the sandbox VM.

Only `ci` and `security` follow the CI_RUNNER variable. Jobs that judge a pull
request always stay on GitHub-hosted runners: a machine that has run a pull
request's code must not be the one that decides whether it passes.

Overflow is OFF by default. Those two jobs run pull request code, so the runner
they overflow to must hold nothing worth stealing and must be thrown away after
each job. A developer's Mac, or any VM an agent works in, is neither. Point `overflow_runner` only at a
dedicated, credential-free, ephemeral runner.

The figure is an estimate. GitHub's billing page is the source of truth.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

DEFAULTS = {
    "monthly_allowance_usd": 18.0,
    "overflow_at": 0.85,
    "hosted_runner": "ubuntu-latest",
    "overflow_runner": [],  # off: see [conductor.actions] in the kit defaults before turning it on
    "light_labels": ["ubuntu-slim"],
    "price_per_minute": {"standard": 0.006, "light": 0.002, "arm": 0.005},
}


def settings(policy: dict | None) -> dict:
    merged = {**DEFAULTS, **((policy or {}).get("actions") or {})}
    merged["price_per_minute"] = {**DEFAULTS["price_per_minute"], **merged.get("price_per_minute", {})}
    return merged


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def month_of(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m")


def month_start_iso(month: str) -> str:
    return f"{month}-01T00:00:00Z"


def classify(labels: list[str], cfg: dict) -> str:
    lowered = [label.lower() for label in labels or []]
    if "self-hosted" in lowered:
        return "self-hosted"
    if any(label in lowered for label in (name.lower() for name in cfg["light_labels"])):
        return "light"
    if any("arm" in label for label in lowered):
        return "arm"
    return "standard"


def job_cost(job: dict, cfg: dict) -> float:
    """Cost of one job record from the Actions API. Unstarted or skipped jobs cost nothing."""
    started, completed = job.get("started_at"), job.get("completed_at")
    if not started or not completed or job.get("conclusion") == "skipped":
        return 0.0
    kind = classify(job.get("labels", []), cfg)
    if kind == "self-hosted":
        return 0.0
    seconds = max(0.0, _ts(completed) - _ts(started))
    minutes = max(1, math.ceil(seconds / 60))
    return minutes * cfg["price_per_minute"][kind]


def accumulate(usage: dict | None, jobs: list[dict], now: float, cfg: dict) -> dict:
    """Add jobs completed after `usage["through"]` to the running total; reset on a new month."""
    month = month_of(now)
    if not usage or usage.get("month") != month:
        usage = {"month": month, "through": month_start_iso(month), "usd": 0.0}
    through = _ts(usage["through"])
    latest = through
    total = float(usage["usd"])
    for job in jobs:
        completed = job.get("completed_at")
        if not completed:
            continue
        at = _ts(completed)
        if at <= through or month_of(at) != month:
            continue
        total += job_cost(job, cfg)
        latest = max(latest, at)
    return {
        "month": month,
        "through": datetime.fromtimestamp(latest, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "usd": round(total, 4),
    }


def choose_runner(usage: dict, cfg: dict) -> tuple[str, str]:
    """Return (CI_RUNNER value as JSON, reason)."""
    share = usage["usd"] / cfg["monthly_allowance_usd"] if cfg["monthly_allowance_usd"] else 1.0
    if share >= cfg["overflow_at"] and cfg["overflow_runner"]:
        return json.dumps(cfg["overflow_runner"]), f"{share:.0%} of the monthly allowance used; heavy CI moves to the self-hosted runner"
    if share >= cfg["overflow_at"]:
        return json.dumps(cfg["hosted_runner"]), (f"{share:.0%} of the monthly allowance used and no overflow runner is configured; "
                                                  "CI stops when the allowance runs out")
    return json.dumps(cfg["hosted_runner"]), f"{share:.0%} of the monthly allowance used"


def summary(usage: dict, runner_json: str, cfg: dict) -> str:
    share = usage["usd"] / cfg["monthly_allowance_usd"] if cfg["monthly_allowance_usd"] else 1.0
    where = "self-hosted runner (sandbox VM)" if "self-hosted" in runner_json else "GitHub-hosted runner"
    return (f"Actions usage {usage['month']}: about ${usage['usd']:.2f} of ${cfg['monthly_allowance_usd']:.2f} "
            f"({share:.0%}, estimated). Heavy CI runs on: {where}.")
