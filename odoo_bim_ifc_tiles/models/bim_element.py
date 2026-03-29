from odoo import fields, models


class BimElement(models.Model):
    _name = "bim.element"
    _description = "BIM Element Metadata"
    _order = "version_id desc, ifc_class, name, global_id"

    version_id = fields.Many2one(
        "bim.model.version",
        string="Version",
        required=True,
        ondelete="cascade",
        index=True,
    )
    bim_model_id = fields.Many2one(
        "bim.model",
        string="BIM Model",
        related="version_id.bim_model_id",
        store=True,
        readonly=True,
        index=True,
    )
    global_id = fields.Char(string="IFC GlobalId", required=True, index=True)
    source_uid = fields.Char(string="Source UID", index=True)
    name = fields.Char(index=True)
    ifc_class = fields.Char(string="IFC Class", index=True)
    object_type = fields.Char()
    predefined_type = fields.Char()
    level_name = fields.Char(index=True)
    system_name = fields.Char(index=True)
    discipline = fields.Char(index=True)
    material_names = fields.Char()
    is_spatial = fields.Boolean()
    property_count = fields.Integer(readonly=True)
    properties_json = fields.Text(string="Properties JSON")

    _sql_constraints = [
        (
            "bim_element_version_global_id_uniq",
            "unique(version_id, global_id)",
            "The IFC GlobalId must be unique within the same BIM version.",
        )
    ]
