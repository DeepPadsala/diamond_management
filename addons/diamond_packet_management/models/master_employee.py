from odoo import api, fields, models


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

    @api.depends("code", "name")
    def _compute_display_name(self):
        for rec in self:
            if rec.code and rec.name:
                rec.display_name = f"{rec.code} - {rec.name}"
            else:
                rec.display_name = rec.code or rec.name or ""
