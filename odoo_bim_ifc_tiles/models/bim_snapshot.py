from odoo import fields, models


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
    camera_json = fields.Text(required=True)
    note = fields.Text()
