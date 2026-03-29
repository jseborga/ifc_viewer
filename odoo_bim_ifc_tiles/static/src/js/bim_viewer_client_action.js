/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";

const CAPTURE_COLORS = ["#d13030", "#ff8f00", "#167f39", "#1463b8", "#7f2db8", "#101820"];

function safeJsonParse(value, fallback = {}) {
    if (!value) {
        return fallback;
    }
    try {
        return JSON.parse(value);
    } catch {
        return fallback;
    }
}

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function clamp01(value) {
    return clamp(value, 0, 1);
}

function pointsToText(points) {
    return (points || [])
        .map((point) => `${Math.round(point.x * 1000)},${Math.round(point.y * 1000)}`)
        .join(" ");
}

function loadImage(dataUrl) {
    return new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = () => reject(new Error("No se pudo cargar la imagen de la captura."));
        image.src = dataUrl;
    });
}

class BimViewerClientAction extends Component {
    static template = "odoo_bim_ifc_tiles.BimViewerAction";

    setup() {
        this.viewerRef = useRef("viewer");
        this.cesiumViewer = null;
        this.tileset = null;
        this.screenSpaceHandler = null;
        this.clippingPlane = null;
        this.clippingPlaneMatrix = null;
        this.capturePointerState = {
            active: false,
            moved: false,
            start: null,
            points: [],
        };
        this.captureSuppressClick = false;
        this.state = useState({
            loading: true,
            error: null,
            reviewBusy: false,
            viewerStatus: "idle",
            versionId: this.props.action?.params?.version_id || null,
            versionName: "",
            modelName: "",
            sourceFilename: "",
            status: "",
            validationStatus: "",
            elementCount: 0,
            tilesetUrl: "",
            rawTilesetUrl: "",
            cesiumJsUrl: "",
            cesiumCssUrl: "",
            metadataHint: "",
            selectedElementGuid: "",
            selectedElementLabel: "",
            commentTitle: "Revision BIM",
            commentElementGuid: "",
            commentText: "",
            commentPriority: "medium",
            commentSnapshotId: null,
            snapshotNote: "",
            qualityPreset: "standard",
            clipEnabled: false,
            clipAxis: "z",
            clipDistance: 0,
            clipRange: 100,
            reviewSummary: {
                openCount: 0,
                resolvedCount: 0,
                totalCount: 0,
                projectName: "",
            },
            snapshots: [],
            comments: [],
            selectedSnapshotId: null,
            captureDraftImage: "",
            captureDraftCamera: null,
            captureAnnotations: [],
            captureDraftShape: null,
            captureTool: "marker",
            captureColor: CAPTURE_COLORS[0],
            captureStrokeWidth: 3,
            activeAnnotationId: null,
            activeAnnotationText: "",
            activeAnnotationType: "",
        });

        onWillStart(async () => {
            if (!this.state.versionId) {
                this.state.error = "No se recibio version_id para abrir el visor.";
                this.state.loading = false;
                return;
            }
            await this._loadViewerPayload();
            await this._loadReviewData();
        });

        onMounted(() => this._mountViewer());
        onWillUnmount(() => this._destroyViewer());
    }

    async _loadViewerPayload() {
        try {
            const payload = await rpc(`/bim/version/${this.state.versionId}/payload`, {});
            this.state.versionName = payload.name || "";
            this.state.modelName = payload.model_name || "";
            this.state.sourceFilename = payload.source_filename || "";
            this.state.status = payload.status || "";
            this.state.validationStatus = payload.validation_status || "";
            this.state.elementCount = payload.element_count || 0;
            this.state.tilesetUrl = payload.tileset_url || "";
            this.state.rawTilesetUrl = payload.raw_tileset_url || "";
            this.state.cesiumJsUrl = payload.cesium_js_url || "";
            this.state.cesiumCssUrl = payload.cesium_css_url || "";
            this.state.metadataHint = payload.metadata_hint || "";
        } catch (error) {
            this.state.error = error.message || "No se pudo cargar el payload del visor.";
            this.state.loading = false;
        }
    }

    async _loadReviewData() {
        try {
            const reviewData = await rpc(`/bim/version/${this.state.versionId}/review_data`, {});
            const snapshots = (reviewData.snapshots || []).map((snapshot) => ({
                ...snapshot,
                annotations: safeJsonParse(snapshot.annotations_json, []),
                annotation_count:
                    Number(snapshot.annotation_count || 0) ||
                    safeJsonParse(snapshot.annotations_json, []).length,
            }));
            this.state.reviewSummary = {
                openCount: reviewData.summary?.open_count || 0,
                resolvedCount: reviewData.summary?.resolved_count || 0,
                totalCount: reviewData.summary?.total_count || 0,
                projectName: reviewData.summary?.project_name || "",
            };
            this.state.snapshots = snapshots;
            this.state.comments = reviewData.comments || [];
            if (
                this.state.selectedSnapshotId &&
                !snapshots.some((snapshot) => snapshot.id === this.state.selectedSnapshotId)
            ) {
                this.state.selectedSnapshotId = null;
            }
        } catch (error) {
            this.state.error = error.message || "No se pudieron cargar los datos de revision.";
        }
    }

    async _mountViewer() {
        if (this.state.error) {
            return;
        }
        if (!this.state.tilesetUrl) {
            this.state.viewerStatus = "missing_tileset";
            this.state.loading = false;
            return;
        }
        if (!window.Cesium) {
            try {
                await this._ensureCesiumLoaded();
            } catch (error) {
                this.state.error = error.message || "No se pudo cargar CesiumJS.";
                this.state.viewerStatus = "missing_cesium";
                this.state.loading = false;
                return;
            }
        }
        if (!this.viewerRef.el) {
            this.state.viewerStatus = "missing_container";
            this.state.loading = false;
            return;
        }

        try {
            const Cesium = window.Cesium;
            this.cesiumViewer = new Cesium.Viewer(this.viewerRef.el, {
                animation: false,
                baseLayerPicker: false,
                contextOptions: {
                    webgl: {
                        alpha: false,
                        preserveDrawingBuffer: true,
                    },
                },
                fullscreenButton: false,
                geocoder: false,
                homeButton: false,
                infoBox: false,
                navigationHelpButton: false,
                sceneModePicker: false,
                timeline: false,
                shouldAnimate: false,
                requestRenderMode: true,
            });
            this.cesiumViewer.scene.postProcessStages.fxaa.enabled = true;
            this.cesiumViewer.scene.highDynamicRange = true;
            this.cesiumViewer.scene.msaaSamples = 4;
            this.cesiumViewer.scene.backgroundColor =
                Cesium.Color.fromCssColorString("#0f1720");
            this.cesiumViewer.scene.skyAtmosphere.show = false;
            if (this.cesiumViewer.scene.skyBox) {
                this.cesiumViewer.scene.skyBox.show = false;
            }
            if (this.cesiumViewer.scene.sun) {
                this.cesiumViewer.scene.sun.show = false;
            }
            if (this.cesiumViewer.scene.moon) {
                this.cesiumViewer.scene.moon.show = false;
            }
            if (this.cesiumViewer.imageryLayers) {
                while (this.cesiumViewer.imageryLayers.length) {
                    this.cesiumViewer.imageryLayers.remove(
                        this.cesiumViewer.imageryLayers.get(0),
                        true
                    );
                }
            }
            this.cesiumViewer.scene.globe.show = false;

            this.tileset = await Cesium.Cesium3DTileset.fromUrl(this.state.tilesetUrl);
            this.cesiumViewer.scene.primitives.add(this.tileset);
            this._setupClippingPlane(Cesium);
            this._setupFeaturePicking(Cesium);
            this._applyQualityPreset();
            await this.cesiumViewer.zoomTo(this.tileset);
            this._requestRender();
            this.state.viewerStatus = "ready";
        } catch (error) {
            this.state.error = error.message || "Cesium no pudo abrir el tileset.";
            this.state.viewerStatus = "error";
        } finally {
            this.state.loading = false;
        }
    }

    _setupClippingPlane(Cesium) {
        if (!this.tileset) {
            return;
        }
        this.state.clipRange = Math.max(20, Math.ceil(this.tileset.boundingSphere.radius || 100));
        this.state.clipDistance = 0;
        this.clippingPlane = new Cesium.ClippingPlane(this._getClipNormal(Cesium), 0.0);
        this.clippingPlaneMatrix = Cesium.Transforms.eastNorthUpToFixedFrame(
            this.tileset.boundingSphere.center
        );
        this.tileset.clippingPlanes = new Cesium.ClippingPlaneCollection({
            planes: [this.clippingPlane],
            enabled: false,
            edgeColor: Cesium.Color.fromCssColorString("#ff8f00"),
            edgeWidth: 2.0,
            modelMatrix: this.clippingPlaneMatrix,
        });
        this._updateClippingPlane();
    }

    _getClipNormal(Cesium) {
        if (this.state.clipAxis === "x") {
            return new Cesium.Cartesian3(1.0, 0.0, 0.0);
        }
        if (this.state.clipAxis === "y") {
            return new Cesium.Cartesian3(0.0, 0.0, 1.0);
        }
        return new Cesium.Cartesian3(0.0, -1.0, 0.0);
    }

    _setupFeaturePicking(Cesium) {
        if (!this.cesiumViewer) {
            return;
        }
        this.screenSpaceHandler = new Cesium.ScreenSpaceEventHandler(this.cesiumViewer.scene.canvas);
        this.screenSpaceHandler.setInputAction((movement) => {
            const picked = this.cesiumViewer.scene.pick(movement.position);
            if (!picked) {
                this.state.selectedElementGuid = "";
                this.state.selectedElementLabel = "";
                return;
            }

            const propertyIds =
                typeof picked.getPropertyIds === "function" ? picked.getPropertyIds() || [] : [];
            const normalizedMap = {};
            for (const propertyId of propertyIds) {
                normalizedMap[String(propertyId).toLowerCase()] = propertyId;
            }
            const guidKey =
                normalizedMap.globalid ||
                normalizedMap.ifcguid ||
                normalizedMap.guid ||
                normalizedMap.id ||
                null;
            const nameKey = normalizedMap.name || normalizedMap.title || null;
            const classKey = normalizedMap.ifcclass || normalizedMap.class || null;

            const guid =
                guidKey && typeof picked.getProperty === "function"
                    ? String(picked.getProperty(guidKey) || "")
                    : "";
            const featureName =
                nameKey && typeof picked.getProperty === "function"
                    ? String(picked.getProperty(nameKey) || "")
                    : "";
            const featureClass =
                classKey && typeof picked.getProperty === "function"
                    ? String(picked.getProperty(classKey) || "")
                    : "";

            this.state.selectedElementGuid = guid;
            this.state.commentElementGuid = guid || this.state.commentElementGuid;
            this.state.selectedElementLabel = [featureClass, featureName].filter(Boolean).join(" - ");
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    }

    async captureSnapshotDraft() {
        if (!this.cesiumViewer || this.state.reviewBusy) {
            return;
        }
        this.state.reviewBusy = true;
        try {
            this.state.captureDraftImage = await this._captureCurrentFrameDataUrl();
            this.state.captureDraftCamera = this._getCurrentCameraPayload();
            this.state.captureAnnotations = [];
            this.state.captureDraftShape = null;
            this.state.captureTool = "marker";
            this.state.activeAnnotationId = null;
            this.state.activeAnnotationText = "";
            this.state.activeAnnotationType = "";
            this.state.snapshotNote = "";
        } catch (error) {
            this.state.error = error.message || "No se pudo capturar la imagen del visor.";
        } finally {
            this.state.reviewBusy = false;
        }
    }

    clearCaptureDraft() {
        this.capturePointerState = {
            active: false,
            moved: false,
            start: null,
            points: [],
        };
        this.captureSuppressClick = false;
        this.state.captureDraftImage = "";
        this.state.captureDraftCamera = null;
        this.state.captureAnnotations = [];
        this.state.captureDraftShape = null;
        this.state.activeAnnotationId = null;
        this.state.activeAnnotationText = "";
        this.state.activeAnnotationType = "";
        this.state.snapshotNote = "";
    }

    setCaptureToolFromDataset(ev) {
        this.state.captureTool = ev.currentTarget.dataset.tool || "marker";
        this.state.captureDraftShape = null;
        this.capturePointerState.active = false;
    }

    setCaptureColorFromDataset(ev) {
        const color = ev.currentTarget.dataset.color || CAPTURE_COLORS[0];
        this._setCaptureColor(color);
    }

    onCaptureColorInput(ev) {
        const color = ev.target.value || CAPTURE_COLORS[0];
        this._setCaptureColor(color);
    }

    _setCaptureColor(color) {
        this.state.captureColor = color;
        if (this.state.activeAnnotationId) {
            this._updateAnnotation(this.state.activeAnnotationId, { color });
        }
    }

    onCaptureStrokeWidthInput(ev) {
        const width = clamp(Number(ev.target.value || 3), 1, 12);
        this.state.captureStrokeWidth = width;
        if (this.state.activeAnnotationId) {
            this._updateAnnotation(this.state.activeAnnotationId, { width });
        }
    }

    onCaptureStageClick(ev) {
        if (!this.state.captureDraftImage) {
            return;
        }
        if (this.captureSuppressClick) {
            this.captureSuppressClick = false;
            return;
        }
        if (this.state.captureTool === "rect" || this.state.captureTool === "freehand") {
            return;
        }
        const position = this._getCapturePointerPosition(ev);
        if (!position) {
            return;
        }
        if (this.state.captureTool === "text") {
            this._appendAnnotation(this._buildTextAnnotation(position));
        } else {
            this._appendAnnotation(this._buildMarkerAnnotation(position));
        }
    }

    onCaptureStagePointerDown(ev) {
        if (!this.state.captureDraftImage || ev.button !== 0) {
            return;
        }
        if (this.state.captureTool !== "rect" && this.state.captureTool !== "freehand") {
            return;
        }
        const position = this._getCapturePointerPosition(ev);
        if (!position) {
            return;
        }
        this.capturePointerState = {
            active: true,
            moved: false,
            start: position,
            points: [position],
        };
        if (this.state.captureTool === "rect") {
            this.state.captureDraftShape = {
                type: "rect",
                x: position.x,
                y: position.y,
                w: 0,
                h: 0,
                color: this.state.captureColor,
                width: this.state.captureStrokeWidth,
            };
        } else {
            this.state.captureDraftShape = {
                type: "freehand",
                points: [position],
                points_text: pointsToText([position]),
                color: this.state.captureColor,
                width: this.state.captureStrokeWidth,
            };
        }
    }

    onCaptureStagePointerMove(ev) {
        if (!this.capturePointerState.active) {
            return;
        }
        const position = this._getCapturePointerPosition(ev);
        if (!position) {
            return;
        }
        this.capturePointerState.moved = true;
        if (this.state.captureTool === "rect") {
            const rect = this._normalizeRect(this.capturePointerState.start, position);
            this.state.captureDraftShape = {
                type: "rect",
                ...rect,
                color: this.state.captureColor,
                width: this.state.captureStrokeWidth,
            };
        } else {
            const lastPoint =
                this.capturePointerState.points[this.capturePointerState.points.length - 1];
            const deltaX = Math.abs(lastPoint.x - position.x);
            const deltaY = Math.abs(lastPoint.y - position.y);
            if (deltaX < 0.002 && deltaY < 0.002) {
                return;
            }
            const points = [...this.capturePointerState.points, position];
            this.capturePointerState.points = points;
            this.state.captureDraftShape = {
                type: "freehand",
                points,
                points_text: pointsToText(points),
                color: this.state.captureColor,
                width: this.state.captureStrokeWidth,
            };
        }
    }

    onCaptureStagePointerUp() {
        if (!this.capturePointerState.active) {
            return;
        }
        const draftShape = this.state.captureDraftShape;
        if (draftShape && this.state.captureTool === "rect") {
            if (draftShape.w >= 0.01 && draftShape.h >= 0.01) {
                this._appendAnnotation(this._buildRectAnnotation(draftShape));
            }
        } else if (draftShape && this.state.captureTool === "freehand") {
            if ((draftShape.points || []).length > 1) {
                this._appendAnnotation(this._buildFreehandAnnotation(draftShape));
            }
        }
        this.capturePointerState = {
            active: false,
            moved: false,
            start: null,
            points: [],
        };
        this.state.captureDraftShape = null;
        this.captureSuppressClick = true;
    }

    selectAnnotationFromDataset(ev) {
        const annotationId = Number(ev.currentTarget.dataset.annotationId);
        if (!annotationId) {
            return;
        }
        this._selectAnnotation(annotationId);
    }

    onAnnotationTextInput(ev) {
        const activeId = this.state.activeAnnotationId;
        if (!activeId) {
            return;
        }
        const value = ev.target.value || "";
        this.state.activeAnnotationText = value;
        this._updateAnnotation(activeId, { text: value });
    }

    removeSelectedAnnotation() {
        if (!this.state.activeAnnotationId) {
            return;
        }
        const removedId = this.state.activeAnnotationId;
        const remaining = this.state.captureAnnotations.filter(
            (annotation) => annotation.id !== removedId
        );
        this.state.captureAnnotations = remaining;
        if (remaining.length) {
            this._selectAnnotation(remaining[remaining.length - 1].id);
        } else {
            this.state.activeAnnotationId = null;
            this.state.activeAnnotationText = "";
            this.state.activeAnnotationType = "";
        }
    }

    async saveAnnotatedSnapshot() {
        if (!this.state.captureDraftImage || this.state.reviewBusy) {
            return;
        }
        this.state.reviewBusy = true;
        try {
            const annotatedImage = await this._buildAnnotatedSnapshotDataUrl();
            const snapshotName = `${this.state.modelName || "BIM"} Snapshot`;
            const response = await rpc(`/bim/version/${this.state.versionId}/snapshot`, {
                image_data_url: annotatedImage,
                camera: this.state.captureDraftCamera || this._getCurrentCameraPayload(),
                note: this.state.snapshotNote,
                name: snapshotName,
                annotations: this.state.captureAnnotations,
            });
            this.clearCaptureDraft();
            await this._loadReviewData();
            this.state.selectedSnapshotId = response?.snapshot_id || this.state.selectedSnapshotId;
        } catch (error) {
            this.state.error = error.message || "No se pudo guardar la captura anotada.";
        } finally {
            this.state.reviewBusy = false;
        }
    }

    async _buildAnnotatedSnapshotDataUrl() {
        const image = await loadImage(this.state.captureDraftImage);
        const canvas = document.createElement("canvas");
        canvas.width = image.naturalWidth;
        canvas.height = image.naturalHeight;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(image, 0, 0);
        ctx.font = `600 ${Math.max(18, Math.round(canvas.width * 0.014))}px sans-serif`;
        ctx.textBaseline = "middle";
        for (const annotation of this.state.captureAnnotations) {
            if (annotation.type === "marker") {
                this._drawMarkerAnnotation(ctx, canvas, annotation);
            } else if (annotation.type === "text") {
                this._drawTextAnnotation(ctx, canvas, annotation);
            } else if (annotation.type === "rect") {
                this._drawRectangleAnnotation(ctx, canvas, annotation);
            } else if (annotation.type === "freehand") {
                this._drawFreehandAnnotation(ctx, canvas, annotation);
            }
        }
        return canvas.toDataURL("image/png");
    }

    _drawMarkerAnnotation(ctx, canvas, annotation) {
        const markerRadius = Math.max(18, Math.round(canvas.width * 0.012));
        const px = annotation.x * canvas.width;
        const py = annotation.y * canvas.height;
        ctx.fillStyle = annotation.color || CAPTURE_COLORS[0];
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = Math.max(2, Math.round(canvas.width * 0.002));
        ctx.beginPath();
        ctx.arc(px, py, markerRadius, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.fillText(String(annotation.id), px, py + 1);

        const label = annotation.text || `Punto ${annotation.id}`;
        this._drawLabelBubble(ctx, label, px + markerRadius + 16, py, annotation.color);
    }

    _drawTextAnnotation(ctx, canvas, annotation) {
        const label = annotation.text || `Texto ${annotation.id}`;
        this._drawLabelBubble(
            ctx,
            label,
            annotation.x * canvas.width,
            annotation.y * canvas.height,
            annotation.color,
            true
        );
    }

    _drawRectangleAnnotation(ctx, canvas, annotation) {
        const x = annotation.x * canvas.width;
        const y = annotation.y * canvas.height;
        const width = annotation.w * canvas.width;
        const height = annotation.h * canvas.height;
        ctx.strokeStyle = annotation.color || CAPTURE_COLORS[0];
        ctx.lineWidth = annotation.width || 3;
        ctx.strokeRect(x, y, width, height);
        if (annotation.text) {
            this._drawLabelBubble(ctx, annotation.text, x + 8, y + 18, annotation.color, true);
        }
    }

    _drawFreehandAnnotation(ctx, canvas, annotation) {
        const points = annotation.points || [];
        if (points.length < 2) {
            return;
        }
        ctx.strokeStyle = annotation.color || CAPTURE_COLORS[0];
        ctx.lineWidth = annotation.width || 3;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.beginPath();
        ctx.moveTo(points[0].x * canvas.width, points[0].y * canvas.height);
        for (const point of points.slice(1)) {
            ctx.lineTo(point.x * canvas.width, point.y * canvas.height);
        }
        ctx.stroke();
        if (annotation.text) {
            const lastPoint = points[points.length - 1];
            this._drawLabelBubble(
                ctx,
                annotation.text,
                lastPoint.x * canvas.width + 10,
                lastPoint.y * canvas.height,
                annotation.color,
                true
            );
        }
    }

    _drawLabelBubble(ctx, label, x, y, color, compact = false) {
        const paddingX = compact ? 10 : 12;
        const metrics = ctx.measureText(label);
        const boxWidth = metrics.width + paddingX * 2;
        const boxHeight = compact ? 30 : 34;
        ctx.fillStyle = "rgba(17, 25, 34, 0.84)";
        ctx.fillRect(x, y - boxHeight / 2, boxWidth, boxHeight);
        ctx.strokeStyle = color || CAPTURE_COLORS[0];
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y - boxHeight / 2, boxWidth, boxHeight);
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "left";
        ctx.fillText(label, x + paddingX, y + 1);
    }

    async submitComment() {
        if (!this.state.commentText.trim() || this.state.reviewBusy) {
            return;
        }
        this.state.reviewBusy = true;
        try {
            await rpc(`/bim/version/${this.state.versionId}/comment`, {
                title: this.state.commentTitle,
                priority: this.state.commentPriority,
                comment: this.state.commentText,
                camera: this._getCurrentCameraPayload(),
                element_guid: this.state.commentElementGuid || this.state.selectedElementGuid || "",
                snapshot_id: this.state.commentSnapshotId || this.state.selectedSnapshotId || false,
            });
            this.state.commentText = "";
            this.state.commentTitle = "Revision BIM";
            this.state.commentSnapshotId = null;
            await this._loadReviewData();
        } catch (error) {
            this.state.error = error.message || "No se pudo guardar la nota.";
        } finally {
            this.state.reviewBusy = false;
        }
    }

    async setCommentStatusFromDataset(ev) {
        const commentId = Number(ev.currentTarget.dataset.commentId);
        const status = ev.currentTarget.dataset.status;
        if (!commentId || !status || this.state.reviewBusy) {
            return;
        }
        this.state.reviewBusy = true;
        try {
            await rpc(`/bim/comment/${commentId}/status`, { status });
            await this._loadReviewData();
        } catch (error) {
            this.state.error = error.message || "No se pudo actualizar el estado de la revision.";
        } finally {
            this.state.reviewBusy = false;
        }
    }

    restoreView() {
        if (this.cesiumViewer && this.tileset) {
            this.cesiumViewer.zoomTo(this.tileset);
            this._requestRender();
        }
    }

    restoreCameraFromDataset(ev) {
        const cameraJson = ev?.currentTarget?.dataset?.cameraJson || "";
        this.restoreCameraFromJson(cameraJson);
    }

    selectSnapshotFromDataset(ev) {
        const snapshotId = Number(ev.currentTarget.dataset.snapshotId);
        if (!snapshotId) {
            return;
        }
        this.state.selectedSnapshotId = snapshotId;
    }

    restoreSnapshotCameraFromDataset(ev) {
        const snapshotId = Number(ev.currentTarget.dataset.snapshotId);
        const snapshot = this.state.snapshots.find((item) => item.id === snapshotId);
        if (snapshot?.camera_json) {
            this.restoreCameraFromJson(snapshot.camera_json);
        }
    }

    closeSnapshotPreview() {
        this.state.selectedSnapshotId = null;
    }

    restoreSelectedSnapshotCamera() {
        const snapshot = this.getSelectedSnapshot();
        if (snapshot?.camera_json) {
            this.restoreCameraFromJson(snapshot.camera_json);
        }
    }

    getSelectedSnapshot() {
        return (
            this.state.snapshots.find((item) => item.id === this.state.selectedSnapshotId) || null
        );
    }

    prefillCommentFromSelectedSnapshot() {
        const snapshot = this.getSelectedSnapshot();
        if (!snapshot) {
            return;
        }
        this.state.commentSnapshotId = snapshot.id;
        this.state.commentTitle = snapshot.name || "Revision BIM";
        const annotationNotes = (snapshot.annotations || [])
            .map((annotation) => annotation.text)
            .filter(Boolean);
        const noteParts = [];
        if (snapshot.note) {
            noteParts.push(snapshot.note);
        }
        if (annotationNotes.length) {
            noteParts.push(annotationNotes.join("\n"));
        }
        this.state.commentText = noteParts.join("\n\n").trim();
    }

    getSnapshotCardClass(snapshot) {
        return snapshot.id === this.state.selectedSnapshotId
            ? "o_bim_viewer__snapshot-card o_bim_viewer__snapshot-card--active"
            : "o_bim_viewer__snapshot-card";
    }

    restoreCameraFromJson(cameraJson) {
        if (!this.cesiumViewer) {
            return;
        }
        const camera = safeJsonParse(cameraJson, null);
        if (!camera || !camera.destination) {
            return;
        }
        const Cesium = window.Cesium;
        this.cesiumViewer.camera.flyTo({
            destination: new Cesium.Cartesian3(
                camera.destination.x,
                camera.destination.y,
                camera.destination.z
            ),
            orientation: {
                heading: camera.heading,
                pitch: camera.pitch,
                roll: camera.roll,
            },
            duration: 0.8,
        });
    }

    setQualityLow() {
        this.state.qualityPreset = "low";
        this._applyQualityPreset();
    }

    setQualityStandard() {
        this.state.qualityPreset = "standard";
        this._applyQualityPreset();
    }

    setQualityHigh() {
        this.state.qualityPreset = "high";
        this._applyQualityPreset();
    }

    setClipAxisHorizontal() {
        this.state.clipAxis = "z";
        this.state.clipDistance = -this.state.clipRange;
        this._updateClippingPlane();
    }

    setClipAxisVerticalX() {
        this.state.clipAxis = "x";
        this.state.clipDistance = 0;
        this._updateClippingPlane();
    }

    setClipAxisVerticalY() {
        this.state.clipAxis = "y";
        this.state.clipDistance = 0;
        this._updateClippingPlane();
    }

    toggleClipping(ev) {
        this.state.clipEnabled = Boolean(ev.target.checked);
        this._updateClippingPlane();
    }

    onClipDistanceInput(ev) {
        this.state.clipDistance = clamp(
            Number(ev.target.value || 0),
            -this.state.clipRange,
            this.state.clipRange
        );
        this._updateClippingPlane();
    }

    resetClippingDistance() {
        this.state.clipDistance = 0;
        this._updateClippingPlane();
    }

    onSnapshotNoteInput(ev) {
        this.state.snapshotNote = ev.target.value || "";
    }

    onCommentTextInput(ev) {
        this.state.commentText = ev.target.value || "";
    }

    onCommentGuidInput(ev) {
        this.state.commentElementGuid = ev.target.value || "";
    }

    onCommentTitleInput(ev) {
        this.state.commentTitle = ev.target.value || "";
    }

    onCommentPriorityChange(ev) {
        this.state.commentPriority = ev.target.value || "medium";
    }

    _applyQualityPreset() {
        if (!this.cesiumViewer || !this.tileset) {
            return;
        }
        const deviceScale = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
        if (this.state.qualityPreset === "low") {
            this.cesiumViewer.resolutionScale = 1;
            this.tileset.maximumScreenSpaceError = 24;
        } else if (this.state.qualityPreset === "standard") {
            this.cesiumViewer.resolutionScale = Math.min(1.25, deviceScale);
            this.tileset.maximumScreenSpaceError = 16;
        } else {
            this.cesiumViewer.resolutionScale = Math.min(1.75, deviceScale * 1.25);
            this.tileset.maximumScreenSpaceError = 8;
        }
        this._requestRender();
    }

    _updateClippingPlane() {
        if (!this.tileset || !this.tileset.clippingPlanes || !this.clippingPlane) {
            return;
        }
        const Cesium = window.Cesium;
        this.clippingPlane.normal = this._getClipNormal(Cesium);
        this.clippingPlane.distance = clamp(
            this.state.clipDistance,
            -this.state.clipRange,
            this.state.clipRange
        );
        if (this.clippingPlaneMatrix) {
            this.tileset.clippingPlanes.modelMatrix = this.clippingPlaneMatrix;
        }
        this.tileset.clippingPlanes.enabled = this.state.clipEnabled;
        this._requestRender();
    }

    _getCurrentCameraPayload() {
        if (!this.cesiumViewer) {
            return {};
        }
        const camera = this.cesiumViewer.camera;
        const destination = camera.positionWC;
        return {
            destination: {
                x: destination.x,
                y: destination.y,
                z: destination.z,
            },
            heading: camera.heading,
            pitch: camera.pitch,
            roll: camera.roll,
        };
    }

    _requestRender() {
        if (this.cesiumViewer?.scene) {
            this.cesiumViewer.scene.requestRender();
        }
    }

    async _captureCurrentFrameDataUrl() {
        if (!this.cesiumViewer?.canvas) {
            throw new Error("El visor no esta listo para capturar.");
        }
        this.cesiumViewer.resize();
        this.cesiumViewer.render();
        await new Promise((resolve) => window.requestAnimationFrame(resolve));
        this.cesiumViewer.render();
        await new Promise((resolve) => window.requestAnimationFrame(resolve));
        return this.cesiumViewer.canvas.toDataURL("image/png");
    }

    async _ensureCesiumLoaded() {
        if (window.Cesium) {
            return;
        }
        if (!this.state.cesiumJsUrl) {
            throw new Error("Cesium JS URL is not configured.");
        }
        if (this.state.cesiumCssUrl) {
            this._loadStylesheetOnce(this.state.cesiumCssUrl);
        }
        await this._loadScriptOnce(this.state.cesiumJsUrl);
        if (!window.Cesium) {
            throw new Error("CesiumJS loaded but window.Cesium is not available.");
        }
    }

    _loadStylesheetOnce(url) {
        const existing = document.querySelector(`link[data-bim-cesium-css="${url}"]`);
        if (existing) {
            return;
        }
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = url;
        link.dataset.bimCesiumCss = url;
        document.head.appendChild(link);
    }

    _loadScriptOnce(url) {
        if (!window.__bimCesiumLoader) {
            window.__bimCesiumLoader = {};
        }
        if (window.__bimCesiumLoader[url]) {
            return window.__bimCesiumLoader[url];
        }
        window.__bimCesiumLoader[url] = new Promise((resolve, reject) => {
            const existing = document.querySelector(`script[data-bim-cesium-js="${url}"]`);
            if (existing) {
                if (window.Cesium) {
                    resolve();
                    return;
                }
                existing.addEventListener("load", () => resolve(), { once: true });
                existing.addEventListener(
                    "error",
                    () => reject(new Error("CesiumJS script failed to load.")),
                    { once: true }
                );
                return;
            }
            const script = document.createElement("script");
            script.src = url;
            script.async = true;
            script.dataset.bimCesiumJs = url;
            script.onload = () => resolve();
            script.onerror = () => reject(new Error("CesiumJS script failed to load."));
            document.head.appendChild(script);
        });
        return window.__bimCesiumLoader[url];
    }

    _getCapturePointerPosition(ev) {
        const stage = ev.currentTarget;
        if (!stage) {
            return null;
        }
        const rect = stage.getBoundingClientRect();
        if (!rect.width || !rect.height) {
            return null;
        }
        return {
            x: clamp01((ev.clientX - rect.left) / rect.width),
            y: clamp01((ev.clientY - rect.top) / rect.height),
        };
    }

    _normalizeRect(start, end) {
        return {
            x: Math.min(start.x, end.x),
            y: Math.min(start.y, end.y),
            w: Math.abs(end.x - start.x),
            h: Math.abs(end.y - start.y),
        };
    }

    _buildMarkerAnnotation(position) {
        const id = this._nextAnnotationId();
        return {
            id,
            type: "marker",
            x: position.x,
            y: position.y,
            text: `Punto ${id}`,
            color: this.state.captureColor,
            width: this.state.captureStrokeWidth,
        };
    }

    _buildTextAnnotation(position) {
        const id = this._nextAnnotationId();
        return {
            id,
            type: "text",
            x: position.x,
            y: position.y,
            text: `Texto ${id}`,
            color: this.state.captureColor,
            width: this.state.captureStrokeWidth,
        };
    }

    _buildRectAnnotation(rect) {
        const id = this._nextAnnotationId();
        return {
            id,
            type: "rect",
            x: rect.x,
            y: rect.y,
            w: rect.w,
            h: rect.h,
            text: `Area ${id}`,
            color: rect.color,
            width: rect.width,
        };
    }

    _buildFreehandAnnotation(shape) {
        const id = this._nextAnnotationId();
        const points = (shape.points || []).map((point) => ({ x: point.x, y: point.y }));
        return {
            id,
            type: "freehand",
            points,
            points_text: pointsToText(points),
            text: `Trazo ${id}`,
            color: shape.color,
            width: shape.width,
        };
    }

    _nextAnnotationId() {
        return this.state.captureAnnotations.reduce(
            (maxId, item) => Math.max(maxId, Number(item.id) || 0),
            0
        ) + 1;
    }

    _appendAnnotation(annotation) {
        this.state.captureAnnotations = [...this.state.captureAnnotations, annotation];
        this._selectAnnotation(annotation.id);
    }

    _selectAnnotation(annotationId) {
        const annotation = this.state.captureAnnotations.find((item) => item.id === annotationId);
        if (!annotation) {
            this.state.activeAnnotationId = null;
            this.state.activeAnnotationText = "";
            this.state.activeAnnotationType = "";
            return;
        }
        this.state.activeAnnotationId = annotationId;
        this.state.activeAnnotationText = annotation.text || "";
        this.state.activeAnnotationType = annotation.type || "";
        this.state.captureColor = annotation.color || this.state.captureColor;
        this.state.captureStrokeWidth = annotation.width || this.state.captureStrokeWidth;
    }

    _updateAnnotation(annotationId, patch) {
        this.state.captureAnnotations = this.state.captureAnnotations.map((annotation) => {
            if (annotation.id !== annotationId) {
                return annotation;
            }
            const updated = { ...annotation, ...patch };
            if (updated.type === "freehand") {
                updated.points_text = pointsToText(updated.points || []);
            }
            return updated;
        });
        this._selectAnnotation(annotationId);
    }

    getAnnotationItemClass(annotation) {
        return annotation.id === this.state.activeAnnotationId
            ? "o_bim_viewer__annotation-item o_bim_viewer__annotation-item--active"
            : "o_bim_viewer__annotation-item";
    }

    getMarkerStyle(annotation) {
        return [
            `left:${annotation.x * 100}%`,
            `top:${annotation.y * 100}%`,
            `--annotation-color:${annotation.color || this.state.captureColor}`,
        ].join("; ");
    }

    getTextStyle(annotation) {
        return [
            `left:${annotation.x * 100}%`,
            `top:${annotation.y * 100}%`,
            `--annotation-color:${annotation.color || this.state.captureColor}`,
        ].join("; ");
    }

    getRectStyle(annotation) {
        return [
            `left:${annotation.x * 100}%`,
            `top:${annotation.y * 100}%`,
            `width:${annotation.w * 100}%`,
            `height:${annotation.h * 100}%`,
            `--annotation-color:${annotation.color || this.state.captureColor}`,
            `--annotation-width:${annotation.width || 3}px`,
        ].join("; ");
    }

    getDraftRectStyle() {
        if (!this.state.captureDraftShape || this.state.captureDraftShape.type !== "rect") {
            return "";
        }
        return this.getRectStyle(this.state.captureDraftShape);
    }

    getSvgPolylineStyle(annotation) {
        const width = clamp(annotation.width || 3, 1, 12);
        const selected = annotation.id === this.state.activeAnnotationId;
        return `stroke:${annotation.color || this.state.captureColor}; stroke-width:${
            selected ? width + 1.5 : width
        };`;
    }

    getDraftPolylineStyle() {
        if (!this.state.captureDraftShape || this.state.captureDraftShape.type !== "freehand") {
            return "";
        }
        return `stroke:${this.state.captureDraftShape.color}; stroke-width:${this.state.captureDraftShape.width};`;
    }

    getAnnotationPointsText(annotation) {
        return annotation.points_text || pointsToText(annotation.points || []);
    }

    getDraftPointsText() {
        return this.state.captureDraftShape?.points_text || "";
    }

    getAnnotationSummary(annotation) {
        return `${this.getAnnotationTypeLabel(annotation.type)} ${annotation.id}`;
    }

    getAnnotationTypeLabel(type) {
        if (type === "rect") {
            return "Rect";
        }
        if (type === "text") {
            return "Text";
        }
        if (type === "freehand") {
            return "Pencil";
        }
        return "Marker";
    }

    _destroyViewer() {
        if (this.screenSpaceHandler) {
            this.screenSpaceHandler.destroy();
        }
        this.screenSpaceHandler = null;
        if (this.cesiumViewer && !this.cesiumViewer.isDestroyed()) {
            this.cesiumViewer.destroy();
        }
        this.cesiumViewer = null;
        this.tileset = null;
        this.clippingPlane = null;
        this.clippingPlaneMatrix = null;
    }
}

registry.category("actions").add("odoo_bim_ifc_tiles.BimViewerAction", BimViewerClientAction);

export default BimViewerClientAction;
