# Vision Guided Positioning V1 — zatwierdzona baza laboratoryjna

**Odbiór:** 23 listopada 2026 r.
**Status:** ACCEPTED LAB BASELINE V1 — nie jest to wdrożenie produkcyjne ani dopuszczenie pracy bezobsługowej.
**Źródło prawdy:** niniejsze podsumowanie oraz prywatny, zapieczętowany snapshot na VENTUNO Q, z manifestem SHA-256.

## Potwierdzony przepływ Vision

1. Nieruchomy Luxonis OAK-D Pro AF dostarcza obrazy RGB i Depth oraz CameraInfo przez oficjalny ROS 2 DepthAI v3.
2. Logika specyficzna dla ECU rozpoznaje widoczną płytkę lub wskazane złącze, wyznacza położenie, wysokość przeszkód i obwiednię bieżącego obiektu.
3. PlanningScene w MoveIt 2 łączy stałą geometrię stanowiska z dynamiczną bryłą aktualnego ECU. MoveIt oblicza TF/FK/IK, kontroluje ograniczenia i planuje bezkolizyjną trajektorię.
4. Standardowa akcja MoveIt kieruje ruch przez ros2_control i fabryczny sterownik AgileX do NERO na magistrali CAN.
5. Operator nadzoruje fizyczne wykonanie. Ramię może wrócić do laboratoryjnego punktu PARK V1.

**Fizycznie zweryfikowane 23.11.2026:**
- Dwa pełne cykle PARK → ETC3 → PARK.
- Po przesunięciu ETC3: Luxonis wyznaczył nowy cel szarej wtyczki, MoveIt przeplanował trasę, NERO wykonał dojazd i powrót.
- Po wymianie na wcześniej niewprowadzony PTM: Luxonis zlokalizował środek widocznego PCB, wyznaczył bryłę kolizyjną; MoveIt skierował NERO nad środek laminatu. Operator potwierdził rzeczywiste centralne ustawienie atrapy.
- Późniejszy pełny fizyczny powrót znad PTM do PARK V1, status MoveIt SUCCEEDED, firmware NORMAL.

Nie deklarujemy jeszcze niezależnego, metrologicznego potwierdzenia bezwzględnej dokładności 5 mm ani automatycznego wykonania zdjęć Sony.

## Architektura — zakres odpowiedzialności

| Warstwa | Odpowiedzialność |
|---|---|
| Stały profil stanowiska | Stół, montaż NERO i Luxonis, narzędzie Sony na J7, PARK V1 |
| Luxonis / ROS 2 | RGB, stereo Depth, chmura punktów i dane kamery |
| Logika ECU | Lokalizacja aktualnej obudowy, laminatu, złączy i punktów zdjęciowych |
| MoveIt 2 | Aktualizacja sceny, IK, trajektoria, sprawdzanie kolizji |
| Fabryczny AgileX ROS 2 | Kontrola przegubów, bramka sterowania i CAN |
| Sony | Docelowe zdjęcia PCB (kolejny, niezakończony etap) |

Nie rozwijamy własnego, alternatywnego wykonawcy trajektorii C8/C9 ani własnego ogólnego Camera Service/Perception Engine. Starsze eksperymenty pozostają dostępne jako historia badawcza.

## Geometria: stała i dynamiczna

**Stałe po odbiorze:** geometria i montaż stanowiska, pozycja PARK V1, model Sony na J7 oraz nieruchoma kamera Luxonis. W PARK V1 spód atrapy celowo dotyka stołu (nominalny prześwit 0 mm). Adapter mieści się wewnątrz J7, a model kolizyjny nie wyłącza kontroli względem link6.

**Dynamiczne:** pozycja i obrót bieżącego ECU, jego obwiednia, wysokości przeszkód, cele fotograficzne i planowane ruchy. Podmiana ETC3 na PTM nie wymaga ponownej kalibracji niezmienionego stanowiska.

## Ograniczenia i zasady odbioru

- To laboratorium z nadzorem operatora. Programowe HOLD jest przyjęte operacyjnie, ale nie stanowi certyfikowanego przycisku bezpieczeństwa; osobny test naciśnięcia przycisku podczas ruchu pozostaje niezakończony.
- Absolute Camera–Table–Robot TF to wciąż laboracyjny kandydat kalibracji. Wynik FK z enkoderów nie dowodzi niezależnie dokładności osi optycznej.
- Wypróbowana fabryczna integracja ros2_control używała GenericSystem jako mostka komend do osobnego sterownika AgileX; nie jest wdrożeniem dedykowanego produkcyjnego hardware_interface.
- Część aktywnych usług ROS 2 uruchomiono jako transient systemd units; snapshot nie gwarantuje autostartu po reboocie. Nie uruchamiać równoległych właścicieli CAN.
- Wszystkie trasy do nowych ECU należy planować od bieżących enkoderów i sprawdzać na aktualnej scenie, z ograniczeniami osi i modelowymi prześwitami.
- Prywatna geometria, surowe zdjęcia PCB/RAW16, identyfikatory sprzętu, pełne logi i snapshoty runtime pozostają na prywatnym NVMe, nie w publicznym GitHub.

## Rozwój po V1

Bazę V1 utrzymujemy jako punkt odniesienia bez edycji. Nowa integracja Sony, metrologia, segmentacja ECU i testy regresyjne będą w oddzielnych gałęziach, bez zmiany potwierdzonego sterownika ruchu. Zobacz politykę: docs/process/REPOSITORY_HYGIENE_V1.md oraz rejestr PR: docs/operations/OPEN_PR_PORTFOLIO_2026-11-23.md.
