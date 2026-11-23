# Vision — zasady utrzymania lokalnego repozytorium i GitHub

**Obowiązują od 23.11.2026 po odbiorze Vision Guided Positioning V1.**

## Jeden aktualny fundament

- main to kanoniczna gałąź zaakceptowanych zmian i dokumentacji, a nie obraz uruchomionych usług sprzętowych.
- Nowe prace startują z aktualnego origin/main; preferujemy jeden niewielki PR na zagadnienie. Nie rozbudowujemy kolejnych eksperymentów w nieprzejrzyste wielopiętrowe stacked PRs.
- Zamrożona baza laboratoryjna V1 znajduje się prywatnie na VENTUNO jako snapshot tylko do odczytu z sumami SHA-256; jej publikowanie wprost do otwartego GitHuba jest zabronione.
- Nie modyfikujemy działającej konfiguracji AgileX, MoveIt i Luxonis tylko po to, by uporządkować Git.
- C9 i podobne własne wykonawce ruchu pozostają archiwalnymi eksperymentami, nie docelowym kodem.

## Publiczne vs prywatne

| GitHub (publicznie) | Prywatny NVMe/NAS |
|---|---|
| Zanonimizowane ADR, kontrakty, małe algorytmy i syntetyczne testy | Raw RGB, RAW16, PointCloud, obrazy rzeczywistych ECU |
| Stan architektury i ogólne kryteria odbioru | Pełna geometria konkretnego stanowiska, kalibracja TF, seriale |
| Testy offline bez danych klienta | Rejestry ruchów fizycznych, logi sprzętu, profile runtime i snapshoty |
| Programistyczne przykłady bez dostępu do aktuatorów | Dane do odtworzenia rzeczywistego kontrolera i HOLD |

Przed publikacją: przegląd git diff --cached i weryfikacja, że zmiana nie zawiera danych prywatnych.

## Stare PR i worktrees

- Zachowujemy historię i stare gałęzie; nie używamy force-push do nadpisania materiału dowodowego.
- PR-y ze starym alternatywnym executorem, własnym Camera Service/Perception Engine lub jawnie historycznymi dokumentami można zamknąć jako superseded, dodając komentarz i odwołanie do V1. Zamknięty PR pozostaje dostępny.
- Przydatne moduły replay, precyzyjnej wizji i testów sprzętu przenosimy do nowych, ograniczonych PR od main po osobnym przeglądzie; nie scalamy automatycznie starych stosów.
- Stary katalog Git worktree można usunąć tylko po sprawdzeniu: czystego statusu z untracked, obecności gałęzi na GitHub i braku zależności usług działających na NERO. Jeśli występują zależności — zachować jako archiwum.
- Nie używać git clean -fdx w katalogach laboratoryjnych ani nie kasować danych z NVMe dla kosmetycznego porządku.

## Nazwy przyszłych gałęzi

- docs/temat-YYYYMMDD — dokumentacja i ADR.
- feat/modul-vN — nowe zaakceptowane moduły.
- lab/temat-YYYYMMDD — izolowane eksperymenty.
- archive/temat-YYYYMMDD — materiał referencyjny, bez automatycznego merge.

Wydania V1 i kolejne traktujemy jako laboratoryjne, dopóki nie zakończymy niezależnego odbioru uruchamiania, kalibracji i procedur ruchu.
