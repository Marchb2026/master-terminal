# Master Terminal

Warstwa decyzyjna nad EA Terminal. Nie generuje sygnałów — **filtruje** je.
Pracuje jako osobny proces (port 8052), czyta dane z `signals_unified.db`
i z plików EA, prowadzi własny dziennik trade'ów (`data/journal.db`).

## Filozofia

Zobacz [`CONTEXT.md`](CONTEXT.md) — manifest projektu, destylacja zasad
z piętnastu książek (Tharp, Murphy, Komar, Zaremba, Lefèvre, Schwager,
Douglas, Elder, Faith, Clenow, Kaufman, Williams, Chan, Pardo, Taleb).

Zasada nadrzędna:

> Trader przegrywa nie dlatego, że nie ma sygnału — tylko dlatego,
> że bierze za dużo sygnałów. Master ma odrzucać, nie generować.

## Architektura

```
EA TERMINAL (8051)              MASTER TERMINAL (8052)
─────────────────                ─────────────────────
eksploracja, surowe dane    ──▶  decyzja, jeden werdykt
9 TF, footprint, magnety         regime, MTF, grade, edge
compute_sig, bankradar           sizing, psych, tail risk

         │                                │
         ▼                                ▼
    ┌─────────────────────────────────────────┐
    │   signals_unified.db / signal_log.csv   │
    │   (read-only z perspektywy Mastera)     │
    └─────────────────────────────────────────┘
```

## Quick start

```bash
# zależności
pip install -e .

# import historycznych sygnałów EA jako proto-journal
python -m master.journal.importer --csv "C:/Users/User/Desktop/terminal/logs/signal_log.csv"

# uruchomienie (CLI verdict + UI placeholder)
python -m master.main
```

## Struktura

```
master/
├── core/        # logika decyzyjna (regime, MTF, grader, sizer, plan)
├── data/        # adapter do EA + kalendarz + COT
├── journal/     # własny dziennik trade'ów + expectancy
├── monitor/     # psych state + tail risk
└── ui/          # jeden ekran, cztery stany (STAND_DOWN/WATCH/READY/ENGAGED)
```

## Stany werdyktu

- **STAND_DOWN** — aktywny no-trade, nic się nie kwalifikuje
- **WATCH** — warunki się rozwijają, czekamy na trigger
- **READY** — wszystko zielone, trigger uzbrojony
- **ENGAGED** — w pozycji, monitoring SL/TP/trailing
- **EXIT** — sygnał wyjścia
