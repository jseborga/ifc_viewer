# Guía de despliegue y pruebas en Easypanel

## Qué archivos subir al servidor

Para probar el módulo en Odoo solo necesitas subir la carpeta:

- `odoo_bim_ifc_tiles/`

Estos archivos son de apoyo y no hace falta copiarlos al contenedor de Odoo:

- `SPEC_ODOO18_CE_IFC_VIEWER.md`
- `instrucciones.txt`
- `GUIA_PRUEBAS_EASYPANEL.md`

## Dónde colocar el módulo

Sube `odoo_bim_ifc_tiles/` a una ruta incluida en `addons_path`, por ejemplo:

- `/opt/odoo/custom-addons/odoo_bim_ifc_tiles`

## Ejemplo concreto de subida en servidor

Si tu contenedor Odoo ya monta una carpeta de addons personalizados, el flujo típico es:

1. Comprimir localmente la carpeta `odoo_bim_ifc_tiles`.
2. Subirla al servidor por SFTP, SCP o el administrador de archivos de Easypanel.
3. Descomprimirla dentro de tu carpeta de addons.

Ejemplo de destino:

- `/opt/odoo/custom-addons/odoo_bim_ifc_tiles`

El resultado final debe verse así:

- `/opt/odoo/custom-addons/odoo_bim_ifc_tiles/__manifest__.py`
- `/opt/odoo/custom-addons/odoo_bim_ifc_tiles/models/`
- `/opt/odoo/custom-addons/odoo_bim_ifc_tiles/views/`
- `/opt/odoo/custom-addons/odoo_bim_ifc_tiles/static/`

## Pasos en Odoo

1. Reinicia el servicio de Odoo.
2. Activa modo desarrollador.
3. Ve a Apps.
4. Ejecuta `Update Apps List`.
5. Busca `BIM IFC Tiles Viewer`.
6. Instala el módulo.

## Estado actual del visor 3D

La integración backend con el microservicio ya quedó operativa.

El render 3D final ahora puede usar CesiumJS desde CDN oficial configurable en `Settings`.
En este estado del módulo:

- puedes probar instalación
- puedes probar carga de IFC
- puedes probar envío al microservicio
- puedes probar callback y cambio de estados
- puedes probar el botón `Open Viewer`
- el visor cargará Cesium automáticamente desde la URL configurada
- si el navegador no puede salir a Internet o la CDN está bloqueada, el visor mostrará placeholder

## Configuración mínima en Settings

En `Settings > BIM IFC Viewer` configura:

- `Converter Endpoint`
- `Shared Token`
- `Request Timeout`
- `Verify SSL`
- `Public Base URL`
- `Cesium JS URL`
- `Cesium CSS URL`

## Primera prueba recomendada: sin conversor real

Esta prueba sirve para verificar que:

- el módulo instala
- el menú aparece
- el formulario BIM funciona
- el visor abre
- Cesium carga desde CDN

### Valores exactos para esta primera prueba

- `Converter Endpoint`: déjalo vacío por ahora
- `Shared Token`: déjalo vacío por ahora
- `Request Timeout`: `30`
- `Verify SSL`: activado
- `Public Base URL`: `https://TU-ODOO`
- `Cesium JS URL`: `https://cesium.com/downloads/cesiumjs/releases/1.139.1/Build/Cesium/Cesium.js`
- `Cesium CSS URL`: `https://cesium.com/downloads/cesiumjs/releases/1.139.1/Build/Cesium/Widgets/widgets.css`

### Paso a paso exacto

1. Entra a `BIM > Models`.
2. Crea un modelo nuevo:
   - `Name`: `Prueba IFC`
   - `Discipline`: `Architecture`
3. Guarda.
4. En `Versions`, crea una nueva versión.
5. Adjunta cualquier archivo `.ifc`.
6. Guarda la versión.
7. En esa versión, completa manualmente:
   - `Status`: `ready`
   - `Tileset URL`: una URL pública de `tileset.json`
8. Pulsa `Open Viewer`.

### URL pública de prueba para el campo `Tileset URL`

Puedes probar con un tileset público de ejemplo alojado desde GitHub CDN:

- `https://cdn.jsdelivr.net/gh/CesiumGS/3d-tiles-samples@main/1.0/TilesetWithDiscreteLOD/tileset.json`

Referencia del repositorio de ejemplos:

- https://github.com/CesiumGS/3d-tiles-samples

Si todo está bien:

- abrirá la pantalla del visor
- cargará Cesium desde CDN
- debería verse el modelo de ejemplo

Si no se ve:

- revisa consola del navegador
- revisa que tu servidor permita salir a `cesium.com`
- revisa que la URL del tileset responda desde el navegador
- revisa CORS del tileset si el navegador lo bloquea

## Segunda prueba: con callback manual pero sin conversor real

Esta prueba valida la integración backend Odoo -> callback.

### Configuración

- `Shared Token`: `abc123456`
- `Public Base URL`: `https://TU-ODOO`

El `Converter Endpoint` todavía puede quedar vacío si no vas a pulsar `Queue Conversion`.

### Preparación del registro

1. Crea un `BIM Model`.
2. Crea una `BIM Version`.
3. Adjunta un IFC.
4. Guarda.

### Llamada manual al callback

Haz un `POST` a:

- `https://TU-ODOO/bim/conversion/callback`

Headers:

- `Authorization: Bearer abc123456`
- `Content-Type: application/json`

Body:

```json
{
  "version_id": 1,
  "status": "ready",
  "job_id": "manual-test-1",
  "tileset_url": "https://cdn.jsdelivr.net/gh/CesiumGS/3d-tiles-samples@main/1.0/TilesetWithDiscreteLOD/tileset.json",
  "conversion_log": "Manual callback test"
}
```

Si el `version_id` existe, la versión debe quedar en:

- `status = ready`
- `conversion_job_ref = manual-test-1`
- `tileset_url` con la URL enviada

Después de eso:

1. abre la versión
2. pulsa `Open Viewer`

## Tercera prueba: con endpoint temporal falso

Si quieres probar también el botón `Queue Conversion`, puedes poner un microservicio mínimo que solo responda JSON.

El endpoint debe aceptar `POST` y devolver algo como:

```json
{
  "status": "processing",
  "job_id": "job-prueba-1"
}
```

Con eso, al pulsar `Queue Conversion`, Odoo debe:

- cambiar la versión a `processing`
- guardar `job-prueba-1`
- dejar traza en `conversion_log`

Luego haces el callback manual del bloque anterior.

Ejemplo:

- `Converter Endpoint`: `https://converter.midominio.com/api/jobs`
- `Shared Token`: un valor secreto compartido entre Odoo y el microservicio
- `Public Base URL`: `https://odoo.midominio.com`
- `Cesium JS URL`: `https://cesium.com/downloads/cesiumjs/releases/1.139.1/Build/Cesium/Cesium.js`
- `Cesium CSS URL`: `https://cesium.com/downloads/cesiumjs/releases/1.139.1/Build/Cesium/Widgets/widgets.css`

## Contrato que Odoo enviará al microservicio

```json
{
  "version_id": 15,
  "model_name": "Hospital Central",
  "source_filename": "modelo.ifc",
  "ifc_download_url": "https://odoo.midominio.com/bim/version/15/ifc",
  "callback_url": "https://odoo.midominio.com/bim/conversion/callback",
  "access_token": "TOKEN_COMPARTIDO",
  "longitude": -68.1193,
  "latitude": -16.4897,
  "height": 3650,
  "heading": 0,
  "pitch": 0,
  "roll": 0
}
```

## Qué debe responder el microservicio al aceptar el trabajo

Respuesta inmediata esperada:

```json
{
  "status": "processing",
  "job_id": "job-15"
}
```

O también puede responder directamente:

```json
{
  "status": "ready",
  "job_id": "job-15",
  "tileset_url": "https://storage.midominio.com/tiles/15/tileset.json",
  "conversion_log": "Conversion completed"
}
```

## Callback que debe hacer el microservicio al terminar

Endpoint:

- `POST /bim/conversion/callback`

Headers:

- `Authorization: Bearer TOKEN_COMPARTIDO`

Body:

```json
{
  "version_id": 15,
  "status": "ready",
  "job_id": "job-15",
  "tileset_url": "https://storage.midominio.com/tiles/15/tileset.json",
  "conversion_log": "IfcConvert + tiles generation completed",
  "error_message": ""
}
```

Si falla:

```json
{
  "version_id": 15,
  "status": "error",
  "job_id": "job-15",
  "conversion_log": "Conversion failed",
  "error_message": "IfcConvert returned exit code 1"
}
```

## Ruta que usará el microservicio para descargar el IFC

- `GET /bim/version/<version_id>/ifc`

Headers:

- `Authorization: Bearer TOKEN_COMPARTIDO`

## Secuencia de prueba recomendada

1. Instala el módulo.
2. Configura el endpoint y token.
3. Crea un `BIM Model`.
4. Crea una `BIM Version` con un adjunto IFC.
5. Pulsa `Queue Conversion`.
6. Verifica que el microservicio reciba el job.
7. Haz el callback con `status = ready`.
8. Verifica que aparezca el botón `Open Viewer`.
9. Abre el visor.

## Si aún no tienes microservicio listo

Puedes probar la mitad Odoo así:

1. Configura un endpoint temporal que responda `{"status":"processing","job_id":"test-1"}`.
2. Ejecuta `Queue Conversion`.
3. Llama manualmente al callback con `status = ready` y un `tileset_url` válido.
4. Abre el visor.

## Riesgo operativo a vigilar

Si el `Public Base URL` no coincide con la URL pública real de Easypanel, el microservicio no podrá descargar el IFC ni devolver el callback.

## Sobre endpoints públicos gratuitos para convertir IFC

Resumen corto:

- no encontré un endpoint público, gratuito y estable, listo para pegar directamente en `Converter Endpoint` y usar con este módulo tal como está
- sí existen opciones SaaS o self-hosted
- para pruebas reales, lo más práctico es usar un microservicio propio o adaptar uno

### Opciones reales encontradas

1. `Cesium ion`

- soporta AEC/IFC y lo convierte a 3D Tiles
- requiere cuenta y flujo propio
- no encaja directamente como `Converter Endpoint` de este módulo sin un adaptador intermedio

Fuentes:

- https://cesium.com/learn/3d-tiling/ion-tile-aec-models/
- https://cesium.com/learn/3d-tiling/tiler-data-formats/

2. `IfcOpenShell + 3d-tiles-tools`

- es la opción libre y controlable
- no te da una URL pública lista; tú debes montar el microservicio

Fuentes:

- https://docs.ifcopenshell.org/ifcconvert/usage.html
- https://github.com/CesiumGS/3d-tiles-tools

3. `GISBox`

- publicita conversión IFC -> 3DTiles y despliegue propio
- no lo encontré como API pública simple y gratuita para pegar tal cual en Odoo

Fuente:

- https://www.gisbox.com/

## Recomendación práctica

Para avanzar rápido, te recomiendo este orden:

1. prueba primero el visor con el tileset público de ejemplo
2. prueba el callback manual
3. si eso funciona, yo te preparo un microservicio mínimo propio para Easypanel

Ese microservicio sí te dará una URL real para `Converter Endpoint`.
