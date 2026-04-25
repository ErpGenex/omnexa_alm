import frappe


def execute(filters=None):
	columns = [
		{"label": "Run Date", "fieldname": "run_date", "fieldtype": "Date", "width": 120},
		{"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 180},
		{"label": "LCR", "fieldname": "lcr", "fieldtype": "Float", "width": 100},
		{"label": "NSFR", "fieldname": "nsfr", "fieldtype": "Float", "width": 100},
		{"label": "LCR Breach", "fieldname": "lcr_breach", "fieldtype": "Check", "width": 100},
		{"label": "NSFR Breach", "fieldname": "nsfr_breach", "fieldtype": "Check", "width": 100},
	]
	rows = frappe.db.sql(
		"""
		select
			run_date,
			company,
			ifnull(lcr, 0) as lcr,
			ifnull(nsfr, 0) as nsfr,
			case when ifnull(lcr, 0) < 1 then 1 else 0 end as lcr_breach,
			case when ifnull(nsfr, 0) < 1 then 1 else 0 end as nsfr_breach
		from `tabALM Daily Run`
		order by run_date desc
		limit 200
		""",
		as_dict=True,
	)
	return columns, rows

