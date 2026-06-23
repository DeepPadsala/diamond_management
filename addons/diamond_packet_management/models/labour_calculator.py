from odoo import models


class DiamondLabourCalculator(models.AbstractModel):
    """Shared labour rate lookup and amount calculation."""

    _name = "diamond.labour.calculator"
    _description = "Diamond Labour Calculator"

    def _weight_in_bracket(self, weight_cts, from_cts, to_cts):
        """Return True if weight falls in [from_cts, to_cts] bracket."""
        low = from_cts or 0.0
        high = to_cts if to_cts else float("inf")
        return low <= weight_cts <= high

    def _find_party_labour_rate(self, ledger, process, weight_cts, company=None):
        """Find matching party labour rate for party + process + weight."""
        if not ledger or not process:
            return self.env["diamond.party.labour"]
        company = company or self.env.company
        domain = [
            ("ledger_id", "=", ledger.id),
            ("process_id", "=", process.id),
            ("company_id", "=", company.id),
            ("active", "=", True),
        ]
        candidates = self.env["diamond.party.labour"].search(domain, order="from_cts")
        for rate in candidates:
            if self._weight_in_bracket(weight_cts, rate.from_cts, rate.to_cts):
                return rate
        return self.env["diamond.party.labour"]

    def _find_worker_labour_rate(self, process, weight_cts, company=None):
        """Find matching worker labour rate for process + weight."""
        if not process:
            return self.env["diamond.worker.labour"]
        company = company or self.env.company
        domain = [
            ("process_id", "=", process.id),
            ("company_id", "=", company.id),
            ("active", "=", True),
        ]
        candidates = self.env["diamond.worker.labour"].search(domain, order="from_cts")
        for rate in candidates:
            if self._weight_in_bracket(weight_cts, rate.from_cts, rate.to_cts):
                return rate
        return self.env["diamond.worker.labour"]

    def _compute_labour_amount(self, rate_record, issue_cts, loss_cts):
        """Calculate labour amount from rate card flags.

        Rate bracket uses receive weight (regular) or labour weight (resumed factory).
        - multiply_by + multiply_by_weight_loss: rate × weight loss
        - multiply_by without weight loss: rate × issue / labour weight
        - otherwise: flat rate
        """
        if not rate_record or not rate_record.rate:
            return 0.0
        if rate_record.multiply_by:
            if rate_record.multiply_by_weight_loss:
                return rate_record.rate * max(loss_cts or 0.0, 0.0)
            return rate_record.rate * max(issue_cts or 0.0, 0.0)
        return rate_record.rate

    def _get_packet_owner_party(self, packet):
        """Party that owns the packet (diamond provider)."""
        if packet.inward_id and packet.inward_id.ledger_id:
            return packet.inward_id.ledger_id
        return packet.current_holder_id

    def _labour_weight_cts(self, line):
        """Stored labour weight for factory resume cycles."""
        return getattr(line, "labour_weight_cts", None) or 0.0

    def _uses_stored_labour_weight(self, line):
        """True when labour uses the original process weight (resumed factory job)."""
        labour_weight = self._labour_weight_cts(line)
        segment_issue = getattr(line, "issue_cts", None) or 0.0
        return labour_weight > 0 and abs(labour_weight - segment_issue) > 0.0001

    def _issued_weight_cts(self, line):
        """Issued weight before receive (used as multiply factor for regular receives)."""
        if self._uses_stored_labour_weight(line):
            return self._labour_weight_cts(line)
        if getattr(line, "session_issue_cts", None):
            return line.session_issue_cts
        if getattr(line, "issue_cts", None):
            return line.issue_cts
        received = line.cts or 0.0
        loss = line.loss_cts or 0.0
        return received + loss if (received or loss) else (line.packet_id.rdy_cts or 0.0)

    def _receive_weight_cts(self, line):
        """Receive weight used to find the labour rate bracket (regular receives only)."""
        return line.cts or 0.0

    def _labour_bracket_weight(self, line):
        """Weight bracket for rate card lookup."""
        if self._uses_stored_labour_weight(line):
            return self._labour_weight_cts(line)
        return self._receive_weight_cts(line)

    def _effective_loss_cts(self, line):
        """Loss used for labour amount (cumulative for resumed factory processes)."""
        if getattr(line, "unprocessed", False):
            return 0.0
        if self._uses_stored_labour_weight(line):
            return max(self._labour_weight_cts(line) - (line.cts or 0.0), 0.0)
        if getattr(line, "labour_loss_cts", None) is not None:
            return line.labour_loss_cts
        return line.loss_cts or 0.0

    def _prepare_party_labour_vals(self, receive_doc, line, source_model, source_line_field):
        """Build vals for a party labour entry from a receive line."""
        packet = line.packet_id
        party = self._get_packet_owner_party(packet)
        process = receive_doc.process_id
        if not party or not process:
            return False

        bracket_weight = self._labour_bracket_weight(line)
        issue_cts = self._issued_weight_cts(line)
        rate = self._find_party_labour_rate(party, process, bracket_weight, receive_doc.company_id)
        if not rate:
            return False

        labour_loss = self._effective_loss_cts(line)
        amount = self._compute_labour_amount(rate, issue_cts, labour_loss)
        if not amount:
            return False

        qty_basis = "weight_loss" if rate.multiply_by_weight_loss else (
            "issue_cts" if rate.multiply_by else "flat"
        )
        return {
            "entry_type": "party",
            "company_id": receive_doc.company_id.id,
            "date": receive_doc.date,
            "ledger_id": party.id,
            "process_id": process.id,
            "packet_id": packet.id,
            "receive_model": source_model,
            "receive_line_id": line.id,
            "receive_doc_name": receive_doc.name,
            "pcs": line.pcs,
            "cts": line.cts,
            "loss_cts": labour_loss,
            "weight_cts": bracket_weight,
            "labour_weight_cts": self._labour_weight_cts(line) or issue_cts,
            "rate": rate.rate,
            "multiply_by": rate.multiply_by,
            "multiply_by_weight_loss": rate.multiply_by_weight_loss,
            "quantity_basis": qty_basis,
            "amount": amount,
            "party_labour_id": rate.id,
        }

    def _prepare_worker_labour_vals(self, receive_doc, line, source_model):
        """Build vals for a worker labour entry from a factory receive line."""
        employee = receive_doc.employee_id
        process = receive_doc.process_id
        if not employee or not process:
            return False

        bracket_weight = self._labour_bracket_weight(line)
        issue_cts = self._issued_weight_cts(line)
        rate = self._find_worker_labour_rate(process, bracket_weight, receive_doc.company_id)
        if not rate:
            return False

        labour_loss = self._effective_loss_cts(line)
        amount = self._compute_labour_amount(rate, issue_cts, labour_loss)
        if not amount:
            return False

        qty_basis = "weight_loss" if rate.multiply_by_weight_loss else (
            "issue_cts" if rate.multiply_by else "flat"
        )
        return {
            "entry_type": "worker",
            "company_id": receive_doc.company_id.id,
            "date": receive_doc.date,
            "employee_id": employee.id,
            "process_id": process.id,
            "packet_id": line.packet_id.id,
            "receive_model": source_model,
            "receive_line_id": line.id,
            "receive_doc_name": receive_doc.name,
            "pcs": line.pcs,
            "cts": line.cts,
            "loss_cts": labour_loss,
            "weight_cts": bracket_weight,
            "labour_weight_cts": self._labour_weight_cts(line) or issue_cts,
            "rate": rate.rate,
            "multiply_by": rate.multiply_by,
            "multiply_by_weight_loss": rate.multiply_by_weight_loss,
            "quantity_basis": qty_basis,
            "amount": amount,
            "worker_labour_id": rate.id,
        }

    def _create_labour_entries_from_receive(self, receive_doc, line_model_name, source_model, create_party=True, create_worker=False):
        """Create labour entries for all lines on a confirmed receive document."""
        LabourEntry = self.env["diamond.labour.entry"]
        created = LabourEntry
        labour_line_ids = self.env.context.get("factory_labour_line_ids")
        lines = receive_doc.line_ids
        if labour_line_ids:
            lines = lines.filtered(lambda l: l.id in labour_line_ids)
        for line in lines:
            if getattr(line, "unprocessed", False):
                continue
            vals_list = []
            if create_party:
                party_vals = self._prepare_party_labour_vals(receive_doc, line, source_model, "receive_line_id")
                if party_vals:
                    existing = LabourEntry.search([
                        ("receive_model", "=", source_model),
                        ("receive_line_id", "=", line.id),
                        ("entry_type", "=", "party"),
                    ], limit=1)
                    if not existing:
                        vals_list.append(party_vals)
            if create_worker:
                worker_vals = self._prepare_worker_labour_vals(receive_doc, line, source_model)
                if worker_vals:
                    existing = LabourEntry.search([
                        ("receive_model", "=", source_model),
                        ("receive_line_id", "=", line.id),
                        ("entry_type", "=", "worker"),
                    ], limit=1)
                    if not existing:
                        vals_list.append(worker_vals)
            if vals_list:
                created |= LabourEntry.create(vals_list)
            line_vals = {}
            party_entry = created.filtered(
                lambda e, lid=line.id: e.receive_line_id == lid and e.entry_type == "party"
            )[:1]
            worker_entry = created.filtered(
                lambda e, lid=line.id: e.receive_line_id == lid and e.entry_type == "worker"
            )[:1]
            if party_entry:
                line_vals["party_labour_amount"] = party_entry.amount
            if worker_entry:
                line_vals["worker_labour_amount"] = worker_entry.amount
            if line_vals and hasattr(line, "party_labour_amount"):
                line.write(line_vals)
        return created

    def _unlink_labour_entries_for_receive(self, receive_doc, source_model):
        """Remove draft labour entries when receive is cancelled."""
        entries = self.env["diamond.labour.entry"].search([
            ("receive_model", "=", source_model),
            ("receive_line_id", "in", receive_doc.line_ids.ids),
            ("state", "=", "draft"),
        ])
        entries.unlink()
