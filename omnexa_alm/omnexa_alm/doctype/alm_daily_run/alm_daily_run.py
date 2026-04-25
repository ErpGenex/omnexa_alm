# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AlmDailyRun(Document):
	def validate(self):
		self._validate_lifecycle_controls()

	def _validate_lifecycle_controls(self):
		if not self.input_hash:
			frappe.throw(_("Input Hash is mandatory for model run traceability."), title=_("Traceability"))
		if not self.run_reference:
			frappe.throw(_("Run Reference is mandatory for audit traceability."), title=_("Traceability"))
		if self.run_status == "SUCCESS":
			if not self.result_json:
				frappe.throw(_("Result JSON is mandatory for successful runs."), title=_("Result"))
			if self.lcr is not None and self.lcr < 0:
				frappe.throw(_("LCR cannot be negative."), title=_("Metrics"))
			if self.nsfr is not None and self.nsfr < 0:
				frappe.throw(_("NSFR cannot be negative."), title=_("Metrics"))


class ALMDailyRun(AlmDailyRun):
	pass

