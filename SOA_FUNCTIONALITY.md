# Automated Monthly Statement of Account (SOA) Emails

## Overview

Every month, this app can automatically email a Statement of Account (SOA) PDF
to every customer who had ledger activity in the previous month — without
requiring anyone to manually create or maintain a `Process Statement Of
Accounts` (PSOA) document per customer.

## How it's triggered

`hooks.py` registers a monthly scheduler event:

```python
scheduler_events = {
	"monthly": [
		"singapore_l10n.events.process_statement_of_accounts.send_soa_emails"
	],
}
```

Frappe's scheduler runs `send_soa_emails()` once a month (1st of the month,
per Frappe's standard monthly scheduler convention).

## Enabling / disabling

Controlled by the single doctype **SOA Settings**:

| Field | Purpose |
|---|---|
| `enable_auto_soa_email` | Master switch. If unchecked, `send_soa_emails()` returns immediately and does nothing. |
| `email_subject` | Subject template. Supports `{month}` placeholder. Defaults to `Statement of Account — {month}`. |
| `email_message` | Body template. Supports `{customer_name}` and `{month}` placeholders. Falls back to a built-in default message if left blank. |

## What happens on each run (`send_soa_emails`)

Source: `singapore_l10n/events/process_statement_of_accounts.py`

1. **Gate check** — exits if `SOA Settings.enable_auto_soa_email` is off.
2. **Computes the previous full calendar month** as the statement period
   (e.g. run on 2026-08-01 → period is 2026-07-01 to 2026-07-31).
3. **Finds eligible customers** via `get_eligible_customer_companies()`:
   - Queries `GL Entry` directly for distinct `(customer, company)` pairs
     with at least one non-cancelled entry (`party_type = "Customer"`)
     posted within the previous month.
   - Joins to `Customer` and excludes disabled customers (`disabled = 0`).
   - This check is **independent of any existing PSOA document** — a
     customer doesn't need to be pre-configured on any PSOA record to
     receive a statement. Any customer with real GL activity last month is
     picked up automatically.
4. **For each eligible `(customer, company)` pair**, `create_soa_for_customer()`:
   - Creates a dedicated `Process Statement Of Accounts` document scoped to
     that single customer, with `report = "General Ledger"`, `from_date` /
     `to_date` set to the previous month, and a deterministic name:
     `SOA-{customer}-{company}-{YYYY-MM}`.
   - If a doc with that name already exists (e.g. the job was re-run for
     the same month), it's reused instead of duplicated.
   - The document is **kept permanently** as an audit record of what was
     generated and sent each month — it is not deleted after sending.
5. **Builds and sends the email**:
   - Statement data (transactions, ageing, address/contact info) is pulled
     via `get_statements_of_account_from_gl()`.
   - Recipient email is resolved via `get_customer_email()`, in priority
     order: primary Contact → any other Contact → Address email. Customers
     with no resolvable email are skipped.
   - A PDF is rendered via `build_soa_html()` + `get_pdf()`.
   - The email is sent via `frappe.sendmail()` with the PDF attached
     (`SOA_{customer}_{Month_Year}.pdf`), referencing the PSOA doc.
6. **Deduplication** — a `(customer, company)` pair is only ever emailed
   once per run, tracked via an in-memory `sent_customers` set. Since
   eligibility is now customer-driven (not PSOA-doc-driven), each customer
   gets exactly **one** statement per company per month, even if multiple
   PSOA documents happen to reference them.
   - A customer transacting under two different companies still receives
     two separate emails — one per company — since each represents a
     distinct legal entity's receivables, not a duplicate.
7. **Error isolation** — failures for one customer are caught and logged to
   `Error Log` (`SOA Email Failed: {customer}`) without aborting the run
   for other customers.

## Design notes / known gaps this replaced

An earlier version of `send_soa_emails()` looped over *existing* PSOA
documents and emailed whatever customers were listed on each one. That
approach had two gaps, both addressed by the current implementation:

- **Missed customers**: a customer with real transactions but not listed on
  any PSOA document was silently never emailed. Fixed by driving eligibility
  from GL Entry directly rather than from PSOA customer lists.
- **Duplicate emails**: a customer listed on more than one PSOA document
  would receive one email per document. Fixed by making the loop
  customer-centric with an explicit dedup set, and by generating one
  dedicated PSOA per customer per run instead of reusing arbitrary
  pre-existing docs.

## Manual / on-demand sending

For ad-hoc sending from a specific PSOA document's UI (not the scheduled
job), see `send_emails()` in the same module, which is wired in as an
override via:

```python
override_whitelisted_methods = {
	"erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts.send_emails": "singapore_l10n.events.process_statement_of_accounts.send_emails"
}
```

This uses the PSOA document's own configured date range (not auto-shifted
to the previous month) and its own recipient/CC configuration
(`get_recipients_and_cc`), rather than the GL-driven eligibility check above.

## Shared core: `run_soa_monthly_job()`

`send_soa_emails()` and the test-email feature below both delegate to a
single shared function, `run_soa_monthly_job(from_date, to_date, month_label,
test_email=None)`:

- Runs `get_eligible_customer_companies()` for the given date range and loops
  over each `(customer, company)` pair exactly as described above.
- When `test_email` is `None` (the real monthly run), it behaves exactly as
  documented above: persists one `SOA-*` PSOA doc per customer via
  `create_soa_for_customer()`, and resolves each recipient via
  `get_customer_email()`.
- When `test_email` is set, every resolved recipient is replaced by
  `test_email`, and the PSOA document for each customer is built **entirely
  in memory** via `build_temp_soa_for_customer()` — it is never inserted
  into the database. `get_statements_of_account_from_gl()` accepts either a
  document name (DB lookup) or an already-built `Document` object directly,
  so the test path never touches the PSOA naming series or triggers
  insert/delete DocType hooks.
- Returns the total number of emails actually sent.

## Send Test Email (SOA Settings)

For testing the monthly logic without waiting for the 1st of the month and
without emailing real customers, **SOA Settings** has a **Send Test Email**
button (`singapore_l10n/singapore_l10n/doctype/soa_settings/soa_settings.js`).

1. Click **Send Test Email**.
2. Enter a **Send To Email**, **From Date**, and **To Date**.
3. Click **Send**.

This calls the whitelisted `send_test_soa_email(email, from_date, to_date)`
(System Manager only), which **enqueues a background job**
(`run_test_soa_email_job`, `long` queue, 1 hour timeout) and returns
immediately — the dialog closes right away with a "queued" toast, so there
is no request timeout even when many customers are eligible in the chosen
range.

The background job runs `run_soa_monthly_job(from_date, to_date, month_label,
test_email=email)` and, on completion, notifies the browser via
`frappe.publish_realtime("soa_test_email_done", ...)` scoped to the
requesting user. The SOA Settings client script listens for this event and
shows the final result (emails sent / nothing to send / failure).

Every customer with GL activity in the chosen date range gets a statement
generated and emailed — but **all of them** go to the one test address, not
to real customers. Because no PSOA documents are persisted for test sends,
running this repeatedly does not clutter the `Process Statement Of Accounts`
list or contend with the naming-series counter.

⚠️ An earlier version of this feature built each customer's PSOA by calling
`frappe.new_doc(...).insert()` then `frappe.delete_doc(...)` per customer.
With many eligible customers this caused heavy lock contention on the PSOA
naming series (`Lock wait timeout exceeded`) and queued up large numbers of
`delete_dynamic_links` background jobs, silently failing every send inside
the per-customer `try/except`. The in-memory approach above replaced this
and should be preferred for anything that needs to build a PSOA report
without keeping a persistent record.

## Testing

Not covered by an automated test yet. To verify manually:

```python
# bench console, on a test site with GL entries dated in the previous month
import frappe
frappe.get_single("SOA Settings").enable_auto_soa_email  # confirm it's set
from singapore_l10n.events.process_statement_of_accounts import send_soa_emails
send_soa_emails()
```

Check `Process Statement Of Accounts` list for newly created `SOA-*` docs
and the `Email Queue` / `Error Log` for send results.

To test without affecting real customers or waiting for month-end, use the
**Send Test Email** button in SOA Settings (see above) instead — it exercises
the exact same `run_soa_monthly_job()` logic but redirects all recipients to
one address and never persists PSOA documents.
