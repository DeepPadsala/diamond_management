from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DiamondImprovementReturn(models.Model):
    """Party returns an outward packet for improvement (re-polish).

    The packet comes back to stock flagged for improvement work.
    No party labour charge on receive; worker salary is still created.
    """

    _name = "diamond.improvement.return"
    _description = "Improvement Return"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _rec_name = "name"

    name = fields.Char(
        string="Return No.", required=True, copy=False, readonly=True,
        default=lambda self: _("New"), tracking=True,
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    date = fields.Datetime(string="Date", default=fields.Datetime.now, required=True, tracking=True)
    ledger_id = fields.Many2one("diamond.ledger", string="Party", required=True, tracking=True)
    ref = fields.Char(string="Reference", tracking=True)
    state = fields.Selection(
        selection=[("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        string="Status", default="draft", required=True, tracking=True,
    )
    line_ids = fields.One2many("diamond.improvement.return.line", "return_id", string="Lines")
    total_pcs = fields.Integer(string="Total Pcs", compute="_compute_totals", store=True)
    total_cts = fields.Float(string="Total Cts", digits=(12, 4), compute="_compute_totals", store=True)
    note = fields.Text(string="Note")

    @api.depends("line_ids.pcs", "line_ids.cts")
    def _compute_totals(self):
        for rec in self:
            rec.total_pcs = sum(rec.line_ids.mapped("pcs"))
            rec.total_cts = sum(rec.line_ids.mapped("cts"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].with_company(company).next_by_code("diamond.improvement.return")
                    or _("New")
                )
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Add at least one line before confirming."))
            for line in rec.line_ids:
                packet = line.packet_id
                if packet.state != "outward":
                    raise UserError(_(
                        "Packet %(packet)s is not outward (current state: %(state)s)."
                    ) % {"packet": packet.packet_no, "state": packet.state})
                polish_employee = packet._find_last_polish_employee()
                packet.write({
                    "state": "in_stock",
                    "current_location": "office",
                    "improvement_return": True,
                    "improvement_polish_employee_id": polish_employee.id if polish_employee else False,
                    "current_holder_id": rec.ledger_id.id,
                    "current_employee_id": False,
                    "current_process_id": False,
                })
                packet._log_history(
                    action="improvement_return",
                    note=_("Improvement return via %s") % rec.name,
                    party_id=rec.ledger_id.id,
                    employee_id=polish_employee.id if polish_employee else False,
                )
            rec.state = "confirmed"
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True

    def action_draft(self):
        self.write({"state": "draft"})
        return True


class DiamondImprovementReturnLine(models.Model):
    _name = "diamond.improvement.return.line"
    _description = "Improvement Return Line"
    _order = "id"

    return_id = fields.Many2one(
        "diamond.improvement.return", string="Improvement Return",
        required=True, ondelete="cascade",
    )
    company_id = fields.Many2one(related="return_id.company_id", store=True, index=True)
    packet_id = fields.Many2one(
        "diamond.packet", string="Packet", required=True,
        domain="[('state', '=', 'outward')]",
    )
    barcode = fields.Char(
        string="Barcode",
        help="Scan packet barcode to auto-select the outward packet.",
    )
    pcs = fields.Integer(string="Pcs", default=1)
    cts = fields.Float(string="Cts", digits=(12, 4))
    note = fields.Char(string="Note")

    def _apply_packet(self, packet):
        """Fill line fields from the selected outward packet."""
        self.packet_id = packet
        self.barcode = packet.barcode
        self.pcs = packet.rdy_pcs or 1
        self.cts = packet.rdy_cts or 0.0
        if self.return_id and not self.return_id.ledger_id and packet.current_holder_id:
            self.return_id.ledger_id = packet.current_holder_id

    @api.onchange("barcode")
    def _onchange_barcode(self):
        code = (self.barcode or "").strip()
        if not code:
            return
        Packet = self.env["diamond.packet"]
        packet = Packet.find_by_barcode(code)
        if not packet:
            return {
                "warning": {
                    "title": _("Packet not found"),
                    "message": _("No packet found for barcode: %s") % code,
                }
            }
        if packet.state != "outward":
            return {
                "warning": {
                    "title": _("Not an outward packet"),
                    "message": _(
                        "Packet %(packet)s is %(state)s. Only outward packets can be returned for improvement."
                    ) % {"packet": packet.packet_no, "state": packet.state},
                }
            }
        company = self.return_id.company_id if self.return_id else self.env.company
        if company and packet.company_id != company:
            return {
                "warning": {
                    "title": _("Wrong company"),
                    "message": _("Packet %(packet)s belongs to another company.") % {
                        "packet": packet.packet_no,
                    },
                }
            }
        # Avoid duplicate lines for the same packet on this document.
        siblings = (self.return_id.line_ids - self) if self.return_id else self.env[self._name]
        if siblings.filtered(lambda l: l.packet_id == packet):
            return {
                "warning": {
                    "title": _("Already added"),
                    "message": _("Packet %(packet)s is already on this improvement return.") % {
                        "packet": packet.packet_no,
                    },
                }
            }
        self._apply_packet(packet)

    @api.onchange("packet_id")
    def _onchange_packet(self):
        if self.packet_id:
            self._apply_packet(self.packet_id)
