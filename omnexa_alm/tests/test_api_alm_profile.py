from frappe.tests.utils import FrappeTestCase

from omnexa_alm.api import evaluate_alm_profile


class TestAlmApi(FrappeTestCase):
	def test_evaluate_alm_profile(self):
		out = evaluate_alm_profile(
			points=[
				{"book": "ASSET", "amount": "100000", "repricing_days": 20},
				{"book": "LIABILITY", "amount": "70000", "repricing_days": 20},
			],
			bps_shift=100,
			hqla="150",
			stressed_net_outflow_30d="100",
		)
		self.assertIn("gaps", out)
		self.assertIn("nii_sensitivity", out)
		self.assertIn("lcr", out)

