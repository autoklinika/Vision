# ZASADA BEZWZGLĘDNA: dane użytkownika Vision wyłącznie na NVMe

**Status: BINDING / wymaganie architektoniczne od 2026-10-10.**

Właściciel projektu ustanowił następującą regułę: **eMMC VENTUNO Q służy do systemu operacyjnego i jego niezbędnych komponentów. Wszystkie pliki tworzone, pobierane lub przetwarzane dla projektu Vision jako dane użytkownika przechowujemy na NVMe 1 TB.** Dotyczy to także kodu źródłowego, dokumentacji, środowisk deweloperskich i plików tymczasowych aplikacji, a nie tylko zdjęć.

## Dyski i ścieżki

| Dysk | Przeznaczenie | Lokalizacja |
|---|---|---|
| eMMC | Ubuntu, kernel, oprogramowanie producenta, niezbędne biblioteki, systemowe konfiguracje i logi | systemowe punkty montowania |
| NVMe Lexar SSD PLAY 1 TB, ext4, VISION_DATA | wszystkie dane użytkownika związane z Vision | `/srv/vision-data` |

Docelowe lokalizacje na NVMe:

- `/srv/vision-data/projects/Vision` — fizyczne repozytorium GitHub, kod, dokumentacja, testy i buildy.
- `/home/arduino/Vision` — wyłącznie **symlink** zgodności z dotychczasowymi poleceniami i VS Code; dane w docelowym katalogu NVMe.
- `/srv/vision-data/captures` — fotografie oryginalne z Sony A6100.
- `/srv/vision-data/thermal` — źródłowe dane termowizyjne radiometryczne i metadane.
- `/srv/vision-data/mosaics` i `focus-stacks` — przetworzone obrazy i dane pośrednie.
- `/srv/vision-data/calibration`, `sessions`, `exports` — kalibracja, sesje, eksport.
- `/srv/vision-data/models`, `cache`, `tmp`, `logs`, `build` — modele, cache, pliki tymczasowe, logi **aplikacji Vision** i artefakty narzędzi deweloperskich.
- `/srv/vision-data/venvs` — wirtualne środowiska Pythona projektu.
- Dane Docker/Compose używane **przez aplikację Vision** (volume, bind mount, cache build): wyłącznie na NVMe, bez przenoszenia systemowego Docker Engine i bez zmiany globalnej lokalizacji danych Dockera bez osobnej decyzji.

## Wymaganie krytyczne: fail-closed

**Każdy proces Vision musi weryfikować, że `/srv/vision-data` jest rzeczywistym punktem montowania oczekiwanego NVMe (ext4, etykieta `VISION_DATA`) PRZED utworzeniem, pobraniem lub modyfikacją pliku użytkownika.**

Jeżeli NVMe nie jest zamontowany, tożsamość urządzenia nie pasuje, nośnik jest tylko do odczytu albo jest za mało miejsca — **odmówić zapisu i zgłosić czytelny błąd**. Nie wolno automatycznie przełączać się na eMMC, `/home/arduino` ani zwykły katalog `/srv/vision-data` pod spodem (gdy montowanie nie zadziała).

- Katalogów aplikacji na NVMe nie tworzymy przed walidacją montowania.
- Nie wystarczy samo `test -d /srv/vision-data` lub `df`; wymagany jest odczyt faktycznego mountpointu, urządzenia i filesystemu.
- Na starcie każdej sesji zapisu powtarzamy weryfikację (nie zakładamy, że mountpoint jest nadal obecny).
- Nowy moduł i każdy PR muszą zawierać dowód, że wszystkie ścieżki zapisu przechodzą przez politykę storage oraz test sytuacji „NVMe niedostępny”.
- `TMPDIR`, `XDG_CACHE_HOME`, build dirs, scratch space i cache modeli ustawiamy **dla procesów Vision** na ścieżki NVMe po weryfikacji montowania. Nie przestawiamy globalnie systemowego `/tmp` ani `/var`.
- Dane administracyjne systemu i poświadczenia usług, np. `~/.ssh` czy `~/.config/gh`, pozostają w lokalizacjach systemowo wymaganych; nie są artefaktami projektu Vision. W razie potrzeby rozszerzenia zakresu migracji wymagana jest osobna analiza bezpieczeństwa.
- Wewnętrzne zapisy Ubuntu, journald, aktualizacje pakietów i inne niezależne procesy systemowe nie są objęte zakazem; nie obiecujemy, że eMMC nie będzie nigdy zapisywane.

## Procedura migracji repozytorium

Skrypt: `scripts/storage/migrate_repo_to_nvme.sh`.

1. Otwórz VS Code przez USB-C / SSH, utrzymaj aktywny NVMe.
2. Uruchom skrypt z `--check` i sprawdź status git oraz wykryty nośnik.
3. Uruchom `--migrate`: kopiowanie repozytorium na NVMe, porównanie zawartości, przeniesienie starego katalogu na kopię awaryjną, utworzenie symlinka.
4. Sprawdź `git status`, `readlink`, `findmnt`, dostęp VS Code przez symlink i dalsze działanie Git.
5. Po osobnym potwierdzeniu usuń pozostawioną kopię z eMMC. Do tego czasu to **krótkotrwała kopia rollback**, nie właściwy katalog pracy.

Skrypt nie usuwa starej kopii samoczynnie. W razie błędu walidacji **nie kopiuje ani nie przenosi niczego**.

## Zakazy

- Brak danych zdjęciowych, modeli, raportów, repozytoriów, plików build oraz logów aplikacyjnych Vision na eMMC.
- Brak fallbacku na eMMC po błędzie montowania.
- Brak automatycznego formatowania, naprawiania lub montowania obcego dysku przez aplikację.
- Brak globalnej migracji systemowych katalogów Ubuntu w ramach tej decyzji.

**Źródło prawdy:** ten dokument i testy polityki storage są obowiązkowe dla przyszłych modułów Vision. Zmiana zasad wyłącznie na wyraźne polecenie właściciela projektu.
