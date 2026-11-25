# Zasady pracy — Vision

## Repozytorium

- Jedno repozytorium projektu: `autoklinika/Vision`; inne projekty pozostają odrębne.
- `main` jest kanoniczną bazą zatwierdzonego kodu i dokumentacji; nie jest gwarancją wdrożenia na stanowisku. [Bieżący indeks dokumentacji](../README.md).
- Nowa zmiana od aktualnego `origin/main`, na gałęzi `feat/`, `fix/`, `docs/` lub `lab/` zgodnie z [Repository Hygiene V1](REPOSITORY_HYGIENE_V1.md), i przez PR; merge tylko po jednoznacznym zatwierdzeniu przez właściciela. Stare nazwy `feature/` zachowujemy w historii.
- PR musi opisywać zakres, ryzyka sprzętowe, testy, zgodność z Ubuntu/ARM64 i rollback.
- Obrazy produkcyjne, dane surowe i duże modele trzymamy poza Git (w przyszłości: dedykowana retencja/archiwizacja).

## Rozdzielenie środowisk — decyzja właściciela 24.11.2026

- **VENTUNO Q (Vision)** jest jedynym lokalnym komputerem do programowania, budowania i testowania projektu Vision, w tym WebGUI. Prace prowadzić w izolowanym worktree od aktualnego `origin/main`, na NVMe, bez zmiany aktywnego środowiska stanowiskowego.
- **GitHub** pozostaje kanonicznym repozytorium, miejscem PR i CI; dopuszczalne jest tworzenie kodu backendu w środowisku Codex połączonym z GitHub.
- **AI Platform** jest oddzielnym projektem i komputerem przeznaczonym do zadań AI. Nie wolno tam klonować repozytorium Vision w celu programowania, uruchamiać Codexa dla Vision, budować GUI ani przechowywać lokalnych worktree/katalogów roboczych Vision. Odrębne zadania analizy danych AI wymagają osobnego uzgodnienia i nie zmieniają tej zasady.
- Przed każdą operacją lokalną potwierdzić tożsamość urządzenia i właściwy katalog NVMe. Gdy VENTUNO jest niedostępny, nie przenosić prac automatycznie na AI Platform; zgłosić blokadę lub skorzystać z odpowiedniego środowiska GitHub.
- Kod WebGUI pozostaje wyłącznie klientem Vision. Prywatne assety, pomiary i archiwa pozostają poza publicznym Git. Nie uruchamiać sprzętu przy zwykłych testach oprogramowania.

## Etapy weryfikacji

1. Odczyt i udokumentowanie stanu urządzenia.
2. Testy jednostkowe na mockach.
3. Testy integracyjne bez sterowania sprzętem.
4. Testy na rzeczywistych urządzeniach z uzgodnionymi ograniczeniami.
5. Odrębna zgoda na uruchomienie aktuatorów, urządzeń grzewczych i autonomicznego ruchu.

## Wrażliwe dane

- Poświadczenia GitHub pozostają w autoryzowanym środowisku; nie kopiować lokalnych plików poświadczeń ani włączać tokenów do komend/logów.
- Nie commitować kluczy SSH, tokenów, plików `.env`, parametrów prywatnej sieci ani niezredagowanych logów sprzętowych.
- Przed publikacją raportu audytu usunąć numery seryjne i identyfikatory sprzętu, a także dane topologii sieci i wszelkie przypadkowo ujawnione sekrety.
- Ponieważ repozytorium jest publiczne, audyty i surowe zdjęcia domyślnie pozostają lokalne.

## Stan i odpowiedzialność

Dokumentacja planu nie oznacza wdrożenia. W raportach używamy rozróżnienia: PLAN / TEST / PASS / FAIL / BLOCKED / NOT TESTED.
