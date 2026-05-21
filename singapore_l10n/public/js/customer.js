frappe.ui.form.on('Customer', {
	refresh(frm) {
		frm.add_custom_button(__('Download SOA'), function(){
			let dialog = new frappe.ui.Dialog({
				title: __('Select Date Range'),
				fields: [
					{
						fieldname: 'from_date',
						fieldtype: 'Date',
						label: __('From Date'),
						reqd: 1,
						default: frappe.datetime.month_start()
					},
					{
						fieldname: 'to_date',
						fieldtype: 'Date',
						label: __('To Date'),
						reqd: 1,
						default: frappe.datetime.get_today()
					}
				],
				primary_action_label: __('Download'),
				primary_action(values) {
					dialog.hide();
					frappe.call({
						method: "singapore_l10n.events.customer.get_statements_of_account_for_customer",
						args: {
							name: frm.doc.name,
							from_date: values.from_date,
							to_date: values.to_date
						},
						freeze: true,
						freeze_message: __("Generating report ..."),
						callback: function (r) {
							let p_html = set_html(frm, r.message)
							frappe.render_pdf(p_html, {orientation:"Portrait"});
						}
					});
				}
			});
			dialog.show();
		});
	}
})


var set_html = function(frm, r) {
	let style = `
	<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;700&display=swap" rel="stylesheet">
	<style>
.page-break    { display: block; page-break-before: always; }

.lhead{
	font-size:9px;
	margin-top:0px;
	margin-bottom:0px !important;
	vertical-align: top !important;
	}
	*{
		font-family: 'IBM Plex Sans', sans-serif !important;
	}
	.print-format {
		margin-left: 4mm;
		margin-right: 4mm;
	}
	.new1{
		border-top: 1px dotted !important;
		}
	.blhead{
	font-weight:600 !important;
	font-size:9px !important;
	}
	.print-format .letter-head {
		margin-bottom: 0px;
		}
	.print-format .letterhead td, .print-format th {
	padding: 1 1px 1 1px !important;
	vertical-align: top !important;
	margin:0px !important;
	}
	.print-format p{
	margin:0px 0px 2px;
	}
	.print-format .letter-head {
	margin-bottom: 0px;
	}

	p{
        font-size: 13px;
    }
	.address-sec{
		margin-top:0px;
		margin-bottom:0px !important;
		vertical-align: text-top;
	}
	.left_dotted {
		border-left: 2px dotted !important;
	  }
	.ontop{
		border-top: 1px;
	}
	.onbottom{
		border-bottom: 1px;;
	}


</style>`
let header = `
	<div class="letter-head"  style="padding-top:10px;">
		<div class="letter-head">
		<table  width="100%" "class="letter-head">
		<tbody>
		<tr>
			<td width="10%">
				<img height="60" src="/files/photo_2024-05-10_09-34-57.jpg" width="60">
			</td>
			<td width="21%">
				<p style="margin-bottom:0px !important; margin-top:0px;">
					<b style="font-size:11px; margin-bottom:0px !important; margin-top:0px;">KG SOWERS GROUP PTE LTD</b>
				</p>
				<p class="lhead">2 GAMBAS CRESCENT,</p>
				<p class="lhead">#08-03/04 NORDCOM II, TOWER 1</p>
				<p class="lhead">Singapore 757044</p>
			</td>
			<td width="32%">
				<br>
				<p class="lhead"><b class="blhead">Web: </b>www.sowers.com.sg</p>
				<p class="lhead"><b class="blhead">UEN/GST No: </b> 201527820N</p>
			</td>
			<td align="centre">
				<b style="font-size: 20px; text-transform: uppercase;">
				Statement of Account
				</b>
			</td>
		</tr></tbody>
	</table>
	<div/>
	<div/>
	<hr>
	<div>
		`

	let table_header = `
		<table class="table table-bordered" style="font-size: 13px; border-spacing: 1px;">
		<thead>
			<tr>
				<td style="width: 5%"><b>No.</b></td>
				<td style="width: 18%"><b>Doc No</b></td>
				<td style="width: 10%"><b>Date</b></td>
				<td style="width: 11%"><b>Due Date</b></td>
				<td style="width: 13%" align="right"><b>Debit</b></td>
				<td style="width: 13%" align="right"><b>Credit</b></td>
				<td style="width: 13%" align="right"><b>Balance</b></td>
			</tr>
		</thead>
		<tbody>`

	let html = style + header
	if (r.cust) {
		$.each(r.cust, function(j, cu) {
			html +=`

		<table width="100%" class="cust_head">
	<tbody>
		<tr>
			<td>
			<p class="address-sec">${(cu.cad_data && cu.cad_data.customer_name)?cu.cad_data.customer_name:''}</p>
			<p class="address-sec">${(cu.cad_data && cu.cad_data.address_line1)?cu.cad_data.address_line1:''}</p>
			<p class="address-sec">${(cu.cad_data && cu.cad_data.address_line2)?cu.cad_data.address_line2:''}</p>
			<p class="address-sec">${(cu.cad_data && cu.cad_data.city)?cu.cad_data.city:''} ${(cu.cad_data && cu.cad_data.pincode)?cu.cad_data.pincode:''}</p>
			<p class="address-sec">${(cu.cad_data && cu.cad_data.country)?cu.cad_data.country:''}</p>
			</td>
			<td>
				<p class="address-sec">Currency : ${r.currency ? r.currency : ''}</p>
				<p class="address-sec">Payment Terms : C.O.D</p>
				<p class="address-sec">Total Due : ${(cu.ageing && cu.ageing.outstanding != null)?format_currency(cu.ageing.outstanding):''}</p>
			</td>
			<td class="left_dotted">
				<p class="address-sec" style="padding-left:10px;">Statement No.: ${frm.doc.name}</p>
				<p class="address-sec" style="padding-left:10px;">Date.: ${r.posting_date} </p>
			</td>
		</tr>
	</tbody>
</table>
<hr class="new1">
		`
		html += table_header;

		if (cu.data) {
			var idx = 1;
			$.each(cu.data, function(_i, val) {
				let is_summary = !val.voucher_no && val.account;
				if (is_summary) {
					html += `<tr style="font-weight:bold; background:#f5f5f5;">
						<td colspan="4">${val.account || ''}</td>
						<td align="right">${val.debit != null ? format_currency(val.debit) : '-'}</td>
						<td align="right">${val.credit != null ? format_currency(val.credit) : '-'}</td>
						<td align="right">${val.balance != null ? format_currency(val.balance) : '-'}</td>
					</tr>`;
				} else if (val.voucher_no) {
					html += `<tr>
						<td style="width: 5%">${idx}</td>
						<td style="width: 18%">${val.voucher_no || ''}</td>
						<td style="width: 10%">${val.posting_date || ''}</td>
						<td style="width: 11%; white-space: nowrap;">${val.due_date || ''}</td>
						<td style="width: 13%" align="right">${val.debit != null ? format_currency(val.debit) : '-'}</td>
						<td style="width: 13%" align="right">${val.credit != null ? format_currency(val.credit) : '-'}</td>
						<td style="width: 13%" align="right">${val.balance != null ? format_currency(val.balance) : '-'}</td>
					</tr>`;
					if (idx % 27 == 0) {
						html += `</tbody></table><div class="page-break"></div>`;
						html += header + table_header;
					}
					idx += 1;
				}
			})
		}
		html += `</tbody>
		</table>

		<div id="footer-html" class="visible-pdf letter-head-footer">
		<table width="100%" class="table" >
			<tbody>
				<tr>
					<td width="14%" class="ontop onbottom"><p><b>In Words:</b></p></td>
					<td width="60%" class="ontop onbottom">
						<p>${(cu.ageing && cu.ageing.outstanding_in_words) ? cu.ageing.outstanding_in_words : ''}</p>
					</td>
					<td width="12%" class="ontop onbottom"><p><b>Total Due</b>:</p></td>
					<td width="14%" class="ontop onbottom"><p>${(cu.ageing && cu.ageing.outstanding != null)?format_currency(cu.ageing.outstanding):'-'}</p></td>
				</tr>
			</tbody>
		</table>
		<table class="table table-bordered" style="font-size: 13px; border-spacing: 0px;">
		<thead>
			<tr>
				<td style="width: 16%" align="center"><b>Current Due</b></td>
				<td style="width: 16%" align="center"><b>1-30 Days</b></td>
				<td style="width: 16%" align="center"><b>31-60 Days</b></td>
				<td style="width: 16%" align="center"><b>61-90 Days</b></td>
				<td style="width: 16%" align="center"><b>120+ Days</b></td>
				<td style="width: 16%" align="center"><b>Amount Due</b></td>
			</tr>
		</thead>
		<tbody>
			<tr>
				<td align="center">${(cu.ageing && cu.ageing.current_due != null)?format_currency(cu.ageing.current_due):'-'}</td>
				<td align="center">${(cu.ageing && cu.ageing.range1 != null)?format_currency(cu.ageing.range1):'-'}</td>
				<td align="center">${(cu.ageing && cu.ageing.range2 != null)?format_currency(cu.ageing.range2):'-'}</td>
				<td align="center">${(cu.ageing && cu.ageing.range3 != null)?format_currency(cu.ageing.range3):'-'}</td>
				<td align="center">${(cu.ageing && cu.ageing.range4 != null)?format_currency(cu.ageing.range4):'-'}</td>
				<td align="center">${(cu.ageing && cu.ageing.outstanding != null)?format_currency(cu.ageing.outstanding):'-'}</td>
			</tr>
		</tbody>
	</table>
	<center style="font-size: 8px;">THIS IS A COMPUTER GENERATED DOCUMENT. NO SIGNATURE IS REQUIRED. </center>
	</div>`
	if ((j+1)< r.cust.length) {
		html += `
			<div style="page-break-before: always;" class="pagebreak"></div>`
		html += header
	}
	})
	}

	html += '</div>'
	return html
}
