/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";

class BimViewerClientAction extends Component {
    static template = "odoo_bim_ifc_tiles.BimViewerAction";

    setup() {
        this.viewerRef = useRef("viewer");
        this.cesiumViewer = null;
        this.tileset = null;
        this.state = useState({
            loading: true,
            error: null,
            viewerStatus: "idle",
            versionId: this.props.action?.params?.version_id || null,
            versionName: "",
            modelName: "",
            sourceFilename: "",
            status: "",
            tilesetUrl: "",
            rawTilesetUrl: "",
            cesiumJsUrl: "",
            cesiumCssUrl: "",
            metadataHint: "",
        });

        onWillStart(async () => {
            if (!this.state.versionId) {
                this.state.error = "No se recibió version_id para abrir el visor.";
                this.state.loading = false;
                return;
            }
            try {
                const payload = await rpc(`/bim/version/${this.state.versionId}/payload`, {});
                this.state.versionName = payload.name || "";
                this.state.modelName = payload.model_name || "";
                this.state.sourceFilename = payload.source_filename || "";
                this.state.status = payload.status || "";
                this.state.tilesetUrl = payload.tileset_url || "";
                this.state.rawTilesetUrl = payload.raw_tileset_url || "";
                this.state.cesiumJsUrl = payload.cesium_js_url || "";
                this.state.cesiumCssUrl = payload.cesium_css_url || "";
                this.state.metadataHint = payload.metadata_hint || "";
            } catch (error) {
                this.state.error = error.message || "No se pudo cargar el payload del visor.";
                this.state.loading = false;
            }
        });

        onMounted(() => this._mountViewer());
        onWillUnmount(() => this._destroyViewer());
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
                fullscreenButton: false,
                geocoder: false,
                homeButton: false,
                infoBox: false,
                navigationHelpButton: false,
                sceneModePicker: false,
                timeline: false,
            });
            this.tileset = await Cesium.Cesium3DTileset.fromUrl(this.state.tilesetUrl);
            this.cesiumViewer.scene.primitives.add(this.tileset);
            await this.cesiumViewer.zoomTo(this.tileset);
            this.state.viewerStatus = "ready";
        } catch (error) {
            this.state.error = error.message || "Cesium no pudo abrir el tileset.";
            this.state.viewerStatus = "error";
        } finally {
            this.state.loading = false;
        }
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

    _destroyViewer() {
        if (this.cesiumViewer && !this.cesiumViewer.isDestroyed()) {
            this.cesiumViewer.destroy();
        }
        this.cesiumViewer = null;
        this.tileset = null;
    }
}

registry.category("actions").add("odoo_bim_ifc_tiles.BimViewerAction", BimViewerClientAction);

export default BimViewerClientAction;
