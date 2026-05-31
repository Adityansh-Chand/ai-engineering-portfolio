# Demo Capture Guide

Use this guide to produce screenshots or short terminal recordings that match
the existing `DEMO.md` files. Keep captures short, deterministic, and focused on
evidence: setup, tests, one API request, one response, and metrics.

## Recommended Assets

| Asset | Project | What to Show |
|---|---|---|
| `rag-smoke.gif` | `enterprise-rag-knowledge-system` | Test run, server start, `scripts/smoke_test.py`, `/query` response |
| `customer-ops-smoke.gif` | `ai-proactive-customer-operations` | `/decide` request and decision trace |
| `incident-score.gif` | `ai-incident-detection-platform` | `/score` response with anomaly label and `/metrics` |
| `sales-score.gif` | `ai-sales-intelligence-engine` | `/score` response with propensity explanation |
| `meeting-analysis.gif` | `autonomous-meeting-intelligence` | `/analyze` response with summary, decisions, action items |
| `adaas-backend.gif` | `ADAAS` | Backend smoke test, `/chat`, `/leave-balance`, `/metrics` |
| `adaas-flutter.png` | `ADAAS` | Flutter web app running against local backend |

Store final assets in `docs/assets/` in the portfolio repository, then link them
from `README.md` or `DEMO.md` when they are available.

## Terminal GIF Workflow

Install optional capture tools:

```bash
pipx install asciinema
cargo install --git https://github.com/asciinema/agg
```

If Rust is not available, install `agg` from its release binaries or use any
terminal recorder that can export GIF or MP4.

Record a smoke test:

```bash
asciinema rec docs/assets/rag-smoke.cast
```

In the recording shell:

```bash
cd ../enterprise-rag-knowledge-system
python -m pytest -q
uvicorn api.server:app --reload --port 8000
```

In a second terminal while the server is running:

```bash
cd enterprise-rag-knowledge-system
python scripts/smoke_test.py
curl -s http://localhost:8000/metrics
```

Convert the recording:

```bash
agg docs/assets/rag-smoke.cast docs/assets/rag-smoke.gif
```

## Screenshot Workflow

For API services, capture three images:

1. Passing tests or smoke test output.
2. A successful curl request using the sample request file.
3. `/metrics` output after the request.

For ADAAS, capture four images:

1. `npm test` passing in `ADAAS/hr-backend`.
2. `npm run smoke` passing while the backend is running.
3. Flutter web app launched with `flutter run -d chrome`.
4. A visible HR assistant or leave-balance interaction.

## Capture Standards

- Use demo keys only, such as `demo-key`.
- Do not display personal credentials, cloud tokens, or real employee data.
- Keep terminal width near 100 columns so JSON remains readable.
- Prefer `python -m json.tool` or `jq` formatting for response captures.
- Show command prompts and exit status when possible.
- Keep each GIF under one minute; reviewers should understand the system at a
  glance.
