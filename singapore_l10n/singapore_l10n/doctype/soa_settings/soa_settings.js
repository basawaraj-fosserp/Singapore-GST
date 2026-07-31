frappe.ui.form.on('SOA Settings', {
	refresh: function(frm) {
		frm.add_custom_button(__('Send Test Email'), function() {
			let dialog = new frappe.ui.Dialog({
				title: __('Send Test SOA Email'),
				fields: [
					{
						fieldname: 'email',
						fieldtype: 'Data',
						label: __('Send To Email'),
						options: 'Email',
						reqd: 1,
					},
					{
						fieldname: 'from_date',
						fieldtype: 'Date',
						label: __('From Date'),
						reqd: 1,
						default: frappe.datetime.month_start(),
					},
					{
						fieldname: 'to_date',
						fieldtype: 'Date',
						label: __('To Date'),
						reqd: 1,
						default: frappe.datetime.month_end(),
					},
				],
				primary_action_label: __('Send'),
				primary_action(values) {
					frappe.call({
						method: 'singapore_l10n.events.process_statement_of_accounts.send_test_soa_email',
						args: {
							email: values.email,
							from_date: values.from_date,
							to_date: values.to_date,
						},
						callback: function() {
							dialog.hide();
							frappe.show_alert({
								message: __('Test SOA email job queued'),
								indicator: 'blue',
							});
						},
					});
				},
			});
			dialog.show();
		});
	},
});

frappe.realtime.on('soa_test_email_done', function(data) {
	if (data.success) {
		if (data.emails_sent) {
			frappe.show_alert({
				message: __('Test SOA emails sent: {0}', [data.emails_sent]),
				indicator: 'green',
			});
		} else {
			frappe.show_alert({
				message: __('No eligible customers found for the selected range'),
				indicator: 'orange',
			});
		}
	} else {
		frappe.msgprint({
			title: __('SOA Test Email Failed'),
			message: __('The test SOA email job failed. Check the Error Log for details.'),
			indicator: 'red',
		});
	}
});
