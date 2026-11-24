# Vision — ETC3: rzeczywista lokalizacja RGB-D, 24 listopada 2026

**Status:** `PROVISIONAL_LIVE_ECU_LOCALIZED` — pozycja w ramce optycznej Luxonis i względem lokalnej płaszczyzny stołu zmierzona; absolutne `table/world` oraz tożsamość wariantu ECU **niezatwierdzone**.

**Zakres:** pomiar offline na rzeczywistych klatkach z nieruchomej OAK-D Pro AF; bez ruchu NERO/Sony, uruchamiania sterownika, aktualizacji PlanningScene, wstrzykiwania TF, modyfikacji zamrożonego VGP i bez wdrożenia PR #50.

## Obserwacja

Operator wskazał, że na stole leży otwarty ETC3 z odsłoniętą PCB. Nowo zebrana sekwencja zawiera osiem klatek RGB (1920×1080 BGR) i osiem klatek Depth (16UC1 w mm) z ROS 2 Jazzy / DepthAI ROS v3, wraz z CameraInfo i datami/sha256 surowych próbek. Ramki RGB i Depth są wyrównane do `oak_rgb_camera_optical_frame`. Kluczowy materiał pomiarowy jest zachowany wyłącznie w **prywatnym staging na NVMe VENTUNO**, nie w repozytorium.

## Dopasowanie wizualne

- Archiwalny obraz tego samego, uprzednio wskazanego ECU z 23.11.2026 został wykorzystany wyłącznie jako referencja do śledzenia cech, **nie jako zatwierdzony Reference Profile**.
- SIFT + RANSAC: **1207–1273 punktów zgodnych na każdej z ośmiu klatek**, dopasowanie 94–95%, zmiana orientacji obrazu około **+0,65°** względem pozycji archiwalnej.
- Środek charakterystycznego szarego złącza na obrazie: **(1179,13; 543,02) px**. Wartość jest lokalizacją obrazu, nie identyfikacją wariantu.
- Niezależna kontrola z drugiego zdjęcia archiwalnego, wykonanego po przesunięciu ETC3: **216/289 dopasowań SIFT/RANSAC**; aktualne położenie złącza wyznaczono niezależnie jako **(1179,20; 542,98) px**. Różnica z pierwszą rejestracją **0,077 px** (zgodność śledzenia obrazowego, nie dokładność przestrzenna).
- Obrazowe pozycje złącza były stabilne we wszystkich ośmiu bieżących klatkach.

## Wynik głębi, XYZ i powierzchni stołu

| Wielkość | Zmierzona wartość / status |
| --- | --- |
| Szare złącze — kamera optyczna X [mm] | **+115,94** |
| Szare złącze — kamera optyczna Y [mm] | **+15,63** |
| Szare złącze — kamera optyczna Z [mm] | **751,00** |
| Głębokość złącza | mediana **751 mm**, MAD **2 mm**, odchylenie standardowe między klatkami **2,53 mm** |
| Liczba zaakceptowanych odczytów | **7 z 8**; jeden odstający odczyt 894 mm został odrzucony |
| Lokalna płaszczyzna stołu | osiem niezależnych dopasowań do punktów 3D otaczających ECU, bez używania zewnętrznego TF |
| RMS reszt płaszczyzny | **1,72–1,84 mm** zależnie od klatki |
| 95. percentyl reszt na danych kontrolnych | **3,37–3,80 mm** |
| Obrys widocznych powierzchni ETC3 | około **239,9 × 285,3 mm** przy progu wysokości 12 mm |
| Stabilność obrysu (8 klatek) | krótszy bok **238,6–241,1 mm**, dłuższy **282,2–285,3 mm** |
| Wysokość widocznych powierzchni | mediana **26,6 mm**, 99. percentyl około **49,2 mm**; **nie** jest to pełna, zweryfikowana wysokość kolizyjna ECU |

Szczególnie ważne: 49,2 mm opisuje **99. percentyl widocznych punktów głębi**, nie maksymalną fizyczną wysokość obudowy, złącz lub elementów zasłoniętych. Segmentacja 8/12/18 mm i osiem osobnych ramek dały zbliżone obrysy. Rozrzut wewnętrzny nie stanowi certyfikowanej dokładności pomiaru XYZ.

## Układ stołu — tylko niezatwierdzony kandydat

Historyczny wynik pięciu pozycji ChArUco (20.11.2026) zawiera `T_table_rgb_optical_candidate`, **UNAPPROVED_CANDIDATE**. Transformacja była użyta wyłącznie do diagnostycznego przeliczenia kamery na osie stołu, bez publikowania TF w ROS 2.

| Punkt | X, Y, Z [mm] — laboratoryjny CANDIDATE |
| --- | --- |
| Szare złącze | **(702,74; 471,36; 38,94)** |
| Środek widocznego obrysu, punkt na płaszczyźnie blatu | **(672,33; 426,34; −3,37)** |

Współrzędna Z=−3,37 mm środka obrysu po przeliczeniu przez stary transform jest przykładem jego niezweryfikowanego przesunięcia względem nowej lokalnie zmierzonej płaszczyzny stołu. Współrzędne absolutne **nie są zatwierdzone do sterowania robotem, wyznaczania prześwitów ani aktywacji S03/S04**.

## Ograniczenia i bramki

1. Klatki RGB/Depth zapisano osobnymi kolejkami; przyporządkowanie najbliższych czasowo par obejmuje odstępy do około 0,6 s. Stabilność obiektu była sprawdzona obrazowo, ale pomiar głębi zakłada brak ruchu w tym czasie. Nie udajemy pełnej synchronizacji każdej pary.
2. Pomiary optyczne wynikają z intrinsics CameraInfo aktywnego sterownika i lokalnie dopasowanej płaszczyzny stołu. Wymagany jest osobny niezależny punkt kontrolny, aby zatwierdzić absolutne `table → rgb_optical`.
3. Obrys jest **widoczną bryłą depth**, a nie kompletną obwiednią kolizyjną. Przesłonięcia, otwory i brak górnych punktów nie są automatycznie rekonstruowane.
4. SIFT wykazuje bardzo mocną zgodność obrazu ze znanym zdjęciem. Nie zastępuje to sprawdzenia wszystkich wymaganych reguł typu/wariantu `ECU Reference Profile`. Rzeczywisty profil ETC3 pozostaje `DRAFT / NOT_READY`.
5. Nie wykonano fizycznego zaliczenia Core **S03 ani S04**. Brakuje zatwierdzonego wspólnego TF, pełnego profilu wzorcowego ETC3 i niezależnie uwierzytelnionego `MeasurementBinding`.
6. W tej serii nie było poleceń do NERO, MoveIt, CAN, Sony ani zmiany aktywnej sceny. Nie ruszano kalibracji VGP V1.

**Dalszy etap:** walidacja bezwzględnej transformacji kamery do osi stołu przy użyciu niezależnego punktu odniesienia, zatwierdzenie referencyjnej geometrii ETC3 i podłączenie neutralnego estymatora bryły do `VisionRuntimeCoordinator`. Bez powtarzania sprawdzonych testów RGB-D czy wykonywania ruchów robota.

## Powtarzalność i integralność (prywatne dowody)

- Capture manifest SHA-256: `69a4f64da781d04bafc3866e1a1dc12aa9b9ad1a88b005729911831a27dac72e`
- Wynik pełny JSON SHA-256: `c8cad62ab2e4361e74f1a2392742bad0ae95bcf65a4d909de3de4b44ee5e30a5`
- Archiwalny obraz wzorcowy (23.11) SHA-256: `ba147d3272779774fcc3af795810ee38f4bcdd3909a82e0613630756f6fedb39`
- Kandydat kalibracji (20.11) SHA-256: `d909ea9e94a02e561277c56d4989c9e41b896e68a2e867f90f4012854b7f21ec`
- Program diagnostyczny: `tools/lab/etc3_localization/localize_etc3_rgbd.py`; **14 syntetycznych testów PASS**.
