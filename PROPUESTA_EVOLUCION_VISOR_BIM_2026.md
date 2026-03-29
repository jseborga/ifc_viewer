# Propuesta de Evolucion del Visor BIM 2026

## Objetivo

Definir la evolucion del visor BIM y del microservicio de conversion para pasar de un flujo minimo "IFC -> b3dm -> visor" a una arquitectura BIM web moderna, interoperable y preparada para crecimiento funcional dentro de Odoo.

## Validacion de la propuesta

La direccion general de la propuesta es correcta y conviene adoptarla.

Puntos validados:

- El archivo IFC debe seguir siendo la fuente maestra.
- La geometria para visualizacion debe publicarse como contenido optimizado para streaming, preferentemente alineado con 3D Tiles 1.1 y glTF/GLB.
- La metadata BIM no debe depender exclusivamente del tileset visual.
- El visor debe desacoplar render, metadata BIM y logica ERP.
- El servicio necesita validaciones del paquete visual antes de publicar.
- Conviene soportar modalidad autohospedada y modalidad gestionada.

Correccion importante:

- `b3dm` no debe considerarse "prohibido", pero si debe dejar de ser el formato objetivo principal. En 3D Tiles 1.1, glTF es el formato primario y los formatos heredados de 3D Tiles 1.0 quedaron como legado/deprecados. Por tanto, `b3dm` debe quedar solo como compatibilidad temporal o fallback.

## Estado recomendado del stack

- Visor web: CesiumJS, con version fijada y controlada.
- Version de referencia validada: CesiumJS `1.139.1`, publicada el `5 de marzo de 2026` y mostrada en la pagina de descargas de Cesium con fecha `6 de marzo de 2026`.
- Formato visual objetivo: `3D Tiles 1.1` con contenido `glTF/GLB`.
- Metadata BIM: persistida externamente en Odoo o en un almacén asociado, vinculada por `IFC GlobalId` y por un identificador interno estable del elemento.

## Arquitectura objetivo

### 1. Capa de fuente BIM

Responsabilidad:

- conservar el IFC original
- versionar el archivo fuente
- registrar disciplina, fecha, autor, proyecto y trazabilidad documental

Implementacion propuesta:

- Odoo mantiene el `ir.attachment` del IFC original
- cada `bim.model.version` conserva una referencia inmutable al archivo fuente
- toda reconversion parte siempre del IFC, nunca de un derivado visual

### 2. Capa de visualizacion

Responsabilidad:

- generar un paquete ligero para navegador
- optimizar carga progresiva
- soportar streaming y futuros modelos federados

Implementacion propuesta:

- el microservicio genera un `tileset.json`
- el contenido principal debe migrar a flujo glTF/GLB alineado con 3D Tiles 1.1
- `b3dm` queda como fallback temporal mientras se estabiliza la cadena de conversion
- el servicio publica un manifiesto interno con:
  - version del pipeline
  - hash del IFC fuente
  - fecha de generacion
  - validaciones ejecutadas
  - lista de recursos generados

### 3. Capa de metadata BIM estructurada

Responsabilidad:

- conservar propiedades BIM sin depender del motor grafico
- permitir consultas funcionales desde Odoo
- soportar filtros y relaciones de negocio

Implementacion propuesta:

- extraer metadata del IFC a tablas propias o JSON estructurado indexado
- usar `GlobalId` como llave principal de interoperabilidad
- agregar una llave tecnica interna para casos donde el `GlobalId` cambie entre versiones
- almacenar como minimo:
  - `GlobalId`
  - `IfcClass`
  - nombre
  - tipo
  - nivel/planta
  - sistema
  - disciplina
  - material
  - propiedades relevantes para negocio

## Cambios recomendados al proyecto actual

### En el modulo Odoo

- agregar un modelo de metadata de elementos BIM por version
- exponer endpoints para consultar propiedades por `GlobalId`
- soportar filtros por disciplina, nivel, clase IFC y visibilidad
- guardar resultado de validaciones del paquete visual
- separar claramente:
  - archivo IFC original
  - paquete visual publicado
  - metadata estructurada

### En el microservicio

- reemplazar la salida centrada solo en `b3dm` por un pipeline orientado a 3D Tiles 1.1
- incorporar una fase de validacion antes del callback a Odoo
- publicar recursos solo si:
  - `tileset.json` es valido
  - los recursos referenciados existen
  - las transformaciones espaciales son coherentes
  - el paquete responde dentro de tiempos aceptables
- ofrecer dos adaptadores de salida:
  - `self_hosted`
  - `managed_service`

### En el frontend del visor

El visor debe soportar como minimo:

- navegacion 3D fluida
- seleccion de elementos
- resaltado por categorias
- panel de propiedades consultado externamente
- aislamiento de disciplinas
- filtrado por niveles
- control de visibilidad por clases IFC
- base para incidencias, tareas, mediciones y comentarios

## Validaciones del paquete visual

Antes de marcar una version como `ready`, el servicio debe validar:

- presencia de `tileset.json`
- resolucion correcta de `content.uri`
- accesibilidad HTTP de todos los recursos publicados
- existencia de transformaciones espaciales validas
- coherencia del sistema de coordenadas
- carga inicial dentro de umbrales configurables
- consistencia entre elementos visibles y metadata indexada

Resultado sugerido:

- `ready`
- `ready_with_warnings`
- `error`

## Modalidades operativas

### Modalidad autohospedada

Uso recomendado:

- infraestructura propia
- mayor control de seguridad
- integracion directa con Odoo y almacenamiento local

### Modalidad gestionada

Uso recomendado:

- cuando se quiera delegar optimizacion y hosting del paquete 3D
- integracion tipo proveedor externo, similar a Cesium ion

Requisito tecnico:

- el modulo Odoo no debe acoplarse a un proveedor concreto
- debe existir una interfaz de adaptador para proveedores de conversion/publicacion

## Hoja de ruta sugerida

### Fase 1: estabilizacion del flujo actual

- estabilizar conversion y despliegue del microservicio
- consolidar visor Cesium embebido
- mantener `b3dm` solo para pruebas controladas

Criterio de salida:

- un IFC subido desde Odoo puede convertirse y visualizarse de punta a punta

### Fase 2: separacion formal de metadata

- extraer metadata BIM del IFC
- persistir por `GlobalId`
- consultar propiedades desde el panel del visor

Criterio de salida:

- al seleccionar un elemento, el visor obtiene propiedades desde Odoo o API asociada

### Fase 3: migracion del paquete visual

- evolucionar a flujo principal basado en glTF/GLB y 3D Tiles 1.1
- dejar `b3dm` como fallback o compatibilidad

Criterio de salida:

- el paquete visual publicado no depende de un formato legado como via principal

### Fase 4: filtros BIM y funciones ERP

- filtros por niveles, disciplinas, clases y estados
- integracion con tareas, incidencias, mantenimiento y presupuesto

Criterio de salida:

- el visor sirve como componente funcional del ERP, no solo como renderizador

### Fase 5: federacion y validaciones avanzadas

- multiples modelos por proyecto
- comparacion entre versiones
- validacion automatica mas estricta
- trazabilidad completa del paquete visual

## Decision tecnica recomendada

Adoptar esta propuesta como arquitectura objetivo del proyecto.

En la practica:

- mantener el IFC como fuente maestra
- separar visualizacion y metadata BIM
- migrar el pipeline hacia 3D Tiles 1.1 con glTF/GLB como objetivo principal
- conservar `b3dm` unicamente como compatibilidad temporal
- usar Odoo como capa de negocio, permisos, historial y consulta de propiedades

## Referencias oficiales

- Cesium downloads: https://cesium.com/downloads/
- CesiumJS quickstart 1.139.1: https://cesium.com/learn/cesiumjs-learn/cesiumjs-quickstart/
- OGC 3D Tiles Specification: https://docs.ogc.org/cs/22-025r4/22-025r4.html
- OGC 3D Tiles PDF: https://docs.ogc.org/cs/22-025r4/22-025r4.pdf
