# Vision — rejestr dowodów Sony A6100A (2026-10-12–13)

**Status:** indeks istniejących, **lokalnych** dowodów z VENTUNO Q. Publiczne GitHub przechowuje wyłącznie podsumowania i skróty. Nie dodawać zdjęć scen, surowych logów PTP/BLE, adresów MAC/IP/SSID ani poświadczeń do repo.

**Katalog bazowy:** `/srv/vision-data/vision/sessions/` (NVMe). W tabelach ścieżki względne wobec tego katalogu.

## A. Jednoczesne HDMI / USB / BLE

| Dowód | Katalog/plik lokalny | Weryfikacja |
| --- | --- | --- |
| HDMI, USB i BLE, oryginalny JPEG | `sony-hdmi-monitor-usb-check-20261013T110500Z/hdmi_monitor_test.jpg` | 6000×4000, 7 350 888 B, EXIF 16 mm |
| HDMI, USB i BLE, po TELE 650 ms | `sony-hdmi-monitor-usb-check-20261013T110500Z/hdmi_monitor_after_ble.jpg` | 6000×4000, EXIF 20 mm |
| Przebieg poleceń BLE i klatek USB | `sony-hdmi-monitor-usb-check-20261013T110500Z/ble_hdmi_concurrent_result.json` | BLE PRESS/RELEASE ACK, USB Live View 5/5 |
| Fotografowanie i Live View przy monitorze HDMI | `sony-hdmi-monitor-usb-check-20261013T110500Z/{capture_result.json,REPORT.md}` | JPEG 24 MP i HDMI z potwierdzeniem operatora |
| Powtórzony USB/BLE Live View | `sony-usb-wifi-parallel-20261013T092004Z/ble_usb_liveview_result.json` | 10/10 klatek, 2 nakładające się czasowo z impulsem BLE |
| Diagnostyka PTP/BLE i awaria zdjęcia | `sony-usb-wifi-parallel-20261013T092004Z/{REPORT.md,ble_usb_concurrency_result.json}` | Pierwsze zdjęcie przy aktywnym BLE FAIL; także bez BLE pojawił się timeout |
| Ustalona semantyka Sony PTP 2 | `/srv/vision-data/tools/sony-a6100-verify/ptp2-capabilities-test/REPORT-PTP2-2026-10-12.md` | 0xD214 to predicted file size, nie zoom |
| Sony BLE TELE + USB — wcześniejsza próba | `/srv/vision-data/tools/streamdeck-eval/BLE07_TELE_1000MS_USB_CONNECTED_20261012T205540871692Z.json` | Operator potwierdził ruch obiektywu |

## B. Wi-Fi Remote API i oryginały zapisane na karcie SD

| Dowód | Katalog/plik lokalny | Weryfikacja |
| --- | --- | --- |
| Fotografia przez Wi-Fi / JPEG postview | `sony-wifi-hdmi-usb-staged-20261013/wifi_hdmi_capture_postview.jpg` | 1616×1080, 463 984 B |
| Metadane wywołania Wi-Fi | `sony-wifi-hdmi-usb-staged-20261013/wifi_hdmi_capture.json` | `actTakePicture` OK; postview EXIF 14:04:15 |
| Oryginalny JPEG z karty SD | `sony-wifi-hdmi-usb-staged-20261013/imported_originals/DSC00020.JPG` | **6000×4000, 12 877 824 B**, 20 mm |
| Oryginalny RAW z karty SD | `sony-wifi-hdmi-usb-staged-20261013/imported_originals/DSC00020.ARW` | **24 816 384 B**, Sony ARW/TIFF |
| Transfer i zgodność kopii | `sony-wifi-hdmi-usb-staged-20261013/wifi_mass_storage_import_report.json` | `/dev/sda1` ro, SHA-256 SD = NVMe |
| Przebieg sesji oraz testy portu | `sony-wifi-hdmi-usb-staged-20261013/{PLAN.md,REPORT.md,initial.json}` | Wyniki i ograniczenia pracy na realnym aparacie |
| Programowy disconnect portu (test jednokrotny) | `sony-wifi-hdmi-usb-staged-20261013/usb_port_probe_result.json` | Port `disable=1`, Sony znika; brak DIRECT; powrót `disable=0` |
| Skrypt próby portu (nie uruchamiać ponownie bez zatwierdzenia) | `sony-wifi-hdmi-usb-staged-20261013/usb_port_switch_probe.py` | Fail-closed, NVMe guard, niezależny timer rollback |

### B.1. Suma SHA-256 potwierdzonych oryginałów

| Lokalny oryginał | SHA-256 SD = SHA-256 NVMe |
| --- | --- |
| `DSC00020.JPG` | `51fc6cd21a51e19c410dff73128b9e8a04ebb5f33666f49096ab032e6acc3d65` |
| `DSC00020.ARW` | `70d5c22b945dc3a22d62f5ed653355785a45f8b4ffd47f2a21c59eecf0c26278` |

Zgodny identyfikator `DSC00020` i EXIF/time `2026:10:13 14:04:15` pozwoliły powiązać oryginały SD z próbą zdalnego zdjęcia po Wi-Fi. Znaczniki czasu pochodzą z zegara aparatu/plików, **nie traktować ich bez dodatkowej synchronizacji jako monotonicznego czasu systemowego Vision**.

### B.2. Ograniczenia interpretacji

- Test przeprowadzono na **jednej parze JPG/ARW** w pełnym cyklu Wi-Fi → SD → USB. Brak potwierdzenia odporności długiej serii.
- **RAW oryginalny** rozpoznany po nagłówku i bezstratnie skopiowany: demosaicing/kompletny workflow RAW nie został jeszcze wykonany.
- **Mass Storage** z tej sesji był montowany ręcznie przez operatora, wyłącznie w trybie `ro`; później karta została odmontowana.
- Przy próbie logicznego wyłączenia portu był timer ratunkowy; powrót Sony na USB potwierdzono, lecz stan/energia linii VBUS nie były mierzone.
- **„Zawsze połączony”** nie doczekało się testu wznowienia Wi-Fi po rozładowaniu baterii. Nie nadawać temu statusu PASS.
- Zmiany w projekcie Vision i przebieg robota nie były testowane; wynik aparatu **nie** oznacza gotowości całego stanowiska.

## C. Poprzednie pomiary USB, RAW i stabilności

Dokument historyczny z 10 października: [Sony A6100 — USB/PTP, Live View, RAW i stabilność](SONY_A6100_VERIFICATION_2026-10-10.md). Katalogi LV-01–05, RAW-02 i STAB-01–06: [rejestr dowodów 10 października](EVIDENCE_REGISTER_2026-10-10.md).

## D. Reguły retencji i prywatności

- Nie dodawać do publicznego repo lokalnych `*.jpg`, `*.arw`, `*.bin`, plików profili Bluetooth, surowych raportów i logów sieciowych.
- Repozytorium przechowuje tylko datowane raporty syntetyczne, statusy PASS/FAIL/UNVERIFIED, identyfikatory testów i hashe dowodowe.
- Pliki źródłowe należy zabezpieczyć w ramach osobnego procesu backup/retencji Vision na NVMe; obecność w tym katalogu **nie jest gwarancją backupu**.
