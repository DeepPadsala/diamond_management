from odoo import _, fields, models


class DiamondJangadPrintWizard(models.TransientModel):
    """Ask whether to print thermal jangad slips after issue/receive."""

    _name = "diamond.jangad.print.wizard"
    _description = "Print Jangad Wizard"

    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    movement_type = fields.Selection(
        [("issue", "Issue"), ("receive", "Receive")],
        required=True,
    )
    slip_count = fields.Integer(readonly=True)
    summary = fields.Char(readonly=True)

    def action_print_jangad(self):
        self.ensure_one()
        return self.env["diamond.jangad.print.service"].print_wizard_slips(self)

    def action_skip_print(self):
        self.ensure_one()
        doc = self.env[self.res_model].browse(self.res_id)
        if not doc.exists():
            return {"type": "ir.actions.act_window_close"}
        return {"type": "ir.actions.act_window_close"}
