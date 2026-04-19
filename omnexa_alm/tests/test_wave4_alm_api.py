# Copyright (c) 2026, Omnexa and contributors

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from omnexa_alm.api import (
	approve_irrbb_outlier_assessment,
	compute_ftp_margin_attribution,
	evaluate_behavioral_assumptions,
	evaluate_contingency_triggers,
	run_irrbb_standardized_outlier_suite_api,
	submit_irrbb_outlier_assessment,
)


class TestAlmWave4Api(FrappeTestCase):
	def _ensure_user(self, email: str) -> None:
		if frappe.db.exists("User", email):
			return
		doc = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "AlmChecker",
				"send_welcome_email": 0,
				"enabled": 1,
			}
		)
		doc.append("roles", {"role": "System Manager"})
		doc.insert(ignore_permissions=True)

	def test_behavioral_ftp_and_outlier_suite_api(self):
		b = evaluate_behavioral_assumptions(
			[
				{
					"book": "LIABILITY",
					"amount": "100000",
					"repricing_days": 200,
					"instrument_type": "NMD",
				}
			],
			nmd_sticky_ratio="0.8",
		)
		self.assertTrue(b["adjusted_points"])

		curve = json.dumps(
			[
				{"tenor_days": 0, "ftp_rate": "0.02"},
				{"tenor_days": 365, "ftp_rate": "0.045"},
			]
		)
		m = compute_ftp_margin_attribution(
			[{"amount": "50000", "client_rate": "0.07", "tenor_days": 180, "label": "x"}],
			curve,
		)
		self.assertIn("total_margin_income_proxy", m)

		suite = run_irrbb_standardized_outlier_suite_api(
			points=[
				{"book": "ASSET", "amount": "100000", "repricing_days": 365},
				{"book": "LIABILITY", "amount": "80000", "repricing_days": 180},
			],
			tier1_capital="500000",
		)
		self.assertIn("any_breach", suite)

	def test_irrbb_assessment_governance_and_contingency(self):
		sub = submit_irrbb_outlier_assessment(
			valuation_date="2026-04-01",
			points=[{"book": "ASSET", "amount": "100000", "repricing_days": 90}],
			tier1_capital="400000",
		)
		name = sub["name"]
		self._ensure_user("alm_checker_wave4@example.com")
		frappe.set_user("alm_checker_wave4@example.com")
		ap = approve_irrbb_outlier_assessment(name)
		frappe.set_user("Administrator")
		self.assertEqual(ap["workflow_status"], "APPROVED")

		pcode = f"PB-{frappe.generate_hash(length=6)}"
		frappe.get_doc(
			{
				"doctype": "ALM Contingency Playbook",
				"playbook_code": pcode,
				"title": "Liquidity stress",
				"trigger_thresholds_json": json.dumps({"lcr": {"min": 1.0}}),
				"response_steps_json": json.dumps([{"step": 1, "action": "notify_treasury"}]),
				"status": "ACTIVE",
			}
		).insert(ignore_permissions=True)
		ev = evaluate_contingency_triggers(pcode, json.dumps({"lcr": 0.95}))
		self.assertTrue(ev["breaches"])
