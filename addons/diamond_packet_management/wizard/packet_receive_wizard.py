from odoo import _, api, fields, models
from odoo.exceptions import UserError


_MODE_FROM_STATE = {
    "in_process": "process",
    "in_factory": "factory",
    "in_jobwork": "jobwork",
    "in_hpht": "hpht",
}
_STATE_FROM_MODE = {v: k for k, v in _MODE_FROM_STATE.items()}
_MODE_TO_DOC = {
    "process": "diamond.process.receive",
    "factory": "diamond.factory.receive",
    "jobwork": "diamond.jobwork.receive",
    "hpht": "diamond.hpht.receive",
}


class DiamondPacketReceiveWizard(models.TransientModel):
    """Unified receive wizard — enter new weight per packet on return."""

    _name = "diamond.packet.receive.wizard"
    _description = "Receive Packet(s) Wizard"

    mode = fields.Selection(
        selection=[
            ("process", "Process Receive"),
            ("factory", "Factory Receive"),
            ("jobwork", "Jobwork Receive"),
            ("hpht", "HPHT Receive"),
        ],
        string="Receive Type",
        required=True,
        default="process",
    )

    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )
    date = fields.Datetime(string="Receive Date", default=fields.Datetime.now, required=True)

    process_id = fields.Many2one("diamond.process", string="Process", required=True)
    ledger_id = fields.Many2one("diamond.ledger", string="Party / Vendor")
    employee_id = fields.Many2one("diamond.employee", string="Employee")
    note = fields.Text(string="Note")

    line_ids = fields.One2many(
        "diamond.packet.receive.wizard.line", "wizard_id",
        string="Lines", required=True,
    )

    show_labour = fields.Boolean(compute="_compute_flags")
    show_party_labour = fields.Boolean(compute="_compute_flags")
    show_worker_labour = fields.Boolean(compute="_compute_flags")
    show_unprocessed = fields.Boolean(compute="_compute_flags")
    show_new_color = fields.Boolean(compute="_compute_flags")

    total_old_cts = fields.Float(string="Issued Cts", digits=(12, 4), compute="_compute_totals")
    total_new_cts = fields.Float(string="Received Cts", digits=(12, 4), compute="_compute_totals")
    total_loss_cts = fields.Float(string="Total Loss Cts", digits=(12, 4), compute="_compute_totals")
    total_loss_pct = fields.Float(string="Loss %", digits=(6, 2), compute="_compute_totals")

    @api.depends("mode")
    def _compute_flags(self):
        for rec in self:
            rec.show_labour = rec.mode in ("process", "factory", "hpht", "jobwork")
            rec.show_worker_labour = rec.mode == "factory"
            rec.show_party_labour = rec.mode in ("process", "factory", "hpht")
            rec.show_unprocessed = rec.mode == "factory"
            rec.show_new_color = rec.mode == "hpht"

    @api.depends("line_ids.old_cts", "line_ids.new_cts", "line_ids.loss_cts")
    def _compute_totals(self):
        for rec in self:
            old = sum(rec.line_ids.mapped("old_cts"))
            new = sum(rec.line_ids.mapped("new_cts"))
            loss = sum(rec.line_ids.mapped("loss_cts"))
            rec.total_old_cts = old
            rec.total_new_cts = new
            rec.total_loss_cts = loss
            rec.total_loss_pct = (loss / old * 100.0) if old else 0.0

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context or {}
        active_ids = ctx.get("active_ids") or (
            [ctx["active_id"]] if ctx.get("active_id") else []
        )
        mode = ctx.get("default_receive_mode")

        if ctx.get("active_model") == "diamond.packet" and active_ids:
            packets = self.env["diamond.packet"].browse(active_ids).exists()
            if mode:
                target_state = _STATE_FROM_MODE.get(mode)
                eligible = packets.filtered(lambda p: p.state == target_state)
            else:
                in_transit = packets.filtered(lambda p: p.state in _MODE_FROM_STATE)
                if in_transit:
                    state_counts = {}
                    for p in in_transit:
                        state_counts[p.state] = state_counts.get(p.state, 0) + 1
                    primary_state = max(state_counts, key=state_counts.get)
                    mode = _MODE_FROM_STATE[primary_state]
                    eligible = in_transit.filtered(lambda p: p.state == primary_state)
                else:
                    eligible = self.env["diamond.packet"]

            if eligible:
                holders = eligible.mapped("current_holder_id")
                if len(holders) == 1:
                    res["ledger_id"] = holders.id
                processes = eligible.mapped("current_process_id")
                if len(processes) == 1 and processes:
                    res["process_id"] = processes.id
                employees = eligible.mapped("current_employee_id")
                if len(employees) == 1 and employees:
                    res["employee_id"] = employees.id
                res["mode"] = mode
                res["line_ids"] = [
                    (0, 0, {
                        "packet_id": p.id,
                        "new_pcs": p.rdy_pcs or 1,
                        "new_cts": p.rdy_cts or 0.0,
                    })
                    for p in eligible
                ]
        elif mode:
            res["mode"] = mode

        return res

    @api.onchange("mode")
    def _onchange_mode(self):
        if self.mode and not self.process_id:
            target_type = {
                "process": "internal",
                "factory": "internal",
                "jobwork": "jobwork",
                "hpht": "hpht",
            }[self.mode]
            self.process_id = self.env["diamond.process"].search(
                [("process_type", "=", target_type), ("active", "=", True)],
                limit=1, order="sequence_no",
            )

    def _validate(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No packets to receive."))

        target_state = _STATE_FROM_MODE[self.mode]
        bad_state = self.line_ids.packet_id.filtered(lambda p: p.state != target_state)
        if bad_state:
            raise UserError(_(
                "These packets are not in the expected state for this receive mode: %s"
            ) % ", ".join(bad_state.mapped("packet_no")))

        bad_co = self.line_ids.packet_id.filtered(
            lambda p: p.company_id.id != self.company_id.id
        )
        if bad_co:
            raise UserError(_("Some packets are from a different company."))

        bad_qty = self.line_ids.filtered(lambda l: l.new_pcs <= 0 or l.new_cts <= 0)
        if bad_qty:
            raise UserError(_(
                "Received pcs and cts must be greater than zero for: %s"
            ) % ", ".join(bad_qty.mapped("packet_id.packet_no")))

        gain = self.line_ids.filtered(lambda l: l.new_cts > l.old_cts + 0.0001)
        if gain.filtered(lambda l: not l.allow_weight_gain):
            raise UserError(_(
                "Received weight exceeds issued weight for: %s. "
                "Tick 'Allow Gain' on those lines to override."
            ) % ", ".join(gain.filtered(lambda l: not l.allow_weight_gain).mapped("packet_id.packet_no")))

    def action_receive(self):
        self.ensure_one()
        self._validate()

        Doc = self.env[_MODE_TO_DOC[self.mode]]
        line_vals = []
        for wl in self.line_ids:
            v = {
                "packet_id": wl.packet_id.id,
                "pcs": wl.new_pcs,
                "cts": wl.new_cts,
                "loss_cts": wl.loss_cts,
                "note": wl.note or "",
            }
            if self.mode == "jobwork":
                v["labour_amount"] = wl.labour_amount
            elif self.mode == "factory":
                v["unprocessed"] = wl.unprocessed
                v["issue_cts"] = wl.old_cts
            elif self.mode == "hpht":
                v["new_color_id"] = wl.new_color_id.id or False
            line_vals.append((0, 0, v))

        doc = Doc.with_company(self.company_id).create({
            "company_id": self.company_id.id,
            "date": self.date,
            "process_id": self.process_id.id,
            "ledger_id": self.ledger_id.id or False,
            "employee_id": self.employee_id.id or False,
            "note": self.note or "",
            "line_ids": line_vals,
        })
        return doc.action_confirm()


class DiamondPacketReceiveWizardLine(models.TransientModel):
    _name = "diamond.packet.receive.wizard.line"
    _description = "Receive Wizard Line"
    _order = "id"

    wizard_id = fields.Many2one(
        "diamond.packet.receive.wizard", required=True, ondelete="cascade",
    )
    packet_id = fields.Many2one(
        "diamond.packet", required=True, string="Packet",
        domain="[('state', 'in', ('in_process','in_factory','in_jobwork','in_hpht'))]",
    )

    barcode = fields.Char(related="packet_id.barcode", readonly=True)
    shape = fields.Char(related="packet_id.shape_id.code", string="Shape", readonly=True)
    color = fields.Char(related="packet_id.color_id.code", string="Color", readonly=True)
    clarity = fields.Char(related="packet_id.clarity_id.code", string="Clarity", readonly=True)

    old_pcs = fields.Integer(related="packet_id.rdy_pcs", string="Issued Pcs", readonly=True)
    old_cts = fields.Float(related="packet_id.rdy_cts", string="Issued Cts", digits=(12, 4), readonly=True)

    new_pcs = fields.Integer(string="Received Pcs", required=True, default=1)
    new_cts = fields.Float(string="Received Cts", required=True, digits=(12, 4))

    loss_cts = fields.Float(string="Loss Cts", digits=(12, 4), compute="_compute_loss")
    loss_pct = fields.Float(string="Loss %", digits=(6, 2), compute="_compute_loss")

    allow_weight_gain = fields.Boolean(string="Allow Gain")
    new_color_id = fields.Many2one("diamond.color", string="New Color (HPHT)")
    labour_amount = fields.Float(string="Jobwork Labour", digits=(14, 2))
    unprocessed = fields.Boolean(
        string="Un-Processed",
        help="Process not finished — packet returns to stock without salary. "
             "Re-issue later to the same worker to complete the job.",
    )
    party_labour_amount = fields.Float(string="Party Labour", digits=(14, 2), compute="_compute_labour_preview")
    worker_labour_amount = fields.Float(string="Worker Labour", digits=(14, 2), compute="_compute_labour_preview")
    note = fields.Char(string="Note")

    @api.depends("old_cts", "new_cts")
    def _compute_loss(self):
        for rec in self:
            rec.loss_cts = (rec.old_cts or 0.0) - (rec.new_cts or 0.0)
            rec.loss_pct = (rec.loss_cts / rec.old_cts * 100.0) if rec.old_cts else 0.0

    @api.depends(
        "wizard_id.process_id", "wizard_id.mode", "wizard_id.company_id",
        "wizard_id.employee_id", "packet_id", "new_pcs", "new_cts", "loss_cts", "unprocessed",
    )
    def _compute_labour_preview(self):
        calc = self.env["diamond.labour.calculator"]
        FactoryLine = calc.env["diamond.factory.receive.line"]
        FactoryDoc = calc.env["diamond.factory.receive"]
        for rec in self:
            rec.party_labour_amount = 0.0
            rec.worker_labour_amount = 0.0
            wizard = rec.wizard_id
            if not wizard or not wizard.process_id or not rec.packet_id or rec.unprocessed:
                continue

            packet = rec.packet_id
            segment_issue = rec.old_cts or 0.0
            resuming = (
                wizard.mode == "factory"
                and packet.pending_factory_issue_cts
                and packet.pending_factory_employee_id == wizard.employee_id
                and packet.pending_factory_process_id == wizard.process_id
            )
            if resuming:
                session_issue = packet.pending_factory_issue_cts
                labour_loss = max(session_issue - (rec.new_cts or 0.0), 0.0)
            else:
                session_issue = segment_issue
                labour_loss = rec.loss_cts or max(segment_issue - (rec.new_cts or 0.0), 0.0)

            if wizard.mode == "factory":
                fake_line = FactoryLine.new({
                    "packet_id": packet.id,
                    "pcs": rec.new_pcs,
                    "cts": rec.new_cts,
                    "loss_cts": rec.loss_cts,
                    "issue_cts": segment_issue,
                    "session_issue_cts": session_issue,
                    "labour_loss_cts": labour_loss,
                    "unprocessed": False,
                })
                fake_doc = FactoryDoc.new({
                    "company_id": wizard.company_id.id,
                    "date": wizard.date,
                    "process_id": wizard.process_id.id,
                    "employee_id": wizard.employee_id.id if wizard.employee_id else False,
                })
            else:
                fake_line = calc.env["diamond.process.receive.line"].new({
                    "packet_id": packet.id,
                    "pcs": rec.new_pcs,
                    "cts": rec.new_cts,
                    "loss_cts": rec.loss_cts,
                })
                fake_doc = calc.env["diamond.process.receive"].new({
                    "company_id": wizard.company_id.id,
                    "date": wizard.date,
                    "process_id": wizard.process_id.id,
                    "employee_id": wizard.employee_id.id if wizard.employee_id else False,
                })

            if wizard.mode in ("process", "factory", "hpht"):
                party_vals = calc._prepare_party_labour_vals(
                    fake_doc, fake_line, "preview", "receive_line_id",
                )
                if party_vals:
                    rec.party_labour_amount = party_vals["amount"]
            if wizard.mode == "factory" and wizard.employee_id:
                worker_vals = calc._prepare_worker_labour_vals(fake_doc, fake_line, "preview")
                if worker_vals:
                    rec.worker_labour_amount = worker_vals["amount"]

    @api.onchange("packet_id")
    def _onchange_packet(self):
        if self.packet_id:
            self.new_pcs = self.packet_id.rdy_pcs or 1
            self.new_cts = self.packet_id.rdy_cts or 0.0
