# Vision — Luxonis BoxEstimator: test wysokości 34 / 50,4 / 101 mm

**Data:** 2026-11-13. **Stan:** OFFLINE_REPLAY_PASS / GEOMETRY_PARTIAL_PASS / UNIVERSAL_1MM_ACCURACY_FAIL / PRODUCTION_UNTOUCHED.

**Scope:** oddzielny eksperyment dokumentacyjny pod PR #25 (DepthAI v3, OAK-D Pro AF, VENTUNO Q ARM64). Bez wdrażania, bez USB, IR, E-STOP i NERO.

## Źródło i rodzaj testu

Oficjalna implementacja Luxonis: [BoxEstimator](https://github.com/luxonis/depthai/blob/main/depthai_sdk/src/depthai_sdk/classes/box_estimator.py), źródło pobrane z aktualnej gałęzi `main` (SHA-256 pliku `2b248a80d2396f01c1b30d136823693f5e3b484cdaf0760f5539e85913068317`). Funkcje `get_box_top`, `fit_plane_vec_constraint`, `get_plane_inliers`, `get_pts_distances_plane`, `create_rotation_matrix`, `rotate_points`, `translate_points` i `get_dimensions` zostały użyte z **oryginalnymi ciałami metod** wyodrębnionymi AST, bez ich zmieniania.

**To NIE jest uruchomienie całej aplikacji Luxonis ani pełnej klasy BoxEstimator:** dostępny VENTUNO ARM64 nie ma pakietu Open3D. Zamiast Open3D voxel/outlier/ground plane wykorzystano istniejący moduł Vision `fit_plane` (3D RANSAC, lokalny ROI stołu, próg 6 mm, wyłącznie inliery stołu) oraz ręcznie uprzednio wybrane ROI trzech obiektów. Poza tym górna płaszczyzna jest dopasowywana oryginalną metodą Luxonis.

Dane fizyczne pochodzą z wcześniejszej kontrolowanej rejestracji RAW16 1280×800 dla tej samej OAK-D Pro AF. Dla każdego trybu odtworzono 25 map głębi oraz odczytane z klatek K. Punkty są przeliczane na mm w optycznym układzie `stereo_left_rectified_optical`. Znane wysokości używane **wyłącznie do QA, nie przez algorytm**: beżowe 34,0 mm, czerwony 50,4 mm, biało-czerwone 101,0 mm.

## Test oryginalnego progu BoxEstimator: 50 mm

Subpixel ON, IR OFF przed, 5 zapisanych klatek na element:

| Obiekt | Wynik | Akceptacja przez procedurę |
|---|---:|---:|
| Beżowe 34,0 mm | brak wyniku | 0/5 |
| Czerwony 50,4 mm | mediana 53,189 mm | 4/5 |
| Biało-czerwone 101,0 mm | mediana 100,585 mm | 5/5 |

Domyślne `threshold=50` w oryginalnym BoxEstimator usuwa obiekt 34 mm, bo nie jest wystarczająco wysoki nad stołem. Nie jest to odpowiedni parametr dla wszystkich elementów Vision.

## Adaptacja: próg separacji 15 mm, pełna seria 25 klatek na fazę

Wartości to mediany estymowanej wysokości; w nawiasach błąd od referencji w mm:

| Tryb / IR | Beżowe, ref. 34,0 | Czerwony, ref. 50,4 | Biało-czerwone, ref. 101,0 |
|---|---:|---:|---:|
| Subpixel ON / OFF #1 | 32,685 (−1,315) | 49,963 (−0,437) | 100,858 (−0,142) |
| Subpixel ON / Dot 5% | 34,623 (+0,623) | 47,091 (−3,309) | 100,764 (−0,236) |
| Subpixel ON / OFF #2 | 32,555 (−1,445) | 49,633 (−0,767) | 100,675 (−0,325) |
| Subpixel OFF / OFF #1 | 32,215 (−1,785) | 50,768 (+0,368) | 100,504 (−0,496) |

Wszystkie warianty zwróciły liczbowy wynik dla 25/25 ramek na obiekt. **To nie oznacza metrologicznej akceptacji wyników.**

Rozrzut dla Subpixel ON:
- OFF #1: beżowe std 1,078 mm; czerwone std **2,499 mm** (min–max **44,241–53,982 mm**); biało-czerwone std 0,338 mm;
- Dot 5%: beżowe std 0,184 mm; czerwone std 0,814 mm, ale mediana zaniżona o **3,309 mm**; biało-czerwone std 0,202 mm.

Ramy tego samego ujęcia są skorelowane czasowo. Odchylenie standardowe między klatkami nie jest certyfikowanym błędem urządzenia. Sprawdzana była metoda pomiaru geometrii, nie dokładność kalibracji fabrycznej, transformacji table/robot_base czy rozpoznawania ECU.

## Porównanie z istniejącym algorytmem Vision

W tym samym wcześniejszym teście trzech wysokości `height_planes.v1` dla Subpixel ON / IR OFF #1 dawał mediany **35,456 / 53,494 / 103,349 mm** (34 / 50,4 / 101 mm). Adaptacja oryginalnych metod Luxonis dała **32,685 / 49,963 / 100,858 mm**. Widać wyraźne zmniejszenie błędu mediany na 50,4 i 101 mm, ale **nie** można jeszcze uznać za rozwiązany problem niestabilności czerwonego elementu ani jakości geometrycznej obrazu.

## Decyzja rozwojowa

1. **Wykorzystać wzorzec Luxonis**: chmura 3D + lokalny stół + dopasowanie górnej płaszczyzny. Nie kopiować bezrefleksyjnie progów 50 mm ani całej aplikacji.
2. Dla prostokątnych ECU kontynuować klasyczną geometrię płaszczyzn, z raportowaniem rozrzutu i fail-closed po przekroczeniu bramek.
3. Dla małych / cylindrycznych elementów najpierw wyodrębnić ROI samej górnej powierzchni (RGB + prawidłowa transformacja RGB–stereo); nie redukować błędu przez arbitralną korektę offsetu.
4. Nie uruchamiać kolejnych sweepów IR ani nie zmieniać EEPROM. `CuboidFitter` z nowszego przykładu Luxonis wymaga dodatkowo Open3D i detekcji/segmentacji, dlatego nie należy go uznawać za natywny miernik wysokości w obecnym Camera Service.
5. **Robot-ready: NIE.** Układy `table` i `robot_base` nadal niezweryfikowane; wizyjne wykrycie geometrii nie jest certyfikowaną funkcją bezpieczeństwa.

Źródła dodatkowe:
- [Oficjalny Luxonis box-measurement (DepthAI v3)](https://github.com/luxonis/oak-examples/tree/main/depth-measurement/measurement-3d/box-measurement)
- [CuboidFitter](https://github.com/luxonis/oak-examples/blob/main/depth-measurement/measurement-3d/box-measurement/utils/cuboid_fitter.py)

**Dane prywatne:** tylko lokalny NVMe, `/srv/vision-data/staging/oak-three-heights-private-20261113` i `/srv/vision-data/staging/oak-luxonis-boxestimator-20261113`; brak obrazów, map i prywatnych danych w GitHub. Oryginalny Camera Service pozostał aktywny przez cały replay.
