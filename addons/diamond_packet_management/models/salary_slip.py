from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DiamondSalarySlip(models.Model):
    """Monthly salary slip for a worker based on completed factory labour."""

    _name = "diamond.salary.slip"
    _description = "Worker Salary Slip"
    _inherit = ["diamond.salary.slip.withdrawal.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "period_year desc, period_month desc, id desc"
    _rec_name = "name"

    name = fields.Char(string="Slip No.", required=True, copy=False, readonly=True, default=lambda self: _("New"))
    company_id = fields.Many2one("res.company", required=True, index=True, default=lambda self: self.env.company)
    employee_id = fields.Many2one("diamond.employee", string="Worker", required=True, index=True, tracking=True)
    period_month = fields.Selection(
        selection=[
            ("1", "January"), ("2", "February"), ("3", "March"), ("4", "April"),
            ("5", "May"), ("6", "June"), ("7", "July"), ("8", "August"),
            ("9", "September"), ("10", "October"), ("11", "November"), ("12", "December"),
        ],
        string="Month",
        required=True,
        tracking=True,
    )
    period_year = fields.Integer(string="Year", required=True, default=lambda self: fields.Date.today().year, tracking=True)
    date = fields.Date(string="Slip Date", default=fields.Date.context_today, required=True, tracking=True)

    line_ids = fields.One2many("diamond.salary.slip.line", "slip_id", string="Lines")
    entry_ids = fields.One2many("diamond.labour.entry", "salary_slip_id", string="Labour Entries")

    total_pcs = fields.Integer(string="Total Pcs", compute="_compute_totals", store=True)

    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("paid", "Paid"), ("cancelled", "Cancelled")],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
    )
    note = fields.Text(string="Note")
    payment_ref = fields.Char(string="Payment Reference", tracking=True)
    payment_date = fields.Date(string="Payment Date", tracking=True)
    is_supplemental = fields.Boolean(
        string="Supplemental",
        default=False,
        tracking=True,
        help="Additional salary slip for the same month (e.g. mid-month advance after the main slip was paid).",
    )

    @api.depends("line_ids.pcs")
    def _compute_totals(self):
        for rec in self:
            rec.total_pcs = sum(rec.line_ids.mapped("pcs"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("diamond.salary.slip") or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Add at least one line before confirming."))
            rec.action_apply_withdrawals()
            rec.entry_ids.write({"state": "invoiced"})
            rec.state = "confirmed"

    def action_reopen_draft(self):
        """Reopen a confirmed slip so withdrawals can be recalculated."""
        for rec in self:
            if rec.state != "confirmed":
                raise UserError(_("Only confirmed salary slips can be reopened."))
            rec.entry_ids.write({"state": "draft"})
            rec.state = "draft"
        self.action_apply_withdrawals()

    def action_mark_paid(self):
        for rec in self:
            rec.entry_ids.write({"state": "paid"})
            rec.state = "paid"

    def action_cancel(self):
        for rec in self:
            rec._reverse_withdrawal_allocations()
            rec.entry_ids.write({"state": "draft", "salary_slip_id": False})
            rec.line_ids.unlink()
            rec.state = "cancelled"

    def action_draft(self):
        self.filtered(lambda r: r.state == "cancelled").write({"state": "draft"})


class DiamondSalarySlipLine(models.Model):
    _name = "diamond.salary.slip.line"
    _description = "Salary Slip Line"
    _order = "id"

    slip_id = fields.Many2one("diamond.salary.slip", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="slip_id.company_id", store=True)
    labour_entry_id = fields.Many2one("diamond.labour.entry", string="Labour Entry", ondelete="set null")
    date = fields.Datetime(string="Date")
    process_id = fields.Many2one("diamond.process", string="Process")
    packet_id = fields.Many2one("diamond.packet", string="Packet")
    receive_doc_name = fields.Char(string="Receive Doc")
    pcs = fields.Integer(string="Pcs")
    cts = fields.Float(string="Cts", digits=(12, 4))
    loss_cts = fields.Float(string="Loss Cts", digits=(12, 4))
    rate = fields.Float(string="Rate", digits=(12, 2))
    amount = fields.Float(string="Amount", digits=(14, 2))
    note = fields.Char(string="Note")
