# ADR-VISION-ARCH-002 — ROS 2 jako fundament robotyczny Vision

- **Decyzja:** 2026-11-14, zatwierdzona przez właściciela Vision.
- **Status architektoniczny:** **ACCEPTED**.
- **Status realizacji:** **PLANNED / DOCUMENTATION ONLY** — ROS 2 nie zainstalowano ani nie uruchomiono w ramach tego ADR. NERO nie uzyskał nowych uprawnień do ruchu.
- **Docelowa platforma:** ROS 2 **Jazzy** / Ubuntu **24.04 ARM64** / Arduino VENTUNO Q (QCS8275); MoveIt 2 Jazzy.
- **Zakres:** OAK-D Pro AF i przyszła Eye-in-Hand, AgileX NERO, oficjalny Luxonis ROS 2 driver v3, MoveIt 2 + occupancy map, tf2, opcjonalne wyspecjalizowane węzły ECU, Vision Core, adaptery urządzeń i AI Platform.
- **Powiązane ADR:** ADR-VISION-ARCH-001 (historyczne granice odpowiedzialności Camera/Perception/Core) oraz ADR-VISION-ROBOT-001 (NERO STOP i ograniczenia bezpieczeństwa). Ten ADR **zastępuje plan budowy własnych, odrębnych usług Camera Service i Perception Engine**, zachowując zasady pojedynczego właściciela kamery, separacji sterowania i fail-closed. Poprzednie ADR pozostają w gałęziach dokumentacyjnych, bez automatycznego wdrożenia.
- **Cel tej zmiany:** przyjąć nową bazę architektury i plan walidacji, nie instalować pakietów, nie zmieniać usług produkcyjnych, nie przejmować USB/CAN i nie wykonywać ruchów.

## 1. Kontekst

Dotychczasowe testy VENTUNO Q potwierdziły komunikację z OAK-D Pro AF i NERO, a rozbudowany Perception Engine pozyskiwał i analizował rzeczywiste RAW16 DepthAI. Testy wysokości ECU wykazały, że oryginalne dane stereo zawierają powtarzalne wysokie krawędzie, które nasze doświadczalne przetwarzanie usuwało filtrem medianowym 5×5. Nie oznacza to certyfikowanej dokładności 3D. Chcemy ograniczyć własny kod do wartości dodanej dla analizy ECU, a standardowe mechanizmy robotyczne oprzeć na sprawdzonym ekosystemie.

VENTUNO Q to komputer ARM64 z Ubuntu 24.04. Oficjalne źródła wspierają ROS 2 Jazzy na Ubuntu Noble ARM64; MoveIt 2 ma pakiety Jazzy; Luxonis udostępnia DepthAI ROS Driver v3 dla Jazzy; oficjalny AgileX `agx_arm_ros` obsługuje `arm_type:=nero` i MoveIt 2. Wymaga to jednak testów dokładnych wersji, firmware, launch files i zależności na naszym VENTUNO.

## 2. Decyzja

**ROS 2 Jazzy jest standardową bazą komunikacji robotycznej i integracji przestrzennej Vision**. MoveIt 2 będzie preferowanym planistą ruchu NERO, po osobnej walidacji modelu i sterowników. **Nie oznacza to, że wszystkie programy Vision muszą być natywnymi węzłami ROS**, ani że ROS zastępuje Ubuntu, systemd, DepthAI SDK, WebGUI, AI Platform czy niezależny system bezpieczeństwa.

### Upraszczamy implementację: bez dwóch naszych osobnych usług

1. **OAK-D: bezpośrednio oficjalny `depthai_ros_driver_v3`** jako domyślny jedyny właściciel danej kamery na VENTUNO Q. Publikuje obrazy, Depth i `PointCloud2` z `CameraInfo`, znacznikami czasu, kalibracją i diagnostyką. Jego `rgbd_pcl.launch.py` i `pointcloud.launch.py` stanowią punkt wyjścia. Istniejący eksperymentalny Vision Camera Service zachowujemy do porównania i rollbacku, **nie rozwijamy jako kolejnego docelowego produktu**. Migracja po fizycznym smoke teście RVC2 i przywróceniu produkcji; nigdy dwa USB-ownery jednocześnie.
2. **Podstawowa geometria przeszkód: MoveIt 2 Occupancy Map Monitor** konsumujący wprost głębię lub chmurę punktów ROS i budujący OctoMap / Planning Scene dla NERO. Ten standardowy mechanizm zastępuje potrzebę własnej rozbudowanej usługi Perception Engine **w zadaniu bazowego omijania obiektów**. Konieczna walidacja rozdzielczości voxeli, widoczności czarnych powierzchni i wąskich wystających krawędzi; samo „MoveIt widzi PointCloud2” nie gwarantuje ochrony przed kolizją.
3. **Specjalistyczna percepcja ECU — tylko tam, gdzie jest wartość dodana**: identyfikacja modelu ECU, dokładne położenie/orientacja względem złącz i PCB, segmentacja gniazd, lokalizacja otworów, cechy dla manipulatora lub analiza AI. Realizowana jako możliwie małe węzły ROS 2 i/lub istniejące pakiety PCL/Open3D/AI Platform. Nie utrzymujemy oddzielnego, ogólnego Perception Engine ani autorskiego stosu filtracji głębi „na zapas”.
4. **tf2**: standardowe `camera_*_optical_frame`, `table`, `nero_base_link` i rzeczywiste `tool0` (nazwy sprawdzić z URDF). Kalibracja transformacji musi być zmierzona i zweryfikowana; brak kalibracji = `UNAVAILABLE/NO_GO`, nie domyślne identity.
5. **MoveIt 2 + oficjalny AgileX ROS 2 driver**: model URDF/SRDF, kinematyka J1–J7, geometria narzędzi, planowanie i wykonanie po przetestowaniu centralnej bramki ruchu. Dokładnie jeden właściciel poleceń CAN/Ethernet, nie równoległy `pyAgxArm`.
6. **Vision Core**: zachowujemy jako logikę procesu analizy ECU, decyzje operatorskie i orkiestrację, z wykorzystaniem ROS actions/services. Nie przejmuje sprzętu, nie przelicza własnego stereo i nie jest funkcją bezpieczeństwa.
7. **AI Platform (Minisforum)**: cięższe modele AI i specjalizacja ECU poprzez jawne adaptery; nie przenosimy alokacji GPU do drivera kamery. **Sony A6100, termowizja, Stream Deck i WebGUI** nadal mogą używać API/bridge i nie są natywnymi węzłami ROS 2 tylko dlatego, że ROS stanowi bazę robotyki.

**Wniosek z testów ECU:** wcześniejszy autorski median filter 5×5 usuwał wąskie wysokie złącza widoczne w RAW16. Nowy domyślny tor powinien przekazywać standardową chmurę do MoveIt 2 bez własnego agresywnego wygładzania. Jednak OctoMap również może pomijać cienkie szczyty lub źle obserwowane powierzchnie; zaliczenie wymaga sprawdzenia na dwóch zachowanych pomiarach ECU i fizycznych referencjach. Nie uznajemy braku danych Depth za wolną przestrzeń.

## 3. Szkic przepływu i kontraktów

```text
  OAK-D Pro AF (overhead)  /  OAK Eye-in-Hand
                  │
   oficjalny depthai_ros_driver_v3 (1 USB owner na kamerę)
     │        │                │
     RGB      Depth            PointCloud2 / CameraInfo
              └─────────┬───────────────┘
                        │
                tf2 + kalibracja
                        │
               MoveIt 2 Occupancy Map Monitor
                 (Depth / PointCloud → OctoMap)
                        │
             MoveIt 2 Planning Scene + URDF NERO
                        │
             Planowanie trajektorii — FAKE ONLY
                        │
              Vision Core / operator / motion gate
                        │
              AgileX ROS 2 driver (PÓŹNIEJ)
                        │
                       NERO

  Dodatkowy mały węzeł rozpoznania ECU / złączy (tylko
  gdy potrzebny) ← RGB, Depth, PointCloud, AI Platform.

  Niezależna ochrona operatora / E-STOP:
  POZA ROS 2, MoveIt 2, AI i kamerą.
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

- **Preferujemy wprost `depthai_ros_driver_v3` zamiast własnego Camera Service**; przed wycofaniem starej usługi sprawdzić RVC2, USB ownership, sync, wydajność, IR/AF i rollback, a następnie wdrożyć tylko jednego ownera.
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
- **Faza 3:** oryginalny Luxonis `depthai_ros_driver_v3` jako pojedynczy właściciel OAK; RGB/Depth/PointCloud2, latency, sync i diagnostyka; dotychczasowy Camera Service tylko rollback.
- **Faza 4:** MoveIt 2 Occupancy Map Monitor z PointCloud2/Depth → OctoMap i Planning Scene; test, czy nie pomija wąskich szczytów ECU (~75 mm), kalibracja i fail-closed. Dodatkowa percepcja ECU tylko dla precyzyjnych operacji.
- **Faza 5:** integracja rzeczywistego kontrolera tylko po odrębnej zgodzie operatora, zamknięciu interlocków, walidacji ruchu/STOP i ocenie bezpieczeństwa.

Każda faza wymaga dowodów PASS i mechanizmu rollback. Żaden FAIL/NOT_READY nie odblokowuje kolejnego etapu.

## 7. Źródła producentów i stan decyzji

- ROS 2 Jazzy / Ubuntu Noble ARM64: https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html
- MoveIt 2 Jazzy: https://moveit.ai/install-moveit2/binary/
- Luxonis DepthAI ROS v3 (Jazzy: `depthai_ros_driver_v3`): https://docs.luxonis.com/software-v3/depthai/ros/driver
- MoveIt 2 3D Perception / Occupancy Map Monitor i OctoMap: https://moveit.ai/documentation/concepts/
- AgileX ROS 2 Driver `arm_type:=nero`, parametry `auto_enable`: https://github.com/agilexrobotics/agx_arm_ros/blob/ros2/README_EN.md
- AgileX MoveIt 2, fake demo oraz ryzyko real launch: https://github.com/agilexrobotics/agx_arm_ros/blob/ros2/src/agx_arm_moveit/README_EN.md

**Decyzja jest zatwierdzona architektonicznie. Implementacja, instalacja i wszystkie próby z NERO wymagają odrębnych bramek.** To dokumentacja na gałęzi PR do `main`, nie wdrożenie.
