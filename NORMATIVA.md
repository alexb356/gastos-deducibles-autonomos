# Normativa fiscal — Gastos deducibles para autónomos (IRPF/IVA) — fuentes y criterios

## Principio general (Art. 30 LIRPF y art. 95 Ley IVA)
Para que un gasto sea deducible debe cumplir 3 requisitos (fuente: fiscalitiasesores.com, right-now.es, infoautonomos):
1. **Vinculación con la actividad económica** (necesario para obtener los ingresos).
2. **Justificación documental**: factura completa con NIF, no basta un simple recibo/ticket sin datos fiscales.
3. **Registro contable**: anotado en el libro de gastos/inversiones correspondiente.

## Gastos deducibles al 100% (criterio general)
- Cuota de autónomos (RETA).
- Alquiler de local/oficina exclusivamente profesional.
- Suministros del local si es de uso exclusivo profesional.
- Compras de mercancías/materias primas consumidas en el ejercicio.
- Sueldos y Seguridad Social de empleados.
- Servicios profesionales (gestoría, asesoría legal, subcontratas).

## Vivienda habitual usada parcialmente para la actividad (Art. 30 LIRPF)
- **Suministros (luz, agua, gas, internet)**: fórmula legal = importe factura × (m² afectados / m² totales) × 30%.
- **Alquiler/IBI/comunidad**: proporcional a los m² afectados declarados en el modelo 036/037 (100% de la parte proporcional si el espacio es de uso exclusivo).

## Vehículo (criterio distinto en IRPF vs IVA — fuente: cuentica.com, infoautonomos, centregestor.es)
- **IRPF**: solo deducible si hay **afectación exclusiva al 100%** (no cabe afectación parcial: es un bien indivisible). Se presume afectación al 100% solo en vehículos mixtos/industriales cuya naturaleza de uso profesional quede acreditada (taxis, autoescuelas, transportistas, repartidores, comerciales con desplazamiento constante, vehículos de alquiler). Para el resto de autónomos, en general **NO deducible en IRPF**.
- **IVA**: se presume deducible al **50%** salvo prueba de mayor afectación (100% en actividades de transporte/autoescuela con afectación exclusiva demostrada).
- Gastos asociados (combustible, seguro, reparaciones, ITV, peajes, parking) siguen la misma regla que la deducción del vehículo.

## Gastos de manutención/dietas (fuente: infoautonomos)
- Deducibles cuando: (a) se producen en el desarrollo de la actividad, (b) en municipio distinto al de residencia habitual, (c) en establecimientos de restauración/hostelería, (d) pagados por medios electrónicos (no efectivo) y con justificante.
- **Límites diarios**: 26,67 €/día en España (sin pernoctar) — 48,08 €/día en el extranjero (sin pernoctar). Con pernocta los límites son mayores (no cuantificados aquí con la misma certeza — **duda a revisar por el usuario/asesor**, ya que las fuentes consultadas no detallan de forma unívoca el importe con pernocta).

## Gastos de difícil justificación (estimación directa simplificada)
- Deducción automática del **5% del rendimiento neto previo**, con un máximo de **2.000 €/año**, sin necesidad de factura específica. Sustituye gastos menores no documentados.

## Teléfono móvil, software, formación, marketing
- Deducibles si vinculados a la actividad; el móvil solo la parte proporcional de uso profesional si es de uso mixto (o 100% si hay una línea exclusivamente profesional).

## Decisiones de diseño para el MVP (a revisar por el usuario)
- El clasificador aplica las reglas generales anteriores mediante coincidencia de categoría/palabra clave sobre la descripción del movimiento bancario o del texto extraído del ticket, y devuelve: `deducible` (sí/no/parcial), `porcentaje estimado`, y **la norma que lo justifica** (texto corto).
- **No sustituye el criterio de un asesor fiscal**: casos límite (vehículos, dietas con pernocta, gastos mixtos) requieren revisión humana — se marcan explícitamente como "requiere revisión" en vez de decidir con falsa seguridad.
- **[DUDA A REVISAR POR EL USUARIO]**: los importes exactos de dietas con pernocta y algunos supuestos de vehículos "mixtos/industriales" tienen matices que varían según inspección y jurisprudencia; el MVP usa los criterios generales más citados por fuentes fiscales pero recomienda confirmación con un asesor antes de presentar el modelo 130/303/100.
- OCR de tickets: implementado de forma opcional vía `pytesseract`, que requiere el binario **Tesseract OCR** instalado en el sistema (no incluido, no se pudo instalar automáticamente por requerir permisos de administrador vía instalador gráfico). El flujo principal y siempre disponible es la **subida de CSV de movimientos bancarios**, que no depende de OCR.
