# Vision Core 0.4 / Thermal Inspection V1 — audyt przed scaleniem

**Data: 24.11.2026.**
**Status: poprawki przygotowane do oddzielnego PR; bez wdrożenia sprzętowego.**
**Zakres:** cały łańcuch PR #43 (mechanizm rozszerzeń) i PR #44 (moduł termowizyjny), odtworzenie błędów, poprawki kompatybilne wstecznie i testy niezmienionych funkcji 0.1–0.3.

## 1. Punkt odniesienia

| Element | Commit bazowy | Cel |
| --- | --- | --- |
| Main, Core 0.1–0.3 | 7026da76e503c8bb72e2e70f7c5845fd15fa0b95 | Zatwierdzony fundament offline |
| PR #43, Core 0.4 | 05073a3aa8b50b2edb88eccfd65a5a6148d76848 | Deklaratywne moduły i graf zależności |
| PR #44, Thermal V1 | 22bb917f9e09ee07333f33195cd5d3823097a322 | Tryb względny, radiometryczny, źródła, QA |
| Pakiet audytowy | Gałąź feat/vision-core-004-thermal-premerge-hardening | Rozszerzone bramki archiwizacji i obsługi awarii |

Zachowujemy jeden silnik Workflow, standardowe etapy S01–S11, sterowniki i planowanie ruchu w ROS 2/MoveIt 2 oraz w pełni izolowaną instalację stanowiska. Nie było ruchu robota, fotografowania Sony, podłączenia kamery termowizyjnej ani modyfikacji zamrożonej bazy VGP V1.

## 2. Metoda

- Dwa niezależne przeglądy kodu 0.4 i Thermal V1 przeanalizowały warunki zaliczania etapów, dziennik SQLite, restarty, grafy i archiwum.
- Własne testy audytowe zapisano PRZED naprawami. Cztery testy Core i cztery testy termowizji rzeczywiście zgłaszały błędy, nie były tylko potencjalnymi scenariuszami.
- Dodano kontrolę pochodzenia plików termicznych w S10 oraz testy błędnych/missing referencji, pomijania obowiązkowego potwierdzenia i odrzucania niepełnych list archiwalnych.
- Po pierwszych poprawkach osobny przegląd wykrył dodatkowy problem publikacji manifestu, który również odtworzono testami przed naprawą.
- Ostateczna weryfikacja obejmuje pełne testy istniejących Core 0.1–0.4 i Thermal, kompilację oraz osobny kontener tylko do odczytu bez sieci, z wyłączonymi możliwościami systemowymi i bez urządzeń.

## 3. Rejestr istotnych błędów

| ID | Waga | Błąd przed naprawą | Naprawa i test |
| --- | --- | --- | --- |
| V4-A01 | P1 | Odrzucony przez SQLite commit kończący etap mógł pozostawić nieutrwalony SUCCEEDED w pamięci | Niepewny zapis trwale blokuje efektywne stany danej instancji; test failed_result_commit |
| V4-A02 | P1 | Wyjątek podczas utrwalania unieważnienia umożliwiał późniejszy dispatch | Invalidate po błędzie przechodzi w fail-closed, wymaga nowego uzgodnienia sesji; test failed_invalidation |
| V4-A03 | P1 | Jednoczesna zmiana polityki i kontekstu podczas restartu powodowała podwójne unieważnienie i wyjątek zamiast kontrolowanego BLOCKED | Zebrane powody w jednym zdarzeniu SQLite; test simultaneous_config_and_context_change |
| V4-A04 | P2 | Nieograniczony rozmiar deklaratywnego grafu scenariusza | Limit 256 etapów przed tworzeniem grafu; test large_scenario |
| V4-A05 | P1 | S10 mógł osiągnąć SUCCEEDED po usunięciu lub zmianie oryginału, mapy lub JSON modułu termicznego, choć występowały wcześniejsze potwierdzenia modułu | Ogólny kontrakt archive_required i archiwalne dowody powiązane z modułem; test missing_thermal_map, corrupt_native, missing_qa_json |
| V4-A06 | P1 | Sam zestaw deklaracji module_archive_verified pozwalał zaliczyć S10 bez opublikowania manifestu | S10 wymaga osobnego, związanego z wynikiem zdarzenia archive_verified potwierdzającego właściwą nazwę i SHA-256 manifestu; test module_proofs_without_manifest_publication |
| V4-A07 | P1 | Nieoczekiwany wyjątek z publikacji manifestu mógł pozostawić S10 w RUNNING i umożliwić późniejszą ręczną akceptację | Szeroka obsługa normalnych wyjątków, zapis FAILED i zablokowanie kolejnego wyniku; test unexpected_manifest_exception |
| V4-A08 | P2 | Skrajny nasycony piksel mógł sam wytworzyć pozorną rozpiętość mapy względnej | Dynamic range wyliczane z co najmniej dwóch nienasyconych próbek, niezależnie od limitu nasycenia; test saturated_outlier |
| V4-A09 | P2 | Numeryczny frame_id mógł przejść walidację i być archiwizowany zamiast tekstowej ramki TF | Typowane, drukowalne i ograniczone identyfikatory kalibracji oraz ramek; test numeric_frame_id |

Wszystkie powyższe scenariusze były testowane syntetycznie. Prawidłowość ich napraw nie jest dowodem bezpieczeństwa funkcjonalnego robota ani metrologicznej dokładności termowizji.

## 4. Uogólniony kontrakt archiwalny

ModuleSpec otrzymał jawne pole archive_required (domyślnie false dla zgodności wstecznej). Moduł deklarujący obowiązkową archiwizację:

1. Przedstawia odrębne podpisane identyfikatorami SHA-256 JSON dowodowe na każdym wymaganym etapie oraz jawne archive_entries opisujące wszystkie powiązane pliki.
2. Core sprawdza zgodność session, stage, request, module/version, profile, scene i zakończenia, a następnie weryfikuje w Archive każdy wymieniony oryginał, mapę i dokument, nie tylko samo potwierdzenie wykonania modułu.
3. Dla każdego etapu zapisuje modułową kontrolę archiwalną w dzienniku S10, dopiero potem publikuje manifest-v1.json.
4. Przed S10 SUCCEEDED wymaga trwałego potwierdzenia publikacji manifestu archive_verified o zgodnej nazwie i SHA-256.
5. Przy braku, podmianie, duplikacie lub uszkodzeniu danych blokuje S10 i etapy zależne; nie ponawia automatycznie zleceń ruchu ani migawki.

To jest kontrakt uniwersalny: Core nie importuje modułu Thermal ani nie ma ścieżki warunkowej dla nazwy producenta. Przyszłe moduły z obowiązkowym archiwum stosują ten sam schemat metadanych.

## 5. Granice i znane ograniczenia

- Mechanizm nie nadaje potwierdzeniom sensora autentyczności kryptograficznej. Moduł i dostarczający mu dane adapter pozostają zaufanym źródłem deklaracji o pochodzeniu próbek, kalibracji i czasie.
- Dane radiometryczne w Kelvinach nie są jeszcze potwierdzone na żadnej fizycznej kamerze; emisyjność, temperatura odbita, czułość i współrejestracja ze zdjęciami Sony wymagają odrębnych testów po wyborze modelu.
- Archiwum zapewnia ochronę przed nadpisaniem w przyjętym procesie i integralność SHA-256, ale nie jest certyfikowanym WORM. Weryfikacja jest punktowa; administrator z uprawnieniami systemowymi może później zmienić lub usunąć plik.
- Nie implementowano transferu z konkretnej kamery IR, synchronizacji z ROS 2, ruchu NERO ani automatycznego PARK/ponowienia po awarii.
- Po przerwanym zapisie SQLite i niejednoznacznym wyniku stan instancji zostaje zablokowany; dalsza sesja wymaga kontrolowanego uzgodnienia stanu.
- Odpowiednie kalibracje i limity jakości będą wymagały wymiany zatwierdzonych profili na dane pomierzone fizycznie.

## 6. Warunki odbioru i scalania

- Nowy pakiet poprawek powinien pozostać oddzielnym PR względem #44, aby historyczne zatwierdzone gałęzie były możliwe do odtworzenia.
- Wymagane są PASS wszystkich testów offline, compileall oraz zielone GitHub Actions wszystkich workflow na końcowym drzewie kodu.
- Należy sprawdzić poprawność kolejności gałęzi i symulowanego scalania: main → #43 → #44 → PR naprawczy; finalne drzewo Git musi być identyczne z audytowanym.
- Main produkcyjny na GitHub można scalić za zgodą właściciela; lokalne repozytorium uruchomieniowe VENTUNO oraz baseline VGP V1 pozostają nienaruszone.
- Odbiór stanowi akceptację logiki OFFLINE, a nie faktyczne uruchomienie termowizji.

**Raport powstał dla audytu pre-merge. Link i końcowe SHA po scaleniu należy zapisać osobno w komentarzu PR.**
