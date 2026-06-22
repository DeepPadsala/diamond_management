from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    code = fields.Char(
        string="Code",
        help="Short code used in packet barcodes (companycode-partycode-number).",
    )

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        if self.env.registry.ready:
            companies._diamond_create_default_data()
        return companies

    def _diamond_create_default_data(self):
        self.env["diamond.company.defaults"].sudo().create_for_companies(self)
