"""
inject_ride.py — Injeta dados do último treino no dashboard HTML
Uso: python src/inject_ride.py
"""
import json
from pathlib import Path

OUTPUT = Path("outputs")

json_path = OUTPUT / "last_ride_analysis.json"
html_path = OUTPUT / "dashboard.html"

if not json_path.exists():
    print(f"  Não encontrou {json_path}")
    print(f"  Rode analyze_ride.py primeiro")
    exit(1)

if not html_path.exists():
    print(f"  Não encontrou {html_path}")
    exit(1)

with open(json_path, 'r', encoding='utf-8') as f:
    data = f.read().strip()

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

marker = '// RIDE_DATA_PLACEHOLDER'
injection = f'window.RIDE_DATA = {data};'

if marker in html:
    html = html.replace(marker, injection)
    print(f"  Placeholder substituído")
elif 'window.RIDE_DATA = {' in html:
    import re
    html = re.sub(r'window\.RIDE_DATA = \{.*?\};', injection, html, flags=re.DOTALL)
    print(f"  Dados anteriores substituídos")
else:
    print(f"  ⚠️  Placeholder não encontrado no HTML")
    exit(1)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"  ✅ Dashboard atualizado: {html_path}")
