from singer import Catalog


class XeroCatalog(Catalog):
    def __init__(self, streams=None):
        if streams is None:
            streams = []
        super().__init__(streams)
