import frappe


def execute(filters=None):
	columns = [
		{"label": "Run Date", "fieldname": "run_date", "fieldtype": "Date", "width": 120},
		{"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 180},
		{"label": "Outlier Ratio", "fieldname": "outlier_ratio", "fieldtype": "Float", "width": 120},
		{"label": "Breach", "fieldname": "breach", "fieldtype": "Check", "width": 100},
	]
	rows = frappe.db.sql(
		"""
		select
			run_date,
			company,
			ifnull(outlier_ratio, 0) as outlier_ratio,
			case when ifnull(outlier_ratio, 0) > 0.15 then 1 else 0 end as breach
		from `tabALM Daily Run`
		order by run_date desc
		limit 200
		""",
		as_dict=True,
	)
	return columns, rows

