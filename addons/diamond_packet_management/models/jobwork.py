from odoo import _, api, fields, models
from odoo.exceptions import UserError


# ─────────── Jobwork Issue (F7) ───────────
class DiamondJobworkIssue(models.Model):
    _name = "diamond.jobwork.issue"
    _description = "Jobwork Issue"
    _inherit = "diamond.movement.mixin"
    _order = "date desc, id desc"

    expected_return_date = fields.Date(string="Expected Return")
    line_ids = fields.One2many("diamond.jobwork.issue.line", "doc_id", string="Lines")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("diamond.jobwork.issue") or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.ledger_id:
                raise UserError(_("Select a Jobworker (party) first."))
            for line in rec.line_ids:
                line.packet_id.write({
                    "state": "in_jobwork",
                    "current_location": "jobwork",
                    "current_holder_id": rec.ledger_id.id,
                    "current_process_id": rec.process_id.id,
                })
                line.packet_id._log_history(action="jobwork_issue",
                                            note=_("Jobwork Issue %s") % rec.name,
                                            process_id=rec.process_id.id,
                                            party_id=rec.ledger_id.id)
            rec.state = "confirmed"
        if len(self) == 1:
            return self._prompt_jangad_print("issue")
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_draft(self):
        self.write({"state": "draft"})


class DiamondJobworkIssueLine(models.Model):
    _name = "diamond.jobwork.issue.line"
    _description = "Jobwork Issue Line"
    _inherit = "diamond.movement.line.mixin"

    doc_id = fields.Many2one("diamond.jobwork.issue", string="Document", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="doc_id.company_id", store=True, index=True)


# ─────────── Jobwork Receive (F8) ───────────
class DiamondJobworkReceive(models.Model):
    _name = "diamond.jobwork.receive"
    _description = "Jobwork Receive"
    _inherit = "diamond.movement.mixin"
    _order = "date desc, id desc"

    line_ids = fields.One2many("diamond.jobwork.receive.line", "doc_id", string="Lines")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("diamond.jobwork.receive") or _("New")
        return super().create(vals_list)

    def _apply_regular_receive_line(self, rec, line):
        packet = line.packet_id
        packet.write({
            "state": "in_stock",
            "current_location": "office",
            "current_holder_id": packet._owner_ledger_for_barcode().id if packet._owner_ledger_for_barcode() else False,
            "current_process_id": False,
            "rdy_pcs": line.pcs or packet.rdy_pcs,
            "rdy_cts": line.cts or packet.rdy_cts,
        })
        packet._log_history(
            action="jobwork_receive",
            note=_("Jobwork Receive %s") % rec.name,
            process_id=rec.process_id.id,
            party_id=rec.ledger_id.id,
        )

    def _apply_split_receive_line(self, rec, line):
        parent = line.packet_id
        Packet = self.env["diamond.packet"]
        children = Packet
        for idx, child_line in enumerate(line.child_line_ids, start=1):
            child = Packet.create(parent._prepare_child_packet_vals(
                child_line.pcs, child_line.cts, idx,
            ))
            child_line.packet_id = child.id
            children |= child
            child._log_history(
                action="create",
                note=_("Child of %(parent)s from jobwork split %(doc)s") % {
                    "parent": parent.packet_no,
                    "doc": rec.name,
                },
                party_id=rec.ledger_id.id,
                process_id=rec.process_id.id,
            )
        parent.write({
            "state": "split",
            "current_location": "office",
            "current_holder_id": False,
            "current_process_id": False,
            "split_date": rec.date,
        })
        parent._log_history(
            action="split",
            note=_("Split into %(count)s child packets via %(doc)s") % {
                "count": len(children),
                "doc": rec.name,
            },
            process_id=rec.process_id.id,
            party_id=rec.ledger_id.id,
        )
        line.child_packet_ids = [(6, 0, children.ids)]

    def action_confirm(self):
        for rec in self:
            for line in rec.line_ids:
                if line.is_split:
                    if len(line.child_line_ids) < 2:
                        raise UserError(_(
                            "Split receive on %(packet)s needs at least 2 child packets."
                        ) % {"packet": line.packet_id.packet_no})
                    self._apply_split_receive_line(rec, line)
                else:
                    self._apply_regular_receive_line(rec, line)
            rec.state = "confirmed"
        if len(self) == 1:
            return self._prompt_jangad_print("receive")
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_draft(self):
        self.write({"state": "draft"})


class DiamondJobworkReceiveLine(models.Model):
    _name = "diamond.jobwork.receive.line"
    _description = "Jobwork Receive Line"
    _inherit = "diamond.movement.line.mixin"

    doc_id = fields.Many2one("diamond.jobwork.receive", string="Document", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="doc_id.company_id", store=True, index=True)
    is_split = fields.Boolean(
        string="Split Receive",
        help="Parent packet is split into multiple child packets on receive.",
    )
    loss_cts = fields.Float(string="Loss (cts)", digits=(12, 4))
    labour_amount = fields.Float(string="Labour Amount", digits=(14, 2))
    child_line_ids = fields.One2many(
        "diamond.jobwork.receive.child.line", "receive_line_id", string="Child Packets",
    )
    child_packet_ids = fields.Many2many(
        "diamond.packet", "diamond_jobwork_receive_child_packet_rel",
        "receive_line_id", "packet_id", string="Created Child Packets", readonly=True,
    )


class DiamondJobworkReceiveChildLine(models.Model):
    _name = "diamond.jobwork.receive.child.line"
    _description = "Jobwork Receive Child Line"
    _order = "id"

    receive_line_id = fields.Many2one(
        "diamond.jobwork.receive.line", string="Receive Line",
        required=True, ondelete="cascade",
    )
    company_id = fields.Many2one(related="receive_line_id.company_id", store=True, index=True)
    packet_id = fields.Many2one(
        "diamond.packet", string="Child Packet", readonly=True,
        help="Created when the jobwork receive is confirmed.",
    )
    pcs = fields.Integer(string="Pcs", default=1, required=True)
    cts = fields.Float(string="Cts", digits=(12, 4), required=True)
    note = fields.Char(string="Note")
