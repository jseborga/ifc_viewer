{
    "name": "BIM IFC Tiles Viewer",
    "summary": "Versionado IFC y visor 3D base para Odoo 18 Community",
    "version": "18.0.1.0.0",
    "category": "Services/Project",
    "license": "LGPL-3",
    "author": "Codex",
    "depends": ["base", "base_setup", "mail", "project", "web"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_actions.xml",
        "views/res_config_settings_views.xml",
        "views/bim_client_action.xml",
        "views/bim_model_views.xml",
        "views/bim_version_views.xml",
        "views/bim_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "odoo_bim_ifc_tiles/static/src/js/bim_viewer_client_action.js",
            "odoo_bim_ifc_tiles/static/src/xml/bim_viewer_templates.xml",
            "odoo_bim_ifc_tiles/static/src/scss/bim_viewer.scss",
        ],
    },
    "application": True,
    "installable": True,
}
