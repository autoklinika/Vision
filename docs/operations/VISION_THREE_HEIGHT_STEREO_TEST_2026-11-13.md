# Vision — test trzech wysokości na OAK-D Pro AF

**Data:** 2026-11-13
**Host:** Arduino VENTUNO Q / Ubuntu ARM64 / NVMe
**Kamera:** Luxonis OAK-D Pro AF, DepthAI 3.12.0, USB3 SuperSpeed
**ADR:** ADR-VISION-ARCH-001 (Camera Service / Perception Engine / Vision Core)
**Gałąź:** feature/perception-parallel-plane-height-20261113 (stacked nad PR #23)
**Status:** CAPTURE_PASS / THREE_HEIGHT_GEOMETRY_TEST_PASS / 1MM_METROLOGY_FAIL / PROD_RESTORED_PASS
**Bezpieczeństwo:** ZERO komend ruchu NERO, ZERO Core, ZERO EEPROM/calibration flash, ZERO on-camera NN, ZERO GPU RM.

## 1. Fizyczne wzorce i założenia

Operator umieścił na stole:
- beżowe pudełko — nominalnie **34,0 mm** wysokości;
- czerwony element o płaskim, kolistym wierzchu — zmierzony **50,4 mm**;
- biało-czerwone pudełko — nominalnie **101,0 mm**.

Na prywatnej próbce RGB wszystkie obiekty oraz plansza ChArUco są w pełni widoczne. Ustawienie nie było zmieniane w ramach danej sesji. Przekazana wysokość pudełek jest referencją operatora, a nie świadectwem kalibracyjnym. Zmierzony bok czarnego kwadratu ChArUco = 29,5 mm (poprzedni raport).

Manually preselected rectified-left depth ROIs (xyxy), na podstawie wizualnego podglądu PRZED sesjami, bez optymalizacji względem znanych wysokości:

| Obiekt | ROI obiektu | ROI lokalnego stołu |
|---|---|---|
| beige_box | 475,170,625,330 | 350,70,755,425 |
| red_cylinder | 403,299,521,404 | 275,223,670,513 |
| white_red_box | 560,427,805,637 | 490,337,875,710 |

ROI w pikselach rectified-left StereoDepth **nie** jest automatycznie powiązany z obrazem RGB. Ręczne określenie ROI nie jest docelową automatyczną detekcją obiektów. Obliczenia pozostają w stereo_left_rectified_optical; table_frame/robot_base są UNAVAILABLE.

## 2. Procedura

Wykonano dwie oddzielne sesje testowe przy tym samym układzie fizycznym:
- subpixel ON (3 fractional bits);
- standardowy integer disparity: subpixel OFF.

W każdej sesji: 13 s stabilizacji, 3 fazy po 16 s (IR OFF / IR Dot 5% / IR OFF). RGB 1920x1080, StereoDepth 1280x800 RAW16 w mm, left-right-check ON, rectification ON, extended disparity OFF; profil urządzenia USB3 SUPER.

Zbierano 25 pełnych map depth na fazę, co ~0,5 s po 3 s settle, razem **75 map na sesję / 150 map RAW16**. Po zakończeniu sesji, offline na VENTUNO (bez ponownego otwierania USB), **ten sam estymator height_planes.v1** obliczył wyniki dla trzech obiektów na każdej mapie. Łącznie **450 prób pomiaru wysokości**.

Algorytm wyznacza niezależnie lokalną płaszczyznę stołu i górną powierzchnię (RANSAC), odrzuca ścianki boczne, ocenia normalne i residual RMSE. Wartości 34,0/50,4/101,0 mm NIE są podawane do estymatora, służą tylko do osobnej QA. Test nie może potwierdzić certyfikowanej dokładności, stabilności układu RGB->stereo ani parametrów ruchu robota.

## 3. Wyniki subpixel ON

| Faza | Beżowe 34,0 mm | Czerwone 50,4 mm | Biało-czerwone 101,0 mm |
|---|---:|---:|---:|
| IR OFF #1 | 35,456 (+1,456) | 53,494 (+3,094) | 103,349 (+2,349) |
| IR Dot 5% | 36,219 (+2,219) | 49,291 (-1,109) | 102,301 (+1,301) |
| IR OFF #2 | 35,357 (+1,357) | 52,916 (+2,516) | 103,083 (+2,083) |

Wszystkie liczby w mm: mediana obliczonych wysokości (błąd do referencji w nawiasie). Każda faza: 25 ramek. Oba pudełka 25/25 zaakceptowane we wszystkich fazach; czerwony: 25/25, 25/25, 24/25.

Odchylenie standardowe kolejnych klatek:
- beige 0,660 / 0,175 / 0,591 mm;
- red 1,856 / 0,899 / 1,539 mm;
- white_red 0,531 / 0,179 / 0,610 mm.

Subpixel ON utrzymał RGB 30,06–30,25 FPS, depth 29,12–29,38 FPS. W statystykach konsumenta DepthAI wykryto 13–16 luk sekwencji w fazie.

## 4. Wyniki standard disparity / subpixel OFF

| Faza | Beżowe 34,0 mm | Czerwone 50,4 mm | Biało-czerwone 101,0 mm |
|---|---:|---:|---:|
| IR OFF #1 | 36,467 (+2,467) | 52,047 (+1,647) | 103,681 (+2,681) |
| IR Dot 5% | 39,356 (+5,356) | 52,408 (+2,008) | 103,185 (+2,185) |
| IR OFF #2 | 35,902 (+1,902) | 51,764 (+1,364) | 103,832 (+2,832) |

Czerwony w trybie integer i bez IR miał **tylko 5/25 i 4/25** pomiarów, które przeszły bramkę geometrii. Te mediany są obarczone selekcją i nie można traktować ich jako dowodu lepszej dokładności integer mode. Pozostałe obiekty i faza Dot 5% miały po 25/25 zaakceptowanych pomiarów. W części dopasowań integer obserwowano residual RMSE=0 (artefakt kwantyzacji/wyboru punktów, NIE dowód idealnej płaszczyzny).

Subpixel OFF utrzymał RGB 30,12–30,25 FPS, depth 30,12–30,25 FPS i 0 wykrytych luk sekwencji w krótkich fazach testu.

## 5. Wnioski o jakości metrologicznej

1. **Płaskie pudełka są wykrywane z wysoką stabilnością geometryczną**, ale błędy mediany nadal sięgają 1,3–2,8 mm w subpixel i 1,9–5,4 mm w integer. Wszystkie fazy dla każdego obiektu nie spełniają badawczego progu bezwzględnego błędu mediany <= 1 mm.
2. Red cylinder jest znacznie trudniejszy przy IR OFF, szczególnie bez subpixel. Prawdopodobne są problemy z krawędziami i widocznością górnego, kolistego dysku. Należy oddzielić błąd stereomatchingu i doboru inlierów.
3. Dot 5% zmienia wyniki w sposób **zależny od obiektu**: bias czerwonego przy subpixel poprawia się z ok. +2,5..+3,1 mm do -1,1 mm, beżowego pogarsza się z +1,4 do +2,2 mm, biało-czerwonego poprawia się z +2,1..+2,35 do +1,3 mm. Brak podstaw do globalnej korekty IR lub jednego offsetu dla wszystkich ECU.
4. Zmniejszenie rozrzutu klatek po włączeniu IR nie jest równoznaczne z mniejszym błędem bezwzględnym. Klatki czasowo skorelowane; wartości std nie są niezależnym oszacowaniem niepewności metrologicznej.
5. Subpixel pozostaje kandydatem rozwojowym: wyraźnie poprawia akceptację pomiarów czerwonego i zwykle zmniejsza bias względem integer dla obu pudełek w stanie OFF. Dla pomiaru precyzyjnego IR Dot nadal NIE ma bramki akceptacji.
6. Nie należy dopasowywać liniowego modelu korekty skali/offsetu wyłącznie do dwóch pudełek i używać czerwonego jako pozornej certyfikacji. Potrzebne niezależne sprawdziany w różnych pozycjach FOV, odmiennej powierzchni i geometrii, fizyczne pomiary wymiarów.
7. Testy powtarzalności na 16-sekundowych fazach nie zastępują długiego testu stabilności Camera Service + Perception.

## 6. Dane, repozytorium, produkcja

DEV:
- scripts/perception/capture_three_height_oak.py — kontrolowany single-owner pipeline zapisujący wyłącznie prywatne RAW16.
- scripts/perception/analyze_three_height_oak.py — niezależna analiza offline 3 obiektów, bez otwierania USB.
- tests/test_three_height_geometry.py — synteza 3 elementów, test bramki badawczej.

Dane prywatne na NVMe:
- /srv/vision-data/staging/oak-three-heights-private-20261113/subpixel_on/
- /srv/vision-data/staging/oak-three-heights-private-20261113/subpixel_off/
W każdym katalogu: capture_result.json, three_heights_aggregate.json, private three_heights_per_frame_private.json, 3 x frames.npz (RAW16, metadata), uprawnienia prywatne (mode 0600). Nie wolno publikować zdjęć, RAW16 i adresów sieciowych na GitHub.

Po obu sesjach Camera Service przywrócony automatycznie: prod ONLINE, USB SUPER, IR Dot OFF i Flood OFF (SDK ACK true/true). Wysokopoziomowe usługi Vision Core, robot NERO i STOP/E-STOP bez dotknięcia. Bez zmian w fabrycznej kalibracji, plikach produkcyjnych i main.

## 7. Następny etap

Przed poprawkami metrologicznymi: ręczna kontrola górnej powierzchni i dopasowania pod obiektami, walidacja parametrów rectified-left, test odtwarzania w kilku pozycjach pola widzenia oraz na sztywnych wzorcach. Rozważyć segmentację 2D top-face RGB dopiero PO potwierdzeniu transformacji RGB<->stereo, nie przez skalowanie współrzędnych pikseli. Bramka ±1 mm pozostaje FAIL, a ustawienia produkcyjne nie zmienione.
