# ADR — ECU Reference Profile V1: biblioteka wiedzy i instrukcji Vision

**Data decyzji:** 2026-11-24
**Status:** ACCEPTED — właściciel zatwierdził architekturę i polecił najpierw opublikować dokumentację, a następnie implementować moduł.
**Zakres:** architektura danych profilu wzorcowego ECU, przygotowanie inspekcji i ścieżka wyboru ECU.
**Nie dotyczy:** zatwierdzenia rzeczywistych wymiarów ETC3, wdrożenia na VENTUNO, planowania ruchu w trybie LIVE ani automatycznej identyfikacji ECU.

## Przyjęta decyzja

**Profil wzorcowy nie jest jedynie bazą parametrów. Stanowi obszerną, wersjonowaną wiedzę o konkretnym wariancie ECU oraz deklaratywną instrukcję dla całego Vision:** co ma rozpoznać Luxonis, jak lokalizować ECU, co zaplanować i fotografować, jak oceniać wyniki, które moduły są potrzebne i jak dokumentować sesję.

Profil jest rozdzielony od konfiguracji wykonawczej i danych konkretnego egzemplarza:

- **ECU Reference Profile** — niezmienne wiedza, zdjęcia i modele referencyjne, geometria, reguły rozpoznawania, wymagane cechy, polityki, receptury; bez aktualnego położenia ECU na stole.
- **Execution Profile** — zatwierdzony wycinek wybranego profilu i receptury przekazany do istniejącego `ECUProfile`, zależności `ScenarioSpec`, wymagań capabilities i zaufanych adapterów.
- **Inspection Session / karta egzemplarza** — deklaracja operatora, aktualne obserwacje i TF, wyniki ujęć, QA i archiwum, z niezmiennym wskazaniem źródłowego profilu i jego rewizji.

**Wybór zawsze deklaruje operator**: rodzina → wariant → rewizja → stan fizyczny (np. zamknięty / odsłonięte PCB) → zatwierdzona receptura. System nie dobiera zastępczego wariantu bez jawnej decyzji. Luxonis potwierdza obserwowalne cechy i pozycję obiektu, nie zastępuje wiedzy nominalnej. Nierozróżnialne warianty prowadzą do `AMBIGUOUS` i decyzji operatora.

## Zatwierdzona struktura (15 sekcji)

`metadata`, `identity`, `physical_states`, `coordinate_systems`, `geometry`, `connectors_landmarks`, `reference_assets`, `recognition_rules`, `localization_rules`, `pcb_definition`, `photography_recipes`, `thermal_recipes`, `inspection_workflows`, `validation_policies`, `provenance_release`.

**Pełny zatwierdzony opis semantyki:** [ECU Reference Profile V1 — specyfikacja](../architecture/ECU_REFERENCE_PROFILE_V1_SPECIFICATION.md).
**Przykład kształtu danych (nie gotowy profil):** [szablon JSON](../templates/ECU_REFERENCE_PROFILE_V1_TEMPLATE.json).

Oryginalny dokument specyfikacji zachowuje historię statusu `DESIGN / PROPOSED` i wcześniejszy zakaz implementacji. **Ten ADR superseduje tamten status i zakaz:** użytkownik wyraźnie zatwierdził strukturę i polecił jej realizację. Pozostają w mocy niezmienność zamrożonego VGP V1, brak zgadywania geometrii ETC3 i wymaganie osobnego odbioru wdrożenia sprzętowego.

## Ustalona granica modułów

- Core odpowiada za sesję, zależności S01–S11, identyfikatory, stan i dowody końcowe; profil nie ma własnego silnika Workflow ani wykonywalnych skryptów.
- Luxonis/ROS 2/OpenCV: pomiar geometrii i cech, TF i aktualna lokalizacja; reguły profilu są deklaratywnymi danymi i wymagają zaufanej realizacji przez adapter.
- MoveIt 2: IK, kontrola kolizji, planowanie; profil zapisuje lokalne cele i zatwierdzone geometrie, **nie** wartości J1–J7 i nie gotowe trajektorie.
- CaptureDevice (Sony): zlecenia perspektyw, RAW/JPEG, ostrość i potwierdzenia; cele aparatu różnią się od regionów PCB.
- Thermal: opcjonalny moduł, wymaga osobnych kalibracji i nie uznaje wartości względnych za temperaturę absolutną.
- Asset Store: pliki zdjęć, CAD i modeli mogą być prywatne, ale są weryfikowane przez referencje i SHA-256. SHA to integralność, nie autentyczność sensora/recenzenta.

## Weryfikacja i wersjonowanie

Brak wymaganej wartości lub źródła oznacza `NOT_READY`, nie arbitralne zero. Profil ma status dokumentacji oraz **oddzielną gotowość dla fizycznego stanu i receptury**. Profil `APPROVED` nie dopuszcza automatycznie każdego rodzaju inspekcji. Zmiana zatwierdzonych danych wymaga nowej rewizji, a wynik sesji nie modyfikuje profilu wzorcowego. Profil i wszystkie użyte assety muszą być związane z rewizją oraz pełnymi hashami w archiwum.

**ETC3** pozostaje pierwszym PoC: 2 czarne i 1 szara wtyczka, raporty wysokości 65/69 mm jedynie jako niezweryfikowane notatki bez wspólnego datumu. Nie wolno wytwarzać pozornej geometrii, modeli CAD ani przepisów na ujęcia Sony.

## Sekwencja prac i kryteria odbioru

1. **Dokumentacja (pierwszy pakiet):** specyfikacja, szablon, ten ADR i zasady UX trafiają do repozytorium jako osobna zmiana.
2. **Implementacja (drugi pakiet):** typowany, testowany, niezależny od sprzętu moduł Reference Profile; integracja przez adapter do Core i ECU Profiles V1 z PR #46. Brak zmian w zaakceptowanych kontraktach Core bez osobnego uzasadnienia.
3. **Następny, osobno odbierany etap:** GUI biblioteki, ekranu wyboru ECU i edytora wzorca, a później przygotowanie kompletnego ETC3 z rzeczywistymi zdjęciami i pomiarami.

Obowiązkowe kontrole: walidacja struktury i semantyki, brak nieznanych executable fields, fail-closed dla DRAFT, niejednoznaczności, błędnej kalibracji i plików, wersjonowanie, zgodność z Core 0.1–0.4 oraz niezmienność stanowiska. Implementacji offline **nie należy utożsamiać z fizycznym odbiorem pracy urządzeń**.
