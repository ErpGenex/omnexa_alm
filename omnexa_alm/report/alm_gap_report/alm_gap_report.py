import frappe


def execute(filters=None):
	columns = [
		{"label": "Bucket", "fieldname": "bucket", "fieldtype": "Data", "width": 130},
		{"label": "Asset Repricing", "fieldname": "asset_repricing", "fieldtype": "Currency", "width": 170},
		{"label": "Liability Repricing", "fieldname": "liability_repricing", "fieldtype": "Currency", "width": 170},
		{"label": "Gap", "fieldname": "gap", "fieldtype": "Currency", "width": 140},
	]
	rows = frappe.db.sql(
		"""
		select
			case
				when repricing_days between 0 and 30 then '0-30'
				when repricing_days between 31 and 90 then '31-90'
				when repricing_days between 91 and 180 then '91-180'
				when repricing_days between 181 and 365 then '181-365'
				else '366+'
			end as bucket,
			sum(case when book='ASSET' then amount else 0 end) as asset_repricing,
			sum(case when book='LIABILITY' then amount else 0 end) as liability_repricing,
			sum(case when book='ASSET' then amount else -amount end) as gap
		from `tabALM Position Snapshot`
		group by bucket
		order by field(bucket, '0-30', '31-90', '91-180', '181-365', '366+')
		""",
		as_dict=True,
	)
	return columns, rows

