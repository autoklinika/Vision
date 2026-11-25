# Vision — rejestr repozytorium po integracji Core ↔ GUI

**Snapshot 25.11.2026:** main [`6c5f1391`](https://github.com/autoklinika/Vision/tree/6c5f1391b4f7242393246bbb306baf342ba21d80), przed aktualizacją PR #56. Rejestr opisuje stan Git, nie telemetrię sprzętu. Poprzedni snapshot [24.11](REPOSITORY_REGISTER_2026-11-24.md) pozostaje historyczny.

## Wynik porządkowania

- 63 gałęzie; przed porządkowaniem 9 otwartych PR, po porządkowaniu 2. Wszystkie gałęzie zachowane; bez force-push, kasowania kodu lub historii.
- #56: wyłącznie dokumentacja i rejestr, aktualizowany względem bieżącego main.
- #51: odrębny draft LAB dotyczący lokalizacji ETC3; baza #50 jest scalona. Przed integracją minimalny diff od main, osobna weryfikacja transformacji i zaufanych dowodów. S03/S04 nadal NOT_READY.
- Zamknięto bez merge #2–4, #11–13 i #31, każdy z komentarzem i odsyłaczem do nowego zadania. Nie jest to akceptacja brakujących testów ani rezygnacja z funkcji.

## Backlog zamiast historycznych stosów PR

| Issue | Materiał | Zakres |
| --- | --- | --- |
| [#71](https://github.com/autoklinika/Vision/issues/71) | #11–13 | Sony, AF/BLE/RAW+JPEG/stabilność, selektywny adapter |
| [#72](https://github.com/autoklinika/Vision/issues/72) | #2–4 | NVMe / Remote MCP — audyt aktualnej infrastruktury |
| [#73](https://github.com/autoklinika/Vision/issues/73) | #31 | Replay First, RGB-D, walidacja danych |

## Punkt odniesienia wdrożenia (stan odczytany 25.11)

Core i WebGUI są niezależnymi usługami. Core release `dede6dd2` (#65), GUI/API release `44cecff5` (#70). Rozdzielenie wersji jest zamierzone. Core CONNECTED / NO_ACTIVE_SESSION / UNKNOWN, biblioteka ETC3 DRAFT / NOT_READY. Lokalny main zsynchronizowany fast-forward z GitHub; procesy Core/GUI nie były restartowane. Testy audytu: 34/34 Core Host + Station API, zapisany odbiór ostatniego wydania 12/12 CI, 51 jednostkowych GUI, 10 Firefox i 10 Chromium. Aktualny odczyt IPC i autoryzacja endpointów potwierdzone; nie wykonano rzeczywistej aktywnej inspekcji ani nowego logowania na koncie produkcyjnym. Publiczny status boot nie jest raportem Core. Okna sprzętowe są placeholderami.

Dalszy rozwój od aktualnego main, pojedyncze PR, bez zmian działającego stanowiska w ramach repo hygiene. [Zasady](../process/REPOSITORY_HYGIENE_V1.md). Starych worktree, prywatnych danych, wydań i rollbacków nie kasować bez osobnej weryfikacji zależności i retencji.

## Ewidencja 63 gałęzi (snapshot)

M = merged PR, O = open, A = closed without merge. Klasyfikacja nie stanowi dowodu równoważności drzew po squash merge ani zgody na usuwanie refs. Pełne SHA zachowane jako linki. Head #56 i main zmienią się po publikacji tej aktualizacji.

| Gałąź | SHA | PR | Kategoria |
| --- | --- | --- | --- |
| `audit/ventuno-baseline-20261010` | [`68a3b3acd390`](https://github.com/autoklinika/Vision/tree/68a3b3acd390ac7edb64bf44e422ce50310011c3) | [#1](https://github.com/autoklinika/Vision/pull/1) A | ARCHIWUM |
| `chore/nvme-user-data-policy-20261010` | [`067de48fd034`](https://github.com/autoklinika/Vision/tree/067de48fd034ca490d46a85afdb0b2f676358f37) | [#2](https://github.com/autoklinika/Vision/pull/2) A | ARCHIWUM — [#72](https://github.com/autoklinika/Vision/issues/72) |
| `chore/vision-remote-mcp-autostart` | [`38669e5a7d3b`](https://github.com/autoklinika/Vision/tree/38669e5a7d3b50a8f7585f6b169d1e976c2635f5) | [#4](https://github.com/autoklinika/Vision/pull/4) A | ARCHIWUM — [#72](https://github.com/autoklinika/Vision/issues/72) |
| `codex/api03-ecu-library-read` | [`26de647bfa07`](https://github.com/autoklinika/Vision/tree/26de647bfa07eb02e074c9dbe4f63a48b7853c6f) | [#61](https://github.com/autoklinika/Vision/pull/61) M | PO MERGE |
| `codex/firefox-auth-origin` | [`44cecff5aaf9`](https://github.com/autoklinika/Vision/tree/44cecff5aaf9fefd81b92f824da800ab6c4cda9c) | [#70](https://github.com/autoklinika/Vision/pull/70) M | PO MERGE |
| `codex/gui-core-connection` | [`dede6dd2dcf8`](https://github.com/autoklinika/Vision/tree/dede6dd2dcf8e324988c53b77d8e641e387f58d3) | [#65](https://github.com/autoklinika/Vision/pull/65) M | PO MERGE |
| `codex/gui-station-deployment` | [`233dca08fbb3`](https://github.com/autoklinika/Vision/tree/233dca08fbb306284f6ff756832a857ead87b2f9) | [#63](https://github.com/autoklinika/Vision/pull/63) M | PO MERGE |
| `codex/settings-password-change` | [`3cd8b9903237`](https://github.com/autoklinika/Vision/tree/3cd8b9903237efaff19c17d75ab9ff7320325073) | [#68](https://github.com/autoklinika/Vision/pull/68) M | PO MERGE |
| `docs/adr-camera-perception-core-boundaries-20261112` | [`f8d1ec8a0788`](https://github.com/autoklinika/Vision/tree/f8d1ec8a0788578582477bf10994854b3164f7b3) | [#21](https://github.com/autoklinika/Vision/pull/21) A | ARCHIWUM |
| `docs/adr-core-mandatory-step-gates-20261123` | [`bef2791559f1`](https://github.com/autoklinika/Vision/tree/bef2791559f1b7c7ee299469298676cebeac010c) | [#38](https://github.com/autoklinika/Vision/pull/38) M | PO MERGE |
| `docs/adr-nero-two-stage-stop-20261110` | [`4f5b8bbc0c7b`](https://github.com/autoklinika/Vision/tree/4f5b8bbc0c7b69a1384d5118bbbd6c2848ae4a71) | [#14](https://github.com/autoklinika/Vision/pull/14) A | ARCHIWUM |
| `docs/adr-vision-core-hardware-independence-20261123` | [`a59f8cdaf95e`](https://github.com/autoklinika/Vision/tree/a59f8cdaf95e8a0c9964befcddda432a2e6e4c40) | [#37](https://github.com/autoklinika/Vision/pull/37) M | PO MERGE |
| `docs/adr-vision-ros2-foundation-20261114` | [`1361dc6e1eb8`](https://github.com/autoklinika/Vision/tree/1361dc6e1eb813bc9d020bb660e9db472be72ee9) | [#27](https://github.com/autoklinika/Vision/pull/27) A | ARCHIWUM |
| `docs/ecu-reference-profile-v1-accepted` | [`71c325b85eed`](https://github.com/autoklinika/Vision/tree/71c325b85eede3db0d501e865f739ea11fe070bd) | [#47](https://github.com/autoklinika/Vision/pull/47) M | PO MERGE |
| `docs/hardware-verification-20261010` | [`30d60ebcb86c`](https://github.com/autoklinika/Vision/tree/30d60ebcb86ce7afc54b66a355dcb30310873ef9) | [#5](https://github.com/autoklinika/Vision/pull/5) M, [#7](https://github.com/autoklinika/Vision/pull/7) A | MIESZANA — ZACHOWAĆ |
| `docs/oak-d-pro-af-bringup-20261110` | [`97ec69dd7df1`](https://github.com/autoklinika/Vision/tree/97ec69dd7df1ab762ed6ea85da934da06acc7878) | [#17](https://github.com/autoklinika/Vision/pull/17) A | ARCHIWUM |
| `docs/repository-hygiene-20261124` | [`2f9b00b111c1`](https://github.com/autoklinika/Vision/tree/2f9b00b111c1cc1ba5b066729b95eb12575c4d84) | [#56](https://github.com/autoklinika/Vision/pull/56) O | AKTYWNY PR (snapshot przed aktualizacją) |
| `docs/ros2-lab-production-vision-20261116` | [`994ab7b7bf20`](https://github.com/autoklinika/Vision/tree/994ab7b7bf20c83fa6bf73c6fdefe8a9a807ca02) | [#30](https://github.com/autoklinika/Vision/pull/30) M | PO MERGE |
| `docs/scn-001-etc3-20261114` | [`74210bedb42a`](https://github.com/autoklinika/Vision/tree/74210bedb42a0d70f9ab417cf605b6640966dc58) | [#29](https://github.com/autoklinika/Vision/pull/29) A | ARCHIWUM |
| `docs/sony-a6100-hdmi-wifi-20261013` | [`7a1f7b0972bd`](https://github.com/autoklinika/Vision/tree/7a1f7b0972bd7e092b235fef6cfaff4e3b2c78a8) | [#9](https://github.com/autoklinika/Vision/pull/9) A | ARCHIWUM |
| `docs/sony-a6100a-hdmi-wifi-usb-20261013` | [`3a110cd47fc9`](https://github.com/autoklinika/Vision/tree/3a110cd47fc9db813c87bfbf6bec1acf6d0c58b1) | [#8](https://github.com/autoklinika/Vision/pull/8) A | ARCHIWUM |
| `docs/sony-protocol-audit-20261013` | [`f397161d4578`](https://github.com/autoklinika/Vision/tree/f397161d4578c027dfe8a156755388c057e4d726) | [#10](https://github.com/autoklinika/Vision/pull/10) A | ARCHIWUM |
| `docs/ventuno-stm32-csi-can-20261011` | [`f9108a0c4376`](https://github.com/autoklinika/Vision/tree/f9108a0c4376914a9548f12b71cec53fa610c270) | [#6](https://github.com/autoklinika/Vision/pull/6) A | ARCHIWUM |
| `docs/vision-approved-baseline-20261110` | [`dfc9a788eefc`](https://github.com/autoklinika/Vision/tree/dfc9a788eefcb54f044880e510ff8bac48119bd0) | [#16](https://github.com/autoklinika/Vision/pull/16) M | PO MERGE |
| `docs/vision-foundation-20261114` | [`efd6cf9e6c9f`](https://github.com/autoklinika/Vision/tree/efd6cf9e6c9f5745cc785f9fa4d2fe95c3dafdec) | [#28](https://github.com/autoklinika/Vision/pull/28) M | PO MERGE |
| `docs/vision-thermal-v06-freeze-20261015` | [`77d6fc8b0dfd`](https://github.com/autoklinika/Vision/tree/77d6fc8b0dfd23b2d9c9819d01324309b9d20ce0) | — | BEZ PR — TRIAGE |
| `docs/vision-uh720-streamdeck-20261110` | [`66638f0f7359`](https://github.com/autoklinika/Vision/tree/66638f0f7359d29d68f70498407b322a35018c7a) | [#18](https://github.com/autoklinika/Vision/pull/18) A | ARCHIWUM |
| `docs/webgui-architecture-20261124` | [`3c55daf2ae15`](https://github.com/autoklinika/Vision/tree/3c55daf2ae15a3c683273870e15aa2339a47b901) | [#53](https://github.com/autoklinika/Vision/pull/53) M | PO MERGE |
| `experiment/vision-etc3-rgbd-localization-v1` | [`14b5215cf140`](https://github.com/autoklinika/Vision/tree/14b5215cf140f2946f990e681f13bb4b0e20ac81) | [#51](https://github.com/autoklinika/Vision/pull/51) O | OTWARTY DRAFT |
| `feat/vision-api-core-reports-v1` | [`8240cfad4359`](https://github.com/autoklinika/Vision/tree/8240cfad435943e76cb475d1e1f3e4a122a4f05d) | [#59](https://github.com/autoklinika/Vision/pull/59) M | PO MERGE |
| `feat/vision-api-foundation-v1` | [`b4c35f997091`](https://github.com/autoklinika/Vision/tree/b4c35f997091a7659243ad00ce0f8a59e0d83ae6) | [#57](https://github.com/autoklinika/Vision/pull/57) M | PO MERGE |
| `feat/vision-core-001-foundation` | [`d90902c431c1`](https://github.com/autoklinika/Vision/tree/d90902c431c1073c19382c7605b9b4945a72ad95) | [#39](https://github.com/autoklinika/Vision/pull/39) M | PO MERGE |
| `feat/vision-core-002-photography` | [`132f838e7ecf`](https://github.com/autoklinika/Vision/tree/132f838e7ecff1992b0cb9a8428aaffefc32c02d) | [#40](https://github.com/autoklinika/Vision/pull/40) M | PO MERGE |
| `feat/vision-core-003-repeatable-inspection` | [`83abf1c470cd`](https://github.com/autoklinika/Vision/tree/83abf1c470cd6c566b5c637188af49c3cd82b56e) | [#41](https://github.com/autoklinika/Vision/pull/41) M | PO MERGE |
| `feat/vision-core-004-extensibility-foundation` | [`05073a3aa8b5`](https://github.com/autoklinika/Vision/tree/05073a3aa8b50b2edb88eccfd65a5a6148d76848) | [#43](https://github.com/autoklinika/Vision/pull/43) M | PO MERGE |
| `feat/vision-core-004-thermal-premerge-hardening` | [`6df7ff88d000`](https://github.com/autoklinika/Vision/tree/6df7ff88d000716ab155a0437e47ae3a8c2a27d5) | [#45](https://github.com/autoklinika/Vision/pull/45) M | PO MERGE |
| `feat/vision-core-integration-hardening-v1` | [`6aa19648ad74`](https://github.com/autoklinika/Vision/tree/6aa19648ad74c6ddcc9dd4605b2a0049d9ad98b2) | [#42](https://github.com/autoklinika/Vision/pull/42) M | PO MERGE |
| `feat/vision-ecu-library-backend-v1` | [`31027b45fb94`](https://github.com/autoklinika/Vision/tree/31027b45fb94ec95f277b772ef6eb004cb32f05d) | [#49](https://github.com/autoklinika/Vision/pull/49) M | PO MERGE |
| `feat/vision-ecu-profile-catalog-v1` | [`06a452b3b5d1`](https://github.com/autoklinika/Vision/tree/06a452b3b5d1a4435c05bd30f642cde8f018e5ba) | [#46](https://github.com/autoklinika/Vision/pull/46) M | PO MERGE |
| `feat/vision-ecu-reference-profile-v1` | [`e4cbb1eadd50`](https://github.com/autoklinika/Vision/tree/e4cbb1eadd50207c019a50f615f0585201e4c170) | [#48](https://github.com/autoklinika/Vision/pull/48) M | PO MERGE |
| `feat/vision-inspection-planner-v1-s05-s06` | [`b929909de4d0`](https://github.com/autoklinika/Vision/tree/b929909de4d0fd183acb928cbad7437dda65a2ba) | [#52](https://github.com/autoklinika/Vision/pull/52) M | PO MERGE |
| `feat/vision-runtime-v1-s01-s04` | [`d02a58c93d30`](https://github.com/autoklinika/Vision/tree/d02a58c93d309408b001cc3ff7929b482eb0ca9c) | [#50](https://github.com/autoklinika/Vision/pull/50) M | PO MERGE |
| `feat/vision-thermal-inspection-v1` | [`22bb917f9e09`](https://github.com/autoklinika/Vision/tree/22bb917f9e09ee07333f33195cd5d3823097a322) | [#44](https://github.com/autoklinika/Vision/pull/44) M | PO MERGE |
| `feat/webgui-desktop-v1` | [`f7c4c3890e39`](https://github.com/autoklinika/Vision/tree/f7c4c3890e39bbeb69a31d86a5dbe90af1819220) | [#54](https://github.com/autoklinika/Vision/pull/54) M | PO MERGE |
| `feat/webgui-startup-v1` | [`d53312444972`](https://github.com/autoklinika/Vision/tree/d533124449722e5917625fb0271335100dc46929) | [#55](https://github.com/autoklinika/Vision/pull/55) M | PO MERGE |
| `feature/c7-v1-ik-perception-20261120` | [`697a295c5984`](https://github.com/autoklinika/Vision/tree/697a295c598499fcd797b4798889133a3a2a4b13) | [#34](https://github.com/autoklinika/Vision/pull/34) A | ARCHIWUM |
| `feature/c7-v1-planonly-20261120` | [`ef33ca1f230f`](https://github.com/autoklinika/Vision/tree/ef33ca1f230fa6530649e44d38c03225bc003ce8) | [#33](https://github.com/autoklinika/Vision/pull/33) A | ARCHIWUM |
| `feature/c8-nero-follow-action-lab-20261120` | [`8a09670e787c`](https://github.com/autoklinika/Vision/tree/8a09670e787ca765385ec9dbd13b85e2b6312fac) | [#35](https://github.com/autoklinika/Vision/pull/35) A | ARCHIWUM |
| `feature/nvme-write-guard-v1` | [`6dfdf1fc8885`](https://github.com/autoklinika/Vision/tree/6dfdf1fc8885e3c142c0642b5b65606ca8c7b619) | [#3](https://github.com/autoklinika/Vision/pull/3) A | ARCHIWUM — [#72](https://github.com/autoklinika/Vision/issues/72) |
| `feature/oak-browser-preview-20261112` | [`18bdc3b73875`](https://github.com/autoklinika/Vision/tree/18bdc3b73875c45c1d3f303015649b4e5620cdff) | [#19](https://github.com/autoklinika/Vision/pull/19) A | ARCHIWUM |
| `feature/oak-camera-service-production-20261112` | [`97f276287fed`](https://github.com/autoklinika/Vision/tree/97f276287fed1df6afc6e04cbd4971fc1fde106d) | [#20](https://github.com/autoklinika/Vision/pull/20) A | ARCHIWUM |
| `feature/oak-luxonis-native-20261113` | [`a09b2be1fa3b`](https://github.com/autoklinika/Vision/tree/a09b2be1fa3b977fc135791a918b91db807cb6e4) | [#25](https://github.com/autoklinika/Vision/pull/25) A | ARCHIWUM |
| `feature/oak-optics-ir-af-roi-20261113` | [`c2cbd400e583`](https://github.com/autoklinika/Vision/tree/c2cbd400e5836e6de4c56221a825af4f988e4901) | [#23](https://github.com/autoklinika/Vision/pull/23) A | ARCHIWUM |
| `feature/oak-rgbd-sync-perception-v1-20261112` | [`2ffcfccea225`](https://github.com/autoklinika/Vision/tree/2ffcfccea225e87b527ad51f4a356cea107083b0) | [#22](https://github.com/autoklinika/Vision/pull/22) A | ARCHIWUM |
| `feature/perception-auto-top-face-20261113` | [`0f9c827f8faa`](https://github.com/autoklinika/Vision/tree/0f9c827f8faa5e5983784db3587dafecc25cca99) | [#26](https://github.com/autoklinika/Vision/pull/26) A | ARCHIWUM |
| `feature/perception-parallel-plane-height-20261113` | [`5ba704baa060`](https://github.com/autoklinika/Vision/tree/5ba704baa060f33ea648a37cea6a79a154a9ef8e) | [#24](https://github.com/autoklinika/Vision/pull/24) A | ARCHIWUM |
| `feature/replay-first-capture-gate-20261118` | [`f91d96d22f79`](https://github.com/autoklinika/Vision/tree/f91d96d22f790024591453f926b9eb4d2a5cf3d7) | [#31](https://github.com/autoklinika/Vision/pull/31) A | ARCHIWUM — [#73](https://github.com/autoklinika/Vision/issues/73) |
| `feature/sony-af-before-shutter-prototype-20261013` | [`f08d6292b2ed`](https://github.com/autoklinika/Vision/tree/f08d6292b2edd55c622c77e94276958f7fbdd69b) | [#11](https://github.com/autoklinika/Vision/pull/11) A | ARCHIWUM — [#71](https://github.com/autoklinika/Vision/issues/71) |
| `feature/sony-ble-zoom-af-test-20261013` | [`0b7685908973`](https://github.com/autoklinika/Vision/tree/0b7685908973c11979822722647d8be684bacbc3) | [#12](https://github.com/autoklinika/Vision/pull/12) A | ARCHIWUM — [#71](https://github.com/autoklinika/Vision/issues/71) |
| `feature/sony-stability-50-100-20261014` | [`25f7271e58af`](https://github.com/autoklinika/Vision/tree/25f7271e58af10725e8133db2486f8699e841746) | [#13](https://github.com/autoklinika/Vision/pull/13) A | ARCHIWUM — [#71](https://github.com/autoklinika/Vision/issues/71) |
| `feature/station-profile-v1-20261118` | [`642ecc080182`](https://github.com/autoklinika/Vision/tree/642ecc0801826a02f9aa2dda688a7dbf82a13303) | [#32](https://github.com/autoklinika/Vision/pull/32) M | PO MERGE |
| `main` | [`6c5f1391b4f7`](https://github.com/autoklinika/Vision/tree/6c5f1391b4f7242393246bbb306baf342ba21d80) | — | KANONICZNA |
| `sync/vision-factual-baseline-20261110` | [`34181a620691`](https://github.com/autoklinika/Vision/tree/34181a6206918dce91021dce3286a221f6e32058) | [#15](https://github.com/autoklinika/Vision/pull/15) A | ARCHIWUM |
