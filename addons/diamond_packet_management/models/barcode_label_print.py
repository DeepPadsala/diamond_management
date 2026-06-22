from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DiamondBarcodeLabelPrintService(models.AbstractModel):
    """Build packet barcode label data and open the HTML print page."""

    _name = "diamond.barcode.label.print.service"
    _description = "Barcode Label Print Service"

    BARCODE_REPORT_XMLID = "diamond_packet_management.action_report_diamond_packet_barcode_label"

    @api.model
    def _fmt_date(self, dt):
        """Format datetime as DD/MM for the label."""
        if not dt:
            return ""
        local = fields.Datetime.context_timestamp(self, dt)
        return local.strftime("%d/%m")

    @api.model
    def build_labels(self, inward):
        labels = []
        for line in inward.line_ids:
            packet = line.packet_id
            if not packet or not packet.barcode:
                continue
            labels.append(self._build_label(inward, line, packet))
        return labels

    @api.model
    def _build_label(self, inward, line, packet):
        # Rough weight from packet (as received in inward).
        rough_cts = packet.org_cts or 0.0
        # Polish / expected weight from the inward line (what was expected/entered).
        polish_cts = line.expected_cts or packet.expected_cts or 0.0

        cps_parts = [
            packet.shape_id.code or "",
            packet.color_id.code or "",
            packet.clarity_id.code or "",
        ]
        cps = "  ".join(p for p in cps_parts if p)

        return {
            # Identification
            "barcode": packet.barcode,
            "packet_no": packet.packet_no or "",
            "user_packet_no": packet.user_packet_no or "",
            "kapan_no": packet.kapan_no or "",
            "inward_no": inward.name or "",
            # Company / date header
            "company_name": inward.company_id.name or "",
            "date": self._fmt_date(inward.date),
            # Weights
            "rough_cts": rough_cts,
            "polish_cts": polish_cts,
            # Stone info
            "shape": packet.shape_id.code or "",
            "color": packet.color_id.code or "",
            "clarity": packet.clarity_id.code or "",
            "cps": cps,
            "party": inward.ledger_id.code or inward.ledger_id.name or "",
        }

    @api.model
    def print_inward_labels(self, inward):
        inward.ensure_one()
        if not self.build_labels(inward):
            raise UserError(_("No barcodes to print for this inward entry."))
        BrowserPrint = self.env["diamond.browser.print.service"]
        url = "/diamond/barcode_labels_html/%d" % inward.id
        return BrowserPrint.print_html_url(url)
