# Sony ILCE-6100A — prototyp AF przed migawką

Izolowane narzędzie diagnostyczne dla VENTUNO Q / Ubuntu ARM64. Korzysta z istniejących gphoto2 2.5.28, libgphoto2 2.5.31, v4l2-ctl i Pillow. Nie integruje usług ani koordynatora produkcyjnego.

Problem i dotychczasowe dowody: [audyt oraz odtworzenie błędu AF-A](https://github.com/autoklinika/Vision/pull/10). Przy użyciu zwykłego capture-image-and-download sterownik wysyła half-press i full-press przed potwierdzeniem AF, a następnie zwalnia spust po nominalnie 1 s. Nasza wcześniejsza próba samego AF pokazała potwierdzenie przy odczycie po około 3 s, lecz późniejsze źródło ujawniło udział dwusekundowego cache właściwości. Nie traktujemy tych 3 s jako czystego pomiaru czasu pracy autofocusa.

## Sekwencja prototypu

1. Jedna sesja gphoto2 --shell, wyłączne lokalne flock i jedna sesja UVC.
2. Odczyt modelu i nastaw, pusty bufor D215; potwierdzony powrót D213 do 1 przed nową próbą AF.
3. Osobny half-press przez /main/actions/autofocus=1.
4. Odczyty D213 po rozpoczęciu AF. Wyłącznie wartość 2 zaobserwowana na tym ILCE-6100A, dwa kolejne potwierdzenia rozdzielone co najmniej 50 ms, przed upływem limitu 8 s. Przed odczytem prototyp wymusza Sony GetAllDevicePropData przez wait-event 1ms, które omija dwusekundowy cache get-config. Nie zmienia ustawień cache biblioteki. Jeżeli odświeżenie wykryje nieoczekiwany obiekt zdjęcia, zachowuje jego buforowaną kopię w osobnym katalogu NVMe i zatrzymuje próbę bez nowej migawki.
5. Sprawdzenie NVMe/UVC i trwały znacznik O_EXCL; jedno full-press przez /main/actions/capture=1, 150 ms w Single Shot.
6. Zawsze zwolnienie full-press i half-press. Odbiór zdarzeniami wait-event-and-download, bez ponownego capture.
7. Weryfikacja jednej pary: JPEG pełny decode 6000×4000, ARW nagłówek TIFF i SHA-256 obu. Świeżo odczytane D215 musi wrócić do 0 przed następnym ujęciem; oczekiwanie na opróżnienie ma limit 3 s.

Kod nie wywołuje capture-image, capture-image-and-download ani trigger-capture. Nie ustawia MF i nie zmienia trybu zdjęć, jakości, ekspozycji ani zapisu na kartę.

## Wymagania przed uruchomieniem

Model ILCE-6100A, USB PC Remote 054c:0f0d, AF-A, Single Shot, card+sdram, RAW+JPEG (X.Fine). Grabber UVC /dev/video0 w MJPEG 1920×1080. Przed zdjęciem wymagane są trzy kolejne sprawdzenia zawartości bez znanego ośmiopasowego wzorca grabbera; kontrola co 15 klatek, limit rozruchu 25 s. To detektor konkretnego wzorca, nie uniwersalna ocena poprawności każdej klatki. Auto podgląd WYŁ. pozostaje nastawą operatora; prototyp tego parametru nie odczytuje ani nie zmienia.

NVMe /srv/vision-data: prawdziwy mountpoint, źródło /dev/nvme*, ext4, label VISION_DATA, rw i co najmniej 2 GiB wolnego miejsca. Weryfikacja przed tworzeniem sesji i kolejnymi zapisami/wyzwoleniem. Brak fallbacku na eMMC. TMPDIR/XDG_* kierowane na sesję NVMe; Python uruchamiany z -B.

Zachowane stare lub niejednoznaczne zdjęcie w RAM blokuje nowe wyzwolenie. flock zapobiega dwóm kopiom prototypu; inne klienty PTP muszą być zamknięte.

## Uruchomienie

Kod urządzenia: /srv/vision-data/tools/sony-af-prototype/scripts/audit/sony_af_prototype.py.

```bash
python3 -B scripts/audit/sony_af_prototype.py --help
python3 -B tests/test_sony_af_prototype.py
python3 -B scripts/audit/sony_af_prototype.py --run --shots 1
python3 -B scripts/audit/sony_af_prototype.py --run --shots 10
```

--run jawnie uruchamia diagnostykę sprzętową. Dostępne 1 lub 10 zdjęć, minimum 10 s przerwy po zweryfikowanej parze, limit AF domyślnie 8 s i maksymalnie 15 s. Sesje tworzą się w /srv/vision-data/vision/sessions/sony-af-prototype-*; ponowne uruchomienie tworzy **nową próbę**, a nie odzyskuje wcześniejsze zdjęcie.

## Zatrzymanie i dane

Brak świeżego AF, UVC, NVMe, modelu/nastaw, kompletnej pary, wolnego bufora albo błąd PTP zatrzymują sekwencję. Nie ma automatycznych ponowień migawki. Przy timeoutcie shell pierwotny proces jest zamykany; osobny klient może wyłącznie zwolnić S2/S1, nigdy wyzwolić zdjęcie. Niepotwierdzone zwolnienie oznacza FAIL.

Kod procesu 0 oznacza PASS całego przebiegu; błędy kończą się 1. result.json / checkpoint.json zapisują liczbę faktycznie wysłanych żądań, próbki AF, kompletność par i statystyki UVC. Brak potwierdzonego pliku po full-press jest wynikiem niejednoznacznym; nie można traktować następnej próby jako bezpiecznego retry tego samego ujęcia.

ptp-shell-private.log, ptp-debug-private.log, fotografie i próbki UVC zostają na NVMe. **Nie commitować** tych plików: debug może zawierać identyfikację aparatu. Publiczne dowody zawierają jedynie ograniczone metadane, hashe i wyniki.

## Granice i rollback

Potwierdzenie AF w protokole nie jest oceną ostrości PCB. Pełny RAW decode, bit depth, integralność nowych zdjęć względem SD, pomiar sensor→ekran i wielogodzinna stabilność wymagają osobnych prób. AF-A i kodowanie wartości 2 są sprawdzone na tym egzemplarzu; inne modele/tryby nie są zadeklarowane jako obsługiwane.

Tylko prototyp, bez wdrożenia, zmian bibliotek, usług, firmware ani merge do main. Rollback: zakończyć proces, sprawdzić zwolnienie przycisków i zamknąć draft PR; kod/logi na NVMe nie są częścią autostartu. Nie usuwać oryginałów zdjęć jako rollbacku.

Źródła kodu odniesienia: [Sony capture](https://github.com/gphoto/libgphoto2/blob/v2.5.31/camlibs/ptp2/library.c), [osobne akcje autofocus/capture](https://github.com/gphoto/libgphoto2/blob/v2.5.31/camlibs/ptp2/config.c), [cache właściwości](https://github.com/gphoto/libgphoto2/blob/v2.5.31/camlibs/ptp2/ptp.c).
