#!/usr/bin/env python3
"""
Red Basa · Análisis nocturno
Lee la planilla consolidada UNA vez, pre-calcula todo,
y escribe una hoja de resultados plana que el tablero lee directamente.

Estructura de salida (una fila por combinación centro × período × financiador):
  centro | periodo | financiador | nps | n_nps | csat_rrhh | csat_confort | csat_adic | csat_global
  | estrellas | n_estrellas | nps_prev | estrellas_prev | csat_prev
  | dist_nps (JSON) | sparkline (JSON) | resumen_ia | problemas (JSON) | tags
  | fecha_analisis
"""

import os, json, csv, io, re, datetime, urllib.request, urllib.parse, time

# ── CONFIG ────────────────────────────────────────────────────────────────
CONSOLIDATED_SHEET_ID = "1mhUnoBaKmomr2HM3Ojr_-2Anf0deefnS4TWm0P_WLbc"
RESULTS_SHEET_ID      = os.environ["RESULTS_SHEET_ID"]
ANTHROPIC_API_KEY     = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_SA             = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])

# Columnas 0-based
C_DATE  = 0;  C_CENTRO = 2
C_ADM   = 3;  C_MED    = 4;  C_ENF  = 5;  C_SEG  = 6;  C_LIMP  = 7
C_LCAL  = 8;  C_INST   = 9;  C_MENU = 10
C_STAR  = 11; C_NPS    = 12
C_ESP   = 15; C_SOL    = 16; C_CMT  = 17; C_PREP = 22

PREMIUM_NAMES = ['Swiss Medical','OSDE','Omint','Medicus','Sanidad','Accord Salud','Galeno','Jerárquico']
PREMIUM_KEYS  = [p.lower() for p in PREMIUM_NAMES] + ['swis medical','jerarquico']
MIN_N = 5

# ── UTILS ─────────────────────────────────────────────────────────────────
def fetch_csv(sheet_id, gid="0"):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    with urllib.request.urlopen(url) as r:
        return list(csv.reader(io.StringIO(r.read().decode('utf-8'))))

def parse_date(s):
    if not s: return None
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', str(s).strip())
    if m: return datetime.date(int(m[3]), int(m[2]), int(m[1]))
    return None

def today(): return datetime.date.today()

def cutoffs():
    t = today()
    def safe_month(y, m, d):
        import calendar
        last = calendar.monthrange(y, m)[1]
        return datetime.date(y, m, min(d, last))
    wk  = t - datetime.timedelta(days=7)
    mo  = safe_month(t.year if t.month>1 else t.year-1, t.month-1 if t.month>1 else 12, t.day)
    yr  = safe_month(t.year-1, t.month, t.day)
    pwk = t - datetime.timedelta(days=14)
    pmo = safe_month(t.year if t.month>2 else t.year-1, (t.month-2) if t.month>2 else (12+t.month-2), t.day)
    pyr = safe_month(t.year-2, t.month, t.day)
    return {
        'week':  (wk,  t),
        'month': (mo,  t),
        'year':  (yr,  t),
        'prev_week':  (pwk, wk),
        'prev_month': (pmo, mo),
        'prev_year':  (pyr, yr),
    }

def is_premium(p):
    if not p: return False
    pl = p.lower().strip()
    return any(k in pl for k in PREMIUM_KEYS)

def norm_prepaga(p):
    """Return canonical premium name or None."""
    if not p: return None
    pl = p.lower().strip()
    for name in PREMIUM_NAMES:
        if name.lower() in pl: return name
    if 'swis' in pl: return 'Swiss Medical'
    if 'jerarquico' in pl or 'jerárquico' in pl: return 'Jerárquico'
    return None

TEXT_MAP = {'muy bueno':5,'muy malo':1,'bueno':4,'malo':2,'regular':3}
def t2n(v):
    if not v: return None
    return TEXT_MAP.get(str(v).lower().strip())

def to_num(v):
    try: return float(str(v).replace(',','.'))
    except: return None

def invalid(v):
    if not v: return True
    s = str(v).lower().strip()
    return not s or any(x in s for x in ['no tengo','no aplica','no me corresponde','no opinion'])

def safe(r, i):
    return r[i] if i < len(r) else ''

# ── METRIC CALCS ──────────────────────────────────────────────────────────
def calc_nps(rows):
    vals = [v for r in rows for v in [to_num(safe(r,C_NPS))] if v is not None and 1<=v<=10]
    if len(vals) < MIN_N: return None, len(vals), None, None
    p = sum(1 for v in vals if v>=9) / len(vals)
    d = sum(1 for v in vals if v<=6) / len(vals)
    return round((p-d)*100), len(vals), round(p*100,1), round(d*100,1)

def calc_csat_col(rows, cols, use_text):
    vals = []
    for r in rows:
        for c in cols:
            v = safe(r,c)
            if invalid(v): continue
            n = t2n(v) if use_text else to_num(v)
            if n is not None and 1<=n<=5: vals.append(n)
    if len(vals) < MIN_N: return None
    return round(sum(vals)/len(vals), 2)

def calc_csat(rows):
    rrhh = calc_csat_col(rows, [C_ADM,C_MED,C_ENF,C_SEG,C_LIMP], True)
    conf = calc_csat_col(rows, [C_LCAL,C_INST,C_MENU], False)
    adic = calc_csat_col(rows, [C_ESP,C_SOL], True)
    parts = [v for v in [rrhh,conf,adic] if v is not None]
    glob = round(sum(parts)/len(parts),2) if parts else None
    return rrhh, conf, adic, glob

def calc_stars(rows):
    vals = [v for r in rows for v in [to_num(safe(r,C_STAR))] if v is not None and 1<=v<=5]
    if len(vals) < MIN_N: return None, len(vals)
    return round(sum(vals)/len(vals),2), len(vals)

def calc_dist(rows):
    """Distribution of NPS scores 1-10."""
    counts = {i:0 for i in range(1,11)}
    for r in rows:
        v = to_num(safe(r,C_NPS))
        if v is not None and 1<=v<=10:
            counts[int(v)] += 1
    return counts

def calc_sparkline(rows):
    """Monthly NPS/stars for last 18 months. Returns list of {m, nps, stars}."""
    t = today()
    result = []
    for i in range(17,-1,-1):
        yr  = t.year  + (t.month - 1 - i) // 12 * (1 if (t.month-1-i)>=0 else -1)
        mo  = ((t.month - 1 - i) % 12) + 1
        yr  = t.year + ((t.month - 1 - i) // 12)
        if t.month - 1 - i < 0:
            yr = t.year - (-(t.month - 1 - i) + 11) // 12
            mo = 12 - (-(t.month - 1 - i) - 1) % 12
        label = f"{yr}-{mo:02d}"
        mrows = [r for r in rows if parse_date(safe(r,C_DATE)) and
                 parse_date(safe(r,C_DATE)).year==yr and parse_date(safe(r,C_DATE)).month==mo]
        nps_v, n_nps, *_ = calc_nps(mrows)
        st_v, n_st       = calc_stars(mrows)
        _, _, _, csat_v  = calc_csat(mrows)
        result.append({"m": label, "nps": nps_v, "stars": st_v, "csat": csat_v, "n": len(mrows)})
    return result

# ── FILTER BY DATE ────────────────────────────────────────────────────────
def period_rows(rows, start, end):
    return [r for r in rows if parse_date(safe(r,C_DATE)) and start <= parse_date(safe(r,C_DATE)) <= end]

# ── FINANCIADOR GROUPS ────────────────────────────────────────────────────
def financiador_rows(rows, fin):
    if fin == 'TODAS':      return rows
    if fin == 'PREMIUM':    return [r for r in rows if is_premium(safe(r,C_PREP))]
    if fin == 'NO_PREMIUM': return [r for r in rows if safe(r,C_PREP) and not is_premium(safe(r,C_PREP))]
    if fin == 'SIN_DATO':   return [r for r in rows if not safe(r,C_PREP)]
    # Individual premium name
    return [r for r in rows if norm_prepaga(safe(r,C_PREP)) == fin]

FINANCIADORES = ['TODAS','PREMIUM','NO_PREMIUM','SIN_DATO'] + PREMIUM_NAMES

# ── GOOGLE AUTH ───────────────────────────────────────────────────────────
def get_token():
    import base64
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend
    sa = GOOGLE_SA
    now = int(time.time())
    hdr = base64.urlsafe_b64encode(json.dumps({"alg":"RS256","typ":"JWT"}).encode()).rstrip(b'=').decode()
    pay = base64.urlsafe_b64encode(json.dumps({
        "iss": sa["client_email"],
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now, "exp": now+3600
    }).encode()).rstrip(b'=').decode()
    pk = serialization.load_pem_private_key(sa["private_key"].encode(), password=None, backend=default_backend())
    sig = base64.urlsafe_b64encode(pk.sign(f"{hdr}.{pay}".encode(), padding.PKCS1v15(), hashes.SHA256())).rstrip(b'=').decode()
    jwt = f"{hdr}.{pay}.{sig}"
    data = urllib.parse.urlencode({"grant_type":"urn:ietf:params:oauth:grant-type:jwt-bearer","assertion":jwt}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=data)) as r:
        return json.loads(r.read())["access_token"]

def write_sheet(token, values):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{RESULTS_SHEET_ID}/values/{urllib.parse.quote('Hoja 1!A1')}?valueInputOption=RAW"
    body = json.dumps({"values": values}).encode()
    req = urllib.request.Request(url, data=body, method='PUT')
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def clear_sheet(token):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{RESULTS_SHEET_ID}/values/{urllib.parse.quote('Hoja 1!A1:Z2000')}:clear"
    req = urllib.request.Request(url, data=b'{}', method='POST')
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req) as r: pass

# ── CLAUDE AI ─────────────────────────────────────────────────────────────
def analyze_with_ai(centro, neg_comments, nps_val, csat_val, stars_val):
    if not neg_comments:
        return "Sin comentarios negativos en el período.", "[]", ""
    prompt = f"""Sos analista de calidad de atención médica para {centro}.

Métricas del último mes: NPS={nps_val}, CSAT={csat_val}, Estrellas={stars_val}

Comentarios negativos (NPS≤6 o estrellas≤2):
{chr(10).join(f'- {c}' for c in neg_comments[:30])}

Respondé SOLO con JSON (sin markdown):
{{"resumen":"2-3 oraciones sobre los problemas principales","problemas":[{{"tema":"...","frecuencia":"alta|media|baja","ejemplo":"..."}}],"tags":["tag1","tag2","tag3"]}}"""

    data = json.dumps({"model":"claude-sonnet-4-20250514","max_tokens":800,
                       "messages":[{"role":"user","content":prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=data)
    req.add_header('x-api-key', ANTHROPIC_API_KEY)
    req.add_header('anthropic-version', '2023-06-01')
    req.add_header('content-type', 'application/json')
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read())
    text = resp['content'][0]['text'].strip()
    try:
        p = json.loads(text)
        return p.get('resumen',''), json.dumps(p.get('problemas',[]),ensure_ascii=False), ','.join(p.get('tags',[]))
    except:
        return text[:300], '[]', ''

# ── MAIN ──────────────────────────────────────────────────────────────────
def main():
    print("=== Red Basa · Análisis nocturno ===")
    print(f"Fecha: {today()}")

    print("\n1. Descargando planilla consolidada...")
    raw = fetch_csv(CONSOLIDATED_SHEET_ID)
    all_rows = [r for r in raw[1:] if r and len(r)>C_CENTRO and safe(r,C_DATE) and safe(r,C_CENTRO)]
    print(f"   {len(all_rows)} filas cargadas")

    cuts = cutoffs()
    centros = sorted(set(safe(r,C_CENTRO).strip() for r in all_rows))
    print(f"   Centros: {centros}")

    HEADER = [
        "centro","periodo","financiador",
        "nps","n_nps","pct_promotores","pct_detractores",
        "csat_rrhh","csat_confort","csat_adic","csat_global",
        "estrellas","n_estrellas",
        "nps_prev","csat_prev","estrellas_prev",
        "dist_nps","sparkline",
        "resumen_ia","problemas_ia","tags_ia",
        "fecha_analisis"
    ]
    rows_out = [HEADER]

    PERIODOS = ['week','month','year']

    print("\n2. Pre-calculando métricas...")
    for centro in centros:
        print(f"   → {centro}")
        crows = [r for r in all_rows if safe(r,C_CENTRO).strip()==centro]

        # Sparkline (calculado una sola vez por centro, sobre todos los datos)
        sparkline = calc_sparkline(crows)

        # AI analysis (solo para periodo month, financiador TODAS)
        month_rows = period_rows(crows, *cuts['month'])
        neg_cmts = [safe(r,C_CMT) for r in month_rows
                    if not invalid(safe(r,C_CMT)) and
                    ((to_num(safe(r,C_NPS)) or 99) <= 6 or (to_num(safe(r,C_STAR)) or 99) <= 2)]
        nps_m, n_m, *_ = calc_nps(month_rows)
        _, _, _, csat_m = calc_csat(month_rows)
        st_m, _         = calc_stars(month_rows)
        resumen, problemas, tags = analyze_with_ai(centro, neg_cmts, nps_m, csat_m, st_m)

        for periodo in PERIODOS:
            start, end       = cuts[periodo]
            prev_start, prev_end = cuts[f'prev_{periodo}']
            p_rows  = period_rows(crows, start, end)
            pp_rows = period_rows(crows, prev_start, prev_end)

            # Dist NPS (solo una vez por periodo, con TODAS)
            dist = calc_dist(p_rows)

            for fin in FINANCIADORES:
                f_rows  = financiador_rows(p_rows, fin)
                fp_rows = financiador_rows(pp_rows, fin)

                nps_v, n_nps, pct_p, pct_d = calc_nps(f_rows)
                rrhh, conf, adic, glob      = calc_csat(f_rows)
                st_v, n_st                  = calc_stars(f_rows)

                nps_prev, *_  = calc_nps(fp_rows)
                _, _, _, cp   = calc_csat(fp_rows)
                st_prev, _    = calc_stars(fp_rows)

                rows_out.append([
                    centro, periodo, fin,
                    nps_v  if nps_v  is not None else '',
                    n_nps,
                    pct_p  if pct_p  is not None else '',
                    pct_d  if pct_d  is not None else '',
                    rrhh   if rrhh   is not None else '',
                    conf   if conf   is not None else '',
                    adic   if adic   is not None else '',
                    glob   if glob   is not None else '',
                    st_v   if st_v   is not None else '',
                    n_st,
                    nps_prev  if nps_prev  is not None else '',
                    cp        if cp        is not None else '',
                    st_prev   if st_prev   is not None else '',
                    json.dumps(dist, ensure_ascii=False)   if fin=='TODAS' else '',
                    json.dumps(sparkline, ensure_ascii=False) if fin=='TODAS' and periodo=='month' else '',
                    resumen   if fin=='TODAS' and periodo=='month' else '',
                    problemas if fin=='TODAS' and periodo=='month' else '',
                    tags      if fin=='TODAS' and periodo=='month' else '',
                    today().isoformat(),
                ])

        print(f"     {len(PERIODOS)*len(FINANCIADORES)} filas generadas")

    print(f"\n3. Escribiendo {len(rows_out)-1} filas en Google Sheets...")
    token = get_token()
    clear_sheet(token)
    write_sheet(token, rows_out)
    print("   ✓ Listo")
    print(f"\nTotal: {len(centros)} centros × {len(PERIODOS)} períodos × {len(FINANCIADORES)} financiadores = {len(rows_out)-1} filas")

if __name__ == '__main__':
    main()
