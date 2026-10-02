from __future__ import annotations

from urllib.parse import quote

from .base import Upstream

BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PROPERTIES = "Title,MolecularFormula,MolecularWeight,SMILES,InChIKey,IUPACName,XLogP"


class PubChemClient:
    def __init__(self, client, min_interval: float = 0.25):  # PubChem allows 5 requests/s
        self.up = Upstream("PubChem", BASE, client, min_interval)

    async def compound(self, name: str) -> dict:
        data = await self.up.get_json(f"/compound/name/{quote(name, safe='')}/property/{PROPERTIES}/JSON")
        return data["PropertyTable"]["Properties"][0]
