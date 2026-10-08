import argparse
from datetime import date
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import BaseModel

from adnet_mcp import networks, reports

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
Network = Literal["cpi_network", "search_ads", "video_network"]
Dimension = Literal["network", "campaign", "country", "day"]

INSTRUCTIONS = """\
Ad network reporting in one schema: spend_usd, installs, revenue_d7_usd, cpi and roas_d7, whatever shape each
network reports in. The data is a 90-day demo from 2026-07-01 to 2026-09-28. Ranges are inclusive and capped at
92 days. Start with compare_networks for an overview, get_report to slice, find_anomalies for what changed,
and budget_pacing for spend against budget."""


class NetworkInfo(BaseModel):
    name: str
    campaigns: list[str]
    first_day: date
    last_day: date


class NetworkTotals(BaseModel):
    network: str
    spend_usd: float
    installs: int
    revenue_d7_usd: float
    cpi: float | None
    roas_d7: float | None
    share_of_spend: float


class Anomaly(BaseModel):
    day: date
    network: str
    campaign: str
    metric: str
    value: float
    baseline: float
    z_score: float


class Pacing(BaseModel):
    network: str
    campaign: str
    budget_usd: float
    spend_to_date_usd: float
    projected_usd: float
    projected_vs_budget: float
    status: Literal["under", "on_track", "over"]


def build_server() -> FastMCP:
    rows = networks.load()
    mcp = FastMCP("adnetwork-reporting", instructions=INSTRUCTIONS)

    def guarded(fn, *args):
        try:
            return fn(*args)
        except ValueError as e:
            raise ToolError(str(e)) from None

    @mcp.tool(annotations=READ_ONLY)
    async def list_networks() -> list[NetworkInfo]:
        """Networks, their campaigns and the dates covered."""
        out = []
        for name in networks.NETWORKS:
            mine = [r for r in rows if r.network == name]
            out.append(NetworkInfo(name=name, campaigns=sorted({r.campaign for r in mine}), first_day=min(r.day for r in mine), last_day=max(r.day for r in mine)))
        return out

    @mcp.tool(annotations=READ_ONLY)
    async def compare_networks(start_date: date, end_date: date) -> list[NetworkTotals]:
        """Spend, installs, CPI, day-7 ROAS and share of spend per network, biggest spender first."""
        return [NetworkTotals(**r) for r in guarded(reports.compare, rows, start_date, end_date)]

    @mcp.tool(annotations=READ_ONLY)
    async def get_report(
        start_date: date,
        end_date: date,
        group_by: list[Dimension],
        networks_filter: list[Network] | None = None,
    ) -> list[dict[str, Any]]:
        """Spend, installs, day-7 revenue, CPI and ROAS grouped by any of network, campaign, country and day."""
        return guarded(reports.report, rows, start_date, end_date, list(group_by), set(networks_filter or []) or None)

    @mcp.tool(annotations=READ_ONLY)
    async def find_anomalies(
        start_date: date,
        end_date: date,
        metric: Literal["spend_usd", "installs", "cpi"] = "cpi",
        threshold: float = 3.0,
    ) -> list[Anomaly]:
        """Campaign-days where a metric is `threshold` standard deviations away from that campaign's previous 14 days."""
        if not 2.0 <= threshold <= 10.0:
            raise ToolError("threshold must be between 2 and 10")
        return [Anomaly(**a) for a in guarded(reports.anomalies, rows, start_date, end_date, metric, threshold)]

    @mcp.tool(annotations=READ_ONLY)
    async def budget_pacing(month: Literal["2026-07", "2026-08", "2026-09"], as_of: date) -> list[Pacing]:
        """Each campaign's spend so far against its monthly budget, projected to month end."""
        return [Pacing(**p) for p in guarded(reports.pacing, rows, month, as_of)]

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Ad network reporting MCP server")
    parser.add_argument("--http", action="store_true", help="serve Streamable HTTP on 127.0.0.1 instead of stdio")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    server = build_server()
    if args.http:
        server.run(transport="http", host="127.0.0.1", port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
