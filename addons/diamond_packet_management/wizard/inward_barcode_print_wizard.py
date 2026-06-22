from odoo import fields, models


class DiamondInwardBarcodePrintWizard(models.TransientModel):
    """Ask whether to print barcode labels after inward confirmation."""

    _name = "diamond.inward.barcode.print.wizard"
    _description = "Print Inward Barcode Labels Wizard"

    inward_id = fields.Many2one("diamond.inward", required=True, ondelete="cascade")
    label_count = fields.Integer(readonly=True)
    summary = fields.Char(readonly=True)

    def action_print_barcodes(self):
        self.ensure_one()
        return self.inward_id.action_print_barcodes()

    def action_skip_print(self):
        self.ensure_one()
        inward = self.inward_id
        if not inward.exists():
            return {"type": "ir.actions.act_window_close"}
        return {
            "type": "ir.actions.act_window",
            "name": inward._description,
            "res_model": "diamond.inward",
            "res_id": inward.id,
            "view_mode": "form",
            "target": "current",
        }
