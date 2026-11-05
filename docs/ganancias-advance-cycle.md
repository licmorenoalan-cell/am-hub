# Ciclo de anticipos de Ganancias PH

Cambio preparado el 04/11/2026; no publicado. Las 13 tarjetas existentes mantienen
IDs y series. El motor reconoce GANANCIAS / ANTICIPO_PH y usa la clave de mes de
vencimiento YYYY-MM, distinta del ejercicio fiscal mostrado en la etiqueta.

Secuencia: agosto, octubre, diciembre, febrero, abril; abril pasa a agosto.
Excepción primer anticipo 2026: septiembre (RG 5876/5890), luego octubre.
Cada ejercicio tiene cinco ocurrencias; junio no es válido. La frecuencia
almacenada Mensual/intervalo 2 conserva compatibilidad de formulario, pero esta
obligación usa la secuencia fiscal específica. Otros impuestos no cambian.
Los CUIT societarios nunca aportan una terminación a anticipos PH.

Se agregan seis filas de calendario normativo, no agenda 2027 confirmada:
cuarto anticipo ejercicio 2026: 15/16/17 febrero 2027; quinto: 13/14/15 abril.
Grupos 0–3/4–6/7–9. Fuente RG 5211 arts. 2,4,5 vigente:
https://biblioteca.arca.gob.ar/search/query/norma.aspx?p=t:RAG%7Cn:5211%7Co:3%7Ca:2022%7Cf:24/06/2022
El tipo norma_vigente_fecha_derivada se muestra con aviso de futuras prórrogas
/ inhábiles. No se generan fechas perpetuas. Diciembre 2026 NO tiene fila por
contradicción oficial. Agosto 2027 NO tiene fecha: la siguiente ocurrencia queda
pendiente. La excepción septiembre proviene de RG5890 art2 (24/09/2026), sin
cargar un plazo de primer anticipo porque no hace falta para las tareas nuevas.

Antes de habilitar: integrar sin pisar cambios concurrentes, publicar motor y
calendario en AM Hub y Pocket y verificar versiones; aplicar por ID el plan
privado post-deploy-description-plan.json con precondiciones. Ese plan solo
normaliza textos heredables y checklist: no habilita fechas ni cambia estados.
No ejecutar el auditor global ni recrear tarjetas. Aun publicado, el anticipo3
permanece bloqueado hasta resolver su fecha; la cobertura de cuarto/quinto está
preparada y probada, no habilita cerrar tercero por inferencia. No finalizar
para forzar la generación futura. Para habilitación del tercero se requiere
fuente oficial unívoca; Nico/Socios también requieren persona y terminación.

Verificación local: 117 tests unittest, 1 omitido por dependencia opcional.
Incluye 12 ejercicios sin junio, excepción 2026, grupos cuarto/quinto, diciembre
bloqueado aun con fecha manual, CUIT societario excluido, label ejercicio/anticipo,
transacción de cuarto→quinto→agosto, replay/reapertura sin duplicados y preservación
de 113 filas finalizadas y CM03 de control. SQLite adapta FOR UPDATE: no simula
concurrencia real PostgreSQL. Read-back real de producción verifica los 113 hashes
históricos, CM03 Alan y 13 anticipos únicos bloqueados en el motor publicado.

Actualización 05/11/2026: agenda oficial ARCA (actualizada 03/11) consultada para
01–31 diciembre, Ganancias PH / RG5211, tercer anticipo2026: 14/15/16 diciembre
según grupos0–3/4–6/7–9. Se agregan tres entradas expresas que sustituyen el
bloqueo de diciembre descrito arriba; no se extrapolan fechas de agosto2027.
Fuente: https://seti.afip.gob.ar/av/ .
