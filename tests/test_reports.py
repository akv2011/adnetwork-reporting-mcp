from datetime import date

import pytest

from adnet_mcp import networks, reports
from adnet_mcp.networks import Row

ROWS = networks.load()
ALL = (date(2026, 7, 1), date(2026, 9, 28))


def test_each_adapter_reads_its_own_format():
    cpi = networks._cpi({"day": "2026-07-01", "campaign_id": "c", "geo": "US", "cost_cents": 12345, "installs": 50, "d7_revenue_cents": 500})
    search = networks._search({"date": "2026-07-01", "campaign": "s", "countryOrRegion": "gb", "localSpend": {"amount": "123.45", "currency": "USD"}, "taps": 9, "installs": 50, "revenueD7": 5.0})
    video = networks._video({"report_date": "07/01/2026", "campaign_name": "v", "country_code": "DE", "spend_usd": 123.45, "impressions": 1, "completed_views": 1, "conversions": 50, "d7_iap_usd": 5.0})
    for row, country in ((cpi, "US"), (search, "GB"), (video, "DE")):
        assert (row.day, row.country, row.spend_usd, row.installs, row.revenue_d7_usd) == (date(2026, 7, 1), country, 123.45, 50, 5.0)


def test_a_non_usd_report_is_refused_not_mixed_in():
    with pytest.raises(ValueError, match="EUR"):
        networks._search({"date": "2026-07-01", "campaign": "s", "countryOrRegion": "gb", "localSpend": {"amount": "1", "currency": "EUR"}, "taps": 0, "installs": 0, "revenueD7": 0})


def test_grouped_report_adds_up_to_the_total():
    total = reports.report(ROWS, *ALL, [])[0]
    by_country = reports.report(ROWS, *ALL, ["network", "country"])
    assert sum(r["installs"] for r in by_country) == total["installs"]
    assert sum(r["spend_usd"] for r in by_country) == pytest.approx(total["spend_usd"], abs=0.05)
    assert len(by_country) == 3 * 8


def test_cpi_and_roas_are_ratios_of_the_summed_totals():
    rows = [Row(date(2026, 7, 1), "n", "c", "US", 100.0, 10, 50.0), Row(date(2026, 7, 1), "n", "c", "GB", 300.0, 90, 30.0)]
    [r] = reports.report(rows, date(2026, 7, 1), date(2026, 7, 1), ["network"])
    assert (r["cpi"], r["roas_d7"]) == (4.0, 0.2)


def test_the_planted_anomalies_rank_first():
    cpi = reports.anomalies(ROWS, date(2026, 7, 15), ALL[1], "cpi")
    installs = reports.anomalies(ROWS, date(2026, 7, 15), ALL[1], "installs")
    assert {(a["network"], a["day"]) for a in cpi[:2]} == {("search_ads", "2026-08-20"), ("video_network", "2026-09-10")}
    assert (installs[0]["campaign"], installs[0]["day"], installs[0]["z_score"] < 0) == ("Search - Brand", "2026-08-20", True)


def test_a_quiet_window_has_no_planted_anomaly():
    quiet = reports.anomalies(ROWS, date(2026, 7, 20), date(2026, 8, 10), "cpi", threshold=6.0)
    assert quiet == []


def test_pacing_projects_the_daily_rate_to_month_end():
    rows = [Row(date(2026, 9, d), "cpi_network", "cpi-101", "US", 1000.0, 1, 0.0) for d in range(1, 16)]
    row = next(p for p in reports.pacing(rows, "2026-09", date(2026, 9, 15)) if p["campaign"] == "cpi-101")
    assert (row["spend_to_date_usd"], row["projected_usd"], row["status"]) == (15000.0, 30000.0, "on_track")


def test_pacing_on_the_demo_data_has_every_status():
    statuses = {p["status"] for p in reports.pacing(ROWS, "2026-09", date(2026, 9, 15))}
    assert statuses == {"under", "on_track", "over"}


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: reports.report(ROWS, date(2026, 9, 1), date(2026, 8, 1), []), "after"),
        (lambda: reports.report(ROWS, date(2026, 1, 1), date(2026, 9, 1), []), "at most"),
        (lambda: reports.report(ROWS, *ALL, ["platform"]), "unknown dimension"),
        (lambda: reports.anomalies(ROWS, *ALL, "clicks"), "metric must be"),
        (lambda: reports.pacing(ROWS, "2026-09", date(2026, 10, 1)), "inside"),
    ],
)
def test_bad_inputs_are_refused(call, message):
    with pytest.raises(ValueError, match=message):
        call()
