# Vision — Stream Deck Plus / Linux ARM64 — test 2026-10-12

Status: **EVALUATION ONLY**. Brak instalacji systemowej OpenDeck, trwałej reguły udev, autostartu, zmian w repozytorium Vision lub firmware. Wszystkie artefakty znajdują się w `/srv/vision-data/tools/streamdeck-eval/`.

## Urządzenie i środowisko
- Host: `vision`, Linux `6.8.0-1084-qcom`, `aarch64`, Ubuntu 24.04.
- Elgato Stream Deck Plus; VID:PID `0fd9:0084`; Linux HID `hid-generic`.
- `/dev/hidraw0` i `/dev/input/event2` poprawnie wykryte.
- Tymczasowy ACL `/dev/hidraw0`: `user:arduino:rw-`, ręcznie zatwierdzony przez właściciela.
- OpenDeck 2.14.1 arm64, rozpakowany z `.deb`, bez instalowania systemowo. SHA-256 paczki `b16f9801bd65a47d204329d0863c37f0d4e7ad879ed1b417c3e7b9da5aab85b4`.
- Xvfb uruchamiany i zamykany tylko na czas testów. Brak aktywnej sesji graficznej użytkownika; logowanie na ekranie GDM.

## Wyniki
| Próba | Wynik | Dowód |
|---|---|---|
| USB/HID enumeration | PASS | `HID_ID=0003:00000FD9:00000084`, `/dev/hidraw0` |
| User-space HID read/write permission | PASS | `os.open(...,O_RDWR)` |
| OpenDeck startup in Xvfb | PASS | 15-s test bez crashu; zakończenie `timeout` exit 124 zgodnie z planem |
| OpenDeck actually opens Stream Deck HID | PASS | `/proc/<pid>/fd/379 -> /dev/hidraw0` |
| HID button events | PASS | `01 00 08 00 ...` press/release bitmap |
| Touchscreen gesture (flick) | PASS | `01 02 0e 00 03 ...` coordinates |
| Encoder rotation | PASS | `01 03 05 00 01 ...`, dodatnie i ujemne delty |
| Kernel evdev activity | PASS | `/dev/input/event2`, 112 events |
| HID report capture | PASS | 44 reports / 45 s, 19 unique initial-byte patterns |
| Device info, read-only HID feature 0x08 | PASS | 2 rows × 4 columns, LCD 800×480 |
| Host-to-device, feature 0x03/0x06 | TRANSPORT PASS | Firmware przyjął test chwilowego zielonego koloru przycisku #0; ioctl zwrócił 32 bajty |
| Restore-logo feature 0x03/0x02 | TRANSPORT PASS | Firmware przyjął polecenie przywrócenia logo; ioctl zwrócił 32 bajty |
| Wygląd wyświetlaczy / fizyczna zmiana koloru | NIEPOTWIERDZONE | Wymaga obserwacji użytkownika |
| Wciskanie osi enkoderów | NIEPOTWIERDZONE | W odczycie nie uchwycono raportu `01 03 ... 00` (encoder button) |
| Każdy z 8 przycisków / każdy z 4 enkoderów osobno | NIEPOTWIERDZONE | Oceniono próbkowe zdarzenia, nie pełny test per element |

## Weryfikacja formatu raportów
Dokumentacja Elgato: https://docs.elgato.com/streamdeck/hid/stream-deck-plus/ oraz https://docs.elgato.com/streamdeck/hid/general/

Wejścia: `0x01 0x00` = przyciski, `0x01 0x02` = dotyk, `0x01 0x03` = enkodery. Dla enkodera payload kind `0x01` oznacza obrót, `0x00` zmianę przycisku. Dla dotyku kind `0x03` oznacza flick. Wynik zgodny z surowymi raportami.

## Co pozostaje po teście
- Testowe pliki i raporty na NVMe (brak produkcyjnego deploymentu).
- Udzielony ręcznie ACL tylko dla bieżącego `/dev/hidraw0`, dopóki nie zostanie cofnięty/reutworzony węzeł.

## Cofnięcie tymczasowych uprawnień
Przed poleceniem zweryfikować, że urządzeniem jest nadal Stream Deck Plus. Następnie:

```bash
sudo setfacl -x u:arduino /dev/hidraw0
```

Dalszy test GUI wymaga aktywnej sesji graficznej `arduino`. Po dopuszczeniu urządzenia do pracy docelowej należy osobno zatwierdzić regułę udev i sposób uruchamiania, nie wdrażać ich w ramach tej ewaluacji.

## Uzupełnienie — test LCD i paska dotykowego (2026-10-12)
- Zweryfikowano dokumentację Elgato HID Stream Deck Plus: 8 × JPEG 120×120, osobny obraz paska dotykowego JPEG 800×100; transmisja poprzez output report 0x02 / command 0x07 i 0x0B, fragmenty po 1016 bajtów z raportem HID o długości 1024 B.
- Python Pillow 10.2.0 dostępny, bez instalacji.
- Pierwszy test: 8/8 przycisków i pasek dotykowy przyjęły transmisje po HID bez błędów zapisu; 95 sekund nasłuchu nie przyniosło nowych zdarzeń dotyku (niewykonanie ruchów przez operatora / niewiadome; nie oznaczać tego jako usterki). Automatyczna próba Show Logo miała błędnie zakodowany ioctl i zakończyła się `EINVAL`; następczy poprawny ioctl przywrócił logo (PASS); skrypt testowy poprawiono.
- Druga transmisja: ponownie 8 obrazów oznaczonych cyframi 1–8 i kolorami oraz wzorzec paska z czterema strefami A/B/C/D. Wszystkie 8+1 transmisji HID bez błędu; wzorce pozostawiono na urządzeniu do oceny wzrokowej użytkownika. Proces zakończył się i zwolnił deskryptor HID. Nie twierdzić, że fizyczna prezentacja obrazu została potwierdzona, dopóki operator tego nie zaobserwuje.
- **Kolejna czynność:** potwierdzenie wyglądu przycisków i paska przez operatora; następnie osobny test TAP/PRESS/FLICK z weryfikacją współrzędnych każdej strefy, ewentualnie z reakcją wizualną.
- **Przywrócenie logo** po ocenie: przez znany działający HID SEND FEATURE `0x03 0x02` z `ioctl` direction bits `3`, 32 B. Nie odinstalowywać nic z systemu (OpenDeck nadal wyłącznie rozpakowany w katalogu testowym).

## Domknięcie testu dotyku — 2026-10-12
- Próba `touch-bc-retest.py` (60 s) dała pusty wynik — najprawdopodobniej gesty wykonano poza aktywnym oknem. Nie była dowodem awarii.
- Powtórzenie w trybie diagnostyki surowej `diagnose-all-inputs.py` (120 s) dało: `TAP` strefy A (x=105, y=57), C (x=524, y=59), D (x=732, y=60); `PRESS` strefy B (x=300, y=62) i C (x=480, y=60); `FLICK` w prawo od x=347 do x=412 oraz w lewo od x=745 do x=686.
- Zdarzenia wykryto w `hidraw0` z poprawnym typem raportu `01 02`, równolegle zdarzenia z `/dev/input/event2`.
- **Weryfikacja pokrycia A/B/C/D: PASS. TAP: PASS (A/C/D), PRESS: PASS (B/C), FLICK: PASS (oba kierunki).** Nie zarejestrowano odrębnego TAP w strefie B, lecz detekcję dotyku B potwierdza PRESS. Gesty przesunięcia były krótkie, więc nie należy deklarować potwierdzenia pełnego przesuwania od A do D.
- Wcześniej operator potwierdził widoczne wzorce na **wszystkich 8 LCD** i **całym pasku dotykowym**, zamykając weryfikację wyświetlania.
- Nie wprowadzono zmian produkcyjnych; używany jest wyłącznie katalog testowy i wcześniej zatwierdzony, nietrwały ACL dla `/dev/hidraw0`.

## 2026-10-12 — pełna weryfikacja pokręteł i OpenDeck GUI (TRYB TESTOWY)

### Sprzęt — 4 × enkoder Stream Deck Plus
- Zweryfikowano urządzenie HID `0fd9:0084` na `/dev/hidraw0`. Test read-only typu `01 03` według oficjalnej specyfikacji Elgato (offset 4: `0` = przycisk, `1` = obrót; dane pozycji na offsetach 5–8).
- Wynik `encoder-test-results.json`: 125 bezpośrednich zdarzeń HID (pełna rejestracja), zakończenie na żądanie po uzyskaniu kompletu PASS (nie awaria testu).
- Enkoder 1: CW 21 ticków, CCW 31 ticków, PRESS 1, RELEASE 1 — **PASS**.
- Enkoder 2: CW 17 ticków, CCW 11 ticków, PRESS 2, RELEASE 2 — **PASS**.
- Enkoder 3: CW 9 ticków, CCW 11 ticków, PRESS 1, RELEASE 1 — **PASS**.
- Enkoder 4: CW 10 ticków, CCW 9 ticków, PRESS 1, RELEASE 1 — **PASS**.
- Po zakończeniu procesu deskryptor HID został zamknięty.

### OpenDeck 2.14.1 (Linux ARM64) — GUI i konfiguracja
- Uruchomiono z rozpakowanej paczki w testowym Xvfb (1440×900) z izolowanymi `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME` na NVMe. Brak instalacji systemowej, usługi i autostartu.
- OpenDeck rozpoznał urządzenie jako Stream Deck Plus, włączył UI konfiguracji i otworzył `/dev/hidraw0`; potwierdzony zrzut `logs/opendeck-gui.png`.
- Test interakcji przez wirtualną mysz XTest: `Toggle Action` przeniesiono z listy akcji na klawisz 1. W bieżącym, wyłącznie testowym profilu `Default.json` powstał wpis `Keypad.0.0`; zrzut `logs/opendeck-after-drag.png` i próbka danych `logs/Default.after-gui-test.json`.
- Drugi test interakcji przez GUI: `Device Brightness` przeniesiono na enkoder 1. W wyłącznie testowym profilu `Default.json` powstał wpis `Encoder.0.0` w `sliders[0]`, `controllers: ["Keypad", "Encoder"]`; zrzut `logs/opendeck-after-encoder-drag.png` i próbka danych `logs/Default.after-encoder-gui-test.json`.
- Oba testy GUI zakończyły się poprawnie. Po wyłączeniu aplikacji `Default.json` został przywrócony do pustych `keys` i `sliders`; sprawdzone programowo.
- **Nie testowano wykonania akcji Device Brightness przez obrót podczas działania OpenDeck** — zweryfikowano mapowanie akcji, zapis profilu oraz niezależnie sprzętowe obroty/naciśnięcia HID. Nie utożsamiać tych wyników z pełnym end-to-end wykonaniem akcji.
- W wirtualnym środowisku aplikacja logowała ostrzeżenie `login1/session/auto` o niemożności nasłuchiwania zdarzeń zasilania; samo uruchomienie GUI i zapis profili działały.
- Po zakończeniu: brak procesów OpenDeck/Xvfb z katalogu testowego; komenda HID przywrócenia logo `0x03 0x02` **PASS**.
- `opendeck` nadal **niezainstalowany systemowo**, w repo Vision nic nie zmieniono.
- Tymczasowy ACL `user:arduino:rw-` na `/dev/hidraw0` wciąż obecny (do cofnięcia przez operatora: `sudo setfacl -x u:arduino /dev/hidraw0` po zakończeniu dalszych testów).

## 2026-10-12 — Stream Deck Plus + Sony ILCE-6100A (shutter and zoom preliminary)
- Tests remain on VENTUNO Q in `/srv/vision-data/tools/streamdeck-eval/`. No system package install, repo merge, firmware or services change.
- USB simultaneous detection: Stream Deck Plus `0fd9:0084`, Sony `054c:0f0d` (camera port `usb:001,005`).
- Direct HID key 1 (top left) -> single gphoto2 `--keep --capture-image-and-download`: **PASS**. Camera shutter actually fired; returned JPEG `6000×4000`, `8,145,433` B, SHA256 `f51f4cec09b39e46a2147e162027712e3e4a4ef79d3b909c77b23e902f29bf07`, elapsed 1.97 s. Path: `camera-test-captures/shutter-20261012T115712Z/deck_shutter.jpg`; detailed log beside photo.
- EXIF current photo: lens `E PZ 16-50mm F3.5-5.6 OSS II` (power zoom), focal length 39mm, Sony camera in M. No setting changes, photograph preserved by `--keep`.
- USB gphoto Zoom `/main/capturesettings/zoom`: read only `Current: 34.4975`; PTP raw `0xD214 = 34497536`. This is not numerically equal to EXIF focal length (39mm). No assumption about optical zoom from existence of widget. Upstream gphoto/libgphoto2 source comments uncertainty, source setter converts float to u32 millions.
- Prepared safe one-shot motor test `camera-zoom-deck-test.py` (encoder #1 CW -> one Zoom write target35, verify, restore only if changed). Test ran 150 seconds but **NO ENCODER TURN REPORT** arrived during armed interval: `status=TIMEOUT`. Hence **no zoom command was issued** and no movement or support was demonstrated. Not a device or camera fail.
- After timeout: no active test or camera process, HID descriptor released, Stream Deck logo restored; USB Zoom readback unchanged (`34.4975`). Evidence `camera-zoom-test-result.json`.
- Next: when operator ready, arm zoom test again and physically rotate first encoder clockwise. Observe lens movement and verify readback; if setting unsupported, test alternative Sony API separately rather than claim zoom operational.

## 2026-10-12 — powtórny test sterowania zoomem pokrętłem (wynik)
- Aktywne urządzenia: Stream Deck Plus `0fd9:0084`, Sony ILCE-6100A `054c:0f0d`, obiektyw E PZ 16–50mm F3.5–5.6 OSS II. Próba izolowana, bez wdrożenia produkcyjnego.
- Pierwszy enkoder: wykryto `ENCODER_1_CW_DETECTED ticks=1` → **PASS**.
- Wysłano **dokładnie jedno** polecenie `gphoto2 --set-config-value=/main/capturesettings/zoom=35`; kod wyjścia `0`, czas `3.67 s`. Bez ponawiania komendy.
- Przed zapisem `Zoom=34.4975`, `D214 raw=34497536`. Po zapisie `Zoom=34.4975`, czyli **brak obserwowanej zmiany**. Nie uruchomiono restore zoom, bo atrybut nie zmienił się w odczycie.
- Wykonano pojedyncze kontrolne zdjęcie. Skrypt początkowo nie znalazł pliku, ponieważ `gphoto2` odziedziczył cwd agenta MCP zamiast sesji. Plik **odzyskano i przeniesiono** do `/srv/vision-data/tools/streamdeck-eval/camera-test-captures/zoom-20261012T121801Z/zoom_after.jpg`. Zdjęcie poprawne, 6000×4000 px, 8232534 B, SHA256 `5d0f39f8c9cead6f2b64b5221c8f7b4b6502f54c1a719df99f62fcd1440afc6d`, EXIF focal length **39 mm** (tak samo, jak zdjęcie sprzed próby). Plik zachowano na aparacie i NVMe.
- Dodatkowe źródło: libgphoto2 `ptp2/config.c` udostępnia nazwę `Sony_Zoom (D214)` i heurystyczny przelicznik `1e6`; sukces wywołania nie dowodzi możliwości sterowania optyką. Zgłoszenie gPhoto dotyczące Sony A7sii raportuje podobny brak reakcji dla `D214`: https://github.com/gphoto/gphoto2/issues/533. Sony ILCE-6100A z obiektywem PZ opisuje lokalne sterowanie zoomem dźwignią/pierścieniem: https://helpguide.sony.net/ilc/2460/v1/en/contents/0401_zoom_ilc.html.
- **Status zoom USB: NIEPOTWIERDZONY / brak efektu w aktualnej metodzie**; nie deklarować, że gphoto2 steruje silnikiem PZ. Nie wysłano kolejnych prób, nie zmieniono wartości zoomu, logo Stream Deck przywrócono, HID zwolniony, brak procesów testowych.
- Dalsze działania: zweryfikować obsługę zoom motor w alternatywnym, udokumentowanym interfejsie Sony (jeśli dostępny dla ILCE-6100A) lub rozważyć zewnętrzny mechanizm; wszelkie nowe komendy aktywujące ruch wymagają oddzielnej zgody.

### Potwierdzenie operatora — zoom optyczny
- Operator obserwował obiektyw Sony E PZ 16–50 mm OSS II podczas testu enkoder 1 → `gphoto2` / Sony PTP `Zoom (0xD214)` i potwierdził: **obiektyw fizycznie nie poruszył się**.
- Zestawienie: komenda zakończona exit=0, odczyt Zoom bez zmiany `34.4975`, EXIF zdjęcia kontrolnego nadal 39 mm, brak fizycznego ruchu napędu. **Test sterowania zoomem tą metodą = FAIL (brak efektu)**. Nie jest to dowód, że aparat nie obsługuje żadnego innego protokołu zdalnego sterowania zoomem.
- Kolejny krok wyłącznie po decyzji użytkownika: analiza alternatywnych udokumentowanych interfejsów sterowania bez wysyłania eksperymentalnych komend do obiektywu.

## 2026-10-12 — audyt dostarczonego pakietu Sony CameraRemoteCommand-2.02.00 (bez testów aktywnych)
- Analizowany upload: `CameraRemoteCommand-2.02.00.zip`, SHA-256 `eea563acb772f99001ac530b116423a337ce464193371b10fed0ba4768acb4a9`. Bez uruchamiania kodu vendor SDK, bez kopiowania pakietu na VENTUNO i bez wysyłania komend do Sony.
- **KOMPATYBILNOŚĆ:** Sony `README.pdf`, str. 4: `ILCE-6100(A)` obsługuje **Camera Control PTP 2**; brak obsługi **PTP 3** w oficjalnej macierzy. Przykład `Examples/example-v3-linux/frontend/scripts/change_camera_settings_zoom.sh` dotyczy wyłącznie PTP 3 i nie jest przeznaczony do bezpośredniego użycia z ILCE-6100A. Katalog v2-linux nie zawiera analogicznego przykładu zoomu.
- **KRYTYCZNE WYJAŚNIENIE:** Sony `Camera Control PTP 2 Reference.pdf`, str. 24 i 60: właściwość `0xD214` to `Predicted Maximum File Size`, GET-only według specyfikacji PTP2, **nie Zoom**. Wykorzystany dotychczas `gphoto2` błędnie prezentował dla tego urządzenia `0xD214` jako `Zoom` i surowe `34497536` jako `34.4975`. Poprzednia próba ustawienia `zoom=35` nie była poprawnym testem sterowania optyką; rejestrowany brak ruchu obiektywu jest spójny z tą interpretacją.
- **PTP 3** ma dedykowane komendy zmiany zoomu (`Zoom Operation` 0xD2DD, `Zoom Operation Enable Status` 0xD25B, `Zoom Setting` 0xD25F) opisane w `Camera Control PTP 3 Reference.pdf` s. 478, 481, 651–652, ale **nie należy ich wysyłać do 6100A bez dowodu obsługi protokołu**. W przykładzie v3 wykryto też brak timeoutów pętli oczekiwania.
- **Alternatywa**: Sony ILCE-6100A wspiera oficjalnie pilot BT `RMT-P1BT` (`https://helpguide.sony.net/ilc/2460/v1/en/contents/0706_bluetooth_remote.html`), a pilot posiada obsługę zoomu PZ (`https://helpguide.sony.net/ilc/1820/v1/en/contents/TP0002240389.html`). Projekt Freemote dokumentuje komunikację BLE w tym zoom (`https://github.com/coral/freemote`), z zastrzeżeniem: testowany na innym modelu, wymaga portu z nRF52840 do BlueZ.
- **Host VENTUNO:** read-only `bluetoothctl show`: kontroler `hci0` obecny, `Powered=yes`, role `central` i `peripheral`; usługa bluetooth `active`. Nie skanowano BLE, nie parowano aparatu, nie zmieniano ustawień hosta.
- **Pozostałe ryzyko:** niepotwierdzona równoczesna obsługa Sony USB PTP2 i BLE remote, pairing/bezpieczeństwo i test zachowania Power Zoom; wymaga osobnej akceptacji testu i uwzględnienia resetu/parowania tylko z zaufanym urządzeniem. W pakiecie Sony brak pliku LICENSE dla kodu, a README zawiera ograniczoną licencję na dokumentację — nie kopiować kodu SDK do publicznego repo Vision bez sprawdzenia warunków.
- **STATUS:** analiza kompletna; zero wdrożeń produkcyjnych.

## 2026-10-12 — PTP 2 capability read-only probe: final conclusion
- Wykonano izolowaną diagnostykę Sony ILCE-6100A przez PTP 2 na USB; pełny raport: `/srv/vision-data/tools/sony-a6100-verify/ptp2-capabilities-test/REPORT-PTP2-2026-10-12.md`.
- `GetDeviceInfo (0x1001)`: 16 operacji; `SDIO_GetExtDeviceInfo (0x9202)`: wersja 0x00C8, 45 właściwości + 18 komend sterujących, brak oficjalnego polecenia zoomu optycznego.
- `SDIO_GetAllExtDevicePropInfo (0x9209)`: 62 kompletne deskryptory (1759 B). **`0xD214` = Predicted Maximum File Size**, typ UINT32, `GetSet=0`, `CurrentValue=34497536`. To jest źródłem mylącego odczytu `gphoto2 Zoom=34.4975` w starszej próbie, nie funkcja napędu obiektywu.
- Sesja PTP zamknięta, USB zwolnione, bieżący odczyt `gphoto2` działa. Brak setterów/control, migawki, ruchu zoom, firmware/udev/systemd/repo zmian. Wniosek dotyczy dokumentowanego Camera Control PTP 2, nie wszystkich możliwych sposobów sterowania przez port fizyczny.

## 2026-10-12 — Sony ILCE-6100A BLE pairing (test)
- Operator włączył `Bluetooth Rmt Ctrl` na Sony A6100A, odłączył USB i przygotował ekran akceptacji parowania.
- VENTUNO Q BlueZ 5.72/hci0 wykryło Sony `ILCE-6100A` z ManufacturerData Sony 0x012D.
- Uruchomiono **jedną próbę** `bluetoothctl pair` wyłącznie z wykrytym Sony. Wynik: `Connected: yes`, `ServicesResolved: yes`, `Paired: yes`, `Bonded: yes`, `Pairing successful`; stan ponownie potwierdzony po zakończeniu CLI.
- Kamera ogłasza Sony BLE Remote GATT service `8000ff00-ff00-ffff-ffff-ffffffffffff` i charakterystyki `0000ff01` (remote command) oraz `0000ff02` (odpowiedź). To pasuje do dokumentowanego przez społeczność protokołu RMT-P1BT; nie wykonywano odczytów/zapisów charakterystyk ani sterowania zoomem.
- Na VENTUNO przywrócono początkowe `Pairable: no`, zatrzymano skanowanie (`Discovering: no`). Kamera nadal `Connected: yes`; `Trusted: no` (nie włączano automatycznego zaufania), zapisane BLE bond na VENTUNO i w aparacie pozostaje do następnych testów.
- `USB 054c:0f0d` zgodnie z dyspozycją operatora nadal **odłączone**. Stream Deck Plus nadal wykryty po USB.
- **Stan:** BLE pairing PASS; zoom / jednoczesny USB+BLE NIEPRZETESTOWANE. Brak instalacji oprogramowania, firmware i zmian repo Vision.

## 2026-10-12 — BLE Power Zoom TELE preflight (DRY RUN)
- Operator potwierdził ekran Sony `Sparowano`; VENTUNO potwierdził `Paired=yes / Bonded=yes / Connected=yes`.
- Read-only introspekcja BlueZ: Sony GATT `8000ff00-ff00-ffff-ffff-ffffffffffff`; `0000ff01` ma flagę `write`, `0000ff02` ma `notify`. Są zgodne z reverse-engineeringiem Freemote (Sony BLE pilot).
- Przygotowano izolowany `/srv/vision-data/tools/streamdeck-eval/sony-ble-zoom-tele-once.py` (DOMYŚLNIE DRY RUN): press TELE `02 45 10` (160 ms), następnie release TELE `02 44 00`, próba zwolnienia także w ścieżce błędu, limit czasu D-Bus, kontrola UUID urządzenia i uprawnień. Wzorzec komand wg https://github.com/coral/freemote .
- Sprawdzono składnię i wykonano jedynie DRY RUN: `SONY_BLE_PRECHECK=PASS`, bez żadnej operacji `WriteValue`. **Silnik zoomu nie był uruchamiany**.
- Faktyczna próba ruchu optyki **oczekuje na osobne zatwierdzenie użytkownika**. Będziemy wymagać trybu fotografowania poza menu parowania i wolnej przestrzeni wokół obiektywu. Nadal test, bez zmian w produkcji Vision.

## 2026-10-12 — Sony A6100A Power Zoom przez BLE, TELE pulse (AKTYWNY TEST)
- **Zatwierdzone przez użytkownika:** pojedynczy krótki impuls TELE 160 ms z komendą RELEASE. Brak USB kamery; test wyłącznie BLE na VENTUNO Q.
- Sparowane urządzenie `ILCE-6100A`, profil GATT Sony `8000ff00` / WriteValue `0000ff01`. BlueZ przed i po próbie: `Paired=yes`, `Bonded=yes`, `Connected=yes`.
- **TELE PRESS** `02 45 10` (`0x0245`, stopień 0x10): BlueZ WriteValue return code 0, 0.077 s.
- Przerwa na aktywny TELE: 160 ms.
- **TELE RELEASE** `02 44 00` (`0x0244`, stopień 0x00): BlueZ WriteValue return code 0, 0.078 s. Powtórka nie była potrzebna. Test wykonany jeden raz, proces zakończony, brak pozostawionych programów GATT.
- **TRANSPORT GATT=PASS; ruch optyczny/zmiana ogniskowej = NIEPOTWIERDZONY** — oczekujemy obserwacji operatora. Kod 0 z BlueZ potwierdza wykonanie operacji WriteValue przez stos, nie faktyczną reakcję optyczną.
- Artefakt: `/srv/vision-data/tools/streamdeck-eval/sony-ble-zoom-tele-once-result.json`; skrypt w tym samym katalogu. Produkcyjne repo Vision: clean, bez zmian. Żadnego sterowania migawką ani interfejsem USB.

### Obserwacja operatora po impulsie BLE TELE 160 ms
- Operator ocenił ruch obiektywu jako **niepewny; najprawdopodobniej brak zauważalnego ruchu**. Wynik testu sterowania zoomem: **INCONCLUSIVE**, nie PASS ani definitywny FAIL. BlueZ potwierdził zapisy PRESS i RELEASE do GATT, ale nie ruch optyczny ani zmianę ogniskowej.
- Dokumentacja pilota Sony RMT-P1BT potwierdza sterowanie zoomem elektrycznym i zależność prędkości od obiektywu. Freemote opisuje `02 45 10` jako najwolniejszy TELE PRESS i `02 44 00` jako TELE RELEASE. 160 ms może być za krótkim czasem do zauważalnego ruchu; **nie testowano dłuższego impulsu**.
- Dalszy test wyłącznie po zgodzie operatora: jeden ograniczony czasowo impuls TELE np. 0,8–1,0 s, komenda RELEASE nawet w ścieżce błędu, kontrola ruchu na skali obiektywu i przywrócenie warunków testowych. Bez zmian produkcyjnych.

## 2026-10-12 — Sony A6100A BLE Power Zoom TELE 1000 ms (zatwierdzony test)
- Użytkownik zatwierdził **jeden impuls TELE przez 1 sekundę** i RELEASE.
- Przed wykonaniem: `ILCE-6100A` połączony / sparowany / bonded z VENTUNO Q; GATT `0000ff01-0000-1000-8000-00805f9b34fb` (write). Żadnych innych aktywnych procesów sterujących kamerą.
- Test przygotowano na bazie wcześniejszego skryptu, zapisano osobno jako `sony-ble-zoom-tele-1000ms.py`; wykonano dry-run PASS.
- TELE PRESS `02 45 10` → BlueZ `WriteValue` exit=0, 0.100 s. Po 1.0 s TELE RELEASE `02 44 00` → exit=0, 0.076 s. Bez drugiego impulsu.
- Stan po teście: Sony nadal `Paired=yes`, `Bonded=yes`, `Connected=yes`. Brak procesów GATT. Repo Vision clean, produkcja bez zmian.
- JSON z wynikami: `/srv/vision-data/tools/streamdeck-eval/sony-ble-zoom-tele-1000ms-result.json` (`outcome=PRESS_AND_RELEASE_OK`).
- **Weryfikacja faktycznego ruchu / zmiany kadru: OCZEKUJE NA OBSERWACJĘ OPERATORA**. Kod wyjścia `0` z BlueZ nie dowodzi, że aparat uruchomił silnik Power Zoom.

### Wynik końcowy testu BLE TELE 1000 ms — potwierdzenie operatora
- Operator jednoznacznie potwierdził **fizyczny ruch obiektywu Sony E PZ 16–50 mm OSS II** po jednokrotnym impulsie TELE 1.0 s z VENTUNO Q przez Bluetooth.
- Połączenie BLE: Sony ILCE-6100A, GATT FF01; PRESS `02 45 10`, po 1000 ms RELEASE `02 44 00`. Oba wywołania BlueZ zakończyły się `exit=0`; później operator potwierdził reakcję napędu optycznego.
- **WYNIK: BLE TELE ZOOM = PASS (transport + obserwacja fizycznego ruchu).** Nie potwierdzono jeszcze kierunku WIDE, mapowania pokrętła Stream Deck na zoom ani równoczesnego USB PTP + BLE.
- Implementacja pozostaje **wyłącznie testowa**; brak autostartu/usługi i brak wdrożenia produkcyjnego Vision. Dalsze testy ruchu wyłącznie po osobnej zgodzie.
