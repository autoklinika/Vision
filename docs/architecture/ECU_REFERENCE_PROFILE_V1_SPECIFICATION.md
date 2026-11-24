# VISION — ECU Reference Profile V1

**Status:** ACCEPTED (2026-11-24) — pełna struktura 15 sekcji zaakceptowana przez właściciela
**Data:** 24.11.2026
**Zakres:** uniwersalny profil wzorcowy typu i wariantu ECU, wykorzystywany po wyborze przez operatora i przed inspekcją konkretnego egzemplarza.
**Podstawa:** zaakceptowany kierunek Vision Core 0.4 (niezależność sprzętowa, jawne scenariusze, bramki), istniejący `ECUProfile`, moduł ECU Profiles V1 w **Draft PR #46**.
**Zakres decyzji:** dopuszczono oddzielne publikowanie dokumentacji i późniejszą implementację offline; bez wdrożenia stanowiska, zmian kalibracji i VGP V1. ETC3 pozostaje DRAFT.

## 0. Główna definicja

**ECU Reference Profile** jest *niezmiennym, wersjonowanym źródłem wiedzy wzorcowej* o rodzinie i konkretnym wariancie ECU **oraz deklaratywną instrukcją** dla Vision: co weryfikować, jak uzyskać aktualną pozycję ECU, jakie inspekcje przygotować, jakie moduły są wymagane i co należy udokumentować.

Nie jest programem sterownika robota, skryptem wykonawczym ani dziennikiem pomiarów konkretnego egzemplarza. Nie zawiera wspólnych dla każdego stanowiska kalibracji Luxonis, Sony, NERO, fizycznej pozycji na stole ani bieżących wyników sesji.

**Rozdzielone warstwy:**

1. `ReferenceProfile` — biblioteka nominalnej wiedzy, wyglądu, geometrii, wymagań i receptur, identyfikowana przez `profile_id`, `variant_id`, `revision` i SHA-256.
2. `ExecutionProfile` — z profilu wzorcowego i wybranej, zatwierdzonej receptury powstają *tylko potrzebne* istniejące kontrakty Core: `ECUProfile`, zestaw capabilities, `ScenarioSpec` i parametry adapterów.
3. `InspectionSession` — konkretny egzemplarz, deklaracja operatora, obserwacja Luxonis, `T_world_ecu`, dane sceny, wykonane ujęcia, QA, archiwum i wyniki; wyniki nie zmieniają automatycznie profilu wzorcowego.

---

## 1. Struktura pliku manifestu (15 sekcji)

| Nr | Klucz | Zakres |
|---|---|---|
| 01 | `metadata` | ID profilu, rodzina, wariant, rewizja, stan i zgodność schematu |
| 02 | `identity` | producent, OE, oznaczenia, aliases, relacje i różnice między wariantami |
| 03 | `physical_states` | stan zamknięty, otwarty, odsłonięte PCB; przejścia i osobne referencje |
| 04 | `coordinate_systems` | ECU-local, datuma, osie, jednostki, transformacje między stanami |
| 05 | `geometry` | obudowa, obwiednia, collision geometry, pliki modeli |
| 06 | `connectors_landmarks` | złącza i miejsca diagnostyczne XYZ, wygląd, orientacje, wysokości |
| 07 | `reference_assets` | zdjęcia/RAW/3D/maski z SHA i pochodzeniem |
| 08 | `recognition_rules` | czego Luxonis ma szukać i jak rozpoznać niezgodność |
| 09 | `localization_rules` | jak wyznaczać pozę, weryfikować TF, świeżość i niepewność |
| 10 | `pcb_definition` | PCB, strony, ROI, zakryte obszary, wymagany stan otwarcia |
| 11 | `photography_recipes` | cele aparatu, perspektywy, ujęcia, RAW/AF/zoom/QA |
| 12 | `thermal_recipes` | opcjonalne obszary termiczne, tryb, metadane i wymagania |
| 13 | `inspection_workflows` | gotowe receptury scenariuszy, moduły, zależności, bramki |
| 14 | `validation_policies` | tolerancje, warunki wstrzymania, zgodność wariantu, ograniczenia |
| 15 | `provenance_release` | źródła wiedzy, statusy pomiarów, zatwierdzenie i wersje |

Każda sekcja jest wersjonowana w kontekście manifestu. Nieznane wartości przy tworzeniu DRAFT są reprezentowane jako `null` lub brak wpisu wymagającego pomiaru, **nigdy jako wymyślona wartość lub zero o nieznanym znaczeniu**.

## 2. Sekcja 01 — `metadata`

**Pola:** `schema_version`, `profile_id`, `family_id`, `variant_id`, `profile_revision`, `revision_created_at`, `display_name`, `status`, `approval_scopes`, `replaces_revision`, `content_sha256`, `required_schema_features`.

- `profile_id` jest trwały i nieidentyfikujący jednostkowego ECU. `variant_id` musi oznaczać konkretny, weryfikowalny wariant. Alias i numer OE nie zastępują jednoznacznego `variant_id`.
- `status`: `DRAFT` → `REVIEW_READY` → `APPROVED` → `SUPERSEDED`/`REVOKED` (cofnięcie nie usuwa historii).
- `APPROVED` dotyczy opublikowanego zestawu danych, ale **wykonawcza gotowość jest osobną macierzą dopuszczeń per stan i receptura** (patrz sekcja 18).
- W sesji wiążemy pełny identyfikator profilu, rewizję i sumę SHA-256; zmiana wymaga nowej wersji planu/sesji.

## 3. Sekcja 02 — `identity`

Przechowujemy deklarowaną tożsamość: producent, rodzina, typ, wariant mechaniczny/elektroniczny, listy numerów OE lub producenta (tylko ze źródłami), aliasy i historyczne kompatybilności.

**Rozróżnianie wariantów:** pozycje/kolory/liczba złączy, obrys, widoczne szczegóły mechaniczne, możliwe oznaczenia tekstowe oraz jawna lista wariantów, których *nie da się rozróżnić* dostępną obserwacją. **Nie traktujemy wewnętrznych nazw connector_id jako cechy fizycznej**. Jeśli cechy dwóch zatwierdzonych wariantów są nierozróżnialne, wynik to `AMBIGUOUS`, a nie automatyczny wybór.

Deklarację wykonuje operator. Dopiero później Luxonis dostarcza niezależną obserwację. Rozpoznanie kamerą jest potwierdzeniem cech **wybranego** wariantu, a nie upoważnieniem do ukrytej zamiany wariantu.

## 4. Sekcja 03 — `physical_states`

Profil może obsługiwać wiele stanów, np. `closed`, `opened_top`, `pcb_exposed_top`, `pcb_exposed_bottom`. Każdy stan ma własny `state_id`, warunki wejścia, dozwolone inspekcje i referencje do geometrii, zdjęć, PCB i receptur.

Położenie pokrywy, dostępność PCB i usunięcie przeszkód muszą być potwierdzone w bieżącej sesji, nie wynikać z samej deklaracji operatora. Gdy nie potwierdzono transformacji między stanami, każdy wymaga osobnej lokalizacji; zabrania się domniemanego dziedziczenia poz dla odkrytej płytki.

Stan fizyczny nie jest stanem Workflow. Zmiana `physical_state` w trakcie sesji zmienia scenę i może unieważnić wcześniejsze plany ruchu.

## 5. Sekcja 04 — `coordinate_systems`

Wszystkie wymiary nominalne są w **milimetrach** i zatwierdzonym prawoskrętnym lokalnym układzie `ecu_local`. Profil musi dokumentować:

- jednoznaczny fizyczny początek (datum), osie X/Y/Z, stronę dodatniej normalnej i sposób odtworzenia układu po obrocie/przeniesieniu ECU;
- do jakiego stanu obudowy odnosi się datum, dokładność pomiaru, źródło oraz referencję;
- ewentualne zmierzone transformacje lokalne PCB/złącza/komponentów, z kierunkiem transformacji, jednostką i rewizją.

**Bieżące `T_world_ecu` nie należy do profilu wzorcowego** — jest mierzone podczas sesji i podlega TF/freshness/quality. Transformacja celu aparatu jest obliczana z zatwierdzonego lokalnego celu i aktualnej pozy ECU: `T_world_camera_goal = T_world_ecu × T_ecu_camera_goal`. Kalibracja `T_tool_camera` pochodzi z profilu narzędzia i stanowiska. W profilu wzorcowym nie zapisujemy kątów J1–J7.

## 6. Sekcja 05 — `geometry`

Geometria jest przypisana do stanu fizycznego:

- obwiednia nominalna X/Y/Z oraz maksymalne wystające punkty; rozdział na korpus, złącza, osłony, PCB, przeszkody;
- opcjonalna zatwierdzona siatka/STEP/CAD i jej **osobno** zdefiniowane uproszczenie kolizyjne;
- rozsądny geometryczny margines i niepewność; konserwatywna bryła musi faktycznie obejmować zatwierdzoną geometrię szczegółową;
- źródło i datuma każdego wymiaru, jednostki, zakresy tolerancji, wersje modelu.

Geometryczne pliki w Asset Store są identyfikowane SHA-256 i lokalną ramką współrzędnych. Brak/niezweryfikowana obwiednia blokuje wykorzystanie tej informacji do planowania ruchu; nie można z niej wnioskować prześwitu.

## 7. Sekcja 06 — `connectors_landmarks`

Każde złącze ma `feature_id` (wewnętrzny), typ/kolor, liczbę pinów tylko gdy zweryfikowana, pozycję środka XYZ, lokalną orientację i bryłę, najwyższy punkt i `physical_state` widoczności.

Każdy landmark ma `feature_id`, typ (`connector`, `housing_corner`, `screw`, `label`, `hole`, `pcb_mark`...), mierzoną pozę lub punkt, obraz referencyjny, przewidywaną widoczność, niepewność i źródło. Definiujemy zestawy **cech rozróżniających** warianty, nie tylko łatwych do znalezienia.

Weryfikacja porównuje fizycznie obserwowalne cechy i ich geometrię, a nie nazwy. Pomiar landmarku, jego niepewność i orientacja wymagają zapisania niezależnej podstawy dowodowej. Wykryte lokalne cechy trafiają do sesji, nie nadpisują wartości wzorcowych.

## 8. Sekcja 07 — `reference_assets`

Zdjęcia i modele nie są bezpośrednio wbudowane do JSON. Każdy asset ma:

| Pole | Znaczenie |
|---|---|
| `asset_id` | Stałe ID wewnątrz rewizji |
| `kind` | `photo`, `raw`, `depth_reference`, `mesh`, `cad`, `mask`, `drawing` |
| `physical_state` | Stan, w którym pozyskano obraz/model |
| `view/feature_refs` | Powiązane landmarki, złącza i ROI |
| `sha256`, `bytes`, `mime` | Integralność i format |
| `source`, `captured_at`, `verified_by` | Pochodzenie i zatwierdzenie |
| `frame`, `scale`, `calibration_ref` | Ramka i skala, jeśli zastosowanie wymaga miary |
| `privacy_class` | Dostęp, retencja i miejsce przechowania |

Asset Store pozostaje odrębny i może być prywatny. Zdjęcie referencyjne bez zatwierdzonej skali nie staje się automatycznie źródłem wymiarów metrycznych. Rozdzielamy zdjęcia orientacyjne GUI od zweryfikowanych danych dla algorytmu.

## 9. Sekcja 08 — `recognition_rules` — instrukcje dla Luxonis

Receptura weryfikacji jest jawna, deklaratywna i wersjonowana:

- dostępny stan ECU i oczekiwane widoki/ROI;
- kolejność sprawdzania cech: obrys i główna geometria → układ złączy → pozycje landmarków → cechy wariantu → opcjonalne oznaczenia z obrazu;
- metody pomiaru: RGB, Depth, PointCloud2, segmentacja, wyznaczanie cech i porównanie geometryczne; konkretne algorytmy wykonują adaptery ROS/OpenCV;
- per cecha: `required`, `observable_in`, `reference_asset`, `expected`, `tolerance`, `uncertainty`, `evidence_type`, `acceptance_policy`;
- reguły, kiedy potrzebna jest kontrola operatora (np. nieczytelne oznaczenie, przysłonięte złącza, podobne warianty).

**Wynik:** `MATCHED`, `MISMATCHED`, `AMBIGUOUS`, `INSUFFICIENT_EVIDENCE` wraz z listą dopasowań, odchyłek, źródeł, pewności i powodów. Przedziały progów są mierzone/walidowane w rzeczywistych warunkach — nie zakładamy arbitralnego uniwersalnego „90% zgodności”. Nie wolno zwracać `MATCHED`, gdy brak wymaganej cechy lub możliwy jest nierozróżnialny wariant.

## 10. Sekcja 09 — `localization_rules` — instrukcje pozycjonowania

Profil opisuje, *jakie dane lokalizacji trzeba uzyskać i jak je sprawdzić*, nie przechowuje aktualnej pozycji:

- zestaw mierzalnych punktów 3D/feature anchors i rama docelowa;
- wymagany metryczny Depth, intrinsics, synchronizacja, transformacje TF, planowany stan fizyczny;
- dopuszczalne warunki zasłonięcia, uzgodnienia danych RGB i głębi;
- wyjściowy pose `T_world_ecu`, jego covariance/niepewność lub bezpieczne ograniczenie błędu, `frame_id`, `timestamp`, `scene_revision`, reference;
- zasada ponownego pomiaru po przesunięciu/otwarciu ECU i nieważność starszych planów.

Brak wiarygodnego Depth/TF/cech → `NOT_READY`, nigdy sztuczne `XYZ=(0,0,0)`. Nie ma własnego, alternatywnego wykonawcy ruchu.

## 11. Sekcja 10 — `pcb_definition`

Każda płytka ma `board_id`, `physical_state`, stronę `top/bottom`, ramkę `pcb_local` z transformacją do `ecu_local` (jeśli zatwierdzona), rozmiar/obrys i listę ROI. ROI może być prostokątem/poligonem z jednostkami oraz tolerancją. Rozdzielamy region *przedmiotu*, który ma być widoczny, od *pozy aparatu*, z której wykonujemy zdjęcie.

Możliwe typy ROI: cała płytka, strefy złączy, obszar układów scalonych, punkty lutownicze, oznaczenia, fragment wymagający zdjęcia porównawczego. Można zapisać strefy zakryte, wyjątki i wymagany stan otwarcia. Wykrycie/weryfikacja rzeczywistego PCB w sesji należy do adaptera; nie zakładamy jego widoczności przy zamkniętym ECU.

## 12. Sekcja 11 — `photography_recipes`

Receptura opisuje grupę ujęć i jej cel (identyfikacja, cały PCB, detal, porównanie wersji, złącze):

| Pole ujęcia | Interpretacja |
|---|---|
| `view_id`, `state_id`, `roi_refs` | Co i w jakim stanie fotografujemy |
| `camera_goal` | Zamierzona **poza osi optycznej lub TCP** w `ecu_local`, jawna konwencja transformacji |
| `aim_point` | Osobny opcjonalny punkt widzenia na ECU, nie zastępuje pozy aparatu |
| `orientation_xyzw` | Unormowany kwaternion i ramka odniesienia |
| `distance_range_mm` | Zakres odległości roboczej, jeśli zmierzony |
| `framing_target`, `overlap` | Oczekiwane pokrycie obszaru i nakładanie ujęć |
| `capture_capabilities` | RAW/JPEG, AF/MF, zoom, metadane ekspozycji, źródła transferu |
| `quality_policy_ref` | Polityka focus, ekspozycji, blur, widoczności i coverage |
| `required/optional`, `dependencies` | Czy ujęcie musi zostać ukończone i po jakich bramkach |

**Przykład semantyczny:** „sfotografuj ROI connector_A na odsłoniętej PCB z perspektywy bocznej”, a nie „J2 +18°”. Ujęcie skośne może mieć XY aparatu poza obrysem PCB. Receptura nie stanowi akceptacji trajektorii ani automatycznej gwarancji, że FoV obejmuje obszar. MoveIt 2 dobiera IK i bezkolizyjną trajektorię na podstawie bieżącej sceny, profilu narzędzia i robota. QA sprawdza wykonany obraz.

## 13. Sekcja 12 — `thermal_recipes` (opcjonalna)

Sekcja nie wymusza obecności kamery IR w zwykłej sesji. Dla obszarów termicznych opisuje:

- `roi_refs`, `physical_state` i wymagany sposób zasilania lub stan ECU (jeśli zatwierdzony zewnętrznie);
- tryb `relative_intensity` albo `radiometric`, osobne wymagane capabilities i politykę QA;
- dla radiometrii: kalibrację sensora, zasady pomiaru emisyjności materiału, temperaturę odbitą, znane niepewności oraz dopuszczalne formaty surowe;
- wymagane czasy, związanie z obserwacją i sceną oraz warunki rejestracji w jednym układzie z fotografią, tylko jeśli współrejestracja rzeczywiście skalibrowana;
- zakaz przypisywania temperatur absolutnych fałszywie kolorowanej mapie względnej.

Nie opisujemy „automatycznego podania zasilania ECU” jako domyślnej akcji profilu. To odrębna, weryfikowana zdolność instalacji z osobnym dopuszczeniem. Brak modułu termicznego nie blokuje scenariusza, który nie wymaga termowizji; wymagany moduł nie może zostać pominięty.

## 14. Sekcja 13 — `inspection_workflows`

Profil zawiera *receptury*, które odwołują się do zatwierdzonego `ScenarioSpec`, nie nowe wykonywalne skrypty. Przykładowe receptury:

- `external_identification` — weryfikacja zamkniętej obudowy i numerów;
- `pcb_documentation_top` — zdjęcia otwartego PCB według celów i QA;
- `pcb_variant_comparison` — powtarzalne ujęcia do późniejszego OpenCV;
- `thermal_screening` — moduł Thermal jako wymagany tylko, jeśli wybrana receptura i spełnione warunki.

Każda receptura wskazuje: `recipe_id`, `revision`, `supported_states`, `scenario_ref`, `required_capabilities`, `required_view_ids`, `required_modules`, `quality_policy_refs`, `archive_policy`, `operator_decisions`, `approval_scope`.

**Bez zmian w logice Core:**

| Etap Core | Odpowiedzialność profilu wzorcowego |
|---|---|
| S01 | Wymagane capabilities i zatwierdzone zależności |
| S02 | Dokładny wybór rodziny, wariantu, rewizji i receptury |
| S03 | Wymagania i punkty lokalizacyjne, nie aktualne XYZ |
| S04 | Reguły weryfikacji tożsamości, niejednoznaczności i odmowy |
| S05 | ECU-relative cele zdjęć, regiony PCB i QA/coverage |
| S06 | Wymagana aktualna scena i profil narzędzia/robota; bez przegubów w profilu |
| S07 | Zlecenia ujęć, transfer, zachowanie RAW i potwierdzenia |
| S08 | Polityka jakości, pokrycia i ewentualnej powtórki |
| moduły opt. | Thermal lub przyszłe etapy wymagane przez wybraną recepturę |
| S09 | Zweryfikowany osobny PARK, bez niejawnego pominięcia bramek |
| S10 | Wymagane oryginały, artefakty, snapshot profilu i SHA |
| S11 | Raport rzeczywistego wykonania/odmów |

Core weryfikuje końcowe dowody i nie rozpoczyna etapu bez poprzednich obowiązkowych zakończonych SUCCESS. Nie ma automatycznego retry ruchu po awarii ani domyślnego PARK po niepowodzeniu.

## 15. Sekcja 14 — `validation_policies`

Walidacja jest deklaratywną tablicą wymagań, nie dowolnym kodem/wyrażeniami wykonywanymi z pliku profilu. Możliwe kategorie:

- `identity` — kompletność niepowtarzalnych cech i wykluczenie nierozróżnialnych wariantów;
- `geometry` — zgodność obrysu i punktów, tolerancje z pomiaru, niepewność;
- `localization` — świeżość RGB-D, poprawność TF, jakość i niepewność położenia;
- `motion` — aktualna scena, collision clearance, robot/tool revision i potwierdzony wynik MoveIt;
- `photo` — RAW i potwierdzony transfer, ostrość/ekspozycja/pokrycie;
- `thermal` — odrębne polityki względne i radiometryczne;
- `archive` — integralność oryginałów, hash, wersja i dokumentacja.

Wynik walidacji zawiera `PASS`, `REJECTED`, `NOT_READY` lub `AMBIGUOUS`, powód, źródła dowodu, profil/rewizję i kontekst sceny. Wszystkie liczby progowe mają mieć własne źródło i zakres obowiązywania; brak zatwierdzonego progu nie jest domyślnym PASS.

## 16. Sekcja 15 — `provenance_release`

Każda wielkość używana do wykonania musi wskazywać: `value`, `units`, `datum`, `source_id`, `instrument`, `date`, `uncertainty`, `verification_status`, `review_reference`, ewentualnie wynik kontrolnego drugiego pomiaru.

- `DRAFT_NOTE`: wiadomość operatora, bez wymuszonego pomiaru;
- `MEASURED`: pomiar istnieje, nie jest jeszcze zatwierdzony;
- `VERIFIED`: pomiar i źródło zweryfikowano;
- `APPROVED_RELEASE`: cały związany snapshot zatwierdzony w konkretnym zakresie.

Snapshot posiada manifest plików i SHA-256, identyfikator rewizji oraz zatwierdzenie recenzenta. SHA-256 dowodzi spójności bitów, **nie** autentyczności podpisu ani sensora. Ochrona dostępu, kontrola recenzentów, polityka retencji i zaufane zatwierdzenie pozostają obowiązkiem wdrożenia. Nie zmieniamy wydanej rewizji w miejscu; nowe pomiary tworzą nową wersję.

## 17. Macierz gotowości i zakresu zatwierdzeń

Jeden wskaźnik `APPROVED` nie wystarcza. Dla każdego `state_id` i receptury system publikuje dopuszczenia funkcjonalne, np.:

| Zdolność | Warunek minimalny | Bez niego |
|---|---|---|
| `browse_and_select` | Tożsamość rekordu i DRAFT/approved | Możliwy podgląd DRAFT, bez wykonania |
| `verify_identity` | Cechy rozróżniające, źródła, lista wariantów i policy | `NOT_READY/AMBIGUOUS` |
| `localize` | Datum, punkty 3D, wymagania sensora, aktualne TF | `NOT_READY` |
| `photo_inspection` | Zatwierdzona geometria, lokalne cele i ujęcia, kalibracje, capabilities, QA | Brak planowania zdjęć/ruchu |
| `pcb_inspection` | Potwierdzony stan otwarty, ROI PCB i zależności | Brak inspekcji PCB |
| `thermal_relative` | Receptura, odpowiedni sensor i raw/QA | Nie uruchamiaj etapu IR |
| `thermal_radiometric` | Ponadto sprawdzona radiometria i metadane | Zakaz twierdzeń o °C/K |

Rozróżniamy stan dokumentacji profilu (DRAFT/APPROVED) od zdolności wykorzystania go w danej recepturze. W normalnym trybie operator może **obejrzeć** profil DRAFT, lecz nie może uruchomić operacji, do których brakuje zatwierdzenia.

## 18. Uruchomienie Vision — prekonfiguracja i weryfikacja

1. GUI wyświetla bibliotekę zatwierdzonych profili i ich zdjęcia poglądowe; DRAFT widoczny wyłącznie jako podgląd z ostrzeżeniem.
2. Operator wybiera `family → variant → revision`, stan fizyczny i recepturę inspekcji. Bez automatycznego zamieniania wariantów.
3. Loader sprawdza integralność manifestu i assetów, zatwierdzenie zakresu, dostępne capabilities i kalibracje stanowiska.
4. GUI pokazuje nominalną bryłę ECU, zdjęcia i planowane perspektywy oraz braki/warunki, które Luxonis ma potwierdzić.
5. Luxonis pozyskuje bieżące RGB-D i dane 3D. Adapter wykonuje recepturę weryfikacji: geometrię, landmarki, warianty, widoczność i aktualne położenie.
6. S04 zwraca wynik jawny: potwierdzony, niejednoznaczny, odrzucony lub brak danych; w razie niezgodności wymagana decyzja operatora i odpowiednia procedura. Nie jest dozwolone samoczynne przełączenie profilu.
7. Po PASS Core wiąże profil/recepturę, `T_world_ecu`, aktualną scenę i rejestruje przeliczone cele aparatu. Dopiero S05–S06 sprawdza planowanie i możliwości urządzeń.
8. Pozostałe etapy wykonują zlecenia i archiwizują wyniki konkretnego egzemplarza. Po sesji profil wzorcowy pozostaje nienaruszony.

## 19. Struktura przechowywania (logiczna, nie obowiązek bieżącej implementacji)

```text
ECU_LIBRARY/
  <family_id>/
    <variant_id>/
      releases/
        <revision>/
          reference-profile.json     # kanoniczny manifest i SHA
          approval.json              # osobny zweryfikowany odbiór
          assets-manifest.json       # nazwy, formaty, hashe, pochodzenie
          assets/
            photos/...               # obrazy referencyjne, prywatne wg polityki
            geometry/...             # zatwierdzone CAD/mesh/maski
          recipes/
            ...                      # deklaratywne instrukcje
SESSIONS/
  <session_id>/
    selected-profile-snapshot.json   # profile_id/revision/hash i receptura
    observation/...                  # RGB-D, TF, referencje pomiarów
    captures/...                     # oryginały Sony/IR i QA
    manifest-v1.json                 # archiwum zgodne z Core
```

Assety mogą pozostać na prywatnym magazynie; manifest zawiera referencje z hashami, bez wymagania publikacji zdjęć sterowników na publicznym GitHubie. Wersja wydana jest nienaruszalna logicznie; dostęp administratora nadal wymaga osobnej kontroli i backupu.

## 20. Kontrakt danych V1 — podstawowa struktura

Do tej specyfikacji dołączono **niezatwierdzony szablon JSON** z 15 sekcjami, polami `null` i pustymi kolekcjami. Szablon jest dokumentem architektonicznym, nie gotowym profilem ETC3 ani kompatybilnym już dzisiaj z kodem `ECURecord` z PR #46.

Przykładowy rekord pojedynczego ujęcia **bez danych fizycznych**:

```json
{
  "view_id": "VIEW_ID",
  "physical_state_id": "STATE_ID",
  "roi_refs": ["ROI_ID"],
  "camera_goal": {"frame": "ecu_local", "translation_mm": null, "quaternion_xyzw": null},
  "aim_point_mm": null,
  "working_distance_range_mm": null,
  "required_capabilities": ["capture.photo"],
  "quality_policy_ref": null,
  "required": true,
  "provenance_ref": null
}
```

Gdy pole ma `null` i jest wymagane do wykonania, receptura musi pozostać `NOT_READY`.

## 21. Zgodność z istniejącym Vision i plan migracji

Obecny `vision_core.profiles.ECUProfile` ma mały, słusznie ograniczony interfejs wykonawczy: nominalne X/Y, `max_height`, `pcb_regions`, `view_targets` XYZ, `view_quaternions_xyzw`, tolerancje, capabilities i kalibracje. **Nie poszerzamy Core o 15 sekcji referencyjnych.**

Draft PR #46 ECU Profiles V1 wprowadza katalog i kontrolowane wersje danych oraz weryfikację obserwacji. To odpowiedni punkt wyjścia, ale jeszcze nie zawiera kompletnej biblioteki referencyjnych zdjęć, stanów obudowy, modeli CAD, reguł Luxonis i receptur modułowych. Przyszły kompilator/adapter:

1. pobiera zatwierdzony `ECU Reference Profile` + odpowiednią recepturę i stan;
2. sprawdza zakres zatwierdzenia i powiązane assety;
3. tworzy/synchronizuje `ECURecord` / `ECUProfile` wykonawcze, zestaw wymagań capabilities oraz `ScenarioSpec`/referencje polityk;
4. wiąże dane bieżące z sesją dopiero **po** weryfikacji operatora i Luxonis;
5. blokuje działanie przy brakach zamiast domniemywać wartości.

Nie tworzymy nowego monolitycznego serwisu, alternatywnego planera ruchu, programów per ECU, ani „magicznego” wykonywalnego pliku profilowego.

## 22. Minimalne testy odbiorcze struktury V1 (do późniejszej implementacji)

| Obszar | Warunek PASS |
|---|---|
| Schema | odrzucone nieznane klucze, NaN, błędne jednostki, path traversal, brak wymaganych ID |
| Release | nowa rewizja przy zmianie danych, SHA/assets zweryfikowane, brak nadpisania historii |
| DRAFT | można wyświetlić; nie można go wykorzystać do ruchu lub sesji wymagającej braków |
| Warianty | identyczne fizyczne cechy alternatywnych wariantów → AMBIGUOUS |
| Lokalizacja | brak/nieaktualny TF lub Depth → NOT_READY; po przesunięciu ECU poprzedni plan nieważny |
| Stan ECU | closed vs open mają odrębne, zweryfikowane geometrie i widoczność PCB |
| Oblique view | cel aparatu może być poza XY płytki; rzeczywiste coverage weryfikuje się osobno |
| Integracja | zatwierdzony Reference Profile dostarcza istniejący Core ECUProfile bez zmiany Core |
| Termowizja | opcjonalny etap tylko na życzenie; wymagany etap bez modułu nie może być pominięty |
| Archiwum | sesja zawiera dokładne ID/revision/hash profilu, RAW, wyniki i dowody końcowe |
| Niezmienność | sesja nie zapisuje wyników do profilu wzorcowego |
| Brak sprzętu | można testować cały model bez ROS 2, NERO i rzeczywistej kamery |

## 23. ETC3 — pierwsza karta wzorcowa PoC

Pierwsze ECU to ETC3 ze zgłoszonym układem **dwóch czarnych i jednego szarego złącza**. Aktualne notatki 65/69 mm nie mają zatwierdzonego wspólnego datumu, a geometrii korpusu, otwartego PCB i przepisów na ujęcia Sony jeszcze nie zatwierdzono. **Nie tworzę pozornie pełnego profilu, modelu 3D ani obrazów.** Dla ETC3 możemy wypełnić sekcje 01 i część 02/06 z oznaczeniem „wstępne”, natomiast 03–05 i 08–14 pozostają DRAFT/NOT_READY tam, gdzie brakuje rzeczywistych danych.

Następny zatwierdzony etap to najpierw publikacja tej specyfikacji i szablonu w repozytorium, a następnie implementacja offline kodu ECU Reference Profile V1. Projekt edytora profilu i ekranu wyboru ECU w GUI będzie osobnym etapem. Referencyjna karta ETC3 wymaga później rzeczywistych pomiarów i zdjęć.

---

## Decyzje zaakceptowane

**Zalecane do zatwierdzenia:** 15-sekcyjny, sprzętowo niezależny schemat; rozdzielenie Reference/Execution/Session; profile wielostanowe; osobne zasoby z SHA; jawne instrukcje Luxonis; deklaratywne receptury Sony/IR; bramki gotowości per zakres, nie globalny bool; brak automatycznego podstawiania innego wariantu; DTO/adapter do istniejącego Core; brak wymyślonych parametrów ETC3.

**Dalsza decyzja projektowa (bez blokowania schematu):** jaka część gotowego profilu referencyjnego będzie zarządzana w GUI Vision, a jak będzie przebiegać formalne autoryzowanie recenzenta w magazynie wydań.
