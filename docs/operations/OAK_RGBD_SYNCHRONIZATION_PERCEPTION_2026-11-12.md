# Vision — RGB–Depth synchronization i eksperymentalna percepcja 3D

**Data:** 2026-11-12
**ADR:** ADR-VISION-ARCH-001 (ACCEPTED, PR #21, niescalony)
**Kod bazowy:** PR #20 (Camera Service, niescalony)
**Gałąź:** feature/oak-rgbd-sync-perception-v1-20261112
**Runtime produkcyjny:** niezmieniony, przywrócony po kontrolowanych próbach.

## 1. Zmiany

- Nowy moduł scripts/camera/oak/camera_sync.py: timestampy device monotonic i host monotonic (odrębne domeny), frame ID i sequence, parowanie do 20 ms, identyfikator sesji, liczniki utraconych/odrzuconych i przeterminowanych klatek, bounded queue.
- Rozszerzenie camera_service_prod.py: atomowy camera.frame_bundle.v1 z JPEG sprzętowym oraz stereo RAW16 mm, odczyt factory EEPROM tylko READ-ONLY; legacy API i profil balanced bez zmian.
- Wyszczególnienie układów rgb_optical i stereo_left_rectified_optical; RGB nie jest wyrównane do depth. Bez macierzy rectified-left i kalibracji stołu/NERO: robot_base = UNAVAILABLE.
- GET /api/status: status synchronizacji, pochodzenie kalibracji, statystyki; GET /api/frame-bundle/latest: spójne metadane lub HTTP 503; GET /snapshot/frame-bundle.npz: wyłącznie na żądanie, spójny, bezstratny JPEG + uint16 + metadata bez pickle.
- Schematy: contracts/camera.frame_bundle.v1.schema.json i contracts/perception.scene_observation.v1.schema.json.
- Zapis nie jest automatyczny. HTTP/NPZ to diagnostyka/replay, nie przyszły transport pełnej chmury 3D przy 30 FPS.

## 2. Korekta po pierwszym FAIL

Pierwsza próba (bufor 4, max pending 180 ms) dała jedynie 3 sparowane klatki przy ~29 FPS depth. W prawdziwym pipeline depth dociera na host później od odpowiadającego mu RGB. Różnica najnowszych timestampów device w chwilach jednakowego odbioru na hoście wynosiła 100–300 ms. Nie wolno dopasowywać na podstawie host arrival time.

Korekta: bufor max 16 pakietów na strumień, max pending 550 ms, max fresh pair 450 ms, tolerancja sparowania device ±20 ms. To jawnie ograniczone bufory; nie stanowią gwarancji czasu rzeczywistego ani sygnału bezpieczeństwa.

## 3. Test rzeczywisty na VENTUNO Q / OAK-D Pro AF

**Procedura:** pojedynczy właściciel USB; stop dotychczasowej jednostki; testowa kopia na localhost w tym samym profilu balanced; 26 pomiarów diagnostycznych; zapis i replay jednej rzeczywistej pary do prywatnego katalogu; zatrzymanie kopii; restart oryginalnej jednostki i health.

| Metryka | Bazowy prod przed | Kandydat testowy |
|---|---:|---:|
| RGB FPS | 30.0 | mediana 30.1 |
| Depth FPS | 29.2 | mediana 29.1 |
| USB | SUPER | SUPER |
| Temperatura chipu | 51.2°C | 51.2°C |
| RSS aplikacji | 975 MiB | 974 MiB |
| Sparowane klatki | brak funkcji | **745 / 746** odebranych depth |
| Status SYNCED | brak funkcji | **26 / 26** próbek |
| Delta device timestamps | brak funkcji | mediana **0.029 ms**; maksimum w próbkach **0.057 ms** |
| Lost sequence | bez porównania | RGB 1, depth 17 |
| Niesparowane / odrzucone | bez funkcji | RGB 17, depth 1 / rejected 0 |

**PASS:** dotychczasowe FPS i USB SUPER, atomowe sparowanie, uruchomienie i bezstratny replay prawdziwego JPEG 1920×1080 i RAW16 1280×800. Depth nonzero fraction 0.7942; archiwum 2 293 284 B. Utraconych sekwencji nie ignorujemy.

**PASS:** przywrócono oryginalny serwis bez zmiany plików produkcyjnych. Po ustabilizowaniu: ActiveState=active, NRestarts=0, 30.2 FPS RGB, 29.3 FPS Depth, USB SUPER, error=null.

**PENDING:** wielogodzinna stabilność; realny kabel USB unplug/replug; restart całego VENTUNO; rozkład p95/p99 sensor-to-host latency, utraty sekwencji pod obciążeniem. Żadnych komend ruchu NERO.

## 4. Perception Engine — oddzielny moduł offline

- scripts/perception/perception_engine.py: XYZ z piksel+depth uint16 mm w układzie stereo_left_rectified_optical (metry), próbkowana chmura punktów, RANSAC płaszczyzny, widoczne wymiary AABB, osiowy yaw z dwuznacznością 180°, OpenCV connected components, porównanie map głębi.
- Wyniki obiektów są oznaczone unknown_object i candidate_ecu=UNCONFIRMED; bez identyfikacji ECU, bez AI Luxonis, bez USB/DepthAI w Perception, bez GPU, bez NERO.
- Brak danych, niespójne strumienie, brak intrinsics lub przestarzały pomiar -> NOT_READY. Kalibracje stół/robot_base zawsze UNAVAILABLE.
- Intrinsics z factory EEPROM i rotacja rectification są dostępne, ale **K odpowiadająca wyjściu rectified-left nie została zweryfikowana**. Wartości realnego XYZ są wyłącznie eksploracyjne, nie metrologiczne, nie nadają się do prowadzenia ramienia.

**Prawdziwa próbka replay:** ~51 032 ważnych punktów przy stride=4; 79.7% ważnej głębi, płaszczyzna z udziałem ~66.6% inlierów i residual RMSE ~0.004 m. Znaleziono 8 regionów jako unknown_object (nie potwierdzono ECU). Jednorazowy czas obliczeń 0.074 s. Residual RMSE **nie** oznacza błędu metrologicznego. Jedna klatka **nie** dowodzi stabilnego FPS percepcji. Wynik: EXPLORATORY_UNVERIFIED_PROJECTION; table i robot_base UNAVAILABLE.

## 5. Testy i ograniczenia

Polecenie offline w istniejącym venv: python -m unittest discover -s tests -v

- Legacy Camera Service API: 6 PASS.
- Nowy API RGB-D i symulacja USB failure: 3 PASS.
- Parowanie, kolejki, utrata, sekwencje, replay: 9 PASS.
- Syntetyczna percepcja XYZ/plane/objects/change/stale: 8 PASS.
- **Razem: 26/26 PASS** na VENTUNO.

Prawdziwy plik RGB-D i pełne logi są wyłącznie w lokalnym /srv/vision-data/staging/oak-rgbd-live-evidence z ograniczonymi uprawnieniami, poza repo Git. W PR nie ma obrazów, IP, sekretów, modeli ani logów zawierających dane prywatne.

## 6. Kolejne bramki

1. Skalibrować i zweryfikować K dla wyjściowego rectified-left, wykonać pomiary fizycznego wzorca na stanowisku docelowym.
2. Zmierzyć długotrwałą pracę RGB-D z Perception; obciążenie, opóźnienia, gubienie ramek, kwantyle p95/p99. Ustalić rygorystyczne progi NOT_READY.
3. Zbenchmarkować ograniczony IPC/memory bus dla szybkiego odczytu bez drugiego właściciela USB. HTTP/NPZ ma pozostać narzędziem testowym.
4. Zweryfikować odłączenie USB i start po pełnym reboot; przetestować rollback.
5. Produkcyjne uruchomienie nowego kodu, PR merge i późniejsze integracje wymagają odrębnej zgody.

**Release gate:** PR do przeglądu. Nie scalać do main. Nie uruchamiać Vision Core, autonomii NERO, kamerowego AI ani ROS 2.
