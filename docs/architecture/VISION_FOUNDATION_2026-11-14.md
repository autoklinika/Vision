# Vision — fundament nowego systemu (ustalenia z 14.11.2026)

> **Status:** wymagania funkcjonalne i zasady prowadzenia projektu przyjęte przez właściciela w rozmowie 14.11.2026. Szczegóły stosu technologicznego i podziału wykonawczego są **PROPOSED — do weryfikacji i zatwierdzenia w osobnych ADR**. Dokument nie potwierdza gotowości robota do pracy autonomicznej.
>
> **Charakter:** dokument założycielski **nowego** systemu Vision; nie plan migracji starego kodu. Pełniejszy zapis dyskusji: [VISION_ARCHITECTURE_DISCUSSION_2026-11-14.md](VISION_ARCHITECTURE_DISCUSSION_2026-11-14.md).
>
> **Zasada publikacji:** dokumentacja i podsumowanie rozmowy bez prywatnych zdjęć, surowych danych ECU, sekretów, numerów seryjnych i konfiguracji sieciowej. Repozytorium jest publiczne.

## 1. Z czego wynika nowy start

Dotychczasowe prace na VENTUNO Q, Luxonis OAK-D Pro AF, AgileX NERO, Sony A6100, kamerze termowizyjnej, Stream Deck Plus oraz AI Platform były **testami uruchomieniowymi, diagnostyką i rozpoznaniem możliwości sprzętu**, a nie wdrożeniem docelowego systemu Vision. Część prototypów (np. własny Camera Service) powstała, zanim oceniliśmy standardowe rozwiązania ekosystemu ROS 2.

**Budujemy system Vision od podstaw. Nie migrujemy starego oprogramowania.** Zachowujemy doświadczenia, raporty, wyniki testów i wzorce regresji; żaden wcześniejszy prototyp nie zyskuje prawa do wejścia do nowego runtime tylko dlatego, że istnieje. Nie kasujemy historii ani gałęzi referencyjnych, w tym PR #15 oraz eksperymentalnych PR #20–24.

Nie traktować historycznego schematu „Camera Service → Perception Engine → Vision Core” jako automatycznie obowiązującego podziału procesów. Obowiązują funkcje, kontrakty i ograniczenia nowego projektu, a nie wcześniejsze nazwy usług. Rozdzielenie odpowiedzialności pozostaje ważne, ale granice wykonawcze ustalimy od nowa.

## 2. Misja stanowiska

Vision jest **modularnym stanowiskiem inspekcji optycznej, przestrzennej i opcjonalnie termicznej ECU/PCB**. Robot NERO w pierwszych etapach pełni przede wszystkim rolę precyzyjnego pozycjonera aparatu i czujników. Vision nie jest w pierwszej kolejności uniwersalnym robotem rozpoznającym dowolne, nieznane obiekty ani automatycznie demontującym ECU.

Docelowe funkcje:
1. Operator deklaruje typ i wariant ECU.
2. Vision ładuje profil ze znanymi cechami, wymiarami, zdjęciami referencyjnymi i planem inspekcji.
3. Kamera **weryfikuje zgodność** deklaracji i rzeczywistego obiektu oraz lokalizuje ECU w przestrzeni.
4. System aktualizuje scenę przestrzenną; przygotowuje plan obserwacji i ruchu zgodnie z profilem i obowiązującymi ograniczeniami.
5. NERO po dopuszczeniu przez niezależne zabezpieczenia pozycjonuje aparaturę; Sony wykonuje zdjęcia, a pozostałe czujniki dostarczają uzupełniających danych.
6. Vision sprawdza jakość ujęć, obsługuje powtórki i zachowuje oryginały.
7. Minisforum / AI Platform wykonuje zadania AI, kiedy są potrzebne i dopuszczone w profilu zadania.
8. Wyniki i metadane są archiwizowane; stanowisko kończy zadanie w bezpiecznym stanie.

Nie wprowadzamy automatycznej identyfikacji modelu ECU jako obowiązkowego warunku wejścia. Jeśli wykryto niezgodność lub brak wystarczającej pewności, system ma żądać sprawdzenia przez operatora, a **nie samoczynnie zmieniać deklarację**.

## 3. Wiążące decyzje właściciela

**REQ-001 — deklaracja ECU.** Operator wybiera ECU przed sesją; automatyka może potwierdzić bądź zakwestionować wybór.

**REQ-002 — wielokrotne użycie wiedzy.** Dla znanych ECU wykorzystujemy wcześniej ustalone informacje: maksymalną wysokość, obrys, położenie złączy, punkty referencyjne, oczekiwane obszary fotografowania, zdjęcia wzorcowe i plany inspekcji. Ograniczamy konieczność każdorazowego skanowania i samodzielnego odkrywania geometrii.

**REQ-003 — greenfield.** Nowy Vision piszemy od początku. Nie dokonujemy migracji aplikacji, modułów ani struktury architektonicznej z eksperymentów. Reużycie *wiedzy/testów* jest obowiązkowe, reużycie *kodu* nie jest założeniem.

**REQ-004 — modularność.** Wymiana modelu AI kamery, kamery, sterownika, modelu analizy ECU lub innego komponentu nie może wymagać przepisywania logiki całego Vision. Moduły i adaptery mają stabilne, wersjonowane kontrakty.

**REQ-005 — gotowe rozwiązania przed własnym kodem.** Najpierw oceniamy dojrzałe biblioteki, SDK, ROS 2 i narzędzia producentów. Własny kod tylko do brakujących funkcji stanowiska i integracji.

**REQ-006 — AI nie steruje bezpośrednio napędami.** AI dostarcza obserwacje, wykrycia, wyniki i sugestie; Vision podejmuje decyzje procesowe, a sterowanie ruchem przechodzi przez jedną kontrolowaną bramkę.

**REQ-007 — testowalność.** Moduły, gdzie technicznie możliwe, muszą działać z nagranymi obrazami, symulatorami i atrapami urządzeń. Testy dokumentacji/kontraktów nie wyzwalają ruchu, migawki ani zasilania.

**REQ-008 — niezależne bezpieczeństwo.** Głębokość, AI, ROS 2, MoveIt, Stream Deck i wywołanie STOP w SDK nie stanowią samodzielnie niezależnego toru bezpieczeństwa operatora.

## 4. Profile ECU — dane a pomiary

Profil ECU to wersjonowany zbiór wiedzy o **typie/wariancie**, nie o pojedynczej sesji. Przechowujemy:
- identyfikatory producenta / rodziny / modelu / wariantu;
- gabaryty nominalne i **maksymalne** dopuszczone do planowania, wraz z jednostkami i źródłem pomiaru;
- obrys, złącza, elementy wystające, obszary niedostępne i charakterystyczne punkty;
- zdjęcia referencyjne / lokalizacje punktów kontrolnych;
- plan inspekcji i parametrów akwizycji;
- opcjonalne referencje do modeli AI, wraz z wersjami i poziomem dopuszczenia;
- historię zmian profilu.

Osobno utrzymujemy **sesję** danego fizycznego egzemplarza: identyfikator, wybór operatora, status weryfikacji, kalibrację, pozycję na stole, ujęcia, daty, wyniki, wersje algorytmów i ich provenance. Osobno przechowujemy **artefakt modelu AI**, jego manifest, typ zadania, wejścia/wyjścia, wersję, hash i testy regresyjne.

**Ważne:** dane deklarowane służą do wstępnego planu i weryfikacji; nie zastępują aktualnej kontroli położenia, stanu robota, obwiedni kolizyjnej i zabezpieczeń. Niepewność ma dawać stan `NOT_READY`/wymagane potwierdzenie, a nie „bezpieczny” wynik przez domyślne założenie.

## 5. Proponowana warstwa gotowych systemów (jeszcze nie wdrożona jako Vision)

| Element | Rola | Status |
| --- | --- | --- |
| ROS 2 Jazzy | komunikacja systemu robotycznego na Ubuntu 24.04 ARM64 | **KANDYDAT GŁÓWNY**, weryfikacja zgodności |
| AgileX `agx_arm_ros` | obsługa NERO, odczyt stanu i sterowanie | **DO TESTU** na firmware NERO |
| MoveIt 2 | kinematyka, planowanie trajektorii, model sceny kolizyjnej | **DO TESTU**, bez ruchu fizycznego |
| tf2, URDF/Xacro | geometria i transformacje między stołem, robotem i sensorami | **PODSTAWA DO PROJEKTU** |
| RViz 2 | wizualizacja i testy offline | **DO URUCHOMIENIA** |
| Luxonis DepthAI ROS v3 | oficjalny tor RGB, stereo i depth, ewentualnie modele na urządzeniu | **DO TESTU**; jeden właściciel USB |
| OpenCV + ChArUco | kalibracja, rejestracja i klasyczne algorytmy obrazu | **DO WALIDACJI METROLOGICZNEJ** |
| rosbag2 | rejestracja i odtwarzanie danych ROS | **ZALECANE** |
| Sony Camera Remote Command/PTP | podstawa adaptera aparatu, z potwierdzeniem konkretnego firmware i komend | **DO TESTU** |
| Gazebo, MoveIt Servo, BehaviorTree.CPP, MLflow | pełna symulacja, sterowanie serwo, złożone workflow i rejestr modeli | **ODŁOŻONE** do uzasadnionych potrzeb |

ROS 2 nie zastępuje identyfikacji ECU, logiki sesji, kontroli jakości zdjęć ani weryfikacji bezpieczeństwa. Używamy standardowych komunikatów ROS tam, gdzie istnieją, zamiast powielać ich znaczenie we własnych protokołach.

## 6. Proponowane moduły logiczne Vision (nie liczba usług Linux)

1. **Vision Workflow** — maszyna stanów i koordynacja sesji, recovery i decyzje operatora.
2. **ECU Catalog** — profile i plany inspekcji, wersjonowanie.
3. **Scene Verification** — porównanie ECU z deklaracją, pozycja, przeszkody i jakość obserwacji.
4. **Motion Gateway** — jedyna dopuszczona programowa ścieżka żądania ruchu, weryfikacja warunków, integracja z MoveIt 2; *nie* zamiennik sprzętowego toru bezpieczeństwa.
5. **Camera Adapters** — Luxonis ROS, Sony, opcjonalna termowizja i przyszłe sensory.
6. **Image Quality** — ostrość, ekspozycja, pokrycie, powtórki, obróbka obrazu.
7. **AI Bridge** — żądania i wyniki do istniejącego Resource Managera AI Platform; bez dublowania zarządzania GPU.
8. **Session Storage** — metadane, oryginały, wyniki, hashe, archiwizacja.
9. **Vision HMI** — WebGUI operatora, stan urządzeń i proces.

To **warstwy odpowiedzialności**: nie ma wymogu osobnego procesu dla każdej. Możemy grupować funkcje w odpowiedzialnie wyznaczone procesy ROS, lokalne usługi i API. Komunikacja wysokoprzepustowa/sterująca powinna korzystać z odpowiednich typów ROS (topics/services/actions), a komunikacja z UI i AI Platform z odpowiednio wersjonowanych API.

Planowane kontrakty semantyczne: `ECUProfile.v1`, `SceneObservation.v1`, `MotionRequest.v1`, `CaptureRequest.v1`, `CaptureResult.v1`, `AIJob.v1`, `InspectionResult.v1`. Są to **nazwy robocze**, a nie wdrożone API. Każdy pomiar 3D musi zawierać frame_id, jednostkę, timestamp, wersję kalibracji, status jakości i informacje o niepewności. Zmiana modelu AI wymaga zachowania kontraktu, zgodności z profilem i walidacji regresji.

## 7. Role komputerów i pamięci

**VENTUNO Q:** lokalna integracja ROS 2, obserwacja i geometria, planowanie, sterowanie po dopuszczeniu, aparatura i HMI. Nie wiążemy bezpieczeństwa z dostępnością sieci.

**AI Platform / Minisforum:** trening, analiza zdjęć na RTX, wymienne modele AI, kolejka i Resource Manager. Bez samodzielnego publikowania komend do NERO.

**Dane:** na start katalog i sesje w lokalnej bazie SQLite za API, zdjęcia/RAW i manifesty na NVMe, kontrolowane kopie na NAS. Baza i magazyn pozostają wymienne przez repozytoria/interfejsy. Nie wdrażamy dużego MLOps i klastra baz danych bez potrzeby.

## 8. Krytyczne ryzyka i warunki ruchu

- **Bezpieczeństwo fizyczne:** osobny przegląd funkcji zatrzymania, wejść bezpieczeństwa NERO i możliwości niezależnego obwodu; uwzględnić ryzyko opadnięcia ramienia po odłączeniu 24 V. Sam przycisk STOP w OpenDeck ani GPIO nie zapewnia bezpieczeństwa.
- **Eye-in-Hand / widoczność:** jedna kamera Luxonis może mieć martwe pola i zasłonięcia podczas ruchu. Rozstrzygnąć rozmieszczenie i wymagane obserwacje sceny; nie obiecywać ciągłej, niezależnej ochrony ludzi na podstawie depth.
- **Geometria:** ustalić transformacje `robot_base`–`J7`–`tool`–`camera`–`table`, fizyczny model adaptera i przewodów, walidować poprawność kalibracji.
- **Metrologia:** testy wzorców 34 / 50,4 / 101 mm z 13.11.2026 (PR #24) nie spełniły warunku ±1 mm dla wszystkich konfiguracji; algorytm i sensor nie są uznane za skalibrowane metrologicznie. Oddzielamy dokładność inspekcji od konserwatywnej geometrii kolizyjnej.
- **Integracja:** weryfikacja ROS 2/sterowników na VENTUNO, komunikacji NERO i jedynego właściciela USB, zachowanie przy utracie łączności i restartach.

**Zakaz przyjmowania autonomii jako gotowej:** żadnego ruchu robota bez dopuszczenia przez wymagane zabezpieczenia, szczególnych testów i zgody operatora.

## 9. Etapy realizacji i bramki

1. **Specyfikacja i kontrakty:** zaakceptowany przykładowy profil ECU i pełna ścieżka sesji bez sprzętu.
2. **Środowisko ROS 2 offline:** sterownik i model NERO, narzędzia planowania i wizualizacja; bez wykonywania ruchu fizycznego.
3. **Pierwsza sesja offline:** profil, obserwacje z zapisanych danych, weryfikacja, plan, jakościowa analiza i archiwum.
4. **Geometria i bezpieczeństwo:** kalibracja stanowiska, walidacja modelu kolizji, wymagane niezależne zabezpieczenia.
5. **Pierwsza ograniczona sesja z rzeczywistym NERO:** tylko po spełnieniu wszystkich wcześniejszych bramek; pomiar hamowania, odzyskiwanie z awarii i kontrola jakości.

## 10. Pierwszy scenariusz — korekta wyboru ECU

**Pierwsze ECU do opracowania: ETC3, nie DAF SAC.**

Identyfikator roboczy: **„ETC3 — pierwszy egzemplarz mierzony 14.11.2026; trzy złącza: dwie czarne wtyczki i jedna szara”**. To cechy rozróżniające przekazane przez właściciela; *nie* automatycznie odczytany numer katalogowy ani ostateczny wariant produktu.

Pomiary wykonane 14.11.2026 mają być materiałem wejściowym do osobnej karty danych ETC3, z jawnymi źródłami i statusem weryfikacji. **Nie przenosimy jeszcze wymiarów do obowiązującego profilu jako pewnych**, dopóki nie uzgodnimy, które odnoszą się do obudowy, złączy i punktów maksymalnej wysokości oraz czy chodzi o ten sam układ odniesienia. Scenariusz będzie zaprojektowany **po** zatwierdzeniu fundamentu, a nie w tym PR.

## 11. Relacja do starych dokumentów / PR

- [PR #15](https://github.com/autoklinika/Vision/pull/15): archiwum testów i historii, bez automatycznego merge.
- [PR #20](https://github.com/autoklinika/Vision/pull/20): historyczny test Camera Service, nie gotowy składnik nowego Vision.
- [PR #21](https://github.com/autoklinika/Vision/pull/21): wcześniejszy zaakceptowany podział Camera/Perception/Core, **do ponownej oceny** na podstawie ustaleń 14.11.
- [PR #22](https://github.com/autoklinika/Vision/pull/22)–[#24](https://github.com/autoklinika/Vision/pull/24): testy synchronizacji, optyki i geometrii; wartościowe wyniki oraz regresje, bez obowiązku migracji kodu.

Ten dokument **nie modyfikuje istniejącego runtime, nie uruchamia ROS 2 i nie dopuszcza NERO do autonomicznej pracy**. Rewizje architektury i nowe wdrożenia przechodzą osobne PR, testy oraz bramki bezpieczeństwa.

## 12. Następny krok po zatwierdzeniu fundamentu

Przygotować **ETC3 — profil roboczy i pojedynczą kompletną sesję offline**, z deklaracją ECU, weryfikacją, planem akwizycji, oceną jakości, opcjonalnym zadaniem AI i archiwizacją. Nie rozpoczynać od DAF SAC.
