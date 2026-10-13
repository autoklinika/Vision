# Sony A6100A — test stabilności 50/100 zdjęć w każdym trybie

Status: **PREPARED / SOFTWARE VERIFIED / HARDWARE RUN NOT STARTED**.
Data przygotowania: 2026-10-14 (Europe/Warsaw).
**Nie uruchamiać serii bez kolejnej, jednoznacznej zgody właściciela.**

## Zakres i liczenie zdjęć

Nowy skrypt: `scripts/audit/sony_stability_test.py`.
Tryby fixed (bez poleceń zoomu), zoom (naprzemienne WIDE/TELE) i both.
Parametr `--shots` to liczba ekspozycji **w każdym trybie**, nie suma.

| Wywołanie | Bez zoomu | Z zoomem | Razem ekspozycji | RAW+JPEG |
| --- | --- | --- | --- | --- |
| run --mode fixed --shots 50 | 50 | 0 | 50 | 100 plików |
| run --mode zoom --shots 50 | 0 | 50 | 50 | 100 plików |
| run --mode both --shots 50 | 50 | 50 | 100 | 200 plików |
| run --mode both --shots 100 | 100 | 100 | 200 | 400 plików |

Rekomendowany pierwszy przebieg: **both / 50**, czyli 50 zdjęć bez zoomu,
następnie 50 z zoomem, w jednej sesji PTP i przy jednym ciągłym UVC.
Każda faza ma własne zdjęcie bazowe. W fazie zoom występuje shots−1 impulsów;
ogniskową każdego ujęcia sprawdza EXIF. Identyczne impulsy nie ustawiają
absolutnej pozycji; brak zmiany lub odwrotny kierunek przerywają test.
W fixed EXIF ogniskowej musi pozostać takie samo.

Dla obecnych czasów AF/odbioru i przerwy 10 s szacujemy około 27–30 minut
dla both/50 i 55–60 minut dla both/100. To szacunki, nie wynik długiego testu.
Dokładne czasy i trend pierwszych/ostatnich 10 zdjęć trafią do raportu.
Kolejność fixed→zoom nie izoluje wpływu zoomu od temperatury lub baterii.

## Bramki i zachowanie

- Wyłącznie Sony ILCE-6100A i sprawdzony Power Zoom 16–50 mm.
- Jedna sesja gphoto2, świeże właściwości AF, AF-A / Single Shot /
  card+sdram / RAW+JPEG (X.Fine), Auto podgląd WYŁ. ustawione przez operatora.
- Zero automatycznych ponowień full-press i PRESS zoomu. RELEASE zoomu
  zachowuje istniejące maksymalnie jedno zabezpieczające powtórzenie; błąd
  pierwszego RELEASE nadal oznacza FAIL.
- Durable marker z fsync przed każdym full-press; checkpointy i oryginały
  zachowywane także po błędzie. Brak automatycznego wznawiania przerwanej serii.
- Stop po błędzie AF, BLE, PTP, UVC, bufora, plików lub EXIF. Próba zwolnienia
  migawki i AF przy kończeniu. Nie zmienia nastaw aparatu w celu ukrycia błędu.
- Lokalne blokady zgodne z prototypami. Inne programy/piloty trzeba zamknąć;
  flock nie zapewnia wyłączności wobec obcych klientów.
- UVC bez limitu liczby ramek (frame_count=0). Poprzedni limit 12600 ramek
  wystarczał na około 7 minut, więc nie nadaje się do tej serii.
- Kontrola odbioru UVC również podczas przerw. Po rozruchu domyślnie
  maksymalna przerwa odbioru 1 s i zero wykryć znanych pasów testowych.
  Historyczna przerwa podczas blokującego pobierania jest wykrywana po powrocie.
- AF limit 8 s; zoom 650 ms, settle 1 s, odstęp 10 s po zweryfikowanej parze.
  Settle to opóźnienie, nie mechaniczne potwierdzenie zatrzymania obiektywu.
- JPEG pełne dekodowanie 6000×4000; ARW nagłówek TIFF i SHA-256.
  Pełne dekodowanie RAW pozostaje NOT_TESTED.
- Zapisy tylko na sprawdzonym NVMe VISION_DATA. Rezerwa: 64 MiB na każdą
  pozostałą parę i 2 GiB zapasu. Osobna kontrola miejsca przed importem SD.
  Debug gphoto2 z obrazowymi dumpami wyłączony dla długiego testu.
- SIGINT/SIGTERM zatrzymują serię i uruchamiają cleanup. Przerwane polecenie
  PTP oznacza sesję unusable; najpierw kończymy jej właściciela, dopiero potem
  próbujemy awaryjnego RELEASE bez wyzwalania kolejnego zdjęcia.
  SIGKILL/zanik zasilania nie gwarantują wykonania cleanup.

## Przygotowanie operatora przed przyszłym uruchomieniem

1. Aparat podłączony: USB Sterowanie PC, HDMI do sprawdzonego grabbera;
   istniejące sparowanie/połączenie BLE dla zoom/both.
2. Stabilne zasilanie aparatu, miejsce na SD, stabilna scena i oświetlenie.
   Nie poruszać ramieniem ani aparatem; nie dotykać pierścienia zoomu.
3. Ustawienia jak powyżej, wystarczająca scena do AF. Test nie wymaga PCB,
   ale nie daje wtedy dowodu ostrości rzeczywistej elektroniki.
4. Karta SD odmontowana przed wejściem do PC Remote. Zamknąć inne klienty PTP,
   UVC i pilota BLE. Używany grabber to obecne /dev/video0.
5. Potwierdzić tryb i liczbę zdjęć z właścicielem. Następujące polecenia
   są instrukcją przyszłego testu, a nie dyspozycją uruchomienia teraz.

Izolowany katalog przygotowany na VENTUNO:
`/srv/vision-data/tools/sony-stability-test`.
Nie podmieniono wcześniejszego katalogu `sony-af-prototype`, usług ani bibliotek.

## Etap 1 — akwizycja po zgodzie

```bash
python3 -B /srv/vision-data/tools/sony-stability-test/scripts/audit/sony_stability_test.py run --mode both --shots 50
```

Dla 100 ekspozycji na każdy tryb zmienić tylko --shots na 100.
Sam import modułu, --help i assess nie otwierają aparatu ani radia.

Konsola wypisuje postęp każdego zdjęcia i na końcu dokładną ścieżkę result.json.
Sesje są tworzone jako `/srv/vision-data/vision/sessions/sony-stability-<UTC>`.
Akwizycja może zakończyć się capture_status=PASS, ale status całego zadania
pozostaje **PENDING_SD**. Kod wyjścia 0 polecenia run oznacza tylko udaną akwizycję.

## Etap 2 — karta SD i porównanie tych samych ekspozycji

Po zakończeniu i zamknięciu właściciela PTP operator przełącza aparat do
Mass Storage. Nie zmieniać trybu w trakcie serii.

Podstawić dokładną ścieżkę nowej sesji zamiast /pełna/ścieżka/sesji.
Sprawdzić bieżące urządzenie karty przez lsblk; nie zakładać na stałe /dev/sda1.
Mountpoint można stworzyć w sesji, po potwierdzeniu dostępności NVMe.

```bash
mkdir /pełna/ścieżka/sesji/sd-ro
sudo mount -t exfat -o ro,nosuid,nodev,noexec,uid=1000,gid=1000 /dev/WŁAŚCIWA_PARTYCJA_SD /pełna/ścieżka/sesji/sd-ro
python3 -B /srv/vision-data/tools/sony-stability-test/scripts/audit/sony_stability_test.py compare --session /pełna/ścieżka/sesji --sd-root /pełna/ścieżka/sesji/sd-ro
sudo umount /pełna/ścieżka/sesji/sd-ro
```

Skrypt nie wykonuje sudo, montowania, zmiany trybu USB ani odłączania aparatu.
Weryfikuje Sony USB 054c:0f0b, exFAT i mountpoint tylko do odczytu.

Porównanie:
- Jednoznaczne EXIF DateTimeOriginal + FocalLength, a następnie pełne pliki.
- Sprawdzenie, czy pliki PTP nadal odpowiadają manifestowi.
- RAW identyczne bajtowo i SHA-256.
- JPEG: cała zawartość PTP identyczna z SD; dopuszczalne wyłącznie dodatkowe
  zera SD poza końcem całego pliku PTP. Zachowujemy również drugi JPEG/dane
  po pierwszym EOI. Obie wersje muszą dać identyczne RGB 6000×4000.
- Dokładne oryginały SD kopiowane do sd-originals, z fsync i zgodnością SHA-256.
- Nie nadpisuje wcześniejszego porównania ani importu. Zapisane błędy
  porównania/dekodera lub niepełny import nie mogą dać PASS.
- Można porównać kompletnie pobrane pary z przerwanej serii; cała seria
  pozostaje FAIL mimo PASS tych kilku par.

## Raport i ponowna ocena

compare automatycznie tworzy assessment.json i REPORT.md.
Ocena bez aparatu, na wcześniej zapisanych wynikach:

```bash
python3 -B /srv/vision-data/tools/sony-stability-test/scripts/audit/sony_stability_test.py assess --session /pełna/ścieżka/sesji
```

assess ponownie sprawdza SHA-256 kopii SD oraz oryginałów PTP.
PASS wymaga pełnego planu, jednego żądania na zdjęcie, poprawnego release,
wszystkich bramek akwizycji, całego porównania i wszystkich kopii SD.
Kod: 0 PASS; 1 FAIL; 2 PENDING_SD.

Raport zawiera osobne wyniki fixed/zoom, AF i odbiór pary min/mediana/p95/max,
pierwsze/ostatnie 10 zdjęć, liczbę impulsów i dane UVC (ramki, różne payloady,
przerwy odbioru, pasy i identyczne fragmenty). Identyczny payload przez >2 s
jest sygnałem do oceny człowieka, nie dowodem zawieszenia nieruchomej sceny.

PASS to stabilność akwizycji/transferu w konkretnym przebiegu. Nie obejmuje
optycznego QC PCB, dokładności absolutnego zoomu, pełnego RAW decode,
bezpieczeństwa ramienia ani opóźnienia sensor→ekran. Detektor pasów sprawdza
okresowe klatki, a nie każdą. Świeżość sceny pozostaje NOT_PROVEN.
Nie publikować fotografii, surowych logów i prywatnego manifestu w GitHub.

## Walidacja przygotowania

- **81/81 testów lokalnie** oraz **81/81 na VENTUNO Ubuntu ARM64 / Python 3.12.3**.
- Pełny runner z atrapami: both/50 = 100 i both/100 = 200 ekspozycji;
  fixed nie tworzy klienta BLE. Zero rzeczywistych ekspozycji podczas walidacji.
- AF/zoom/BLE/UVC/pair/EXIF/release/interruption: FAIL blokuje dalsze zdjęcia,
  zachowuje dowody i wykonuje cleanup. Marker zachowuje niejednoznaczny full-press.
- Comparator: 50/100/200 par, legacy 13 par, brakujące/niejednoznaczne SD,
  zmienione PTP, niezerowy sufiks i dane za głównym EOI.
- Brak PASS bez SD; przerwana seria, obca sesja, duplikaty i uszkodzona kopia
  nie przechodzą końcowej oceny. Błąd dekodera/porównania daje jawny FAIL.
- Na VENTUNO --help działa; Pillow/dbus/PyGObject dostępne. Nic nie instalowano.
- Nie uruchomiono prawdziwej serii 50/100; testy z atrapami potwierdzają
  logikę i obsługę błędów, nie fizyczną stabilność aparatu.
- Bez usług/autostartu, zmian firmware, GPU/NPU i merge do main.
