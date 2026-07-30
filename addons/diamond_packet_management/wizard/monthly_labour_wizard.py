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

    def _has_closed_document(self, model_name, month, partner_field, partner):
        """Return True when a confirmed or paid document already exists for the period."""
        Doc = self.env[model_name]
        base = self._document_domain(model_name, month, partner_field, partner)
        return bool(Doc.search_count(base + [("state", "in", ("confirmed", "paid"))]))

    def _find_or_reopen_document(self, model_name, month, partner_field, partner):
        """Return a draft billing document, reopening confirmed ones when needed."""
        Doc = self.env[model_name]
        base = self._document_domain(model_name, month, partner_field, partner)
        draft = Doc.search(base + [("state", "=", "draft")], order="id desc", limit=1)
        if draft:
            return draft, None
        confirmed = Doc.search(base + [("state", "=", "confirmed")], order="id desc", limit=1)
        if confirmed:
            confirmed.action_reopen_draft()
            return confirmed, None
        return Doc, "new"

    def action_generate(self):
        self.ensure_one()
        if not self.generate_party_invoices and not self.generate_salary_slips:
            raise UserError(_("Select at least one document type to generate."))

        month = int(self.period_month)
        touched_invoices = self.env["diamond.party.invoice"]
        touched_slips = self.env["diamond.salary.slip"]

        if self.generate_party_invoices:
            touched_invoices, _added = self._generate_party_invoices(month)
        if self.generate_salary_slips:
            touched_slips, _added = self._generate_salary_slips(month)

        if not touched_invoices and not touched_slips:
            Entry = self.env["diamond.labour.entry"]
            open_party = Entry.search_count(self._billable_party_domain(month))
            open_worker = Entry.search_count(self._billable_worker_domain(month))
            if open_party or open_worker:
                raise UserError(_(
                    "Labour entries exist but could not be billed. "
                    "Open existing draft invoices or salary slips for this month."
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
            raise UserError(_(
                "No open labour entries or fixed-salary employees found for the selected month."
            ))

        month = int(self.period_month)
        if touched_invoices and touched_slips:
            return self._open_documents_action(
                _("Monthly Labour Documents"),
                "diamond.party.invoice",
                touched_invoices,
                month,
            )
        if touched_invoices:
            return self._open_documents_action(
                _("Party Invoices"), "diamond.party.invoice", touched_invoices, month,
            )
        return self._open_documents_action(
            _("Salary Slips"), "diamond.salary.slip", touched_slips, month,
        )

    def _open_documents_action(self, name, model, records, month):
        """Open billing documents for the period — include prior paid slips/invoices too."""
        domain = [
            ("period_month", "=", str(month)),
            ("period_year", "=", self.period_year),
            ("company_id", "=", self.company_id.id),
            ("state", "!=", "cancelled"),
        ]
        if model == "diamond.salary.slip":
            domain.append(("employee_id", "in", records.mapped("employee_id").ids))
        else:
            domain.append(("ledger_id", "in", records.mapped("ledger_id").ids))
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": "list,form",
            "domain": domain,
            "target": "current",
        }

    def _generate_party_invoices(self, month):
        Entry = self.env["diamond.labour.entry"]
        Invoice = self.env["diamond.party.invoice"]
        entries = Entry.search(self._billable_party_domain(month))
        touched = Invoice
        lines_added = 0

        for ledger in entries.mapped("ledger_id"):
            ledger_entries = entries.filtered(lambda e: e.ledger_id == ledger)
            invoice, status = self._find_or_reopen_document(
                "diamond.party.invoice", month, "ledger_id", ledger,
            )
            if status == "new":
                vals = {
                    "company_id": self.company_id.id,
                    "ledger_id": ledger.id,
                    "period_month": str(month),
                    "period_year": self.period_year,
                    "date": self.invoice_date,
                }
                if self._has_closed_document("diamond.party.invoice", month, "ledger_id", ledger):
                    vals["is_supplemental"] = True
                invoice = Invoice.create(vals)
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

        return touched, lines_added

    def _generate_salary_slips(self, month):
        Entry = self.env["diamond.labour.entry"]
        Slip = self.env["diamond.salary.slip"]
        Employee = self.env["diamond.employee"]
        entries = Entry.search(self._billable_worker_domain(month))
        touched = Slip
        lines_added = 0

        # Piece-rate workers with open labour entries
        piece_employees = entries.mapped("employee_id")
        # Fixed-salary workers (attendance-based), even with no labour entries
        fixed_employees = Employee.search([
            ("company_id", "=", self.company_id.id),
            ("active", "=", True),
            ("salary_type", "=", "fixed"),
            ("monthly_salary", ">", 0),
        ])
        all_employees = piece_employees | fixed_employees

        for employee in all_employees:
            emp_entries = entries.filtered(lambda e: e.employee_id == employee)
            # Skip piece-rate employees with nothing to bill this pass
            if employee.salary_type != "fixed" and not emp_entries:
                continue

            slip, status = self._find_or_reopen_document(
                "diamond.salary.slip", month, "employee_id", employee,
            )
            if status == "new":
                vals = {
                    "company_id": self.company_id.id,
                    "employee_id": employee.id,
                    "period_month": str(month),
                    "period_year": self.period_year,
                    "date": self.slip_date,
                }
                if self._has_closed_document("diamond.salary.slip", month, "employee_id", employee):
                    vals["is_supplemental"] = True
                slip = Slip.create(vals)
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

            if employee.salary_type == "fixed":
                added = self._ensure_fixed_salary_line(slip, employee, month)
                lines_added += added

            slip.action_apply_withdrawals()

        return touched, lines_added

    def _ensure_fixed_salary_line(self, slip, employee, month):
        """Create or refresh the attendance-based fixed salary line on the slip."""
        Attendance = self.env["diamond.attendance"]
        paid_days = Attendance.paid_days_for_period(employee, self.period_year, month)
        days_in_month = Attendance.calendar_days_in_month(self.period_year, month)
        if days_in_month <= 0:
            return 0
        amount = round((employee.monthly_salary or 0.0) * (paid_days / days_in_month), 2)
        note = _(
            "Fixed salary: %(paid).2f / %(total)d paid days × %(salary).2f"
        ) % {
            "paid": paid_days,
            "total": days_in_month,
            "salary": employee.monthly_salary or 0.0,
        }
        Line = self.env["diamond.salary.slip.line"]
        existing = Line.search([
            ("slip_id", "=", slip.id),
            ("is_fixed_salary", "=", True),
        ], limit=1)
        vals = {
            "slip_id": slip.id,
            "is_fixed_salary": True,
            "date": fields.Datetime.to_datetime(
                fields.Date.to_date(f"{self.period_year:04d}-{month:02d}-01")
            ),
            "pcs": 0,
            "cts": 0.0,
            "loss_cts": 0.0,
            "rate": employee.monthly_salary or 0.0,
            "amount": amount,
            "note": note,
        }
        if existing:
            existing.write({
                "rate": vals["rate"],
                "amount": vals["amount"],
                "note": vals["note"],
            })
            return 0
        Line.create(vals)
        return 1
