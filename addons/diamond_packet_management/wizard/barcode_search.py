from odoo import _, fields, models
from odoo.exceptions import UserError


class DiamondBarcodeSearch(models.TransientModel):
    """Quick lookup wizard — paste / scan a barcode and it opens the packet.

    A barcode gun typically acts as a keyboard: it types the barcode into
    the active input then presses Enter. We bind the *Search* button to
    Enter via the view's ``invisible`` modifier so the wizard auto-submits
    when the gun finishes scanning.
    """

    _name = "diamond.barcode.search"
    _description = "Barcode Search Wizard"

    barcode = fields.Char(string="Scan Barcode")
    party_barcode = fields.Char(string="Or Party Barcode")
    company_id = fields.Many2one(
        "res.company", string="Company", default=lambda self: self.env.company,
    )
    result_packet_id = fields.Many2one("diamond.packet", string="Found Packet", readonly=True)

    def action_search(self):
        self.ensure_one()
        if not (self.barcode or self.party_barcode):
            raise UserError(_("Scan or type a packet barcode (or a party barcode)."))
        Packet = self.env["diamond.packet"]
        if self.barcode:
            packet = Packet.find_by_barcode(self.barcode)
            if packet and packet.company_id != self.company_id:
                packet = Packet.browse()
        elif self.party_barcode:
            ledger = self.env["diamond.ledger"].search([
                ("barcode", "=ilike", self.party_barcode.strip()),
                ("company_id", "=", self.company_id.id),
            ], limit=1)
            if not ledger:
                raise UserError(_("No party found for barcode: %s") % self.party_barcode)
            domain = [
                ("company_id", "=", self.company_id.id),
                ("current_holder_id", "=", ledger.id),
            ]
            packet = Packet.search(domain, limit=1)
            if not packet:
                raise UserError(_("No packet found for the scanned code."))
            self.result_packet_id = packet.id
            return {
                "type": "ir.actions.act_window",
                "name": _("Packet"),
                "res_model": "diamond.packet",
                "view_mode": "form",
                "res_id": packet.id,
                "target": "current",
            }
        if not packet:
            raise UserError(_("No packet found for the scanned code."))
        self.result_packet_id = packet.id
        return {
            "type": "ir.actions.act_window",
            "name": _("Packet"),
            "res_model": "diamond.packet",
            "view_mode": "form",
            "res_id": packet.id,
            "target": "current",
        }
