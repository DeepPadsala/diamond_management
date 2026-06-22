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
