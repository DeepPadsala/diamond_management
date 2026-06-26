{
    "name": "Diamond Packet Management",
    "version": "18.0.1.10.0",
    "summary": "Diamond packet lifecycle: inward, process / jobwork / factory / HPHT, outward — multi-company, barcode-ready.",
    "description": """
Diamond Packet Management
=========================

A self-contained, multi-company packet management system for diamond
manufacturers and traders. All masters and transactions are custom — only
``res.users`` and ``res.company`` from Odoo are reused (for auth and
multi-company isolation).

Features
--------
* Masters: Shape, Color, Clarity, Cut, Polish, Symmetry, Fluorescence,
  Lab, Charni (sieve), Process, Employee, Account Group, Ledger / Party,
  Party Labour, Worker Labour, Price, Product.
* Packet master with auto-generated barcode + 4Cs + CPS (cut-polish-sym).
* Transactions: Inward / Outward, Process Issue & Receive, Jobwork Issue
  & Receive, Factory Issue & Receive, HPHT Issue & Receive.
* Live Stock dashboard with quick keyboard shortcuts (F1/F2/F5/F6/F7/F8/F10/F12).
* Barcode-gun search wizard for instant packet lookup.
* Per-packet history log (audit trail of every state change).
* Party & worker labour rate cards with auto-calculation on process complete.
* Monthly party invoices and worker salary slips from labour entries.
* Strict per-company data isolation via record rules.
""",
    "author": "Deep Padsala",
    "category": "Industry/Diamond",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/diamond_security.xml",
        "security/ir.model.access.csv",
        "data/diamond_sequences.xml",
        "data/diamond_demo_masters.xml",
        "views/diamond_menus.xml",
        "views/res_company_views.xml",
        "views/master_shape_views.xml",
        "views/master_color_views.xml",
        "views/master_clarity_views.xml",
        "views/master_cut_polish_sym_views.xml",
        "views/master_fluorescence_views.xml",
        "views/master_lab_views.xml",
        "views/master_charni_views.xml",
        "views/master_process_views.xml",
        "views/master_employee_views.xml",
        "views/master_ledger_views.xml",
        "views/master_labour_views.xml",
        "views/labour_billing_views.xml",
        "views/employee_withdrawal_views.xml",
        "views/master_price_views.xml",
        "views/master_product_views.xml",
        "views/packet_views.xml",
        "views/inward_views.xml",
        "views/outward_views.xml",
        "views/process_transaction_views.xml",
        "views/jobwork_views.xml",
        "views/factory_views.xml",
        "views/hpht_views.xml",
        "wizard/barcode_search_views.xml",
        "wizard/packet_issue_wizard_views.xml",
        "wizard/packet_receive_wizard_views.xml",
        "wizard/packet_rollback_wizard_views.xml",
        "views/live_stock_views.xml",
        "views/packet_history_views.xml",
        "wizard/jangad_print_wizard_views.xml",
        "wizard/inward_barcode_print_wizard_views.xml",
        "wizard/monthly_labour_wizard_views.xml",
        "report/jangad_report.xml",
        "report/barcode_label_report.xml",
        "views/barcode_labels_html.xml",
        "views/jangad_slip_html.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "diamond_packet_management/static/src/js/barcode_listener.js",
            "diamond_packet_management/static/src/js/diamond_browser_print.js",
            "diamond_packet_management/static/src/views/live_stock_list/live_stock_list.scss",
            "diamond_packet_management/static/src/views/live_stock_list/live_stock_list_controller.xml",
            "diamond_packet_management/static/src/views/live_stock_list/live_stock_list_controller.js",
            "diamond_packet_management/static/src/views/live_stock_list/live_stock_list_view.js",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
    "post_init_hook": "post_init_hook",
}
