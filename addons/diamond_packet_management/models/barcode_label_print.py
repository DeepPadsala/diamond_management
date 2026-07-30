from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DiamondBarcodeLabelPrintService(models.AbstractModel):
    """Build packet barcode label data and open the HTML print page."""

    _name = "diamond.barcode.label.print.service"
    _description = "Barcode Label Print Service"

    BARCODE_REPORT_XMLID = "diamond_packet_management.action_report_diamond_packet_barcode_label"

    @api.model
    def _fmt_date(self, dt):
        """Format datetime/date as DD/MM for the label."""
        if not dt:
            return ""
        if isinstance(dt, str):
            dt = fields.Datetime.to_datetime(dt) if " " in dt else fields.Date.to_date(dt)
        # Date has no time — format directly
        if hasattr(dt, "hour"):
            local = fields.Datetime.context_timestamp(self, dt)
            return local.strftime("%d/%m")
        return dt.strftime("%d/%m")

    @api.model
    def build_labels(self, inward):
        labels = []
        for line in inward.line_ids:
            packet = line.packet_id
            if not packet or not packet.barcode:
                continue
            labels.append(self._build_label_from_packet(
                packet,
                polish_cts=line.expected_cts or packet.expected_cts or 0.0,
                inward_no=inward.name or "",
                company_name=inward.company_id.name or "",
                date_value=inward.date,
                party=inward.ledger_id.code or inward.ledger_id.name or "",
            ))
        return labels

    @api.model
    def build_packet_labels(self, packets):
        labels = []
        for packet in packets:
            if not packet.barcode:
                continue
            party = ""
            if packet.current_holder_id:
                party = packet.current_holder_id.code or packet.current_holder_id.name or ""
            elif packet.inward_id and packet.inward_id.ledger_id:
                party = (
                    packet.inward_id.ledger_id.code
                    or packet.inward_id.ledger_id.name
                    or ""
                )
            inward_no = packet.inward_id.name if packet.inward_id else ""
            labels.append(self._build_label_from_packet(
                packet,
                polish_cts=packet.expected_cts or 0.0,
                inward_no=inward_no,
                company_name=packet.company_id.name or "",
                date_value=packet.inward_date or packet.create_date,
                party=party,
            ))
        return labels

    @api.model
    def _build_label_from_packet(
        self, packet, polish_cts=0.0, inward_no="", company_name="",
        date_value=None, party="",
    ):
        rough_cts = packet.org_cts or 0.0
        cps_parts = [
            packet.shape_id.code or "",
            packet.color_id.code or "",
            packet.clarity_id.code or "",
        ]
        cps = "  ".join(p for p in cps_parts if p)

        return {
            "barcode": packet.barcode,
            "packet_no": packet.packet_no or "",
            "user_packet_no": packet.user_packet_no or "",
            "kapan_no": packet.kapan_no or "",
            "inward_no": inward_no,
            "company_name": company_name,
            "date": self._fmt_date(date_value),
            "rough_cts": rough_cts,
            "polish_cts": polish_cts or 0.0,
            "shape": packet.shape_id.code or "",
            "color": packet.color_id.code or "",
            "clarity": packet.clarity_id.code or "",
            "cps": cps,
            "party": party,
        }

    @api.model
    def print_inward_labels(self, inward):
        inward.ensure_one()
        if not self.build_labels(inward):
            raise UserError(_("No barcodes to print for this inward entry."))
        BrowserPrint = self.env["diamond.browser.print.service"]
        url = "/diamond/barcode_labels_html/%d" % inward.id
        return BrowserPrint.print_html_url(url)

    @api.model
    def print_packet_labels(self, packets):
        packets = packets.filtered(lambda p: p.barcode)
        if not packets:
            raise UserError(_("No barcodes to print for the selected packet(s)."))
        BrowserPrint = self.env["diamond.browser.print.service"]
        ids_str = ",".join(str(i) for i in packets.ids)
        url = "/diamond/barcode_labels_packet/%s" % ids_str
        return BrowserPrint.print_html_url(url)
