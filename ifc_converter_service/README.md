# IFC Converter Service

Microservicio compatible con `odoo_bim_ifc_tiles`.

Flujo:

1. Odoo envía un job a `POST /jobs`
2. El servicio descarga el IFC desde Odoo
3. Ejecuta `IfcConvert`
4. Genera `3D Tiles` con `3d-tiles-tools`
5. Publica `tileset.json` en `/tiles/<version_id>/tileset.json`
6. Hace callback a Odoo

Endpoints:

- `GET /health`
- `POST /jobs`
- `GET /jobs/{job_id}`
- `GET /tiles/{version_id}/{resource_path}`

Variables de entorno mínimas:

- `PUBLIC_BASE_URL`
- `SHARED_TOKEN`
- `STORAGE_ROOT`

Despliegue recomendado:

- Easypanel App Service usando `Dockerfile`
- volumen persistente montado en `/data`
