from odoo import _, api, fields, models
from odoo.exceptions import UserError


_ISSUE_MODEL_BY_RECEIVE = {
    "diamond.process.receive": "diamond.process.issue",
    "diamond.factory.receive": "diamond.factory.issue",
    "diamond.jobwork.receive": "diamond.jobwork.issue",
    "diamond.hpht.receive": "diamond.hpht.issue",
}

_DOC_KIND = {
    "diamond.process.issue": "process",
    "diamond.process.receive": "process",
    "diamond.factory.issue": "factory",
    "diamond.factory.receive": "factory",
    "diamond.jobwork.issue": "jobwork",
    "diamond.jobwork.receive": "jobwork",
    "diamond.hpht.issue": "hpht",
    "diamond.hpht.receive": "hpht",
}


class DiamondJangadPrintService(models.AbstractModel):
    """Build thermal jangad slip data and open the PDF in the browser."""

    _name = "diamond.jangad.print.service"
    _description = "Jangad Print Service"

    @api.model
    def open_print_prompt(self, res_model, res_id, movement_type):
        """Ask whether to print jangad; Yes opens PDF for manual printer selection."""
        doc = self.env[res_model].browse(res_id)
        if not doc.exists():
            return {"type": "ir.actions.act_window_close"}
        slips = self.build_slips(doc, movement_type)
        if not slips:
            return True
        wizard = self.env["diamond.jangad.print.wizard"].create({
            "res_model": res_model,
            "res_id": res_id,
            "movement_type": movement_type,
            "slip_count": len(slips),
            "summary": self._build_summary(doc, movement_type, len(slips)),
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Print Jangad?"),
            "res_model": "diamond.jangad.print.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.model
    def print_document_slips(self, doc, movement_type):
        """Open browser print dialog for jangad (no PDF tab)."""
        doc.ensure_one()
        slips = self.build_slips(doc, movement_type)
        if not slips:
            return True
        wizard = self.env["diamond.jangad.print.wizard"].create({
            "res_model": doc._name,
            "res_id": doc.id,
            "movement_type": movement_type,
            "slip_count": len(slips),
            "summary": self._build_summary(doc, movement_type, len(slips)),
        })
        return self.print_wizard_slips(wizard)

    @api.model
    def _build_summary(self, doc, movement_type, slip_count):
        kind = _DOC_KIND.get(doc._name, "")
        label = {
            "process": _("Process"),
            "factory": _("Factory"),
            "jobwork": _("Jobwork"),
            "hpht": _("HPHT"),
        }.get(kind, doc._description)
        action = _("Issue") if movement_type == "issue" else _("Receive")
        return _("%(action)s — %(label)s (%(count)s slip(s))") % {
            "action": action,
            "label": label,
            "count": slip_count,
        }

    @api.model
    def build_slips(self, doc, movement_type):
        slips = []
        for line in doc.line_ids:
            slips.append(self._build_slip(doc, line, movement_type))
        return slips

    @api.model
    def _format_dt(self, dt):
        if not dt:
            return ""
        local_dt = fields.Datetime.context_timestamp(self, dt)
        return local_dt.strftime("%d/%m/%Y %H:%M:%S")

    @api.model
    def _packet_label(self, packet):
        return packet.user_packet_no or packet.kapan_no or packet.packet_no or packet.barcode or ""

    @api.model
    def _find_issue_doc(self, doc, line):
        issue_model = _ISSUE_MODEL_BY_RECEIVE.get(doc._name)
        if not issue_model:
            return self.env["diamond.process.issue"].browse()
        domain = [
            ("state", "=", "confirmed"),
            ("line_ids.packet_id", "=", line.packet_id.id),
            ("date", "<=", doc.date),
        ]
        if doc.process_id:
            domain.append(("process_id", "=", doc.process_id.id))
        if doc.employee_id:
            domain.append(("employee_id", "=", doc.employee_id.id))
        if doc.ledger_id:
            domain.append(("ledger_id", "=", doc.ledger_id.id))
        return self.env[issue_model].search(domain, order="date desc", limit=1)

    @api.model
    def _issue_weight(self, doc, line, movement_type):
        if movement_type == "issue":
            return getattr(line, "issue_cts", None) or line.cts or 0.0
        if getattr(line, "session_issue_cts", None):
            return line.session_issue_cts
        if getattr(line, "issue_cts", None):
            return line.issue_cts
        issue_doc = self._find_issue_doc(doc, line)
        if issue_doc:
            issue_line = issue_doc.line_ids.filtered(lambda l: l.packet_id == line.packet_id)[:1]
            if issue_line:
                return getattr(issue_line, "issue_cts", None) or issue_line.cts or 0.0
        received = line.cts or 0.0
        loss = getattr(line, "labour_loss_cts", None) or getattr(line, "loss_cts", None) or 0.0
        return received + loss if (received or loss) else (line.packet_id.rdy_cts or 0.0)

    @api.model
    def _loss_weight(self, line, movement_type):
        if movement_type == "issue":
            return 0.0
        if getattr(line, "labour_loss_cts", None) is not None:
            return line.labour_loss_cts
        if getattr(line, "loss_cts", None) is not None:
            return line.loss_cts
        issue_wt = self._issue_weight(line.doc_id, line, movement_type)
        return max(issue_wt - (line.cts or 0.0), 0.0)

    @api.model
    def _labour_rate_amount(self, doc, line, movement_type):
        LabourEntry = self.env["diamond.labour.entry"]
        if movement_type == "receive":
            entry_types = ["worker"] if doc._name == "diamond.factory.receive" else ["party"]
            for entry_type in entry_types:
                entry = LabourEntry.search([
                    ("receive_model", "=", doc._name),
                    ("receive_line_id", "=", line.id),
                    ("entry_type", "=", entry_type),
                ], limit=1)
                if entry:
                    return entry.rate, entry.amount
            if doc._name == "diamond.jobwork.receive" and line.labour_amount:
                return 0.0, line.labour_amount
        return 0.0, 0.0

    @api.model
    def _slip_title(self, doc, movement_type):
        kind = _DOC_KIND.get(doc._name, "")
        if kind == "factory":
            return _("Employee Return Print") if movement_type == "receive" else _("Employee Issue Print")
        labels = {
            ("process", "issue"): _("Process Issue Print"),
            ("process", "receive"): _("Process Return Print"),
            ("jobwork", "issue"): _("Jobwork Issue Print"),
            ("jobwork", "receive"): _("Jobwork Return Print"),
            ("hpht", "issue"): _("HPHT Issue Print"),
            ("hpht", "receive"): _("HPHT Return Print"),
        }
        return labels.get((kind, movement_type), _("Movement Print"))

    @api.model
    def _build_slip(self, doc, line, movement_type):
        kind = _DOC_KIND.get(doc._name, "")
        issue_wt = self._issue_weight(doc, line, movement_type)
        return_wt = line.cts or 0.0 if movement_type == "receive" else 0.0
        loss_wt = self._loss_weight(line, movement_type)
        issue_doc = self._find_issue_doc(doc, line) if movement_type == "receive" else doc
        issue_date = issue_doc.date if issue_doc else (doc.date if movement_type == "issue" else False)
        rate, amount = self._labour_rate_amount(doc, line, movement_type)
        process = doc.process_id
        return {
            "title": self._slip_title(doc, movement_type),
            "show_employee": bool(doc.employee_id),
            "emp_name": doc.employee_id.name or "",
            "emp_code": doc.employee_id.code or "",
            "show_party": bool(doc.ledger_id) and kind in ("jobwork", "hpht"),
            "party_name": doc.ledger_id.name or "",
            "party_code": doc.ledger_id.code or "",
            "packet_no": self._packet_label(line.packet_id),
            "issue_wt": issue_wt,
            "return_wt": return_wt,
            "loss_wt": loss_wt,
            "issue_date": self._format_dt(issue_date),
            "return_date": self._format_dt(doc.date) if movement_type == "receive" else "",
            "process": process.name if process else "",
            "rate": rate,
            "amount": amount,
            "doc_name": doc.name,
        }

    JANGAD_REPORT_XMLID = "diamond_packet_management.action_report_diamond_jangad"

    @api.model
    def print_wizard_slips(self, wizard):
        wizard.ensure_one()
        doc = self.env[wizard.res_model].browse(wizard.res_id)
        if not doc.exists():
            raise UserError(_("The source document no longer exists."))
        if not self.build_slips(doc, wizard.movement_type):
            raise UserError(_("No jangad slips to print."))
        BrowserPrint = self.env["diamond.browser.print.service"]
        url = "/diamond/jangad_html/%d" % wizard.id
        return BrowserPrint.print_html_url(
            url,
            next_action={"type": "ir.actions.act_window_close"},
        )
