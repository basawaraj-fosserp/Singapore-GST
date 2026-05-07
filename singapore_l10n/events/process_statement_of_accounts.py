import frappe
import json
from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	execute as get_ageing,
)
from erpnext import get_company_currency
from frappe.www.printview import get_print_style
from frappe.utils import getdate, money_in_words, today
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
			if len(res) == 3:
				continue
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
	psoa_doc = frappe.get_doc('Process Statement Of Accounts', name)
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
			if len(res) == 3:
				continue
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

			if not gl_res or len(gl_res) <= 3:
				continue

			# First row is Opening, last two are totals — extract opening balance
			opening_balance = 0.0
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
					"debit": opening_balance if opening_balance > 0 else 0,
					"credit": -opening_balance if opening_balance < 0 else 0,
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
			# Total row
			normalised.append({
				"is_summary": True,
				"label": "Total",
				"debit": total_debit,
				"credit": total_credit,
				"accum_balance": running_balance,
			})
			# Closing row (Opening + Total)
			closing_debit = (opening_balance if opening_balance > 0 else 0) + total_debit
			closing_credit = (-opening_balance if opening_balance < 0 else 0) + total_credit
			normalised.append({
				"is_summary": True,
				"label": "Closing (Opening + Total)",
				"debit": closing_debit,
				"credit": closing_credit,
				"accum_balance": closing_debit - closing_credit,
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

		if ageing:
			ageing[0]["ageing_based_on"] = psoa_doc.ageing_based_on
			ageing_row = ageing[0]
			outstanding = ageing_row.get("outstanding") or 0
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
