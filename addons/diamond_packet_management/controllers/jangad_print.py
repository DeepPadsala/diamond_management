from odoo import http
from odoo.http import request


class DiamondJangadPrintController(http.Controller):
    """Serve jangad slips as a printable HTML page (ngrok-safe)."""

    @http.route(
        "/diamond/jangad_html/<int:wizard_id>",
        auth="user",
        type="http",
        methods=["GET"],
        csrf=False,
    )
    def jangad_slip_html(self, wizard_id, **kwargs):
        wizard = request.env["diamond.jangad.print.wizard"].browse(wizard_id)
        if not wizard.exists():
            return request.not_found()
        doc = request.env[wizard.res_model].browse(wizard.res_id)
        if not doc.exists():
            return request.not_found()
        service = request.env["diamond.jangad.print.service"]
        slips = service.build_slips(doc, wizard.movement_type)
        html = request.env["ir.qweb"]._render(
            "diamond_packet_management.tmpl_jangad_slip_print",
            {"slips": slips},
        )
        return request.make_response(
            html,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )
