# SCN-001 — ETC3: pierwsza sesja Vision (offline-first)

**Status:** `DRAFT / DESIGN_ONLY / NO_REAL_ROBOT_MOTION`  
**Data rozpoczęcia:** 14.11.2026  
**Cel:** sprawdzić pełny przebieg nowego Vision na **ETC3 z dwoma czarnymi i jednym szarym złączem** przy użyciu istniejących danych testowych, bez migracji historycznego kodu i bez sterowania rzeczywistym NERO.  
**Podstawa:** [Vision Foundation](../architecture/VISION_FOUNDATION_2026-11-14.md)  
**Profil:** [ETC3_INITIAL_PROFILE_2026-11-14.md](../ecu/ETC3_INITIAL_PROFILE_2026-11-14.md)  
**Wejście:** pierwszy ECU badany 14.11.2026, a **nie** drugi ECU o maks. wysokości 75 mm i **nie** DAF SAC.

> To projekt scenariusza i kryteriów jego testowania; **nie** zapis przeprowadzonej sesji nowego Vision ani zatwierdzony plan ruchu. ROS 2, MoveIt i Luxonis ROS mają status uzależniony od testów sprzętowych. Nie uruchamiać napędów na podstawie tego dokumentu.

## 1. Dlaczego właśnie taki scenariusz?

Celem SCN-001 nie jest rozpoznawanie nieznanego ECU, trenowanie modelu, montaż aparatu ani tworzenie kompletnego HMI. Chcemy sprawdzić podstawową tezę nowego Vision: **operator deklaruje ETC3 → Vision pobiera profil → weryfikuje zgodność i geometrię z zarejestrowanej sceny → przygotowuje plan inspekcji → symuluje przebieg → ocenia i archiwizuje rezultaty**.

Pierwsza sesja ma być odtwarzalna, bez skutków na fizycznym sprzęcie, i modułowa — podmiana modelu detekcji lub adaptera kamery nie może wymagać przeróbki Vision Workflow.

### Minimalny zakres `SCN-001-A` (pierwszy kamień milowy)

- Operator wybiera **ETC3**, wersję profilu i sesję danych ECU1.
- Odtwarzamy **zapisane** RGB/RAW16 z pierwszego ECU; nie inicjalizujemy fizycznej kamery.
- Vision ocenia: czy obserwowana geometria i układ trzech złączy **nie przeczą** deklaracji ETC3; jeśli niepewność duża, prosi o zatwierdzenie.
- Obiekt dostaje pozycję i orientację **tylko we właściwej ramie optycznej**, dopóki nie ma zwalidowanego `table → robot_base`.
- Weryfikujemy konserwatywną obwiednię kolizyjną w modelu offline; nie ogłaszamy `SAFE_TO_MOVE`.
- Budujemy **wirtualny** plan inspekcji PCB/obszaru złączy, bez ruchu NERO.
- Wywołujemy atrapę fotograficzną (lub analizujemy wcześniej zapisane obrazy, o ile istnieją), generujemy wyniki z flagami jakości i manifest sesji.
- Opcjonalna analiza AI na tym etapie ma być **mockiem**; nie wymagamy modeli ECU ani GPU.

### Odrębna przyszła faza `SCN-001-B`

Dopiero po przejściu bramek: aktywacja prawdziwych adapterów ROS/Sony, kalibracja całości, pełny model kolizji i niezależne zabezpieczenia oraz osobna zgoda operatora na kontrolowaną próbę ruchu. Nie mieszać wyników faz A i B.

## 2. Wymagane dane początkowe i ich jakość

| Parametr | Dane dostępne obecnie | Ograniczenie |
| --- | --- | --- |
| ECU | ETC3, pierwszy ECU z 14.11 | Nazwa/rewizja deklarowana przez operatora |
| Obiekt | Otwarte ECU, PCB; złącza czarne–szare–czarne | Orientacja dotyczy widoku referencyjnego, nie osi robota |
| Fizyczna maks. wysokość | **65 mm** po korekcie operatora | Wstępna wartość profilu, bez niezależnego potwierdzenia obwiedni |
| Obrys z DepthAI | **274,2 × 224,1 mm**, mediana 25 obserwacji | Nie jest to zweryfikowany wymiar fizyczny |
| Dominująca wysokość / P99 | 24,9 / 51,3 mm | P99 **nie reprezentuje** najważniejszego prześwitu |
| Najwyższy lokalny fragment | ok. 62,9 mm; filtrowane ok. 63,9 mm | Wrażliwość na segmentację i ustawienia głębi |
| Klasyfikacja obiektu | Jeszcze brak zatwierdzonego modelu AI | Weryfikacja wizualna/geometryczna, może wymagać operatora |
| Pozycja ECU względem robota | Brak | **Blokada rzeczywistego ruchu** |
| Rzeczywisty model adaptera J7 / Sony / Luxonis | Niezweryfikowany w planowaniu MoveIt | Nie planować rzeczywistego ruchu |
| ROS v3 z fizycznym OAK | Test 14.11: brak strumienia w kontenerze | W `SCN-001-A` dane wyłącznie z replay |
| Surowa mapa MoveIt / OctoMap | Z ECU1 także fałszywe voxele do ok. 122–125 mm | Nie stosować surowej mapy jako jedynej prawdy geometrycznej |

Źródła: zapisane dane z pomiarów 14.11 na prywatnym NVMe oraz [PR #27 — audyt ROS 2 / MoveIt 2](https://github.com/autoklinika/Vision/pull/27). Zadanie odczytu danych testowych nie może umożliwiać jednoczesnej pracy fizycznego sterownika kamery i prototypu replay na tym samym USB.

## 3. Przebieg SCN-001-A: kroki, moduły i warunki

| Krok | Moduł odpowiedzialny | Wejście → wyjście | Błąd / zatrzymanie |
| --- | --- | --- | --- |
| 00. `IDLE` | Vision Workflow / HMI | Rozpocznij sesję offline | Nie uruchamia napędów |
| 01. `ECU_DECLARED` | HMI → ECU Catalog | Operator wskazuje ETC3 + wersję → `ECUProfile.v1` | Brak profilu → `BLOCKED` |
| 02. `DATA_LOADED` | Camera Adapter: Replay | Zapisane RGB/RAW16 + metadane → standardowe `sensor_msgs/Image`, `CameraInfo`, ramy i znaczniki czasu | Brak kalibracji / niespójne pary → `NOT_READY` |
| 03. `SCENE_OBSERVED` | Scene Verification | RGB-D + profil → obiekt, obrys, obraz trzech złączy, dane geometryczne, jakość | Niepewne ROI/głębia → `REVIEW_REQUIRED` |
| 04. `ECU_VERIFIED` | Workflow / HMI | Porównanie z ETC3 → zgodne / niezgodne / niepewne | Inny ECU albo nierozpoznane złącza → zatrzymaj i poproś operatora |
| 05. `GEOMETRY_ASSESSED` | Scene Verification + tf2 | `SceneObservation.v1`, maski, wysokie złącza, obwiednia z profilu | Błędne/outlier voxele nie mogą być traktowane jako precyzyjna kalibracja |
| 06. `PLAN_DRAFTED` | Motion Gateway + MoveIt 2 *offline/fake* | Propozycje pozycji fotograficznych / trajectory preview w RViz | Bez `table→robot_base` → `PLAN_UNCALIBRATED`, bez możliwości wykonania |
| 07. `CAPTURE_SIMULATED` | Camera Adapter: Sony Mock | Lista wirtualnych ujęć → `CaptureResult.v1` z `simulated=true` | Brak rzeczywistego zdjęcia ≠ PASS jakości fotografii |
| 08. `QUALITY_CHECKED` | Image Quality | Dane zapisane lub mock → ocena ostrości/ekspozycji/kompletności, jeśli realne zdjęcia dostępne | Brak materiału → `NOT_TESTED`, nie „zaliczone” |
| 09. `AI_OPTIONAL` | AI Bridge: Mock | Przykładowe żądanie → wynik syntetyczny oznaczony `mocked` | AI niedostępne nie blokuje bazowego przepływu |
| 10. `ARCHIVED` | Session Storage | Wersja profilu, provenance, identyfikatory obrazów, stany i manifest | Brak zapisu/haszy → `INCOMPLETE` |
| 11. `DONE_OFFLINE` | Vision Workflow / HMI | Raport i lista nierozwiązanych bramek | Nigdy `MOTION_APPROVED` w fazie A |

W każdej fazie komunikaty muszą rozróżniać `PASS`, `FAIL`, `NOT_READY`, `NOT_TESTED`, `MOCKED`, `REVIEW_REQUIRED`. `DONE_OFFLINE` znaczy, że przebieg przetestowano bez sprzętu; **nie** oznacza gotowości do automatycznej inspekcji fizycznej.

## 4. Pierwszy plan inspekcji ETC3

Nie znamy jeszcze wszystkich wymaganych obszarów PCB, numerów elementów i dokładnych transformacji. Dlatego na początek stosujemy **plan logiczny w układzie ECU**, a nie listę kątów przegubów:

1. **Widok globalny** — całe otwarte ETC3 i trzy złącza; potwierdzenie profilu oraz zorientowanie obiektu.
2. **Rząd złączy** — lewy czarny, środkowy szary, prawy czarny; sprawdzenie ich obecności, obrysu i najwyższych punktów.
3. **Cała dostępna PCB** — pokrycie obrazu, identyfikacja fragmentów niewidocznych w pierwszym ujęciu.
4. **Ujęcia szczegółowe** — dopiero na podstawie późniejszych danych profilu, nie wymyślamy listy elementów.
5. **Wyniki** — zapis oczekiwanych `CaptureRequest.v1`, pozycji teoretycznych, statusów jakości i zdjęć (jeśli są).

Dla pierwszej próby dość czterech *typów obserwacji*; liczba ujęć, czasy ekspozycji, wymagania ostrości i pozycje J1–J7 pozostają **TBD**, zależnie od docelowego układu i kalibracji. Nie generujemy trajektorii robotycznych z samych 274,2×224,1 mm i 65 mm.

## 5. Kontrakty między modułami

Zamiast wiązać logikę z nazwą sterownika czy modelu:

- `ECUProfile.v1`: family, variant, revision, physical_envelope, reference_features, plan_id, provenance.
- `SceneObservation.v1`: object_pose, frame_id, stamp, ROI, `CameraInfo`/kalibracja, wysokość i jej wiarygodność, złącza, `validity`, `uncertainty`.
- `VerificationResult.v1`: `MATCH`, `MISMATCH`, `REVIEW_REQUIRED`; cechy wspierające decyzję i wersja algorytmu.
- `MotionRequest.v1`: zadanie, numer sceny, docelowe położenia, narzędzie i ograniczenia; w fazie A **tylko podgląd** bez `execute`.
- `CaptureRequest.v1` / `CaptureResult.v1`: typ ujęcia, urządzenie abstrakcyjne, stan, identyfikator obrazu/artefaktu, jakość, czy `mocked`.
- `InspectionResult.v1`: wyniki, błędy, oryginały, wersja profilu i kalibracji, wyniki jakości, wersje modeli AI, manifest hash.

Wszystkie powyższe nazwy to propozycje kontraktów semantycznych, **nie powielamy** standardowych wiadomości ROS 2, gdzie już istnieją (obrazy, point cloud, transformacje, stany robota, akcje). Używamy adapterów: `ReplayRGBDAdapter`, `LuxonisROSAdapter`, `SonyMockAdapter`, `SonyPTPAdapter`, `AIPlatformRMAdapter`. Ich zmiana nie może modyfikować state machine Workflow.

## 6. Stany i zasady `fail closed`

```text
IDLE
  → ECU_DECLARED
  → DATA_LOADED
  → SCENE_OBSERVED
  → [ECU_VERIFIED | REVIEW_REQUIRED | MISMATCH]
  → GEOMETRY_ASSESSED
  → PLAN_DRAFTED (offline)
  → CAPTURE_SIMULATED
  → QUALITY_CHECKED
  → AI_OPTIONAL
  → ARCHIVED
  → DONE_OFFLINE
```

- Każdy `MISMATCH` lub błąd profilu zatrzymuje przebieg automatyczny.
- Każdy `NOT_READY` geometrii lub brak transformacji blokuje **wykonanie** trajektorii i może pozwalać jedynie na nieszkodliwy podgląd.
- Nie podmieniamy niepewnych wyników z kamery na profil nominalny jako gwarancję bezpieczeństwa.
- Fałszywy voxel powyżej obwiedni: rejestrujemy jako konflikt danych/niepewność, nie usuwamy go automatycznie w celu „zaliczenia” testu. Niepewne lub nieobserwowane obszary sceny pozostają przeszkodą/zakazem ruchu dla docelowej wersji.
- AI, UI, dostęp do Minisforum ani ROS 2 nie mogą obejść sprzętowych zabezpieczeń.
- Dane `MOCKED` lub `REPLAY` w manifestach muszą być jawnie odróżnione od pomiarów nowego systemu na żywo.

## 7. Kryteria ukończenia SCN-001-A

| Bramka | Kryterium | Obecnie |
| --- | --- | --- |
| A1 Profil ETC3 | Odczyt deklaracji, komplet provenance, kontrola braku wymaganych nieznanych pól | Specyfikacja utworzona; kod jeszcze nie istnieje |
| A2 Replay | Powtarzalne otwarcie danych **właściwego ECU1**, synchronizacja i raport złych ramek | Historyczne RAW16 istnieją, nowy adapter nie napisany |
| A3 Weryfikacja ECU | `MATCH`/ `REVIEW_REQUIRED` dla ETC3, `MISMATCH` lub brak automatycznej zgody dla innego ECU | Do implementacji i testów |
| A4 Scena | Raport wysokich złączy oraz jakości bez przeoczeń i fałszywej dokładności | Testy MoveIt historycznie PASS tylko jako import PointCloud; geometria FAIL |
| A5 Plan offline | Model NERO + narzędzie; brak komendy rzeczywistego ruchu i jawny błąd brakującego TF | Do wykonania |
| A6 Akwizycja mock | Ujęcia logiczne bez migawki Sony | Do wykonania |
| A7 Session Store | Zapis wersji profilu, danych wejściowych, statusów, manifestów i wyników | Do wykonania |
| A8 Błędy i recovery | Nieprawidłowy profil, niedostępna klatka, brak kalibracji, niepewność i odmowa ruchu kończą się przewidywalnie | Do testów |

**Sukces etapu A** to pełny przebieg `DONE_OFFLINE`, bez aktywowania fizycznego NERO/kamery; nie jest nim „ładna wizualizacja” lub samo powstanie chmury punktów.

## 8. Następne zadania programistyczne (osobne PR)

1. **Kontrakt i profil:** walidowany schema `ECUProfile.v1` i przykładowy profil ETC3; testy braków, niepewności i wersjonowania.
2. **Dane testowe / replay:** kontrolowany interfejs do wcześniej zapisanych `RGB + RAW16` z ETC3, bez publikacji danych prywatnych.
3. **Weryfikacja obiektu:** lekki moduł geometryczny, który rozpoznaje układ trzech złączy lub zwraca `REVIEW_REQUIRED`; bazujemy na gotowych algorytmach.
4. **Maszyna stanów Vision Workflow:** wykonanie SCN-001-A ze wszystkimi blokadami, testami offline.
5. **Model i plan MoveIt:** dopiero kiedy poprawnie skonstruujemy model NERO + J7 + Sony + OAK, kalibrację i scenę; nadal bez komend ruchu.

Przyszła faza sprzętowa B wymaga osobnego ADR, testów i zgody: rzeczywiste ROS Luxonis na VENTUNO (obecny test FAIL), kompletne transformacje, dopuszczenie niezależnego bezpieczeństwa NERO, model kolizji narzędzia, poprawne zarządzanie utratą zasilania.

## 9. Świadomie nie robimy teraz

- Nie instalujemy nowego Vision w systemowym Ubuntu VENTUNO, nie startujemy ani nie zatrzymujemy żadnych usług produkcyjnych.
- Nie migrujemy własnego Camera Service ani poprzedniego Perception Engine — tylko zachowujemy wnioski i dane z testów.
- Nie sterujemy rzeczywistymi napędami NERO i nie wyzwalamy zdjęć Sony.
- Nie uznajemy mierzonych 65 mm za pełną mapę kolizyjną ani nie „naprawiamy” błędów DepthAI ukrywaniem niepewnych punktów.
- Nie wprowadzamy obowiązkowego modelu AI dla ETC3.
- Nie nazywamy wyników offline i mocków gotową inspekcją produkcyjną.

**Decyzja wymagana po SCN-001-A:** czy podstawowy przepływ jest odpowiedni i które funkcje z modułów są rzeczywiście potrzebne przed etapem sprzętowym.
