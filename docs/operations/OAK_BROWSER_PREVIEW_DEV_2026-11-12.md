# Vision — podgląd RGB + głębia OAK-D Pro AF w przeglądarce (DEV)

**Data:** 2026-11-12  
**Status:** `HARDWARE_RGB_DEPTH_PASS / TAILSCALE_HTTP_PASS / SHORT_STABILITY_PASS / NOT_PRODUCTION`  
**Zakres:** oddzielny, tylko do odczytu serwer HTTP/MJPEG dla Luxonis OAK-D Pro AF (overhead), host VENTUNO Q. Nie jest to aplikacja Vision Core ani sterowanie robotem.

## Funkcje

- Jedna sesja DepthAI v3 jest właścicielem kamery; dwa obrazy MJPEG (RGB 640×360 i kolorowana mapa głębi 640×400) są udostępniane wielu klientom HTTP bez otwierania USB przez każdą kartę przeglądarki.
- `GET /` — jasny panel WWW, `GET /stream/rgb.mjpg`, `GET /stream/depth.mjpg`, `GET /api/status`.
- Status zawiera bieżącą komunikację USB, szacunkowe FPS, udział pikseli głębi 200–4999 mm, świeżość klatek oraz błąd urządzenia.
- Strumienie zostają zatrzymane, jeśli kamera przestaje dostarczać klatki; błędy i brak urządzenia nie są pokazywane jako sprawny obraz.
- Brak zapisu klatek, brak połączenia z chmurą, brak NN, brak wykonywania poleceń robota, brak ustawiania IR, brak modyfikacji kalibracji i EEPROM.
- To **nie** jest funkcja bezpieczeństwa. OAK nie zastępuje E-STOP i interlocków.

## Ograniczenia

1. Kod wymaga sprawdzenia **na rzeczywistym VENTUNO Q**: w szczególności API DepthAI 3.12.0, USB2/USB3, długiej stabilności i obciążenia CPU. Samo przejście testów offline nie jest testem sprzętowym.
2. Kamera jest zasobem wyłącznym. Przed uruchomieniem podglądu należy zakończyć pozostałe eksperymenty DepthAI. Nie zabijać działających procesów automatycznie.
3. Stereo 3D i mapa odległości nie są skalibrowane do blatu ani układu NERO. Kolory odpowiadają tylko wizualizacji zakresu 0,2–5 m.
4. Przy USB2 obciążenie łącza ogranicza wydajność; serwer nie uruchamia w tym trybie modelu YOLOv6 Nano ani IR. Nie zakładać stałych 12 FPS bez pomiaru.
5. HTTP **nie ma uwierzytelniania ani TLS**. Domyślnie nasłuchuje **wyłącznie 127.0.0.1**. Do podglądu z Windows zalecane jest jawne związanie z adresem **Tailscale** i ograniczenie dostępu regułami tailnet ACL; **nie używać `--bind 0.0.0.0`** na otwartej sieci.
6. Nie instalowano usługi systemd. Start jest ręczny; stop `Ctrl+C`; żadnego automatycznego uruchamiania kamery przy starcie hosta.

## Procedura testowego uruchomienia na Vision

Nie modyfikować aktualnego checkoutu produkcyjnego. Utworzyć osobny katalog:

```bash
git clone --depth 1 --branch feature/oak-browser-preview-20261112 \
  https://github.com/autoklinika/Vision.git \
  /srv/vision-data/staging/oak-browser-preview-dev
cd /srv/vision-data/staging/oak-browser-preview-dev
python3 -m unittest discover -s tests -p test_oak_browser_preview.py -v
```

Przed testem obrazu zweryfikować brak innego właściciela OAK i stan USB. Istniejący izolowany Python z poprzednich testów zawiera DepthAI 3.12.0 oraz OpenCV. Po aktywacji Tailscale:

```bash
TS_IP="$(tailscale ip -4)"
test -n "$TS_IP" || exit 1
/srv/vision-data/staging/oak-overhead-v0/venv/bin/python \
  scripts/camera/oak/browser_preview.py \
  --bind "$TS_IP" --port 18092
```

Na komputerze Windows należącym do tego samego tailnet otworzyć:

**`http://vision:18092/`** (gdy działa MagicDNS) albo **`http://<adres_IP_Tailscale_Vision>:18092/`**.

Po uruchomieniu przetestować oba widoki, zmianę sceny, przerwanie kamery, zmianę stanu na OFFLINE, wyjście Ctrl+C i uwolnienie urządzenia USB. Zarejestrować FPS, jakość głębi, obciążenie CPU i stabilność. **Nie uruchamiać żadnych ruchów NERO w ramach tej próby.**

## Testy i stan wdrożenia

Dnia 2026-11-12 pobrano gałąź na AI Platform do tymczasowego katalogu, sprawdzono `py_compile` i wykonano testy `unittest` bez sprzętu: **6/6 PASS**. Uruchomienie wirtualnej kamery nie było częścią testu; nie stwierdzono realnej pracy OAK w przeglądarce.

Bezpośredni agent Desktop Commander `vision` był offline; host odpowiadał na ping w Tailscale, ale nie było autoryzowanego zdalnego dostępu powłoki. Z tego powodu **nie włączono procesu ani usługi na VENTUNO Q**, nie zajęto kamery i nie zmieniono istniejących testów. Po odzyskaniu dostępu należy wykonać wyżej opisany test sprzętowy i dopiero potem rozważyć usługę Camera Service / Vision Core z centralnym właścicielem pipeline.

## Wycofanie

Zatrzymać proces `Ctrl+C`. Nie istnieją zmiany w systemd, udev ani sterowaniu NERO. Usunąć tylko utworzony katalog staging podglądu, jeśli nie jest już potrzebny; nie usuwać `oak-overhead-v0` ani jego wyników testów.

## 2026-11-12 — rzeczywista próba na VENTUNO Q (po przygotowaniu DEV)

**Status uzupełniony:** `HARDWARE_RGB_DEPTH_PASS / TAILSCALE_HTTP_PASS / SHORT_STABILITY_PASS / NOT_PRODUCTION`.

- VENTUNO Q po naprawie Remote MCP działał po restarcie; NVMe `/dev/nvme0n1p1` zamontowany jako ext4 RW.
- OAK-D Pro AF wykryta przed uruchomieniem jako `03e7:2485`; brak aktywnego innego pipeline DepthAI.
- Checkout gałęzi DEV w `/srv/vision-data/staging/oak-browser-preview-dev`; `py_compile` i 6/6 testów offline PASS na urządzeniu Vision w istniejącym venv `depthai==3.12.0`, `opencv-python-headless==5.0.0.93`.
- Uruchomiony **ręcznie, bez systemd/autostartu** jeden proces `browser_preview.py` z `--bind <TS_IP_Vision> --port 18092`.
- DepthAI przestawił urządzenie na `03e7:f63b` na gałęzi SuperSpeed; `UsbSpeed.SUPER` oraz log systemowy potwierdziły USB3. To odmienny, pozytywny wynik wobec wcześniejszego ograniczenia USB2 w innym torze danych.
- `GET /` i `GET /api/status` osiągalne z **AI Platform** przez Tailscale; status `online=true`, `pipeline_running=true`, bez błędu.
- `GET /stream/rgb.mjpg`: ok. 25 kompletnych klatek JPEG w 2 s; `GET /stream/depth.mjpg`: ok. 24 klatki JPEG w 2 s; odebrane z AI Platform, nie tylko w pętli localhost.
- W trakcie pomiarów status RGB i depth ~12–13 FPS; pełny udział ważnych pikseli głębi ~61–65% w aktualnej, niekalibrowanej scenie.
- Po ok. 1 min 44 s nadal `online=true`, brak nowych rozłączeń USB lub `X_LINK_ERROR` w tym oknie. CPU procesu ~146% jednego rdzenia logicznego w notacji `ps`, RSS ~993 MB; na hoście dostępne ~12,5 GB RAM. Te wartości wymagają dalszej optymalizacji, ale nie zablokowały funkcjonalnego testu.
- Kamera działa bez włączania IR i bez NN, robot NERO nie otrzymał poleceń; brak zapisu prywatnych klatek na dysk (poza chwilowymi transferami HTTP odczytanymi na AI Platform i następnie usuniętymi).

**Nadal NIE potwierdzono**: stabilności wielogodzinnej, rozłączenia USB w trakcie strumieniowania, kalibracji przestrzennej, automatycznego startu po restarcie ani integracji z Vision Core. W obecnym trybie źródłem serwera pozostaje terminalowy proces DEV (nie usługa systemd). Ponieważ kamera jest zasobem wyłącznym, autostart wymaga osobnej decyzji i centralnego właściciela pipeline, aby nie blokować testów pozostałych modułów.

