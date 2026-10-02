"""FastAPI app: GET /compound/{name} and GET /target/{uniprot_id}."""
from __future__ import annotations

import asyncio
import os
import re
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse

from . import __version__
from .cache import TTLCache
from .clients.chembl import ChemblClient
from .clients.pubchem import PubChemClient
from .clients.uniprot import UniProtClient
from .errors import LookupFailure, NotFoundError, UpstreamError
from .models import Compound, CompoundTargets, Target
from .parsers import (
    component_accessions,
    group_mechanisms,
    parse_chembl,
    parse_pubchem,
    parse_target_hit,
    parse_uniprot,
)

USER_AGENT = f"bio-lookup-api/{__version__} (+https://github.com/Akkaya-Furkan/bio-lookup-api)"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# UniProt's documented accession format: https://www.uniprot.org/help/accession_numbers
MAX_TARGETS, MAX_PROTEINS = 10, 15  # caps for /compound/{name}/targets
ACCESSION = re.compile(r"[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as http:
        # read at startup, not import: tests set BIO_RATE_SCALE=0 to skip the polite delays
        scale = float(os.getenv("BIO_RATE_SCALE", "1"))
        cache = TTLCache(ttl=float(os.getenv("BIO_CACHE_TTL", "3600")),
                         maxsize=int(os.getenv("BIO_CACHE_SIZE", "1024")))
        app.state.cache = cache
        app.state.pubchem = PubChemClient(http, 0.25 * scale, cache)
        app.state.chembl = ChemblClient(http, 0.1 * scale, cache)
        app.state.uniprot = UniProtClient(http, 0.05 * scale, cache)
        yield


app = FastAPI(
    title="bio-lookup-api",
    version=__version__,
    description="Resolve a compound name to PubChem and ChEMBL data, and a UniProt accession to its protein. "
                "Upstream timeouts and throttling are mapped to 504 and 502; a missing record is 404.",
    lifespan=lifespan,
)


@app.exception_handler(NotFoundError)
async def not_found(_: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": exc.detail, "source": exc.source})


@app.exception_handler(UpstreamError)
async def upstream_failed(_: Request, exc: UpstreamError):
    return JSONResponse(status_code=504 if exc.timeout else 502,
                        content={"detail": exc.detail, "source": exc.source})


@app.get("/health", summary="Liveness check")
async def health():
    return {"status": "ok", "version": __version__}


@app.get("/compound/{name}", response_model=Compound, summary="Compound by name",
         responses={404: {"description": "PubChem has no compound with that name"},
                    502: {"description": "An upstream service failed"},
                    504: {"description": "An upstream service timed out"}})
async def compound(request: Request, name: str = Path(min_length=1, max_length=100, examples=["aspirin"])):
    """PubChem properties plus the matching ChEMBL record (matched exactly by InChIKey).

    If ChEMBL fails or has no match the compound is still returned, with `chembl` null and a warning."""
    st = request.app.state
    result = parse_pubchem(await st.pubchem.compound(name), name)
    if result.inchikey:
        try:
            molecule = await st.chembl.molecule_by_inchikey(result.inchikey)
            if molecule:
                result.chembl = parse_chembl(molecule)
        except UpstreamError as e:
            result.warnings.append(f"ChEMBL unavailable: {e.detail}")
    return result


@app.get("/compound/{name}/targets", response_model=CompoundTargets, summary="Protein targets of a compound",
         responses={404: {"description": "PubChem has no compound with that name"},
                    502: {"description": "An upstream service failed"},
                    504: {"description": "An upstream service timed out"}})
async def compound_targets(request: Request,
                           name: str = Path(min_length=1, max_length=100, examples=["imatinib"])):
    """Name -> PubChem structure -> ChEMBL molecule -> mechanisms -> targets -> UniProt proteins.

    ChEMBL records mechanisms on the salt form, so they are looked up by parent molecule. A target can be a
    protein family (aspirin: COX-1 and COX-2), so each target lists its UniProt entries. A compound with no
    ChEMBL record or no recorded mechanism returns an empty list with a warning, not an error."""
    st = request.app.state
    pub = parse_pubchem(await st.pubchem.compound(name), name)
    out = CompoundTargets(query=name, cid=pub.cid, name=pub.name)
    molecule = await st.chembl.molecule_by_inchikey(pub.inchikey) if pub.inchikey else None
    if not molecule:
        out.warnings.append("ChEMBL has no record for this structure")
        return out
    ref = parse_chembl(molecule)
    out.chembl_id, out.parent_chembl_id = ref.chembl_id, ref.parent_chembl_id
    grouped = group_mechanisms(await st.chembl.mechanisms(ref.parent_chembl_id or ref.chembl_id))
    if not grouped:
        out.warnings.append(f"ChEMBL lists no mechanism of action for {ref.parent_chembl_id or ref.chembl_id}")
        return out
    if len(grouped) > MAX_TARGETS:
        out.warnings.append(f"{len(grouped)} targets found, showing the first {MAX_TARGETS}")
    ids = list(grouped)[:MAX_TARGETS]
    targets = await asyncio.gather(*(st.chembl.target(t) for t in ids))
    budget = MAX_PROTEINS
    for tid, tdata in zip(ids, targets):
        accessions = component_accessions(tdata)[:budget]
        budget -= len(accessions)
        results = await asyncio.gather(*(st.uniprot.entry(a) for a in accessions), return_exceptions=True)
        proteins = []
        for acc, res in zip(accessions, results):
            if isinstance(res, LookupFailure):
                out.warnings.append(f"UniProt {acc}: {res.detail}")
            elif isinstance(res, BaseException):
                raise res
            else:
                proteins.append(parse_uniprot(res))
        out.targets.append(parse_target_hit(tdata, grouped[tid], proteins))
    return out


@app.get("/target/{uniprot_id}", response_model=Target, summary="Protein by UniProt accession",
         responses={404: {"description": "UniProt has no such entry"},
                    422: {"description": "Not a valid UniProt accession"},
                    502: {"description": "UniProt failed"}, 504: {"description": "UniProt timed out"}})
async def target(request: Request, uniprot_id: str = Path(examples=["P00533"])):
    accession = uniprot_id.upper()
    if not ACCESSION.fullmatch(accession):
        raise HTTPException(status_code=422, detail=f"{uniprot_id!r} is not a valid UniProt accession")
    return parse_uniprot(await request.app.state.uniprot.entry(accession))
