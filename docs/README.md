# Dokumentacja Vision — indeks

**Punkt wejścia aktualny 25.11.2026.** Dokumenty z wcześniejszych dat zachowują własny status i zakres; nie są aktualną telemetrią. [README projektu](../README.md) zawiera bieżący przegląd.

## Decyzje i obowiązujące kontrakty

| Dokument | Status |
| --- | --- |
| [Fundament Vision, 14.11](architecture/VISION_FOUNDATION_2026-11-14.md) | zaakceptowany kierunek greenfield / ETC3-first; późniejsze ADR rozstrzygają szczegóły |
| [ADR Core — hardware independence](architecture/ADR_VISION_CORE_HARDWARE_INDEPENDENCE_2026-11-23.md) | ACCEPTED |
| [Workflow V1 S01–S11](workflows/VISION_INSPECTION_WORKFLOW_V1.md) | PRELIMINARILY ACCEPTED, szczegóły podczas implementacji |
| [ADR ECU Reference Profile V1](decisions/ADR_VISION_ECU_REFERENCE_PROFILE_V1_2026-11-24.md) | ACCEPTED |
| [ADR WebGUI client-only](decisions/ADR_VISION_WEBGUI_CLIENT_ONLY_2026-11-24.md) | ACCEPTED |
| [ADR dwustopniowego STOP NERO](architecture/ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md) | ACCEPTED architektura; nie potwierdzenie pełnego wdrożenia |
| [ADR Station LAB/PROD](architecture/ADR_VISION_PORTABLE_STATION_LAB_PROD_2026-11-16.md) | PROPOSED |
| [ADR Sony staged acquisition](architecture/ADR_SONY_STAGED_ACQUISITION_2026-10-13.md) | PROPOSED |

## Implementacja i UX

- Core: [001 Foundation](implementation/VISION_CORE_001_FOUNDATION.md), [002 Photography](implementation/VISION_CORE_002_PHOTOGRAPHY.md), [003 Repeatability](implementation/VISION_CORE_003_REPEATABLE_INSPECTION.md), [004 Extensions](implementation/VISION_CORE_004_MODULAR_EXTENSIONS.md).
- ECU: [specyfikacja 15 sekcji](architecture/ECU_REFERENCE_PROFILE_V1_SPECIFICATION.md), [szablon](templates/ECU_REFERENCE_PROFILE_V1_TEMPLATE.json), [ECU Profiles](implementation/VISION_ECU_PROFILES_V1.md), [Reference Profile](implementation/VISION_ECU_REFERENCE_PROFILE_V1_IMPLEMENTATION.md), [Library Backend](implementation/VISION_ECU_LIBRARY_BACKEND_V1.md), [ETC3 PoC — DRAFT](profiles/ETC3_POC_V1_PL.md).
- Runtime: [S01–S04](implementation/VISION_RUNTIME_V1_S01_S04.md), [ROS 2 Luxonis adapter](implementation/VISION_RUNTIME_ROS2_LUXONIS_ADAPTER_V1.md).
- Planner: [S05–S06](implementation/VISION_INSPECTION_PLANNER_V1_S05_S06.md).
- [Thermal Inspection V1](implementation/VISION_THERMAL_INSPECTION_V1.md).
- WebGUI: [specyfikacja V1](ux/VISION_WEBGUI_V1_SPECIFICATION.md), [biblioteka i edytor ECU](ux/ECU_LIBRARY_SELECTION_EDITOR_V1.md), [kod i instrukcja](../webgui/README.md). GUI-01/02, API-01–03 i stanowiskowy Core/GUI są w main; edytor i obsługa urządzeń pozostają odrębnymi pakietami.
- API: [Foundation](implementation/VISION_API_FOUNDATION_V1.md), [Core reports](implementation/VISION_API_CORE_REPORTS_V1.md), [ECU Library read](implementation/VISION_API_ECU_LIBRARY_READ_V1.md), [Station WebGUI](implementation/VISION_STATION_WEBGUI_V1.md), [deployment](operations/VISION_WEBGUI_DEPLOYMENT.md), [kontrakt API](../contracts/vision-api/v1/README.md).

## Odbiory i kalibracja

- [Zamrożony VGP V1, 23.11](baselines/VISION_GUIDED_POSITIONING_V1_2026-11-23.md).
- [Station Calibration V1](calibration/VISION_STATION_CALIBRATION_V1.md), [checklista pomiarów](calibration/MEASUREMENT_CHECKLIST_V1.md).
- [Audyt Core](audits/VISION_CORE_INTEGRATION_AUDIT_2026-11-23.md), [Core 004/Thermal](audits/VISION_CORE_004_THERMAL_PREMERGE_AUDIT.md).
- [ECU Profiles](audits/VISION_ECU_PROFILES_V1_AUDIT_2026-11-24.md), [Reference Profile](audits/VISION_ECU_REFERENCE_PROFILE_V1_PREMERGE_AUDIT_2026-11-24.md), [Library Backend](audits/VISION_ECU_LIBRARY_BACKEND_V1_AUDIT_2026-11-24.md).
- [Runtime](audits/VISION_RUNTIME_V1_FINAL_AUDIT_2026-11-24.md), [odczyt Luxonis](audits/VISION_RUNTIME_LUXONIS_LIVE_READONLY_ACCEPTANCE_2026-11-24.md), [Planner](audits/VISION_INSPECTION_PLANNER_V1_AUDIT_2026-11-24.md), [symulacja MoveIt](audits/VISION_INSPECTION_PLANNER_MOVEIT_SIMULATION_2026-11-24.md), [wspólny audyt Runtime/Planner](audits/VISION_RUNTIME_PLANNER_FINAL_AUDIT_2026-11-24.md).
- [GUI-01](../webgui/docs/audit/GUI-01_AUDIT_2026-11-24.md), [GUI-02 końcowy odbiór](../webgui/docs/audit/GUI-02_FINAL_ACCEPTANCE_2026-11-24.md). Historyczne odbiory izolowanego klienta. Nowsze odbiory stanowiskowe: [#63](https://github.com/autoklinika/Vision/pull/63), [#65](https://github.com/autoklinika/Vision/pull/65), [#68](https://github.com/autoklinika/Vision/pull/68), [#70](https://github.com/autoklinika/Vision/pull/70). Aktywna inspekcja i sprzęt pozostają osobnymi bramkami.

## Proces i stan prac

- [Mapa kodu](../src/README.md), [testy](../tests/README.md).
- [Repository Hygiene V1](process/REPOSITORY_HYGIENE_V1.md), [Development](process/DEVELOPMENT.md).
- [Aktualny rejestr repozytorium 25.11](operations/REPOSITORY_REGISTER_2026-11-25.md); [snapshot 24.11](operations/REPOSITORY_REGISTER_2026-11-24.md) — historyczny.
- [Przegląd PR z 23.11](operations/OPEN_PR_PORTFOLIO_2026-11-23.md) jest historycznym punktem odniesienia, nie bieżącą listą.

## Materiały historyczne

- [OVERVIEW v0.1](architecture/OVERVIEW.md) — architektura 10.10, zastąpiona fundamentem i późniejszymi ADR.
- [Zapis dyskusji architektonicznej](architecture/VISION_ARCHITECTURE_DISCUSSION_2026-11-14.md), [raport ROS 2 / LAB–PROD 16.11](architecture/VISION_ROS2_NERO_LAB_TO_PROD_TECHNICAL_REPORT_2026-11-16.md).
- [AS-BUILT 10.11](operations/VISION_AS_BUILT_2026-11-10.md), [Open Items 10.11](operations/OPEN_ITEMS_2026-11-10.md), [Release Gates 10.11](operations/RELEASE_GATES_2026-11-10.md) — zachować daty; w razie sprzeczności nowsze zaakceptowane ADR i odbiory rozstrzygają zakres.
- [VENTUNO 10.10](hardware/VENTUNO_Q_HARDWARE_VERIFICATION_2026-10-10.md), [Sony 10.10](hardware/SONY_A6100_VERIFICATION_2026-10-10.md), [Evidence Register](hardware/EVIDENCE_REGISTER_2026-10-10.md), [Integration Plan](hardware/INTEGRATION_PLAN.md), [VENTUNO baseline](hardware/VENTUNO_Q_BASELINE.md).
- [Historyczna instrukcja audytu stanowiska](audits/README.md), [snapshot #15](https://github.com/autoklinika/Vision/pull/15), [README przed uporządkowaniem](https://github.com/autoklinika/Vision/blob/4bb088186eb06a40ab9fd2e96072551d318a2d90/README.md).

Nie przenosić raportów, testów fizycznych i prywatnych profili do nowej architektury bez osobnego przeglądu. Raw RGB/Depth/PointCloud, szczegółowa kalibracja, logi, sekrety oraz prywatne assety pozostają poza publicznym Git.
