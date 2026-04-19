from frappe.tests.utils import FrappeTestCase

from omnexa_alm.api import get_regulatory_dashboard


class TestAlmRegulatoryDashboard(FrappeTestCase):
	def test_get_regulatory_dashboard(self):
		out = get_regulatory_dashboard()
		self.assertEqual(out["app"], "omnexa_alm")
		self.assertIn("standards", out)
		self.assertIn("governance", out)
		self.assertIn("compliance_score", out)
		self.assertGreaterEqual(out["compliance_score"], 0)
