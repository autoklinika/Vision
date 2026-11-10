# Vision — polityka `main` i kryteria integracji Vision Core

**Uzgodniono:** 2026-11-10. **Status:** ACCEPTED jako sposób prowadzenia projektu.  
**Zasada:** `main` nie jest magazynem wszystkich eksperymentów ani odzwierciedleniem działającego runtime. Jest sprawdzoną bazą decyzji i komponentów, które uzyskały zgodę na integrację.

## 1. Co utrzymujemy teraz w `main`

- Architektura i granice modułów Vision.
- Zatwierdzone ADR i jawnie oznaczone jako `PROPOSED` warianty projektowe, które wymagają dalszej walidacji.
- Datowany raport AS-BUILT, w którym `PASS` dotyczy jedynie konkretnego testu, a nie gotowości całego urządzenia.
- Ograniczenia bezpieczeństwa, zależności sprzętowe, lista otwartych ryzyk i zasady publikowania.
- Wcześniejsze przyjęte raporty VENTUNO/Sony, z zachowaniem oryginalnej daty.

**Nie włączamy teraz:** testowych sterowników Sony, niezweryfikowanego kodu ruchu NERO, konfiguracji uruchomieniowej OpenDeck, kopii SDK, migawkowych logów CAN, prywatnego kodu Thermal, danych RAW i modeli AI.

## 2. Gdzie trzymamy prace niezakończone

- **PR #15** (`sync/vision-factual-baseline-20261110`) pozostaje repozytoryjnym punktem odniesienia dla skonsolidowanych testów, skryptów i historii rozwoju.
- Dotychczasowe gałęzie tematyczne (Sony, NVMe, VENTUNO, Thermal, OpenDeck) pozostają dostępne. Nie scalamy ani nie zamykamy ich automatycznie.
- Eksperymenty bez wersji produkcyjnej mogą być rozwijane w osobnych gałęziach; dokumentacja danej próby musi określać jej faktyczny zakres i status.
- Duże zbiory dowodów, zamrożone archiwa i dane wrażliwe pozostają poza publicznym GitHubem, na dedykowanym NVMe lub w zatwierdzonym prywatnym repozytorium.

Pełny snapshot: [PR #15](https://github.com/autoklinika/Vision/pull/15), [niezmienny commit snapshotu](https://github.com/autoklinika/Vision/tree/34181a6206918dce91021dce3286a221f6e32058).

## 3. Warunki przenoszenia modułu do `main`

Kod danego modułu należy zaproponować w oddzielnym, niewielkim PR dopiero gdy:

1. **Kontrakt modułu** jest opisany: wersje API, dane wejściowe/wyjściowe, jednostki, stan błędu i właściciel procesu.
2. **Testy offline** (w tym błędy i brak urządzeń) przechodzą bez przypadkowego sterowania napędami, kamerą, przekaźnikami i zasilaniem.
3. **Testy na rzeczywistym sprzęcie** mają jawny zakres, kryterium sukcesu, protokół, dane dowodowe i wcześniejszą zgodę operatora.
4. **Awaria komponentu** kończy się przewidywalnym stanem i nie umożliwia przypadkowego wznowienia zadań.
5. **Odtwarzalność i rollback** zostały przetestowane; konfiguracja i sekrety pozostają poza repo.
6. **Zależności i licencje** (w tym SDK producentów, kontenery oraz kod GPL) zostały zidentyfikowane, a publikacja źródeł jest dozwolona.
7. **Stan prod/dev** jest jawnie opisany: spełnienie jednej próby laboratoryjnej nie podnosi całego modułu do `PROD`.
8. **Właściciel projektu** zaakceptował PR i wyraźnie zgodził się na merge.

## 4. Bramka szczególna — NERO i bezpieczeństwo

- ADR-VISION-ROBOT-001 zatwierdza **dwa etapy STOP**, nie dopuszcza jeszcze sterowania autonomicznego i nie potwierdza niezależnego E-STOP.
- Przed włączeniem kodu ruchu do produkcyjnego Vision Core wymagamy centralnej bramki poleceń ruchu, zatrzaskiwania STOP i kontrolowanego recovery.
- Przed testem rzeczywistego ruchu: odpowiednio zabezpieczone i sztywno zamocowane ramię, wolny obszar roboczy, niezależne zabezpieczenia wynikające z oceny ryzyka oraz procedura dla ryzyka opadnięcia po utracie zasilania.
- Naciśnięcie przycisku GPIO przez VENTUNO/Linux/CAN pozostaje STOP-em programowym, nie jest samo w sobie certyfikowaną funkcją bezpieczeństwa.
- STOP ma wyższy priorytet niż automatyczne parkowanie po zaniku zasilania. Przywrócenie zasilania lub restart systemu nie wznawia ruchu.
- Brak potwierdzenia bezruchu i podtrzymania napędów = **brak podstaw do dopuszczenia ruchu autonomicznego**.

Powiązanie: [ADR NERO](../architecture/ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md).

## 5. Bramka szczególna — aparaty i obraz

- Sony: automatyczne przełączanie HDMI/Wi-Fi/SD/USB i odzyskiwanie po utracie łączności muszą mieć testy całych serii, weryfikację oryginałów i hashy oraz niezawodne logowanie błędów. ADR Sony nadal jest `PROPOSED`.
- Thermal: aktualna v0.6 pozostaje zamrożonym prototypem, bez metrologicznie potwierdzonych °C i bez produkcyjnej integracji.
- Kamera głębi i AI mogą wspierać planowanie położenia, ale nie przejmują roli niezależnych elementów ochronnych.
- Oświetlenie i sterowanie ECU/DUT wymagają osobnych prób i ograniczeń elektrycznych.

## 6. Kolejność dalszych prac

1. Uporządkować i wdrożyć stabilną bazę dokumentacyjną `main`.
2. Kontynuować moduły na osobnych gałęziach, bez zbiorczego merge eksperymentów.
3. Zbudować pierwszy integracyjny szkielet Vision Core z bezpiecznymi atrapami sprzętu.
4. Dodawać stabilne moduły stopniowo, z audytem API i kontrolą regresji, zawsze przez PR.
5. Dopiero po przejściu bramek sprzętowych i bezpieczeństwa zatwierdzić docelowe wydanie produkcyjne Vision Core.

Dokument dotyczy **zarządzania repozytorium**, nie wydaje polecenia zmiany firmware, startu usług ani fizycznego poruszania NERO.
