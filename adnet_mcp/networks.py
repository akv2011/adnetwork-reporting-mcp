"""Three demo ad networks that each report in their own shape, and the adapters that map them onto one row type.

Real networks differ the same ways: money in cents or in a nested currency object, dates in different
formats, country codes in different cases, installs called installs or conversions.
"""

import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

FIRST_DAY = date(2026, 7, 1)
DAYS = 90
COUNTRIES = ("US", "GB", "DE", "IN", "BR", "JP", "CA", "FR")
COUNTRY_WEIGHT = {"US": 3.0, "GB": 1.2, "DE": 1.1, "IN": 2.5, "BR": 1.5, "JP": 1.0, "CA": 0.8, "FR": 0.9}
COUNTRY_CPI = {"US": 3.2, "GB": 2.4, "DE": 2.6, "IN": 0.35, "BR": 0.6, "JP": 3.0, "CA": 2.8, "FR": 2.2}

# Planted so the anomaly report has known answers: (network, campaign, day, field, multiplier).
SPIKES = (
    ("video_network", "Video - Puzzle Launch", date(2026, 9, 10), "cost", 4.0),
    ("search_ads", "Search - Brand", date(2026, 8, 20), "installs", 0.15),
)


@dataclass(frozen=True)
class Row:
    day: date
    network: str
    campaign: str
    country: str
    spend_usd: float
    installs: int
    revenue_d7_usd: float


def _base(rng: random.Random, country: str, day_index: int, scale: float) -> tuple[float, int, float]:
    trend = 1 + 0.15 * (day_index / DAYS)
    weekend = 0.85 if (FIRST_DAY + timedelta(days=day_index)).weekday() >= 5 else 1.0
    installs = max(0, int(rng.gauss(40, 6) * COUNTRY_WEIGHT[country] * scale * weekend))
    cost = installs * COUNTRY_CPI[country] * rng.uniform(0.9, 1.1) * trend
    revenue = cost * rng.uniform(0.25, 0.55)
    return cost, installs, revenue


def _spike(network: str, campaign: str, day: date) -> dict[str, float]:
    return {field: m for (n, c, d, field, m) in SPIKES if (n, c, d) == (network, campaign, day)}


def cpi_network_raw(seed: int = 7) -> Iterator[dict]:
    """Money in cents, ISO dates, uppercase geos."""
    rng = random.Random(seed)
    campaigns = {"cpi-101": 1.0, "cpi-102": 0.7, "cpi-205": 0.4}
    for i in range(DAYS):
        day = FIRST_DAY + timedelta(days=i)
        for cid, scale in campaigns.items():
            for geo in COUNTRIES:
                cost, installs, rev = _base(rng, geo, i, scale)
                yield {"day": day.isoformat(), "campaign_id": cid, "geo": geo, "cost_cents": round(cost * 100), "installs": installs, "d7_revenue_cents": round(rev * 100)}


def search_ads_raw(seed: int = 11) -> Iterator[dict]:
    """Spend as a nested amount string with currency, lowercase countries, taps alongside installs."""
    rng = random.Random(seed)
    campaigns = {"Search - Brand": 0.8, "Search - Generic": 1.1, "Search - Competitor": 0.5}
    for i in range(DAYS):
        day = FIRST_DAY + timedelta(days=i)
        for name, scale in campaigns.items():
            spike = _spike("search_ads", name, day)
            for geo in COUNTRIES:
                cost, installs, rev = _base(rng, geo, i, scale)
                installs = int(installs * spike.get("installs", 1.0))
                yield {
                    "date": day.isoformat(),
                    "campaign": name,
                    "countryOrRegion": geo.lower(),
                    "localSpend": {"amount": f"{cost:.2f}", "currency": "USD"},
                    "taps": installs * 6,
                    "installs": installs,
                    "revenueD7": round(rev, 2),
                }


def video_network_raw(seed: int = 13) -> Iterator[dict]:
    """US-style dates, installs called conversions, impressions and completed views."""
    rng = random.Random(seed)
    campaigns = {"Video - Puzzle Launch": 1.2, "Video - Retarget": 0.6}
    for i in range(DAYS):
        day = FIRST_DAY + timedelta(days=i)
        for name, scale in campaigns.items():
            spike = _spike("video_network", name, day)
            for geo in COUNTRIES:
                cost, installs, rev = _base(rng, geo, i, scale)
                yield {
                    "report_date": day.strftime("%m/%d/%Y"),
                    "campaign_name": name,
                    "country_code": geo,
                    "spend_usd": round(cost * spike.get("cost", 1.0), 2),
                    "impressions": installs * 900,
                    "completed_views": installs * 210,
                    "conversions": installs,
                    "d7_iap_usd": round(rev, 2),
                }


def _cpi(r: dict) -> Row:
    return Row(date.fromisoformat(r["day"]), "cpi_network", r["campaign_id"], r["geo"], r["cost_cents"] / 100, r["installs"], r["d7_revenue_cents"] / 100)


def _search(r: dict) -> Row:
    spend = r["localSpend"]
    if spend["currency"] != "USD":
        raise ValueError(f"search_ads reported {spend['currency']}; only USD is supported")
    return Row(date.fromisoformat(r["date"]), "search_ads", r["campaign"], r["countryOrRegion"].upper(), float(spend["amount"]), r["installs"], r["revenueD7"])


def _video(r: dict) -> Row:
    day = datetime.strptime(r["report_date"], "%m/%d/%Y").date()
    return Row(day, "video_network", r["campaign_name"], r["country_code"], r["spend_usd"], r["conversions"], r["d7_iap_usd"])


NETWORKS: dict[str, tuple[Callable[[], Iterator[dict]], Callable[[dict], Row]]] = {
    "cpi_network": (cpi_network_raw, _cpi),
    "search_ads": (search_ads_raw, _search),
    "video_network": (video_network_raw, _video),
}

BUDGETS_USD = {
    ("cpi_network", "cpi-101"): 32_000,
    ("cpi_network", "cpi-102"): 18_000,
    ("cpi_network", "cpi-205"): 16_000,
    ("search_ads", "Search - Brand"): 25_000,
    ("search_ads", "Search - Generic"): 30_000,
    ("search_ads", "Search - Competitor"): 20_000,
    ("video_network", "Video - Puzzle Launch"): 46_000,
    ("video_network", "Video - Retarget"): 24_000,
}


def load() -> list[Row]:
    return [adapt(raw) for fetch, adapt in NETWORKS.values() for raw in fetch()]
