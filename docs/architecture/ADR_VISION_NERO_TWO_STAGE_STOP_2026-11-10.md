# ADR-VISION-ROBOT-001 — Dwustopniowe zatrzymanie AgileX NERO w stanowisku Vision

- **Data decyzji:** 2026-11-10
- **Status decyzji architektonicznej:** **ACCEPTED** — podział na etap 1 i etap 2 uzgodniony z właścicielem projektu
- **Status realizacji:** **ETAP 1 — PARTIAL / LAB TEST**; **ETAP 2 — PLANNED**
- **Zakres:** NERO 7-DOF, Arduino VENTUNO Q (Vision), Elgato Stream Deck Plus, SocketCAN / pyAgxArm, zasilanie i UPS
- **Zasięg zastosowania:** prototyp laboratoryjny pod bezpośrednim nadzorem operatora; **nie jest to deklaracja osiągnięcia bezpieczeństwa funkcjonalnego**
- **Repozytorium:** `autoklinika/Vision`; dokument decyzji — bez kodu, numerów seryjnych, adresów prywatnej sieci i sekretów

## 1. Kontekst i wcześniejsze ustalenia

Vision to stanowisko do fotograficznej inspekcji PCB/ECU. NERO przenosi docelowo aparat Sony A6100 i kamerę głębi Eye-in-Hand. Ruch ramienia musi współistnieć z akwizycją, sterowanym oświetleniem i obecnością operatora w laboratorium.

W rozmowach projektowych z 2026-10-28 ustalono:
- fizyczny E-STOP ma być **niezależny** od Linuxa, połączenia CAN i aplikacji Vision, a jego stan powinien być monitorowany przez VENTUNO Q;
- Stream Deck Plus udostępnia oddzielny STOP programowy i po zatrzymaniu może udostępniać panel decyzji;
- po zatrzymaniu nie ma samoczynnego wznowienia: wymagane są potwierdzenie operatora, przywrócenie gotowości i weryfikacja stanu;
- `EMERGENCY STOP` oraz `POWER FAILURE` to dwa różne scenariusze;
- w przypadku utraty zasilania UPS ma zapewnić czas na zakończenie pracy i, **jeżeli jest to bezpieczne i dozwolone**, automatyczne parkowanie oraz kontrolowane wyłączenie; stan STOP / awaria mają pierwszeństwo nad parkowaniem.

W dniu 2026-11-10 właściciel zdecydował o **realizacji w dwóch etapach** z odłożeniem prac nad przyciskiem fizycznym do momentu przeniesienia robota poza laboratorium. Ta decyzja opisuje priorytet rozwoju; nie znosi potrzeby oceny ryzyka ani wymogu niezależnych zabezpieczeń przed użyciem, jeśli ocena ryzyka ich wymaga.

Dokumentacja NERO ostrzega, że po odcięciu zasilania ramienia może dojść do jego opadnięcia; zwykłe przerwanie 24 V nie może zostać przyjęte jako domyślna metoda zatrzymywania i podtrzymania ramienia. Nie mamy zweryfikowanego wejścia STO/SS1 ani sposobu działania opcjonalnego fabrycznego przycisku STOP.

## 2. Decyzja: dwa etapy, bez odcinania 24 V przy zwykłym STOP

### Etap 1 — STOP programowy na Stream Deck Plus (realizacja bieżąca)

- Wyznaczony klawisz: **prawy dolny** (ósmy z ośmiu klawiszy, indeks 7); czytelna czerwona grafika `STOP SW`.
- Naciśnięcie **żąda niezwłocznego, kontrolowanego zatrzymania ruchu** przez oficjalne SDK AgileX (`pyAgxArm`, firmware profile `NeroFW.V121`, funkcja `electronic_emergency_stop()`).
- **Nie wywoływać `disable()`, nie odcinać 24 V i nie inicjować wyłączenia zasilacza** jako normalnej reakcji na STOP. Utrzymanie pozycji przez napędy po hamowaniu wymaga osobnej walidacji na rzeczywistym ramieniu z docelowym obciążeniem.
- Zatrzymanie ma być **zatrzaskiwane (latched)**: żadna nowa komenda ruchu nie może zostać dopuszczona, dopóki operator nie wykona jawnej procedury przywrócenia gotowości.
- Po zatrzymaniu Stream Deck ma przełączyć się w **menu obsługi zatrzymania**. Zakres i zachowanie opcji nie są jeszcze zatwierdzone.
- STOP musi być dostępny niezależnie od aktualnego ekranu/menu aplikacji użytkownika, o ile działa sam Stream Deck i jego ścieżka komunikacji.
- Wszystkie ścieżki zadawania ruchu (GUI, skrypt, SDK, przyszły planner, automatyka) muszą przechodzić przez **wspólny centralny interlock ruchu**. Sam plik z flagą STOP nie blokuje innych procesów.
- Brak pozytywnej telemetrii, utrata CAN lub timeout potwierdzenia = **stan błędu/niepewnego zatrzymania**. Nie oznaczać wyniku jako potwierdzonego; blokować nowe zadania i wymagać interwencji operatora.
- Wstępny test wykonany w laboratorium potwierdził dostarczenie komendy i odpowiedź `EMERGENCY_STOP(0x1)`, ale **nie jest pomiarem drogi/czasu zatrzymania podczas ruchu i nie dowodzi funkcji bezpieczeństwa**.

### Etap 2 — grzybek jako fizyczne wejście STOP programowego (odroczony)

- Po przeniesieniu robota do stanowiska docelowego zostanie dodany fizyczny przycisk zatrzymania podłączony do odpowiedniego wejścia VENTUNO Q / lokalnego kontrolera IO.
- Przycisk ma uruchamiać **ten sam logiczny tor żądania STOP** co Stream Deck: blokada ruchu, polecenie hamowania, monitoring, zatrzask i panel obsługi zatrzymania.
- Projekt wejścia powinien uwzględnić styki normalnie zamknięte, diagnostykę przerwy przewodu, filtrację drgań styków, stan przy starcie, wykrycie odłączenia urządzenia i zakaz automatycznego restartu; **dobór pinów i układu elektrycznego pozostaje otwarty**.
- **Zastrzeżenie:** grzybek działający wyłącznie przez GPIO/STM32/VENTUNO/Linux/CAN nadal jest STOP-em sterowanym programowo, a **nie niezależnym, certyfikowanym obwodem E-STOP**. Nie wolno go tak oznaczać ani deklarować PL/SIL/STO/SS1 bez osobnej weryfikacji.
- Zgodnie z wcześniejszym wymaganiem architektury, niezależne zabezpieczenie zatrzymania, podtrzymania i ochrony przed opadnięciem należy rozstrzygnąć po ocenie ryzyka i dokumentacji AgileX; nie projektować zwykłego odcięcia zasilania jako substytutu podtrzymania.

## 3. Co faktycznie działa na Vision (stan 2026-11-10)

**Potwierdzone:**
- VENTUNO Q / Ubuntu ARM64 komunikuje się z NERO przez odrębny adapter USB-CAN i SocketCAN 1 Mb/s; nie mylić go z wbudowanymi kanałami CAN VENTUNO.
- Oficjalne SDK `pyAgxArm` odczytuje firmware NERO **1.22**, status sterownika i kąty siedmiu przegubów.
- OpenDeck **2.14.1 ARM64** uruchomiono z NVMe jako usługę użytkownika `vision-opendeck.service` z autostartem; Stream Deck Plus jest rozpoznawany przez USB/HID.
- Prawy dolny przycisk `STOP SW` został przypisany do skryptu wykonującego `electronic_emergency_stop()`.
- Dwa wcześniejsze wywołania STOP zostały zarejestrowane; sterownik zgłosił `EMERGENCY_STOP(0x1)` i kod błędu `0x0`.
- Poprawiono mapowanie klawisza w profilu OpenDeck; grafika jest widoczna; operator zaakceptował chwilowe zmniejszenie ikony po naciśnięciu.
- Odczytano i zachowano lokalnie pozycję referencyjną siedmiu przegubów. Żadne polecenia ruchu testowego nie zostały jeszcze wykonane w tej sesji.

**Niepotwierdzone / do wdrożenia:**
- zatrzymanie **podczas rzeczywistego ruchu**: opóźnienie od klawisza do reakcji, czas/droga hamowania, powtarzalność;
- stabilne **utrzymanie pozycji** przy masie aparatu i przy utracie komunikacji lub zasilania;
- reakcja na kolizję i odłączenie CAN/USB, awarię OpenDeck, restart kontrolera oraz brak odpowiedzi firmware;
- centralne wymuszanie blokady ruchu przez wszystkie sterowniki — obecny zapis lokalnego latch **nie jest jeszcze globalnym interlockiem**;
- ekran/menu działań po STOP — nie wdrożono;
- wspólny stan i kontrakt komunikatów między aplikacją Vision, kontrolerem ruchu i Stream Deck;
- układ elektryczny przycisku fizycznego, niezależna funkcja bezpieczeństwa, procedura testów oraz certyfikacja (jeżeli wymagana).

## 4. Kontrakt zachowania i priorytety

### Stany logiczne (projekt)

| Stan | Znaczenie | Czy wolno wysłać nowy ruch? |
|---|---|---|
| `INIT / NOT_READY` | Brak walidacji uruchomienia lub brak telemetrii | **NIE** |
| `READY` | Warunki uruchomienia potwierdzone; reset STOP zakończony | Tylko po świadomym zleceniu operatora i dodatkowych ograniczeniach |
| `MOVING` | Ruch kontrolowany | Nie przyjmować sprzecznych poleceń |
| `STOP_REQUESTED` | STOP w toku; wysyłanie komendy i oczekiwanie na stan | **NIE** |
| `STOPPED_SW` | Sterownik potwierdził zatrzymanie; blokada jest zatrzaśnięta | **NIE** |
| `STOP_UNCONFIRMED / FAULT` | Brak komunikacji, sprzeczna telemetria lub brak potwierdzenia | **NIE**; interwencja operatora |
| `RECOVERY_PENDING` | Operator rozpoczął procedurę powrotu, brak pełnego preflight | **NIE** |
| `POWER_FAILURE` | Zanik sieci / tryb UPS; osobny scenariusz | **NIE** dla nowych zadań |

**Priorytety:**
1. Żądanie STOP/awaria blokuje wszystkie nowe polecenia; żadne zdjęcia ani zadania AI nie mogą samoczynnie ponowić ruchu.
2. Aktywny STOP **blokuje automatyczne parkowanie** — parkowanie oznacza ruch i wymaga osobnej zgody po przywróceniu warunków.
3. Zanik zasilania bez STOP uruchamia osobną procedurę UPS: blokada nowych zadań, bezpieczne przerwanie operacji, parkowanie **tylko gdy warunki i zapas energii są potwierdzone**, następnie wyłączenie.
4. Równoczesne `POWER_FAILURE` i `STOPPED_SW`: STOP ma pierwszeństwo; brak automatycznego ruchu. Zapobieganie opadnięciu przy wyczerpaniu UPS wymaga rozwiązania mechanicznego/sprzętowego — oprogramowanie nie daje gwarancji.
5. Awaria systemu Linux, OpenDeck albo CAN może uniemożliwić dostarczenie programowego STOP; dlatego nie jest to funkcja bezpieczeństwa niezależna od oprogramowania.

### Semantyka STOP

`STOP_REQUESTED`, `STOP_COMMAND_SENT` i `STOP_CONFIRMED_BY_CONTROLLER` to **trzy odrębne zdarzenia**. Potwierdzenie `EMERGENCY_STOP(0x1)` oznacza deklarowany stan kontrolera, nie dowód bezruchu każdego przegubu. Docelowa walidacja porównuje kąty/prędkości w kolejnych próbkach oraz rzeczywiste zachowanie ramienia i ładunku.

Stan zatrzymania musi przetrwać restart usług; wznowienie po restarcie nie może następować automatycznie. Przycisk STOP może zostać naciśnięty wielokrotnie — żądanie powinno być idempotentne i nie odblokowywać ruchu.

## 5. Menu Stream Deck po STOP — kierunek, nie decyzja o funkcjach

Do uzgodnienia z właścicielem:

| Opcja | Założony sens | Warunek |
|---|---|---|
| `STATUS` | Stan kontrolera, przegubów, komunikacji i powód zatrzymania | Tylko odczyt |
| `RESET / PRZYGOTUJ` | Rozpoczyna nadzorowany recovery i preflight; **nie uruchamia ruchu** | Jawna decyzja operatora |
| `PARKUJ` | Żąda kontrolowanego przejścia do bezpiecznej pozycji | Tylko po odblokowaniu, nowym preflight i zgodzie |
| `WYŁĄCZ` | Kontrolowane zakończenie działania | Ocenić ryzyko opadnięcia i stan UPS przed wyłączeniem |

Możliwa osobna akcja `KONTYNUUJ` także pozostaje otwarta. W żadnym wariancie samo zwolnienie klawisza STOP, reset aplikacji, ponowne podłączenie CAN ani restart VENTUNO nie może automatycznie wznowić trajektorii.

## 6. Granice bezpieczeństwa i akceptowane ryzyka

- Etap 1 jest **narzędziem do kontrolowanych prób laboratoryjnych** i nie zastępuje odpowiedniego sprzętowego systemu bezpieczeństwa.
- Właściciel wybrał tymczasowe prowadzenie prac pod stałym nadzorem i odroczył GPIO/grzybek do etapu stanowiska docelowego. Sam nadzór **nie eliminuje** ryzyka błędu oprogramowania, utraty CAN, zablokowania USB, uderzenia ani opadnięcia ramienia.
- Przed każdym testem: pewne mocowanie podstawy, znany obszar pracy bez osób i przeszkód, zachowawcze obciążenie, mechaniczne ograniczenie opadnięcia/odciążenie podczas uruchomienia i plan awaryjnego odłączenia zasilania z uwzględnieniem jego skutków.
- Nie oznaczać istniejącego klawisza `STOP SW` ani przyszłego samego wejścia GPIO jako certyfikowanego „E-STOP”; nazwa `EMERGENCY_STOP` w API jest nazwą stanu/komendy protokołu, nie dowodem funkcji STO/SS1 lub odpowiedniej kategorii/PL/SIL.
- Kamera głębi, AI i algorytmy detekcji przeszkód są wsparciem planowania, **nie** niezależnymi urządzeniami ochronnymi.
- Projekt nie zatwierdza prowadzenia ruchów autonomicznych ani eksploatacji w otoczeniu osób bez odrębnej oceny ryzyka i zabezpieczeń.

## 7. Plan walidacji i bramki

### Etap 1 — zadania do zamknięcia

1. Centralny interlock: jedna bramka dla wszystkich producentów komend ruchu, trwały latch, stan po restarcie `NOT_READY`/`STOPPED`; testy mock i negatywne.
2. Potwierdzić prawidłowy stop request → komenda → status → blokada ruchu; test niespójności i timeoutów **bez** poruszania ramieniem.
3. Zaprojektować i zatwierdzić menu STOP, dokładne akcje oraz kontrolowany reset/recovery; sprawdzić, że RESET sam nie uruchamia ruchu.
4. Przygotować technicznie i organizacyjnie nadzorowany test małego ruchu z właściwym podparciem i niezależną metodą ograniczenia skutków niepowodzenia; dopiero wtedy osobna zgoda operatora na zasilenie napędów i ruch.
5. Zmierzyć zatrzymanie w ruchu, stabilność pozycji i zachowanie z docelowym obciążeniem, następnie sprawdzić utratę CAN, USB, zasilania oraz komunikat o niepotwierdzonym STOP.
6. Zachować lokalne logi, wersje SDK i firmware, konfigurację, wyniki/odchyłki oraz procedurę rollback. Wynik `PASS` dotyczy **tylko** badanego zakresu.

### Etap 2 — wymagania wejściowe

1. Określić wolny i odpowiedni interfejs IO VENTUNO/STM32, projekt obwodu przycisku, monitoring ciągłości i izolację elektryczną.
2. Zdefiniować kontrakt GPIO → kontroler STOP → CAN; uwzględnić rozłączenie przewodu, restart, utratę hosta i powrót zasilania.
3. Potwierdzić z AgileX, jak działa opcjonalny fabryczny STOP, czy istnieje wejście STO/SS1 i jakie mechanizmy zapobiegają opadnięciu po awarii zasilania.
4. Wykonać ocenę ryzyka stanowiska docelowego i podjąć **osobną decyzję** o koniecznej niezależnej, sprzętowej funkcji bezpieczeństwa. Sam grzybek na GPIO nie kończy tego zadania.
5. Zatwierdzić montaż, testy odbiorcze i scenariusze awaryjne przed wdrożeniem poza laboratorium.

## 8. Alternatywy i powody odrzucenia

| Wariant | Rozstrzygnięcie |
|---|---|
| Odcinanie zasilania 24 V standardowym grzybkiem jako podstawowy STOP | **Nie przyjęto** — ryzyko niekontrolowanego opadnięcia; wymaga innego rozwiązania zabezpieczającego |
| Sam przycisk OpenDeck jako docelowy E-STOP | **Nie przyjęto** — zależy od wielu warstw software/USB/CAN |
| Dodatkowy grzybek GPIO jako niezależna funkcja bezpieczeństwa | **Nie przyjęto takiej klasyfikacji** — to drugi wyzwalacz STOP SW, nie obwód niezależny |
| Użycie kamery głębi/AI jako zabezpieczenia | **Nie przyjęto** — brak niezależności i walidacji bezpieczeństwa |
| Natychmiastowe automatyczne parkowanie po STOP | **Nie przyjęto** — parkowanie wymaga ruchu po zatrzymaniu |
| NERO SDK `electronic_emergency_stop()` jako bieżąca komenda hamowania | **Przyjęto do etapu laboratoryjnego**, z obowiązkiem weryfikacji skuteczności i ograniczeń |

## 9. Powiązane dokumenty i zasady procesu

- [Architektura Vision — bezpieczeństwo mechaniczne](OVERVIEW.md).
- [Plan weryfikacji integracji sprzętowej](../hardware/INTEGRATION_PLAN.md).
- [Weryfikacja Stream Deck Plus i OpenDeck (gałąź robocza)](https://github.com/autoklinika/Vision/blob/docs/hardware-verification-20261010/docs/hardware/STREAM_DECK_SONY_BLE_TESTS_2026-10-12.md).
- [Weryfikacja VENTUNO Q / STM32 / CAN (gałąź robocza)](https://github.com/autoklinika/Vision/blob/docs/ventuno-stm32-csi-can-20261011/docs/hardware/VENTUNO_Q_STM32_CSI_CAN_READONLY_2026-10-11.md).
- [Zasady zmian w repozytorium](../process/DEVELOPMENT.md).
- Instrukcja producenta AgileX NERO, rozdział `11.3 Emergency Handling` (lokalnie, nie dodawać kopii PDF bez zweryfikowania praw do dystrybucji).

**Zmiany realizacyjne w repozytorium i na sprzęcie:** osobne gałęzie/PR, testy, ocena ryzyka i wyraźna zgoda właściciela na merge do `main` oraz aktywowanie napędów. Ten ADR **nie uruchamia żadnego ruchu** i nie zmienia firmware, CAN, OpenDeck ani konfiguracji zasilania.

## 10. Otwarte decyzje (do osobnego zatwierdzenia)

- Ostateczne menu i zachowanie `STATUS / RESET / PARKUJ / WYŁĄCZ / KONTYNUUJ`.
- Definicja i miejsce implementacji centralnego nadzorcy interlocków oraz mechanizmu wyłącznego dostępu do CAN dla sterowania ruchem.
- Progi czasowe potwierdzenia STOP, sposób pomiaru opóźnienia i kryteria akceptacji hamowania oraz podtrzymania.
- Strategia mechanicznego zabezpieczenia przed opadnięciem ramienia, szczególnie z kamerą na końcu.
- Weryfikacja fabrycznego akcesorium STOP AgileX, złącza i jego klasyfikacji bezpieczeństwa.
- GPIO, obwód i testy przycisku w etapie 2.
- Niezależna funkcja bezpieczeństwa wymagana przed użytkowaniem poza laboratorium.
