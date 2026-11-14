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

## Korekta: najwyższe punkty trzech złączy (14.11.2026)

Poprzednia obwiednia całego ECU **P99 = 51,32 mm nie jest najwyższym punktem bryły**. P99 całego ECU pomija wąskie, wysokie złącza, ponieważ zajmują niewielką część punktów stereo. Dla przyszłego planowania trajektorii NERO NIE wolno utożsamiać globalnego P99 z maksymalną wysokością przeszkody.

Ponownie przeanalizowano te same **25 rzeczywistych klatek RAW16**, bez ponownego otwierania kamery, bez nowej regulacji IR i bez ingerencji w produkcję. Lokalną płaszczyznę stołu dopasowano oddzielnie dla każdej klatki w 3D (RANSAC, threshold 6 mm, wycięcie ECU/większości planszy). Z mapy wysokości względem normalnej stołu wydzielono trzy widoczne gniazda, **w układzie depth rectified-left**. Małe stabilne rejony 5×5 wokół górnych krawędzi poddano filtrowaniu medianowemu — to nie raw MAX wszystkich pikseli.

| Wtyczka / gniazdo | Lokalny obszar 5×5 (depth u,v) | Mediana wysokości nad stołem | std między 25 klatkami | Mediana punktu w układzie optycznym kamery XYZ [m] |
|---|---|---:|---:|---|
| Lewe czarne | 645,439 | 56,91 mm | 1,28 mm | [0,00965; 0,05797; 0,76600] |
| **Środkowe szare — najwyższe** | **726,444** | **62,88 mm** | **1,12 mm** | **[0,08717; 0,06205; 0,76300]** |
| Prawe czarne | 772,494 | 53,56 mm | 0,64 mm | [0,13398; 0,11285; 0,77900] |

Każdy pomiar lokalnego obszaru posiadał poprawne dane we wszystkich 25/25 klatkach. W niezależnym sprawdzeniu **całego obszaru ECU** (nie tylko trzech ręcznie zidentyfikowanych złączy) zbudowano medianową mapę wysokości na podstawie 25 klatek, wymagając ważności pikseli w co najmniej 20 klatkach, a następnie filtracji medianowej 5×5. **Jedyny spójny obszar z wysokością powyżej 60 mm** miał powierzchnię 29 pikseli w pobliżu szarego złącza (box depth [720,442,731,446], centroid [725,6;443,4], najwyższa przefiltrowana wartość ~63,94 mm). Nie znaleziono spójnych obszarów >65 mm po filtracji. To potwierdza ranking wysokości złączy w obserwowanej scenie.

**Uwaga:** wysokości to estymaty ze stereo, nie dokładne mechaniczne wymiary wtyczek. Wartość std opisuje korelację kolejnych klatek, nie niepewność bezwzględną. Nierówna widoczność krawędzi, powierzchnie odblaskowe i luki stereo mogą nadal zaniżać lub zawyżać wartości. Fizyczne wysokości złączy zostały później podane przez operatora; porównanie i ograniczenia opisano w aktualizacji poniżej.

**Konsekwencja dla Vision:** Perception powinien udostępniać oddzielnie: wysokość powierzchni korpusu (~25 mm), kilka lokalnych wierzchołków elementów wystających (~54–63 mm) z lokalizacją i jakością pomiaru oraz ostrożnościową przestrzeń zabronioną dla trajektorii. Takie dane są wyłącznie percepcją; przed ruchem robota wymagane są kalibracja stołu/robot_base, marginesy bezpieczeństwa i niezależne mechanizmy STOP.

## Referencje mechaniczne operatora — 14.11.2026

Operator podał fizyczne wysokości nad stołem: **szare środkowe złącze 68 mm**, **czarna wtyczka 64 mm**. W scenie występują dwa czarne złącza; operator nie wskazał jeszcze, czy 64 mm odnosi się do lewego czy prawego. Poniższe porównanie ma charakter diagnostyczny, nie jest korektą kalibracji.

| Złącze | Wysokość fizyczna (operator) | Pomiar stereo lokalnej łaty 5×5 | Różnica stereo − fizyczny |
|---|---:|---:|---:|
| Szare środkowe | 68,00 mm | 62,88 mm | **−5,12 mm** |
| Lewe czarne, jeżeli to jego dotyczy 64 mm | 64,00 mm (przypisanie niepotwierdzone) | 56,91 mm | −7,09 mm (warunkowo) |
| Prawe czarne, jeżeli to jego dotyczy 64 mm | 64,00 mm (przypisanie niepotwierdzone) | 53,56 mm | −10,44 mm (warunkowo) |

Spójny szczyt szarego złącza z medianowej mapy 25 klatek osiągał około **63,94 mm** (różnica do referencji 68 mm: **−4,06 mm**), ale jest to inna definicja pomiaru niż mediana lokalnej łaty. Nie należy mieszać tych metod w wyznaczaniu offsetu.

**Istotne ograniczenie**: wysokość fizyczna z suwmiarki może odnosić się do zewnętrznej krawędzi złącza słabo obserwowalnej przez stereo, podczas gdy lokalna łata 5×5 mierzy widoczne punkty bliżej wewnętrznej części. Różnica nie dowodzi stałego offsetu głębi ani błędnej skali kamery. Nie wprowadzamy automatycznej korekty +5 mm ani innych dopasowań do jednej sztuki ECU.

**Kierunek Perception**: zachować odrębne pomiary 3D korpusu i wystających elementów; do wykrywania najwyższej przeszkody użyć przestrzennie spójnego szczytu ze wskaźnikiem pokrycia, zmienności i niepewności, a nie globalnego P99. Nie deklarować gotowości NERO do ruchu bez walidacji 3D i transformacji table↔robot_base.
