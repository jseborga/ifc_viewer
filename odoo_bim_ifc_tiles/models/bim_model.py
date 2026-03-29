from odoo import api, fields, models


class BimModel(models.Model):
    _name = "bim.model"
    _description = "BIM Model"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        tracking=True,
        ondelete="set null",
    )
    task_id = fields.Many2one(
        "project.task",
        string="Task",
        tracking=True,
        ondelete="set null",
    )
    discipline = fields.Selection(
        selection=[
            ("architecture", "Architecture"),
            ("structure", "Structure"),
            ("mep", "MEP"),
            ("civil", "Civil"),
            ("other", "Other"),
        ],
        default="architecture",
        required=True,
        tracking=True,
    )
    description = fields.Text()
    version_ids = fields.One2many(
        "bim.model.version",
        "bim_model_id",
        string="Versions",
    )
    active_version_id = fields.Many2one(
        "bim.model.version",
        string="Active Version",
        domain="[('bim_model_id', '=', id)]",
        tracking=True,
        ondelete="set null",
    )
    version_count = fields.Integer(compute="_compute_version_count")
    latest_status = fields.Selection(
        related="active_version_id.status",
        string="Active Status",
        readonly=True,
    )
    active_validation_status = fields.Selection(
        related="active_version_id.validation_status",
        string="Validation Status",
        readonly=True,
    )
    active_element_count = fields.Integer(
        related="active_version_id.element_count",
        string="Element Count",
        readonly=True,
    )
    active_version_can_open_viewer = fields.Boolean(
        compute="_compute_active_version_can_open_viewer"
    )

    @api.depends("version_ids")
    def _compute_version_count(self):
        for record in self:
            record.version_count = len(record.version_ids)

    @api.depends("active_version_id", "active_version_id.status", "active_version_id.tileset_url")
    def _compute_active_version_can_open_viewer(self):
        for record in self:
            record.active_version_can_open_viewer = bool(
                record.active_version_id
                and record.active_version_id.status == "ready"
                and record.active_version_id.tileset_url
            )

    def action_view_versions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Versions",
            "res_model": "bim.model.version",
            "view_mode": "list,form",
            "domain": [("bim_model_id", "=", self.id)],
            "context": {"default_bim_model_id": self.id},
        }

    def action_open_active_viewer(self):
        self.ensure_one()
        if not self.active_version_id:
            return False
        return self.active_version_id.action_open_viewer()
