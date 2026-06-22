from odoo import fields, models


class DiamondClarity(models.Model):
    """Diamond clarity master (FL, IF, VVS1, VVS2, VS1, VS2, SI1, SI2, I1...)."""

    _name = "diamond.clarity"
    _description = "Diamond Clarity Master"
    _inherit = "diamond.master.mixin"

    grade_value = fields.Integer(string="Grade Value", help="Numeric ranking; lower = cleaner (FL=1, IF=2, ...).")
