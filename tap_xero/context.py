from typing import List

import singer
from singer import bookmarks as bks_, Catalog

from .client import XeroClient


class Context:
    def __init__(self, config: dict, catalog: Catalog, config_path: str, state: dict = None):
        self.config: dict = config
        self.config_path: str = config_path
        self.state: dict = state
        self.catalog: Catalog = catalog
        self.client: XeroClient = XeroClient(config)

    def set_tenant(self, tenant_id: str) -> None:
        self.client.tenant_id = tenant_id

    def refresh_credentials(self) -> None:
        self.client.refresh_credentials(self.config, self.config_path)

    def check_platform_access(self) -> None:
        self.client.check_platform_access(self.config, self.config_path)

    def get_bookmark(self, path: List[str]):
        return bks_.get_bookmark(self.state, *path)

    def set_bookmark(self, path: List[str], val) -> None:
        bks_.write_bookmark(self.state, path[0], path[1], val)

    def get_offset(self, path: List[str]):
        off = bks_.get_offset(self.state, path[0])
        return (off or {}).get(path[1])

    def set_offset(self, path: List[str], val) -> None:
        bks_.set_offset(self.state, path[0], path[1], val)

    def clear_offsets(self, tap_stream_id: str) -> None:
        bks_.clear_offset(self.state, tap_stream_id)

    def update_start_date_bookmark(self, path: List[str]):
        val = self.get_bookmark(path)
        if not val:
            val = self.config["start_date"]
            self.set_bookmark(path, val)
        return val

    def write_state(self) -> None:
        singer.write_state(self.state)
