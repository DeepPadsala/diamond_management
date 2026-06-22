from odoo import fields, models


class DiamondProduct(models.Model):
    """Product master (rough lots, polished SKUs, jewellery, etc.).

    Sits above ``diamond.packet`` — many packets can belong to one product.
    """

    _name = "diamond.product"
    _description = "Diamond Product Master"
    _inherit = "diamond.master.mixin"

    product_type = fields.Selection(
        selection=[
            ("rough", "Rough"),
            ("polished", "Polished"),
            ("mixed", "Mixed Lot"),
            ("jewellery", "Jewellery"),
            ("other", "Other"),
        ],
        string="Type",
        default="polished",
        required=True,
    )
    default_shape_id = fields.Many2one("diamond.shape", string="Default Shape")
    default_color_id = fields.Many2one("diamond.color", string="Default Color")
    default_clarity_id = fields.Many2one("diamond.clarity", string="Default Clarity")
    hs_code = fields.Char(string="HS / HSN Code")
    standard_cost = fields.Float(string="Standard Cost / Cts", digits=(12, 2))
