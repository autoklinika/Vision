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

Testy React/TypeScript, importer Python i Chromium znajdują się w `webgui/tests/`. Polecenia, izolacja i granice testów: [webgui/README.md](../webgui/README.md). Testy jednostkowe i izolowane DEV/build nie wymagają ROS 2 ani sprzętu. Stanowiskowy zestaw Playwright używa rzeczywistego WSGI API oraz niezależnego Core hosta z tymczasową biblioteką i tożsamością testową. Firefox i Chromium uruchamiać osobno, z odizolowanymi fixture. Prywatna animacja ma osobne testy opt-in. Dedykowany workflow `vision-api-webgui-v1.yml` sprawdza API i klienta; CI nie jest odbiorem sprzętowym.

## API i Core Host

`tests/api/` obejmuje boot/status, projekcje sesji i dziennika, bibliotekę ECU, tożsamość oraz prywatny IPC. W odizolowanym venv, z katalogu repozytorium:

```sh
python -m pip install -r requirements-station.txt pytest
PYTHONPATH=src python -B -m pytest -q -p no:cacheprovider tests/api/test_core_host.py tests/api/test_station.py
```

Szczegóły kontraktu i pełnej akceptacji: [Station WebGUI](../docs/implementation/VISION_STATION_WEBGUI_V1.md), [runbook](../docs/operations/VISION_WEBGUI_DEPLOYMENT.md). Nie używać produkcyjnego socketu, kont ani biblioteki w fixture.
