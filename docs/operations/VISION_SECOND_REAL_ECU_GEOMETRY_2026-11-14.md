# Vision — drugie ECU: automatyczny obrys i najwyższe stabilne punkty 3D

**Data:** 2026-11-14. **Stan:** CAPTURE_PASS / ECU_DETECTED_25_OF_25 / PEAK_SCAN_PASS_EXPLORATORY / TOP_SURFACE_FAIL_23_OF_25 / PROD_RESTORED_PASS / NOT_ROBOT_READY.

## Cel i scena

Położono drugi fizyczny ECU na stole. W podglądzie RGB widać otwartą PCB z dwoma pionowymi (na obrazie) zespołami czarnych gniazd, po lewej i po prawej. Nie ma już planszy ChArUco ani pierwszego ECU. Nie wprowadzono nowych modeli AI, a operator nie podał jeszcze rzeczywistych wymiarów drugiego ECU.

**Uwaga:** określenia *lewe* i *prawe* złącze odnoszą się do oglądanego kadru. Nie istnieje jeszcze zweryfikowana transformacja do bazy NERO.

## Pomiar i niezmienione ustawienia

- Zebrano **25 rzeczywistych klatek depth RAW16 (1280×800)** z kamerą OAK-D Pro AF (DepthAI 3.12.0).
- Ta sama konfiguracja, co w pomiarze pierwszego ECU: stereo subpixel ON, rectification i LR-check ON, extended disparity OFF, IR Dot/Flood OFF; `K` pobrano z transformacji Depth.
- Wykorzystano **identyczną kopię skryptu** `analyze_ecu_scene.py` z pierwszego pomiaru, zmieniając tylko lokalizację plików nowej sesji; brak dopasowania algorytmu do oczekiwanego wymiaru.
- Skan najwyższych punktów opiera się na **tej samej metodzie analizy punktów wystających**, którą zastosowano przy pierwszym ECU: lokalna płaszczyzna stołu dopasowana RANSAC, mediana per-pixel z 25 map (wymagane co najmniej 20 ważnych klatek), filtr przestrzenny 5×5, spójne obszary wysokie i lokalne maksimum wraz z kamerowym XYZ. Nie jest to rozpoznawanie typów złączy przez sieć neuronową.
- Akwizycja: `CAPTURE_PASS` 25/25, RGB 372 packets, Depth 360 packets, 8 luk numeracji konsumenta, ważność RAW16 ~80,64% całego kadru. IR OFF ACK `True,True`. Oryginalny Camera Service przywrócony online/USB SuperSpeed.

## Wyniki obrysu — replay 25 klatek

| Parametr | Mediana | Odchylenie standardowe między klatkami | Akceptacja |
|---|---:|---:|---:|
| Widoczny rdzeń ECU — długość | **252,40 mm** | 2,263 mm | 25/25 |
| Widoczny rdzeń ECU — szerokość | **215,53 mm** | 2,156 mm | 25/25 |
| Globalna obwiednia wysokości P95 | 53,84 mm | 0,303 mm | 25/25 |
| Globalna obwiednia wysokości P99 | **57,92 mm** | 0,808 mm | 25/25 |
| Dotychczasowy `top_surface.py` — wysokość pojedynczej dominującej płaszczyzny | **NIE RAPORTOWAĆ JAKO POMIAR KORPUSU** (51,34 mm tylko w 2/25 klatek) | 0,161 mm tylko dla 2 klatek | **2/25 FAIL** |
| RMSE globalnej płaszczyzny stołu | 3,311 mm | 0,044 mm | 25/25 |

Automatycznie wykryty obrys Depth: mediana `[532,252,800,492]` w `rectified_left`. Obrys jest „rdzeniem” widzialnym przez stereo, więc może pomijać cienkie uszy montażowe i zasłonięte krawędzie.

## Mapa najwyższych stabilnych punktów

Skan wysokości całego ECU w ROI będącym poszerzeniem **automatycznie znalezionego obrysu** `[510,225,825,520]`. Lokalną płaszczyznę stołu dopasowano z wyłączeniem obszaru ECU. Mediana RMSE stołu: **2,382 mm**. Wymagano poprawnych pikseli w ≥20/25 klatkach i filtrowano przestrzennie medianą 5×5 przed analizą spójności wysokości.

| Element / lokalizacja na mapie depth | Najwyższy stabilny przefiltrowany punkt | Spójność / uwagi |
|---|---:|---|
| **Prawa listwa czarnych gniazd**, `u=720,v=409` | **65,28 mm** | Spójny region **35 px** powyżej 60 mm; lokalny piksel poprawny 25/25, mediana lokalnej wysokości 64,83 mm, std 1,78 mm |
| Inny szczyt **prawej** listwy, `u=716,v=441` | **63,06 mm** | Region 10 px >60 mm; 20/25 poprawnych klatek; std lokalnego piksela 3,35 mm, mniejsze zaufanie |
| **Lewa listwa czarnych gniazd**, `u=605,v=422` | **56,83 mm** | Spójny region 42 px >55 mm; 25/25 poprawnych klatek, mediana lokalnego piksela 57,62 mm, std 0,55 mm |
| Inne fragmenty gniazd i PCB | ~50–57 mm | Wiele odrębnych spójnych obszarów; nie najwyższy stabilny region |

**Pozycja najwyższego piksela prawej listwy (optyczny układ kamery):** `u=720,v=409` odpowiada szacunkowo `XYZ=[0,08121;0,02912;0,76100] m`. Nie jest to układ stołu ani podstawy NERO. Punkt ma przefiltrowaną wysokość nad stołem ~65,28 mm. Jego odczyt z nieprzefiltrowanego stałego piksela ma medianę 64,83 mm i międzyklatkową std 1,78 mm.

**WAŻNE:** globalny P99 **57,92 mm** pomija najwyżej położoną prawą listwę **65,28 mm** (różnica 7,36 mm). Algorytm lokalnych pików jest więc potrzebny do tworzenia mapy przeszkód.

### Ograniczenia

- Wysokości to pomiar **widocznych** punktów stereo; nie gwarantują fizycznie najwyższego punktu mechanicznego, szczególnie na błyszczących, czarnych, częściowo zasłoniętych krawędziach. Brak porównania do suwmiarki dla tego ECU.
- Wykrycie geometryczne ECU 25/25 to **nie identyfikacja modelu ECU** ani walidacja dokładności mechanicznej.
- Dla obecnej obudowy `top_surface` nie potrafi wiarygodnie wskazać pojedynczej dominującej powierzchni górnej (2/25); należy rozdzielić klasy powierzchni/wystających elementów, bez podawania wartości z dwóch klatek jako pewnych.
- Wartości `std` są zmiennością z klatek, a nie całkowitą niepewnością kalibracji.
- Eksperymentalna wartość `footprint_orientation_raw_deg` w prywatnym JSON nie jest miarą orientacji gotową do użycia: dotychczasowy skrypt błędnie stosuje `np.degrees()` do kąta `cv2.minAreaRect()` podanego już w stopniach. Nie używać pola do sterowania robotem; poprawę zostawić do oddzielnego zweryfikowanego PR.
- Robot NERO nie był sterowany. `metrology_verified=false`, `table_frame=UNAVAILABLE`, `robot_base_frame=UNAVAILABLE`, `safety_function=false`. Punktu 65,28 mm nie można bezpośrednio traktować jako zewnętrznej granicy bezpiecznej trajektorii — wymagane są zapas, ocena niepewności i niezależne zabezpieczenia.

**Surowe dane nie są commitowane.** Prywatna lokalizacja: `/srv/vision-data/staging/vision-ecu2-live-test-20261114` (RAW16, zdjęcia RGB, mapa peak depth, per-frame JSON, skrypty jednorazowe). Produkcja i kod main niezmienione.

**Kolejny etap:** fizyczny pomiar długości, szerokości i wysokości górnych krawędzi obu czarnych złączy względem stołu. Porównanie powinno pozostać niezależne od kodu estymatora.
