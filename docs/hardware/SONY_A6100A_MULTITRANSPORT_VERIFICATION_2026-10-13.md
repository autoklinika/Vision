# Sony ILCE-6100A — HDMI, Wi-Fi, USB/PTP, BLE i import oryginałów (2026-10-13)

**Projekt:** Vision / VENTUNO Q / fotograficzna akwizycja PCB i ECU  
**Zakres:** rzeczywiste testy aparatu 12–13 października 2026, jako kontynuacja [raportu USB/PTP z 10 października](SONY_A6100_VERIFICATION_2026-10-10.md).  
**Status:** **PASS funkcjonalny** dla HDMI (obserwacja operatora) + Wi-Fi (sterowanie i zdjęcia) + późniejszy import RAW/JPEG przez USB Mass Storage; **NOT TESTED** dla w pełni bezobsługowego cyklu i parametrów grabbera HDMI.  
**Charakter dokumentu:** opis testów, **nie** implementacja produkcyjna ani akceptacja Vision Hardware Baseline v1.

## 1. Konfiguracja i granice testu

- Aparat: **Sony ILCE-6100A** z obiektywem **E PZ 16–50 mm F3.5–5.6 OSS II**; karta SD exFAT około 64 GB.
- Host: **Arduino VENTUNO Q**, Ubuntu 24.04.4 LTS ARM64, kernel `6.8.0-1084-qcom`.
- Wi-Fi Sony: dedykowany adapter **Realtek RTL8188EUS**, osobny od głównej sieci VENTUNO (bez zmiany default route i DNS).
- Zapis testów i zdjęć: tylko lokalny NVMe pod `/srv/vision-data/vision/sessions/`.
- HDMI: wyjście aparatu podłączone bezpośrednio do monitora. Brak grabbera UVC, zatem obraz i brak ikon potwierdzał **operator**, nie VENTUNO.
- Bluetooth: wcześniej sparowany pilot Sony BLE przez BlueZ; używany do testów porównawczych, **nie** jest preferowanym docelowym kanałem sterowania.
- USB Sony: **PC Remote/PTP** `054c:0f0d` oraz **Mass Storage** `054c:0f0b`. Są to różne tryby połączenia.
- Żadne zdjęcia i surowe dzienniki z numerami seryjnymi, adresami ani danymi scen nie są publikowane w Git.

## 2. Matryca wyników

| Obszar / scenariusz | Wynik | Zakres potwierdzenia |
| --- | --- | --- |
| Wi-Fi ScalarWebAPI, wykrywanie i odczyty | **PASS** | Aparat odpowiada, 55 aktywnych metod Camera API |
| Wi-Fi sterowanie parametrami | **PASS częściowy** | f-number, shutter, ISO, white balance, flash, timer, continuous mode: zapis/odczyt i przywrócenie |
| Wi-Fi korekta ekspozycji w M | **UNVERIFIED** | Komenda ACK, ale wartość odczytu nie zmieniła się |
| Wi-Fi Power Zoom IN/OUT | **PASS** | Zmiana pozycji API 0–100; powtarzalność i mm **UNVERIFIED** |
| Wi-Fi fotografowanie | **PASS** | `actHalfPressShutter` + `actTakePicture`, JPEG postview |
| Wi-Fi Live View | **PASS** | Pojedyncze klatki JPEG 640×424 |
| Wi-Fi bezpośredni transfer pełnego JPG/ARW z Remote API | **NOT SUPPORTED w badanej sesji** | Brak odpowiednich metod i tylko JPEG postview ~1,75 MP |
| Zapis oryginalnego RAW+JPEG na SD podczas sterowania Wi-Fi | **PASS** | Para JPG 6000×4000 i ARW tego samego ujęcia |
| HDMI — czysty podgląd przy USB PTP lub Wi-Fi | **PASS — obserwacja operatora** | Nakładki wyłączone; obraz widoczny w normalnym kadrze |
| HDMI cyfrowe 1080p/4K, FPS, opóźnienia | **NOT TESTED** | Grabber/UVC jeszcze niepodłączony |
| USB PC Remote — Preview | **PASS** | JPEG 1024×680; m.in. 8/8 i 4/4 klatki w osobnych seriach |
| USB PC Remote — pełny JPEG | **PASS** | JPEG 6000×4000, na NVMe |
| USB PC Remote — ARW | **PASS historyczny** | Weryfikacja RAW-02 z 10 października, nie powtarzano w każdym trybie |
| USB + BLE + fizyczny HDMI | **PASS** | BLE TELE i USB Preview równolegle; EXIF 16→20 mm |
| USB PC Remote + Wi-Fi ScalarWebAPI | **BLOCKED** | Sony nie pozwolił włączyć `Steruj ze smartfonu` |
| Po Wi-Fi: automatyczne USB Mass Storage po wpięciu przewodu | **PASS, 1 próba** | Użytkownik wpiął kabel, Sony zgłosił storage bez dodatkowego menu |
| SD Mass Storage — odczyt i kopia na NVMe | **PASS** | exFAT read-only, JPG i ARW, SHA-256 źródła i kopii zgodne |
| Linux USB port disable + ponowna enumeracja Sony | **PASS transportu** | Sony zniknął z USB i wrócił; aparat pozostawał w „Trybie USB” |
| Automatyczne wznowienie Wi-Fi po logicznym/fizycznym odłączeniu USB | **FAIL w badanej próbie** | Połączenie DIRECT nie pojawiło się automatycznie |
| `Zawsze połączony = Wł.` po cyklu USB lub restarcie | **NOT TESTED do końca** | Następna sesja Wi-Fi zestawiona, potem rozładowała się bateria |

## 3. ScalarWebAPI — identyfikacja i możliwości

Z urządzenia przez SSDP pobrano opis usług Sony. Wystawiał `camera`, `system`, `guide`, `accessControl`; aplikacja zgłaszała **Smart Remote Control 2.1.7**, Camera API w wersjach 1.0–1.8, łącznie **55 aktywnych metod**. Odczyty parametrów (40 badanych getterów) zakończyły się powodzeniem. Ta liczba **nie oznacza**, że 55 setterów wypróbowano fizycznie.

W testach zmian z odczytem zwrotnym i przywróceniem:
- przysłona: **f/5.6 → f/6.3 → f/5.6**; pierwszy timeout, osobna powtórka PASS;
- migawka: **1/250 → 1/320 → 1/250**;
- ISO: **AUTO → 100 → AUTO**;
- balans bieli: **AUTO → Daylight → AUTO**;
- samowyzwalacz: **0 → 2 s → 0**;
- flash: **On → Rear Sync → On**;
- zdjęcia seryjne: **Single → Continuous → Single** (setter tej wersji API zwracał pustą tablicę, ale stan zmienił się i wrócił);
- korekta ekspozycji: w M komenda dla +1 przyjęta, jednak odczyt nadal `0`, więc bez PASS funkcjonalnego.

**Fotografowanie Wi-Fi:** bezpośrednie `actTakePicture` raz zwróciło błąd aparatu `40400`; sekwencja `actHalfPressShutter` → `actTakePicture` → pobranie URI JPEG → `cancelHalfPressShutter` przeszła. Nie zakładać, że autofocus jest zawsze gotowy ani że każdy ACK oznacza zachowany oryginał.

**Podgląd Wi-Fi:** HTTP JPEG 640×424. Zdalne wykonanie zdjęcia daje podglądowy JPEG 1616×1080. W testowanym trybie nie wystawiano komend `getPostviewImageSize`, `getStillSize`, przeglądania zawartości SD ani transferu oryginalnego ARW. Nie mylić tego z funkcją zapisu do **samej karty SD**.

### 3.1. Power Zoom przez Wi-Fi

- `actZoom(in/out, 1shot)` zwróciło sukces, a pozycja API zmieniła się np. **74 → 93 → 77**.
- `actZoom(..., start/stop)` działało, ale dokładnie taki sam czas impulsu nie daje stałego przesunięcia.
- Testy 10 ms dały m.in. **−4** i **+17** jednostek; 80/120 ms również dawały różnice kierunkowe.
- `zoomPosition` to wartość reprezentacyjna 0–100, **nie** bieżąca ogniskowa w mm.
- Dla Vision potrzebny jest regulator sprzężenia zwrotnego (ruch, stop, stabilizacja, odczyt, tolerancja, limit prób) i kalibracja mm / pozycji z EXIF.

## 4. HDMI i USB/BLE — rzeczywiste eksperymenty

- Przy USB PC Remote użytkownik potwierdził obraz na monitorze HDMI, początkowo z ikonami. Po `Wyśw. inf. HDMI → Wył.` obraz stał się **czysty**.
- Po tej zmianie gPhoto2 nadal pobierał klatki USB 1024×680, a Sony zachował połączenie BLE.
- Przy USB + BLE + HDMI wysłano impuls **TELE 650 ms**; 5/5 równoległych odczytów USB Preview PASS, zdjęcie pełne po impulsie PASS. EXIF pełnych zdjęć wskazał zmianę **16 → 20 mm**.
- Przy wcześniejszym BLE+USB wystąpił błąd `Could not capture image`; podobny timeout wystąpił po **rozłączeniu BLE**, więc **nie wolno uznawać BLE za udowodnioną przyczynę**.
- W trybie Wi-Fi ekran nawiązywania połączenia Sony czasowo wygaszał obraz na HDMI. **Po wyjściu z ekranu połączenia obraz wracał**; operator potwierdził jednoczesny czysty obraz HDMI i Wi-Fi z połączonym VENTUNO.
- Nie potwierdzono fizycznych parametrów HDMI (grabber nieobecny), tylko zachowanie na monitorze.

## 5. Najważniejszy dowód: RAW+JPEG z sesji Wi-Fi na SD

W czasie aktywnego HDMI i Wi-Fi VENTUNO wykonał zdjęcie przez ScalarWebAPI. Otrzymał JPEG postview **1616×1080**, **463 984 B**, z czasem EXIF **2026-10-13 14:04:15** według zegara aparatu.

Po zakończeniu sesji Wi-Fi użytkownik podłączył kabel USB; aparat zgłosił **Mass Storage** i kartę exFAT. Operator zamontował ją **read-only** na VENTUNO. W `DCIM/100MSDCF/` znaleziono:

| Plik na karcie SD | Wielkość | Walidacja |
| --- | ---: | --- |
| `DSC00020.JPG` | **12 877 824 B** | JPEG **6000×4000**, EXIF A6100A, czas **14:04:15**, ogniskowa 20 mm |
| `DSC00020.ARW` | **24 816 384 B** | SONY ARW/TIFF, ten sam identyfikator DSC00020 i czas |

Oryginały skopiowano do katalogu na NVMe. SHA-256 źródła i kopii były identyczne:

- `DSC00020.JPG`: `51fc6cd21a51e19c410dff73128b9e8a04ebb5f33666f49096ab032e6acc3d65`.
- `DSC00020.ARW`: `70d5c22b945dc3a22d62f5ed653355785a45f8b4ffd47f2a21c59eecf0c26278`.

**Ocena:** pełna droga **Wi-Fi shutter → lokalny RAW+JPEG na SD → późniejszy odczyt przez USB Mass Storage → NVMe** zakończyła się **PASS na jednej fotografii**. Nie oznacza to jeszcze niezawodności serii kilkuset ujęć.

Kontrola RAW dotyczyła prawidłowego formatu pliku, obecności oryginału i SHA-256; pełnego demosaicingu zawartości sensora nie wykonano.

## 6. Przełączanie Wi-Fi ↔ USB: zakończona próba i granice

### 6.1. USB po zakończeniu fotografowania

Po zatrzymaniu sesji Wi-Fi użytkownik **fizycznie podłączył USB** i Sony automatycznie zgłosił `054c:0f0b` Mass Storage. USB PC Remote (`054c:0f0d`) jest osobnym trybem — **nie jest domyślną drogą importu istniejących zdjęć z SD**.

Karta była zamontowana na VENTUNO `ro,nosuid,nodev,noexec`; kopie powstały na NVMe, a karta została następnie odmontowana. Warunek produkcyjny: mount ro, pełna walidacja źródło/kopia, fail-closed, jawne odmontowanie przed odcięciem portu.

### 6.2. Wyłączanie logiczne portu VENTUNO

Urządzenia laboratoryjne:
- Sony Mass Storage: USB root hub port **1-2**;
- Realtek Wi-Fi: port **1-4**.

Jednorazowy test atrybutu Linux `usb1-port2/disable` (bez zamontowanej karty) i timer przywracający port:

| Stan | Linux | Aparat i sieć DIRECT |
| --- | --- | --- |
| `disable=1` | Sony znika z `lsusb` | Ekran Sony stale pokazuje „Tryb USB”, DIRECT nie rozgłasza |
| `disable=1`, ponowna kontrola po ~5 s | Sony nadal nieobecny w `lsusb` | Nadal brak DIRECT |
| `disable=0` | Sony ponownie enumerowane, nowy numer urządzenia | Wraca jako Mass Storage, DIRECT nadal brak |

**Wniosek:** izolacja logiczna USB działa **po stronie Linux**, lecz nie została rozpoznana przez Sony jako odłączenie przewodu. Możliwy powód to pozostawiony VBUS 5 V albo zachowanie firmware. **Nie wolno** bez pomiaru twierdzić, że port odciął VBUS. Nie powtarzać eksperymentu bez osobnej zgody.

### 6.3. Fizyczne odłączenie kabla i „Zawsze połączony”

Po **fizycznym** odłączeniu USB obraz HDMI powrócił, a w menu `Steruj ze smartfonu` pozostało `Wł.`. Mimo tego Sony **nie rozgłaszał samodzielnie DIRECT**, także po ponownym wyjściu z ekranu łączenia w opisanej próbie.

Użytkownik włączył opcję `Zawsze połączony → Wł.`. Samo ustawienie nie uruchomiło natychmiast DIRECT. Następnie operator zestawił jednorazowo połączenie Wi-Fi z VENTUNO (`połączone`), jednak **akumulator rozładował się przed właściwą weryfikacją cyklu USB/ponownego rozruchu**.

**Status „Zawsze połączony”: NOT TESTED do końca.** Nie zakładać, że funkcja gwarantuje stale emitowany SSID lub automatyczne wznowienie po USB. Następny test powinien rozróżnić utrzymanie sesji z aktywnym klientem, broadcast SSID i odzyskanie sesji po odłączeniu USB.

## 7. Problem z odczytem ogniskowej przez BLE i PTP

- BLE Sony posiada m.in. `FF01` (write komend pilota), `FF02` (notify) oraz `DD21` (read nieopisanych danych).
- **Nie potwierdzono** charakterystyki zwracającej aktualną ogniskową/zoom w mm.
- W USB gPhoto2 pokazuje mylący parametr `Zoom = 34.4975`, lecz wcześniejsza diagnostyka PTP 2 z referencją Sony ustaliła, że kod **0xD214 = Predicted Maximum File Size**, a nie położenie mechanizmu optycznego. **Nie używać do sterowania zoomem**.
- Wiarygodna ogniskowa optyczna jest obecna w EXIF **po wykonaniu zdjęcia**, co potwierdzono m.in. 16→20 mm podczas BLE+USB oraz 20 mm podczas Wi-Fi→SD.

## 8. Decyzja robocza i pozostałe bramki

**Preferowany kandydat:** **HDMI clean view + Wi-Fi ScalarWebAPI → zapis RAW+JPEG na SD → po sesji USB Mass Storage → import na NVMe**. Wybór uzasadnia funkcjonalny PASS pojedynczego pełnego cyklu. Nie zatwierdzono produkcyjnego wdrożenia ani wykluczenia awaryjnej ścieżki USB PC Remote/BLE.

**Do zamknięcia przed implementacją:**
1. Bezobsługowy powrót do Wi-Fi po cyklu USB (największa otwarta blokada); pomiar zachowania opcji `Zawsze połączony`.
2. Weryfikacja faktycznego rozłączenia elektrycznego USB/VBUS i ew. wybór kontrolowanego przełącznika/huba, bez ryzyka dla karty SD.
3. Podłączenie i pomiar grabbera HDMI/UVC (formaty, 1080p 30/60, opóźnienia, utrata klatek) podczas Wi-Fi shutter.
4. Wielokrotne zdjęcia 20–100–300 szt., wykrywanie braków/par JPG/ARW, bezpieczne odstępy, recovery po błędach.
5. Kalibracja Power Zoom + EXIF mm, stabilizacja ostrości i parametry oświetlenia, odchyłki powtarzalności.
6. Retencja karty SD, manifesty/hashing, idempotentny transfer i bezpieczne odmontowanie przed zmianą portu.

**Zasady:** bez aktualizacji firmware, zapisów na SD, automatycznych restartów, scalania do `main` i ingerencji w repozytoria innych projektów bez zgody.

## 9. Dowody

Syntetyczny rejestr lokalnych dowodów: [EVIDENCE_REGISTER_SONY_2026-10-13.md](EVIDENCE_REGISTER_SONY_2026-10-13.md).

Dokument 10 października pozostaje miarodajny dla wcześniejszych testów USB, RAW-02 i STAB-01–06: [SONY_A6100_VERIFICATION_2026-10-10.md](SONY_A6100_VERIFICATION_2026-10-10.md).
