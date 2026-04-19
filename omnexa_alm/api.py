# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

from __future__ import annotations

from decimal import Decimal
import hashlib
import json

import frappe
from frappe.utils import nowdate

from .engine import (
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
from .standards_profile import get_standards_profile as _get_standards_profile


@frappe.whitelist()
def get_standards_profile() -> dict:
	"""Expose standards profile for governance dashboards and audits."""
	return _get_standards_profile()


@frappe.whitelist()
def evaluate_alm_profile(points: list[dict], bps_shift: int = 100, hqla: str = "0", stressed_net_outflow_30d: str = "1") -> dict:
	"""
	ALM baseline profile:
	- repricing gap buckets
	- NII sensitivity under parallel shift
	- LCR
	"""
	rows = [
		AssetLiabilityPoint(
			book=str(x.get("book")),
			amount=Decimal(str(x.get("amount"))),
			repricing_days=int(x.get("repricing_days")),
		)
		for x in (points or [])
	]
	gaps = calculate_gap_buckets(rows)
	nii_sensitivity = estimate_nii_sensitivity_parallel_shift(rows, int(bps_shift))
	eve_sensitivity = estimate_eve_sensitivity_parallel_shift(rows, int(bps_shift))
	lcr = liquidity_coverage_ratio(Decimal(str(hqla)), Decimal(str(stressed_net_outflow_30d)))
	return {
		"gaps": gaps,
		"cashflow_aggregation": aggregate_cashflows(rows),
		"nii_sensitivity": str(nii_sensitivity),
		"eve_sensitivity": str(eve_sensitivity),
		"lcr": str(lcr),
		"daily_reporting_ready": True,
	}


@frappe.whitelist()
def evaluate_liquidity_stress_ladder(inflows: list[dict], outflows: list[dict]) -> dict:
	ladder = build_liquidity_stress_ladder(inflows=inflows or [], outflows=outflows or [])
	return {
		"ladder": ladder,
		"cumulative_net": str(sum((Decimal(str(x["net"])) for x in ladder), Decimal("0"))),
	}


@frappe.whitelist()
def evaluate_nsfr(asf_components: list[dict], rsf_components: list[dict]) -> dict:
	asf = [
		NsfrComponent(
			category=str(x.get("category") or "ASF"),
			amount=Decimal(str(x.get("amount"))),
			factor=Decimal(str(x.get("factor"))),
		)
		for x in (asf_components or [])
	]
	rsf = [
		NsfrComponent(
			category=str(x.get("category") or "RSF"),
			amount=Decimal(str(x.get("amount"))),
			factor=Decimal(str(x.get("factor"))),
		)
		for x in (rsf_components or [])
	]
	return {"nsfr": str(net_stable_funding_ratio(asf, rsf))}


@frappe.whitelist()
def run_interest_rate_shock_scenarios(points: list[dict], shocks_bps: list[int] | None = None) -> dict:
	rows = [
		AssetLiabilityPoint(
			book=str(x.get("book")),
			amount=Decimal(str(x.get("amount"))),
			repricing_days=int(x.get("repricing_days")),
			rate_type=str(x.get("rate_type") or "FIXED"),
			entity=str(x.get("entity") or "DEFAULT"),
			currency=str(x.get("currency") or "USD"),
			product_code=str(x.get("product_code") or "GENERIC"),
		)
		for x in (points or [])
	]
	shocks = shocks_bps or [-200, -100, 100, 200]
	return {"shock_results": simulate_interest_rate_shocks(rows, shocks)}


@frappe.whitelist()
def evaluate_behavioral_assumptions(
	points: list[dict],
	nmd_sticky_ratio: str = "0.75",
	loan_prepayment_cpr: str = "0.05",
	term_deposit_early_withdrawal_rate: str = "0.08",
) -> dict:
	"""Apply NMD decay, loan CPR, and term-deposit early withdrawal to ALM points."""
	adj = apply_behavioral_cashflow_adjustments(
		points or [],
		nmd_sticky_ratio=Decimal(str(nmd_sticky_ratio)),
		loan_prepayment_cpr=Decimal(str(loan_prepayment_cpr)),
		term_deposit_early_withdrawal_rate=Decimal(str(term_deposit_early_withdrawal_rate)),
	)
	return {"adjusted_points": adj}


@frappe.whitelist()
def compute_ftp_margin_attribution(balances: list[dict], ftp_curve_json: str) -> dict:
	"""
	FTP curve JSON: [{"tenor_days": 0, "ftp_rate": "0.02"}, ...] annual decimal rates.
	Balances rows: amount, client_rate, tenor_days, label (optional).
	"""
	curve = json.loads(ftp_curve_json) if isinstance(ftp_curve_json, str) else ftp_curve_json
	pts = sorted(curve, key=lambda x: int(x.get("tenor_days", 0)))
	curve_tuples = [(int(x["tenor_days"]), Decimal(str(x["ftp_rate"]))) for x in pts]
	lines = margin_attribution_for_balances(balances or [], curve_tuples)
	total = sum((Decimal(str(x["margin_income_proxy"])) for x in lines), Decimal("0"))
	return {"lines": lines, "total_margin_income_proxy": str(total)}


@frappe.whitelist()
def ftp_rate_at_tenor(tenor_days: int, ftp_curve_json: str) -> dict:
	curve = json.loads(ftp_curve_json) if isinstance(ftp_curve_json, str) else ftp_curve_json
	pts = sorted(curve, key=lambda x: int(x.get("tenor_days", 0)))
	curve_tuples = [(int(x["tenor_days"]), Decimal(str(x["ftp_rate"]))) for x in pts]
	r = interpolate_ftp_rate(int(tenor_days), curve_tuples)
	return {"tenor_days": int(tenor_days), "ftp_rate": str(r)}


@frappe.whitelist()
def run_irrbb_standardized_outlier_suite_api(
	points: list[dict],
	tier1_capital: str,
	shocks_bps: str | None = None,
) -> dict:
	"""Parallel shock grid for standardized IRRBB outlier monitoring."""
	rows = [
		AssetLiabilityPoint(
			book=str(x.get("book")),
			amount=Decimal(str(x.get("amount"))),
			repricing_days=int(x.get("repricing_days")),
			rate_type=str(x.get("rate_type") or "FIXED"),
			entity=str(x.get("entity") or "DEFAULT"),
			currency=str(x.get("currency") or "USD"),
			product_code=str(x.get("product_code") or "GENERIC"),
		)
		for x in (points or [])
	]
	raw_shocks = json.loads(shocks_bps) if shocks_bps else None
	return irrbb_standardized_outlier_suite(rows, Decimal(str(tier1_capital)), shocks_bps=raw_shocks)


@frappe.whitelist()
def submit_irrbb_outlier_assessment(
	valuation_date: str,
	points: list[dict],
	tier1_capital: str,
	shocks_bps: str | None = None,
) -> dict:
	from frappe.utils import now_datetime

	suite = run_irrbb_standardized_outlier_suite_api(points=points, tier1_capital=tier1_capital, shocks_bps=shocks_bps)
	doc = frappe.get_doc(
		{
			"doctype": "ALM IRRBB Outlier Assessment",
			"valuation_date": valuation_date,
			"points_json": json.dumps(points or [], sort_keys=True, default=str),
			"tier1_capital": tier1_capital,
			"suite_results_json": json.dumps(suite, sort_keys=True, default=str),
			"workflow_status": "PENDING",
			"submitted_by": frappe.session.user,
			"submitted_on": now_datetime(),
		}
	)
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "suite": suite}


@frappe.whitelist()
def approve_irrbb_outlier_assessment(name: str) -> dict:
	from frappe.utils import now_datetime

	doc = frappe.get_doc("ALM IRRBB Outlier Assessment", name)
	if doc.workflow_status != "PENDING":
		frappe.throw(frappe._("Assessment is not pending approval"))
	if doc.submitted_by == frappe.session.user:
		frappe.throw(frappe._("Checker must differ from submitter"))
	doc.workflow_status = "APPROVED"
	doc.approved_by = frappe.session.user
	doc.approved_on = now_datetime()
	doc.save(ignore_permissions=True)
	return {"name": name, "workflow_status": doc.workflow_status}


@frappe.whitelist()
def evaluate_contingency_triggers(playbook_code: str, bank_metrics: str) -> dict:
	pb = frappe.get_doc("ALM Contingency Playbook", playbook_code)
	if pb.status != "ACTIVE":
		frappe.throw(frappe._("Playbook must be ACTIVE"))
	rules = json.loads(pb.trigger_thresholds_json or "{}")
	metrics = json.loads(bank_metrics) if isinstance(bank_metrics, str) else bank_metrics
	breaches: list[dict] = []
	for metric, spec in rules.items():
		val = float(metrics.get(metric, 0))
		if "min" in spec and val < float(spec["min"]):
			breaches.append({"metric": metric, "value": val, "breach": "below_min", "threshold": float(spec["min"])})
		if "max" in spec and val > float(spec["max"]):
			breaches.append({"metric": metric, "value": val, "breach": "above_max", "threshold": float(spec["max"])})
	responses = json.loads(pb.response_steps_json or "[]")
	return {"playbook": playbook_code, "breaches": breaches, "response_steps": responses}


@frappe.whitelist()
def evaluate_irrbb_outlier(points: list[dict], tier1_capital: str, bps_shift: int = 200) -> dict:
	rows = [
		AssetLiabilityPoint(
			book=str(x.get("book")),
			amount=Decimal(str(x.get("amount"))),
			repricing_days=int(x.get("repricing_days")),
			rate_type=str(x.get("rate_type") or "FIXED"),
			entity=str(x.get("entity") or "DEFAULT"),
			currency=str(x.get("currency") or "USD"),
			product_code=str(x.get("product_code") or "GENERIC"),
		)
		for x in (points or [])
	]
	return evaluate_basel_outlier_test(rows, tier1_capital=Decimal(str(tier1_capital)), bps_shift=int(bps_shift))


@frappe.whitelist()
def build_daily_alm_reporting_pack(
	points: list[dict],
	hqla: str,
	stressed_net_outflow_30d: str,
	asf_components: list[dict],
	rsf_components: list[dict],
	tier1_capital: str,
) -> dict:
	profile = evaluate_alm_profile(points=points, bps_shift=100, hqla=hqla, stressed_net_outflow_30d=stressed_net_outflow_30d)
	nsfr = evaluate_nsfr(asf_components=asf_components, rsf_components=rsf_components)
	irrbb = evaluate_irrbb_outlier(points=points, tier1_capital=tier1_capital, bps_shift=200)
	shocks = run_interest_rate_shock_scenarios(points=points, shocks_bps=[-200, -100, 100, 200])
	return {
		"profile": profile,
		"nsfr": nsfr.get("nsfr"),
		"irrbb_outlier": irrbb,
		"shock_results": shocks.get("shock_results", []),
		"regulatory_framework": "Basel III",
	}


@frappe.whitelist()
def aggregate_cashflows_from_finance_contracts(
	contract_rows: list[dict],
) -> dict:
	"""
	Integration hook for Finance Engine contract cashflows.
	Input rows expected: {book, amount, repricing_days, currency, product_code}
	"""
	points = [
		AssetLiabilityPoint(
			book=str(r.get("book")),
			amount=Decimal(str(r.get("amount"))),
			repricing_days=int(r.get("repricing_days")),
			rate_type=str(r.get("rate_type") or "FIXED"),
			entity=str(r.get("entity") or "DEFAULT"),
			currency=str(r.get("currency") or "USD"),
			product_code=str(r.get("product_code") or "GENERIC"),
		)
		for r in (contract_rows or [])
	]
	return {"cashflow_aggregation": aggregate_cashflows(points)}


@frappe.whitelist()
def persist_daily_alm_run(
	company: str,
	points: list[dict],
	hqla: str,
	stressed_net_outflow_30d: str,
	asf_components: list[dict],
	rsf_components: list[dict],
	tier1_capital: str,
	run_date: str | None = None,
) -> dict:
	pack = build_daily_alm_reporting_pack(
		points=points,
		hqla=hqla,
		stressed_net_outflow_30d=stressed_net_outflow_30d,
		asf_components=asf_components,
		rsf_components=rsf_components,
		tier1_capital=tier1_capital,
	)
	input_payload = {
		"points": points,
		"hqla": hqla,
		"stressed_net_outflow_30d": stressed_net_outflow_30d,
		"asf_components": asf_components,
		"rsf_components": rsf_components,
		"tier1_capital": tier1_capital,
	}
	input_hash = hashlib.sha256(json.dumps(input_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
	irrbb = pack.get("irrbb_outlier", {})
	doc = frappe.get_doc(
		{
			"doctype": "ALM Daily Run",
			"run_date": run_date or nowdate(),
			"company": company,
			"run_status": "SUCCESS",
			"input_hash": input_hash,
			"lcr": str(pack.get("profile", {}).get("lcr", 0)),
			"nsfr": str(pack.get("nsfr", 0)),
			"nii_sensitivity": str(pack.get("profile", {}).get("nii_sensitivity", 0)),
			"eve_sensitivity": str(pack.get("profile", {}).get("eve_sensitivity", 0)),
			"outlier_ratio": str(irrbb.get("outlier_ratio", 0)),
			"result_json": json.dumps(pack, sort_keys=True, default=str),
		}
	)
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "run_date": doc.run_date, "company": doc.company}


@frappe.whitelist()
def get_liquidity_risk_dashboard(as_of_date: str | None = None) -> dict:
	as_of_date = as_of_date or nowdate()
	rows = frappe.get_all(
		"ALM Daily Run",
		filters={"run_date": as_of_date},
		fields=["name", "company", "lcr", "nsfr", "outlier_ratio", "nii_sensitivity", "eve_sensitivity"],
		order_by="creation desc",
		limit_page_length=50,
	)
	return {
		"as_of_date": as_of_date,
		"runs": rows,
		"regulatory_thresholds": {"lcr_min": 1.0, "nsfr_min": 1.0, "irrbb_outlier_max": 0.15},
	}


@frappe.whitelist()
def submit_policy_version(policy_name: str, version: str, payload: str, effective_from: str | None = None) -> dict:
	import json
	from .governance import submit_policy_version as _submit
	obj = json.loads(payload) if isinstance(payload, str) else payload
	if not isinstance(obj, dict):
		frappe.throw(frappe._("payload must be a JSON object"))
	return _submit("omnexa_alm", policy_name=policy_name, version=version, payload=obj, effective_from=effective_from)


@frappe.whitelist()
def approve_policy_version(policy_name: str, version: str) -> dict:
	from .governance import approve_policy_version as _approve
	return _approve("omnexa_alm", policy_name=policy_name, version=version)


@frappe.whitelist()
def create_audit_snapshot(process_name: str, inputs: str, outputs: str, policy_ref: str | None = None) -> dict:
	import json
	from .governance import create_audit_snapshot as _snap
	in_obj = json.loads(inputs) if isinstance(inputs, str) else inputs
	out_obj = json.loads(outputs) if isinstance(outputs, str) else outputs
	if not isinstance(in_obj, dict) or not isinstance(out_obj, dict):
		frappe.throw(frappe._("inputs/outputs must be JSON objects"))
	return _snap("omnexa_alm", process_name=process_name, inputs=in_obj, outputs=out_obj, policy_ref=policy_ref)


@frappe.whitelist()
def get_governance_overview() -> dict:
	from .governance import governance_overview as _overview
	return _overview("omnexa_alm")


@frappe.whitelist()
def reject_policy_version(policy_name: str, version: str, reason: str = "") -> dict:
	from .governance import reject_policy_version as _reject
	return _reject("omnexa_alm", policy_name=policy_name, version=version, reason=reason)


@frappe.whitelist()
def list_policy_versions(policy_name: str | None = None) -> list[dict]:
	from .governance import list_policy_versions as _list
	return _list("omnexa_alm", policy_name=policy_name)


@frappe.whitelist()
def list_audit_snapshots(process_name: str | None = None, limit: int = 100) -> list[dict]:
	from .governance import list_audit_snapshots as _list
	return _list("omnexa_alm", process_name=process_name, limit=int(limit))


@frappe.whitelist()
def get_regulatory_dashboard() -> dict:
	"""Unified compliance dashboard payload for this app."""
	from .governance import governance_overview
	from .standards_profile import get_standards_profile
	std = get_standards_profile()
	gov = governance_overview("omnexa_alm")
	return {
		"app": "omnexa_alm",
		"standards": std.get("standards", []),
		"activity_controls": std.get("activity_controls", []),
		"governance": gov,
		"compliance_score": _compute_compliance_score(std=std, gov=gov),
	}


def _compute_compliance_score(std: dict, gov: dict) -> int:
	"""Simple normalized readiness score (0..100) for executive monitoring."""
	base = min(50, 5 * len(std.get("standards", [])))
	controls = min(30, 3 * len(std.get("activity_controls", [])))
	approved = int(gov.get("policies_approved", 0) or 0)
	pending = int(gov.get("policies_pending", 0) or 0)
	governance = min(20, approved * 2)
	if pending > 0:
		governance = max(0, governance - min(10, pending))
	return int(base + controls + governance)
