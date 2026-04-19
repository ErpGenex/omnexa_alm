from frappe.tests.utils import FrappeTestCase

from omnexa_alm.api import (
	build_daily_alm_reporting_pack,
	evaluate_nsfr,
	run_interest_rate_shock_scenarios,
)


class TestAlmAdvancedApi(FrappeTestCase):
	def test_nsfr_and_shock_api(self):
		nsfr = evaluate_nsfr(
			asf_components=[
				{"category": "capital", "amount": "200000", "factor": "1.0"},
			],
			rsf_components=[
				{"category": "loans", "amount": "150000", "factor": "0.85"},
			],
		)
		self.assertIn("nsfr", nsfr)

		shocks = run_interest_rate_shock_scenarios(
			points=[
				{"book": "ASSET", "amount": "100000", "repricing_days": 30},
				{"book": "LIABILITY", "amount": "80000", "repricing_days": 30},
			],
			shocks_bps=[-100, 100, 200],
		)
		self.assertEqual(len(shocks["shock_results"]), 3)

	def test_daily_reporting_pack(self):
		pack = build_daily_alm_reporting_pack(
			points=[
				{"book": "ASSET", "amount": "200000", "repricing_days": 30},
				{"book": "LIABILITY", "amount": "150000", "repricing_days": 30},
			],
			hqla="120000",
			stressed_net_outflow_30d="100000",
			asf_components=[{"category": "capital", "amount": "200000", "factor": "1.0"}],
			rsf_components=[{"category": "assets", "amount": "150000", "factor": "0.85"}],
			tier1_capital="400000",
		)
		self.assertIn("profile", pack)
		self.assertIn("nsfr", pack)
		self.assertIn("irrbb_outlier", pack)

