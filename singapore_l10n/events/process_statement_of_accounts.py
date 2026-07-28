import frappe
import json
from frappe.model.document import Document
from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	execute as get_ageing,
)
from erpnext import get_company_currency
from frappe.www.printview import get_print_style
from frappe.utils import getdate, money_in_words, today, fmt_money, add_months, get_last_day
from erpnext.accounts.party import get_party_account_currency
from erpnext.accounts.report.general_ledger.general_ledger import execute as get_soa
from erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts import set_ageing, get_common_filters, get_ar_filters, get_gl_filters
from erpnext.accounts.report.accounts_receivable.accounts_receivable import execute as get_ar_soa
from frappe.utils.pdf import get_pdf


@frappe.whitelist()
def get_statements_of_account(document_name):
	doc = frappe.get_doc("Process Statement Of Accounts", document_name)
	report = get_report_pdf(doc)
	if report:
		frappe.local.response.filename = doc.name + ".pdf"
		frappe.local.response.filecontent = report
		frappe.local.response.type = "download"

def get_report_pdf(doc, consolidated=True):
	statement_dict = get_statement_dict(doc)
	if not bool(statement_dict):
		return False
	elif consolidated:
		delimiter = '<div style="page-break-before: always;"></div>' if doc.include_break else ""
		result = delimiter.join(list(statement_dict.values()))
		return get_pdf(result, {"orientation": doc.orientation})
	else:
		for customer, statement_html in statement_dict.items():
			statement_dict[customer] = get_pdf(statement_html, {"orientation": doc.orientation})
		return statement_dict

def get_statement_dict(doc, get_statement_dict=False):
	statement_dict = {}
	ageing = ""

	for entry in doc.customers:
		if doc.include_ageing:
			ageing = set_ageing(doc, entry)

		tax_id = frappe.get_doc("Customer", entry.customer).tax_id
		presentation_currency = (
			get_party_account_currency("Customer", entry.customer, doc.company)
			or doc.currency
			or get_company_currency(doc.company)
		)

		filters = get_common_filters(doc)
		if doc.ignore_exchange_rate_revaluation_journals:
			filters.update({"ignore_err": True})

		# if doc.ignore_cr_dr_notes:
		filters.update({"ignore_cr_dr_notes": True})
		if doc.report == "General Ledger":
			filters.update(get_gl_filters(doc, entry, tax_id, presentation_currency))
			filters.update({"show_opening_entries": 1})
			col, res = get_soa(filters)
			for x in [0, -2, -1]:
				if res[x].get("account"):
					res[x]["account"] = res[x]["account"].replace("'", "")
		else:
			filters.update(get_ar_filters(doc, entry))
			ar_res = get_ar_soa(filters)
			col, res = ar_res[0], ar_res[1]
			outstading_list = []
			if not res:
				continue
			else:
				for row in res:
					outstading_list.append(row.get("outstanding") or 0)
					row.update({"outstanding": sum(outstading_list)})

		statement_dict[entry.customer] = (
			[res, ageing] if get_statement_dict else get_html(doc, filters, entry, col, res, ageing)
		)

	return statement_dict

def get_html(doc, filters, entry, col, res, ageing):
	base_template_path = "frappe/www/printview.html"
	template_path = "singapore_l10n/events/process_statement_of_accounts_accounts_receivable.html"
	if doc.report == "General Ledger":
		template_path = (
			"erpnext/accounts/doctype/process_statement_of_accounts/process_statement_of_accounts.html"
		)

	process_soa_html = frappe.get_hooks("process_soa_html")
	# fetching custom print format for Process Statement of Accounts
	if process_soa_html and process_soa_html.get(doc.report):
		template_path = process_soa_html[doc.report][-1]

	letter_head = None
	if doc.letter_head:
		from frappe.www.printview import get_letter_head

		letter_head = get_letter_head(doc, 0)
	html = frappe.render_template(
		template_path,
		{
			"filters": filters,
			"data": res,
			"report": {"report_name": doc.report, "columns": col},
			"ageing": ageing[0] if (doc.include_ageing and ageing) else None,
			"letter_head": letter_head if doc.letter_head else None,
			"terms_and_conditions": frappe.db.get_value(
				"Terms and Conditions", doc.terms_and_conditions, "terms"
			)
			if doc.terms_and_conditions
			else None,
		},
	)
	html = frappe.render_template(
		base_template_path,
		{"body": html, "css": get_print_style(), "title": "Statement For " + entry.customer},
	)
	return html

@frappe.whitelist()
def get_statements_of_account_from_gl(name, is_from_customer = False):
	psoa_doc = name if isinstance(name, Document) else frappe.get_doc('Process Statement Of Accounts', name)
	out_data = {}
	out_list = []
	if not psoa_doc.from_date:
		psoa_doc.from_date = '2000-01-01'
	if not psoa_doc.to_date:
		psoa_doc.to_date = today()
	if psoa_doc.report == "General Ledger":
		all_statement_data = get_statement_dict(psoa_doc, get_statement_dict=True)
	else:
		all_statement_data = {}

	for cust in psoa_doc.customers:
		cust_dict = {}

		if psoa_doc.report == "General Ledger":
			if not all_statement_data.get(cust.customer):
				continue
			res = all_statement_data.get(cust.customer)[0]
			for row in res:
				if row.get('voucher_type') == 'Sales Invoice' and row.get('voucher_no'):
					due_date = frappe.db.get_value('Sales Invoice', row['voucher_no'], 'due_date')
					row['due_date'] = due_date or ''
				else:
					row.setdefault('due_date', '')
			cust_dict['data'] = res
		else:
			# Use GL to get all transactions (invoices + payments) within the date range
			gl_filters = frappe._dict({
				"company": psoa_doc.company,
				"from_date": psoa_doc.from_date,
				"to_date": psoa_doc.to_date,
				"party_type": "Customer",
				"party": [cust.customer],
				"show_opening_entries": 1,
				"include_default_book_entries": 0,
				"group_by": "Group by Voucher (Consolidated)",
			})
			gl_col, gl_res = get_soa(gl_filters)

			if not gl_res:
				continue

			# First row is Opening, last two are totals — extract opening balance
			opening_balance = 0.0
			ob_debit = 0.0
			ob_credit = 0.0
			if gl_res and gl_res[0].get("account"):
				ob_debit = gl_res[0].get("debit") or 0
				ob_credit = gl_res[0].get("credit") or 0
				opening_balance = ob_debit - ob_credit

			# Build normalised rows from GL entries
			running_balance = opening_balance
			normalised = []
			if opening_balance != 0:
				normalised.append({
					"is_opening": True,
					"label": "Opening Balance",
					"debit": ob_debit,
					"credit": ob_credit,
					"accum_balance": opening_balance,
				})
			total_debit = 0.0
			total_credit = 0.0
			for row in gl_res:
				if not row.get("voucher_no"):
					continue
				debit = row.get("debit") or 0
				credit = row.get("credit") or 0
				total_debit += debit
				total_credit += credit
				running_balance += debit - credit
				due_date = ""
				if row.get("voucher_type") == "Sales Invoice":
					due_date = frappe.db.get_value("Sales Invoice", row["voucher_no"], "due_date") or ""
				normalised.append({
					"voucher_no": row.get("voucher_no"),
					"voucher_type": row.get("voucher_type"),
					"posting_date": row.get("posting_date"),
					"due_date": due_date,
					"debit": debit,
					"credit": credit,
					"accum_balance": running_balance,
				})
			# Total row — balance is net of period (total_debit - total_credit), same as GL
			normalised.append({
				"is_summary": True,
				"label": "Total",
				"debit": total_debit,
				"credit": total_credit,
				"accum_balance": total_debit - total_credit,
			})
			# Closing row (Opening + Total) — running_balance already equals opening + period net
			closing_debit = ob_debit + total_debit
			closing_credit = ob_credit + total_credit
			normalised.append({
				"is_summary": True,
				"label": "Closing (Opening + Total)",
				"debit": closing_debit,
				"credit": closing_credit,
				"accum_balance": running_balance,
			})
			cust_dict['data'] = normalised

		cad_query = f'''
			SELECT
				ad.name,
				ad.address_line1,
				ad.address_line2,
				ad.city,
				ad.email_id,
				ad.phone,
				ad.pincode,
				ad.country,
				cus.name as customer,
				cus.customer_name as customer_name,
				cus.payment_terms
			FROM
				tabAddress AS ad LEFT JOIN
				`tabDynamic Link` AS dl ON dl.parent=ad.name LEFT JOIN
				tabCustomer AS cus ON dl.link_name=cus.name
			WHERE
				dl.link_doctype="Customer" AND dl.link_name={json.dumps(cust.get("customer"))}'''
		cad_data = frappe.db.sql(f"{cad_query}", as_dict=True)
		if cad_data and cad_data[0]:
			cust_dict['cad_data'] = cad_data[0]
		cco_query = f'''
			SELECT
				co.first_name,
				co.middle_name,
				co.last_name
			FROM
				tabContact AS co LEFT JOIN
				`tabDynamic Link` AS dl ON dl.parent=co.name
			WHERE
				dl.link_doctype="Customer" AND dl.link_name={json.dumps(cust.get("customer"))}
				AND co.is_primary_contact=1'''
		cco_data = frappe.db.sql(f"{cco_query}", as_dict=True)
		if cco_data and cco_data[0]:
			cust_dict['cco_data'] = cco_data[0]
		ageing_filters = frappe._dict(
			{
				"company": psoa_doc.company,
				"report_date": psoa_doc.to_date,
				"ageing_based_on": psoa_doc.ageing_based_on,
				"range1": 30,
				"range2": 60,
				"range3": 90,
				"range4": 120,
				"party": [cust.customer],
				"party_type": "Customer",
			}
		)
		col1, ageing = get_ageing(ageing_filters)

		ageing_row = ageing[0] if ageing else frappe._dict()
		ageing_row["ageing_based_on"] = psoa_doc.ageing_based_on
		outstanding = ageing_row.get("outstanding") or 0
		ageing_row["outstanding"] = outstanding
		ageing_row["outstanding_in_words"] = money_in_words(abs(outstanding))
		ageing_row["current_due"] = (
			outstanding
			- (ageing_row.get("range1") or 0)
			- (ageing_row.get("range2") or 0)
			- (ageing_row.get("range3") or 0)
			- (ageing_row.get("range4") or 0)
		)
		cust_dict['ageing'] = ageing_row
		out_list.append(cust_dict)

	out_data['cust'] = out_list
	out_data['report'] = psoa_doc.report
	out_data.update({'currency': psoa_doc.currency})
	out_data.update({'to_date': frappe.utils.formatdate(psoa_doc.to_date, "dd MMM YYYY")})
	out_data.update({'posting_date': frappe.utils.formatdate(getdate(), "dd MMM YYYY")})
	cod_query = f'''
		SELECT
			ad.name,
			ad.address_line1,
			ad.address_line2,
			ad.city,
			ad.email_id,
			ad.phone,
			ad.pincode,
			ad.fax,
			ad.country
		FROM
			tabAddress AS ad LEFT JOIN
			`tabDynamic Link` AS dl ON dl.parent=ad.name
		WHERE
			dl.link_doctype="Company" AND dl.link_name={json.dumps(psoa_doc.get("company"))}'''
	cod_data = frappe.db.sql(f"{cod_query}", as_dict=True)
	if cod_data and cod_data[0]:
		out_data['cod_data'] = cod_data[0]
	out_data['tax_id'] = frappe.db.get_value("Company", psoa_doc.company, "tax_id")

	return out_data


def get_customer_email(customer):
	"""Return the best available email for a customer (Contact primary → Contact any → Address)."""
	# 1. Primary contact email
	primary = frappe.db.sql("""
		SELECT co.email_id
		FROM tabContact AS co
		INNER JOIN `tabDynamic Link` AS dl ON dl.parent = co.name
		WHERE dl.link_doctype = 'Customer'
		  AND dl.link_name = %s
		  AND co.is_primary_contact = 1
		  AND co.email_id IS NOT NULL
		  AND co.email_id != ''
		LIMIT 1
	""", customer, as_dict=True)
	if primary:
		return primary[0].email_id

	# 2. Any other contact email
	any_contact = frappe.db.sql("""
		SELECT co.email_id
		FROM tabContact AS co
		INNER JOIN `tabDynamic Link` AS dl ON dl.parent = co.name
		WHERE dl.link_doctype = 'Customer'
		  AND dl.link_name = %s
		  AND co.email_id IS NOT NULL
		  AND co.email_id != ''
		LIMIT 1
	""", customer, as_dict=True)
	if any_contact:
		return any_contact[0].email_id

	# 3. Address email
	addr = frappe.db.sql("""
		SELECT ad.email_id
		FROM tabAddress AS ad
		INNER JOIN `tabDynamic Link` AS dl ON dl.parent = ad.name
		WHERE dl.link_doctype = 'Customer'
		  AND dl.link_name = %s
		  AND ad.email_id IS NOT NULL
		  AND ad.email_id != ''
		LIMIT 1
	""", customer, as_dict=True)
	if addr:
		return addr[0].email_id

	return None


@frappe.whitelist()
def get_customer_contact_emails(customer):
	"""Return every distinct Contact email linked to a customer, primary
	contact first, as a comma-separated string (used to auto-fill the SOA
	Customer table's Email field when a customer is selected)."""
	rows = frappe.db.sql("""
		SELECT co.email_id
		FROM tabContact AS co
		INNER JOIN `tabDynamic Link` AS dl ON dl.parent = co.name
		WHERE dl.link_doctype = 'Customer'
		  AND dl.link_name = %s
		  AND co.email_id IS NOT NULL
		  AND co.email_id != ''
		ORDER BY co.is_primary_contact DESC
	""", customer, as_dict=True)

	seen = set()
	emails = []
	for row in rows:
		email = row.email_id.strip()
		if email and email.lower() not in seen:
			seen.add(email.lower())
			emails.append(email)

	return ", ".join(emails)


def split_emails(email_string):
	"""Split a comma-separated email string into a list of trimmed addresses."""
	if not email_string:
		return []
	return [addr.strip() for addr in email_string.split(",") if addr.strip()]


def get_customer_email_list(customer):
	"""Return get_customer_email() as a single-item list, or [] if none found."""
	email = get_customer_email(customer)
	return [email] if email else []


def _fmt(value, currency="SGD"):
	if value is None:
		return "-"
	return fmt_money(value, currency=currency)


def build_soa_html(doc_name, data):
	"""Build the full SOA HTML string server-side (mirrors the JS set_html logic)."""
	currency = data.get("currency", "SGD")
	posting_date = data.get("posting_date", "")
	is_gl = data.get("report") == "General Ledger"

	style = """
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;700&display=swap">
<style>
.page-break { display: block; page-break-before: always; }
.lhead { font-size:9px; margin-top:0px; margin-bottom:0px !important; vertical-align: top !important; }
* { font-family: 'IBM Plex Sans', sans-serif !important; }
.print-format { margin-left: 4mm; margin-right: 4mm; }
.new1 { border-top: 1px dotted !important; }
.blhead { font-weight:600 !important; font-size:9px !important; }
.print-format .letter-head { margin-bottom: 0px; }
.print-format .letterhead td, .print-format th { padding: 1 1px 1 1px !important; vertical-align: top !important; margin:0px !important; }
.print-format p { margin:0px 0px 2px; }
p { font-size: 13px; }
.address-sec { margin-top:0px; margin-bottom:0px !important; vertical-align: text-top; }
.left_dotted { border-left: 2px dotted !important; }
.ontop { border-top: 1px; }
.onbottom { border-bottom: 1px; }
</style>"""

	header = """
<div class="letter-head" style="padding-top:10px;">
<div class="letter-head">
<table width="100%" class="letter-head"><tbody>
<tr>
  <td width="10%"><img height="60" src="/files/KGS-Logo.png" width="60"></td>
  <td width="21%">
    <p style="margin-bottom:0px !important; margin-top:0px;"><b style="font-size:11px;">KGS Pte Ltd</b></p>
    <p class="lhead">8 Tuas South Lane,</p>
    <p class="lhead">#01-71, Factory 4,</p>
    <p class="lhead">Singapore 637302</p>
  </td>
  <td width="32%">
    <br>
    <p class="lhead"><b class="blhead">Web:</b>kgs.com.sg</p>
    <p class="lhead"><b class="blhead">UEN/GST No:</b> 201607799N</p>
  </td>
  <td align="centre"><b style="font-size: 20px; text-transform: uppercase;">Statement of Account</b></td>
</tr>
</tbody></table>
</div></div><hr><div>"""

	if is_gl:
		table_header = """
<table class="table table-bordered" style="font-size: 13px; border-spacing: 1px; table-layout: auto; width: 100%;">
<thead><tr>
  <td style="width: 4%;"><b>No.</b></td>
  <td style="width: 24%;"><b>Doc No</b></td>
  <td style="width: 11%; white-space: nowrap;"><b>Date</b></td>
  <td style="width: 11%; white-space: nowrap;"><b>Due Date</b></td>
  <td style="white-space: nowrap;" align="right"><b>Debit</b></td>
  <td style="white-space: nowrap;" align="right"><b>Credit</b></td>
  <td style="white-space: nowrap;" align="right"><b>Balance</b></td>
</tr></thead>
<tbody>"""
	else:
		table_header = """
<table class="table table-bordered" style="font-size: 13px; border-spacing: 1px; table-layout: auto; width: 100%;">
<thead><tr>
  <td style="width: 4%;"><b>No.</b></td>
  <td style="width: 24%;"><b>Doc No</b></td>
  <td style="width: 11%; white-space: nowrap;"><b>Date</b></td>
  <td style="width: 11%; white-space: nowrap;"><b>Due Date</b></td>
  <td style="white-space: nowrap;" align="right"><b>Debit</b></td>
  <td style="white-space: nowrap;" align="right"><b>Credit</b></td>
  <td style="white-space: nowrap;" align="right"><b>Balance</b></td>
</tr></thead>
<tbody>"""

	html = style + header

	for cu in (data.get("cust") or []):
		cad = cu.get("cad_data") or {}
		ageing = cu.get("ageing") or {}
		outstanding = ageing.get("outstanding") or 0

		html += f"""
<table width="100%" class="cust_head"><tbody><tr>
  <td>
    <p class="address-sec">{cad.get('customer_name','')}</p>
    <p class="address-sec">{cad.get('address_line1','')}</p>
    <p class="address-sec">{cad.get('address_line2','')}</p>
    <p class="address-sec">{cad.get('city','')} {cad.get('pincode','')}</p>
    <p class="address-sec">{cad.get('country','')}</p>
  </td>
  <td>
    <p class="address-sec">Currency : {currency}</p>
    <p class="address-sec">Payment Terms : C.O.D</p>
    <p class="address-sec">Total Due : {_fmt(outstanding, currency)}</p>
  </td>
  <td class="left_dotted" style="width: 25%; max-width: 25%;">
    <p class="address-sec" style="padding-left:10px; word-break: break-word; white-space: normal;">Statement No.: {doc_name}</p>
    <p class="address-sec" style="padding-left:10px;">Date.: {posting_date}</p>
  </td>
</tr></tbody></table>
<hr class="new1">"""

		html += table_header
		idx = 1
		for val in (cu.get("data") or []):
			if is_gl:
				# GL rows: summary rows have no voucher_no but have account label
				is_summary = not val.get("voucher_no") and val.get("account")
				if is_summary:
					html += f"""<tr style="font-weight:bold; background:#f5f5f5;">
  <td></td>
  <td><b>{val.get('account','')}</b></td>
  <td></td>
  <td></td>
  <td style="white-space: nowrap;" align="right">{_fmt(val.get('debit'), currency) if val.get('debit') else '-'}</td>
  <td style="white-space: nowrap;" align="right">{_fmt(val.get('credit'), currency) if val.get('credit') else '-'}</td>
  <td style="white-space: nowrap;" align="right">{_fmt(val.get('balance'), currency) if val.get('balance') is not None else '-'}</td>
</tr>"""
				elif val.get("voucher_no"):
					html += f"""<tr>
  <td style="width: 4%;">{idx}</td>
  <td style="width: 24%;">{val.get('voucher_no','')}</td>
  <td style="width: 11%; white-space: nowrap;">{val.get('posting_date','')}</td>
  <td style="width: 11%; white-space: nowrap;">{val.get('due_date','')}</td>
  <td style="white-space: nowrap;" align="right">{_fmt(val.get('debit'), currency) if val.get('debit') else '-'}</td>
  <td style="white-space: nowrap;" align="right">{_fmt(val.get('credit'), currency) if val.get('credit') else '-'}</td>
  <td style="white-space: nowrap;" align="right">{_fmt(val.get('balance'), currency) if val.get('balance') is not None else '-'}</td>
</tr>"""
					if idx % 27 == 0:
						html += "</tbody></table><div class='page-break'></div>"
						html += header + table_header
					idx += 1
			else:
				# AR rows use is_opening, is_summary flags and accum_balance
				if val.get("is_opening"):
					html += f"""<tr style="font-weight:bold; background:#f5f5f5;">
  <td></td>
  <td><b>Opening Balance</b></td>
  <td></td>
  <td></td>
  <td style="white-space: nowrap;" align="right">{_fmt(val.get('debit'), currency) if val.get('debit') else '-'}</td>
  <td style="white-space: nowrap;" align="right">{_fmt(val.get('credit'), currency) if val.get('credit') else '-'}</td>
  <td style="white-space: nowrap;" align="right">{_fmt(val.get('accum_balance'), currency)}</td>
</tr>"""
				elif val.get("is_summary"):
					html += f"""<tr style="font-weight:bold; background:#f5f5f5;">
  <td></td>
  <td><b>{val.get('label','')}</b></td>
  <td></td>
  <td></td>
  <td style="white-space: nowrap;" align="right">{_fmt(val.get('debit'), currency) if val.get('debit') else '-'}</td>
  <td style="white-space: nowrap;" align="right">{_fmt(val.get('credit'), currency) if val.get('credit') else '-'}</td>
  <td style="white-space: nowrap;" align="right">{_fmt(val.get('accum_balance'), currency)}</td>
</tr>"""
				elif val.get("voucher_no"):
					html += f"""<tr>
  <td style="width: 5%">{idx}</td>
  <td style="width: 20%">{val.get('voucher_no','')}</td>
  <td style="width: 12%">{val.get('posting_date','')}</td>
  <td style="width: 12%">{val.get('due_date','')}</td>
  <td style="width: 10%" align="right">{_fmt(val.get('debit'), currency) if val.get('debit') else '-'}</td>
  <td style="width: 10%" align="right">{_fmt(val.get('credit'), currency) if val.get('credit') else '-'}</td>
  <td style="width: 14%" align="right">{_fmt(val.get('accum_balance'), currency) if val.get('accum_balance') is not None else '-'}</td>
</tr>"""
					if idx % 27 == 0:
						html += "</tbody></table><div class='page-break'></div>"
						html += header + table_header
					idx += 1

		outstanding_in_words = ageing.get("outstanding_in_words", "")
		html += f"""</tbody></table>
<div id="footer-html" class="visible-pdf letter-head-footer">
<table width="100%" class="table"><tbody><tr>
  <td width="14%" class="ontop onbottom"><p><b>In Words:</b></p></td>
  <td width="58%" class="ontop onbottom"><p>{outstanding_in_words}</p></td>
  <td width="12%" class="ontop onbottom"><p><b>Total Due</b>:</p></td>
  <td width="16%" class="ontop onbottom"><p>{_fmt(outstanding, currency)}</p></td>
</tr></tbody></table>
<table class="table table-bordered" style="font-size: 13px; border-spacing: 0px;">
<thead><tr>
  <td style="width: 16%" align="center"><b>Current Due</b></td>
  <td style="width: 16%" align="center"><b>1-30 Days</b></td>
  <td style="width: 16%" align="center"><b>31-60 Days</b></td>
  <td style="width: 16%" align="center"><b>61-90 Days</b></td>
  <td style="width: 16%" align="center"><b>120+ Days</b></td>
  <td style="width: 16%" align="center"><b>Amount Due</b></td>
</tr></thead>
<tbody><tr>
  <td align="center">{_fmt(ageing.get('current_due'), currency)}</td>
  <td align="center">{_fmt(ageing.get('range1'), currency)}</td>
  <td align="center">{_fmt(ageing.get('range2'), currency)}</td>
  <td align="center">{_fmt(ageing.get('range3'), currency)}</td>
  <td align="center">{_fmt(ageing.get('range4'), currency)}</td>
  <td align="center">{_fmt(outstanding, currency)}</td>
</tr></tbody></table>
<center style="font-size: 8px;">THIS IS A COMPUTER GENERATED DOCUMENT. NO SIGNATURE IS REQUIRED.</center>
</div>"""

	html += "</div>"
	return html


def build_email_body(customer_name, cad_data, ageing, doc, currency):
	outstanding = ageing.get("outstanding") or 0
	from_date = frappe.utils.formatdate(doc.from_date, "dd MMM YYYY") if doc.from_date else ""
	to_date = frappe.utils.formatdate(doc.to_date, "dd MMM YYYY") if doc.to_date else ""
	today_date = frappe.utils.formatdate(frappe.utils.today(), "dd MMM YYYY")

	range1 = ageing.get("range1") or 0
	range2 = ageing.get("range2") or 0
	range3 = ageing.get("range3") or 0
	range4 = ageing.get("range4") or 0
	current_due = ageing.get("current_due") or 0

	def row(label, value, highlight=False):
		bg = "#fff3cd" if highlight else "#f9f9f9"
		return f"""
		<tr>
			<td style="padding:8px 12px; border:1px solid #dee2e6; width:55%; background:{bg};">{label}</td>
			<td style="padding:8px 12px; border:1px solid #dee2e6; width:45%; text-align:right; background:{bg};"><b>{value}</b></td>
		</tr>"""

	return f"""
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; max-width: 680px; margin: 0 auto;">

  <!-- Header -->
  <div style="background-color: #1a3c5e; padding: 20px 24px; border-radius: 6px 6px 0 0;">
    <img src="https://erp.kgs.com.sg/files/KGS-Logo.png" height="45" style="vertical-align:middle; margin-right:12px;">
    <span style="color:#ffffff; font-size:18px; font-weight:bold; vertical-align:middle;">KGS Pte Ltd</span>
  </div>

  <!-- Greeting -->
  <div style="padding: 24px; background:#ffffff; border-left:1px solid #dee2e6; border-right:1px solid #dee2e6;">
    <p style="margin:0 0 12px;">Dear <b>{customer_name}</b>,</p>
    <p style="margin:0 0 20px; line-height:1.6;">
      Thank you for your continued business. Please find attached your
      <b>Statement of Accounts</b> for the period <b>{from_date}</b> to <b>{to_date}</b>.
      Kindly review and arrange payment for any outstanding amounts at your earliest convenience.
    </p>

    <!-- Summary Table -->
    <table style="width:100%; border-collapse:collapse; margin-bottom:20px;">
      <thead>
        <tr style="background-color:#1a3c5e; color:#ffffff;">
          <th style="padding:10px 12px; text-align:left; border:1px solid #dee2e6;" colspan="2">Account Summary</th>
        </tr>
      </thead>
      <tbody>
        {row("Statement Period", f"{from_date} &nbsp;to&nbsp; {to_date}")}
        {row("Statement Date", today_date)}
        {row("Currency", currency)}
        {row("Total Outstanding Amount", _fmt(outstanding, currency), highlight=True)}
      </tbody>
    </table>

    <!-- Ageing Table -->
    <table style="width:100%; border-collapse:collapse; margin-bottom:24px;">
      <thead>
        <tr style="background-color:#1a3c5e; color:#ffffff;">
          <th style="padding:10px 12px; text-align:center; border:1px solid #dee2e6;">Current Due</th>
          <th style="padding:10px 12px; text-align:center; border:1px solid #dee2e6;">1–30 Days</th>
          <th style="padding:10px 12px; text-align:center; border:1px solid #dee2e6;">31–60 Days</th>
          <th style="padding:10px 12px; text-align:center; border:1px solid #dee2e6;">61–90 Days</th>
          <th style="padding:10px 12px; text-align:center; border:1px solid #dee2e6;">120+ Days</th>
        </tr>
      </thead>
      <tbody>
        <tr style="background:#f9f9f9; text-align:center;">
          <td style="padding:8px 12px; border:1px solid #dee2e6;">{_fmt(current_due, currency)}</td>
          <td style="padding:8px 12px; border:1px solid #dee2e6;">{_fmt(range1, currency)}</td>
          <td style="padding:8px 12px; border:1px solid #dee2e6;">{_fmt(range2, currency)}</td>
          <td style="padding:8px 12px; border:1px solid #dee2e6;">{_fmt(range3, currency)}</td>
          <td style="padding:8px 12px; border:1px solid #dee2e6;">{_fmt(range4, currency)}</td>
        </tr>
      </tbody>
    </table>

    <p style="margin:0 0 8px; line-height:1.6;">
      Should you have any queries regarding this statement, please do not hesitate to contact us.
    </p>
    <p style="margin:0 0 24px; line-height:1.6;">We appreciate your prompt attention to this matter.</p>

    <p style="margin:0;">Warm regards,</p>
    <p style="margin:4px 0 0;"><b>KGS Pte Ltd</b></p>
    <p style="margin:2px 0 0; color:#666; font-size:13px;">Web: kgs.com.sg &nbsp;|&nbsp; UEN/GST No: 201607799N</p>
  </div>

  <!-- Footer -->
  <div style="background:#f1f1f1; padding:12px 24px; border-radius:0 0 6px 6px; border:1px solid #dee2e6; border-top:none;">
    <p style="margin:0; font-size:11px; color:#888; text-align:center;">
      This is an automated email. Please do not reply directly to this message.
    </p>
  </div>

</div>"""


@frappe.whitelist()
def send_emails(document_name, from_scheduler=False, posting_date=None):
	from erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts import (
		get_context,
		get_recipients_and_cc,
	)

	doc = frappe.get_doc("Process Statement Of Accounts", document_name)
	data = get_statements_of_account_from_gl(document_name)
	if not data or not data.get("cust"):
		return False

	currency = data.get("currency", "SGD")
	sent = False
	for cu in data["cust"]:
		cad = cu.get("cad_data") or {}
		customer = cad.get("customer")
		customer_name = cad.get("customer_name") or customer
		if not customer:
			continue

		single_cust_data = dict(data)
		single_cust_data["cust"] = [cu]
		soa_html = build_soa_html(document_name, single_cust_data)
		report_pdf = get_pdf(soa_html, {"orientation": doc.orientation or "Portrait"})

		context = get_context(customer, doc)
		filename = frappe.render_template(doc.pdf_name, context)
		attachments = [{"fname": filename + ".pdf", "fcontent": report_pdf}]

		recipients, cc = get_recipients_and_cc(customer, doc)
		if not recipients:
			continue

		subject = frappe.render_template(doc.subject, context)
		ageing = cu.get("ageing") or {}
		message = build_email_body(customer_name, cad, ageing, doc, currency)

		sender_email = frappe.db.get_value("Email Account", doc.sender, "email_id") if doc.sender else frappe.session.user

		frappe.enqueue(
			queue="short",
			method=frappe.sendmail,
			recipients=recipients,
			sender=sender_email,
			cc=cc,
			subject=subject,
			message=message,
			now=True,
			reference_doctype="Process Statement Of Accounts",
			reference_name=document_name,
			attachments=attachments,
		)
		sent = True

	return sent


def get_eligible_customer_companies(from_date, to_date):
	"""Return [{"customer": ..., "company": ...}] for customers with at least one
	non-cancelled GL entry against their receivable account in the given date range."""
	return frappe.db.sql(
		"""
		SELECT DISTINCT gle.party AS customer, gle.company AS company
		FROM `tabGL Entry` gle
		INNER JOIN `tabCustomer` cus ON cus.name = gle.party
		WHERE gle.party_type = 'Customer'
		  AND gle.is_cancelled = 0
		  AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND cus.disabled = 0
		""",
		{"from_date": from_date, "to_date": to_date},
		as_dict=True,
	)


def create_soa_for_customer(customer, company, from_date, to_date, month_label):
	"""Create (and keep) a General Ledger Process Statement Of Accounts for one
	customer/company/month, as an audit record of what was generated and sent."""
	name = f"SOA-{customer}-{company}-{getdate(from_date).strftime('%Y-%m')}"

	if frappe.db.exists("Process Statement Of Accounts", name):
		return frappe.get_doc("Process Statement Of Accounts", name)

	psoa_doc = frappe.new_doc("Process Statement Of Accounts")
	psoa_doc.name = name
	psoa_doc.report = "General Ledger"
	psoa_doc.company = company
	psoa_doc.from_date = str(from_date)
	psoa_doc.to_date = str(to_date)
	psoa_doc.group_by = "Group by Voucher (Consolidated)"
	psoa_doc.include_ageing = 1
	psoa_doc.ageing_based_on = "Due Date"
	psoa_doc.orientation = "Portrait"
	psoa_doc.primary_mandatory = 0
	psoa_doc.append("customers", {"customer": customer})
	psoa_doc.insert(ignore_permissions=True)
	return psoa_doc


def run_soa_monthly_job(from_date, to_date, month_label):
	"""Core SOA-emailing loop for the given date range.

	For every customer with GL activity in the range that is also listed in
	SOA Settings' "SOA Customer" table, auto-creates a General Ledger SOA and
	emails the PDF to them. Returns the number of emails sent.
	"""
	settings = frappe.get_single("SOA Settings")

	email_subject = (settings.email_subject or "Statement of Account — {month}").replace("{month}", month_label)

	soa_customer_emails = {row.customer: row.email for row in settings.soa_customer if row.customer}
	if not soa_customer_emails:
		return 0

	eligible = get_eligible_customer_companies(from_date, to_date)
	eligible = [row for row in eligible if row["customer"] in soa_customer_emails]
	sent_customers = set()
	sent_count = 0

	for row in eligible:
		customer = row["customer"]
		company = row["company"]

		# A customer transacting under multiple companies gets one statement per
		# company; within the same company they are only ever emailed once.
		dedup_key = (customer, company)
		if dedup_key in sent_customers:
			continue

		try:
			psoa_doc = create_soa_for_customer(customer, company, from_date, to_date, month_label)
			doc_name = psoa_doc.name
			data = get_statements_of_account_from_gl(doc_name)

			currency = data.get("currency", "SGD")

			for cu in (data.get("cust") or []):
				cad = cu.get("cad_data") or {}
				cust_id = cad.get("customer") or customer
				customer_name = cad.get("customer_name") or cust_id

				recipients = split_emails(soa_customer_emails.get(cust_id)) or get_customer_email_list(cust_id)
				if not recipients:
					continue

				single_cust_data = dict(data)
				single_cust_data["cust"] = [cu]

				soa_html = build_soa_html(doc_name, single_cust_data)
				pdf_content = get_pdf(soa_html, {"orientation": "Portrait"})

				ageing = cu.get("ageing") or {}
				message = build_email_body(customer_name, cad, ageing, psoa_doc, currency)

				frappe.sendmail(
					recipients=recipients,
					subject=email_subject,
					message=message,
					attachments=[{
						"fname": f"SOA_{cust_id}_{month_label.replace(' ', '_')}.pdf",
						"fcontent": pdf_content,
					}],
					reference_doctype="Process Statement Of Accounts",
					reference_name=doc_name,
				)
				sent_customers.add(dedup_key)
				sent_count += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"SOA Email Failed: {customer}")

	return sent_count


def send_soa_emails():
	"""Scheduled monthly function: for every customer with GL activity in the
	previous month, auto-creates a General Ledger SOA and emails the PDF to them."""
	settings = frappe.get_single("SOA Settings")
	if not settings.enable_auto_soa_email:
		return

	# Previous full month date range
	today_date = getdate(today())
	first_of_this_month = today_date.replace(day=1)
	last_of_prev_month = get_last_day(add_months(first_of_this_month, -1))
	first_of_prev_month = last_of_prev_month.replace(day=1)
	month_label = first_of_prev_month.strftime("%B %Y")

	run_soa_monthly_job(first_of_prev_month, last_of_prev_month, month_label)
