from odoo import api, fields, models


class DiamondMasterMixin(models.AbstractModel):
    """Shared base for every short master (Shape, Color, Clarity, etc.).

    Provides: code + name + sequence + active flag + per-company isolation.
    Inheriting models only need to set ``_name`` and ``_description`` and
    optionally add their own fields.
    """

    _name = "diamond.master.mixin"
    _description = "Diamond Master Mixin"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "code"
    _order = "sequence, code, id"

    code = fields.Char(string="Code", required=True, index=True, size=16, tracking=True)
    name = fields.Char(string="Name", required=True, translate=False, tracking=True)
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(string="Active", default=True, tracking=True)
    note = fields.Text(string="Note")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(code, company_id)",
            "Code must be unique per company.",
        ),
    ]

    @api.depends("code")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.code or ""

    @api.model
    def _name_search(self, name="", domain=None, operator="ilike", limit=100, order=None):
        domain = list(domain or [])
        if name:
            domain = ["|", ("code", operator, name), ("name", operator, name)] + domain
        return self._search(domain, limit=limit, order=order)
