from odoo import _, api, fields, models
from odoo.exceptions import UserError


# ─────────────────────────────────────────────────────────────────
#   Abstract base shared by Process / Jobwork / Factory / HPHT
# ─────────────────────────────────────────────────────────────────


class DiamondMovementMixin(models.AbstractModel):
    """Common fields & flow for all movement documents."""

    _name = "diamond.movement.mixin"
    _description = "Diamond Movement Mixin"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Doc No.", required=True, copy=False, readonly=True, default=lambda self: _("New"), tracking=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True, default=lambda self: self.env.company,
    )
    date = fields.Datetime(string="Date", default=fields.Datetime.now, required=True, tracking=True)
    process_id = fields.Many2one("diamond.process", string="Process", tracking=True)
    ledger_id = fields.Many2one("diamond.ledger", string="Party / Vendor", tracking=True)
    employee_id = fields.Many2one("diamond.employee", string="Employee", tracking=True)
    note = fields.Text(string="Note")
    state = fields.Selection(
        selection=[("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        string="Status", default="draft", required=True, tracking=True,
    )

    total_pcs = fields.Integer(string="Total Pcs", compute="_compute_totals", store=True)
    total_cts = fields.Float(string="Total Cts", digits=(12, 4), compute="_compute_totals", store=True)

    @api.depends("line_ids.pcs", "line_ids.cts")
    def _compute_totals(self):
        for rec in self:
            rec.total_pcs = sum(rec.line_ids.mapped("pcs"))
            rec.total_cts = sum(rec.line_ids.mapped("cts"))

    def _prompt_jangad_print(self, movement_type):
        """Ask user whether to print jangad after issue/receive confirm."""
        self.ensure_one()
        if self.env.context.get("skip_jangad_prompt"):
            return True
        return self.env["diamond.jangad.print.service"].open_print_prompt(
            self._name, self.id, movement_type,
        )


class DiamondMovementLineMixin(models.AbstractModel):
    """Common line fields for movement documents."""

    _name = "diamond.movement.line.mixin"
    _description = "Diamond Movement Line Mixin"

    packet_id = fields.Many2one("diamond.packet", string="Packet", required=True)
    barcode = fields.Char(related="packet_id.barcode", string="Barcode", store=False)
    pcs = fields.Integer(string="Pcs", default=1)
    cts = fields.Float(string="Cts", digits=(12, 4))
    note = fields.Char(string="Note")

    @api.onchange("packet_id")
    def _onchange_packet(self):
        if self.packet_id:
            self.pcs = self.packet_id.rdy_pcs or 1
            self.cts = self.packet_id.rdy_cts or 0.0


# ─────────────────────────────────────────────────────────────────
#   Process Issue / Receive (F1 / F2)
# ─────────────────────────────────────────────────────────────────


class DiamondProcessIssue(models.Model):
    _name = "diamond.process.issue"
    _description = "Process Issue"
    _inherit = "diamond.movement.mixin"
    _order = "date desc, id desc"

    line_ids = fields.One2many("diamond.process.issue.line", "doc_id", string="Lines")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("diamond.process.issue") or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Add at least one line."))
            for line in rec.line_ids:
                line.packet_id.write({
                    "state": "in_process",
                    "current_process_id": rec.process_id.id,
                    "current_employee_id": rec.employee_id.id,
                    "current_holder_id": rec.ledger_id.id,
                })
                line.packet_id._log_history(action="process_issue",
                                            note=_("Process Issue %s") % rec.name,
                                            process_id=rec.process_id.id,
                                            employee_id=rec.employee_id.id,
                                            party_id=rec.ledger_id.id)
            rec.state = "confirmed"
        if len(self) == 1:
            return self._prompt_jangad_print("issue")
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_draft(self):
        self.write({"state": "draft"})


class DiamondProcessIssueLine(models.Model):
    _name = "diamond.process.issue.line"
    _description = "Process Issue Line"
    _inherit = "diamond.movement.line.mixin"

    doc_id = fields.Many2one("diamond.process.issue", string="Document", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="doc_id.company_id", store=True, index=True)


class DiamondProcessReceive(models.Model):
    _name = "diamond.process.receive"
    _description = "Process Receive"
    _inherit = ["diamond.movement.mixin", "diamond.labour.calculator"]
    _order = "date desc, id desc"

    line_ids = fields.One2many("diamond.process.receive.line", "doc_id", string="Lines")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("diamond.process.receive") or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            for line in rec.line_ids:
                line.packet_id.write({
                    "state": "in_stock",
                    "current_location": "office",
                    "rdy_pcs": line.pcs or line.packet_id.rdy_pcs,
                    "rdy_cts": line.cts or line.packet_id.rdy_cts,
                })
                line.packet_id._log_history(action="process_receive",
                                            note=_("Process Receive %s") % rec.name,
                                            process_id=rec.process_id.id,
                                            employee_id=rec.employee_id.id,
                                            party_id=rec.ledger_id.id)
            rec._create_labour_entries_from_receive(
                rec, "diamond.process.receive.line", "diamond.process.receive",
                create_party=True, create_worker=False,
            )
            rec.state = "confirmed"
        if len(self) == 1:
            return self._prompt_jangad_print("receive")
        return True

    def action_cancel(self):
        for rec in self:
            rec._unlink_labour_entries_for_receive(rec, "diamond.process.receive")
        self.write({"state": "cancelled"})

    def action_draft(self):
        self.write({"state": "draft"})


class DiamondProcessReceiveLine(models.Model):
    _name = "diamond.process.receive.line"
    _description = "Process Receive Line"
    _inherit = "diamond.movement.line.mixin"

    doc_id = fields.Many2one("diamond.process.receive", string="Document", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="doc_id.company_id", store=True, index=True)
    loss_cts = fields.Float(string="Loss (cts)", digits=(12, 4))
    party_labour_amount = fields.Float(string="Party Labour", digits=(14, 2), readonly=True)
