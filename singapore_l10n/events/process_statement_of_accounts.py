import frappe
import json
from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	execute as get_ageing,
)

@frappe.whitelist()
def get_statements_of_account(name):
	name = frappe.form_dict.name
	psoa_doc = frappe.get_doc('Process Statement Of Accounts', name)
	from_date = json.dumps(psoa_doc.get('from_date'), default=str)
	to_date = json.dumps(psoa_doc.get('to_date'), default=str)
	out_data = {}
	out_list = []
	for cust in psoa_doc.customers:
		cust_dict = {}
		si_query = f'''
			SELECT
				name,
				posting_date,
				due_date,
				total,
				po_no
			FROM
				`tabSales Invoice`
			WHERE
				customer={json.dumps(cust.get("customer"))} AND posting_date BETWEEN {from_date} and {to_date}'''
		si_data = frappe.db.sql(f"{si_query}", as_dict=True)
		if si_data:
			cust_dict['si_data'] = si_data
		cad_query = f'''
			SELECT
				ad.name,
				ad.address_line1,
				ad.address_line2,
				ad.city,
				ad.email_id,
				ad.phone,
				ad.pincode,
				cus.name as customer,
				cus.payment_terms
			FROM
				tabAddress AS ad LEFT JOIN
				`tabDynamic Link` AS dl ON dl.parent=ad.name LEFT JOIN
				tabCustomer AS cus ON dl.link_name=cus.name
			WHERE
				dl.link_doctype="Customer" AND dl.link_name={json.dumps(cust.get("customer"))}
				AND ad.is_primary_address=1'''
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
					"report_date": psoa_doc.to_date,
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
	cod_query = f'''
		SELECT
			ad.name,
			ad.address_line1,
			ad.address_line2,
			ad.city,
			ad.email_id,
			ad.phone,
			ad.pincode,
			ad.fax
		FROM
			tabAddress AS ad LEFT JOIN
			`tabDynamic Link` AS dl ON dl.parent=ad.name
		WHERE
			dl.link_doctype="Company" AND dl.link_name={json.dumps(psoa_doc.get("company"))}'''
	cod_data = frappe.db.sql(f"{cod_query}", as_dict=True)
	if cod_data and cod_data[0]:
		out_data['cod_data'] = cod_data[0]
	return out_data
