# Luxonis OAK-D Pro AF — uruchomienie na VENTUNO Q i testy RGB-D

**Data:** 2026-11-10  
**Projekt:** Vision / kamera obserwacyjna nad stanowiskiem (overhead)  
**Status:** `HARDWARE_BRINGUP_PASS` / `RGB_DEPTH_SMOKE_PASS` / kalibracja stanowiska **jeszcze niewykonana**  
**Host:** VENTUNO Q, Ubuntu 24.04.4 LTS, ARM64 (aarch64), Python 3.12.3  
**Zakres:** sprawdzenie urządzenia, przygotowanie oprogramowania, poprawienie dostępu USB, uruchomienie RGB + stereo depth i zapis klatek diagnostycznych.

## 1. Identyfikacja i rezultat

- Model odczytany z fabrycznej kalibracji: **OAK-D-PRO-AF** (Luxonis, platforma RVC2 / Myriad X).
- Rewizja sprzętowa odczytana z kalibracji: **R9M2E9**.
- Po skonfigurowaniu dostępu USB: **jedno urządzenie DepthAI wykryte**, komunikacja działa.
- W trakcie uruchomionego pipeline: **`UsbSpeed.SUPER`** (USB 3.x).
- Fabryczna kalibracja **odczytana**, bez modyfikowania EEPROM, flashowania firmware ani rekalibracji.
- Działa równoczesny strumień RGB i `StereoDepth`, bez aktywacji emiterów IR.
- Końcowy wynik obu prób: `STREAM_PASS` / `SNAPSHOT_PASS`.

To jest potwierdzony **pierwszy test sprzętowy**, a nie akceptacja metrologiczna ani gotowość robota do autonomicznego ruchu.

## 2. Co dokładnie wykonano, żeby kamera ruszyła

### 2.1. Audyt przed uruchomieniem

Na hoście `vision` sprawdzono `lsusb`, `lsusb -t`, wersję systemu i dostępne kontrolery USB.

VENTUNO Q miał aktywny kontroler USB 3.0 (5 Gb/s); kamera **nie była jeszcze podłączona** podczas wstępnego audytu. Potwierdzono obecność Stream Deck Plus i interfejsu USB-CAN; nie zmieniano ich konfiguracji.

### 2.2. Izolowane środowisko Python na NVMe

Utworzono środowisko testowe (bez globalnej instalacji):

```bash
mkdir -p /srv/vision-data/staging/oak-overhead-v0
python3 -m venv /srv/vision-data/staging/oak-overhead-v0/venv
/srv/vision-data/staging/oak-overhead-v0/venv/bin/python -m pip install depthai
```

Potwierdzone pakiety:
- `depthai==3.12.0` na ARM64, import **PASS**;
- `numpy==2.5.4`;
- później do zapisu obrazów doinstalowano **tylko w tym venv** `opencv-python-headless==5.0.0.93`.

Przed podłączeniem DepthAI zgłaszał **0 dostępnych urządzeń** — zgodnie z oczekiwaniem.

### 2.3. Pierwsze podłączenie — wykryte ograniczenie uprawnień

Po fizycznym podłączeniu system wykrył `03e7:2485` (Movidius MyriadX) jako urządzenie na USB 2.0 / 480 Mb/s. Próba użycia DepthAI zwróciła:

```text
Insufficient permissions to communicate with X_LINK_UNBOOTED device
```

Węzeł `/dev/bus/usb/001/005` miał wtedy uprawnienia `root:root`, tryb `0664`. Wykrycie przez `lsusb` nie oznacza jeszcze dostępu przez DepthAI.

### 2.4. Naprawa uprawnień — wykonana przez operatora

Właściciel urządzenia, na podstawie przygotowanej instrukcji, uruchomił jednorazowo polecenie administracyjne:

```bash
printf '%s\n' 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", GROUP="users", MODE="0660"' | sudo tee /etc/udev/rules.d/80-movidius.rules >/dev/null && sudo udevadm control --reload-rules && sudo udevadm trigger --action=change --subsystem-match=usb --attr-match=idVendor=03e7 --settle
```

Reguła dotyczy wyłącznie urządzeń USB producenta `03e7`, przyznaje dostęp grupie `users`, do której należy użytkownik `arduino`. **Nie zastosowano** globalnego `chmod 666`, nie zmieniano reguł Sony, CAN ani Stream Deck Plus.

Po jej zastosowaniu węzeł miał `root:users`, `0660`; DepthAI zwrócił **1 urządzenie** i `DISCOVERY_PASS`.

### 2.5. Boot firmware i przejście na USB 3.x

Pierwsza właściwa sesja DepthAI uruchomiła firmware kamery i odczytała:

```text
Negotiated USB speed: UsbSpeed.SUPER
Calibration product: OAK-D-PRO-AF
Calibration revision: R9M2E9
```

Log jądra potwierdził przejście z `03e7:2485` (tryb nieuruchomiony, USB 2.0) na `03e7:f63b` (uruchomiony Luxonis, SuperSpeed), a po zamknięciu pipeline powrót do `03e7:2485`. **Widoczność 480 Mb/s przed uruchomieniem pipeline nie oznacza awarii kabla ani portu**. Docelową prędkość oceniamy w *aktywnej* sesji DepthAI.

## 3. Rzeczywiste wyniki pomiarów

| Próba | Wynik |
|---|---|
| Wykrywanie `DepthAI` | `1 device / PASS` |
| Prędkość w aktywnym pipeline | `UsbSpeed.SUPER` |
| Fabryczna kalibracja | odczyt OK, zapisów brak |
| RGB | **1280 × 720** |
| Mapa głębi | **1280 × 800**, wartości w mm |
| Czas testu strumieni | **12,03 s** |
| Liczba par klatek obsłużonych w pętli | **180** |
| Efektywna wydajność testu | **15,0 FPS** |
| Udział poprawnych wartości głębi w centralnym ROI (średnio) | **37,9%** |
| Mediana poprawnej głębi w ROI, ostatnia klatka | **2412 mm** |
| Udział poprawnych wartości głębi w pełnej klatce (jedna migawka diagnostyczna) | **19,9%** |
| Projektor IR / flood | **nieaktywowane** |
| Zakończenie procesów | **exit code 0 / PASS** |

W statystykach poprawnej głębi przyjęto wartości **1–4999 mm**. Wynik 15 FPS odzwierciedla obecną pętlę odbioru danych, **nie maksymalną liczbę FPS sensora**. Pokrycie głębi nie zostało jeszcze zoptymalizowane.

### Obraz referencyjny i ograniczenia

Pobrano pliki diagnostyczne **lokalnie na NVMe**:

```text
/srv/vision-data/staging/oak-overhead-v0/results/oak_rgb.jpg
/srv/vision-data/staging/oak-overhead-v0/results/oak_depth_preview.jpg
/srv/vision-data/staging/oak-overhead-v0/results/oak_depth_raw_mm.png
```

Obraz RGB jest czytelny, ale kamera była skierowana **ukośnie na scenę pomieszczenia**, a nie pionowo na pole robocze PCB/ECU. Na mapie głębi występują liczne obszary bez pomiaru; aktualna scena zawiera ciemne, jednorodne i odbijające światło powierzchnie. **Nie ma podstaw, aby na podstawie tej jednej sceny uznać kamerę za uszkodzoną albo precyzyjnie skalibrowaną.**

**Zdjęć nie dodano do publicznego repozytorium** — przedstawiają prywatne pomieszczenie i fragment sylwetki. Nie publikujemy też numeru seryjnego, prywatnych adresów ani binarnego zrzutu kalibracji.

## 4. Artefakty testowe na VENTUNO Q

Pozostawiono na hoście w katalogu `/srv/vision-data/staging/oak-overhead-v0/`:

- `venv/` — izolowane środowisko ARM64;
- `probe_oak.py` — wykrywanie, odczyt kalibracji i krótki test RGB + StereoDepth (`--capture --seconds 12`);
- `capture_diagnostic.py` — zapis RGB, kolorowanej mapy i surowej głębi 16-bit;
- `results/` — fotografie i surowa mapa głębi;
- `RESULT_2026-11-10.md` — pierwotny raport terenowy.

To **lokalne artefakty staging**, nie pliki dołączone do repozytorium. Nie było deploymentu, restartu usług Vision, zmiany `main`, uruchomienia NERO ani manipulowania fabryczną kalibracją.

## 5. Kolejne testy przed integracją z robotem

1. Zamontować kamerę sztywno, możliwie pionowo nad stołem; początkowo przetestować wysokość około **0,9–1,2 m** nad blatem. Zweryfikować wspólne pole obserwacji RGB i stereo oraz zakres MinZ.
2. Umieścić na stole matowy wzorzec / planszę o znanym wymiarze i na znanej wysokości; porównać błąd głębi w centrum i na obrzeżach.
3. Porównać ustawienia stereo (Left-Right Check, extended disparity, filtry) i pracę projektora/flood IR **OFF/ON** po weryfikacji zasilania oraz wpływu na drugą kamerę Eye-in-Hand.
4. Sprawdzić dłuższą stabilność USB 3.x, spadki klatek, obciążenie VENTUNO Q i parametry AF/ekspozycji.
5. Wykonać kalibrację `camera → table → NERO base` za pomocą wzorców/AprilTag; odróżnić dokładność wykrycia obrazu 2D od rzeczywistej dokładności pozycji XYZ.
6. Dopiero po weryfikacji jakości pomiarów zasilić danymi z kamery Vision Core. Kamera RGB-D **nie jest urządzeniem bezpieczeństwa** i nie zastępuje sprzętowego E-STOP, interlocków oraz kontroli kolizji.

## 6. Dokumentacja producenta

- [Luxonis OAK-D Pro — Hardware](https://docs.luxonis.com/hardware/products/OAK-D%20Pro)
- [Luxonis DepthAI — Documentation](https://docs.luxonis.com/software-v3/depthai/)
- [Luxonis — USB deployment](https://docs.luxonis.com/hardware/platform/deploy/usb-deployment-guide)
- [Luxonis — StereoDepth configuration](https://docs.luxonis.com/hardware/platform/depth/configuring-stereo-depth)

**Decyzja:** pierwszy etap uruchomienia kamery oznaczamy jako **PASS**. Moduł percepcji overhead pozostaje **DEV / NOT CALIBRATED / NO ROBOT ACTUATION**.
