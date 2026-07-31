# /home/erevive/frappe-bench/apps/singapore_l10n/singapore_l10n/events/process_statement_of_accounts.py
import frappe
import json
import base64
import os
from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	execute as get_ageing,
)
from frappe.utils import getdate, money_in_words, fmt_money
from erpnext import get_company_currency
from erpnext.accounts.party import get_party_account_currency
from erpnext.accounts.report.general_ledger.general_ledger import execute as get_soa

@frappe.whitelist()
def get_statements_of_account(name, from_date=None, to_date=None):
	if isinstance(name, frappe.model.document.Document):
		psoa_doc = name
	else:
		psoa_doc = frappe.get_doc('Process Statement Of Accounts', name)
	from_date = from_date or psoa_doc.get('from_date')
	to_date = to_date or psoa_doc.get('to_date')
	out_data = {}
	out_list = []
	for cust in psoa_doc.customers:
		cust_dict = {}
		presentation_currency = (
			get_party_account_currency("Customer", cust.customer, psoa_doc.company)
			or psoa_doc.currency
			or get_company_currency(psoa_doc.company)
		)
		tax_id = frappe.get_doc("Customer", cust.customer).tax_id
		filters = frappe._dict(
			{
				"from_date": from_date,
				"to_date": to_date,
				"company": psoa_doc.company,
				"finance_book": psoa_doc.finance_book if psoa_doc.finance_book else None,
				"account": [psoa_doc.account] if psoa_doc.account else None,
				"party_type": "Customer",
				"party": [cust.customer],
				"presentation_currency": presentation_currency,
				"group_by": psoa_doc.group_by,
				"currency": psoa_doc.currency,
				"cost_center": [cc.cost_center_name for cc in psoa_doc.get("cost_center") or []],
				"project": [p.project_name for p in psoa_doc.get("project") or []],
				"show_opening_entries": 0,
				"include_default_book_entries": 0,
				"tax_id": tax_id if tax_id else None,
			}
		)
		col, res = get_soa(filters)

		for x in [0, -2, -1]:
			res[x]["account"] = res[x]["account"].replace("'", "")

		if res:
			for re in res:
				if re.get('voucher_type') and re.get('voucher_type') == 'Sales Invoice':
					sales_invoice = frappe.db.get_value(re.get('voucher_type'), re.get('voucher_no'), ['due_date', 'po_no', 'total'], as_dict=1)
					if sales_invoice.get('due_date'):
						re['due_date'] = sales_invoice.get('due_date') if sales_invoice.get('due_date') else ''
					if sales_invoice.get('po_no'):
						re['po_no'] = sales_invoice.get('po_no') if sales_invoice.get('po_no') else ''
					if sales_invoice.get('total'):
						re['total'] = sales_invoice.get('total') if sales_invoice.get('total') else 0
			cust_dict['data'] = res

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
		if psoa_doc.include_ageing:
			ageing_filters = frappe._dict(
				{
					"company": psoa_doc.company,
					"report_date": to_date,
					"ageing_based_on": psoa_doc.ageing_based_on,
					"range1": 30,
					"range2": 60,
					"range3": 90,
					"range4": 120,
					"customer": cust.customer,
				}
			)
			col1, ageing = get_ageing(ageing_filters)
			if ageing:
				ageing[0]["ageing_based_on"] = psoa_doc.ageing_based_on
				cust_dict['ageing'] = ageing[0]
			out_list.append(cust_dict)
	out_data['cust'] = out_list
	out_data['currency'] = psoa_doc.currency
	out_data['to_date'] = frappe.utils.formatdate(to_date, "dd MMM YYYY")
	out_data['posting_date'] = frappe.utils.formatdate(getdate() , "dd MMM YYYY")
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

	logo_path = os.path.join(frappe.get_site_path(), "public", "files", "KGS-Logo.png")
	if os.path.exists(logo_path):
		with open(logo_path, "rb") as f:
			out_data['logo_base64'] = "data:image/png;base64," + base64.b64encode(f.read()).decode("utf-8")
	else:
		out_data['logo_base64'] = ""
	if len(out_data['cust']) and out_data['cust'][0].get("ageing"):
		out_data['cust'][0]['ageing']['outstanding_in_words'] = money_in_words(abs(out_data['cust'][0]['ageing']['outstanding']))
		out_data['cust'][0]['ageing']['current_due'] = (out_data['cust'][0]['ageing']['outstanding'] -
														out_data['cust'][0]['ageing']['range1'] -
														out_data['cust'][0]['ageing']['range2'] -
														out_data['cust'][0]['ageing']['range3'] -
														out_data['cust'][0]['ageing']['range4'] -
														out_data['cust'][0]['ageing']['range5']
														)
	return out_data


def get_customer_email(customer):
	# 1. Primary contact email
	result = frappe.db.sql("""
		SELECT ce.email_id
		FROM `tabContact Email` ce
		JOIN `tabContact` co ON co.name = ce.parent
		JOIN `tabDynamic Link` dl ON dl.parent = co.name
		WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
		  AND co.is_primary_contact = 1
		LIMIT 1
	""", customer)
	if result and result[0][0]:
		return result[0][0]

	# 2. Any contact email
	result = frappe.db.sql("""
		SELECT ce.email_id
		FROM `tabContact Email` ce
		JOIN `tabContact` co ON co.name = ce.parent
		JOIN `tabDynamic Link` dl ON dl.parent = co.name
		WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
		LIMIT 1
	""", customer)
	if result and result[0][0]:
		return result[0][0]

	# 3. Address email fallback
	result = frappe.db.sql("""
		SELECT ad.email_id
		FROM tabAddress ad
		JOIN `tabDynamic Link` dl ON dl.parent = ad.name
		WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
		  AND ad.email_id IS NOT NULL AND ad.email_id != ''
		LIMIT 1
	""", customer)
	return result[0][0] if result else None


def build_soa_html(doc_name, data):
	def fc(amount):
		if amount is None:
			return '-'
		return fmt_money(amount, currency=data.get('currency') or 'SGD')

	style = """
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;700&display=swap">
<style>
* { font-family: 'IBM Plex Sans', sans-serif !important; }
.page-break { display: block; page-break-before: always; }
.lhead { font-size:9px; margin-top:0px; margin-bottom:0px !important; vertical-align: top !important; }
.blhead { font-weight:600 !important; font-size:9px !important; }
.address-sec { margin-top:0px; margin-bottom:0px !important; vertical-align: text-top; }
.left_dotted { border-left: 2px dotted !important; }
p { font-size: 13px; margin: 0px 0px 2px; }
.new1 { border-top: 1px dotted !important; }
.ontop { border-top: 1px; }
.onbottom { border-bottom: 1px; }
</style>"""

	logo_path = os.path.join(frappe.get_site_path(), "public", "files", "photo_2024-05-10_09-34-57.jpg")
	logo_src = ""
	if os.path.exists(logo_path):
		with open(logo_path, "rb") as f:
			logo_src = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")

	header = f"""
<div class="letter-head" style="padding-top:10px;">
	<div class="letter-head">
	<table width="100%"><tbody><tr>
		<td width="10%"><img height="60" src="{logo_src}" width="60"></td>
		<td width="21%">
			<p style="margin-bottom:0px !important; margin-top:0px;"><b style="font-size:11px;">KG SOWERS GROUP PTE LTD</b></p>
			<p class="lhead">2 GAMBAS CRESCENT,</p>
			<p class="lhead">#08-03/04 NORDCOM II, TOWER 1</p>
			<p class="lhead">Singapore 757044</p>
		</td>
		<td width="32%">
			<br>
			<p class="lhead"><b class="blhead">Web: </b>www.sowers.com.sg</p>
			<p class="lhead"><b class="blhead">UEN/GST No: </b>201527820N</p>
		</td>
		<td align="centre"><b style="font-size:20px; text-transform:uppercase;">Statement of Account</b></td>
	</tr></tbody></table>
	</div>
</div>
<hr>
<div>"""

	table_header = """
<table class="table table-bordered" style="font-size:13px; border-spacing:1px; width:100%;">
<thead><tr>
	<td style="width:5%"><b>No.</b></td>
	<td style="width:18%"><b>Doc No</b></td>
	<td style="width:10%"><b>Date</b></td>
	<td style="width:11%"><b>Due Date</b></td>
	<td style="width:13%" align="right"><b>Debit</b></td>
	<td style="width:13%" align="right"><b>Credit</b></td>
	<td style="width:13%" align="right"><b>Balance</b></td>
</tr></thead>
<tbody>"""

	html = style + header

	for j, cu in enumerate(data.get('cust', [])):
		cad = cu.get('cad_data') or {}
		ageing = cu.get('ageing') or {}

		html += f"""
<table width="100%"><tbody><tr>
	<td>
		<p class="address-sec">{cad.get('customer_name','')}</p>
		<p class="address-sec">{cad.get('address_line1','')}</p>
		<p class="address-sec">{cad.get('address_line2','')}</p>
		<p class="address-sec">{cad.get('city','')} {cad.get('pincode','')}</p>
		<p class="address-sec">{cad.get('country','')}</p>
	</td>
	<td>
		<p class="address-sec">Currency : {data.get('currency','')}</p>
		<p class="address-sec">Payment Terms : C.O.D</p>
		<p class="address-sec">Total Due : {fc(ageing.get('outstanding'))}</p>
	</td>
	<td class="left_dotted">
		<p class="address-sec" style="padding-left:10px;">Statement No.: {doc_name}</p>
		<p class="address-sec" style="padding-left:10px;">Date.: {data.get('posting_date','')}</p>
	</td>
</tr></tbody></table>
<hr class="new1">"""

		html += table_header
		idx = 1
		for row in cu.get('data', []):
			is_summary = not row.get('voucher_no') and row.get('account')
			if is_summary:
				html += f"""<tr style="font-weight:bold; background:#f5f5f5;">
	<td colspan="4"><b>{row.get('account','')}</b></td>
	<td align="right">{fc(row.get('debit'))}</td>
	<td align="right">{fc(row.get('credit'))}</td>
	<td align="right">{fc(row.get('balance'))}</td>
</tr>"""
			elif row.get('voucher_no'):
				due_date = str(row.get('due_date') or '')
				html += f"""<tr>
	<td style="width:5%">{idx}</td>
	<td style="width:18%">{row.get('voucher_no','')}</td>
	<td style="width:10%">{str(row.get('posting_date',''))}</td>
	<td style="width:11%; white-space:nowrap;">{due_date}</td>
	<td style="width:13%" align="right">{fc(row.get('debit'))}</td>
	<td style="width:13%" align="right">{fc(row.get('credit'))}</td>
	<td style="width:13%" align="right">{fc(row.get('balance'))}</td>
</tr>"""
				idx += 1

		outstanding_in_words = ageing.get('outstanding_in_words', '')
		html += f"""</tbody></table>
<div id="footer-html">
<table width="100%" class="table"><tbody><tr>
	<td width="14%" class="ontop onbottom"><p><b>In Words:</b></p></td>
	<td width="60%" class="ontop onbottom"><p>{outstanding_in_words}</p></td>
	<td width="12%" class="ontop onbottom"><p><b>Total Due:</b></p></td>
	<td width="14%" class="ontop onbottom"><p>{fc(ageing.get('outstanding'))}</p></td>
</tr></tbody></table>
<table class="table table-bordered" style="font-size:13px; border-spacing:0px; width:100%;">
<thead><tr>
	<td style="width:16%" align="center"><b>Current Due</b></td>
	<td style="width:16%" align="center"><b>1-30 Days</b></td>
	<td style="width:16%" align="center"><b>31-60 Days</b></td>
	<td style="width:16%" align="center"><b>61-90 Days</b></td>
	<td style="width:16%" align="center"><b>120+ Days</b></td>
	<td style="width:16%" align="center"><b>Amount Due</b></td>
</tr></thead>
<tbody><tr>
	<td align="center">{fc(ageing.get('current_due'))}</td>
	<td align="center">{fc(ageing.get('range1'))}</td>
	<td align="center">{fc(ageing.get('range2'))}</td>
	<td align="center">{fc(ageing.get('range3'))}</td>
	<td align="center">{fc(ageing.get('range4'))}</td>
	<td align="center">{fc(ageing.get('outstanding'))}</td>
</tr></tbody></table>
<center style="font-size:8px;">THIS IS A COMPUTER GENERATED DOCUMENT. NO SIGNATURE IS REQUIRED.</center>
</div>"""

		if j + 1 < len(data.get('cust', [])):
			html += '<div style="page-break-before:always;"></div>' + header

	html += '</div>'
	return html


@frappe.whitelist()
def send_emails(document_name, from_scheduler=False):
	"""Override for ERPNext's send_emails — sends SOA PDF using our GL-based HTML builder."""
	from frappe.utils.pdf import get_pdf
	name = document_name
	data = get_statements_of_account(name)
	if not data.get('cust'):
		frappe.msgprint("No statement data found.")
		return
	cu = data['cust'][0]
	customer = (cu.get('cad_data') or {}).get('customer_name') or name
	psoa_doc = frappe.get_doc('Process Statement Of Accounts', name)
	recipients = [get_customer_email(psoa_doc.customers[0].customer)]
	recipients = [r for r in recipients if r]
	if not recipients:
		frappe.msgprint("No email address found for this customer.")
		return
	html = build_soa_html(name, data)
	pdf_content = get_pdf(html)
	frappe.sendmail(
		recipients=recipients,
		subject=f"Statement of Account",
		message=f"<p>Please find your Statement of Account attached.</p>",
		attachments=[{'fname': f"SOA_{name}.pdf", 'fcontent': pdf_content}],
		reference_doctype='Process Statement Of Accounts',
		reference_name=name,
		now=True
	)
	frappe.msgprint(f"SOA email sent to: {', '.join(recipients)}")


def get_eligible_customer_companies(from_date, to_date):
	"""Return distinct (customer, company) pairs with GL activity in the given period."""
	return frappe.db.sql("""
		SELECT DISTINCT gl.party AS customer, gl.company
		FROM `tabGL Entry` gl
		JOIN `tabCustomer` cu ON cu.name = gl.party
		WHERE gl.party_type = 'Customer'
		  AND gl.is_cancelled = 0
		  AND gl.posting_date BETWEEN %s AND %s
		  AND cu.disabled = 0
	""", (from_date, to_date), as_dict=True)


def create_soa_for_customer(customer, company, from_date, to_date):
	"""Create or reuse a deterministic PSOA doc for this customer+company+month."""
	month_str = frappe.utils.getdate(to_date).strftime('%Y-%m')
	doc_name = f"SOA-{customer}-{company}-{month_str}"

	if frappe.db.exists('Process Statement Of Accounts', doc_name):
		psoa_doc = frappe.get_doc('Process Statement Of Accounts', doc_name)
		psoa_doc.from_date = from_date
		psoa_doc.to_date = to_date
		psoa_doc.group_by = "Group by Voucher (Consolidated)"
		psoa_doc.save(ignore_permissions=True)
	else:
		psoa_doc = frappe.new_doc('Process Statement Of Accounts')
		psoa_doc.name = doc_name
		psoa_doc.company = company
		psoa_doc.from_date = from_date
		psoa_doc.to_date = to_date
		psoa_doc.group_by = "Group by Voucher (Consolidated)"
		psoa_doc.append('customers', {'customer': customer})
		psoa_doc.insert(ignore_permissions=True)

	frappe.db.commit()
	return psoa_doc


def build_temp_soa_for_customer(customer, company, from_date, to_date):
	"""Build an in-memory (never inserted) PSOA doc for this customer+company+period."""
	month_str = frappe.utils.getdate(to_date).strftime('%Y-%m')
	psoa_doc = frappe.new_doc('Process Statement Of Accounts')
	psoa_doc.name = f"SOA-{customer}-{company}-{month_str}"
	psoa_doc.company = company
	psoa_doc.from_date = from_date
	psoa_doc.to_date = to_date
	psoa_doc.group_by = "Group by Voucher (Consolidated)"
	psoa_doc.append('customers', {'customer': customer})
	return psoa_doc


def run_soa_monthly_job(from_date, to_date, month_label, test_email=None):
	"""Shared core for the real monthly SOA run and the SOA Settings test-email feature."""
	from frappe.utils.pdf import get_pdf

	settings = frappe.get_single('SOA Settings')
	default_subject = settings.email_subject or "Statement of Account — {month}"
	default_message = settings.email_message or """
		<p>Dear {customer_name},</p>
		<p>Thank you for your continued business and valued partnership with us.</p>
		<p>Please find attached your Statement of Account for <b>{month}</b>.</p>
		<p>Should you have any queries, please do not hesitate to reach out to us.</p>
		<p>We truly appreciate your trust and look forward to serving you.</p>
		<br><p>Warm regards,<br><b>KG Sowers Group Pte Ltd</b></p>
	"""

	eligible = get_eligible_customer_companies(from_date, to_date)
	sent_customers = set()
	emails_sent = 0

	for entry in eligible:
		customer = entry['customer']
		company = entry['company']
		key = (customer, company)
		if key in sent_customers:
			continue

		try:
			if test_email:
				psoa_doc = build_temp_soa_for_customer(customer, company, from_date, to_date)
			else:
				psoa_doc = create_soa_for_customer(customer, company, from_date, to_date)

			data = get_statements_of_account(psoa_doc, from_date, to_date)

			if not data.get('cust'):
				continue

			cu = data['cust'][0]
			if not any(r.get('voucher_no') for r in cu.get('data', [])):
				continue

			recipient = test_email or get_customer_email(customer)
			if not recipient:
				continue

			customer_name = (cu.get('cad_data') or {}).get('customer_name') or customer
			subject = default_subject.replace('{month}', month_label)
			message = default_message.replace('{month}', month_label).replace('{customer_name}', customer_name)

			html = build_soa_html(psoa_doc.name, data)
			pdf_content = get_pdf(html)

			sendmail_kwargs = dict(
				recipients=[recipient],
				subject=subject,
				message=message,
				attachments=[{
					'fname': f"SOA_{customer}_{month_label.replace(' ', '_')}.pdf",
					'fcontent': pdf_content
				}],
				now=True
			)
			if not test_email:
				sendmail_kwargs['reference_doctype'] = 'Process Statement Of Accounts'
				sendmail_kwargs['reference_name'] = psoa_doc.name

			frappe.sendmail(**sendmail_kwargs)
			sent_customers.add(key)
			emails_sent += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"SOA Email Failed: {customer}")

	return emails_sent


def send_soa_emails():
	from frappe.utils import get_first_day, get_last_day, add_months, today

	settings = frappe.get_single('SOA Settings')
	if not settings.enable_auto_soa_email:
		return

	first_of_prev = get_first_day(add_months(today(), -1))
	last_of_prev = get_last_day(first_of_prev)
	from_date = str(first_of_prev)
	to_date = str(last_of_prev)
	month_label = frappe.utils.formatdate(to_date, 'MMMM YYYY')

	run_soa_monthly_job(from_date, to_date, month_label)


@frappe.whitelist()
def send_test_soa_email(email, from_date, to_date):
	frappe.only_for('System Manager')
	frappe.enqueue(
		run_test_soa_email_job,
		queue='long',
		timeout=3600,
		email=email,
		from_date=from_date,
		to_date=to_date,
		requesting_user=frappe.session.user,
	)
	return {"queued": True}


def run_test_soa_email_job(email, from_date, to_date, requesting_user):
	month_label = frappe.utils.formatdate(to_date, 'MMMM YYYY')
	try:
		emails_sent = run_soa_monthly_job(from_date, to_date, month_label, test_email=email)
		frappe.publish_realtime(
			"soa_test_email_done",
			{"success": True, "emails_sent": emails_sent},
			user=requesting_user,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "SOA Test Email Job Failed")
		frappe.publish_realtime(
			"soa_test_email_done",
			{"success": False, "error": frappe.get_traceback()},
			user=requesting_user,
		)
