# BIM IFC Tiles Viewer

Scaffold inicial para Odoo 18 Community Edition.

Incluye:

- modelos BIM y versionado IFC
- seguridad base
- menus y vistas
- accion cliente OWL para visor
- endpoints backend para payload y redireccion al tileset
- metadata BIM estructurada por `GlobalId`
- resultados de validacion del paquete visual
- consulta HTTP de elementos BIM desde Odoo

No incluye todavia:

- interaccion semantica avanzada directamente dentro del canvas 3D
- libreria Cesium vendorizada

La integracion real con un conversor externo ya esta preparada mediante:

- ajustes en `Settings`
- envio del job por HTTP desde Odoo
- descarga autenticada del IFC
- callback autenticado para actualizar la version

La guia de despliegue y pruebas esta en `GUIA_PRUEBAS_EASYPANEL.md`.

Para probar el visor con este scaffold:

1. Cree un modelo BIM.
2. Cree una version y adjunte un IFC.
3. Ejecute `Queue Conversion`.
4. Espere a que la version quede en `ready`.
5. Abra el visor desde el boton de la version.

Si `window.Cesium` no esta disponible, el visor mostrara un placeholder en lugar del canvas 3D.
