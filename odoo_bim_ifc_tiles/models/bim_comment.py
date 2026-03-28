from odoo import fields, models


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
    author_id = fields.Many2one(
        "res.users",
        string="Author",
        default=lambda self: self.env.user,
        readonly=True,
    )
    comment = fields.Text(required=True)
    element_guid = fields.Char(string="Element GlobalId")
    camera_json = fields.Text()
