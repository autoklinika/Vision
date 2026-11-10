# VISION — Luxonis OAK-D Pro AF: raport zbiorczy uruchomienia, testów i ustaleń

**Stan na:** 10 listopada 2026  
**Projekt:** Vision / kamera obserwacyjna overhead / VENTUNO Q + AgileX NERO + Sony A6100  
**Urządzenie:** Luxonis OAK-D Pro AF, RVC2 / Intel Movidius Myriad X  
**Status:** `BRINGUP_PASS`, `RGB_PASS`, `STEREO_PASS`, `IR_CONTROL_PASS`, `ON_DEVICE_AI_PASS`, `180S_USB2_STRESS_PASS`; **`USB3_AI_IR_STABILITY_NOT_VERIFIED`**, **`NOT_CALIBRATED`**, **`NO_ROBOT_ACTUATION`**  
**Repozytorium:** `autoklinika/Vision`; dokument DEV, bez merge do `main`.

> **Cel dokumentu:** jedno źródło aktualnego stanu, które spina szczegółowe raporty i ustalenia z testów. Pomiary i logi historyczne zachowują swoją wartość, ale **najnowszy stan połączenia nie jest tożsamy ze stanem pierwszego uruchomienia**. Rozdzielamy potwierdzone pomiary, hipotezy i prace planowane. Poprzednie raporty pozostają niezmienionymi zapisami poszczególnych prób.

## 1. Decyzje projektowe i rola kamery

1. Utrzymujemy **DepthAI v3** jako SDK kamery; działająca, przetestowana baza na VENTUNO to **DepthAI 3.12.0** w osobnym Python venv. Nie migrujemy na DepthAI v2 ani nie piszemy własnych sterowników.
2. Kamera **overhead** będzie obserwować całe stanowisko z góry: ECU/PCB, geometrię sceny, pozycje przedmiotów i ruchy NERO. Nie ma jeszcze docelowej ramy ani stałego montażu.
3. **Sony A6100** pozostaje aparatem do zdjęć inspekcyjnych; osobna kamera Luxonis **Eye-in-Hand** na NERO służyć ma lokalnej percepcji. Dane muszą być łączone przez Vision Core, nie bezpośrednio przez niezweryfikowane komendy ruchu.
4. Projektowany układ: `OAK overhead → DepthAI Camera Service → Vision Core (mapa/XYZ/detekcje) → planer NERO`; rejestrowanie danych, replay i API dopiero do implementacji.
5. **OpenCV** do analizy i obróbki obrazu; **ROS 2** nie jest obecnie wymagany. AI może działać na VPU w OAK, a bardziej złożone modele na VENTUNO Q po ocenie wydajności.
6. Początkowe pole badanych PCB: **300 × 300 mm** — robocze założenie, a nie końcowy wymiar stanowiska. Wstępnie rozważana wysokość overhead **0,9–1,2 m od blatu** to punkt wyjścia do prób pola widzenia i MinZ, a nie zatwierdzony wymiar.
7. Kamera **nie jest czujnikiem bezpieczeństwa funkcjonalnego**. Sprzętowy E-STOP robota pozostaje niezależny; bez interlocków, kalibracji i testów skuteczności **zakaz automatycznego sterowania ruchem NERO na podstawie detekcji**.

## 2. Faktycznie wykonane uruchomienie

**Host:** VENTUNO Q, Ubuntu 24.04.4 LTS ARM64/aarch64, Python 3.12.3, dane użytkownika na NVMe `/srv/vision-data`.

Chronologia prac:

1. Sprawdzono `lsusb`, `lsusb -t`, kontroler USB3 5 Gb/s, dostępność hosta oraz działanie Stream Deck Plus i interfejsu USB-CAN NERO.
2. Utworzono izolowane środowisko `/srv/vision-data/staging/oak-overhead-v0/venv`; zainstalowano `depthai==3.12.0`, `numpy==2.5.4` i do diagnostycznego zapisu obrazów `opencv-python-headless==5.0.0.93`. Bez globalnego `pip install`.
3. Po podłączeniu kamera zgłosiła `03e7:2485`, ale DepthAI zwrócił `Insufficient permissions to communicate with X_LINK_UNBOOTED device`.
4. Właściciel urządzenia wdrożył regułę `/etc/udev/rules.d/80-movidius.rules` (dostęp grupy `users`, członkiem jest `arduino`):

   ```bash
   printf '%s\n' 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", GROUP="users", MODE="0660"' | sudo tee /etc/udev/rules.d/80-movidius.rules >/dev/null
   sudo udevadm control --reload-rules
   sudo udevadm trigger --action=change --subsystem-match=usb --attr-match=idVendor=03e7 --settle
   ```

   Potwierdzono `root:users` / `0660` oraz `DISCOVERY_PASS` — kamera wykrywana przez DepthAI bez `sudo`.
5. Aktywny pipeline uruchomił firmware i osiągnął `UsbSpeed.SUPER` (USB3). Odczytana kalibracja: `productName=OAK-D-PRO-AF`, `boardRev=R9M2E9`. Nie zapisano danych do EEPROM.
6. Pierwszy test RGB + StereoDepth zakończył się `STREAM_PASS`, test zapisu diagnostycznych obrazów `SNAPSHOT_PASS`. Obrazy pozostały tylko na prywatnym NVMe, nie zostały opublikowane.

**Ważne:** w trybie *unbooted* po zamknięciu pipeline kamera może być widoczna jako USB2 `03e7:2485`. Prędkość `HIGH` jest problemem **dopiero wtedy**, gdy występuje w *aktywnym* pipeline `03e7:f63b`. Przejście między tymi identyfikatorami jest typowym cyklem start/stop i samo w sobie nie świadczy o awarii.

## 3. Zbiorcza matryca wykonanych testów

| Etap / warunki | Główne wyniki | Ocena |
|---|---|---|
| Podłączenie USB + DepthAI | `1 device`, dostęp `root:users/0660`; aktywne `UsbSpeed.SUPER` | **PASS** |
| Odczyt kalibracji | `OAK-D-PRO-AF`, `R9M2E9`, bez zapisu EEPROM | **PASS** |
| RGB + StereoDepth, IR OFF, USB3 | RGB `1280×720`; depth `1280×800`; 180 par klatek / 12,03 s = **15,00 FPS**; średnie poprawne centrum **37,9%** | **PASS** funkcjonalny |
| Zapis jednej klatki | RGB, kolorowana głębia i 16-bit głębia mm; pełny kadr **19,9%** poprawnych pikseli | **PASS** funkcjonalny |
| YOLOv6 Nano (RVC2), sam NN, USB3 | 427 wyników w 20,04 s = **21,31 wyników/s**; model COCO 80 klas | **PASS** inferencji |
| YOLOv6 Nano + StereoDepth, USB3, IR OFF | 223 pary wyników w 15,04 s = **14,83 par/s**; 20,0% poprawnej głębi pełnego kadru | **PASS** |
| StereoDepth + IR, bez AI, USB3 | Projektor IR 15%: **48,39%** poprawnej głębi vs **18,69%** dla początkowego OFF, ok. 16 FPS | **PASS** sterowania i pomiaru |
| AI + stereo + IR 15%, USB3, poprzednie zasilanie | `X_LINK_ERROR`, watchdog utracił łączność, nastąpiło rozłączenie i ponowna enumeracja USB | **FAIL**, przyczyna nieustalona |
| AI + StereoDepth USB3, IR OFF — kontrola | 30 s, **447** depth (14,90 FPS), **577** NN (19,23/s); chip **46,4°C** | **PASS** (30 s) |
| Osobne zasilanie i fabryczny adapter Y, nowy tor danych | Aktywna kamera **`UsbSpeed.HIGH` (USB2)**; nie powraca do SuperSpeed | **BLOCKER USB3** |
| AI + stereo + IR w 6 konfiguracjach, aktywne USB2 | 6 × 8 s; **ok. 12 FPS**; bez `X_LINK_ERROR` | **PASS** (krótko, USB2) |
| AI + stereo + dot IR 15%, aktywne USB2 | 180 s: **2226** depth = **12,37 FPS**, **2269** NN = **12,61 wyników/s**; 47,31% pełny kadr i 65,84% centrum; chip **52,6°C** końcowo; exit 0 | **PASS** (3 min, USB2) |
| Długi stres USB3 + AI + stereo + IR | Nie wykonany w nowej konfiguracji zasilania i przewodu danych | **PENDING** |

**Sposób interpretacji:** `FPS` oznacza liczbę odebranych pakietów/klatek na sekundę przez konkretny skrypt, a nie nominalny maksymalny FPS kamer ani szczytową moc VPU. Wartości procentowe to udział pikseli o głębi **1–4999 mm**, nie procent dokładnych pomiarów. Scena nie była nieruchomym wzorcem kalibracyjnym; porównania IR nie dają jeszcze błędu metrologicznego. Liczba detekcji sumuje obserwacje z kolejnych klatek, nie unikalne obiekty.

## 4. IR / stereo — szczegółowe ustalenia

Odczyt sprzętowy `getIrDrivers()` zwrócił `LM3644`, a oba polecenia: `setIrLaserDotProjectorIntensity` i `setIrFloodLightIntensity` potwierdziły dostępność emiterów. Testowano dot projector do 30%, flood 20%, oba 20% oraz konfiguracje OFF.

### StereoDepth bez AI, na USB3 (6 s/faza)

| IR | Poprawny pełny kadr | Poprawne centrum | Stereo FPS |
|---|---:|---:|---:|
| OFF początek | 18,69% | 24,01% | 15,83 |
| Dot 15% | **48,39%** | **60,97%** | 16,00 |
| Dot 30% | 44,64% | 54,12% | 16,00 |
| Flood 20% | 20,25% | 26,47% | 16,00 |
| Dot 20% + flood 20% | 20,55% | 26,73% | 15,83 |
| OFF koniec | 20,17% | 26,93% | 15,83 |

Dot projector w tej próbie wyraźnie zwiększał liczbę poprawnych pikseli głębi. **Nie zatwierdzono** nastawy 15% jako ostatecznej: inna scena i inne zasilanie przyniosły inne wyniki dla 30% oraz kombinacji dot+flood. Flood przy tej scenie nie dawał porównywalnej samodzielnej korzyści.

### AI + StereoDepth + IR po dołączeniu niezależnego zasilania, aktywne USB2 (8 s/faza)

| IR | Stereo FPS | AI wyników/s | Poprawny pełny kadr | Temperatura chip |
|---|---:|---:|---:|---:|
| OFF początek | 12,12 | 12,12 | 23,80% | 40,6°C |
| Dot 15% | 12,00 | 12,00 | 46,19% | 42,0°C |
| Dot 30% | 12,12 | 12,00 | 49,09% | 42,8°C |
| Flood 20% | 11,87 | 11,87 | 25,07% | 42,8°C |
| Dot 20% + flood 20% | 12,00 | 12,12 | 48,74% | 43,6°C |
| OFF koniec | 12,00 | 11,87 | 24,50% | 44,6°C |

W obu seriach: w pełni kontrolowane programowo emitery i stereo działają; dokładność głębi względem rzeczywistej odległości oraz powtarzalność na PCB **nie zostały zbadane**.

## 5. AI uruchomione wewnątrz OAK

- Model: **Luxonis Model Zoo / YOLOv6 Nano**, wersja dla **RVC2**, archiwum `YOLOv6_Nano-R2_COCO_512x384.rvc2.tar.xz`, format `SUPERBLOB`.
- `dai.node.DetectionNetwork` wykonuje inferencję i parsowanie detekcji na kamerze; host VENTUNO odbiera i zlicza wyniki. Nie obciążano CPU hosta inferencją tego NN.
- Model ma **80 klas COCO**, więc jest modelem demonstracyjnym. Zgłoszenia klasy `tv` podczas próby są **niezweryfikowane względem etykiet referencyjnych**; nie dowodzą rozpoznawania ECU/PCB.
- Do detekcji PCB, modułów ECU, złączy i narzędzi potrzebujemy własnego zbioru uczącego, oceny precyzji i wyeksportowanego modelu dla RVC2.
- 21,31 wyników/s w teście samego NN na USB3 i ~12,61 wyników/s w pełnym teście USB2 **nie mogą być interpretowane jako czysty spadek wydajności Myriad X**: zmieniono pipeline, liczbę strumieni i połączenie USB.

## 6. Zasilanie i przewody — stan, problem, decyzja

**Potwierdzone przez użytkownika:**
- Kamera początkowo pracowała przez **hub TP-Link UH720 z własnym zasilaniem sieciowym**.
- Następnie podłączono **osobne zasilanie kamery przez fabryczny adapter Y USB-C Luxonis**, dostarczony w zestawie.
- Między **adapterem Y (DATA) a hubem** zastosowano **inny przewód USB-C → USB-A**, niewchodzący w skład zestawu. Użytkownik zaobserwował **białe wnętrze złącza USB-A**.
- Specyfikacja elektryczna osobnego zasilacza i rzeczywista klasa kabla nie zostały odczytane ani zmierzone.

**Potwierdzone pomiarami:**
- Przed zmianą toru zasilania/danych aktywne DepthAI potrafiło negocjować `UsbSpeed.SUPER` (USB3, 5 Gb/s).
- Po dodaniu fabrycznego Y-adaptera, zasilania niezależnego i innego kabla DATA, **aktywny** pipeline był na `UsbSpeed.HIGH` (USB2, 480 Mb/s), również po załadowaniu firmware.
- Konfiguracja USB2 przechodzi obecnie krótkie i trzyminutowe próby AI+StereoDepth+IR bez `X_LINK_ERROR`, ale **nie dowodzi stabilności przy pełnym USB3**.
- Wcześniejszy błąd USB3 + AI + IR nie zawierał dowodu przegrzania ani jednoznacznego komunikatu o zbyt niskim napięciu. Hipoteza przeciążenia zasilania nie została potwierdzona pomiarem.

**Ustalenie zakupowe i instalacyjne:**
- Fabryczny adapter Y **zostaje**. Luxonis przewiduje w nim złącze USB-C **DATA** do hosta i osobne USB-C **POWER 5 V**; dla OAK Pro zaleca źródło **15 W lub więcej** (wymagana weryfikacja tabliczki zasilacza). Patrz dokumenty producenta niżej.
- Kupujemy **przewód transmisyjny USB-C → USB-A z jednoznaczną specyfikacją USB 3.x SuperSpeed ≥5 Gb/s**, nie kabel deklarowany wyłącznie jako ładujący. Kolor białego plastiku w USB-A jest wskazówką, **nie niezawodnym identyfikatorem standardu**. Weryfikacja: `UsbSpeed.SUPER` w aktywnym pipeline i `lsusb -t` na gałęzi 5000M.
- Dla prostego pasywnego kabla preferujemy **1–2 m** dobrej jakości. Producent ostrzega, że przy kablach **dłuższych niż ok. 2 m** mogą wystąpić problemy; dłuższą trasę rozwiązać **aktywnym USB3**, dopasowanym do planowanego prowadzenia kabli i dopiero potem sprawdzonym na stanowisku.
- **Nie określono jeszcze docelowej długości** pomiędzy kamerą overhead a VENTUNO Q; 5 m aktywnego przewodu to **wariant do rozważenia**, a nie zamówiony/zatwierdzony element.
- Przed następnym stress-testem trzeba wykluczyć kabel z ograniczeniem do USB2. Nie wymieniać na ślepo sprawnego Y-adaptera ani nie przestawiać innych urządzeń na hubie.

## 7. Incydent USB3: dowody i granice rozpoznania

Przy wcześniejszej próbie USB3 z jednoczesnym YOLOv6 Nano, StereoDepth i projektorem IR 15% wystąpił `X_LINK_ERROR` na strumieniach, zatrzymał się watchdog, urządzenie zniknęło z magistrali SuperSpeed i ponownie się enumerowało; kod wyjścia testu 1. Temperatura w poprzedzającej fazie była około **44°C**, bez dowodu problemu termicznego. Po utracie komunikacji wysłanie komendy wyłączenia emiterów w `finally` nie powiodło się, bo urządzenie było rozłączone; po ponownym uruchomieniu wróciło do stanu domyślnego IR OFF.

**Wniosek:** wcześniejszej awarii nie przypisujemy bez dowodów wyłącznie hubowi, zasilaczowi, kablowi ani firmware. Konfiguracja z osobnym zasilaniem **przeszła test tylko przy USB2**, a nie przy początkowym USB3. Warunek zamknięcia tej usterki to **powtarzalny test AI+StereoDepth+IR na USB3**.

## 8. Temperatura i test obciążenia USB2

Próba nieprzerwana: **180 s**, jednocześnie YOLOv6 Nano (RVC2), StereoDepth 1280×800 i projektor dot 15%:

| Metryka | Odczyt |
|---|---:|
| Interfejs | `UsbSpeed.HIGH`, USB2 |
| Odebrane klatki stereo | **2226** |
| Średnia efektywna wydajność stereo | **12,37 FPS** |
| Wyniki AI / średnio | **2269 / 12,61/s** |
| Udział poprawnych pikseli głębi w całym obrazie | **47,31%** |
| Udział poprawnych pikseli głębi w centrum | **65,84%** |
| Mediana poprawnej głębi centrum | **2364 mm** |
| Temperatura po 15 s / 60 s / 120 s / 180 s | **44,9 / 47,5 / 49,9 / 52,6°C** |
| `X_LINK_ERROR` w oknie próby | **brak** |
| Wyjście skryptu | **0** |
| Zakończenie IR | `DOT_OFF=True`, `FLOOD_OFF=True` |

Ustawiony w skrypcie próg przerwania **65°C** był **wewnętrznym progiem testowym**, a nie deklarowaną granicą bezpieczeństwa producenta. Temperatura wciąż rosła przy końcu pomiaru — nie potwierdzono stanu ustalonego, więc nie oznaczamy testu jako wielogodzinnej stabilności.

## 9. Repo, lokalne artefakty i odtwarzalność

### Wcześniejsze raporty szczegółowe
- [Pierwsze uruchomienie — udev, USB3, kalibracja, RGB-D](OAK_D_PRO_AF_BRINGUP_2026-11-10.md)
- [Wbudowane AI — model RVC2, wyniki NN i NN+stereo](OAK_D_PRO_AF_AI_TEST_2026-11-10.md)
- [IR / stereo / AI — porównania i wcześniejszy X_LINK_ERROR](OAK_D_PRO_AF_IR_STEREO_AI_2026-11-10.md)
- [Osobne zasilanie — 6 faz + test 180 s na USB2](OAK_D_PRO_AF_EXTERNAL_POWER_STRESS_2026-11-10.md)

### Skrypty źródłowe w repo (gałąź DEV)
- [YOLOv6 Nano RVC2 — test AI](../../scripts/camera/oak/test_rvc2_ai.py)
- [YOLOv6 Nano RVC2 + stereo](../../scripts/camera/oak/test_rvc2_ai_stereo.py)
- [Benchmark IR / stereo / AI, pomiar temperatury i kontrola połączenia](../../scripts/camera/oak/ir_stereo_ai_benchmark.py)

### Dane wyłącznie na VENTUNO Q / NVMe
- `/srv/vision-data/staging/oak-overhead-v0/venv/`
- `/srv/vision-data/staging/oak-overhead-v0/probe_oak.py`
- `/srv/vision-data/staging/oak-overhead-v0/capture_diagnostic.py`
- `/srv/vision-data/staging/oak-overhead-v0/results/` (zdjęcia RGB i wizualizacje głębi, surowa mapa głębi)
- `/srv/vision-data/staging/oak-overhead-v0/IR_AI_EXTERNAL_POWER_SHORT_20261110.log`
- `/srv/vision-data/staging/oak-overhead-v0/IR_AI_EXTERNAL_POWER_SOAK_20261110.log`
- Raporty `RESULT_*.md` w tym samym katalogu.

**Repozytorium jest publiczne:** nie publikujemy zdjęć pomieszczenia, wizerunków ludzi, pełnych logów z numerem seryjnym kamery, danych sieciowych ani surowego EEPROM. W repo pozostają jedynie oczyszczone wyniki i kod diagnostyczny. Zmiany bez merge do `main`, usługi produkcyjne Vision niezmienione.

## 10. Lista dalszych prac i kryteria akceptacji

| Priorytet | Zadanie | Warunek ukończenia |
|---|---|---|
| **P0** | Nowy przewód DATA **USB3 5 Gb/s** do fabrycznego Y-adaptera | `UsbSpeed.SUPER` i 5000M w **aktywnym** pipeline |
| **P0** | Stres AI+StereoDepth+dot 15% z niezależnym zasilaniem na USB3 | Co najmniej 180 s bez `X_LINK_ERROR` / restartu USB; temperatura i FPS zapisane |
| **P1** | Kontrolny powtarzalny test IR OFF/15%/30% na statycznym wzorcu | Głębia: pokrycie, błąd mm, rozrzut i powtarzalność, osobno w centrum i na obrzeżach |
| **P1** | Dłuższy soak na USB3 z rejestracją temperatury i utraty pakietów | Udokumentowany przebieg, brak resetów i termicznych alarmów; bez uznawania progu 65°C za wartość producenta |
| **P1** | Stabilny Camera Service dla Vision Core | Obsługa restartu USB, jawne statusy, znacznik czasu, zasady fail-closed |
| **P2** | Rejestrowanie i odtwarzanie danych DepthAI | Powtarzalne offline testy algorytmów bez robota |
| **P2** | Detekcja/śledzenie obiektów, specjalizacja PCB/ECU | Model RVC2 z metrykami jakości na oznaczonym zbiorze |
| **P2** | Wstępna kalibracja AprilTag / znane odległości | Pomiary XYZ z błędem mm, bez końcowej transformacji NERO |
| **Po montażu** | Docelowa geometria overhead–stół–podstawa NERO | Zweryfikowana transformacja, pole widzenia i strefy kolizyjne; osobna zgoda na integrację z ruchem |

## 11. Źródła producenta

- [Luxonis — OAK-D Pro, parametry i zasilanie](https://docs.luxonis.com/hardware/products/OAK-D%20Pro)
- [Luxonis — Y-Adapter (DATA / 5 V POWER)](https://docs.luxonis.com/hardware/products/Y-Adapter)
- [Luxonis — USB deployment guide (USB3, przewody, problemy, udev)](https://docs.luxonis.com/hardware/platform/deploy/usb-deployment-guide)
- [Luxonis — DepthAI v3](https://docs.luxonis.com/software-v3/depthai/)
- [Luxonis — Stereo depth](https://docs.luxonis.com/hardware/platform/depth/configuring-stereo-depth)

---

**Decyzja końcowa na 2026-11-10:** **DepthAI v3 zostaje**. OAK-D Pro AF ma funkcjonalne RGB, StereoDepth, IR i AI na Myriad X; odnotowano poprawny 180-sekundowy stres przy niezależnym zasilaniu **na USB2**, ale **brakuje powtórzenia pełnego obciążenia na USB3**. Zakup i test przewodu USB3 DATA są najbliższym krokiem sprzętowym. Kamera overhead pozostaje **DEV** do czasu stałego montażu, kalibracji i osobnej akceptacji integracji z Vision Core/NERO.
