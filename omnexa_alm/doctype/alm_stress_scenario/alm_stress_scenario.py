# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AlmStressScenario(Document):
	def validate(self):
		self._validate_lifecycle_controls()

	def _validate_lifecycle_controls(self):
		if self.liquidity_outflow_multiplier is not None and float(self.liquidity_outflow_multiplier) <= 0:
			frappe.throw(_("Liquidity Outflow Multiplier must be greater than zero."), title=_("Scenario"))
		if self.status in {"ACTIVE", "RETIRED"} and not self.scenario_owner:
			frappe.throw(_("Scenario Owner is mandatory for active/retired scenarios."), title=_("Governance"))
		if self.status == "RETIRED" and not self.description:
			frappe.throw(_("Description is mandatory when retiring a stress scenario."), title=_("Governance"))


class ALMStressScenario(AlmStressScenario):
	pass

