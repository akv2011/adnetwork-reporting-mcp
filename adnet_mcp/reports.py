"""Reports over the unified rows. Pure functions, so every number is easy to test."""

import calendar
import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from adnet_mcp.networks import BUDGETS_USD, Row

MAX_DAYS = 92
DIMENSIONS = ("network", "campaign", "country", "day")


@dataclass
class Totals:
    spend_usd: float = 0.0
    installs: int = 0
    revenue_d7_usd: float = 0.0

    def add(self, r: Row) -> None:
        self.spend_usd += r.spend_usd
        self.installs += r.installs
        self.revenue_d7_usd += r.revenue_d7_usd

    @property
    def cpi(self) -> float | None:
        return round(self.spend_usd / self.installs, 4) if self.installs else None

    @property
    def roas_d7(self) -> float | None:
        return round(self.revenue_d7_usd / self.spend_usd, 4) if self.spend_usd else None

    def as_dict(self) -> dict:
        return {"spend_usd": round(self.spend_usd, 2), "installs": self.installs, "revenue_d7_usd": round(self.revenue_d7_usd, 2), "cpi": self.cpi, "roas_d7": self.roas_d7}


def check_range(start: date, end: date) -> None:
    if start > end:
        raise ValueError("start_date is after end_date")
    if (end - start).days >= MAX_DAYS:
        raise ValueError(f"ask for at most {MAX_DAYS} days at a time")


def _in(rows: Iterable[Row], start: date, end: date, networks: set[str] | None) -> Iterable[Row]:
    return (r for r in rows if start <= r.day <= end and (not networks or r.network in networks))


def report(rows: list[Row], start: date, end: date, group_by: list[str], networks: set[str] | None = None) -> list[dict]:
    check_range(start, end)
    if bad := [d for d in group_by if d not in DIMENSIONS]:
        raise ValueError(f"unknown dimension {bad[0]!r}; dimensions are {', '.join(DIMENSIONS)}")
    dims = tuple(dict.fromkeys(group_by))
    groups: dict[tuple, Totals] = defaultdict(Totals)
    for r in _in(rows, start, end, networks):
        groups[tuple(getattr(r, d) for d in dims)].add(r)
    out = []
    for key, t in sorted(groups.items(), key=lambda kv: tuple(str(k) for k in kv[0])):
        out.append({**{d: (v.isoformat() if isinstance(v, date) else v) for d, v in zip(dims, key)}, **t.as_dict()})
    return out


def compare(rows: list[Row], start: date, end: date) -> list[dict]:
    per_network = report(rows, start, end, ["network"])
    total = sum(r["spend_usd"] for r in per_network) or 1.0
    return [{**r, "share_of_spend": round(r["spend_usd"] / total, 4)} for r in sorted(per_network, key=lambda r: -r["spend_usd"])]


def anomalies(rows: list[Row], start: date, end: date, metric: str, threshold: float = 3.0, baseline_days: int = 14) -> list[dict]:
    """Days where a campaign's metric sits more than `threshold` standard deviations from its own trailing baseline."""
    check_range(start, end)
    if metric not in ("spend_usd", "installs", "cpi"):
        raise ValueError("metric must be spend_usd, installs or cpi")
    daily: dict[tuple[str, str], dict[date, Totals]] = defaultdict(lambda: defaultdict(Totals))
    for r in rows:
        if start - timedelta(days=baseline_days) <= r.day <= end:
            daily[(r.network, r.campaign)][r.day].add(r)

    def value(t: Totals) -> float | None:
        return t.cpi if metric == "cpi" else getattr(t, metric)

    found = []
    for (network, campaign), by_day in daily.items():
        for day in sorted(d for d in by_day if start <= d <= end):
            history = [value(by_day[day - timedelta(days=k)]) for k in range(1, baseline_days + 1) if day - timedelta(days=k) in by_day]
            history = [h for h in history if h is not None]
            today = value(by_day[day])
            if today is None or len(history) < baseline_days // 2:
                continue
            mean, spread = statistics.fmean(history), statistics.pstdev(history)
            if spread and abs(today - mean) / spread >= threshold:
                found.append({
                    "day": day.isoformat(), "network": network, "campaign": campaign, "metric": metric,
                    "value": round(today, 4), "baseline": round(mean, 4), "z_score": round((today - mean) / spread, 2),
                })
    return sorted(found, key=lambda a: -abs(a["z_score"]))


def pacing(rows: list[Row], month: str, as_of: date) -> list[dict]:
    """Spend so far against each campaign's monthly budget, projected to month end at the current daily rate."""
    year, mon = (int(p) for p in month.split("-"))
    first, days_in_month = date(year, mon, 1), calendar.monthrange(year, mon)[1]
    last = date(year, mon, days_in_month)
    if not first <= as_of <= last:
        raise ValueError(f"as_of must fall inside {month}")
    elapsed = (as_of - first).days + 1
    spent: dict[tuple[str, str], float] = defaultdict(float)
    for r in rows:
        if first <= r.day <= as_of:
            spent[(r.network, r.campaign)] += r.spend_usd
    out = []
    for (network, campaign), budget in sorted(BUDGETS_USD.items()):
        so_far = spent.get((network, campaign), 0.0)
        projected = so_far / elapsed * days_in_month
        ratio = projected / budget
        status = "over" if ratio > 1.05 else "under" if ratio < 0.9 else "on_track"
        out.append({
            "network": network, "campaign": campaign, "budget_usd": budget, "spend_to_date_usd": round(so_far, 2),
            "projected_usd": round(projected, 2), "projected_vs_budget": round(ratio, 3), "status": status,
        })
    return out
