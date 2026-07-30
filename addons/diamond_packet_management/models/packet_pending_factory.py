from odoo import fields, models


class DiamondPacketPendingFactory(models.Model):
    """Unfinished factory process on a packet (from Un-Processed receive).

    A packet can have several pending processes at once (e.g. PLS unfinished
    while BLK is issued and completed). Each process keeps its own worker
    and labour weights until that process is finally completed.
    """

    _name = "diamond.packet.pending.factory"
    _description = "Pending Factory Process"
    _order = "id"

    packet_id = fields.Many2one(
        "diamond.packet", string="Packet", required=True, ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(related="packet_id.company_id", store=True, index=True)
    employee_id = fields.Many2one("diamond.employee", string="Worker", required=True, index=True)
    process_id = fields.Many2one("diamond.process", string="Process", required=True, index=True)
    issue_cts = fields.Float(
        string="Process Start Weight", digits=(12, 4),
        help="Packet weight when this unfinished process first started.",
    )
    labour_weight_cts = fields.Float(
        string="Labour Weight", digits=(12, 4),
        help="Weight used for labour rate lookup on final completion.",
    )

    _sql_constraints = [
        (
            "packet_process_uniq",
            "unique(packet_id, process_id)",
            "A packet can only have one pending entry per process.",
        ),
    ]
