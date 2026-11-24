# Kod aplikacji Vision — mapa modułów

**Stan: 24.11.2026.** W tym katalogu istnieje już kod Python, a nie tylko plan aplikacji. Zatwierdzone kontrakty: [ADR Core](../docs/architecture/ADR_VISION_CORE_HARDWARE_INDEPENDENCE_2026-11-23.md), [Workflow V1](../docs/workflows/VISION_INSPECTION_WORKFLOW_V1.md) i [ADR WebGUI](../docs/decisions/ADR_VISION_WEBGUI_CLIENT_ONLY_2026-11-24.md).

| Katalog | Odpowiedzialność | Dokumentacja |
| --- | --- | --- |
| `vision_core/` | Profile wykonawcze, sesje i Workflow, kontekst i dowody, journal/archive, fotografia offline, jakość, powtarzalność, rozszerzenia | [Core README](vision_core/README.md), [Core 004](../docs/implementation/VISION_CORE_004_MODULAR_EXTENSIONS.md) |
| `vision_modules/ecu_profiles/` | Katalog i reguły odbioru danych ECU | [ECU Profiles V1](../docs/implementation/VISION_ECU_PROFILES_V1.md) |
| `vision_modules/ecu_reference/` | Wersjonowany pełny model referencyjny, walidacja, zasoby i kompilacja profilu wykonawczego | [Reference Profile implementation](../docs/implementation/VISION_ECU_REFERENCE_PROFILE_V1_IMPLEMENTATION.md) |
| `vision_modules/ecu_library_backend/` | Biblioteka ECU, robocze profile, historia, ETag i prywatny magazyn zasobów; bez transportu HTTP | [ECU Library Backend](../docs/implementation/VISION_ECU_LIBRARY_BACKEND_V1.md) |
| `vision_modules/thermal.py` | Moduł termiczny offline i kontrola jakości | [Thermal V1](../docs/implementation/VISION_THERMAL_INSPECTION_V1.md) |
| `vision_runtime/` | Koordynacja S01–S04, kontrakty obserwacji i adapter odczytowy ROS 2 | [Runtime V1](../docs/implementation/VISION_RUNTIME_V1_S01_S04.md), [Luxonis adapter](../docs/implementation/VISION_RUNTIME_ROS2_LUXONIS_ADAPTER_V1.md) |
| `vision_planner/` | Optyka i recepty ujęć S05, planowanie S06 przez MoveIt, kontekst i dowody | [Planner V1](../docs/implementation/VISION_INSPECTION_PLANNER_V1_S05_S06.md) |
| [`../webgui/`](../webgui/README.md) | Niezależny klient React/TypeScript, nie część logiki Core | [WebGUI spec](../docs/ux/VISION_WEBGUI_V1_SPECIFICATION.md) |

`config/` przechowuje wersjonowane publiczne szablony i przykładowe profile; nie jest kopią prywatnej kalibracji stanowiska. `tools/lab/` zawiera odrębne narzędzia eksperymentalne; nie są automatycznie uruchamiane jako produkcyjne usługi. `tests/` zawiera testy backendu, a `webgui/tests/` testy klienta.

Nie istnieje jeszcze kompletny wdrożony scenariusz S01–S11. Nie zastępujemy sterowników ROS 2 i MoveIt 2 własnym executor/Camera Service. Core nie zależy od uruchomienia WebGUI.

Testy: [tests/README.md](../tests/README.md). Historyczny plan katalogów jest zachowany w historii Git: [poprzedni src/README](https://github.com/autoklinika/Vision/blob/4bb088186eb06a40ab9fd2e96072551d318a2d90/src/README.md).
