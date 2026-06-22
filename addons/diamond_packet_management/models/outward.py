from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DiamondOutward(models.Model):
    """Outward — ship packets out (sale, return, courier)."""

    _name = "diamond.outward"
    _description = "Diamond Outward Entry"
    _order = "date desc, id desc"
    _rec_name = "name"

    name = fields.Char(string="Outward No.", required=True, copy=False, readonly=True, default=lambda self: _("New"))
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True, default=lambda self: self.env.company,
    )
    date = fields.Datetime(string="Date", default=fields.Datetime.now, required=True)
    ledger_id = fields.Many2one("diamond.ledger", string="Party", required=True)
    ref = fields.Char(string="Reference / Invoice")
    transport = fields.Char(string="Transport / Courier")

    state = fields.Selection(
        selection=[("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        string="Status", default="draft", required=True,
    )

    line_ids = fields.One2many("diamond.outward.line", "outward_id", string="Lines")
    total_pcs = fields.Integer(string="Total Pcs", compute="_compute_totals", store=True)
    total_cts = fields.Float(string="Total Cts", digits=(12, 4), compute="_compute_totals", store=True)
    total_amount = fields.Float(string="Total Amount", digits=(14, 2), compute="_compute_totals", store=True)
    note = fields.Text(string="Note")

    @api.depends("line_ids.pcs", "line_ids.cts", "line_ids.amount")
    def _compute_totals(self):
        for rec in self:
            rec.total_pcs = sum(rec.line_ids.mapped("pcs"))
            rec.total_cts = sum(rec.line_ids.mapped("cts"))
            rec.total_amount = sum(rec.line_ids.mapped("amount"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("diamond.outward") or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Add at least one line before confirming."))
            for line in rec.line_ids:
                if not line.packet_id:
                    raise UserError(_("Every outward line must reference a packet."))
                line.packet_id.write({
                    "state": "outward",
                    "current_location": "outward",
                    "outward_id": rec.id,
                    "outward_date": rec.date,
                    "current_holder_id": rec.ledger_id.id,
                })
                line.packet_id._log_history(action="outward",
                                            note=_("Outward via %s") % rec.name,
                                            party_id=rec.ledger_id.id)
            rec.state = "confirmed"
        return True

    def action_cancel(self):
        for rec in self:
            rec.state = "cancelled"
        return True

    def action_draft(self):
        for rec in self:
            rec.state = "draft"
        return True


class DiamondOutwardLine(models.Model):
    _name = "diamond.outward.line"
    _description = "Diamond Outward Line"
    _order = "id"

    outward_id = fields.Many2one("diamond.outward", string="Outward", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="outward_id.company_id", store=True, index=True)
    packet_id = fields.Many2one("diamond.packet", string="Packet", required=True)
    barcode = fields.Char(related="packet_id.barcode", string="Barcode", store=False)
    pcs = fields.Integer(string="Pcs", default=1)
    cts = fields.Float(string="Cts", digits=(12, 4))
    rate_per_cts = fields.Float(string="Rate / Cts", digits=(12, 2))
    amount = fields.Float(string="Amount", digits=(14, 2), compute="_compute_amount", store=True)
    note = fields.Char(string="Note")

    @api.depends("cts", "rate_per_cts")
    def _compute_amount(self):
        for rec in self:
            rec.amount = (rec.cts or 0.0) * (rec.rate_per_cts or 0.0)

    @api.onchange("packet_id")
    def _onchange_packet(self):
        if self.packet_id:
            self.pcs = self.packet_id.rdy_pcs or 1
            self.cts = self.packet_id.rdy_cts or 0.0
            self.rate_per_cts = self.packet_id.rate_per_cts or 0.0
