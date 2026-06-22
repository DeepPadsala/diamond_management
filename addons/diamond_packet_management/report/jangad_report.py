from odoo import models


class ReportDiamondJangad(models.AbstractModel):
    _name = "report.diamond_packet_management.report_jangad_slip"
    _description = "Jangad Thermal Slip Report"

    def _get_report_values(self, docids, data=None):
        wizard = self.env["diamond.jangad.print.wizard"].browse(docids)
        wizard.ensure_one()
        doc = self.env[wizard.res_model].browse(wizard.res_id)
        slips = self.env["diamond.jangad.print.service"].build_slips(
            doc, wizard.movement_type,
        )
        return {
            "doc_ids": docids,
            "doc_model": "diamond.jangad.print.wizard",
            "docs": wizard,
            "slips": slips,
            "company": doc.company_id,
        }
