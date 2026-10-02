from __future__ import annotations

from .base import Upstream

BASE = "https://rest.uniprot.org/uniprotkb"


class UniProtClient:
    def __init__(self, client, min_interval: float = 0.05, cache=None):
        self.up = Upstream("UniProt", BASE, client, min_interval, cache=cache)

    async def entry(self, accession: str) -> dict:
        return await self.up.get_json(f"/{accession}.json")
