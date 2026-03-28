# BIM IFC Tiles Viewer

Scaffold inicial para Odoo 18 Community Edition.

Incluye:

- modelos BIM y versionado IFC
- seguridad base
- menús y vistas
- acción cliente OWL para visor
- endpoints backend para payload y redirección al tileset

No incluye todavía:

- extracción real de metadata IFC
- librería Cesium vendorizada

La integración real con un conversor externo ya está preparada mediante:

- ajustes en `Settings`
- envío del job por HTTP desde Odoo
- descarga autenticada del IFC
- callback autenticado para actualizar la versión

La guía de despliegue y pruebas está en `GUIA_PRUEBAS_EASYPANEL.md`.

Para probar el visor con este scaffold:

1. Cree un modelo BIM.
2. Cree una versión y adjunte un IFC.
3. Establezca manualmente `status = ready`.
4. Coloque un valor válido en `tileset_url`.
5. Abra el visor desde el botón de la versión.

Si `window.Cesium` no está disponible, el visor mostrará un placeholder en lugar del canvas 3D.
