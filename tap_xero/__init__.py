import argparse
import os
from typing import List

import singer
from singer import metadata, utils
from singer.catalog import Catalog, CatalogEntry, Schema

from tap_xero import streams as STREAMS
from tap_xero.client import XeroClient
from tap_xero.context import Context
from tap_xero.custom import XeroCatalog
from tap_xero.streams import Stream

REQUIRED_CONFIG_KEYS = [
    "start_date",
    "client_id",
    "client_secret",
    "parent_id",
    "refresh_token",
]

LOGGER = singer.get_logger()

BAD_CREDS_MESSAGE = (
    "Failed to refresh OAuth token using the credentials from both the config and S3. "
    "The token might need to be reauthorized from the integration's properties "
    "or there could be another authentication issue. Please attempt to reauthorize "
    "the integration."
)


class BadCredsException(Exception):
    pass


def get_abs_path(path):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), path)


def load_schema(tap_stream_id):
    path = "schemas/{}.json".format(tap_stream_id)
    schema = utils.load_json(get_abs_path(path))
    dependencies = schema.pop("tap_schema_dependencies", [])
    refs = {}
    for sub_stream_id in dependencies:
        refs[sub_stream_id] = load_schema(sub_stream_id)
    if refs:
        singer.resolve_schema_references(schema, refs)
    return schema


def load_metadata(stream, schema):
    mdata = metadata.new()

    mdata = metadata.write(mdata, (), "table-key-properties", stream.pk_fields)
    mdata = metadata.write(
        mdata, (), "forced-replication-method", stream.replication_method
    )

    if stream.bookmark_key:
        mdata = metadata.write(
            mdata, (), "valid-replication-keys", [stream.bookmark_key]
        )

    for field_name in schema["properties"].keys():
        if field_name in stream.pk_fields or field_name == stream.bookmark_key:
            mdata = metadata.write(
                mdata, ("properties", field_name), "inclusion", "automatic"
            )
        else:
            mdata = metadata.write(
                mdata, ("properties", field_name), "inclusion", "available"
            )

    return metadata.to_list(mdata)


def ensure_credentials_are_valid(config):
    XeroClient(config).filter("currencies")


def discover() -> Catalog:
    catalog: Catalog = XeroCatalog()
    for stream in STREAMS.all_streams:
        schema_dict = load_schema(stream.tap_stream_id)
        meta_data = load_metadata(stream, schema_dict)

        schema = Schema.from_dict(schema_dict)
        catalog.streams.append(
            CatalogEntry(
                stream=stream.tap_stream_id,
                tap_stream_id=stream.tap_stream_id,
                key_properties=stream.pk_fields,
                schema=schema,
                metadata=meta_data,
                replication_key=stream.bookmark_key,
                replication_method=stream.replication_method,
            )
        )
    return catalog


def load_and_write_schema(stream):
    singer.write_schema(
        stream.tap_stream_id,
        load_schema(stream.tap_stream_id),
        stream.pk_fields,
    )


def sync(context_: Context) -> None:
    # Get 30 minutes valid refresh token to be consumed
    context_.refresh_credentials()
    # Get a new refresh token and sent it to DataSource API
    from custom import refresh_token, write_secrets

    response = refresh_token(context_.config)
    config = context_.config
    config["refresh_token"] = response["refresh_token"]
    write_secrets(config)

    tenants: List[str] = context_.config["parent_id"].split(",")
    for tenant in tenants:
        context_.set_tenant(tenant)
        context_.check_platform_access()

    currently_syncing = context_.state.get("currently_syncing")
    start_idx: int = (
        STREAMS.all_stream_ids.index(currently_syncing) if currently_syncing else 0
    )

    stream_ids_to_sync: List[str] = [
        cs.tap_stream_id for cs in context_.catalog.streams if cs.is_selected()
    ]

    streams: List[Stream] = [
        stream
        for stream in STREAMS.all_streams[start_idx:]
        if stream.tap_stream_id in stream_ids_to_sync
    ]

    for stream in streams:
        context_.state["currently_syncing"] = stream.tap_stream_id
        context_.write_state()
        load_and_write_schema(stream)
        LOGGER.info("Syncing stream: %s", stream.tap_stream_id)
        for tenant_id in tenants:
            context_.set_tenant(tenant_id)
            stream.sync(context_)

    context_.state["currently_syncing"] = None
    context_.write_state()


def main_impl() -> None:
    args: argparse.Namespace = utils.parse_args(REQUIRED_CONFIG_KEYS)
    # context_instance: Context = Context(config=args.config,
    #                                     catalog=XeroCatalog(),
    #                                     config_path=args.config_path)
    if args.discover:
        discover().dump()
    else:
        if args.catalog:
            catalog = args.catalog
        else:
            LOGGER.info("Running sync without provided Catalog. Discovering.")
            catalog = discover()

        context_instance = Context(
            config=args.config,
            catalog=catalog,
            config_path=args.config_path,
            state=args.state,
        )
        sync(context_instance)


def main() -> None:
    try:
        main_impl()
    except Exception as exc:
        LOGGER.critical(exc)
        raise exc


if __name__ == "__main__":
    main()
