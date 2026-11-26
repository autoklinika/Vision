# Vision — stanowisko inspekcji PCB / ECU

Vision to modułowy system dokumentowania i inspekcji sterowników ECU oraz płytek PCB. Platforma stanowiskowa: VENTUNO Q / Ubuntu ARM64, sensor RGB-D Luxonis, AgileX NERO i aparat Sony; urządzenia są wymienne przez kontrakty i profile.

**Stan referencyjny: 26.11.2026.** Fundament Fluent 2 ([#79](https://github.com/autoklinika/Vision/pull/79)) i poprawka sesji ([#80](https://github.com/autoklinika/Vision/pull/80)) są w main. Aktualny pakiet stanowiskowy DEV jest w [Draft PR #81](https://github.com/autoklinika/Vision/pull/81) — bez zgody na merge. `main` jest zatwierdzonym punktem odniesienia dla kodu i dokumentacji, **nie obrazem uruchomionych usług ani wydaniem produkcyjnym**.

**Najważniejsza zasada: WebGUI jest wyłącznie klientem całego systemu Vision.** Core koordynuje scenariusze i bramki, ROS 2 integruje urządzenia, MoveIt 2 planuje ruch, a właściwe moduły dostarczają dane oraz dowody.

## Aktualny stan projektu

| Obszar | Stan i zakres |
| --- | --- |
| [Vision Guided Positioning V1](docs/baselines/VISION_GUIDED_POSITIONING_V1_2026-11-23.md) | LAB ACCEPTED 23.11: fizyczne dojazdy NERO do celów ETC3/PTM i powrót do PARK; zamrożona baza laboratoryjna |
| [Vision Core](src/vision_core/README.md) | Merged: fundament, fotografia offline, powtarzalność, rozszerzenia i audyty ([#39](https://github.com/autoklinika/Vision/pull/39)–[#45](https://github.com/autoklinika/Vision/pull/45)); nie stanowią pełnego wdrożenia sprzętowego |
| [ECU Reference Profiles i biblioteka](docs/implementation/VISION_ECU_LIBRARY_BACKEND_V1.md) | Merged: katalog, model wzorcowy, wersje, walidacja, robocze profile, backend biblioteki ([#46](https://github.com/autoklinika/Vision/pull/46)–[#49](https://github.com/autoklinika/Vision/pull/49)); ETC3 DRAFT / NOT_READY |
| [Runtime V1 S01–S04](docs/implementation/VISION_RUNTIME_V1_S01_S04.md) | Merged [#50](https://github.com/autoklinika/Vision/pull/50); odczyt ROS 2 Luxonis zweryfikowany, fizyczne S03/S04 dla ETC3 nadal wymagają odbioru |
| [Inspection Planner V1 S05–S06](docs/implementation/VISION_INSPECTION_PLANNER_V1_S05_S06.md) | Merged [#52](https://github.com/autoklinika/Vision/pull/52); planowanie i testy plan-only, nie wykonanie ruchu ani zdjęć |
| [Thermal Inspection V1](docs/implementation/VISION_THERMAL_INSPECTION_V1.md) | Merged moduł offline ([#44](https://github.com/autoklinika/Vision/pull/44), [#45](https://github.com/autoklinika/Vision/pull/45)); brak odbioru metrologicznego toru sprzętowego |
| [WebGUI](webgui/README.md) | Fluent 2 Kiosk i zdalny klient, rzeczywiste logowanie, zmiana hasła, prywatny IPC do niezależnego Core. Produkcyjny GUI pozostaje na wydaniu #80. |
| [System Status / diagnostyka](docs/implementation/VISION_DEVICE_READINESS_V1.md) | DEV #81: usługi, USB i diagnostyka ROS 2; nie jest autoryzacją inspekcji |
| [Biblioteka ECU — deklaracja V2](docs/implementation/VISION_ECU_DECLARATION_V2.md) | DEV #81: uproszczony formularz, wersje, wyszukiwanie i cykl życia; nie jest zatwierdzonym profilem wykonawczym |
| [Luxonis V1](docs/implementation/VISION_DEVICES_LUXONIS_V1.md) | DEV #81: osobna zakładka, parametry, RGB/Depth, IR i stabilizacja podglądu; zakres zaakceptowany na obecnym etapie. Samodzielna usługa kamery ma autostart; pełny odbiór zimnego rozruchu pozostaje otwarty. NERO, Sony i Images wymagają osobnych pakietów |
| [ETC3 — lokalizacja RGB-D](https://github.com/autoklinika/Vision/pull/51) | Odrębny draft LAB, nie wdrożenie ani dowód S03/S04 PASS |

## Rozpocznij tutaj

- [Indeks aktualnej dokumentacji i ADR](docs/README.md) — obowiązujące decyzje, kontrakty, testy, raporty i materiały historyczne.
- [Mapa kodu](src/README.md) — odpowiedzialność istniejących modułów.
- [Testy offline](tests/README.md) i [testy WebGUI](webgui/README.md) — niezależne od sprzętu.
- [Rejestr bieżących prac — 26.11.2026](docs/operations/REPOSITORY_REGISTER_2026-11-26.md) — bieżące prace i archiwum.
- [Zasady utrzymania repozytorium](docs/process/REPOSITORY_HYGIENE_V1.md) i [proces rozwoju](docs/process/DEVELOPMENT.md).

## Kolejne pakiety

Dwa równoległe tory, bez kopiowania logiki systemu do klienta:

| Tor | Najbliższe zadania |
| --- | --- |
| Backend | Odbiór absolutnej transformacji, profilu ETC3 i powiązania dowodów Runtime dla S03/S04; późniejsza integracja S07 i kolejnych etapów zgodnie z Workflow |
| WebGUI | Zachować odebrany zakres Luxonis V1. Następny pakiet urządzenia: do uzgodnienia (NERO proponowany). Inspection Manager i kolejne urządzenia pozostają odrębnymi zadaniami. Przed merge #81: pełny audyt, aktualne CI i decyzja operatora |

Szczegóły i kryteria: [Workflow V1](docs/workflows/VISION_INSPECTION_WORKFLOW_V1.md), [WebGUI V1](docs/ux/VISION_WEBGUI_V1_SPECIFICATION.md). Oryginalne prywatne zasoby marki pozostają poza Git i standardowym buildem; prawa do dystrybucji prywatnych zasobów pozostają odrębną bramką. Prywatny dostęp HTTPS działa. [Kontrakt stanowiskowy](docs/implementation/VISION_STATION_WEBGUI_V1.md) · [Runbook wdrożenia](docs/operations/VISION_WEBGUI_DEPLOYMENT.md).

## Zasady rozwoju

1. Nowy, mały PR od aktualnego `origin/main`; testy, audyt i zatwierdzenie właściciela przed merge.
2. Nie przywracamy dawnych executorów ani własnego stosu Camera Service/Perception Engine jako konkurencyjnej architektury.
3. Testy kodu nie oznaczają odbioru stanowiskowego. Operacje sprzętowe mają osobną procedurę i akceptację.
4. Publiczny GitHub: kod, syntetyczne testy, zanonimizowane decyzje. Prywatne dane, kalibracje stanowiska, obrazy, logi i zasoby o niezweryfikowanych prawach pozostają poza Git.

Historia dawnych testów i opisów: [indeks dokumentacji historycznej](docs/README.md#materiały-historyczne), [poprzedni README](https://github.com/autoklinika/Vision/blob/4bb088186eb06a40ab9fd2e96072551d318a2d90/README.md) i [snapshot #15](https://github.com/autoklinika/Vision/pull/15). Zachowujemy historię bez scalania przestarzałych eksperymentów.
