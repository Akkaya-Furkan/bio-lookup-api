from bio_lookup.parsers import (
    component_accessions,
    group_mechanisms,
    parse_chembl,
    parse_pubchem,
    parse_target_hit,
    parse_uniprot,
)

from .conftest import CHEMBL_ASPIRIN, PUBCHEM_ASPIRIN, TARGET_COX, uniprot_entry


def test_pubchem_fields_and_numeric_conversion():
    c = parse_pubchem(PUBCHEM_ASPIRIN["PropertyTable"]["Properties"][0], "aspirin")
    assert (c.cid, c.formula, c.molecular_weight, c.xlogp) == (2244, "C9H8O4", 180.16, 1.2)
    assert c.pubchem_url.endswith("/compound/2244") and c.chembl is None


def test_pubchem_tolerates_missing_fields():
    c = parse_pubchem({"CID": 1}, "x")
    assert c.name is None and c.molecular_weight is None and c.xlogp is None


def test_chembl_reads_the_parent_molecule():
    ref = parse_chembl(CHEMBL_ASPIRIN["molecules"][0])
    assert (ref.chembl_id, ref.parent_chembl_id, ref.max_phase) == ("CHEMBL25", "CHEMBL25", 4.0)


def test_chembl_without_hierarchy():
    assert parse_chembl({"molecule_chembl_id": "CHEMBL1"}).parent_chembl_id is None


def test_uniprot_reviewed_entry():
    t = parse_uniprot(uniprot_entry("P00533", "EGFR_HUMAN"))
    assert (t.gene, t.reviewed, t.sequence_length) == ("EGFR", True, 1210)
    assert t.protein_name == "Epidermal growth factor receptor" and t.function == "Receptor tyrosine kinase."


def test_uniprot_unreviewed_entry_falls_back_to_submission_name():
    t = parse_uniprot(uniprot_entry("A0A024R161", "A0A024R161_HUMAN", reviewed=False))
    assert t.reviewed is False and t.protein_name == "Epidermal growth factor receptor"


def test_uniprot_without_gene_or_function():
    entry = uniprot_entry("P1", "X", gene=None)
    entry["comments"] = []
    t = parse_uniprot(entry)
    assert t.gene is None and t.function is None


def test_group_mechanisms_dedupes_and_keeps_order():
    rows = [{"target_chembl_id": "T1", "mechanism_of_action": "A", "action_type": "INHIBITOR"},
            {"target_chembl_id": "T1", "mechanism_of_action": "A", "action_type": "INHIBITOR"},
            {"target_chembl_id": "T1", "mechanism_of_action": "B", "action_type": "BLOCKER"},
            {"target_chembl_id": "T2", "mechanism_of_action": "C", "action_type": "AGONIST"},
            {"mechanism_of_action": "orphan"}]
    g = group_mechanisms(rows)
    assert list(g) == ["T1", "T2"]
    assert g["T1"] == {"mechanisms": ["A", "B"], "action_types": ["INHIBITOR", "BLOCKER"]}


def test_target_hit_and_components():
    assert component_accessions(TARGET_COX) == ["P35354", "P23219"]
    assert component_accessions({"target_components": [{"accession": None}]}) == []
    hit = parse_target_hit(TARGET_COX, {"mechanisms": ["m"], "action_types": ["a"]}, [])
    assert (hit.chembl_target_id, hit.target_type) == ("CHEMBL2094253", "PROTEIN FAMILY")
