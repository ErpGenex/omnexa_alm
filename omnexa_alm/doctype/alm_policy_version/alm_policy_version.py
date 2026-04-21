import frappe
from frappe import _
from frappe.model.document import Document


class AlmPolicyVersion(Document):
	def validate(self):
		self._validate_lifecycle_controls()

	def _validate_lifecycle_controls(self):
		if self.status in {"PENDING_APPROVAL", "APPROVED", "REJECTED"} and not self.maker:
			frappe.throw(_("Maker is mandatory once policy leaves draft state."), title=_("Governance"))
		if self.status in {"PENDING_APPROVAL", "APPROVED"} and not self.checker:
			frappe.throw(_("Checker is mandatory for approval workflow."), title=_("Governance"))
		if self.status == "APPROVED":
			if not self.approved_at:
				frappe.throw(_("Approved At is mandatory when status is APPROVED."), title=_("Governance"))
			if not self.effective_from:
				frappe.throw(_("Effective From is mandatory when policy is APPROVED."), title=_("Policy"))
		if self.status == "REJECTED":
			if not self.rejector:
				frappe.throw(_("Rejector is mandatory when status is REJECTED."), title=_("Governance"))
			if not self.rejection_reason:
				frappe.throw(_("Rejection Reason is mandatory when policy is REJECTED."), title=_("Governance"))
		if not self.policy_reference:
			frappe.throw(_("Policy Reference is mandatory."), title=_("Governance"))


class ALMPolicyVersion(AlmPolicyVersion):
	pass
