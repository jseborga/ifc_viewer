import base64
import json
from urllib import error, request as urlrequest
from urllib.parse import urljoin

from werkzeug.exceptions import Forbidden, NotFound

from odoo import http
from odoo.http import request


class BimTilesController(http.Controller):
    def _json_response(self, payload, status=200):
        return request.make_response(
            json.dumps(payload),
            headers=[("Content-Type", "application/json")],
            status=status,
        )

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

    @http.route("/bim/tiles/<int:version_id>/<path:resource_path>", type="http", auth="user")
    def bim_tiles_proxy(self, version_id, resource_path, **kwargs):
        version = request.env["bim.model.version"].browse(version_id).exists()
        if not version:
            raise NotFound()
        version.check_access_rights("read")
        version.check_access_rule("read")
        if version.status != "ready" or not version.tileset_url:
            raise NotFound()

        upstream_url = (
            version.tileset_url
            if resource_path == "tileset.json"
            else urljoin(version.tileset_url, resource_path)
        )
        try:
            with urlrequest.urlopen(upstream_url, timeout=60) as response:
                body = response.read()
                headers = [
                    ("Content-Type", response.headers.get("Content-Type", "application/octet-stream")),
                    ("Content-Length", str(len(body))),
                    ("Cache-Control", "public, max-age=300"),
                ]
                return request.make_response(body, headers=headers)
        except error.HTTPError as exc:
            if exc.code == 404:
                raise NotFound()
            raise
        except error.URLError:
            raise NotFound()

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

    @http.route("/bim/version/<int:version_id>/elements", type="http", auth="user")
    def bim_version_elements(self, version_id, **kwargs):
        version = request.env["bim.model.version"].browse(version_id).exists()
        if not version:
            raise NotFound()
        version.check_access_rights("read")
        version.check_access_rule("read")

        domain = [("version_id", "=", version.id)]
        global_id = (kwargs.get("global_id") or "").strip()
        ifc_class = (kwargs.get("ifc_class") or "").strip()
        level_name = (kwargs.get("level_name") or "").strip()
        if global_id:
            domain.append(("global_id", "ilike", global_id))
        if ifc_class:
            domain.append(("ifc_class", "ilike", ifc_class))
        if level_name:
            domain.append(("level_name", "ilike", level_name))

        limit = min(max(int(kwargs.get("limit", 200)), 1), 1000)
        offset = max(int(kwargs.get("offset", 0)), 0)
        elements = request.env["bim.element"].search(
            domain,
            limit=limit,
            offset=offset,
            order="ifc_class, name, global_id",
        )

        payload = {
            "version_id": version.id,
            "element_count": version.element_count,
            "validation_status": version.validation_status,
            "items": [
                {
                    "id": element.id,
                    "global_id": element.global_id,
                    "source_uid": element.source_uid,
                    "name": element.name,
                    "ifc_class": element.ifc_class,
                    "object_type": element.object_type,
                    "predefined_type": element.predefined_type,
                    "level_name": element.level_name,
                    "system_name": element.system_name,
                    "discipline": element.discipline,
                    "material_names": element.material_names,
                    "is_spatial": element.is_spatial,
                    "property_count": element.property_count,
                }
                for element in elements
            ],
        }
        return self._json_response(payload)

    @http.route("/bim/version/<int:version_id>/elements/<string:global_id>", type="http", auth="user")
    def bim_version_element_detail(self, version_id, global_id, **kwargs):
        version = request.env["bim.model.version"].browse(version_id).exists()
        if not version:
            raise NotFound()
        version.check_access_rights("read")
        version.check_access_rule("read")

        element = request.env["bim.element"].search(
            [("version_id", "=", version.id), ("global_id", "=", global_id)],
            limit=1,
        )
        if not element:
            raise NotFound()

        payload = {
            "id": element.id,
            "version_id": version.id,
            "global_id": element.global_id,
            "source_uid": element.source_uid,
            "name": element.name,
            "ifc_class": element.ifc_class,
            "object_type": element.object_type,
            "predefined_type": element.predefined_type,
            "level_name": element.level_name,
            "system_name": element.system_name,
            "discipline": element.discipline,
            "material_names": element.material_names,
            "is_spatial": element.is_spatial,
            "property_count": element.property_count,
            "properties": json.loads(element.properties_json or "{}"),
        }
        return self._json_response(payload)

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
            return self._json_response({"ok": False, "error": "version_id is required"}, status=400)

        version = request.env["bim.model.version"].sudo().browse(int(version_id)).exists()
        if not version:
            raise NotFound()

        try:
            version._apply_conversion_callback(payload)
        except Exception as exc:
            return self._json_response({"ok": False, "error": str(exc)}, status=400)

        return self._json_response({"ok": True, "version_id": version.id, "status": version.status})
