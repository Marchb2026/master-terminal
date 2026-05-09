# Master Terminal — CONTEXT

Żywy manifest projektu. Czytaj na początku każdej sesji.

## Cel

Master Terminal to **filtr decyzyjny** stojący nad EA Terminalem. Surowy EA
generuje setki sygnałów dziennie. Master z tych setek wybiera maksymalnie
2–5 dziennie godnych realnej pozycji, resztę odrzuca.

Master nie zastępuje EA. EA to nadal *eksploracja* (footprint, magnets,
9 TF, bankradar, compute_sig). Master to *decyzja* — jeden ekran, jeden
werdykt, jedna kwota R do zaryzykowania.

## Piętnaście zasad mistrzów (skondensowane)

1. **Edge mierzony, nie wymyślony** — bez statystyki nie ma trade'a (Tharp, Chan, Pardo)
2. **Position size > entry signal** — wielkość bije sygnał (Tharp, Schwager, Kaufman)
3. **Ruina to jedyny prawdziwy wróg** — sekwencja strat normalna, ekspozycja na ruinę nie (Taleb, Tharp)
4. **Cut losses, let winners run** — asymetryczny R:R obowiązkowy (Lefèvre, Faith, Clenow)
5. **Reżim definiuje strategię** — trend/range/chaos to różne zwierzęta (Clenow, Komar, Murphy)
6. **Multi-timeframe obowiązkowy** — wyższy TF kierunek, niższy moment (Elder, Murphy)
7. **Confluence > pojedynczy wskaźnik** — co najmniej 3 niezależne potwierdzenia (Murphy, Komar)
8. **Cierpliwość to alfa** — siedzenie i nicnierobienie to stanowisko (Lefèvre, Schwager)
9. **Probabilistyczny umysł** — każdy trade niezależny, żaden "pewny" (Douglas, Tharp)
10. **Tail risk większy niż sugeruje rozkład** — gaussowski model to bajka (Taleb, Pardo)
11. **Macro/intermarket kontekst** — instrument nie istnieje w próżni (Murphy, Zaremba)
12. **Order flow / czytanie taśmy** — kto kupuje, gdzie, jak agresywnie (Lefèvre, Wizards)
13. **Psychologia to 50% wyniku** — najlepszy system z tilted traderem to katastrofa (Douglas, Komar t.2, Elder)
14. **System pasuje do tradera** — nie ma uniwersalnej metody (Tharp, Komar)
15. **Robustność > optymalizacja** — 3 parametry biją 30 (Pardo, Chan, Taleb)

## Mapowanie zasad na moduły

| Zasada | Moduł | Status |
|---|---|---|
| Edge mierzony | `journal/stats.py` + `core/edge_lookup.py` | scaffold |
| Position size | `core/sizer.py` | scaffold |
| Ruina | `monitor/psych.py` (session caps) | scaffold |
| Cut losses | `core/plan.py` (twardy SL = invalidation lub ATR) | scaffold |
| Reżim | `core/regime.py` | scaffold |
| MTF | `core/mtf.py` | scaffold |
| Confluence | `core/setup_grader.py` | scaffold |
| Cierpliwość | werdykt STAND_DOWN jako default | by design |
| Probabilistyka | werdykt zwraca expectancy w R, nie "buy/sell" | by design |
| Tail risk | `monitor/tail.py` + `data/calendar.py` | scaffold |
| Macro | `data/feature_store.py` (czyta compute_sig z EA) | scaffold |
| Flow | `data/feature_store.py` (czyta footprint z EA) | scaffold |
| Psych | `monitor/psych.py` | scaffold |
| Trader-fit | konfiguracja w `config.py` (R%, daily caps) | scaffold |
| Robustność | `core/wfa.py` (walk-forward analysis) | scaffold |

## Pipeline decyzyjny

```
                         ┌─────────────────┐
                         │   pre-checks    │  gates.py
                         │ (events/psych/  │
                         │   stale data)   │
                         └────────┬────────┘
                                  │  pass?
                          ┌───────┴───────┐
                          ▼               ▼
                       FAIL            CONTINUE
                    STAND_DOWN              │
                                            ▼
                                  ┌─────────────────┐
                                  │  regime.classify │ regime.py
                                  └────────┬────────┘
                                           │
                                           ▼
                                  ┌─────────────────┐
                                  │   mtf.align      │ mtf.py
                                  │   (score 0–9)    │
                                  └────────┬────────┘
                                           │
                                           ▼
                                  ┌─────────────────┐
                                  │  setup.grade    │ setup_grader.py
                                  │   (A/B/C)       │
                                  └────────┬────────┘
                                           │  A or B?
                                           ▼
                                  ┌─────────────────┐
                                  │  edge.lookup    │ edge_lookup.py
                                  │  (E from        │
                                  │   journal)      │
                                  └────────┬────────┘
                                           │  E > threshold?
                                           ▼
                                  ┌─────────────────┐
                                  │  sizer.size     │ sizer.py
                                  │  (R-multiples)  │
                                  └────────┬────────┘
                                           │
                                           ▼
                                  ┌─────────────────┐
                                  │  plan.build     │ plan.py
                                  │  WATCH/READY    │
                                  └─────────────────┘
```

## Dane wejściowe (z EA Terminal)

Stałe ścieżki (konfigurowane w `master/config.py`):

- `signals_unified.db` — główny hub sygnałów EA
- `logs/signal_log.csv` — historyczne sygnały z outcomes (proto-journal)
- `super_learner.db`, `ml_predictor.db`, `adaptive.db` — ML stan
- inne DB i pliki — TBD po pełnym audycie

Master jest **read-only** wobec wszystkich plików EA. Nigdy nie zapisuje
do żadnego z nich. Własny dziennik trzyma w `data/journal.db`.

## Constraints

- `signal_log.csv` ma kolumny: `ts, tf, signal, score, strength, ofi, cd50,
  dxy_bias, vix, price_at_signal, price_1h_later, price_4h_later, outcome_1h,
  outcome_4h, r_pips_1h, r_pips_4h, correct_1h, supporting, opposing, agreement`
- 6EM26 jako instrument bazowy; w przyszłości multi-instrument
- Strefa czasowa: +2h offset jak w EA
- Magnety: `RANGE=0.020`

## Co Master ma POKAZYWAĆ

Jeden ekran. Cztery stany. Bez tabów. Bez migoczących liczb.

```
┌─────────────────────────────────────────────────────────────┐
│  MASTER · 6EM26 · 14:32:18                                  │
│                                                              │
│         ┌──────────────────────┐                            │
│         │      STAND DOWN       │  główny werdykt            │
│         └──────────────────────┘                            │
│                                                              │
│  REGIME: TREND_UP_WEAK     MTF: 3.5/9                       │
│  SETUP:  C                 EDGE: n/a                        │
│  PSYCH:  CALM              TAIL: ECB in 18h — OK            │
│                                                              │
│  AUDIT TRAIL                                                │
│   ✓ pre-checks                                              │
│   ✗ MTF below threshold (3.5 < 7)                           │
│   ✗ no magnet within 1.5×ATR                                │
│   ✗ setup C — discarded                                     │
│                                                              │
│  LAST 5 TRADES         RUNNING E (n=30): +0.41R             │
│  +1.8R A TREND_UP                                           │
│  -1.0R B RANGE                                              │
│  ...                                                         │
└─────────────────────────────────────────────────────────────┘
```

Reguła: **jeśli coś nie zmienia werdyktu, nie pokazuj tego**.

## Backlog priorytetowy

1. ✅ Scaffold projektu, schemat danych, manifest
2. `feature_store.py` — introspekcja `signals_unified.db`, kontrakt danych
3. `journal/importer.py` — import `signal_log.csv` jako historia
4. `journal/stats.py` — running expectancy, R-distribution
5. `core/regime.py` — pierwszy realny klasyfikator (TF240/60)
6. `core/sizer.py` — R-multiples sizing
7. `core/mtf.py` — agregator 9 TF
8. `core/setup_grader.py` — A/B/C grading
9. `monitor/psych.py` — session caps, tilt detection
10. `monitor/tail.py` + `data/calendar.py` — eventy, blackout windows
11. `core/edge_lookup.py` — wyciąganie expectancy z journal'a
12. `core/plan.py` — generator planu trade'a
13. `ui/app.py` — minimalny widok jednoekranowy
14. `core/wfa.py` — walk-forward analysis (Pardo)
15. `data/cot.py` — CFTC weekly dla 6E

## Zasady rozwoju

- Nie dodajemy modułu, jeśli nie wpływa na werdykt
- Każdy moduł ma test smoke w `tests/`
- Nie kopiujemy logiki z EA — wołamy ją przez `data/feature_store.py`
- Nigdy nie piszemy do plików EA
- Konfiguracja: tylko `master/config.py`, jedno źródło prawdy
