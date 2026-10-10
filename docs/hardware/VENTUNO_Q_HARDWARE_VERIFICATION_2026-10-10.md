# Arduino VENTUNO Q — raport weryfikacji sprzętowej (stan na 2026-10-10)

**Projekt:** Vision — stanowisko akwizycji fotograficznej i termowizji PCB/ECU.
**Status dokumentu:** migawka wyników, **nie** finalny „Vision Hardware Baseline v1”.
**Platforma:** Arduino VENTUNO Q, Qualcomm QCS8275, Ubuntu 24.04.4 LTS, ARM64, kernel `6.8.0-1084-qcom`.
**Zasada:** status `PASS` oznacza przejście *konkretnego* opisanego testu, nie ogólną certyfikację urządzenia.

## 1. Źródła i wiarygodność

- **POMIAR/LOG:** wynik uzyskany na fizycznym VENTUNO przez SSH lub Desktop Commander MCP; lokalne dowody wskazano w [rejestrze](EVIDENCE_REGISTER_2026-10-10.md). Surowe logi mogą pozostać poza Git.
- **WYNIK WCZEŚNIEJSZEJ SESJI:** potwierdzony w poprzedniej sesji testowej, ale niekoniecznie istnieje komplet surowych logów w repo. Takich wyników nie należy mylić z ponownym testem wykonanym na potrzeby tego dokumentu.
- **UNVERIFIED:** urządzenie/interfejs może być wykryty lub deklarowany w specyfikacji, lecz nie przeszedł wymaganej próby funkcjonalnej.
- Brak testu nie oznacza awarii. `FAIL` testu oprogramowania nie jest automatycznie `FAIL` sprzętu.

## 2. Matryca wyników VENTUNO Q

| ID | Obszar | Dowód wykonania | Wynik | Ograniczenia |
|---|---|---|---|---|
| SYS-01 | System/architektura | Ubuntu 24.04.4, ARM64, kernel 6.8.0-1084-qcom | PASS — identyfikacja | Nie wykonano benchmarku CPU/RAM |
| REM-01 | Zdalne zarządzanie | SSH/Tailscale, MCP na urządzeniu `vision` | PASS — połączenia | Bez testu długotrwałej dostępności |
| GPU-01 | Adreno 623 / Vulkan | Mesa Freedreno/Turnip, urządzenie Vulkan, API 1.3.318 | PASS — enumeracja | Sama enumeracja nie wystarcza do potwierdzenia renderowania |
| GPU-02 | Adreno 623 / EGL/OpenGL ES | Renderowanie do bufora, odczyt RGBA `PASS_RENDER` | PASS — render | Brak benchmarku wydajności i stabilności termicznej |
| NPU-01 | Hexagon DSP / FastRPC | Obecność CDSP/ADSP/GPDSP, FastRPC, bibliotek QNN/HTP | PASS — wykrycie/środowisko | Nie wykonano niezależnej inferencji na każdym DSP |
| NPU-02 | Hexagon HTP V75 | ONNX Conv+ReLU, `QNNExecutionProvider`, brak fallbacku CPU | PASS_STRICT_HTP | Nie jest to benchmark TOPS, temperatur ani obciążenia długotrwałego |
| PCIE-01 | Połączenie NVMe | PCIe Gen4 ×4, 16 GT/s, Lexar SSD PLAY 1 TB | PASS — link | Nie weryfikowano degradacji przy obciążeniu |
| NVME-01 | Odczyt NVMe | Bezpośredni odczyt 64 MiB: około 1,7 GB/s | PASS — pojedynczy pomiar | To nie ciągły benchmark |
| NVME-02 | Montowanie i zapis sesji | `/dev/nvme0n1p1`, ext4 rw na `/srv/vision-data` | PASS — operacje w rzeczywistych testach | SMART/temperatura NVMe: UNVERIFIED |
| STORAGE-01 | NVMe Write Guard | 9/9 testów jednostkowych według wcześniejszej sesji | PASS — unit | Test izolowanego zapisu/sandbox: niedomknięty (Bubblewrap) |
| USB-01 | Kontroler USB 3.0 | TI TUSB73x0, 5 Gb/s, wykryty | PASS — enumeracja | Transfer 5 Gb/s na rzeczywistym urządzeniu: UNVERIFIED |
| USBC-01 | USB-C Power Delivery / DP Alt Mode | Rozpoznane deklaracje PD i DP Alt Mode | PASS — deklaracja/odczyt | Zasilanie i obraz+dotyk jednym kablem: UNVERIFIED |
| SONY-01 | Sony A6100 | USB/PTP, JPEG/ARW, podgląd, serie zdjęć | PASS z ograniczeniami | Szczegóły i błędy STAB-01/STAB-03 w osobnym raporcie |
| STM32-01 | STM32H5 / komunikacja Qualcomm–STM32 | Nie wykonano testu | UNVERIFIED | Nie modyfikować firmware bez zgody |
| CSI-01 | MIPI CSI / ISP / V4L2 | Nie wykonano funkcjonalnego testu kamery | UNVERIFIED | Wybór modułu kamery później |
| NET-01 | Ethernet 2.5 Gb/s | Nie wykonano pomiaru transferu | UNVERIFIED | Sama obecność portu/sterownika nie wystarcza |
| THERM-01 | Temperatury/throttling pod obciążeniem | Nie wykonano pełnego testu | UNVERIFIED | Objęte dalszą roadmapą |

## 3. GPU Adreno 623

**Narzędzie lokalne:** `/srv/vision-data/tools/ventuno_gpu_verify.py`.

- Sprawdzono DRM/sterownik `msm`, bibliotekę Vulkan i Freedreno/Turnip; Vulkan wykrył sprzętowy Adreno 623, API 1.3.318.
- Test `--render` utworzył kontekst EGL/GLES, wypełnił bufor 2×2, wykonał `glReadPixels` i potwierdził oczekiwane RGBA z tolerancją skryptu; wynik `PASS_RENDER`.
- Renderer nie był programowym `llvmpipe`. To potwierdza faktyczną ścieżkę renderowania, **nie** gwarantuje wydajności dowolnych shaderów, OpenCL ani zgodności modeli ML.
- Pierwotne wyniki pochodzą z wcześniejszej weryfikacji sprzętowej; w ramach tworzenia dokumentacji skryptu nie uruchamiano ponownie.

Odtworzenie (po osobnym zatwierdzeniu): `python3 -B /srv/vision-data/tools/ventuno_gpu_verify.py --render`.

## 4. NPU Qualcomm Hexagon — test ścisły

**Środowisko:** `/srv/vision-data/tools/npu-verify/`; Python 3.12, ONNX Runtime QNN **1.23.0**, Qualcomm AI Runtime/QAIRT **2.46.0**, HTP V75. Pakiety QAIRT wypakowano lokalnie na NVMe, nie zastępując systemowych bibliotek.

- Model: `models/tiny_conv_relu.onnx`, operacje Conv + ReLU, tensor wyniku `(1, 4, 16, 16)`.
- Test kontrolny CPU: PASS; QNN skonfigurowano bez CPU fallback.
- Log `verify_htp_run.txt`: **FAIL** pierwszej inicjalizacji (`QNN_DEVICE_ERROR_INVALID_CONFIG`). Nie jest to finalny stan NPU.
- Log `verify_htp_run2.txt`: **PASS_STRICT_HTP** po skorygowaniu konfiguracji backendu.
- Profil ORT: operacja na `QNNExecutionProvider`; według wyniku testu 1 węzeł QNN / 0 węzłów CPU.
- Maksymalny bezwzględny błąd względem CPU: **0,0004889965**; wartości skończone.
- W logu sukcesu `wall_time_s_including_session_init=0.31` dla małego modelu; **nie** traktować jako benchmarku szybkości Vision.

Reprodukcja po zatwierdzeniu: `bash /srv/vision-data/tools/npu-verify/run_htp.sh`.

## 5. PCIe, NVMe, polityka zapisu

- Lexar SSD PLAY 1 TB podłączony przez PCIe Gen4 ×4, zgłoszone 16 GT/s.
- Zamontowany rzeczywiście na `/srv/vision-data`, `/dev/nvme0n1p1`, ext4 rw. W czasie testu RAW-01 podawano około **887 GB wolnego miejsca** (wartość historyczna, nie stan bieżący).
- Jednorazowy odczyt 64 MiB około **1,7 GB/s** — pomiar wcześniej wykonany, bez wnioskowania o maksymalnym transferze Gen4.
- Wszystkie sesje akwizycji Sony zapisywano na NVMe, z weryfikacją plików. Brak fallbacku na eMMC jest **wymaganiem docelowego Vision runtime**, a nie udowodnioną właściwością wszystkich programów diagnostycznych.
- Projekt `NVMe Write Guard`: 9/9 testów jednostkowych PASS; fizyczny smoke izolacji przez Bubblewrap napotkał ograniczenia. **Nie nadawać `HARDWARE_GATE=PASS`; nie pogłębiać teraz Write Guard.**
- SMART, temperatura i długotrwały zapis NVMe: **UNVERIFIED**.

Wymóg zapisu wyłącznie na NVMe wynika z zasad projektu; jego szczegółowa polityka i Write Guard pozostają na odrębnych gałęziach `chore/nvme-user-data-policy-20261010` i `feature/nvme-write-guard-v1`, jeszcze poza bazowym `main`. Niniejszy raport nie wdraża ani nie zatwierdza ich runtime.

## 6. USB i peryferia

- Kontroler **Texas Instruments TUSB73x0** zgłasza USB 3.0/5 Gb/s — stan wykrycia, bez testu przesyłu z urządzeniem SuperSpeed.
- USB-C zgłasza **Power Delivery** i **DisplayPort Alt Mode**, ale nie przetestowano monitora z obrazem i dotykiem na jednym kablu.
- Sony ILCE-6100A wykryty jako USB `054c:0f0d`, fizyczne połączenie USB 2.0 High Speed 480 Mb/s. PTP i transfer plików są potwierdzone **funkcjonalnie**.
- Reguła Sony `udev` daje dostęp bez `sudo` grupie `arduino`; test wykonywano bez podnoszenia uprawnień.
- Brak zweryfikowanej obsługi kamer MIPI CSI/ISP, termowizji radiometrycznej i kamery głębi.

## 7. Dostęp administracyjny i izolacja

- `vision` jest osiągalny zdalnie przez SSH/Tailscale i Desktop Commander MCP. Agent MCP uruchamia się automatycznie, nie wymagając aktywnego terminala operatora.
- Repozytorium: `/srv/vision-data/projects/Vision` (NVMe).
- Środowisko NPU i narzędzia Sony: w izolowanych katalogach NVMe. Nie wdrażano właściwej aplikacji Vision ani jej runtime.
- Nie kopiować danych dostępowych, numerów seryjnych, identyfikatorów połączeń czy pełnych raportów audytu do publicznego Git.

## 8. Kryteria dalszego etapu sprzętowego

1. **STM32H5:** wykrycie obecności, opis kanału Qualcomm ↔ STM32, potwierdzenie dwukierunkowej wymiany testowej bez zmiany firmware (najpierw odczyt).
2. **MIPI CSI/ISP:** spis fizycznych portów i sterowników, potem realny capture na wspieranym module.
3. **Ethernet:** link i pomiar rzeczywistego transferu 2.5 Gb/s.
4. **USB-C / DP Alt Mode:** obraz + dotyk na właściwym monitorze i przewodzie, osobno od deklaracji firmware.
5. **System/temperatury:** SMART NVMe, monitorowanie CPU/GPU/NPU, throttling i powtarzalny test pod obciążeniem.
6. **Termowizja/depth/robot:** dopiero po wyborze urządzeń i osobnej zgodzie; danych radiometrycznych oraz funkcji bezpieczeństwa nie można zastępować pseudokolorem lub samym AI.
7. Po zakończeniu odpowiedniego zakresu powstanie finalny dokument **Vision Hardware Baseline v1**. **Nie** uznawać tego raportu za jego zatwierdzenie.

## 9. Powiązane dokumenty

- [Sony A6100 — szczegółowy raport testów](SONY_A6100_VERIFICATION_2026-10-10.md)
- [Rejestr dowodów i ścieżek](EVIDENCE_REGISTER_2026-10-10.md)
- [Stan bazowy VENTUNO](VENTUNO_Q_BASELINE.md)
- [Plan integracji](INTEGRATION_PLAN.md)

**Zakres publikacji:** wyłącznie przeglądowe dane techniczne i lokalne ścieżki do dowodów. Bez zdjęć, surowych logów USB/PTP, tokenów, adresów sieci i numerów seryjnych.
