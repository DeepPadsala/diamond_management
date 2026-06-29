import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DiamondPacket(models.Model):
    """The diamond packet — one physical lot or stone tracked end-to-end.

    Lifecycle:
        draft → in_stock → in_process → in_jobwork → in_factory →
        in_hpht → ready → outward → closed.

    All movements are recorded both via the ``state`` machine *and* via
    ``diamond.packet.history`` (immutable audit trail).
    """

    _name = "diamond.packet"
    _description = "Diamond Packet"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _rec_name = "packet_no"

    # ───────────────────────── Identity ─────────────────────────
    packet_no = fields.Char(
        string="Sequence No.",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
        index=True,
        help="Auto-generated internal packet number.",
    )
    barcode = fields.Char(
        string="Barcode",
        required=True,
        copy=False,
        index=True,
        help="Scanned by barcode gun. Auto-generated as companycode-partycode-number if left blank.",
    )
    kapan_no = fields.Char(string="Kapan No.", help="Rough source / kapan reference (e.g. K-330, K-326).")
    party_barcode = fields.Char(string="Party Barcode")
    lot_ref = fields.Char(string="Lot Reference")

    # ───────────────────────── Multi-company ─────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )

    # ───────────────────────── Master links ─────────────────────────
    product_id = fields.Many2one("diamond.product", string="Product")
    shape_id = fields.Many2one("diamond.shape", string="Shape", required=True, tracking=True)
    color_id = fields.Many2one("diamond.color", string="Color", required=True, tracking=True)
    clarity_id = fields.Many2one("diamond.clarity", string="Clarity", required=True, tracking=True)
    cut_id = fields.Many2one("diamond.cut", string="Cut")
    polish_id = fields.Many2one("diamond.polish", string="Polish")
    symmetry_id = fields.Many2one("diamond.symmetry", string="Symmetry")
    fluorescence_id = fields.Many2one("diamond.fluorescence", string="Fluorescence")
    lab_id = fields.Many2one("diamond.lab", string="Lab")
    charni_id = fields.Many2one("diamond.charni", string="Charni / Sieve")
    user_packet_no = fields.Char(string="Packet No.", help="Party / factory packet reference entered by user.")

    cps = fields.Char(string="CPS", compute="_compute_cps", store=True, help="Cut-Polish-Symmetry combined display, e.g. EX-EX-EX.")

    # ───────────────────────── Quantities ─────────────────────────
    org_pcs = fields.Integer(string="Original Pcs", default=1)
    org_cts = fields.Float(string="Original Cts", digits=(12, 4))
    expected_cts = fields.Float(string="Expected Cts", digits=(12, 4))
    rdy_pcs = fields.Integer(string="Ready Pcs", default=1, tracking=True)
    rdy_cts = fields.Float(string="Ready Cts", digits=(12, 4), tracking=True)
    rate_per_cts = fields.Float(string="Rate / Cts", digits=(12, 2))
    amount = fields.Float(string="Amount", compute="_compute_amount", store=True, digits=(14, 2))

    # ───────────────────────── State ─────────────────────────
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("in_stock", "In Stock"),
            ("in_process", "In Process"),
            ("in_jobwork", "In Jobwork"),
            ("in_factory", "In Factory"),
            ("in_hpht", "In HPHT"),
            ("ready", "Ready"),
            ("outward", "Outward"),
            ("closed", "Closed"),
        ],
        string="Status",
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )

    # ───────────────────────── Current location ─────────────────────────
    current_location = fields.Selection(
        selection=[
            ("office", "Office / Stock"),
            ("factory", "Factory"),
            ("jobwork", "At Jobworker"),
            ("hpht", "At HPHT Vendor"),
            ("lab", "At Lab"),
            ("party", "With Party"),
            ("outward", "Outward / Sold"),
        ],
        string="Current Location",
        default="office",
        index=True,
        tracking=True,
    )
    current_holder_id = fields.Many2one("diamond.ledger", string="Current Holder (Party)", tracking=True)
    current_employee_id = fields.Many2one("diamond.employee", string="Current Holder (Employee)", tracking=True)
    current_process_id = fields.Many2one("diamond.process", string="Current Process", tracking=True)

    # Suspended factory process (receive with Un-Processed = process not finished yet)
    pending_factory_employee_id = fields.Many2one(
        "diamond.employee", string="Pending Factory Worker", index=True,
        help="Worker who still has an unfinished factory process on this packet.",
    )
    pending_factory_process_id = fields.Many2one(
        "diamond.process", string="Pending Factory Process", index=True,
        help="Factory process that was interrupted and must be completed later.",
    )
    pending_factory_issue_cts = fields.Float(
        string="Pending Process Start Weight", digits=(12, 4),
        help="Packet weight when the pending factory process was first issued. "
             "Used for cumulative salary/invoice on final completion.",
    )
    pending_factory_labour_weight_cts = fields.Float(
        string="Pending Labour Weight", digits=(12, 4),
        help="Original labour weight for an unfinished factory process (survives un-processed receive).",
    )
    current_factory_labour_weight_cts = fields.Float(
        string="Current Labour Weight", digits=(12, 4),
        help="Labour weight for the active factory issue (set on issue, used on receive).",
    )

    # ───────────────────────── Timestamps ─────────────────────────
    inward_id = fields.Many2one("diamond.inward", string="Inward Doc", ondelete="set null")
    inward_party_id = fields.Many2one(
        "diamond.ledger",
        string="Inward Party",
        related="inward_id.ledger_id",
        readonly=True,
    )
    inward_date = fields.Datetime(string="Inward Date")
    outward_id = fields.Many2one("diamond.outward", string="Outward Doc", ondelete="set null")
    outward_date = fields.Datetime(string="Outward Date")
    last_movement_date = fields.Datetime(string="Last Movement", default=fields.Datetime.now)

    days_in_stock = fields.Integer(string="Days", compute="_compute_days_in_stock", store=False)

    # ───────────────────────── Audit trail ─────────────────────────
    history_ids = fields.One2many("diamond.packet.history", "packet_id", string="History")

    note = fields.Text(string="Internal Note")
    active = fields.Boolean(string="Active", default=True)

    _sql_constraints = [
        (
            "barcode_company_uniq",
            "unique(barcode, company_id)",
            "Packet barcode must be unique per company.",
        ),
        (
            "packet_no_company_uniq",
            "unique(packet_no, company_id)",
            "Packet number must be unique per company.",
        ),
    ]

    # ───────────────────────── Computes ─────────────────────────
    @api.depends("cut_id", "polish_id", "symmetry_id")
    def _compute_cps(self):
        for rec in self:
            parts = [
                (rec.cut_id.code or "-") if rec.cut_id else "-",
                (rec.polish_id.code or "-") if rec.polish_id else "-",
                (rec.symmetry_id.code or "-") if rec.symmetry_id else "-",
            ]
            rec.cps = "-".join(parts)

    @api.depends("rdy_cts", "rate_per_cts")
    def _compute_amount(self):
        for rec in self:
            rec.amount = (rec.rdy_cts or 0.0) * (rec.rate_per_cts or 0.0)

    def _compute_days_in_stock(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.days_in_stock = (now - rec.inward_date).days if rec.inward_date else 0

    # ───────────────────────── Constraints ─────────────────────────
    @api.constrains("org_cts", "rdy_cts")
    def _check_weights(self):
        for rec in self:
            if rec.org_cts < 0 or rec.rdy_cts < 0:
                raise ValidationError(_("Weights cannot be negative."))

    # ───────────────────────── Sequence + barcode auto-gen ─────────────────────────
    @api.model
    def _barcode_part(self, value):
        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

    @api.model
    def _sequence_number_from_packet_no(self, packet_no):
        """Return the zero-padded 6-digit number portion of packet_no."""
        if not packet_no or packet_no == _("New"):
            return "0"
        parts = str(packet_no).replace("\\", "/").split("/")
        number = parts[-1] if parts else str(packet_no)
        digits = re.sub(r"\D", "", number) or "0"
        return digits.zfill(6)

    @api.model
    def _short_number_from_packet_no(self, packet_no):
        """Return the packet number without leading zeros (e.g. '000008' → '8')."""
        padded = self._sequence_number_from_packet_no(packet_no)
        return str(int(padded)) if padded.isdigit() else padded

    @api.model
    def _generate_barcode(self, vals):
        """Generate barcode as PARTYCODE-NUMBER (e.g. MAD-8, MAD-160).

        Short format → thick Code128 bars on 50mm label → scannable by gun.
        Company code is omitted; party+number is unique within a company.
        """
        ledger = self.env["diamond.ledger"].browse(vals.get("current_holder_id"))
        party_code = self._barcode_part(ledger.code) if ledger else ""
        if not party_code:
            raise UserError(
                _("Party is required to generate packet barcodes (partycode-number).")
            )
        short_num = self._short_number_from_packet_no(vals.get("packet_no"))
        return "%s-%s" % (party_code, short_num)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("packet_no") or vals["packet_no"] == _("New"):
                vals["packet_no"] = self.env["ir.sequence"].with_company(company).next_by_code("diamond.packet") or _("New")
            if not vals.get("barcode"):
                vals["barcode"] = self._generate_barcode(vals)
        records = super().create(vals_list)
        for rec in records:
            rec._log_history(action="create", note=_("Packet created."))
        return records

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("skip_packet_auto_history"):
            return res
        if any(k in vals for k in ("state", "current_location", "current_holder_id", "current_employee_id", "current_process_id")):
            for rec in self:
                rec._log_history(action="update", note=_("Status / location updated."))
                rec.last_movement_date = fields.Datetime.now()
        return res

    # ───────────────────────── Helpers ─────────────────────────
    def _log_history(self, action, note=False, party_id=False, employee_id=False, process_id=False):
        self.ensure_one()
        return self.env["diamond.packet.history"].sudo().create({
            "packet_id": self.id,
            "company_id": self.company_id.id,
            "action": action,
            "state": self.state,
            "location": self.current_location,
            "process_id": process_id or self.current_process_id.id,
            "ledger_id": party_id or self.current_holder_id.id,
            "employee_id": employee_id or self.current_employee_id.id,
            "user_id": self.env.user.id,
            "note": note or "",
            "rdy_pcs": self.rdy_pcs,
            "rdy_cts": self.rdy_cts,
        })

    @api.depends("packet_no", "barcode", "shape_id", "color_id", "clarity_id", "rdy_cts")
    def _compute_display_name(self):
        for rec in self:
            label = rec.packet_no or rec.barcode or "Packet"
            if rec.shape_id and rec.color_id and rec.clarity_id:
                label = "%s [%s %s %s %.3fct]" % (
                    label, rec.shape_id.code, rec.color_id.code, rec.clarity_id.code, rec.rdy_cts or 0.0,
                )
            rec.display_name = label

    @api.model
    def _name_search(self, name="", domain=None, operator="ilike", limit=100, order=None):
        domain = list(domain or [])
        if name:
            domain = ["|", "|", "|",
                      ("packet_no", operator, name),
                      ("barcode", operator, name),
                      ("kapan_no", operator, name),
                      ("user_packet_no", operator, name)] + domain
        return self._search(domain, limit=limit, order=order)

    # ───────────────────────── Scan-by-barcode helper ─────────────────────────
    @api.model
    def _normalize_scan_code(self, code):
        """Strip whitespace, control chars, and uppercases scan input."""
        if not code:
            return ""
        code = re.sub(r"[\x00-\x1f\x7f]+", "", str(code).strip().upper())
        return code

    @api.model
    def _alphanumeric_only(self, code):
        """Return only A-Z 0-9 characters — used to match old barcodes that had hyphens."""
        return re.sub(r"[^A-Z0-9]", "", code)

    @api.model
    def find_by_barcode(self, code):
        """Lookup a packet by scanned barcode.

        Handles both new format (MCMAD000008) and old format (MC-MAD-000008)
        stored in the database.
        """
        code = self._normalize_scan_code(code)
        if not code:
            return self.browse()
        # Exact match (new format in DB, gun scanned same).
        packet = self.search([("barcode", "=", code)], limit=1)
        if packet:
            return packet
        # Case-insensitive exact match.
        packet = self.search([("barcode", "=ilike", code)], limit=1)
        if packet:
            return packet
        # Normalized match: strip non-alphanumeric from both sides.
        # Handles old DB records that still have hyphens (MC-MAD-000008).
        normalized = self._alphanumeric_only(code)
        if normalized and normalized != code:
            self.env.cr.execute(
                """
                SELECT id FROM diamond_packet
                WHERE company_id = %s
                  AND REGEXP_REPLACE(UPPER(barcode), '[^A-Z0-9]', '', 'g') = %s
                LIMIT 1
                """,
                (self.env.company.id, normalized),
            )
            row = self.env.cr.fetchone()
            if row:
                return self.browse(row[0])
        return self.browse()

    @api.model
    def find_live_stock_by_barcode(self, code):
        """Lookup an in-stock packet by barcode (excludes outward / closed)."""
        code = self._normalize_scan_code(code)
        if not code:
            return []
        live_domain = [("state", "not in", ("outward", "closed"))]
        packet = self.search([("barcode", "=", code)] + live_domain, limit=1)
        if not packet:
            packet = self.search([("barcode", "=ilike", code)] + live_domain, limit=1)
        if not packet:
            normalized = self._alphanumeric_only(code)
            if normalized and normalized != code:
                self.env.cr.execute(
                    """
                    SELECT id FROM diamond_packet
                    WHERE company_id = %s
                      AND state NOT IN ('outward', 'closed')
                      AND REGEXP_REPLACE(UPPER(barcode), '[^A-Z0-9]', '', 'g') = %s
                    LIMIT 1
                    """,
                    (self.env.company.id, normalized),
                )
                row = self.env.cr.fetchone()
                if row:
                    packet = self.browse(row[0])
        return packet.ids

    # ───────────────────────── State transitions ─────────────────────────
    def _open_issue_wizard(self, mode):
        """Generic helper: open the unified Issue wizard for ``self``.

        Used by the form-header buttons (F1 / F5 / F7 / F12). The wizard
        asks for process + party / employee, then creates and confirms
        the matching transaction document — which is what actually
        moves the packet's state and writes the audit-log row.
        """
        for rec in self:
            if rec.state in ("outward", "closed"):
                raise UserError(_("Packet %s is already outward / closed.") % rec.packet_no)
        return {
            "type": "ir.actions.act_window",
            "name": _("Issue Packet(s)"),
            "res_model": "diamond.packet.issue.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_ids": self.ids,
                "active_model": "diamond.packet",
                "default_issue_mode": mode,
            },
        }

    def action_issue_process(self):
        return self._open_issue_wizard("process")

    def action_issue_factory(self):
        return self._open_issue_wizard("factory")

    def action_issue_jobwork(self):
        return self._open_issue_wizard("jobwork")

    def action_issue_hpht(self):
        return self._open_issue_wizard("hpht")

    def _open_receive_wizard(self, mode=False):
        """Open the Receive wizard; auto-detect mode from state if omitted."""
        for rec in self:
            if rec.state in ("outward", "closed", "draft", "in_stock", "ready"):
                raise UserError(_(
                    "Packet %s is not currently issued (state: %s)."
                ) % (rec.packet_no, rec.state))
        ctx = {
            "active_ids": self.ids,
            "active_model": "diamond.packet",
        }
        if mode:
            ctx["default_receive_mode"] = mode
        return {
            "type": "ir.actions.act_window",
            "name": _("Receive Packet(s)"),
            "res_model": "diamond.packet.receive.wizard",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }

    def action_receive(self):
        return self._open_receive_wizard()

    def action_receive_process(self):
        return self._open_receive_wizard("process")

    def action_receive_factory(self):
        return self._open_receive_wizard("factory")

    def action_receive_jobwork(self):
        return self._open_receive_wizard("jobwork")

    def action_receive_hpht(self):
        return self._open_receive_wizard("hpht")

    # ─── Low-level state setters (kept for internal use / scripts) ───
    def action_to_stock(self):
        for rec in self:
            rec.write({"state": "in_stock", "current_location": "office"})
        return True

    def action_to_factory(self):
        for rec in self:
            if rec.state in ("closed",):
                raise UserError(_("Closed packets cannot move."))
            rec.write({"state": "in_factory", "current_location": "factory"})
        return True

    def action_to_jobwork(self):
        for rec in self:
            rec.write({"state": "in_jobwork", "current_location": "jobwork"})
        return True

    def action_to_hpht(self):
        for rec in self:
            rec.write({"state": "in_hpht", "current_location": "hpht"})
        return True

    def action_to_process(self):
        for rec in self:
            rec.write({"state": "in_process"})
        return True

    def action_mark_ready(self):
        for rec in self:
            rec.write({"state": "ready", "current_location": "office"})
        return True

    def action_outward(self):
        for rec in self:
            rec.write({"state": "outward", "current_location": "outward",
                       "outward_date": fields.Datetime.now()})
        return True

    def action_close(self):
        for rec in self:
            rec.write({"state": "closed", "active": False})
        return True
