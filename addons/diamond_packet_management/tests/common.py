from odoo.tests import TransactionCase


class DiamondRollbackTestCommon(TransactionCase):
    """Shared fixtures for packet transaction rollback tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.shape = cls.env.ref("diamond_packet_management.shape_round")
        cls.color = cls.env.ref("diamond_packet_management.color_g")
        cls.clarity = cls.env.ref("diamond_packet_management.clarity_vs1")
        cls.process_cut = cls.env.ref("diamond_packet_management.process_cutting")
        cls.process_polish = cls.env.ref("diamond_packet_management.process_polish")
        cls.process_jobwork = cls.env.ref("diamond_packet_management.process_jobwork")
        cls.process_hpht = cls.env.ref("diamond_packet_management.process_hpht")
        cls.acct_debtor = cls.env.ref("diamond_packet_management.acct_grp_debtor")
        cls.acct_jobworker = cls.env.ref("diamond_packet_management.acct_grp_jobworker")

        cls.party = cls.env["diamond.ledger"].create({
            "code": "RBTPARTY",
            "name": "Rollback Test Party",
            "party_type_ids": [(6, 0, [cls.env.ref("diamond_packet_management.party_type_customer").id])],
            "account_group_id": cls.acct_debtor.id,
            "barcode": "RBTPARTY",
        })
        cls.jobworker = cls.env["diamond.ledger"].create({
            "code": "RBTJOB",
            "name": "Rollback Jobworker",
            "party_type_ids": [(6, 0, [cls.env.ref("diamond_packet_management.party_type_jobworker").id])],
            "account_group_id": cls.acct_jobworker.id,
        })
        cls.hpht_vendor = cls.env["diamond.ledger"].create({
            "code": "RBTHPHT",
            "name": "Rollback HPHT Vendor",
            "party_type_ids": [(6, 0, [cls.env.ref("diamond_packet_management.party_type_hpht_vendor").id])],
            "account_group_id": cls.acct_debtor.id,
        })
        cls.employee = cls.env["diamond.employee"].create({
            "code": "RBTE1",
            "name": "Rollback Worker",
            "process_ids": [(6, 0, [cls.process_cut.id, cls.process_polish.id])],
        })

        cls.env["diamond.party.labour"].create({
            "ledger_id": cls.party.id,
            "process_id": cls.process_cut.id,
            "from_cts": 0.0,
            "to_cts": 100.0,
            "rate": 10.0,
            "multiply_by": True,
            "multiply_by_weight_loss": True,
        })
        cls.env["diamond.party.labour"].create({
            "ledger_id": cls.party.id,
            "process_id": cls.process_polish.id,
            "from_cts": 0.0,
            "to_cts": 100.0,
            "rate": 10.0,
            "multiply_by": True,
            "multiply_by_weight_loss": True,
        })
        cls.env["diamond.party.labour"].create({
            "ledger_id": cls.party.id,
            "process_id": cls.process_hpht.id,
            "from_cts": 0.0,
            "to_cts": 100.0,
            "rate": 10.0,
            "multiply_by": True,
            "multiply_by_weight_loss": True,
        })
        cls.env["diamond.worker.labour"].create({
            "process_id": cls.process_cut.id,
            "from_cts": 0.0,
            "to_cts": 100.0,
            "rate": 5.0,
            "multiply_by": True,
            "multiply_by_weight_loss": True,
        })
        cls.env["diamond.worker.labour"].create({
            "process_id": cls.process_polish.id,
            "from_cts": 0.0,
            "to_cts": 100.0,
            "rate": 5.0,
            "multiply_by": True,
            "multiply_by_weight_loss": True,
        })

    def _create_packet(self, rdy_cts=5.0):
        inward = self.env["diamond.inward"].create({
            "ledger_id": self.party.id,
            "line_ids": [(0, 0, {
                "shape_id": self.shape.id,
                "color_id": self.color.id,
                "clarity_id": self.clarity.id,
                "org_pcs": 1,
                "org_cts": rdy_cts,
                "expected_cts": rdy_cts,
            })],
        })
        inward.action_confirm()
        return inward.line_ids.packet_id

    def _process_issue(self, packet, issue_cts=None, process=None):
        issue_cts = issue_cts if issue_cts is not None else packet.rdy_cts
        process = process or self.process_cut
        doc = self.env["diamond.process.issue"].create({
            "process_id": process.id,
            "ledger_id": self.party.id,
            "line_ids": [(0, 0, {
                "packet_id": packet.id,
                "pcs": packet.rdy_pcs,
                "cts": issue_cts,
            })],
        })
        doc.with_context(skip_jangad_prompt=True).action_confirm()
        packet.invalidate_recordset()
        return doc

    def _process_receive(self, packet, receive_cts, process=None):
        process = process or self.process_cut
        doc = self.env["diamond.process.receive"].create({
            "process_id": process.id,
            "ledger_id": self.party.id,
            "line_ids": [(0, 0, {
                "packet_id": packet.id,
                "pcs": packet.rdy_pcs,
                "cts": receive_cts,
                "loss_cts": max((packet.rdy_cts or 0.0) - receive_cts, 0.0),
            })],
        })
        doc.with_context(skip_jangad_prompt=True).action_confirm()
        packet.invalidate_recordset()
        return doc

    def _factory_issue(self, packet, issue_cts=None, process=None):
        issue_cts = issue_cts if issue_cts is not None else packet.rdy_cts
        process = process or self.process_polish
        doc = self.env["diamond.factory.issue"].create({
            "process_id": process.id,
            "employee_id": self.employee.id,
            "line_ids": [(0, 0, {
                "packet_id": packet.id,
                "pcs": packet.rdy_pcs,
                "cts": issue_cts,
            })],
        })
        doc.with_context(skip_jangad_prompt=True).action_confirm()
        packet.invalidate_recordset()
        return doc

    def _factory_receive(self, packet, receive_cts, unprocessed=False, process=None):
        process = process or self.process_polish
        issue_cts = packet.rdy_cts or receive_cts
        doc = self.env["diamond.factory.receive"].create({
            "process_id": process.id,
            "employee_id": self.employee.id,
            "line_ids": [(0, 0, {
                "packet_id": packet.id,
                "pcs": packet.rdy_pcs,
                "cts": receive_cts,
                "loss_cts": 0.0 if unprocessed else max(issue_cts - receive_cts, 0.0),
                "unprocessed": unprocessed,
            })],
        })
        doc.with_context(skip_jangad_prompt=True).action_confirm()
        packet.invalidate_recordset()
        return doc

    def _jobwork_issue(self, packet, issue_cts=None):
        issue_cts = issue_cts if issue_cts is not None else packet.rdy_cts
        doc = self.env["diamond.jobwork.issue"].create({
            "process_id": self.process_jobwork.id,
            "ledger_id": self.jobworker.id,
            "line_ids": [(0, 0, {
                "packet_id": packet.id,
                "pcs": packet.rdy_pcs,
                "cts": issue_cts,
            })],
        })
        doc.with_context(skip_jangad_prompt=True).action_confirm()
        packet.invalidate_recordset()
        return doc

    def _jobwork_receive(self, packet, receive_cts):
        issue_cts = packet.rdy_cts or receive_cts
        doc = self.env["diamond.jobwork.receive"].create({
            "process_id": self.process_jobwork.id,
            "ledger_id": self.jobworker.id,
            "line_ids": [(0, 0, {
                "packet_id": packet.id,
                "pcs": packet.rdy_pcs,
                "cts": receive_cts,
                "loss_cts": max(issue_cts - receive_cts, 0.0),
            })],
        })
        doc.with_context(skip_jangad_prompt=True).action_confirm()
        packet.invalidate_recordset()
        return doc

    def _hpht_issue(self, packet, issue_cts=None):
        issue_cts = issue_cts if issue_cts is not None else packet.rdy_cts
        doc = self.env["diamond.hpht.issue"].create({
            "process_id": self.process_hpht.id,
            "ledger_id": self.hpht_vendor.id,
            "line_ids": [(0, 0, {
                "packet_id": packet.id,
                "pcs": packet.rdy_pcs,
                "cts": issue_cts,
            })],
        })
        doc.with_context(skip_jangad_prompt=True).action_confirm()
        packet.invalidate_recordset()
        return doc

    def _hpht_receive(self, packet, receive_cts):
        issue_cts = packet.rdy_cts or receive_cts
        doc = self.env["diamond.hpht.receive"].create({
            "process_id": self.process_hpht.id,
            "ledger_id": self.hpht_vendor.id,
            "line_ids": [(0, 0, {
                "packet_id": packet.id,
                "pcs": packet.rdy_pcs,
                "cts": receive_cts,
                "loss_cts": max(issue_cts - receive_cts, 0.0),
            })],
        })
        doc.with_context(skip_jangad_prompt=True).action_confirm()
        packet.invalidate_recordset()
        return doc
