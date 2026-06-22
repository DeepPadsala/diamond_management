from odoo import fields, models


class DiamondColor(models.Model):
    """Diamond color grade master (D, E, F, G, H, ...)."""

    _name = "diamond.color"
    _description = "Diamond Color Master"
    _inherit = "diamond.master.mixin"

    grade_value = fields.Integer(string="Grade Value", help="Numeric ranking; lower = whiter (D=1, E=2, ...). Used for price-list lookups.")
    is_fancy_color = fields.Boolean(string="Fancy Color", default=False)
