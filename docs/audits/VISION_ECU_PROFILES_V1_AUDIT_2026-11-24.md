# Vision ECU Profiles V1 — audyt modułu i ETC3 PoC

**Data:** 24.11.2026
**Punkt startowy:** Vision Core 0.1–0.4 + Thermal Inspection, GitHub main 5cb9e83b5b0fee5aecb2cf1def54cecb2e6f3813
**Status:** kandydat do odbioru architektury OFFLINE; brak merge, brak wdrożenia i brak zatwierdzonego profilu ETC3.

## 1. Cele i granice

Wprowadzenie osobnego katalogu profili ECU, który nie wymusza wypełniania braków geometrycznych fikcyjnymi zerami. Dopuszczalne są niepełne rekordy DRAFT; na potrzeby działania Core tworzony jest dopiero kompletne, zweryfikowane, ręcznie zatwierdzone ECUProfile, którego snapshot ma identyfikator i SHA-256.

Podstawowe moduły: models (immutability, strict JSON), catalog (jawne wersje/wybór), promotion (review gate), verification (deklaracja i obserwacja), releases (niezmienne wydania lokalne), activation (wiązanie zatwierdzenia i planu). Bez zmian w src/vision_core, bez dodatkowych serwisów i bez automatycznej identyfikacji ECU.

## 2. Karta ETC3

**Rekord:** config/ecu_profiles/etc3_poc_v1.json.
**Karta pomiarowa:** docs/profiles/ETC3_POC_V1_PL.md.

ETC3 to roboczo zadeklarowany egzemplarz z 14.11.2026 o trzech złączach (2 czarne, 1 szare). Zanotowane wcześniej wartości 69 mm dla szarego i 65 mm dla czarnego złącza są wyłącznie notatkami terenowymi, bez zatwierdzonego datumu, przyrządu i niepewności. Nie definiują bryły kolizyjnej, wysokości korpusu ani profilu widoku aparatu. Brakuje m.in. obwiedni, współrzędnych złączy, otwartego obszaru PCB, perspektyw fotograficznych, kwaternionów i kalibracji. Stan **DRAFT** bez możliwości promocji na profil wykonawczy.

## 3. Audyt i odtworzone problemy

| Priorytet | Wykryty problem | Poprawka |
| --- | --- | --- |
| P1 | Poprawna ścieżka TF z ukośnikiem była odrzucana, ponieważ nie była identyfikatorem katalogowym | Odrębny, walidowany identyfikator ramki ROS 2 ze ścieżką segmentową |
| P1 | Pozycja aparatu dla ujęcia skośnego musiała leżeć rzutem XY w PCB | Usunięto fałszywe założenie; wymagane pokrycie należy mierzyć w odrębnej bramce przestrzennej |
| P1 | Sprawdzano niezależność źródeł tylko pierwszego regionu PCB, widoku i landmarku | Kontrola wszystkich obszarów i ujęć, osobne źródło zweryfikowanej orientacji |
| P1 | Weryfikacja operatora mogła zaakceptować jeden wariant bez sprawdzania innych zatwierdzonych wariantów rodziny | Katalog jest wymagany dla statusu ACCEPTED, weryfikowane są wszystkie znane zatwierdzone alternatywy |
| P1 | Zmiana wewnętrznego connector_id alternatywnego wariantu ukrywała fizycznie nieodróżnialne złącza | Porównanie nieetykietowanych zbiorów kolorów i położeń metodą dopasowania jednoznacznego; wykrywanie AMBIGUOUS |
| P1 | Sama poprawność Core InspectionPlan nie wiązała się z wyborem ECU i dowodem obserwacji | Kontrolowany adapter select_and_plan_verified wymaga deklaracji, profilu w katalogu, wydania, obecnej obserwacji i spójności session/scene/frame/rev/time/ref |
| P1 | In-memory katalog nie zachowywał historii rewizji po restarcie | Lokalny ReleaseStore publikuje snapshot pod nazwą profile/revision bez nadpisywania, sprawdza kanoniczny JSON i SHA-256 |
| P2 | Zapis wydania korzystał z pierwotnej ścieżki, którą można było wymienić po otwarciu katalogu | Tworzenie, linkowanie i usuwanie pliku tymczasowego są wykonywane względem otwartego deskryptora katalogu z fsync |

Problemów nie uznajemy za „naprawione bezpieczeństwo robotyczne”: są to własności kodu, weryfikowane przez testy syntetyczne. Standardowy Core nadal samodzielnie nie uwierzytelnia danych sensora; adapter produkcyjny musi korzystać z zatwierdzonej ścieżki wejściowej.

## 4. Kontrakt danych i zatwierdzenia

- Deklaracja operatora wskazuje dokładne family/variant/revision. Nie ma fallbacku ani zgadywania.
- Próbka obserwacji musi mieć właściwą scenę, ramkę, sesję, rewizję, czas, wymagane kolory i geometryczne landmarki. Porównanie z alternatywnymi wariantami odbywa się na fizycznych cechach, nie nazwach wewnętrznych złączy.
- Status APPROVED i zgodny SHA-256 nie uwierzytelniają tożsamości recenzenta. To wymaga niezależnej polityki zatwierdzania, kontroli dostępu i zaufanego podpisu/źródła poza katalogiem.
- ReleaseStore zapewnia trwałość i wyłączność tworzenia rewizji w kontrolowanym katalogu, lecz nie jest WORM: podmiot z prawem do modyfikacji całego katalogu może manipulować plikami. Niezweryfikowane fotografie i pomiary nie są przechowywane w repozytorium.
- Utworzenie Core InspectionPlan nie jest zatwierdzeniem ruchu. Obowiązują nadal bramki S04→S05→S06, sprawdzenie realnego stanu sprzętu i MoveIt 2 oraz nadzór operatora.
- Niezależny adapter przyszłego wdrożenia musi uwierzytelniać źródła obserwacji i recenzentów i używać związanego z nimi kontraktu planowania; bez tego Core nie potwierdza rzeczywistej tożsamości ECU.

## 5. Testy i odbiór

Komendy weryfikacji: pełne unittest discover dla tests/core, compileall dla src/vision_core, src/vision_modules i tests/core, sprawdzanie diff --check, osobny kontener Docker --network none --read-only bez urządzeń. Stan początkowy: 156 regresji Vision Core/Thermal. Moduł ECU zawiera testy PoC, katalogu, zatwierdzania, rewizji, protokołu JSON, geometrii, obserwacji, scenariusza syntetycznego i błędów granicznych. Ostateczna liczba PASS jest raportowana z końcowego niezależnego przebiegu; CI GitHub dla nowego PR musi zostać przeprowadzone po publikacji.

**Wniosek do odbioru:** wystawić Draft PR modułu ECU profiles V1. Nie scalać bez jawnego przeglądu. Nie używać roboczego ETC3 do fizycznego sterowania ani do porównywania prawdziwych zdjęć PCB do czasu uzupełnienia i zatwierdzenia geometrii, złączy i ujęć.
