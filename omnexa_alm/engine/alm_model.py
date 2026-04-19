# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class AssetLiabilityPoint:
	book: str  # ASSET | LIABILITY
	amount: Decimal
	repricing_days: int
	rate_type: str = "FIXED"  # FIXED | FLOATING
	entity: str = "DEFAULT"
	currency: str = "USD"
	product_code: str = "GENERIC"


@dataclass(frozen=True)
class GapBucket:
	name: str
	from_day: int
	to_day: int


DEFAULT_BUCKETS = [
	GapBucket("0-30", 0, 30),
	GapBucket("31-90", 31, 90),
	GapBucket("91-180", 91, 180),
	GapBucket("181-365", 181, 365),
	GapBucket("366+", 366, 10_000),
]


@dataclass(frozen=True)
class NsfrComponent:
	category: str
	amount: Decimal
	factor: Decimal  # 0..1


def calculate_gap_buckets(points: list[AssetLiabilityPoint], buckets: list[GapBucket] | None = None) -> list[dict]:
	"""Classic ALM gap profile by repricing buckets."""
	if not points:
		return []
	bk = buckets or DEFAULT_BUCKETS
	out: list[dict] = []
	for b in bk:
		assets = Decimal("0")
		liabs = Decimal("0")
		for p in points:
			if b.from_day <= p.repricing_days <= b.to_day:
				if p.book == "ASSET":
					assets += p.amount
				elif p.book == "LIABILITY":
					liabs += p.amount
				else:
					raise ValueError(f"Unknown book type: {p.book}")
		out.append(
			{
				"bucket": b.name,
				"asset_repricing": str(assets),
				"liability_repricing": str(liabs),
				"gap": str(assets - liabs),
			}
		)
	return out


def aggregate_cashflows(points: list[AssetLiabilityPoint], buckets: list[GapBucket] | None = None) -> list[dict]:
	"""Aggregate projected repricing cashflows by time bucket for daily ALM."""
	bk = buckets or DEFAULT_BUCKETS
	out: list[dict] = []
	for b in bk:
		bucket_assets = Decimal("0")
		bucket_liabilities = Decimal("0")
		for p in points:
			if b.from_day <= p.repricing_days <= b.to_day:
				if p.book == "ASSET":
					bucket_assets += p.amount
				elif p.book == "LIABILITY":
					bucket_liabilities += p.amount
		out.append(
			{
				"bucket": b.name,
				"projected_asset_cashflow": str(bucket_assets),
				"projected_liability_cashflow": str(bucket_liabilities),
				"net_cashflow": str(bucket_assets - bucket_liabilities),
			}
		)
	return out


def estimate_nii_sensitivity_parallel_shift(points: list[AssetLiabilityPoint], bps_shift: int) -> Decimal:
	"""
	Approximate one-year NII sensitivity under parallel rate shift.
	Simplified baseline: sum(gap * shift_rate * tenor_weight).
	"""
	shift = Decimal(bps_shift) / Decimal("10000")
	gap_rows = calculate_gap_buckets(points)
	total = Decimal("0")
	for r in gap_rows:
		bucket = r["bucket"]
		gap = Decimal(r["gap"])
		weight = _bucket_weight(bucket)
		total += gap * shift * weight
	return total


def simulate_interest_rate_shocks(points: list[AssetLiabilityPoint], shocks_bps: list[int]) -> list[dict]:
	"""Run NII/EVE sensitivities for multiple Basel shock scenarios."""
	out = []
	for shock in shocks_bps:
		out.append(
			{
				"shock_bps": int(shock),
				"nii_sensitivity": str(estimate_nii_sensitivity_parallel_shift(points, int(shock))),
				"eve_sensitivity": str(estimate_eve_sensitivity_parallel_shift(points, int(shock))),
			}
		)
	return out


def liquidity_coverage_ratio(hqla: Decimal, stressed_net_outflow_30d: Decimal) -> Decimal:
	if stressed_net_outflow_30d <= 0:
		raise ValueError("stressed_net_outflow_30d must be > 0")
	return hqla / stressed_net_outflow_30d


def net_stable_funding_ratio(asf_components: list[NsfrComponent], rsf_components: list[NsfrComponent]) -> Decimal:
	"""Basel III NSFR = Available Stable Funding / Required Stable Funding."""
	asf = sum((c.amount * c.factor for c in asf_components), Decimal("0"))
	rsf = sum((c.amount * c.factor for c in rsf_components), Decimal("0"))
	if rsf <= 0:
		raise ValueError("Required Stable Funding must be > 0")
	return asf / rsf


def estimate_eve_sensitivity_parallel_shift(points: list[AssetLiabilityPoint], bps_shift: int) -> Decimal:
	"""
	Baseline EVE delta under parallel shift using simple repricing-duration proxy.
	Assets lose value when rates rise; liabilities gain value.
	"""
	shift = Decimal(bps_shift) / Decimal("10000")
	total = Decimal("0")
	for p in points:
		duration_proxy = Decimal(max(1, p.repricing_days)) / Decimal("365")
		sign = Decimal("-1") if p.book == "ASSET" else Decimal("1")
		total += sign * p.amount * shift * duration_proxy
	return total


def build_liquidity_stress_ladder(
	inflows: list[dict],
	outflows: list[dict],
	buckets: list[GapBucket] | None = None,
) -> list[dict]:
	"""
	Simple liquidity stress ladder by maturity bucket.
	Input rows: {"amount": "...", "day": int}
	"""
	bk = buckets or DEFAULT_BUCKETS
	out: list[dict] = []
	for b in bk:
		bucket_in = sum(
			Decimal(str(x.get("amount", "0")))
			for x in (inflows or [])
			if b.from_day <= int(x.get("day", 0)) <= b.to_day
		)
		bucket_out = sum(
			Decimal(str(x.get("amount", "0")))
			for x in (outflows or [])
			if b.from_day <= int(x.get("day", 0)) <= b.to_day
		)
		out.append(
			{
				"bucket": b.name,
				"inflows": str(bucket_in),
				"outflows": str(bucket_out),
				"net": str(bucket_in - bucket_out),
			}
		)
	return out


def interpolate_ftp_rate(tenor_days: int, curve_points: list[tuple[int, Decimal]]) -> Decimal:
	"""
	Piecewise-linear FTP rate (annual, decimal) by tenor in days.
	`curve_points` sorted by tenor ascending: [(0, r0), (30, r1), ...]
	"""
	if not curve_points:
		raise ValueError("curve_points required")
	td = int(tenor_days)
	if td <= curve_points[0][0]:
		return curve_points[0][1]
	if td >= curve_points[-1][0]:
		return curve_points[-1][1]
	for i in range(len(curve_points) - 1):
		d0, r0 = curve_points[i]
		d1, r1 = curve_points[i + 1]
		if d0 <= td <= d1:
			if d1 == d0:
				return r0
			w = (Decimal(td) - Decimal(d0)) / (Decimal(d1) - Decimal(d0))
			return r0 + w * (r1 - r0)
	return curve_points[-1][1]


def margin_attribution_for_balances(
	rows: list[dict],
	curve_points: list[tuple[int, Decimal]],
) -> list[dict]:
	"""
	Each row: amount, client_rate (annual decimal), tenor_days, book (optional label).
	Returns per-row ftp_rate, margin_spread, margin_income_proxy (amount * spread).
	"""
	out: list[dict] = []
	for r in rows:
		amt = Decimal(str(r.get("amount", "0")))
		client = Decimal(str(r.get("client_rate", "0")))
		tenor = int(r.get("tenor_days", 0))
		ftp = interpolate_ftp_rate(tenor, curve_points)
		spread = client - ftp
		out.append(
			{
				"label": str(r.get("label") or ""),
				"amount": str(amt),
				"tenor_days": tenor,
				"client_rate": str(client),
				"ftp_rate": str(ftp),
				"margin_spread": str(spread),
				"margin_income_proxy": str(amt * spread),
			}
		)
	return out


def apply_behavioral_cashflow_adjustments(
	points: list[dict],
	*,
	nmd_sticky_ratio: Decimal,
	loan_prepayment_cpr: Decimal,
	term_deposit_early_withdrawal_rate: Decimal,
) -> list[dict]:
	"""
	Adjust effective repricing balances for behavioral runoff:
	- NMD (non-maturity deposits): treat sticky core only as long-dated; shrink balance by (1-sticky) toward overnight.
	- LOAN assets: reduce outstanding by CPR (annualized simple factor for ALM bucket).
	- TERM_DEPOSIT liabilities: apply early withdrawal haircut to balance.
	Other instruments pass through with multiplier 1.
	Each point may include instrument_type: NMD | LOAN | TERM_DEPOSIT | OTHER
	"""
	out: list[dict] = []
	for p in points:
		row = dict(p)
		it = str(p.get("instrument_type") or "OTHER").upper()
		amt = Decimal(str(p.get("amount", "0")))
		rd = int(p.get("repricing_days", 0))
		mult = Decimal("1")
		note = "none"
		if it == "NMD":
			mult = nmd_sticky_ratio
			row["repricing_days"] = rd if mult >= Decimal("0.99") else min(rd, 30)
			note = "nmd_sticky"
		elif it == "LOAN":
			mult = Decimal("1") - loan_prepayment_cpr
			note = "loan_cpr"
		elif it == "TERM_DEPOSIT":
			mult = Decimal("1") - term_deposit_early_withdrawal_rate
			note = "td_ew"
		adj = (amt * mult).quantize(Decimal("0.01"))
		row["amount"] = str(adj)
		row["behavioral_adjustment"] = note
		row["behavioral_multiplier"] = str(mult)
		out.append(row)
	return out


def irrbb_standardized_outlier_suite(
	points: list[AssetLiabilityPoint],
	tier1_capital: Decimal,
	shocks_bps: list[int] | None = None,
) -> dict:
	"""
	Basel-style parallel shock grid for IRRBB outlier monitoring (simplified to EVE/tier1 ratio per shock).
	"""
	shocks = shocks_bps or [-200, -100, 100, 200]
	scenarios: list[dict] = []
	worst_ratio = Decimal("0")
	worst_bps = shocks[0]
	any_breach = False
	for bps in shocks:
		r = evaluate_basel_outlier_test(points, tier1_capital, bps_shift=int(bps))
		ratio = Decimal(str(r["outlier_ratio"]))
		scenarios.append({"shock_bps": int(bps), **r})
		if ratio > worst_ratio:
			worst_ratio = ratio
			worst_bps = int(bps)
		if r.get("breach"):
			any_breach = True
	return {
		"scenarios": scenarios,
		"worst_outlier_ratio": str(worst_ratio),
		"worst_shock_bps": worst_bps,
		"any_breach": any_breach,
	}


def evaluate_basel_outlier_test(points: list[AssetLiabilityPoint], tier1_capital: Decimal, bps_shift: int = 200) -> dict:
	"""
	Simplified IRRBB outlier-style metric:
	|EVE sensitivity| / Tier1 Capital.
	"""
	if tier1_capital <= 0:
		raise ValueError("tier1_capital must be > 0")
	eve = estimate_eve_sensitivity_parallel_shift(points, bps_shift)
	ratio = abs(eve) / tier1_capital
	return {
		"eve_sensitivity": str(eve),
		"tier1_capital": str(tier1_capital),
		"outlier_ratio": str(ratio),
		"breach": ratio > Decimal("0.15"),
	}


def _bucket_weight(bucket_name: str) -> Decimal:
	# crude duration proxy for baseline sensitivity.
	if bucket_name == "0-30":
		return Decimal("0.08")
	if bucket_name == "31-90":
		return Decimal("0.25")
	if bucket_name == "91-180":
		return Decimal("0.50")
	if bucket_name == "181-365":
		return Decimal("0.90")
	return Decimal("1.30")

