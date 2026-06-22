from odoo import fields, models


class DiamondCut(models.Model):
    """Cut grade master (EX, VG, GD, FR, PR)."""

    _name = "diamond.cut"
    _description = "Diamond Cut Master"
    _inherit = "diamond.master.mixin"

    grade_value = fields.Integer(string="Grade Value")
