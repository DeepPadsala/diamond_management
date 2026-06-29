from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DiamondEmployeeWithdrawal(models.Model):
    """Cash advance / withdrawal taken by a worker — recovered from salary slips."""

    _name = "diamond.employee.withdrawal"
    _description = "Employee Withdrawal"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _rec_name = "name"

    name = fields.Char(
        string="Withdrawal No.", required=True, copy=False, readonly=True,
        default=lambda self: _("New"),
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    employee_id = fields.Many2one(
        "diamond.employee", string="Employee", required=True, index=True, tracking=True,
    )
    date = fields.Date(
        string="Withdrawal Date", required=True,
        default=fields.Date.context_today, index=True, tracking=True,
    )
    amount = fields.Float(string="Amount", digits=(14, 2), required=True, tracking=True)
    deducted_amount = fields.Float(
        string="Recovered via Salary", digits=(14, 2), readonly=True, copy=False,
    )
    balance_amount = fields.Float(
        string="Balance to Recover", digits=(14, 2),
        compute="_compute_balance", store=True,
    )
    period_month = fields.Integer(
        string="Month", compute="_compute_period", store=True, index=True,
    )
    period_year = fields.Integer(
        string="Year", compute="_compute_period", store=True, index=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status", default="draft", required=True, index=True, tracking=True,
    )
    note = fields.Text(string="Note")
    slip_line_ids = fields.One2many(
        "diamond.salary.slip.withdrawal.line", "withdrawal_id",
        string="Salary Deductions", readonly=True,
    )

    _sql_constraints = [
        (
            "amount_positive",
            "CHECK(amount > 0)",
            "Withdrawal amount must be greater than zero.",
        ),
    ]

    @api.depends("amount", "deducted_amount")
    def _compute_balance(self):
        for rec in self:
            rec.balance_amount = max((rec.amount or 0.0) - (rec.deducted_amount or 0.0), 0.0)

    @api.depends("date")
    def _compute_period(self):
        for rec in self:
            if rec.date:
                rec.period_month = rec.date.month
                rec.period_year = rec.date.year
            else:
                rec.period_month = 0
                rec.period_year = 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].with_company(company).next_by_code(
                        "diamond.employee.withdrawal"
                    ) or _("New")
                )
        return super().create(vals_list)

    def write(self, vals):
        if any(f in vals for f in ("amount", "employee_id", "date")):
            locked = self.filtered(lambda w: w.state != "draft" or w.deducted_amount)
            if locked:
                raise UserError(_(
                    "Cannot change a withdrawal that is confirmed and already "
                    "linked to salary deductions."
                ))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda w: w.state != "draft" or w.deducted_amount):
            raise UserError(_("Only draft withdrawals with no salary deductions can be deleted."))
        return super().unlink()

    def action_confirm(self):
        for rec in self:
            if rec.amount <= 0:
                raise UserError(_("Withdrawal amount must be greater than zero."))
            rec.state = "confirmed"
        self._apply_to_draft_salary_slips()

    def _apply_to_draft_salary_slips(self):
        """Push confirmed withdrawals onto any open draft salary slips for the worker."""
        Slip = self.env["diamond.salary.slip"]
        for withdrawal in self:
            slips = Slip.search([
                ("employee_id", "=", withdrawal.employee_id.id),
                ("company_id", "=", withdrawal.company_id.id),
                ("state", "=", "draft"),
            ], order="period_year desc, period_month desc, id desc")
            if slips:
                slips.action_apply_withdrawals()

    def action_cancel(self):
        for rec in self:
            if rec.deducted_amount:
                raise UserError(_(
                    "Cannot cancel withdrawal %(name)s — %(amount)s already recovered "
                    "through salary slip(s). Reverse the salary slip first."
                ) % {"name": rec.name, "amount": rec.deducted_amount})
            rec.state = "cancelled"

    def action_draft(self):
        self.filtered(lambda w: w.state == "cancelled").write({"state": "draft"})
