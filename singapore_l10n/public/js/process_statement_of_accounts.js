frappe.ui.form.on('Process Statement Of Accounts', {
	refresh(frm) {
		frm.add_custom_button(__('Download SOA'), function(){
			frappe.call({
				"method": "singapore_l10n.events.process_statement_of_accounts.get_statements_of_account_from_gl",
				"args": {
					'name': frm.doc.name
				},
				callback: function (r) {
					let is_gl = r.message.report === "General Ledger";
					let p_html = set_html(frm, r.message, is_gl)
					frappe.render_pdf(p_html, {orientation:"Portrait"});
				}
			});
		});
		frm.remove_custom_button(__("Download"))
		}
})


var set_html = function(frm, r, is_gl) {
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
	<table  width="100%" class="letter-head">
	<tbody>
	   <tr>
		  <td width="10%">
			<img height="60" src="/files/KGS-Logo.png" width="60">
		  </td>
		  <td width="21%">
			 <p style="margin-bottom:0px !important; margin-top:0px;">
			 	<b style="font-size:11px; margin-bottom:0px !important; margin-top:0px;">KGS Pte Ltd</b>
			 </p>
			 <p class="lhead">8 Tuas South Lane,</p>
			 <p class="lhead">#01-71, Factory 4,</p>
			 <p class="lhead">Singapore 637302</p>
		  </td>
		  <td width="32%">
			 <br>
			 <p class="lhead"><b class="blhead">Web:</b>kgs.com.sg</p>
			 <p class="lhead"><b class="blhead">UEN/GST No:</b> 201607799N</p>
		  </td>
		  <td align="centre">
			 <b style="font-size: 20px; text-transform: uppercase;">
			 Statement of Account 
			  </b>
		 </td>
	</tr></tbody>
 </table>	
 </div>
	</div>
	<hr>
	<div>
		`

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
			<td class="left_dotted" style="width: 25%; max-width: 25%;">
				<p class="address-sec" style="padding-left:10px; word-break: break-word; white-space: normal;">Statement No.: ${frm.doc.name}</p>
				<p class="address-sec" style="padding-left:10px;">Date.: ${r.posting_date} </p>
			</td>
		</tr>
	</tbody>
</table>
<hr class="new1">
		`

		let table_header = is_gl ? `
		<table class="table table-bordered" style="font-size: 13px; border-spacing: 1px; table-layout: auto; width: 100%;">
		<thead>
			<tr>
				<td style="width: 4%;"><b>No.</b></td>
				<td style="width: 24%;"><b>Doc No</b></td>
				<td style="width: 11%; white-space: nowrap;"><b>Date</b></td>
				<td style="width: 11%; white-space: nowrap;"><b>Due Date</b></td>
				<td style="white-space: nowrap;" align="right"><b>Debit</b></td>
				<td style="white-space: nowrap;" align="right"><b>Credit</b></td>
				<td style="white-space: nowrap;" align="right"><b>Balance</b></td>
			</tr>
		</thead>
		<tbody>` : `
		<table class="table table-bordered" style="font-size: 13px; border-spacing: 1px; table-layout: auto; width: 100%;">
		<thead>
			<tr>
				<td style="width: 4%;"><b>No.</b></td>
				<td style="width: 24%;"><b>Doc No</b></td>
				<td style="width: 11%; white-space: nowrap;"><b>Date</b></td>
				<td style="width: 11%; white-space: nowrap;"><b>Due Date</b></td>
				<td style="white-space: nowrap;" align="right"><b>Debit</b></td>
				<td style="white-space: nowrap;" align="right"><b>Credit</b></td>
				<td style="white-space: nowrap;" align="right"><b>Balance</b></td>
			</tr>
		</thead>
		<tbody>`;

		html += table_header;

		if (cu.data) {
			var idx = 1;
			$.each(cu.data, function(i, val) {
				if (is_gl) {
					// GL rows: regular entries have voucher_no; opening/total/closing rows have account label only
					let is_summary = !val.voucher_no && val.account;
					if (is_summary) {
						html += `<tr style="font-weight:bold; background:#f5f5f5;">
							<td></td>
							<td><b>${val.account || ''}</b></td>
							<td></td>
							<td></td>
							<td style="white-space: nowrap;" align="right">${val.debit != null ? format_currency(val.debit) : '-'}</td>
							<td style="white-space: nowrap;" align="right">${val.credit != null ? format_currency(val.credit) : '-'}</td>
							<td style="white-space: nowrap;" align="right">${val.balance != null ? format_currency(val.balance) : '-'}</td>
						</tr>`;
					} else if (val.voucher_no) {
						html += `<tr>
							<td style="width: 4%;">${idx}</td>
							<td style="width: 24%;">${val.voucher_no || ''}</td>
							<td style="width: 11%; white-space: nowrap;">${val.posting_date || ''}</td>
							<td style="width: 11%; white-space: nowrap;">${val.due_date || ''}</td>
							<td style="white-space: nowrap;" align="right">${val.debit != null ? format_currency(val.debit) : '-'}</td>
							<td style="white-space: nowrap;" align="right">${val.credit != null ? format_currency(val.credit) : '-'}</td>
							<td style="white-space: nowrap;" align="right">${val.balance != null ? format_currency(val.balance) : '-'}</td>
						</tr>`;
						if (idx % 27 == 0) {
							html += `</tbody></table><div class="page-break"></div>`;
							html += header + table_header;
						}
						idx += 1;
					}
				} else {
					// AR rows
					if (val.is_opening) {
						html += `<tr style="font-weight:bold; background:#f5f5f5;">
							<td></td>
							<td><b>Opening Balance</b></td>
							<td></td>
							<td></td>
							<td style="white-space: nowrap;" align="right">${val.debit ? format_currency(val.debit) : '-'}</td>
							<td style="white-space: nowrap;" align="right">${val.credit ? format_currency(val.credit) : '-'}</td>
							<td style="white-space: nowrap;" align="right">${val.accum_balance != null ? format_currency(val.accum_balance) : '-'}</td>
						</tr>`;
					} else if (val.is_summary) {
						html += `<tr style="font-weight:bold; background:#f5f5f5;">
							<td></td>
							<td><b>${val.label || ''}</b></td>
							<td></td>
							<td></td>
							<td style="white-space: nowrap;" align="right">${val.debit ? format_currency(val.debit) : '-'}</td>
							<td style="white-space: nowrap;" align="right">${val.credit ? format_currency(val.credit) : '-'}</td>
							<td style="white-space: nowrap;" align="right">${val.accum_balance != null ? format_currency(val.accum_balance) : '-'}</td>
						</tr>`;
					} else if (val.voucher_no) {
						html += `<tr>
							<td style="width: 4%;">${idx}</td>
							<td style="width: 24%;">${val.voucher_no || ''}</td>
							<td style="width: 11%; white-space: nowrap;">${val.posting_date || ''}</td>
							<td style="width: 11%; white-space: nowrap;">${val.due_date || ''}</td>
							<td style="white-space: nowrap;" align="right">${val.debit ? format_currency(val.debit) : '-'}</td>
							<td style="white-space: nowrap;" align="right">${val.credit ? format_currency(val.credit) : '-'}</td>
							<td style="white-space: nowrap;" align="right">${val.accum_balance != null ? format_currency(val.accum_balance) : '-'}</td>
						</tr>`;
						if (idx % 27 == 0) {
							html += `</tbody></table><div class="page-break"></div>`;
							html += header + table_header;
						}
						idx += 1;
					}
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
					<td width="58%" class="ontop onbottom"><p>${(cu.ageing && cu.ageing.outstanding_in_words) ? cu.ageing.outstanding_in_words : ''}</p></td>
					<td width="12%" class="ontop onbottom"><p><b>Total Due</b>:</p></td>
					<td width="16%" class="ontop onbottom"><p>${(cu.ageing && cu.ageing.outstanding != null)?format_currency(cu.ageing.outstanding):'-'}</p></td>
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
