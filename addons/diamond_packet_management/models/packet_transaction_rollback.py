from odoo import _, api, fields, models
from odoo.exceptions import UserError


# Registry of confirmed movement line models (issue + receive).
_TRANSACTION_LINE_SPECS = [
    ("diamond.process.issue.line", "diamond.process.issue", "issue", "process", None),
    ("diamond.process.receive.line", "diamond.process.receive", "receive", "process", "diamond.process.receive"),
    ("diamond.factory.issue.line", "diamond.factory.issue", "issue", "factory", None),
    ("diamond.factory.receive.line", "diamond.factory.receive", "receive", "factory", "diamond.factory.receive"),
    ("diamond.jobwork.issue.line", "diamond.jobwork.issue", "issue", "jobwork", None),
    ("diamond.jobwork.receive.line", "diamond.jobwork.receive", "receive", "jobwork", None),
    ("diamond.hpht.issue.line", "diamond.hpht.issue", "issue", "hpht", None),
    ("diamond.hpht.receive.line", "diamond.hpht.receive", "receive", "hpht", "diamond.hpht.receive"),
]


class DiamondPacket(models.Model):
    _inherit = "diamond.packet"

    def _find_latest_confirmed_transaction(self):
        """Return the most recent confirmed issue/receive line for this packet."""
        self.ensure_one()
        candidates = []
        for line_model, doc_model, kind, movement, labour_source in _TRANSACTION_LINE_SPECS:
            lines = self.env[line_model].search([
                ("packet_id", "=", self.id),
                ("doc_id.state", "=", "confirmed"),
            ])
            for line in lines:
                doc = line.doc_id
                # write_date reflects confirm time; fall back to line create_date.
                confirmed_at = (
                    doc.write_date
                    or line.write_date
                    or line.create_date
                    or doc.create_date
                    or doc.date
                    or fields.Datetime.now()
                )
                # When timestamps tie, receive is later in the workflow than issue.
                kind_rank = 1 if kind == "issue" else 2
                candidates.append({
                    "line": line,
                    "doc": doc,
                    "line_model": line_model,
                    "doc_model": doc_model,
                    "kind": kind,
                    "movement": movement,
                    "labour_source": labour_source,
                    "sort_key": (
                        fields.Datetime.to_datetime(confirmed_at),
                        kind_rank,
                        line.id,
                    ),
                })
        if not candidates:
            return None
        return max(candidates, key=lambda c: c["sort_key"])

    def _snapshot_transaction(self, tx):
        """Capture doc metadata before the transaction line/doc is deleted."""
        doc = tx["doc"]
        return {
            "label": self._rollback_label(tx),
            "process_id": doc.process_id.id,
            "employee_id": doc.employee_id.id or False,
            "party_id": doc.ledger_id.id or False,
        }

    def _rollback_label(self, tx):
        doc = tx["doc"]
        kind = tx["kind"].title()
        return _("%(movement)s %(kind)s %(doc)s") % {
            "movement": tx["movement"].title(),
            "kind": kind,
            "doc": doc.name,
        }

    def _pre_receive_rdy_cts(self, line):
        """Estimate ready cts before a receive was confirmed."""
        received = line.cts or 0.0
        loss = getattr(line, "loss_cts", 0.0) or 0.0
        labour_loss = getattr(line, "labour_loss_cts", 0.0) or 0.0
        issue_cts = getattr(line, "issue_cts", 0.0) or 0.0
        if issue_cts:
            return issue_cts
        if received or loss:
            return received + loss
        if labour_loss:
            return received + labour_loss
        return self.rdy_cts or 0.0

    def _unlink_receive_labour_entries(self, line, labour_source):
        if not labour_source:
            return
        entries = self.env["diamond.labour.entry"].search([
            ("receive_model", "=", labour_source),
            ("receive_line_id", "=", line.id),
        ])
        locked = entries.filtered(lambda e: e.state != "draft")
        if locked:
            raise UserError(_(
                "Cannot rollback %(doc)s — labour entries are already invoiced or paid."
            ) % {"doc": line.doc_id.name})
        billed = entries.filtered(lambda e: e.party_invoice_id or e.salary_slip_id)
        if billed:
            raise UserError(_(
                "Cannot rollback %(doc)s — labour is linked to a party invoice or salary slip. "
                "Cancel that billing document first."
            ) % {"doc": line.doc_id.name})
        entries.unlink()

    def _factory_issue_weight_for_segment(self, packet, doc, line):
        """Weight when the packet was issued to factory for this receive segment."""
        issue_lines = self.env["diamond.factory.issue.line"].search([
            ("packet_id", "=", packet.id),
            ("doc_id.state", "=", "confirmed"),
            ("doc_id.employee_id", "=", doc.employee_id.id),
            ("doc_id.process_id", "=", doc.process_id.id),
        ])
        issue_line = issue_lines.sorted(
            key=lambda l: (l.doc_id.write_date or l.doc_id.create_date, l.id),
            reverse=True,
        )[:1]
        if issue_line:
            line = issue_line[0]
            return (
                line.issue_cts
                or line.labour_weight_cts
                or line.cts
                or packet.rdy_cts
                or 0.0
            )
        return line.issue_cts or line.session_issue_cts or self._pre_receive_rdy_cts(line)

    def _cleanup_transaction_line(self, line, doc):
        doc_id = doc.id
        line.unlink()
        remaining = self.env[doc._name].browse(doc_id).exists()
        if remaining and not remaining.line_ids:
            remaining.unlink()

    def _rollback_process_issue(self, tx):
        packet = self
        doc = tx["doc"]
        packet.write({
            "state": "in_stock",
            "current_location": "office",
            "current_process_id": False,
            "current_employee_id": False,
            "current_holder_id": False,
        })
        self._cleanup_transaction_line(tx["line"], doc)

    def _rollback_process_receive(self, tx):
        packet = self
        line = tx["line"]
        doc = tx["doc"]
        self._unlink_receive_labour_entries(line, tx["labour_source"])
        packet.write({
            "state": "in_process",
            "current_location": "office",
            "current_process_id": doc.process_id.id,
            "current_employee_id": doc.employee_id.id or False,
            "current_holder_id": doc.ledger_id.id or False,
            "rdy_pcs": line.pcs or packet.rdy_pcs,
            "rdy_cts": self._pre_receive_rdy_cts(line),
        })
        self._cleanup_transaction_line(line, doc)

    def _rollback_factory_issue(self, tx):
        packet = self
        line = tx["line"]
        doc = tx["doc"]
        pending = packet._get_pending_factory(doc.process_id)
        has_pending = bool(
            pending
            and pending.employee_id == doc.employee_id
            and (pending.issue_cts or pending.labour_weight_cts)
        )
        packet.write({
            "state": "in_stock",
            "current_location": "office",
            "current_employee_id": False,
            "current_process_id": False,
            "current_factory_labour_weight_cts": 0.0,
        })
        if not has_pending:
            packet._clear_pending_factory(doc.process_id)
        self._cleanup_transaction_line(line, doc)

    def _rollback_factory_receive_unprocessed(self, tx):
        packet = self
        line = tx["line"]
        doc = tx["doc"]
        issue_cts = self._factory_issue_weight_for_segment(packet, doc, line)
        labour_weight = line.labour_weight_cts or issue_cts
        packet.write({
            "state": "in_factory",
            "current_location": "factory",
            "current_employee_id": doc.employee_id.id,
            "current_process_id": doc.process_id.id,
            "current_factory_labour_weight_cts": labour_weight,
            "rdy_pcs": line.pcs or packet.rdy_pcs,
            "rdy_cts": issue_cts,
        })
        packet._clear_pending_factory(doc.process_id)
        self._cleanup_transaction_line(line, doc)

    def _rollback_factory_receive_complete(self, tx):
        packet = self
        line = tx["line"]
        doc = tx["doc"]
        self._unlink_receive_labour_entries(line, tx["labour_source"])
        issue_cts = line.issue_cts or self._pre_receive_rdy_cts(line)
        labour_weight = line.labour_weight_cts or issue_cts
        resuming = bool(
            line.session_issue_cts
            and (
                line.labour_weight_cts
                and line.labour_weight_cts > (line.issue_cts or 0.0)
            )
        )
        packet.write({
            "state": "in_factory",
            "current_location": "factory",
            "current_employee_id": doc.employee_id.id,
            "current_process_id": doc.process_id.id,
            "current_factory_labour_weight_cts": labour_weight,
            "rdy_pcs": line.pcs or packet.rdy_pcs,
            "rdy_cts": issue_cts,
        })
        if resuming:
            packet._upsert_pending_factory(
                doc.employee_id,
                doc.process_id,
                line.session_issue_cts or issue_cts,
                labour_weight,
            )
        else:
            packet._clear_pending_factory(doc.process_id)
        self._cleanup_transaction_line(line, doc)

    def _rollback_factory_receive(self, tx):
        line = tx["line"]
        if line.unprocessed:
            self._rollback_factory_receive_unprocessed(tx)
        else:
            self._rollback_factory_receive_complete(tx)

    def _rollback_jobwork_issue(self, tx):
        packet = self
        line = tx["line"]
        doc = tx["doc"]
        packet.write({
            "state": "in_stock",
            "current_location": "office",
            "current_holder_id": False,
            "current_process_id": False,
        })
        self._cleanup_transaction_line(line, doc)

    def _rollback_jobwork_receive(self, tx):
        packet = self
        line = tx["line"]
        doc = tx["doc"]
        packet.write({
            "state": "in_jobwork",
            "current_location": "jobwork",
            "current_holder_id": doc.ledger_id.id,
            "current_process_id": doc.process_id.id,
            "rdy_pcs": line.pcs or packet.rdy_pcs,
            "rdy_cts": self._pre_receive_rdy_cts(line),
        })
        self._cleanup_transaction_line(line, doc)

    def _rollback_hpht_issue(self, tx):
        packet = self
        line = tx["line"]
        doc = tx["doc"]
        packet.write({
            "state": "in_stock",
            "current_location": "office",
            "current_holder_id": False,
            "current_process_id": False,
        })
        self._cleanup_transaction_line(line, doc)

    def _rollback_hpht_receive(self, tx):
        packet = self
        line = tx["line"]
        doc = tx["doc"]
        self._unlink_receive_labour_entries(line, tx["labour_source"])
        packet.write({
            "state": "in_hpht",
            "current_location": "hpht",
            "current_holder_id": doc.ledger_id.id,
            "current_process_id": doc.process_id.id,
            "rdy_pcs": line.pcs or packet.rdy_pcs,
            "rdy_cts": self._pre_receive_rdy_cts(line),
        })
        self._cleanup_transaction_line(line, doc)

    _ROLLBACK_HANDLERS = {
        ("process", "issue"): _rollback_process_issue,
        ("process", "receive"): _rollback_process_receive,
        ("factory", "issue"): _rollback_factory_issue,
        ("factory", "receive"): _rollback_factory_receive,
        ("jobwork", "issue"): _rollback_jobwork_issue,
        ("jobwork", "receive"): _rollback_jobwork_receive,
        ("hpht", "issue"): _rollback_hpht_issue,
        ("hpht", "receive"): _rollback_hpht_receive,
    }

    def action_rollback_last_transaction(self):
        """Undo the latest confirmed issue/receive for each packet (LIFO stack)."""
        rolled_back = []
        errors = []
        for packet in self:
            tx = packet._find_latest_confirmed_transaction()
            if not tx:
                errors.append(_("%s: no confirmed issue/receive found.") % packet.barcode)
                continue
            handler = packet._ROLLBACK_HANDLERS.get((tx["movement"], tx["kind"]))
            if not handler:
                errors.append(_("%s: unsupported transaction type.") % packet.barcode)
                continue
            meta = packet._snapshot_transaction(tx)
            handler(packet, tx)
            packet._log_history(
                action="rollback",
                note=_("Rolled back: %s") % meta["label"],
                process_id=meta["process_id"],
                employee_id=meta["employee_id"],
                party_id=meta["party_id"],
            )
            rolled_back.append(_("%s → %s") % (packet.barcode, meta["label"]))

        if errors and not rolled_back:
            raise UserError("\n".join(errors))
        if errors:
            raise UserError(
                _("Rolled back:\n%(ok)s\n\nSkipped:\n%(skip)s") % {
                    "ok": "\n".join(rolled_back),
                    "skip": "\n".join(errors),
                }
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Rollback complete"),
                "message": "\n".join(rolled_back),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_open_rollback_wizard(self):
        if not self:
            raise UserError(_("Select at least one packet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Rollback Last Transaction"),
            "res_model": "diamond.packet.rollback.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_ids": self.ids,
                "active_model": "diamond.packet",
            },
        }

    def preview_latest_transaction(self):
        """Return human-readable label of latest transaction per packet."""
        self.ensure_one()
        tx = self._find_latest_confirmed_transaction()
        if not tx:
            return _("No confirmed transaction")
        return self._rollback_label(tx)
