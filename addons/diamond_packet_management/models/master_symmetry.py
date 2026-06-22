from odoo import fields, models


class DiamondSymmetry(models.Model):
    """Symmetry grade master (EX, VG, GD, FR, PR)."""

    _name = "diamond.symmetry"
    _description = "Diamond Symmetry Master"
    _inherit = "diamond.master.mixin"

    grade_value = fields.Integer(string="Grade Value")
