"""
analyze_ride.py — Análise pós-treino com contexto completo
Uso:
  python src/analyze_ride.py --manual
  python src/analyze_ride.py --fit data/raw/fit/arquivo.fit
  python src/analyze_ride.py --quick 90 180 150 45   (duração_min avgW NP TSS)

Gera:
  output/last_ride_analysis.json  — dados pra dashboard
  output/last_ride_analysis.html  — relatório standalone

Lê de:
  data/processed/health_unified.csv
  data/processed/pmc.csv
  data/processed/sessions_clean.csv
  data/processed/lab_results.csv
"""

import pandas as pd
import numpy as np
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

DATA = Path("data/processed")
RAW = Path("data/raw")
OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════

def load_unified():
    f = DATA / "health_unified.csv"
    if f.exists():
        df = pd.read_csv(f, parse_dates=["date"])
        return df
    return None

def load_pmc():
    f = DATA / "pmc.csv"
    if f.exists():
        return pd.read_csv(f, parse_dates=["date"])
    return None

def load_sessions():
    f = DATA / "sessions_clean.csv"
    if f.exists():
        df = pd.read_csv(f)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        elif 'start_time' in df.columns:
            df['date'] = pd.to_datetime(df['start_time']).dt.normalize()
        return df
    return None

def load_lab():
    f = DATA / "lab_results.csv"
    if f.exists():
        return pd.read_csv(f, parse_dates=["date"])
    return None


# ═══════════════════════════════════════════════════════════════
# INPUT RIDE DATA
# ═══════════════════════════════════════════════════════════════

def input_manual():
    """Input manual dos dados do treino"""
    print("\n" + "="*50)
    print("  DADOS DO TREINO")
    print("="*50)
    
    ride = {}
    ride['date'] = input("  Data (YYYY-MM-DD) [hoje]: ").strip()
    if not ride['date']:
        ride['date'] = datetime.now().strftime("%Y-%m-%d")
    
    ride['type'] = input("  Tipo (road/mtb/indoor/gravel) [road]: ").strip() or "road"
    ride['duration_min'] = float(input("  Duração (minutos): "))
    ride['distance_km'] = float(input("  Distância (km) [0]: ") or 0)
    ride['elevation_m'] = float(input("  Elevação (m) [0]: ") or 0)
    ride['avg_power'] = float(input("  Potência média (W): "))
    ride['normalized_power'] = float(input("  NP (W) [=avg]: ") or ride['avg_power'])
    ride['avg_hr'] = float(input("  FC média (bpm) [0]: ") or 0)
    ride['max_hr'] = float(input("  FC max (bpm) [0]: ") or 0)
    ride['tss'] = float(input("  TSS [calcular]: ") or 0)
    ride['avg_cadence'] = float(input("  Cadência média [0]: ") or 0)
    
    # Perceived effort
    ride['rpe'] = int(input("  RPE 1-10 (esforço percebido) [5]: ") or 5)
    ride['feel'] = input("  Sensação (great/good/ok/tired/bad) [ok]: ").strip() or "ok"
    ride['notes'] = input("  Notas livres: ").strip()
    
    # Whoop pre-ride (if known)
    print("\n  Whoop pré-treino (enter pra pular):")
    rec = input("    Recovery score %: ").strip()
    ride['pre_recovery'] = float(rec) if rec else None
    hrv = input("    HRV (ms): ").strip()
    ride['pre_hrv'] = float(hrv) if hrv else None
    
    return ride


def input_quick(args):
    """Input rápido via argumentos"""
    return {
        'date': datetime.now().strftime("%Y-%m-%d"),
        'type': 'road',
        'duration_min': float(args[0]),
        'avg_power': float(args[1]),
        'normalized_power': float(args[2]) if len(args) > 2 else float(args[1]),
        'tss': float(args[3]) if len(args) > 3 else 0,
        'distance_km': 0,
        'elevation_m': 0,
        'avg_hr': 0,
        'max_hr': 0,
        'avg_cadence': 0,
        'rpe': 5,
        'feel': 'ok',
        'notes': '',
        'pre_recovery': None,
        'pre_hrv': None,
    }


def input_fit(fit_path):
    """Extrai dados de arquivo .fit"""
    try:
        import fitparse
    except ImportError:
        print("  ⚠️  fitparse não instalado. pip install fitparse")
        return None
    
    fitfile = fitparse.FitFile(str(fit_path))
    
    # Get session summary
    sessions = list(fitfile.get_messages('session'))
    if not sessions:
        print("  ⚠️  Sem dados de session no .fit")
        return None
    
    s = sessions[0]
    fields = {f.name: f.value for f in s.fields}
    
    ride = {
        'date': datetime.now().strftime("%Y-%m-%d"),
        'type': 'road',
        'duration_min': fields.get('total_timer_time', 0) / 60,
        'distance_km': fields.get('total_distance', 0) / 1000,
        'elevation_m': fields.get('total_ascent', 0),
        'avg_power': fields.get('avg_power', 0) or 0,
        'normalized_power': fields.get('normalized_power', 0) or fields.get('avg_power', 0) or 0,
        'avg_hr': fields.get('avg_heart_rate', 0) or 0,
        'max_hr': fields.get('max_heart_rate', 0) or 0,
        'avg_cadence': fields.get('avg_cadence', 0) or 0,
        'tss': fields.get('training_stress_score', 0) or 0,
        'rpe': 5,
        'feel': 'ok',
        'notes': f'Importado de {fit_path.name}',
        'pre_recovery': None,
        'pre_hrv': None,
    }
    
    # Try to get timestamp
    ts = fields.get('start_time') or fields.get('timestamp')
    if ts:
        ride['date'] = ts.strftime("%Y-%m-%d") if hasattr(ts, 'strftime') else str(ts)[:10]
    
    print(f"  .fit importado: {ride['duration_min']:.0f}min, {ride['avg_power']:.0f}W avg, {ride['distance_km']:.1f}km")
    
    # Ask for subjective data
    ride['rpe'] = int(input("  RPE 1-10: ") or 5)
    ride['feel'] = input("  Sensação (great/good/ok/tired/bad): ").strip() or "ok"
    
    return ride


# ═══════════════════════════════════════════════════════════════
# CALCULATE DERIVED METRICS
# ═══════════════════════════════════════════════════════════════

FTP = 219  # Update this or read from config

def calc_derived(ride):
    """Calcula métricas derivadas"""
    r = ride.copy()
    
    # TSS if not provided
    if r['tss'] == 0 and r['normalized_power'] > 0:
        intensity_factor = r['normalized_power'] / FTP
        r['tss'] = (r['duration_min'] * 60 * r['normalized_power'] * intensity_factor) / (FTP * 3600) * 100
        r['tss_calculated'] = True
    else:
        r['tss_calculated'] = False
    
    # Intensity Factor
    r['intensity_factor'] = r['normalized_power'] / FTP if FTP > 0 else 0
    
    # Variability Index
    r['variability_index'] = r['normalized_power'] / r['avg_power'] if r['avg_power'] > 0 else 1
    
    # Efficiency Factor
    r['ef'] = r['normalized_power'] / r['avg_hr'] if r['avg_hr'] > 0 else 0
    
    # W/kg (68kg current)
    weight = 68  # TODO: read from config or latest data
    r['wkg'] = r['avg_power'] / weight
    r['np_wkg'] = r['normalized_power'] / weight
    
    # Zone estimate
    if_val = r['intensity_factor']
    if if_val < 0.55:
        r['zone'] = "Z1 — Recuperação"
    elif if_val < 0.75:
        r['zone'] = "Z2 — Endurance"
    elif if_val < 0.90:
        r['zone'] = "Z3 — Tempo"
    elif if_val < 1.05:
        r['zone'] = "Z4 — Limiar"
    elif if_val < 1.20:
        r['zone'] = "Z5 — VO₂max"
    else:
        r['zone'] = "Z6 — Anaeróbico"
    
    return r


# ═══════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════

def get_current_state(unified, pmc, ride_date):
    """Pega estado atual (dia do treino ou mais recente)"""
    state = {}
    rd = pd.Timestamp(ride_date)
    
    if pmc is not None:
        recent = pmc[pmc['date'] <= rd].tail(1)
        if len(recent) > 0:
            r = recent.iloc[0]
            state['ctl'] = r.get('ctl', None)
            state['atl'] = r.get('atl', None)
            state['tsb'] = r.get('tsb', None)
    
    if unified is not None:
        recent = unified[unified['date'] <= rd].tail(1)
        if len(recent) > 0:
            r = recent.iloc[0]
            for col in ['Recovery score %', 'Heart rate variability (ms)', 
                       'Resting heart rate (bpm)', 'Skin temp (celsius)',
                       'Asleep duration (min)', 'Deep (SWS) duration (min)',
                       'Day Strain']:
                if col in r.index and pd.notna(r[col]):
                    state[col] = r[col]
        
        # 7-day averages
        week = unified[(unified['date'] > rd - timedelta(days=7)) & (unified['date'] <= rd)]
        if len(week) > 0:
            for col in ['Recovery score %', 'Heart rate variability (ms)', 'Resting heart rate (bpm)']:
                if col in week.columns:
                    vals = week[col].dropna()
                    if len(vals) > 0:
                        state[f'{col}_7d'] = vals.mean()
    
    return state


def get_lab_context(lab):
    """Pega último exame relevante"""
    if lab is None:
        return {}
    
    latest_date = lab['date'].max()
    latest = lab[lab['date'] == latest_date]
    
    context = {'exam_date': latest_date.strftime('%Y-%m-%d')}
    
    key_markers = {
        'hematocrito': 'Hematócrito',
        'hemoglobina': 'Hemoglobina', 
        'ferritina': 'Ferritina',
        'sat_transferrina': 'Sat. Transferrina',
        'cortisol': 'Cortisol',
        'insulina': 'Insulina',
    }
    
    for marker_id, label in key_markers.items():
        m = latest[latest['marker'] == marker_id]
        if len(m) > 0:
            row = m.iloc[0]
            context[marker_id] = {
                'value': row['value'],
                'status': row['status'],
                'label': label,
            }
    
    return context


def find_similar_rides(sessions, ride):
    """Encontra treinos semelhantes no histórico"""
    if sessions is None or len(sessions) == 0:
        return []
    
    dur = ride['duration_min']
    power = ride['avg_power']
    
    # Filter similar duration (±30%) and type
    similar = sessions.copy()
    
    if 'duration_min' in similar.columns:
        dur_col = 'duration_min'
    elif 'moving_time' in similar.columns:
        similar['duration_min'] = similar['moving_time'] / 60
        dur_col = 'duration_min'
    elif 'total_time' in similar.columns:
        similar['duration_min'] = similar['total_time'] / 60
        dur_col = 'duration_min'
    else:
        return []
    
    similar = similar[
        (similar[dur_col] > dur * 0.7) & 
        (similar[dur_col] < dur * 1.3)
    ]
    
    if 'avg_power' in similar.columns and power > 0:
        similar = similar[similar['avg_power'].notna()]
        if len(similar) > 0:
            similar['power_diff'] = abs(similar['avg_power'] - power)
            similar = similar.nsmallest(5, 'power_diff')
    else:
        similar = similar.tail(5)
    
    results = []
    for _, s in similar.iterrows():
        r = {
            'date': str(s.get('date', ''))[:10],
            'duration_min': s.get(dur_col, 0),
            'avg_power': s.get('avg_power', 0),
            'tss': s.get('training_stress_score', s.get('tss', 0)),
        }
        if 'avg_hr' in s.index:
            r['avg_hr'] = s['avg_hr']
        if 'normalized_power' in s.index:
            r['normalized_power'] = s['normalized_power']
        results.append(r)
    
    return results


def predict_recovery_impact(ride, state):
    """Estima impacto no recovery baseado em dados históricos"""
    impact = {}
    
    tss = ride.get('tss', 0)
    tsb = state.get('tsb', 0)
    current_rec = state.get('Recovery score %', 50)
    
    # TSS-based impact estimate
    if tss < 50:
        impact['tss_level'] = "Leve"
        impact['estimated_recovery_drop'] = -5
        impact['recovery_days'] = 0
    elif tss < 100:
        impact['tss_level'] = "Moderado"
        impact['estimated_recovery_drop'] = -10
        impact['recovery_days'] = 1
    elif tss < 200:
        impact['tss_level'] = "Forte"
        impact['estimated_recovery_drop'] = -20
        impact['recovery_days'] = 1
    elif tss < 350:
        impact['tss_level'] = "Muito forte"
        impact['estimated_recovery_drop'] = -30
        impact['recovery_days'] = 2
    else:
        impact['tss_level'] = "Extremo"
        impact['estimated_recovery_drop'] = -40
        impact['recovery_days'] = 3
    
    # Adjust for current state
    if tsb is not None:
        if tsb < -20:
            impact['state_warning'] = "⚠️ TSB muito negativo — fadiga acumulada amplifica impacto"
            impact['estimated_recovery_drop'] *= 1.3
            impact['recovery_days'] += 1
        elif tsb > 20:
            impact['state_bonus'] = "✅ TSB positivo — corpo descansado absorve melhor"
            impact['estimated_recovery_drop'] *= 0.7
    
    # New CTL/ATL estimate (simplified exponential)
    if state.get('ctl') is not None:
        ctl = state['ctl']
        atl = state.get('atl', ctl)
        new_ctl = ctl + (tss - ctl) / 42
        new_atl = atl + (tss - atl) / 7
        new_tsb = new_ctl - new_atl
        impact['new_ctl'] = round(new_ctl, 1)
        impact['new_atl'] = round(new_atl, 1)
        impact['new_tsb'] = round(new_tsb, 1)
        impact['ctl_delta'] = round(new_ctl - ctl, 1)
    
    impact['estimated_recovery_drop'] = round(impact['estimated_recovery_drop'])
    
    return impact


def generate_suggestions(ride, state, impact, lab_context):
    """Gera sugestões para próximo treino"""
    suggestions = []
    
    tss = ride.get('tss', 0)
    tsb = state.get('tsb', 0) or 0
    new_tsb = impact.get('new_tsb', tsb)
    
    # Next day suggestion
    if tss > 200 or new_tsb < -30:
        suggestions.append({
            'priority': 'high',
            'action': 'Rest day amanhã',
            'reason': f'TSS {tss:.0f} + TSB projetado {new_tsb:.0f} = fadiga significativa',
        })
    elif tss > 100:
        suggestions.append({
            'priority': 'medium',
            'action': 'Z1-Z2 curto amanhã (30-45min)',
            'reason': f'Recovery ativo ajuda sem acumular fadiga',
        })
    else:
        suggestions.append({
            'priority': 'low',
            'action': 'Treino normal amanhã',
            'reason': f'Carga leve, sem necessidade de recovery extra',
        })
    
    # RPE vs power mismatch
    if ride.get('rpe', 5) >= 8 and ride.get('intensity_factor', 0) < 0.75:
        suggestions.append({
            'priority': 'high',
            'action': 'Investigar: esforço percebido alto com potência baixa',
            'reason': 'RPE alto + IF baixo pode indicar fadiga acumulada, desidratação, ou sono insuficiente',
        })
    
    # Lab-based suggestions
    if lab_context:
        hct = lab_context.get('hematocrito', {})
        if hct and hct.get('status') == 'high':
            suggestions.append({
                'priority': 'medium',
                'action': 'Hidratação reforçada',
                'reason': f'Hematócrito {hct["value"]}% (alto) — sangue viscoso piora com desidratação',
            })
        
        ferr = lab_context.get('ferritina', {})
        if ferr and ferr.get('value', 100) < 30:
            suggestions.append({
                'priority': 'high',
                'action': 'Ferro baixo limita transporte de O₂',
                'reason': f'Ferritina {ferr["value"]} — EF e recovery comprometidos até normalizar',
            })
    
    # EF analysis
    if ride.get('ef', 0) > 0:
        ef = ride['ef']
        if ef > 1.8:
            suggestions.append({
                'priority': 'info',
                'action': f'EF excelente ({ef:.2f})',
                'reason': 'Boa relação potência/FC — eficiência cardiovascular em dia',
            })
        elif ef < 1.3:
            suggestions.append({
                'priority': 'medium',
                'action': f'EF baixo ({ef:.2f})',
                'reason': 'FC alta pra potência produzida — fadiga, calor, ou desidratação',
            })
    
    # Weekly load check
    rec_7d = state.get('Recovery score %_7d')
    if rec_7d is not None and rec_7d < 40:
        suggestions.append({
            'priority': 'high',
            'action': 'Recovery médio 7d abaixo de 40%',
            'reason': f'Recovery 7d = {rec_7d:.0f}% — considerar semana de descarga',
        })
    
    return suggestions


# ═══════════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════════

def inject_into_dashboard(analysis):
    """Injeta dados do treino no dashboard HTML"""
    dashboard_path = OUTPUT / "dashboard.html"
    if not dashboard_path.exists():
        # Try alternative names
        for name in ["dashboard_unified.html", "dashboard.htm"]:
            alt = OUTPUT / name
            if alt.exists():
                dashboard_path = alt
                break
    
    if not dashboard_path.exists():
        print(f"  ⚠️  Dashboard não encontrado em {OUTPUT}/")
        return False
    
    html = dashboard_path.read_text(encoding='utf-8')
    
    # Build JS injection
    data_json = json.dumps(analysis, default=str, ensure_ascii=False)
    injection = f"window.RIDE_DATA = {data_json};"
    
    # Replace placeholder or existing injection
    if '// RIDE_DATA_PLACEHOLDER' in html:
        html = html.replace('// RIDE_DATA_PLACEHOLDER', injection)
    elif 'window.RIDE_DATA = ' in html:
        # Replace existing data
        import re
        html = re.sub(r'window\.RIDE_DATA = \{.*?\};', injection, html, flags=re.DOTALL)
    else:
        # Inject before first Chart.defaults
        html = html.replace('// ── Chart defaults', f'{injection}\n\n// ── Chart defaults')
    
    dashboard_path.write_text(html, encoding='utf-8')
    print(f"  ✅ Dashboard atualizado: {dashboard_path}")
    return True


def save_analysis(ride, state, impact, similar, suggestions, lab_context):
    """Salva análise em JSON pra dashboard e gera HTML"""
    
    analysis = {
        'generated': datetime.now().isoformat(),
        'ride': ride,
        'state': {k: float(v) if isinstance(v, (np.floating, np.integer)) else v 
                  for k, v in state.items() if v is not None},
        'impact': impact,
        'similar_rides': similar,
        'suggestions': suggestions,
        'lab_context': {k: v for k, v in lab_context.items() if k != 'exam_date'} if lab_context else {},
        'lab_exam_date': lab_context.get('exam_date', '') if lab_context else '',
        'ftp': FTP,
    }
    
    # Save JSON
    json_path = OUTPUT / "last_ride_analysis.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, default=str, ensure_ascii=False, indent=2)
    print(f"\n  ✅ JSON: {json_path}")
    
    # Inject into dashboard HTML
    inject_into_dashboard(analysis)
    
    return analysis


def print_summary(ride, state, impact, similar, suggestions, lab_context):
    """Print resumo no terminal"""
    
    print("\n" + "═"*60)
    print(f"  ANÁLISE DO TREINO — {ride['date']}")
    print("═"*60)
    
    # Ride summary
    print(f"\n  ⏱  {ride['duration_min']:.0f}min | {ride['distance_km']:.1f}km | {ride['elevation_m']:.0f}m↑")
    print(f"  ⚡ Avg {ride['avg_power']:.0f}W | NP {ride['normalized_power']:.0f}W | IF {ride.get('intensity_factor',0):.2f}")
    print(f"  📊 TSS {ride['tss']:.0f} {'(calculado)' if ride.get('tss_calculated') else ''} | {ride.get('zone','')}")
    print(f"  💪 {ride.get('wkg',0):.2f} W/kg avg | {ride.get('np_wkg',0):.2f} W/kg NP")
    if ride.get('ef', 0) > 0:
        print(f"  ❤️  FC {ride['avg_hr']:.0f}/{ride['max_hr']:.0f} bpm | EF {ride['ef']:.2f}")
    print(f"  🧠 RPE {ride['rpe']}/10 | Sensação: {ride['feel']}")
    
    # State
    print(f"\n  {'─'*50}")
    print(f"  ESTADO PRÉ-TREINO:")
    if state.get('ctl'):
        print(f"    CTL {state['ctl']:.0f} | ATL {state.get('atl',0):.0f} | TSB {state.get('tsb',0):+.0f}")
    if state.get('Recovery score %'):
        print(f"    Recovery: {state['Recovery score %']:.0f}%")
    if state.get('Heart rate variability (ms)'):
        print(f"    HRV: {state['Heart rate variability (ms)']:.0f}ms | RHR: {state.get('Resting heart rate (bpm)',0):.0f}bpm")
    
    # Impact
    print(f"\n  {'─'*50}")
    print(f"  IMPACTO ESTIMADO:")
    print(f"    Nível: {impact['tss_level']}")
    print(f"    Recovery estimado: {impact['estimated_recovery_drop']:+.0f}%")
    print(f"    Dias pra absorver: {impact['recovery_days']}")
    if impact.get('new_ctl'):
        print(f"    CTL: {state.get('ctl',0):.0f} → {impact['new_ctl']:.0f} ({impact['ctl_delta']:+.1f})")
        print(f"    TSB: {state.get('tsb',0):+.0f} → {impact['new_tsb']:+.0f}")
    if impact.get('state_warning'):
        print(f"    {impact['state_warning']}")
    if impact.get('state_bonus'):
        print(f"    {impact['state_bonus']}")
    
    # Similar rides
    if similar:
        print(f"\n  {'─'*50}")
        print(f"  TREINOS SEMELHANTES:")
        for s in similar[:3]:
            print(f"    {s['date']} | {s['duration_min']:.0f}min | {s.get('avg_power',0):.0f}W | TSS {s.get('tss',0):.0f}")
    
    # Lab context
    if lab_context and len(lab_context) > 1:
        print(f"\n  {'─'*50}")
        print(f"  CONTEXTO LAB ({lab_context.get('exam_date','')}):")
        for k, v in lab_context.items():
            if k != 'exam_date' and isinstance(v, dict):
                status_icon = "✅" if v['status'] == 'normal' else "⚠️" if v['status'] == 'high' else "🔻"
                print(f"    {status_icon} {v['label']}: {v['value']} ({v['status']})")
    
    # Suggestions
    print(f"\n  {'─'*50}")
    print(f"  SUGESTÕES:")
    icons = {'high': '🔴', 'medium': '🟡', 'low': '🟢', 'info': 'ℹ️'}
    for s in suggestions:
        print(f"    {icons.get(s['priority'],'•')} {s['action']}")
        print(f"       {s['reason']}")
    
    print(f"\n{'═'*60}\n")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Análise pós-treino')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--manual', action='store_true', help='Input manual interativo')
    group.add_argument('--fit', type=str, help='Caminho do arquivo .fit')
    group.add_argument('--quick', nargs='+', help='Rápido: duração_min avgW [NP] [TSS]')
    
    args = parser.parse_args()
    
    # Get ride data
    if args.manual:
        ride = input_manual()
    elif args.fit:
        ride = input_fit(Path(args.fit))
    elif args.quick:
        ride = input_quick(args.quick)
    
    if ride is None:
        print("Erro ao obter dados do treino")
        return
    
    # Calculate derived metrics
    ride = calc_derived(ride)
    
    # Load context
    print("\nCarregando contexto...")
    unified = load_unified()
    pmc = load_pmc()
    sessions = load_sessions()
    lab = load_lab()
    
    # Analyze
    state = get_current_state(unified, pmc, ride['date'])
    lab_context = get_lab_context(lab)
    similar = find_similar_rides(sessions, ride)
    impact = predict_recovery_impact(ride, state)
    suggestions = generate_suggestions(ride, state, impact, lab_context)
    
    # Output
    print_summary(ride, state, impact, similar, suggestions, lab_context)
    analysis = save_analysis(ride, state, impact, similar, suggestions, lab_context)
    
    print(f"  Dashboard: abrir output/dashboard.html → aba '🔄 Último Treino'")
    
    return analysis


if __name__ == "__main__":
    main()
