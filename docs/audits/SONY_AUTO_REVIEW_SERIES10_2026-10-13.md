# Sony ILCE-6100A — Auto podgląd WYŁ. i próba serii 10

**Data:** 2026-10-13. **Zakres:** diagnostyka stanowiska VENTUNO Q; bez wdrożenia i merge.
**Wynik:** pojedynczy RAW+JPEG PASS; seria 10 **FAIL / INCOMPLETE**, zatrzymana na czwartym żądaniu. Odebrano trzy kompletne pary.

To kontynuacja [testów T1/T2](SONY_PTP_HDMI_SD_T1_T2_2026-10-13.md). Nazwy T3/T4 w lokalnym JSON oznaczają kolejne uruchomienia, nie bramki T3/T4 z głównego audytu.

## Warunki i metoda

Operator potwierdził wyłączenie **Auto podgląd** oraz powrót do USB PC Remote. Poprzednia wartość podglądu nie została podana. Oświetlenie jest ograniczone, zaakceptowane dla testów transportu; nie wykonano porównania jakości optycznej.

Odczyt ustawień: card+sdram, RAW+JPEG (X.Fine), AF-A, tryb A; EXIF 50 mm, f/5,6, ISO 6400. Skrypty nie zmieniały parametrów aparatu. UVC: MJPEG 1920×1080, żądane 30 fps. Wszystkie logi, oryginały i próbki trafiały na NVMe po sprawdzeniu mountpoint, źródła NVMe, ext4, etykiety VISION_DATA i rw.

Próba serii użyła jednego procesu gphoto2 --shell, jednej sesji UVC i serialnych poleceń capture-image-and-download. Przekazano --keep; retencja na SD wymaga bezpośredniej kontroli. Odstęp 10 s liczono po odebraniu i zweryfikowaniu kompletnej pary. Każdy JPEG dekodowano w pełni, ARW sprawdzano nagłówkiem TIFF i SHA-256. Pełny dekoder RAW nadal niedostępny. Nie ponawiano wyzwolenia po błędzie.

## Pojedyncza próba po wyłączeniu podglądu

Odbiór jednej pary trwał **5,249 s**. JPEG: 6000×4000, 15 381 590 B, pełne dekodowanie PASS. ARW: 24 918 784 B, nagłówek TIFF PASS, pełne dekodowanie UNKNOWN.

UVC: 399 odebranych ramek, 156 podczas zdjęcia+odbioru, 69 różnych payloadów w tym przedziale. Największa przerwa między odbiorami: 0,132356 s. Najdłuższy ciąg identycznych payloadów po 3 s rozruchu: 20 ramek / **0,632085 s**. Wcześniejszy ciąg 2,134255 s z T1 nie powtórzył się.

Nie jest to kontrolowany dowód wpływu Auto podgląd: poprzednia wartość jest nieznana, a ekspozycja zmieniła się z 1/6 s w T1 na 1/3 s. Próbki pokazują scenę; nie potwierdzają zawartości każdej ramki.

## Seria — trzy udane ujęcia, błąd czwartego

| Żądanie | Wynik | Zdjęcie + odbiór | Ekspozycja JPEG | UVC odebrane / różne podczas operacji |
| --- | --- | --- | --- | --- |
| 1 | RAW+JPEG PASS | 4,764 s | 1/4 s | 143 / 62 |
| 2 | RAW+JPEG PASS | 4,832 s | 1/3 s | 145 / 62 |
| 3 | RAW+JPEG PASS | 4,055 s | 1/4 s | 122 / 55 |
| 4 | ERROR; brak odebranej pary | nie zaliczono do czasów sukcesu | UNKNOWN | nie oceniono osobno |

Czwarte polecenie zwróciło:

```text
ERROR: Could not capture image.
ERROR: Could not capture.
```

Katalog shot-04 zawierał jedynie capture.log; brak ARW/JPEG. Seria zatrzymana: **4 żądania, 3 zweryfikowane pary, 0 automatycznych ponowień**, żądania 5–10 nie wysłane. Kod zakończenia procesu diagnostycznego 0 nie jest PASS: wynik result.json jednoznacznie FAIL_OR_INCOMPLETE. Nie wiadomo, czy czwarte zdjęcie zostało zapisane na SD.

Po zakończeniu PTP nadal odpowiadało na odczyty ustawień (rc=0): AF-A, card+sdram, RAW+JPEG (X.Fine). Odczyt baterii 2%; operator zgłasza aktywne zasilanie USB. Ani słabe światło/AF, ani zasilanie, ani błąd sterownika nie zostały wykazane jako przyczyna. Nie zmieniano ustawień i nie wykonywano zdjęcia recovery.

UVC przez około 88,882 s: 2667 odebranych ramek, 1106 różnych payloadów, maksymalna przerwa odbioru 0,119192 s, brak błędów kolektora. Najdłuższe identyczne ciągi po rozruchu: 0,634709 s przy ujęciu 2 oraz około 0,568 s przy ujęciach 1 i 3. Są to znaczniki dostarczenia danych do hosta, nie pomiar sensor→ekran. Dopływ ramek nie oznacza stale aktualizowanego obrazu; przyczyny powtórzeń kamera/grabber nie rozdzielono.

## Pozostałe kroki

1. Przełączyć operatorowo na Mass Storage i zamontować kartę tylko do odczytu.
2. Porównać pojedynczą próbę oraz trzy udane pary z SD; sprawdzić dodatkowe pliki po ostatnim udanym ujęciu, aby ustalić możliwy wynik czwartego żądania.
3. Dopiero po rozstrzygnięciu plików ustalić kontrolowaną próbę przyczyny: np. AF-A versus MF przy tej samej scenie i stałej ekspozycji, bez ślepego ponawiania migawki.
4. Pełne 10/50/100 i próba wielogodzinna pozostają otwarte; obecny wynik nie zamyka niezawodności.

Integralność ARW bajtowo i JPEG do EOI potwierdzona w T2 dotyczy tamtej jednej ekspozycji; nie przeniesiono jej automatycznie na nowe zdjęcia. Nie testowano w tej serii BLE, MTP, pełnego dekodowania RAW, jakości PCB ani latencji.

## Odtwarzalność

Ograniczony zapis wyników i hashów: [SONY_AUTO_REVIEW_SERIES_EVIDENCE_2026-10-13.json](SONY_AUTO_REVIEW_SERIES_EVIDENCE_2026-10-13.json). Bez zdjęć, identyfikatorów sieci i numerów seryjnych.

Lokalne dowody pod /srv/vision-data/vision/sessions/:

- sony-uvc-ptp-autoreview-off-20261013T200129Z: result.json, repeat-analysis.json, ptp-one-shot.log, próbki i oryginały.
- sony-uvc-ptp-series10-20261013T200614Z: result.json, checkpoint.json, ptp-shell.log, shot-01–04, uvc-frames.json, preflight-config.txt i post-failure-readonly-config.txt.

Dokumentacja ustawienia: [Sony ILCE-6100A, polska instrukcja PDF — Auto podgląd](https://helpguide.sony.net/ilc/2460/v1/pl/print.pdf#page=276), MENU → Ustawienia fotograf.2 → Auto podgląd → WYŁ.

## Diagnostyka błędu — 20:16–20:20 UTC

Nie wykonano nowej ekspozycji ani ponowienia niejednoznacznego zdjęcia.

- W logu kernela z 20:07:20–20:10:00 UTC nie znaleziono zdarzeń USB/UVC świadczących o rozłączeniu lub resecie; odczyt journalctl zakończył się rc=0. Nie wyklucza to każdego błędu transportu.
- Kolejny odczyt PTP: AF-A, Single Shot, D215 Objects in memory = 0. To stan późniejszy, nie dowód braku czwartej ekspozycji na SD.
- Źródła używanej wersji [libgphoto2 v2.5.31, library.c](https://github.com/gphoto/libgphoto2/blob/v2.5.31/camlibs/ptp2/library.c): camera_sony_capture wysyła half-press i full-press, w AF czeka najwyżej 1000 ms na ostrość, zwalnia oba przyciski i czeka do 35000 ms na ObjectAdded lub ObjectInMemory >= 0x8000. Bez obiektu zwraca GP_ERROR. Komunikaty tego mechanizmu obecne w załadowanym systemowym ptp2.so; CLI i biblioteka raportują 2.5.28 / 2.5.31.
- Różnica mtime logów końca ujęć 3 i 4 wynosiła 49,564931 s, obejmując 10 s przerwy i walidację pary 3. Przedział około 39 s dla nieudanego żądania jest zgodny z oczekiwaniem na obiekt; nie zastępuje brakującego szczegółowego trace tego żądania.
- Wykonano jedną kontrolowaną próbę **wyłącznie half-press przez D2C1**, bez full-press D2C2 i bez aktywnego UVC. Komenda zaakceptowana; odczyty właściwości odświeżały dane z Sony GetAllDevicePropData. W świeżym trace przejście Focus status D213 **1 → 2** odnotowano przy 3,304151 s od startu logu, około **3,012 s po wysłaniu half-press** (0,292035 s). Sterownik traktuje 2/3 jako osiągnięcie ostrości. Odczyty były dyskretne, więc to czas obserwacji potwierdzenia, nie dokładna chwila uzyskania ostrości.
- Tekstowe odpowiedzi shell get-config pozostawały Current: 1 również w ostatniej próbce; nowsze przejście 1→2 wynika ze szczegółowego trace odświeżenia. Nie ukryto tej różnicy; do wniosku użyto świeżego trace.
- Half-press zwolniony poprawnie. Pełnych żądań migawki: 0. Nie zmieniano focus mode ani ekspozycji.

**Wiodąca hipoteza:** AF w bieżących warunkach potwierdza ostrość później niż limit trzymania spustu w sterowniku. Aparat może więc nie wykonać zdjęcia przed zwolnieniem, a klient kończy oczekiwanie bez obiektu. Późniejsza próba wspiera ten mechanizm, lecz nie dowodzi stanu AF podczas pierwotnego czwartego wyzwolenia. To nie jest jeszcze zdiagnozowany błąd sterownika ani dowód uszkodzenia aparatu.

Następny test rozróżniający: operator ustawia MF; oddzielna, oznaczona próba RAW+JPEG przy UVC i pełnym debug, bez automatycznych ponowień. Wynik poprzedniej ekspozycji na SD nadal wymaga kontroli; nowej próby nie liczyć jako odzyskania tamtego ujęcia.

Dowody na NVMe: failure-state-readonly.txt, failure-readonly-debug.log, failure-state-get-debug.log, af-halfpress-only-shell.log, af-halfpress-only-debug.log, af-halfpress-only-result.json i failure-diagnosis-preliminary.json. Surowy debug nie jest publikowany — zawiera pełne dane urządzenia. Publiczny JSON uzupełniono wyłącznie o ograniczoną diagnozę i istotne znaczniki.
