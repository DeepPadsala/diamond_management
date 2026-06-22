from odoo import api, fields, models


class DiamondLedger(models.Model):
    """Party / Ledger master — covers customers, suppliers, jobworkers, banks.

    Used everywhere a 'Party' is referenced (Inward, Outward, Jobwork, etc.).
    """

    _name = "diamond.ledger"
    _description = "Diamond Ledger / Party"
    _inherit = "diamond.master.mixin"

    party_type = fields.Selection(
        selection=[
            ("customer", "Customer"),
            ("supplier", "Supplier"),
            ("jobworker", "Jobworker"),
            ("hpht_vendor", "HPHT Vendor"),
            ("lab", "Lab"),
            ("bank", "Bank / Cash"),
            ("internal", "Internal Office"),
            ("other", "Other"),
        ],
        string="Party Type",
        default="customer",
        required=True,
    )
    account_group_id = fields.Many2one("diamond.account.group", string="Account Group")
    barcode = fields.Char(string="Party Barcode", help="Used by barcode gun on Inward / Outward forms.")

    address_line = fields.Char(string="Address")
    city = fields.Char(string="City")
    state = fields.Char(string="State")
    country = fields.Char(string="Country")
    zip = fields.Char(string="Zip")
    phone = fields.Char(string="Phone")
    mobile = fields.Char(string="Mobile")
    email = fields.Char(string="Email")
    gst_no = fields.Char(string="GST / Tax No.")
    pan_no = fields.Char(string="PAN")

    opening_balance = fields.Float(string="Opening Balance", digits=(16, 2))

    # Repeat the mixin's code-uniqueness constraint here so it is
    # preserved regardless of how Odoo merges _sql_constraints across
    # an AbstractModel _inherit chain.
    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(code, company_id)",
            "Code must be unique per company.",
        ),
        (
            "barcode_company_uniq",
            "unique(barcode, company_id)",
            "Party barcode must be unique per company.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("barcode") and vals.get("code"):
                vals["barcode"] = "P-" + str(vals["code"]).upper()
        return super().create(vals_list)
