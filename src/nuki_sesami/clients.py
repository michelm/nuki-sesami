import json
import os


class SesamiClient:
    def __init__(self, client: dict):
        self._macaddr = client['macaddr']
        self._pubkey = client['pubkey']

    @property
    def macaddr(self) -> str:
        return self._macaddr

    @property
    def pubkey(self) -> str:
        return self._pubkey


def get_clients(prefix: str) -> list[SesamiClient]:
    fname = os.path.join(prefix, 'clients.json')
    with open(fname) as f:
        clients = json.load(f)
    return [SesamiClient(client) for client in clients]
