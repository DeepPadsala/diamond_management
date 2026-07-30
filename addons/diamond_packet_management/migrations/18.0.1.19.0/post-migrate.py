from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Move legacy single-slot pending factory fields into per-process rows."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Packet = env["diamond.packet"].sudo()
    Pending = env["diamond.packet.pending.factory"].sudo()
    packets = Packet.search([
        ("pending_factory_process_id", "!=", False),
        ("pending_factory_employee_id", "!=", False),
    ])
    for packet in packets:
        if packet.pending_factory_ids.filtered(
            lambda p, process=packet.pending_factory_process_id: p.process_id == process
        ):
            continue
        Pending.create({
            "packet_id": packet.id,
            "employee_id": packet.pending_factory_employee_id.id,
            "process_id": packet.pending_factory_process_id.id,
            "issue_cts": packet.pending_factory_issue_cts or 0.0,
            "labour_weight_cts": packet.pending_factory_labour_weight_cts or 0.0,
        })
