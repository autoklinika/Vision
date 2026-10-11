# VENTUNO Q — audyt bazowy 2026-10-10

**Status:** część 1 (inwentaryzacja tylko do odczytu), raport interpretacyjny.  
**Data próbki:** 2026-10-10 16:38:18 UTC.  
**Źródło:** raport operatora z `scripts/audit/vision_audit_v1.sh`; nie wykonano dodatkowych poleceń na sprzęcie.  
**Prywatność:** raport celowo pomija adresy IP, BSSID, numery seryjne, identyfikatory USB/PCI, sekrety i topologię sieci. Surowy log nie jest wersjonowany w publicznym repozytorium.

## Wnioski wykonawcze

- System Ubuntu ARM64, kernel Qualcomm i usługi bazowe są uruchomione; podczas próbki nie stwierdzono usług w stanie `failed`.
- CPU (4 × Cortex-A55, 4 × Cortex-A78C) i pamięć RAM zostały prawidłowo wykryte; zużycie pamięci przy niewielkim obciążeniu jest niskie.
- Fizyczny NVMe o pojemności około 1 TB **istnieje**, ale jego jedyna partycja ma system NTFS i nie jest zamontowana. Nie formatować przed inwentaryzacją danych i osobną zgodą.
- Urządzenia FastRPC oraz biblioteki Qualcomm są obecne, ale brak dowodu uruchomienia inferencji QNN/Hexagon.
- Sterownik graficzny /dev/dri i biblioteka Vulkan Freedreno są obecne; brak testu rzeczywistej akceleracji Adreno.
- OpenCV `cv2` nie jest dostępne w systemowym Pythonie; libgphoto2 jest obecne, ale Sony A6100 nie zostało przetestowane.
- Audyt bazowy **nie** oznacza zaliczenia testów GPU, NPU, kamer, robotyki ani termowizji.

## Macierz stanu

| Obszar | Stan | Dowód / ograniczenie |
|---|---|---|
| OS | PASS (identyfikacja) | Ubuntu 24.04.4 LTS, aarch64; Linux 6.8.0-1084-qcom |
| CPU | PASS (identyfikacja) | 8 rdzeni: 4 × Cortex-A55 (maks. ~1,96 GHz), 4 × Cortex-A78C (maks. ~2,36 GHz) |
| RAM | PASS (odczyt) | 14 GiB widoczne dla OS; 1,7 GiB używane, 13 GiB dostępne; brak swap |
| Kernel/usługi | PASS (próbka) | `ssh`, `tailscaled`, `NetworkManager`, `docker` aktywne; zero usług `failed` |
| eMMC | PASS (wykrycie) | Urządzenie ~59,3 GiB; root ext4 ~55 GiB, ~16 GiB zajęte, ~38 GiB wolne |
| NVMe | PARTIAL | Lexar SSD PLAY 1TB, ~953,9 GiB; NTFS; niewmontowany; brak testu danych/W-R |
| GPU | NOT VERIFIED | `/dev/dri` obecne i biblioteka `libvulkan_freedreno.so` widoczna, bez sprawdzenia aktywnego adaptera/inferencji |
| Hexagon NPU / DSP | NOT VERIFIED | `/dev/fastrpc-cdsp`, `/dev/fastrpc-gdsp0`, biblioteki FastRPC; brak testu wykonania QNN |
| QNN runtime | NOT VERIFIED | Nie pojawił się w `ldconfig -p`; to nie wyklucza instalacji poza ścieżkami loadera |
| V4L2 / Media | PARTIAL | `/dev/video32`, `/dev/video33`, `/dev/media0` istnieją; `v4l2-ctl` niezainstalowany, nie wiadomo do czego służą |
| Sony A6100 | NOT TESTED | libgphoto2 2.5.31 jest obecne; brak fizycznego testu sterowania i wyzwalania |
| OpenCV | MISSING (system Python) | Python 3.12.3, `importlib.util.find_spec('cv2')` = false; nie wnioskujemy o osobnych virtualenv/containers |
| Temperatura | PASS (próbka bez obciążenia) | Odczytane strefy ~35,7–39,7 °C; obciążenie loadavg ~0,04 |
| Termowizja radiometryczna | NOT TESTED | Brak wybranego i podłączonego urządzenia oraz danych per piksel |
| Robot / unikanie kolizji | NOT TESTED | Brak zatwierdzonego robota, systemu E-stop i testów aktuacji |

### Ryzyka i zależności

**NVMe:** nie zakładać, że NTFS jest pusty. Przed zmianą systemu plików: odczytać etykietę i montowania, ustalić własność danych i wykonać kopię, jeśli potrzebna. Propozycja ext4 na `/srv/vision-data` wymaga osobnej akceptacji i planu wycofania; **żaden format ani mount nie został wykonany**.

**GPU/NPU:** nie interpretować obecności urządzeń, plików .so lub biblioteki Vulkan jako dowodu kompatybilności modeli. Potrzebny smoke test na rzeczywistym GPU i QNN/Hexagon z zapisaniem wersji runtime, backendu, wyniku i czasu.

**RAM / swap:** 14 GiB RAM to budżet pamięci widocznej dla Linuxa; brak swap może wymusić przetwarzanie kafelkowe dla pełnorozdzielczych mozaik i focus stackingu. Nie włączać swap bez pomiarów.

**Kamera:** porty /dev/video* mogą należeć do wewnętrznych podsystemów. Nie przypisujemy ich arbitralnie do aparatu lub MIPI.

**System OEM:** nie wykonywać `do-release-upgrade`, `apt full-upgrade`, aktualizacji kernela lub podmiany SDK bez osobnej analizy zgodności Arduino/Qualcomm. Nie instalować losowych binarek QNN.

## Plan dalszych testów (każdy osobno, bez zmiany systemu)

**A. NVMe (inwentaryzacja bez zapisu)**

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINTS,MODEL
sudo blkid /dev/nvme0n1p1
findmnt /dev/nvme0n1p1 || true
```

Cel: potwierdzić dysk, typ partycji i stan montowania. `blkid` może nie pokazać informacji o zawartości plików — przed formatowaniem konieczny dodatkowy, kontrolowany podgląd danych (preferowany mount tylko do odczytu, dopiero za zgodą).

**B. GPU / urządzenia** (read-only)

```bash
ls -la /dev/dri
lsmod | grep -Ei 'msm|kgsl|drm|qcom' || true
command -v vulkaninfo || true
```

Następnie opracować test rzeczywistego renderingu/compute z identyfikacją GPU, nie `llvmpipe` ani software rasterizer. Nie instalować narzędzi przed osobną decyzją.

**C. Hexagon / QNN — discovery** (read-only)

```bash
id -nG
ls -l /dev/fastrpc* 2>/dev/null
find /opt /usr/local -maxdepth 5 \( -iname '*qnn*' -o -iname '*hexagon*' \) -print 2>/dev/null | head -n 80
```

Cel: znaleźć oficjalny runtime i dostęp do urządzeń. Dalszym krokiem jest przykładowe wykonanie modelu przez właściwy backend (do uzgodnienia).

**D. Kamery** — po wyborze/podłączeniu: identyfikacja V4L2 i sterowania Sony A6100, RAW/JPEG, wyzwalanie, zapis metadanych i czasy. Brak instalacji i testów w tej fazie.

## Gate następnego etapu

1. Zatwierdzić sposób wykorzystania NVMe po upewnieniu się, że nie utracimy istniejących danych.
2. Sprawdzić GPU i NPU bez naruszania fabrycznych pakietów.
3. Przeprowadzić test podłączonego Sony A6100.
4. Dopiero potem zaprojektować/wybrać pakiety OpenCV, narzędzia foto i opcjonalny lekki model detekcyjny.

**Stan audytu:** `BASELINE-CAPTURED` / `HARDWARE-ACCELERATION-NOT-YET-VERIFIED`. Żadne działanie na actuatorach ani ruch ramienia nie jest dozwolone na podstawie samego raportu.
