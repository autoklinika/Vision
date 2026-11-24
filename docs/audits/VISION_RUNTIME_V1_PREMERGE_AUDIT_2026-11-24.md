# Vision Runtime V1 — audyt S01–S04 i adaptera Luxonis ROS 2

**Data:** 2026-11-24
**Status:** kandydat do odbioru offline, osobny Draft PR; bez scalania i wdrażania na VENTUNO.
**Podstawa:** zaakceptowane ADR o niezależności sprzętowej, Vision Inspection Workflow V1 (S01–S11), ECU Reference Profile V1.

## Cel

Zintegrować przyjęty Vision Core i bibliotekę profili ECU z deklarowanym przez operatora wariantem oraz obserwacjami ROS 2 Luxonis. Runtime nie wprowadza nowego silnika scenariuszy, sterowników robota, Camera Service, Perception Engine, WebGUI ani C9.

## Elementy zaimplementowane

1. **Koordynator S01–S04** — używa istniejącego Core Workflow i SQLite Journal. Potwierdza gotowość urządzeń, kalibracje i zatwierdzone profile, wiąże deklarację operatora z konkretnym wariantem oraz wersją, przyjmuje lokalizację RGB-D i atomowo aktualizuje kontekst sceny S03, weryfikuje zadeklarowane ECU w S04. Błędy zamykają bramki zależnych etapów, bez automatycznego PARK.
2. **Reference Rules** — wymagane reguły selected-state Reference Profile są oceniane wobec zweryfikowanych cech, lokalnej geometrii i zatwierdzonych ECURecord. Brak obsługi wymaganego algorytmu lub sprzeczność danych blokuje obserwację, a nie ją zalicza. Aktualnie wspierany jest kontrolowany pomiar landmark RGB-D, nie autonomiczne wykrywanie dowolnych wizualnych znaków.
3. **Komunikaty ROS 2** — normalizacja sensor_msgs/Image, CameraInfo oraz geometry_msgs/TransformStamped z zachowaniem oryginalnych ramek optycznych RGB i Depth, jawnych jednostek głębi, czasu, intrinsics i metrycznego TF. Brak założenia, że stereo/depth jest zawsze metryczne.
4. **Odczyt ROS 2** — opt-in SnapshotCollector, jawne nazwy tematów i ROS domain, bez uruchamiania node'a, kamery, urządzeń i silników. Bufory przechowują własne niezmienne kopie, kontrolują rozmiar i wybierają zsynchronizowaną poprawną sekwencję, z ograniczoną liczbą prób.
5. **Dowód pochodzenia** — niezależny estimator geometrii, źródło danych i wspólny pakiet RGB-D muszą być połączone w potwierdzonym obiekcie MeasurementBinding. Sama nazwa hasha ani quality=True nie uwierzytelnia sensora; wdrożenie musi dostarczyć zaufany verifier i pomiary źródłowe.

## Zarejestrowane błędy i poprawki

| ID | Przed poprawką | Po poprawce |
| --- | --- | --- |
| R01 | Weryfikacja S04 mogła zignorować sprzeczność między Reference Profile i zaobserwowanym ECU | Wymagane reguły i cechy wzorcowe muszą być zgodne z ECURecord i danymi pomiarowymi |
| R02 | Zawyżona niepewność pomiaru mogła przykryć skrajną różnicę wymiarową | Pomiar i niepewność ograniczone zatwierdzonymi tolerancjami, brak automatycznej akceptacji |
| R03 | Niezależne potwierdzanie geometrii i klatek bez powiązania z konkretną obserwacją | Jedno powiązanie packet + geometry + session/request/scene/calibration/source |
| R04 | Klatka bez użytecznej głębi metrycznej była akceptowana w normalizacji | Co najmniej jeden ważny pomiar, poprawne jednostki, endian i row stride |
| R05 | Najnowszy zestaw niesynchronicznych wiadomości mógł ukryć wcześniejszy poprawny | Przegląd zsynchronizowanych kandydatów z ograniczonym budżetem, fail-closed |
| R06 | Bufor mógł przechowywać nieograniczone dane wejściowe oraz oryginalne zmienne obiekty ROS | Limity 64 MiB / klatkę, 128 MiB bufor oraz prywatne, niezmienne kopie |
| R07 | Zmiana nazwy ramki nowszego obrazu mogła przesłonić prawidłową starszą parę | Sprawdzanie alternatywnych zsynchronizowanych czwórek |
| R08 | Uszkodzona najnowsza klatka Depth blokowała wcześniejszą poprawną klatkę | Próbowane są inne poprawne kandydaty; nie ma omijania jakości |
| R09 | Zmiana przez nadawcę danych po inject mogła naruszyć integralność kolejki i limit pamięci | Bufor przejmuje własność danych i metadanych przy przyjęciu |

Wszystkie istotne scenariusze zostały odtworzone na danych syntetycznych przed poprawkami (RED), a następnie objęte testami regresyjnymi. Odrębny audyt przeprowadzono niezależnie od implementatora.

## Kontrole

- **616/616 testów offline PASS** (pełny zestaw, obejmuje Core, ECU Profiles, Reference, Thermal, bibliotekę i Runtime), Python 3.12.
- **compileall PASS**.
- Test w odizolowanym Docker bez sieci, bez urządzeń i z repozytorium wyłącznie do odczytu.
- Brak zmian pod src/vision_core i src/vision_modules oraz brak zmian bazowych VGP V1.
- Zgodność komunikatów Jazzy i dostępność oficjalnego DepthAI ROS v3 sprawdzone na hoście bez uruchamiania kamery.

## Ograniczenia i następny odbiór

**To nie jest odbiór fizycznego rozpoznawania ECU.** Na aktualnym stanowisku Runtime nie był uruchamiany z rzeczywistą kamerą. Adapter nie tworzy algorytmu lokalizacji bryły ani samodzielnie nie identyfikuje wariantu. Niezbędny jest niezależny estimator pozy/cech oraz zaufana weryfikacja źródła danych, aktualne CameraInfo/TF i zgodna kalibracja stanowiska. ROS static TF i poprawna synchronizacja czasu wymagają osobnego testu integracyjnego z rzeczywistymi topicami.

Rzeczywisty ETC3 ma obecnie tylko niezatwierdzony katalogowy profil DRAFT i nie może przejść pełnej weryfikacji S04. Brak automatycznego podstawiania nieznanych wymiarów i zdjęć. WebGUI, fotografia Sony, planowanie ruchu NERO i sterowanie urządzeniami pozostają osobnymi etapami.

**Wymagany dalszy krok:** osobny odbiór i zatwierdzenie PR Runtime oraz późniejszy test read-only Luxonis na rzeczywistym stanowisku, bez poleceń do robota. Zmiana kodu produkcyjnego wymaga osobnej autoryzacji.
