# Vision — optyka / IR / autofocus / ROI / profile pracy

**Audyt:** 2026-11-13. **Decyzja:** ADR-VISION-ARCH-001 (ACCEPTED, PR #21). **Baza:** PR #22 (Camera Service PR #20).
**Status:** DEVELOPED OFFLINE / HARDWARE BLOCKED / PRODUCTION UNCHANGED.

## 1. Krytyczny bloker: OAK-D Pro AF nieobecna na USB

- VENTUNO Q jest dostępny, NVMe pracuje, ale nie ma obrazu i urządzenia Luxonis na magistrali.
- Read-only lsusb -t: tylko USB2 root-hub z Arduino gs_usb/CDC; brak OAK, brak dotychczasowego huba USB3.
- Systemd camera.service w pętli auto-restart: początkowy NRestarts=222; RuntimeError: No available devices na dai.Pipeline(). Ostatnie skuteczne starty z UsbSpeed.SUPER odnotowano 12 listopada o 16:52 i 16:54 UTC. W logach występują błędy braku sprzętu od 12 listopada ~17:30 UTC i ponownie dziś po uruchomieniu systemu.
- Błędy PCIe AER widoczne w kernel log, lecz ich relacja z USB NIE JEST POTWIERDZONA.
- Nie wykonano resetów PCIe, rebootów, zmian zasilania ani modyfikacji aktywnego katalogu Camera Service. Nie uruchomiono konkurencyjnego właściciela USB.
- Przed testem fizycznym: sprawdzić adapter zasilania kamery Y, przewód USB 3, połączenia i hub, następnie powtórzyć enumerację i health.

## 2. Zmiany w odizolowanym kodzie

### Optyka i geometria

Nowy moduł: scripts/camera/oak/camera_optics.py.
Pobiera z ImgFrame.getTransformation() macierz dla obrazu wynikowego getIntrinsicMatrix oraz macierz źródłową getSourceIntrinsicMatrix; sprawdza zgodność rozdzielczości, ogniskowe i elementy K. Osobne układy rgb_optical i stereo_left_rectified_optical. ID parametrów wersjonowane w metadanych. Perception nie może oznaczyć metrologii jako zweryfikowanej wyłącznie na podstawie zgłoszonego K; wynik pozostaje EXPLORATORY_UNVERIFIED_PROJECTION do walidacji na wzorcu. Table/robot_base zawsze UNAVAILABLE przed montażem.

### Zoom cyfrowy

Nowy endpoint wyłącznie na gałęzi rozwojowej: GET /snapshot/rgb-roi.jpg?x=0.25&y=0.25&w=0.5&h=0.5.
Wycinanie ROI z rzeczywistego JPEG (bez sztucznego zwiększania rozdzielczości). Jeden slot CPU dla JPEG ROI; zły input -> HTTP 400, utrata kamery/przeterminowane RGB -> HTTP 503; brak jakiegokolwiek wpływu na depth. Współrzędne optyczne źródłowego RGB nie są automatycznie wyrównane do stereo.

### IR i autofocus

Nowy moduł: scripts/camera/oak/camera_features.py.
Jawny opt-in pilot, poziom IR ograniczony 0..0.35, oba emitery 0 w finally (żądanie wyłączenia; nie oznacza sprzętowego ACK), test błędu drugiej komendy i wyłączenia pierwszej. Komendy do IR są wysyłane wyłącznie wewnątrz pojedynczego Camera Service, nie przez osobny proces.
Dai CameraControl AutoFocus AUTO, CONTINUOUS_VIDEO, MACRO, OFF działa na klasach zainstalowanego DepthAI 3.12.0 w testach offline. AF ROI mapowane na piksele sensora z macierzy odwrotnej ImgTransformation; bez prawidłowych metadanych brak wysłania ROI AF. Nie ma komend NERO.

### Profile (eksperymentalne, wyłącznie jawne uruchomienie)

| Profil | Akwizycja | IR dot/flood | AF/ROI |
|---|---|---|---|
| survey | balanced | 0/0 | bez zmiany |
| depth_precision | balanced | 15%/0 | bez zmiany |
| detail | detail | 0/0 | AF AUTO, centralny ROI, jeśli znana transformacja |
| low_light | balanced | 0/20% | bez zmiany |

Parametry są kandydatami, nie produkcyjną polityką. Jawny argument --pilot-profile do skryptu rozwojowego, profil rozdzielczości musi zgadzać się z --profile. Produkcyjny unit nie zawiera tego argumentu ani nie ładuje nowego skryptu.

## 3. Testy

13 listopada, VENTUNO Q: 39/39 PASS testów offline, compileall PASS, git diff --check PASS.
Wliczono 26 regresji Camera Service i Perception oraz 13 nowych testów macierzy wynikowej DepthAI, obsługi AF, wirtualnych komend IR, ROI i HTTP, ochrony przed starymi klatkami i błędnym inputem. Nie otwierano USB i nie publikowano obrazów.
Nowa funkcja jest oznaczona jako NIEPRZETESTOWANA na sprzęcie z powodu braku kamery.

## 4. Wcześniejsze A/B IR (12 listopada 2026)

Raport istnieje: docs/operations/OAK_IR_COMPARISON_2026-11-12.md w PR #20.
W rzeczywistej scenie sprzed awarii: IR dot 15% poprawił pokrycie prawidłowej głębi z ok. 73.6% do 75.1% (zysk 1.5 p.p.). Flood 20% nie poprawił całego obrazu. Nie jest to dowód poprawy dokładności XYZ na ECU. IR po teście wyłączone.

## 5. Bramka przed długim testem

1. Odzyskać sprzęt USB3 i stabilną aktywną usługę produkcyjną.
2. Sprawdzić per-frame K/rectified-left na rzeczywistej kamerze i zmierzyć odchyłki na znanym wzorcu na stanowisku.
3. W kontrolowanym, izolowanym teście pojedynczego właściciela OAK: IR OFF -> dot 15 -> flood 20 -> OFF, bez zapisu obrazu do publicznego GitHub.
4. AF i crop ROI, pomiary ostrości/FPS, rollback produkcyjnej jednostki.
5. Po zatwierdzeniu kryteriów: 2–3 godz. ciągłego RGB-D z obciążeniem Perception, FPS, capture age, dropout, CPU/RAM, temperatura i p50/p95/p99 latencji.

**Nie uruchomiono Vision Core, NERO, wbudowanego AI kamery, GPU Platform, ROS2. Nie zmieniono STOP/E-STOP ani repo main.**
