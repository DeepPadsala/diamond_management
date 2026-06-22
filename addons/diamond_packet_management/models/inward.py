from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DiamondInward(models.Model):
    """Inward header — receive packets into stock from a party."""

    _name = "diamond.inward"
    _description = "Diamond Inward Entry"
    _order = "date desc, id desc"
    _rec_name = "name"

    name = fields.Char(string="Inward No.", required=True, copy=False, readonly=True, default=lambda self: _("New"))
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True, default=lambda self: self.env.company,
    )
    date = fields.Datetime(string="Date", default=fields.Datetime.now, required=True)
    ledger_id = fields.Many2one("diamond.ledger", string="Party", required=True)
    party_barcode = fields.Char(string="Party Barcode (scan)")
    ref = fields.Char(string="Reference / Challan")

    state = fields.Selection(
        selection=[("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        string="Status",
        default="draft",
        required=True,
    )

    line_ids = fields.One2many("diamond.inward.line", "inward_id", string="Lines")

    total_pcs = fields.Integer(string="Total Pcs", compute="_compute_totals", store=True)
    total_cts = fields.Float(string="Total Cts", digits=(12, 4), compute="_compute_totals", store=True)
    total_amount = fields.Float(string="Total Amount", digits=(14, 2), compute="_compute_totals", store=True)

    note = fields.Text(string="Note")

    @api.depends("line_ids.org_pcs", "line_ids.org_cts", "line_ids.amount")
    def _compute_totals(self):
        for rec in self:
            rec.total_pcs = sum(rec.line_ids.mapped("org_pcs"))
            rec.total_cts = sum(rec.line_ids.mapped("org_cts"))
            rec.total_amount = sum(rec.line_ids.mapped("amount"))

    @api.onchange("ledger_id")
    def _onchange_ledger_party_barcode(self):
        if self.ledger_id:
            self.party_barcode = self.ledger_id.barcode

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("diamond.inward") or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Add at least one line before confirming."))
            if not (rec.ledger_id.code or "").strip():
                raise UserError(
                    _("Party %(party)s has no Code. Set it on the ledger master before confirming.")
                    % {"party": rec.ledger_id.display_name}
                )
            for line in rec.line_ids:
                line._create_or_update_packet()
            rec.state = "confirmed"
        if len(self) == 1:
            return self.action_print_barcodes()
        return True

    def action_print_barcodes(self):
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(_("Confirm the inward entry before printing barcodes."))
        return self.env["diamond.barcode.label.print.service"].print_inward_labels(self)

    def action_cancel(self):
        for rec in self:
            rec.state = "cancelled"
        return True

    def action_draft(self):
        for rec in self:
            rec.state = "draft"
        return True


class DiamondInwardLine(models.Model):
    """Inward line — one packet per row."""

    _name = "diamond.inward.line"
    _description = "Diamond Inward Line"
    _order = "id"

    inward_id = fields.Many2one("diamond.inward", string="Inward", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="inward_id.company_id", store=True, index=True)

    packet_id = fields.Many2one("diamond.packet", string="Packet", help="Filled after confirm.")
    barcode = fields.Char(string="Barcode")
    kapan_no = fields.Char(string="Kapan")
    user_packet_no = fields.Char(string="Packet No.")
    sequence_packet_no = fields.Char(
        string="Sequence No.",
        related="packet_id.packet_no",
        readonly=True,
    )
    process_id = fields.Many2one("diamond.process", string="Process")

    shape_id = fields.Many2one("diamond.shape", string="Shape", required=True)
    color_id = fields.Many2one("diamond.color", string="Color", required=True)
    clarity_id = fields.Many2one("diamond.clarity", string="Clarity", required=True)
    cut_id = fields.Many2one("diamond.cut", string="Cut")
    polish_id = fields.Many2one("diamond.polish", string="Polish")
    symmetry_id = fields.Many2one("diamond.symmetry", string="Symmetry")
    fluorescence_id = fields.Many2one("diamond.fluorescence", string="Fluo")
    lab_id = fields.Many2one("diamond.lab", string="Lab")

    org_pcs = fields.Integer(string="Pcs", default=1)
    org_cts = fields.Float(string="Rough Weight", digits=(12, 4))
    expected_cts = fields.Float(string="Polish Weight", digits=(12, 4))
    rate_per_cts = fields.Float(string="Rate / Cts", digits=(12, 2))
    amount = fields.Float(string="Amount", digits=(14, 2), compute="_compute_amount", store=True)

    note = fields.Char(string="Note")

    @api.depends("org_cts", "rate_per_cts")
    def _compute_amount(self):
        for rec in self:
            rec.amount = (rec.org_cts or 0.0) * (rec.rate_per_cts or 0.0)

    def _packet_vals(self):
        self.ensure_one()
        return {
            "org_pcs": self.org_pcs,
            "org_cts": self.org_cts,
            "expected_cts": self.expected_cts,
            "rate_per_cts": self.rate_per_cts,
            "user_packet_no": self.user_packet_no,
            "state": "in_stock",
            "current_location": "office",
            "current_holder_id": self.inward_id.ledger_id.id,
            "current_process_id": self.process_id.id if self.process_id else False,
            "inward_id": self.inward_id.id,
            "inward_date": self.inward_id.date,
        }

    def _create_or_update_packet(self):
        Packet = self.env["diamond.packet"]
        for line in self:
            if line.packet_id:
                line.packet_id.write(line._packet_vals())
                line.barcode = line.packet_id.barcode
                line.packet_id._log_history(
                    action="inward",
                    note=_("Inward via %s") % line.inward_id.name,
                    party_id=line.inward_id.ledger_id.id,
                    process_id=line.process_id.id if line.process_id else False,
                )
                continue

            packet_vals = {
                "company_id": line.company_id.id,
                "kapan_no": line.kapan_no,
                "user_packet_no": line.user_packet_no,
                "shape_id": line.shape_id.id,
                "color_id": line.color_id.id,
                "clarity_id": line.clarity_id.id,
                "cut_id": line.cut_id.id,
                "polish_id": line.polish_id.id,
                "symmetry_id": line.symmetry_id.id,
                "fluorescence_id": line.fluorescence_id.id,
                "lab_id": line.lab_id.id,
                "rdy_pcs": line.org_pcs,
                "rdy_cts": line.org_cts,
                **line._packet_vals(),
            }
            packet = Packet.create(packet_vals)
            line.packet_id = packet.id
            line.barcode = packet.barcode
            packet._log_history(
                action="inward",
                note=_("Inward via %s") % line.inward_id.name,
                party_id=line.inward_id.ledger_id.id,
                process_id=line.process_id.id if line.process_id else False,
            )
