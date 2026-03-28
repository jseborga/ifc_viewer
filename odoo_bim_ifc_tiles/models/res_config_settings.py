from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    _CESIUM_JS_DEFAULT = (
        "https://cesium.com/downloads/cesiumjs/releases/1.139.1/Build/Cesium/Cesium.js"
    )
    _CESIUM_CSS_DEFAULT = (
        "https://cesium.com/downloads/cesiumjs/releases/1.139.1/Build/Cesium/Widgets/widgets.css"
    )

    bim_converter_endpoint = fields.Char(
        string="Converter Endpoint",
        config_parameter="odoo_bim_ifc_tiles.converter_endpoint",
    )
    bim_converter_shared_token = fields.Char(
        string="Shared Token",
        config_parameter="odoo_bim_ifc_tiles.converter_shared_token",
    )
    bim_converter_timeout = fields.Integer(
        string="Request Timeout",
        default=30,
        config_parameter="odoo_bim_ifc_tiles.converter_timeout",
    )
    bim_converter_verify_ssl = fields.Boolean(
        string="Verify SSL",
        default=True,
        config_parameter="odoo_bim_ifc_tiles.converter_verify_ssl",
    )
    bim_callback_base_url = fields.Char(
        string="Public Base URL",
        config_parameter="odoo_bim_ifc_tiles.callback_base_url",
        help="Optional override for the public Odoo URL used in download and callback links.",
    )
    bim_cesium_js_url = fields.Char(
        string="Cesium JS URL",
        config_parameter="odoo_bim_ifc_tiles.cesium_js_url",
        default=_CESIUM_JS_DEFAULT,
    )
    bim_cesium_css_url = fields.Char(
        string="Cesium CSS URL",
        config_parameter="odoo_bim_ifc_tiles.cesium_css_url",
        default=_CESIUM_CSS_DEFAULT,
    )
