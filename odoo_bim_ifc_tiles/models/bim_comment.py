from markupsafe import Markup, escape

from odoo import _, api, fields, models


class BimComment(models.Model):
    _name = "bim.comment"
    _description = "BIM Comment"
    _order = "create_date desc, id desc"

    version_id = fields.Many2one(
        "bim.model.version",
        string="Version",
        required=True,
        ondelete="cascade",
    )
    snapshot_id = fields.Many2one(
        "bim.snapshot",
        string="Snapshot",
        ondelete="set null",
        tracking=True,
    )
    parent_id = fields.Many2one(
        "bim.comment",
        string="Reply To",
        ondelete="cascade",
    )
    child_ids = fields.One2many(
        "bim.comment",
        "parent_id",
        string="Replies",
    )
    author_id = fields.Many2one(
        "res.users",
        string="Author",
        default=lambda self: self.env.user,
        readonly=True,
    )
    image_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Clarification Image",
        ondelete="set null",
    )
    image_upload = fields.Binary(
        string="Upload Clarification Image",
        attachment=False,
        copy=False,
    )
    image_upload_filename = fields.Char(copy=False)
    image_filename = fields.Char(related="image_attachment_id.name", readonly=True)
    review_image = fields.Binary(
        string="Image Preview",
        compute="_compute_review_image",
    )
    image_preview_html = fields.Html(
        string="Image Preview",
        compute="_compute_image_preview_html",
        sanitize=True,
    )
    title = fields.Char(required=True, default="Review Note")
    status = fields.Selection(
        selection=[
            ("open", "Open"),
            ("resolved", "Resolved"),
        ],
        default="open",
        required=True,
        tracking=True,
    )
    priority = fields.Selection(
        selection=[
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
        ],
        default="medium",
        required=True,
    )
    comment = fields.Text(required=True)
    element_guid = fields.Char(string="Element GlobalId")
    camera_json = fields.Text()
    project_id = fields.Many2one(
        "project.project",
        related="version_id.bim_model_id.project_id",
        store=True,
        readonly=True,
    )
    task_id = fields.Many2one(
        "project.task",
        related="version_id.bim_model_id.task_id",
        store=True,
        readonly=True,
    )
    reply_count = fields.Integer(compute="_compute_reply_count")

    @api.depends("image_attachment_id.datas")
    def _compute_review_image(self):
        for record in self:
            record.review_image = record.image_attachment_id.datas or False

    @api.depends("image_attachment_id")
    def _compute_image_preview_html(self):
        for record in self:
            if record.image_attachment_id:
                record.image_preview_html = Markup(
                    '<div><img src="%s" style="max-width: 100%%; max-height: 720px; border-radius: 10px; border: 1px solid #d8dadd;"/></div>'
                    % escape(f"/web/image/ir.attachment/{record.image_attachment_id.id}/datas")
                )
            else:
                record.image_preview_html = Markup(
                    "<p>%s</p>" % escape(_("No clarification image attached."))
                )

    @api.depends("child_ids")
    def _compute_reply_count(self):
        for record in self:
            record.reply_count = len(record.child_ids)

    @api.onchange("snapshot_id")
    def _onchange_snapshot_id(self):
        for record in self:
            if record.snapshot_id:
                record.version_id = record.snapshot_id.version_id

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        for vals in vals_list:
            vals = dict(vals)
            snapshot_id = vals.get("snapshot_id")
            if snapshot_id and not vals.get("version_id"):
                snapshot = self.env["bim.snapshot"].browse(snapshot_id).exists()
                if snapshot:
                    vals["version_id"] = snapshot.version_id.id
            prepared_vals_list.append(vals)

        records = super().create(prepared_vals_list)
        for record, vals in zip(records, prepared_vals_list):
            if vals.get("image_upload"):
                record._sync_uploaded_image_to_attachment()
        return records

    def write(self, vals):
        if vals.get("snapshot_id") and not vals.get("version_id"):
            snapshot = self.env["bim.snapshot"].browse(vals["snapshot_id"]).exists()
            if snapshot:
                vals = dict(vals, version_id=snapshot.version_id.id)
        result = super().write(vals)
        if not self.env.context.get("skip_review_image_sync") and (
            "image_upload" in vals or "image_upload_filename" in vals
        ):
            for record in self:
                if record.image_upload:
                    record._sync_uploaded_image_to_attachment()
        return result

    def _sync_uploaded_image_to_attachment(self):
        self.ensure_one()
        if not self.image_upload:
            return

        attachment_name = (
            self.image_upload_filename
            or self.image_filename
            or f"review_comment_{self.id}.png"
        )
        attachment_vals = {
            "name": attachment_name,
            "datas": self.image_upload,
            "res_model": self._name,
            "res_id": self.id,
            "type": "binary",
            "mimetype": "image/png",
        }

        if self.image_attachment_id:
            attachment = self.image_attachment_id.sudo()
            attachment.write(attachment_vals)
        else:
            attachment = self.env["ir.attachment"].sudo().create(attachment_vals)

        self.with_context(skip_review_image_sync=True).write(
            {
                "image_attachment_id": attachment.id,
                "image_upload": False,
            }
        )
