# Vision / OAK-D Pro AF — oficjalne profile Luxonis DepthAI v3

**Data:** 2026-11-13. **Stan:** SDK_PROFILE_INTEGRATED / SHORT_HARDWARE_PASS / PRODUCTION_RESTORED_PASS; gałąź oparta na PR #23, bez deploymentu i bez merge do main.

## Decyzja techniczna

Zamiast ręcznego strojenia subpixel / extended disparity / filtrów / IR przechodzimy na gotowe presety `dai.node.StereoDepth.PresetMode` w DepthAI 3.12.0 na RVC2 (OAK-D Pro AF). Zachowujemy architekturę: Camera Service -> wersjonowany RAW16 depth + RGB -> Perception. Vision Core i NERO pozostają poza zakresem; kamera **nie jest certyfikowanym zabezpieczeniem** NERO.

| Profil aplikacji | Preset Luxonis | Przeznaczenie | Rozdzielczość depth |
|---|---|---|---|
| balanced | FAST_ACCURACY | geometria statycznego ECU | pełna wejściowa (800p) |
| detail | FAST_ACCURACY | RGB 4K, geometria ECU | pełna wejściowa (800p) |
| near | HIGH_DETAIL | detale i bliski zasięg | domyślnie 1/2 (400p) |
| robotics | ROBOTICS | obserwacja zmian i przeszkód (nie safety) | domyślnie 1/2 (400p) |

**Uwaga:** `FAST_ACCURACY` jest oznaczony w najnowszej dokumentacji jako deprecated, ale SDK 3.12.0 na VENTUNO Q udostępnia ten wariant dla RVC2. Nie zastępujemy go niezweryfikowanym `ACCURACY` dla RVC4. Profil i wersję SDK należy jawnie utrzymać do migracji.

## Inwarianty kamery / Perception

- Za wybór filtra, subpixel, extended disparity i decymacji odpowiada fabryczny preset; po jego ustawieniu wymuszamy jedynie `RECTIFIED_LEFT`, rektyfikację i LR check.
- Rozmiar RAW16 i macierz intrinsics `K` są pobierane z **rzeczywistego ImgFrame**. W szczególności `HIGH_DETAIL` i `ROBOTICS` nie mogą używać `K` skopiowanego z 1280×800.
- Fabryczne EEPROM/camera calibration są odczytywane bez zapisu. `RGB` nie jest równoznaczny z `stereo_left_rectified_optical`; nie tworzymy fałszywej transformacji XYZ do NERO.
- `Sync` i `ImageAlign` są dostępne w SDK. Obecny hostowy `RgbdSynchronizer` pozostaje, ponieważ ma już sprawdzony kontrakt i zbiera dane o dropach. Native `ImageAlign` do RGB uruchomimy dopiero jako osobny strumień, gdy będzie potrzebny do dopasowania ROI rozpoznanego ECU; nie wolno podmieniać nim cicho istniejących danych rectified-left.
- `SpatialLocationCalculator` oblicza XYZ tylko dla wskazanego ROI; nie rozpoznaje ECU, nie estymuje jego orientacji i nie daje transformacji do układu robota. Powinien otrzymywać ROI z Perception, gdy segmentacja ECU będzie gotowa.
- Zostaje znana blokada: położenie `table` i `robot_base` = UNAVAILABLE, safety_function = false, metrologia 50,4 mm niezweryfikowana.

## Dlaczego przerywamy testy ustawień IR

PR #23 udokumentował porównania OFF/DOT 5/10/15%: większy udział prawidłowych pikseli nie zapewnił prawidłowej wysokości ROI. Obecny percentyl p75 miesza górną powierzchnię obiektu z bokami i tłem. Nie powtarzamy tych prób. Własny etap Perception: segmentacja ECU i osobna estymacja płaszczyzny górnej względem stołu.

## Gate i wykonanie (13.11.2026)

1. **PASS 43/43**: 35 testów Camera Service (w tym mapowanie presetów i reguły transformacji/K) + 8 testów Perception. Testy bez fizycznego otwierania USB.
2. **PASS jeden krótki smoke sprzętowy `balanced` / Luxonis `FAST_ACCURACY`**: podgląd RGB mediana 30,25 FPS, depth 29,4 FPS, 266 sparowanych RGB-D; RAW16 uint16 **1280×800**, `sync_state=SYNCED`, macierz K z rzeczywistego `ImgFrame` o rozdzielczości 1280×800. W Replay Perception: 50 700 próbek XYZ, płaszczyzna wykryta (RMSE ~3,87 mm), 8 obszarów `unknown`; bez deklarowania klasy ECU ani robot_base.
3. **PASS przywrócenie produkcji**: test wymagał chwilowego zatrzymania user-systemd Camera Service i automatycznego wznowienia w `finally`; po ustabilizowaniu: ONLINE, USB SUPER, RGB 30,1 FPS / depth 29,1 FPS, brak bieżących błędów. Produkcyjne pliki oraz `main` bez zmian.
4. Test był tylko uruchomieniem profilu, **nie** sweepem IR; użyto trybu `survey` z IR OFF. Zakresy `HIGH_DETAIL`/`ROBOTICS` są skonfigurowane według producenta, ale **nie** mają własnej bramki hardware PASS.
5. **PENDING przed robotyką:** dopiero montaż na docelowym stanowisku, ustawienie i weryfikacja układu table/robot_base, sensowna segmentacja ECU oraz wyjaśnienie incydentu USB3 i dłuższy test stabilności. Nie powtarzamy metrologii 50,4 mm na obecnym estimatorze p75.

Pierwsze uruchomienie harnessu nie weszło w test kamery z powodu brakującej ścieżki importu Perception; produkcja została przywrócona. Naprawiono import w `controlled_optics_smoke.py` i **następny, pojedynczy** hardware smoke przeszedł PASS. Dane testowe zostały lokalnie na NVMe; repo zawiera wyłącznie agregaty.

**Rozgraniczenie:** hardware PASS oznacza poprawne uruchomienie i kontrakt RGB-D dla `FAST_ACCURACY`, nie dokładność XYZ na wzorcu, brak błędów USB po zimnym starcie ani gotowość sterowania NERO.

Źródła producenta:
- https://docs.luxonis.com/software-v3/depthai/depthai-components/nodes/stereo_depth
- https://docs.luxonis.com/hardware/platform/depth/configuring-stereo-depth
- https://docs.luxonis.com/software-v3/depthai/depthai-components/nodes/image_align
- https://docs.luxonis.com/software-v3/depthai/examples/spatial_location_calculator/spatial_location_calculator/
