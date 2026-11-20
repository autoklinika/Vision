# C7 V1 — Vision Perception → Photo Viewpoints → MoveIt 2 IK/Collision, LAB

**Stan 20.11.2026:** integracja usług laboratoryjnych działa na VENTUNO Q w izolowanej domenie ROS 2. Trajektorie są tylko planowane, nie wykonywane. Pełna walidacja C7/C8 i dopuszczenie ruchu nadal niezatwierdzone.

## Co działa

1. **Wejście Perception:** `scripts/lab/c7_v1_perception_adapter.py` akceptuje:
   - rzeczywisty obecny kontrakt `perception.scene_observation.v1`, w układzie `stereo_left_rectified_optical` (tylko camera-frame); wynik **BLOCKED**;
   - archiwalny `ecu_geometry_private.json` ETC3 z 14 listopada 2026 r., 25/25 wykrytych klatek 1280×800; wynik **BLOCKED**, bo footprint całego otwartego ECU nie oznacza samej PCB, a `table_frame` / `robot_base_frame` są niedostępne;
   - nowy, wąski kontrakt `vision.perception_pcb_table.v1`: **jawnie wykryta PCB z górną powierzchnią w układzie stołu**. Wymaga oznaczenia pochodzenia, SHA256 źródła, statusu niezatwierdzonej geometrii, geometrii PCB i roboczej odległości fotografowania. Konwersja zachowuje `CANDIDATE_UNVERIFIED`, nigdy nie uprawnia ruchu. **Obecny Perception Engine nie emituje jeszcze tego kontraktu.**

2. **Generator C7 V1:** `scripts/lab/c7_v1_photo_viewpoints.py` wyznacza 5 miejsc fotografowania × 2 hipotezy montażu ±90°; wynik to tylko `link7` IK candidates, bez publikowania TF.

3. **MoveIt 2 LAB:** `scripts/lab/c7_v1_moveit_ik_check.py` na VENTUNO Q:
   - wymaga `ROS_DOMAIN_ID=201`, `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`, `allow_trajectory_execution=false`, fizycznego CAN0 DOWN i CAN TX=0;
   - używa faktycznych usług MoveIt `/compute_ik`, `/compute_fk`, `/check_state_validity`, `/apply_planning_scene`, `/plan_kinematic_path`;
   - wstawia stół 1500×780 mm oraz **syntetyczny** prostopadłościan ECU/PCB, używa niezatwierdzonego `T_table_base_link`;
   - dołącza do link7 szczegółowy model kolizyjny Sony z adapterem; każdy wynik IK sprawdza dodatkowo w oddzielnym konserwatywnym walcu;
   - dla wybranych poprawnych par rozwiązań sprawdza Pilz PTP i wszystkie próbki trajektorii. Żadnego wykonania.

4. **Powtarzalny przebieg**: `scripts/lab/run_c7_v1_planonly_moveit.sh` wykonuje import → generowanie propozycji → izolowany MoveIt 2 → zapis wyniku → zatrzymanie całej prywatnej grupy procesów. Konfiguracja jest trwała w repo. Każdy test tworzy osobne artefakty na NVMe, bez nadpisywania wyników.

## Wynik faktyczny — test wyłącznie syntetyczny

Użyto **wymyślonej płytki PCB ETC3**: środek stołu X750/Y410 mm, powierzchnia 120×80 mm, górne Z45 mm, odległość czoła obiektywu 230 mm. Parametry NIE zostały zmierzone na rzeczywistym ETC3 i nie określają jego wymiarów.

- **10/10** kandydatów: IK MoveIt znalezione.
- **10/10**: odtworzenie położenia przez FK zgodne z celem w przyjętym progu.
- **10/10**: statyczne pozycje bez zgłoszonych kolizji zarówno dla modelu szczegółowego Sony, jak i zachowawczego walca przy nominalnym offset 0 mm.
- **2/2** przejazdy Pilz PTP pomiędzy punktami widoku: zaplanowane, wszystkie punkty zbadane pod kątem kolizji (liczba punktów różni się między uruchomieniami solvera).
- **0** komend do ramienia; `can0 DOWN`, CAN TX 0→0; `move_group` zatrzymany po teście.

Wynik oznacza działającą *integrację programową*, nie potwierdzoną dokładność rzeczywistego ETC3 ani możliwość fizycznego wykonania.

## Dlaczego prawdziwy ETC3 jeszcze nie zastępuje syntetycznego PCB?

Archiwum ETC3 z 14 listopada zawiera rzeczywiste zdjęcie RGB **otwartego ECU z widoczną PCB i trzema złączami** oraz 25 klatek DepthAI 800p. Istniejący wynik analizy `ecu_geometry_private.json` podaje przybliżony obrys **całego ECU** ok. 274.19 × 224.13 mm i wysokość widocznej obwiedni P99 ok. 51.32 mm w układzie optycznym. Nie jest to osobno zmierzony obrys samej PCB; nie ma wiarygodnego table XYZ, pozycji osi PCB ani obrotu względem stołu. Synchronizacja historycznego RGB i głębi również nie została potwierdzona.

**Nie wolno używać** liczb całego ECU jako wymiarów PCB ani transformować historycznej kamery do aktualnego stołu na podstawie niezatwierdzonych lub później zmienionych poz kamery.

Następne faktyczne działanie Perception: niezależnie oznaczyć/wyznaczyć **PCB** w rzeczywistych klatkach, policzyć geometryczne granice PCB i powierzchnię, a następnie wyznaczyć pozycję w układzie `table` (z oznaczeniem niepewności i źródeł). Dopiero taki kandydat może zasilić generator w trybie eksperymentalnym. Do tego czasu import aktualnego realnego zapisu **blokuje** tworzenie robotycznych pozycji.

## Jak uruchomić powtarzalny test laboratoryjny

```bash
# Syntetyczny end-to-end, bez ruchu:
bash scripts/lab/run_c7_v1_planonly_moveit.sh \
  --perception examples/lab/etc3_synthetic_perception_pcb_table.json

# Rzeczywisty archiwalny ETC3: wynik BLOCKED, bez uruchomienia MoveIt:
bash scripts/lab/run_c7_v1_planonly_moveit.sh \
  --legacy-etc3 /srv/vision-data/staging/vision-ecu-live-test-20261114/ecu_geometry_private.json

# W przyszłości, po wygenerowaniu rzeczywistej obserwacji PCB w table frame:
bash scripts/lab/run_c7_v1_planonly_moveit.sh \
  --perception /srv/vision-data/calibration/.../pcb_table_candidate.json
```

Uruchomienia laboratoryjne zapisują `perception_import.json`, `scene.json`, `viewpoints.json`, `ik_result.json` i logi tylko na NVMe. Przebieg nie wymaga ponownej kalibracji urządzeń. Ścieżka `--scene` także istnieje dla jawnych fixture testowych.

## Niezmienione ograniczenia

- C2 table-to-base i C7 rzeczywisty znak 90° / offset i TCP optyczny są **kandydatami**.
- Nie dokonano kontroli ciągłego toru między waypointami. W aktualnej scenie brak dodatkowych zacisków i przewodów (potwierdzone przez operatora). Złącza ECU uwzględniamy w obwiedni całego ETC3.
- Kontakt narzędzia z `link6` i `link7` jest pomijany na mocy przyjętych `touch_links`. To nie jest fizyczna weryfikacja odległości.
- Prawdziwe Sony ma ograniczenia ogniskowania/ostrości, które nie zostały tu zweryfikowane.
- Nawet po pojawieniu się prawdziwych danych PCB wynik pozostaje PLAN-ONLY; załączenie napędów i fizyczna realizacja to odrębna decyzja operatora.

**Repozytorium:** osobny PR oparty na C7 V1 PR #33; surowe prywatne dane RGB-D oraz pełne raporty pozostają na VENTUNO Q NVMe.

## Rozszerzenie: rzeczywisty ETC3 20.11.2026 — nadal PLAN-ONLY

- Bieżące RGB 1920×1080 i **12 map StereoDepth 1280×800** z OAK-D Pro AF, IR OFF, bez zmiany usług i bez NERO.
- Wykryto obszar widocznej PCB z rzeczywistego obrazu. Wyznaczono wstępny `table` XY z 50 archiwalnych klatek ChArUco, po rozwiązaniu hipotezy ułożenia planszy (kierunki jej osi oraz fizyczny róg siatki). **Nie oznacza to zatwierdzonego TF**: poprzednie pozycje planszy były mierzone ręcznie i nie mają niezależnego wzorca bezwzględnego XY.
- Oddzielono barwną maskę widocznej PCB od obwiedni całego ECU. Scena testowa może zawierać `obstacle_envelope` z obrysem całego ECU oraz wyższymi złączami, by nie utożsamiać wysokości laminatu z maksymalną wysokością przeszkody.
- Laboratorium MoveIt 2 wykonuje `IK/FK/GetStateValidity/Pilz PTP` także na **realnym kandydacie pozycji ETC3** (źródła i raporty tylko na NVMe; nie publikujemy zdjęć ani surowych danych ECU w GitHubie).
- Próby roboczych odległości czoła obiektywu **230 / 275 / 300 mm**: odpowiednio 6/10, 10/10, 10/10 rozwiązań IK przy testowanych hipotezach ±90°. Dla 275 i 300 mm tylko jeden z dwóch przykładowych przejazdów Pilz PTP uzyskał poprawny plan; drugi zakończył się błędem 99999. Użytkownik nie wybrał fizycznej odległości fotografowania, a min. dystans ostrzenia Sony nie został sprawdzony.
- Ocena statyczna w szczegółowym i zachowawczym modelu narzędzia jest pozytywna dla wszystkich 10 pozycji wariantów 275/300 mm przy tym konkretnym roboczym modelu; **nie daje to zgody na fizyczny ruch**.
- Stała konfiguracja na VENTUNO Q pozostaje nienaruszona; domena LAB=201 jest zatrzymywana po testach, CAN TX=0, `can0 DOWN`, brak publikacji TF.

Pełne źródła i rezultaty (włącznie z błędami C5, kalibracją fabryczną OAK i oznaczeniem niezatwierdzonych założeń):
`/srv/vision-data/calibration/sessions/20261119-vision-station-v1/validation/C7_V1_LIVE_ETC3_SCAN_AND_PLAN_ONLY_20261120.md`
oraz `c7_v1_live_ETC3_RGBD_to_moveit_20261120_summary.json` na tym samym NVMe.

## Diagnostyka granic J7 i walidacja geometrii (20.11.2026)

### Źródło błędu PTP +90°: numeryczny limit J7

- Faktyczne logi izolowanego MoveIt 2 z próby 275 mm: `CheckStartStateBounds` zwrócił błąd, ponieważ joint7 miał z IK wartość dokładnie −90° (`−π/2`), a URDF producenta określa minimum `−1.5707963 rad` (czyli ok. −89.99999846°). Niewielka różnica wynosiła 0.0000000268 rad. W kolejnych przebiegach problematyczny był punkt startowy albo docelowy, zależnie od gałęzi IK.
- Dodano `scripts/lab/c7_v1_joint_limits.py`, który odczytuje **niezmieniony URDF** i w trybie offline wprowadza margines `0.0001 rad` wyłącznie dla wartości przy samej granicy; korekty >0.02° są odrzucane. Każdy skorygowany punkt podlega powtórnej kontroli FK (błąd pozycji <0.25 mm, orientacji <0.05°), przed uruchomieniem Pilz.
- Na realnym kandydacie pozycji ETC3 i wysokości fotografowania 275 mm poprawka J7 wyniosła około 0.00573°. Ponownie wyznaczono trajektorie Pilz PTP **dla +90° i −90°**, oddzielnie dla **dokładniejszego modelu Sony** i dla wcześniejszej **konserwatywnej obwiedni walcowej**. Oba warianty zakończyły się PASS w sprawdzonych punktach; w reprezentatywnym końcowym uruchomieniu +90° wymagał 2584 punktów, a −90° 359 punktów, dla **każdego** modelu kolizyjnego. Brak komend ruchu NERO.
- Ta poprawka jest **tylko rozwiązaniem laboratoryjnego błędu planowania**. Nie zmienia zakresów J7 producenta, nie rusza silników ani robotycznego sterownika. Nie zastępuje testu ciągłej kolizji i niezależnej oceny rzeczywistych prześwitów.

### Sprawdzenie dokładności geometrycznej, bez ponownego pomiaru stanowiska

- Przeprowadzono niezależne **porównanie zarejestrowanych obrazów statycznej płyty mocowania NERO** między wcześniejszymi 5 pozycjami ChArUco a aktualnym skanem ETC3 (SIFT + RANSAC, nie dopasowanie PCB). Zaobserwowana zmiana skali 2D względem C5 wynosiła **1.406–1.938%**, mediana **1.569%** na pięciu ujęciach. W pięciu klatkach aktualnej serii RGB względem jednej próbki C5 zmieniała się od ok. **1.674% do 2.436%**.
- Nie można z tego wywnioskować, czy przyczyną jest autofocus/oddychanie obiektywu, zmiana projekcji/kadrowania, czy inne przesunięcie; wykryta różnica nie jest też równoznaczna z błędem położenia kamery w milimetrach. **Nie wolno przenieść starego C5 TF do rzeczywistego sterowania bez kotwicy i kontroli zmiany parametrów optycznych.**
- 50 historycznych obrazów ChArUco miało medianę RMS reprojekcji około 0.208 px, lecz pięć pozycji planszy zostało oznaczonych ręcznie, bez niezależnego pomiaru dokładności XY. Rozrzut między stacjami nie jest certyfikatem błędu bezwzględnego.
- Aktualne 12 map stereo 1280×800: mediana głębi w wybranym stałym obszarze wynosiła 780–781 mm. To potwierdza krótkoterminową powtarzalność, **nie dokładność absolutną**. W archiwum C6 (IR OFF) odchyłki wysokości dla trzech rzeczywistych wzorców wynosiły około −0.909, −4.144 i −4.560 mm (zależne od powierzchni).
- Obrys barwnej maski PCB z rzeczywistego ETC3 nadal może częściowo obejmować ramkę ECU. Obwiednia kolizyjna całego ECU z wystającymi złączami została utworzona niezależnie i zawiera umowny zapas; nie jest zatwierdzonym modelem wymiarowym.

**Decyzja:** geometria pozwala kontynuować symulacje C7 V1 PLAN-ONLY; **NIE pozwala jeszcze przejść do fizycznego ruchu**. Nie wymagamy dokładności fotograficznej 1 mm. Przed ruchem wymagamy wiarygodnej oceny gabarytów i prześwitów (z błędem pomiaru i zapasem); orientacyjny pomiar jednego narożnika lub wymiarów obudowy ETC3 pozostaje jedną z prostych metod niezależnej kontroli, **nie obowiązkiem pomiaru do milimetra ani powtórzeniem pełnej kalibracji**. Wymagane są również aktualne J1–J7, geometria C2/C7 wystarczająca do ochrony przed kolizją, pełna scena i sprawdzenie prześwitów całej trajektorii.

**Dowody tylko na prywatnym NVMe:**

- `validation/c7_v1_ETC3_independent_geometry_consistency_20261120.json`
- `validation/c7_v1_ik_perception_lab/etc3_live_275mm_both_tool_models_plan_20261120/ik_result.json`

Nie publikowano na GitHubie prywatnych zdjęć ETC3 ani pełnych logów.

## ADR — priorytet bezpieczeństwa i kadrowanie zoomem (20.11.2026)

Użytkownik przyjął dla C7 V1 **brak obowiązku dokładności pozycjonowania Sony do 1 mm**. Cel operacyjny to bezpieczne prowadzenie NERO z zamontowanym aparatem; korektę kadru można wykonywać zoomem optycznym Sony, gdy aparat znajduje się już w bezpiecznej pozycji i może prawidłowo ustawić ostrość.

Wymagania dla kolejnych etapów:

- **Oddzielić kryterium fotograficzne od geometryczno-kolizyjnego:** niewielki błąd kadrowania nie jest problemem samym w sobie, ale nie wolno stosować go jako uzasadnienia małego prześwitu.
- **Preferować ujęcie z większego dystansu** i odpowiedni zoom, zamiast zbliżać aparat do najwyższych elementów ECU. Rzeczywisty zakres ostrzenia i skuteczność zoomu Sony dla wybranego dystansu wymagają osobnego sprawdzenia.
- **Modelować przeszkody jako bryły 3D:** całe ECU i trzy złącza, stół, ramię i adapter J7/Sony; bez nieistniejących dodatkowych zacisków i przewodów. Nie traktować samego laminatu PCB jako najwyższej przeszkody.
- **Planowanie:** uwzględnić niepewność RGB-D i niezatwierdzonych C2/C7; odstęp od przeszkód powinien pokrywać tę niepewność i dodatkowy margines. Operator wybrał bufor kolizyjny C7 V1 5 mm, dodawany do surowej obwiedni ETC3 po każdej stronie w XY i ponad Z; nie dodajemy wcześniejszych 15 mm/12 mm ani nie uznajemy wyniku za zatwierdzoną geometrię.
- **Wykonanie:** testy całego planowanego ruchu, pozycja startowa z aktualnego JointState, operator stale obecny przy stanowisku. Zgodnie z przyjętą procedurą laboratoryjną korzystamy z programowego HOLD.
- **Odbiór:** nie wymagamy pomiarów pozycji PCB do 1 mm, ale nie ogłaszamy fizycznego ruchu bezpiecznym na podstawie wyłącznie poprawnych IK, planów PTP i dyskretnych kontroli waypointów.

Ta decyzja nie zmienia aktualnych bramek allow_trajectory_execution=false, send_robot_commands=false i publish_static_tf=false. Nie stanowi aprobaty dokładności aktualnego table TF ani ograniczeń konstrukcyjnych Sony.

## Korekta bieżącej sceny ETC3 — margines 5 mm (20.11.2026)

Operator potwierdził, że nie ma dodatkowych zacisków ani przewodów w aktualnej scenie. Nie modelujemy fikcyjnych przeszkód. Margines C7 V1 przyjmujemy **5 mm względem pierwotnej zmierzonej obwiedni całego ETC3**: +5 mm na każdej krawędzi XY (czyli +10 mm do całej szerokości i długości) oraz +5 mm ponad Z. Wcześniejsze zapasy +15 mm/stronę i +12 mm Z **zastępujemy**, nie sumujemy. To założenie LAB/PLAN-ONLY na życzenie operatora.

Wymiary obwiedni z poprzedniego zapisu 265.512 × 225.328 × 48.25 mm dają po korekcie 275.512 × 235.328 × 53.25 mm. Środek obwiedni ECU X666.461, Y416.864 mm. Dotyczy tylko wariantu ETC3 275 mm (czoło obiektywu względem górnej powierzchni PCB); nie zmieniono rzeczywistych pomiarów, zapisanych surowych danych ani robotycznych limitów URDF.
