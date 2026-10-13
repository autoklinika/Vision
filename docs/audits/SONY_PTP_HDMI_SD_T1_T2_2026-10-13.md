# Sony ILCE-6100A — T1/T2: HDMI + PTP, RAW/JPEG oraz zgodność z SD

**Data:** 2026-10-13, test T1 około 19:39 UTC, porównanie T2 około 19:48 UTC.
**Status:** PASS pojedynczej akwizycji i zachowania informacji obrazu; PARTIAL ciągłości Live View; serie i pełne dekodowanie RAW pozostają UNKNOWN.
**Zakres:** diagnostyka Vision, bez wdrożenia produkcyjnego ani merge. [Audyt główny](SONY_PROTOCOL_ARCHITECTURE_AUDIT_2026-10-13.md).

## 1. Wynik

Preferowany kierunek HDMI + USB PC Remote/PTP ma teraz **bezpośredni dowód równoczesnego odbioru RAW+JPEG przy aktywnym przechwytywaniu UVC**, dla jednej ekspozycji. Nie był to test równoległego BLE ani trwałej sesji z wieloma zdjęciami.

**ARW z PTP i SD jest identyczny bajtowo. JPEG z PTP zawiera dokładnie te same bajty obrazu i metadanych co JPEG z SD; różnią się wyłącznie 9226 zerami dopisanymi na SD po znaczniku końca JPEG.** Dlatego hashe całych JPEG są różne, mimo braku rekompresji i identycznych pikseli. Nie ogłaszać identyczności całego pliku JPEG.

Obraz HDMI był widoczny przed, podczas i po próbie, ale w czasie operacji wystąpiło 65 identycznych payloadów klatek przez 2,134255 s. Odbieranie około 30 ramek/s nie dowodzi stałej aktualizacji sceny. Auto Review lub inne zatrzymanie obrazu pozostaje hipotezą do testu.

## 2. Warunki i metoda

- Sony ILCE-6100A, VENTUNO Q / Ubuntu ARM64; zapis wyłącznie po weryfikacji rzeczywistego NVMe, ext4, VISION_DATA, rw.
- Operator przygotował scenę ze słabszym oświetleniem i zaakceptował je dla testu transportów. Nie jest to porównanie jakości optycznej PCB.
- Operator ustawił PC+Camera, co odczyt PTP potwierdził jako `card+sdram`; stabilny odczyt: RAW+JPEG X.Fine, tryb A, AF-A.
- Po ponownym wpięciu USB pierwszy odczyt niektórych parametrów był niespójny (RAW / focus Undefined); powtórny odczyt ustabilizował się. Nie zmieniano tych parametrów skryptem ani nie wyzwolono zdjęcia przed stabilnym odczytem.
- Niski poziom baterii był znany; operator potwierdził włączone zasilanie USB. Nie traktować tego krótkiego wyniku jako testu bilansu zasilania przez wiele godzin.
- Jedna sesja UVC MJPEG 1920×1080/30; jeden proces gPhoto2 wyzwolił dokładnie jedno zdjęcie z `--keep`. Bez automatycznego retry.
- PTP proces i UVC zakończono przed zmianą USB na Mass Storage. Operator przełączył tryb i zamontował exFAT tylko do odczytu, z ro,nosuid,nodev,noexec.
- Zweryfikowano tożsamość nośnika przez jego pochodzenie od Sony USB Mass Storage. PMHOME nie montowano.
- Jednoznacznie dopasowano SD JPEG po DateTimeOriginal; znaleziono parę DSC00021.JPG / DSC00021.ARW. Odczyt 21 JPEG w DCIM nie tworzył żadnych nowych ekspozycji.

## 3. T1 — jedna ekspozycja przy ciągłym UVC

| Pomiar | Wynik |
| --- | --- |
| Polecenia migawki | 1 |
| Wykonanie i odbiór obu obiektów | 4,987 s |
| JPEG PTP | 14 801 910 B, 6000×4000, pełne dekodowanie PASS |
| ARW PTP | 24 886 016 B, nagłówek TIFF PASS; dekodowanie danych sensora UNKNOWN |
| EXIF JPEG | 50 mm, f/5,6, 1/6 s, ISO6400 |
| DateTimeOriginal aparatu | 2026:10:13 21:39:28; nie utożsamiać tego bez synchronizacji z czasem UTC hosta |
| Odebrane UVC ramki w całej próbie | 391 |
| Ramki odebrane w czasie zdjęcie + transfer | 149 |
| Średnia szybkość odbioru | 29,778 ramek/s |
| Największa przerwa między odbiorami | 0,132957 s |
| Unikalne payloady w całej próbie / w operacji zdjęcia | 116 / 39 |
| Powtarzanie jednego payloadu podczas operacji | 65 ramek, 2,134255 s |

Znaczniki czasu ramek pochodzą z odbioru bajtów w pipe przez proces hosta. Nie są timestampami sensora ani dequeue V4L2; chwilowe grupowanie odbiorów i zaokrąglenia wpływają na odstępy. Podczas uruchamiania wystąpił również ciąg 63 identycznych ramek przez około 2,065 s.

Zachowano trzy próbki JPEG: przed, w trakcie i po operacji; wizualnie każda przedstawiała rzeczywistą scenę. Nie zachowano pełnego filmu, więc nie można sklasyfikować wizualnie każdego pośredniego payloadu. Wnioski dotyczą transportu i zarejestrowanych powtórzeń, nie braku wszystkich czarnych klatek ani mierzonej latencji sensor→ekran.

## 4. T2 — te same pliki przez PTP i z SD

| Plik | PTP, bajty | SD, bajty | Wynik |
| --- | ---: | ---: | --- |
| ARW | 24 886 016 | 24 886 016 | SHA-256 identyczny |
| JPEG | 14 801 910 | 14 811 136 | SHA-256 całych plików różny; SD ma wyłącznie zerowe dopełnienie |

SHA-256 ARW PTP = SD:
`ebb3b39550e474868fa4434a375bc678b2b09ceb759a9d1ae8d9878565162b5d`.

SHA-256 JPEG PTP:
`d91b7018a34f7b10a301ef63bc9c6719f474bc103554284b1e2d367b6151147e`.

SHA-256 JPEG SD:
`133c615839c9ff4d31384015388d6e14c7bc301fd41feafa15aa0069116528a4`.

### Wyjaśnienie różnicy JPEG

1. Cały plik PTP jest identycznym początkiem pliku SD, bajt po bajcie.
2. JPEG PTP kończy się prawidłowym znacznikiem EOI `FF D9`.
3. Wszystkie dodatkowe **9226 bajtów** z SD mają wartość zero.
4. Dekodowanie obu plików daje identyczne RGB; hash pikseli:
   `5022790d6d2646759b66c1ccb9c7abecdc64bbe8a28139baf9cc72538331ce7a`.
5. Plik SD ma długość będącą wielokrotnością 32768. To obserwacja, nie udowodniony mechanizm firmware lub alokacji.

Sprawdzenie identyczności pełnego prefiksu jest mocniejsze niż samo porównanie pikseli: obejmuje również skompresowany strumień JPEG i metadane. Zatem **brak dodatkowej rekompresji lub zmiany EXIF w tym ujęciu**; nie wnioskowano tego z samego wyglądu zdjęcia.

Pierwotny wynik porównania pełnych hashy zapisano uczciwie jako MISMATCH w `sd-ptp-integrity.json`. Kolejna analiza `jpeg-difference-analysis.json` wyjaśnia ten wynik. Nie zmieniono źródłowych plików, nie nadpisano PTP JPEG ani nie dopisano mu zer.

Zachowano dodatkowo dokładną kopię SD JPEG na NVMe jako `sd-original-DSC00021.JPG`, z ponownym hashem zgodnym z kartą. ARW PTP już stanowi dokładną kopię źródła SD. Karta była wyłącznie czytana.

## 5. Konsekwencje dla architektury

- **PC+Camera: PASS dla tego pojedynczego ujęcia**, nie tylko dokumentacyjnie SUPPORTED.
- **RAW PTP: pełna zgodność bajtowa z SD PASS.** To nie zastępuje pełnego dekodowania sensora, weryfikacji głębi bitowej ani długiej próby.
- **JPEG PTP: zachowanie obrazu i metadanych PASS**, zgodność całego kontenera z SD FAIL z wyjaśnionego powodu.
- Jeśli wymaganiem jest zachowanie dokładnie całego pliku SD wraz z dopełnieniem, potrzebny jest dodatkowy importer SD/MTP lub osobna, zweryfikowana polityka archiwizacji. Nie odtwarzać zer na podstawie jednej zaobserwowanej reguły.
- JPEG PTP może służyć do QC bez utraty informacji obrazu wykazanej w tej próbie. Oryginały i pochodne pozostają rozdzielone.
- HDMI + PTP: PASS jednej ekspozycji, lecz brak dowodu nieprzerwanej aktualizacji Live View. Następny test ma zbadać Auto Review i moment ekspozycji; dopiero potem serie 10/50/100.
- MTP pozostaje nieprzetestowaną alternatywą importu. Nie wysłano w nim poleceń migawki ani Preview.

## 6. Dowody i stan końcowy

[Ograniczony zapis JSON T1/T2](SONY_T1_T2_EVIDENCE_2026-10-13.json).

Lokalne dane pod `/srv/vision-data/vision/sessions/sony-uvc-ptp-T1-20261013T193730Z/`: konfiguracje, skrypt pojedynczej próby, ptp-one-shot.log, uvc-frames.json, result.json, sd-ptp-integrity.json, jpeg-difference-analysis.json, oryginały i trzy próbki HDMI. Zdjęć i niezredagowanych konfiguracji nie publikujemy w publicznym repozytorium.

Na koniec porównania karta pozostaje zamontowana read-only. Przed odłączeniem USB wymaga odmontowania przez operatora; procesy testowe nie korzystają już z karty. Nie wykonywano naprawy filesystemu, usuwania zdjęć, nowych ekspozycji w T2, aktualizacji firmware, zmian sieci/usług/GPU/NPU ani merge.

Ustawienia aparatu zmieniał operator zgodnie z instrukcjami. Brak przywrócenia PC Remote w chwili zapisu raportu nie jest błędem: aparat pozostawiono w Mass Storage do domknięcia bezpiecznego odmontowania.
