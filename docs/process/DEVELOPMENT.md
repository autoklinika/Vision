# Zasady pracy — Vision

## Repozytorium

- Jedno repozytorium projektu: `autoklinika/Vision`; inne projekty pozostają odrębne.
- `main` jest stanem referencyjnym. Pierwsza inicjalizacja zatwierdzona przez właściciela projektu.
- Każda następna zmiana na gałęzi `feature/`, `fix/` lub `docs/` i przez PR; merge tylko po jednoznacznym zatwierdzeniu przez właściciela.
- PR musi opisywać zakres, ryzyka sprzętowe, testy, zgodność z Ubuntu/ARM64 i rollback.
- Obrazy produkcyjne, dane surowe i duże modele trzymamy poza Git (w przyszłości: dedykowana retencja/archiwizacja).

## Etapy weryfikacji

1. Odczyt i udokumentowanie stanu urządzenia.
2. Testy jednostkowe na mockach.
3. Testy integracyjne bez sterowania sprzętem.
4. Testy na rzeczywistych urządzeniach z uzgodnionymi ograniczeniami.
5. Odrębna zgoda na uruchomienie aktuatorów, urządzeń grzewczych i autonomicznego ruchu.

## Reguła obowiązkowa: eMMC vs NVMe

Wszystkie nowe pliki użytkownika i projektu Vision, włącznie z repozytorium Git, zdjęciami, wynikami, cache, plikami tymczasowymi, logami aplikacji i środowiskami deweloperskimi, **muszą** być zapisywane wyłącznie na `/srv/vision-data` (NVMe 1 TB). System i niezbędne pliki systemowe pozostają na eMMC.

PR dodający jakikolwiek zapis pliku musi wskazywać docelową ścieżkę i testować odmowę zapisu, gdy NVMe jest niedostępny; fallback na eMMC jest zabroniony. Normatywny kontrakt: [STORAGE_POLICY.md](../architecture/STORAGE_POLICY.md). Dokumentacja nie oznacza, że taka kontrola jest już wdrożona we wszystkich komponentach.

## Wrażliwe dane

- GitHub CLI przechowuje poświadczenia lokalnie na VENTUNO — nie kopiować `~/.config/gh/hosts.yml`.
- Nie commitować kluczy SSH, tokenów, plików `.env`, parametrów prywatnej sieci ani niezredagowanych logów sprzętowych.
- Przed publikacją raportu audytu usunąć numery seryjne i identyfikatory sprzętu, a także dane topologii sieci i wszelkie przypadkowo ujawnione sekrety.
- Ponieważ repozytorium jest publiczne, audyty i surowe zdjęcia domyślnie pozostają lokalne.

## Stan i odpowiedzialność

Dokumentacja planu nie oznacza wdrożenia. W raportach używamy rozróżnienia: PLAN / TEST / PASS / FAIL / BLOCKED / NOT TESTED.
