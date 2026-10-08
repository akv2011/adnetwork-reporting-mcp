from fastmcp import Client

from adnet_mcp.server import build_server

SERVER = build_server()


async def test_every_tool_is_read_only_and_typed():
    async with Client(SERVER) as c:
        tools = await c.list_tools()
    assert {t.name for t in tools} == {"list_networks", "compare_networks", "get_report", "find_anomalies", "budget_pacing"}
    for t in tools:
        assert t.annotations.read_only_hint is True and t.annotations.destructive_hint is False
        assert t.output_schema


async def test_compare_networks_returns_shares_that_sum_to_one():
    async with Client(SERVER) as c:
        result = await c.call_tool("compare_networks", {"start_date": "2026-08-01", "end_date": "2026-08-31"})
    shares = [r["share_of_spend"] for r in result.structured_content["result"]]
    assert len(shares) == 3 and abs(sum(shares) - 1) < 0.001


async def test_find_anomalies_surfaces_the_video_cost_spike():
    async with Client(SERVER) as c:
        result = await c.call_tool("find_anomalies", {"start_date": "2026-09-01", "end_date": "2026-09-28", "metric": "cpi", "threshold": 6})
    top = result.structured_content["result"][0]
    assert (top["network"], top["campaign"], top["day"]) == ("video_network", "Video - Puzzle Launch", "2026-09-10")


async def test_invalid_input_is_an_error_with_a_reason():
    async with Client(SERVER) as c:
        too_long = await c.call_tool("get_report", {"start_date": "2026-01-01", "end_date": "2026-09-01", "group_by": ["network"]}, raise_on_error=False)
        bad_threshold = await c.call_tool("find_anomalies", {"start_date": "2026-09-01", "end_date": "2026-09-28", "threshold": 0.5}, raise_on_error=False)
    assert too_long.is_error and "at most 92 days" in too_long.content[0].text
    assert bad_threshold.is_error and "between 2 and 10" in bad_threshold.content[0].text
