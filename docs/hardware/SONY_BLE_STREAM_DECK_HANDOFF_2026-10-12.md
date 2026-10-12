# Vision — przekazanie testów Stream Deck / Sony A6100A (2026-10-12)

**Status:** dokumentacja wyników laboratoriów; **bez wdrożenia produkcyjnego**.

**Urządzenie:** Arduino VENTUNO Q (`vision`), Ubuntu ARM64, BlueZ 5.72.

**Aparat:** Sony ILCE-6100A, obiektyw E PZ 16–50 mm F3.5–5.6 OSS II.

**Panel:** Elgato Stream Deck Plus (`0fd9:0084`).

## Potwierdzone wyniki

| Element | Stan | Podstawa |
|---|---|---|
| 8 LCD, pasek dotykowy, wszystkie 4 enkodery | **PASS** | raporty HID, obserwacje operatora, testy CW/CCW/press/release |
| OpenDeck 2.14.1, Linux ARM64 | **PASS dla UI/edycji profili** | GUI przez Xvfb, zapisy `Keypad.0.0` i `Encoder.0.0` w izolowanym katalogu |
| Stream Deck (klawisz FOTO) → USB PTP → migawka | **PASS** | pojedyncze zdjęcie Sony JPEG 6000×4000, `gphoto2 --keep` |
| Sterowanie zoomem przez `gphoto2` / PTP 2 | **BRAK** | `0xD214` to `Predicted Maximum File Size`, `GetSet=0`, nie zoom optyczny |
| Sony Camera Control PTP 2 capabilities | **PASS, read-only** | 45 właściwości, 18 komend, 62 deskryptory, pełne zamknięcie sesji |
| Parowanie Sony / VENTUNO BLE | **PASS** | BlueZ `Paired=yes`, `Bonded=yes`, `Connected=yes` przed wyłączeniem |
| BLE TELE 160 ms / RELEASE | **NIEJEDNOZNACZNY** | BlueZ OK, brak pewnej obserwacji ruchu |
| BLE TELE **1000 ms** / RELEASE | **PASS — fizyczny zoom** | BlueZ GATT WriteValue OK oraz wyraźny ruch obiektywu potwierdzony przez operatora |
| BLE WIDE | **NIEBADANY** | wymaga następnego odrębnie zatwierdzonego testu |
| Pokrętło Stream Deck → BLE zoom | **NIEBADANY** | dotychczas ruch odbywał się z jednorazowego skryptu na VENTUNO |
| Równoczesna praca Sony USB PTP + BLE zoom | **NIEBADANY** | USB odłączone na czas testów BLE |

## BLE — zidentyfikowany interfejs

- Usługa GATT pilota Sony: `8000ff00-ff00-ffff-ffff-ffffffffffff`.
- Charakterystyka komend WRITE: `0000ff01-0000-1000-8000-00805f9b34fb`.
- Charakterystyka NOTIFY: `0000ff02-0000-1000-8000-00805f9b34fb`.
- W teście pozytywnym TELE: `02 45 10` (PRESS) → 1,0 s → `02 44 00` (RELEASE).
- Implementacja protokołu oparta na analizie Freemote: https://github.com/coral/freemote.
- Wartości charakterystyk i ścieżki BlueZ sprawdzać po **każdym restarcie**; ścieżka D-Bus nie musi być stała. Nie zakładać automatycznego połączenia po wznowieniu.

## Lokalizacja dowodów (pozostają na VENTUNO, nie w publicznym Git)

- `/srv/vision-data/tools/streamdeck-eval/TEST-RESULTS.md`.
- `/srv/vision-data/tools/streamdeck-eval/sony-ble-zoom-tele-1000ms-result.json`.
- `/srv/vision-data/tools/sony-a6100-verify/ptp2-capabilities-test/REPORT-PTP2-2026-10-12.md`.
- `/srv/vision-data/tools/sony-a6100-verify/ptp2-capabilities-test/get-ext-device-info.json`.
- `/srv/vision-data/tools/sony-a6100-verify/ptp2-capabilities-test/get-all-ext-properties.json`.
- Programy eksperymentalne i obrazy również pozostają lokalnie na NVMe.

Zapis w repo zawiera **wyłącznie dokumenty Markdown**, bez numerów seryjnych, adresów BLE urządzeń, obrazów fotograficznych, binariów PTP i kodu/dokumentacji objętych licencją Sony.

## Następna rozmowa — kolejność bezpiecznych prac

1. Operator uruchamia VENTUNO i aparat, potem deklaruje gotowość. Najpierw sprawdzić status agenta MCP `vision`.
2. **Bez parowania ani komend sterujących:** odczytać `systemctl is-active bluetooth`, `bluetoothctl show`, `bluetoothctl devices`, `bluetoothctl info` dla rozpoznanego `ILCE-6100A`. Sprawdzić `Paired`, `Bonded`, `Connected`; nie zakładać, że BLE po restarcie jest automatycznie połączone.
3. Jeśli kamera rozłączona, zaproponować jednorazowe połączenie `bluetoothctl connect`, **po zgodzie operatora**; nie usuwać bondu ani nie parować ponownie bez podstaw.
4. Zweryfikować identyfikatory aktualnie dostępnych usług/charakterystyk (WRITE/NOTIFY), a przed wysłaniem ruchu potwierdzić brak równoległego procesu sterującego i wolną przestrzeń dla obiektywu.
5. Na osobne zatwierdzenie: **WIDE 1 sekunda + RELEASE**, jeden impuls, bez automatycznych prób i bez zwiększania czasu; operator potwierdza widoczną zmianę.
6. Dopiero potem zaprojektować test: pierwsze pokrętło Stream Deck → TELE/WIDE przez BLE (bez autostartu i produkcyjnej usługi), z gwarantowanym RELEASE / timeout.
7. Na koniec osobno, po zgodzie operatora: ponownie podłączyć USB Sony, sprawdzić czy połączenie BLE pozostaje aktywne i czy aparat może wykonać zdjęcie przez `gphoto2` bez utraty sterowania zoomem.
8. Przed zakończeniem zapisać wyniki na NVMe. Git/PR/merge i produkcyjne wdrożenia wyłącznie po instrukcji użytkownika.

**Nie mieszać Vision z ECU Platform ani AI Platform.** Analiza zdjęć pozostaje poza VENTUNO; VENTUNO odpowiada za akwizycję i kontrolę jakości.
