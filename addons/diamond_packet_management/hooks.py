def post_init_hook(env):
    """Backfill default masters and per-company sequences for all companies."""
    env["diamond.company.defaults"].sudo().create_for_companies(
        env["res.company"].sudo().search([])
    )
