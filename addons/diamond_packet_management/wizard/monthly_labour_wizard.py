from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DiamondMonthlyLabourWizard(models.TransientModel):
    """Generate monthly party invoices and worker salary slips from open labour entries."""

    _name = "diamond.monthly.labour.wizard"
    _description = "Monthly Labour Billing Wizard"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company,
    )
    period_month = fields.Selection(
        selection=[
            ("1", "January"), ("2", "February"), ("3", "March"), ("4", "April"),
            ("5", "May"), ("6", "June"), ("7", "July"), ("8", "August"),
            ("9", "September"), ("10", "October"), ("11", "November"), ("12", "December"),
        ],
        string="Month",
        required=True,
        default=lambda self: str(fields.Date.today().month),
    )
    period_year = fields.Integer(
        string="Year", required=True, default=lambda self: fields.Date.today().year,
    )
    generate_party_invoices = fields.Boolean(string="Generate Party Invoices", default=True)
    generate_salary_slips = fields.Boolean(string="Generate Salary Slips", default=True)
    invoice_date = fields.Date(string="Invoice Date", default=fields.Date.context_today)
    slip_date = fields.Date(string="Salary Slip Date", default=fields.Date.context_today)

    party_invoice_count = fields.Integer(compute="_compute_counts")
    salary_slip_count = fields.Integer(compute="_compute_counts")
    open_party_entry_count = fields.Integer(compute="_compute_counts")
    open_worker_entry_count = fields.Integer(compute="_compute_counts")

    def _period_domain(self, month):
        return [
            ("company_id", "=", self.company_id.id),
            ("period_month", "=", month),
            ("period_year", "=", self.period_year),
            ("state", "=", "draft"),
        ]

    def _billable_party_domain(self, month):
        return self._period_domain(month) + [
            ("entry_type", "=", "party"),
            ("party_invoice_id", "=", False),
        ]

    def _billable_worker_domain(self, month):
        return self._period_domain(month) + [
            ("entry_type", "=", "worker"),
            ("salary_slip_id", "=", False),
        ]

    @api.depends("company_id", "period_month", "period_year")
    def _compute_counts(self):
        Entry = self.env["diamond.labour.entry"]
        for rec in self:
            month = int(rec.period_month) if rec.period_month else 0
            party_entries = Entry.search(rec._billable_party_domain(month))
            worker_entries = Entry.search(rec._billable_worker_domain(month))
            rec.open_party_entry_count = len(party_entries)
            rec.open_worker_entry_count = len(worker_entries)
            rec.party_invoice_count = len(party_entries.mapped("ledger_id"))
            rec.salary_slip_count = len(worker_entries.mapped("employee_id"))

    def _document_domain(self, model_name, month, partner_field, partner):
        return [
            (partner_field, "=", partner.id),
            ("period_month", "=", str(month)),
            ("period_year", "=", self.period_year),
            ("company_id", "=", self.company_id.id),
        ]

    def _find_or_reopen_document(self, model_name, month, partner_field, partner):
        """Return a draft billing document, reopening confirmed ones when needed."""
        Doc = self.env[model_name]
        base = self._document_domain(model_name, month, partner_field, partner)
        draft = Doc.search(base + [("state", "=", "draft")], limit=1)
        if draft:
            return draft, None
        confirmed = Doc.search(base + [("state", "=", "confirmed")], limit=1)
        if confirmed:
            confirmed.action_reopen_draft()
            return confirmed, None
        if Doc.search_count(base + [("state", "=", "paid")]):
            return Doc, "paid"
        return Doc, "new"

    def action_generate(self):
        self.ensure_one()
        if not self.generate_party_invoices and not self.generate_salary_slips:
            raise UserError(_("Select at least one document type to generate."))

        month = int(self.period_month)
        touched_invoices = self.env["diamond.party.invoice"]
        touched_slips = self.env["diamond.salary.slip"]
        lines_added = 0
        blocked_parties = []
        blocked_employees = []

        if self.generate_party_invoices:
            touched_invoices, added, blocked_parties = self._generate_party_invoices(month)
            lines_added += added
        if self.generate_salary_slips:
            touched_slips, added, blocked_employees = self._generate_salary_slips(month)
            lines_added += added

        if blocked_parties or blocked_employees:
            details = []
            if blocked_parties:
                details.append(_("Parties with paid invoices: %s") % ", ".join(
                    blocked_parties.mapped("display_name")
                ))
            if blocked_employees:
                details.append(_("Workers with paid salary slips: %s") % ", ".join(
                    blocked_employees.mapped("display_name")
                ))
            if not touched_invoices and not touched_slips:
                raise UserError(_(
                    "Labour entries exist but could not be billed.\n\n%s\n\n"
                    "Paid documents cannot be reopened. Create a manual adjustment "
                    "or handle the new labour entries outside this wizard."
                ) % "\n".join(details))

        if not touched_invoices and not touched_slips:
            Entry = self.env["diamond.labour.entry"]
            open_party = Entry.search_count(self._billable_party_domain(month))
            open_worker = Entry.search_count(self._billable_worker_domain(month))
            if open_party or open_worker:
                raise UserError(_(
                    "Labour entries exist but could not be billed. "
                    "A confirmed or paid invoice/slip may already exist for this month. "
                    "Open the existing salary slip or party invoice and use "
                    "'Reopen for Withdrawals' / reopen draft, then run this wizard again."
                ))
            linked_party = Entry.search_count(
                self._period_domain(month) + [
                    ("entry_type", "=", "party"),
                    ("party_invoice_id", "!=", False),
                ]
            )
            linked_worker = Entry.search_count(
                self._period_domain(month) + [
                    ("entry_type", "=", "worker"),
                    ("salary_slip_id", "!=", False),
                ]
            )
            if linked_party or linked_worker:
                raise UserError(_(
                    "All open labour entries for this month are already on draft "
                    "invoices or salary slips. Open those documents to review them."
                ))
            raise UserError(_("No open labour entries found for the selected month."))

        if touched_invoices and touched_slips:
            return self._open_documents_action(
                _("Monthly Labour Documents"),
                "diamond.party.invoice",
                touched_invoices.ids,
            )
        if touched_invoices:
            return self._open_documents_action(
                _("Party Invoices"), "diamond.party.invoice", touched_invoices.ids,
            )
        return self._open_documents_action(
            _("Salary Slips"), "diamond.salary.slip", touched_slips.ids,
        )

    def _open_documents_action(self, name, model, ids):
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": "list,form",
            "domain": [("id", "in", ids)],
            "target": "current",
        }

    def _generate_party_invoices(self, month):
        Entry = self.env["diamond.labour.entry"]
        Invoice = self.env["diamond.party.invoice"]
        entries = Entry.search(self._billable_party_domain(month))
        touched = Invoice
        lines_added = 0
        blocked = self.env["diamond.ledger"]

        for ledger in entries.mapped("ledger_id"):
            ledger_entries = entries.filtered(lambda e: e.ledger_id == ledger)
            invoice, status = self._find_or_reopen_document(
                "diamond.party.invoice", month, "ledger_id", ledger,
            )
            if status == "paid":
                blocked |= ledger
                continue
            if status == "new":
                invoice = Invoice.create({
                    "company_id": self.company_id.id,
                    "ledger_id": ledger.id,
                    "period_month": str(month),
                    "period_year": self.period_year,
                    "date": self.invoice_date,
                })
            touched |= invoice

            for entry in ledger_entries:
                if entry.party_invoice_id:
                    continue
                if self.env["diamond.party.invoice.line"].search_count([
                    ("labour_entry_id", "=", entry.id),
                ]):
                    entry.party_invoice_id = invoice.id
                    continue
                self.env["diamond.party.invoice.line"].create({
                    "invoice_id": invoice.id,
                    "labour_entry_id": entry.id,
                    "date": entry.date,
                    "process_id": entry.process_id.id,
                    "packet_id": entry.packet_id.id,
                    "receive_doc_name": entry.receive_doc_name,
                    "pcs": entry.pcs,
                    "cts": entry.cts,
                    "loss_cts": entry.loss_cts,
                    "rate": entry.rate,
                    "amount": entry.amount,
                })
                entry.party_invoice_id = invoice.id
                lines_added += 1

        return touched, lines_added, blocked

    def _generate_salary_slips(self, month):
        Entry = self.env["diamond.labour.entry"]
        Slip = self.env["diamond.salary.slip"]
        entries = Entry.search(self._billable_worker_domain(month))
        touched = Slip
        lines_added = 0
        blocked = self.env["diamond.employee"]

        for employee in entries.mapped("employee_id"):
            emp_entries = entries.filtered(lambda e: e.employee_id == employee)
            slip, status = self._find_or_reopen_document(
                "diamond.salary.slip", month, "employee_id", employee,
            )
            if status == "paid":
                blocked |= employee
                continue
            if status == "new":
                slip = Slip.create({
                    "company_id": self.company_id.id,
                    "employee_id": employee.id,
                    "period_month": str(month),
                    "period_year": self.period_year,
                    "date": self.slip_date,
                })
            touched |= slip

            for entry in emp_entries:
                if entry.salary_slip_id:
                    continue
                if self.env["diamond.salary.slip.line"].search_count([
                    ("labour_entry_id", "=", entry.id),
                ]):
                    entry.salary_slip_id = slip.id
                    continue
                self.env["diamond.salary.slip.line"].create({
                    "slip_id": slip.id,
                    "labour_entry_id": entry.id,
                    "date": entry.date,
                    "process_id": entry.process_id.id,
                    "packet_id": entry.packet_id.id,
                    "receive_doc_name": entry.receive_doc_name,
                    "pcs": entry.pcs,
                    "cts": entry.cts,
                    "loss_cts": entry.loss_cts,
                    "rate": entry.rate,
                    "amount": entry.amount,
                })
                entry.salary_slip_id = slip.id
                lines_added += 1

            slip.action_apply_withdrawals()

        return touched, lines_added, blocked
