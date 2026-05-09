# CLAUDE.md — instrukcje dla AI

Ten plik czytasz jako pierwszy gdy pomagasz Marcinowi rozwijać Master Terminal.

## Kontekst projektu

Master Terminal to **warstwa decyzyjna** nad EA Terminal (`C:\Users\User\Desktop\terminal\`).
Master nie generuje sygnałów — filtruje je. Dane czyta z `signals_unified.db`
i `signal_log.csv` w EA, własny stan trzyma w `data/journal.db`.

Pełen manifest filozoficzny: [`CONTEXT.md`](CONTEXT.md).

## Zanim cokolwiek napiszesz

1. Przeczytaj `CONTEXT.md` — tam jest piętnaście zasad mistrzów i mapowanie na moduły
2. Przeczytaj `README.md` — szybki start i layout
3. Sprawdź czy zmiana, którą chcesz wprowadzić, **wpływa na werdykt**.
   Jeśli nie — nie wprowadzaj jej.

## Reguły, które łamiesz tylko po wyraźnej prośbie Marcina

- **Master jest read-only wobec EA Terminal.** Nigdy nie pisz do żadnego pliku
  w `C:\Users\User\Desktop\terminal\`.
- **Master ma jeden ekran w UI.** Bez tabów. Bez sub-paneli. Bez popoutów.
- **Werdykt to dataclass.** Nie string, nie dict bez schematu.
- **Wszystkie ścieżki w `master/config.py`.** Nie hardkodujemy w modułach.
- **Każdy nowy moduł = test smoke.** Nawet jeśli to tylko `assert import_works`.

## Konwencje kodu

- Python 3.11+ (jak EA)
- Type hints obowiązkowe na publicznym API modułu
- Dataclasses (lub Pydantic) dla werdyktów, trade'ów, regime states
- Logger przez `logging.getLogger(__name__)`, format ustawia `master/main.py`
- SQLite przez stdlib `sqlite3` dla journal; `sqlalchemy` tylko jeśli realnie
  potrzebne (na razie nie)

## Mapowanie autor → moduł

Gdy implementujesz logikę, cytuj autora w docstringu — to jest celowe,
buduje to "akademicką" tożsamość projektu i ułatwia review.

| Książka / autor | Moduł |
|---|---|
| Tharp — *Trade Your Way…* | `journal/stats.py`, `core/sizer.py`, `core/edge_lookup.py` |
| Murphy — *Technical Analysis…* | `core/setup_grader.py`, `data/feature_store.py` (intermarket) |
| Komar — *Sztuka spekulacji* | `core/setup_grader.py`, `monitor/psych.py` |
| Zaremba — *Jak zarabiać na surowcach* | `data/calendar.py`, `data/cot.py` |
| Lefèvre — *Wspomnienia gracza giełdowego* | werdykt STAND_DOWN jako default; `data/feature_store.py` (flow) |
| Schwager — *Market Wizards* | przekrój zasad |
| Douglas — *Trading in the Zone* | `monitor/psych.py`, werdykt jako probabilistyczny |
| Elder — *Trading for a Living* | `core/mtf.py`, `monitor/psych.py` |
| Faith — *Way of the Turtle* | `core/regime.py` (breakouts), mechaniczność reguł |
| Clenow — *Following the Trend* | `core/regime.py` |
| Kaufman — *Trading Systems and Methods* | `core/sizer.py` (vol-adjusted), AMA |
| Williams — *Long-Term Secrets…* | `data/cot.py`, sentiment extremes |
| Chan — *Quantitative Trading* | `core/wfa.py`, Sharpe/Kelly |
| Pardo — *Evaluation and Optimization…* | `core/wfa.py` |
| Taleb — *Fooled by Randomness* / *Black Swan* | `monitor/tail.py`, fat-tail awareness |

## Format odpowiedzi

- Po polsku, technicznie, bez owijania w bawełnę
- Krótkie sekcje, konkrety, kod gdy potrzeba
- Nie powielaj informacji z `CONTEXT.md` — odsyłaj
- Gdy nie wiesz — pytaj, nie zgaduj. Marcin woli "nie wiem, sprawdź X"
  niż "myślę że Y" które okazuje się złe

## Stan obecny (aktualizuj!)

- ✅ Scaffold (README, CONTEXT, CLAUDE, pyproject, layout katalogów, stuby modułów)
- ⏳ `feature_store.py` — czeka na pełny schemat `signals_unified.db`
- ⏳ `journal/importer.py` — schemat CSV znany, gotowy do implementacji
- ⏳ Reszta modułów — stuby z TODO, do iteracyjnej implementacji

Aktualizuj tę sekcję po każdej znaczącej zmianie.
