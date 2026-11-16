# Vision — ROS 2, AgileX NERO i architektura przenośnego stanowiska LAB → PROD

- **Data opracowania:** 2026-11-16.
- **Źródło:** dyskusja projektowa z 15–16.11.2026 o szczegółowej obsłudze ROS 2 i przygotowaniu systemu w laboratorium z późniejszą relokacją na stanowisko docelowe; uzupełnienie [fundamentu Vision z 14.11.2026](VISION_FOUNDATION_2026-11-14.md).
- **Status dokumentu:** `DESIGN REPORT / PROPOSED`. Opis kierunku rozwoju, wymaganych danych, mechanizmów i planu walidacji; **nie stanowi zatwierdzonego wdrożenia, potwierdzenia kompatybilności konkretnego zestawu wersji ani zgody na ruch NERO**.
- **Zakres zmian repo:** wyłącznie dokumentacja. Bez instalacji, zmian konfiguracji i testów fizycznych na VENTUNO Q, NERO, Luxonis, Sony czy AI Platform.
- **Jawność:** repozytorium jest publiczne; dokument nie zawiera danych dostępowych, adresacji prywatnej sieci, numerów seryjnych ani prywatnych logów i obrazów ECU.
- **Słownik statusów:** `CONFIRMED LAB` — historycznie potwierdzone w określonej próbie; `AVAILABLE UPSTREAM` — dostępne w dokumentacji dostawcy, ale jeszcze nieprzetestowane u nas; `PROPOSED` — projekt; `NOT VALIDATED` — brak wymaganego dowodu; `BLOCKED` — brak warunku dopuszczenia.

> **Główne ustalenie:** rozwijamy **jeden** system Vision, z wymiennymi profilami środowiska `laboratory` i `production`. Algorytmy inspekcji opisują cele względem ECU, a nie względem konkretnego blatu. Przeprowadzka wymusza nową kwalifikację geometrii, kalibracji, przeszkód i bezpieczeństwa — nie wymusza przepisywania sterowników, profili ECU i procesu inspekcji.

## 1. Zakres ustaleń i relacja do wcześniejszych decyzji

1. Wykorzystujemy ROS 2 jako **głównego kandydata** na lokalną szynę integracyjną urządzeń robotycznych, a nie jako alternatywny system operacyjny. Docelowy wybór dystrybucji i zestawu zależności przechodzi testy na VENTUNO Q.
2. Na Ubuntu 24.04 ARM64 preferujemy `ROS 2 Jazzy`; wraz z nim: oficjalny AgileX `agx_arm_ros`, `MoveIt 2`, `ros2_control`, `tf2`, `RViz 2`, `rosbag2` oraz sterownik DepthAI ROS zgodny z DepthAI v3.
3. **Najpierw izolowany test ekosystemu ROS 2, potem dopiero implementacja właściwego Workflow/Core i scenariusza ETC3.** Nie kontynuujemy automatycznie wcześniejszej aplikacji Camera Service.
4. Używamy oficjalnej kinematyki NERO, konfiguracji MoveIt i gotowych mechanizmów mapowania sceny, zamiast przepisywać je od zera. Funkcje, których nie dostarcza ekosystem (weryfikacja ECU, workflow, sesje, Sony, bezpieczeństwo integracji), projektujemy osobno.
5. Pierwsze ECU pozostaje **ETC3**: egzemplarz mierzony 14.11.2026, rozpoznawany roboczo po dwóch czarnych i jednej szarej wtyczce. Operator deklaruje typ, kamera weryfikuje. Wymiary z próby nie stają się automatycznie zatwierdzonym profilem.
6. NERO jest na początku głównie **pozycjonerem Sony A6100 i Luxonis OAK-D Pro AF**, nie autonomicznym manipulatorem do demontażu ECU.
7. Komponent AI na Minisforum wykonuje zadania analizy i treningu, ale **nie publikuje bezpośrednich komend napędów NERO**.
8. Kamera głębi, MoveIt, ROS, Stream Deck i STOP programowy **nie zastępują niezależnych zabezpieczeń operatora**.
9. Zachowujemy wiedzę i wyniki prób z PR #15 i eksperymentów; nowa aplikacja jest projektem greenfield i nie dziedziczy automatycznie starego kodu.

Powiązania nadrzędne: [fundament Vision](VISION_FOUNDATION_2026-11-14.md), [zasady wydania](../operations/RELEASE_GATES_2026-11-10.md), [ADR STOP NERO](ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md). Osobna propozycja decyzji o przenośności: [ADR-VISION-STATION-001](ADR_VISION_PORTABLE_STATION_LAB_PROD_2026-11-16.md).

## 2. Aktualny zakres dowodów — bez nadinterpretacji

| Element | Co wiemy | Status |
| --- | --- | --- |
| VENTUNO Q | Qualcomm QCS8275, Ubuntu 24.04 ARM64, NVMe z danymi Vision | `CONFIRMED LAB` historycznie |
| ROS 2 na VENTUNO | Użytkownik wskazał istniejące środowisko ROS 2 w kontenerze Docker; brak bieżącego audytu obrazu, wersji, sieci, bind-mountów i urządzeń | `REPORTED / NOT VALIDATED NOW` |
| NERO | 7 osi; firmware 1.22; pyAgxArm; interfejs AgileX USB-CAN 1 Mb/s; odczyty pozycji/statusów | `CONFIRMED LAB` historycznie |
| Oficjalny AgileX ROS 2 | Model `nero`, ROS Jazzy, pakiety sterownika, RViz i demo MoveIt | `AVAILABLE UPSTREAM`, bez testu integracyjnego na VENTUNO |
| Luxonis OAK-D Pro AF | Wcześniej działały podgląd RGB, głębia i próby IR; geometria wymaga dalszej walidacji | `CONFIRMED LAB` częściowo |
| DepthAI ROS v3 | Oficjalna integracja RGB-D, CameraInfo, TF i PointCloud2 | `AVAILABLE UPSTREAM`, do testu na VENTUNO |
| Sony A6100 | Potwierdzono osobno PTP, HDMI i wybrane formy kontroli | `CONFIRMED LAB` dla konkretnych prób |
| Montaż J7 | Adapter profilu D i prototypy uchwytu; pełna geometria, masa i transformacje narzędzi niezatwierdzone | `PROPOSED / NOT VALIDATED` |
| Kalibracja głębi | Próby na wzorcach o wysokościach 34 / 50,4 / 101 mm nie spełniły konsekwentnie celu ±1 mm | `NOT VALIDATED` |
| STOP | Klawisz programowy z wcześniejszym potwierdzeniem odpowiedzi sterownika, bez testu dynamicznego hamowania i bez niezależnego toru | `PARTIAL LAB TEST` |
| Pełny Workflow/Core Vision | Istnieją zatwierdzone wymagania, brak produkcyjnego runtime nowego systemu | `PROPOSED` |

**Rozróżnienie:** „dostępne w repozytorium producenta” ≠ „zainstalowane” ≠ „przetestowane z naszym firmware i sprzętem” ≠ „dopuszczone do sterowania”. Podobnie samo istnienie kontenera ROS 2 nie dowodzi zgodności wszystkich pakietów i sterowników.

## 3. Obsługa ROS 2 — szczegółowe pojęcia i praktyka

ROS 2 to framework komunikacji i programowania robotów działający na Linuksie. Rozproszony system jest złożony z procesów zwanych **węzłami** (`nodes`). Węzły udostępniają:

- **Topics**: strumienie wiadomości, np. obrazy, pozycje przegubów, głębia, telemetria.
- **Messages**: strukturyzowane typy, np. `sensor_msgs/msg/JointState`, `sensor_msgs/msg/Image`, `sensor_msgs/msg/CameraInfo`, `sensor_msgs/msg/PointCloud2`, `geometry_msgs/msg/PoseStamped`.
- **Services**: krótkie żądanie/odpowiedź, np. zmiana parametru lub weryfikacja stanu.
- **Actions**: zadania długotrwałe z informacją o postępie, wyniku i możliwością anulowania; naturalne dla wykonania trajektorii.
- **Parameters**: wartości konfiguracyjne węzła (nazwy, port, częstotliwość, wariant robota).
- **Launch**: pliki uruchomienia grupy węzłów, parametrów i przestrzeni nazw.
- **tf2**: drzewo transformacji `frame_id` pomiędzy robotem, stołem, ECU i kamerami.
- **QoS/DDS**: zasady dostarczania/odkrywania komunikatów; odpowiednie ustawienia dla obrazów i sterowania są różne.
- **URDF/Xacro**: geometryczny, kinematyczny i częściowo dynamiczny opis robota i osprzętu.
- **SRDF**: semantyka grup planowania, pozycji nazwanych i reguł kolizji.
- **ros2_control**: interfejsy sprzętowe i kontrolery, w tym `JointTrajectoryController`.
- **MoveIt 2**: planowanie kinematyczne, sprawdzanie kolizji, `PlanningScene` i wykonanie przez kontroler.
- **RViz 2**: inżynierska wizualizacja modelu robota, sceny 3D, TF i zaplanowanych ruchów.
- **rosbag2**: rejestracja i odtwarzanie próbek diagnostycznych i percepcyjnych.

### 3.1. Minimalny słownik operatora

| Komenda / narzędzie | Zastosowanie |
| --- | --- |
| `source /opt/ros/jazzy/setup.bash` | Przygotowanie powłoki po instalacji Jazzy |
| `ros2 node list` / `ros2 node info NAZWA` | Inwentaryzacja węzłów |
| `ros2 topic list -t` / `ros2 topic echo TEMAT` | Odkrywanie i podgląd typowanych tematów |
| `ros2 topic hz TEMAT` / `ros2 topic bw TEMAT` | Częstotliwości i transfer |
| `ros2 interface show TYP` | Schemat wiadomości |
| `ros2 service list` / `ros2 action list -t` | Usługi i akcje |
| `ros2 param list` / `ros2 param get NODE PARAM` | Konfiguracja |
| `ros2 doctor --report` | Podstawowy raport diagnostyczny |
| `ros2 launch PAKIET PLIK.launch.py` | Start zestawu węzłów |
| `colcon build --symlink-install` | Kompilacja workspace |
| `rviz2` | Wizualizacja |
| `ros2 bag record ...` / `ros2 bag play ...` | Zapis/odtwarzanie danych |

Komendy są materiałem edukacyjnym. Uruchamianie programów, które obejmują urządzenia fizyczne, wymaga osobnego preflight; nie kopiować poleceń demonstracyjnych bez zrozumienia ich efektów.

### 3.2. Workspace i pakiety

Proponowana lokalizacja na NVMe, **nie** automatycznie istniejący katalog:

~~~text
/srv/vision-data/ros2_ws/
  src/             # sklonowane zależności i pakiety Vision
  build/           # pliki pośrednie colcon
  install/         # artefakty do source
  log/             # logi budowania
~~~

Pakiety własne (nazwy **robocze**) to m.in. `vision_description`, `vision_interfaces`, `vision_bringup`, `vision_scene`, `vision_motion_gateway` i `vision_workflow`. Nie każda funkcja wymaga osobnego procesu systemd ani osobnej aplikacji.

### 3.3. Trzy interfejsy obsługi

1. **Terminal** — diagnostyka, testy, parametry, build i start.
2. **RViz 2 + panel MoveIt 2** — konfiguracje J1–J7, cele 3D, trajektorie, widok przeszkód, podgląd TF/PointCloud2.
3. **Własny WebGUI Vision** — w przyszłości zadanie inspekcji, profil ECU, stany, zatwierdzanie, wyniki i zarządzanie kalibracją. Nie wystawia surowych komend CAN do użytkownika.

Inżynierski RViz nie jest panelem bezpieczeństwa i sam widok „bez kolizji” nie dopuszcza wykonania.

### 3.4. DDS, QoS, kontenery

Przykładowe ustawienia sesji testowej ROS:

~~~bash
export ROS_DOMAIN_ID=42
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
~~~

Są to parametry **izolacji logicznej**, nie bariera bezpieczeństwa. Kontener może nadal mieć dostęp do urządzeń, sieci hosta czy socketów, jeżeli administrator mu go udostępni. W testach offline: **bez** urządzenia CAN, bez `--privileged`, bez `/dev` robota i bez połączenia z domeną produkcyjną. Należy odizolować także endpointy akcji sterujących i automatyczny start.

W pierwszym zadaniu **audytujemy istniejący kontener ROS 2 wskazany przez użytkownika**, zamiast zakładać konieczność reinstalacji. Sprawdzamy jego obraz, architekturę, distro, ROS_DOMAIN_ID, network mode, urządzenia i zależności. Nie wykonujemy `pip install --break-system-packages` na hoście ani nie uruchamiamy skryptów instalacyjnych producenta bez audytu zależności.

## 4. NERO: dane wejściowe i oficjalny stos sterowania

### 4.1. Od diagnostyki do ruchu

Uproszczona ścieżka **docelowa**, wymagająca kontroli uprawnień:

~~~text
Vision Workflow / operator
    |
    v
Motion Gateway (walidacja celu i warunków)
    |
    v
MoveIt 2 (IK, PlanningScene, trajektoria)
    |
    v
ros2_control / JointTrajectoryController
    |
    v
agx_arm_ros / pyAgxArm / SocketCAN
    |
    v
AgileX NERO J1...J7
    ^
    |  feedback pozycji, prędkości, diagnostyki i błędów
    +---------------------------------------------------
~~~

Oficjalny sterownik obsługuje NERO; demo MoveIt można uruchomić **bez podłączonego robota**:

~~~bash
# Dopiero w izolowanym, zweryfikowanym workspace ROS 2:
ros2 launch agx_arm_description display.launch.py arm_type:=nero
ros2 launch agx_arm_moveit demo.launch.py arm_type:=nero
~~~

Powyższe nazwy i polecenia zweryfikowano w dokumentacji upstream AgileX. Nie stanowią wyniku testu na VENTUNO.

**Uwaga krytyczna:** w opisanych przez AgileX parametrach `auto_enable` i `control_enabled` wartości domyślne to `true`. Rozruch z dostępem do CAN lub launch łączący rzeczywisty sterownik i MoveIt może wywoływać skutki fizyczne. Demo offline i sterownik live muszą być wyraźnie rozdzielone, z osobnymi konfiguracjami i właścicielem CAN. „Przycisk Plan” w RViz nie jest zgodą na `Execute`.

### 4.2. Dane potrzebne do odczytu NERO

- Identyfikacja modelu `nero`; potwierdzenie firmware i zgodności wydania SDK/ROS.
- Połączenie USB-CAN/SocketCAN i rzeczywista nazwa interfejsu, bez założenia, że zawsze będzie to `can0`.
- Telemetria J1–J7: pozycje (radiany), prędkości (rad/s), momenty/effort jeśli udostępnione, napięcia, temperatury, błędy i stan napędów.
- Znaczniki czasu, jakość/świeżość odczytu i heartbeat; sprawdzenie reakcji na utratę magistrali.
- Odczyt `JointState` i transformacji TCP zgodny z faktyczną konfiguracją URDF.

Przykładowy odczyt tematu opisanego przez AgileX:

~~~bash
ros2 topic echo /feedback/joint_states
~~~

Nazwy tematów zależą od przestrzeni nazw i opcji uruchomienia; przed użyciem rzeczywistego sterownika zawsze wykonać `ros2 topic list -t`. Częstotliwość publikacji `pub_rate=200` opisana przez producenta nie jest gwarancją end-to-end 200 Hz na VENTUNO.

### 4.3. Dane do planowania i egzekucji

| Grupa | Co musi być znane |
| --- | --- |
| Kinematyka | zweryfikowany URDF, osie przegubów, kolejność, ograniczenia i zakresy J1–J7 |
| Semantyka | SRDF, grupa planowania `arm`, dopuszczalne samokolizje |
| Stan | aktualne pozycje, prędkości, poziom wiarygodności i czas pomiaru |
| Cel | 7 kątów albo `PoseStamped` TCP, układ odniesienia, orientacja i tolerancje |
| Ograniczenia | prędkość, przyspieszenie, obwiednie, zakazane konfiguracje, aktualny stan zatrzymania |
| Narzędzie | transformacje J7 → adapter/uchwyt/kamera, masa, środek ciężkości, modele kolizyjne |
| Scena | stół, ECU, złącza, mocowania, przeszkody, obszary nieobserwowane |
| Egzekucja | kontroler trajektorii, timeouty, potwierdzenie, blokada powtórek i resetu |
| Warunki ruchu | uprawnienie operatora, kwalifikacja środowiska, stan niezależnego zabezpieczenia |

ROS stosuje dla pozycji przegubów obrotowych radiany, a dla wymiarów pozycyjnych metry. WebGUI może prezentować stopnie i milimetry, ale zapisy wewnętrzne muszą mieć jednoznaczne jednostki.

**Przykład semantyki celu:** „Sony ma znaleźć się w zadanej pozycji i orientacji względem punktu na złączu ETC3”, a nie „J1=...° i J2=...°”. MoveIt rozwiązuje kinematykę odwrotną i szuka bezkolizyjnej ścieżki. NERO ma 7 DOF, więc zwykle mogą istnieć różne konfiguracje ramienia dające zbliżony cel TCP.

### 4.4. URDF, SRDF i geometria uchwytu

Model producenta obejmuje ramię, ale **nie** pełną docelową aparaturę. Musimy dodać własne linki/fixed joints i collision bodies: adapter J7 o profilu D, mocowanie Sony/Luxonis, obudowy, obiektyw w skrajnych konfiguracjach, prowadzenie przewodów i ewentualną termowizję. Dane prototypowe adaptera z wcześniejszych prób (np. średnica zaokrąglonej części ok. 39,8 mm, prosta ok. 17 mm, grubość 10 mm) **nie zastępują pomiaru i zatwierdzenia złożenia**.

Rozdzielamy:
- `visual geometry` — dokładny wygląd w RViz;
- `collision geometry` — uproszczone, lecz niezaniżone obwiednie bezpieczeństwa geometrycznego;
- `inertial` — właściwości dynamiczne z realną masą i środkiem ciężkości.

Zmiana uchwytu, obiektywu, wysunięcia zoomu lub przewodów zmienia obwiednię i może wymagać aktualizacji modelu narzędzia; nie należy maskować tego samą transformacją optyczną.

## 5. Wspólna geometria stanowiska: URDF, tf2 i kalibracja

Dla stanowiska proponujemy nadrzędny układ `table`, stały względem blatu. Konwencja początku i osi (np. narożnik przedni/lewy, osie wzdłuż blatu, +Z do góry) musi zostać jawnie opisana i zatwierdzona. Dokładne nazwy ramek producenta pozostają do odczytania z jego URDF.

Proponowany schemat logiczny (nie gotowe drzewo TF):

~~~text
table
  ├── robot_base
  │     └── [J1 ... J7] ── flange_j7
  │                         └── tool_mount
  │                             ├── sony_optical
  │                             └── luxonis_body
  │                                 ├── rgb_optical
  │                                 ├── left_optical
  │                                 └── right_optical
  └── ecu_etc3
~~~

Uwaga: w praktycznym tf2 **jedna ramka ma jednego rodzica**. Drzewo opisuje relacje transformacji, nie katalog obiektów; mapowanie na konkretny model musi wykluczyć dwa konkurencyjne źródła tego samego transformu.

Pozycję kamery względem stołu obliczamy z:

~~~text
T_table_camera(t) = T_table_base · T_base_J7(t) · T_J7_camera
~~~

Potrzebne są:
1. **Station extrinsics:** położenie i orientacja podstawy NERO względem `table` (6 DOF).
2. **Tool extrinsics:** transformacja J7 → Sony oraz J7 → Luxonis (osobno), wraz z wersją kalibracji.
3. **Robot state:** poprawne pozycje J1–J7 w chwili obserwacji.
4. **Camera intrinsics/extrinsics:** parametry RGB/stereo, distortion, baseline, model optyczny.
5. **ECU pose:** położenie i orientacja danego egzemplarza względem `table`, nie tylko jego nominalna obudowa.
6. **Timing:** zsynchronizowane znaczniki czasu oraz kontrola opóźnienia obrazu, głębi i pozycji robota.

Do kalibracji: fabryczna kalibracja Luxonis jako punkt wyjścia, osobne testy z wzorcem znanego wymiaru, kalibracja hand–eye J7 ↔ kamera przy użyciu wielu pozycji i weryfikacja world/base ↔ table. Wzorce drukowane i metody OpenCV/ChArUco są kandydatami, nie automatycznym dowodem dokładności. Po przeniesieniu stanowiska ponownie sprawdzamy transformację podstawy oraz testy metrologiczne.

**Zasada bramki:** brak transformacji, nieaktualna wersja kalibracji, rozbieżny `frame_id`, przeterminowany timestamp lub nieokreślona niepewność → `NOT_READY`. Nie zastępujemy nieznanych wartości zerami.

## 6. Luxonis: tor danych i model sceny

Oficjalny DepthAI ROS v3 jest kandydatem na pojedynczy proces-właściciel urządzenia USB OAK-D. Nie uruchamiamy równocześnie historycznego Camera Service i nowego sterownika na jednym USB.

Potrzebne wejścia:
- obraz RGB z `sensor_msgs/Image` i odpowiednie `CameraInfo`;
- głębia stereo (oraz kontrola jakości, confidence, ustawienia IR Dot/Flood);
- chmura `PointCloud2`, zachowane znaczniki czasu i `frame_id`;
- dane kalibracyjne, geometria rectified-left/optical frame i ekstrynsyki względem J7.

Proponowany przepływ:

~~~text
RGB + stereo + camera_info
    ↓
głębia / PointCloud2
    ↓
filtry jakości + synchronizacja + tf2
    ↓
lokalizacja ECU, kontrola profilu, przeszkody
    ↓
PlanningScene / modele kolizyjne / opcjonalny OctoMap
    ↓
MoveIt 2 (planowanie, nie automatyczna zgoda na ruch)
~~~

MoveIt udostępnia mechanizmy wprowadzania chmur punktów i obrazów głębi do planowania. Nie oznacza to, że dynamiczna przeszkoda automatycznie zatrzyma wykonywaną trajektorię: strategia monitoringu, anulowania i sprawdzonego zatrzymania jest osobnym zadaniem.

**Eye-in-Hand:** Luxonis obok Sony na J7 może zasłaniać część przestrzeni podczas ruchu. Jedna ruchoma kamera nie zapewnia kompletnego, niezależnego nadzoru nad ludźmi i całą strefą pracy. Obszary niewidoczne lub słabo zmierzone nie są automatycznie puste. Przy braku pokrycia sceny konieczna jest odmowa ruchu albo dodatkowe zweryfikowane dane/scenariusz obserwacji; późniejsza kamera stała pozostaje opcją do oceny.

**Margines geometryczny:** obwiednie uwzględniają niepewność depth, tf2, montażu, powtarzalności robota, przewody i wymaganą odległość od przeszkody. Nie ustalamy fikcyjnego marginesu liczbowego przed pomiarami i oceną ryzyka.

## 7. Dane stanowiska, narzędzi i profilu ECU

### 7.1. Dzielimy dane na trzy niezależne klasy

| Warstwa | Co zawiera | Zmiana przy relokacji? |
| --- | --- | --- |
| `RobotConfig` | model/firmware NERO, ograniczenia osi, sterowniki, wersje | zasadniczo nie, chyba że zmienia się hardware/runtime |
| `StationProfile + Calibration` | stół, baza, stałe przeszkody, strefy, offsety, kalibracja | **tak: przegląd i nowa kwalifikacja** |
| `ECUProfile + InspectionPlan` | cechy typu ECU, geometryczne maksimum, złącza, cele zdjęciowe względem ECU | **nie**, jeśli profil i procedura pozostają właściwe |
| `SessionState` | położenie egzemplarza, bieżące obserwacje, scena, zdjęcia, wyniki | **nowa sesja** na każde uruchomienie |

### 7.2. Lista pomiarowa dla LAB i PROD

- Blat: długość/szerokość, rzeczywista płaszczyzna robocza, krawędzie i obszary poza stołem.
- Podstawa NERO: (x,y,z,rx,ry,rz) względem `table`, sztywność mocowania, odkształcenie przy obciążeniu.
- Przeszkody stałe: ściana, oświetlenie, wsporniki, zaciski, urządzenia i elementy poza blatem w zasięgu.
- Zespół J7: adapter profilu D, Sony A6100 + E PZ 16–50, Luxonis, przewody; bryły, masa, środek ciężkości, transformacje.
- Gniazda i porządek prowadzenia kabli; możliwe zaplątanie/napinanie przy obrocie osi.
- Strefa dopuszczalnego odkładania ECU, zakazane obszary, wysokości dopuszczalnych przeszkód.
- Weryfikacja planowanej strefy i dostępności operatora do STOP oraz zabezpieczeń.

**Stan omawianego stołu docelowego:** rozważano różne wymiary i montaż przy dłuższej przedniej krawędzi; **żaden wymiar nie jest tutaj deklarowany jako zatwierdzony**. W LAB mocowanie jest tymczasowe, w PROD planowane przykręcenie przez fabryczne otwory. Zmiana sztywności i punktu mocowania wymaga nowych testów; nie wolno uznawać laboratoryjnego dowodu za automatyczne dopuszczenie stanowiska docelowego.

### 7.3. Zasada przenośności planu inspekcji

Nie zapisujemy zdjęcia „w punkcie X=... względem starego stołu”. Cel to np. „oś Sony względem `ecu_etc3/connector_A`, dystans i orientacja obserwacji, określony obszar obrazu”. Transformacja aktywnego ECU i kalibracja stanowiska przeliczają ten cel do ramki robota.

Przenosimy **wiedzę o ECU**, nie gotowe trajektorie. Po każdej relokacji planujemy i walidujemy trajektorie ponownie.

## 8. Pełny workflow pierwszego ETC3 (najpierw offline)

1. **Operator deklaruje ETC3 i wariant**; `ECUProfile.v1` jest wersjonowany i zawiera źródła wymiarów, szczególnie maksymalną wysokość.
2. Kamera lub odtworzone dane weryfikują cechy: dwie czarne i jedna szara wtyczka to rozróżnienie robocze, a nie dowód numeru katalogowego.
3. `SceneObservation.v1` określa bieżącą pozycję ECU, orientację, obrys, widoczne elementy i niepewność, z `frame_id`, timestamp i identyfikatorem kalibracji.
4. System buduje zachowawczą scenę z nominalnego zweryfikowanego profilu oraz nowych obserwacji. Nieznane fragmenty nie są uznawane za wolną przestrzeń.
5. Plan inspekcji generuje **cele Sony względem ECU**, nie względem blatu.
6. Motion Gateway żąda planów MoveIt 2; sprawdza aktualność sceny, ograniczenia, zgodność narzędzia i status.
7. W LAB **offline** przeglądamy i zapisujemy plany, bez wydawania komend do NERO.
8. Po osobnym dopuszczeniu w przyszłości NERO pozycjonuje aparaty, Sony wykonuje zdjęcia, Vision kontroluje ostrość, ekspozycję, pokrycie i powtórki.
9. Wyniki wraz z oryginałami, wersjami profilu/kalibracji/modelu i hashami są archiwizowane. AI Platform otrzymuje zadania przez istniejący Resource Manager, nie steruje CAN.

Proponowane kontrakty semantyczne (nie wdrożone): `ECUProfile.v1`, `SceneObservation.v1`, `MotionRequest.v1`, `CaptureRequest.v1`, `CaptureResult.v1`, `AIJob.v1`, `InspectionResult.v1`.

## 9. Architektura logiczna i podział sprzętu

~~~text
                      VISION HMI / WORKFLOW
                     sesje, decyzje, recovery
                              |
          +-------------------+------------------+
          |                                      |
    ECU Catalog /                          AI Bridge / Storage
    Scene Verification                          |
          |                                      v
    Motion Gateway                        AI Platform / RM
          |                               Minisforum / RTX
          v
   VENTUNO Q — ROS 2
   +------------------------------------------------+
   | MoveIt 2    tf2/URDF    ros2_control           |
   | AgileX ROS 2 → CAN → NERO                     |
   | Luxonis DepthAI ROS → RGB-D/PointCloud2        |
   | Sony adapter → capture/status                  |
   | rosbag2/RViz/testy                             |
   +------------------------------------------------+

  Niezależny tor bezpieczeństwa: odrębny projekt fizyczny,
  którego działanie nie zależy od ROS 2, AI ani WebGUI.
~~~

Granica odpowiedzialności:
- ROS/MoveIt: model i planowanie ruchu, wymiana danych robotycznych.
- Workflow: stan sesji, wymagania jakościowe, operator i polityka błędów.
- Motion Gateway: jedna autoryzowana **programowa** droga zlecania ruchu, sprawdzenie stanu, blokada nowych zadań; **nie** funkcja bezpieczeństwa niezależnego.
- Sony: adapter specyficzny dla aparatu, bez kopiowania Camera Service z historycznych prób.
- AI Platform: obciążenia GPU, analiza i modele, nie kontroler napędów.

Wyłączność CAN nie może opierać się wyłącznie na umowie aplikacyjnej. Wymagane są kontrola praw do interfejsu, rozdzielenie procesów/domen, brak równoległego SDK z dostępem sterującym i testy negatywne.

## 10. Portable Station Architecture — LAB teraz, PROD później

### 10.1. Dwa profile, jeden kod

~~~text
config/
  robot/nero.yaml
  tooling/sony_luxonis.yaml
  stations/laboratory.yaml
  stations/production.yaml
calibration/
  laboratory/
  production/
ecu_profiles/
  etc3/
    profile.yaml
~~~

To **proponowana** struktura, a nie potwierdzone pliki w repo. Profil stanowiska zawiera model stołu, transformację `table → robot_base`, przeszkody stałe, dozwolony wolumen, identyfikator użytej kalibracji, identyfikator zestawu narzędzi, datę kwalifikacji i status. Nigdy nie przenosimy tych wartości do pliku profilu ECU.

Schemat kontrolny, nie działająca konfiguracja:

~~~yaml
schema_version: 1
station_id: laboratory
world_frame: table
station_geometry_revision: null
robot_base_transform: null
tooling_revision: null
calibration_revision: null
collision_scene_revision: null
validation:
  state: NOT_READY
  approved_for_motion: false
~~~

Wszystkie `null` są **brakami danych**, a nie wartościami domyślnymi. Przy starcie z niewypełnionym lub niezatwierdzonym profilem możliwy jest tylko tryb diagnostyczny/offline. Nie wolno dziedziczyć ostatnich wartości z innego stanowiska.

Proponowane przyszłe wywołania launch (plików jeszcze nie ma):

~~~bash
ros2 launch vision_bringup vision.launch.py station:=laboratory
ros2 launch vision_bringup vision.launch.py station:=production
~~~

Wybór środowiska w UI wymaga bezruchu, zakończenia sesji, ponownego preflight i jest odseparowany od nieodwracalnego uprawnienia do ruchu.

### 10.2. Procedura relokacji LAB → PROD

1. Zakończyć sesje i odciąć możliwość wydawania nowych komend ruchu; zabezpieczyć sprzęt do demontażu.
2. Zamocować NERO zgodnie z dokumentacją i wymaganiami wynikającymi z analizy ryzyka.
3. Zinwentaryzować wymiary, przeszkody, strefy i prowadzenie przewodów; zrewidować collision geometry.
4. Pomierzyć transformację podstawy NERO i zweryfikować orientację ramki `table`.
5. Zweryfikować sztywność zespołu J7, ekstrynsyki Sony i Luxonis, geometrię obiektywu.
6. Wykonać lub potwierdzić kalibrację świata i hand–eye, walidację wzorców depth/XYZ.
7. Zbudować nową wersję `PlanningScene`, ponownie policzyć zasięgi i wszystkie cele inspekcji; nie używać bezrefleksyjnie starych trajektorii.
8. Przeprowadzić testy offline, negatywne i awaryjne; sprawdzić niezależny tor bezpieczeństwa, procedury STOP i zanik zasilania.
9. Zatwierdzić `production` poprzez jawne kryteria kwalifikacji; dopiero po nich rozważyć pierwsze ograniczone ruchy fizyczne za zgodą operatora.
10. Zachować stare artefakty LAB tylko jako historię testową, bez automatycznego „fallback” podczas produkcji.

Wymiana samej kamery lub uchwytu także może unieważnić kalibrację narzędzia, nawet bez przeniesienia stołu. Wyzwalacze ponownej kwalifikacji muszą być jawne.

## 11. Bezpieczeństwo i niepewność

**Rosnące ryzyko nie może być maskowane poprawnym planem matematycznym.** MoveIt sprawdza tylko opisane ograniczenia i przeszkody. TF może być błędne, scena niekompletna, kabel niewymodelowany, mocowanie niestabilne, a człowiek poza polem widzenia Eye-in-Hand.

| Sytuacja | Zachowanie wymagane od Vision |
| --- | --- |
| Brak aktualnego `JointState`, CAN lub statusu sterownika | `NOT_READY/FAULT`, brak nowych zadań, brak automatycznego wznowienia |
| Brak kalibracji lub błędna ramka TF | Blokada planowania/wykonania zależnego od geometrii |
| Nieznane/niewidoczne miejsce kolizji | Zawężenie przestrzeni lub odmowa ruchu |
| Zmiana sceny po planowaniu | Unieważnienie lub ponowne zweryfikowanie planu; nie zakładać, że stary jest bezpieczny |
| Software STOP | Zatrzask, rozróżnienie żądania / wysłania / potwierdzenia / rzeczywistego bezruchu |
| Power failure | Blokada nowych zadań; parkowanie tylko przy osobno zweryfikowanych warunkach, STOP ma pierwszeństwo |
| Odcięcie zasilania ramienia | Uwzględnić ryzyko opadnięcia; **nie** traktować prostego odcięcia 24 V jako uniwersalnej procedury bezpieczeństwa |
| Restart ROS, kontenera lub Linux | `NOT_READY`; konieczny ponowny preflight, nigdy auto-restart trajektorii |
| Zmiana LAB/PROD | `NOT_READY` do czasu aktualizacji profilu i walidacji |

Stream Deck Plus zapewnił wcześniej ścieżkę **programowego** STOP, ale nie jest niezależnym E-STOP. Grzybek podłączony jedynie przez GPIO/Linux/CAN także nim nie jest. Niezależna funkcja zatrzymania i podtrzymania wymaga oceny ryzyka, weryfikacji możliwości NERO i odpowiedniego rozwiązania sprzętowego. Obowiązuje [ADR-VISION-ROBOT-001](ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md).

## 12. Plan testów, kryteria PASS i kolejność implementacji

| Etap | Przedmiot testu | Dowód odbioru | Ruch fizyczny? |
| --- | --- | --- | --- |
| 0 | Audyt istniejącego kontenera ROS 2, urządzeń i sieci | wersje, architektura, kontener i brak dostępu do napędów | **Nie** |
| 1 | ROS 2 Jazzy na ARM64, podstawowe węzły, DDS, colcon | komunikaty, diagnostyka, odtwarzalny build | **Nie** |
| 2 | Oficjalny NERO w RViz + MoveIt demo | J1–J7, ograniczenia, IK, pozytywne i negatywne przypadki kolizji | **Nie** |
| 3 | Model stanowiska LAB i tooling J7 | poprawne TF, geometryczne przypadki testowe i planowanie z przeszkodami | **Nie** |
| 4 | DepthAI ROS v3, RGB-D, TF, synchronizacja | próbki, kalibracja, błąd XYZ, wersje parametrów, rejestr rosbag | **Nie** |
| 5 | Profil ETC3 + sesja offline | pełna ścieżka: deklaracja → weryfikacja → plan → wynik/odmowa → archiwizacja | **Nie** |
| 6 | Read-only integracja ROS 2 z rzeczywistym NERO | zgodność 7 osi ze SDK, błędy i timeouts, brak autowłączenia napędów | **Nie** |
| 7 | Zamknięcie oceny bezpieczeństwa, ograniczony test ruchu | jawna zgoda, test zatrzymania, kontrola pozycji, recovery, logi | **Dopiero po bramkach** |

Obciążenie VENTUNO (CPU, RAM, I/O), latency kamera–TF–MoveIt, przepływność rosbag i stabilność USB mierzymy w testach, zamiast deklarować wartości z dokumentacji dostawców jako wynik lokalny.

### 12.1. Rejestrowanie prób

W izolacji zapisujemy ustandaryzowany `rosbag2`: `/tf`, `/tf_static`, pozycje przegubów, wymagane tematy RGB/depth/CameraInfo/PointCloud2, statusy, wersję konfiguracji, oznaczenie profilu, znacznik UTC i clock monotoniczny (tam gdzie dostępny). Surowe obrazy i logi pozostają na lokalnym NVMe, nie w publicznym Git.

Odtwarzanie `ros2 bag play` **tylko bez połączenia z działającym robotem**: nagrania mogą zawierać tematy poleceń i ich ponowna publikacja mogłaby spowodować ruch.

### 12.2. Pierwsze polecenia wyłącznie do edukacyjnej diagnostyki

~~~bash
# W prawidłowo odizolowanym kontenerze/środowisku:
source /opt/ros/jazzy/setup.bash
ros2 doctor --report
ros2 node list
ros2 topic list -t
ros2 action list -t

# Dopiero po weryfikacji dostępności pakietów AgileX:
ros2 launch agx_arm_moveit demo.launch.py arm_type:=nero
~~~

Zapisujemy wynik do raportu audytu, a nie instalujemy „na ślepo” sterownika live. Nie wykonywać `Plan & Execute` do rzeczywistego kontrolera.

## 13. Rejestr pytań i decyzji do zamknięcia

| Temat | Status | Dalsza decyzja / dowód |
| --- | --- | --- |
| Docelowa wersja Docker/ROS/DDS na VENTUNO | `NOT VALIDATED` | audyt działającego środowiska |
| Konkretne wersje AgileX ROS, pyAgxArm, MoveIt 2, DepthAI ROS | `NOT VALIDATED` | macierz kompatybilności i pinowanie commitów |
| Niezawodna pojedyncza ścieżka CAN / ograniczenie praw | `PROPOSED` | architektura i test omijania interlocku |
| Fizyczna geometria podstawy LAB/PROD i wymiary stołu | `OPEN` | pomiary po wyborze i zamocowaniu |
| Model collision aparatu, adaptera J7 i przewodów | `OPEN` | CAD + pomiary, masa i środek ciężkości |
| Kalibracja hand–eye, bazowa, rectified-left, dokładność XYZ | `NOT VALIDATED` | niezależne wzorce i próby powtarzalności |
| Zakres widoczności Eye-in-Hand podczas ruchu | `OPEN` | analiza okluzji / ewentualna kamera stała |
| Bezpieczny margines od ECU i przeszkód | `OPEN` | budżet niepewności + ocena ryzyka |
| Maksymalna wysokość ETC3 i zweryfikowane obrysy | `OPEN` | karta pomiarów z 14.11.2026 i dodatkowa walidacja |
| STOP fizyczny i ryzyko opadnięcia NERO | `BLOCKED` dla autonomii | osobny projekt i weryfikacja zabezpieczeń |
| Parkowanie podczas zaniku zasilania UPS | `PROPOSED` | testy przy bezpiecznych warunkach; STOP zawsze ważniejszy |
| Czy i kiedy wdrażać Vision Workflow/Core | `AFTER ROS POC` | najpierw bramki 0–5, potem kontrakty i plan wykonania |

## 14. Źródła referencyjne i granice wiarygodności

### Nasze repozytorium
- [Vision — fundament 14.11.2026](VISION_FOUNDATION_2026-11-14.md).
- [Vision — zapis rozmowy założycielskiej 14.11.2026](VISION_ARCHITECTURE_DISCUSSION_2026-11-14.md).
- [ADR STOP NERO](ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md).
- [AS-BUILT 10.11.2026](../operations/VISION_AS_BUILT_2026-11-10.md).
- [Polityka wydań i zgód](../operations/RELEASE_GATES_2026-11-10.md).
- [PR #28 — fundament systemu](https://github.com/autoklinika/Vision/pull/28).

### Dokumentacja producentów i ROS
- [ROS 2 Jazzy — tutoriale](https://docs.ros.org/en/jazzy/Tutorials.html).
- [AgileX agx_arm_ros, gałąź ros2](https://github.com/agilexrobotics/agx_arm_ros/tree/ros2), [README EN](https://github.com/agilexrobotics/agx_arm_ros/blob/ros2/README_EN.md), [MoveIt demo](https://github.com/agilexrobotics/agx_arm_ros/blob/ros2/src/agx_arm_moveit/README.md).
- [Luxonis DepthAI ROS](https://github.com/luxonis/depthai-ros), [dokumentacja ROS v3](https://docs.luxonis.com/software-v3/depthai/ros/).
- [MoveIt 2](https://moveit.picknik.ai/), [ros2_control](https://control.ros.org/), [tf2](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Tf2.html).
- [OpenCV hand-eye calibration](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html).

**Uwaga dotycząca źródeł:** aktualne instrukcje upstream mogą się zmieniać; wdrożenie wymaga przypięcia wersji/commitów i osobnego raportu zgodności z VENTUNO. Nie kopiować instrukcji instalacji do produkcyjnego systemu bez audytu.

---

## 15. Konkluzja i następne działanie

**Najpierw poznajemy ROS 2 i NERO w bezpiecznej symulacji, wykorzystując już wskazane przez operatora środowisko Docker po uprzednim audycie.** Wprowadzamy architekturę `LAB → PROD`, w której zmiana stołu i położenia robota aktualizuje `StationProfile/Calibration`, nie kod sterownika i nie plany ECU. Pierwsza pełna sesja dotyczy ETC3 i zaczyna się offline. Ruch fizyczny pozostaje odrębnym etapem, zależnym od domknięcia geometrii oraz niezależnych zabezpieczeń.

**Zakres niniejszego raportu:** uporządkowanie i uszczegółowienie ustaleń z rozmowy. Nie uruchomiono żadnego procesu Vision, sterownika ROS, napędów, migawki ani komponentu AI.
