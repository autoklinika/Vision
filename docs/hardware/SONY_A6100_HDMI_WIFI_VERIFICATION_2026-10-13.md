# Sony A6100 ↔ VENTUNO Q — HDMI/UVC i Wi-Fi Camera Remote API (2026-10-13)

**Projekt:** Vision — stanowisko fotograficzno-inspekcyjne PCB/ECU.  
**Host:** Arduino VENTUNO Q, Qualcomm QCS8275, Ubuntu 24.04.4 ARM64, kernel `6.8.0-1084-qcom`.  
**Aparat:** Sony ILCE-6100A (A6100).  
**Zakres:** rzeczywiste testy wejścia HDMI przez grabber USB 2.0 i bezpośredniej komunikacji Wi-Fi; bez wdrażania Vision Core.  
**Wynik:** **HDMI Live View 1920×1080 / MJPEG / ~30 FPS — PASS po rozruchu; dedykowany kanał Wi-Fi — PASS; Sony Camera Remote API — PASS dla odczytu.**  
**Zastrzeżenie:** statusy opisują konkretne próby, a nie gotowość produkcyjną. Zdalne wyzwalanie zdjęć, zoom i Wi-Fi Live View w tym etapie pozostają **NOT TESTED**.

> Repozytorium jest publiczne. Ten raport **celowo nie zawiera** haseł Wi-Fi, pełnych identyfikatorów SSID/BSSID/MAC, adresów prywatnych, numerów seryjnych ani zdjęć i surowych sesji warsztatowych. Adresy i nazwy interfejsów w przykładach są symboliczne; wartości ustala się na urządzeniu.

## 1. Kontekst i konfiguracja stanowiska

| Element | Weryfikowana konfiguracja |
|---|---|
| Wyjście aparatu | Sony A6100, micro-HDMI → HDMI; tryb wyjścia HDMI ręcznie ustawiony na 1080p podczas diagnozy |
| Grabber | MacroSilicon `534d:2109`, nazwa USB `USB Video`, USB 2.0 High-Speed (480 Mb/s), UVC 1.00 |
| Sterowniki Linux | `uvcvideo` (wideo), `snd-usb-audio` (audio), `usbhid` (HID) |
| V4L2 | `/dev/video0` (przechwytywanie), `/dev/video1` (węzeł dodatkowy); nazwy mogą zmienić się po reenumeracji |
| Narzędzie | `v4l2-ctl` z pakietu `v4l-utils`; operator zainstalował je w czasie testów |
| Wi-Fi główne | Pierwszy interfejs WLAN, sieć infrastrukturalna 5 GHz + Tailscale |
| Wi-Fi Sony | **Osobny adapter** Realtek RTL8188EUS (`rtl8xxxu`), AP aparatu `DIRECT-*:ILCE-6100A`, WPA2 / 2,4 GHz |
| Profil Sony | `vision-sony-a6100-wifi`, `ipv4.method=auto`, `ipv4.never-default=yes`, `connection.autoconnect=no` |
| Ścieżka API | HTTP na porcie TCP **10000**, endpoint `/sony/camera` (adres IPv4 aparatu ustalany lokalnie z DHCP) |

Wcześniejsze testy USB/PTP (JPEG 24 MP, RAW+JPEG, Preview, STAB-01–06) pozostają opisane osobno: [SONY_A6100_VERIFICATION_2026-10-10.md](SONY_A6100_VERIFICATION_2026-10-10.md). Wynik obecnego etapu **nie zastępuje** ani nie unieważnia ograniczeń USB/PTP.

## 2. HDMI/UVC — dziennik eksperymentów

| ID | Próba i obserwacja | Wynik |
|---|---|---|
| HDMI-01 | `lsusb` i `lsusb -t`: `534d:2109`, poprawna enumeracja 480 Mb/s; video/audio/HID z odpowiednimi sterownikami | **PASS — USB** |
| HDMI-02 | `v4l2-ctl --list-devices`: urządzenie `USB Video`, węzły wideo i `/dev/media1`; `--list-formats-ext` potwierdza MJPEG oraz YUYV | **PASS — V4L2** |
| HDMI-03 | MJPEG 1920×1080/30, 90 klatek, ok. 28,66–29,55 FPS. Pierwsza zapisana klatka JPEG (61 KiB) przedstawiała **pasy testowe**, a nie scenę z aparatu | **PASS — transport; FAIL — obraz sceny** |
| HDMI-04 | Sony HDMI ręcznie przełączono na 1080p; ponowna krótka próba: nadal pasy testowe | **FAIL — obraz sceny** |
| HDMI-05 | Fizyczne rozłączenie i ponowne podłączenie USB grabbera; log jądra potwierdził reenumerację UVC; nadal pasy | **PASS — reenumeracja; FAIL — obraz sceny** |
| HDMI-06 | Jako źródło HDMI podłączono laptop; przy krótkim teście VENTUNO nadal pasy. Laptop nie wykrywał wtedy drugiego monitora | **NIEJEDNOZNACZNE** — nie dowodzi awarii grabbera |
| HDMI-07 | Operator sprawdził **ten sam grabber z Sony na Windows 11** — poprawny obraz. Sony z tym samym przewodem dawał także obraz na zwykłym monitorze | **PASS (obserwacja operatora)** — sprzęt działa w innych konfiguracjach |
| HDMI-08 | Test formatów na VENTUNO: MJPEG 1080p/30 i 720p/30 zwróciły pasy; YUYV 640×480/10 ostatecznie dostarczył klatkę, także z pasami | **PASS — dekodowanie formatów; FAIL — krótkie sesje wejścia** |
| HDMI-09 | Strumień otwarty ciągle przez około 12 s, pominięto ~360 początkowych klatek i zapisano kolejną: widoczna **rzeczywista scena warsztatowa** | **PASS — obraz HDMI Sony** |
| HDMI-10 | Test **450 kolejnych klatek w jednej sesji, 15 s**; początkowo pasy, następnie prawidłowy obraz aż do końca. Pozytywnie zweryfikowane próbki ok. 6 s oraz 15 s | **PASS — stabilny obraz w oknie 15 s** |
| HDMI-11 | Odczyt USB runtime PM: przy bezczynności `suspended`, podczas długiego przechwytywania w 3. i 9. sekundzie `active` | **PASS — obserwacja stanu**, przyczyna rozruchu **UNVERIFIED** |

### 2.1 Parametry techniczne UVC

Według `v4l2-ctl --list-formats-ext` grabber deklaruje m.in.:

| Format | Rozdzielczość | Deklarowane FPS | Rzeczywiście sprawdzono |
|---|---|---|---|
| MJPEG | 1920×1080 | 60, 30, 25, 20, 10 | **30 FPS** — rzeczywisty Live View po rozruchu |
| MJPEG | 1280×720 | 60, 50, 30, 20, 10 | **30 FPS**, ale przy krótkiej próbie tylko pasy |
| YUYV 4:2:2 | 1920×1080 | 5 | Nie przeprowadzono testu sceny |
| YUYV 4:2:2 | 640×480 | 30, 20, 10, 5 | **10 FPS**, klatka z pasami (dekodowanie RAW → RGB) |

Wartości deklarowane przez urządzenie **nie są benchmarkiem** 60 FPS. Podczas ciągłego przechwytywania 450 klatek pomiar wypisywany przez `v4l2-ctl` ustabilizował się na około 30,00 FPS.

### 2.2 Wyjaśnienie kolorowych pasów — potwierdzone obserwacje

- Pasy pojawiały się w poprawnych plikach JPEG, w rozdzielczościach 1080p i 720p oraz w YUYV. Nie wynikały więc z błędnej aplikacji do wyświetlania JPEG.
- Początkowo uznano je za dowód braku HDMI, następnie podejrzewano uszkodzenie grabbera. **To były przedwczesne hipotezy.** Test na Windows 11 wykazał, że sprzęt potrafi działać prawidłowo.
- Zmiana wyjścia Sony na 1080p oraz krótkie odłączenie/podłączenie grabbera **nie rozwiązały** problemu.
- Kluczowe okazało się przechwytywanie przez dłuższy czas bez zamykania strumienia. Nie wiadomo jeszcze, czy źródłem zwłoki jest synchronizacja HDMI, negocjacja z hostem USB, wewnętrzny stan firmware grabbera czy inny czynnik.

### 2.3 Pomiar początku poprawnego obrazu

W **jednej** 15-sekundowej sesji zapisano 450 klatek MJPEG (~69,4 MB w RAM) i przeanalizowano granice JPEG oraz rozmiary:

| Klatka | Czas nominalny | Obserwacja |
|---:|---:|---|
| 15 | ~0,5 s | Pasy testowe, ~61 881 B |
| 30 | ~1,0 s | Pasy, ~61 881 B |
| 60 | ~2,0 s | Pasy, ~61 881 B |
| 63 | ~2,1 s | Pierwsza klatka >100 kB (ok. 169 566 B); **wniosek o przejściu** na treść sceny na podstawie wielkości |
| 90 | ~3,0 s | Wielkość ~169 474 B |
| 180 | ~6,0 s | **Wizualnie potwierdzony** rzeczywisty obraz |
| 449 | ~15,0 s | **Wizualnie potwierdzony** rzeczywisty obraz |

**Interpretacja:** ~2,1 s to **pojedynczy zaobserwowany próg**, a nie gwarantowany stały czas inicjalizacji. Dla klatki nr 63 odnotowano skok rozmiaru — szczegółowa weryfikacja wizualna obejmowała próbki 15, 180 i 449. Nie ustalono rozkładu opóźnień pomiędzy sesjami.

Ukończony test zwrócił `exit code=0`. Duży, tymczasowy plik strumienia został po analizie usunięty z `/dev/shm`. Próbki pomocnicze i wcześniejsze klatki mogą pozostać w RAM do czyszczenia/restartu — **nie są trwałym archiwum dowodów**.

### 2.4 Wnioski HDMI dla przyszłego adaptera (PLAN, nie implementacja)

1. Otwierać jeden długotrwały strumień UVC, a nie uruchamiać nowego przechwycenia dla każdej klatki.
2. Przewidzieć stany `DISCONNECTED → WARMING_UP → READY → DEGRADED/FAILED`.
3. Akceptować `READY` dopiero po **ocenie zawartości** i serii poprawnych klatek; upływ 3 s sam w sobie nie wystarcza.
4. Detektor pasów statycznych/no-signal nie może opierać się wyłącznie na długości JPEG. Potrzebne testy wzorca, zmian sceny, błędów ramek i timeoutów.
5. Rozpoznać urządzenie po stabilnej właściwości V4L2/USB zamiast na stałe przypisywać `/dev/video0`.
6. Badać **osobno** opóźnienie end-to-end, stabilność FPS, reconnect po utracie HDMI, wpływ zasilania USB i działanie długotrwałe.
7. Nie zmieniać globalnie polityki autosuspend ani kernela tylko na podstawie korelacji `suspended` / `active`. Brak dowodu, że jest to przyczyna opóźnienia.
8. Obraz HDMI 1080p to podgląd do kadrowania i wsparcia robota; **nie** zastępuje pełnych zdjęć 24 MP ani niezależnych zabezpieczeń ruchu.

## 3. Wi-Fi Direct i Sony Camera Remote API — dziennik eksperymentów

| ID | Próba i obserwacja | Wynik |
|---|---|---|
| WIFI-01 | Dwa interfejsy WLAN: infrastrukturalny 5 GHz oraz dedykowany adapter Realtek RTL8188EUS; drugi wykrywa AP aparatu `DIRECT-*:ILCE-6100A` (WPA2, kanał 11) | **PASS — wykrywanie** |
| WIFI-02 | Istniejący profil `vision-sony-a6100-wifi` był rozłączony; automatyczne połączenie przez MCP zatrzymał brak dostępnego sekretu WPA2 | **FAIL — automatyczna aktywacja** |
| WIFI-03 | Operator wykonał `nmcli --ask connection up ...`, wpisał hasło lokalnie; NetworkManager zestawił połączenie i uzyskał dzierżawę DHCP | **PASS — skojarzenie i IPv4** |
| WIFI-04 | Sieć główna pozostała aktywna, podobnie jak Tailscale; domyślna trasa do internetu nadal prowadzi przez główne WLAN | **PASS — izolacja trasowania** |
| WIFI-05 | Ping do serwera DHCP aparatu: 3 wysłane/3 odebrane, 0% utraty, RTT od ~2,9 do ~30,4 ms; pojawiła się też **jedna zduplikowana odpowiedź** | **PASS — ICMP**; duplikat do obserwacji |
| WIFI-06 | TCP: port **10000 otwarty**, porty 80 i 8080 odrzucają połączenie | **PASS — endpoint TCP** |
| WIFI-07 | `POST /sony/camera`, `getAvailableApiList`: HTTP **200**, prawidłowa odpowiedź JSON z listą metod | **PASS — API** |
| WIFI-08 | `getApplicationInfo`: HTTP **200**, `Smart Remote Control __SAK__`, wersja **2.1.7** | **PASS — identyfikacja aplikacji** |
| WIFI-09 | `getShootMode`: HTTP **200**, wartość `still` | **PASS — odczyt stanu** |

**Adresacja i ochrona sieci:** aparat działa jako punkt dostępowy i serwer DHCP; VENTUNO otrzymał adres IPv4 z maską `/16`. Profil ma `ipv4.never-default=yes`, więc nie przejął domyślnej trasy. Prefiks Sony `/16` może częściowo nachodzić na inną prywatną adresację lokalną; w badanym środowisku bardziej szczegółowa trasa głównego WLAN `/24` miała pierwszeństwo. Przy wdrożeniu należy sprawdzać kolizje tras w konkretnej sieci, a nie przyjmować izolacji za pewnik.

**Bezpieczeństwo:** hasło WPA2 wprowadził operator lokalnie interaktywnie. Nie kopiujemy go do dokumentacji, logów lub repo; w przykładach `nmcli` celowo nie użyto `--show-secrets`.

### 3.1 Udostępnione metody Camera Remote API

Przez `getAvailableApiList` aparat zadeklarował m.in. następujące metody:

| Obszar | Metody widoczne na liście | Czy rzeczywiście wykonano? |
|---|---|---|
| Informacje i stan | `getAvailableApiList`, `getApplicationInfo`, `getShootMode` | **TAK — PASS** |
| Wi-Fi Live View | `startLiveview`, `stopLiveview` | **NIE** |
| Wykonanie zdjęcia | `actTakePicture`, `awaitTakePicture` | **NIE** |
| Zoom | `actZoom` | **NIE** |
| Ekspozycja | `setFNumber`, `setShutterSpeed`, `setIsoSpeedRate`, `setExposureCompensation` | **NIE** |
| Inne odczyty | `getAvailableFNumber`, `getAvailableShutterSpeed`, `getAvailableIsoSpeedRate`, `getEvent`, `getTemporarilyUnavailableApiList` | **NIE** |

**Ważne:** obecność nazwy w odpowiedzi API nie oznacza, że dana czynność jest zawsze dostępna, że obiektyw ją wykona, ani że będzie działać równocześnie z HDMI/USB/PTP. Dostępność zależy m.in. od trybu pracy aparatu. Zoom optyczny wymaga osobnej weryfikacji z użytym obiektywem; testy Bluetooth/USB z wcześniejszych etapów nie zastępują próby Wi-Fi.

## 4. Procedury odtwarzalne (bez trwałych zmian konfiguracji)

Przed testem: włączyć aparat, podłączyć źródło HDMI do wejścia grabbera i sprawdzić dostęp do obu interfejsów VENTUNO. Polecenia diagnostyczne poniżej nie wyzwalają migawki.

### 4.1 Enumeracja i parametry wideo

```bash
lsusb -d 534d:2109
lsusb -t
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

### 4.2 Weryfikacja rzeczywistego HDMI z uwzględnieniem rozruchu

```bash
timeout 18s v4l2-ctl -d /dev/video0 --set-fmt-video=width=1920,height=1080,pixelformat=MJPG --set-parm=30 --stream-mmap --stream-skip=120 --stream-count=1 --stream-to=/dev/shm/vision-hdmi-check.jpg
file /dev/shm/vision-hdmi-check.jpg
```

To przechwycenie **nie dowodzi samo w sobie prawidłowego obrazu** — trzeba obejrzeć klatkę i potwierdzić realną scenę, a nie pasy. `--stream-skip=120` jest konserwatywnym ustawieniem diagnostycznym wynikającym z jednej próby, nie gwarancją. Plik trafia do RAM (`/dev/shm`), nie na NVMe.

### 4.3 Diagnostyka Wi-Fi bez ujawniania haseł/IP

```bash
nmcli -f DEVICE,TYPE,STATE,CONNECTION device status
nmcli -t -f NAME,TYPE,DEVICE connection show --active
nmcli -f DHCP4 device show <SONY_WIFI_IFACE>
ip -4 route
```

Gdy połączenie nie jest aktywne, operator może **lokalnie** zatwierdzić:

```bash
nmcli --ask connection up vision-sony-a6100-wifi ifname <SONY_WIFI_IFACE>
```

Po odczytaniu adresu z `DHCP4.OPTION` sprawdzić `ping -I <SONY_WIFI_IFACE> <CAMERA_IP>` i trasę główną `ip -4 route get 1.1.1.1`. Nie hardkodować publicznie adresów aparatu ani sieci pracowni.

### 4.4 Bezpieczny odczyt Sony API (przykład protokołu)

```bash
curl --noproxy '*' --interface <SONY_WIFI_IFACE> --connect-timeout 3 --max-time 8 --header 'Content-Type: application/json' --data '{"method":"getAvailableApiList","params":[],"id":1,"version":"1.0"}' 'http://<CAMERA_IP>:10000/sony/camera'
```

Wynikiem oczekiwanym jest HTTP 200 i obiekt JSON z polem `result`. Na potrzeby kolejnych prób pytać także `getTemporarilyUnavailableApiList`, ale **nie wywoływać** `startLiveview`, `actTakePicture`, `actZoom` ani metod `set*` bez odrębnej akceptacji operatora.

## 5. Architektura docelowa — propozycja, bez wdrożenia

```text
Sony A6100 ── micro-HDMI → HDMI ── MacroSilicon UVC ── VENTUNO: Preview / QC / kadrowanie
         └── Wi-Fi Direct (Sony Camera Remote API) ──── VENTUNO: stan i polecenia
         └── USB/PTP [wcześniej sprawdzone] ──────────── zdjęcia 24 MP / RAW+JPEG
```

- **HDMI/UVC:** główny kandydat na płynny Live View; wymaga stabilnej sesji, detekcji gotowości i nadzoru jakości.
- **Wi-Fi API:** kandydat na sterowanie aparatem, odczyt parametrów i ewentualny zoom. Na razie potwierdzone **tylko** odczyty i lista metod.
- **USB/PTP:** osobny, wcześniej zweryfikowany tor wysokorozdzielczej akwizycji. **Współbieżne** HDMI + Wi-Fi + USB/PTP nie zostało jeszcze zweryfikowane.
- **Sygnały do planowania ruchu:** podgląd może wspierać ręczne pozycjonowanie i przyszłą logikę robota, ale nie jest safety-rated. Niezależne E-stop/interlocki i limity ruchu pozostają wymagane.
- **Warstwa adapterów:** zachować rozdział między `CameraPreview` (strumień), `CameraControl` (API), `StillCapture` (JPEG/RAW), `CameraHealth` (gotowość/timeout) a logiką aplikacji. To rekomendacja projektowa — nie opis istniejącego kodu.

## 6. Otwarte zagadnienia i warunki kolejnego etapu

| Obszar | Stan | Następny test |
|---|---|---|
| HDMI 1080p30 po rozgrzewce | **PASS w jednej 15-sekundowej sesji** | 10–20 cykli start/stop, pomiar rozkładu rozruchu i zakłóceń |
| HDMI 60 FPS | **NOT TESTED** | Rzeczywisty pomiar FPS/dropped frames |
| Opóźnienie podglądu HDMI | **NOT TESTED** | Znany sygnał świetlny, synchronizowany pomiar end-to-end |
| Utrata HDMI w ruchu | **NOT TESTED** | Odpięcie/przywrócenie sygnału przy jednej sesji UVC |
| Przyczyna pasów początkowych | **UNVERIFIED** | A/B z hostem, trybem źródła, kontrolerem USB i firmware grabbera |
| Wi-Fi Camera Remote API — odczyt | **PASS** | Odczyt dostępności i obsługa timeoutów bez zmian stanu |
| Wi-Fi Live View | **NOT TESTED** | Osobno `startLiveview`/`stopLiveview`, pomiar formatu/FPS/latencji |
| Sterowanie zdjęciem przez Wi-Fi | **NOT TESTED** | Jedna próba po akceptacji, walidacja lokalizacji i retencji zdjęcia |
| Zoom przez Wi-Fi | **NOT TESTED** | Test małego kroku z potwierdzeniem optycznym, tylko po akceptacji |
| Jednoczesne Wi-Fi + HDMI + PTP | **NOT TESTED** | Macierz współbieżności i konfliktów sesji |
| Stabilność sieci Wi-Fi | **PARTIAL** | Długotrwały ping/API, powtórna próba po reconnect, analiza zdublowanych ICMP |
| Dokumentacja/prototyp adaptera | **PLAN** | Projekt kontraktu i testy na mockach po decyzji |

## 7. Dowody, ślady i polityka retencji

- Wyniki `lsusb`, `v4l2-ctl`, `journalctl -k`, `nmcli`, `ping`, `curl` oraz analiza strumienia 450 klatek pochodziły z rzeczywistych sesji MCP na urządzeniu `vision` w dniu **2026-10-13**. W tej sesji nie tworzono pełnego archiwum logów na NVMe.
- Weryfikacja podglądu obejmowała **rzeczywiste odczytanie i obejrzenie klatek** z VENTUNO; nie opierano się wyłącznie na kodach wyjścia i istnieniu plików JPEG.
- Sprawdzenie działania Sony i grabbera na Windows 11 oraz przewodu z monitorem zgłosił **operator**. Nie było niezależnego pomiaru MCP na komputerze Windows.
- Pliki robocze `/dev/shm/vision-*` są efemeryczne; **nie publikować** ich w repo, ponieważ mogą ujawniać zawartość warsztatu i identyfikatory sprzętu.
- W trakcie ostatnich testów zdalnych nie zmieniano globalnych parametrów sieci, sterowników, kernela ani profilu USB runtime PM. Zmieniane były tylko **bieżące** formaty V4L2, przywrócone na MJPEG 1920×1080/30 FPS; profil Wi-Fi aktywował interaktywnie operator.
- Na etapie produkcyjnym każde zdjęcie/dowód wymaga osobnej polityki zapisu wyłącznie na NVMe, metadanych, sum kontrolnych, anonimizacji i retencji.

## 8. Wniosek końcowy

**Nie ma podstaw do wymiany grabbera.** Na VENTUNO rzeczywiście udało się uzyskać 1080p30 z Sony przez HDMI, po inicjalizacji trwającej w jednym doświadczeniu około 2,1 s. Niezależnie uruchomiono na drugim adapterze Wi-Fi połączenie Sony Camera Remote API; odczyt stanu i katalogu metod odpowiedział prawidłowo. Oba kanały są obiecującą bazą przyszłej aplikacji Vision, ale pomiary opóźnień, stabilność, współbieżność i polecenia zmieniające stan aparatu wymagają kolejnych oddzielnych testów.

**Powiązane źródła w repo:** [testy USB/PTP Sony](SONY_A6100_VERIFICATION_2026-10-10.md), [rejestr wcześniejszych dowodów](EVIDENCE_REGISTER_2026-10-10.md), [plan integracji](INTEGRATION_PLAN.md), [zasady pracy i publikacji](../process/DEVELOPMENT.md).
