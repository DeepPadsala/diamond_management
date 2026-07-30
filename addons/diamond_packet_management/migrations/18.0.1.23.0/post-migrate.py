from odoo import SUPERUSER_ID, api


_TYPE_XMLIDS = {
    "customer": "diamond_packet_management.party_type_customer",
    "supplier": "diamond_packet_management.party_type_supplier",
    "jobworker": "diamond_packet_management.party_type_jobworker",
    "hpht_vendor": "diamond_packet_management.party_type_hpht_vendor",
    "lab": "diamond_packet_management.party_type_lab",
    "bank": "diamond_packet_management.party_type_bank",
    "internal": "diamond_packet_management.party_type_internal",
    "other": "diamond_packet_management.party_type_other",
}


def migrate(cr, version):
    """Copy legacy single party_type into party_type_ids."""
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'diamond_ledger'
           AND column_name = 'party_type'
        """
    )
    if not cr.fetchone():
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("SELECT id, party_type FROM diamond_ledger WHERE party_type IS NOT NULL")
    rows = cr.fetchall()
    for ledger_id, code in rows:
        xmlid = _TYPE_XMLIDS.get(code)
        if not xmlid:
            continue
        type_rec = env.ref(xmlid, raise_if_not_found=False)
        if not type_rec:
            continue
        cr.execute(
            """
            INSERT INTO diamond_ledger_party_type_rel (ledger_id, type_id)
            SELECT %s, %s
             WHERE NOT EXISTS (
                SELECT 1 FROM diamond_ledger_party_type_rel
                 WHERE ledger_id = %s AND type_id = %s
             )
            """,
            (ledger_id, type_rec.id, ledger_id, type_rec.id),
        )
