# RESUMEN — Proyecto 3: Detector de gastos deducibles para autónomos

## Qué se ha construido
MVP Flask + SQLite + frontend simple:
- **Subida de CSV de movimientos bancarios** (fecha, concepto/descripción, importe): detección automática de columnas por nombre, filtrado de solo gastos (importes negativos).
- **Motor de reglas de clasificación** (ver NORMATIVA.md) que marca cada gasto como: deducible 100%, no deducible, parcial (con % estimado) o "requiere revisión manual" — siempre con **la norma que lo justifica** en texto.
- **Resumen agregado**: total gastado, total deducible estimado, nº de movimientos pendientes de revisión manual.
- **Exportación a CSV** del detalle clasificado.
- **OCR opcional de tickets** vía `pytesseract` — requiere que el usuario final tenga instalado el binario Tesseract OCR en su máquina/servidor; si no está disponible, el endpoint devuelve un error controlado (no rompe la app) y el flujo principal (CSV) sigue funcionando sin depender de esto.
- Stripe en modo TEST para la suscripción del SaaS.
- 11 tests automatizados, todos pasan: clasificación por reglas (RETA, vehículo, gasto personal, desconocido), subida de CSV (filtra ingresos, valida extensión y presencia de archivo), resumen, exportación, endpoint OCR con fallo controlado, flujo de suscripción Stripe test.

## Decisiones de negocio/normativas tomadas y por qué
1. El motor de clasificación usa **reglas por palabras clave** sobre la descripción del movimiento (no un modelo de IA/ML) — es determinista, explicable y barato de mantener, adecuado para un MVP a coste cero. Está basado en los criterios generales de deducibilidad de IRPF/IVA para autónomos: vinculación a la actividad, factura con NIF, registro contable (Art. 30 LIRPF, Art. 95 Ley IVA).
2. Para casos legalmente ambiguos (vehículo, dietas con pernocta, gastos mixtos), el sistema **no decide con falsa seguridad**: marca "parcial" con el % general de mercado (p.ej. 50% IVA vehículo) o "revisar" cuando la norma exige comprobar contexto (dietas: municipio distinto, pago electrónico, justificante).
3. Tesseract OCR no se pudo instalar automáticamente en este entorno (el instalador de Windows requiere una confirmación interactiva de administrador que no pude completar sin bloquear la tarea) — se ha dejado como **funcionalidad opcional y desacoplada**, documentada, sin bloquear el resto del producto.

## Qué debe hacer el usuario para pasar a producción
- Cuenta Stripe real, sustituir claves de `.env`.
- Si se quiere ofrecer OCR de tickets: instalar Tesseract OCR (o usar un servicio de OCR en la nube de pago, decisión de negocio pendiente) y configurar `TESSERACT_CMD`.
- Revisión por un asesor fiscal antes de vender el clasificador como fuente definitiva: el motor de reglas cubre los casos más comunes pero **no sustituye asesoramiento profesional**, especialmente en vehículos con afectación parcial, dietas con pernocta, y gastos mixtos vivienda/actividad.
- Ampliar el catálogo de reglas con más categorías y sinónimos según feedback real de usuarios.
- Dominio y hosting propios; migrar a base de datos más robusta si hay varios usuarios.
- Añadir autenticación/multi-tenant (hoy el MVP no separa usuarios).

## Riesgos / dudas a revisar
- **[DUDA NORMATIVA]** Los límites de dietas con pernocta no se han podido confirmar con la misma certeza que los de "sin pernocta" (26,67€/48,08€) en las fuentes consultadas — recomiendo que un asesor fiscal confirme esos importes antes de mostrarlos como criterio definitivo.
- El motor de reglas puede generar **falsos positivos/negativos** en descripciones ambiguas (ej. "GASOLINERA" en la descripción de un ticket de la propia tienda de conveniencia, no de combustible). Se recomienda seguir marcando como "revisar" cualquier caso donde el usuario no esté seguro, en vez de forzar una respuesta.
- El clasificador no verifica que el gasto tenga realmente una factura con NIF asociada (requisito legal) — eso queda fuera del alcance del MVP y debe ser responsabilidad del usuario final.

## Revisión de bugs post-entrega (07/09/2026)
Se hizo una pasada de QA sobre el código antes de publicarlo. **Se encontró y corrigió un bug funcional real**: los extractos bancarios españoles suelen usar coma como separador decimal (ej. `-45,30 €`); si el CSV también usaba coma como delimitador de columnas, el importe se truncaba silenciosamente a `-45` (perdiendo los decimales) sin ningún aviso al usuario — esto habría dado totales deducibles incorrectos. Se añadió detección automática de delimitador (`csv.Sniffer`, soporta `,` y `;`) y reconstrucción del importe cuando el decimal en coma coincide con el delimitador de columnas. Se añadieron 3 tests de regresión. También se corrigió una vulnerabilidad de **HTML injection**: la descripción del movimiento bancario (dato externo, viene del CSV que sube el usuario) se insertaba sin escapar en el panel vía `innerHTML` — corregido con `escapeHtml()`.

## Auditoría de pentest (07/09/2026) — hallazgos y correcciones

| # | Hallazgo | Severidad | Corrección |
|---|----------|-----------|------------|
| 1 | **Fuga masiva de datos financieros entre usuarios (falta de aislamiento multi-tenant)**: `GET /api/movimientos`, `/resumen` y `/exportar.csv` sin el parámetro `lote` devolvían **todos los movimientos bancarios de todos los usuarios** que hubieran subido un CSV, sin autenticación. Cualquiera podía descargar el histórico financiero completo de todos los clientes del SaaS con una simple petición. | 🔴 Crítica | El parámetro `lote` ahora es **obligatorio** en los tres endpoints; sin él, se rechaza con 400 en vez de devolver todo. |
| 2 | **Colisión de identificadores de lote** (encontrado por el propio test de regresión del hallazgo anterior): el `lote` se generaba solo con resolución de segundos (`lote-YYYYMMDDHHMMSS`); si dos usuarios subían un CSV en el mismo segundo, ambos caían en el mismo lote y sus movimientos se mezclaban — reintroducía la fuga de datos por otra vía. | 🔴 Crítica | El lote ahora incluye un sufijo aleatorio único (`uuid4().hex[:12]`), eliminando la posibilidad de colisión. |
| 3 | **CSV/Formula Injection (CWE-1236)**: la descripción del movimiento (texto libre del CSV subido por el usuario) se volcaba sin sanitizar en la exportación. Un extracto con una descripción como `=cmd|'/c calc'!A1` se ejecutaría como fórmula al abrir el CSV exportado en Excel/Sheets. | 🟠 Alta | Nueva función `_sanitizar_celda_csv()`: si una celda empieza por `=`, `+`, `-`, `@`, tabulador o retorno de carro, se le antepone un apóstrofo para forzar texto plano. |
| 4 | **Decompression bomb en OCR**: `Image.open()` sobre una foto de ticket subida por el usuario, sin límite de dimensiones tras decodificar — una imagen pequeña en disco con dimensiones declaradas absurdas podría agotar memoria. | 🟡 Media | Verificación de integridad (`img.verify()`) + límite explícito de ~40 megapíxeles tras abrir la imagen. |
| 5 | **DoS / debug expuesto** (mismo patrón transversal). | 🟡 Media | `debug` controlado por `FLASK_DEBUG`; `MAX_CONTENT_LENGTH` 8MB (admite CSV/fotos); cabeceras de seguridad estándar. |

8 tests nuevos de regresión (aislamiento por lote entre "usuarios" simulados, rechazo sin lote en los 3 endpoints, sanitización de fórmula CSV verificada carácter a carácter). Total: 19/19 tests pasan.
