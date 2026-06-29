from odoo import fields
from odoo.tests import tagged

from odoo.addons.diamond_packet_management.tests.common import DiamondRollbackTestCommon


@tagged("post_install", "-at_install", "diamond_monthly_labour")
class TestMonthlyLabourWizard(DiamondRollbackTestCommon):

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

    def test_monthly_wizard_creates_supplemental_slip_after_paid(self):
        packet = self._create_packet(rdy_cts=5.0)
        month = str(fields.Date.today().month)
        year = fields.Date.today().year

        entry1 = self._create_worker_labour_entry(packet, 1000.0)
        slip1 = self.env["diamond.salary.slip"].create({
            "employee_id": self.employee.id,
            "period_month": month,
            "period_year": year,
            "line_ids": [(0, 0, {
                "labour_entry_id": entry1.id,
                "process_id": entry1.process_id.id,
                "packet_id": packet.id,
                "amount": 1000.0,
            })],
        })
        entry1.salary_slip_id = slip1.id
        slip1.action_confirm()
        slip1.action_mark_paid()

        entry2 = self._create_worker_labour_entry(packet, 500.0)
        wizard = self.env["diamond.monthly.labour.wizard"].create({
            "period_month": month,
            "period_year": year,
            "generate_party_invoices": False,
            "generate_salary_slips": True,
        })
        wizard.action_generate()

        slips = self.env["diamond.salary.slip"].search([
            ("employee_id", "=", self.employee.id),
            ("period_month", "=", month),
            ("period_year", "=", year),
            ("state", "!=", "cancelled"),
        ])
        self.assertEqual(len(slips), 2)
        supplemental = slips.filtered(lambda s: s.is_supplemental)
        self.assertEqual(len(supplemental), 1)
        self.assertEqual(supplemental.state, "draft")
        self.assertEqual(entry2.salary_slip_id, supplemental)
        self.assertAlmostEqual(supplemental.gross_amount, 500.0)
