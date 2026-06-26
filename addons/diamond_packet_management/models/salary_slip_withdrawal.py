from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DiamondSalarySlipWithdrawalLine(models.Model):
    """Amount recovered from a withdrawal on a salary slip."""

    _name = "diamond.salary.slip.withdrawal.line"
    _description = "Salary Slip Withdrawal Line"
    _order = "id"

    slip_id = fields.Many2one(
        "diamond.salary.slip", string="Salary Slip", required=True, ondelete="cascade",
    )
    company_id = fields.Many2one(related="slip_id.company_id", store=True)
    withdrawal_id = fields.Many2one(
        "diamond.employee.withdrawal", string="Withdrawal", required=True, ondelete="restrict",
    )
    withdrawal_name = fields.Char(related="withdrawal_id.name", string="Withdrawal No.")
    withdrawal_date = fields.Date(related="withdrawal_id.date", string="Withdrawal Date")
    amount = fields.Float(string="Deducted Amount", digits=(14, 2), required=True)


class DiamondSalarySlipWithdrawalMixin(models.AbstractModel):
    """Apply employee withdrawals to draft salary slips (FIFO, with carry-forward)."""

    _name = "diamond.salary.slip.withdrawal.mixin"
    _description = "Salary Slip Withdrawal Mixin"

    withdrawal_line_ids = fields.One2many(
        "diamond.salary.slip.withdrawal.line", "slip_id", string="Withdrawal Deductions",
    )
    gross_amount = fields.Float(
        string="Gross Labour", digits=(14, 2),
        compute="_compute_salary_amounts", store=True,
    )
    withdrawal_deduction = fields.Float(
        string="Withdrawal Deduction", digits=(14, 2),
        compute="_compute_salary_amounts", store=True,
    )
    net_payable_amount = fields.Float(
        string="Net Payable", digits=(14, 2),
        compute="_compute_salary_amounts", store=True,
    )
    total_amount = fields.Float(
        string="Total Payable", digits=(14, 2),
        compute="_compute_salary_amounts", store=True,
    )
    advance_carried_forward = fields.Float(
        string="Advance Carried Forward", digits=(14, 2),
        compute="_compute_advance_carried_forward",
        help="Confirmed withdrawals still to recover in future salary slips.",
    )

    @api.depends("line_ids.amount", "withdrawal_line_ids.amount")
    def _compute_salary_amounts(self):
        for rec in self:
            gross = sum(rec.line_ids.mapped("amount"))
            deduction = sum(rec.withdrawal_line_ids.mapped("amount"))
            rec.gross_amount = gross
            rec.withdrawal_deduction = deduction
            rec.net_payable_amount = gross - deduction
            rec.total_amount = rec.net_payable_amount

    @api.depends("employee_id", "employee_id.advance_balance", "company_id")
    def _compute_advance_carried_forward(self):
        for rec in self:
            if rec.employee_id and rec.company_id:
                rec.advance_carried_forward = rec.employee_id.advance_balance
            else:
                rec.advance_carried_forward = 0.0

    def _reverse_withdrawal_allocations(self):
        """Undo withdrawal deductions linked to these slips."""
        for slip in self:
            for wl in slip.withdrawal_line_ids:
                wl.withdrawal_id.deducted_amount = max(
                    wl.withdrawal_id.deducted_amount - wl.amount, 0.0,
                )
            slip.withdrawal_line_ids.unlink()

    def action_apply_withdrawals(self):
        """FIFO: recover open withdrawals from gross labour on draft slip(s)."""
        WithdrawalLine = self.env["diamond.salary.slip.withdrawal.line"]
        Withdrawal = self.env["diamond.employee.withdrawal"]

        for slip in self:
            if slip.state != "draft":
                raise UserError(_("Withdrawals can only be applied on draft salary slips."))
            slip._reverse_withdrawal_allocations()

            gross = sum(slip.line_ids.mapped("amount"))
            pool = gross
            if pool <= 0:
                continue

            withdrawals = Withdrawal.search([
                ("employee_id", "=", slip.employee_id.id),
                ("company_id", "=", slip.company_id.id),
                ("state", "=", "confirmed"),
            ], order="date asc, id asc")

            for withdrawal in withdrawals:
                balance = withdrawal.amount - withdrawal.deducted_amount
                if balance <= 0.0001 or pool <= 0.0001:
                    continue
                take = min(balance, pool)
                WithdrawalLine.create({
                    "slip_id": slip.id,
                    "withdrawal_id": withdrawal.id,
                    "amount": take,
                })
                withdrawal.deducted_amount += take
                pool -= take

        return True
