# Vision — AS-BUILT / audyt stanu faktycznego, 2026-11-10

**Rodzaj dokumentu:** raport integracyjny po odczycie na urządzeniu `vision` oraz po przeglądzie gałęzi `autoklinika/Vision`.  
**Czas sprawdzenia:** 2026-11-10, około 19:54 UTC.  
**Ważność:** stan punktowy. Po ponownym podłączeniu urządzeń USB lub zmianie usług należy wykonać nowy audyt.  
**Legenda:** `PASS` = potwierdzone w konkretnym teście, `TEST` = prototyp, `FROZEN` = zamrożone, `BLOCKED` = brak wymaganej gotowości, `PLANNED` = niewdrożone, `NOT CHECKED NOW` = brak bieżącej weryfikacji.

## 1. Platforma

| Obszar | Dowód/stan | Ocena |
|---|---|---|
| Komputer | Arduino VENTUNO Q, QCS8275, Ubuntu **24.04.4 LTS ARM64**, kernel **6.8.0-1089-qcom** | PASS — identyfikacja |
| Wolumen użytkownika | `/srv/vision-data` na `/dev/nvme0n1p1`, ext4, montowany RW | PASS — montowanie (nie pełny audyt retencji) |
| Główne repo lokalne | `/srv/vision-data/projects/Vision` na gałęzi `feature/nvme-write-guard-v1`, czyste przed audytem | PASS — stan Git; gałąź nie jest `main` |
| Zdalny agent | `vision-remote-mcp.service` systemd jako konto `arduino`, runtime Node na NVMe | ACTIVE |
| GitHub | `main` opóźniony względem gałęzi roboczych; liczne otwarte PR | Potrzebna konsolidacja |
| Kamera, robot i panel po restarcie | przez USB wykryta płytka Arduino z kanałami CAN; nie wykryto przy tym odczycie urządzeń Sony, AgileX USB-CAN ani Stream Deck Plus | NOT CONNECTED / NOT CHECKED NOW |

Ostatni punkt nie jest dowodem uszkodzenia urządzeń. W poprzednich sesjach zdarzały się problemy z przełącznikiem/koncentratorem USB. Brak enumeracji oznacza **brak bieżącej gotowości urządzenia**, a nie automatycznie błąd SDK.

## 2. Fotografia: Sony A6100

**Udokumentowane próby z 2026-10-10 do 2026-10-14:**
- PTP przez USB: sterowanie, Live View, JPEG 24 MP, RAW+JPEG, stabilność sesji oraz ograniczenia ponawiania zdjęć.
- Czysty podgląd HDMI, przechwytywanie UVC w badanej konfiguracji oraz sterowanie Sony Wi-Fi.
- BLE zoom; testy AF przed zdjęciem, porównanie PTP↔SD i seria 100 zdjęć.
- Docelowy scenariusz **HDMI podgląd + Wi-Fi kontrola + SD magazyn oryginałów + późniejszy import przez USB** zapisano jako **ADR PROPOSED**. Testy poszczególnych kanałów nie dowodzą automatyzacji pełnego cyklu.

**Granica:** brak zatwierdzonego w produkcji Vision Core odpowiadającego za równoczesną, odtwarzalną sesję i bezobsługowe przełączanie Sony USB/Wi-Fi. Skrypty pod `scripts/audit/` mają status laboratoryjny; ich uruchomienie może powodować rzeczywiste zdjęcia lub ruch obiektywu.

Powiązania: `docs/hardware/SONY_A6100A_MULTITRANSPORT_VERIFICATION_2026-10-13.md`, `docs/audits/SONY_PROTOCOL_ARCHITECTURE_AUDIT_2026-10-13.md`, `docs/hardware/SONY_STABILITY_100_REAL_RUN_RESULTS_2026-10-14.md`.

## 3. Vision Thermal v0.6

**Stan:** `DEV FROZEN / FUNCTIONAL PASS (15.10.2026) / NOT PRODUCTION INTEGRATED`.

- Kamera InfiRay T2S+; surowe ramki, podgląd MJPEG; trzy niezależne ROI; obrót 0/90/180/270; historia próbek i zapis danych/manifestów na NVMe.
- W teście zamrożenia odnotowano regresję 8/8 PASS i 128 klatek/5 s (około 25,3 FPS), bez długookresowej gwarancji.
- Wartości stopni C pozostają **NOT VALIDATED** metrologicznie.
- Źródła i archiwa (z komponentem GPL-3.0) pozostają w prywatnym katalogu eksperymentów. Nie kopiujemy ich do publicznego `Vision` bez decyzji licencyjnej.
- Po restarcie aplikacja DEV **nie powinna uruchamiać się automatycznie**. W audycie brak aktywnej produkcyjnej usługi Thermal.

Dowód: `docs/audits/VISION_THERMAL_V06_FREEZE_2026-10-15_PL.md`.

## 4. AgileX NERO i sterowanie ramieniem

**Weryfikacja z 2026-11-09 i 2026-11-10:**
- NERO 7-DOF, firmware **1.22**, właściwy profil `NeroFW.V121` w `pyAgxArm 1.0.0`.
- Zewnętrzny adapter USB-CAN AgileX, bitrate **1 Mb/s**; odczyt pozycji siedmiu przegubów, stanów napędów i komunikacji PASS w poprzedniej sesji.
- Przycisk STOP SW na Stream Deck Plus uruchomił `electronic_emergency_stop()`; odczytano `EMERGENCY_STOP(0x1)` i brak błędu protokołu `0x0`. Żądanie wykonano bez ruchu robota.
- Pozycję referencyjną siedmiu przegubów zapisano **lokalnie**, bez kopiowania operacyjnych danych do GitHuba.
- **Nie wykonano pierwszego ruchu** po otwarciu sesji; test ruchu pod obciążeniem i pomiar hamowania są otwarte.

**Krytyczne ograniczenia:**
- STOP SW nie jest niezależnym sprzętowym E-STOP; utrata Linux/USB/OpenDeck/CAN może zablokować żądanie.
- Skrypt STOP zapisuje lokalny latch, ale nie wymusza go w każdym procesie sterującym; **globalny interlock jeszcze nie istnieje**.
- Nie zweryfikowano utrzymania pozycji przy utracie zasilania ani podczas realnego zatrzymania w ruchu. Nie wolno utożsamiać `EMERGENCY_STOP(0x1)` z certyfikowanym STO/SS1.
- Instrukcja NERO ostrzega o ryzyku opadnięcia po odłączeniu zasilania. STOP SW nie wysyła `disable()` ani nie odcina 24 V.
- Etap 2 (fizyczny grzybek na VENTUNO GPIO) **PLANNED**; jako sam GPIO+Linux/CAN nadal nie stanowi niezależnego obwodu bezpieczeństwa.

Decyzja: `docs/architecture/ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md`. Referencyjny kod: `ops/nero/nero_stop.py`, `scripts/robot/nero_sdk_readonly_probe.py` (lokalne identyfikatory urządzeń zostały usunięte z publikowanych kopii).

## 5. Elgato Stream Deck Plus / OpenDeck

**Zweryfikowane 2026-11-10 przed restartem:**
- OpenDeck **2.14.1 ARM64**, uruchamiany z NVMe, jako `vision-opendeck.service` usługa użytkownika `arduino`.
- Specyficzna reguła udev dla `0fd9:0084`, 8 przycisków, prawy dolny klawisz: `Keypad.7.0`.
- Fizyczny klawisz STOP SW działał w próbie i sterownik NERO potwierdził stan zatrzymania.

**Stan podczas tego audytu po restarcie:** `vision-opendeck.service` jest `activating (auto-restart)`, licznik restartów >= 114; log `STREAM_DECK_PLUS_NOT_AVAILABLE_OR_ACCESS_DENIED hid=none`. USB panelu **nie było w `lsusb`**. To **BLOCKED — fizyczne urządzenie USB**, a nie PASS produkcyjnej dostępności.

Pliki w `ops/streamdeck/` są tylko zanonimizowaną kopią konfiguracji referencyjnej. Rzeczywisty binarny OpenDeck i jego wtyczka pozostają na NVMe. Nie wykonywano automatycznej naprawy, nie zmieniano usługi ani polityki restartu.

## 6. Przyszłe moduły

| Moduł | Stan |
|---|---|
| Główny Vision Core / pełne HMI | PLANNED — nie stwierdzono produkcyjnej usługi |
| Kinematyka, planowanie trajektorii, automatyczny ruch NERO | PLANNED — brak pełnej integracji i niezależnych zabezpieczeń |
| Eye-in-Hand / Luxonis | architektonicznie wybrane, brak w tym audycie dowodu bieżącego podłączenia |
| Dynamiczna detekcja przeszkód przez AI | PLANNED; nie stanowi funkcji bezpieczeństwa |
| Sterowane oświetlenie pola PCB ~300 × 300 mm | PLAN — bez gotowego sterownika produkcyjnego |
| POWER FAILURE / UPS parkowanie NERO | zaprojektowany scenariusz, brak potwierdzonej usługi dla NERO |
| Eksport do AI Platform / RM | osobny projekt; brak potwierdzonego finalnego kontraktu eksportu Vision |

## 7. Rozgraniczenie TEST / PROD / ARCHIVE

- `/srv/vision-data/projects/Vision` — główne repo Git; osobne gałęzie z testami i dokumentacją.
- `/srv/vision-data/tools/` — narzędzia SDK, prototypy oraz konfiguracja produkcyjnego OpenDeck/Remote MCP; nie kopiować bez kontroli.
- `/srv/vision-data/vision/sessions/` — oryginały zdjęć i logi/metryki; **wyłącznie lokalne**.
- `/srv/vision-data/experiments/` — testy, termowizja i prywatne zamrożone archiwa; **wyłącznie lokalne**.
- `/etc/systemd/`, reguły udev — minimalna konfiguracja systemowa; repo zawiera wyłącznie źródłowe kopie/templatki, nie stan systemu jako takiego.

**Działania wykonane w ramach audytu/synchronizacji:** odczyty, `git fetch`, odrębny `git worktree`, sanitizacja kopii i testy bez hardware. Nie aktywowano napędów, nie wysłano komendy ruchu, nie zmieniono konfiguracji produkcyjnej. `main` pozostał bez zmian.

## 8. Dalsza weryfikacja i odtwarzalność

- Zbadać stabilność USB i wykrywanie Stream Deck, Sony i adaptera AgileX; po podłączeniu ponowić status i porównać z logami.
- Wymusić centralną blokadę ruchu po STOP i przetestować reakcje na przerwany CAN/USB.
- Uzyskać dokumentację niezależnej funkcji bezpieczeństwa NERO oraz zabezpieczenia mechanicznego przed opadnięciem.
- Dokończyć dokumenty produkcyjnych procedur uruchomienia, wersjonowania oraz rollbacku.
- Zaktualizować Hardware Baseline v1 dopiero po pełnych testach z kryteriami PASS.
