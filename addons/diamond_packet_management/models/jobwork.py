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

    def action_confirm(self):
        for rec in self:
            for line in rec.line_ids:
                line.packet_id.write({
                    "state": "in_stock",
                    "current_location": "office",
                    "rdy_pcs": line.pcs or line.packet_id.rdy_pcs,
                    "rdy_cts": line.cts or line.packet_id.rdy_cts,
                })
                line.packet_id._log_history(action="jobwork_receive",
                                            note=_("Jobwork Receive %s") % rec.name,
                                            process_id=rec.process_id.id,
                                            party_id=rec.ledger_id.id)
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
    loss_cts = fields.Float(string="Loss (cts)", digits=(12, 4))
    labour_amount = fields.Float(string="Labour Amount", digits=(14, 2))
