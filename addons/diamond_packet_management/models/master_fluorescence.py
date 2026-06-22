from odoo import fields, models


class DiamondFluorescence(models.Model):
    """Fluorescence master (None, Faint, Medium, Strong, Very Strong)."""

    _name = "diamond.fluorescence"
    _description = "Diamond Fluorescence Master"
    _inherit = "diamond.master.mixin"

    grade_value = fields.Integer(string="Grade Value")
