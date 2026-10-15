# Vision Thermal v0.6 — manifest kodu i procedura przekazania

**2026-10-15 · repo publiczne: autoklinika/Vision · status: raport opublikowany, prywatny kod oczekuje na repo docelowe**

## Lokalny commit wersji zamrożonej

- Repo Git gotowe do późniejszego wypchnięcia do **prywatnego** repozytorium: `/srv/vision-data/experiments/thermal-freeze-20261015/PRIVATE_GIT_READY/`.
- Branch: `freeze-v0.6`.
- Commit: `5e75391a72eae1accaef8b5cf6594eb98e27c054`.
- Tag: `v0.6-freeze-20261015`.
- Liczba plików objętych snapshotem Git: 48.
- Kod w repo lokalnym zawiera źródła aplikacji, testy, historię poprzednich wersji i `third_party/IR-Py-Thermal` wraz z licencją **GPL-3.0**. Nie obejmuje laboratoryjnych plików obrazu ani binarnych bibliotek SDK InfiRay.

## Kontrola odtwarzalności

- Git bundle `Vision_Thermal_v0.6_PRIVATE_GIT_20261015.bundle` — SHA-256: `4665d5eec2a6f54173a98e8b9cd610bdbd29a449964b474e10ca29ede97b8748`. Test `git bundle verify` i klonowania z bundle: **PASS**.
- Archiwum źródeł `Vision_Thermal_v0.6_source_private_20261015.tar.gz` — SHA-256: `3c8db1eef5d50343a7fcc02fafbf6fed6c9babfe0d2fedcc712cd5692280f5a2`.
- Archiwum surowych danych warsztatowych `Vision_Thermal_v0.6_lab_data_LOCAL_ONLY_20261015.tar.gz` — SHA-256: `e0cc18f487195a789a0d7364d2cd28aa3e5b731ff1e4d07adf01bb4ad47433d3`.
- Obraz kontenera `Vision_Thermal_v0.6_runtime_base_ARM64_20261015.tar` — SHA-256: `fe863a1afd5c6566e0093b956a7bf0027999509895accec4aa25f26f7774c642`.
- Manifest kontrolny: `/srv/vision-data/experiments/thermal-freeze-20261015/SHA256SUMS`; wszystkie cztery pliki zweryfikowano: **PASS**.

## Granica upubliczniania

Repo `autoklinika/Vision` jest publiczne i ma otrzymać wyłącznie dokumentację techniczną. Źródła GPL i migawki laboratoryjne są przechowywane lokalnie. Aby wysłać źródła Git na GitHub, potrzebne jest osobne repozytorium typu **Private** (przykładowa nazwa: `autoklinika/Vision-Thermal-Private`). Po założeniu repozytorium można przekazać powyższy commit i tag bez scalania do `main` publicznego Vision.

**Nie należy umieszczać obrazu kontenera ~294 MB ani surowych danych laboratoryjnych w publicznym Git.** Zabezpieczenie pełnej kopii tych artefaktów pozostaje na NVMe i wymaga osobnej strategii backupu poza hostem. Aktywna aplikacja DEV pozostaje działająca, lecz nie dodajemy nowych funkcji.
