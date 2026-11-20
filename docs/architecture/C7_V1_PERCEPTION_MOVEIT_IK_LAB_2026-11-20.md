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
- Nie dokonano kontroli ciągłego toru między waypointami. Obiekty poboczne: zaciski, kable, złącza ECU i inne przedmioty mogą nie być w scenie.
- Kontakt narzędzia z `link6` i `link7` jest pomijany na mocy przyjętych `touch_links`. To nie jest fizyczna weryfikacja odległości.
- Prawdziwe Sony ma ograniczenia ogniskowania/ostrości, które nie zostały tu zweryfikowane.
- Nawet po pojawieniu się prawdziwych danych PCB wynik pozostaje PLAN-ONLY; załączenie napędów i fizyczna realizacja to odrębna decyzja operatora.

**Repozytorium:** osobny PR oparty na C7 V1 PR #33; surowe prywatne dane RGB-D oraz pełne raporty pozostają na VENTUNO Q NVMe.
