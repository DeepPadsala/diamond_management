from odoo import fields, models


class DiamondPolish(models.Model):
    """Polish grade master (EX, VG, GD, FR, PR)."""

    _name = "diamond.polish"
    _description = "Diamond Polish Master"
    _inherit = "diamond.master.mixin"

    grade_value = fields.Integer(string="Grade Value")
