import json
import logging
import ssl
from urllib import error, request as urlrequest

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_LOGGER = logging.getLogger(__name__)


class BimModelVersion(models.Model):
    _name = "bim.model.version"
    _description = "BIM Model Version"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "uploaded_on desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    bim_model_id = fields.Many2one(
        "bim.model",
        string="BIM Model",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    ifc_attachment_id = fields.Many2one(
        "ir.attachment",
        string="IFC Attachment",
        ondelete="restrict",
        tracking=True,
    )
    ifc_upload = fields.Binary(
        string="Upload IFC",
        attachment=False,
        copy=False,
    )
    ifc_upload_filename = fields.Char(
        string="Upload Filename",
        copy=False,
    )
    source_filename = fields.Char(string="Source Filename", tracking=True)
    ifc_schema = fields.Char(string="IFC Schema", tracking=True)
    status = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("queued", "Queued"),
            ("processing", "Processing"),
            ("ready", "Ready"),
            ("error", "Error"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    uploaded_by = fields.Many2one(
        "res.users",
        string="Uploaded By",
        default=lambda self: self.env.user,
        readonly=True,
    )
    uploaded_on = fields.Datetime(
        string="Uploaded On",
        default=fields.Datetime.now,
        readonly=True,
    )
    tileset_url = fields.Char(string="Tileset URL", tracking=True)
    metadata_json = fields.Text(string="Metadata JSON")
    conversion_log = fields.Text()
    error_message = fields.Text()
    conversion_job_ref = fields.Char(string="Conversion Job Ref", tracking=True)
    conversion_requested_on = fields.Datetime(readonly=True)
    conversion_finished_on = fields.Datetime(readonly=True)
    georef_lon = fields.Float(string="Longitude", digits=(16, 6))
    georef_lat = fields.Float(string="Latitude", digits=(16, 6))
    georef_height = fields.Float(string="Height")
    heading = fields.Float()
    pitch = fields.Float()
    roll = fields.Float()
    snapshot_ids = fields.One2many(
        "bim.snapshot",
        "version_id",
        string="Snapshots",
    )
    comment_ids = fields.One2many(
        "bim.comment",
        "version_id",
        string="Comments",
    )
    can_open_viewer = fields.Boolean(compute="_compute_can_open_viewer")

    @api.depends("bim_model_id.name", "source_filename", "uploaded_on")
    def _compute_name(self):
        for record in self:
            filename = record.source_filename or _("New Version")
            model_name = record.bim_model_id.name or _("No Model")
            record.name = f"{model_name} - {filename}"

    @api.depends("status", "tileset_url")
    def _compute_can_open_viewer(self):
        for record in self:
            record.can_open_viewer = record.status == "ready" and bool(record.tileset_url)

    @api.onchange("ifc_attachment_id")
    def _onchange_ifc_attachment_id(self):
        for record in self:
            if record.ifc_attachment_id and not record.source_filename:
                record.source_filename = record.ifc_attachment_id.name

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record, vals in zip(records, vals_list):
            if vals.get("ifc_upload"):
                record._sync_uploaded_ifc_to_attachment()
            if record.ifc_attachment_id and not record.source_filename:
                record.source_filename = record.ifc_attachment_id.name
            if record.bim_model_id and not record.bim_model_id.active_version_id:
                record.bim_model_id.active_version_id = record.id
        return records

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get("skip_ifc_sync") and (
            "ifc_upload" in vals or "ifc_upload_filename" in vals
        ):
            for record in self:
                if record.ifc_upload:
                    record._sync_uploaded_ifc_to_attachment()
        return result

    def action_queue_conversion(self):
        for record in self:
            if not record.ifc_attachment_id:
                raise UserError(_("Attach an IFC file before queueing the conversion."))
            record._submit_to_converter()

    def action_set_active(self):
        self.ensure_one()
        self.bim_model_id.active_version_id = self.id

    def action_open_viewer(self):
        self.ensure_one()
        if not self.can_open_viewer:
            raise UserError(
                _("The viewer is available only when the version is ready and has a tileset URL.")
            )
        return {
            "type": "ir.actions.client",
            "name": _("IFC Viewer"),
            "tag": "odoo_bim_ifc_tiles.BimViewerAction",
            "target": "main",
            "params": {"version_id": self.id},
        }

    def _prepare_viewer_payload(self):
        self.ensure_one()
        config = self.env["ir.config_parameter"].sudo()
        return {
            "version_id": self.id,
            "name": self.name,
            "model_name": self.bim_model_id.name,
            "source_filename": self.source_filename,
            "status": self.status,
            "tileset_url": f"/bim/tiles/{self.id}/tileset.json" if self.tileset_url else False,
            "raw_tileset_url": self.tileset_url,
            "longitude": self.georef_lon,
            "latitude": self.georef_lat,
            "height": self.georef_height,
            "heading": self.heading,
            "pitch": self.pitch,
            "roll": self.roll,
            "cesium_js_url": config.get_param("odoo_bim_ifc_tiles.cesium_js_url")
            or "https://cesium.com/downloads/cesiumjs/releases/1.139.1/Build/Cesium/Cesium.js",
            "cesium_css_url": config.get_param("odoo_bim_ifc_tiles.cesium_css_url")
            or "https://cesium.com/downloads/cesiumjs/releases/1.139.1/Build/Cesium/Widgets/widgets.css",
            "metadata_hint": _(
                "Store BIM metadata separately from the tileset and link it by IFC GlobalId."
            ),
        }

    def _sync_uploaded_ifc_to_attachment(self):
        self.ensure_one()
        if not self.ifc_upload:
            return

        attachment_name = (
            self.ifc_upload_filename
            or self.source_filename
            or f"bim_version_{self.id}.ifc"
        )
        attachment_vals = {
            "name": attachment_name,
            "datas": self.ifc_upload,
            "res_model": self._name,
            "res_id": self.id,
            "type": "binary",
            "mimetype": "application/octet-stream",
        }

        if self.ifc_attachment_id:
            attachment = self.ifc_attachment_id.sudo()
            attachment.write(attachment_vals)
        else:
            attachment = self.env["ir.attachment"].sudo().create(attachment_vals)

        self.with_context(skip_ifc_sync=True).write(
            {
                "ifc_attachment_id": attachment.id,
                "source_filename": attachment_name,
                "ifc_upload": False,
            }
        )

    def _submit_to_converter(self):
        self.ensure_one()
        config = self.env["ir.config_parameter"].sudo()
        endpoint = (config.get_param("odoo_bim_ifc_tiles.converter_endpoint") or "").strip()
        token = (config.get_param("odoo_bim_ifc_tiles.converter_shared_token") or "").strip()
        timeout = int(config.get_param("odoo_bim_ifc_tiles.converter_timeout") or 30)
        verify_ssl = config.get_param("odoo_bim_ifc_tiles.converter_verify_ssl", "True") == "True"

        if not endpoint:
            raise UserError(_("Configure the converter endpoint in Settings before queueing jobs."))
        if not token:
            raise UserError(_("Configure the shared token in Settings before queueing jobs."))

        payload = self._prepare_converter_payload(token)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "X-BIM-Token": token,
        }
        self.write(
            {
                "status": "queued",
                "error_message": False,
                "conversion_requested_on": fields.Datetime.now(),
                "conversion_log": _("Queued and submitted to the converter endpoint."),
            }
        )

        try:
            response_payload = self._perform_json_post(
                endpoint, payload, headers=headers, timeout=timeout, verify_ssl=verify_ssl
            )
        except UserError as exc:
            self.write(
                {
                    "status": "error",
                    "error_message": str(exc),
                    "conversion_log": str(exc),
                }
            )
            self.message_post(body=_("Converter submission failed: %s") % str(exc))
            raise

        update_vals = {
            "status": response_payload.get("status") or "processing",
            "conversion_log": self._stringify_payload(response_payload),
        }
        if response_payload.get("job_id"):
            update_vals["conversion_job_ref"] = str(response_payload["job_id"])
        if update_vals["status"] == "ready":
            update_vals["conversion_finished_on"] = fields.Datetime.now()
        if response_payload.get("tileset_url"):
            update_vals["tileset_url"] = response_payload["tileset_url"]
        if response_payload.get("error_message"):
            update_vals["error_message"] = response_payload["error_message"]
        self.write(update_vals)
        self.message_post(
            body=_("Converter accepted the job%s.")
            % (f" ({response_payload['job_id']})" if response_payload.get("job_id") else "")
        )

    def _prepare_converter_payload(self, token):
        self.ensure_one()
        base_url = self._get_public_base_url()
        if not base_url:
            raise UserError(
                _("Set a valid Public Base URL or web.base.url before submitting conversions.")
            )
        return {
            "version_id": self.id,
            "model_name": self.bim_model_id.name,
            "source_filename": self.source_filename,
            "ifc_download_url": f"{base_url}/bim/version/{self.id}/ifc",
            "callback_url": f"{base_url}/bim/conversion/callback",
            "access_token": token,
            "longitude": self.georef_lon,
            "latitude": self.georef_lat,
            "height": self.georef_height,
            "heading": self.heading,
            "pitch": self.pitch,
            "roll": self.roll,
        }

    def _get_public_base_url(self):
        config = self.env["ir.config_parameter"].sudo()
        return (
            config.get_param("odoo_bim_ifc_tiles.callback_base_url")
            or config.get_param("web.base.url")
            or ""
        ).rstrip("/")

    def _apply_conversion_callback(self, payload):
        self.ensure_one()
        status = (payload.get("status") or "").strip()
        allowed = {"queued", "processing", "ready", "error"}
        if status not in allowed:
            raise UserError(_("Invalid callback status: %s") % status)

        vals = {
            "status": status,
            "conversion_log": payload.get("conversion_log") or self.conversion_log,
            "error_message": payload.get("error_message") or False,
        }
        if payload.get("tileset_url"):
            vals["tileset_url"] = payload["tileset_url"]
        if payload.get("job_id"):
            vals["conversion_job_ref"] = str(payload["job_id"])
        if status in {"ready", "error"}:
            vals["conversion_finished_on"] = fields.Datetime.now()
        self.write(vals)
        self.message_post(body=_("Converter callback received. New status: %s") % status)

    def _perform_json_post(self, endpoint, payload, headers, timeout, verify_ssl):
        body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(endpoint, data=body, headers=headers, method="POST")
        context = None
        if not verify_ssl:
            context = ssl._create_unverified_context()
        try:
            with urlrequest.urlopen(req, timeout=timeout, context=context) as response:
                raw_body = response.read().decode("utf-8") or "{}"
        except error.HTTPError as exc:
            raw_body = exc.read().decode("utf-8", errors="replace")
            raise UserError(
                _("Converter HTTP error %(code)s: %(body)s")
                % {"code": exc.code, "body": raw_body}
            ) from exc
        except error.URLError as exc:
            raise UserError(_("Converter connection error: %s") % exc.reason) from exc
        except Exception as exc:
            _LOGGER.exception("Unexpected converter submission error")
            raise UserError(_("Unexpected converter error: %s") % str(exc)) from exc

        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise UserError(_("Converter did not return valid JSON: %s") % raw_body) from exc

    def _stringify_payload(self, payload):
        return json.dumps(payload, indent=2, sort_keys=True)
