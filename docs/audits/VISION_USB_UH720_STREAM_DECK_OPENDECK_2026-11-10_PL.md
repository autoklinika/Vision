# Vision — USB UH720, Stream Deck Plus, logo startowe i animacja OpenDeck

**Raport integracyjno-diagnostyczny (PL): 2026-11-10**  
**Platforma:** Arduino VENTUNO Q / Ubuntu 24.04.4 ARM64, kernel `6.8.0-1089-qcom`.  
**Zakres:** obserwacje sprzętowe na stanowisku `vision`, odwracalne zmiany konfiguracji, testy protokołu HID, interfejs użytkownika i STOP SW.  
**Ostatnia kontrola stanu:** 2026-11-10 ok. 22:53 UTC (23:53 CET).  
**Zasady dowodowe:** `PASS` oznacza wynik konkretnego testu; transmisja bez błędu nie oznacza potwierdzenia zapisu w pamięci; poprawny zapis w logu nie oznacza gwarantowanego zatrzymania robota. To nowszy odczyt niż wcześniejszy [AS-BUILT](../operations/VISION_AS_BUILT_2026-11-10.md).

## 1. Podsumowanie i stan końcowy

| Obszar | Ustalenie | Status |
|---|---|---|
| TP-Link UH720 v5.0, zasilacz 12 V / 3,3 A | Hub wykrywany po restarcie, USB 2.0 i 3.0, cztery logiczne interfejsy z `power/control=on` | **PASS w bieżących testach**; wielodniowa stabilność nadal do obserwacji |
| Konflikt przy inicjalizacji USB | Wyłączenie automatycznego ładowania `onboard_usb_hub` usunęło rozłączenia w porównanym rozruchu | **Silnie uprawdopodobniona przyczyna**, nie udowodniona dla każdego rozruchu |
| Stream Deck Plus | `0fd9:0084`, wykrycie HID i komunikacja OpenDeck | **PASS** |
| Logo startowe | Trwale zapisane logo `VISION`, użytkownik potwierdził wizualnie po ponownym podłączeniu | **PASS** |
| Animacja po połączeniu | Autorski moduł OpenDeck, 47 klatek, 188 aktualizacji segmentowych, biały ekran → czarny ekran | **PASS w logach**, wizualna ocena ostatniej wersji do wykonania |
| Klawisz `STOP SW` | Polecenia naciśnięć trafiają do skryptu `nero_stop.py` także po integracji animacji | **PASS: tor przycisk → OpenDeck → skrypt** |
| STOP do AgileX NERO | Robot odłączony; skrypt odrzuca podłączony adapter USB-CAN (niezgodny VID) | **NOT VALIDATED / BLOCKED**; nie jest to niezależny E-STOP |
| Zmiany na GitHub | Ten raport jest dokumentacją; produkcyjne binaria, prywatne logi i eksperymentalne obrazy zostają na NVMe | **Docs only / review required** |

## 2. Sprzęt i rzeczywista topologia USB

- **Hub:** TP-Link UH720, wersja sprzętowa v5.0, 7 portów danych USB 3.0 + 2 porty ładowania, zasilanie zewnętrzne **12 V DC / 3,3 A**.
- **Host:** Texas Instruments TUSB73x0/TUSB7340, kontroler xHCI pod PCIe `0000:04:00.0`.
- **USB 2.0:** `usb1`, 480 Mb/s, dwa stopnie Genesys Logic `05e3:0610`: urządzenia `1-4`, `1-4.1`.
- **USB 3.x:** `usb2`, 5000 Mb/s, dwa stopnie Genesys Logic `05e3:0626`: urządzenia `2-4`, `2-4.1`.
- **Deck:** Elgato Stream Deck Plus `0fd9:0084`, zwykle `1-4.1.4` / `/dev/hidraw0` (numer urządzenia USB może się zmieniać).
- **Oddzielna gałąź hosta:** `usb3`, kontroler Qualcomm DWC3, w tym wewnętrzny interfejs `gs_usb` / `cdc_acm` dla interfejsów CAN. Sterowniki `dwc3`, `dwc3_qcom`, `xhci_hcd` pozostały aktywne.
- W czasie prób NERO był **fizycznie odłączony**, a `can0`, `can1`, `can2` miały stan `DOWN`. Odczyty nie obejmowały pełnego testu innych peryferiów (np. Sony i Luxonis).

### Problem pierwotny

Linux nieregularnie rozpoznawał UH720. Przy jednym rozruchu zaobserwowano: pierwsze rozpoznanie huba ok. 7,6–8,6 s, Stream Deck ok. 12 s, potem rozłączenia wewnętrznego stopnia USB 2.0 `1-4.1` ok. **15,874 s** i **16,654 s**, a następnie ponowną enumerację.

Rejestracja `onboard_usb_hub` nastąpiła około **15,873556 s**, tuż przed pierwszym rozłączeniem (**15,874112 s**, różnica ok. 0,56 ms). Moduł miał alias dla `05e3:0610`, lecz w audycie **nie stwierdzono aktywnych powiązań** modułu z fabrycznymi urządzeniami ani odpowiednich węzłów Device Tree dla zewnętrznego UH720. Związek czasowy jest przekonujący, ale nie stanowi samodzielnego dowodu przyczynowości.

### Trwała konfiguracja zastosowana na Vision

1. **Reguła udev** `/etc/udev/rules.d/80-vision-uh720-power.rules` ograniczona do identyfikatorów Genesys `05e3:0610` i `05e3:0626` oraz aktualnego fizycznego toru USB. Ustawia `ATTR{power/control}="on"` dla czterech logicznych interfejsów. Nie zmienia globalnej polityki USB.
2. **Modprobe** `/etc/modprobe.d/90-vision-uh720-no-onboard-usb-hub.conf` z `blacklist onboard_usb_hub`. To blokada *globalnego automatycznego ładowania* aliasem, nie tylko jednego portu; może wymagać ponownej oceny po zmianie sprzętu/Device Tree.
3. Po restarcie: `onboard_usb_hub` niezaładowany, wszystkie cztery interfejsy huba w stanie `power/control=on`, runtime `active`, prędkości 480/5000 Mb/s. W porównanym rozruchu nie odnotowano wcześniejszych dwóch rozłączeń.
4. W późniejszym odczycie końcowym (ok. 22:53 UTC) wykryto oba stopnie USB 2.0 i 3.x, reguły nadal istniały, wszystkie cztery interfejsy zachowywały `on`, a usługa OpenDeck była `active`.

**Ograniczenia:** przejście kontroli po jednym restarcie nie jest jeszcze testem długookresowym; hub, przewód i zasilacz pozostają potencjalnymi źródłami awarii. Po przełożeniu UH720 do innego portu regułę ograniczoną przez `ID_PATH` trzeba zrewidować. Nie blokować pozostałych sterowników USB.

## 3. Stream Deck Plus, HID i OpenDeck 2.14.1

W Vision działa `vision-opendeck.service` jako usługa użytkownika. OpenDeck 2.14.1 obsługuje panel oraz profil `Default`, w którym prawy dolny klawisz (`Keypad.7.0`) jest przypisany do `NERO STOP SW` → `nero_stop.py --send`.

Odczyty kontrolne:
- `lsusb` i sysfs: `0fd9:0084`, interfejs HID i `/dev/hidraw0` dostępne;
- proces OpenDeck otwiera deskryptor `/dev/hidraw0` z uprawnieniami użytkownika;
- żądania odczytu `GET_FEATURE` (`0x05` i `0x06`) zakończyły się powodzeniem; firmware zgłaszało **2.0.3.2** i spójny numer seryjny (niepublikowany);
- obraz interfejsu OpenDeck pokazywał podłączonego Decka i czerwony przycisk `STOP SW`.

**Korekta błędnej wcześniejszej diagnozy:** napis `"devices":[]` w argumentach startowych wtyczki *nie* jest bieżącą telemetrią połączenia. Kod OpenDeck `src-tauri/src/plugins/info_param.rs` tworzy listę urządzeń jako snapshot w momencie startu procesu wtyczki. Może ona pozostać pusta po późniejszej enumeracji, mimo że aplikacja obsługuje Deck. Weryfikować równocześnie fizyczny HID, okno OpenDeck oraz rzeczywiste zdarzenia przycisków. Podczas pojedynczych odłączeń zarejestrowano też ostrzeżenie o chwilowym braku VID/PID — nie stanowiło to trwałego uszkodzenia sprzętu.

Źródła implementacji: [OpenDeck `elgato.rs`](https://github.com/nekename/OpenDeck/blob/v2.14.1/src-tauri/src/elgato.rs), [`info_param.rs`](https://github.com/nekename/OpenDeck/blob/v2.14.1/src-tauri/src/plugins/info_param.rs).

## 4. Trwałe logo startowe VISION

**Wymaganie:** odręczny, czarny napis `VISION` jak napisany długopisem; białe tło wyłącznie na dolnym pasku, czarny obszar klawiszy powyżej.

- Pierwszy eksperyment użył komendy HID `0x09` z nagłówkiem 16 B i JPEG 800 × 100. Pakiety zostały wysłane bez błędów systemowych, lecz **logo nie zmieniło się** po wyłączeniu i ponownym podłączeniu urządzenia.
- Analiza implementacji wykazała, że dla komendy logo startowego `0x09` niezależne źródło opisuje **8-bajtowy** nagłówek. Poprzedni format odpowiadał raczej aktualizacji części LCD. Rozróżniono pełny obszar graficzny **800 × 480** i pasek dotykowy **800 × 100**.
- Drugi eksperyment (pełny JPEG 800 × 480, report HID `0x02`, command `0x09`, nagłówek 8 B) spowodował zmianę obrazu na **całej powierzchni LCD, łącznie z klawiszami**. Użytkownik potwierdził to na fizycznym urządzeniu.
- Trzeci obraz zachowuje format 800 × 480, ale jego **górne 380 px jest czarne**, a **dolne 100 px białe z czarnym napisem VISION**. Użytkownik potwierdził docelowy wygląd logo po ponownym połączeniu.
- Logo jest zapamiętane przez Deck i wyświetlane przed uruchomieniem OpenDeck. Nie ma wiarygodnego zwrotnego `readback` zapisanego logo; za dowód przyjęto obserwację na urządzeniu po odłączeniu USB.
- Biblioteka [DeckSurf SDK — StreamDeckPlus](https://github.com/dend/decksurf-sdk/blob/main/src/DeckSurf.SDK/Models/Devices/StreamDeckPlus.cs) zawiera `SetBootLogo()`; alternatywny opis sekwencji pakietów: [gadgetdeck — RESEARCH](https://github.com/DDRBoxman/gadgetdeck/blob/main/docs/RESEARCH.md). Jest to częściowo protokół społecznościowy; nie zaleca się ślepego wysyłania kolejnych sekwencji.

**Środowisko testowe na Vision:**  
`/srv/vision-data/experiments/streamdeck-bootlogo-lab-20261110/`

Zawiera pliki `vision_deck_bootlogo.py`, `bootlogo_protocol_v2.py`, testy offline, kopie obrazów i dokumentację prób. Do zapisu USB trzeba było **zatrzymać OpenDeck i uruchomić go ponownie**; podczas tej czynności STOP SW jest niedostępny. Nie wykonano aktualizacji firmware.

## 5. Animacja po połączeniu z Vision

**Cel:** po zestawieniu komunikacji HID na pasku 800 × 100 odręcznie rysuje się `VISION`, a po zakończeniu pasek łagodnie gaśnie do czerni. Podczas pisania tło pozostaje białe, a pismo czarne.

Zastosowano autorski moduł **`vision.intro.sdPlugin`** uruchamiany przez OpenDeck:
- Cztery segmenty dolnego LCD po **200 × 100 px**; dedykowane pozycje `Encoder.0..3` w profilu `Default` były wcześniej puste.
- Klatki JPEG są wysyłane wyłącznie poprzez OpenDeck `setFeedback` i layout `pixmap` — moduł **nie otwiera bezpośrednio `hidraw`** i nie modyfikuje firmware.
- `willAppear` z czterech segmentów uruchamia sekwencję; `willDisappear` przerywa ją po odłączeniu urządzenia lub zmianie kontekstu.
- Oryginalnie testowano 36 klatek po 12 FPS: rysowanie → krótka pauza → wygaszenie, 144 aktualizacje segmentów.
- Korekty po oględzinach: odwrócenie niewłaściwych kolorów (na **białe tło / czarny napis**), następnie zakończenie w czerni zamiast pozostawienia białego tła, a później wydłużenie i wygładzenie przejścia.

**Wersja końcowa z 2026-11-10:**

| Parametr | Wartość |
|---|---|
| Rysowanie | **28 klatek × 12 FPS** |
| Krótka pauza | **3 klatki × 12 FPS** |
| Wygaszenie | **16 klatek × 16 FPS**, krzywa `smoothstep` |
| Suma | **47 klatek**, **188** aktualizacji czterech segmentów |
| Łączny czas samej sekwencji | około **3,6 s** (+ niewielka zwłoka startowa) |
| Klatka końcowa | **RGB (0, 0, 0)** we wszystkich czterech segmentach |
| Profil STOP SW | **Nie zmieniano**; zgodność klawiszy i hash profilu potwierdzone |

Kolejne wartości tła podczas końcowego wygaszania (0–255) w teście offline: `252, 244, 231, 215, 196, 174, 151, 128, 104, 81, 59, 40, 24, 11, 3, 0`. Kontrola końcowa potwierdziła `INTRO_FINISHED frames=47 updates=188 final_frame=46`. Przy jednym podejściu skrypt wdrożeniowy wycofał zmianę, ponieważ przy samym restarcie OpenDeck nie otrzymał zdarzenia `willAppear` w krótkim oknie testowym. Po analizie ponowiono wdrożenie bez takiego błędnego kryterium; nowe klatki, proces wtyczki oraz logi przeszły test. Użytkownik powinien jeszcze ocenić płynność ostatniej poprawki na fizycznym urządzeniu.

**Środowisko i rollback:**  
`/srv/vision-data/experiments/streamdeck-intro-animation-20261110/`  
Wersje robocze, `INTEGRATION-REPORT.md`, kopie w `backups/` oraz `rollback_intro.py` pozostają na NVMe. Aktywny moduł znajduje się w `/srv/vision-data/tools/streamdeck-prod/config/opendeck/plugins/vision.intro.sdPlugin/`. Przed wycofaniem konieczna weryfikacja, czy profil nie został później zmodyfikowany; skrypt rollback odmawia bezrefleksyjnego nadpisania zmian.

**Uwaga operacyjna:** animacja ma status integracji wizualnej (nie funkcji bezpieczeństwa). Nie powinna przejmować interfejsu USB ani blokować mechanizmu STOP; równoczesne pomiary opóźnienia przycisku podczas wszystkich faz animacji nie zostały jeszcze przeprowadzone.

## 6. STOP SW — osobny audyt funkcjonalny

Po konfiguracji huba, logo i animacji wykonano fizyczne naciśnięcia prawego dolnego przycisku `STOP SW`. Pojawiły się m.in. dwie serie po cztery rejestrowane żądania oraz późniejsza intensywna seria.

**Ostatnia seria (2026-11-10, UTC):**
- Pierwszy `STOP_REQUESTED`: **22:48:23,195365**.
- Ostatni `STOP_REQUESTED`: **22:48:32,972231**.
- Czas obserwacji: **9,777 s**.
- **26 rekordów `STOP_REQUESTED` / 26 rekordów `STOP_DELIVERY_FAILED`**.
- Czas od zapisania żądania przez skrypt do odrzucenia przez walidator USB-CAN: **min. 8,2 ms, średnio 13,7 ms, maks. 23,2 ms**. **To nie jest pomiar latencji od fizycznego naciśnięcia do żądania ani pomiar zatrzymania ramienia.**
- Błąd walidatora: `Wrong USB-CAN adapter ID_VENDOR_ID: 1209`; skrypt oczekuje rodziny adaptera z VID `1d50`.
- Interfejsy `can0`, `can1`, `can2` były `DOWN`; NERO odłączony. Żadne polecenie STOP z tej serii **nie dotarło do robota**.

**Co potwierdzono:** przycisk jest fizycznie rozpoznawany, OpenDeck przetwarza zdarzenia, uruchamia poprawny skrypt i zapisuje zdarzenia w logu; po integracji animacji nie stwierdzono utraty żadnego *zarejestrowanego* żądania.  
**Czego nie potwierdzono:** liczby wszystkich faktycznych mechanicznych naciśnięć (brak niezależnego rejestratora), działania STOP w każdej fazie animacji z dokładnymi znacznikami czasowymi, prędkości reakcji od naciśnięcia, dostarczenia STOP do NERO w tej konfiguracji, ani zachowania ramienia w ruchu.

Przy wcześniejszym, osobnym eksperymencie z prawidłowym adapterem odczytano `EMERGENCY_STOP(0x1)` z NERO bez wykonywania ruchu; nie wolno utożsamiać tego z dzisiejszym testem USB ani z potwierdzeniem drogi hamowania. Patrz [ADR NERO STOP](../architecture/ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md).

**Bezpieczeństwo:** STOP SW jest poleceniem programowym i **nie zastępuje niezależnego sprzętowego E-STOP**. Przed pierwszymi ruchami NERO wymagane są interlock, ocena ryzyka, poprawne i bezpieczne podłączenie, kontrola adaptera i testy ruchowe wg zatwierdzonej procedury.

## 7. Pliki lokalne, odtwarzalność i zalecane kontrole

| Element | Lokalizacja / sposób sprawdzenia |
|---|---|
| Trwała reguła zasilania huba | `/etc/udev/rules.d/80-vision-uh720-power.rules` |
| Testowa blokada autoload | `/etc/modprobe.d/90-vision-uh720-no-onboard-usb-hub.conf` |
| Skrypty wdrożenia i rollback huba | `/srv/vision-data/tools/usb-uh720/` |
| Logo startowe, protokół HID i testy | `/srv/vision-data/experiments/streamdeck-bootlogo-lab-20261110/` |
| Animacja, kopie, raport, generator, rollback | `/srv/vision-data/experiments/streamdeck-intro-animation-20261110/` |
| Konfiguracja i wtyczki OpenDeck | `/srv/vision-data/tools/streamdeck-prod/config/opendeck/` |
| Usługa | `systemctl --user status vision-opendeck.service` |
| Log STOP SW | `/srv/vision-data/tools/streamdeck-prod/logs/nero-software-stop.jsonl` |
| Log animacji | `/srv/vision-data/tools/streamdeck-prod/data/opendeck/logs/plugins/vision.intro.sdPlugin.log` |

Bezpieczne kontrole tylko do odczytu:

```bash
lsusb -t
lsusb -d 0fd9:0084
for h in 1-4 1-4.1 2-4 2-4.1; do
    printf '%s=' "$h"; cat "/sys/bus/usb/devices/$h/power/control"
done
lsmod | grep onboard_usb_hub || echo "onboard_usb_hub not loaded"
systemctl --user is-active vision-opendeck.service
ip -br link show | grep '^can'
tail -n 15 /srv/vision-data/tools/streamdeck-prod/data/opendeck/logs/plugins/vision.intro.sdPlugin.log
tail -n 10 /srv/vision-data/tools/streamdeck-prod/logs/nero-software-stop.jsonl
```

**Nie publikować:** surowych logów systemowych, pełnych numerów seryjnych, prywatnych plików konfiguracyjnych, binarnych plików firmware, materiałów z kamer i sesji diagnostycznych. Ten raport zawiera wyłącznie zsyntetyzowane wyniki i standardowe identyfikatory VID:PID. Skrypty lokalne i pliki multimedialne **nie są objęte tym commitem dokumentacyjnym**.

## 8. Otwarte kwestie / warunki zamknięcia

1. **Stabilność UH720:** kilka kolejnych zimnych startów i restartów Vision, test odłącz/połącz, równoczesne obciążenie kamery i Stream Deck, kontrola błędów `dmesg`, zasilacza i przewodu USB 3.0.
2. **Globalny blacklist:** po zmianie płyty, jądra, Device Tree lub dołożeniu fabrycznych hubów ponownie ocenić, czy `onboard_usb_hub` można nadal bezpiecznie blokować.
3. **Animacja:** potwierdzić na fizycznym Decku, że wygaszanie `smoothstep` jest płynne, kończy się czernią i nie zakłóca normalnej nawigacji. W razie regresji przywrócić poprzednie klatki z katalogu `backups/`.
4. **Weryfikacja STOP podczas animacji:** skorelować logi `willAppear`, pierwszej/ostatniej klatki i wejścia przycisku z monotonicznym czasem; nie wyciągać wniosków o opóźnieniu z czasu odrzucenia przez adapter.
5. **NERO i adapter CAN:** osobno uzgodnić docelowy adapter, VID:PID, konfigurację interlocka i warunki bezpiecznego testu; obecny skrypt STOP odrzuca aktualny adapter. Nie podłączać robota w celu samej demonstracji animacji.
6. **Uporządkowanie kodu:** po pozytywnej walidacji i przeglądzie przygotować osobny PR z minimalnym, zanonimizowanym kodem wtyczki i testami offline. Nie przenosić eksperymentów automatycznie do `main`.

---

**Zarządzanie zmianą:** dokument tylko do przeglądu. Istniejące PR-y, w tym [PR #15 — archiwum / NIE SCALAĆ](https://github.com/autoklinika/Vision/pull/15), pozostają odrębne. Merge do `main` wyłącznie po jawnej zgodzie właściciela projektu.
