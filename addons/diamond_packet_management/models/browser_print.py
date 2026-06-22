from odoo import _, api, models
from odoo.exceptions import UserError


class DiamondBrowserPrintService(models.AbstractModel):
    """Open the browser print dialog — supports both PDF (via wkhtmltopdf)
    and HTML (loaded directly in an iframe, bypassing wkhtmltopdf entirely).

    Use ``print_html_url`` for barcode labels and jangad slips — the browser
    renders at the printer's native DPI and self-initiates print (ngrok-safe).
    Use ``print_report`` only for PDF reports opened locally.
    """

    _name = "diamond.browser.print.service"
    _description = "Browser Print Service"

    @api.model
    def form_action(self, res_model, res_id, name=None):
        """Return a window action Odoo 18 web client can open (requires ``views``)."""
        action = {
            "type": "ir.actions.act_window",
            "res_model": res_model,
            "res_id": res_id,
            "views": [[False, "form"]],
            "target": "current",
        }
        if name:
            action["name"] = name
        return action

    @api.model
    def print_html_url(self, url, next_action=None):
        """Return a client action that loads *url* in a hidden iframe and prints it.

        The browser renders and prints the HTML at the printer's native DPI —
        no wkhtmltopdf involved. Use this for barcode labels.
        """
        params = {"html_url": url}
        if next_action:
            params["next"] = next_action
        return {
            "type": "ir.actions.client",
            "tag": "diamond_browser_print_html",
            "name": _("Print Labels"),
            "params": params,
        }

    @api.model
    def print_report(self, report_xmlid, res_ids, data=None, next_action=None):
        """Return a client action that fetches the PDF and opens the print dialog."""
        report = self.env.ref(report_xmlid)
        if report.report_type != "qweb-pdf":
            raise UserError(_("Browser print supports PDF reports only."))
        ids = list(res_ids) if isinstance(res_ids, (list, tuple)) else [res_ids]
        if not ids:
            raise UserError(_("Nothing to print."))
        params = {
            "report_name": report.report_name,
            "doc_ids": ids,
            "title": report.name or _("Print"),
        }
        if data:
            params["data"] = data
        if next_action:
            params["next"] = next_action
        return {
            "type": "ir.actions.client",
            "tag": "diamond_browser_print",
            "name": report.name,
            "params": params,
        }
