# ADR-VISION-WEBGUI-001 — WebGUI wyłącznie klientem systemu Vision

- **Data decyzji:** 2026-11-24.
- **Status:** **ACCEPTED** — granica odpowiedzialności, kierunek wizualny i tryby dostępu zatwierdzone przez właściciela Vision w rozmowie projektowej 24.11.2026.
- **Zakres:** WebGUI / Vision Desktop Shell, komunikacja klient–system, lokalny Kiosk i zdalna przeglądarka.
- **Rodzaj zmiany:** dokumentacja decyzji; bez implementacji, wdrożenia i zmian konfiguracji sprzętu.
- **Specyfikacja rozwinięcia:** [VISION WebGUI V1](../ux/VISION_WEBGUI_V1_SPECIFICATION.md).
- **Powiązania:** [ADR-VISION-CORE-001](../architecture/ADR_VISION_CORE_HARDWARE_INDEPENDENCE_2026-11-23.md), [ADR ECU Reference Profile V1](ADR_VISION_ECU_REFERENCE_PROFILE_V1_2026-11-24.md), [UX biblioteki ECU](../ux/ECU_LIBRARY_SELECTION_EDITOR_V1.md).

## 1. Kontekst

Vision jest niezależnym sprzętowo systemem inspekcji PCB/ECU. Core koordynuje sesje i bramki scenariusza; Runtime, Planner oraz właściwe moduły i adaptery dostarczają wyniki i realizują zadania. ROS 2 i MoveIt 2 pozostają warstwą integracji i planowania ruchu zgodnie z ADR-VISION-CORE-001. Projekt potrzebuje ergonomicznego klienta lokalnego i zdalnego, rozwijanego równolegle z backendem.

Rozważono klasyczny wielookienkowy pulpit Windows 98, alternatywne historyczne i przemysłowe style oraz autorską koncepcję ATLAS. Właściciel wybrał Windows 98. ATLAS nie jest alternatywnym kierunkiem wizualnym; pojedyncze funkcje pracy na obrazie mogą zostać zaproponowane jako narzędzia w oknach klasycznego pulpitu.

## 2. Decyzja nadrzędna (normatywna)

> **WEBGUI JEST WYŁĄCZNIE KLIENTEM CAŁEGO SYSTEMU VISION.**

Systemem jest Vision, nie WebGUI. Klient nie jest koordynatorem, warunkiem pracy usług, źródłem autorytatywnego stanu ani alternatywną ścieżką sterowania. Vision musi umożliwiać testowanie i obsługę swoich funkcji przez niezależne, uprawnione interfejsy także przy nieuruchomionym WebGUI. Lokalny Kiosk i zdalna przeglądarka są klientami tego samego systemu, podlegającymi tym samym serwerowym regułom dostępu i operacji. Zamknięcie klienta nie oznacza samoczynnie zakończenia ani kontynuacji operacji: zachowanie przy utracie klienta należy wyłącznie do polityki backendu.

```text
 WebGUI w Kiosk     WebGUI w przeglądarce     inne uprawnione klienty
        |                     |                       |
        +---------------------+-----------------------+
                       kontrakty API Vision
                               |
                Vision Core / Runtime / moduły
                Planner / profile / dane / zdarzenia
                               |
             ROS 2 / MoveIt 2 / właściwe adaptery
                               |
                urządzenia i środowisko stanowiska
```

API jest granicą systemu, nie nowym Core. Schemat jest logiczny: nie narzuca oddzielnego mikroserwisu ani konkretnego sposobu wdrożenia.

## 3. Podział odpowiedzialności

| Obszar | WebGUI — klient | System Vision — właściciel |
| --- | --- | --- |
| Pulpit i okna | Układ, fokus, menu, zakładki, preferencje | Nie zależy od układu GUI |
| Sesja i Workflow | Prezentuje stan i powody blokad, wysyła intencje | Stan sesji, kolejność, bramki, dowody, anulowanie, wznowienie |
| Gotowość | Prezentuje raport systemu i świeżość połączenia | Capabilities, kalibracje, aktualność danych, decyzja READY/NOT_READY |
| Profile ECU | Wybór i formularze, lokalny bufor edycji | Walidacja, rewizje, zatwierdzenia, manifesty, zapis |
| Robot i urządzenia | Prezentuje stan i dostępne operacje | Planowanie, kontrola, wykonanie, HOLD, status wykonania |
| Obrazy i analiza | Wyświetlanie, zoom, nawigacja, nakładki i porównanie do oglądania | Akwizycja, integralność, archiwizacja, obliczenia i wiążące wyniki |
| Uprawnienia i sesja dostępu | Formularze logowania, prezentacja dostępnych funkcji | Uwierzytelnienie, autoryzacja każdego żądania, audyt |
| Zamknięcie/restart VENTUNO | Wyświetla dialog i składa żądanie | Sprawdza uprawnienia i stan, koordynuje procedurę zasilania |

Walidacja formularza w przeglądarce może pomagać operatorowi, ale nie zastępuje walidacji po stronie systemu. Cache klienta nie jest rejestrem zdarzeń ani źródłem danych technicznych. Przyjęcie żądania nie jest równoznaczne z wykonaniem operacji; GUI pokazuje stan zwrócony przez system.

## 4. Zakazy architektoniczne

- Brak bezpośredniego dostępu klienta do ROS 2, MoveIt 2, CAN, PTP, DepthAI, lokalnego systemu plików stanowiska, systemd, shella lub sterowników. Przeglądarka nie uzyskuje uprzywilejowanego mostka do tych warstw.
- Brak implementacji maszyny stanów Workflow, bramek, IK, kontroli kolizji, generatora trajektorii, algorytmu identyfikacji, niezależnej oceny dopuszczenia ruchu lub modyfikacji pomiarów i wyników w GUI.
- Brak uruchamiania inspekcji, inicjalizacji sprzętu, uzbrajania robota, automatycznego PARK czy ponawiania operacji fizycznych w wyniku startu, przeładowania, reconnect lub zamknięcia GUI.
- Brak udawanej gotowości: animacja, timer, lokalny licznik i odebranie ACK nie mogą wytworzyć statusu READY. Stan demonstracyjny nie może być mylony ze stanem stanowiska.
- Brak obejścia serwerowych uprawnień przez tryb Kiosk, ukryty przycisk, zmianę lokalnych ustawień czy ręczne wywołanie API.
- Brak zależności backendu od cyklu życia przeglądarki, jej pamięci lokalnej, otwartego okna czy konkretnej implementacji frontendu.

## 5. Zatwierdzony kierunek UX i wdrożenia

- Klasyczny pulpit Windows 98: niezależne okna, menu Start, pasek zadań, szare kontrolki 3D, granatowe paski tytułowe, własne ikony retro, klasyczne dialogi.
- Intro: ta sama odręczna animacja napisu VISION co na Stream Deck Plus, czarny napis na białym tle, około 3 s; następnie okno inicjalizacji w stylu Windows 98 z logo, paskiem postępu i raportowanymi przez system stanami.
- Ekran logowania w tym samym stylu; wygląd nie zastępuje uwierzytelnienia.
- Lokalnie na VENTUNO Q: pełnoekranowy Kiosk; zdalnie: ten sam klient webowy w przeglądarce. Ubuntu i działający stos ROS 2 nie są przebudowywane dla osiągnięcia wyglądu retro.
- Menu Start udostępni autoryzowane żądania zamknięcia/restartu VENTUNO. Tryb administratora umożliwi kontrolowany powrót do zwykłego środowiska Ubuntu; techniczny mechanizm dostępu pozostaje do zaprojektowania.

Nie jest to nowy system operacyjny ani emulator Windows. Sformułowanie „VISION Workstation” oznacza środowisko operatorskie, nie zmianę granic architektury.

## 6. Konsekwencje i kryteria odbioru architektury

1. Frontend może powstawać niezależnie na gałęzi od main, z izolowanym źródłem syntetycznych danych, bez uruchamiania sprzętu.
2. Kontrakt API musi być jawny, wersjonowany, testowalny i wspólny dla klientów. Transport, adresy i schematy wiadomości wymagają osobnego uzgodnienia z kodem backendu.
3. Testy bez GUI wykazują, że stan i cykl życia sesji należą do Vision. Testy klienta wykazują, że restart, reconnect i wiele przeglądarek nie powodują niejawnej dyspozycji operacji.
4. Przy braku, niespójności albo utracie aktualności danych klient pokazuje nieznany/nieaktualny stan, nie przedstawia starego READY jako bieżącego i nie udaje wykonania. Backend pozostaje autorytatywny.
5. Próby operacji z pominięciem GUI są odrzucane przez backend zgodnie z jego uprawnieniami i bramkami. Test izolacji sprawdza brak zależności frontendu od sterowników/ROS 2 i brak dostępu do aktorów w trybie demo.
6. Zatwierdzenie niniejszego ADR nie stanowi zatwierdzenia konkretnego API, gotowości stanowiska, mechanizmu logowania, implementacji Kiosk, kodu ruchu ani wydania produkcyjnego.

## 7. Odrzucone alternatywy

- GUI jako monolityczny kontroler całego stanowiska — łamie niezależność systemu i możliwość wymiany klienta.
- Dwie różne logiki dla Kiosk i przeglądarki — wprowadza rozbieżność stanów i zasad.
- Modyfikacja Ubuntu w celu odtworzenia Windows 98 — zbędna; styl należy do aplikacji.
- Własne równoległe połączenia GUI ze sprzętem — duplikują odpowiedzialność ROS 2/MoveIt 2 i modułów Vision.

## 8. Otwarte decyzje wykonawcze (nie są zatwierdzone tym ADR)

Proponowany React/TypeScript/Vite/98.css, szczegółowy transport REST/zdarzenia, sposób sesji dostępu, role, rozdzielczości docelowe, zasady wieloklientowe, mechanizm administracyjny Kiosk, szczegóły procedur restartu oraz integracja źródłowego assetu intro zostaną ustalone w kolejnych pakietach. Żadna z tych decyzji nie może naruszyć sekcji 2–4.
