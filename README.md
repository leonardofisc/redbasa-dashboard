# Red Basa · Tablero de Calidad de Atención

Tablero ejecutivo en tiempo real para monitorear el NPS de pacientes Swiss Medical en la red de sanatorios de Red Basa. Se actualiza automáticamente cada noche a las 4am con análisis IA de comentarios.

---

## Arquitectura

```
Google Sheets (20 sanatorios)
       ↓  lectura directa en el browser
   index.html  ←──  GitHub Pages (URL pública)
       ↑  resultados del análisis
  Google Sheet "Resultados"
       ↑  escribe cada noche
   scripts/analyze.py
       ↑  dispara a las 4am (UTC-3)
   GitHub Actions
```

---

## Setup paso a paso

### 1. Crear el repositorio en GitHub

```bash
git init redbasa-dashboard
cd redbasa-dashboard
# Copiar todos los archivos de este proyecto
git add .
git commit -m "Initial setup"
git remote add origin https://github.com/TU_ORG/redbasa-dashboard.git
git push -u origin main
```

### 2. Habilitar GitHub Pages

1. Ir a **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / `/ (root)`
4. Guardar → en ~1 minuto el tablero estará en `https://TU_ORG.github.io/redbasa-dashboard`

### 3. Crear la hoja de resultados en Google Sheets

1. Crear una nueva Google Sheet: **"Red Basa · Resultados de Análisis"**
2. Copiar el ID de la URL: `docs.google.com/spreadsheets/d/**ID_AQUÍ**/edit`
3. Guardarlo para el paso 5

### 4. Crear cuenta de servicio de Google

1. Ir a [console.cloud.google.com](https://console.cloud.google.com)
2. Crear proyecto o usar uno existente
3. Activar **Google Sheets API**
4. Ir a **IAM & Admin → Service Accounts → Create**
5. Nombre: `redbasa-sheets`
6. Crear y descargar clave JSON
7. Compartir la hoja de resultados (paso 3) con el email de la cuenta de servicio

> **Nota:** Las planillas de los sanatorios deben ser **públicas** (Compartir → Cualquier persona con el enlace puede ver). La cuenta de servicio solo necesita acceso a la hoja de resultados.

### 5. Configurar secrets en GitHub

Ir a **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Valor |
|--------|-------|
| `ANTHROPIC_API_KEY` | Tu API key de Anthropic |
| `GOOGLE_SERVICE_ACCOUNT` | Contenido completo del JSON de la cuenta de servicio |
| `RESULTS_SHEET_ID` | ID de la hoja de resultados del paso 3 |

### 6. Actualizar index.html

En `index.html`, línea ~120, reemplazar:
```js
const RESULTS_SHEET_ID = 'RESULTS_SHEET_ID_HERE';
```
por el ID real de la hoja de resultados.

### 7. Actualizar config/sanatorios.json

Reemplazar `COMPLETAR_DESPUES_DE_CREAR_SHEET` por el ID de la hoja de resultados.

---

## Agregar un nuevo sanatorio

### Opción A — Desde el tablero (recomendada)

1. Abrir el tablero
2. Click en **+ Sanatorio**
3. Completar nombre, ciudad, URL de Google Sheets y columna de obra social
4. Click en **Agregar sanatorio**

Los datos quedan guardados en `localStorage` del browser. Para que persistan entre dispositivos, exportar la config con el botón de exportar y actualizar `config/sanatorios.json`.

### Opción B — Editar sanatorios.json

```json
{
  "id": "nombre-corto-sin-espacios",
  "name": "Nombre completo del sanatorio",
  "city": "Ciudad",
  "since": "2025-11",
  "sheetId": "ID_DE_GOOGLE_SHEETS",
  "gid": "213280738",
  "obraCol": "Obra social:",
  "active": true
}
```

El `obraCol` es el nombre exacto de la columna que contiene la obra social en esa planilla. Revisarlo en la primera fila de la planilla.

---

## Estructura de las planillas

Cada planilla de sanatorio debe tener estas columnas (igual al formato EP actual):

| Columna | Descripción |
|---------|-------------|
| `Marca temporal` | Fecha y hora de la encuesta (DD/MM/YYYY HH:MM:SS) |
| `¿Qué probabilidad hay de que nos recomiendes…?` | Escala 0–10 (NPS) |
| `¿Cuántas estrellas le darías a la clínica?…` | Escala 1–5 |
| `Aquí puede escribir cualquier sugerencia…` | Comentario abierto |
| `Obra social:` | Nombre de la obra social |

---

## Costos estimados

| Componente | Costo |
|------------|-------|
| GitHub Pages | $0 |
| GitHub Actions (análisis diario) | $0 (dentro del free tier) |
| Google Sheets API | $0 |
| Anthropic Claude API | ~$5–15 USD/mes (20 sanatorios, ~30 comentarios/sanatorio) |
| **Total** | **~$5–15 USD/mes** |

---

## Archivos del proyecto

```
redbasa-dashboard/
├── index.html                    # Tablero ejecutivo (GitHub Pages)
├── config/
│   └── sanatorios.json           # Configuración de los 20 sanatorios
├── scripts/
│   └── analyze.py                # Script de análisis diario con IA
├── .github/
│   └── workflows/
│       └── daily_analysis.yml    # Cron 4am + manual trigger
└── README.md
```

---

## Ejecutar el análisis manualmente

Desde GitHub: **Actions → Análisis diario → Run workflow**

O localmente:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_SERVICE_ACCOUNT='{"type":"service_account",...}'
export RESULTS_SHEET_ID="1abc..."
python scripts/analyze.py
```

---

## Soporte

Para agregar columnas adicionales de análisis o modificar los criterios de NPS, editar `scripts/analyze.py` y `index.html`.
