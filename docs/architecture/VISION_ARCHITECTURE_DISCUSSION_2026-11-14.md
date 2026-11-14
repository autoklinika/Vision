# Vision — zapis rozmowy założycielskiej o architekturze (14.11.2026)

> **Cel archiwum:** zachować przebieg rozumowania, argumenty i ustalenia, a nie tylko listę decyzji. Źródłem jest rozmowa użytkownika z asystentem w projekcie Vision.
>
> **Format zapisu:** wypowiedzi użytkownika zachowano dosłownie (w tym literówki). Wypowiedzi asystenta zapisano jako **rozszerzony zapis redakcyjny w Markdown**: treść i argumentację zachowano, ale pominięto interaktywne elementy interfejsu, grafiki i techniczne identyfikatory cytowań, a część powtórzeń skondensowano. **Nie jest to automatyczny eksport 1:1 surowego czatu.** Jeśli archiwalny cytat różni się od aktualnych decyzji, nadrzędny jest [dokument fundamentowy](VISION_FOUNDATION_2026-11-14.md).
>
> **Granica dyskusji:** od prośby o ponowne przemyślenie architektury do wskazania ETC3 jako pierwszego scenariusza. W zapisanej rozmowie odróżniamy propozycje asystenta od akceptacji właściciela.
>
> **Uwaga bezpieczeństwa:** przed publikacją w publicznym repo nie zamieszczano tajnych danych połączeniowych, prywatnych zdjęć i surowych pomiarów. Opisy elementów sprzętu pochodzą z rozmowy, a nie z bieżącego audytu urządzeń.

---

## Wymiana 1 — ponowne zdefiniowanie projektu

### Użytkownik

> Musimy jeszcze raz przedyskutować projekt bo z tytułu mojej niewiedzy robi nam się niezły bałagan. Musimy jeszcze raz przemyśleć architekturę względem zadania jakie stanowisko vision ma wykonywać docelowo. Na przykład nie wiedziałem co to ROD2, a wygląda na to że musimy go wdrożyć . Może są jesCE jakieś inne systemy o których nie wiem a są nam niezbędne do przyspieszenia projektu. Wszystko co do tej pory robiliśmy to były testy uruchomieniowy każdego elementu systemu. Nie potrzebnie urachmialismy już systemowo kamerę.

### Asystent — odpowiedź (zapis redakcyjny)

Proponuję potraktować dotychczasowe prace jako etap uruchomienia i poznania sprzętu, a nie jako zatwierdzoną architekturę produkcyjną. Przeanalizuję docelowy proces pracy stanowiska, sprawdzę istniejące ekosystemy robotyczne i rozdzielę to, co warto wykorzystać, od tego, co niepotrzebnie napisalibyśmy sami. Na tym etapie bez zmian w działającym systemie.

**Powinniśmy przeprojektować architekturę Vision od podstaw, ale bez kasowania dotychczasowych prac.** Najważniejsze jest rozróżnienie dwóch etapów:

- Etap 1 — uruchomienie sprzętu: sprawdziliśmy VENTUNO Q, Luxonis, AgileX NERO, komunikację CAN, Stream Deck i AI Platform. Poznaliśmy możliwości oraz ograniczenia urządzeń.
- Etap 2 — projekt właściwego stanowiska: ten etap dopiero powinniśmy rozpocząć. Określamy pełny proces pracy z ECU, wybieramy gotowe rozwiązania i dopiero potem projektujemy własne oprogramowanie.

Dotychczasową architekturę Camera Service, Perception Engine i Vision Core należy ponownie ocenić, zamiast rozwijać ją automatycznie.

**ROS 2 jest ważnym odkryciem.** AgileX udostępnia integrację ROS 2 dla NERO i konfigurację MoveIt 2; Luxonis oferuje DepthAI ROS v3. Zamiast implementować od podstaw obsługę sterowania robotem, kinematykę, wymianę obrazów i point cloud, możemy oprzeć się na istniejącym ekosystemie. ROS 2 nie rozwiązuje jednak sam problemu inspekcji ECU: nadal potrzeba kalibracji, rozumienia sceny, planowania zadania i logiki procesu.

### Docelowy proces przedstawiony przez asystenta w pierwszej propozycji

1. Automatyczne rozpoznanie ECU na stole (później **skorygowane przez użytkownika**: model deklaruje operator, kamera jedynie weryfikuje zgodność).
2. Pomiar przestrzenny: obrys, orientacja, wysokości, złącza, przeszkody i układy współrzędnych.
3. Zaplanowanie inspekcji i bezkolizyjnych pozycji NERO z uwzględnieniem Sony, Luxonis i ich uchwytów.
4. Fotografia ogólna, fotografia detali, ujęcia pod różnymi kątami i z dobranym oświetleniem.
5. Kontrola jakości zdjęć, ostrości, ekspozycji i pokrycia PCB, opcjonalne ponowienia, focus stacking i składanie obrazów.
6. Opcjonalna inspekcja termiczna.
7. Analiza danych na Minisforum / AI Platform.
8. Parkowanie robota, archiwizacja danych i raport ECU.

**Wniosek:** to proces stanowiska powinien wyznaczać architekturę, nie odwrotnie.

### Wstępna lista rozwiązań przedstawiona w rozmowie

| Rozwiązanie | Proponowane zastosowanie |
| --- | --- |
| ROS 2 Jazzy | integracja i komunikacja w robotyce |
| AgileX ROS 2 | sterownik NERO |
| Luxonis DepthAI ROS v3 | obrazy i dane RGB-D |
| MoveIt 2 | kinematyka i planowanie ruchu |
| tf2 + URDF/Xacro | układy współrzędnych i geometria narzędzia |
| RViz 2 | wizualizacja |
| OpenCV + ChArUco | kalibracja i klasyczna analiza obrazów |
| Gazebo Harmonic | potencjalna symulacja |
| rosbag2 | zapis i odtwarzanie danych |
| BehaviorTree.CPP | potencjalny silnik złożonego workflow |

Propozycja zakłada użycie oficjalnych sterowników i frameworków, jednak nie jest dowodem, że sprawdziliśmy już każdy z nich na VENTUNO Q. Istotne jest także, że nie wszystkie narzędzia z listy muszą być instalowane jednocześnie.

### Wstępny model logiczny asystenta

- **Vision — koordynator:** przygotowanie zadań, sekwencja pracy, kontrola jakości, obsługa błędów i wyników.
- **VENTUNO Q / ROS 2:** połączenie Luxonis, NERO, MoveIt 2, tf2, Sony i termowizji przez adaptery.
- **AI Platform / Minisforum:** modele ECU, RTX, analiza, trenowanie, kolejka zadań.
- **Niezależna warstwa bezpieczeństwa:** interlocki i fizyczne zabezpieczenia; nie zależą od poprawności działania AI czy Linuxa.

ROS 2 nie rozpoznaje automatycznie ECU i nie ocenia sam jakości fotografii. MoveIt 2 planuje ruch w opisanej scenie, ale potrzebuje poprawnych danych o geometrii i przeszkodach.

**Ocena wykonanych prac:** systemowa usługa kamery powstała za wcześnie jako potencjalny składnik produkcyjny. Była jednak wartościowa jako test. Nie powinniśmy przenosić jej automatycznie do nowej architektury. Powinniśmy zweryfikować oficjalny sterownik Luxonis ROS 2, a dopiero potem porównać własne doświadczenia. Jednoczesny dostęp dwóch procesów do jednego urządzenia USB nie może być dopuszczony.

W testach dokładności wysokości przyjęta bramka ±1 mm nie została osiągnięta. Przejście na ROS 2 samo nie naprawia geometrii, transformacji ani metrologii.

**Istotne zagadnienia:** konfiguracja Eye-in-Hand z kamerą na ramieniu obok Sony może dawać martwe pola podczas ruchu, a kamera nie zastępuje niezależnego zabezpieczenia operatora. STOP na Stream Deck jest programowy; niezweryfikowane pozostaje ryzyko opadnięcia ramienia po utracie zasilania.

**Proponowany następny etap:** specyfikacja funkcjonalna, audyt gotowych rozwiązań, dopiero potem nowy ADR i plan wdrożenia. Najpierw gotowy komponent, dopiero przy braku odpowiednich rozwiązań własny kod.

---

## Wymiana 2 — cztery korekty właściciela

### Użytkownik

> Kilka sprostowań:
> 1. Nie musimy automatycznie rozpoznawać ecu. Możemy je deklarować na początku pracy. System może weryfikować czy dokonaliśmy dobrego wyboru.
> 2. Ze względu że będziemy zazwyczaj pracować ze znanymi już ecu to spora część danych też możemy deklarować (np max wysokość )
> 3. System vision budujemy od podstaw, niczym nie migrujemy, ale wykorzystujemy dotychczasową zdobytą wiedzę
> 4. Vision musimy budować modularnie (oczywiście to co możemy). Chodzi mi o to, że np wymiana modelu w kamerze nie może wiązać się z przeróbką systemu.
> Reszta wstępnych założeń wydaje się ok

### Asystent — odpowiedź (zapis redakcyjny)

Przyjmuję cztery sprostowania jako podstawowe wymagania projektowe Vision. Dzięki nim możemy uprościć cały system: nie musimy za każdym razem odkrywać rodzaju obiektu i wszystkich jego właściwości od początku.

**1. ECU deklaruje operator, Vision weryfikuje.** Operator wybiera sterownik z katalogu; kamera sprawdza zgodność rzeczywistego egzemplarza z profilem, np. na podstawie gabarytów, obrysu, złączy lub obrazu referencyjnego. Przy braku pewności wymagane jest sprawdzenie, a nie cicha automatyczna zmiana profilu.

**2. Katalog ECU jako ważny element architektury.** Przykładowe pola: producent, model, wariant, długość, szerokość, maksymalna wysokość, złącza i części wystające, punkty referencyjne, znane obszary PCB, plan fotografowania, przypisany model AI, historia sesji. Deklarowana wysokość pomaga planować, ale nie daje automatycznego potwierdzenia bezpieczeństwa bez sprawdzenia położenia i przeszkód.

**3. Vision budujemy od początku.** Nie migrujemy istniejącego oprogramowania. Zachowujemy poprzednie raporty, wyniki i wiedzę. Poprzednie podziały i nazwy usług nie determinują nowego rozwiązania.

**4. Modułowość jest obowiązkowa.** Trzeba oddzielić:
- sterownik urządzenia — komunikacja z kamerą, robotem i aparatem;
- model AI — np. detekcja obiektów, złączy i anomalii;
- logika Vision — decyzje o sekwencji zadań, jakości i ruchu.

Między warstwami powinny istnieć wersjonowane kontrakty. Zmiana modelu może wymagać nowego artefaktu, konfiguracji i walidacji, ale nie przeróbki całej aplikacji. Kontrakty określą współrzędne, klasy, pewność, ważność pomiaru i status.

### Zaktualizowany proces

1. Wybór ECU z katalogu.
2. Załadowanie profilu gabarytów, punktów odniesienia i planu inspekcji.
3. Potwierdzenie zgodności ECU i ustalenie położenia.
4. Przygotowanie i weryfikacja sceny 3D.
5. Planowanie ruchów NERO w MoveIt 2 przy zachowaniu ograniczeń.
6. Inspekcja aparatem Sony i pozostałymi czujnikami oraz kontrola jakości.
7. Analiza AI na Minisforum tam, gdzie potrzebna.
8. Archiwizacja i bezpieczne zakończenie.

### Zasady architektoniczne zaproponowane przez asystenta

1. Gotowe rozwiązania przed własnym kodem.
2. Niezależność urządzeń i modeli.
3. Konfiguracja zamiast programowania nowych ECU.
4. Oddzielenie AI od bezpośredniego sterowania napędami.
5. Testowalność bez sprzętu.

Modułowość **nie oznacza osobnego procesu Linux dla każdej funkcji**. Ważniejsze są kontrakty i odpowiedzialność.

Asystent zaproponował dalszą analizę w czterech obszarach: robotyka; akwizycja; dane i AI; organizacja procesu. Ostateczną architekturę wykonawczą odłożono do przeglądu tych obszarów.

---

## Wymiana 3 — polecenie przeglądu

### Użytkownik

> Wykonajmy zaproponowany następny etap

### Asystent — odpowiedź (rozszerzony zapis redakcyjny)

Asystent przedstawił **projekt koncepcyjny v0.2** i podzielił przegląd na cztery obszary. Przyjął deklarację ECU, wykorzystanie danych profilu, rozpoczęcie nowego systemu od zera i wymienność modułów jako wymagania ustalone.

### 3.1 Robotyka — fundament ROS 2

Propozycja: NERO jako precyzyjny pozycjoner Sony i sensorów; model kinematyczny oraz rzeczywista obwiednia narzędzia. Wykorzystać:
- ROS 2 Jazzy;
- `agx_arm_ros` i model NERO producenta;
- MoveIt 2;
- tf2 i URDF/Xacro;
- RViz 2 do wizualizacji;
- najpierw symulację planowania bez wykonywania poleceń na prawdziwym robocie.

Własny kod tylko do specyficznej logiki zadaniowej, bramki ruchu i adapterów stanowiska. Nie implementować ponownie solverów kinematyki ani ogólnego planera.

Przed pierwszym ruchem wymagana jest niezależna analiza i realizacja zabezpieczeń. ROS 2, MoveIt ani programowy STOP Stream Deck nie zastąpią toru bezpieczeństwa.

### 3.2 Akwizycja — oficjalne sterowniki zamiast własnego rdzenia kamery

**Luxonis OAK-D Pro AF:** oficjalny DepthAI ROS v3 ma dostarczać RGB, depth i point cloud. Własny kod Vision ma odpowiadać za zastosowanie obserwacji do weryfikacji ECU, przygotowania sceny oraz oceny jakości. Bez równoległych konkurujących właścicieli USB.

**Sony A6100:** rozważono Sony Camera Remote Command/PTP i adapter aparatu. Zwrócono uwagę, by nie mylić Camera Remote Command z odrębnym Camera Remote SDK i zweryfikować realną obsługę rozkazów przez nasz aparat, firmware oraz używany transport. Osobny adapter ma ukrywać sposób komunikacji Sony przed workflow.

**Termowizja:** moduł opcjonalny, dopiero po potwierdzeniu skali temperatur i kalibracji.

**Kalibracja:** DepthAI/ROS dostarcza dane kalibracyjne kamery, tf2 przechowuje ramy przestrzenne, OpenCV/ChArUco wspiera kalibrację; własna procedura ma połączyć przestrzeń kamery, stołu, podstawy robota i narzędzia.

**Ważna granica:** dokładność metrologiczna 3D i geometria wystarczająca do ostrożnego planowania kolizji to dwa różne wymagania. W testach Luxonis na trzech wysokościach 34 / 50,4 / 101 mm wynik ±1 mm nie został potwierdzony; nie zatrzymuje to wszystkich innych prac offline, ale zabrania traktowania niezwalidowanych pomiarów jako precyzyjnych.

### 3.3 Dane i AI — katalog profili zamiast stałej automatycznej identyfikacji

Zaproponowano **Vision ECU Catalog**. Rozdzielono:
- profil typu ECU — charakterystyka, wymiary, plan inspekcji, złącza, punkty referencyjne i preferowane modele AI;
- sesję konkretnego egzemplarza — wybór operatora, zdjęcia, pomiary, wynik, pozycję robota i wersję kalibracji;
- artefakt modelu AI — wersja, format wejścia/wyjścia, klasy obiektów, parametry i metryki.

Proponowane na start: SQLite na VENTUNO za API, oryginały i manifesty na NVMe, archiwizacja NAS; AI Platform na Minisforum z istniejącym Resource Managerem do kolejkowania RTX. Infrastruktura bazodanowa i MLOps ma być minimalna, a MLflow ewentualnie później.

Wymienność modeli wymaga kontraktu zawierającego m.in. model_id, wersję, task_type, input/output_contract, calibration_ref, confidence, quality, status i hash. Nie każdy profil ECU wymaga własnego modelu. W niektórych sesjach wystarczą deklarowane wymiary, plan i klasyczne algorytmy.

VENTUNO ma realizować robotykę i lokalne procesy, a Minisforum zadania analizy i treningu. AI nie publikuje bezpośrednio komend ruchu NERO.

### 3.4 Organizacja pracy — Vision Workflow

Proponowana kolejność:
1. Wybór i deklaracja ECU.
2. Weryfikacja stanu stanowiska.
3. Potwierdzenie zgodności profilu z obiektem oraz lokalizacja sceny.
4. Weryfikacja planu inspekcji i trajektorii.
5. Fotografia, kontrola jakości, ewentualne powtórki.
6. Analiza, zapis i bezpieczne zakończenie.

Na początek **jawna maszyna stanów** zamiast instalowania złożonego BehaviorTree.CPP. Operator ma korzystać z WebGUI; ROS 2 jest infrastrukturą, nie interfejsem użytkownika. Stream Deck jest dodatkowym panelem, lecz jego STOP nie jest niezależnym E-STOP.

### 3.5 Dziewięć modułów logicznych zaproponowanych w przeglądzie

| Moduł | Odpowiedzialność | Własne / gotowe |
| --- | --- | --- |
| Vision Workflow | cała sesja i recovery | własny |
| ECU Catalog | profile i plany | własny |
| Scene Verification | zgodność i geometria obiektu | OpenCV/PCL + własna logika |
| Motion Gateway | dopuszczenie żądań ruchu | własny + MoveIt 2 |
| Camera Adapters | Luxonis, Sony i Thermal | gotowe sterowniki + adaptery |
| Image Quality | jakość zdjęć i ponowienia | biblioteki + logika |
| AI Bridge | praca przez RM na Minisforum | własny adapter |
| Session Storage | oryginały, wyniki, metadane | SQLite, NVMe |
| Vision HMI | WebGUI operatora | własny |

To **moduły logiczne, a nie dziewięć obowiązkowych usług**.

Rozważono kontrakty: ECUProfile, SceneObservation, MotionRequest, CaptureRequest, CaptureResult, AIJob i InspectionResult (wersja v1). Tam, gdzie ROS 2 już posiada adekwatne typy, nie należy tworzyć ich odpowiedników. Pomiar przestrzenny musi mieć jednostki, ramę, czas, wersję kalibracji, jakość i status niepewności.

### 3.6 Systemy, których nie musimy wdrażać na starcie

- Nav2: przeznaczony do nawigacji mobilnej, obecnie niepotrzebny.
- RTAB-Map / pełny SLAM: w znanym nieruchomym stanowisku nie jest obowiązkowy.
- MoveIt Servo: dopiero dla sterowania ciągłego.
- Gazebo: potencjalnie do dokładniejszej symulacji później.
- BehaviorTree.CPP: po wzroście złożoności workflow.
- MLflow: przy większej skali modeli i eksperymentów.
- Wbudowane NN Luxonis: opcja, nie fundament.

Pierwsze korzyści mają wynikać z ROS 2, MoveIt 2, sterowników producentów, tf2, OpenCV i rosbag2. Nie instalować narzędzi tylko dlatego, że istnieją.

### 3.7 Cztery główne ryzyka

**A. Niezależne bezpieczeństwo NERO:** sprzętowy tor bezpieczeństwa i ochrona przed opadnięciem przy utracie zasilania. Motion Gateway ma być rzeczywistą bramką dostępu do sterowania, nie jedynie umową między modułami; sama bramka programowa nie wystarcza do bezpieczeństwa operatora.

**B. Jedna kamera Eye-in-Hand:** możliwość martwych pól podczas ruchu; weryfikacja położeń obserwacyjnych, skanu z kilku pozycji i obwiedni, bez obietnicy ciągłego bezpieczeństwa.

**C. Kalibracja i model tool:** transformacje stołu, robota, J7 i aparatów; obwiednia Sony, Luxonis, adapterów oraz przewodów.

**D. Zgodność ROS/USB:** rzeczywiste testy na ARM64 i naszym firmware, restart, utrata urządzenia i zasada jednego właściciela USB.

### 3.8 Pięć etapów budowy zaproponowanych w odpowiedzi

1. Specyfikacja i kontrakty — profil ECU oraz pełny opis pojedynczej sesji.
2. ROS 2 offline — model NERO, MoveIt i RViz, bez ruchu fizycznego.
3. Sesja offline — deklaracja, obserwacja z zapisanych danych, plan, analiza, archiwum.
4. Geometria i bezpieczeństwo — kalibracja, model kolizyjny, niezależne zabezpieczenia.
5. Pierwsza ograniczona inspekcja na sprzęcie — dopiero po spełnieniu bramek.

**W pierwotnej odpowiedzi asystent zaproponował DAF SAC jako pierwszy profil i scenariusz**. To nie była decyzja użytkownika i zostało następnie poprawione.

Ostateczna rekomendacja asystenta: przyjąć logiczny podział jako podstawę do specyfikacji Vision, ale nie zatwierdzać jeszcze szczegółów wykonawczych i niczego nie instalować. Pierwszy scenariusz miał sprawdzić, czy planowane moduły są potrzebne.

---

## Wymiana 4 — zapis fundamentu i zmiana pierwszego ECU

### Użytkownik

> Powinniśmy najpierw zamieścić założenia z tej rozmowy jako fundament systemu vision. Umieść raport nw repo na GH, najlepiej poprostu całą naszą rozmowę (kopiuj wklej), bo jest ona konkretna i rzeczowa. Po tym wrócimy do tworzenia pierwszego scenariusza, ale nie dla SAC tylko ETC3, bo jego dziś mierzyliśmy (pierwsze dzisiejsze ecu z dwoma czarnymi i jedna szara wtyczka).

### Skutki dla projektu

- Najpierw repozytoryjny fundament, dopiero potem projekt pierwszego scenariusza.
- Zachować rozumowanie i kontekst dyskusji jako materiał pomocniczy dla przyszłych ADR-ów.
- **Pierwszy scenariusz ma dotyczyć ETC3, nie SAC.**
- Oznaczenie robocze konkretnego egzemplarza: **pierwszy ECU mierzony 14.11.2026, trzy wtyczki — dwie czarne i jedna szara**.
- Nie przypisywać mu bez weryfikacji wymiarów lub parametrów innych ECU. Dalsze szczegóły dzisiejszych pomiarów muszą znaleźć się w osobnym profilu/rejestrze z datą, źródłem i rozróżnieniem wysokości korpusu, złączy i najwyższego punktu.

---

## Podsumowanie rozdzielenia statusów

**Zatwierdzone założenia właściciela:** deklaracja i weryfikacja ECU, katalog znanych danych, nowy system od podstaw, modularność i wymienność modeli, zachowanie wiedzy z prób, pierwsza sesja ETC3.

**Wstępnie przyjęty kierunek do sprawdzenia:** ROS 2, MoveIt 2, oficjalne sterowniki, osobne role VENTUNO i AI Platform, moduły opisane kontraktami, planowanie offline i kontrolowana archiwizacja.

**Otwarte decyzje:** techniczna realizacja bezpieczeństwa NERO; liczba procesów i format transportu; konfiguracja i widoczność Eye-in-Hand; dokładność 3D i transformacje; dokładna obsługa Sony A6100; sterowanie modelami AI na Luxonis; tryb pierwszej sesji ETC3.

**Brak działań na sprzęcie:** ta rozmowa i zapis dokumentacyjny nie uruchamiają ruchu NERO, nie migrują żadnego starego kodu i nie wdrażają nowego Vision.
