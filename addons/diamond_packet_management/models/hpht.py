from odoo import _, api, fields, models


# ─────────── HPHT Issue (F12) ───────────
class DiamondHphtIssue(models.Model):
    _name = "diamond.hpht.issue"
    _description = "HPHT Issue"
    _inherit = "diamond.movement.mixin"
    _order = "date desc, id desc"

    expected_return_date = fields.Date(string="Expected Return")
    line_ids = fields.One2many("diamond.hpht.issue.line", "doc_id", string="Lines")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("diamond.hpht.issue") or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            for line in rec.line_ids:
                line.packet_id.write({
                    "state": "in_hpht",
                    "current_location": "hpht",
                    "current_holder_id": rec.ledger_id.id,
                    "current_process_id": rec.process_id.id,
                })
                line.packet_id._log_history(action="hpht_issue",
                                            note=_("HPHT Issue %s") % rec.name,
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


class DiamondHphtIssueLine(models.Model):
    _name = "diamond.hpht.issue.line"
    _description = "HPHT Issue Line"
    _inherit = "diamond.movement.line.mixin"

    doc_id = fields.Many2one("diamond.hpht.issue", string="Document", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="doc_id.company_id", store=True, index=True)


# ─────────── HPHT Receive ───────────
class DiamondHphtReceive(models.Model):
    _name = "diamond.hpht.receive"
    _description = "HPHT Receive"
    _inherit = ["diamond.movement.mixin", "diamond.labour.calculator"]
    _order = "date desc, id desc"

    line_ids = fields.One2many("diamond.hpht.receive.line", "doc_id", string="Lines")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("diamond.hpht.receive") or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            for line in rec.line_ids:
                line.packet_id.write({
                    "state": "in_stock",
                    "current_location": "office",
                    "rdy_pcs": line.pcs or line.packet_id.rdy_pcs,
                    "rdy_cts": line.cts or line.packet_id.rdy_cts,
                    "color_id": line.new_color_id.id or line.packet_id.color_id.id,
                })
                line.packet_id._log_history(action="hpht_receive",
                                            note=_("HPHT Receive %s") % rec.name,
                                            process_id=rec.process_id.id,
                                            party_id=rec.ledger_id.id)
            rec._create_labour_entries_from_receive(
                rec, "diamond.hpht.receive.line", "diamond.hpht.receive",
                create_party=True, create_worker=False,
            )
            rec.state = "confirmed"
        if len(self) == 1:
            return self._prompt_jangad_print("receive")
        return True

    def action_cancel(self):
        for rec in self:
            rec._unlink_labour_entries_for_receive(rec, "diamond.hpht.receive")
        self.write({"state": "cancelled"})

    def action_draft(self):
        self.write({"state": "draft"})


class DiamondHphtReceiveLine(models.Model):
    _name = "diamond.hpht.receive.line"
    _description = "HPHT Receive Line"
    _inherit = "diamond.movement.line.mixin"

    doc_id = fields.Many2one("diamond.hpht.receive", string="Document", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="doc_id.company_id", store=True, index=True)
    new_color_id = fields.Many2one("diamond.color", string="New Color (after HPHT)")
    loss_cts = fields.Float(string="Loss (cts)", digits=(12, 4))
    party_labour_amount = fields.Float(string="Party Labour", digits=(14, 2), readonly=True)
