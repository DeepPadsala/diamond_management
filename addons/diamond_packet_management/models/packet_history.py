from odoo import fields, models


class DiamondPacketHistory(models.Model):
    """Immutable audit trail for every packet movement.

    Created automatically by ``diamond.packet`` whenever state, location,
    holder, or process changes. Records who, when, what, where.
    """

    _name = "diamond.packet.history"
    _description = "Diamond Packet History"
    _order = "create_date desc, id desc"
    _rec_name = "packet_id"

    packet_id = fields.Many2one("diamond.packet", string="Packet", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", string="Company", required=True, index=True)

    action = fields.Selection(
        selection=[
            ("create", "Create"),
            ("update", "Update"),
            ("inward", "Inward"),
            ("outward", "Outward"),
            ("process_issue", "Process Issue"),
            ("process_receive", "Process Receive"),
            ("jobwork_issue", "Jobwork Issue"),
            ("jobwork_receive", "Jobwork Receive"),
            ("factory_issue", "Factory Issue"),
            ("factory_receive", "Factory Receive"),
            ("hpht_issue", "HPHT Issue"),
            ("hpht_receive", "HPHT Receive"),
            ("improvement_return", "Improvement Return"),
            ("split", "Split into Children"),
            ("rollback", "Rollback"),
            ("note", "Note"),
        ],
        string="Action",
        required=True,
        default="update",
    )

    state = fields.Char(string="State Snapshot")
    location = fields.Char(string="Location Snapshot")

    process_id = fields.Many2one("diamond.process", string="Process")
    ledger_id = fields.Many2one("diamond.ledger", string="Party")
    employee_id = fields.Many2one("diamond.employee", string="Employee")
    user_id = fields.Many2one("res.users", string="User")

    rdy_pcs = fields.Integer(string="Pcs at Event")
    rdy_cts = fields.Float(string="Cts at Event", digits=(12, 4))

    note = fields.Text(string="Note")

    # ── make the log effectively immutable ──
    def write(self, vals):
        # only allow writing 'note' (correction) — never the rest
        forbidden = set(vals.keys()) - {"note"}
        if forbidden and not self.env.user.has_group("base.group_system"):
            from odoo.exceptions import AccessError
            raise AccessError("Packet history entries are immutable.")
        return super().write(vals)

    def unlink(self):
        from odoo.exceptions import AccessError
        if not self.env.user.has_group("base.group_system"):
            raise AccessError("Packet history entries cannot be deleted.")
        return super().unlink()
