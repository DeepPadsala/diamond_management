from odoo import api, models

# Default master rows loaded on install (diamond_demo_masters.xml).
# Kept here so every new company gets the same starter dataset.

_SHAPE_DEFAULTS = [
    {"code": "RD", "name": "Round", "short_code": "RD"},
    {"code": "PR", "name": "Princess", "short_code": "PR"},
    {"code": "OV", "name": "Oval", "short_code": "OV"},
    {"code": "MQ", "name": "Marquise", "short_code": "MQ"},
    {"code": "EM", "name": "Emerald", "short_code": "EM"},
    {"code": "PE", "name": "Pear", "short_code": "PE"},
    {"code": "CU", "name": "Cushion", "short_code": "CU"},
    {"code": "ASS", "name": "Assher", "short_code": "ASS"},
]

_COLOR_DEFAULTS = [
    {"code": "D", "name": "D", "grade_value": 1},
    {"code": "E", "name": "E", "grade_value": 2},
    {"code": "F", "name": "F", "grade_value": 3},
    {"code": "G", "name": "G", "grade_value": 4},
    {"code": "H", "name": "H", "grade_value": 5},
    {"code": "I", "name": "I", "grade_value": 6},
    {"code": "J", "name": "J", "grade_value": 7},
    {"code": "K", "name": "K", "grade_value": 8},
]

_CLARITY_DEFAULTS = [
    {"code": "FL", "name": "Flawless", "grade_value": 1},
    {"code": "IF", "name": "Internally Flawless", "grade_value": 2},
    {"code": "VVS1", "name": "VVS1", "grade_value": 3},
    {"code": "VVS2", "name": "VVS2", "grade_value": 4},
    {"code": "VS1", "name": "VS1", "grade_value": 5},
    {"code": "VS2", "name": "VS2", "grade_value": 6},
    {"code": "SI1", "name": "SI1", "grade_value": 7},
    {"code": "SI2", "name": "SI2", "grade_value": 8},
    {"code": "I1", "name": "I1", "grade_value": 9},
]

_CUT_DEFAULTS = [
    {"code": "EX", "name": "Excellent", "grade_value": 1},
    {"code": "VG", "name": "Very Good", "grade_value": 2},
    {"code": "GD", "name": "Good", "grade_value": 3},
    {"code": "FR", "name": "Fair", "grade_value": 4},
    {"code": "PR", "name": "Poor", "grade_value": 5},
]

_POLISH_DEFAULTS = [
    {"code": "EX", "name": "Excellent", "grade_value": 1},
    {"code": "VG", "name": "Very Good", "grade_value": 2},
    {"code": "GD", "name": "Good", "grade_value": 3},
]

_SYMMETRY_DEFAULTS = [
    {"code": "EX", "name": "Excellent", "grade_value": 1},
    {"code": "VG", "name": "Very Good", "grade_value": 2},
    {"code": "GD", "name": "Good", "grade_value": 3},
]

_FLUORESCENCE_DEFAULTS = [
    {"code": "N", "name": "None", "grade_value": 1},
    {"code": "F", "name": "Faint", "grade_value": 2},
    {"code": "M", "name": "Medium", "grade_value": 3},
    {"code": "S", "name": "Strong", "grade_value": 4},
    {"code": "VS", "name": "Very Strong", "grade_value": 5},
]

_LAB_DEFAULTS = [
    {"code": "GIA", "name": "GIA", "full_name": "Gemological Institute of America"},
    {"code": "IGI", "name": "IGI", "full_name": "International Gemological Institute"},
    {"code": "HRD", "name": "HRD", "full_name": False},
]

_PROCESS_DEFAULTS = [
    {"code": "SARIN", "name": "Sarine Planning", "process_type": "internal", "sequence_no": 10},
    {"code": "CUT", "name": "Cutting", "process_type": "internal", "sequence_no": 20},
    {"code": "POL", "name": "Polishing", "process_type": "internal", "sequence_no": 30},
    {"code": "REP", "name": "Repair", "process_type": "internal", "sequence_no": 40},
    {"code": "HPHT", "name": "HPHT Treatment", "process_type": "hpht", "sequence_no": 50},
    {"code": "JOB", "name": "Jobwork", "process_type": "jobwork", "sequence_no": 60},
    {"code": "CERT", "name": "Certification", "process_type": "certify", "sequence_no": 70},
]

_ACCOUNT_GROUP_DEFAULTS = [
    {"code": "SD", "name": "Sundry Debtors", "nature": "debtor"},
    {"code": "SC", "name": "Sundry Creditors", "nature": "creditor"},
    {"code": "JW", "name": "Jobworkers", "nature": "creditor"},
]

_MASTER_SPECS = (
    ("diamond.shape", _SHAPE_DEFAULTS),
    ("diamond.color", _COLOR_DEFAULTS),
    ("diamond.clarity", _CLARITY_DEFAULTS),
    ("diamond.cut", _CUT_DEFAULTS),
    ("diamond.polish", _POLISH_DEFAULTS),
    ("diamond.symmetry", _SYMMETRY_DEFAULTS),
    ("diamond.fluorescence", _FLUORESCENCE_DEFAULTS),
    ("diamond.lab", _LAB_DEFAULTS),
    ("diamond.process", _PROCESS_DEFAULTS),
    ("diamond.account.group", _ACCOUNT_GROUP_DEFAULTS),
)

_SEQUENCE_DEFAULTS = (
    ("diamond.packet", "Diamond Packet", "PKT/%(year)s/", 6),
    ("diamond.inward", "Diamond Inward", "IN/%(year)s/", 5),
    ("diamond.outward", "Diamond Outward", "OUT/%(year)s/", 5),
    ("diamond.process.issue", "Diamond Process Issue", "PI/%(year)s/", 5),
    ("diamond.process.receive", "Diamond Process Receive", "PR/%(year)s/", 5),
    ("diamond.jobwork.issue", "Diamond Jobwork Issue", "JI/%(year)s/", 5),
    ("diamond.jobwork.receive", "Diamond Jobwork Receive", "JR/%(year)s/", 5),
    ("diamond.factory.issue", "Diamond Factory Issue", "FI/%(year)s/", 5),
    ("diamond.factory.receive", "Diamond Factory Receive", "FR/%(year)s/", 5),
    ("diamond.hpht.issue", "Diamond HPHT Issue", "HI/%(year)s/", 5),
    ("diamond.hpht.receive", "Diamond HPHT Receive", "HR/%(year)s/", 5),
    ("diamond.party.invoice", "Party Labour Invoice", "PINV/%(year)s/", 5),
    ("diamond.salary.slip", "Worker Salary Slip", "SAL/%(year)s/", 5),
    ("diamond.employee.withdrawal", "Employee Withdrawal", "WD/%(year)s/", 5),
)


class DiamondCompanyDefaults(models.AbstractModel):
    """Seed default diamond masters and sequences for a company."""

    _name = "diamond.company.defaults"
    _description = "Diamond Company Default Data"

    @api.model
    def create_for_companies(self, companies):
        for company in companies:
            self.create_for_company(company)

    @api.model
    def create_for_company(self, company):
        company = company.sudo()
        self._create_master_defaults(company)
        self._create_sequence_defaults(company)

    @api.model
    def _create_master_defaults(self, company):
        if self.env["diamond.shape"].sudo().search_count([("company_id", "=", company.id)]):
            return

        for model_name, rows in _MASTER_SPECS:
            vals_list = [{"company_id": company.id, **row} for row in rows]
            self.env[model_name].sudo().create(vals_list)

    @api.model
    def _create_sequence_defaults(self, company):
        Sequence = self.env["ir.sequence"].sudo()
        existing_codes = set(
            Sequence.search([("company_id", "=", company.id)]).mapped("code")
        )
        to_create = []
        for code, name, prefix, padding in _SEQUENCE_DEFAULTS:
            if code in existing_codes:
                continue
            to_create.append({
                "name": name,
                "code": code,
                "prefix": prefix,
                "padding": padding,
                "number_increment": 1,
                "company_id": company.id,
            })
        if to_create:
            Sequence.create(to_create)
