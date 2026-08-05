# Palworld Elemental Team Optimizer

A small Python project generated from the Phase 1–5 Palworld workbook.

## Features

- Five-Pal team builder
- Elemental synergy scoring
- Attack/defense aura detection
- Weakness amplifier detection
- Player elemental conversion detection
- Status setup/payoff detection
- Mount utility scoring
- Candidate ranking per element
- Reference tables for Pals, Partner Skills, Active Skills and Passives
- Streamlit UI and CLI

## Setup

```bash
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Database

Data now lives in PostgreSQL instead of the CSV files. Set the `DATABASE_URL`
environment variable (or copy `.env.example` to `.env` and edit it):

```text
DATABASE_URL=postgresql://user:password@host:5432/palworld_optimizer
```

The CSV files in `data/` are still the source of truth for the reference data.
Load (or reload, after editing a CSV) the database once with:

```bash
python migrate.py
```

## Run the web app

```bash
streamlit run app.py
```

## Run the CLI

```bash
python cli.py --element Fire --team "Wixen" "Kelpsea Ignis" "Renjishi" "Jormuntide Ignis" "Blazamut"
```

## Project structure

```text
palworld_team_optimizer/
├── app.py
├── cli.py
├── data_loader.py
├── db.py
├── engine.py
├── migrate.py
├── requirements.txt
├── .env.example
├── README.md
└── data/
    ├── pals.csv
    ├── partner_skills.csv
    ├── active_skills.csv
    ├── passive_skills.csv
    ├── buff_graph.csv
    ├── status_engine.csv
    └── mount_engine.csv
```

## Scoring model

The initial overall score combines:

- 20% elemental match
- 15% attack aura
- 10% defense aura
- 15% weakness amplification
- 10% player conversion
- 10% status synergy
- 5% mount utility
- 15% average combat quality

The weights are intentionally easy to edit in `engine.py`.
"# palword-team-optimiser" 
"# palword-team-optimiser" 
