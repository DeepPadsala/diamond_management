from odoo import fields
from odoo.tests import tagged

from odoo.addons.diamond_packet_management.tests.common import DiamondRollbackTestCommon


@tagged("post_install", "-at_install", "diamond_withdrawal")
class TestEmployeeWithdrawal(DiamondRollbackTestCommon):

    def _create_worker_labour_entry(self, packet, amount=800.0):
        return self.env["diamond.labour.entry"].create({
            "entry_type": "worker",
            "company_id": self.company.id,
            "date": fields.Datetime.now(),
            "employee_id": self.employee.id,
            "process_id": self.process_polish.id,
            "packet_id": packet.id,
            "receive_model": "diamond.factory.receive",
            "receive_line_id": 1,
            "receive_doc_name": "TEST/FR/1",
            "amount": amount,
            "rate": 10.0,
            "state": "draft",
        })

    def _create_slip_with_entry(self, packet, amount):
        entry = self._create_worker_labour_entry(packet, amount=amount)
        slip = self.env["diamond.salary.slip"].create({
            "employee_id": self.employee.id,
            "period_month": str(fields.Date.today().month),
            "period_year": fields.Date.today().year,
            "line_ids": [(0, 0, {
                "labour_entry_id": entry.id,
                "process_id": entry.process_id.id,
                "packet_id": packet.id,
                "amount": amount,
            })],
        })
        entry.salary_slip_id = slip.id
        return slip

    def test_withdrawal_auto_applies_to_existing_draft_slip(self):
        packet = self._create_packet(rdy_cts=5.0)
        slip = self._create_slip_with_entry(packet, 1972.0)
        self.assertAlmostEqual(slip.withdrawal_deduction, 0.0)

        withdrawal = self.env["diamond.employee.withdrawal"].create({
            "employee_id": self.employee.id,
            "amount": 500.0,
        })
        withdrawal.action_confirm()
        slip.invalidate_recordset()

        self.assertAlmostEqual(slip.withdrawal_deduction, 500.0)
        self.assertAlmostEqual(slip.net_payable_amount, 1472.0)

    def test_withdrawal_deducted_from_salary_slip(self):
        packet = self._create_packet(rdy_cts=5.0)
        withdrawal = self.env["diamond.employee.withdrawal"].create({
            "employee_id": self.employee.id,
            "amount": 1000.0,
        })
        withdrawal.action_confirm()

        slip = self._create_slip_with_entry(packet, 8000.0)
        slip.action_apply_withdrawals()

        self.assertAlmostEqual(slip.gross_amount, 8000.0)
        self.assertAlmostEqual(slip.withdrawal_deduction, 1000.0)
        self.assertAlmostEqual(slip.net_payable_amount, 7000.0)
        self.assertAlmostEqual(withdrawal.balance_amount, 0.0)

    def test_withdrawal_carry_forward_to_next_month(self):
        packet = self._create_packet(rdy_cts=5.0)
        withdrawal = self.env["diamond.employee.withdrawal"].create({
            "employee_id": self.employee.id,
            "amount": 5000.0,
        })
        withdrawal.action_confirm()

        slip_jan = self._create_slip_with_entry(packet, 2000.0)
        slip_jan.action_apply_withdrawals()

        self.assertAlmostEqual(slip_jan.net_payable_amount, 0.0)
        self.assertAlmostEqual(withdrawal.balance_amount, 3000.0)
        self.assertAlmostEqual(self.employee.advance_balance, 3000.0)

        slip_feb = self.env["diamond.salary.slip"].create({
            "employee_id": self.employee.id,
            "period_month": str((fields.Date.today().month % 12) + 1),
            "period_year": fields.Date.today().year,
            "line_ids": [(0, 0, {
                "process_id": self.process_polish.id,
                "packet_id": packet.id,
                "amount": 4000.0,
            })],
        })
        slip_feb.action_apply_withdrawals()

        self.assertAlmostEqual(slip_feb.withdrawal_deduction, 3000.0)
        self.assertAlmostEqual(slip_feb.net_payable_amount, 1000.0)
        self.assertAlmostEqual(withdrawal.balance_amount, 0.0)
