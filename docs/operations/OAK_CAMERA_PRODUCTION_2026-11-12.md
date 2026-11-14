# Vision — produkcyjny Camera Service OAK-D Pro AF (bez wbudowanego AI)

**Stan i pomiary:** 2026-11-12. **Status:** `PRODUCTION_RUNTIME_ACTIVE / RGB_DEPTH_HARDWARE_PASS / BOOT_AUTOSTART_NOT_YET_TESTED / CALIBRATION_PENDING`.

## 1. Rola i architektura

Samodzielna usługa akwizycji RGB i StereoDepth na VENTUNO Q, **jeden właściciel USB**. Kamera Luxonis OAK-D Pro AF (RVC2 / Myriad X); SDK DepthAI 3.12.0, OpenCV Headless 5.0.0.93, NumPy 2.5.4. Wariant **bez DetectionNetwork, NN, IR i bez komend dla NERO**. Model AI pozostaje wyłączony. Sprzętowy VideoEncoder MJPEG koduje strumień RGB bez przetwarzania JPEG na CPU hosta. Pełna głębia RAW16 [mm] pozostaje w RAM na potrzeby późniejszej kalibracji i integracji.

Produkt: usługa użytkownika `vision-oak-camera.service` (systemd --user jako `arduino`, konto ma `Linger=yes`), wdrożona niezależnie od testowego podglądu DEV i terminala. Katalog na NVMe:

- `/srv/vision-data/tools/vision-camera-service/camera_service_prod.py` — backend.
- `camera_service_prod.html` — interfejs WWW.
- `venv/` — izolowane zależności produkcyjne.
- `camera.env` — lokalne ustawienia, uprawnienia `0600`; **nie publikować**, zawiera wewnętrzny adres interfejsu Tailscale.
- `/home/arduino/.config/systemd/user/vision-oak-camera.service` — jednostka autostartu, z szablonem w `ops/camera/`.

Dysk `/srv/vision-data` musi być zamontowany. `ExecStartPre=/usr/bin/mountpoint -q /srv/vision-data` oraz ponawianie startu `Restart=always; RestartSec=15s`. Usługa jest **enabled** i **active**; po restarcie samej usługi pomyślnie wznowiła strumienie. Test po **pełnym restarcie systemu** jeszcze nie był wykonany z nową usługą.

## 2. Profile jakości i wydajności

| Profil | RGB | Głębia stereo | Tryb | Weryfikacja |
|---|---|---|---|---|
| **balanced** — domyślny | 1920×1080, ~30 FPS, MJPEG on-device | 1280×800, ~29 FPS, RAW16 mm | Stereo LR-check ON, extended disparity OFF | **HARDWARE PASS** |
| **detail** | 3840×2160, ~20 FPS, MJPEG on-device | 1280×800, ~20 FPS | Stereo LR-check ON, extended disparity OFF | **HARDWARE PASS** |
| **near** — eksperymentalny | 1920×1080, zadane 15 FPS | 1280×800, zadane 15 FPS | Extended disparity ON (krótszy minimalny dystans, mniejsza wydajność) | **NOT VALIDATED IN PROD** |

Pomiary ze sceny laboratoryjnej w krótkich oknach. `balanced` po wydzieleniu wątku wizualizacji podawał około 30,0 FPS RGB i 28,7–29,4 FPS głębi; proces zużywał około 1–2 rdzeni CPU w notacji `ps`, RSS około 1 GB. Temperatura układu OAK około 47–51°C podczas wykonanych prób. `detail` przekazał przez Tailscale rzeczywisty plik JPEG 3840×2160; obrazy lokalnie nie są archiwizowane.

Profil zmienia administrator przez `VISION_PROFILE=balanced|detail|near` w lokalnym `camera.env` i restart jednostki. W WWW nie ma endpointu zmieniającego stan kamery. Wyłączenie `extended disparity` w profilu `balanced` podniosło rzeczywistą wydajność głębi przy obecnej scenie względem poprzedniego trybu ~15 FPS, **ale nie oznacza poprawy dokładności pomiarowej**.

## 3. API i kontrakt danych

| Endpoint GET | Funkcja |
|---|---|
| `/` | WWW podglądu technicznego i parametrów |
| `/healthz` | HTTP 200/503, bramka dostępności |
| `/api/status` | JSON: profil, rozdzielczości, FPS, USB, temperatura, procent poprawnych pikseli, wiek klatek, status |
| `/stream/rgb.mjpg` | kodowany sprzętowo strumień RGB MJPEG |
| `/stream/depth.mjpg` | kolorowany obraz głębi 640×400, renderowanie niezależne od akwizycji |
| `/snapshot/rgb.jpg` | ostatni JPEG pełnej rozdzielczości |
| `/snapshot/depth-mm.png` | ostatnia pełna mapa głębi **16-bit PNG 1280×800**, milimetry |

W pamięci utrzymuje się tylko bieżące klatki, bez zapisu obrazów, logów sesji ze zdjęciami czy wysyłania ich do chmury. Dwa strumienie i oba rodzaje snapshotu sprawdzono z drugiego komputera (AI Platform) przez Tailscale. Plik głębi zidentyfikowany jako 16-bit grayscale 1280×800. Maksymalnie 10 jednoczesnych strumieni HTTP, aby ograniczyć niekontrolowane obciążenie.

**Granice:** surowa głębia ma układ współrzędnych kamery, jest odnoszona do rectified-left i **nie ma jeszcze kalibracji względem blatu ani ramienia NERO**. `depth_valid_pct` oznacza odsetek pikseli 1–4999 mm, nie deklarowaną dokładność. Kamera nie jest czujnikiem bezpieczeństwa funkcjonalnego i nie zastępuje niezależnego E-STOP.

## 4. Dostęp i bezpieczeństwo

Serwer HTTP nasłuchuje wyłącznie na prywatnym IP interfejsu Tailscale Vision, którego wartość pozostaje w `camera.env`. Zalecany adres przy działającym MagicDNS: `http://vision:18092/`. **Brak uwierzytelniania na poziomie aplikacji** — dostęp kontrolować tailnet ACL oraz bezpieczeństwem urządzeń. **Nie wystawiać portu 18092 do Internetu ani nie ustawiać bind 0.0.0.0**. Połączenie HTTP nie posiada własnego TLS; Tailscale chroni tunel transportowy między węzłami.

Usługa nie uruchamia innych usług Vision, nie wydaje komend robotowi, nie zapisuje ustawień do EEPROM, nie zmienia kalibracji fabrycznej ani nie aktywuje IR. Blokada `flock` chroni przed równoległym startem naszego poprzedniego podglądu DEV, lecz inne niezależne skrypty DepthAI nie współdzielą jej automatycznie — należy **zatrzymać usługę przed eksperymentami z kamerą**.

## 5. Obsługa i rollback

Na VENTUNO Q jako `arduino`:

```bash
systemctl --user status vision-oak-camera.service --no-pager
systemctl --user restart vision-oak-camera.service
journalctl --user -u vision-oak-camera.service -n 60 --no-pager
```

Zatrzymanie na potrzeby testów / rollback bez usuwania zdjęć, sesji i oprogramowania:

```bash
systemctl --user stop vision-oak-camera.service
```

Wycofanie autostartu:

```bash
systemctl --user disable --now vision-oak-camera.service
```

Usługa zawsze wymaga prawidłowego montowania NVMe oraz aktywnej transmisji USB3 `UsbSpeed.SUPER`. W razie jego braku kończy się błędem i jest ponawiana przez systemd co 15 sekund. Brak zapisu na niezamontowany NVMe; logi usługi trafiają do systemd journal.

## 6. Wykonane testy / otwarte kryteria

- **PASS**: kompilacja Python i 6/6 testów offline (stan, endpointy, błędy, klienci MJPEG, RAW16 PNG).
- **PASS**: fizyczny pipeline DepthAI 3.12.0 / OAK-D Pro AF z aktywnym USB3 `SUPER`, RGB i StereoDepth równocześnie.
- **PASS**: 1080p30 + 800p~29, 4K20 + 800p~20, zewnętrzny odczyt JPEG o właściwych wymiarach.
- **PASS**: `systemctl --user enable --now`, późniejszy kontrolowany restart usługi, ponowny start USB i `/healthz` HTTP 200.
- **NOT YET TESTED**: pełny restart VENTUNO z nową usługą, stabilność wielogodzinna, realne odłączenie USB i automatyczne odzyskiwanie po nim, profil `near`, sterowanie AF/ekspozycją, integracja z Vision Core i metrologiczna kalibracja stołu/ramienia.
- **NOT DONE**: wbudowane AI, IR, detekcja ECU, ruch NERO, obsługa E-STOP przez kamerę. Te funkcje nie są częścią bieżącego Camera Service.

**Repozytorium:** nowy moduł na oddzielnej gałęzi `feature/oak-camera-service-production-20261112`; produkcyjny runtime uruchomiono bez scalania do stabilnego `main`. Zgodnie z polityką projektu merge wymaga osobnej zgody właściciela.
