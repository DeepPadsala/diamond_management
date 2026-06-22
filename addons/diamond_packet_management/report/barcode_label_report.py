from odoo import models


def _get_barcode_label_report_values(env, docids, data=None):
    inwards = env["diamond.inward"].browse(docids)
    service = env["diamond.barcode.label.print.service"]
    labels = []
    for inward in inwards:
        labels.extend(service.build_labels(inward))
    company = inwards[:1].company_id if inwards else env.company
    return {
        "doc_ids": docids,
        "doc_model": "diamond.inward",
        "docs": inwards,
        "labels": labels,
        "company": company,
    }


class ReportDiamondPacketBarcodeLabel(models.AbstractModel):
    _name = "report.diamond_packet_management.report_packet_barcode_label"
    _description = "Packet Barcode Label Report"

    def _get_report_values(self, docids, data=None):
        return _get_barcode_label_report_values(self.env, docids, data)


class ReportDiamondPacketBarcodeLabelZpl(models.AbstractModel):
    _name = "report.diamond_packet_management.pkt_barcode_zpl"
    _description = "Packet Barcode Label ZPL Report"

    def _get_report_values(self, docids, data=None):
        return _get_barcode_label_report_values(self.env, docids, data)
