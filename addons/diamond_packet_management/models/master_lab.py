from odoo import fields, models


class DiamondLab(models.Model):
    """Certification lab master (GIA, IGI, HRD, AGS, ...)."""

    _name = "diamond.lab"
    _description = "Diamond Lab Master"
    _inherit = "diamond.master.mixin"

    full_name = fields.Char(string="Full Name")
    website = fields.Char(string="Website")
