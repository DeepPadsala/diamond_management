from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.diamond_packet_management.tests.common import DiamondRollbackTestCommon


@tagged("post_install", "-at_install", "diamond_rollback")
class TestPacketTransactionRollback(DiamondRollbackTestCommon):

    # ── helpers ──────────────────────────────────────────────────────

    def _assert_no_confirmed_lines(self, packet, line_model):
        count = self.env[line_model].search_count([
            ("packet_id", "=", packet.id),
            ("doc_id.state", "=", "confirmed"),
        ])
        self.assertEqual(count, 0, f"Expected no confirmed {line_model} for {packet.barcode}")

    # ── process ──────────────────────────────────────────────────────

    def test_rollback_process_issue(self):
        packet = self._create_packet(rdy_cts=5.0)
        self._process_issue(packet, issue_cts=5.0)
        self.assertEqual(packet.state, "in_process")

        packet.action_rollback_last_transaction()
        packet.invalidate_recordset()

        self.assertEqual(packet.state, "in_stock")
        self.assertFalse(packet.current_process_id)
        self._assert_no_confirmed_lines(packet, "diamond.process.issue.line")

    def test_rollback_process_receive_restores_weight(self):
        packet = self._create_packet(rdy_cts=5.0)
        issue_cts = 5.0
        receive_cts = 4.5
        self._process_issue(packet, issue_cts=issue_cts)
        receive = self._process_receive(packet, receive_cts=receive_cts)
        receive_line = receive.line_ids[:1]
        self.assertEqual(packet.rdy_cts, receive_cts)

        packet.action_rollback_last_transaction()
        packet.invalidate_recordset()

        self.assertEqual(packet.state, "in_process")
        self.assertAlmostEqual(packet.rdy_cts, issue_cts)
        self.assertFalse(self.env["diamond.labour.entry"].search_count([
            ("receive_model", "=", "diamond.process.receive"),
            ("receive_line_id", "=", receive_line.id),
        ]))

    def test_rollback_lifo_issue_then_receive(self):
        packet = self._create_packet(rdy_cts=5.0)
        self._process_issue(packet, issue_cts=5.0)
        self._process_receive(packet, receive_cts=4.8)
        self.assertEqual(packet.state, "in_stock")

        packet.action_rollback_last_transaction()
        packet.invalidate_recordset()
        self.assertEqual(packet.state, "in_process")

        packet.action_rollback_last_transaction()
        packet.invalidate_recordset()
        self.assertEqual(packet.state, "in_stock")
        self.assertFalse(packet.current_process_id)

    # ── factory ──────────────────────────────────────────────────────

    def test_rollback_factory_receive_restores_weight_and_labour(self):
        packet = self._create_packet(rdy_cts=5.0)
        issue_cts = 5.0
        receive_cts = 4.5
        self._factory_issue(packet, issue_cts=issue_cts)
        receive = self._factory_receive(packet, receive_cts=receive_cts)
        receive_line = receive.line_ids[:1]
        entries = self.env["diamond.labour.entry"].search([
            ("receive_model", "=", "diamond.factory.receive"),
            ("receive_line_id", "=", receive_line.id),
        ])
        self.assertTrue(entries)
        self.assertEqual(packet.rdy_cts, receive_cts)

        packet.action_rollback_last_transaction()
        packet.invalidate_recordset()

        self.assertEqual(packet.state, "in_factory")
        self.assertAlmostEqual(packet.rdy_cts, issue_cts)
        self.assertFalse(entries.exists())

    def test_rollback_factory_unprocessed_receive(self):
        packet = self._create_packet(rdy_cts=5.0)
        issue_cts = 5.0
        self._factory_issue(packet, issue_cts=issue_cts)
        receive = self._factory_receive(packet, receive_cts=4.8, unprocessed=True)
        receive_line = receive.line_ids[:1]
        self.assertEqual(packet.state, "in_stock")
        self.assertTrue(packet.pending_factory_employee_id)

        packet.action_rollback_last_transaction()
        packet.invalidate_recordset()

        self.assertEqual(packet.state, "in_factory")
        self.assertAlmostEqual(packet.rdy_cts, issue_cts)
        self.assertFalse(packet.pending_factory_employee_id)
        self.assertFalse(self.env["diamond.labour.entry"].search_count([
            ("receive_model", "=", "diamond.factory.receive"),
            ("receive_line_id", "=", receive_line.id),
        ]))

    def test_rollback_factory_resume_after_unprocessed(self):
        packet = self._create_packet(rdy_cts=5.0)
        self._factory_issue(packet, issue_cts=5.0)
        self._factory_receive(packet, receive_cts=4.8, unprocessed=True)
        self._factory_issue(packet, issue_cts=4.8)
        complete = self._factory_receive(packet, receive_cts=4.5)
        complete_line = complete.line_ids[:1]
        entries = self.env["diamond.labour.entry"].search([
            ("receive_model", "=", "diamond.factory.receive"),
            ("receive_line_id", "=", complete_line.id),
        ])
        self.assertTrue(entries)

        packet.action_rollback_last_transaction()
        packet.invalidate_recordset()

        self.assertEqual(packet.state, "in_factory")
        self.assertTrue(packet.pending_factory_employee_id)
        self.assertFalse(entries.exists())

    # ── jobwork / hpht ───────────────────────────────────────────────

    def test_rollback_jobwork_receive_restores_weight(self):
        packet = self._create_packet(rdy_cts=5.0)
        issue_cts = 5.0
        receive_cts = 4.7
        self._jobwork_issue(packet, issue_cts=issue_cts)
        self._jobwork_receive(packet, receive_cts=receive_cts)
        self.assertEqual(packet.rdy_cts, receive_cts)

        packet.action_rollback_last_transaction()
        packet.invalidate_recordset()

        self.assertEqual(packet.state, "in_jobwork")
        self.assertAlmostEqual(packet.rdy_cts, issue_cts)

    def test_rollback_hpht_receive_restores_weight_and_party_labour(self):
        packet = self._create_packet(rdy_cts=5.0)
        issue_cts = 5.0
        receive_cts = 4.9
        self._hpht_issue(packet, issue_cts=issue_cts)
        receive = self._hpht_receive(packet, receive_cts=receive_cts)
        receive_line = receive.line_ids[:1]
        entries = self.env["diamond.labour.entry"].search([
            ("receive_model", "=", "diamond.hpht.receive"),
            ("receive_line_id", "=", receive_line.id),
        ])
        self.assertTrue(entries)

        packet.action_rollback_last_transaction()
        packet.invalidate_recordset()

        self.assertEqual(packet.state, "in_hpht")
        self.assertAlmostEqual(packet.rdy_cts, issue_cts)
        self.assertFalse(entries.exists())

    # ── billing protection ───────────────────────────────────────────

    def test_rollback_blocked_when_labour_invoiced(self):
        packet = self._create_packet(rdy_cts=5.0)
        self._factory_issue(packet, issue_cts=5.0)
        receive = self._factory_receive(packet, receive_cts=4.5)
        receive_line = receive.line_ids[:1]
        entries = self.env["diamond.labour.entry"].search([
            ("receive_model", "=", "diamond.factory.receive"),
            ("receive_line_id", "=", receive_line.id),
        ])
        entries.write({"state": "invoiced"})

        with self.assertRaises(UserError):
            packet.action_rollback_last_transaction()

    def test_rollback_blocked_when_labour_on_draft_party_invoice(self):
        packet = self._create_packet(rdy_cts=5.0)
        self._factory_issue(packet, issue_cts=5.0)
        receive = self._factory_receive(packet, receive_cts=4.5)
        receive_line = receive.line_ids[:1]
        party_entry = self.env["diamond.labour.entry"].search([
            ("receive_model", "=", "diamond.factory.receive"),
            ("receive_line_id", "=", receive_line.id),
            ("entry_type", "=", "party"),
        ], limit=1)
        invoice = self.env["diamond.party.invoice"].create({
            "ledger_id": party_entry.ledger_id.id,
            "period_month": str(fields.Date.today().month),
            "period_year": fields.Date.today().year,
            "date": fields.Date.today(),
        })
        self.env["diamond.party.invoice.line"].create({
            "invoice_id": invoice.id,
            "labour_entry_id": party_entry.id,
            "process_id": party_entry.process_id.id,
            "packet_id": party_entry.packet_id.id,
            "amount": party_entry.amount,
        })
        party_entry.party_invoice_id = invoice.id

        with self.assertRaises(UserError):
            packet.action_rollback_last_transaction()

    def test_rollback_blocked_when_labour_on_draft_salary_slip(self):
        packet = self._create_packet(rdy_cts=5.0)
        self._factory_issue(packet, issue_cts=5.0)
        receive = self._factory_receive(packet, receive_cts=4.5)
        receive_line = receive.line_ids[:1]
        worker_entry = self.env["diamond.labour.entry"].search([
            ("receive_model", "=", "diamond.factory.receive"),
            ("receive_line_id", "=", receive_line.id),
            ("entry_type", "=", "worker"),
        ], limit=1)
        slip = self.env["diamond.salary.slip"].create({
            "employee_id": worker_entry.employee_id.id,
            "period_month": str(fields.Date.today().month),
            "period_year": fields.Date.today().year,
            "date": fields.Date.today(),
        })
        self.env["diamond.salary.slip.line"].create({
            "slip_id": slip.id,
            "labour_entry_id": worker_entry.id,
            "process_id": worker_entry.process_id.id,
            "packet_id": worker_entry.packet_id.id,
            "amount": worker_entry.amount,
        })
        worker_entry.salary_slip_id = slip.id

        with self.assertRaises(UserError):
            packet.action_rollback_last_transaction()

    def test_rollback_allowed_after_cancel_party_invoice(self):
        packet = self._create_packet(rdy_cts=5.0)
        self._factory_issue(packet, issue_cts=5.0)
        receive = self._factory_receive(packet, receive_cts=4.5)
        receive_line = receive.line_ids[:1]
        party_entry = self.env["diamond.labour.entry"].search([
            ("receive_model", "=", "diamond.factory.receive"),
            ("receive_line_id", "=", receive_line.id),
            ("entry_type", "=", "party"),
        ], limit=1)
        invoice = self.env["diamond.party.invoice"].create({
            "ledger_id": party_entry.ledger_id.id,
            "period_month": str(fields.Date.today().month),
            "period_year": fields.Date.today().year,
            "date": fields.Date.today(),
            "line_ids": [(0, 0, {
                "labour_entry_id": party_entry.id,
                "process_id": party_entry.process_id.id,
                "packet_id": party_entry.packet_id.id,
                "amount": party_entry.amount,
            })],
        })
        party_entry.party_invoice_id = invoice.id
        invoice.action_cancel()

        packet.action_rollback_last_transaction()
        packet.invalidate_recordset()
        self.assertEqual(packet.state, "in_factory")
        self.assertFalse(party_entry.exists())
