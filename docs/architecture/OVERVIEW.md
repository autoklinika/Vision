# Vision — architektura logiczna v0.1

**Status:** projekt architektury, bez implementacji runtime. Dokument opisuje granice odpowiedzialności, a nie gotowe funkcjonalności.

## Kontekst

Stanowisko laboratoryjne wykonuje zdjęcia PCB i pozyskuje *radiometryczne* dane termiczne. VENTUNO Q zarządza pozyskiwaniem i jakością danych, pozycjonowaniem oraz ewentualnym ruchem robota. AI Platform analizuje szczegółowo obrazy *poza* VENTUNO.

## Proponowane niezależne moduły

| Moduł | Odpowiedzialność | Status |
|---|---|---|
| Acquisition | sterowanie kamerą, ekspozycja, synchronizacja, zapis oryginału | do zbadania |
| Quality | ostrość, drgania, ekspozycja, pokrycie, powtórki ujęć | do implementacji |
| Registration | kalibracja intrinsics/extrinsics, układy współrzędnych, korelacja ujęć | do implementacji |
| Mosaic | składanie zdjęć, korekcja geometrii, zachowanie provenance | do implementacji |
| Focus stack | seria zdjęć na różnych płaszczyznach, maski ostrości, składanie | do implementacji |
| Thermal | radiometria per-pixel, kalibracja, synchronizacja z RGB | dobór kamery przed wdrożeniem |
| Robot | trajektorie, ograniczenia ruchu, kontrolowane pozycjonowanie | wymaga wyboru manipulatora |
| Depth/Scene | mapa przeszkód i ocena prześwitu; pomoc dla planera | opcjonalny sensor |
| Export | komplet danych/metryk/metadanych do AI Platform | kontrakt nieustalony |

## Kierunek przepływu

1. Operator wybiera obszar PCB i cel akwizycji.
2. Kontroler sprawdza gotowość sprzętu i limitów ruchu.
3. Pozycjonowanie i oświetlenie; kamera rejestruje oryginalny plik i metadane.
4. Quality akceptuje ujęcie albo żąda powtórzenia z uzasadnieniem.
5. Registration/Mosaic/Focus stack tworzą produkty pochodne *bez utraty oryginałów*.
6. Thermal dołącza dane radiometryczne i parametry korekcji, gdy sensor jest dostępny.
7. Export przygotowuje wersjonowany zestaw dla odrębnej AI Platform.

## Kontrakty do zdefiniowania

- Identyfikator sesji, ujęcia i pozycji robota; monotoniczny znacznik czasu + czas UTC.
- Format oryginału, wartości ekspozycji, obiektywu/ogniskowej, oświetlenia i pozycji w mm/stopniach.
- Jednostki i układy odniesienia: kamera RGB, kamera termiczna, stół, narzędzie, robot.
- Temperatura w K/°C, emisyjność, temperatura otoczenia/odbita, dystans, ważność kalibracji.
- Ocena jakości i powód odrzucenia, wersja algorytmu i nastawy przetwarzania.
- Wersjonowany manifest eksportowy z hashami plików; brak przesyłania sekretów i tokenów.

## Granice i niezależność

- Nie zakładamy konkretnego frameworka UI, robota, SDK Qualcomm ani transportu do AI Platform przed testami.
- OpenCV to kandydat do obróbki klasycznej; YOLO11n to kandydat do prostych zadań detekcyjnych, nie zastępuje pomiarów ani inspekcji eksperckiej.
- Opcjonalne NPU Hexagon i GPU Adreno wymagają dowodu działania w Ubuntu, nie tylko wykrycia w specyfikacji.
- Moduły sprzętowe muszą mieć adaptery i móc pracować na atrapie (mock) do testów.

## Bezpieczeństwo mechaniczne

**Kamera głębi i model AI nie są niezależnym systemem bezpieczeństwa.** Wymagamy mechanicznych/elektrycznych limitów, E-stop, odpowiednich interlocków, osobnego nadzoru napędów oraz procedury bezpiecznego odzyskania stanu. Bez tego system nie może wykonywać autonomicznych ruchów ramieniem.

## Decyzje otwarte

Model ramienia, kamera termiczna, kamera głębi, mechanizm triggera Sony A6100, dobór interfejsu oświetlenia, GUI, framework runtime, protokół eksportu i archiwizacja danych.
