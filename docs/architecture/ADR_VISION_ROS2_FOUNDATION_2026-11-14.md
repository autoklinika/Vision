# ADR-VISION-ARCH-002 — ROS 2 jako fundament robotyczny Vision

- **Decyzja:** 2026-11-14, zatwierdzona przez właściciela Vision.
- **Status architektoniczny:** **ACCEPTED**.
- **Status realizacji:** **PLANNED / DOCUMENTATION ONLY** — ROS 2 nie zainstalowano ani nie uruchomiono w ramach tego ADR. NERO nie uzyskał nowych uprawnień do ruchu.
- **Docelowa platforma:** ROS 2 **Jazzy** / Ubuntu **24.04 ARM64** / Arduino VENTUNO Q (QCS8275); MoveIt 2 Jazzy.
- **Zakres:** OAK-D Pro AF i przyszła kamera Eye-in-Hand, AgileX NERO, Vision Camera Service, Vision Perception Engine, Vision Core, ROS 2 + tf2, MoveIt 2, adaptery urządzeń i AI Platform.
- **Powiązane ADR:** ADR-VISION-ARCH-001 (oddzielenie Camera Service / Perception / Core) oraz ADR-VISION-ROBOT-001 (NERO STOP i jego ograniczenia bezpieczeństwa). Są obecnie również w gałęziach dokumentacyjnych, nie wolno zakładać, że zostały wdrożone przez samą decyzję ROS 2.
- **Cel tej zmiany:** przyjąć nową bazę architektury i plan walidacji, nie instalować pakietów, nie zmieniać usług produkcyjnych, nie przejmować USB/CAN i nie wykonywać ruchów.

## 1. Kontekst

Dotychczasowe testy VENTUNO Q potwierdziły komunikację z OAK-D Pro AF i NERO, a rozbudowany Perception Engine pozyskiwał i analizował rzeczywiste RAW16 DepthAI. Testy wysokości ECU wykazały, że oryginalne dane stereo zawierają powtarzalne wysokie krawędzie, które nasze doświadczalne przetwarzanie usuwało filtrem medianowym 5×5. Nie oznacza to certyfikowanej dokładności 3D. Chcemy ograniczyć własny kod do wartości dodanej dla analizy ECU, a standardowe mechanizmy robotyczne oprzeć na sprawdzonym ekosystemie.

VENTUNO Q to komputer ARM64 z Ubuntu 24.04. Oficjalne źródła wspierają ROS 2 Jazzy na Ubuntu Noble ARM64; MoveIt 2 ma pakiety Jazzy; Luxonis udostępnia DepthAI ROS Driver v3 dla Jazzy; oficjalny AgileX `agx_arm_ros` obsługuje `arm_type:=nero` i MoveIt 2. Wymaga to jednak testów dokładnych wersji, firmware, launch files i zależności na naszym VENTUNO.

## 2. Decyzja

**ROS 2 Jazzy jest standardową bazą komunikacji robotycznej i integracji przestrzennej Vision**. MoveIt 2 będzie preferowanym planistą ruchu NERO, po osobnej walidacji modelu i sterowników. **Nie oznacza to, że wszystkie programy Vision muszą być natywnymi węzłami ROS**, ani że ROS zastępuje Ubuntu, systemd, DepthAI SDK, WebGUI, AI Platform czy niezależny system bezpieczeństwa.

Zachowujemy obowiązujące granice:
- **Vision Camera Service**: pojedynczy właściciel każdego fizycznego OAK, akwizycja i diagnostyka. Preferowane oficjalne pipeline i komponenty DepthAI; interfejs ROS to sposób publikacji, a nie drugi równoczesny proces otwierający tę samą kamerę. Wariant (A) Camera Service + publisher ROS albo (B) oficjalny `depthai_ros_driver_v3` przejmujący rolę właściciela kamery wybierzemy **dopiero po testach porównawczych**. Nie uruchamiać obu wariantów jednocześnie na jednej kamerze.
- **Vision Perception Engine**: interpretacja sceny ECU, lokalizacja, kształt, wysokości lokalnych przeszkód, jakość i niepewność. Wykorzystuje standardowe dane ROS/DepthAI, nie implementuje własnego stereo. Nie jest certyfikowanym czujnikiem bezpieczeństwa.
- **tf2 / robot_state_publisher**: standaryzowane układy `camera_*_optical_frame`, `table`, `nero_base_link`, `tool0` (ostateczne nazwy zgodne z URDF), aktualizacja transformacji z kalibracją i znacznikami czasu. Zanim kalibracja zostanie zmierzona i zwalidowana, transformacje do `nero_base_link` są **UNAVAILABLE**, nigdy sztuczne identity.
- **AgileX ROS 2 Driver / ros2_control (po walidacji)**: w przyszłości jedyny właściciel toru poleceń do NERO i stanów przegubów. Nie może współdzielić dostępu CAN/Ethernet z równoległym `pyAgxArm` czy eksperymentalnym kontrolerem. Przyjmujemy sterownik/transport wyłącznie po audycie wersji i potrzebnej konfiguracji.
- **MoveIt 2**: URDF/SRDF, model kolizyjny, planowanie ruchu J1–J7, sceny z przeszkodami; wyłącznie środowisko symulowane dopóki bramki ruchu nie zostaną zamknięte. Plan nie jest gwarancją braku kolizji, jeżeli scena jest niepełna lub nieaktualna.
- **Vision Core**: przyszła orkiestracja zadania ECU i zatwierdzanie planu, nie surowa obsługa USB, napędów ani bezpośrednie sterowanie GPU.
- **AI Platform (Minisforum)**: modele AI, rozpoznanie wariantów ECU, cięższe zadania przez istniejący Resource Manager. Integracja może być asynchronicznym adapterem API/ROS; nie przenosimy zarządzania GPU do Camera Service, nie uzależniamy podstawowego zatrzymania od sieci.
- **Sony A6100, kamera termiczna, Stream Deck Plus, UPS i WebGUI**: pozostają istniejącymi systemami i wchodzą przez adaptery/bridges tam, gdzie jest to potrzebne. **Nie wszystkie wspierają ROS 2 natywnie.**

## 3. Szkic przepływu i kontraktów

```text
OAK-D overhead / Eye-in-Hand [wyłączny owner sprzętu]
   └── DepthAI Camera Service lub oficjalny DepthAI ROS Driver v3
           ├─ /camera/*: Image, CameraInfo, Depth, PointCloud2, timestamp / frame_id
           └─ health, quality, valid / stale / no depth
                        ↓
               Vision Perception Engine  ← AI Platform (opcjonalny adapter zleceń)
                        ├─ ECU pose / orientation + covariance/quality
                        ├─ wyspecyfikowane bryły i szczyty przeszkód + niepewność
                        └─ invalid/stale i wersja kalibracji
                        ↓
               tf2 (camera → table → nero_base_link)
                        ↓
               MoveIt 2 + Planning Scene
                        ↓
        Vision Core: workflow, operator approval, central motion gate
                        ↓
        NERO Controller (jeden właściciel poleceń, status J1–J7)
                        ↓
                       NERO

  Niezależna ochrona operatora i zatrzymanie: POZA torami ROS/DDS/AI.
```

Standardowe typy wiadomości (kandydaci, do uzgodnienia po teście): `sensor_msgs/Image`, `sensor_msgs/CameraInfo`, `sensor_msgs/PointCloud2`, `sensor_msgs/JointState`, `geometry_msgs/PoseStamped`, `tf2_msgs/TFMessage`, `moveit_msgs/CollisionObject` / `PlanningScene`, `control_msgs/FollowJointTrajectory`. Dla jakości pomiaru i geometrii ECU opracować jawnie wersjonowane wiadomości z polami: `frame_id`, timestamp, kalibracja/revision, uncertainty, source frame(s), validity i max age. Brak wiadomości lub transformacji => **NOT_READY/NO_GO**, nigdy „zero” jako wartość zastępcza.

ROS 2/DDS ma QoS konfigurowalne dla strumieni obrazu i danych sterowania. Parametry czasu, kolejki, synchronizacja sensorów, deadline i sieć muszą zostać zmierzone; DDS nie jest automatycznym systemem czasu rzeczywistego ani bezpieczeństwa. Nie publikować intensywnych chmur 3D poza VENTUNO, jeżeli wystarczy lokalny odbiorca; koszty CPU/RAM/latencji benchmarkować na sprzęcie.

## 4. Granice bezpieczeństwa (twarde)

1. **Brak automatycznego załączania napędów i ruchu.** W dokumentacji AgileX `agx_arm_ros` istnieje `auto_enable=true` jako ustawienie domyślne; konfiguracja MoveIt potrafi uruchomić sterownik rzeczywistego robota i ma `auto_control_gate=false` w jednym z launchów. Nie wolno wykonywać takich launchów na podłączonym NERO bez odrębnego audytu i zatwierdzenia.
2. Pierwsze próby: **wyłącznie URDF, RViz 2, MoveIt 2 z fake/simulated controller**; bez otwarcia CAN/Ethernet NERO i bez wysyłania komend sprzętowych. Zakaz automatycznego wznowienia po restarcie.
3. System sterowania ruchem: jeden właściciel CAN/transportu i centralny interlock. Stream Deck STOP to funkcja programowa; niezależne zabezpieczenia i ocena ryzyka pozostają niezbędne. Przerwanie zwykłego 24 V może doprowadzić do opadnięcia ramienia i nie jest domyślnym E-STOP.
4. Kamera/OAK, percepcja, AI, MoveIt 2 i ROS 2 **nie są certyfikowaną funkcją bezpieczeństwa człowieka**. Nie można z faktu „brak przeszkody w kamerze” wywnioskować zgody na ruch. Utrata głębi, niezidentyfikowane powierzchnie, opóźnienie, niepewność lub błędna kalibracja wymuszają NO_GO i wstrzymanie nowych poleceń.
5. Żadne obecne badania ECU, w tym poprawa wysokości z 65 do ok. 75 mm na surowej chmurze, nie oznaczają gotowości na autonomiczny ruch.

## 5. Decyzje szczegółowe wymagające testu, nie domysłu

- Oficjalny `depthai_ros_driver_v3` vs bridge z istniejącego Camera Service; porównać USB ownership, RVC2, wydajność, znaczniki czasu, IR/AF i rekonfigurację, następnie wybrać jeden.
- AgileX transport: dokumentacja `agx_arm_ros` opisuje CAN/SockeCAN `can_port`; użytkownik preferuje Ethernet. Nie zakładać, że oficjalny launch wspiera Ethernet bez dowodów. Nie uruchamiać dwóch równoległych sterowników.
- Zgodność dokładnego modelu URDF/SRDF NERO i osprzętu J7, elementów Eye-in-Hand i Sony; kalibracja mocowania aparatu oraz narzędzia.
- DDS middleware (Cyclone DDS jako kandydat w dokumentacji MoveIt), ROS_DOMAIN_ID, discovery i segmentacja sieci, parametry QoS oraz kontrola dostępu; nie wyciekać danych/sterowania do VLAN gości, do AI Platform tylko jawny adapter/namespace.
- NVMe-only dla plików projektu, cache, workspace, rosbagów i logów. ROS system packages mogą wymagać osobnej jawnie zatwierdzonej instalacji systemowej; odrębny audyt wpływu na eMMC i Qualcomm.
- Integracja z istniejącym ROS-free WebGUI, Tailscale, OpenDeck oraz AI Platform ma być inkrementalna, bez migracji wszystkiego naraz.

## 6. Wdrożenie etapowe

Pełny plan z mierzalnymi bramkami: [VISION_ROS2_ADOPTION_PLAN_2026-11-14.md](../operations/VISION_ROS2_ADOPTION_PLAN_2026-11-14.md).

- **Faza 0:** read-only preflight ROS/Jazzy/ARM64, NERO i USB, kopie ustawień i lista konfliktów; bez instalacji.
- **Faza 1:** izolowane środowisko ROS 2 Jazzy na NVMe (lub test bezpiecznych paczek systemowych po zatwierdzeniu); talker/listener, DDS, tf2, no hardware control.
- **Faza 2:** model NERO + MoveIt2 fake controller, RViz 2; testy rozwiązywania kinematyki, zasięg, kolizje, osprzęt J7.
- **Faza 3:** integracja Luxonis w trybie jednego właściciela OAK; RGB/Depth/PointCloud, latency, synchronizacja; replay zapisanych ECU z najwyższymi złączami.
- **Faza 4:** Planning Scene i kalibracja do stołu, NERO; analiza fail-closed i regresja po utracie czujnika/USB/DDS.
- **Faza 5:** integracja rzeczywistego kontrolera tylko po odrębnej zgodzie operatora, zamknięciu interlocków, walidacji ruchu/STOP i ocenie bezpieczeństwa.

Każda faza wymaga dowodów PASS i mechanizmu rollback. Żaden FAIL/NOT_READY nie odblokowuje kolejnego etapu.

## 7. Źródła producentów i stan decyzji

- ROS 2 Jazzy / Ubuntu Noble ARM64: https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html
- MoveIt 2 Jazzy: https://moveit.ai/install-moveit2/binary/
- Luxonis DepthAI ROS v3 (Jazzy: `depthai_ros_driver_v3`): https://docs.luxonis.com/software-v3/depthai/ros/driver
- AgileX ROS 2 Driver `arm_type:=nero`, parametry `auto_enable`: https://github.com/agilexrobotics/agx_arm_ros/blob/ros2/README_EN.md
- AgileX MoveIt 2, fake demo oraz ryzyko real launch: https://github.com/agilexrobotics/agx_arm_ros/blob/ros2/src/agx_arm_moveit/README_EN.md

**Decyzja jest zatwierdzona architektonicznie. Implementacja, instalacja i wszystkie próby z NERO wymagają odrębnych bramek.** To dokumentacja na gałęzi PR do `main`, nie wdrożenie.
