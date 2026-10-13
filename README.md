# Vision

Stanowisko akwizycji obrazu i inspekcji fotograficznej płytek PCB / sterowników ECU, rozwijane na Arduino VENTUNO Q (Qualcomm QCS8275).

> **Status na 2026-10-10:** projekt bez wdrożonej aplikacji Vision Core. Zakończono część weryfikacji rzeczywistego hardware: GPU, NPU i funkcje USB/PTP Sony A6100, w tym Live View, JPEG 24 MP oraz RAW+JPEG. Stabilność fotografowania pozostaje warunkowa; pełny Hardware Baseline v1 jest nadal otwarty.

## Raporty z testów sprzętu

- [VENTUNO Q — matryca wyników GPU, NPU, PCIe/NVMe, USB, roadmapa](docs/hardware/VENTUNO_Q_HARDWARE_VERIFICATION_2026-10-10.md)
- [Sony A6100 — wszystkie testy USB/PTP, Live View, RAW, focus, STAB-01–06](docs/hardware/SONY_A6100_VERIFICATION_2026-10-10.md)
- [Lokalne dowody i katalogi sesji na NVMe](docs/hardware/EVIDENCE_REGISTER_2026-10-10.md)
- [Skrócony stan bazowy VENTUNO](docs/hardware/VENTUNO_Q_BASELINE.md)
- [Sony A6100A — HDMI, ScalarWebAPI Wi-Fi, BLE, USB/PTP i pełny cykl RAW+JPEG na SD (13.10.2026)](docs/hardware/SONY_A6100A_MULTITRANSPORT_VERIFICATION_2026-10-13.md)
- [Decyzja robocza: etapowa akwizycja HDMI + Wi-Fi + import USB, bramki przed produkcją](docs/architecture/ADR_SONY_STAGED_ACQUISITION_2026-10-13.md)
- [Rejestr dowodów Sony z 12–13.10.2026 (wyłącznie indeks lokalnych sesji NVMe)](docs/hardware/EVIDENCE_REGISTER_SONY_2026-10-13.md)

**Stan dodatkowy 2026-10-13:** pojedynczy cykl HDMI (obserwacja operatora) + sterowanie Wi-Fi → RAW+JPEG na karcie SD → późniejszy import przez USB Mass Storage na NVMe przeszedł **PASS**. Automatyczne wznowienie Wi-Fi po USB, trwała stabilność serii i przechwytywanie cyfrowe HDMI pozostają **NOT TESTED / BLOCKED**; nie ma wdrożonej aplikacji Vision Core.

**Interpretacja:** status `PASS` dotyczy określonego testu; nie jest równoznaczny z gotowością produkcyjną. Zdjęcia i niezredagowane logi pozostają na NVMe, nie w publicznym repo.

## Cel i podział odpowiedzialności

**VENTUNO (Vision)** jest lokalnym kontrolerem stanowiska: ma obsługiwać wykonywanie zdjęć, pozyskiwanie termowizji radiometrycznej, ocenę ostrości/ekspozycji/pokrycia, rejestrację przestrzenną, mozaiki i focus stacking, kalibrację oraz wspomaganie ustawiania kamery i planowania ruchu ramienia. OpenCV i lekki model detekcyjny pozostają kandydatami do przyszłego etapu — po weryfikacji kompatybilności.

**AI Platform** ma wykonywać wnikliwą analizę zdjęć PCB, wnioskowanie i raporty **poza VENTUNO**. Sposób przekazywania wyników nie jest wdrożony. Projekty i repozytoria pozostają odrębne.

## Sprzęt

- Arduino VENTUNO Q — lokalny komputer/sterownik stanowiska, Ubuntu 24.04.4 ARM64, kernel `6.8.0-1084-qcom`; GPU Adreno i NPU Hexagon przeszły testy funkcjonalne w opisanym zakresie.
- Sony A6100 — **fizycznie przetestowany** po USB: PTP, żywy Preview, JPEG i RAW+JPEG. STAB-01/STAB-03 wykazały błędy szybkiego ponawiania zdjęć; STAB-05 (10/10 w jednej sesji) i STAB-06 (4/4 w oddzielnych sesjach przy 10 s odstępu) przeszły.
- Kamera termowizyjna **radiometryczna** — model/interfejs niezatwierdzone; wymagane dane temperatury per piksel.
- Ramię robota — model niezatwierdzony; wymagana ocena zasięgu, udźwigu, sztywności i niezależnego bezpieczeństwa.
- Nieruchoma kamera głębi/3D — rozważana do mapowania przeszkód, nie jako czujnik bezpieczeństwa funkcjonalnego.
- Sterowane oświetlenie (ring + boczne), uchwyty i kalibratory — do wyboru i weryfikacji.

Test aparatu i GPU/NPU nie oznacza automatycznej kompatybilności pozostałego sprzętu.

## Zasady inżynierskie

1. Rozdzielamy akwizycję, jakość/kalibrację, przetwarzanie obrazu, termowizję, sterowanie robotem i integracje przez wymienne adaptery.
2. AI/kamera głębi nie gwarantują bezpieczeństwa; limity ruchu, E-stop i interlocki muszą działać niezależnie.
3. Zachowujemy oryginalne zdjęcia i radiometrię wraz z metadanymi i hashami; produkty pochodne mają być odtwarzalne.
4. Nie zmieniamy środowiska Qualcomm/Arduino bez audytu i decyzji właściciela.
5. Nie wykonujemy na razie sterowania mechaniką, grzaniem ani zasilaniem DUT.
6. Prace prowadzimy na gałęziach i przez PR; merge do `main` wymaga wyraźnej zgody właściciela.
7. Nie publikujemy kluczy, tokenów, numerów seryjnych, IP, surowych sesji i innych wrażliwych dowodów.

## Plan kolejnych prac

1. Dokończyć weryfikację hardware: STM32H5, Qualcomm ↔ STM32, MIPI CSI/ISP, Ethernet 2.5 Gb/s, USB-C/DP Alt Mode, temperatury/SMART, stabilność.
2. Zamknąć odpowiedni zakres i zatwierdzić **Vision Hardware Baseline v1**.
3. Dopiero potem budować Vision Core, adaptery akwizycji, QC/OpenCV i modele lokalne.
4. Następnie realizować oświetlenie, kalibrację, mozaiki/focus stacking, radiometrię i integrację robota z osobnymi zabezpieczeniami.
5. Przygotować jawny, wersjonowany kontrakt eksportu do odrębnej AI Platform.

Szczegóły: `docs/architecture/`, `docs/hardware/`, `docs/process/`, `scripts/audit/`.

## Połączenia administracyjne

Potwierdzono SSH/Tailscale, wcześniejszą sesję przez USB-C/ADB i Desktop Commander MCP na urządzeniu `vision`. Adresy, identyfikatory urządzeń i dane dostępu nie są częścią repozytorium.
