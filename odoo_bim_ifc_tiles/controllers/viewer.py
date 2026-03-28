import base64
import json

from werkzeug.exceptions import Forbidden, NotFound

from odoo import http
from odoo.http import request


class BimTilesController(http.Controller):
    def _get_request_token(self):
        auth_header = request.httprequest.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header.split(" ", 1)[1].strip()
        return (
            request.httprequest.headers.get("X-BIM-Token")
            or request.params.get("access_token")
            or ""
        ).strip()

    def _has_valid_shared_token(self):
        expected = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("odoo_bim_ifc_tiles.converter_shared_token", "")
            .strip()
        )
        provided = self._get_request_token()
        return bool(expected) and expected == provided

    @http.route("/bim/tiles/<int:version_id>/tileset.json", type="http", auth="user")
    def bim_tileset_redirect(self, version_id, **kwargs):
        version = request.env["bim.model.version"].browse(version_id).exists()
        if not version:
            raise NotFound()
        version.check_access_rights("read")
        version.check_access_rule("read")
        if version.status != "ready" or not version.tileset_url:
            raise NotFound()
        return request.redirect(version.tileset_url, code=302)

    @http.route("/bim/version/<int:version_id>/ifc", type="http", auth="public")
    def bim_ifc_download(self, version_id, **kwargs):
        if self._has_valid_shared_token():
            version = request.env["bim.model.version"].sudo().browse(version_id).exists()
        else:
            version = request.env["bim.model.version"].browse(version_id).exists()
            if not version:
                raise NotFound()
            version.check_access_rights("read")
            version.check_access_rule("read")
        if not version:
            raise NotFound()

        attachment = version.ifc_attachment_id.sudo()
        if not attachment or not attachment.datas:
            raise NotFound()

        binary = base64.b64decode(attachment.datas)
        headers = [
            ("Content-Type", attachment.mimetype or "application/octet-stream"),
            ("Content-Length", str(len(binary))),
            (
                "Content-Disposition",
                f'attachment; filename="{attachment.name or "model.ifc"}"',
            ),
        ]
        return request.make_response(binary, headers=headers)

    @http.route(
        "/bim/conversion/callback",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def bim_conversion_callback(self, **kwargs):
        if not self._has_valid_shared_token():
            raise Forbidden()

        payload = request.httprequest.get_json(silent=True) or {}
        version_id = payload.get("version_id")
        if not version_id:
            return request.make_response(
                json.dumps({"ok": False, "error": "version_id is required"}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )

        version = request.env["bim.model.version"].sudo().browse(int(version_id)).exists()
        if not version:
            raise NotFound()

        try:
            version._apply_conversion_callback(payload)
        except Exception as exc:
            return request.make_response(
                json.dumps({"ok": False, "error": str(exc)}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )

        return request.make_response(
            json.dumps({"ok": True, "version_id": version.id, "status": version.status}),
            headers=[("Content-Type", "application/json")],
            status=200,
        )
