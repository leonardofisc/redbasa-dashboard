#!/usr/bin/env python3
"""
Red Basa · Análisis diario de calidad
Corre a las 4am via GitHub Actions
Lee todas las planillas → analiza con Claude → escribe resultados en Google Sheet
"""

import os
import json
import csv
import io
import time
import datetime
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── CONFIG ─────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ['ANTHROPIC_API_KEY']
GOOGLE_CREDENTIALS = json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT'])

CONFIG_PATH     = 'config/sanatorios.json'
RESULTS_SHEET   = os.environ.get('RESULTS_SHEET_ID', '')

# Columnas de encuesta (iguales en todas las planillas de Red Basa)
COL_REC     = '¿Qué probabilidad hay de que nos recomiendes a un amigo o familiar?'
COL_COMMENT = 'Aquí puede escribir cualquier sugerencia, felicitación o reclamo sobre tu experiencia en nuestro centro de atención:'
COL_DATE    = 'Marca temporal'
COL_STARS   = '¿Cuántas estrellas le darías a la clínica?  Siendo 1 la calificación más baja y 5 la calificación más alta.'

TODAY     = datetime.date.today()
TODAY_STR = TODAY.strftime('%Y-%m-%d')
MONTH_STR = TODAY.strftime('%Y-%m')
PREV_MONTH = (TODAY.replace(day=1) - datetime.timedelta(days=1)).strftime('%Y-%m')

# ── GOOGLE SHEETS ─────────────────────────────────────────────────
def get_sheets_service():
    creds = service_account.Credentials.from_service_account_info(
        GOOGLE_CREDENTIALS,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return build('sheets', 'v4', credentials=creds)

def fetch_sheet_csv(sheet_id, gid='0'):
    """Fetch sheet as CSV via public export URL"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))

def write_results(service, sheet_id, results):
    """Write analysis results to the results sheet"""
    headers = [
        'sanatorio_id', 'sanatorio_nombre', 'fecha_analisis',
        'nps_general', 'n_general',
        'nps_swiss', 'n_swiss',
        'nps_osde', 'n_osde',
        'nps_swiss_mes_actual', 'nps_swiss_mes_anterior',
        'resumen', 'problemas', 'tags',
        'nuevos_comentarios_negativos'
    ]
    # Read existing rows to check if update or insert
    try:
        existing = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range='A:A'
        ).execute().get('values', [])
        existing_ids = [r[0] for r in existing[1:]] if len(existing) > 1 else []
    except:
        existing_ids = []

    for result in results:
        row = [
            result.get('sanatorio_id', ''),
            result.get('sanatorio_nombre', ''),
            TODAY_STR,
            str(result.get('nps_general', '')),
            str(result.get('n_general', '')),
            str(result.get('nps_swiss', '')),
            str(result.get('n_swiss', '')),
            str(result.get('nps_osde', '')),
            str(result.get('n_osde', '')),
            str(result.get('nps_swiss_mes_actual', '')),
            str(result.get('nps_swiss_mes_anterior', '')),
            result.get('resumen', ''),
            json.dumps(result.get('problemas', []), ensure_ascii=False),
            ','.join(result.get('tags', [])),
            result.get('nuevos_comentarios_negativos', ''),
        ]

        if result['sanatorio_id'] in existing_ids:
            # Update existing row
            row_idx = existing_ids.index(result['sanatorio_id']) + 2  # +2 for header
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f'A{row_idx}',
                valueInputOption='RAW',
                body={'values': [row]}
            ).execute()
        else:
            # Append new row
            service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range='A1',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row] if existing_ids else [headers, row]}
            ).execute()

# ── NPS CALC ──────────────────────────────────────────────────────
def calc_nps(rows, obra_filter=None, obra_col=None):
    filtered = rows
    if obra_filter and obra_col:
        filtered = [r for r in rows
                    if obra_filter.lower() in (r.get(obra_col, '') or '').lower()]
    recs = []
    for r in filtered:
        try:
            v = float(r.get(COL_REC, ''))
            if 0 <= v <= 10:
                recs.append(v)
        except (ValueError, TypeError):
            pass
    if not recs:
        return {'nps': None, 'n': 0}
    p = sum(1 for v in recs if v >= 9) / len(recs) * 100
    d = sum(1 for v in recs if v <= 6) / len(recs) * 100
    return {'nps': round(p - d), 'n': len(recs)}

def get_month_rows(rows, month_str, obra_filter=None, obra_col=None):
    """Filter rows by month (YYYY-MM)"""
    result = []
    for r in rows:
        date_str = r.get(COL_DATE, '')
        if not date_str:
            continue
        # Parse DD/MM/YYYY HH:MM:SS
        parts = date_str.replace('/', ' ').replace(':', ' ').split()
        if len(parts) >= 3:
            try:
                d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                row_month = f"{y:04d}-{m:02d}"
                if row_month == month_str:
                    if obra_filter and obra_col:
                        if obra_filter.lower() in (r.get(obra_col, '') or '').lower():
                            result.append(r)
                    else:
                        result.append(r)
            except (ValueError, IndexError):
                pass
    return result

def get_new_rows_since_yesterday(rows, obra_filter=None, obra_col=None):
    """Get rows added in the last 24 hours"""
    yesterday = TODAY - datetime.timedelta(days=1)
    result = []
    for r in rows:
        date_str = r.get(COL_DATE, '')
        if not date_str:
            continue
        parts = date_str.replace('/', ' ').replace(':', ' ').split()
        if len(parts) >= 3:
            try:
                d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                row_date = datetime.date(y, m, d)
                if row_date >= yesterday:
                    if obra_filter and obra_col:
                        if obra_filter.lower() in (r.get(obra_col, '') or '').lower():
                            result.append(r)
                    else:
                        result.append(r)
            except (ValueError, IndexError):
                pass
    return result

# ── CLAUDE ANALYSIS ───────────────────────────────────────────────
def analyze_with_claude(sanatorio_name, negative_comments, new_count):
    """Call Claude API to analyze comments and generate structured summary"""
    if not negative_comments:
        return {
            'resumen': 'Sin comentarios negativos nuevos en el período analizado.',
            'problemas': [],
            'tags': ['Sin incidencias'],
        }

    comments_text = '\n\n'.join([
        f"[{i+1}] rec={c.get('rec','?')}/10 | {c.get('fecha','?')}\n\"{c.get('texto','')}\""
        for i, c in enumerate(negative_comments[:30])  # max 30
    ])

    prompt = f"""Analizá estos comentarios negativos de pacientes del {sanatorio_name}.

{comments_text}

Respondé SOLO en JSON válido sin texto extra ni markdown:
{{
  "resumen": "2 oraciones ejecutivas sobre los principales problemas",
  "problemas": [
    {{"tema": "string corto", "descripcion": "1 oración", "severidad": "critico|alto|moderado", "menciones": number}}
  ],
  "tags": ["tag1", "tag2", "tag3"]
}}

Ordená problemas por menciones descendente. Máximo 5 problemas. Tags: máximo 3, palabras clave del problema principal."""

    headers = {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01'
    }
    body = {
        'model': 'claude-sonnet-4-20250514',
        'max_tokens': 800,
        'messages': [{'role': 'user', 'content': prompt}]
    }

    try:
        r = requests.post('https://api.anthropic.com/v1/messages',
                          headers=headers, json=body, timeout=60)
        r.raise_for_status()
        text = r.json()['content'][0]['text']
        text = text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        print(f"  ⚠ Claude API error: {e}")
        return {
            'resumen': f'Error al analizar comentarios: {str(e)[:100]}',
            'problemas': [],
            'tags': [],
        }

# ── MAIN ──────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print(f"Red Basa · Análisis diario · {TODAY_STR}")
    print(f"{'='*60}\n")

    # Load config
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    sanatorios = config.get('sanatorios', [])
    results_sheet = RESULTS_SHEET or config.get('results_sheet_id', '')

    if not results_sheet or results_sheet == 'COMPLETAR_DESPUES_DE_CREAR_SHEET':
        print("⚠ RESULTS_SHEET_ID no configurado. Configurá el ID de la hoja de resultados.")
        return

    print(f"📋 Procesando {len(sanatorios)} sanatorios...\n")

    sheets_service = get_sheets_service()
    all_results = []

    for san in sanatorios:
        if not san.get('active', True):
            print(f"  ⏭ {san['name']} (inactivo)")
            continue

        print(f"  🏥 {san['name']}...")

        try:
            rows = fetch_sheet_csv(san['sheetId'], san.get('gid', '0'))
            obra_col = san.get('obraCol', 'Obra social:')

            # NPS calculations
            total = calc_nps(rows)
            swiss = calc_nps(rows, 'swiss', obra_col)
            osde  = calc_nps(rows, 'osde',  obra_col)

            # Monthly NPS
            curr_month_rows = get_month_rows(rows, MONTH_STR, 'swiss', obra_col)
            prev_month_rows = get_month_rows(rows, PREV_MONTH, 'swiss', obra_col)
            nps_curr = calc_nps(curr_month_rows)
            nps_prev = calc_nps(prev_month_rows)

            # New comments since yesterday (negative)
            new_rows = get_new_rows_since_yesterday(rows, 'swiss', obra_col)
            new_neg = [r for r in new_rows
                       if r.get(COL_COMMENT, '').strip()
                       and float(r.get(COL_REC, '5') or '5') <= 6]

            comments_for_analysis = [
                {
                    'texto': r.get(COL_COMMENT, ''),
                    'rec': r.get(COL_REC, ''),
                    'fecha': r.get(COL_DATE, '')[:10],
                }
                for r in new_neg
            ]

            # Use last 30 days if no new comments today
            if not comments_for_analysis:
                cutoff = TODAY - datetime.timedelta(days=30)
                recent_neg = []
                for r in rows:
                    try:
                        parts = r.get(COL_DATE, '').replace('/', ' ').replace(':', ' ').split()
                        if len(parts) >= 3:
                            row_date = datetime.date(int(parts[2]), int(parts[1]), int(parts[0]))
                            if row_date >= cutoff:
                                rec = float(r.get(COL_REC, '5') or '5')
                                if rec <= 6 and r.get(COL_COMMENT, '').strip():
                                    obra = (r.get(obra_col, '') or '').lower()
                                    if 'swiss' in obra:
                                        recent_neg.append({
                                            'texto': r.get(COL_COMMENT, ''),
                                            'rec': r.get(COL_REC, ''),
                                            'fecha': r.get(COL_DATE, '')[:10],
                                        })
                    except:
                        pass
                comments_for_analysis = recent_neg[-20:]

            # Analyze with Claude
            print(f"     → {len(rows)} filas · Swiss n={swiss['n']} · {len(comments_for_analysis)} comentarios a analizar")
            ai = analyze_with_claude(san['name'], comments_for_analysis, len(new_neg))
            time.sleep(1)  # Rate limit

            result = {
                'sanatorio_id':            san['id'],
                'sanatorio_nombre':        san['name'],
                'nps_general':             total['nps'],
                'n_general':               total['n'],
                'nps_swiss':               swiss['nps'],
                'n_swiss':                 swiss['n'],
                'nps_osde':                osde['nps'],
                'n_osde':                  osde['n'],
                'nps_swiss_mes_actual':    nps_curr['nps'],
                'nps_swiss_mes_anterior':  nps_prev['nps'],
                'resumen':                 ai.get('resumen', ''),
                'problemas':               ai.get('problemas', []),
                'tags':                    ai.get('tags', []),
                'nuevos_comentarios_negativos': str(len(new_neg)),
            }
            all_results.append(result)

            nps_str = f"NPS Swiss: {swiss['nps']:+d}" if swiss['nps'] is not None else "NPS Swiss: —"
            print(f"     ✓ {nps_str} · {ai.get('resumen','')[:80]}…\n")

        except Exception as e:
            print(f"     ✗ Error: {e}\n")
            all_results.append({
                'sanatorio_id':   san['id'],
                'sanatorio_nombre': san['name'],
                'nps_general': '', 'n_general': '',
                'nps_swiss': '', 'n_swiss': '',
                'nps_osde': '', 'n_osde': '',
                'nps_swiss_mes_actual': '', 'nps_swiss_mes_anterior': '',
                'resumen': f'Error al cargar datos: {str(e)[:200]}',
                'problemas': [], 'tags': ['Error'],
                'nuevos_comentarios_negativos': '0',
            })

    # Write to results sheet
    print(f"📝 Escribiendo resultados en Google Sheets…")
    try:
        write_results(sheets_service, results_sheet, all_results)
        print(f"✓ Resultados actualizados en {results_sheet}\n")
    except Exception as e:
        print(f"✗ Error escribiendo resultados: {e}\n")

    print(f"{'='*60}")
    print(f"Análisis completado · {len(all_results)} sanatorios procesados")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()
