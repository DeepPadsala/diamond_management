from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DiamondPacketIssueWizard(models.TransientModel):
    """Unified issue wizard for one-or-many packets.

    Picks the destination (process + party/employee + dates), then creates
    the matching transaction document (``diamond.process.issue``,
    ``diamond.factory.issue``, ``diamond.jobwork.issue`` or
    ``diamond.hpht.issue``) with one line per packet and *confirms* it.
    Confirming the doc is what actually moves the packet state and writes
    the audit-log row — so we get a single, consistent flow whether the
    user issues from the packet form, from a multi-select on the list,
    or from the transaction screen directly.
    """

    _name = "diamond.packet.issue.wizard"
    _description = "Issue Packet(s) Wizard"

    mode = fields.Selection(
        selection=[
            ("process", "Process Issue"),
            ("factory", "Factory Issue"),
            ("jobwork", "Jobwork Issue"),
            ("hpht",    "HPHT Issue"),
        ],
        string="Issue Type",
        required=True,
        default="process",
    )

    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )
    date = fields.Datetime(string="Issue Date", default=fields.Datetime.now, required=True)

    packet_ids = fields.Many2many(
        "diamond.packet", string="Packets", required=True,
    )

    process_id = fields.Many2one(
        "diamond.process", string="Process", required=True,
        help="Which process is this issue for? (e.g. Cutting, Polishing, HPHT, Repair).",
    )

    # Destination — required-ness is mode-driven (see view).
    ledger_id = fields.Many2one(
        "diamond.ledger", string="Party / Vendor",
        domain="ledger_domain",
        help="For Jobwork: pick the jobworker. For HPHT: pick the HPHT vendor. Optional for Process.",
    )
    employee_id = fields.Many2one(
        "diamond.employee", string="Employee",
        help="For Factory: required. For other modes: optional.",
    )
    employee_domain = fields.Char(
        compute="_compute_employee_domain",
        help="Internal — drives employee domain in the view.",
    )
    expected_return_date = fields.Date(string="Expected Return")
    note = fields.Text(string="Note")

    # ── computed domain so ledger_id only shows the right party type ──
    ledger_domain = fields.Char(
        compute="_compute_ledger_domain",
        help="Internal — drives the ledger domain in the view.",
    )

    # ── derived helpers for the view ──
    is_party_required = fields.Boolean(compute="_compute_flags")
    is_employee_required = fields.Boolean(compute="_compute_flags")
    show_party = fields.Boolean(compute="_compute_flags")
    show_expected_return = fields.Boolean(compute="_compute_flags")

    # Improvement-return polish employee mismatch warning
    show_employee_warning = fields.Boolean(default=False)
    employee_warning_message = fields.Text(readonly=True)

    # ── summary ──
    packet_count = fields.Integer(compute="_compute_summary")
    total_pcs = fields.Integer(compute="_compute_summary")
    total_cts = fields.Float(compute="_compute_summary", digits=(12, 4))

    # ─────────────────────── Computes ───────────────────────
    @api.depends("mode")
    def _compute_ledger_domain(self):
        for rec in self:
            if rec.mode == "jobwork":
                rec.ledger_domain = "[('party_type', '=', 'jobworker')]"
            elif rec.mode == "hpht":
                rec.ledger_domain = "[('party_type', '=', 'hpht_vendor')]"
            else:
                rec.ledger_domain = "[]"

    @api.depends("process_id")
    def _compute_employee_domain(self):
        Employee = self.env["diamond.employee"]
        for rec in self:
            if rec.process_id:
                rec.employee_domain = str(Employee.domain_for_process(rec.process_id))
            else:
                rec.employee_domain = "[]"

    @api.depends("mode")
    def _compute_flags(self):
        for rec in self:
            rec.show_party = rec.mode in ("jobwork", "hpht")
            rec.is_party_required = rec.show_party
            rec.is_employee_required = rec.mode == "factory"
            rec.show_expected_return = rec.show_party

    @api.depends("packet_ids")
    def _compute_summary(self):
        for rec in self:
            rec.packet_count = len(rec.packet_ids)
            rec.total_pcs = sum(rec.packet_ids.mapped("rdy_pcs"))
            rec.total_cts = sum(rec.packet_ids.mapped("rdy_cts"))

    # ─────────────────────── Onchange / defaults ───────────────────────
    @api.onchange("mode")
    def _onchange_mode(self):
        """Reset incompatible fields when mode changes."""
        if self.mode == "jobwork":
            if self.ledger_id and self.ledger_id.party_type != "jobworker":
                self.ledger_id = False
        elif self.mode == "hpht":
            if self.ledger_id and self.ledger_id.party_type != "hpht_vendor":
                self.ledger_id = False
        else:
            self.ledger_id = False
            self.expected_return_date = False

    @api.onchange("process_id")
    def _onchange_process_id(self):
        if self.employee_id and self.process_id:
            if not self.env["diamond.employee"].check_capable_for_process(
                self.employee_id, self.process_id,
            ):
                self.employee_id = False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context or {}
        active_model = ctx.get("active_model")
        active_ids = ctx.get("active_ids") or ([ctx["active_id"]] if ctx.get("active_id") else [])
        if active_model == "diamond.packet" and active_ids:
            packets = self.env["diamond.packet"].browse(active_ids)
            res["packet_ids"] = [(6, 0, active_ids)]
            if packets:
                res["company_id"] = packets[0].company_id.id
        if ctx.get("default_issue_mode"):
            res["mode"] = ctx["default_issue_mode"]
        if active_model == "diamond.packet" and active_ids:
            packets = self.env["diamond.packet"].browse(active_ids)
            improvement_packets = packets.filtered("improvement_return")
            if improvement_packets:
                polish_process = self.env["diamond.packet"]._get_polish_process()
                if polish_process:
                    res.setdefault("process_id", polish_process.id)
                polish_employees = improvement_packets.mapped("improvement_polish_employee_id")
                if len(polish_employees) == 1 and polish_employees:
                    res.setdefault("employee_id", polish_employees.id)
        return res

    # ─────────────────────── Validation ───────────────────────
    def _validate(self):
        self.ensure_one()
        if not self.packet_ids:
            raise UserError(_("Select at least one packet to issue."))
        bad = self.packet_ids.filtered(lambda p: p.state in ("outward", "closed"))
        if bad:
            raise UserError(_(
                "These packets cannot be issued (already outward / closed): %s"
            ) % ", ".join(bad.mapped("packet_no")))
        wrong_co = self.packet_ids.filtered(lambda p: p.company_id.id != self.company_id.id)
        if wrong_co:
            raise UserError(_(
                "Selected packets belong to a different company than the one chosen on the wizard."
            ))
        if self.is_party_required and not self.ledger_id:
            raise UserError(_("Pick the %s for this issue.") % (
                "Jobworker" if self.mode == "jobwork" else "HPHT Vendor"))
        if self.is_employee_required and not self.employee_id:
            raise UserError(_("Pick the Employee for a Factory Issue."))
        if not self.process_id:
            raise UserError(_("Pick a Process."))
        if self.employee_id and not self.env["diamond.employee"].check_capable_for_process(
            self.employee_id, self.process_id,
        ):
            raise UserError(_(
                "Employee %(employee)s is not assigned to process %(process)s."
            ) % {
                "employee": self.employee_id.display_name,
                "process": self.process_id.display_name,
            })
        if self.mode == "jobwork" and self.ledger_id and self.ledger_id.party_type != "jobworker":
            raise UserError(_("Selected party is not flagged as a Jobworker."))
        if self.mode == "hpht" and self.ledger_id and self.ledger_id.party_type != "hpht_vendor":
            raise UserError(_("Selected party is not flagged as an HPHT Vendor."))

    def _is_polish_process(self):
        self.ensure_one()
        if not self.process_id:
            return False
        return self.process_id.code == "POL"

    def _improvement_employee_mismatch(self):
        """Return improvement packets whose polish worker differs from selection."""
        self.ensure_one()
        if self.mode != "factory" or not self._is_polish_process() or not self.employee_id:
            return self.env["diamond.packet"]
        return self.packet_ids.filtered(
            lambda p: (
                p.improvement_return
                and p.improvement_polish_employee_id
                and p.improvement_polish_employee_id != self.employee_id
            )
        )

    def _build_employee_warning_message(self, mismatched_packets):
        self.ensure_one()
        lines = [
            _("This packet was returned for improvement and was previously polished by another worker."),
            "",
        ]
        for packet in mismatched_packets:
            lines.append(_(
                "• %(packet)s — expected: %(expected)s, selected: %(selected)s"
            ) % {
                "packet": packet.packet_no,
                "expected": packet.improvement_polish_employee_id.display_name,
                "selected": self.employee_id.display_name,
            })
        lines.extend([
            "",
            _("Continue with the selected employee, or go back to change the selection."),
        ])
        return "\n".join(lines)

    def action_back_from_warning(self):
        """Return to the issue form to change employee."""
        self.ensure_one()
        self.write({
            "show_employee_warning": False,
            "employee_warning_message": False,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Issue Packet(s)"),
            "res_model": "diamond.packet.issue.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_confirm_mismatch(self):
        """User accepted issuing to a different polish worker."""
        self.ensure_one()
        return self.with_context(skip_improvement_employee_warning=True).action_issue()

    # ─────────────────────── Confirm ───────────────────────
    _MODE_TO_DOC = {
        "process": ("diamond.process.issue", "diamond.process.issue.line"),
        "factory": ("diamond.factory.issue", "diamond.factory.issue.line"),
        "jobwork": ("diamond.jobwork.issue", "diamond.jobwork.issue.line"),
        "hpht":    ("diamond.hpht.issue",    "diamond.hpht.issue.line"),
    }

    def action_issue(self):
        """Create + confirm the matching issue document, then open it."""
        self.ensure_one()
        self._validate()

        if (
            not self.env.context.get("skip_improvement_employee_warning")
            and not self.show_employee_warning
        ):
            mismatched = self._improvement_employee_mismatch()
            if mismatched:
                self.write({
                    "show_employee_warning": True,
                    "employee_warning_message": self._build_employee_warning_message(mismatched),
                })
                return {
                    "type": "ir.actions.act_window",
                    "name": _("Issue Packet(s)"),
                    "res_model": "diamond.packet.issue.wizard",
                    "res_id": self.id,
                    "view_mode": "form",
                    "target": "new",
                }

        doc_model, _line_model = self._MODE_TO_DOC[self.mode]
        Doc = self.env[doc_model]

        vals = {
            "company_id": self.company_id.id,
            "date": self.date,
            "process_id": self.process_id.id,
            "ledger_id": self.ledger_id.id or False,
            "employee_id": self.employee_id.id or False,
            "note": self.note or "",
            "line_ids": [
                (0, 0, {
                    "packet_id": p.id,
                    "pcs": p.rdy_pcs or 1,
                    "cts": p.rdy_cts or 0.0,
                })
                for p in self.packet_ids
            ],
        }
        if self.mode in ("jobwork", "hpht") and self.expected_return_date:
            vals["expected_return_date"] = self.expected_return_date

        doc = Doc.with_company(self.company_id).create(vals)
        return doc.action_confirm()
