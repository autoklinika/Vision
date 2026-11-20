# C7 V1 — Sony A6000 V2 / AgileX NERO, laboratoryjny model PLAN-ONLY

**Decyzja: 20.11.2026 — wybrano C7 V1 zamiast dalszego dopracowywania kalibracji C7 V2.**

## Cel i zakres

Umożliwić rozwijanie scenariusza **ETC3 (PCB po otwarciu obudowy)** niezależnie od pełnej walidacji mechanicznego TCP Sony. Dla zadanej geometrii PCB generujemy propozycje ujęć dla Sony i odpowiadające im kandydackie pozycje `link7`. Żaden z tych kandydatów nie jest komendą NERO, rozwiązaniem IK ani potwierdzeniem bezkolizyjności.

Obecny moduł to **czysto offline generator pozycji**, nie Vision Core ani gotowa integracja z kamerą. Następne oddzielne ogniwo workflow to rozwiązanie IK i sprawdzenie kolizji w izolowanym MoveIt 2. Wykonanie ruchu pozostaje wyłączone.

## Założenia C7 V1

- Stół: **1500 × 780 mm**, punkt zerowy w lewym przednim narożniku, +X w prawo, +Y ku ścianie, +Z w górę.
- NERO `T_table_base_link`: kandydat C2 — środek mocowania ok. (675, 90, 31) mm, yaw −90°, **niezatwierdzony**.
- Fabryczny `link7 → flange_link`: xyz (31, 0, −23,5) mm, rpy (−1,5708, 0, −1,5708) rad (model URDF).
- Makieta Sony V2: obwiednia 120 × 69 × 92 mm, oś obiektywu w ramce socket: +Y, środek czoła obiektywu względem socket: (0, 74, 36) mm. **Nie jest to pomiar środka optycznego rzeczywistego aparatu**.
- Adapter J7 v7, profil D Ø39,8 mm / grubość 10 mm, sztywne osadzenie do oporu, brak szczeliny wg operatora. Makieta również zamocowana sztywno. Masa nominalnie z dwóch pomiarów: 145 + 6 = **151 g**, nie obejmuje potwierdzonej masy wszystkich elementów mocujących i kabli.
- Przyjęto **wartość bezwzględną azymutu obiektywu 90° względem +X ramki flange_link**. Rzeczywisty znak azymutu nierozstrzygnięty: program generuje **+90° i −90°**, nie wybiera go automatycznie.
- Strona normalnej socket +Z i offset osiowy względem kołnierza: dla obliczeń nominalnych **+Z, 0 mm**, przy czym **ani zwrot, ani offset nie są fizycznie potwierdzone**.
- Górny kierunek kadru jest roboczo utożsamiany z kierunkiem +Y PCB; osiowanie obrazu Sony nie było pomierzone.
- Pomiar odległości fotografowania pozostaje parametrem scenariusza. **Nie wpisujemy żadnej niesprawdzonej minimalnej odległości ostrzenia obiektywu jako faktu**.

Wariant zachowawczy kolizji: walec **R=89,148 mm, L=89 mm**, tylko model porównawczy. W teście C7 z 20.11.2026 wykazał **1,449 mm przenikania z blatem** w historycznej pozycji NERO, chociaż model szczegółowy w wariancie nominalnym nie zgłaszał kolizji. Żadnego z modeli nie wolno uznać za fizycznie zatwierdzony. Potwierdzenia wymaga także relacja narzędzia z `link5/link6`.

## Kontrakt geometryczny

Wejście JSON:

- `schema_version: 1`, `scenario_id`, `ecu_type`
- `evidence_kind`: `synthetic_fixture`, `operator_measured` lub `vision_perception_candidate`
- `pcb.center_table_xy_mm: [X,Y]`, `size_xy_mm: [szerokość, długość]`, `top_z_mm`, `yaw_table_deg`
- `camera.lens_front_working_distance_mm`, opcjonalnie `quadrant_fraction` (domyślnie 0,28)

Wyjście: 5 punktów (środek oraz cztery obszary ćwiartek), każdy w dwóch hipotezach +90/−90. Każdy wynik zawiera pozycję czoła obiektywu w ramce stołu, nominalną propozycję pozycji `link7` w ramce `base_link` (położenie i kwaternion xyzw), identyfikator źródła oraz jawne flagi:

`inverse_kinematics_checked=false`, `collision_checked=false`, `trajectory_generated=false`, `execution_allowed=false`.

Współrzędne `link7` są przeliczane przez *niezatwierdzone* C2 i C7. Nie wolno włączać ich do aktywnego TF ani wykonywać jako ruchu.

## Przykład offline (syntetyczny, NIE realny ETC3)

```bash
python3 scripts/lab/c7_v1_photo_viewpoints.py \
  --profile config/lab/c7_v1_sony_tool_planonly.json \
  --scene examples/lab/etc3_synthetic_scene.json \
  --output /tmp/etc3_c7_v1_viewpoints.json

python3 -m unittest discover -s tests/lab -p 'test_c7_v1_photo_viewpoints.py' -v
```

W pliku przykładowym PCB ma **celowo wymyślone** wymiary i pozycję, służące wyłącznie do testu matematyki. Nie traktować ich jako wymiarów sterownika ETC3.

## Przejście do rozwoju Vision

1. **ETC3 PoC:** Vision Perception/ROS 2 wyznacza rzeczywiste położenie, obrys, wysokość i obrót PCB. Wynik ma opis pochodzenia i niepewności; bez danych nie generujemy zatwierdzonych póz.
2. **C7 V1:** generator tworzy propozycje miejsc fotografowania i hipotezy `link7`. Brak wykonania.
3. **MoveIt 2 LAB:** osobny proces w izolowanej domenie ROS 2 rozwiązuje IK; na kompletnej scenie sprawdza stół, zaciski, obudowę ECU, robot, narzędzie i trajektorię. Wynik pozostaje plan-only. Jeżeli obwiednia zachowawcza i szczegółowa są sprzeczne, blokujemy zatwierdzenie ruchu.
4. **Dopiero oddzielna zgoda na etap fizyczny:** aktualny JointState, potwierdzony rzeczywisty offset i zwrot narzędzia, niezależna walidacja TF i prześwitów, nadzór operatora oraz zaakceptowana w Vision procedura HOLD. Sam ten moduł **nie otwiera tej bramki**.

## Trwałość i polityka zmian

Konfigurację i kod trzymamy w repozytorium Vision na osobnej gałęzi/PR. Surowe zdjęcia, rzeczywiste przebiegi i pełne raporty sesji zostają na NVMe: `/srv/vision-data/calibration/sessions/20261119-vision-station-v1/`. Nie zmieniamy `main` bez przeglądu PR. Nie modyfikujemy działających usług NERO, Camera Service, aktywnego TF lub ROS kontrolerów.

**Powiązane materiały:** `docs/calibration/VISION_STATION_CALIBRATION_V1.md` (pełne wymagania C7/C8) oraz prywatne raporty `c7_moveit_final_test_summary_20261120.json` i `C7_MOVEIT_90DEG_OFFLINE_TEST_REPORT_20261120.md` na NVMe. C7 V1 to profil laboratoryjny, a nie odstąpienie od przyszłego odbioru fizycznego C7 V2.
