import json

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

    @http.route("/bim/version/<int:version_id>/review_data", type="json", auth="user")
    def bim_version_review_data(self, version_id):
        version = request.env["bim.model.version"].browse(version_id).exists()
        if not version:
            raise NotFound()
        version.check_access_rights("read")
        version.check_access_rule("read")
        open_count = len(version.comment_ids.filtered(lambda comment: comment.status == "open"))
        resolved_count = len(version.comment_ids.filtered(lambda comment: comment.status == "resolved"))
        return {
            "summary": {
                "open_count": open_count,
                "resolved_count": resolved_count,
                "total_count": len(version.comment_ids),
                "project_name": version.bim_model_id.project_id.name or "",
            },
            "snapshots": [
                {
                    "id": snapshot.id,
                    "name": snapshot.name,
                    "note": snapshot.note or "",
                    "image_attachment_id": snapshot.image_attachment_id.id if snapshot.image_attachment_id else False,
                    "image_url": f"/web/image/ir.attachment/{snapshot.image_attachment_id.id}/datas"
                    if snapshot.image_attachment_id
                    else False,
                    "camera_json": snapshot.camera_json or "{}",
                    "annotations_json": snapshot.annotations_json or "[]",
                    "annotation_count": len(json.loads(snapshot.annotations_json or "[]")),
                    "annotation_summary": snapshot.annotation_summary or "",
                    "review_comment_count": snapshot.review_comment_count,
                    "author_name": snapshot.author_id.name,
                    "create_date": str(snapshot.create_date or ""),
                }
                for snapshot in version.snapshot_ids[:20]
            ],
            "comments": [
                {
                    "id": comment.id,
                    "title": comment.title,
                    "status": comment.status,
                    "priority": comment.priority,
                    "comment": comment.comment,
                    "snapshot_id": comment.snapshot_id.id if comment.snapshot_id else False,
                    "snapshot_name": comment.snapshot_id.name if comment.snapshot_id else "",
                    "parent_id": comment.parent_id.id if comment.parent_id else False,
                    "reply_count": comment.reply_count,
                    "element_guid": comment.element_guid or "",
                    "camera_json": comment.camera_json or "{}",
                    "author_name": comment.author_id.name,
                    "create_date": str(comment.create_date or ""),
                }
                for comment in version.comment_ids[:50]
            ],
        }

    @http.route("/bim/version/<int:version_id>/snapshot", type="json", auth="user")
    def bim_version_create_snapshot(
        self,
        version_id,
        image_data_url=None,
        camera=None,
        note=None,
        name=None,
        annotations=None,
    ):
        version = request.env["bim.model.version"].browse(version_id).exists()
        if not version:
            raise NotFound()
        version.check_access_rights("write")
        version.check_access_rule("write")
        snapshot = version._create_snapshot_from_viewer(
            image_data_url=image_data_url,
            camera_payload=camera or {},
            note=note,
            name=name,
            annotations_payload=annotations or [],
        )
        return {
            "ok": True,
            "snapshot_id": snapshot.id,
            "name": snapshot.name,
        }

    @http.route("/bim/version/<int:version_id>/comment", type="json", auth="user")
    def bim_version_create_comment(
        self,
        version_id,
        comment=None,
        camera=None,
        element_guid=None,
        title=None,
        priority="medium",
        snapshot_id=None,
    ):
        version = request.env["bim.model.version"].browse(version_id).exists()
        if not version:
            raise NotFound()
        version.check_access_rights("write")
        version.check_access_rule("write")
        review_comment = version._create_comment_from_viewer(
            comment=comment,
            camera_payload=camera or {},
            element_guid=element_guid,
            title=title,
            priority=priority,
            snapshot_id=snapshot_id,
        )
        return {
            "ok": True,
            "comment_id": review_comment.id,
        }

    @http.route("/bim/comment/<int:comment_id>/status", type="json", auth="user")
    def bim_comment_set_status(self, comment_id, status=None):
        review_comment = request.env["bim.comment"].browse(comment_id).exists()
        if not review_comment:
            raise NotFound()
        review_comment.check_access_rights("write")
        review_comment.check_access_rule("write")
        if status not in {"open", "resolved"}:
            return {"ok": False, "error": "invalid_status"}
        review_comment.write({"status": status})
        return {"ok": True, "comment_id": review_comment.id, "status": review_comment.status}
