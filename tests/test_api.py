import httpx

from .conftest import (
    CHEMBL,
    CHEMBL_ASPIRIN,
    MECH_ASPIRIN,
    PUBCHEM,
    PUBCHEM_ASPIRIN,
    TARGET_COX,
    UNIPROT,
    uniprot_entry,
)


def mock_aspirin(mock, chembl=CHEMBL_ASPIRIN):
    mock.get(url__regex=rf"{PUBCHEM}/compound/name/aspirin/property/.*").respond(json=PUBCHEM_ASPIRIN)
    return mock.get(f"{CHEMBL}/molecule.json").respond(json=chembl)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_compound_combines_pubchem_and_chembl(client, mock):
    chembl = mock_aspirin(mock)
    r = client.get("/compound/aspirin")
    assert r.status_code == 200
    body = r.json()
    assert (body["cid"], body["formula"], body["molecular_weight"]) == (2244, "C9H8O4", 180.16)
    assert body["chembl"]["chembl_id"] == "CHEMBL25" and body["warnings"] == []
    assert chembl.calls[0].request.url.params["molecule_structures__standard_inchi_key"] == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"


def test_unknown_compound_is_404_and_names_the_source(client, mock):
    mock.get(url__regex=rf"{PUBCHEM}/compound/name/zzz/property/.*").respond(404)
    r = client.get("/compound/zzz")
    assert r.status_code == 404 and r.json()["source"] == "PubChem"


def test_compound_without_a_chembl_match_is_still_returned(client, mock):
    mock_aspirin(mock, chembl={"molecules": []})
    body = client.get("/compound/aspirin").json()
    assert body["chembl"] is None and body["warnings"] == []


def test_chembl_outage_gives_a_partial_result(client, mock):
    mock.get(url__regex=rf"{PUBCHEM}/compound/name/aspirin/property/.*").respond(json=PUBCHEM_ASPIRIN)
    mock.get(f"{CHEMBL}/molecule.json").respond(503)
    r = client.get("/compound/aspirin")
    assert r.status_code == 200 and r.json()["chembl"] is None
    assert "ChEMBL unavailable" in r.json()["warnings"][0]


def test_pubchem_outage_is_502(client, mock):
    mock.get(url__regex=rf"{PUBCHEM}/compound/name/aspirin/property/.*").respond(503)
    r = client.get("/compound/aspirin")
    assert r.status_code == 502 and r.json()["source"] == "PubChem"


def test_pubchem_timeout_is_504(client, mock):
    mock.get(url__regex=rf"{PUBCHEM}/compound/name/aspirin/property/.*").mock(
        side_effect=httpx.ReadTimeout("slow"))
    assert client.get("/compound/aspirin").status_code == 504


def test_second_request_is_served_from_cache(client, mock):
    chembl = mock_aspirin(mock)
    client.get("/compound/aspirin")
    client.get("/compound/aspirin")
    assert chembl.call_count == 1


def test_target(client, mock):
    mock.get(f"{UNIPROT}/P00533.json").respond(json=uniprot_entry("P00533", "EGFR_HUMAN"))
    r = client.get("/target/p00533")  # lower case is normalised
    assert r.status_code == 200 and r.json()["entry_name"] == "EGFR_HUMAN" and r.json()["reviewed"] is True


def test_malformed_accession_is_422_without_calling_uniprot(client, mock):
    route = mock.get(url__startswith=UNIPROT).respond(200, json={})
    assert client.get("/target/NOTANACCESSION").status_code == 422
    assert route.call_count == 0


def test_unknown_accession_is_404(client, mock):
    mock.get(f"{UNIPROT}/P12345.json").respond(404)
    r = client.get("/target/P12345")
    assert r.status_code == 404 and r.json()["source"] == "UniProt"


def mock_targets(mock, uniprot_ok=("P35354", "P23219")):
    mock_aspirin(mock)
    mech = mock.get(f"{CHEMBL}/mechanism.json").respond(json=MECH_ASPIRIN)
    mock.get(f"{CHEMBL}/target/CHEMBL2094253.json").respond(json=TARGET_COX)
    for acc, gene in (("P35354", "PTGS2"), ("P23219", "PTGS1")):
        if acc in uniprot_ok:
            mock.get(f"{UNIPROT}/{acc}.json").respond(json=uniprot_entry(acc, f"{gene}_HUMAN", gene))
        else:
            mock.get(f"{UNIPROT}/{acc}.json").respond(404)
    return mech


def test_targets_merges_the_three_sources(client, mock):
    mock_targets(mock)
    body = client.get("/compound/aspirin/targets").json()
    assert body["chembl_id"] == "CHEMBL25" and body["warnings"] == []
    (hit,) = body["targets"]
    assert hit["target_type"] == "PROTEIN FAMILY" and hit["mechanisms"] == ["Cyclooxygenase inhibitor"]
    assert [p["gene"] for p in hit["proteins"]] == ["PTGS2", "PTGS1"]


def test_targets_look_up_mechanisms_by_parent_molecule(client, mock):
    """ChEMBL stores mechanisms on the salt (imatinib mesylate), so the parent id must be used."""
    salt = {"molecules": [{"molecule_chembl_id": "CHEMBL1642",
                           "molecule_hierarchy": {"parent_chembl_id": "CHEMBL941"}}]}
    mock_targets(mock)
    mock.get(f"{CHEMBL}/molecule.json").respond(json=salt)
    mech = mock.get(f"{CHEMBL}/mechanism.json").respond(json=MECH_ASPIRIN)
    body = client.get("/compound/aspirin/targets").json()
    assert mech.calls[0].request.url.params["parent_molecule_chembl_id"] == "CHEMBL941"
    assert body["parent_chembl_id"] == "CHEMBL941"


def test_targets_empty_with_warning_when_chembl_lists_no_mechanism(client, mock):
    mock_aspirin(mock)
    mock.get(f"{CHEMBL}/mechanism.json").respond(json={"mechanisms": []})
    body = client.get("/compound/aspirin/targets").json()
    assert body["targets"] == [] and "no mechanism" in body["warnings"][0]


def test_targets_empty_with_warning_when_chembl_has_no_record(client, mock):
    mock_aspirin(mock, chembl={"molecules": []})
    body = client.get("/compound/aspirin/targets").json()
    assert body["targets"] == [] and body["chembl_id"] is None and "no record" in body["warnings"][0]


def test_one_failing_uniprot_entry_does_not_lose_the_rest(client, mock):
    mock_targets(mock, uniprot_ok=("P35354",))
    body = client.get("/compound/aspirin/targets").json()
    assert [p["accession"] for p in body["targets"][0]["proteins"]] == ["P35354"]
    assert "P23219" in body["warnings"][0]


def test_chembl_outage_fails_the_targets_endpoint(client, mock):
    mock.get(url__regex=rf"{PUBCHEM}/compound/name/aspirin/property/.*").respond(json=PUBCHEM_ASPIRIN)
    mock.get(f"{CHEMBL}/molecule.json").respond(503)
    r = client.get("/compound/aspirin/targets")
    assert r.status_code == 502 and r.json()["source"] == "ChEMBL"


def test_openapi_documents_all_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/compound/{name}", "/compound/{name}/targets", "/target/{uniprot_id}", "/health"} <= set(paths)
