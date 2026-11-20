# Vision — audyt ROS 2 Jazzy / MoveIt 2 / Luxonis z prawdziwymi ECU

**Data:** 2026-11-14. **Stan:** `ROS2_RUNTIME_PASS` / `MOVEIT_OFFLINE_OCTOMAP_PASS` / `RAW_GEOMETRY_SAFETY_NOT_VALIDATED` / `LUXONIS_ROS3_LIVE_STREAM_FAIL` / `PRODUCTION_RESTORED_PASS`.

## 1. Cel i niezmienniki bezpieczeństwa

Użytkownik zatwierdził ROS 2 jako podstawę robotyczną Vision i polecił sprawdzić oficjalny Luxonis ROS v3 oraz MoveIt 2 na zapisanych danych obu ECU. Nie instalowano ROS 2 w głównym Ubuntu VENTUNO Q i nie zmieniano kodu produkcyjnego.

Ograniczenia: brak poleceń do NERO, brak napędów, brak CAN/Ethernet NERO wewnątrz testu, jeden właściciel kamery USB w danym momencie. Wszystkie dane, zależności i logs na NVMe. Docker użył już istniejącego obrazu bazowego (brak nowego `docker pull` do systemowego `/var/lib/docker`); transientne metadane Dockera nie są podstawą deklaracji „zero zapisów eMMC”. Host Camera Service miał status ONLINE/USB SUPER przed testem i został przywrócony po próbie ROS.

## 2. Rzeczywiste środowisko

- Host: **VENTUNO Q**, Ubuntu **24.04.4 ARM64**, NVMe `/srv/vision-data`.
- Izolowany guest: Ubuntu Base **24.04.5 ARM64** w `/srv/vision-data/staging/vision-ros2-offline-20261114/rootfs`, uruchamiany przez lokalny kontener Docker z `--read-only` i podpiętym NVMe. `proot` zawiódł na kernelu; użyto bezpieczniejszej, kontrolowanej izolacji `chroot` wewnątrz kontenera.
- Oficjalne pakiety: `ros-jazzy-ros-base` **0.11.0**, `ros-jazzy-moveit-ros-perception` **2.12.4**, `ros-jazzy-depthai-ros-driver-v3` **3.2.1**.
- `ros2 pkg list`: obecne `depthai_ros_driver_v3`, `moveit_ros_occupancy_map_monitor`, `moveit_ros_perception`, `rclpy`, `sensor_msgs`, `tf2_ros`.
- `ros2 launch depthai_ros_driver_v3 rgbd_pcl.launch.py --show-args`: **PASS**, oficjalny launch załadowany bez kamery.
- Nie użyto ROS drivera z drugą równoległą sesją sprzętową; wszystkie testy MoveIt na zapisach RAW16 wykonano offline.

## 3. Reprodukowalny test MoveIt 2

**Rzeczywiste implementacje:** `occupancy_map_monitor::OccupancyMapMonitor` + `occupancy_map_monitor::PointCloudOctomapUpdater` z zainstalowanych bibliotek MoveIt 2 (nie nasza imitacja OctoMap).

Dane: oryginalne RAW16 1280×800, klatka **12/25** dla każdego ECU, z wcześniejszych kontrolowanych akwizycji Luxonis. Bez naszego filtra medianowego 5×5. Dla poprawnych pikseli w roboczym ROI obliczono XYZ z zapisanym `K` (standardowa projekcja pinhole); transmisja poprzez `sensor_msgs/PointCloud2` w `oak_left_optical_frame`. Dla każdej próby **1 rzeczywista aktualizacja** oficjalnego Occupancy Map Monitor, ROS_DOMAIN_ID izolowany, brak rzeczywistej kalibracji camera↔NERO, żadnego ruchu i brak fałszywego TF do podstawy robota.

Liczby punktów: ECU1 **91 427**, ECU2 **96 467**. Wysokości zajętych voxeli odniesiono do płaszczyzny stołu dopasowanej niezależnie na oryginalnej klatce (RANSAC). Uwaga: wysokość **centrum voxela** nie jest dokładnym wymiarem fizycznym; jej odchylenie zależy też od rozdzielczości mapy.

### Wyniki (z logów oryginalnego modułu MoveIt)

| ECU | OctoMap voxel | Liczba zajętych voxelów | Voxele ≥70 mm | Voxele ≥75 mm | Najwyższy zajęty voxel |
|---|---:|---:|---:|---:|---:|
| ECU1 | 5 mm | 7914 | 9 | 7 | **122,45 mm** |
| ECU1 | 10 mm | 1890 | 8 | 5 | **125,06 mm** |
| ECU2 | 5 mm | 8544 | 44 | 14 | **85,01 mm** |
| ECU2 | 10 mm | 2112 | 32 | 13 | **87,18 mm** |
| ECU2 | 20 mm | 525 | 19 | 11 | **84,99 mm** |

Fizyczne referencje operatora: maksymalna wysokość **ECU1 = 65 mm**, **ECU2 = 75 mm**.

**PASS mechaniczny podtestu:** oficjalny MoveIt otrzymał realny `PointCloud2`, przetworzył go i utworzył zajęte komórki 3D. Wąskie wysokie punkty nie zostały automatycznie usunięte tak jak w naszym wcześniejszym skrypcie z medianą 5×5. Przynajmniej w tej klatce dostępne są komórki na wysokości ≥75 mm ECU2.

**FAIL bramki geometrii:** równie łatwo zachowują się *zawyżone/niepewne pojedyncze punkty*. ECU1 ma fałszywe zajętości do 122–125 mm, mimo fizycznego maksimum 65 mm. Samo przełączenie rozdzielczości 5→10→20 mm nie usuwa problemu. Nie testowano jeszcze fuzji czasowej 25 klatek przez MoveIt ani kompletnej sceny NERO w MoveGroup. Wyniki **nie pozwalają** uznać OctoMap za zwalidowany ogranicznik bezpiecznej trajektorii i nie dowodzą milimetrowej dokładności.

## 4. Oficjalny sterownik Luxonis ROS 2 — próba na fizycznym OAK-D Pro AF

Krótka próba sprzętowa `ros2 launch depthai_ros_driver_v3 rgbd_pcl.launch.py use_rviz:=false` w odizolowanym guest Ubuntu: obecny produkcyjny Camera Service zatrzymano na czas próby, a kontener miał udostępnioną **wyłącznie magistralę USB 002** z kamerą (NERO/USB-CAN na innej magistrali niedostępny), izolowane ROS_DOMAIN_ID i brak dostępu do sieci.

- Węzeł `/oak` oraz `oak_state_publisher` poprawnie załadowały się z oficjalnej biblioteki drivera; `Pipeline/Driver startup` rozpoczął próbę znalezienia urządzenia.
- **FAIL sprzętowy:** `Cannot find any device with given deviceInfo`; 0 tematów `sensor_msgs/Image`, 0 RGB, 0 Depth i 0 `PointCloud2`. **Nie można twierdzić, że oficjalny sterownik zadziałał na kamerze.**
- W read-only kontroli po próbie urządzenie 03e7:f63b było widoczne z poziomu plików `/dev/bus/usb/002` w gościu, ale to nie dowodzi, że sterownik/libusb poprawnie otwiera kamerę. Przyczyną może być passthrough USB, zależności DepthAI/udev, enumeracja/reconnect lub zgodność wersji; **brak jednoznacznej diagnozy**. Nie zmieniano firmware ani EEPROM.
- Po zakończeniu: `IR_OFF True True`, `PROD_RESTART_RC=0`, `PRODUCTION_RESTORED_PASS`. Osobna końcowa kontrola: produkcyjny Camera Service `online=true`, USB `UsbSpeed.SUPER`, RGB ~29,8 FPS, Depth ~29,3 FPS, `error=null`.

## 5. Decyzja techniczna i dalsze bramki

1. **ROS 2 Jazzy / MoveIt 2 na ARM64: realny test uruchomienia i Map Monitor — PASS.** Ten fakt nie jest równoznaczny z gotową na ruch integracją NERO.
2. **OctoMap z PointCloud2: nie zachowuje walidowanej dokładności ani klasyfikacji błędów samoczynnie.** Potrzebna jest *mała warstwa jakości/niepewności* i co najmniej analiza spójności czasowej/voxelowej, nie wielka własna usługa Perception. Ustalenie tolerancji i fail-closed po pomiarach na wzorcu, bez dopasowywania do jednej sztuki ECU.
3. **DepthAI ROS v3 na fizycznej kamerze: nadal FAIL/NOT_VERIFIED.** Dalszy preflight USB/udev w kontrolowanym środowisku (najlepiej test bezpośrednio na VENTUNO, gdy będzie zatwierdzona instalacja systemowa, lub poprawiony izolowany passthrough) i potem udokumentowane rzeczywiste FPS/Depth/PointCloud2; bez dwóch USB ownerów.
4. MoveIt 2 fake controller + zweryfikowany URDF/SRDF NERO, J7, tf2 camera/table/robot_base i scena kolizyjna to **kolejny odrębny etap**. NERO nie może się poruszyć, dopóki nie przejdą osobne bramki niezależnego bezpieczeństwa i świadoma zgoda operatora.

## 6. Dowody prywatne i powtarzalność

Tylko na NVMe (nie publikować nagrań ani skryptów próbnych z prywatnymi danymi):
- `/srv/vision-data/staging/vision-ros2-offline-20261114/rootfs/opt/vision_ecu_replay`: oryginalne kopie RAW16, pliki XYZ, program testowy C++/CMake, konfiguracja i replayer.
- `/srv/vision-data/staging/vision-ros2-offline-20261114/logs/ecu2_ros_moveit_5mm_v3.log`: **PASS mapy**.
- `.../logs/moveit_voxel_comparison.log`: **ECU1 i ECU2 / 5,10,20 mm**.
- `.../logs/luxonis_ros_hw_test.log` oraz `.../logs/ros_luxonis_guard.log`: oficjalny driver, wynik FAIL sprzętowy, przywrócenie usługi PASS.

**Żadnych nowych usług produkcyjnych, zmian w main, zmian Camera Service, sterowaniu NERO lub uruchomienia ROS2 na systemowym Ubuntu VENTUNO.**
