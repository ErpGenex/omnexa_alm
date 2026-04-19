import frappe


def execute(filters=None):
	columns = [
		{"label": "Run Date", "fieldname": "run_date", "fieldtype": "Date", "width": 120},
		{"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 180},
		{"label": "NII Sensitivity", "fieldname": "nii_sensitivity", "fieldtype": "Currency", "width": 170},
		{"label": "EVE Sensitivity", "fieldname": "eve_sensitivity", "fieldtype": "Currency", "width": 170},
		{"label": "Outlier Ratio", "fieldname": "outlier_ratio", "fieldtype": "Float", "width": 120},
	]
	rows = frappe.get_all(
		"ALM Daily Run",
		fields=["run_date", "company", "nii_sensitivity", "eve_sensitivity", "outlier_ratio"],
		order_by="run_date desc",
		limit_page_length=200,
	)
	return columns, rows

