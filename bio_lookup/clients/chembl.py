from __future__ import annotations

from .base import Upstream

BASE = "https://www.ebi.ac.uk/chembl/api/data"


class ChemblClient:
    def __init__(self, client, min_interval: float = 0.1):
        self.up = Upstream("ChEMBL", BASE, client, min_interval)

    async def molecule_by_inchikey(self, inchikey: str) -> dict | None:
        """Exact structure match; an unknown key gives an empty list, which is not an error."""
        data = await self.up.get_json("/molecule.json",
                                      {"molecule_structures__standard_inchi_key": inchikey})
        molecules = data.get("molecules", [])
        return molecules[0] if molecules else None
