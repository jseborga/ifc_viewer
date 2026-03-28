# Especificación Técnica

## Objetivo

Construir un módulo para Odoo 18 Community Edition que permita:

- registrar modelos BIM
- versionar archivos IFC
- disparar una conversión asíncrona a 3D Tiles
- abrir un visor 3D en el backend
- asociar snapshots y comentarios a una versión

## Decisiones cerradas

- Odoo maneja negocio, permisos, trazabilidad, menús y UI.
- La conversión IFC -> GLB -> 3D Tiles se hace fuera de Odoo.
- El visor se implementa como `ir.actions.client` con OWL en `web.assets_backend`.
- La visualización usa CesiumJS.
- La metadata BIM no debe depender solo del tileset.
- En Community Edition la base documental debe ser `ir.attachment`; la integración con `documents` queda fuera del alcance base.

## Alcance Fase 1

- CRUD de `bim.model`
- CRUD de `bim.model.version`
- asociación opcional con `project.project` y `project.task`
- almacenamiento del IFC como `ir.attachment`
- estados de conversión: `draft`, `queued`, `processing`, `ready`, `error`
- apertura del visor solo cuando la versión está lista
- snapshots y comentarios ligados a la versión
- endpoint backend para entregar payload del visor
- endpoint backend para redirigir al `tileset.json` real

## Fuera de alcance en este scaffold

- llamada HTTP real al microservicio de conversión
- extracción real de metadata IFC con IfcOpenShell
- federación de varios modelos
- diff visual entre versiones
- georreferenciación avanzada
- empaquetado local de CesiumJS dentro del addon

## Arquitectura

### Backend Odoo

- Modelo maestro: `bim.model`
- Versiones: `bim.model.version`
- Snapshots: `bim.snapshot`
- Comentarios: `bim.comment`
- Seguridad por grupos: usuario BIM y manager BIM
- Acción cliente para abrir el visor

### Microservicio externo

Entrada esperada:

```json
{
  "version_id": 15,
  "ifc_path": "/mnt/files/model.ifc",
  "longitude": -68.1193,
  "latitude": -16.4897,
  "height": 3650,
  "heading": 0,
  "pitch": 0,
  "roll": 0
}
```

Salida esperada:

```json
{
  "version_id": 15,
  "status": "ready",
  "tileset_url": "https://storage.example.com/tiles/15/tileset.json",
  "conversion_log": "IfcConvert + glbToB3dm + createTilesetJson completed"
}
```

### Frontend

- Acción cliente: `odoo_bim_ifc_tiles.BimViewerAction`
- Componente OWL que recibe `version_id`
- Llamada RPC a payload backend
- Render de Cesium si `window.Cesium` está disponible
- Fallback visual si la librería aún no está instalada

## Modelo de datos

### `bim.model`

- `name`
- `project_id`
- `task_id`
- `discipline`
- `description`
- `active_version_id`
- `version_ids`

### `bim.model.version`

- `bim_model_id`
- `ifc_attachment_id`
- `source_filename`
- `ifc_schema`
- `status`
- `uploaded_by`
- `uploaded_on`
- `tileset_url`
- `metadata_json`
- `conversion_log`
- `error_message`
- `georef_lon`
- `georef_lat`
- `georef_height`
- `heading`
- `pitch`
- `roll`

### `bim.snapshot`

- `version_id`
- `name`
- `author_id`
- `image_attachment_id`
- `camera_json`
- `note`

### `bim.comment`

- `version_id`
- `author_id`
- `comment`
- `element_guid`
- `camera_json`

## Flujo base

1. Usuario crea un `bim.model`.
2. Usuario agrega una `bim.model.version` con un IFC adjunto.
3. Odoo marca la versión como `queued`.
4. Una integración futura notificará al microservicio.
5. El microservicio convertirá y devolverá `tileset_url`.
6. Odoo actualizará la versión a `ready`.
7. El usuario abrirá el visor desde la versión.

## Riesgos a resolver en siguiente iteración

- definición del storage físico de IFC y tiles
- control de acceso para recursos 3D si se sirven fuera de Odoo
- mapeo de metadata por `GlobalId`
- estrategia de reintentos y observabilidad del pipeline
- empaquetado de Cesium sin depender de CDN si el entorno es restringido

## Próxima iteración recomendada

1. Añadir configuración del endpoint del microservicio.
2. Implementar cola real de conversión.
3. Persistir metadata IFC en adjunto JSON o tabla auxiliar.
4. Incorporar CesiumJS como asset local del módulo.
5. Añadir panel lateral con árbol, búsqueda y propiedades BIM.

## Referencias oficiales usadas

- Odoo 18 assets: https://www.odoo.com/documentation/18.0/developer/reference/frontend/assets.html
- Odoo 18 client actions: https://www.odoo.com/documentation/18.0/id/developer/howtos/javascript_client_action.html
- Odoo 18 actions: https://www.odoo.com/documentation/18.0/developer/reference/backend/actions.html
- Odoo 18 addons comunitarios: https://github.com/odoo/odoo/tree/18.0/addons
- IfcOpenShell IfcConvert: https://docs.ifcopenshell.org/ifcconvert/usage.html
- Cesium 3D Tiles: https://cesium.com/3d-tiles/
