# Vision WebGUI — wdrożenie na VENTUNO

## Co uruchamia to wydanie

Wydanie uruchamia niezależną usługę Core oraz WebGUI w stylu Windows 98 z lokalnym
logowaniem. API odczytuje raporty Core przez prywatne połączenie lokalne.
**WebGUI pozostaje klientem systemu Vision.** Nie tworzy
sesji badanego egzemplarza i nie przejmuje logiki Core, walidacji wzorców ani
sterowania urządzeniami.

Po uruchomieniu tego wydania poprawny stan stanowiska to:

- GUI/API dostępne po zalogowaniu;
- biblioteka ECU podłączona do rzeczywistego, trwałego backendu;
- `coreConnection: CONNECTED`;
- `state: NO_ACTIVE_SESSION`;
- gotowość Core `UNKNOWN`.

Core działa w stanie bezczynności i posiada trwałą bibliotekę. Podłączenie sesji
rzeczywistego egzemplarza wymaga zatwierdzonych wejść Runtime. Stan `CONNECTED`
potwierdza odpowiedź procesu Core, a nie gotowość ruchu, zdjęć czy pomiarów.
Restart GUI/API, wylogowanie i zamknięcie przeglądarki pozostawiają Core działający.

## Układ plików i właściciel

Instalator działa jako aktualny zwykły użytkownik stanowiska. Odczytuje jego
rzeczywisty katalog domowy przez `pwd.getpwuid()`. Na przyjętym VENTUNO jest to
użytkownik `arduino` i `/home/arduino`; nie należy uruchamiać instalatora przez
`sudo`. Instalator nie zmienia kont systemowych, haseł Ubuntu, ustawień GDM,
autologowania ani istniejącego ustawienia linger.

| Element | Położenie |
|---|---|
| Przypięte wydanie | `/srv/vision-data/releases/vision-webgui/<pełny_SHA_40_znaków>/` |
| Środowisko Python | `/srv/vision-data/tools/vision-webgui/venv/` |
| Zapis wersji zależności | `/srv/vision-data/tools/vision-webgui/environment.json` |
| Konta operatorów | `/srv/vision-data/state/vision-webgui/identity/accounts.json` |
| Pierwsze hasło | `/srv/vision-data/state/vision-webgui/identity/initial-login.txt` |
| Trwała biblioteka ECU | `/srv/vision-data/data/ecu-library/` |
| Profil kiosku Firefox | `/srv/vision-data/state/vision-webgui/browser/` |
| Natywny Firefox Mozilla, gdy potrzebny | `/srv/vision-data/tools/vision-webgui/firefox/firefox` |
| Pliki tymczasowe | `/srv/vision-data/run/vision-webgui/` |
| Prywatny socket Core | `/srv/vision-data/run/vision-core/core.sock` |
| Kopie poprzedniej konfiguracji | `/srv/vision-data/state/vision-webgui/deployment-backups/` |
| Usługa użytkownika | `~/.config/systemd/user/vision-webgui.service` |
| Niezależna usługa Core | `~/.config/systemd/user/vision-core.service` |
| Skrót aplikacji | `~/.local/share/applications/vision-webgui.desktop` |
| Autostart pulpitu | `~/.config/autostart/vision-webgui.desktop` |

Wszystkie dane aplikacji, środowisko i profil przeglądarki znajdują się na NVMe.
W katalogu domowym pozostają tylko wskazane pliki integracji pulpitu i systemd.
Konta i plik pierwszego hasła mają uprawnienia `0600`, a prywatne katalogi aplikacji
`0700`. Plik kont nie może znajdować się w repozytorium ani w katalogu obsługiwanym
przez serwer WWW.

## Przygotowanie przypiętego wydania

Najpierw należy dostarczyć sprawdzone wydanie Git do osobnego katalogu o nazwie
równej jego pełnemu SHA. Wymagane są lokalne metadane Git, czysty stan śledzonych
plików i zgodność `HEAD` z nazwą katalogu. Nie używamy ścieżki `current` ani innego
symlinka w konfiguracji usługi. Istniejący checkout projektu pozostaje niezależny.

Przykłady poniżej zakładają, że `VISION_RELEASE` wskazuje już istniejące wydanie;
wartość należy zastąpić rzeczywistym pełnym SHA:

```bash
VISION_RELEASE=/srv/vision-data/releases/vision-webgui/<PELNY_SHA_40_ZNAKOW>
```

Wydanie musi zawierać `requirements-station.txt`, kod `src`, konfigurację katalogu
ECU, szablon profilu oraz gotowy `webgui/dist`. Build wykonywany w tym wydaniu:

```bash
cd "$VISION_RELEASE/webgui"
npm ci
VITE_VISION_DEPLOYMENT=station npm run build
```

Tryb `station` dodaje do HTML znacznik wymagany przez serwer. Build laboratoryjny
nie przejdzie weryfikacji. Instalator sprawdza znacznik, komplet JavaScript/CSS,
noty licencyjne, rozmiary i dozwolone nazwy assetów. Nie buduje GUI samodzielnie.
Przed uruchomieniem powinny przejść odpowiednie testy wydania; samo przygotowanie
pliku instalacyjnego nie stanowi dowodu działania na VENTUNO.

## Walidacja, przygotowanie i uruchomienie

Instalator: `scripts/deploy/install_webgui.py`. Dostępne są trzy tryby:

Na VENTUNO `/usr/bin/firefox` może być launcherem pakietu Snap. Ten wariant nie
udostępnia profilowi przeglądarki wymaganej ścieżki `/srv/vision-data`; instalator
go odrzuca. W takim przypadku przed instalacją należy oddzielnie dostarczyć
zweryfikowane oficjalne wydanie natywnego Firefox Mozilla dla Linux ARM64 do
`/srv/vision-data/tools/vision-webgui/firefox/`. Instalator nie pobiera przeglądarki,
nie zmienia zasad Snap/AppArmor i nie wyłącza sandboxu. Poniższe przykłady używają
tej natywnej przeglądarki:

```bash
VISION_BROWSER=/srv/vision-data/tools/vision-webgui/firefox/firefox

python3 -B "$VISION_RELEASE/scripts/deploy/install_webgui.py" \
  --release "$VISION_RELEASE" --browser "$VISION_BROWSER" --validate-only

python3 -B "$VISION_RELEASE/scripts/deploy/install_webgui.py" \
  --release "$VISION_RELEASE" --browser "$VISION_BROWSER"

python3 -B "$VISION_RELEASE/scripts/deploy/install_webgui.py" \
  --release "$VISION_RELEASE" --browser "$VISION_BROWSER" --start
```

Domyślne `--browser /usr/bin/firefox` jest dopuszczone tylko dla natywnego pliku
wykonywalnego ELF, a nie wrappera Snap. Natywny plik na NVMe musi należeć do
aktualnego użytkownika i nie może mieć symlinków w ścieżce.

`--validate-only` wykonuje odczytowy preflight. Domyślny tryb przygotowuje pliki,
środowisko, konto początkowe i integrację pulpitu, po czym wywołuje `daemon-reload`;
nie uruchamia ani nie zatrzymuje usług. `--start` włącza automatyczny start obu
usług, uruchamia Core, sprawdza rzeczywistą odpowiedź i uruchamia GUI/API.
Przy pierwszym przeniesieniu biblioteki ze starego API do Core zatrzymuje stare
API przed startem nowego właściciela. Działający już GUI/API jest przełączany na
wybrane wydanie. Instalator nie otwiera okna Firefox w bieżącej sesji pulpitu.

Instalator **nie restartuje działającego Core**. Gdy jednostka Core wskazuje inne
wydanie, odmawia automatycznej podmiany. Przed aktualizacją Core należy potwierdzić
`CONNECTED` i `NO_ACTIVE_SESSION`, a następnie jawnie zatrzymać jego usługę.
Aktywna inspekcja wymaga oddzielnej procedury zakończenia lub uzgodnienia stanu.

Aktualizację samego GUI/API wykonujemy z `--core-release`, wskazując dotychczasowe
wydanie Core. Dzięki temu jego jednostka, proces i dane pozostają niezależne od
aktualizacji interfejsu. Obie ścieżki muszą wskazywać czyste wydania przypięte do
pełnego SHA, a pliki zależności współdzielonego środowiska muszą być identyczne:

```bash
python3 -B "$VISION_RELEASE/scripts/deploy/install_webgui.py" \
  --release "$VISION_RELEASE" --core-release "$VISION_CORE_RELEASE" \
  --browser "$VISION_BROWSER" --https-origin "$VISION_HTTPS_ORIGIN" --start
```

`VISION_CORE_RELEASE` należy ustawić na faktyczne bieżące wydanie z jednostki
`vision-core.service`, a origin na skonfigurowany adres HTTPS. Instalator nadal
odmawia nadpisania odmiennej konfiguracji działającego Core. Restart GUI/API
unieważnia jego sesje przeglądarkowe. Po aktualizacji otwarta karta powinna
wczytać dokument ponownie, aby korzystać z nowego kodu interfejsu.

Wymagane są zamontowane `/srv/vision-data`, istniejący bus użytkownika oraz dostępne
`git`, `systemctl`, `mountpoint`, Firefox i moduł Python `venv`. Instalator sam nie
uzyskuje uprawnień administracyjnych. Korzysta z busa przez `XDG_RUNTIME_DIR` równy
`/run/user/<uid>` oraz `DBUS_SESSION_BUS_ADDRESS` wskazujący tamtejszy socket.

Środowisko powstaje z `--system-site-packages`. Pakiety serwera są instalowane do
tego środowiska przez `pip install --require-hashes` z przypiętego pliku wymagań,
bez przebudowy pakietów systemowych. Nie instalujemy sterowników ani zależności
ROS. Przy niezmienionym hashu wymagań instalator zachowuje istniejące środowisko.
Zmiana zależności współdzielonego środowiska wymaga wcześniejszego jawnego
zatrzymania GUI/API i bezczynnego Core:

```bash
systemctl --user stop vision-webgui.service vision-core.service
```

Pliki zarządzane przez instalator mają własny znacznik w pierwszej linii.
Istniejący plik jednostki lub skrótu bez tego znacznika nie zostanie nadpisany.
Przed zmianą zarządzanych plików powstaje ich prywatna kopia na NVMe wraz
z manifestem docelowych ścieżek.

## Jednostka usługi i kiosk

Jednostka użytkownika wywołuje bezwzględną ścieżkę interpretera środowiska:

```text
/srv/vision-data/tools/vision-webgui/venv/bin/python -B -m vision_api.station
```

Argumenty wskazują port `18490`, prywatny plik kont, socket Core przez `--core-socket`
i `webgui/dist` konkretnego wydania. `PYTHONPATH` wskazuje jego `src`, a katalogiem
roboczym jest to samo wydanie. Usługa przed startem sprawdza mountpoint NVMe.
Ma `UMask=0077`, `Restart=on-failure`, `RestartSec=5s`, `NoNewPrivileges=yes`,
`TasksMax=32` i `MemoryMax=512M`. Nie konfiguruje uprzywilejowanych przestrzeni
nazw. Sprawdzenie mountpointu przy starcie nie jest pełnym sprzętowym Write Guard.

Oddzielna jednostka `vision-core.service` uruchamia `python -B -m vision_station.service`
z `--socket /srv/vision-data/run/vision-core/core.sock` i
`--library-root /srv/vision-data/data/ecu-library`. Core posiada bibliotekę oraz
opcjonalny rzeczywisty Runtime. GUI/API nie otwiera magazynu biblioteki.
Obie usługi mają osobne PID i automatyczny start. Jednostka GUI ma tylko `Wants`
i `After` względem Core: zatrzymanie lub restart GUI nie zatrzymuje Core,
a niedostępność Core nie zamyka serwera logowania.

Socket ma uprawnienia `0600`, katalog `0700`; sprawdzany jest UID obu procesów.
Lokalny protokół dopuszcza wyłącznie odczyt raportów. Brak odpowiedzi Core daje
`NOT_CONNECTED`, czytelny brak dostępnych danych i automatyczne ponawianie.
Nie oznacza to, że inspekcja została zatrzymana — jej stan jest wtedy nieznany.

Skrót i autostart uruchamiają wybrany przez `--browser` natywny Firefox; dla
opisanego wariantu Mozilla jest to:

```text
/srv/vision-data/tools/vision-webgui/firefox/firefox --no-remote --profile /srv/vision-data/state/vision-webgui/browser --kiosk http://127.0.0.1:18490/
```

Autostart dotyczy kolejnego logowania na pulpit. Nie włącza logowania automatycznego
do Ubuntu. Styl Windows 98 jest interfejsem aplikacji w przeglądarce; nie zmienia
wyglądu pozostałego Linuxa. Profil kiosku jest oddzielny od osobistego profilu
Firefox. Jeżeli ten profil kiosku już jest otwarty, nie należy uruchamiać drugiej
instancji na tym samym profilu.

## Logowanie i ważność sesji

Tylko jeżeli `accounts.json` jeszcze nie istnieje, instalator tworzy konto
`operator` z rolą `reader` i losowe hasło. Plik `initial-login.txt` zawiera samo
hasło, bez nazwy użytkownika. Jest zapisywany lokalnie jako `0600`; instalator
wypisuje wyłącznie jego ścieżkę. Kolejne instalacje nie zmieniają istniejących
kont i nie generują ponownie hasła.

Uprawnienia tego konta obejmują odczyt. Konto nie jest użytkownikiem systemowym,
administratorem Ubuntu ani upoważnieniem do ruchu lub akwizycji.

Zalogowany użytkownik zmienia własne hasło przez **Settings → Change password**.
Wpisuje obecne hasło, nowe hasło i jego potwierdzenie. Nowe hasło musi mieć co
najmniej 12 znaków, mieścić się w 1024 bajtach UTF-8 i różnić się od obecnego.
Backend zapisuje zmianę atomowo i unieważnia wszystkie sesje tego konta; po
potwierdzeniu należy zalogować się nowym hasłem. Błędne obecne hasło nie wylogowuje
użytkownika. Zmiana hasła nie uruchamia ani nie zatrzymuje Core.

Gdy po wysłaniu formularza połączenie zostanie przerwane, wynik może być
niepotwierdzony. Interfejs nie powtarza zapisu automatycznie. Należy wrócić do
logowania i sprawdzić nowe hasło. Odpowiedź API ani pliki przeglądarki nie zawierają
nowego hasła.

Lokalny reset konta pozostaje dostępny jako czynność administracyjna. Poniższy
proces pyta o nowe hasło przez `getpass`; nie przekazujemy hasła w argumentach
polecenia:

```bash
PYTHONPATH="$VISION_RELEASE/src" \
  /srv/vision-data/tools/vision-webgui/venv/bin/python -B -m vision_api.identity \
  --accounts /srv/vision-data/state/vision-webgui/identity/accounts.json \
  --forbid-root "$VISION_RELEASE/webgui/dist" reset operator
```

Opcja `--generate-to /prywatna/nowa/sciezka` po `reset operator` zamiast tego
generuje hasło do nowego prywatnego pliku. Nie nadpisuje istniejącego pliku.
Po zmianie w Settings lub lokalnym resecie wcześniejszy plik pierwszego hasła nie
jest aktualizowany i nie reprezentuje już obecnego hasła. Narzędzia odbioru i
monitoringu nie powinny traktować go jako stałego poświadczenia. Można też
utworzyć kolejne konto `reader`, używając `provision NAZWA` zamiast `reset operator`.

Sesja ma limit **8 godzin od logowania** oraz **30 minut bez żądań podtrzymujących
aktywność**. Sam odczyt informacji o sesji może korzystać z `touch=False`; żądania
chronionych widoków aktualizują aktywność. Dlatego otwarta karta regularnie
odpytująca backend zwykle dojdzie do limitu 8 godzin, a zamknięta karta wygaśnie
po 30 minutach bez ruchu. `expiresAt` wskazuje wcześniejszy z aktualnego limitu
bezczynności i limitu absolutnego.

Wylogowanie unieważnia token w backendzie, a klient usuwa chronione widoki
i zatrzymuje ich odpytywanie. Restart procesu unieważnia wszystkie sesje, ponieważ
ich tokeny nie są zapisywane na dysku. Reset hasła lub usunięcie konta unieważnia
jego wcześniejsze sesje przy następnym sprawdzeniu. Cofnięcie zegara powoduje
odrzucenie sesji i blokadę nowych logowań do czasu dogonienia ostatniego znanego
czasu; nie należy korygować tego przez kasowanie magazynu kont.

## Dostęp lokalny i prywatny HTTPS

Lokalny adres po uruchomieniu usługi:

```text
http://127.0.0.1:18490/
```

Serwer nasłuchuje wyłącznie na IPv4 loopback. Dostęp zdalny wymaga oddzielnego
zaufanego proxy TLS. Aby dopuścić konkretny adres Tailscale HTTPS, należy podać
ten sam adres podczas instalacji, np. `--https-origin https://NAZWA-URZADZENIA.TAILNET.ts.net`
zastąpiony rzeczywistą nazwą pisaną małymi literami, bez końcowego ukośnika.
Samo dodanie originu nie publikuje serwera.

Instalator tylko wypisuje proponowane polecenie. Operator z już posiadanym
uprawnieniem do Tailscale powinien najpierw sprawdzić istniejącą konfigurację
Serve, a dopiero potem zdecydować o zmianie:

```bash
tailscale serve status
tailscale serve --bg --https=443 http://127.0.0.1:18490
```

Nie stosujemy Funnel. Serve udostępnia usługę w prywatnym tailnecie, zgodnie
z jego uprawnieniami; nadal wymagane jest logowanie Vision. Brak uprawnień do
zmiany Serve nie jest podstawą do obchodzenia uwierzytelniania systemowego ani
do publicznego wystawienia portu. Zasady polecenia i TLS opisuje oficjalna
[dokumentacja Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).

## Sprawdzenie po uruchomieniu

```bash
systemctl --user status vision-core.service vision-webgui.service --no-pager
journalctl --user -u vision-core.service -u vision-webgui.service -n 50 --no-pager
```

Następnie należy sprawdzić lokalny adres w przeglądarce, zalogować się i otworzyć
bibliotekę. Oczekiwany jest rzeczywisty katalog/drafty z prywatnego magazynu,
Core połączony oraz brak aktywnej inspekcji w bezczynnym stanowisku.
Brak danych lub niegotowość wzorca pozostaje
widoczna; interfejs nie uzupełnia jej symulacją. Test HTTPS wykonujemy dopiero po
oddzielnej konfiguracji Serve.

## Wycofanie wydania

Punktem wycofania jest wcześniejszy zachowany katalog wydania i kopia zarządzanych
plików w `deployment-backups`. W kopii jednostki komentarz `# Release:` wskazuje
poprzednią ścieżkę. Nie usuwamy starego wydania przed potwierdzeniem nowego.

Powrót wymaga wcześniejszego potwierdzenia braku aktywnej inspekcji w połączonym
Core. Następnie zatrzymujemy obie zarządzane usługi i uruchamiamy instalator
poprzedniego rzeczywistego SHA. Zachowujemy ten sam wymagany origin HTTPS:

```bash
systemctl --user stop vision-webgui.service vision-core.service
VISION_PREVIOUS_RELEASE=/srv/vision-data/releases/vision-webgui/<POPRZEDNI_PELNY_SHA>
python3 -B "$VISION_PREVIOUS_RELEASE/scripts/deploy/install_webgui.py" \
  --release "$VISION_PREVIOUS_RELEASE" --browser "$VISION_BROWSER" --start
```

Jeśli używany był HTTPS, do ostatniego polecenia należy ponownie dodać właściwe
`--https-origin`. Instalator odtworzy zależności z pliku wymagań poprzedniego
wydania, jeśli ich hash się różni. Konta, biblioteka ECU oraz profil Firefox
pozostają w tych samych katalogach danych. Restart wymaga ponownego logowania.
Jeżeli poprzednie wydanie pochodzi sprzed oddzielenia Core, należy także wyłączyć
autostart `vision-core.service`, ponieważ stary serwer sam posiada bibliotekę.
Nie uruchamiamy równocześnie dwóch właścicieli tego samego magazynu. Wycofanie
tych usług nie wymaga zmian ROS ani istniejącego checkoutu projektu.
