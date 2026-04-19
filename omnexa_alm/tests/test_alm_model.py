from decimal import Decimal

from frappe.tests.utils import FrappeTestCase

from omnexa_alm.engine import (
	AssetLiabilityPoint,
	NsfrComponent,
	aggregate_cashflows,
	apply_behavioral_cashflow_adjustments,
	build_liquidity_stress_ladder,
	calculate_gap_buckets,
	evaluate_basel_outlier_test,
	estimate_eve_sensitivity_parallel_shift,
	estimate_nii_sensitivity_parallel_shift,
	interpolate_ftp_rate,
	irrbb_standardized_outlier_suite,
	liquidity_coverage_ratio,
	margin_attribution_for_balances,
	net_stable_funding_ratio,
	simulate_interest_rate_shocks,
)


class TestAlmModel(FrappeTestCase):
	def test_gap_buckets_and_sensitivity(self):
		points = [
			AssetLiabilityPoint("ASSET", Decimal("100000"), 20),
			AssetLiabilityPoint("LIABILITY", Decimal("70000"), 20),
			AssetLiabilityPoint("ASSET", Decimal("50000"), 120),
		]
		gaps = calculate_gap_buckets(points)
		self.assertTrue(gaps)
		nii = estimate_nii_sensitivity_parallel_shift(points, 100)
		self.assertGreater(nii, Decimal("0"))

	def test_lcr(self):
		lcr = liquidity_coverage_ratio(Decimal("150"), Decimal("100"))
		self.assertEqual(lcr, Decimal("1.5"))

	def test_eve_sensitivity_and_stress_ladder(self):
		points = [
			AssetLiabilityPoint("ASSET", Decimal("100000"), 365),
			AssetLiabilityPoint("LIABILITY", Decimal("50000"), 365),
		]
		eve = estimate_eve_sensitivity_parallel_shift(points, 100)
		self.assertLess(eve, Decimal("0"))

		ladder = build_liquidity_stress_ladder(
			inflows=[{"amount": "70000", "day": 20}],
			outflows=[{"amount": "50000", "day": 20}],
		)
		self.assertTrue(ladder)
		self.assertEqual(Decimal(ladder[0]["net"]), Decimal("20000"))

	def test_nsfr_shocks_and_outlier(self):
		points = [
			AssetLiabilityPoint("ASSET", Decimal("200000"), 365),
			AssetLiabilityPoint("LIABILITY", Decimal("150000"), 180),
		]
		nsfr = net_stable_funding_ratio(
			[NsfrComponent("capital", Decimal("180000"), Decimal("1.0"))],
			[NsfrComponent("assets", Decimal("150000"), Decimal("0.85"))],
		)
		self.assertGreater(nsfr, Decimal("1"))

		shocks = simulate_interest_rate_shocks(points, [-100, 100, 200])
		self.assertEqual(len(shocks), 3)
		self.assertIn("nii_sensitivity", shocks[0])

		outlier = evaluate_basel_outlier_test(points, tier1_capital=Decimal("500000"), bps_shift=200)
		self.assertIn("outlier_ratio", outlier)
		self.assertIn("breach", outlier)

	def test_cashflow_aggregation(self):
		points = [
			AssetLiabilityPoint("ASSET", Decimal("90000"), 20),
			AssetLiabilityPoint("LIABILITY", Decimal("60000"), 20),
		]
		rows = aggregate_cashflows(points)
		self.assertTrue(rows)
		self.assertEqual(Decimal(rows[0]["net_cashflow"]), Decimal("30000"))

	def test_ftp_interpolation_and_margin(self):
		curve = [(0, Decimal("0.01")), (180, Decimal("0.03")), (365, Decimal("0.04"))]
		r = interpolate_ftp_rate(90, curve)
		self.assertGreater(r, Decimal("0.01"))
		lines = margin_attribution_for_balances(
			[{"amount": "100000", "client_rate": "0.06", "tenor_days": 180, "label": "loan"}],
			curve,
		)
		self.assertEqual(len(lines), 1)
		self.assertIn("margin_spread", lines[0])

	def test_behavioral_adjustments(self):
		raw = [
			{"book": "LIABILITY", "amount": "200000", "repricing_days": 365, "instrument_type": "NMD"},
			{"book": "ASSET", "amount": "100000", "repricing_days": 180, "instrument_type": "LOAN"},
		]
		out = apply_behavioral_cashflow_adjustments(
			raw,
			nmd_sticky_ratio=Decimal("0.8"),
			loan_prepayment_cpr=Decimal("0.1"),
			term_deposit_early_withdrawal_rate=Decimal("0"),
		)
		self.assertEqual(len(out), 2)
		self.assertLess(Decimal(out[0]["amount"]), Decimal("200000"))

	def test_irrbb_standardized_suite(self):
		points = [
			AssetLiabilityPoint("ASSET", Decimal("300000"), 365),
			AssetLiabilityPoint("LIABILITY", Decimal("200000"), 180),
		]
		suite = irrbb_standardized_outlier_suite(points, Decimal("1000000"))
		self.assertIn("scenarios", suite)
		self.assertGreaterEqual(len(suite["scenarios"]), 4)

