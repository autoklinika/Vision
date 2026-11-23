# VISION CORE — szczegółowy audyt integracyjny 0.1–0.3

**Data:** 2026-11-23
**Status:** REVIEW CANDIDATE / PR DRAFT. Bez odbioru użytkownika, bez merge, bez wdrożenia sprzętowego.
**Zakres:** Foundation, Photography, Repeatable Inspection, wspólny Workflow S01–S11, sesje SQLite, profile, sceny, plan ujęć, kontrola jakości i archiwum.

## 1. Punkt odniesienia i stan Git

| Element | Baza przed audytem | Status |
| --- | --- | --- |
| Main | f3c6b5cabb8a94e08845aeffd7ca7bbe4b587a4f | bez zmian |
| [PR #39 — Foundation](https://github.com/autoklinika/Vision/pull/39) | d90902c431c1073c19382c7605b9b4945a72ad95 | draft, brak merge |
| [PR #40 — Photography](https://github.com/autoklinika/Vision/pull/40) | 132f838e7ecff1992b0cb9a8428aaffefc32c02d | draft od #39 |
| [PR #41 — Repeatability](https://github.com/autoklinika/Vision/pull/41) | 83abf1c470cd6c566b5c637188af49c3cd82b56e | draft od #40 |
| Audyt naprawczy | osobna gałąź od #41 | oddzielny draft PR, oczekuje na odbiór |

Obowiązuje ADR-VISION-CORE-001 (ACCEPTED), Vision Inspection Workflow V1 i polityka higieny repozytorium. Zamrożone VGP V1 nie było modyfikowane, nie uruchamiano ROS 2, MoveIt, NERO, Luxonis, Sony, CAN ani migawki. Nie użyto rzeczywistych zdjęć ECU i kalibracji.

## 2. Metoda

1. Porównano 0.1, 0.2 i 0.3 w jednym checkout z wymaganiami ADR i specyfikacji.
2. Kilkukrotnie wykonano **niezależny przegląd kodu** przez osobnego agenta tylko do odczytu. Wyniki agentów traktowano jako hipotezy do samodzielnego odtworzenia, nie jako dowód.
3. Przed zmianami zapisano testy, które **rzeczywiście obnażały błędy**: początkowe pięć regresji FAIL; kolejne dwa testy nieaktualnej instancji i limitu czasu FAIL; następne dwa testy niepewnego zapisu/STOP FAIL.
4. Poprawiono implementację i uruchomiono ponownie całe testy syntetyczne oraz ograniczoną infrastrukturę SQLite/OpenCV.
5. Pełny test integracyjny wykonuje S01→S11 z planem związanym z ECU, dwoma różnymi obrazami PNG, syntetycznymi oryginałami RAW, polityką QA OpenCV, zewnętrznie potwierdzonym w teście pokryciem, osobnym mockiem PARK, archiwum i replay po restarcie.
6. Dodatkowo 120 deterministycznych zestawów prostokątów zweryfikowano względem niezależnego algorytmu rastrowego (suma/intersekcja).
7. Testy są offline i nie zastępują testów sprzętowych ani metrologicznych.

## 3. Rejestr wykrytych i naprawionych błędów

| ID | Waga | Problem przed poprawką | Zastosowany mechanizm i test |
| --- | --- | --- | --- |
| AUD-01 | P1 | Restart mógł zgubić wcześniejsze unieważnienie sceny, jeśli awaria nastąpiła przed blokadą wszystkich etapów | Replay respektuje trwały context_invalidated; test partial_invalidation |
| AUD-02 | P1 | Dwie instancje Workflow mogły zlecić S01 jednocześnie | SQLite unique stage_claims + BEGIN IMMEDIATE i atomowa rezerwacja etapu; test równoległych połączeń |
| AUD-03 | P1 | Plan S05 nie był wymuszony przez S06/S07/S08 — możliwe zdjęcia z innych celów lub z wyłączonym RAW | Trwały digest zaakceptowanego planu, wymagane dokładnie te same cele, orientacje, RAW i plan-bound CoverageProof |
| AUD-04 | P1 | Zmiana zawartości profilu bez zmiany numeru rewizji nie unieważniała sesji | Kanoniczny SHA-256 sześciu profili, kalibracji, capabilities i wymagań |
| AUD-05 | P1 | Wynik mógł pochodzić sprzed dyspozycji, a mimo to przechodzić bramkę świeżości | Zapis czasu dispatch i sprawdzenie causal order dla wyników, motion, capture, coverage |
| AUD-06 | P1 | Stary worker mógł nadpisać trwały BLOCKED zapisany przez restart innej instancji | Transakcyjne sprawdzanie trwałego stanu przy complete/stop; test stale_instance |
| AUD-07 | P1 | Sesję można było wznowić z luźniejszym max_age i zaakceptować stare dane | max_age również przypięte do konfiguracyjnego fingerprintu i sprawdzane na każdym etapie |
| AUD-08 | P1 | CoverageProof identyfikował tylko view_id, nie konkretne zapisane zdjęcia | CaptureBinding zawiera kanoniczny hash źródła/transferu/original SHA-256; porównanie proof z manifestem bieżących ujęć |
| AUD-09 | P1 | Po niejednoznacznym błędzie zapisu SQLite ten sam worker mógł ponownie zaakceptować wynik lub nieudany STOP | Fail-closed lokalnej instancji po exception, nowa instancja wymaga replay/reconciliation; dwa testy uncertain_transaction uprzednio FAIL |
| AUD-10 | P2 | Nadmierne footprinty lub bomba dekompresji mogły wyczerpać zasoby | Jawne limity danych, liczby footprintów, siatki, JPEG/PNG IHDR/SOF, plików/manifestów; testy wejść skrajnych |

**Ważne:** to bramki aplikacyjne, nie certyfikowane funkcje bezpieczeństwa ani zastępstwo przyjętego laboratoryjnego HOLD.

## 4. Limity przyjęte w implementacji offline

| Kontrola | Limit |
| --- | --- |
| Ujęcia, regiony PCB, footprinty | maksymalnie 128 każdego rodzaju |
| Siatka obliczenia obszarów | maks. 100 000 komórek |
| Odległości/współrzędne lokalne | w zakresie ±1 000 000 mm |
| Zakodowany JPEG/PNG | do 128 MiB |
| Dekodowany obraz | do 50 mln pikseli |
| Jedno archiwizowane zdjęcie/RAW | do 128 MiB |
| Manifest | do 16 MiB |

Te limity są implementacyjnymi zabezpieczeniami offline, a nie zmierzonymi parametrami docelowego Sony. Adapter musi ograniczyć rozmiar **przed** alokacją obrazu w pamięci. Zapis transferu strumieniowego nie jest jeszcze zaimplementowany.

## 5. Rejestr testów

Do pakietu audytowego dołączono testy:
- test_audit_regressions — świadome próby obejścia bramek i przyjętego planu;
- test_audit_hardening — współbieżny start oraz przerwany zapis SQLite;
- test_plan_binding — plan S05 do ujęć i pokrycia S08;
- test_post_audit_regressions — stary worker, max_age i powiązanie hashy zdjęć;
- test_uncertain_transaction — błędy trwałego zapisu success/STOP;
- test_resource_limits — JPEG/PNG, archiwum i obszary;
- test_integrated_inspection_v1 — pełna sesja S01→S11 i replay;
- test_coverage_properties — 120 dodatkowych porównań geometrycznych.

**Oryginalne testy 0.1–0.3:** 50.
**Po audycie:** 79 testów (łącznie z nowymi przypadkami i testem end-to-end); uruchamiane razem.
**CI dla pakietu napraw:** wymagany osobny rzeczywisty przebieg GitHub Actions po utworzeniu draft PR; wynik poprzednich PR nie potwierdza automatycznie poprawek.

**Podział CI:** workflow Foundation uruchamia 18 testów niezależnych od OpenCV (14 Foundation + 2 audyt współbieżności + 2 niepewny zapis). Workflow Photography i Repeatability instalują przypięte numpy/OpenCV i każdy uruchamia pełny zestaw 79 testów; dzięki temu Foundation nie wymaga zależności obrazowych. Wszystkie trzy muszą przejść na ostatecznym commicie PR naprawczego.

Komendy walidacyjne: PYTHONPATH=src python3 -m unittest discover -s tests/core -v, python3 -m compileall -q src/vision_core tests/core, git diff --cached --check.

## 6. Granice rzeczywistej integracji i źródła ryzyka

- Core sprawdza korelację, identyfikatory, hashe, czas i stan Workflow, ale **nie uwierzytelnia fizycznego źródła twierdzeń** o położeniu aparatu, stanie NERO, pomiarze footprintów i zgodzie operatora. Przyszły adapter musi to zapewnić.
- Plan XYZ+kwaternion względem ECU nie oznacza rozwiązania IK ani gwarancji bezkolizyjnej trajektorii — te pozostają w standardowym MoveIt 2.
- OpenCV ocenia piksele (ostrość/ekspozycję/ROI); rzeczywiste FoV i pokrycie PCB potrzebują potwierdzonej geometrii i kalibracji.
- Nie testowano automatycznego transferu RAW+JPEG Sony przez Wi-Fi/USB/SD, rzeczywistego autofocusa, zoomu ani fizycznych ruchów.
- Oryginały są zapisywane bez nadpisywania z SHA-256; uprawnienia same w sobie nie są systemem WORM. Wdrożenie wymaga backupu, niezależnej ochrony hashy i polityki sprzątania niekompletnych operacji.
- Powtarzanie ujęć w 0.3 oznacza kontrolowaną **decyzję**, a nie fizyczne uruchomienie robota czy migawki.
- HOLD jest przyjętym laboratoryjnym rozwiązaniem operacyjnym pod osobistym nadzorem operatora; ten PR nie zmienia uzgodnień ani sterownika.
- W razie niejednoznacznego błędu nie wznawiamy automatycznie ruchu ani nie wykonujemy PARK.

## 7. Decyzja i warunki merge

**Wniosek:** po potwierdzonym zielonym CI i odbiorze diff można przedstawić poprawiony fundament 0.1–0.3 do akceptacji **jako bibliotekę offline**. Bez tego nie ma zgody na merge. Nie wolno utożsamiać tego odbioru z gotowością produkcyjną.

Warunki:
1. Zmiany audytowe jako osobny draft PR z bazą na gałęzi 0.3.
2. Rzeczywisty CI: wszystkie testy i compileall PASS, żadnych danych prywatnych i importów sprzętowych.
3. Akceptacja właściciela przed merge; plan kolejności #39 → #40 → #41 → PR audytowy.
4. Nie uruchamiać na fizycznym stanowisku przejściowych stanów main w trakcie sekwencji merge.
5. Po operacjach sprawdzić finalny commit main, CI i brak zmian usługi oraz zamrożonego VGP V1.
6. Integracja rzeczywistego VGP i Sony to kolejny odrębny pakiet z testami fizycznymi.

**Brak wdrożenia, brak certyfikacji metrologicznej, brak autonomii.**
