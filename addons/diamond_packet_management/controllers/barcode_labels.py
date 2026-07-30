from odoo import http
from odoo.http import request


class DiamondBarcodeLabelController(http.Controller):
    """Serve barcode labels as a printable HTML page.

    Using HTML (instead of wkhtmltopdf PDF) lets the browser render
    barcode images with full-resolution nearest-neighbour scaling and
    respects ``image-rendering: pixelated`` — giving scannable bars.
    """

    @http.route(
        "/diamond/barcode_labels_html/<int:inward_id>",
        auth="user",
        type="http",
        methods=["GET"],
        csrf=False,
    )
    def barcode_labels_html(self, inward_id, **kwargs):
        inward = request.env["diamond.inward"].browse(inward_id)
        if not inward.exists():
            return request.not_found()
        service = request.env["diamond.barcode.label.print.service"]
        labels = service.build_labels(inward)
        html = request.env["ir.qweb"]._render(
            "diamond_packet_management.tmpl_barcode_labels_print",
            {"labels": labels},
        )
        return request.make_response(
            html,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    @http.route(
        "/diamond/barcode_labels_packet/<string:packet_ids>",
        auth="user",
        type="http",
        methods=["GET"],
        csrf=False,
    )
    def barcode_labels_packet(self, packet_ids, **kwargs):
        try:
            ids = [int(x) for x in packet_ids.split(",") if x.strip().isdigit()]
        except (TypeError, ValueError):
            return request.not_found()
        packets = request.env["diamond.packet"].browse(ids).exists()
        if not packets:
            return request.not_found()
        service = request.env["diamond.barcode.label.print.service"]
        labels = service.build_packet_labels(packets)
        html = request.env["ir.qweb"]._render(
            "diamond_packet_management.tmpl_barcode_labels_print",
            {"labels": labels},
        )
        return request.make_response(
            html,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )
