from __future__ import annotations

from pydantic import BaseModel, Field


class ChemblRef(BaseModel):
    chembl_id: str
    pref_name: str | None = None
    max_phase: float | None = Field(None, description="Highest clinical phase reached (4 = approved drug)")
    molecule_type: str | None = None
    url: str


class Compound(BaseModel):
    query: str
    cid: int
    name: str | None = Field(None, description="PubChem title")
    iupac_name: str | None = None
    formula: str | None = None
    molecular_weight: float | None = None
    smiles: str | None = None
    inchikey: str | None = None
    xlogp: float | None = None
    pubchem_url: str
    chembl: ChemblRef | None = Field(None, description="Null when ChEMBL has no matching structure")
    warnings: list[str] = Field(default_factory=list, description="Partial-result notes, e.g. ChEMBL unavailable")


class Target(BaseModel):
    accession: str
    entry_name: str
    protein_name: str | None = None
    gene: str | None = None
    organism: str | None = None
    sequence_length: int | None = None
    function: str | None = Field(None, description="First FUNCTION annotation in UniProt")
    reviewed: bool = Field(description="True for Swiss-Prot (manually curated) entries")
    url: str
