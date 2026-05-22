#!/usr/bin/env python3
"""
Red Basa · Test diagnóstico Todoist San José
Requiere: TODOIST_SSJ env variable
"""
import os, json, urllib.request, urllib.parse, datetime

TOKEN = os.environ.get('TODOIST_SSJ', '')
if not TOKEN:
    print("ERROR: TODOIST_SSJ no configurado")
    exit(1)

def api_get(url):
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Bearer {TOKEN}')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

today     = datetime.date.today()
week_ago  = today - datetime.timedelta(days=7)
month_ago = today - datetime.timedelta(days=30)
year_ago  = today - datetime.timedelta(days=365)

print("=" * 60)
print("RED BASA · Diagnóstico Todoist San José")
print(f"Fecha: {today}")
print("=" * 60)

# 1. Proyectos activos
print("\n1. PROYECTOS ACTIVOS (SSJ):")
try:
    data = api_get('https://api.todoist.com/api/v1/projects?limit=200')
    projects = data.get('results', data) if isinstance(data, dict) else data
    ssj = [p for p in projects if p.get('name','').startswith('SSJ')]
    print(f"   Total proyectos activos SSJ: {len(ssj)}")
    for p in ssj[:5]:
        print(f"   - {p['name'][:70]}")
    if len(ssj) > 5:
        print(f"   ... y {len(ssj)-5} más")
except Exception as e:
    print(f"   ERROR: {e}")

# 2. Tareas completadas por período
print("\n2. TAREAS COMPLETADAS:")
TAREAS = ['Bienvenida al paciente', 'Visita Diaria', 'Realización de la encuesta']
PERIODOS = [
    ('Última semana',  week_ago.isoformat(),  today.isoformat()),
    ('Último mes',     month_ago.isoformat(), today.isoformat()),
    ('Último año',     year_ago.isoformat(),  today.isoformat()),
]

for label, since, until in PERIODOS:
    print(f"\n   [{label}] {since} → {until}")
    try:
        url = (f"https://api.todoist.com/api/v1/tasks/completed/by_completion_date"
               f"?since={since}T00:00:00Z&until={until}T23:59:59Z&limit=200")
        data  = api_get(url)
        items = data.get('items', data.get('results', []))
        print(f"   Total tareas completadas: {len(items)}")
        conteos = {t: 0 for t in TAREAS}
        for item in items:
            nombre = item.get('content', item.get('task_content','')).strip()
            if nombre in conteos:
                conteos[nombre] += 1
        pacientes = len(set(item.get('project_id') for item in items))
        print(f"   Pacientes únicos: {pacientes}")
        for tarea, count in conteos.items():
            print(f"   - {tarea}: {count}")
    except Exception as e:
        print(f"   ERROR: {e}")

# 3. Muestra de últimas tareas
print("\n3. ÚLTIMAS 5 TAREAS COMPLETADAS (último mes):")
try:
    url = (f"https://api.todoist.com/api/v1/tasks/completed/by_completion_date"
           f"?since={month_ago.isoformat()}T00:00:00Z"
           f"&until={today.isoformat()}T23:59:59Z&limit=5")
    data  = api_get(url)
    items = data.get('items', data.get('results', []))
    for item in items:
        nombre    = item.get('content', item.get('task_content',''))
        completed = item.get('completed_at', item.get('completedAt',''))[:10]
        project   = str(item.get('project_id',''))[:8]
        print(f"   {completed} | {nombre} | proyecto:{project}")
    if not items:
        print("   Sin tareas completadas en el período")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n" + "=" * 60)
print("Diagnóstico completado")
