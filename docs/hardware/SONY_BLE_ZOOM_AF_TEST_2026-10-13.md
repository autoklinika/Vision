# Sony ILCE-6100A — test BLE zoom + AF + RAW/JPEG + UVC

Status: **PROTOTYPE / TEST przygotowany; seria sprzętowa z zoomem NOT RUN**.
Odczyt usług BLE i pasywna obserwacja: **PASS**. Data: 2026-10-13.
Rozszerzenie [prototypu AF, PR #11](https://github.com/autoklinika/Vision/pull/11).
Kod `scripts/audit/sony_zoom_af_test.py` wykorzystuje jego niezmienione Shell,
UVC, świeżą bramkę AF, odbiór i weryfikację pary. Nie zastępuje wcześniejszego
wyniku 10/10: tamta seria nie obejmowała zoomu BLE.

## Czy BLE odczytuje pozycję obiektywu?

**W badanym protokole pilota tego aparatu nie znaleziono dostępnego odczytu
ogniskowej ani pozycji focus.** Potwierdzono względne komendy WIDE/TELE;
ogniskową można zweryfikować po wykonaniu zdjęcia z JPEG EXIF FocalLength.
Nie oznacza to absolutnego ustawiania obiektywu w mm ani odczytu na żywo.

Sprawdzono istniejące sparowanie, połączono aparat bez nowego parowania i
odczytano wszystkie usługi GATT udostępnione przez BlueZ po ServicesResolved.
Nie wysyłano komend ruchu, migawki, lokalizacji ani nieznanych sond protokołu.

| Usługa / charakterystyka | Flagi na urządzeniu | Interpretacja |
| --- | --- | --- |
| FF00 / FF01 | write | Komendy pilota, bez ReadValue |
| FF00 / FF02 | notify | Znane stany AF, migawki i nagrywania; brak opisanego statusu zoomu |
| EE00 / EE01 | write | Nie badano poleceń; brak read |
| DD00 / DD21 | read | Location feature flags według referencji AlphaLoc |
| DD00 / DD11 | write | Kanał lokalizacji; nie wysyłano danych |
| DD00 / DD01 | notify | Nie interpretowano jako telemetrii obiektywu |
| 1801 / 2A05 | indicate | Standardowe Service Changed |

Jedyny ReadValue DD21 zwrócił 7 B (`0610009c020000`). To nie potwierdza
ogniskowej; nie dekodowano nieznanych pól tego payloadu. Pasywny nasłuch FF02
przez 10 s nie odebrał powiadomień. Brak powiadomień w spoczynku nie dowodzi
braku wszystkich możliwych nieudokumentowanych funkcji BLE. Wniosek opiera
się na interfejsie konkretnego egzemplarza i znanej implementacji pilota.

Wcześniejszy test HDMI + USB + BLE potwierdził EXIF **16 → 20 mm** po TELE
650 ms; nowy test powtarza tę metodę przy ciągłym UVC i RAW+JPEG.
ACK zapisu GATT oznacza odpowiedź transportu, nie osiągnięcie pozycji.
PTP D214, mylnie nazwane Zoom przez gphoto2, oznacza PredictedMaximumFileSize;
nie używać go do odczytu ani ustawiania obiektywu.

## Plan serii

| Parametr | Ustawienie |
| --- | --- |
| Krótka próba | 3 zdjęcia: bazowe + dwa przeciwne impulsy zoomu |
| Pełna seria | 10 zdjęć: bazowe + 9 naprzemiennych impulsów |
| Zoom | Slowest, 650 ms po ACK; maks. 1 s w CLI |
| Po zwolnieniu zoomu | 1 s przerwy przed nowym AF; stałe opóźnienie, bez statusu mechanicznego |
| AF | AF-A, świeże D213=2 dwukrotnie, limit 8 s; pominięcie cache jak PR #11 |
| Migawka | Single Shot, jedno full-press 150 ms, zero retry |
| Oryginały | card+sdram, RAW+JPEG (X.Fine), odbiór --keep |
| Przerwa | Co najmniej 10 s po zweryfikowanej parze |
| Podgląd | Jedna ciągła sesja UVC MJPEG 1920×1080 / żądane 30 FPS |

1. Bramki NVMe, wyłączne lokalne blokady PTP i wcześniejszego narzędzia BLE,
   połączony sparowany ILCE-6100A oraz usługi FF00. Brak scan/pair/reconnect w serii.
2. Odczyt modelu i nastaw PTP, pusty bufor, rozruch UVC bez znanych pasów grabbera.
3. Pierwsze zdjęcie bez zoomu przez sprawdzoną bramkę AF. Odczyt bazowej
   ogniskowej z EXIF; test jest ograniczony do aktualnego zakresu Power Zoom 16–50 mm.
4. Jeśli bazowa ogniskowa jest ≥33 mm, pierwszy impuls WIDE, inaczej TELE.
   Kolejne impulsy naprzemienne, bez zlecania konkretnej absolutnej ogniskowej.
5. RELEASE zawsze po PRESS, także po niejednoznacznym błędzie. Tylko RELEASE
   może zostać powtórzone raz jako zabezpieczenie; błąd pierwszego RELEASE
   nadal oznacza FAIL i blokuje następne zdjęcie.
6. Przerwa na zatrzymanie, ponowne bramki BLE/UVC, nowy AF i jedno zdjęcie PTP.
   Przed full-press ponownie sprawdzane BLE, UVC i NVMe; trwały znacznik próby.
7. Dokładnie jedna para, pełne dekodowanie JPEG 6000×4000, nagłówek TIFF ARW,
   SHA-256 obu plików, pusty bufor. EXIF musi maleć po WIDE, rosnąć po TELE.
8. Zatrzymanie przy braku zmiany, odwrotnym kierunku, brakującym EXIF, utracie
   BLE/PTP/UVC/NVMe, timeout AF, niepełnej parze lub niepotwierdzonym release.

Na krótkim impulsie EXIF może pozostać takie samo z powodu rozdzielczości
metadanych albo ograniczenia mechanicznego. Wynik wtedy FAIL tej bramki,
bez automatycznego wydłużania impulsu czy ponowienia ekspozycji. Naprzemienne
impulsy nie gwarantują powrotu do dokładnie tej samej pozycji.

## Uruchomienie na VENTUNO

Pliki przygotowane w istniejącym katalogu diagnostycznym
`/srv/vision-data/tools/sony-af-prototype`. Wymagane istniejące połączenie BLE,
USB Sterowanie PC, AF-A, RAW+JPEG (X.Fine), Single Shot, card+sdram oraz
Auto podgląd WYŁ. Podgląd pozostaje na obecnym stanowisku; słabsze oświetlenie
zaakceptowano, zasilanie USB włączone. Nie zmieniać tych ustawień w trakcie.

```bash
python3 -B /srv/vision-data/tools/sony-af-prototype/scripts/audit/sony_zoom_af_test.py --inspect
python3 -B /srv/vision-data/tools/sony-af-prototype/scripts/audit/sony_zoom_af_test.py --run --shots 3
python3 -B /srv/vision-data/tools/sony-af-prototype/scripts/audit/sony_zoom_af_test.py --run --shots 10
```

`--inspect` zapisuje inwentarz GATT, odczyt DD21 i pasywny nasłuch 10 s;
nie otwiera PTP/UVC i nie wysyła komend obiektywu ani migawki. Testy bez
sprzętu uruchamiać z TMPDIR wskazującym istniejący katalog NVMe na VENTUNO.
Import modułu i --help nie sterują urządzeniem. Nie uruchamiać dwóch klientów
PTP ani innego pilota BLE równolegle; flock nie blokuje obcych programów.

Sesje `sony-zoom-af-*` na NVMe zawierają result.json/checkpoint.json,
oryginały i próbki UVC. Dane obrazu, raw debug oraz error-private.log pozostają
na urządzeniu. Nie commitować MAC, seriali, fotografii ani surowych logów.

## Weryfikacja przygotowania

- 14/14 nowych testów lokalnie i ARM64 VENTUNO: niejednoznaczny PRESS,
  przerwanie, release/retry, błędny EXIF/kierunek oraz realny runner z atrapami.
  Błąd zoomu po zdjęciu bazowym wysyła zero następnych migawkowych żądań;
  utrata BLE w bramce migawki blokuje full-press; niezmienione EXIF blokuje
  trzecią ekspozycję. Wiersze FAIL w wyjściu testów są oczekiwanymi scenariuszami.
- 17/17 wcześniejszych testów AF lokalnie i VENTUNO; kod AF niezmieniony.
- `--inspect` na ARM64 PASS, 10,213074 s; 0 impulsów zoomu, 0 zdjęć,
  FF02 brak powiadomień w 10 s, BLE postflight PASS.
- **Seria sprzętowa 3/10 z nowym skryptem: NOT RUN.** Kod jest przygotowany,
  wyniku AF 10/10 z PR #11 nie przenosimy na nową kombinację kanałów.

PASS serii wymaga odpowiednio 3 lub 10 zweryfikowanych ujęć oraz 2 lub 9
zmian EXIF we właściwym kierunku, bez retry, z UVC i poprawnym release.
AF state nie zastępuje optycznej oceny ostrości PCB. Pełne dekodowanie ARW,
integralność tych nowych plików PTP↔SD, absolutna pozycja zoom/focus,
długotrwała stabilność i metrologia po zmianie skali pozostają UNKNOWN.
Zoom podczas skalibrowanej mozaiki nadal wymaga stałej ogniskowej; ta seria
jest diagnostyką współpracy kanałów, nie kalibracją geometrii obrazu.

Tylko draft PR, bez merge, autostartu, wdrożenia i zmian firmware/usług.
Rollback: zatrzymać proces i potwierdzić release; zachować oryginały i wyniki.
SIGINT/SIGTERM wyzwalają cleanup; SIGKILL, utrata radia i zasilania nie dają
gwarancji wykonania programowego RELEASE.

## Referencje pierwotne

- [coral/freemote](https://github.com/coral/freemote), README blob
  `fc6e49564b3b72b460bf7bd611ebd47776c15a5f`: WIDE `02 47 10` / `02 46 00`,
  TELE `02 45 10` / `02 44 00`, FF01/FF02 i znane powiadomienia.
- [Staacks/alpharemote](https://github.com/Staacks/alpharemote), README blob
  `3d9ff3c7484b8ee88ff2ebc205d9fbef7049f96f`: ograniczony feedback pilota,
  względne przyciski, brak getterów nastaw i absolutnej pozycji.
- [finfinack/alphaloc](https://github.com/finfinack/alphaloc), README blob
  `1a80d75a5a6eb21d6e36a210d076079fe258b770`: DD21 jako location feature flags.
