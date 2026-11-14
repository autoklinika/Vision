# Vision — stanowisko inspekcji PCB / ECU

> **Nowy fundament Vision (ustalenia 14.11.2026, PR dokumentacyjny):** [założenia nowego systemu](docs/architecture/VISION_FOUNDATION_2026-11-14.md) i [archiwum rozmowy architektonicznej](docs/architecture/VISION_ARCHITECTURE_DISCUSSION_2026-11-14.md). Vision budujemy od podstaw, operator deklaruje ECU, a moduły i modele są wymienne. Pierwszy scenariusz dotyczy **ETC3 z dwiema czarnymi i jedną szarą wtyczką**, nie DAF SAC. Szczegóły wykonawcze pozostają do walidacji. Historyczne dokumenty niżej zachowują swoje oryginalne daty i statusy.

Projekt stanowiska fotograficzno-inspekcyjnego opartego na **Arduino VENTUNO Q** (Ubuntu ARM64), aparacie Sony A6100, kamerze termowizyjnej i ramieniu **AgileX NERO**.

**Stan dokumentacji na 10.11.2026:** `main` jest **zatwierdzoną bazą architektury, decyzji i statusów**, a nie kompletną działającą aplikacją Vision Core. Stan urządzeń jest zmienny; raport AS-BUILT jest datowaną fotografią konfiguracji i wyników testów.

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
