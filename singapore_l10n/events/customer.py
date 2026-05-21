import frappe
from frappe.utils import today


@frappe.whitelist()
def get_statements_of_account_for_customer(name, from_date=None, to_date=None):
    from_date = from_date or '2000-01-01'
    to_date = to_date or today()

    if frappe.db.exists("Process Statement Of Accounts", name):
        psoa_doc = frappe.get_doc("Process Statement Of Accounts", name)
        psoa_doc.posting_date = today()
        psoa_doc.from_date = from_date
        psoa_doc.to_date = to_date
        psoa_doc.save(ignore_permissions=True)
    else:
        psoa_doc = frappe.new_doc("Process Statement Of Accounts")
        psoa_doc.name = name
        psoa_doc.report = "Accounts Receivable"
        psoa_doc.posting_date = today()
        psoa_doc.from_date = from_date
        psoa_doc.to_date = to_date
        psoa_doc.append("customers", {
            'customer': name
        })
        psoa_doc.insert(ignore_permissions=True)
    frappe.db.commit()

    from singapore_l10n.events.process_statement_of_accounts import get_statements_of_account
    return get_statements_of_account(psoa_doc.name)