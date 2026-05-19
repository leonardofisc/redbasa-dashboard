# Red Basa · Tablero de Control v3

## Arquitectura

```
analyze.py (4am)
  └─ Lee planilla consolidada (1 vez)
  └─ Pre-calcula todo: NPS, CSAT, Estrellas × período × financiador
  └─ Llama Claude API para análisis IA de comentarios negativos
  └─ Escribe hoja de resultados (~156 filas)

index.html (al abrir)
  └─ Lee hoja de resultados (~156 filas, instantáneo)
  └─ Renderiza sin procesar nada
  └─ Cambia período/reporte/filtro en memoria (sin red)
```

## Setup

### 1. Repo y GitHub Pages
```bash
git init && git add . && git commit -m "v3"
git remote add origin https://github.com/TU_ORG/redbasa-dashboard.git
git push -u origin main
```
Settings → Pages → branch `main` / root → Save

### 2. Hoja de resultados
Crear Google Sheet "Red Basa · Resultados". Copiar ID de la URL.

### 3. Cuenta de servicio Google
- console.cloud.google.com → Activar Sheets API → Service Account → Descargar JSON
- Compartir la hoja de resultados con el email de la cuenta (editor)
- Las planillas de encuesta solo necesitan ser públicas (leer)

### 4. Secrets en GitHub
Settings → Secrets → Actions:
| Secret | Valor |
|--------|-------|
| `ANTHROPIC_API_KEY` | API key Anthropic |
| `GOOGLE_SERVICE_ACCOUNT` | JSON completo cuenta de servicio |
| `RESULTS_SHEET_ID` | ID hoja de resultados |

### 5. index.html
Línea ~31: reemplazar `RESULTS_SHEET_ID_HERE` con el ID real.
Línea ~30: reemplazar `PASS_HASH` con SHA-256 de la nueva contraseña.
→ https://emn178.github.io/online-tools/sha256.html

### 6. Primer análisis
GitHub → Actions → Análisis diario → Run workflow

## Agregar centro con modelo EP
En `index.html`, constante `EP_CONFIG`:
```js
'NOMBRE CENTRO EN MAYÚSCULAS': { since: 'YYYY-MM' },
```

## Planilla consolidada
ID: `1mhUnoBaKmomr2HM3Ojr_-2Anf0deefnS4TWm0P_WLbc`

Columnas: A=fecha, C=centro, D-H=CSAT RRHH, I-K=CSAT Confort,
L=Estrellas, M=NPS, P-Q=CSAT Adicional, R=Comentario, W=Obra Social

## Costo: ~$5–15 USD/mes (solo Claude API)
