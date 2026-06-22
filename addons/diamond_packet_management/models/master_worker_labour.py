from odoo import api, fields, models


class DiamondWorkerLabour(models.Model):
    """Worker labour rate card per process and weight bracket — used for monthly salary."""

    _name = "diamond.worker.labour"
    _description = "Worker Labour Rate"
    _order = "company_id, process_id, from_cts"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    process_id = fields.Many2one("diamond.process", string="Process", required=True, index=True)
    packet_type = fields.Char(string="Packet Type", help="Optional packet type filter.")
    from_cts = fields.Float(string="From Weight", digits=(8, 4), required=True)
    to_cts = fields.Float(string="To Weight", digits=(8, 4), required=True)
    rate = fields.Float(string="Rate", digits=(12, 2), required=True)
    multiply_by = fields.Boolean(string="Multiply By", default=True,
                                 help="When checked, rate is multiplied by quantity or weight loss.")
    multiply_by_weight_loss = fields.Boolean(
        string="Weight Loss",
        help="When checked with Multiply By, amount = Rate × Weight Loss. "
             "Otherwise amount = Rate × Quantity (pcs).",
    )
    note = fields.Text(string="Note")
    active = fields.Boolean(string="Active", default=True)
    write_uid = fields.Many2one("res.users", string="Updated By", readonly=True)
    write_date = fields.Datetime(string="Updated On", readonly=True)

    _sql_constraints = [
        (
            "worker_process_weight_uniq",
            "unique(process_id, from_cts, to_cts, company_id)",
            "A rate already exists for this process and weight range.",
        ),
    ]

    @api.onchange("multiply_by")
    def _onchange_multiply_by(self):
        if not self.multiply_by:
            self.multiply_by_weight_loss = False
