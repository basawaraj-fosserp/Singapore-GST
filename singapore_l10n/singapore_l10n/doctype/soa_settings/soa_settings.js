frappe.ui.form.on('SOA Settings', {
	refresh(frm) {

	}
});

frappe.ui.form.on('SOA Table', {
	customer(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		console.log(row.customer);
		if (!row.customer) {
			return;
		}
		frappe.call({
			method: 'singapore_l10n.events.process_statement_of_accounts.get_customer_contact_emails',
			args: {
				customer: row.customer
			},
			callback: function (r) {
				if (r.message !== undefined) {
					frappe.model.set_value(cdt, cdn, 'email', r.message);
				}
			}
		});
	}
});
