def migrate(cr, version):
    cr.execute("""
        ALTER TABLE diamond_salary_slip
        DROP CONSTRAINT IF EXISTS employee_period_uniq
    """)
    cr.execute("""
        ALTER TABLE diamond_party_invoice
        DROP CONSTRAINT IF EXISTS party_period_uniq
    """)
