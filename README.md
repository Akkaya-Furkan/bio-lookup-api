# Compound/target lookup API

**Question.** One API that resolves a compound to its properties, bioactivities and protein targets.

## Data
PubChem PUG REST, ChEMBL, UniProt.

## Approach
1. FastAPI + httpx (async) + pydantic
2. Endpoints: /compound/{name}, /target/{uniprot_id}, /compound/{name}/targets
3. Timeouts, error handling, rate-limit compliance, TTL cache
4. pytest + respx (no network in tests), Dockerfile

## Deliverables
Deployed API with Swagger docs and green CI.

## Status
Planned — part of a 30-project computational biology and scientific software portfolio.
