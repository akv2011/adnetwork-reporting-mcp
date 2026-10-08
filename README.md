# adnetwork-reporting-mcp

An MCP server that answers user acquisition questions across ad networks in one vocabulary: what did we spend, how many installs did it buy, what did each install cost, what came back in the first week, what changed, and are we on budget.

Every ad network reports differently. One sends cost in cents, one sends spend as a nested amount with a currency, one uses US-style dates and calls installs "conversions". This server keeps one adapter per network that maps its raw rows onto a single row type, so the tools and the model never see the differences.

It ships with 90 days of generated data for three demo networks (`cpi_network`, `search_ads`, `video_network`), each with its own raw format, eight campaigns and eight countries. Two incidents are planted in the data so the anomaly tool has known answers.

## Tools

| Tool | What it returns |
|---|---|
| `list_networks` | Networks, their campaigns and the dates covered |
| `compare_networks` | Spend, installs, CPI, day-7 ROAS and share of spend per network |
| `get_report` | The same measures grouped by any of network, campaign, country and day |
| `find_anomalies` | Campaign-days where spend, installs or CPI sit far from that campaign's own previous 14 days |
| `budget_pacing` | Spend so far against each campaign's monthly budget, projected to month end, with an under, on-track or over status |

All five carry `readOnlyHint: true` and return typed results.

## How it holds up

- **One schema.** Adapters convert cents, nested currency objects, date formats and country case. A report in a currency other than USD is refused rather than silently mixed into USD totals.
- **Ratios from totals.** CPI and ROAS are computed from summed spend, installs and revenue, never by averaging daily ratios, so grouped numbers add up.
- **Bounded inputs.** Networks, dimensions, metrics and months come from fixed lists; date ranges are capped at 92 days; anomaly thresholds must sit between 2 and 10 standard deviations. A bad input returns `isError: true` with the reason.
- **Anomalies against each campaign's own history.** A z-score against the previous 14 days, so a campaign that is always expensive is not flagged for being expensive.

## Run

```sh
uv sync
uv run adnet-mcp            # stdio
uv run adnet-mcp --http     # Streamable HTTP on 127.0.0.1:8002/mcp
```

To report on real networks, add a fetch function and an adapter for each one in `adnet_mcp/networks.py`; the reports and tools stay the same.

## Connect a client

Replace `/path/to` with where you cloned this repo.

Claude Code:

```sh
claude mcp add adnet -- uv --directory /path/to/adnetwork-reporting-mcp run adnet-mcp
```

Codex CLI:

```sh
codex mcp add adnet -- uv --directory /path/to/adnetwork-reporting-mcp run adnet-mcp
```

Gemini CLI (no `--` before the command):

```sh
gemini mcp add -s user adnet uv --directory /path/to/adnetwork-reporting-mcp run adnet-mcp
```

Claude Desktop (`claude_desktop_config.json`) and Cursor (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "adnet": {
      "command": "uv",
      "args": ["--directory", "/path/to/adnetwork-reporting-mcp", "run", "adnet-mcp"]
    }
  }
}
```

MCP Inspector:

```sh
npx @modelcontextprotocol/inspector /path/to/adnetwork-reporting-mcp/.venv/bin/adnet-mcp
```

Checked on 2026-10-08: Claude Code 2.1.294 connects; MCP Inspector lists the five tools and runs `budget_pacing`; Codex CLI 0.156.1 accepts the config; Gemini CLI 0.63.0 ran headless, called `list_networks` and named all three networks. Gemini CLI marks servers "Disabled" in a folder it does not trust; trust the folder or pass `--skip-trust`.

## Tests

```sh
uv run pytest
```

17 tests: each adapter against its raw format, the currency check, grouped totals adding up, CPI and ROAS from totals, the planted anomalies ranking first and a quiet window staying quiet, the pacing arithmetic, input limits, and the MCP surface. Breaking an adapter or the anomaly baseline makes them fail.

## Layout

```
adnet_mcp/networks.py   raw formats, adapters, budgets
adnet_mcp/reports.py    report, compare, anomalies, pacing
adnet_mcp/server.py     MCP tools
```

## License

MIT
