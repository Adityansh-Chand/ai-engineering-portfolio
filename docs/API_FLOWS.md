# API Flow Diagrams

These flows show how an external reviewer can reason about each API without
reading the full implementation first. The common hardening path is repeated
across services: request ID, optional API key, domain logic, JSON response,
metrics, and event/audit persistence.

## Retrieval Query

Repository: `enterprise-rag-knowledge-system`

```mermaid
sequenceDiagram
  participant C as Client
  participant API as FastAPI /query
  participant Auth as Optional API Key
  participant Search as Retrieval Pipeline
  participant Store as SQLite Events
  participant Metrics as /metrics

  C->>API: POST /query
  API->>Auth: Validate X-API-Key when API_KEY is set
  API->>Search: Retrieve, rank, and compose answer
  Search-->>API: Answer, confidence, sources
  API->>Store: Persist request event
  API->>Metrics: Increment counters
  API-->>C: JSON response with request_id
```

## Customer Operations Decision

Repository: `ai-proactive-customer-operations`

```mermaid
sequenceDiagram
  participant C as Client
  participant API as FastAPI /decide
  participant Planner as Planner
  participant Policy as Policy Specialist
  participant Action as Action Selector
  participant Store as SQLite Events

  C->>API: POST /decide
  API->>Planner: Classify intent and priority
  Planner->>Policy: Check policy and customer context
  Policy->>Action: Choose recommended action
  Action-->>API: Decision trace
  API->>Store: Persist event/audit record
  API-->>C: Decision JSON with request_id
```

## Scoring Services

Repositories: `ai-incident-detection-platform`, `ai-sales-intelligence-engine`

```mermaid
sequenceDiagram
  participant C as Client
  participant API as FastAPI /score
  participant Validator as Schema Validator
  participant Model as Scoring Pipeline
  participant Store as SQLite Events
  participant Metrics as /metrics

  C->>API: POST /score
  API->>Validator: Validate payload
  Validator->>Model: Build features and score
  Model-->>API: Score, label, explanation
  API->>Store: Persist scored event
  API->>Metrics: Update request counters
  API-->>C: Score response with request_id
```

## Meeting Intelligence

Repository: `autonomous-meeting-intelligence`

```mermaid
sequenceDiagram
  participant C as Client
  participant API as FastAPI /analyze
  participant Parser as Transcript Parser
  participant Extractor as Summary Extractor
  participant Store as SQLite Events

  C->>API: POST /analyze
  API->>Parser: Normalize transcript
  Parser->>Extractor: Extract summary, decisions, and action items
  Extractor-->>API: Structured meeting record
  API->>Store: Persist analysis event
  API-->>C: Analysis JSON with request_id
```

## ADAAS HR Assistant

Repository: `ADAAS`

```mermaid
sequenceDiagram
  participant U as User
  participant UI as Flutter App
  participant API as Node HR Backend
  participant Data as MongoDB or Seeded Data
  participant Provider as Optional Assistant Provider

  U->>UI: Ask HR question or submit leave action
  UI->>API: REST request with optional X-API-Key
  API->>Data: Read or write HR records
  API->>Provider: Use provider only when configured
  Provider-->>API: Assistant response
  Data-->>API: HR data
  API-->>UI: JSON response
  UI-->>U: Render answer or workflow result
```

## Common Error Path

```mermaid
sequenceDiagram
  participant C as Client
  participant API as Service API
  participant Handler as Safe Error Handler
  participant Store as Event Store

  C->>API: Invalid or unauthorized request
  API->>Handler: Convert exception to safe JSON
  Handler->>Store: Persist failure event when applicable
  Handler-->>C: Status code, error message, request_id
```
