# tap-xero

This is a [Singer](https://singer.io) tap that produces JSON-formatted data following
the [Singer spec](https://github.com/singer-io/getting-started/blob/master/SPEC.md).

This tap:

- Pulls raw data from Xero's [API](https://developer.xero.com/documentation/)
- Extracts the following resources from Xero
    - [Bank Transactions](https://developer.xero.com/documentation/api/banktransactions)
    - [Contacts](https://developer.xero.com/documentation/api/contacts)
    - [Credit Notes](https://developer.xero.com/documentation/api/credit-notes)
    - [Invoices](https://developer.xero.com/documentation/api/invoices)
    - [Manual Journals](https://developer.xero.com/documentation/api/manual-journals)
    - [Overpayments](https://developer.xero.com/documentation/api/overpayments)
    - [Prepayments](https://developer.xero.com/documentation/api/prepayments)
    - [Purchase Orders](https://developer.xero.com/documentation/api/purchase-orders)
    - [Journals](https://developer.xero.com/documentation/api/journals)
    - [Accounts](https://developer.xero.com/documentation/api/accounts)
    - [Bank Transfers](https://developer.xero.com/documentation/api/bank-transfers)
    - [Employees](https://developer.xero.com/documentation/api/employees)
    - [Expense Claims](https://developer.xero.com/documentation/api/expense-claims)
    - [Items](https://developer.xero.com/documentation/api/items)
    - [Payments](https://developer.xero.com/documentation/api/payments)
    - [Receipts](https://developer.xero.com/documentation/api/receipts)
    - [Users](https://developer.xero.com/documentation/api/users)
    - [Branding Themes](https://developer.xero.com/documentation/api/branding-themes)
    - [Contact Groups](https://developer.xero.com/documentation/api/contactgroups)
    - [Currencies](https://developer.xero.com/documentation/api/currencies)
    - [Organisations](https://developer.xero.com/documentation/api/organisation)
    - [Repeating Invoices](https://developer.xero.com/documentation/api/repeating-invoices)
    - [Tax Rates](https://developer.xero.com/documentation/api/tax-rates)
    - [Tracking Categories](https://developer.xero.com/documentation/api/tracking-categories)
    - [Linked Transactions](https://developer.xero.com/documentation/api/linked-transactions)
- Outputs the schema for each resource
- Incrementally pulls data based on the input state

## Limitations

- Only designed to work with
  Xero [Partner Applications](https://developer.xero.com/documentation/auth-and-limits/partner-applications), not
  Private Applications.

---

## Authentication

Xero uses OAuth 2.0
protocol. [Check here authentication workflow](https://developer.xero.com/documentation/guides/oauth2/auth-flow#1-send-a-user-to-authorize-your-app)

### Refreshing access tokens

Access tokens expire after 30 minutes. Your app can refresh an access token without user interaction by using a refresh
token. You get a refresh token by requesting the offline_access scope during the initial user
authorization. [See more](https://developer.xero.com/documentation/guides/oauth2/auth-flow#refreshing-access-tokens)

> Each time you **perform a token refresh**, you should **save the new refresh token returned to the response**.
> Your existing refresh token will last for a grace period of 30 minutes. So in the end of import process you need to request a new refresh token and store it in run-time or in DB.

### Frequently Asked Questions

[Check it out here...](https://developer.xero.a/faq/oauth2/)

## Rate limits

- Uncertified apps will be limited to 25 connections.
- API rate limits. Daily Limit: 5000 calls per
  day. ([Details](https://developer.xero.com/documentation/guides/oauth2/limits#api-rate-limits))
- Rate limit FAQ ([Check here](https://developer.xero.com/documentation/guides/oauth2/limits#rate-limit-faq))