# Vision — automatyczna segmentacja górnej powierzchni elementów

**Data:** 2026-11-13
**Gałąź:** `feature/perception-auto-top-face-20261113` (stacked na PR #25).
**Status:** TOP_SURFACE_SEGMENTATION_IMPLEMENTED / OFFLINE_REPLAY_PASS / 4_OF_18_RESEARCH_GATES_PASS / METROLOGY_NOT_VALIDATED / PROD_UNTOUCHED.

## Zakres

Nowy, niezależny od kamery moduł `scripts/perception/top_surface.py`, bez AI, Open3D, Vision Core i komend NERO. Jego wejściem jest RAW16 depth (mm), **rzeczywiste K dla rectified-left** i dwa ROI:
- zgrubny obrys CAŁEGO obiektu, dostarczany przez przyszły detektor obiektów; na tym etapie jest to uprzednio wybrany ROI,
- otoczenie obiektu używane do dopasowania lokalnej płaszczyzny stołu.

**Nie ma ręcznie wyznaczanego ROI górnej powierzchni**; wykrywana jest automatycznie wewnątrz ROI obiektu. Wartości 34 / 50,4 / 101 mm nie są używane przez segmentator, lecz tylko na etapie niezależnej kontroli QA.

Algorytm: lokalna RANSAC płaszczyzny stołu -> odległość prostopadła od stołu -> dominujący górny modalny poziom głębi -> przestrzennie spójna składowa/maska z uzupełnieniem otworów w samej segmentacji -> mediana rzeczywiście zarejestrowanych punktów wysokości. Nie interpoluje sztucznie XYZ do estymacji. Jakość: RMSE stołu, MAD/RMSE wysokości, liczba pikseli, spójność i odrzucenie niepewnych klatek.

Wynik w `perception.top_surface.v1`: lokalna maska binarna górnej powierzchni, bounding box w rectified-left, metryki. Jeśli `validity=NOT_READY`, `height_mm=null`, a wartość diagnostyczna może istnieć osobno jako `quality.candidate_height_mm`. Nawet poprawny pomiar jest oznaczony tylko `EXPLORATORY_UNVERIFIED_PROJECTION`; `robot_base_frame=UNAVAILABLE`, `metrology_verified=false`, `safety_function=false`.

Podejście wzorowane na Luxonis [BoxEstimator](https://github.com/luxonis/depthai/blob/main/depthai_sdk/src/depthai_sdk/classes/box_estimator.py), ale maskowanie górnej powierzchni jest nową, własną implementacją w Perception. Nie podmienia istniejących interfejsów Camera Service ani Perception Engine V1.

## Testy

- **49/49 PASS:** 6 nowych testów automatycznej segmentacji (syntetyczny prostokąt/cylinder, ubytki stereo, błędna konfiguracja, odrzucanie niestabilnego pomiaru) + 35 testów Camera Service + 8 testów Perception; `compileall` i `git diff --check` PASS.
- Replay na **150 wcześniej zapisanych mapach RAW16**: 2 tryby stereo, po 3 fazy OFF/DOT5/OFF, każda po 25 klatek; razem **450 analiz** po 3 obiekty. Urządzenie, USB, systemd, emitery IR i robot pozostawały nietknięte.
- Weryfikacja wzrokowa lokalnej maski na prywatnej mapie głębi: maska odpowiada górnej powierzchni dwóch pudełek i widocznej części czerwonego elementu. Obrazy i pliki RAW16 WYŁĄCZNIE na prywatnym NVMe.
- Dane referencyjne operatora: beżowe **34,0 mm**, czerwony cylinder **50,4 mm**, biało-czerwone pudełko **101,0 mm**. Nie są świadectwem metrologicznym.

### Wyniki (mediana tylko z klatek zaakceptowanych przez bramkę jakości)

| Stereo / faza | Beżowe 34 mm | Czerwone 50,4 mm | Biało-czerwone 101 mm |
|---|---:|---:|---:|
| Subpixel ON / IR OFF #1 | 33,403 (9/25) | 48,568 (17/25) | **100,489 (25/25)** |
| Subpixel ON / Dot5 | **34,869 (25/25)** | 47,164 (25/25) | **100,718 (25/25)** |
| Subpixel ON / IR OFF #2 | 32,806 (5/25) | 49,156 (15/25) | **100,359 (25/25)** |
| Subpixel OFF / IR OFF #1 | 32,248 (25/25) | 51,457 (8/25) | brak (0/25) |
| Subpixel OFF / Dot5 | 32,305 (25/25) | 51,731 (25/25) | brak (0/25) |
| Subpixel OFF / IR OFF #2 | 31,967 (25/25) | 51,505 (6/25) | brak (0/25) |

Udział `accepted` dotyczy tylko geometrii i lokalnej jakości, nie zgodności z wysokością referencyjną. **4/18 kompletów obiekt × faza przeszły wyłącznie bramkę badawczą**: bias mediany <= 1 mm, std <= 1 mm, >= 95% zaakceptowanych klatek, p05/p95 nie dalej niż 2 mm od referencji. Wszystkie 3 fazy Subpixel ON dla pudełka 101 mm; Dot5 dla beżowego 34 mm.

### Istotne ograniczenia

- **Mały czerwony cylinder nadal nie przechodzi** bramki ±1 mm i powtarzalności. IR Dot5 zwiększa pokrycie, ale zaniża medianę do 47,164 mm (bias −3,236 mm). Nie ma jednego offsetu dla wszystkich materiałów/obiektów.
- Subpixel OFF ma kwantyzację: dla pudełka 101 mm algorytm uzyskuje numeryczny kandydat, lecz odrzuca wszystkie 25 klatek w każdej fazie jako `UNSTABLE_TOP_SURFACE`. `height_mm` pozostaje `null`, nie wolno wykorzystywać kandydatów do ruchu robota.
- W fazach IR OFF / Subpixel ON beżowe i czerwone mają luki stereo i niepewne płaszczyzny: 9/25 i 17/25 w pierwszej fazie, 5/25 i 15/25 w ostatniej. Odmawianie pomiaru jest prawidłową reakcją fail-closed.
- Zdjęcia RGB nie są przekształcane „na oko” do depth; nie wykonano jeszcze RGB→rectified-left walidacji. Wstępny ROI całego obiektu pochodzi z poprzedniej ręcznej selekcji; **automatyczna detekcja ECU i identyfikacja top-face w RGB są następnymi osobnymi krokami.**
- To test na zapisach starego pipeline stereo (ON/OFF), **nie test metrologiczny produkcyjnego presetu Luxonis FAST_ACCURACY**. Stan fabrycznej kalibracji, table/robot_base i odtwarzanie po zimnym USB nadal niepotwierdzone.
- Brak podstaw do certyfikacji wymiarów, komend NERO i funkcji bezpieczeństwa na podstawie tych danych. Nie zalecamy dalszego strojenia IR na obecnym stanowisku.

## Reproducibility / repo

Kod wersjonowany:
- `scripts/perception/top_surface.py`
- `scripts/perception/replay_top_surface_three_heights.py`
- `tests/test_top_surface.py`
- ten raport.

Prywatny zapis testu: `/srv/vision-data/staging/vision-top-face-private-20261113` (agregaty, rekordy per-frame i prywatny podgląd maski, 0600), źródłowe dane `/srv/vision-data/staging/oak-three-heights-private-20261113`. Żadnych zdjęć/RAW16 w publicznym repozytorium.

**Decyzja:** Algorytm zachować w DEV jako autonomiczne maskowanie w obrębie ROI. Następna praca użyteczna dla Vision: uzyskać automatyczny wstępny ROI ECU z rozpoznawania sceny (nie zgadywać RGB→depth) i walidować go na docelowym montażu. Równolegle utrzymać profil jakości / brak wartości gdy niepewne.
