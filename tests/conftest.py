import pytest
import respx
from fastapi.testclient import TestClient

from bio_lookup.clients.base import Upstream
from bio_lookup.main import app

PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
UNIPROT = "https://rest.uniprot.org/uniprotkb"

PUBCHEM_ASPIRIN = {"PropertyTable": {"Properties": [{
    "CID": 2244, "Title": "Aspirin", "IUPACName": "2-acetyloxybenzoic acid", "MolecularFormula": "C9H8O4",
    "MolecularWeight": "180.16", "SMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N", "XLogP": 1.2}]}}

CHEMBL_ASPIRIN = {"molecules": [{
    "molecule_chembl_id": "CHEMBL25", "pref_name": "ASPIRIN", "max_phase": "4.0",
    "molecule_type": "Small molecule", "molecule_hierarchy": {"parent_chembl_id": "CHEMBL25"}}]}

MECH_ASPIRIN = {"mechanisms": [{"target_chembl_id": "CHEMBL2094253", "mechanism_of_action": "Cyclooxygenase inhibitor",
                                "action_type": "INHIBITOR"}]}

TARGET_COX = {"target_chembl_id": "CHEMBL2094253", "pref_name": "Cyclooxygenase", "target_type": "PROTEIN FAMILY",
              "organism": "Homo sapiens",
              "target_components": [{"accession": "P35354"}, {"accession": "P23219"}]}


def uniprot_entry(acc: str, entry_name: str, gene: str | None = "EGFR", reviewed: bool = True) -> dict:
    entry = {"entryType": "UniProtKB reviewed (Swiss-Prot)" if reviewed else "UniProtKB unreviewed (TrEMBL)",
             "primaryAccession": acc, "uniProtkbId": entry_name,
             "organism": {"scientificName": "Homo sapiens"}, "sequence": {"length": 1210},
             "comments": [{"commentType": "FUNCTION", "texts": [{"value": "Receptor tyrosine kinase."}]}]}
    name = {"fullName": {"value": "Epidermal growth factor receptor"}}
    entry["proteinDescription"] = {"recommendedName": name} if reviewed else {"submissionNames": [name]}
    if gene:
        entry["genes"] = [{"geneName": {"value": gene}}]
    return entry


@pytest.fixture(autouse=True)
def fast_env(monkeypatch):
    monkeypatch.setenv("BIO_RATE_SCALE", "0")  # skip the polite inter-request delays in tests
    monkeypatch.setenv("BIO_CACHE_TTL", "3600")


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def client(mock, monkeypatch):
    monkeypatch.setattr(Upstream, "_retry_delay", staticmethod(lambda resp, attempt: 0.0))  # no real backoff
    with TestClient(app) as c:
        yield c
