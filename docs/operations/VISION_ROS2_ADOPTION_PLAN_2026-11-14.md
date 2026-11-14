# Vision — plan przejścia na ROS 2 Jazzy / MoveIt 2

**Data:** 2026-11-14. **Decyzja nadrzędna:** [ADR-VISION-ARCH-002](../architecture/ADR_VISION_ROS2_FOUNDATION_2026-11-14.md) (**ACCEPTED**).
**Wdrożenie:** NOT_STARTED. Niniejszy dokument jest planem testowym; nie upoważnia do uruchamiania fizycznego NERO, instalacji na eMMC ani zmiany Camera Service.

## Kontrakt implementacji

- Bazą robotyki staje się **ROS 2 Jazzy** na VENTUNO Q / Ubuntu 24.04 ARM64.
- ROS 2 służy do komunikacji, tf2 do transformacji, MoveIt 2 do planowania, oficjalne sterowniki Luxonis/AgileX są preferowane po pozytywnej weryfikacji wersji.
- Zachować oddzielne logiczne moduły Camera Service, Perception Engine, Vision Core oraz jedyny NERO Controller. Nie odtwarzać od zera standardowej kinematyki i mechanizmów komunikacji.
- Dane/ROS workspaces, rosbag, cache i artefakty testowe wyłącznie na `/srv/vision-data` po sprawdzeniu mountpoint. Nie modyfikować istniejących usług, zasilania NERO, konfiguracji STOP lub sterowników GPU podczas prób przygotowawczych.
- **Brak ruchu NERO** do odrębnej, świadomej zgody operatora po walidacji interlocków i niezależnego bezpieczeństwa.
- Produkcyjna kamera nie może być otwierana jednocześnie przez dwa procesy.

## Etapy i kryteria PASS

| Etap | Zadania | PASS | Czego NIE wolno |
|---|---|---|---|
| **0. Audyt bez zmian** | Architektura ARM64, kernel, zasoby CPU/RAM/NVMe, polityka NVMe, pakiety ROS2 Jazzy/MoveIt, oficjalne repo AgileX i Luxonis; wersje hardware, backup serwisów i ich konfiguracji | Zgodny zestaw wersji, plan rollback, produkcja bez restartów, przyjęte zagrożenia | Instalować pakietów, przejmować USB/CAN, ruszać NERO |
| **1. ROS 2 minimum** | Oddzielne testowe środowisko na NVMe; `ros2 topic`, publisher/subscriber, tf2, clock, QoS, DDS discovery i metryki zasobów | Testy łączności, pamięci, czasu, restartu, zatrzymania i braku ingerencji w usługi | Włączać sprzętowy AgileX driver lub drugiego USB ownera |
| **2. NERO bez sprzętu** | Zweryfikować oficjalny URDF/SRDF NERO, brakujący model rzeczywistego adaptera J7, RViz 2, MoveIt 2 z fake controller, offline joint_states i Planning Scene | Poprawne J1–J7, zakresy, model kolizji, kilka testowych trajektorii w symulacji bez kolizji | Uruchamiać launch z rzeczywistym `auto_enable` / `auto_control_gate=false`, CAN/Ethernet |
| **3. Luxonis ROS** | Dwa warianty w DEV: (A) bridge jednego Camera Service do ROS vs (B) `depthai_ros_driver_v3` jako jedyny właściciel OAK; zmierzyć sync, fps, opóźnienie, IR, AF, Depth RAW16, PointCloud2, tf | Wybrany jeden owner, stabilność i rollback, brak podwójnego przejęcia USB, zgodne camera_info/frame_id | Równolegle przejmować kamerę drugim driverem |
| **4. ECU & sceny 3D** | Geometria dwóch ECU z zapisanych RAW16; w szczególności wąskie szczyty ~75 mm usuwane wcześniej przez medianę 5×5, rzeczywista niepewność, obrysy, tf camera/table/nero_base, collision objects i aktualizacja Planning Scene | Rozbieżności porównane do fizycznych wzorców, fail-closed przy brakach Depth/tf, spójna geometria, odtwarzalny replay | Uznawać P99 za max przeszkody, ufać gołym pojedynczym pikselom, sterować real NERO |
| **5. Integracja NERO live** | Po osobnym zatwierdzeniu: jedyny właściciel transportu, kontrola `auto_enable:=false`, centralny gate STOP, fault injection i walidacja real-time; dopiero potem ruchy pod nadzorem | Wymagana niezależna ocena ryzyka i zabezpieczenia, zbadane zachowanie STOP, braking/hold, UPS, transport recovery, jawna zgoda na konkretny test | Wykonywać automatycznie ruch po uruchomieniu, traktować Camera/ROS jako funkcję bezpieczeństwa |

**Wejście do kolejnego etapu tylko po raporcie PASS poprzedniego.** W razie utraty USB3/can0/DDS, stale messages, zniknięcia transformacji, błędu table plane, nieznanego punktu najwyższego lub niespójnego stanu napędów => NOT_READY/NO_GO; nie podejmować automatycznego restartu ruchu.

## Szczegółowe kryteria sprawdzające

### Camera Service i DepthAI

1. Każda fizyczna OAK ma jednego właściciela USB. Tryb B oznacza kontrolowaną migrację/wyłączenie starego ownera, nie dwie aktywne usługi.
2. Zsynchronizowane `sensor_msgs/Image`, `CameraInfo` i `PointCloud2` muszą posiadać spójne timestampy, calibrations i frame_id, jawnie rozróżniać RAW16 i przetworzoną chmurę.
3. Zweryfikować montaż overhead, przyszły Eye-in-Hand, jego sztywność i zmienną transformację narzędzie→kamera. W RViz nie dopuszczać niezdefiniowanych transformacji.
4. Regresja ECU1 i ECU2: różnice wysokości oceniane po fizycznych pomiarach; szczególnie wąskie krawędzie muszą pozostać widoczne jako spójne ograniczenia przestrzeni mimo filtracji.
5. Analiza wpływu ARM64 CPU i USB: klatki, temperatury, opóźnienie starych wiadomości, reconnect, 30 FPS jako wartość zaobserwowana w obecnej produkcji, nie nowa gwarancja ROS.

### AgileX NERO, MoveIt 2 i safety

1. Oficjalny kod producenta sprawdzić pod kątem zgodności rzeczywistego NERO 7-DOF z `arm_type:=nero`, firmware i transportem USB-CAN (SocketCAN 1 Mbps); Ethernet tylko po potwierdzonym wsparciu, nie przez założenie.
2. **Nigdy nie używać demo real-arm jako testu startowego.** Producent dokumentuje `auto_enable=true` w sterowniku i `auto_control_gate=false` w jednym z launchów MoveIt: ich domyślne wartości nie są bezpiecznym lab setup.
3. Symulowany robot nie ma fizycznego połączenia CAN/Ethernet i nie może przypadkowo włączać napędów.
4. Model kolizyjny obejmuje realne mocowanie NERO, adapter o profilu D J7 (weryfikowany mechanicznie), osprzęt, Sony i Eye-in-Hand; placeholdery nie dają zgody na ruch.
5. Planer może generować propozycję trajektorii; wykonanie wymaga centralnego gate i świadomej decyzji. STOP SW na Stream Deck nie zastępuje niezależnego rozwiązania bezpieczeństwa.
6. Zmiana stanu `POWER_FAILURE`, utrata telemetrii, STOP latch, brak świeżej percepcji i błędy planowania blokują nowe zadania; nie wolno automatycznie odblokować po restarcie.

### Architektura danych i AI

- Lokalnie na VENTUNO: ROS Graph, sterowanie, stany J1–J7, chmury, geometria, tf2, planowanie MoveIt 2 po próbach wydajności.
- Na Minisforum AI Platform: cięższe wnioskowanie i specjalizowane modele ECU, integracja asynchroniczna przez istniejący Resource Manager. Bez traktowania GPU i łączności Tailscale jako pętli natychmiastowego bezpieczeństwa.
- WebGUI i Stream Deck pozostają interfejsami operatorskimi/diagnostycznymi; decyzja o wykonaniu ruchu nie jest przesyłana bez gate.
- Monitoring: uruchomienie, odłączenie urządzeń, QoS loss, pairing failure, opóźnienie danych, TF age, CPU/RAM, STOP oraz rozbieżność model/real. Dane źródłowe i raporty lokalnie na NVMe, bez publikowania surowych sesji ECU.

## Wersje i źródła do preflight

- ROS 2 Jazzy (Ubuntu Noble ARM64): https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html
- MoveIt 2 Jazzy: https://moveit.ai/install-moveit2/binary/
- Luxonis ROS v3 na Jazzy: https://docs.luxonis.com/software-v3/depthai/ros/driver
- AgileX `agx_arm_ros` ROS2 branch: https://github.com/agilexrobotics/agx_arm_ros/blob/ros2/README_EN.md
- AgileX MoveIt 2 NERO fake demo: https://github.com/agilexrobotics/agx_arm_ros/blob/ros2/src/agx_arm_moveit/README_EN.md

## Zasada publikacji

Ta dokumentacja jest przygotowana w osobnej gałęzi z PR względem `main`, bez automatycznego merge. Wdrożenie ROS 2, dodatkowych pakietów Ubuntu i integracji sterowników ma stan **NOT_STARTED**, dopóki osobny protokół odbioru nie potwierdzi zmiany.
