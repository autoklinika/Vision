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

- Wysokości to pomiar **widocznych** punktów stereo; nie gwarantują fizycznie najwyższego punktu mechanicznego, szczególnie na błyszczących, czarnych, częściowo zasłoniętych krawędziach. Fizyczną wysokość maksymalną całego ECU operator podał później jako 75 mm; porównanie opisano w uzupełnieniu poniżej.
- Wykrycie geometryczne ECU 25/25 to **nie identyfikacja modelu ECU** ani walidacja dokładności mechanicznej.
- Dla obecnej obudowy `top_surface` nie potrafi wiarygodnie wskazać pojedynczej dominującej powierzchni górnej (2/25); należy rozdzielić klasy powierzchni/wystających elementów, bez podawania wartości z dwóch klatek jako pewnych.
- Wartości `std` są zmiennością z klatek, a nie całkowitą niepewnością kalibracji.
- Eksperymentalna wartość `footprint_orientation_raw_deg` w prywatnym JSON nie jest miarą orientacji gotową do użycia: dotychczasowy skrypt błędnie stosuje `np.degrees()` do kąta `cv2.minAreaRect()` podanego już w stopniach. Nie używać pola do sterowania robotem; poprawę zostawić do oddzielnego zweryfikowanego PR.
- Robot NERO nie był sterowany. `metrology_verified=false`, `table_frame=UNAVAILABLE`, `robot_base_frame=UNAVAILABLE`, `safety_function=false`. Punktu 65,28 mm nie można bezpośrednio traktować jako zewnętrznej granicy bezpiecznej trajektorii — wymagane są zapas, ocena niepewności i niezależne zabezpieczenia.

**Surowe dane nie są commitowane.** Prywatna lokalizacja: `/srv/vision-data/staging/vision-ecu2-live-test-20261114` (RAW16, zdjęcia RGB, mapa peak depth, per-frame JSON, skrypty jednorazowe). Produkcja i kod main niezmienione.

**Kolejny etap:** fizyczny pomiar długości, szerokości i wysokości górnych krawędzi obu czarnych złączy względem stołu. Porównanie powinno pozostać niezależne od kodu estymatora.

## Fizyczna weryfikacja najwyższego punktu — 14.11.2026

Operator zmierzył rzeczywisty **najwyższy punkt całego drugiego ECU = 75,00 mm nad stołem**. Nie wskazano jeszcze, z którym konkretnie punktem obiektu/pikselem kamera ma tę wysokość zestawić; nie wolno automatycznie uznawać, że fizyczny szczyt i wyszukany szczyt głębi `u=720,v=409` są tą samą krawędzią.

| Wartość | Wysokość |
|---|---:|
| Fizyczna maksymalna wysokość ECU (referencja operatora) | **75,00 mm** |
| Najwyższy stabilny szczyt znaleziony przez Vision na mapie głębi | **65,28 mm** |
| **Różnica: wynik Vision − rzeczywista najwyższa wysokość ECU** | **−9,72 mm** |
| Globalny P99 (niepoprawny jako granica przeszkody) | 57,92 mm |

**Bramka bezpieczeństwa: NIEZALICZONA.** Aktualny algorytm znajdowania szczytów zaniżył rzeczywistą maksymalną wysokość ECU o co najmniej wartość wynikającą z tego porównania, jeśli oba szczyty uznać za reprezentację tej samej wielkości. Nie jest znana całkowita maksymalna niepewność pomiaru ani ryzyko pomijania innych zasłoniętych fragmentów; nie wolno użyć wyniku 65,28 mm jako samodzielnej granicy planowania bezkolizyjnego NERO.

**Diagnoza pozostaje otwarta**: (a) kamera widzi niewłaściwą / niższą powierzchnię niż rzeczywista krawędź, (b) ubytek stereo na ciemnej lub odbijającej powierzchni, (c) niepewność kalibracji geometrycznej. Różnica nie dowodzi błędu samej skali głębi; nie wprowadzać bez dowodów globalnego offsetu +9,72 mm ani poprawki do parametrów kamery.

Operator nie podał jeszcze fizycznej długości/szerokości ani odrębnych wysokości obu listew złączy. **Następny sensowny test** to wskazać na obrazie fizycznie najwyższy punkt (lub porównać z przyłożonym wzorcem wysokości), a następnie sprawdzić, czy widać go w RGB, stereo i chmurze punktów. Robot NERO nie został użyty.

## Audyt surowej głębi na krawędziach złączy — 14.11.2026

Na polecenie operatora przeanalizowano **oryginalne 25 klatek RAW16 drugiego ECU** (`light_on_subpixel_on_ir_off_frames.npz`), bez nowej akwizycji, zmian ustawień kamery, zmian w programie produkcyjnym ani zmian parametrów stereowizji. Cel: ustalić, czy kamera w ogóle rejestruje najwyższe krawędzie na wysokości fizycznej 75 mm i czy to nasz filtr je usuwa. Użyto lokalnej płaszczyzny stołu RANSAC jak we wcześniejszym raporcie, zgodnej macierzy `K` oraz niezależnych obszarów lewej/prawej listwy czarnych złączy w **układzie rectified-left depth**, a nie w niezweryfikowanym RGB.

| Obszar | Najwyższy punkt mediany 25 klatek RAW (min. 20 ważnych) | Klatki ważne w tym pikselu | Odchylenie między klatkami | Maksimum po medianie przestrzennej 5×5 |
|---|---:|---:|---:|---:|
| Lewe czarne złącza, punkt `u=634,v=333` | **76,61 mm** | 24/25 (powyżej 75 mm w 21 klatkach) | 1,37 mm | **56,83 mm** (maksimum całej listwy po filtracji; w samym pikselu 0) |
| Prawe czarne złącza, punkt `u=722,v=410` | **74,99 mm** | 25/25 (powyżej 70 mm w 25 klatkach) | 1,06 mm | **65,28 mm** (maksimum całej listwy po filtracji) |
| Fizyczne maksimum ECU | **75,00 mm** | referencja operatora | — | — |

**Dowód utraty wysokich pikseli:** w pełnym obszarze ECU mediana surowych punktów (czasowa z warunkiem ≥20/25 ważnych klatek) zawiera **25 pikseli z wysokością ≥70 mm**, zgrupowanych m.in. w wydłużone obszary prawej (`2×7 px`) i lewej (`2×7 px`) listwy. Mediana przestrzenna **5×5 eliminuje wszystkie te piksele**, pozostawiając **0 pikseli ≥70 mm**. Surowy punkt 76,61 mm na lewym złączu ma tylko niewielkie sąsiedztwo podobnie wysokich pikseli i sam po tej filtracji znika.

Szczegółowe liczby na klatkę (w obrębie lewych/prawych gniazd):
- Lewe: surowych pikseli ≥70 mm jest medianowo **71/klatkę** (zakres 48–89), ≥75 mm **20/klatkę** (6–35). Mediana po czasie wskazuje 12 punktów ≥70 mm i 2 ≥75 mm. Po przestrzennej medianie 5×5 żadnego ≥70 mm.
- Prawe: surowych pikseli ≥70 mm medianowo **32/klatkę** (19–47), ≥75 mm 4/klatkę (0–11). Mediana po czasie wskazuje 13 punktów ≥70 mm; po przestrzennej medianie 5×5 żadnego ≥70 mm.

**Zaktualizowana diagnoza:** wcześniejsza różnica `65,28−75,00=−9,72 mm` dotyczy **wyniku naszego przetwarzania**, a nie dowodzi, że sama kamera nie potrafi widzieć punktów w okolicy 75 mm. Największa udowodniona przyczyna: filtr medianowy przestrzenny 5×5 **niszczy wąskie, lecz powtarzalne górne krawędzie złączy**. Brak gwarancji, że pojedyncze punkty RAW są dokładnymi mechanicznymi wierzchołkami — mogą obejmować artefakty na krawędziach stereo; zgodność ~75 mm jest obiecująca, ale nadal wymaga walidacji na niezależnych wzorcach.

**Zalecenie dla nowej wersji Perception, bez wdrażania w tym teście:** oddzielić usuwanie szumu od zachowania ciągłych wąskich krawędzi; traktować *czasową powtarzalność punktów i niewielką spójną strukturę* jako sygnał zachowania lokalnego szczytu; nie używać globalnego P99 ani mediany 5×5 do wyznaczania maksymalnego pułapu przeszkody. Wycena i ocena niepewności oraz ręczna walidacja powinny być niezależne od algorytmu. Każdy ruch NERO nadal zablokowany do etapu kalibracji i bezpieczeństwa.

**Dowody prywatne na NVMe:** `/srv/vision-data/staging/vision-ecu2-live-test-20261114/raw_connector_edge_audit_private.json`, `raw_ecu2_heights_temporal_no_spatial_filter.png`, `audit_raw_connector_edges.py` i oryginalny RAW16. Nie commitować danych zdjęciowych ani surowych map głębi.
