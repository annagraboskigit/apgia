# APGIA

Dashboard pessoal de saúde e performance — treinos (Garmin .fit), exames médicos, Whoop.

## Estrutura

```
apgia/
├── index.html              ← dashboard principal (deploy GitHub Pages)
├── scripts/
│   ├── dashboard.py        ← gerador do dashboard v1
│   ├── dashboard_v2.py     ← gerador do dashboard v2
│   ├── analyze_ride.py     ← análise de atividades
│   └── inject_ride.py      ← injeção de dados de atividade
└── archive/dashboards/     ← versões anteriores do dashboard
```

## Deploy

GitHub Pages → `apgia.annagraboski.com`

```bash
git add index.html
git commit -m "atualiza dashboard"
git push
```

GitHub Pages atualiza em ~1-2 min.
