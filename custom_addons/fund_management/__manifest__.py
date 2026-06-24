# module metadata loaded by odoo during installation
{
    'name': 'Fund Management',

    # module version used during upgrades
    'version': '18.0.1.0.5',

    # module category shown in apps
    'category': 'Accounting',

    # short description shown in apps
    'summary': 'Manage fund allocations, requisitions, transfers, and approvals',

    # required modules
    'depends': [
        'base',
    ],

    # files loaded during installation
    'data': [
        'security/fund_management_groups.xml',
        'security/ir.model.access.csv',
        'security/fund_management_record_rules.xml',
        'data/fund_sequence_data.xml',
        'views/fund_account_views.xml',
        'views/fund_bucket_views.xml',
        'views/fund_allocation_request_views.xml',
        'views/fund_requisition_views.xml',
        'views/fund_transfer_request_views.xml',
        'views/fund_incoming_views.xml',
        'views/fund_bill_views.xml',
        'views/fund_ledger_views.xml',
        'views/fund_approval_history_views.xml',
        'views/fund_audit_history_views.xml',
        'views/fund_menus.xml',
    ],

    # module can be installed
    'installable': True,

    # show as main application
    'application': True,
}
