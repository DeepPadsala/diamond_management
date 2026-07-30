from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DiamondAttendanceBatchWizard(models.TransientModel):
    """Mark attendance for all (or selected) employees on one date."""

    _name = "diamond.attendance.batch.wizard"
    _description = "Mark Daily Attendance"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company,
    )
    date = fields.Date(string="Date", required=True, default=fields.Date.context_today)
    default_status = fields.Selection(
        selection=[
            ("present", "Present"),
            ("half_day", "Half Day"),
            ("absent", "Absent"),
            ("holiday", "Holiday / Week Off"),
        ],
        string="Default Status",
        required=True,
        default="present",
    )
    only_fixed_salary = fields.Boolean(
        string="Fixed-Salary Employees Only",
        default=True,
        help="If checked, only employees with Fixed Monthly salary type are listed.",
    )
    line_ids = fields.One2many(
        "diamond.attendance.batch.wizard.line", "wizard_id", string="Employees",
    )

    @api.onchange("company_id", "date", "default_status", "only_fixed_salary")
    def _onchange_load_lines(self):
        Employee = self.env["diamond.employee"]
        domain = [
            ("company_id", "=", self.company_id.id),
            ("active", "=", True),
        ]
        if self.only_fixed_salary:
            domain.append(("salary_type", "=", "fixed"))
        employees = Employee.search(domain, order="name")
        existing = {
            a.employee_id.id: a.status
            for a in self.env["diamond.attendance"].search([
                ("company_id", "=", self.company_id.id),
                ("date", "=", self.date),
            ])
        }
        lines = []
        for emp in employees:
            lines.append((0, 0, {
                "employee_id": emp.id,
                "status": existing.get(emp.id, self.default_status),
            }))
        self.line_ids = [(5, 0, 0)] + lines

    def action_confirm(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No employees to mark. Load the list first."))
        Attendance = self.env["diamond.attendance"]
        for line in self.line_ids:
            existing = Attendance.search([
                ("employee_id", "=", line.employee_id.id),
                ("date", "=", self.date),
                ("company_id", "=", self.company_id.id),
            ], limit=1)
            if existing:
                existing.write({"status": line.status})
            else:
                Attendance.create({
                    "employee_id": line.employee_id.id,
                    "date": self.date,
                    "company_id": self.company_id.id,
                    "status": line.status,
                })
        return {
            "type": "ir.actions.act_window",
            "name": _("Attendance"),
            "res_model": "diamond.attendance",
            "view_mode": "list,form",
            "domain": [
                ("date", "=", self.date),
                ("company_id", "=", self.company_id.id),
            ],
            "target": "current",
        }


class DiamondAttendanceBatchWizardLine(models.TransientModel):
    _name = "diamond.attendance.batch.wizard.line"
    _description = "Mark Daily Attendance Line"

    wizard_id = fields.Many2one(
        "diamond.attendance.batch.wizard", required=True, ondelete="cascade",
    )
    employee_id = fields.Many2one("diamond.employee", string="Employee", required=True)
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
