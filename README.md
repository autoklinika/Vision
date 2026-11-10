# Vision — stanowisko inspekcji PCB / ECU

**Aktualizacja stanu faktycznego: 2026-11-10.** Projekt działa na Arduino VENTUNO Q (Qualcomm QCS8275, Ubuntu 24.04 ARM64) z NVMe `/srv/vision-data`. To **integracyjne repozytorium kodu, dokumentacji i testów**; nie oznacza jeszcze istnienia jednego ukończonego Vision Core ani dopuszczenia autonomicznych ruchów robota.

> **Najważniejsze:** sprawdzone moduły nie są równoznaczne z gotowością całego stanowiska. Każda funkcja ma własny stan TEST / PASS / FROZEN / BLOCKED. Faktyczne wyniki dotyczą konkretnych sesji opisanych w raportach. `main` nie aktualizuje automatycznie usług na VENTUNO.

## Ostatni audyt rzeczywistego urządzenia

- [Stan aktualny / AS-BUILT 2026-11-10](docs/operations/VISION_AS_BUILT_2026-11-10.md) — fakty, testy, stan usług oraz rozbieżności.
- [Problemy otwarte i bramki integracji](docs/operations/OPEN_ITEMS_2026-11-10.md) — priorytety i warunki dalszych testów.
- [Zakres konsolidacji i manifest źródeł](docs/operations/SYNC_MANIFEST_2026-11-10.md) — pochodzenie plików, wyłączenia i bezpieczeństwo publikacji.

| Moduł | Potwierdzone osiągnięcie | Stan na dzień audytu |
|---|---|---|
| VENTUNO Q + NVMe | Ubuntu 24.04.4; NVMe ext4; GPU/NPU ocenione w wyodrębnionych testach | platforma czynna; Hardware Baseline v1 wciąż otwarty |
| Sony A6100 | HDMI, Wi-Fi, USB PTP/RAW+JPEG i BLE ocenione w testach; różne tryby mają ograniczenia | eksperymenty udokumentowane; brak zintegrowanej produkcyjnej akwizycji |
| Vision Thermal InfiRay T2S+ | aplikacja webowa DEV v0.6, 3 ROI, historia, obrót, radiometria surowa | **DEV FROZEN**, źródła prywatne; temperatura w °C **NOT VALIDATED** |
| AgileX NERO 7-DOF | SDK pyAgxArm 1.0.0, CAN 1 Mb/s, firmware 1.22, odczyt 7 przegubów | komunikacja przetestowana; ruch robota niezatwierdzony |
| Stream Deck Plus | OpenDeck 2.14.1 i prawy dolny STOP SW; sterownik NERO potwierdził `EMERGENCY_STOP(0x1)` | **po restarcie USB Stream Deck niewykryte**; usługa w pętli restartów |
| STOP / UPS | ADR dwustopniowego zatrzymania i odrębnego scenariusza zaniku zasilania | **etap 1 częściowo wdrożony**, brak globalnego interlocka i niezależnego E-STOP |
| Vision Core / autonomiczna inspekcja | architektura modułowa, prototypy i raporty | **brak finalnej aplikacji produkcyjnej** |

## Architektura i najważniejsze decyzje

- [Architektura logiczna Vision](docs/architecture/OVERVIEW.md): akwizycja, jakość, termowizja, robot i eksport do oddzielnej AI Platform.
- [ADR-VISION-ROBOT-001 — NERO STOP](docs/architecture/ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md): etap 1 STOP programowy na Stream Deck, etap 2 przycisk GPIO; jasno określone ograniczenia bezpieczeństwa.
- [ADR Sony — HDMI + Wi-Fi + import z SD](docs/architecture/ADR_SONY_STAGED_ACQUISITION_2026-10-13.md): **PROPOSED**, nie wdrożenie.
- [Polityka NVMe](docs/architecture/STORAGE_POLICY.md), [fail-closed write guard](docs/architecture/NVME_ENFORCEMENT.md).
- [Proces zmian i zgody na aktywowanie urządzeń](docs/process/DEVELOPMENT.md).

## Fotografia, BLE, kamera głębi, robot

- [Sony HDMI/Wi-Fi](docs/hardware/SONY_A6100_HDMI_WIFI_VERIFICATION_2026-10-13.md), [Sony multitransport / SD](docs/hardware/SONY_A6100A_MULTITRANSPORT_VERIFICATION_2026-10-13.md), [audyt protokołów](docs/audits/SONY_PROTOCOL_ARCHITECTURE_AUDIT_2026-10-13.md).
- [AF przed migawką](docs/hardware/SONY_AF_BEFORE_SHUTTER_PROTOTYPE_2026-10-13.md), [BLE i zoom](docs/hardware/SONY_BLE_ZOOM_AF_TEST_2026-10-13.md), [stabilność 100 zdjęć](docs/hardware/SONY_STABILITY_100_REAL_RUN_RESULTS_2026-10-14.md).
- [Stream Deck + Sony — testy HID/GUI](docs/hardware/STREAM_DECK_SONY_BLE_TESTS_2026-10-12.md).
- [STM32, CSI i wbudowany CAN VENTUNO](docs/hardware/VENTUNO_Q_STM32_CSI_CAN_READONLY_2026-10-11.md).
- [Eksperymentalny skrypt diagnostyczny NERO](scripts/robot/nero_sdk_readonly_probe.py), [odwzorowanie STOP SW](ops/nero/nero_stop.py), [OpenDeck — konfiguracja referencyjna](ops/streamdeck/README.md).
- [Archiwum autorskich narzędzi eksperymentalnych](scripts/experiments/README.md): Sony/PTP, Stream Deck/GUI/BLE, GPU i NPU — kod zanonimizowany, nieuruchamiany automatycznie.

## Termowizja i granica publikacji

- [Raport zamrożenia Vision Thermal v0.6](docs/audits/VISION_THERMAL_V06_FREEZE_2026-10-15_PL.md).
- [Przekazanie źródeł prywatnych](docs/audits/VISION_THERMAL_V06_PRIVATE_SOURCE_HANDOFF_2026-10-15_PL.md).

Pełny kod, archiwa, zależności licencyjne i pomiary laboratoryjne Thermal pozostają **wyłącznie lokalnie na NVMe**. Publiczne repo przechowuje tylko udokumentowane wyniki, nie prywatne archiwa.

## Zasady repozytorium

1. `main` stanowi referencję zaakceptowaną przez właściciela. Nowe zmiany przechodzą przez osobne gałęzie i PR. **Brak automatycznego merge.**
2. Nie commitujemy numerów seryjnych, sekretów, adresów sieci prywatnej, surowych logów, zdjęć, plików RAW, baz, kontenerów ani binarnych SDK.
3. Testy hardware i każde rzeczywiste uruchomienie aktuatorów wymagają osobnej zgody i spełnienia wymagań bezpieczeństwa.
4. Skrypty i profile w `ops/` opisują stan wdrożenia w sposób **zanonimizowany i przenośny**. Nie są automatycznie uruchamiane po checkout.
5. SDK firm trzecich i środowiska runtime są instalowane niezależnie. Ten Git nie jest kopią kompletnego dysku NVMe.
