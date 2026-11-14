# ETC3 — profil roboczy ECU, egzemplarz 01 (2026-11-14)

**Profil:** `ETC3-CANDIDATE-001`  
**Status:** `DRAFT / PARTIAL_MEASUREMENTS / NOT_MOTION_READY`  
**Cel:** pierwsze wejście do katalogu ECU i pierwsza sesja `SCN-001` nowego systemu Vision, a nie gotowy profil produkcyjny.  
**Fundament:** [VISION_FOUNDATION_2026-11-14.md](../architecture/VISION_FOUNDATION_2026-11-14.md)  
**Scenariusz:** [SCN-001-ETC3-OFFLINE.md](../scenarios/SCN-001-ETC3-OFFLINE.md)

## 1. Identyfikacja i zakres

- **Deklaracja operatora:** `ETC3`. Pełny producent, numer części, wariant elektroniki, rewizja i ewentualny numer seryjny nie zostały tutaj potwierdzone i **nie są dopowiadane**.
- **Wybór referencyjnego egzemplarza:** **pierwszy** ECU mierzony w dniu **14.11.2026**; otwarta obudowa, widoczna PCB; trzy złącza w rzędzie — **czarne, szare, czarne** (w orientacji zdjęcia operatora).
- **Wykluczenie pomyłki:** tego ECU **nie wolno łączyć z drugim ECU** zmierzonym tego dnia (tam operator podał maksymalną wysokość 75 mm). DAF SAC także nie jest pierwszym scenariuszem.
- **Tryb rozpoznania:** operator wybiera ETC3; system próbuje potwierdzić, że obraz, cechy PCB i układ złączy odpowiadają profilowi. Nie rozpoznaje automatycznie nieznanego ECU ani nie zmienia deklaracji sam.
- **Zakres pierwszej sesji:** otwarte ECU/PCB, plan inspekcji optycznej, geometria do weryfikacji i planowanie **wyłącznie offline**. Obecnie brak dopuszczonego planu rzeczywistego ruchu NERO.

## 2. Dane początkowe, jednostki i provenance

Poniższe dane obejmują **różne rodzaje informacji**. Estymacja z map głębi nie jest automatycznie fizycznym wymiarem ECU. Wartości obrazu i koordynaty są zależne od pozycji kamery, ROI, filtracji i kalibracji.

| Właściwość | Wartość | Źródło / status | Dozwolone użycie teraz |
| --- | ---: | --- | --- |
| Liczba / barwy złączy | 3: czarne–szare–czarne | Deklaracja i oględziny operatora, 14.11 | Weryfikacja wizualna |
| Fizyczny najwyższy punkt ECU1 | **65 mm** | **Końcowa korekta użytkownika** z 14.11; wcześniejszy pomiar 69 mm dla szarego złącza został zastąpiony | Wstępny limit odniesienia; nie samodzielna gwarancja clearance |
| Obrys w obrazie przeliczony na mm | 274,2 × 224,1 mm | Mediana 25 obserwacji DepthAI; **nie pomiar suwmiarką** | Hipoteza obrysu / kontrola QA |
| Dominująca powierzchnia obiektu | 24,9 mm nad stołem | Obserwacja DepthAI | Diagnostyka geometrii |
| Wysokość percentyla 99% (całe ECU) | 51,3 mm | P99 DepthAI; **nie** całkowite maksimum | Diagnostyka, nie clearance |
| Lewe czarne złącze | ok. 51,2 mm | Lokalny P99 DepthAI | Diagnostyka |
| Środkowe szare złącze | ok. 54,3 mm | Lokalny P99 DepthAI | Diagnostyka |
| Prawe czarne złącze | ok. 51,6 mm | Lokalny P99 DepthAI | Diagnostyka |
| Najwyższy lokalny obszar szarego złącza | 62,9 mm | Lokalny pomiar z mapy głębi | Diagnostyka |
| Maksimum po filtracji kamery | 63,9 mm | Algorytm filtrujący wyniki depth | Diagnostyka |
| Wykrycie obiektu w próbie | 25/25 klatek | Próbka laboratoryjna z 14.11 | Wskaźnik detekcji **dla tej próby** |
| Zmienność obrysu | 2,1 mm (dł.), 4,2 mm (szer.) | Rozrzut wyników DepthAI między klatkami | Wstępna ocena powtarzalności |
| Zmienność dominującej wysokości | 0,57 mm | Rozrzut wyników DepthAI | **Nie** dokładność pomiaru wysokości |
| Fizyczne gabaryty suwmiarką | **nieustalone** | Wymaga osobnego potwierdzenia | Niedostępne do zamrożenia w profilu |
| Transformacja `table → robot_base` | **niedostępna** | Brak zwalidowanej kalibracji stanowiska | Zakaz planowania do wykonania |
| Pozycja złączy w układzie stołu/robota | **nieustalona** | Tylko orientacja względna na zdjęciu | Niedostępna do robotyki |

**Uwaga o korekcie pomiarów:** w trakcie pierwszej sesji podano osobno wysokości złączy 69 / 65 / 65 mm, ale później operator wyraźnie poprawił **najwyższy punkt całego pierwszego ECU do 65 mm**. Dlatego wartość 69 mm jest **archiwalna i nieobowiązująca**. Nie utożsamiać P99 z najwyższym punktem. W kolejnym fizycznym pomiarze można potwierdzić każdy z trzech punktów względem tej samej płaszczyzny stołu, bez zmiany obecnej deklaracji w ciemno.

## 3. Dowody i ograniczenia archiwum

- Pomiary ECC/DepthAI: kontrolowana sesja z 14.11.2026, zapisane RAW16 na NVMe Vision (prywatne) — w tym dokumencie **nie umieszczamy** surowych zdjęć, ścieżek identyfikujących sesję ani danych prywatnych.
- Test ROS 2 / MoveIt 2 na zapisanych prawdziwych ECU: [PR #27](https://github.com/autoklinika/Vision/pull/27), dokument `docs/operations/VISION_ROS2_MOVEIT_ECU_OFFLINE_TEST_2026-11-14.md`. `ECU1` w raporcie = pierwszy obiekt (ETC3) w niniejszym scenariuszu, `ECU2` = drugi, inny sterownik.
- Dla ECU1 oficjalny MoveIt OctoMap utworzył zajęte voxele do ok. **122–125 mm**, mimo pomiaru fizycznego najwyższego punktu **65 mm**. To **niezwalidowane outliery głębi**, nie nowa wysokość ECU. Surowa chmura nie może być uznana bezkrytycznie za rzeczywistą geometrię sceny.
- Próba oficjalnego Luxonis ROS v3 z fizyczną kamerą na VENTUNO 14.11 zakończyła się **brakiem strumienia w kontenerze**. Poprawna instalacja i import sterownika nie są dowodem działania z USB na urządzeniu.
- Poprzednie testy geometrii i IR na innych wzorcach nie udowodniły dokładności ±1 mm; dla ETC3 nie należy zakładać, że taki poziom został osiągnięty.

## 4. Pola profilu w nowej aplikacji

Model danych **proponowany**, niezaimplementowany. Pola powinny być rozdzielone na:
- `identity`: `family=ETC3`, `variant=null`, wersja profilu, aliasy i dowód deklaracji;
- `physical_envelope`: `declared_max_height_mm=65`, informacja o źródle, niepewności i dacie; `verified_length_mm=null`, `verified_width_mm=null`;
- `observed_geometry`: wyniki powiązane z sesją/klatkami, a nie kopiowane do trwałych wymiarów konstrukcyjnych;
- `visual_signatures`: schemat trzech złączy `black-grey-black`, wzorzec obrazu referencyjnego (po zatwierdzeniu);
- `inspection_plan_ref`: `SCN-001` jako plan offline;
- `ai_models`: lista opcjonalna; **pusta w pierwszym scenariuszu**, bo celem nie jest trening ani automatyczne klasyfikowanie ECU;
- `status`: `DRAFT`; `approved_for_motion=false`.

Identyfikatory obiektu, kalibracji i sesji muszą być jawne i wersjonowane. Nie wpisywać fikcyjnego numeru ECU, pełnej orientacji w `robot_base` czy certyfikowanej dokładności.

## 5. Kryterium zatwierdzenia profilu fizycznego

Do zatwierdzenia po późniejszych pomiarach: udokumentowane fizyczne długość/szerokość, spójna maksymalna wysokość, geometria wystających elementów i złączy, układ odniesienia, powtarzalność na kilku położeniach oraz ścieżka dowodowa do oryginałów. Te warunki **nie blokują** testów scenariusza w trybie offline/mocked.

**Następny dokument:** [SCN-001-ETC3-OFFLINE.md](../scenarios/SCN-001-ETC3-OFFLINE.md).
