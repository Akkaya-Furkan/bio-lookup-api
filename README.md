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

## Run
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
uvicorn bio_lookup.main:app --host 127.0.0.1 --port 8000     # Swagger UI at /docs
```
```
GET /compound/aspirin     PubChem properties + exact-match ChEMBL record
GET /target/P00533        UniProt protein (EGFR_HUMAN)
GET /health
```
Errors: 404 record not found (the body names the upstream), 422 malformed UniProt accession, 502 upstream
failed or throttled, 504 upstream timed out. If ChEMBL fails or has no match, `/compound` still answers with
`chembl: null` (and a warning when ChEMBL was unreachable).

## Status
Skeleton works locally against the live services (aspirin, caffeine, EGFR, Swagger UI). Tests, the
`/compound/{name}/targets` endpoint, caching, Docker and deploy are next.
Part of a 30-project computational biology and scientific software portfolio.
