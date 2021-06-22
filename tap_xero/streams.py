from abc import ABC
from typing import List

import backoff
import singer
from requests.exceptions import HTTPError
from singer import metadata, metrics, Transformer
from singer.utils import strptime_with_tz

from tap_xero import transform
from tap_xero.client import XeroClient
from tap_xero.context import Context

LOGGER = singer.get_logger()
FULL_PAGE_SIZE = 100


def _request_with_timer(tap_stream_id: str, xero: XeroClient, filter_options: dict) -> List[dict]:
    with metrics.http_request_timer(tap_stream_id) as timer:
        try:
            response = xero.filter(tap_stream_id, **filter_options)
            timer.tags[metrics.Tag.http_status_code] = 200
            return response
        except HTTPError as error:
            timer.tags[metrics.Tag.http_status_code] = error.response.status_code
            raise


class RateLimitException(Exception):
    pass


@backoff.on_exception(backoff.expo,
                      RateLimitException,
                      max_tries=10,
                      factor=2)
def _make_request(context: Context, tap_stream_id: str, filter_options: dict = None, attempts: int = 0) -> List[dict]:
    filter_options = filter_options or {}
    try:
        return _request_with_timer(tap_stream_id, context.client, filter_options)
    except HTTPError as e:
        if e.response.status_code == 401:
            if attempts == 1:
                raise Exception("Received Not Authorized response after credential refresh.") from e
            context.refresh_credentials()
            return _make_request(context, tap_stream_id, filter_options, attempts + 1)

        if e.response.status_code == 503:
            raise RateLimitException() from e

        raise HTTPError


class Stream(ABC):
    def __init__(self, tap_stream_id, pk_fields, bookmark_key="UpdatedDateUTC", format_fn=None):
        self.tap_stream_id = tap_stream_id
        self.pk_fields = pk_fields
        self.format_fn = format_fn or (lambda x: x)
        self.bookmark_key = bookmark_key
        self.replication_method = "INCREMENTAL"
        self.filter_options = {}

    def metrics(self, records: List[dict]):
        with metrics.record_counter(self.tap_stream_id) as counter:
            counter.increment(len(records))

    def write_records(self, records: List[dict], context: Context) -> None:
        stream = context.catalog.get_stream(self.tap_stream_id)
        schema: dict = stream.schema.to_dict()
        meta_data = stream.metadata
        for rec in records:
            with Transformer() as transformer:
                rec = transformer.transform(rec, schema, metadata.to_map(meta_data))
                singer.write_record(self.tap_stream_id, rec)
        self.metrics(records)

    def sync(self, context: Context) -> None:
        raise NotImplementedError("Implement this method!")


class BookmarkedStream(Stream):
    def sync(self, context: Context) -> None:
        bookmark: List[str] = [self.tap_stream_id, self.bookmark_key]
        start: str = context.update_start_date_bookmark(bookmark)
        records: List[dict] = _make_request(context, self.tap_stream_id, dict(since=start))
        if records:
            self.format_fn(records)
            self.write_records(records, context)
            max_bookmark_value = max([record[self.bookmark_key] for record in records])
            context.set_bookmark(bookmark, max_bookmark_value)
            context.write_state()


class PaginatedStream(Stream):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def sync(self, context: Context) -> None:
        bookmark: List[str] = [self.tap_stream_id, self.bookmark_key]
        offset = [self.tap_stream_id, "page"]
        start = context.update_start_date_bookmark(bookmark)
        curr_page_num = context.get_offset(offset) or 1

        self.filter_options.update(dict(since=start, order="UpdatedDateUTC ASC"))

        max_updated = start
        while True:
            context.set_offset(offset, curr_page_num)
            context.write_state()
            self.filter_options["page"] = curr_page_num
            records = _make_request(context, self.tap_stream_id, self.filter_options)
            if records:
                self.format_fn(records)
                self.write_records(records, context)
                max_updated = records[-1][self.bookmark_key]
            if not records or len(records) < FULL_PAGE_SIZE:
                break
            curr_page_num += 1
        context.clear_offsets(self.tap_stream_id)
        context.set_bookmark(bookmark, max_updated)
        context.write_state()


class Contacts(PaginatedStream):
    def __init__(self, *args, **kwargs):
        super().__init__("contacts", ["ContactID"], format_fn=transform.format_contacts, *args, **kwargs)

    def sync(self, context: Context) -> None:
        # Parameter to collect archived contacts from the Xero platform
        if context.config.get("include_archived_contacts") in ["true", True]:
            self.filter_options.update({'includeArchived': "true"})

        super().sync(context)


class Journals(Stream):
    """The Journals endpoint is a special case. It has its own way of ordering
    and paging the data. See
    https://developer.xero.com/documentation/api/journals"""

    def sync(self, context: Context) -> None:
        bookmark: List[str] = [self.tap_stream_id, self.bookmark_key]
        journal_number = context.get_bookmark(bookmark) or 0
        while True:
            filter_options = {"offset": journal_number}
            records = _make_request(context, self.tap_stream_id, filter_options)
            if records:
                self.format_fn(records)
                self.write_records(records, context)
                journal_number = max((record[self.bookmark_key] for record in records))
                context.set_bookmark(bookmark, journal_number)
                context.write_state()
            if not records or len(records) < FULL_PAGE_SIZE:
                break


class LinkedTransactions(Stream):
    """The Linked Transactions endpoint is a special case. It supports
    pagination, but not the Modified At header, but the objects returned have
    the UpdatedDateUTC timestamp in them. Therefore we must always iterate over
    all of the data, but we can manually omit records based on the
    UpdatedDateUTC property."""

    def sync(self, context: Context) -> None:
        bookmark: List[str] = [self.tap_stream_id, self.bookmark_key]
        offset: List[str] = [self.tap_stream_id, "page"]
        start = context.update_start_date_bookmark(bookmark)
        curr_page_num = context.get_offset(offset) or 1
        max_updated = start
        while True:
            context.set_offset(offset, curr_page_num)
            context.write_state()
            filter_options = {"page": curr_page_num}
            raw_records = _make_request(context, self.tap_stream_id, filter_options)
            records = [x for x in raw_records
                       if strptime_with_tz(x[self.bookmark_key]) >= strptime_with_tz(start)]
            if records:
                self.write_records(records, context)
                max_updated = records[-1][self.bookmark_key]
            if not records or len(records) < FULL_PAGE_SIZE:
                break
            curr_page_num += 1
        context.clear_offsets(self.tap_stream_id)
        context.set_bookmark(bookmark, max_updated)
        context.write_state()


class Everything(Stream):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bookmark_key = None
        self.replication_method = "FULL_TABLE"

    def sync(self, context: Context) -> None:
        records = _make_request(context, self.tap_stream_id)
        self.format_fn(records)
        self.write_records(records, context)


all_streams: List[Stream] = [
    # PAGINATED STREAMS
    # These endpoints have all the best properties: they return the
    # UpdatedDateUTC property and support the Modified After, order, and page
    # parameters
    PaginatedStream("bank_transactions", ["BankTransactionID"]),
    Contacts(),
    PaginatedStream("quotes", ["QuoteID"]),
    PaginatedStream("credit_notes", ["CreditNoteID"], format_fn=transform.format_credit_notes),
    PaginatedStream("invoices", ["InvoiceID"], format_fn=transform.format_invoices),
    PaginatedStream("manual_journals", ["ManualJournalID"]),
    PaginatedStream("overpayments", ["OverpaymentID"], format_fn=transform.format_over_pre_payments),
    PaginatedStream("payments", ["PaymentID"], format_fn=transform.format_payments),
    PaginatedStream("prepayments", ["PrepaymentID"], format_fn=transform.format_over_pre_payments),
    PaginatedStream("purchase_orders", ["PurchaseOrderID"]),
    # PaginatedStream("assets", ["assetId"]),
    # PaginatedStream("asset_types", ["assetTypeId"]),

    # JOURNALS STREAM
    # This endpoint is paginated, but in its own special snowflake way.
    Journals("journals", ["JournalID"], bookmark_key="JournalNumber", format_fn=transform.format_journals),

    # NON-PAGINATED STREAMS
    # These endpoints do not support pagination, but do support the Modified At
    # header.
    BookmarkedStream("accounts", ["AccountID"]),
    BookmarkedStream("bank_transfers", ["BankTransferID"], bookmark_key="CreatedDateUTC"),
    BookmarkedStream("employees", ["EmployeeID"]),
    BookmarkedStream("expense_claims", ["ExpenseClaimID"]),
    BookmarkedStream("items", ["ItemID"]),
    BookmarkedStream("receipts", ["ReceiptID"], format_fn=transform.format_receipts),
    BookmarkedStream("users", ["UserID"], format_fn=transform.format_users),

    # PULL EVERYTHING STREAMS
    # These endpoints do not support the Modified After header (or paging), so
    # we must pull all the data each time.
    Everything("branding_themes", ["BrandingThemeID"]),
    Everything("contact_groups", ["ContactGroupID"], format_fn=transform.format_contact_groups),
    Everything("currencies", ["Code"]),
    Everything("organisations", ["OrganisationID"]),
    Everything("repeating_invoices", ["RepeatingInvoiceID"]),
    Everything("tax_rates", ["TaxType"]),
    Everything("tracking_categories", ["TrackingCategoryID"]),
    Everything("assets", ["assetId"]),
    Everything("asset_types", ["assetTypeId"]),

    # LINKED TRANSACTIONS STREAM
    # This endpoint is not paginated, but can do some manual filtering
    LinkedTransactions("linked_transactions", ["LinkedTransactionID"], bookmark_key="UpdatedDateUTC"),
]
all_stream_ids: List[str] = [s.tap_stream_id for s in all_streams]

account_api_path = "api.xro/2.0/"
accounting_api = {
    "bank_transactions": account_api_path,
    "contacts": account_api_path,
    "quotes": account_api_path,
    "credit_notes": account_api_path,
    "invoices": account_api_path,
    "manual_journals": account_api_path,
    "overpayments": account_api_path,
    "payments": account_api_path,
    "prepayments": account_api_path,
    "purchase_orders": account_api_path,
    "assets": account_api_path,
    "journals": account_api_path,
    "accounts": account_api_path,
    "bank_transfers": account_api_path,
    "employees": account_api_path,
    "expense_claims": account_api_path,
    "items": account_api_path,
    "receipts": account_api_path,
    "users": account_api_path,
    "branding_themes": account_api_path,
    "contact_groups": account_api_path,
    "currencies": account_api_path,
    "organisations": account_api_path,
    "repeating_invoices": account_api_path,
    "tax_rates": account_api_path,
    "tracking_categories": account_api_path,
    "linked_transactions": account_api_path,
}

assets_api_path = "assets.xro/1.0/"
assets_api = {
    "assets": assets_api_path,
    "asset_types": assets_api_path
}

XERO_APIS = {**accounting_api, **assets_api}
