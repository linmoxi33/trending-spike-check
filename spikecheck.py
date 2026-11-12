"""trending-spike-check: tell a one-day burst from a sustained trend in GitHub Trending snapshots.

The dataset records `stars_period` per list (daily / weekly / monthly). A repo ranked on
the daily list with 2,776 stars in one day is a very different signal from one that also
carries 7,947 over the week. This module turns those two numbers into a concentration
ratio and refuses to guess when the weekly list has no entry for the repo.
"""

from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional

SPIKE = "SPIKE"
CONSISTENT = "CONSISTENT"
UNDERWEIGHT = "UNDERWEIGHT"
ABSTAIN = "ABSTAIN"

SPIKE_RATIO = 2.0
UNDERWEIGHT_RATIO = 0.5


class InputError(Exception):
    """Malformed snapshot; the CLI maps this to exit code 2."""


def load_snapshot(payload) -> dict:
    if not isinstance(payload, dict):
        raise InputError("snapshot must be a JSON object")
    date = payload.get("date")
    if not isinstance(date, str) or not date:
        raise InputError("snapshot has no string 'date'")
    lists = payload.get("lists")
    if not isinstance(lists, dict):
        raise InputError("snapshot %r has no 'lists' object" % date)
    clean = {}
    for name, rows in lists.items():
        if not isinstance(rows, list):
            raise InputError("snapshot %r: list %r is not an array" % (date, name))
        by_repo = {}
        for row in rows:
            if not isinstance(row, dict):
                raise InputError("snapshot %r / %r: entry is not an object" % (date, name))
            repo = row.get("repo")
            if not isinstance(repo, str) or not repo:
                raise InputError("snapshot %r / %r: entry has no 'repo'" % (date, name))
            stars = row.get("stars_period")
            if not isinstance(stars, int) or isinstance(stars, bool) or stars < 0:
                raise InputError("snapshot %r / %r: %r has invalid stars_period" % (date, name, repo))
            by_repo[repo] = {"stars_period": stars, "rank": len(by_repo) + 1,
                             "language": row.get("language"), "description": row.get("description")}
        clean[name] = by_repo
    if "daily" not in clean:
        raise InputError("snapshot %r has no 'daily' list" % date)
    return {"date": date, "lists": clean}


def classify(daily: int, weekly: Optional[int]) -> (str, Optional[float]):
    """Return (verdict, ratio) where ratio = daily / (weekly / 7)."""
    if weekly is None or weekly <= 0:
        return ABSTAIN, None
    ratio = (daily * 7.0) / weekly
    if ratio >= SPIKE_RATIO:
        return SPIKE, ratio
    if ratio < UNDERWEIGHT_RATIO:
        return UNDERWEIGHT, ratio
    return CONSISTENT, ratio


def classify_by_ratio(ratio: float):
    if ratio >= SPIKE_RATIO:
        return SPIKE
    if ratio < UNDERWEIGHT_RATIO:
        return UNDERWEIGHT
    return CONSISTENT


def analyse(snapshots: Iterable[dict]) -> dict:
    snaps = sorted(snapshots, key=lambda s: s["date"])
    if not snaps:
        raise InputError("need at least one snapshot")
    dates = [s["date"] for s in snaps]
    if len(set(dates)) != len(dates):
        raise InputError("duplicate snapshot date: %s" % dates)

    appearance: Dict[str, List[str]] = {}
    history: Dict[str, List[int]] = {}
    for snap in snaps:
        for repo, row in snap["lists"]["daily"].items():
            appearance.setdefault(repo, []).append(snap["date"])
            history.setdefault(repo, []).append(row["stars_period"])

    latest = snaps[-1]
    rows = []
    for repo in sorted(appearance):
        last_seen = appearance[repo][-1]
        today = latest["lists"]["daily"].get(repo)
        last = snaps[[s["date"] for s in snaps].index(last_seen)]["lists"]["daily"][repo]
        daily = today or last
        weekly_row = latest["lists"].get("weekly", {}).get(repo)
        weekly = weekly_row["stars_period"] if weekly_row else None
        verdict, ratio = classify(daily["stars_period"], weekly)
        basis = "weekly" if ratio is not None else None
        self_ratio = None
        if ratio is None:
            prior = history.get(repo, [])[:-1]
            if len(prior) >= 1:
                prior_sorted = sorted(prior)
                mid = len(prior_sorted) // 2
                median = (prior_sorted[mid] if len(prior_sorted) % 2
                          else (prior_sorted[mid - 1] + prior_sorted[mid]) / 2.0)
                if median > 0:
                    self_ratio = round(daily["stars_period"] / median, 4)
                    verdict = classify_by_ratio(self_ratio)
                    ratio = self_ratio
                    basis = "self-baseline(%d prior days)" % len(prior)
        first_seen = min(appearance.get(repo, [latest["date"]]))
        rows.append({
            "repo": repo,
            "daily_stars": daily["stars_period"],
            "weekly_stars": weekly,
            "daily_share_ratio": None if ratio is None else round(ratio, 4),
            "self_baseline_ratio": self_ratio,
            "basis": basis,
            "verdict": verdict,
            "days_on_daily": len(appearance.get(repo, [])),
            "snapshots": len(snaps),
            "first_seen": first_seen,
            "new_in_latest": first_seen == latest["date"],
            "on_daily_today": today is not None,
            "last_seen": last_seen,
            "language": daily.get("language"),
            "rank_today": daily.get("rank"),
        })

    rows.sort(key=lambda r: (-(r["daily_share_ratio"] if r["daily_share_ratio"] is not None else -1), r["repo"]))
    counts = {SPIKE: 0, CONSISTENT: 0, UNDERWEIGHT: 0, ABSTAIN: 0}
    for row in rows:
        counts[row["verdict"]] += 1
    return {
        "schema_version": 1,
        "snapshots": dates,
        "latest": latest["date"],
        "tool_count": len(rows),
        "counts": counts,
        "rows": rows,
    }
