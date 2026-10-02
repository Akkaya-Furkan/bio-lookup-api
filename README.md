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
Docker: `docker build -t bio-lookup-api . && docker run -p 8000:8000 bio-lookup-api` (honours `$PORT`).

Deploy on Render: New > Blueprint, pick this repo; `render.yaml` sets the Docker build, the free plan, the
Frankfurt region and the `/health` check. The free plan sleeps when idle, so the first request after a pause is slow.

## Endpoints
| Endpoint | Returns |
| --- | --- |
| `GET /compound/{name}` | PubChem properties plus the ChEMBL record, matched exactly by InChIKey |
| `GET /compound/{name}/targets` | name -> ChEMBL mechanisms -> targets -> UniProt proteins |
| `GET /target/{uniprot_id}` | UniProt protein: name, gene, organism, length, function |
| `GET /health`, `/docs`, `/openapi.json` | liveness check and the Swagger UI |

Example: `/compound/imatinib/targets` lists ABL1, PDGFRB, KIT and the BCR-ABL fusion with their UniProt entries;
`/compound/aspirin/targets` returns one target, a protein family, with COX-1 and COX-2 under it.

Notes on behaviour:
- ChEMBL records mechanisms on the salt form (imatinib mesylate), so they are looked up by **parent** molecule;
  querying by the molecule itself silently returns nothing for imatinib.
- A compound with no ChEMBL record or no recorded mechanism gives an empty `targets` list and a warning, not an error.
- `/compound/{name}` still answers if ChEMBL is down (`chembl: null` and a warning); `/targets` cannot, so it fails.

## Errors
404 record not found (the body names the upstream), 422 malformed UniProt accession (checked before calling
UniProt), 502 upstream failed or throttled, 504 upstream timed out. Upstream calls have a 10 s timeout, two retries
with backoff, honour `Retry-After` (capped at 10 s) and are spaced per host (PubChem: 4 requests/s).

## Cache and configuration
Successful upstream answers are cached in memory (LRU) for an hour, "not found" for 5 minutes, failures never.
| Variable | Default | Meaning |
| --- | --- | --- |
| `BIO_CACHE_TTL` | 3600 | seconds; 0 turns the cache off |
| `BIO_CACHE_SIZE` | 1024 | maximum cached responses |
| `BIO_RATE_SCALE` | 1 | multiplies the per-host request spacing; 0 disables it (tests) |

## Tests
```bash
pytest -q        # 43 tests, no network: the three upstreams are mocked with respx
ruff check .
```
CI runs both on Python 3.10 and 3.12, then builds the Docker image, starts it and checks `/health` and `/docs`.
The suite covers the parsers, the cache (with a fake clock), the HTTP layer (retries, `Retry-After`, timeouts, rate
spacing, cache rules) and every endpoint including partial failures. The parent-molecule lookup, caching, the 504
mapping and the accession check were each switched off by hand to confirm a test fails without them.

## Limitations
- The cache is per process and does not stop two simultaneous misses from both calling the upstream.
- `/targets` shows at most 10 targets and 15 proteins per compound (a warning says when it truncates).
- Only ChEMBL mechanism-of-action targets are listed, not every bioactivity measurement.
- Upstream schemas can change; the parsers are the only place that reads them.

## Status
Local: all endpoints checked against the live services (aspirin, imatinib, caffeine, EGFR). Public deploy pending.
Part of a 30-project computational biology and scientific software portfolio.
