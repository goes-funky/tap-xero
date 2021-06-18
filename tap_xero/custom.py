from singer import Catalog


class XeroCatalog(Catalog):
    def __init__(self, streams=()):
        super().__init__(streams)

