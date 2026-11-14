# Vision — oryginalne Luxonis Box Measurement, bez modyfikacji algorytmu

Data: 2026-11-14. Status: ORIGINAL_VENDOR_PIPELINE_PASS / SCENE_MEASUREMENT_UNVERIFIED / ORIGINAL_SOURCE_UNCHANGED / PRODUCTION_RESTORED_PASS.

## Cel

Na polecenie operatora wykonano próbę **100% oryginalnego przykładu Luxonis** (bez kodu Vision Perception, bez zmian w modelu, parametrach dopasowania, algorytmach segmentacji lub filtrach). Celem było sprawdzenie, czy producent dostarcza od razu pomiary trzech obiektów na stole: 34 mm, 50,4 mm i 101 mm.

Oficjalny upstream: https://github.com/luxonis/oak-examples/tree/main/depth-measurement/measurement-3d/box-measurement

Odtworzony upstream commit: `5c7c7d591e08613ee71012be35e565b4475a45af`, `main.py` SHA256 `ced1b68aba7b028a4391e0ff232eb652d90a20c8456a594895a9aa86ac99f8a2`. `git status --short` dla kodu upstream: czysty.

## Środowisko

Platforma: VENTUNO Q, ARM64 Ubuntu 24.04. Kamera: OAK-D Pro AF, RVC2, USB3 SuperSpeed. Specjalnie wydzielone lokalne Python venv; dokładne wersje z `requirements.txt` Luxonis:
- `depthai==3.11.0`
- `depthai-nodes==0.7.0`
- `numpy==1.26.4` (warunek producenta <2)
- `open3d==0.20.0`
- `opencv-python-headless==4.10.0.84`

Na ARM64 brakowało współdzielonego `libgfortran.so.5`; wydobyto oficjalną bibliotekę Ubuntu do izolowanego katalogu NVMe i podano jej ścieżkę wyłącznie w `LD_LIBRARY_PATH` uruchomienia. Nie zmieniano pakietów ani plików systemowych produkcji.

`depthai_models/box_instance_segmentation.RVC2.yaml` wskazuje model `luxonis/box-instance-segmentation:512x320`, załadowany przez **oryginalne** `dai.getModelFromZoo`. W kodzie producenta projektor IR Dot jest ustawiany na **1.0 (100%)**, kamera RGB i Depth na 640×400, `Depth.Algorithm.AUTO`, `RGBD`, inferencja na RVC2 (numShaves=7), `CuboidFitter` w hostowym `BoxProcessingNode` i wizualizacja `RemoteConnection` port 8082. Nie zmieniano żadnej z tych opcji.

## Próba sprzętowa

Dwukrotnie wykonano odizolowany, ograniczony czasowo start **niezmienionego `python -u main.py`**. Procedura otaczająca (nie zmieniająca kodu producenta) zatrzymywała pojedynczy produkcyjny Camera Service na czas próby, kończyła proces, wymuszała IR Dot i Flood OFF na wyjściu, ponownie uruchamiała produkcję i sprawdzała ONLINE/USB SUPER.

**Fakty zaobserwowane:**
- `Pipeline created` i `Pipeline started`, bez błędu wczytania modelu / brakujących bibliotek. W wersji RVC2 oficjalny parser YOLOExtendedParser działa na hoście, o czym informuje SDK.
- Oficjalny wizualizator Luxonis prezentował **rzeczywisty RGB z obecnej sceny i chmurę punktów**. Dowód: lokalny prywatny zrzut `vendor_visualizer_live_01.png`.
- Widoczna detekcja `Box 0.89`, ale narysowana maska obejmowała niemal cały obraz sceny, nie każdy z trzech fizycznych elementów osobno.
- Na zaobserwowanym widoku był tylko napis `Box 0.89` — **nie** `Box confidence L×W×H cm`. Zgodnie z oryginalnym kodem `BoxProcessingNode._draw_box_and_label`, drugi wariant jest prezentowany wyłącznie gdy `self.fit` jest true (lub gdy istnieje jeszcze aktualna cache ostatniego sukcesu). Podgląd nie dostarczył **żadnej wiarygodnej wartości wymiarów** dla pudełek 34 / 101 mm lub walca 50,4 mm.
- Oryginalny `main.py` nie wypisuje wartości wymiarów do stdout (`print('Dimensions')` w `box_processing_node.py` jest zakomentowany). Dlatego **nie można udawać pomiaru liczbowego** na podstawie samych logów, ani twierdzić, że żadne klatki w całej sesji nigdy nie miały fittingu. Zrzut dowodzi braku dopasowania w zarejestrowanym widoku.
- Na końcu ograniczonego testu `timeout` wysyła SIGINT, dlatego w logach pojawiają się oczekiwane `KeyboardInterrupt` i możliwe `MessageQueue was closed` przy zamykaniu, nie są dowodem błędu samego pomiaru podczas pracy.

**Wynik:** przykład producenta działa i uruchamia AI + stereo na tej kamerze, lecz jego **model carton box segmentation nie wydzielił prawidłowo naszych trzech przedmiotów**, więc nie otrzymano tabeli wiarygodnych wymiarów. Nie należy podawać fikcyjnych wartości ani utożsamiać napisu `Box 0.89` z pomiarem 89 mm.

## Zakończenie i stan

Dwa uruchomienia zakończono przez otaczającą procedurę, która **nie dotykała plików upstream**. Za drugim razem odnotowano `IR_OFF_ACK True True`, `PROD_START_RC=0`, `PRODUCTION_RESTORED_ONLINE_PASS`. Końcowy rzeczywisty odczyt produkcyjnej kamery: `online=True`, `usb=UsbSpeed.SUPER`, RGB ~30,0 FPS, depth ~29,3 FPS, `error=None`.

Brak zmian w plikach produkcyjnych, modelach Vision, NERO i `main`. Wszystkie prywatne dane i oba zrzuty wizualizatora są tylko na NVMe:
`/srv/vision-data/staging/luxonis-official-box-measurement-20261114`.

## Decyzja

Oryginalny gotowy przykład **nie zaliczył pomiaru naszej sceny** (brak wiarygodnej segmentacji trzech obiektów i wymiarów). Nie proponujemy kolejnych parametrów „na oko”. Taki wynik mówi o ograniczeniach **gotowego modelu do pudełek i konkretnej sceny**, a nie dowodzi, że stereo OAK nie może mierzyć wysokości elementów po prawidłowej segmentacji i kalibracji.
