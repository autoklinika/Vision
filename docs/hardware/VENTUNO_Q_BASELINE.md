# VENTUNO Q — stan bazowy sprzętu i weryfikacji

**Data aktualizacji:** 2026-10-10.
**Status:** roboczy stan przed finalnym **Vision Hardware Baseline v1**. Nie jest to pełny audyt systemu ani zgoda na rozpoczęcie Vision Core.

## Sprzęt i oprogramowanie

- Płyta: Arduino VENTUNO Q, Qualcomm QCS8275, ARM64.
- System: Ubuntu 24.04.4 LTS, kernel `6.8.0-1084-qcom`.
- Host: `vision`; standardowy użytkownik: `arduino`.
- Dostęp: SSH (lokalny / Tailscale, wcześniej również przekierowanie USB-C/ADB) oraz automatycznie dostępny Desktop Commander MCP.
- Repozytorium i dane projektu: **NVMe `/srv/vision-data`**, repo `/srv/vision-data/projects/Vision`; dane akwizycji `/srv/vision-data/vision/sessions`.
- Nie przechowujemy w publicznym repo numerów seryjnych, adresów IP, identyfikatorów ADB/MCP, kluczy ani tokenów.

## Faktycznie sprawdzone funkcje

| Obszar | Status | Zakres dowodu |
|---|---|---|
| GPU Adreno 623 | **PASS** | Vulkan sprzętowy API 1.3.318; EGL/GLES render + odczyt RGBA; bez llvmpipe |
| Hexagon NPU/HTP V75 | **PASS_STRICT_HTP** | ONNX Conv+ReLU przez QNNExecutionProvider, CPU fallback wyłączony |
| Dysk Lexar SSD PLAY 1 TB | **PASS częściowy** | PCIe Gen4×4 16 GT/s; montowanie ext4 rw; jednorazowy odczyt 64 MiB ~1,7 GB/s |
| NVMe Write Guard | **PASS unit / hardware UNVERIFIED** | 9/9 unit; fizyczna izolacja przez Bubblewrap niedomknięta; temat odłożony |
| USB 3.0 / TUSB73x0 | **PASS wykrycia** | Kontroler deklaruje 5 Gb/s; realny transfer nieprzetestowany |
| USB-C PD / DP Alt Mode | **PASS deklaracji** | Brak testu obrazu i dotyku na pojedynczym kablu |
| Sony A6100 — PTP/zdjęcia | **PASS warunkowo** | JPEG 24 MP, RAW+JPEG, żywy Preview 1024×680, udane serie z odstępami |
| Sony A6100 — szybkie sekwencje | **FAIL niektórych prób** | STAB-01/STAB-03: `Could not capture` przy szybkich osobnych sesjach |
| Sony focus stepping | **UNVERIFIED optycznie** | Polecenia Near/Far działały; zmienność ekspozycji uniemożliwiła rozstrzygnięcie |
| CAN `can0`/`can1`/`can2`, `docker0` | **UNVERIFIED funkcjonalnie** | Wcześniejsze wykrycie interfejsów nie stanowi testu ruchu |
| STM32H5, CSI/ISP, Ethernet 2.5 Gb/s, pomiary temperatur | **UNVERIFIED** | Odpowiednie testy jeszcze nie wykonane |

### Uwaga o stwierdzeniu PASS

`PASS` dotyczy konkretnej próby, nie gotowości produkcyjnej. Szczególnie:
- GPU: test renderowania nie jest benchmarkiem ani testem kompatybilności OpenCV/AI.
- NPU: strict execution to nie gwarancja stabilności pod obciążeniem; wcześniej wystąpił błąd konfiguracji backendu, potem test przeszedł.
- Sony: 10/10 w jednej sesji i 4/4 w osobnych przy odstępach 10 s; szybkie wywołania w osobnych sesjach nie były stabilne.
- NVMe: wykryty dysk i pojedynczy odczyt nie zastępują SMART, temperatury i pełnego smoke Write Guard.

## Raporty źródłowe

- [VENTUNO Q — szczegółowe wyniki i roadmapa](VENTUNO_Q_HARDWARE_VERIFICATION_2026-10-10.md)
- [Sony A6100 — USB/PTP, Live View, RAW, STAB](SONY_A6100_VERIFICATION_2026-10-10.md)
- [Rejestr dowodów i ścieżek NVMe](EVIDENCE_REGISTER_2026-10-10.md)
- [Plan integracji](INTEGRATION_PLAN.md)

## Zasady ochrony środowiska

Nie wykonujemy `do-release-upgrade`, `apt full-upgrade`, zmiany pakietów Qualcomm, sterowników, kernela ani firmware bez osobnej decyzji i planu wycofania. Właściwa aplikacja Vision Core, autonomiczny robot, radiometria i moduły OpenCV/AI nie są jeszcze wdrożone.

## Dalsze bramki hardware

1. STM32H5 i komunikacja Qualcomm ↔ STM32 (start od odczytu, bez flashowania).
2. MIPI CSI/ISP, wykrywanie i funkcjonalna próba kamery.
3. Ethernet 2.5 Gb/s, rzeczywisty transfer.
4. USB-C/DisplayPort Alt Mode na fizycznym monitorze z dotykiem.
5. Temperatury, SMART NVMe, stabilność sprzętu pod obciążeniem.
6. Po zatwierdzeniu zakresu: finalny **Vision Hardware Baseline v1**.

Audyt odczytowy: `scripts/audit/vision_audit_v1.sh`; raporty audytu po weryfikacji danych wrażliwych pozostają domyślnie poza Git.
