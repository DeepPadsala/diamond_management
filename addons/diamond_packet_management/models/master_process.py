from odoo import fields, models


class DiamondProcess(models.Model):
    """Process master (e.g. Sarine, Cutting, Polishing, HPHT, Repair, Final).

    Each process can be configured for default loss %, expected days,
    and whether it is performed in-house, by jobwork, or by HPHT vendor.
    """

    _name = "diamond.process"
    _description = "Diamond Process Master"
    _inherit = "diamond.master.mixin"

    process_type = fields.Selection(
        selection=[
            ("internal", "Internal / Factory"),
            ("jobwork", "Jobwork (Outside)"),
            ("hpht", "HPHT"),
            ("certify", "Certification"),
            ("other", "Other"),
        ],
        string="Process Type",
        default="internal",
        required=True,
    )
    expected_days = fields.Integer(string="Expected Days", default=1)
    expected_loss_pct = fields.Float(string="Expected Loss %", digits=(5, 2))
    sequence_no = fields.Integer(string="Workflow Step", help="Order in standard workflow.", default=10)
