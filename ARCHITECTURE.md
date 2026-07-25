# Curate Architecture

## Overview

Curate is composed of three main layers:

1. An offline catalogue pipeline that prepares product data and embeddings.
2. A runtime recommendation pipeline that turns a user query into structured recommendations.
3. A web application that presents the results and captures follow-up refinement.

## High-level flow

```text
User query
  -> Intent extraction
  -> Hard filters + retrieval
  -> Deterministic pre-ranking
  -> LLM reranking + explanation
  -> Grouped recommendation response
  -> React UI rendering
```

## Components

### 1. Offline pipeline

The offline pipeline ingests product data, applies hygiene and validation rules, enriches items conservatively, and builds embeddings for retrieval.

Key responsibilities:
- Load and normalize catalogue records
- Apply trust-tiered enrichment rules
- Generate and store embeddings
- Produce a catalogue index and manifest for runtime verification

### 2. Runtime recommendation pipeline

The runtime path is orchestrated by the backend services layer.

Flow:
- The API receives a query from the frontend.
- A generation provider extracts structured intent and sub-needs.
- Deterministic services apply hard filters and vector retrieval.
- A pre-ranker narrows the candidate set.
- A second LLM pass reranks and produces grounded explanations.
- The response is returned as grouped recommendations.

### 3. Frontend experience

The React frontend provides:
- a prompt input panel
- assumption and refinement handling
- grouped result cards
- product details and explanation surfaces

## Backend structure

- app/main.py — app factory, middleware, and lifecycle hooks
- app/config.py — environment-driven configuration
- app/schemas/ — request, response, and product domain models
- app/providers/ — generation and embedding provider integrations
- app/catalogue/ — catalogue loading and retrieval indexing
- app/services/ — intent extraction, retrieval, scoring, ranking, and orchestration
- app/api/ — HTTP routes and dependency wiring

## Design principles

- Trust tiers govern filtering and ranking behavior.
- Missing metadata is preferred over fabricated metadata.
- Embedding configuration is pinned and must remain consistent across build and query time.
- The system favors deterministic logic before LLM-based refinement.
- No runtime claims are made without measured evidence.

## Operational notes

- The backend is intended to run with a single worker for session-local behavior.
- Environment values such as API keys and origins are loaded from configuration rather than hard-coded.
- Large source data files remain external to the repository and are never committed.

## Future direction

The current implementation is focused on a reliable, explainable first version of Curate. Once the core retrieval and ranking loop is working well, the system can expand to richer refinement flows, better personalization, and broader catalogue coverage.
