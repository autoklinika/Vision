# Vision — pierwszy pomiar geometrii prawdziwego ECU

**Data:** 2026-11-14. **Status:** REAL_ECU_CAPTURE_PASS / AUTO_OBJECT_COMPONENT_25_OF_25 / TOP_SURFACE_20_OF_25 / METROLOGY_UNVERIFIED / PRODUCTION_RESTORED_PASS.

## Scena

Na stole VENTUNO Q po raz pierwszy położono otwarty sterownik ECU z widoczną PCB, trzema dużymi gniazdami/złączami i otworami montażowymi. Plansza ChArUco leży obok; elementy testowe 34/50,4/101 mm zostały usunięte. Oświetlenie białe pozostawiono włączone.

Podgląd RGB 1920×1080 i mapa Depth 1280×800 zostały sprawdzone wizualnie. Detekcja ECU jest **geometryczna, a nie identyfikacją marki/modelu AI**. Nie zakładano zgodności współrzędnych pikseli RGB z Depth.

## Akwizycja

Zapisano prywatnie **25 pełnych, rzeczywistych map RAW16** z Luxonis OAK-D Pro AF. Aby porównać z wcześniej zweryfikowanymi pomiarami, wykorzystano konfigurację DepthAI 3.12.0: StereoDepth 800p, rektyfikacja ON, LR check ON, Subpixel ON, Extended Disparity OFF, IR Dot OFF, IR Flood OFF, RGB 1080p/30. Właściwą macierz K pobrano bezpośrednio z `ImgFrame.getTransformation()`, rozdzielczość 1280×800, bez zapisu EEPROM.

Akwizycję wykonano ze skryptem bezpiecznej pojedynczej własności USB, który zatrzymuje `vision-oak-camera.service`, zbiera próbki i przywraca usługę. **CAPTURE_PASS, 25/25**, 373 pakiety RGB, 362 pakiety Depth, 10 luk numeracji Depth odnotowanych przez konsumenta, RAW16 valid ~80,108% dla całego kadru. Wyłączenie IR potwierdzone przez SDK Dot/Flood `True/True`.

## Metoda Perception

1. Dopasowanie płaszczyzny stołu w 3D (RANSAC, bez podawania wymiarów ECU).
2. W obrębie roboczego ROI **całego stołu**, nie ręcznego ROI ECU, odrzucenie tła płaskiego i punktów o wysokości poza zakresem 12–105 mm nad stołem; największa spójna składowa, bez wyjścia poza strefę stołu, zostaje kandydatem ECU.
3. Projekcja poprawnych punktów tej składowej na płaszczyznę stołu i obrócony prostokąt obwiedni (wymiary **widocznego rdzenia**, nie wszystkich cienkich mocowań).
4. Osobny pomiar dominującej powierzchni przez `top_surface.py` (PR #26), z odmową pomiaru w klatkach niestabilnych.
5. Osobne statystyki najwyżej położonych punktów bryły (percentyl 95 i 99), **bez uznawania percentyla za rzeczywisty absolutny najwyższy punkt mechaniczny**.

Wartości są w `stereo_left_rectified_optical` (camera XYZ) i nie mają jeszcze transformacji do `table` ani `robot_base`.

## Wyniki: mediana z 25 klatek

| Parametr | Mediana | Odchylenie std klatek | Akceptacja |
|---|---:|---:|---:|
| Długość widocznego rdzenia | **274,19 mm** | 2,144 mm | 25/25 |
| Szerokość widocznego rdzenia | **224,13 mm** | 4,232 mm | 25/25 |
| Dominująca powierzchnia nad stołem | **24,875 mm** | 0,574 mm | 20/25 |
| Obwiednia wysokości P95 | **47,14 mm** | 0,283 mm | 25/25 |
| Obwiednia wysokości P99 | **51,32 mm** | 0,593 mm | 25/25 |
| RMSE dopasowania dominującego stołu | **3,53 mm** | 0,045 mm | 25/25 |

- Geometryczny ECU wykryty w każdej klatce, mediana obrysu Depth `[556,320,832,552]`.
- Pozostałe 5/25 klatek `top_surface.py` odrzucono jako `UNSTABLE_TOP_SURFACE` (height=null, bez ekspozycji jako gotowy pomiar).
- Orientacyjna mediana punktu położenia w układzie optycznym kamery: **[0,0488, 0,0582, 0,7990] m**. Jest to **centroid widocznych punktów**, nie origin/uchwyt robota ani punkt montażowy.
- Wysokości P95/P99 opisują punkty 3D komponentów i złącz; ich wartość **nie jest gwarantowaną wysokością obudowy**. Różnica pomiędzy dominującą powierzchnią ~25 mm a obwiednią ~51 mm jest spodziewana dla otwartej PCB z wypukłymi komponentami.

## Bezpieczeństwo, metrologia, odtwarzalność

**NOT_METROLOGICALLY_VERIFIED**: nie wykonano jeszcze porównania do fizycznych wymiarów tego ECU. Nie wolno interpretować niewielkiego rozrzutu klatek jako błędu bezwzględnego. Długość/szerokość pomijać mogą cienkie mocowania, a niektóre złącza i powierzchnie nie są pełne w chmurze stereo. Układy `table` i `robot_base` są UNAVAILABLE; nie wyzwalano ani nie programowano ruchu NERO. Brak bezpieczeństwa funkcjonalnego gwarantowanego przez kamerę.

Po zakończeniu kontroli produkcyjny Camera Service: **ONLINE**, USB SUPER, RGB ~30,2 FPS, Depth ~29,3 FPS, Depth valid ~80%, `error=null`. Prod i `main` bez zmian.

**Dane prywatne (nie commitować):** `/srv/vision-data/staging/vision-ecu-live-test-20261114` — rzeczywiste zdjęcia, RAW16, skrypty pilotowe, per-frame JSON i podgląd mapy głębi. Wszystkie surowe pliki 0600. Repo zawiera tylko zagregowany raport.

**Następna pojedyncza potrzebna czynność:** operator mierzy suwmiarką rzeczywistą długość, szerokość oraz wysokość korpusu i maksymalną wysokość wystającego złącza; dopiero wtedy sprawdzamy bias i decydujemy o dokładności algorytmu. Przed ruchem robota konieczna kalibracja table↔robot_base oraz osobna bramka bezpieczeństwa.
