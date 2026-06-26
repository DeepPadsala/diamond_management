from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DiamondEmployee(models.Model):
    """In-house employee master (cutter, polisher, manager, etc.)."""

    _name = "diamond.employee"
    _description = "Diamond Employee Master"
    _inherit = "diamond.master.mixin"

    phone = fields.Char(string="Phone")
    email = fields.Char(string="Email")
    role = fields.Selection(
        selection=[
            ("cutter", "Cutter"),
            ("polisher", "Polisher"),
            ("checker", "Checker"),
            ("manager", "Manager"),
            ("packer", "Packer"),
            ("other", "Other"),
        ],
        string="Role",
        default="other",
    )
    join_date = fields.Date(string="Joined On")
    user_id = fields.Many2one("res.users", string="Linked Login User", help="Optional Odoo login for this employee.")
    process_ids = fields.Many2many(
        "diamond.process",
        "diamond_employee_process_rel",
        "employee_id",
        "process_id",
        string="Capable Processes",
        help="Processes this employee can work on. Leave empty to allow all processes.",
    )
    withdrawal_ids = fields.One2many(
        "diamond.employee.withdrawal", "employee_id", string="Withdrawals",
    )
    advance_balance = fields.Float(
        string="Advance Balance",
        digits=(14, 2),
        compute="_compute_advance_balance",
        store=True,
        help="Confirmed withdrawals not yet recovered through salary slips.",
    )

    @api.depends(
        "withdrawal_ids.amount", "withdrawal_ids.deducted_amount", "withdrawal_ids.state",
    )
    def _compute_advance_balance(self):
        for rec in self:
            open_withdrawals = rec.withdrawal_ids.filtered(lambda w: w.state == "confirmed")
            rec.advance_balance = sum(
                max(w.amount - w.deducted_amount, 0.0) for w in open_withdrawals
            )

    @api.model
    def domain_for_process(self, process):
        """Employees allowed for a process (empty process_ids = all processes)."""
        if not process:
            return []
        process_id = process.id if hasattr(process, "id") else process
        return ["|", ("process_ids", "=", False), ("process_ids", "in", [process_id])]

    @api.model
    def check_capable_for_process(self, employee, process):
        if not employee or not process:
            return True
        if not employee.process_ids:
            return True
        return process in employee.process_ids

    @api.constrains("process_ids", "company_id")
    def _check_process_company(self):
        for rec in self:
            wrong = rec.process_ids.filtered(lambda p: p.company_id != rec.company_id)
            if wrong:
                raise ValidationError(_(
                    "Process %(process)s belongs to a different company than employee %(employee)s."
                ) % {"process": wrong[0].display_name, "employee": rec.display_name})

    @api.depends("code", "name")
    def _compute_display_name(self):
        for rec in self:
            if rec.code and rec.name:
                rec.display_name = f"{rec.code} - {rec.name}"
            else:
                rec.display_name = rec.code or rec.name or ""
