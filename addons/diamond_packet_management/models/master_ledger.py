from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DiamondLedger(models.Model):
    """Party / Ledger master — covers customers, suppliers, jobworkers, banks.

    Used everywhere a 'Party' is referenced (Inward, Outward, Jobwork, etc.).
    A party can have multiple types (e.g. Customer + Jobworker + Lab).
    """

    _name = "diamond.ledger"
    _description = "Diamond Ledger / Party"
    _inherit = "diamond.master.mixin"

    party_type_ids = fields.Many2many(
        "diamond.party.type",
        "diamond_ledger_party_type_rel",
        "ledger_id",
        "type_id",
        string="Party Types",
        required=True,
        tracking=True,
        default=lambda self: self._default_party_type_ids(),
        help="A party can have multiple roles (Customer, Jobworker, HPHT Vendor, Lab, …).",
    )
    party_type_display = fields.Char(
        string="Types",
        compute="_compute_party_type_display",
        store=True,
    )
    account_group_id = fields.Many2one("diamond.account.group", string="Account Group", tracking=True)
    barcode = fields.Char(string="Party Barcode", help="Used by barcode gun on Inward / Outward forms.", tracking=True)

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

    opening_balance = fields.Float(string="Opening Balance", digits=(16, 2), tracking=True)

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

    @api.depends("party_type_ids", "party_type_ids.name")
    def _compute_party_type_display(self):
        for rec in self:
            rec.party_type_display = ", ".join(rec.party_type_ids.mapped("name"))

    def has_party_type(self, code):
        """Return True if this ledger has the given party type code."""
        self.ensure_one()
        return bool(self.party_type_ids.filtered(lambda t: t.code == code))

    @api.model
    def _default_party_type_ids(self):
        customer = self.env.ref(
            "diamond_packet_management.party_type_customer", raise_if_not_found=False,
        )
        return [(6, 0, customer.ids)] if customer else []

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("barcode") and vals.get("code"):
                vals["barcode"] = "P-" + str(vals["code"]).upper()
            if not vals.get("party_type_ids"):
                vals["party_type_ids"] = self._default_party_type_ids()
        return super().create(vals_list)

    @api.constrains("party_type_ids")
    def _check_party_type_ids(self):
        for rec in self:
            if not rec.party_type_ids:
                raise ValidationError(_("Select at least one Party Type."))
