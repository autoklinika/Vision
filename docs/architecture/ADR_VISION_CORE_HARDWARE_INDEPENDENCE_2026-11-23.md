# ADR-VISION-CORE-001 — Hardware Independence & Modular Architecture

- **Data decyzji:** 2026-11-23.
- **Status:** **ACCEPTED** — kierunek zaakceptowany przez właściciela Vision przed rozpoczęciem implementacji Core.
- **Zakres:** Vision Core, ROS 2, MoveIt 2, kamery RGB-D, aparaty fotograficzne, roboty i profile stanowiska.
- **Punkt odniesienia:** [Vision Guided Positioning V1](../baselines/VISION_GUIDED_POSITIONING_V1_2026-11-23.md), odebrany laboratoryjnie.
- **Rodzaj zmiany:** dokumentacja i kontrakt architektoniczny; bez uruchamiania lub modyfikowania sprzętu.

## Kontekst

Vision to platforma inspekcji PCB/ECU, nie aplikacja przywiązana na stałe do konkretnego zestawu Luxonis OAK-D Pro AF, Sony A6000 i AgileX NERO. Pierwsza konfiguracja VGP V1 wykazała w laboratorium fizyczne ustawienie aparatu nad ETC3 i PTM na podstawie aktualnego obrazu RGB-D, z planowaniem i wykonaniem przez standardowe MoveIt 2 / AgileX.

Zmiana aparatu, obiektywu, sensora RGB-D, robota albo mocowania **nie może wymuszać przebudowy Vision Core ani scenariuszy inspekcyjnych**. Wymienność oprogramowania nie zwalnia z ponownej walidacji geometrii, kalibracji, zasięgu i zdolności sprzętowych.

## Decyzja

**Vision Core jest niezależnym sprzętowo koordynatorem inspekcji**. Zna kontrakty i możliwości urządzeń, a nie ich producenta, transport lub komendy niskiego poziomu.

1. **Core odpowiada za:** sesje, deklarację typu ECU przez operatora, Workflow, wybór punktów fotografowania, wersje obserwacji i planów, kontrolę gotowości, wyniki oraz archiwizację.
2. **Core nie steruje bezpośrednio urządzeniami:** nie wysyła poleceń CAN, komend przegubów AgileX ani natywnych wywołań USB/PTP/DepthAI. Nie odtwarza własnego wykonawcy trajektorii C8/C9.
3. **ROS 2 jest warstwą integracji:** oficjalne sterowniki dostarczają obraz, Depth, CameraInfo, PointCloud2, stany, tf2 i interfejsy akcji. MoveIt 2 jest właścicielem planowania, IK, kontroli kolizji i zlecania wykonania przez właściwy ros2_control / sterownik producenta.
4. **Interfejsy i profile oddzielają kod od sprzętu:** wymiana urządzenia zmienia adapter/driver i odpowiedni profil, a nie kod scenariusza. Adaptery powinny być cienkie; nie wprowadzamy konkurencyjnego, ogólnego Camera Service ani Perception Engine.
5. **Stała geometria stanowiska jest wersjonowana i zamrożona po odbiorze.** Obiekt ECU pozostaje dynamiczny: aktualne położenie, obrót, obwiednia, wysokości i punkty inspekcyjne pochodzą z bieżącej obserwacji Luxonis lub zamiennego sensora.
6. **Plan jest związany z kontekstem.** Zmiana obiektu, sceny, kalibracji, narzędzia, robota albo nieaktualne dane unieważniają możliwość wykonania wcześniej wyliczonej trajektorii. Brak danych oznacza NOT_READY (fail-closed).
7. **Obowiązkowa bramka zakończenia etapu.** Vision Core nie rozpoczyna etapu zależnego, dopóki nie zweryfikuje, że wszystkie obowiązkowe warunki poprzedzających go etapów zostały spełnione. Samo przyjęcie polecenia przez usługę nie jest potwierdzeniem ukończenia.

## Kontrakty logiczne

| Kontrakt | Wymagane znaczenie | Istniejąca realizacja |
| --- | --- | --- |
| VisionSensor | RGB, CameraInfo, opcjonalna metryczna głębia i PointCloud2, frame_id, timestamp, stan kalibracji i jakość | Oficjalny DepthAI ROS 2 v3 lub inny zgodny driver |
| CaptureDevice | Zdjęcie, potwierdzenie wyzwolenia, obsługa AF/zoom/RAW, transfer i weryfikacja pliku | Adapter Sony lub innego aparatu; PTP/Wi-Fi/USB są detalami adaptera |
| MotionPlanner / Robot | Stany J1–Jn, TF, IK, aktualna scena kolizyjna, plan, wykonanie/cancel i feedback | MoveIt 2, ros2_control, sterownik danego robota |
| StationGeometry | Stałe ramki, stół, mocowania, kolizje statyczne, PARK, identyfikator zatwierdzonego profilu | StationProfile, tf2, PlanningScene |
| InspectionObject | Deklarowany typ ECU, obserwowana pozycja, obwiednia, poziom pewności i lokalne punkty zdjęć | Algorytmy specyficzne dla ECU korzystające z danych ROS 2 |

Są to **kontrakty funkcjonalne**, nie obowiązek tworzenia dodatkowego procesu lub mikroserwisu dla każdego komponentu. Preferujemy istniejące wiadomości, tematy, serwisy i akcje ROS 2.

## Wersjonowane profile

| Profil | Co definiuje |
| --- | --- |
| StationProfile | Stół, world/table/base, położenie NERO i Luxonis, stałe przeszkody, strefy i PARK |
| VisionSensorProfile | Driver, tematy, frame_id, intrinsics, extrinsics, synchronizacja RGB/depth, rozdzielczość i QA |
| CaptureDeviceProfile | Funkcje migawki, RAW/JPEG, AF, zoom, parametry akwizycji, bufor, transport i potwierdzenie transferu |
| ToolProfile | Korpus + obiektyw + adapter, geometria kolizyjna, masa, TCP, oś optyczna, mocowanie do link7 |
| RobotProfile | URDF/SRDF, grupa MoveIt, limity osi, kontroler, obsługa HOLD, PARK i zgodność wykonania |
| ECUProfile | Tożsamość zadeklarowana przez operatora, wymagane ujęcia, tolerancje, cechy i kryteria jakości |

Każdy profil powinien mieć schema_version, identyfikator, rewizję, wymagane capabilities, zależności kalibracyjne i status odbioru. Nazwy tematów, ramek i grup MoveIt są wybierane z profilu — nie są na stałe wpisane w Workflow.

## Capability-based selection

Scenariusz określa wymagania, np. metryczne RGB-D z ważną transformacją do stołu, wyzwolenie zdjęcia, RAW, autofocus, planowanie kolizyjne albo świeży stan robota. Core sprawdza dostępne możliwości urządzeń **przed** użyciem.

- Kamera 2D bez Depth nie przechodzi scenariusza wymagającego XYZ.
- Aparat bez RAW nie realizuje scenariusza wymagającego RAW.
- Kamera wykryta przez USB, lecz bez ważnego CameraInfo/TF nie uzyskuje statusu READY.
- Niezgodność toola, limitów robota, stanu sceny lub brak bieżącego feedbacku blokuje wykonanie; nie podstawiamy domyślnych współrzędnych.
- Typ ECU jest deklarowany przez operatora, a system sprawdza zgodność i wyznacza bieżącą pozycję zamiast niejawnie zgadywać tożsamość.

## Skutki wymiany sprzętu

| Zmiana | Aktualizujemy i weryfikujemy | Nie przepisujemy |
| --- | --- | --- |
| Sony A6000 → inny aparat | Adapter zdjęciowy, CaptureDeviceProfile, ToolProfile, oś optyczna/TCP, kolizje, akwizycja | Vision Core, scenariusze ECU |
| Obiektyw Sony → inny | Optics/ToolProfile, pole widzenia, odległość robocza, TCP, bryła i masa | Workflow ECU, driver NERO |
| Luxonis → inna kamera RGB-D | ROS 2 driver, VisionSensorProfile, intrinsics/extrinsics, synchronizacja, TF, QA 3D | Core, MoveIt, scenariusze zdjęć |
| NERO → inny robot | RobotProfile, URDF/SRDF, MoveIt, ros2_control, geometria i odbiór ruchu/PARK | Koordynacja inspekcji i definicje ECU |
| ETC3 → PTM | Dynamiczny obiekt PlanningScene, aktualna obserwacja oraz ECUProfile | Stały StationProfile, Core i warstwa ruchu |

Zmiana elementu geometrycznego **unieważnia odpowiednie kalibracje i poprzednie plany**, ale nie stanowi powodu do ponownej implementacji Core. Trajektorie nie są automatycznie przenoszone między robotami, toolami lub stanowiskami.

## Identyfikacja kontekstu operacji

Każda sesja/obserwacja/plan musi znać co najmniej: session_id, station_profile_revision, vision_sensor_revision, capture_device_revision, tool_profile_revision, robot_profile_revision, scene_revision, observation_timestamp i frame_id.

Przed wykonaniem Core potwierdza, że bieżący kontekst jest zgodny z kontekstem planowania. Przesunięcie ECU, zmiana sensora, nowy obiektyw, inny robot lub utrata ważności obserwacji wymagają nowego planu i kontroli kolizji. Nie wznawiamy automatycznie wcześniejszego ruchu.

## Nadzór Workflow: obowiązkowe bramki etapów

**Reguła nadrzędna: żaden etap scenariusza nie może rozpocząć się przed otrzymaniem i zweryfikowaniem przez Core potwierdzenia wykonania wszystkich wymaganych warunków jego poprzedników.** Core deleguje zadania do właściwych adapterów/akcji ROS 2, ale pozostaje właścicielem stanu sesji i decyzji o przejściu do następnego etapu.

1. **Jawna maszyna stanów.** Każda instancja etapu ma identyfikator i stan co najmniej: PENDING, READY, RUNNING, SUCCEEDED, FAILED, CANCELLED, BLOCKED lub TIMED_OUT. Przejście do SUCCEEDED wymaga wyników potwierdzonych przez określone dla etapu kryteria akceptacji.
2. **Odróżnienie ACK od wyniku.** Przyjęcie żądania, uruchomienie akcji albo odebranie feedbacku ROS 2 nie oznacza sukcesu. Przykładowo ruch wymaga terminalnego SUCCEEDED oraz sprawdzenia rzeczywistego stanu robota; zdjęcie wymaga potwierdzenia zapisu i integralności pliku, a lokalizacja ECU — aktualnej obserwacji z wymaganą jakością.
3. **Kontrakt potwierdzenia.** Wynik musi być powiązany z session_id, step_id, request_id/correlation_id, czasem wykonania, wersjami aktywnych profili i sceny oraz wymaganymi danymi dowodowymi. Wyniki przeterminowane lub odnoszące się do innego kontekstu nie otwierają bramki.
4. **Tylko spełnione zależności.** Core uruchamia następny krok wyłącznie wtedy, gdy wszystkie jego wymagane zależności mają zweryfikowany status SUCCEEDED. Dopuszczamy niezależne etapy równoległe tylko przy jawnie zdefiniowanym grafie zależności; następny etap nie może ominąć żadnej obowiązkowej bramki.
5. **Błędy, timeout i anulowanie.** FAILED, BLOCKED, TIMED_OUT, CANCELLED, brak wymaganych wyników lub zmiana konfiguracji zatrzymują automatyczne przejście. Core rejestruje przyczynę, anuluje dalszą dyspozycję zadań i stosuje właściwą dla stanu procedurę HOLD/odzyskiwania. Nie zakłada, że zawsze wolno automatycznie wykonać PARK po błędzie.
6. **Powtórzenia i wznowienie.** Retry jest jawnie dozwolony tylko dla etapów, których skutki można bezpiecznie rozpoznać i skontrolować. Nie ponawiamy automatycznie poleceń ruchu ani migawki po niejednoznacznym timeout. Po restarcie Core odtwarza dziennik sesji, uzgadnia stan faktyczny usług i sprzętu oraz wymaga nowej walidacji przed wznowieniem.
7. **Dziennik audytowy.** Każda dyspozycja, odpowiedź, przejście stanu i odmowa przejścia trafiają do trwałego dziennika sesji. Core zapisuje *dlaczego* krok został uznany za zakończony i który wynik pozwolił otworzyć następną bramkę.

Bramka Workflow jest kontrolą **aplikacyjną**; nie zastępuje nadzoru trajektorii w MoveIt 2/sterowniku robota ani przyjętej na stanowisku procedury HOLD.

## Zakres Vision Core 0.1

Pierwszy Workflow: **deklaracja ECU → obserwacja → dynamiczna scena → plan → kontrola gotowości → wykonanie pod nadzorem → wynik → PARK**. Integracja rzeczywistego wyzwalania i transferu zdjęć Sony jest niezależnym kolejnym etapem. Nie blokujemy budowy Core na oczekiwanie na pełną automatyzację aparatu.

## Minimalne testy architektoniczne

1. Dwa symulowane źródła RGB-D z różnymi tematami/ramkami — identyczny kod scenariusza.
2. Dwa mocki aparatu o różnych capabilities — te same ujęcia, jawne odrzucenie nieobsługiwanego RAW/AF.
3. Zmiana ToolProfile wymusza ponowną aktualizację geometrii i planowania.
4. Przemieszczenie ECU unieważnia stary plan i aktualizuje PlanningScene.
5. Nowy RobotProfile nie zmienia specyfikacji inspekcji ECU, ale wymaga walidacji ograniczeń i wykonania.
6. Brak depth, CameraInfo, TF albo zbyt stary timestamp daje NOT_READY — bez ruchu.
7. Testy offline nie wysyłają CAN; ruch rzeczywisty wymaga aktualnych enkoderów i nadzoru operatora.
8. ACK przyjęcia zadania bez terminalnego sukcesu albo bez kompletu wymaganych wyników nie odblokowuje kolejnego etapu.
9. FAILED, TIMED_OUT, CANCELLED, wynik niezgodny z session_id/scene_revision i zmiana konfiguracji blokują dalszy Workflow; nie ma automatycznego wznowienia ruchu.
10. Po restarcie Core nie powtarza bezwarunkowo ostatniej akcji; odczytuje dziennik i rzeczywiste stany usług, a następnie ponownie sprawdza warunki wejścia.


## Konsekwencje i ograniczenia

**Korzyści:** niezależny rozwój fotografii, perception specyficznej dla ECU i robotyki, wymienne komponenty, mniej regresji i prostsze testy Replay.

**Koszty:** kontrakty, kompatybilność profili, adaptery i walidacja metrologii po zmianach sprzętowych.

**Granice:** VGP V1 to sukces laboratoryjny, nie metrologicznie potwierdzone 5 mm ani produkcyjne bezpieczeństwo. Programowe HOLD pozostaje przyjętą konwencją pracy nadzorowanej w laboratorium. Ten ADR nie tworzy nowej usługi, nie uruchamia ruchu i nie zmienia zamrożonej konfiguracji VGP V1.

## Powiązania

- [Vision Guided Positioning V1](../baselines/VISION_GUIDED_POSITIONING_V1_2026-11-23.md)
- [Fundament Vision](VISION_FOUNDATION_2026-11-14.md)
- [ADR-VISION-STATION-001 — LAB/PROD](ADR_VISION_PORTABLE_STATION_LAB_PROD_2026-11-16.md)
- [Polityka repozytorium](../process/REPOSITORY_HYGIENE_V1.md)

**ADR-VISION-CORE-001 obowiązuje jako fundament wszystkich przyszłych modułów Vision Core.** Wyjątki zależne od konkretnej marki sprzętu wymagają osobnego uzasadnienia architektonicznego.
