# Recruiter and Interviewer Walkthrough

This walkthrough is designed for a 5 to 20 minute review. It starts with the
clearest evidence, then gives interviewers several deeper paths depending on the
role focus.

## 5-Minute Recruiter Path

1. Open the portfolio `README.md` and scan the system map.
2. Open `DEMO.md` and review the demo matrix.
3. Open `docs/PROJECT_COMPARISON.md` to compare scope across projects.
4. Open one project repository and inspect its `README.md`, `DEMO.md`, and
   `examples/` directory.
5. Confirm the maturity labels: runnable demo, deployable baseline, needs cloud
   deployment, needs production data.

Best first repository: `enterprise-rag-knowledge-system`, because it has the
most direct API demo path and a clear retrieval result.

## 15-Minute Technical Screen Path

1. Run the tests for one Python service:

```bash
cd enterprise-rag-knowledge-system
pip install -r requirements.txt
python -m pytest -q
python evaluation/run_eval.py
```

2. Start the API:

```bash
uvicorn api.server:app --reload --port 8000
```

3. In a second terminal, run:

```bash
python scripts/smoke_test.py
```

4. Inspect `examples/requests/query.json` and
   `examples/responses/query.json`.
5. Review `docs/API_FLOWS.md` to see how the same operational pattern applies
   across the other APIs.

## 20-Minute Engineering Interview Path

Use one project for code depth and the portfolio docs for system breadth.

Recommended sequence:

1. `enterprise-rag-knowledge-system`: retrieval behavior, testability, evals.
2. `ai-proactive-customer-operations`: orchestration and decision traces.
3. `ai-incident-detection-platform` or `ai-sales-intelligence-engine`: scoring
   API design and explainability.
4. `ADAAS`: full-stack integration and frontend/backend contract.
5. `docs/TRADEOFFS.md`: maturity boundaries and production next steps.

Good discussion prompts:

- How are request IDs propagated into responses and persisted events?
- What changes when `API_KEY` is set?
- What does `/metrics` expose, and what would a production metrics backend add?
- Which tests protect the hardening features?
- How would the SQLite event store evolve for production traffic?
- What would be required before connecting real providers, brokers, employee
  records, or customer data?

## Role-Specific Focus

| Role Focus | Best Repositories | Why |
|---|---|---|
| Backend/API engineering | Python services, ADAAS backend | Typed APIs, auth boundary, error handling, metrics, persistence |
| Machine learning systems | Sales, incident, RAG | Scoring/eval loops, sample data, model-facing contracts |
| Product engineering | ADAAS, meeting intelligence | User workflows, structured outputs, end-to-end demoability |
| Platform readiness | All runnable repos | Docker, Compose, Kubernetes manifests, CI, smoke tests |

## Suggested Interview Narrative

Start with the portfolio as a coherent system rather than seven disconnected
repositories:

> This portfolio demonstrates a set of local-first systems that share a common
> operational baseline: tests, API contracts, metrics, request tracing, optional
> API key protection, event persistence, containerization, and deployment
> manifests. Each repository focuses on a different applied problem, but the
> reviewer experience is intentionally consistent.

Then move from breadth to depth:

1. Breadth: compare the projects using `docs/PROJECT_COMPARISON.md`.
2. Evidence: run one service using `DEMO.md`.
3. Depth: inspect code, tests, and evaluation script for that service.
4. Maturity: use `docs/TRADEOFFS.md` to explain what is production-ready versus
   what remains intentionally out of scope.
