# Vision / OAK-D Pro AF — 100% oryginalny przykład Luxonis Box Measurement

**Data testu:** 2026-11-14
**Status:** ORIGINAL_VENDOR_PIPELINE_STARTED / LIVE_MODEL_DETECTION_WRONG / NO_VALID_CUBOID_DIMENSIONS / PROD_RESTORED_PASS.

## Cel

Sprawdzić działanie metody pomiaru brył Luxonis bez zastępowania modelu, progów ani algorytmów rozwiązaniami Vision. **To nie jest test własnego `top_surface` ani `height_planes`.**

## Źródło producenta (bez zmian)

Oficjalny projekt `luxonis/oak-examples`:
`depth-measurement/measurement-3d/box-measurement`.

- Commit źródła: `5c7c7d591e08613ee71012be35e565b4475a45af`.
- SHA-256 niezmienionego `main.py`: `ced1b68aba7b028a4391e0ff232eb652d90a20c8456a594895a9aa86ac99f8a2`.
- Uruchomienie: oryginalny `python -u main.py` w trybie `PERIPHERAL`, domyślne `fps_limit=10`; bez dodatkowych argumentów aplikacji.
- Wersje dokładnie według oryginalnego `requirements.txt`: `depthai==3.11.0`, `depthai-nodes==0.7.0`, `numpy<2` (zainstalowane 1.26.4), `open3d==0.20.0`, `opencv-python-headless==4.10.0.84`.
- Systemowa biblioteka `libgfortran5` pobrana z pakietu Ubuntu i rozpakowana WYŁĄCZNIE do katalogu testowego NVMe (`LD_LIBRARY_PATH`), bez globalnej instalacji i bez zmiany kodu producenta.
- Oryginalny model pobrany poprzez `dai.getModelFromZoo()`, `box_instance_segmentation.RVC2.yaml` → `luxonis/box-instance-segmentation:512x320`; cache wskazuje plik `yolov8n-carton_seg_balanced_synthetic_v2_background_512x320.rvc2.tar.xz`.
- Oryginalny `main.py` ustawia projektor IR Dot na `1.0` (100%). Nie jest to izolowany test oświetlenia widzialnego.
- Wykorzystano fabryczny `dai.node.Depth`, `dai.node.RGBD`, `ParsingNeuralNetwork`, hostowy `BoxProcessingNode` i oryginalny `CuboidFitter` z Open3D.

**Żadnych modyfikacji oryginalnego repozytorium** (`git status --porcelain` puste). Żadnego autorskiego ROI ani korekt znanych wymiarów w tym teście.

## Przebieg rzeczywisty

- Kamera OAK-D Pro AF / VENTUNO Q / USB SuperSpeed.
- Na stole leżały trzy znane elementy: pudełko 34,0 mm, czerwony element okrągły 50,4 mm, pudełko 101,0 mm; pozostawiona plansza ChArUco i dodatkowe oświetlenie.
- Przed testem sprawdzono `/healthz = OK`, USB3 i jednego właściciela urządzenia.
- Zewnętrzny skrypt obsługi sesji zatrzymywał produkcyjną usługę systemd, uruchamiał **niezmieniony `main.py`** w pojedynczej ograniczonej czasowo sesji (75 s), a następnie w `finally` przywracał IR Dot i Flood do zera oraz usługę. To zarządzanie testem, nie ingerencja w implementację Luxonis.
- **Dwa uruchomienia:** oba wypisały `Pipeline created.` i `Pipeline started.`. Konsola potwierdziła obsługę YOLOExtendedParser na RVC2, parser pracował na hoście.
- W drugim uruchomieniu otwarto oryginalny **OAK Visualizer 4.1.6** w przeglądarce na oddzielnym komputerze. Trzy prywatne screenshoty z kolejnych klatek pokazują ten sam rezultat: jeden ogromny prostokąt detekcji zajmujący niemal cały obraz i etykiety `Box 0.81`, `Box 0.79`, `Box 0.80`. Maska/obszar obejmuje większość stołu zamiast pojedynczych pudełek.
- Nie było wyświetlanych napisów z trzema wymiarami `L × W × H cm` dla żadnego z trzech wzorców; na podstawie oryginalnego `_draw_box_and_label()` oznacza to, że nie uzyskano stabilnego poprawnego dopasowania bryły (w kodzie `self.fit` / `dimensions_cache` decydują o wyświetleniu wymiarów).
- Na zakończenie ograniczonego testu wyemitowano sygnał SIGINT. Zamknięcie kolejki podczas tego procesu spowodowało pojedynczy `MessageQueue was closed` i `KeyboardInterrupt`; są to logi shutdown, nie udokumentowane przyczyny niepowodzenia pomiarów.

## Wynik

| Fizyczny wzorzec | Wysokość deklarowana | Oryginalny Luxonis Box Measurement |
|---|---:|---|
| Beżowe pudełko | 34,0 mm | Brak poprawnych wymiarów |
| Czerwony element okrągły | 50,4 mm | Brak poprawnych wymiarów |
| Biało-czerwone pudełko | 101,0 mm | Brak poprawnych wymiarów |

**Wniosek:** Na bieżącej scenie oryginalny, niezmodyfikowany przykład Luxonis uruchamia akwizycję i model AI, ale **nie daje prawidłowego pomiaru** żadnego z trzech wzorców. Gotowy model do kartonów klasyfikuje niemal całe pole widzenia jako `Box`. Brak podstaw do prezentowania własnych wyników Vision jako wyników producenta lub do wyznaczania błędu wysokości na tej podstawie.

Luxonis w oficjalnym README ostrzega o niestabilności dopasowań `CuboidFitter`, szczególnie dla RVC2, a kod nie jest uniwersalnym miernikiem wysokości dowolnych elementów i ECU. Próba testowała *dokładnie ten przykład*, przy scenie warsztatowej z trzema elementami i planszą. Osobna próba na pojedynczym, odizolowanym kartonie byłaby bardziej miarodajna dla demonstracji, ale **nie została przeprowadzona** i nie wolno zgadywać jej wyniku.

## Stan końcowy i prywatność

- Po każdej sesji `IR_OFF_ACK True True`, Camera Service restored ONLINE, USB SUPER.
- Ostatnia niezależna kontrola: RGB 30,1 FPS, depth 29,2 FPS, `error=null`, `NRestarts=0`.
- Zero zmian do `main`, produkcyjnego Camera Service, Vision Core, NERO czy EEPROM.
- Kod producenta i logi lokalnie: `/srv/vision-data/staging/luxonis-official-box-measurement-20261114/`.
- Trzy screenshoty OAK Visualizer **wyłącznie na prywatnym hoście AI Platform**: `/home/harrypotter/snap/firefox/common/vision-vendor/official_vendor_{0,1,2}.png`, nie publikowane na GitHub.

**Oficjalne źródła:**
- https://github.com/luxonis/oak-examples/tree/main/depth-measurement/measurement-3d/box-measurement
- https://github.com/luxonis/oak-examples/blob/main/depth-measurement/measurement-3d/box-measurement/utils/box_processing_node.py
- https://github.com/luxonis/oak-examples/blob/main/depth-measurement/measurement-3d/box-measurement/utils/cuboid_fitter.py
