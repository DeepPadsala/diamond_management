from odoo import fields, models


class DiamondPartyType(models.Model):
    """Party role / type — a ledger can have several (customer + jobworker, …)."""

    _name = "diamond.party.type"
    _description = "Diamond Party Type"
    _order = "sequence, name"
    _rec_name = "name"

    code = fields.Char(string="Code", required=True, index=True)
    name = fields.Char(string="Name", required=True, translate=True)
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Party type code must be unique."),
    ]
