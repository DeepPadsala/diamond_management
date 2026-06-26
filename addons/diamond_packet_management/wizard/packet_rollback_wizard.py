from odoo import _, api, fields, models


class DiamondPacketRollbackWizard(models.TransientModel):
    """Confirm rollback of the latest issue/receive per selected packet."""

    _name = "diamond.packet.rollback.wizard"
    _description = "Rollback Last Transaction"

    packet_ids = fields.Many2many("diamond.packet", string="Packets", required=True)
    line_ids = fields.One2many(
        "diamond.packet.rollback.wizard.line", "wizard_id", string="Preview",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context or {}
        active_ids = ctx.get("active_ids") or (
            [ctx["active_id"]] if ctx.get("active_id") else []
        )
        if ctx.get("active_model") == "diamond.packet" and active_ids:
            packets = self.env["diamond.packet"].browse(active_ids).exists()
            res["packet_ids"] = [(6, 0, packets.ids)]
            res["line_ids"] = [
                (0, 0, {
                    "packet_id": p.id,
                    "transaction_label": p.preview_latest_transaction(),
                })
                for p in packets
            ]
        return res

    def action_confirm_rollback(self):
        self.ensure_one()
        return self.packet_ids.action_rollback_last_transaction()


class DiamondPacketRollbackWizardLine(models.TransientModel):
    _name = "diamond.packet.rollback.wizard.line"
    _description = "Rollback Preview Line"

    wizard_id = fields.Many2one("diamond.packet.rollback.wizard", required=True, ondelete="cascade")
    packet_id = fields.Many2one("diamond.packet", string="Packet", required=True)
    barcode = fields.Char(related="packet_id.barcode", string="Barcode")
    transaction_label = fields.Char(string="Latest Transaction", readonly=True)
