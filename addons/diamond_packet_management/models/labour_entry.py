from odoo import _, api, fields, models


class DiamondLabourEntry(models.Model):
    """Labour accrual created when a process is completed (receive confirmed)."""

    _name = "diamond.labour.entry"
    _description = "Labour Entry"
    _order = "date desc, id desc"
    _rec_name = "display_name"

    company_id = fields.Many2one("res.company", required=True, index=True, default=lambda self: self.env.company)
    entry_type = fields.Selection(
        [("party", "Party Labour"), ("worker", "Worker Labour")],
        string="Type",
        required=True,
        index=True,
    )
    date = fields.Datetime(string="Date", required=True, index=True)
    period_month = fields.Integer(string="Month", compute="_compute_period", store=True, index=True)
    period_year = fields.Integer(string="Year", compute="_compute_period", store=True, index=True)

    ledger_id = fields.Many2one("diamond.ledger", string="Party", index=True)
    employee_id = fields.Many2one("diamond.employee", string="Worker", index=True)
    process_id = fields.Many2one("diamond.process", string="Process", required=True)
    packet_id = fields.Many2one("diamond.packet", string="Packet", required=True, ondelete="restrict")

    receive_model = fields.Char(string="Receive Model", index=True)
    receive_line_id = fields.Integer(string="Receive Line ID", index=True)
    receive_doc_name = fields.Char(string="Receive Doc")

    pcs = fields.Integer(string="Pcs")
    cts = fields.Float(string="Cts", digits=(12, 4))
    loss_cts = fields.Float(string="Loss Cts", digits=(12, 4))
    weight_cts = fields.Float(string="Bracket Weight", digits=(12, 4),
                              help="Weight used to find the rate bracket.")
    labour_weight_cts = fields.Float(
        string="Labour Weight", digits=(12, 4),
        help="Original labour weight for resumed factory processes.",
    )

    party_labour_id = fields.Many2one("diamond.party.labour", string="Party Rate Card", ondelete="set null")
    worker_labour_id = fields.Many2one("diamond.worker.labour", string="Worker Rate Card", ondelete="set null")
    rate = fields.Float(string="Rate", digits=(12, 2))
    multiply_by = fields.Boolean(string="Multiply By")
    multiply_by_weight_loss = fields.Boolean(string="Weight Loss")
    quantity_basis = fields.Selection(
        [
            ("quantity", "Quantity"),
            ("issue_cts", "Issue Cts"),
            ("receive_cts", "Receive Cts"),
            ("weight_loss", "Weight Loss"),
            ("flat", "Flat"),
        ],
        string="Basis",
    )
    amount = fields.Float(string="Amount", digits=(14, 2), required=True)

    state = fields.Selection(
        [("draft", "Open"), ("invoiced", "Invoiced"), ("paid", "Paid")],
        string="Status",
        default="draft",
        required=True,
        index=True,
    )
    party_invoice_id = fields.Many2one("diamond.party.invoice", string="Party Invoice", ondelete="set null")
    salary_slip_id = fields.Many2one("diamond.salary.slip", string="Salary Slip", ondelete="set null")

    display_name = fields.Char(compute="_compute_display_name", store=True)

    @api.depends("date")
    def _compute_period(self):
        for rec in self:
            if rec.date:
                dt = fields.Datetime.to_datetime(rec.date)
                rec.period_month = dt.month
                rec.period_year = dt.year
            else:
                rec.period_month = 0
                rec.period_year = 0

    @api.depends("entry_type", "ledger_id", "employee_id", "process_id", "packet_id", "amount")
    def _compute_display_name(self):
        for rec in self:
            who = rec.ledger_id.name if rec.entry_type == "party" else rec.employee_id.name
            rec.display_name = "%s — %s / %s — %s" % (
                dict(rec._fields["entry_type"].selection).get(rec.entry_type, ""),
                who or "-",
                rec.process_id.name or "-",
                rec.packet_id.packet_no or "-",
            )
