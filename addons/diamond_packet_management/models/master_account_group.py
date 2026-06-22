from odoo import fields, models


class DiamondAccountGroup(models.Model):
    """Account group master used to classify ledgers (Sundry Debtor, Creditor, ...)."""

    _name = "diamond.account.group"
    _description = "Diamond Account Group"
    _inherit = "diamond.master.mixin"

    nature = fields.Selection(
        selection=[
            ("debtor", "Sundry Debtor"),
            ("creditor", "Sundry Creditor"),
            ("expense", "Expense"),
            ("income", "Income"),
            ("asset", "Asset"),
            ("liability", "Liability"),
            ("other", "Other"),
        ],
        string="Nature",
        default="other",
        required=True,
    )
