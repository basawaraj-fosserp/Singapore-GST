frappe.ui.form.on('Process Statement Of Accounts', {
	refresh(frm) {
		frm.add_custom_button(__('Download SOA'), function(){
			frappe.call({
				"method": "singapore_l10n.events.process_statement_of_accounts.get_statements_of_account",
				"args": {
					'name': frm.doc.name
				},
				callback: function (r) {
					let p_html = set_html(frm, r.message)
					frappe.render_pdf(p_html, {orientation:"Landscape"});
				}
			});
		});
		
		}
})

var set_html = function(frm, r) {
	let html = `
	<style>
.page-break    { display: block; page-break-before: always; }
</style>
	<div>
		<div style="width: 100%; overflow: hidden;">
			<div style="width: 50%; float: left;"> <h3>${frm.doc.company}</h3> <br>
				${(r.cod_data && r.cod_data.address_line1)?r.cod_data.address_line1:''}<br>
				${(r.cod_data && r.cod_data.address_line2)?r.cod_data.address_line2:''}<br>
				${(r.cod_data && r.cod_data.city)?r.cod_data.city:''} ${(r.cod_data && r.cod_data.pincode)?r.cod_data.pincode:''}<br><br>
				Company Registration No:  ${r.tax_id?r.tax_id:''}<br>
				GST Registration No: ${r.tax_id?r.tax_id:''}
			</div>
			<div style="width: 10%; float: right;">
			<br>
		</div>
			<div style="margin-left: 25%; float: right;"><br><br><br>
				Tel : ${(r.cod_data && r.cod_data.phone)?r.cod_data.phone:''}<br>
				Fax : ${(r.cod_data && r.cod_data.fax)?r.cod_data.fax:''}<br>
				Email : ${(r.cod_data && r.cod_data.email_id)?r.cod_data.email_id:''}
			</div>
		</div>`
		if (r.cust) {
			$.each(r.cust, function(j, cu) {
				html +=`
		<div>
			<h2 style="text-align:center"> STATEMENT OF ACCOUNT </h2>
			<h5 style="text-align:center"> AS AT ${frm.doc.to_date} </h5>
		</div>
		<div style="width: 100%; overflow: hidden;">
			<div style="width: 10%; float: left;">
				Customer <br>
				Address	<br>
			</div>
			<div style="width: 1%; float: left;">
				: <br>
				: <br>
			</div>
			<div style="width: 30%; float: left;">
				${(cu.cad_data && cu.cad_data.customer_name)?cu.cad_data.customer_name:''}<br>
				${(cu.cad_data && cu.cad_data.address_line1)?cu.cad_data.address_line1:''}<br>
				${(cu.cad_data && cu.cad_data.address_line2)?cu.cad_data.address_line2:''}<br>
				${(cu.cad_data && cu.cad_data.city)?cu.cad_data.city:''} ${(cu.cad_data && cu.cad_data.pincode)?cu.cad_data.pincode:''}<br><br><br>
			</div>
			<div style="margin-left: width:59%; float: right;">
				Cust. Code : ${(cu.cad_data && cu.cad_data.customer)?cu.cad_data.customer:''}<br>
				Tel : ${(cu.cad_data && cu.cad_data.phone)?cu.cad_data.phone:''}<br>
				Fax : ${(cu.cad_data && cu.cad_data.fax)?cu.cad_data.fax:''}<br>
				Credit Terms : ${(cu.cad_data && cu.cad_data.payment_terms)?cu.cad_data.payment_terms:''}<br>
				Sales Code : <br>
			</div>
		</div>
		<div style="float: left;"> Attention: ${(cu.cco_data && cu.cco_data.first_name)?cu.cco_data.first_name:''} ${(cu.cco_data && cu.cco_data.middle_name)?cu.cco_data.middle_name:''} 
				${(cu.cco_data && cu.cco_data.last_name)?cu.cco_data.last_name:''}
		</div>
		<br>
		<table class="table table-bordered" style="font-size: 15px">
		<thead>
			<tr>
				<td style="width: 5%"><b>No.</b></td>
				<td style="width: 20%"><b>Doc NO</b></td>
				<td style="width: 15%"><b>REFERENCE</b></td>
				<td style="width: 12%"><b>DOCDATE</b></td>
				<td style="width: 12%"><b>DUE DATE</b></td>
				<td style="width: 10%"><b>DEBIT</b></td>
				<td style="width: 10%"><b>CREDIT</b></td>
				<td style="width: 14%"><b>ACCUM. BALANCE</b></td>
			</tr>
		</thead>
		<tbody>
		<b><br>CURRENCY : </b>`
		if (cu.data) {
			var idx = 1;
			$.each(cu.data, function(i, val) {
				if (val.voucher_no) {
					html += `<tr>
						<td style="width: 5%">${idx}</td>
						<td style="width: 20%">${val.voucher_no?val.voucher_no:''}</td>
						<td style="width: 15%">${val.po_no?val.po_no:''}</td>
						<td style="width: 12%">${val.posting_date?val.posting_date:''}</td>
						<td style="width: 12%">${val.due_date?val.due_date:''}</td>
						<td style="width: 10%">${val.debit?val.debit:0}</td>
						<td style="width: 10%">${val.credit?Math.round(((val.credit)+Number.EPSILON)*100)/100:0}</td>
						<td style="width: 14%">${val.balance?format_currency(val.balance):0}</td>
					</tr>`
				idx += 1
				}
			})
		}
		html += `</tbody>
		</table><br>
		<table class="table table-bordered" style="width: 100%">
		<thead>
			<tr>
				<td style="width: 16%"><b>AGEING SUMMARY IN</b></td>
				<td style="width: 16%"><b>TOTAL</b></td>
				<td style="width: 16%"><b>30 Days</b></td>
				<td style="width: 16%"><b>60 Days</b></td>
				<td style="width: 16%"><b>90 Days</b></td>
				<td style="width: 16%"><b>120 Days</b></td>
			</tr>
		</thead>
		<tbody>
			<tr>
				<td>${(cu.ageing && cu.ageing.currency)?cu.ageing.currency:''}</td>
				<td>${(cu.ageing && cu.ageing.outstanding)?cu.ageing.outstanding:''}</td>
				<td>${(cu.ageing && cu.ageing.range1)?cu.ageing.range1:''}</td>
				<td>${(cu.ageing && cu.ageing.range2)?cu.ageing.range2:''}</td>
				<td>${(cu.ageing && cu.ageing.range3)?cu.ageing.range3:''}</td>
				<td>${(cu.ageing && cu.ageing.range4)?cu.ageing.range4:''}</td>
			</tr>
		</tbody>
	</table>`
	if ((j+1)< r.cust.length) {
		html += `
			<div style="page-break-before: always;" class="pagebreak"></div>`
	}
	})
	}
	
	html += '</div>'
	return html
}
