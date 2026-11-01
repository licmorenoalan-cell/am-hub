# Recurrencias con calendario oficial

El motor compartido por AM Hub y Pocket no calcula vencimientos fiscales sumando meses. Resuelve una entrada exacta por impuesto, obligación, jurisdicción, período fiscal y terminación de CUIT. Las tareas no fiscales conservan su comportamiento habitual.

## Datos y calendario

`data/fiscal_calendar.json` conserva cada grupo de terminaciones, fecha, norma, fuente oficial y fecha de verificación. Solo se aceptan entradas verificadas y unívocas. Contiene 68 entradas verificadas:

| Obligación | Períodos | Entradas por grupo |
|---|---|---:|
| CM03 / COMARB | octubre–diciembre 2026 | 12 |
| IIBB local general ARBA | septiembre–diciembre 2026 | 20 |
| IIBB local general AGIP | octubre 2026 (grupos 2–9), noviembre–diciembre 2026 | 14 |
| IVA | octubre–noviembre 2026 | 10 |
| Autónomos | septiembre–noviembre 2026 | 9 |
| Monotributo mensual | octubre–diciembre 2026, sin distinción por CUIT | 3 |

Cada tabla ARCA registra la URL de la agenda dinámica, consulta 01/11/2026, obligación y período exactos. No se extrapolan días a otros períodos. Fuentes provinciales: calendario ARBA 2026 página 2; Resolución AGIP 557/2025 anexo página 1. COMARB: RG CA 20/2025 para noviembre/diciembre y RG CA 11/2026 art. 3 para octubre, con procedencia explícita de la excepción que reemplaza las fechas originales. Las fechas exactas y procedencia están en cada entrada JSON.

Las tablas generales no sirven para Simplificado ni Monotributo Unificado. «Local» por sí solo no confirma régimen general: la obligación queda sin identificar. Para AGIP octubre 2026 falta confirmar únicamente la prórroga del grupo 0–1; grupos 2–9 se incorporan sin afectación.

Recategorización: RG 4309 art. 20 (texto según RG 5546/2024) establece 5 de febrero/agosto, con traslado al hábil siguiente. El 05/02/2027 es candidato normativo, **no entrada oficial verificada de calendario/feriados**, por lo que no se carga como vencimiento. Fuentes: https://biblioteca.arca.gob.ar/search/query/norma.aspx?p=t:RAG%7Cn:4309%7Co:3%7Ca:2018%7Cf:17/09/2018 y https://www.arca.gob.ar/monotributo/ayuda/recategorizacion.asp . Anticipos no se mapea a Ganancias sin identificar impuesto y número.

Las prórrogas deben reemplazar la entrada correspondiente y conservar su fuente de excepción: dos entradas para la misma clave bloquean la resolución en vez de elegir arbitrariamente.

Los períodos mensuales son `YYYY-MM`; los anuales, `YYYY`. Recategorizaciones usan el mes de la obligación y cadencia semestral. Otros impuestos/anticipos requieren identificar la obligación concreta; no se confunden con CM03 ni se deducen de una fecha suelta.

Los campos fiscales se guardan como JSON versionado `fiscal:v1:` en `id_externo`, ya existente; no se requiere migración. Se conserva un identificador externo ajeno a este formato y se bloquea la resolución hasta revisar el conflicto. La terminación se toma de la ficha fiscal del cliente o de datos históricos de la tarjeta; discrepancias y fichas duplicadas bloquean la resolución. El contexto nuevo guarda solo el último dígito, nunca el identificador completo.

Un período antiguo se recupera automáticamente únicamente de una mención explícita de la primera ocurrencia (ISO, mes/año o mes en castellano), o de configuración revisada con procedencia. Las descripciones de ocurrencias posteriores pueden ser heredadas: no confirman el período actual. La coincidencia exacta con una tabla oficial es solo una **sugerencia** en la auditoría. Para completar/corregir datos se usa `--config`: JSON por ID con `impuesto`, `obligacion`, `jurisdiccion`, `periodo`, `terminacion` y opcional `periodo_fuente`.

## Sin datos o calendario

Si el período origen está confirmado, la siguiente ocurrencia sin calendario queda Pendiente, sin fecha, con comentario explicativo y etiqueta visible que distingue «Calendario fiscal pendiente» de «Datos fiscales por revisar». Su período fiscal se conserva/avanza aunque falte la terminación. Si no se conoce el período origen o la frecuencia es inválida, se bloquea la transición: no se genera una ocurrencia sin período o repitiendo el período anterior. Las nuevas recurrencias creadas desde el formulario/grilla tampoco aceptan una fecha inicial arbitraria. No se permite finalizar una tarea pendiente de validación. Tampoco basta con escribir una fecha manual sobre una tarjeta configurada: debe coincidir con el calendario.

La generación y el cambio de estado se ejecutan en una misma transacción con bloqueo de la tarea origen. La serie y la ocurrencia impiden repetir una generación al reintentar o reabrir/finalizar. La edición detallada de Pocket usa esa misma transacción. Las grillas de Hub conservan en el conjunto guardado las nuevas ocurrencias para que un guardado completo no las borre. El modo CSV reutiliza el constructor fiscal; no ofrece garantías de concurrencia entre procesos.

## Activación (no ejecutada)

1. Revisar e integrar el cambio con la última versión del repositorio. Esta copia aislada parte de `a525904ac01088e2ab70ca3e45d8ec68ec2ce9cc`; no sobrescribir el trabajo activo.
2. Completar las fuentes y los datos que estén confirmados. Mantener lo demás sin fecha. Completar los períodos y regímenes faltantes; confirmar recategorización 2027 y la excepción AGIP 0–1 octubre; identificar el impuesto y número de los anticipos. Las tablas disponibles se detallan arriba. No se cargaron fechas sin verificar del motor anterior.
3. Tras autorización de publicación, desplegar **ambos** puntos de entrada, `app.py` y `pocket_app.py`, con el nuevo módulo y JSON. No activar recurrencias mientras alguno siga con el motor anterior.
4. En el entorno operativo que ya tiene la conexión configurada, ejecutar `python scripts/audit_fiscal_recurrences.py --report /ruta/privada/plan.json`. Es solo lectura. El informe contiene IDs, campos y motivos; no nombres ni CUIT completos.
5. Para una activación puntual aprobada, añadir `--config /ruta/privada/contexto.json --activate /ruta/privada/activacion.json`. La activación admite únicamente título y descripción; usa recurrencia mensual. No crea clientes ni perfiles fiscales.
6. Revisar el plan. Después del despliegue agregar `--apply --deployed-engine fiscal-v1`. Se modifican solo campos distintos de tarjetas no finalizadas, en una transacción; se vuelven a consultar después del commit para verificar idempotencia. El script no publica ni verifica por sí solo la versión remota: el operador debe confirmar primero ambos despliegues.
7. Abrir Hub y Pocket, comprobar las tarjetas sin fecha y la primera fecha de la activación. Los informes y configuraciones de producción deben permanecer fuera del repositorio público.

No hay cambios de datos de producción en esta implementación. La auditoría revisada de 01/11/2026 abarca 57 recurrencias existentes: 3 resueltas con período y fecha oficial y 54 con datos faltantes; ninguna queda pendiente exclusivamente de calendario. Las recategorizaciones aún requieren datos y un calendario confirmado. Se agrega una activación individual verificada. El plan propone una sola corrección de fecha, sin borrar ninguna. Cuando no puede resolverse una tarjeta legada, conserva su fecha exacta, marca revisión y muestra «fecha previa sin verificar». Hay 16 coincidencias de tabla sugeridas, no confirmadas. Las 12 recategorizaciones también carecen de calendario oficial confirmado, aunque primero necesitan confirmar el período. Los históricos finalizados se excluyen.

## Validación y límites

La suite cubre grupos de terminaciones, cambios de año, períodos anuales, jurisdicciones, datos faltantes/contradictorios, calendario ausente/ambiguo/no verificado, conservación de IDs externos, no exposición de identificadores completos en metadatos, historial intacto, replay/reapertura sin duplicados y rutas de edición de Pocket/grillas de Hub. Persistencia probada con SQLite y adaptador del bloqueo PostgreSQL; no es una prueba de concurrencia real sobre PostgreSQL. No se ejecutaron pruebas de escritura ni despliegue en producción, ni comprobación visual de la versión nueva en el navegador.

Revisión final: pruebas transaccionales de plan aplicado dos veces verifican idempotencia, preservación de filas finalizadas y de fechas/notas legadas. La activación individual funciona con el último dígito únicamente. Única corrección propuesta: IVA, período octubre 2026, de 19/11 a 20/11/2026; todavía no aplicada.
