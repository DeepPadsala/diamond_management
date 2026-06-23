from odoo import _, api, fields, models
from odoo.exceptions import UserError

_ISSUED_STATES = ("in_process", "in_factory", "in_jobwork", "in_hpht")

_ISSUE_LINE_MODEL = {
    "in_factory": "diamond.factory.issue.line",
    "in_process": "diamond.process.issue.line",
    "in_jobwork": "diamond.jobwork.issue.line",
    "in_hpht": "diamond.hpht.issue.line",
}


class DiamondPacketIssueCorrectionWizard(models.TransientModel):
    """Fix wrong process / employee / party on an active issue."""

    _name = "diamond.packet.issue.correction.wizard"
    _description = "Correct Issue Assignment"

    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )
    reason = fields.Text(string="Reason / Note", help="Why is this correction being made?")
    packet_ids = fields.Many2many(
        "diamond.packet",
        string="Packets",
        domain="['|', ('state', 'in', ('in_process', 'in_factory', 'in_jobwork', 'in_hpht')), "
               "'&', ('state', '=', 'in_stock'), ('pending_factory_employee_id', '!=', False)]",
    )

    new_process_id = fields.Many2one("diamond.process", string="New Process")
    new_employee_id = fields.Many2one("diamond.employee", string="New Employee")
    new_holder_id = fields.Many2one("diamond.ledger", string="New Party")

    show_employee = fields.Boolean(compute="_compute_field_visibility")
    show_party = fields.Boolean(compute="_compute_field_visibility")

    @api.model
    def _is_correctable(self, packet):
        if packet.state in _ISSUED_STATES:
            return True
        return bool(
            packet.state == "in_stock"
            and packet.pending_factory_employee_id
            and packet.pending_factory_process_id
        )

    @api.depends("packet_ids", "packet_ids.state", "packet_ids.pending_factory_employee_id")
    def _compute_field_visibility(self):
        for wizard in self:
            packets = wizard.packet_ids
            states = set(packets.mapped("state"))
            wizard.show_employee = bool(
                states & {"in_process", "in_factory"}
                or any(packets.mapped("pending_factory_employee_id"))
            )
            wizard.show_party = bool(states & {"in_process", "in_jobwork", "in_hpht"})

    @api.model
    def _packet_assignment(self, packet):
        """Return (is_pending, process, employee, holder) for a packet."""
        pending = (
            packet.state == "in_stock"
            and packet.pending_factory_employee_id
            and packet.pending_factory_process_id
        )
        if pending:
            return (
                True,
                packet.pending_factory_process_id,
                packet.pending_factory_employee_id,
                packet.current_holder_id,
            )
        return (
            False,
            packet.current_process_id,
            packet.current_employee_id,
            packet.current_holder_id,
        )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_model = self.env.context.get("active_model")
        active_ids = self.env.context.get("active_ids") or []
        if active_model == "diamond.packet" and active_ids:
            packets = self.env["diamond.packet"].browse(active_ids).filtered(self._is_correctable)
            if packets:
                res["packet_ids"] = [(6, 0, packets.ids)]
                _, process, employee, holder = self._packet_assignment(packets[0])
                res["new_process_id"] = process.id
                res["new_employee_id"] = employee.id if employee else False
                res["new_holder_id"] = holder.id if holder else False
        return res

    @api.onchange("packet_ids")
    def _onchange_packet_ids(self):
        correctable = self.packet_ids.filtered(self._is_correctable)
        skipped = self.packet_ids - correctable
        if skipped:
            return {
                "warning": {
                    "title": _("Some packets skipped"),
                    "message": _(
                        "Only packets currently issued (or with a pending factory process) "
                        "can be corrected. Skipped: %s"
                    ) % ", ".join(skipped.mapped("barcode")),
                }
            }
        if correctable:
            _, process, employee, holder = self._packet_assignment(correctable[0])
            self.new_process_id = process
            self.new_employee_id = employee
            self.new_holder_id = holder

    def action_apply(self):
        self.ensure_one()
        packets = self.packet_ids.filtered(self._is_correctable)
        if not packets:
            raise UserError(_("Add at least one issued packet to correct."))

        corrected = 0
        for packet in packets:
            if self._apply_to_packet(packet):
                corrected += 1
        if not corrected:
            raise UserError(_("Change process, employee, or party before applying."))
        return {"type": "ir.actions.act_window_close"}

    def _apply_to_packet(self, packet):
        self.ensure_one()
        pending, old_process, old_employee, old_holder = self._packet_assignment(packet)
        changes = []
        packet_vals = {}
        pending_vals = {}

        if self.new_process_id and self.new_process_id != old_process:
            changes.append(
                _("Process: %s → %s") % (old_process.display_name, self.new_process_id.display_name)
            )
            if pending:
                pending_vals["pending_factory_process_id"] = self.new_process_id.id
            else:
                packet_vals["current_process_id"] = self.new_process_id.id

        if self.show_employee and self.new_employee_id != old_employee:
            old_name = old_employee.display_name if old_employee else "-"
            new_name = self.new_employee_id.display_name if self.new_employee_id else "-"
            changes.append(_("Employee: %s → %s") % (old_name, new_name))
            if pending:
                pending_vals["pending_factory_employee_id"] = self.new_employee_id.id
            else:
                packet_vals["current_employee_id"] = self.new_employee_id.id

        if self.show_party and self.new_holder_id != old_holder:
            old_name = old_holder.display_name if old_holder else "-"
            new_name = self.new_holder_id.display_name if self.new_holder_id else "-"
            changes.append(_("Party: %s → %s") % (old_name, new_name))
            packet_vals["current_holder_id"] = self.new_holder_id.id

        if not changes:
            return False

        if pending_vals:
            packet.write(pending_vals)
        if packet_vals:
            packet.with_context(skip_packet_auto_history=True).write(packet_vals)

        note = _("Issue correction — %s") % "; ".join(changes)
        if self.reason:
            note = "%s. %s" % (note, _("Reason: %s") % self.reason)

        packet._log_history(
            action="update",
            note=note,
            process_id=self.new_process_id.id or packet.current_process_id.id or packet.pending_factory_process_id.id,
            employee_id=self.new_employee_id.id or packet.current_employee_id.id or packet.pending_factory_employee_id.id,
            party_id=self.new_holder_id.id or packet.current_holder_id.id,
        )
        self._sync_issue_document(packet, packet_vals, pending_vals)
        return True

    def _sync_issue_document(self, packet, packet_vals, pending_vals):
        """Update the source issue document when it only contains this packet."""
        if packet.state not in _ISSUE_LINE_MODEL:
            return
        line_model = _ISSUE_LINE_MODEL[packet.state]
        line = self.env[line_model].search(
            [
                ("packet_id", "=", packet.id),
                ("doc_id.state", "=", "confirmed"),
            ],
            order="id desc",
            limit=1,
        )
        if not line or len(line.doc_id.line_ids) != 1:
            return
        doc_vals = {}
        if packet_vals.get("current_process_id") or pending_vals.get("pending_factory_process_id"):
            doc_vals["process_id"] = packet_vals.get("current_process_id") or pending_vals.get(
                "pending_factory_process_id"
            )
        if packet_vals.get("current_employee_id") or pending_vals.get("pending_factory_employee_id"):
            doc_vals["employee_id"] = packet_vals.get("current_employee_id") or pending_vals.get(
                "pending_factory_employee_id"
            )
        if packet_vals.get("current_holder_id"):
            doc_vals["ledger_id"] = packet_vals["current_holder_id"]
        if doc_vals:
            line.doc_id.write(doc_vals)
