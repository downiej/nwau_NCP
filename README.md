# NEP MCP Server

A Model Context Protocol server that calculates Australian hospital funding
metrics from the IHPA **National Efficient Price Determination 2025-26**.

National Efficient Price (NEP) for 2025-26: **$7,258 per NWAU**.

## Care streams supported

| Stream | Classification | Pricing model |
| --- | --- | --- |
| `acute` | AR-DRG V11.0 (Table 12) | Episode NWAU with same-day / SSO / inlier / LSO bands |
| `subacute` | AN-SNAP V5.0 (Table 13) | Same-day class or per-diem SSO / fixed inlier / LSO |
| `mh_admitted` | AMHCC V1.1 (Table 14) | Phase NWAU with SSO / inlier / LSO |
| `mh_community` | AMHCC V1.1 (Table 15) | Per-contact NWAU (consumer present / not) |
| `non_admitted` | Tier 2 V9.1 (Table 16) | Per-service NWAU + paediatric uplift |
| `aecc` | AECC V1.1 (Table 17) | Per-presentation NWAU |
| `udg` | UDG V1.3 (Table 18) | Per-presentation NWAU |

## MCP tools exposed

- `get_nwau(stream, classification_code, los, demographics?, contact_with_consumer?)`
- `get_rate_dollars(stream, classification_code, los, demographics?, contact_with_consumer?)`
- `get_average_daily_rate(care_type?)` — subacute care-type $/day
- `list_classifications(stream)` — every code + description in a stream
- `search_classifications(stream, query)` — substring search

`demographics` is an optional dict accepting `indigenous`, `patient_remoteness`,
`treatment_remoteness`, `private_patient_service`, `private_patient_accommodation`,
`is_paediatric`. Multiplier values are in `nep_mcp/config.py` —
`DEMOGRAPHIC_ADJUSTMENTS` — and should be reviewed against the determination
each year.

## Layout

```
nep-mcp-server/
├── nep_mcp/
│   ├── config.py          # NEP price + adjustment multipliers
│   ├── loader.py          # xlsx → typed dataclasses (only file using openpyxl)
│   ├── store.py           # process-wide singleton, loaded once at cold start
│   ├── adjustments.py     # demographic uplifts
│   ├── pricing/           # one file per stream, formulas only
│   ├── server.py          # FastMCP tools — the MCP-shaped surface
│   ├── auth.py            # X-API-Key middleware
│   └── __main__.py        # local dev: stdio or streamable-http
├── price_weights/
│   └── nep_2025_26_price_weights.xlsx
├── function_app.py        # Azure Functions entry — wraps the ASGI app
├── host.json              # Functions config (route prefix = /mcp)
├── local.settings.json.example
└── tests/test_pricing.py
```

The data layer (`loader.py`, `store.py`) and the MCP layer (`server.py`) are
deliberately decoupled. To roll the server forward to NEP 2026-27:

1. Drop the new xlsx into `price_weights/`
2. Update `NEP_PRICE` in env / app settings
3. Re-check the column positions in `loader.py` (IHPA occasionally shuffles them)
4. Review `DEMOGRAPHIC_ADJUSTMENTS` in `config.py`

## Local development

### Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Run as MCP stdio server (e.g. for Claude Desktop)

```powershell
python -m nep_mcp
```

### Run as HTTP server (same transport Azure Functions hosts)

```powershell
python -m nep_mcp --http --port 8000
```

Endpoint: `http://127.0.0.1:8000/mcp/` — POST a JSON-RPC `initialize` to confirm.

If `NEP_API_KEY` is set in the environment, the server requires
`X-API-Key: <value>` on every request. Leave it unset for unauthenticated local
testing.

### Quick smoke test

```powershell
pytest tests/
```

## Azure Functions deployment

Tested against the Python v2 programming model on the Linux Consumption /
Flex Consumption plan.

```powershell
# 1. Create function app (one-off)
az functionapp create `
  --name nep-mcp-prod `
  --resource-group rg-cove-mcp `
  --consumption-plan-location australiaeast `
  --runtime python --runtime-version 3.11 --os-type Linux `
  --functions-version 4 --storage-account <storage>

# 2. Set required app settings
az functionapp config appsettings set `
  --name nep-mcp-prod --resource-group rg-cove-mcp `
  --settings NEP_API_KEY=<random-secret> NEP_PRICE=7258 NEP_YEAR=2025-26

# 3. Deploy (from this directory)
func azure functionapp publish nep-mcp-prod --python
```

The route prefix in `host.json` is `mcp`, so the deployed URL is:

```
https://nep-mcp-prod.azurewebsites.net/mcp/
```

Clients connect using the MCP streamable-http transport with header
`X-API-Key: <NEP_API_KEY>`.

## Notes

- Same-day flag is taken literally from the AR-DRG / AN-SNAP "Same-day" column;
  if a DRG isn't on the same-day list, LOS = 0 falls through to SSO with LOS = 1.
- The AN-SNAP "average daily rate" calc is the unweighted mean of
  `inlier_NWAU * NEP / ALOS` across multi-day classifications in each care type.
  Same-day classes are excluded.
- The xlsx is read with `openpyxl` in read-only mode; large rows stream so the
  cold-start memory footprint is small (~5 MB resident after parse).
- `loader.py` is the only file that touches openpyxl. Pricing modules consume
  the in-memory dataclasses, so unit-testing them does not require any I/O.
