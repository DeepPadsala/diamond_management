from odoo import fields, models


class DiamondPrice(models.Model):
    """Price master (Rapaport-style grid).

    Lookup by Shape × Color × Clarity × weight bucket.
    """

    _name = "diamond.price"
    _description = "Diamond Price Master"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, shape_id, color_id, clarity_id, from_cts"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    shape_id = fields.Many2one("diamond.shape", string="Shape", required=True, tracking=True)
    color_id = fields.Many2one("diamond.color", string="Color", required=True, tracking=True)
    clarity_id = fields.Many2one("diamond.clarity", string="Clarity", required=True, tracking=True)
    from_cts = fields.Float(string="From (cts)", digits=(8, 4), required=True, tracking=True)
    to_cts = fields.Float(string="To (cts)", digits=(8, 4), required=True, tracking=True)
    rate_per_cts = fields.Float(string="Rate / Cts", digits=(12, 2), required=True, tracking=True)
    discount_pct = fields.Float(string="Discount %", digits=(6, 2), tracking=True)
    valid_from = fields.Date(string="Valid From", tracking=True)
    valid_to = fields.Date(string="Valid To", tracking=True)
    active = fields.Boolean(string="Active", default=True, tracking=True)
    note = fields.Text(string="Note")
