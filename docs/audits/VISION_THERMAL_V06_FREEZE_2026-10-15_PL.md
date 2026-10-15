# Vision Thermal — raport końcowy i zamrożenie DEV v0.6

**Data:** 2026-10-15  
**Projekt:** Vision — warsztatowe stanowisko akwizycji obrazów i termowizji PCB/ECU  
**Decyzja:** koniec bieżącego etapu rozwoju aplikacji Thermal; dalsze modyfikacje wymagają nowej dyspozycji właściciela projektu.  
**Status:** `DEV FROZEN / FUNCTIONAL PASS / NOT PRODUCTION INTEGRATED`.

## 1. Weryfikacja działającej wersji

Aplikacja Vision Thermal v0.6 pracuje na Arduino VENTUNO Q (Ubuntu ARM64) z kamerą InfiRay T2S+ podłączoną przez USB UVC. Zweryfikowano identyfikator urządzenia `1514:0001`, format `YUYV 256×196` i dane radiometryczne `RAW16 256×192` z czterema wierszami metadanych. Podgląd udostępnia ciągły MJPEG, a aplikacja używa wyłącznie lokalnego endpointu na `127.0.0.1:8765` (dostęp z laptopa przez SSH tunnel).

Zakres zamrożony:
- Widok termiczny z paletą Inferno; podgląd niezależny od zapisu RAW.
- Obrót obrazu **0°, 90°, 180°, 270°** w przeglądarce. Współrzędne obrazu, wskaźnik piksela i nakładki ROI zachowują zgodność z pikselami sensora.
- **3 niezależne ROI** z osobnym minimum, maksimum i średnią temperaturą; zmiana aktywnego ROI nie usuwa innych.
- Historia minimum/maksimum/średniej każdego ROI: próbka co około sekundę, maksymalnie **300 punktów i 5 minut**, wyłącznie RAM przeglądarki. Oś czasu zaczyna się z lewej i po 5 min przechodzi w okno przesuwne.
- Ręczny zapis migawki na NVMe: oryginalna ramka `frame.yuyv`, mapa `pixels_u16.npy`, mapa `temperature_unverified_c.npy`, `preview.png`, manifest JSON z kontrolnymi SHA-256.
- Lokalny kontrakt API: `GET /api/status`, `GET /api/stream.mjpeg`, `GET /api/frame.png`, `GET /api/point`, `GET /api/roi`, `POST /api/snapshot`.

**Pomiary °C oznaczone są `NOT_VALIDATED` — nie przeprowadzono walidacji temperatury wzorcem ani potwierdzenia błędu pomiarowego.** Używanie odczytów jako pomiarów bezwzględnych do decyzji serwisowych wymaga osobnej kalibracji i uwzględnienia emisyjności PCB.

## 2. Dowody testów końcowych (15.10.2026)

| Kontrola | Wynik |
| --- | --- |
| Kamera i strumień RAW16 | PASS |
| Lokalny stan aplikacji / health | PASS |
| Trzy ROI odczytane z kamery | PASS |
| Testy regresyjne Python | **8/8 PASS** |
| Testy JS: trzy ROI, niezależne historie, retencja, geometria | PASS |
| Testy JS: obrót 0/90/180/270 i mapowanie kliknięć/ROI | PASS |
| Strumień MJPEG przez 5 s | **128 klatek / 25,29 FPS** |
| Odstęp klatek, mediana / 95. percentyl | **39,95 / 43,44 ms** |
| Pamięć kontenera (jedna próbka pomiarowa) | **~33 MiB** |
| Integracja z głównym Vision | **Nie wykonano — świadomie** |
| Katalog roboczy produkcyjnego repo | CLEAN |

Nie przeprowadzono testów metrologicznych, testów awarii/ponownego podłączenia kamery, odtwarzania danych na drugim urządzeniu ani pełnego długoterminowego testu obciążeniowego. Wyniki z wybranej sesji nie zastępują tych testów.

## 3. Architektura i odtwarzanie

Aplikacja ma osobny worker Python, dekodowanie radiometryczne, interfejs HTTP i warstwę wizualizacji JS. Produkcyjne repo `autoklinika/Vision` nie zostało zmienione ani scalone. Wszystkie pliki robocze i migawki zapisywano na NVMe `/srv/vision-data`, z blokadą zapisu przy nieprawidłowym montowaniu wolumenu.

Lokalizacja aplikacji: `/srv/vision-data/experiments/vision-thermal-app-dev-20261015/`.  
Uruchomienie: `bash /srv/vision-data/experiments/vision-thermal-app-dev-20261015/start_dev.sh`.  
Zatrzymanie: `bash /srv/vision-data/experiments/vision-thermal-app-dev-20261015/stop_dev.sh`.  
Po restarcie hosta aplikacja nie startuje samoczynnie. Nie należy na razie przełączać jej do usługi systemowej.

Obraz środowiska: `ghcr.io/arduino/app-bricks/python-apps-base:0.12.0`, ARM64, digest `sha256:35eb218ee65c4886a2e0ead685ae8d16a68ecd6bc0a0dfc678669f69d7987a7a`.

Zależność termometryczna: `diminDDL/IR-Py-Thermal` pinned `edf7d5619f77c18c54d7c618fa9ea3f78bdf02d6` (GNU GPL-3.0). Bez tej zależności obecny backend temperatur nie jest samodzielny.

## 4. Archiwa — prywatne, wyłącznie NVMe Vision

Katalog zamrożenia: `/srv/vision-data/experiments/thermal-freeze-20261015/`.

- `Vision_Thermal_v0.6_source_private_20261015.tar.gz` — kod źródłowy aplikacji, dokumentacja, testy, poprzednie wersje i kod zależności GPL; SHA-256: `3c8db1eef5d50343a7fcc02fafbf6fed6c9babfe0d2fedcc712cd5692280f5a2`.
- `Vision_Thermal_v0.6_lab_data_LOCAL_ONLY_20261015.tar.gz` — lokalne migawki RAW, mapy i próbki testowe; SHA-256: `e0cc18f487195a789a0d7364d2cd28aa3e5b731ff1e4d07adf01bb4ad47433d3`.
- `Vision_Thermal_v0.6_runtime_base_ARM64_20261015.tar` — obraz kontenera użytego w testach; SHA-256: `fe863a1afd5c6566e0093b956a7bf0027999509895accec4aa25f26f7774c642`.

Każdy archiwalny plik należy przed użyciem zweryfikować poleceniem `sha256sum`. Dane laboratoryjne i obraz kontenera **nie są przeznaczone do publicznej publikacji ani commitowania do głównego repo**. Archiwum źródeł zawiera kod GPL, zatem jego przyszłe udostępnienie wymaga dochowania warunków tej licencji.

## 5. Licencje i publikacja

- `IR-Py-Thermal`: GPL-3.0. Dopuszczalne wewnętrzne użytkowanie i modyfikacja w warsztacie bez wymogu upubliczniania kodu. Dalsza dystrybucja wymaga odpowiedniej obsługi licencji.
- Testowany projekt `infiray-t2pro`: kod MIT, lecz dołączona binarna biblioteka SDK producenta ma niewyjaśniony status redystrybucji i dawała niespójne wyniki na T2S+. **Nie jest włączona do archiwum aplikacji**.
- `thermal-viewer`: MIT, tylko badany jako inspiracja, nie wymagany przez v0.6.
- Repo `autoklinika/Vision` jest **publiczne**. Raport może się w nim znaleźć, ale źródeł GPL, surowych danych warsztatowych i artefaktów binarnych nie publikujemy bez odrębnej weryfikacji i decyzji. Preferowane miejsce pełnego kodu: **repozytorium prywatne**.

## 6. Otwarte zagadnienia — odłożone

1. **Focus Assist / autofocus:** T2S+ zgłasza interfejs `focus_absolute`, ale fizyczny AF nie został potwierdzony; przewidziano osobny etap wskaźnika ostrości i ewentualny napęd obiektywu.
2. **Walidacja temperatur:** wzorzec cieplny i porównanie z termometrem referencyjnym, korekcja emisyjności/odbicia.
3. **Odporność na USB:** długotrwała stabilność, identyfikacja urządzenia po USB, automatyczne odzyskanie po odłączeniu.
4. **Dodatkowe funkcje:** nazwy ROI, alarmy, eksport serii czasowej i synchronizacja Sony A6100/ramienia.
5. **Integracja z Vision i ERS:** tylko przez osobne wersjonowane kontrakty, po zatwierdzeniu; nie łączyć repozytoriów.

**Decyzja końcowa:** stan DEV v0.6 zamrożony. Nowy rozwój jedynie na osobnej gałęzi/prototypie po zgodzie właściciela; nie wykonywać automatycznego merge do `main`.
