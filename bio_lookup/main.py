"""FastAPI app: GET /compound/{name} and GET /target/{uniprot_id}."""
from __future__ import annotations

import re
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse

from . import __version__
from .clients.chembl import ChemblClient
from .clients.pubchem import PubChemClient
from .clients.uniprot import UniProtClient
from .errors import NotFoundError, UpstreamError
from .models import Compound, Target
from .parsers import parse_chembl, parse_pubchem, parse_uniprot

USER_AGENT = f"bio-lookup-api/{__version__} (+https://github.com/Akkaya-Furkan/bio-lookup-api)"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# UniProt's documented accession format: https://www.uniprot.org/help/accession_numbers
ACCESSION = re.compile(r"[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as http:
        app.state.pubchem = PubChemClient(http)
        app.state.chembl = ChemblClient(http)
        app.state.uniprot = UniProtClient(http)
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


@app.get("/target/{uniprot_id}", response_model=Target, summary="Protein by UniProt accession",
         responses={404: {"description": "UniProt has no such entry"},
                    422: {"description": "Not a valid UniProt accession"},
                    502: {"description": "UniProt failed"}, 504: {"description": "UniProt timed out"}})
async def target(request: Request, uniprot_id: str = Path(examples=["P00533"])):
    accession = uniprot_id.upper()
    if not ACCESSION.fullmatch(accession):
        raise HTTPException(status_code=422, detail=f"{uniprot_id!r} is not a valid UniProt accession")
    return parse_uniprot(await request.app.state.uniprot.entry(accession))
