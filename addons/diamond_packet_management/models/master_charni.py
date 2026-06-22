from odoo import fields, models


class DiamondCharni(models.Model):
    """Sieve / Charni master (size buckets used to group small diamonds)."""

    _name = "diamond.charni"
    _description = "Diamond Charni / Sieve Master"
    _inherit = "diamond.master.mixin"

    size_from_mm = fields.Float(string="Size From (mm)", digits=(8, 3))
    size_to_mm = fields.Float(string="Size To (mm)", digits=(8, 3))
    weight_pp_cts = fields.Float(string="Approx Wt / Pc (cts)", digits=(8, 4))
