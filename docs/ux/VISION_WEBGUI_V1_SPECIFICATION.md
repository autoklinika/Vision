# VISION WebGUI V1 — specyfikacja klienta operatorskiego

> **Aktualizacja UI, 25.11.2026:** [Workspace V2](VISION_WORKSPACE_V2.md) zastępuje styl Windows 98, menu Start, zarządzanie oknami i zapis ich geometrii. Poniższe opisy tego wyglądu są historyczne. Zasady odpowiedzialności Core, uwierzytelniania, raportów i prywatności pozostają obowiązujące. Status wdrożenia jest odrębny od implementacji.

- **Data:** 2026-11-24.
- **Status:** DESIGN BASELINE — zasady i kierunek UX zaakceptowane; szczegóły oznaczone PROPOSED są wymaganiami do przeglądu, nie dowodem wdrożenia.
- **Nadrzędny ADR:** [ADR-VISION-WEBGUI-001](../decisions/ADR_VISION_WEBGUI_CLIENT_ONLY_2026-11-24.md).
- **Powiązania:** [UX biblioteki ECU](ECU_LIBRARY_SELECTION_EDITOR_V1.md), [specyfikacja ECU Reference Profile](../architecture/ECU_REFERENCE_PROFILE_V1_SPECIFICATION.md), [szablon profilu](../templates/ECU_REFERENCE_PROFILE_V1_TEMPLATE.json), [ADR Core](../architecture/ADR_VISION_CORE_HARDWARE_INDEPENDENCE_2026-11-23.md).
- **Zakres zmiany:** projekt dokumentacyjny; bez modyfikacji kodu, sprzętu i usług VENTUNO.

## 1. Cel i granice

WebGUI jest wymiennym klientem całego Vision, a nie systemem samym w sobie. Jego rolą jest przedstawienie danych systemu, ergonomiczne zebranie intencji operatora i prezentacja odpowiedzi. Obsługuje zarówno stanowisko lokalne, jak i dostęp zdalny. Backend musi być niezależny od klienta, a frontend nie może zastępować Core, Runtime, Planner, ROS 2, MoveIt 2, modułów akwizycji ani przetwarzania obrazu.

V1 obejmuje środowisko operatorskie oraz sukcesywną integrację funkcji udostępnionych przez system. Analiza przez lokalne AI pozostaje poza zakresem V1. Funkcja widoczna w makiecie, ale jeszcze niedostępna w backendzie, jest jednoznacznie oznaczona jako niedostępna lub demonstracyjna.

## 2. System wizualny (ACCEPTED)

| Element | Kierunek |
| --- | --- |
| Pulpit | Klasyczny Windows 98, wiele niezależnych okien |
| Okna | Kanciaste, szare, wypukłe ramki, granatowe paski tytułowe |
| Nawigacja | Menu Start, pasek zadań, zasobnik systemowy, własne ikony |
| Dialogi i formularze | Klasyczne komunikaty, pola, zakładki, drzewa, listy i paski stanu |
| Marka | Oryginalny odręczny znak VISION z animacji Stream Deck |
| Środowisko lokalne | Pełnoekranowy Kiosk bez widocznego pulpitu Ubuntu |
| Dostęp zdalny | Ten sam klient przez przeglądarkę |

**PROPOSED:** podstawowa paleta #008080 (pulpit), #C0C0C0 (okna), #000080 (aktywny pasek tytułowy), białe i ciemnoszare krawędzie 3D, bitmapowy charakter ikon, czytelny krój z legalną licencją. Kolory statusów: tekst i symbol oprócz koloru. Brak nowoczesnych kafelków i zaokrąglonych obramowań. Używamy własnych assetów i zgodnych licencyjnie bibliotek, nie kopiujemy zastrzeżonych ikon, fontów czy brandingów Windows.

Rozdzielczość i skala są do weryfikacji na faktycznym monitorze stanowiska. GUI powinno uwzględniać również mysz, klawiaturę i czytelność w mniejszym oknie przeglądarki. Opcjonalne motywy nie są warunkiem V1.

## 3. Sekwencja startowa klienta (ACCEPTED kierunek)

### A. Intro VISION

Białe tło, czarny odręczny napis VISION powstający od lewej do prawej, około 3 sekund, zgodny z oryginałem Stream Deck Plus. Bez dodatkowych ozdobników. Docelowo wykorzystać faktyczny zatwierdzony asset, nie imitację wygenerowaną na potrzeby makiety. Źródło, licencję i format trzeba zweryfikować przed importem; sam plik nie był sprawdzany ani publikowany w tym PR. Nie przesyłać prywatnych plików stanowiska do publicznego repozytorium.

Intro jest animacją klienta, a nie poleceniem uruchomienia systemu. Jego zakończenie nie zmienia stanu Core. Dopuszczalne skrócenie lub pominięcie animacji (PROPOSED: preferencja reduced motion, reconnect) nie wpływa na backend.

### B. Okno inicjalizacji Windows 98

Klasyczne tło pulpitu i wyśrodkowane szare okno „Vision Workstation Startup”; odręczny znak VISION, segmentowy niebieski pasek postępu oraz lista usług i urządzeń. Statusy pochodzą z udokumentowanego interfejsu Vision, a nie z sekwencji czasowej w przeglądarce.

Przykładowe etykiety prezentacyjne (PROPOSED, nie lista istniejących endpointów):

| Pozycja | Co przedstawia |
| --- | --- |
| Vision Workstation | Stan połączenia klienta z systemem, jawnie odrębny od gotowości sprzętu |
| Vision Core | Raport usługi/koordynatora |
| ROS 2 services | Raport integracji |
| Luxonis | Raport dostępnego sensora RGB-D |
| NERO / MoveIt 2 | Raport warstwy robota i planowania |
| Sony Camera | Raport dostępnego urządzenia fotograficznego |

Lista powinna ostatecznie wynikać z raportu i capabilities systemu, bez sztywnego związania z konkretnym sprzętem. Etykiety READY, INITIALIZING, WAITING, ERROR, UNKNOWN/STALE są proponowanym językiem prezentacji, nie nową maszyną stanów. Backend dostarcza statusy oraz powody, ich mapowanie do interfejsu musi być jawne. Prawdziwy procent prezentować tylko przy udostępnionym przez backend mierniku ukończenia; w przeciwnym razie wskaźnik nieokreślony i opis bieżącego stanu. Brak odpowiedzi nie oznacza 100% ani READY. Ekran nie uruchamia urządzeń i nie wymusza przejścia do kolejnego stanu systemu. Gdy Vision jest już uruchomiony, klient odczytuje aktualny raport bez ponownej inicjalizacji.

### C. Logowanie i D. Pulpit

Klasyczny dialog użytkownik/hasło; uwierzytelnienie i autoryzacja należą do systemu. Szczegóły kolejności uwierzytelnienia i udostępnienia raportu rozruchowego do uzgodnienia; przed logowaniem nie ujawniać chronionych informacji. Pulpit może pokazywać niedostępne urządzenia, jeżeli system zezwala na taką sesję; nie utożsamiać dostępności aplikacji z dopuszczeniem inspekcji. Awaria nie może blokować odczytu dostępnej, autoryzowanej diagnostyki tylko przez animację.

## 4. Desktop Shell (PROPOSED szczegóły)

Wielookienkowy pulpit: otwieranie i zamykanie, fokus i z-order, przeciąganie, zmiana rozmiaru, minimalizacja, maksymalizacja i przywrócenie, przełączanie z paska zadań. Menu Start zawiera skróty do aplikacji i uprawnione funkcje systemowe. Zasobnik pokazuje stan komunikacji, ewentualny stan systemu z raportu oraz zegar; rozróżnia czas klienta od czasu danych systemowych. Zapamiętywanie układu okien to preferencja interfejsu (np. lokalnie dla danego klienta), nie zapis stanu sesji inspekcji. Po zmianie rozdzielczości okna pozostają dostępne. Zamknięcie okna nie powoduje zatrzymania modułu lub anulowania scenariusza.

Zamknięcie klienta, wylogowanie oraz żądanie zamknięcia VENTUNO to trzy różne czynności. Dialog nie może sugerować ich równoważności.

## 5. Aplikacje pulpitu (PROPOSED podział/nazwy, integracja etapowa)

| Aplikacja | Funkcje widoczne dla operatora | Autorytatywne dane/operacje |
| --- | --- | --- |
| Vision Core / System Status | Stan sesji, urządzeń, powody blokad, stan komunikacji | Core/Runtime i raport capabilities |
| ECU Library / Reference Editor | Katalog, wyszukiwanie, wybór modelu, rewizje, edycja wzorca i przegląd | ECU Profiles i Asset Store |
| Inspection Manager | Karta sztuki, zadeklarowany wariant i receptura, etapy, dowody, wynik, dozwolone żądania | Core / Workflow / Runtime |
| Luxonis Viewer | RGB, Depth, Point Cloud, geometria, timestamp i oznaczenia pomiarów | Sensor i moduły systemu, przez udostępnione API |
| NERO / Motion Viewer | Stan robota i osi, scena, podgląd planu, diagnostyka, dozwolone operacje | MoveIt/robot przez system; brak własnego planowania i executorów |
| Sony Camera | Parametry i stan akwizycji, zdjęcia i transfer | Moduł akwizycji przez system |
| Image Explorer | Miniatury, metadane, zoom, nawigacja, A/B i nakładki różnic | Archiwum i wyniki przetwarzania Vision/OpenCV |
| Control Panel | Preferencje GUI, widok konfiguracji stanowiska, uprawnione zmiany | System dla ustawień technicznych; klient dla wyglądu |
| Event Viewer | Zdarzenia, błędy, filtry i identyfikatory operacji | Dziennik systemu |

Podgląd 3D, strumienie i porównanie zdjęć mogą być rozwijane etapami. Etykiety nie oznaczają dodatkowych procesów sprzętowych ani zamrożenia konkretnego modelu kamery lub robota w logice GUI. Przy wymianie urządzenia interfejs prezentuje dostępne capabilities zamiast zakładać konkretnego producenta lub liczbę przegubów.

### ECU Reference Profile — wiążące istniejące UX

Realizować [zaakceptowany UX V1](ECU_LIBRARY_SELECTION_EDITOR_V1.md), nie tworzyć konkurencyjnej specyfikacji. Edytor odzwierciedla 15 sekcji profilu, źródło, jednostkę, datum, niepewność, datę, autora, stan weryfikacji oraz zasoby i manifesty. Wzorzec jest oddzielony od karty badanego egzemplarza i od wykonawczego ECUProfile/ScenarioSpec. DRAFT może być przeglądany i edytowany, ale nie uruchamia niezatwierdzonej receptury. Backend decyduje o dostępnych operacjach, zatwierdzeniach i rewizjach; APPROVED nie edytuje się w miejscu. Operator deklaruje typ ECU, system go weryfikuje. Aktualne pomiary, wyniki porównania i ocena zgodności nie są obliczane ani zatwierdzane przez GUI.

## 6. Granica API i niezawodność (PROPOSED kontrakt logiczny)

Nie definiujemy fikcyjnych działających adresów endpointów. Najpierw inwentaryzacja aktualnych portów i kontraktów Core/Runtime/Planner/Profile, następnie osobny przegląd adaptera API. Interfejs powinien opisywać:

| Obszar kontraktu | Oczekiwane dane lub zachowanie |
| --- | --- |
| Tożsamość i wersja | Wersja API i schematów, dostępne capabilities, zgodność klienta |
| Raport stanu | Aktualny snapshot, znacznik czasu/revision, gotowość, przyczyny blokad |
| Zdarzenia | Zmiany stanu z identyfikatorem/porządkiem pozwalającym wykryć lukę |
| Sesje i etapy | Identyfikator sesji/etapu, stan, powiązania, wymagane dowody, wynik |
| Katalog i zasoby | Identyfikatory i rewizje profilu, status, metadane assetów i dostęp autoryzowany |
| Żądania | Autoryzowane intencje, korelacja, kontekst/revision, odpowiedź i powód odmowy |
| Wynik operacji | ACK oddzielony od końcowego rezultatu; aktualny stan z backendu |
| Media | Udokumentowane strumienie/zasoby z timestampem, identyfikacją i kontrolą dostępu |

Proponowany transport REST dla snapshotów i żądań oraz WebSocket (lub uzgodniony transport zdarzeń) dla aktualizacji. Transport obrazów dobierany oddzielnie według wymaganej przepustowości, bez wystawiania ROS bezpośrednio do przeglądarki. Kontrakty i typy mają pochodzić ze wspólnego, wersjonowanego źródła, z walidacją danych na granicy klienta. Niezgodny schemat nie może zostać przemilczany.

Po utracie połączenia: wyraźny OFFLINE/UNKNOWN, oznaczenie ostatnich danych jako nieaktualnych, brak niejawnych nowych żądań operacyjnych i brak automatycznej kolejki odtwarzającej polecenia po reconnect. Po ponownym połączeniu odczytać świeży snapshot, uzgodnić wersję/ciąg zdarzeń i odtworzyć prezentację aktualnego stanu. Reakcja fizycznego procesu na rozłączenie należy do systemu. Przy wielu klientach konflikty zapisu i równoległe żądania rozstrzyga backend; GUI prezentuje odrzucenie i aktualizuje stan. Nie zakładać sukcesu operacji przy timeout po stronie klienta.

## 7. Logowanie, dostęp i Kiosk

**ACCEPTED:** lokalny Kiosk, zdalna przeglądarka, ekran logowania, administracyjny powrót do Ubuntu, zamknięcie/restart z menu Start jako żądania do systemu.

**PROPOSED wymagania:** ten sam build klienta i API, niezależny cykl życia przeglądarki, automatyczne uruchomienie klienta na stanowisku bez zmiany stosu ROS 2. Preferowany Chromium Kiosk + systemd lub odpowiednia sesja systemowa, po osobnym sprawdzeniu na ARM64. Kiosk nie jest mechanizmem bezpieczeństwa ani autoryzacji. Konto przeglądarki bez uprawnień roota, chroniony administracyjny mechanizm opuszczenia Kiosk, brak dowolnego wykonywania komend z GUI. Uprawnienia egzekwowane dla każdej operacji po stronie systemu; nie zapisywać haseł, tokenów ani danych wrażliwych w preferencjach pulpitu. Autoryzacja strumieni i assetów, ograniczenia origin, transport i bezpieczne przechowywanie sesji do projektu integracyjnego. Nie publikować surowego API sterowania ani usług ROS w Internecie. Rola operatora i administratora stanowią propozycję do specyfikacji dostępu, nie istniejące role.

Restart i shutdown: oddzielne dialogi potwierdzenia, serwerowa kontrola uprawnień i bieżącego kontekstu oraz status przyjęcia/odmowy. System decyduje o koordynacji usług i urządzeń zgodnie z własnymi procedurami; GUI nigdy nie uruchamia systemowych komend ani nie wymyśla procedury PARK/HOLD. Nie wdrażać wykonawczych poleceń zasilania przed uzgodnieniem i odbiorem właściwego backendu.

## 8. Organizacja kodu i izolacja (PROPOSED)

Preferowany stos React + TypeScript + Vite + 98.css; własny lekki Desktop Shell. Wersje i licencje zależności weryfikować przy implementacji, utrzymywać lockfile. Proponowany katalog i podział:

```text
webgui/
  src/
    shell/           # desktop, window manager, taskbar
    startup/         # intro, widok raportu rozruchowego
    apps/            # okna poszczególnych aplikacji
    components/      # współdzielone kontrolki 98
    api/             # transport, typy, walidacja, subskrypcje
    state/           # stan prezentacji, nie Workflow
    demo/            # izolowane syntetyczne fixtures (tylko dev/test)
    assets/          # legalne i zatwierdzone zasoby
  tests/
```

Oddzielny adapter demonstracyjny: jasno widoczny DEMO, syntetyczne dane, brak możliwości połączenia z aktuatorami, brak żądań do produkcyjnego API; nie może zastąpić realnego adaptera jako fallback. Budowa i testy klienta niezależne od sprzętu. Preferencje lokalne nie przechowują autorytatywnych danych. Nie kopiować istniejącego kodu Workflow ani algorytmów planowania do TypeScript.

## 9. Pakiety prac równoległych (PROPOSED)

| Pakiet | Dostarczany zakres | Zależności / kryterium wejścia |
| --- | --- | --- |
| GUI-01 | Desktop Shell, komponenty i ikony, menu Start, zarządzanie oknami, szkielet adaptera | ADR; izolowany tryb demo |
| GUI-02 | Intro VISION, ekran raportu inicjalizacji, dialog logowania jako widok | GUI-01, asset intro do weryfikacji; bez sterowania sprzętem |
| GUI-03 | ECU Library i Reference Editor | Przyjęte UX profili; fixtures do czasu kontraktu API |
| GUI-04 | Inspection Manager | Kontrakt sesji/etapów; tylko prezentacja i żądania |
| GUI-05 | Widoki urządzeń i planów | Kontrakt capabilities, stanu i strumieni |
| GUI-06 | Image Explorer i porównania | Kontrakt archiwum, assetów i wyników analizy |
| GUI-07 | Integracja z realnym API, reconnect i synchronizacja | Wersjonowane kontrakty, testy autoryzacji i integracji |
| GUI-08 | Uwierzytelnienie w pełnej integracji, Kiosk, funkcje administracyjne i zasilanie | Odbiór backendu i lokalnej konfiguracji; osobny przegląd |

Kontrakty API uzgadniamy od GUI-01, nie dopiero na GUI-07. Prace rozpoczynają się z aktualnego main w małych PR, np. feat/webgui-desktop-v1, niezależnie od eksperymentów runtime. W tej zmianie nie rozpoczynamy implementacji ani wdrożenia. [Repository Hygiene](../process/REPOSITORY_HYGIENE_V1.md) określa granice publicznych danych i nazw gałęzi.

## 10. Kryteria akceptacji / testy

| ID | Warunek weryfikacji (do wykonania podczas implementacji) |
| --- | --- |
| WEB-01 | Build/typecheck/lint i testy jednostkowe GUI bez ROS, sprzętu i aktywnego backendu. |
| WEB-02 | Otwarcie wielu okien, fokus, minimalizacja, maksymalizacja, przywrócenie, zamknięcie i zachowanie preferencji. |
| WEB-03 | Intro z prawdziwego assetu po jego odbiorze; statusy inicjalizacji odzwierciedlają fixture lub rzeczywisty raport, nigdy timer gotowości. |
| WEB-04 | Backend testowany headless; zamknięcie lub reload przeglądarki nie kasują stanu sesji ani nie dyspozycjonują operacji. |
| WEB-05 | OFFLINE, stale, luki zdarzeń, timeout, nieznany status i niezgodna wersja API są obsłużone jawnie; brak fikcyjnego READY. |
| WEB-06 | Reconnect i dwóch klientów odtwarzają ten sam autorytatywny stan, bez niejawnego retry operacji fizycznej. |
| WEB-07 | ACK nie zmienia etapu na SUCCEEDED; odmowa/bramka i jej powód prezentowane z systemu. |
| WEB-08 | DRAFT widoczny, ale brak uruchomienia niezatwierdzonej receptury; profil i karta egzemplarza odrębne. Backend blokuje również bezpośrednie, nieuprawnione żądanie API. |
| WEB-09 | Tryb demo oznaczony, odizolowany, brak dostępu do rzeczywistego sprzętu; sprawdzenie zależności i granicy transportu. |
| WEB-10 | Wygasanie sesji, autoryzacja odczytu i operacji, odmowa nieuprawnionego restartu; klient nie wykonuje powłoki. |
| WEB-11 | Kiosk i zdalna przeglądarka używają tego samego API; kontrolowany powrót administracyjny do Ubuntu, restart GUI nie restartuje usług sprzętowych. |
| WEB-12 | Czytelność na rzeczywistym ekranie, obsługa klawiatury, widoczny fokus, statusy rozpoznawalne również bez koloru. |

Testy frontendowe i integracyjne wykorzystują syntetyczne dane lub zatwierdzony system testowy. Odbiór na VENTUNO i wszelkie próby z rzeczywistym sprzętem są oddzielnym etapem. Żaden PASS dla makiety nie jest dowodem gotowości NERO, kamer ani inspekcji.

## 11. Otwarte elementy do przeglądu

- Lokalizacja i integralność źródłowej animacji Stream Deck; weryfikacja, czy można legalnie umieścić asset w publicznym repozytorium.
- Konkretne schematy/wersje API, mechanizm autoryzacji, polityka konfliktów wielu klientów i świeżość raportów.
- Wersje zależności frontendowych, finalna paleta i zestaw własnych ikon, ekran referencyjny i skala, nazwy aplikacji, język GUI.
- Sposób uruchamiania i opuszczenia Kiosk na VENTUNO; działanie bez sieci, polityka dostępu zdalnego i procedury zasilania.
- Kolejność i granice pakietów do dopracowania podczas projektowania; nie zmieniają obowiązującej zasady klient-only.
