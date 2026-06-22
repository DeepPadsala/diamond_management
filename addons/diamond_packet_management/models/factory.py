from odoo import _, api, fields, models
from odoo.exceptions import UserError


# ─────────── Factory Issue (F5) ───────────
class DiamondFactoryIssue(models.Model):
    _name = "diamond.factory.issue"
    _description = "Factory Issue"
    _inherit = "diamond.movement.mixin"
    _order = "date desc, id desc"

    line_ids = fields.One2many("diamond.factory.issue.line", "doc_id", string="Lines")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("diamond.factory.issue") or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.employee_id:
                raise UserError(_("Select an employee for factory issue."))
            for line in rec.line_ids:
                packet = line.packet_id
                issue_cts = line.cts or packet.rdy_cts or 0.0
                line.issue_cts = issue_cts
                packet.write({
                    "state": "in_factory",
                    "current_location": "factory",
                    "current_employee_id": rec.employee_id.id,
                    "current_process_id": rec.process_id.id,
                })
                packet._log_history(
                    action="factory_issue",
                    note=_("Factory Issue %s") % rec.name,
                    process_id=rec.process_id.id,
                    employee_id=rec.employee_id.id,
                )
            rec.state = "confirmed"
        if len(self) == 1:
            return self._prompt_jangad_print("issue")
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_draft(self):
        self.write({"state": "draft"})


class DiamondFactoryIssueLine(models.Model):
    _name = "diamond.factory.issue.line"
    _description = "Factory Issue Line"
    _inherit = "diamond.movement.line.mixin"

    doc_id = fields.Many2one("diamond.factory.issue", string="Document", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="doc_id.company_id", store=True, index=True)
    issue_cts = fields.Float(string="Issue Weight", digits=(12, 4), readonly=True,
                             help="Packet weight when issued to the worker.")


# ─────────── Factory Receive (F6) ───────────
class DiamondFactoryReceive(models.Model):
    _name = "diamond.factory.receive"
    _description = "Factory Receive"
    _inherit = ["diamond.movement.mixin", "diamond.labour.calculator"]
    _order = "date desc, id desc"

    line_ids = fields.One2many("diamond.factory.receive.line", "doc_id", string="Lines")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("diamond.factory.receive") or _("New")
        return super().create(vals_list)

    def _segment_issue_cts(self, line):
        """Weight when this factory issue segment started."""
        if line.issue_cts:
            return line.issue_cts
        received = line.cts or 0.0
        loss = line.loss_cts or 0.0
        return received + loss if (received or loss) else (line.packet_id.rdy_cts or 0.0)

    def _is_resuming_pending(self, packet, employee, process):
        return (
            packet.pending_factory_issue_cts
            and packet.pending_factory_employee_id == employee
            and packet.pending_factory_process_id == process
        )

    def _apply_factory_receive_line(self, rec, line):
        packet = line.packet_id
        segment_issue_cts = self._segment_issue_cts(line)

        if line.unprocessed:
            line.write({
                "issue_cts": segment_issue_cts,
                "session_issue_cts": segment_issue_cts,
                "labour_loss_cts": 0.0,
            })
            packet.write({
                "state": "in_stock",
                "current_location": "office",
                "rdy_pcs": line.pcs or packet.rdy_pcs,
                "rdy_cts": line.cts or packet.rdy_cts,
                "pending_factory_employee_id": rec.employee_id.id,
                "pending_factory_process_id": rec.process_id.id,
                "pending_factory_issue_cts": segment_issue_cts,
                "current_employee_id": False,
                "current_process_id": False,
            })
            note = _("Factory Receive %s (un-processed)") % rec.name
        else:
            resuming = self._is_resuming_pending(packet, rec.employee_id, rec.process_id)
            if resuming:
                session_issue_cts = packet.pending_factory_issue_cts
                labour_loss_cts = max(session_issue_cts - (line.cts or 0.0), 0.0)
            else:
                session_issue_cts = segment_issue_cts
                labour_loss_cts = line.loss_cts if line.loss_cts else max(segment_issue_cts - (line.cts or 0.0), 0.0)

            line.write({
                "issue_cts": segment_issue_cts,
                "session_issue_cts": session_issue_cts,
                "labour_loss_cts": labour_loss_cts,
            })
            packet.write({
                "state": "in_stock",
                "current_location": "office",
                "rdy_pcs": line.pcs or packet.rdy_pcs,
                "rdy_cts": line.cts or packet.rdy_cts,
                "current_employee_id": False,
                "current_process_id": False,
                "pending_factory_employee_id": False,
                "pending_factory_process_id": False,
                "pending_factory_issue_cts": 0.0,
            })
            note = _("Factory Receive %s") % rec.name

        packet._log_history(
            action="factory_receive",
            note=note,
            process_id=rec.process_id.id,
            employee_id=rec.employee_id.id,
        )

    def action_confirm(self):
        for rec in self:
            if not rec.employee_id:
                raise UserError(_("Select the employee returning the packet."))
            for line in rec.line_ids:
                self._apply_factory_receive_line(rec, line)

            completed_lines = rec.line_ids.filtered(lambda l: not l.unprocessed)
            if completed_lines:
                temp_rec = rec.with_context(factory_labour_line_ids=completed_lines.ids)
                temp_rec._create_labour_entries_from_receive(
                    temp_rec, "diamond.factory.receive.line", "diamond.factory.receive",
                    create_party=True, create_worker=True,
                )
            rec.state = "confirmed"
        if len(self) == 1:
            return self._prompt_jangad_print("receive")
        return True

    def action_cancel(self):
        for rec in self:
            rec._unlink_labour_entries_for_receive(rec, "diamond.factory.receive")
        self.write({"state": "cancelled"})

    def action_draft(self):
        self.write({"state": "draft"})


class DiamondFactoryReceiveLine(models.Model):
    _name = "diamond.factory.receive.line"
    _description = "Factory Receive Line"
    _inherit = "diamond.movement.line.mixin"

    doc_id = fields.Many2one("diamond.factory.receive", string="Document", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="doc_id.company_id", store=True, index=True)
    unprocessed = fields.Boolean(
        string="Un-Processed",
        help="Check when the worker has not finished this process. "
             "The packet returns to stock and can be issued to another worker. "
             "Salary for this process is calculated on final completion using "
             "the full weight loss from the original issue weight.",
    )
    issue_cts = fields.Float(string="Segment Issue Weight", digits=(12, 4), readonly=True)
    session_issue_cts = fields.Float(
        string="Process Start Weight", digits=(12, 4), readonly=True,
        help="Original issue weight for this process cycle (used for cumulative labour).",
    )
    loss_cts = fields.Float(string="Segment Loss (cts)", digits=(12, 4))
    labour_loss_cts = fields.Float(
        string="Labour Loss (cts)", digits=(12, 4), readonly=True,
        help="Weight loss used for salary/invoice (cumulative when resuming a pending process).",
    )
    party_labour_amount = fields.Float(string="Party Labour", digits=(14, 2), readonly=True)
    worker_labour_amount = fields.Float(string="Worker Labour", digits=(14, 2), readonly=True)
