# Vision — stanowisko inspekcji PCB / ECU

> **Aktualny stan zaakceptowany laboratoryjnie, 23.11.2026:** [Vision Guided Positioning V1](docs/baselines/VISION_GUIDED_POSITIONING_V1_2026-11-23.md) — kamera Luxonis wykrywa ETC3/PTM, MoveIt 2 planuje ruch, a AgileX NERO fizycznie wykonuje dojazdy i wraca do PARK. Operator potwierdził centralne pozycjonowanie nad PCB PTM. To **LAB**, nie wydanie produkcyjne; prywatne surowe obrazy, TF i snapshot runtime pozostają poza GitHub. Zobacz także [porządek repozytorium](docs/process/REPOSITORY_HYGIENE_V1.md) i [archiwum PR](docs/operations/OPEN_PR_PORTFOLIO_2026-11-23.md).

> **Uwaga:** kolejne historyczne sekcje README i datowane audyty opisują stan z października i pierwszej połowy listopada 2026. Nie należy interpretować ich jako bieżącego statusu hardware po odbiorze V1.

> **Nowy fundament Vision (ustalenia 14.11.2026, PR dokumentacyjny):** [założenia nowego systemu](docs/architecture/VISION_FOUNDATION_2026-11-14.md) i [archiwum rozmowy architektonicznej](docs/architecture/VISION_ARCHITECTURE_DISCUSSION_2026-11-14.md). Vision budujemy od podstaw, operator deklaruje ECU, a moduły i modele są wymienne. Pierwszy scenariusz dotyczy **ETC3 z dwiema czarnymi i jedną szarą wtyczką**, nie DAF SAC. Szczegóły wykonawcze pozostają do walidacji. Historyczne dokumenty niżej zachowują swoje oryginalne daty i statusy.

Projekt stanowiska fotograficzno-inspekcyjnego opartego na **Arduino VENTUNO Q** (Ubuntu ARM64), aparacie Sony A6100, kamerze termowizyjnej i ramieniu **AgileX NERO**.

**Stan dokumentacji na 10.11.2026:** `main` jest **zatwierdzoną bazą architektury, decyzji i statusów**, a nie kompletną działającą aplikacją Vision Core. Stan urządzeń jest zmienny; raport AS-BUILT jest datowaną fotografią konfiguracji i wyników testów.

## ECU Reference Profile V1 — zatwierdzony wzorzec wiedzy i instrukcji (24.11.2026)

- [ADR — ECU Reference Profile V1: ACCEPTED](docs/decisions/ADR_VISION_ECU_REFERENCE_PROFILE_V1_2026-11-24.md) — profil jest nominalnym, wersjonowanym źródłem wiedzy o ECU i instrukcją dla całego Vision, nie plikiem komend robota.
- [Pełna specyfikacja: 15 sekcji](docs/architecture/ECU_REFERENCE_PROFILE_V1_SPECIFICATION.md) i [szablon JSON](docs/templates/ECU_REFERENCE_PROFILE_V1_TEMPLATE.json) — dokumentacja architektury, **nie** wykonywalny profil ETC3.
- [Biblioteka ECU, wybór operatora i edytor — UX V1](docs/ux/ECU_LIBRARY_SELECTION_EDITOR_V1.md) — zaakceptowany kierunek GUI; implementacja dopiero w kolejnym etapie.
- Oddzielamy **Reference Profile**, wykonawczy **ECUProfile/ScenarioSpec** oraz **kartę badanej sztuki**. ETC3 pozostaje niezatwierdzonym DRAFT. Projekt katalogu: [PR #46](https://github.com/autoklinika/Vision/pull/46) (oddzielna, niescalona gałąź).

## Obowiązująca architektura Vision Core

- [ADR-VISION-CORE-001 — Hardware Independence & Modular Architecture](docs/architecture/ADR_VISION_CORE_HARDWARE_INDEPENDENCE_2026-11-23.md) — **ACCEPTED (23.11.2026)**: Core jest niezależnym od sprzętu koordynatorem inspekcji. Aparat, obiektyw, RGB-D i robot są wymienne przez interfejsy, adaptery i profile. Nowe urządzenie wymaga odpowiedniej kalibracji i weryfikacji, lecz nie przepisywania scenariuszy ECU.

## ROS 2 i przenośność stanowiska (16.11.2026)

- [Raport techniczny: ROS 2, NERO, MoveIt, Luxonis, ETC3 i przejście LAB → PROD](docs/architecture/VISION_ROS2_NERO_LAB_TO_PROD_TECHNICAL_REPORT_2026-11-16.md) — szczegółowe ustalenia, wymagania wejściowe, architektura i plan izolowanych testów; **DESIGN REPORT / PROPOSED**, bez wdrożenia na sprzęcie.
- [ADR-VISION-STATION-001: jeden kod, profile LAB i PROD](docs/architecture/ADR_VISION_PORTABLE_STATION_LAB_PROD_2026-11-16.md) — **PROPOSED**, wymaga formalnego zatwierdzenia; zmiana stanowiska unieważnia odpowiednie kalibracje i dopuszczenie ruchu.

## Bieżąca dokumentacja projektu

- [Stan faktyczny VENTUNO Q i modułów (AS-BUILT, 10.11.2026)](docs/operations/VISION_AS_BUILT_2026-11-10.md).
- [Otwarte problemy, ryzyka i bramki techniczne](docs/operations/OPEN_ITEMS_2026-11-10.md).
- [Polityka `main`, eksperymentów i dopuszczenia Vision Core](docs/operations/RELEASE_GATES_2026-11-10.md).
- [Architektura logiczna Vision](docs/architecture/OVERVIEW.md).
- [ADR-VISION-ROBOT-001 — dwustopniowy STOP AgileX NERO](docs/architecture/ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md), **ACCEPTED** jako architektura; wdrożenie etapu 1 **częściowe**.
- [ADR Sony — kanały HDMI/Wi-Fi/SD/USB](docs/architecture/ADR_SONY_STAGED_ACQUISITION_2026-10-13.md), **PROPOSED** — brak wdrożenia produkcyjnego.

## Status potwierdzonych prac

| Moduł | Najważniejsze potwierdzone wyniki | Stan integracji |
|---|---|---|
| VENTUNO Q | Ubuntu 24.04.4 ARM64, NVMe ext4, próby GPU/NPU, STM32/CAN | platforma laboratoryjna; pełny hardware baseline nadal otwarty |
| Sony A6100 | PTP, HDMI, Wi-Fi, BLE, RAW/JPEG, testy AF i stabilności | osobne próby udokumentowane; docelowy pipeline jeszcze nie wdrożony |
| Vision Thermal / InfiRay T2S+ | Web DEV v0.6: podgląd, 3 ROI, historia, obrót | **DEV FROZEN**, temperatury **NOT VALIDATED** metrologicznie; źródła prywatne |
| AgileX NERO 7 DOF | pyAgxArm, firmware 1.22, odczyt wszystkich przegubów i potwierdzenie komendy STOP | pierwsze ruchy / hamowanie pod obciążeniem jeszcze niewalidowane |
| Stream Deck Plus | OpenDeck 2.14.1 i klawisz STOP SW z wcześniejszym potwierdzeniem sterownika | podczas audytu po restarcie **brak panelu w USB, usługa restartowała się** |
| Vision Core, ruch autonomiczny, Eye-in-Hand, UPS / automatyczne parkowanie | architektura i plany etapów | **niezatwierdzone jako produkcyjny system** |

Powyższa tabela przedstawia datowany audyt, a nie bieżącą telemetrię online. W szczególności **STOP programowy nie zastępuje niezależnego zabezpieczenia operatora**, a odcięcie zasilania NERO może spowodować opadnięcie ramienia.

## Gdzie znajdują się testy i kod roboczy?

Pełna konsolidacja prac z października i listopada, łącznie z testami Sony, STM32, skryptami GPU/NPU, referencyjnym kodem NERO/OpenDeck, raportami Thermal i dowodami, pozostaje na osobnej gałęzi:

- [PR #15 — integracyjny punkt odniesienia całego projektu](https://github.com/autoklinika/Vision/pull/15).
- [Zamrożony commit pełnego snapshotu](https://github.com/autoklinika/Vision/tree/34181a6206918dce91021dce3286a221f6e32058).

Kod eksperymentalny, testy urządzeń i niezatwierdzone konfiguracje **nie są scalane do `main`** tylko dlatego, że działały w laboratorium. Zostają w swoich gałęziach i w archiwum na NVMe. Zamrożone źródła Thermal, zewnętrzne SDK, duże obrazy, prywatne sesje i sekrety nie trafiają do publicznego GitHuba.

## Zasady bezpieczeństwa i procesu

1. **`main` to wiarygodna, zatwierdzona baza**, a nie automatyczny obraz aktualnego systemu lub kompletna dystrybucja oprogramowania.
2. Moduły wprowadzamy do `main` po przeglądzie, testach i jawnej zgodzie właściciela. Każda zmiana przez osobną gałąź i PR.
3. Autonomiczny ruch ramienia wymaga odrębnej oceny ryzyka i niezależnych zabezpieczeń; kamera głębi i algorytmy AI ich nie zastępują.
4. Nie uruchamiamy aktuatorów, migawki, zasilania ani testów na żywym sprzęcie w trakcie zwykłego tworzenia PR.
5. Nie publikujemy kluczy, tokenów, numerów seryjnych, prywatnej adresacji, surowych zdjęć, archiwów i logów laboratoryjnych.

Historia wcześniejszych testów: [weryfikacja VENTUNO Q](docs/hardware/VENTUNO_Q_HARDWARE_VERIFICATION_2026-10-10.md), [weryfikacja Sony A6100](docs/hardware/SONY_A6100_VERIFICATION_2026-10-10.md), [proces rozwoju](docs/process/DEVELOPMENT.md).
