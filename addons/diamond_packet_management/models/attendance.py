from calendar import monthrange

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DiamondAttendance(models.Model):
    """Daily attendance for employees (used for fixed-salary payroll)."""

    _name = "diamond.attendance"
    _description = "Employee Attendance"
    _order = "date desc, employee_id"
    _rec_name = "display_name"

    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    date = fields.Date(
        string="Date", required=True, index=True,
        default=fields.Date.context_today,
    )
    employee_id = fields.Many2one(
        "diamond.employee", string="Employee", required=True, index=True,
        ondelete="restrict",
    )
    status = fields.Selection(
        selection=[
            ("present", "Present"),
            ("half_day", "Half Day"),
            ("absent", "Absent"),
            ("holiday", "Holiday / Week Off"),
        ],
        string="Status",
        required=True,
        default="present",
    )
    paid_days = fields.Float(
        string="Paid Days", digits=(4, 2),
        compute="_compute_paid_days", store=True,
        help="Present=1, Half Day=0.5, Holiday=1, Absent=0.",
    )
    note = fields.Char(string="Note")

    display_name = fields.Char(compute="_compute_display_name")

    _sql_constraints = [
        (
            "employee_date_uniq",
            "unique(employee_id, date, company_id)",
            "Attendance for this employee on this date already exists.",
        ),
    ]

    @api.depends("status")
    def _compute_paid_days(self):
        for rec in self:
            rec.paid_days = {
                "present": 1.0,
                "half_day": 0.5,
                "absent": 0.0,
                "holiday": 1.0,
            }.get(rec.status, 0.0)

    @api.depends("employee_id", "date", "status")
    def _compute_display_name(self):
        for rec in self:
            emp = rec.employee_id.display_name or ""
            day = fields.Date.to_string(rec.date) if rec.date else ""
            status = dict(rec._fields["status"].selection).get(rec.status, "")
            rec.display_name = f"{emp} — {day} ({status})" if emp else day

    @api.constrains("employee_id", "company_id")
    def _check_employee_company(self):
        for rec in self:
            if rec.employee_id and rec.company_id and rec.employee_id.company_id != rec.company_id:
                raise ValidationError(_(
                    "Employee %(emp)s belongs to a different company."
                ) % {"emp": rec.employee_id.display_name})

    @api.model
    def paid_days_for_period(self, employee, year, month):
        """Sum paid days for an employee in a calendar month."""
        if not employee or not year or not month:
            return 0.0
        last_day = monthrange(year, month)[1]
        date_from = fields.Date.to_date(f"{year:04d}-{month:02d}-01")
        date_to = fields.Date.to_date(f"{year:04d}-{month:02d}-{last_day:02d}")
        records = self.search([
            ("employee_id", "=", employee.id),
            ("company_id", "=", employee.company_id.id),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ])
        return sum(records.mapped("paid_days"))

    @api.model
    def calendar_days_in_month(self, year, month):
        return monthrange(year, month)[1]
