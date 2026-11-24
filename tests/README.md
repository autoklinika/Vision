# Testy Vision

Testy Core, profili ECU, biblioteki i Runtime znajdują się w `tests/core`.
Zestaw `tests/planner` obejmuje geometrię optyki, przygotowanie recepty S05,
granice usług MoveIt, koordynację S05–S06 oraz atomowy zapis i odtwarzanie
dowodów w ścisłym trybie planowania.

```bash
python -m pip install -r requirements-photography.txt
PYTHONPATH=src python -m unittest discover -s tests/core -q
PYTHONPATH=src:tests/core:tests/planner python -m unittest discover -s tests/planner -v
```

CI nie wymaga ROS ani podłączonych urządzeń. Profile, obrazy i odpowiedzi usług
używane w testach są syntetyczne. Nie stanowią pomiarów rzeczywistego ETC3.
Pomocnicze fixture są importowane jako moduły lub zwykłe klasy, żeby nowe testy
nie zwiększały liczników przez ponowne odkrywanie zaimportowanych TestCase.

Osobny skrypt `tools/lab/inspection_planner/moveit_smoke.py` sprawdza prawdziwe
usługi MoveIt na syntetycznej scenie w izolowanej domenie ROS z wyłączonym
wykonywaniem trajektorii. Nie uruchamia sterownika robota ani aparatu.

## WebGUI — niezależny klient

Testy React/TypeScript, importer Python i Chromium znajdują się w `webgui/tests/`. Polecenia, izolacja i granice testów: [webgui/README.md](../webgui/README.md). Nie wymagają ROS 2, VENTUNO ani realnego API; prywatna animacja ma osobne testy opt-in. CI backendu nie jest dowodem uruchomienia testów GUI.
