from typing import List

import singer
from singer import bookmarks as bookmarks_, Catalog

from .client import XeroClient
from .custom_bookmarks import ensure_bookmark_path


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
        return bookmarks_.get_bookmark(self.state, *path)

    def set_bookmark(self, path: List[str], val) -> None:
        tap_stream_id, key = path
        bookmarks_.write_bookmark(self.state, tap_stream_id, key, val)

    def get_offset(self, path: List[str]):
        tap_stream_id, key = path
        off = bookmarks_.get_offset(self.state, tap_stream_id)
        return (off or {}).get(key)

    def set_offset(self, path: List[str], val) -> None:
        tap_stream_id, key = path
        bookmarks_.set_offset(self.state, tap_stream_id, key, val)

    def clear_offsets(self, tap_stream_id: str) -> None:
        state = ensure_bookmark_path(self.state, ['bookmarks', tap_stream_id, "offset"])
        state['bookmarks'][tap_stream_id].pop("offset")

    def update_start_date_bookmark(self, path: List[str]) -> str:
        val = self.get_bookmark(path)
        if not val:
            val = self.config["start_date"]
            self.set_bookmark(path, val)
        return val

    def write_state(self) -> None:
        singer.write_state(self.state)
