from odoo import fields, models


class DiamondShape(models.Model):
    """Diamond shape master (Round, Princess, Oval, Marquise, ...)."""

    _name = "diamond.shape"
    _description = "Diamond Shape Master"
    _inherit = "diamond.master.mixin"

    short_code = fields.Char(string="Short Code", size=4, help="2-3 letter code shown in stock grid (e.g. RD, PR, OV).")
    is_fancy = fields.Boolean(string="Fancy Shape", default=False)
