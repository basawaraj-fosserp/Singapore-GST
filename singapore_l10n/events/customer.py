import frappe
from frappe.utils import today


@frappe.whitelist()
def get_statements_of_account_for_customer(name, from_date=None, to_date=None):
    default_company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
    default_currency = frappe.db.get_value("Company", default_company, "default_currency") or "SGD"

    psoa_doc = frappe.new_doc("Process Statement Of Accounts")
    psoa_doc.report = "General Ledger"
    psoa_doc.company = default_company
    psoa_doc.currency = default_currency
    psoa_doc.ageing_based_on = "Due Date"
    psoa_doc.posting_date = today()
    psoa_doc.from_date = from_date or '2000-01-01'
    psoa_doc.to_date = to_date or today()
    psoa_doc.append("customers", {
        'customer': name
    })
    psoa_doc.insert(ignore_permissions=True)
    frappe.db.commit()

    from singapore_l10n.events.process_statement_of_accounts import get_statements_of_account_from_gl
    return get_statements_of_account_from_gl(psoa_doc.name, is_from_customer=True)