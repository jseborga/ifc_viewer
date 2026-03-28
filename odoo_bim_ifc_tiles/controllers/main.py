from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request


class BimViewerPayloadController(http.Controller):
    @http.route("/bim/version/<int:version_id>/payload", type="json", auth="user")
    def bim_version_payload(self, version_id):
        version = request.env["bim.model.version"].browse(version_id).exists()
        if not version:
            raise NotFound()
        version.check_access_rights("read")
        version.check_access_rule("read")
        return version._prepare_viewer_payload()
