from __future__ import annotations

from .base import Upstream

BASE = "https://www.ebi.ac.uk/chembl/api/data"


class ChemblClient:
    def __init__(self, client, min_interval: float = 0.1, cache=None):
        self.up = Upstream("ChEMBL", BASE, client, min_interval, cache=cache)

    async def molecule_by_inchikey(self, inchikey: str) -> dict | None:
        """Exact structure match; an unknown key gives an empty list, which is not an error."""
        data = await self.up.get_json("/molecule.json",
                                      {"molecule_structures__standard_inchi_key": inchikey})
        molecules = data.get("molecules", [])
        return molecules[0] if molecules else None

    async def mechanisms(self, parent_chembl_id: str) -> list[dict]:
        """Mechanism rows are recorded on the salt form (imatinib mesylate), so ask by parent molecule."""
        data = await self.up.get_json("/mechanism.json",
                                      {"parent_molecule_chembl_id": parent_chembl_id, "limit": 100})
        return data.get("mechanisms", [])

    async def target(self, target_chembl_id: str) -> dict:
        return await self.up.get_json(f"/target/{target_chembl_id}.json")
