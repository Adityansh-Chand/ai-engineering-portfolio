# Portfolio Architecture

This portfolio is organized as a set of focused, independently runnable systems.
Each repository demonstrates one production engineering concern: retrieval,
workflow orchestration, scoring, anomaly detection, transcript understanding, or
application integration.

## System Landscape

```mermaid
flowchart LR
  Reviewer[Reviewer / Hiring Team]
  Portfolio[AI Engineering Portfolio]

  subgraph Apps[Application Layer]
    ADAAS[ADAAS\nFlutter HR Assistant]
  end

  subgraph APIs[Runnable Service Layer]
    RAG[Enterprise RAG\nKnowledge System]
    OPS[Proactive Customer\nOperations]
    INCIDENT[Incident Detection\nPlatform]
    SALES[Sales Intelligence\nEngine]
    MEETING[Meeting Intelligence]
  end

  subgraph Evidence[Evidence Layer]
    Tests[Unit and API Tests]
    Evals[Evaluation Scripts]
    Samples[Sample Requests and Responses]
    Smoke[Smoke Tests]
    Deploy[Docker, Compose, Kubernetes, CI]
  end

  Reviewer --> Portfolio
  Portfolio --> ADAAS
  Portfolio --> RAG
  Portfolio --> OPS
  Portfolio --> INCIDENT
  Portfolio --> SALES
  Portfolio --> MEETING

  ADAAS --> RAG
  OPS --> SALES
  OPS --> INCIDENT
  MEETING --> RAG

  RAG --> Tests
  OPS --> Tests
  INCIDENT --> Tests
  SALES --> Tests
  MEETING --> Tests
  ADAAS --> Tests

  Tests --> Evals
  Tests --> Samples
  Tests --> Smoke
  Tests --> Deploy
```

## Shared Service Architecture

The five Python services use a common FastAPI baseline: typed request handling,
optional API key protection, request IDs, safe JSON errors, metrics, event
persistence, tests, evaluation scripts, and container/deployment manifests.

```mermaid
flowchart TD
  Client[Client or curl]
  Auth[Optional API key check]
  RequestID[Request ID middleware]
  Route[FastAPI route]
  Domain[Domain pipeline]
  Store[(SQLite event store)]
  Metrics[/metrics JSON]
  Error[Safe JSON error handler]
  Response[Typed JSON response]

  Client --> Auth --> RequestID --> Route --> Domain --> Response
  Domain --> Store
  Route --> Metrics
  Route -. exceptions .-> Error --> Response
```

## ADAAS Architecture

ADAAS adds a user-facing Flutter layer and a Node backend. The backend keeps the
same reviewer-friendly operational baseline: health checks, metrics, API key
support, smoke tests, Docker Compose, Kubernetes manifests, and CI.

```mermaid
flowchart LR
  Browser[Reviewer Browser]
  Flutter[Flutter Web App]
  Backend[Node HR Backend]
  Mongo[(MongoDB when configured)]
  Memory[(Seeded in-memory demo data)]
  Assistant[Optional assistant provider]

  Browser --> Flutter
  Flutter --> Backend
  Backend --> Mongo
  Backend --> Memory
  Backend --> Assistant
```

## Deployment Baseline

```mermaid
flowchart LR
  Repo[Repository]
  CI[GitHub Actions]
  Tests[Tests and Evals]
  Image[Container Build]
  Compose[Docker Compose]
  K8s[Kubernetes Manifests]
  Local[Local Reviewer Run]

  Repo --> CI --> Tests
  CI --> Image
  Repo --> Compose --> Local
  Repo --> K8s
```

These projects are intentionally local-first. They are credible deployable
baselines, but they do not include live cloud environments or production data.
