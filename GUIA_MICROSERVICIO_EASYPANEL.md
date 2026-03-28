# Guía de despliegue del microservicio en Easypanel

## Archivos a subir

Para el conversor sube la carpeta:

- `ifc_converter_service/`

Para Odoo ya debes tener subida la carpeta:

- `odoo_bim_ifc_tiles/`

## Qué hace este microservicio

- recibe el job desde Odoo
- descarga el IFC desde Odoo
- lo convierte a GLB con `IfcConvert`
- genera `3D Tiles`
- expone el `tileset.json`
- hace callback a Odoo para dejar la versión en `ready`

## Paso 1 - Crear el servicio en Easypanel

1. Entra a Easypanel.
2. Crea un nuevo `App Service`.
3. Como origen, usa tu repositorio Git o sube el contenido al servidor.
4. En `Build`, selecciona `Dockerfile`.
5. Como ruta del Dockerfile usa:

- `ifc_converter_service/Dockerfile`

6. Define el puerto expuesto:

- `8080`

7. Asigna un dominio público, por ejemplo:

- `https://converter.tudominio.com`

## Paso 2 - Crear volumen persistente

Crea un volumen y móntalo en:

- `/data`

Eso guardará:

- jobs temporales
- `model.b3dm`
- `tileset.json`
- recursos del tileset

## Paso 3 - Variables de entorno del microservicio

Configura estas variables en Easypanel:

- `PUBLIC_BASE_URL=https://converter.tudominio.com`
- `SHARED_TOKEN=abc123456`
- `STORAGE_ROOT=/data`
- `VERIFY_SSL=true`
- `PORT=8080`
- `LOG_LEVEL=INFO`
- `DOWNLOAD_TIMEOUT=300`
- `CALLBACK_TIMEOUT=60`
- `IFC_CONVERT_BIN=IfcConvert`

## Paso 4 - Desplegar

Haz `Deploy`.

Cuando termine, prueba:

- `https://converter.tudominio.com/health`

La respuesta esperada debe ser JSON con:

- `ok: true`

## Paso 5 - Configurar Odoo

En `Settings > BIM IFC Viewer` completa así:

- `Converter Endpoint`: `https://converter.tudominio.com/jobs`
- `Shared Token`: `abc123456`
- `Request Timeout`: `30`
- `Verify SSL`: activado
- `Public Base URL`: `https://odoo.tudominio.com`
- `Cesium JS URL`: `https://cesium.com/downloads/cesiumjs/releases/1.139.1/Build/Cesium/Cesium.js`
- `Cesium CSS URL`: `https://cesium.com/downloads/cesiumjs/releases/1.139.1/Build/Cesium/Widgets/widgets.css`

Importante:

- el `Shared Token` debe ser exactamente el mismo en Odoo y en el microservicio
- `Public Base URL` en Odoo debe ser la URL pública real del Odoo publicado por Easypanel

## Paso 6 - Prueba completa

1. En Odoo crea un `BIM Model`.
2. Agrega una versión.
3. Sube un archivo `.ifc`.
4. Guarda.
5. Pulsa `Queue Conversion`.

Resultado esperado:

- Odoo cambia la versión a `processing`
- el conversor recibe el job
- descarga el IFC desde Odoo
- genera el tileset
- hace callback
- Odoo cambia la versión a `ready`
- aparece `Open Viewer`

## URLs que usa el flujo

Odoo envía al microservicio algo de este tipo:

```json
{
  "version_id": 15,
  "source_filename": "modelo.ifc",
  "ifc_download_url": "https://odoo.tudominio.com/bim/version/15/ifc",
  "callback_url": "https://odoo.tudominio.com/bim/conversion/callback",
  "access_token": "abc123456"
}
```

Cuando termina, el microservicio hace callback a Odoo con:

```json
{
  "version_id": 15,
  "status": "ready",
  "job_id": "8f4b0b8d...",
  "tileset_url": "https://converter.tudominio.com/tiles/15/tileset.json",
  "conversion_log": "..."
}
```

## Paso 7 - Verificación manual rápida

Si quieres verificar que el conversor está sirviendo tiles, abre:

- `https://converter.tudominio.com/tiles/15/tileset.json`

Debe devolver JSON cuando ya exista una conversión de la versión `15`.

## Problemas típicos

### Odoo queda en `error`

Revisa:

- token distinto entre Odoo y el microservicio
- `Public Base URL` de Odoo mal configurado
- el dominio público de Odoo no es accesible desde el microservicio
- `IfcConvert` falló con ese IFC

### El job queda en `processing` y no termina

Revisa los logs del microservicio en Easypanel.

### `Open Viewer` aparece pero no se ve nada

Revisa:

- consola del navegador
- acceso a `cesium.com`
- que `tileset_url` responda
- CORS si usas otro dominio o CDN

## Prueba local con Docker Compose

Si quieres probar fuera de Easypanel:

1. entra a la carpeta `ifc_converter_service`
2. ajusta `docker-compose.yml`
3. ejecuta:

```bash
docker compose up --build
```

## Fuentes oficiales usadas

- Easypanel build con Dockerfile: https://easypanel.io/docs/quickstarts/rails
- IfcConvert: https://docs.ifcopenshell.org/ifcconvert/usage.html
- 3d-tiles-tools: https://github.com/CesiumGS/3d-tiles-tools
