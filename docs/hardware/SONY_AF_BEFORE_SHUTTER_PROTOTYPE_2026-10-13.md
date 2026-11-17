# Sony ILCE-6100A — prototyp AF przed migawką

**Data:** 2026-10-13. **Wynik:** aktualny prototyp: jedno zdjęcie PASS, potem **10/10 RAW+JPEG PASS przy ciągłym UVC**. **Status:** PROTOTYPE / TEST, bez wdrożenia ani merge.

## Co zmieniono

Zastąpiono jedno capture-image-and-download osobnymi etapami: wyłączenie spustów i sprawdzenie pustego bufora → half-press AF → świeże potwierdzenie D213=2 → jedno full-press w Single Shot → release obu spustów → odbiór zdarzeniami → walidacja pary i pustego bufora. Limit AF 8 s; brak potwierdzenia oznacza zero nowych wyzwoleń. Nie przełączano na MF.

Kod: [sony_af_prototype.py](../../scripts/audit/sony_af_prototype.py), [instrukcja](../../scripts/audit/SONY_AF_PROTOTYPE.md), [testy bez sprzętu](../../tests/test_sony_af_prototype.py).

W libgphoto2 get-config korzysta z domyślnie dwusekundowego cache. Samo dwukrotne get-config nie zapewnia świeżego odczytu. Prototyp wymusza odświeżenie przez wait-event 1ms: ścieżka Sony wait_for_event wykonuje GetAllDevicePropData, po czym odczyt pochodzi z odświeżonego cache. Nie zmieniono biblioteki ani jej globalnych ustawień. Nieoczekiwany obiekt przy odświeżeniu jest zachowywany w osobnym katalogu NVMe i zatrzymuje próbę; nie jest ignorowany jako gotowość do nowego zdjęcia.

**Korekta wcześniejszego wniosku:** zaobserwowane wcześniej około 3 s do potwierdzenia AF zawierało także opóźnienie cache. Nie jest samodzielnym pomiarem pracy AF. W aktualnej serii świeże, stabilne potwierdzenie nadal przekraczało 1 s w 9/10 ujęć, co wspiera zasadność oczekiwania na stan zamiast stałego krótkiego trzymania spustu. Nie zmierzono dokładnej chwili optycznego uzyskania ostrości.

## Aktualna walidacja

17/17 testów bez sprzętu PASS lokalnie i na VENTUNO Q ARM64: wolny/brakujący AF, stary status, nieznana wartość, bufor z poprzednim zdjęciem, brak NVMe/ro, błąd UVC/storage przed migawką, niejednoznaczny full-press bez retry, release po błędzie, wymuszenie odświeżenia, nieoczekiwany obiekt, opróżnienie bufora i znany wzorzec pasów grabbera.

Pojedyncza próba aktualnego kodu: AF potwierdzone po **2,297046 s**, kompletna para po **6,194432 s**, S1/S2 release potwierdzone, D215=0. JPEG 6000×4000 pełny decode PASS, ARW nagłówek i hash PASS; pełny RAW decode UNKNOWN.

Seria rozpoczęta **20:59:02 UTC / 22:59:02 Europe/Warsaw**, zakończona po **148,917023 s**. Jeden właściciel PTP, jedna sesja UVC, 10 s przerwy po zweryfikowanej parze.

| Ujęcie | Potwierdzenie AF [s] | Do zweryfikowanej pary [s] | Wynik |
| --- | --- | --- | --- |
| 1 | 3.034 | 6.912 | PASS |
| 2 | 2.067 | 5.908 | PASS |
| 3 | 0.861 | 4.643 | PASS |
| 4 | 1.504 | 5.222 | PASS |
| 5 | 1.506 | 4.983 | PASS |
| 6 | 1.635 | 5.544 | PASS |
| 7 | 2.089 | 5.855 | PASS |
| 8 | 1.994 | 5.356 | PASS |
| 9 | 1.518 | 5.060 | PASS |
| 10 | 1.559 | 5.085 | PASS |

Potwierdzenie AF: min **0.861007 s**, mediana **1.596963 s**, max **3.034372 s**. Kompletna para: min **4.642819 s**, mediana **5.289050 s**, max **6.912226 s**. To czasy etapów prototypu, nie osobny pomiar mechanizmu migawki lub transferu.

**10 żądań full-press, 10 zweryfikowanych par, 0 automatycznych ponowień**, brak błędu w aktualnej serii. Każdy JPEG pełne dekodowanie 6000×4000; ARW sprawdzony nagłówkiem TIFF i SHA-256. Oba przyciski zwolnione; nie zmieniano trwałych nastaw fotograficznych.

## UVC i wcześniejsze zatrzymania prototypu

Aktualna seria: **4444 ramek**, 1896 różnych payloadów, maksymalna przerwa odbioru **0,108292 s**, najdłuższy identyczny fragment po rozruchu **0,533508 s**. 293 okresowe kontrole zawartości, 0 wykrytych znanych wzorców pasów. Próbki przed/po sprawdzone wizualnie: scena z aparatu. Kontrole co 15 klatek nie dowodzą poprawności każdej ramki ani stale świeżego obrazu.

W trakcie tworzenia prototypu wystąpiły również:
- Device or resource busy na UVC, przed AF, 0 żądań migawki. Przyczyny nie ustalono; kod później objął bezpośrednią własnością proces v4l2-ctl, z terminate/wait zamiast pośredniego timeout.
- Celowo krótki deadline AF 0,05 s: oczekiwane zatrzymanie, 0 żądań migawki, release potwierdzony. Dotyczy wcześniejszej wersji; ta sama logika gate pozostała i jest objęta regresją bez sprzętu.
- Pierwsza próba serii wcześniejszej wersji zatrzymała się po jednej odebranej parze, bo kontrola bufora odczytała cache 32769, podczas gdy świeży trace wykazał już 0. W tej próbie UVC pokazywało też pasy; **nie zaliczono jej jako wspólnego testu UVC**. Aktualny kod wymusza odświeżenie, czeka maksymalnie 3 s na pusty bufor i blokuje zdjęcie przy znanym wzorcu pasów.

Nie wznowiono tamtej sekwencji. Aktualna seria to osobna oznaczona próba z nowymi zdjęciami. Naprawa nie jest bezwarunkowym ignorowaniem wartości D215 ani błędów podglądu.

## Zakres PASS i pozostałe granice

PASS obejmuje protokół AF→migawka, odbiór kompletnych par i współdziałanie z UVC w pojedynczej oraz jednej dziesięcioujęciowej próbie. Pracowano przy ograniczonym świetle i automatycznej ekspozycji, AF-A, Single Shot, card+sdram, RAW+JPEG (X.Fine); Auto podgląd WYŁ. potwierdzone wcześniej przez operatora.

Nie oceniono dokładności autofocusa na PCB, ostrości oryginałów ani kalibracji punktu AF. Pełny RAW decode, bit depth, integralność nowych par PTP↔SD, równoległe BLE, 50/100 i wielogodzinna stabilność pozostają UNKNOWN. Hostowe czasy odbioru nie są timestampami sensora ani latencją sensor→ekran. Oryginalny wcześniejszy błąd AF-A nie otrzymał własnego trace; nowy wynik wspiera działanie zmienionej sekwencji, nie ustala wszystkich możliwych przyczyn dawnych błędów.

## Odtwarzalność i rollback

Publiczne ograniczone metadane i hashe: [SONY_AF_PROTOTYPE_EVIDENCE_2026-10-13.json](SONY_AF_PROTOTYPE_EVIDENCE_2026-10-13.json).

Źródło prototypu SHA-256: 8fc71b344ae4487ab2b84aa63453404c0474c8c732a457eb6066abc3adb94efb.
Środowisko: istniejące gphoto2 2.5.28, libgphoto2 2.5.31, Pillow i v4l2-ctl; Ubuntu ARM64 VENTUNO Q. Wszystkie artefakty urządzenia po sprawdzeniu NVMe mountpoint, źródła, ext4, label VISION_DATA, rw i wolnego miejsca.

Sesje aktualnej wersji pod /srv/vision-data/vision/sessions/:
- sony-af-prototype-20261013T205703779805Z — jedna para.
- sony-af-prototype-20261013T205902100686Z — 10 par, result.json/checkpoint.json/uvc-frames.json, prywatne logi i próbki.

Kod urządzenia pod /srv/vision-data/tools/sony-af-prototype/. Prywatnych logów debug, próbek i oryginałów nie publikowano. Rollback: zakończenie prototypu i potwierdzenie release; brak usług/autostartu, instalacji bibliotek, zmian firmware/GPU/NPU i wdrożenia. Merge należy do właściciela projektu.
