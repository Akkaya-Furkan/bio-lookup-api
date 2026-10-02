"""Pure functions: raw upstream JSON -> our models. No I/O, so they are easy to test."""
from __future__ import annotations

from .models import ChemblRef, Compound, Target


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_pubchem(props: dict, query: str) -> Compound:
    cid = props["CID"]
    return Compound(
        query=query, cid=cid, name=props.get("Title"), iupac_name=props.get("IUPACName"),
        formula=props.get("MolecularFormula"), molecular_weight=_float(props.get("MolecularWeight")),
        smiles=props.get("SMILES"), inchikey=props.get("InChIKey"), xlogp=_float(props.get("XLogP")),
        pubchem_url=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
    )


def parse_chembl(molecule: dict) -> ChemblRef:
    cid = molecule["molecule_chembl_id"]
    return ChemblRef(
        chembl_id=cid, pref_name=molecule.get("pref_name"), max_phase=_float(molecule.get("max_phase")),
        molecule_type=molecule.get("molecule_type"),
        url=f"https://www.ebi.ac.uk/chembl/compound_report_card/{cid}/",
    )


def _protein_name(entry: dict) -> str | None:
    desc = entry.get("proteinDescription", {})
    name = desc.get("recommendedName") or (desc.get("submissionNames") or [None])[0]
    return name["fullName"]["value"] if name else None  # unreviewed entries only have submissionNames


def parse_uniprot(entry: dict) -> Target:
    genes = entry.get("genes") or []
    gene = genes[0].get("geneName", {}).get("value") if genes else None
    function = next((c["texts"][0]["value"] for c in entry.get("comments", [])
                     if c.get("commentType") == "FUNCTION" and c.get("texts")), None)
    acc = entry["primaryAccession"]
    return Target(
        accession=acc, entry_name=entry["uniProtkbId"], protein_name=_protein_name(entry), gene=gene,
        organism=entry.get("organism", {}).get("scientificName"),
        sequence_length=entry.get("sequence", {}).get("length"), function=function,
        reviewed=entry.get("entryType", "").startswith("UniProtKB reviewed"),
        url=f"https://www.uniprot.org/uniprotkb/{acc}/entry",
    )
