# Statement of Account (SOA) — Feature Documentation

## Overview

The SOA feature allows KG Sowers Group Pte Ltd to generate and distribute Statement of Account PDFs to customers. It supports two workflows:

1. **Manual Download** — triggered on demand from the Customer or Process Statement Of Accounts form
2. **Automated Monthly Email** — runs on the 1st of every month, sends the previous month's SOA as a PDF attachment to each customer's email address

---

## 1. Manual Download

### 1.1 From Customer Doctype

**Location:** Open any Customer record → click **Download SOA** button

**Behaviour:**
- A date range dialog appears with:
  - **From Date** — defaults to the 1st of the current month
  - **To Date** — defaults to today
- User selects the desired range and clicks **Download**
- System fetches GL transactions for that customer, generates an HTML report, and renders it as a PDF in the browser

**Code:** `singapore_l10n/public/js/customer.js` → `singapore_l10n/events/customer.py`

---

### 1.2 From Process Statement Of Accounts Doctype

**Location:** Open any Process Statement Of Accounts record → click **Download SOA** button

**Behaviour:**
- No dialog is shown — uses the `from_date` and `to_date` already saved on the document
- Generates and renders the PDF immediately

**Code:** `singapore_l10n/public/js/process_statement_of_accounts.js` → `singapore_l10n/events/process_statement_of_accounts.py`

---

## 2. PDF Layout

Both manual and automated PDFs share the same design:

| Section | Contents |
|---|---|
| **Header** | KG Sowers Group Pte Ltd logo, company address, UEN/GST No, "Statement of Account" title |
| **Customer Block** | Customer name, billing address, currency, payment terms, total due, statement number, date |
| **Transaction Table** | No., Doc No, Date, Due Date, Debit, Credit, Balance |
| **Summary Rows** | Opening, Total, Closing (bold, grey background) |
| **Footer** | In Words, Total Due, Ageing summary (Current Due, 1–30, 31–60, 61–90, 120+ days, Amount Due) |
| **Disclaimer** | "THIS IS A COMPUTER GENERATED DOCUMENT. NO SIGNATURE IS REQUIRED." |

Pagination: a page break with repeated header is inserted every 27 transaction rows.

---

## 3. Automated Monthly Email

### 3.1 How It Works

On the **1st of every month**, the Frappe scheduler fires `send_soa_emails()`. It:

1. Checks **SOA Settings** — if `Enable Auto SOA Email` is off, stops immediately
2. Calculates the previous full month date range (e.g. on 1 June → 1 May – 31 May)
3. Loops through every Process Statement Of Accounts document
4. For each document:
   - Fetches GL data for the previous month
   - **Skips** if no actual transactions exist (only Opening/Total/Closing rows)
   - Looks up the customer's email address
   - **Skips** silently if no email is found
   - Generates the SOA HTML and converts it to a PDF
   - Sends the email with the PDF as an attachment

### 3.2 Email Address Lookup Priority

For each customer the system checks in this order:

| Priority | Source | Condition |
|---|---|---|
| 1 | Contact doctype | Primary contact (`is_primary_contact = 1`) email |
| 2 | Contact doctype | Any other contact email linked to the customer |
| 3 | Address doctype | `email_id` on any address linked to the customer |

If no email is found at any level, the customer is silently skipped — no error is logged.

### 3.3 Skip Conditions

A customer's SOA email is **not sent** if:
- No transactions exist in the previous month (blank PDF)
- No email address found in Contact or Address records
- `Enable Auto SOA Email` is disabled in SOA Settings

### 3.4 Error Handling

If PDF generation or sending fails for any individual customer, the error is logged to **Frappe Error Log** with the title `SOA Email Failed: <document name>`. Processing continues for remaining customers.

---

## 4. SOA Settings

**Location:** Singapore L10N module → **SOA Settings**

This is a Single DocType (one global configuration record).

| Field | Type | Description |
|---|---|---|
| Enable Auto SOA Email | Check | Master switch — must be enabled for automated emails to send |
| Email Subject | Data | Subject line. Use `{month}` as a placeholder (e.g. `Statement of Account — {month}`) |
| Email Message | Text Editor | Rich-text email body. Available placeholders: `{customer_name}`, `{month}` |

**Default subject:** `Statement of Account — {month}`

**Default message** (used when Email Message is blank):
```
Dear {customer_name},

Thank you for your continued business and valued partnership with us.
Please find attached your Statement of Account for {month}.
Should you have any queries, please do not hesitate to reach out to us.
We truly appreciate your trust and look forward to serving you.

Warm regards,
KG Sowers Group Pte Ltd
```

---

## 5. Key Files

| File | Purpose |
|---|---|
| `singapore_l10n/events/process_statement_of_accounts.py` | Core data fetching, HTML building, email sending, email lookup |
| `singapore_l10n/events/customer.py` | Creates/updates PSOA doc from Customer form, delegates to above |
| `singapore_l10n/public/js/customer.js` | Date range dialog + client-side PDF rendering for Customer form |
| `singapore_l10n/public/js/process_statement_of_accounts.js` | Download SOA button + client-side PDF rendering for PSOA form |
| `singapore_l10n/singapore_l10n/doctype/soa_settings/` | SOA Settings Single DocType (JSON + Python) |
| `singapore_l10n/hooks.py` | Registers the monthly scheduler event |

---

## 6. Key Functions

### `get_statements_of_account(name, from_date, to_date)`
**File:** `events/process_statement_of_accounts.py`

Fetches all GL transactions, customer address, contact, and ageing data for a given PSOA document and date range. Returns a structured dictionary consumed by both the client-side JS renderer and the server-side `build_soa_html()`.

---

### `get_customer_email(customer)`
**File:** `events/process_statement_of_accounts.py`

Resolves the best available email for a customer using the priority described in section 3.2. Returns `None` if no email is found.

---

### `build_soa_html(doc_name, data)`
**File:** `events/process_statement_of_accounts.py`

Builds the full SOA HTML string server-side (mirrors the JS `set_html` logic). Used by `send_soa_emails()` to generate the PDF attachment. Uses `frappe.utils.fmt_money()` for currency formatting.

---

### `send_soa_emails()`
**File:** `events/process_statement_of_accounts.py`

Scheduled function registered in `hooks.py`. Entry point for the automated monthly email process. Checks SOA Settings, calculates date range, iterates all PSOA documents, and sends emails with PDF attachments via `frappe.sendmail()`.

---

## 7. Scheduler Registration

In `hooks.py`:

```python
scheduler_events = {
    "monthly": [
        "singapore_l10n.events.process_statement_of_accounts.send_soa_emails"
    ],
}
```

Frappe fires `monthly` events on the **1st of each month**.

---

## 8. Manual Testing

To trigger the automated email function manually (without waiting for the 1st of the month):

```bash
bench --site site1.local execute singapore_l10n.events.process_statement_of_accounts.send_soa_emails
```

To verify emails were queued:
- Go to **Setup → Email Queue** in the Frappe desk
- Each sent email will appear with the PDF attachment and reference to the PSOA document

To check for errors:
- Go to **Setup → Error Log**
- Filter by title `SOA Email Failed`

To verify the scheduler is active:
```bash
bench --site site1.local scheduler status
```
