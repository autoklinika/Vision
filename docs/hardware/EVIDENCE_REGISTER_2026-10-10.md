# Vision — rejestr dowodów testowych (2026-10-10)

**Status:** indeks ścieżek lokalnych na NVMe urządzenia `vision`. Nie jest archiwum binariów w Git.
**Ważne:** repozytorium jest publiczne. Nie kopiujemy tu zdjęć osób/scen, logów PTP z identyfikatorami, numerów seryjnych ani raportów audytu z informacjami infrastrukturalnymi.

## 1. Katalogi bazowe na VENTUNO

| Przeznaczenie | Lokalna ścieżka |
|---|---|
| Główne repozytorium | `/srv/vision-data/projects/Vision/` |
| Sesje obrazu | `/srv/vision-data/vision/sessions/` |
| Narzędzie GPU | `/srv/vision-data/tools/ventuno_gpu_verify.py` |
| Izolowany NPU | `/srv/vision-data/tools/npu-verify/` |
| Izolowany Sony | `/srv/vision-data/tools/sony-a6100-verify/` |
| Reguła dostępu Sony USB | `/etc/udev/rules.d/99-vision-sony-a6100.rules` |
| Testy polityki storage w repo (gałąź robocza) | `feature/nvme-write-guard-v1` |

Dane o GPU, PCIe, USB-C oraz części testów storage przedstawiono w dokumentacji na podstawie wcześniejszej sesji operatora. Nie wszystkie wytworzyły osobne trwałe pliki logów.

## 2. GPU i NPU

| Obszar | Dowód i sposób oceny | Uwagi |
|---|---|---|
| GPU Adreno 623 | `/srv/vision-data/tools/ventuno_gpu_verify.py` | Wcześniejszy wynik `PASS_RENDER`; skrypt wspiera enumerację Vulkan i EGL/GLES readback; surowego logu nie dodano do Git |
| NPU — pierwszy nieudany setup | `/srv/vision-data/tools/npu-verify/logs/verify_htp_run.txt` | `QNN_DEVICE_ERROR_INVALID_CONFIG`; historyczny **FAIL** |
| NPU — poprawny przebieg | `/srv/vision-data/tools/npu-verify/logs/verify_htp_run2.txt` | `PASS_STRICT_HTP`, różnica względem CPU ~0,000489 |
| NPU — profilu ORT | `/srv/vision-data/tools/npu-verify/logs/ort_qnn_strict_2026-10-10_19-31-24.json` | Wynik przydziału wykonania przez QNN |
| NPU — profil HTP | `/srv/vision-data/tools/npu-verify/logs/qnn_htp_profile.csv` | Profil backendu, **nie** pełny benchmark |
| NPU — odtwarzalność | `/srv/vision-data/tools/npu-verify/{README.md,verify_htp.py,run_htp.sh,models/tiny_conv_relu.onnx}` | Uruchomienie dopiero za osobną zgodą |

## 3. Sony A6100 — narzędzia

| Narzędzie | Lokalna ścieżka / znaczenie |
|---|---|
| gPhoto2 bez instalacji globalnej | `/srv/vision-data/tools/sony-a6100-verify/root/usr/bin/gphoto2` |
| Tylko odczyt PTP | `/srv/vision-data/tools/sony-a6100-verify/verify-ptp.sh` |
| Jeden capture JPEG | `/srv/vision-data/tools/sony-a6100-verify/capture-once.sh` |
| Focus/porównania | `/srv/vision-data/tools/sony-a6100-verify/focus-one-step.sh`, `optical-focus-plus3.sh`, `compare_exposure_normalized.py` |
| Uprawnienia USB | `/srv/vision-data/tools/sony-a6100-verify/99-vision-sony-a6100.rules` |

Przed wykonaniem poleceń sterujących aparatem wymagane jest zatwierdzenie operatora. Na potrzeby niniejszej dokumentacji nie wykonywano ponownych zdjęć.

## 4. Sony — rejestr sesji akwizycji

Wszystkie ścieżki są względne wobec `/srv/vision-data/vision/sessions/`.

| ID | Katalog sesji | Istotne dowody | Wynik |
|---|---|---|---|
| SONY-JPEG-1 | `sony-a6100-test-20261010T201642Z/` | `capture.log`, `sony_a6100_test.jpg` | PASS |
| SONY-JPEG-2 | `sony-a6100-test-20261010T202725Z/` | `capture.log`, `preview.jpg`, JPEG | PASS |
| FOCUS +1 | `focus-step-20261010T203439Z/` | `image_1.jpg`, `image_2.jpg`, różnice, `gphoto_*.log` | Optyka UNVERIFIED |
| FOCUS +3 | `focus-step-20261010T203642Z/` | obrazy przed/po, `comparison_side_by_side.jpg`, logi | Optyka UNVERIFIED |
| LV-01 | brak osobnego katalogu | Odczyt `verify-ptp.sh`, `--abilities`, `--list-config` w sesji MCP | PASS — komunikacja |
| LV-02 | `liveview-preview-LV02-rLADzmnj/` | `thumb_lv02_preview.jpg` (1024×680) | PASS |
| LV-03 | `liveview-series-LV03-gHCew2Ku/` | 10 JPEG, `timing.tsv` (3896 ms) | PASS |
| LV-04 | `liveview-shell-LV04-niP3dU0d/` | 10 JPEG (693 ms wg pomiaru MCP) | PASS |
| LV-05 | `liveview-motion-LV05-fYyr99wi/` | 85 JPEG, `capture.log`, klatki ruchu ręki | PASS — realne odświeżanie |
| RAW-01 | brak osobnego katalogu | Odczyt `Image Quality`, `Capture Target`, stan montowania NVMe | PASS — diagnostyka |
| RAW-02 | `sony-raw-RAW02-HLbWO7NB/` | `sony_raw02.arw`, `sony_raw02.jpg`, `quality_after.txt` | PASS |
| STAB-01 | `sony-stability-STAB01-aOfu7zgf/` | `capture_01..04.log`, 2 JPEG, `timing.tsv` | **FAIL** serii |
| STAB-02 | brak osobnego katalogu | Odczyt konfiguracji i logów STAB-01 przez MCP | PASS — diagnostyka |
| STAB-03 | `sony-stability-STAB03-9ehWyeyY/` | `capture_1.log`, `capture_2.log`, 1 JPEG, `timing.tsv` | **FAIL** serii |
| STAB-04 | `sony-stability-STAB04-rg4LhmGw/` | 2 JPEG, komunikaty gPhoto2 w sesji MCP | PASS |
| STAB-05 | `sony-stability-STAB05-Uy3enZUJ/` | 10 JPEG i wynik w sesji MCP | PASS |
| STAB-06 | `sony-stability-STAB06-6XUZKHkJ/` | 4 JPEG, `capture_1..4.log`, `timing.tsv` | PASS |

**Uwaga o STAB-01:** `timing.tsv` nie zawiera zakończonego pomiaru czwartego wywołania (proces przerwano), ale `capture_04.log` zawiera błąd. **Uwaga o STAB-04/05:** wynik terminalowy MCP nie był zapisany jako osobny `capture.log`; dowód lokalny to rzeczywiście pobrane obrazy, ich rozmiary i hashe obliczone w testach.

## 5. Próbki integralności

Przy kontroli plików potwierdzono m.in.:

| Plik lokalny | SHA-256 |
|---|---|
| `sony-raw-RAW02-HLbWO7NB/sony_raw02.arw` | `d1fc49b47f4aaafda38aa4dd9fdbabe47d41571a34faf48dc8089cd52616afa0` |
| `sony-raw-RAW02-HLbWO7NB/sony_raw02.jpg` | `e79da7664d90f59364133aa99cff80580a37638d15814930575d2498d29ea118` |
| `sony-stability-STAB06-6XUZKHkJ/stab06_1.jpg` | `3ba3cf64aa602f7b9c151e14bb4bf76f54ca16866f9e359931cc2a37813bf64a` |
| `sony-stability-STAB06-6XUZKHkJ/stab06_4.jpg` | `6e8b39346edaac11ce6255f86d47c9103d16e0f82b33eb90316b982f205a7c76` |

To **punkty odniesienia** do późniejszego ponownego obliczenia hashy, nie kopie dowodów. Weryfikacja pełnej retencji i automatycznego katalogu manifestów pozostaje pracą przyszłej aplikacji.

## 6. Diagnostyka read-only STM32, CSI i CAN (2026-10-11)

| Etap | Źródło dowodu (odczyt MCP) | Granica potwierdzenia |
|---|---|---|
| STM32-01 | `udevadm`, `lsusb -t`, `/dev/ttySTM0`, `systemctl`, `journalctl`, Zephyr Core | Enumeracja USB i Router; nie firmware faktycznie działającego MCU |
| STM32-02 | `arduino-router-cli '$/version'` | Odpowiedź 0.10.0 jest z Routera, nie z MCU |
| CSI-01 | Device Tree, platform sysfs, `/dev/video*`, `lsmod`, `modinfo` | Konfiguracja kontrolerów; brak potwierdzonego capture |
| CAN-01 | `ip -details -statistics link show`, sysfs `can0`–`can2`, `udevadm`, `journalctl -k` | 3 kanały `gs_usb` DOWN/STOPPED, 0 TX/RX; brak aktywnej próby |

Pomiar wykonany bez zmian urządzenia. Dowody terminalowe pozostają w historii sesji MCP; nie zapisano nowych lokalnych plików dowodowych ani surowych logów w Git. Szczegóły w [raporcie 2026-10-11](VENTUNO_Q_STM32_CSI_CAN_READONLY_2026-10-11.md).

## 7. Ograniczenia rejestru i bezpieczeństwo

- Ścieżki są przypisane do konkretnego urządzenia i mogą stać się nieaktualne po reorganizacji NVMe.
- Surowe zdjęcia oraz dane, na których widać człowieka, pozostają lokalne. Nie dodawać do publicznego repo.
- Część dowodów (np. wynik GPU/PCIe/USB-C, brak ciągłego logu z `gphoto2 --shell`) pochodzi z wcześniej zanotowanych pomiarów. Raport szczegółowy jawnie zaznacza, gdzie brak pełnych logów.
- Nie wnioskować o długoterminowej stabilności, pełnym bezpieczeństwie robota lub możliwości radiometrii z samych testów fotograficznych.
- Nie uruchamiać powtórnych testów sprzętu, nie zmieniać firmware, systemu ani konfiguracji bez zatwierdzenia właściciela projektu.

Zobacz [raport VENTUNO](VENTUNO_Q_HARDWARE_VERIFICATION_2026-10-10.md) i [raport Sony](SONY_A6100_VERIFICATION_2026-10-10.md).
