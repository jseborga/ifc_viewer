import json

from markupsafe import Markup, escape

from odoo import _, api, fields, models


class BimSnapshot(models.Model):
    _name = "bim.snapshot"
    _description = "BIM Snapshot"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True)
    version_id = fields.Many2one(
        "bim.model.version",
        string="Version",
        required=True,
        ondelete="cascade",
    )
    author_id = fields.Many2one(
        "res.users",
        string="Author",
        default=lambda self: self.env.user,
        readonly=True,
    )
    image_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Screenshot Attachment",
        ondelete="set null",
    )
    image_filename = fields.Char(related="image_attachment_id.name", readonly=True)
    screenshot_image = fields.Binary(
        string="Screenshot Preview",
        compute="_compute_screenshot_image",
    )
    screenshot_preview_html = fields.Html(
        string="Snapshot Review Image",
        compute="_compute_screenshot_preview_html",
        sanitize=True,
    )
    camera_json = fields.Text(required=True)
    annotations_json = fields.Text()
    annotation_count = fields.Integer(compute="_compute_annotation_fields")
    annotation_summary = fields.Text(compute="_compute_annotation_fields")
    annotation_preview_html = fields.Html(
        string="Annotation Summary",
        compute="_compute_annotation_fields",
        sanitize=True,
    )
    note = fields.Text()
    review_comment_ids = fields.One2many(
        "bim.comment",
        "snapshot_id",
        string="Review Comments",
    )
    review_comment_count = fields.Integer(compute="_compute_review_comment_count")

    @api.depends("image_attachment_id.datas")
    def _compute_screenshot_image(self):
        for record in self:
            record.screenshot_image = record.image_attachment_id.datas or False

    @api.depends("image_attachment_id")
    def _compute_screenshot_preview_html(self):
        for record in self:
            if record.image_attachment_id:
                record.screenshot_preview_html = Markup(
                    '<div><img src="%s" style="max-width: 100%%; max-height: 900px; border-radius: 12px; border: 1px solid #d8dadd; box-shadow: 0 12px 28px rgba(0,0,0,0.08);"/></div>'
                    % escape(f"/web/image/ir.attachment/{record.image_attachment_id.id}/datas")
                )
            else:
                record.screenshot_preview_html = Markup(
                    "<p>%s</p>" % escape(_("No snapshot image available."))
                )

    @api.depends("annotations_json")
    def _compute_annotation_fields(self):
        type_labels = {
            "marker": _("Marker"),
            "text": _("Text"),
            "rectangle": _("Rectangle"),
            "freehand": _("Freehand"),
        }
        for record in self:
            annotations = record._parse_annotations_payload(record.annotations_json)
            record.annotation_count = len(annotations)
            if not annotations:
                record.annotation_summary = _("No annotations recorded.")
                record.annotation_preview_html = Markup(
                    "<p>%s</p>" % escape(_("No annotations recorded."))
                )
                continue

            summary_lines = []
            summary_items = []
            for index, annotation in enumerate(annotations, start=1):
                kind = type_labels.get(annotation.get("type"), _("Annotation"))
                text = (annotation.get("text") or "").strip() or _("No text")
                summary_lines.append(_("%(index)s. %(kind)s: %(text)s") % {
                    "index": index,
                    "kind": kind,
                    "text": text,
                })
                summary_items.append(
                    "<li><strong>%s</strong>: %s</li>" % (escape(kind), escape(text))
                )
            record.annotation_summary = "\n".join(summary_lines)
            record.annotation_preview_html = Markup("<ul>%s</ul>" % "".join(summary_items))

    @api.depends("review_comment_ids")
    def _compute_review_comment_count(self):
        for record in self:
            record.review_comment_count = len(record.review_comment_ids)

    def _parse_annotations_payload(self, payload):
        self.ensure_one()
        if not payload:
            return []
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
