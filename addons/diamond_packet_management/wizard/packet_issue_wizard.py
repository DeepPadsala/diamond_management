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
        if self.mode == "jobwork" and self.ledger_id and self.ledger_id.party_type != "jobworker":
            raise UserError(_("Selected party is not flagged as a Jobworker."))
        if self.mode == "hpht" and self.ledger_id and self.ledger_id.party_type != "hpht_vendor":
            raise UserError(_("Selected party is not flagged as an HPHT Vendor."))

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
