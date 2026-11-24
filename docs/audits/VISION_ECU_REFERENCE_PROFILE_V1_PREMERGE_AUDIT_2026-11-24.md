# Vision ECU Reference Profile V1 — audyt i odbiór offline

**Data:** 2026-11-24.
**Status:** implementacja offline przygotowana jako kandydat do osobnego Draft PR, nie wdrożona i nie scalona.
**Dokument źródłowy:** docs/decisions/ADR_VISION_ECU_REFERENCE_PROFILE_V1_2026-11-24.md (ACCEPTED, PR #47 scalony do main).
**Zależność kodowa:** osobny Draft PR #46 ECU Profiles V1, bez zmiany jego kontraktów.
**Urządzenia:** zero działań na VENTUNO, NERO, CAN, Sony, Luxonis lub zamrożonym VGP V1.

## Cel

Jeden kompletny model ECU Reference Profile jako (a) nominalna, zatwierdzona wiedza o wariancie ECU i (b) deklaratywna instrukcja dla Vision, oddzielona od wykonawczego Core ECUProfile i od wyników konkretnego egzemplarza.

## Zakres implementacji

- Wszystkie 15 przyjętych sekcji obsługiwane przez zamknięty schemat JSON V1.
- Pusty oryginalny szablon V1-PROPOSED jest czytelny do podglądu, lecz nie daje gotowości.
- Wersjonowane, głęboko niezmienne snapshoty oraz powtarzalny SHA-256 treści.
- Readiness per stan ECU + receptura + zakres zgody, z walidacją wymaganej geometrii, źródeł, kalibracji, cech identyfikacyjnych, polityk, widoków, ROI i referencji do plików.
- Jawny katalog z wyborem dokładnie family/variant/revision, bez automatycznego podmieniania wariantu.
- Offline AssetStore weryfikuje rzeczywiste pliki przez SHA-256, rozmiar, rodzaj MIME i zamknięty katalog lokalny; nie pobiera danych z sieci.
- Trwały ReferenceReleaseStore publikuje kanoniczny profil z zasadą no-overwrite; weryfikuje spójność wersji i hashów przy odczycie.
- Kompilacja zatwierdzonej receptury PHOTO_INSPECTION wiąże Reference Profile z zatwierdzonym ECURecord i istniejącym Core ECUProfile; sprawdza geometrię, recepturę, identyfikatory ujęć, kwaterniony, obszary PCB i profile kalibracyjne; przekazuje tylko zatwierdzone wybrane ROI. Obowiązujące S01–S11 nie są omijane.
- Receptury Thermal i inne są zachowane w strukturze danych i weryfikacji gotowości, lecz na tym etapie NIE dostają ścieżki wykonawczej w compiler.py. Brak potwierdzenia rzeczywistej radiometrii.
- GUI jest przyszłym etapem; backend udostępnia metadane do listy i podglądu, nie implementuje okien programu.
- ETC3 nadal nie zawiera zatwierdzonej geometrii, zdjęć ani zaakceptowanego wariantu. Dane ETC3 w katalogu z PR #46 pozostają DRAFT.

## Wykryte i odtworzone przypadki niepoprawnego działania

| Regresja | Problem przed poprawką | Oczekiwany stan |
| --- | --- | --- |
| R01 | PASS mimo braku metrycznej cechy identyfikacyjnej, niepewności, wymaganych cech lokalizacji i polityk RGB-D | NOT_READY |
| R02 | Receptura PHOTO mogła korzystać z ujęć należących do innej receptury w tym samym stanie fizycznym | NOT_READY / odrzucenie niespójnej referencji |
| R03 | Kompilacja przenosiła do Core dodatkowe widoki i regiony PCB poza zakresem zatwierdzonej receptury | Odrzucenie dodatkowych widoków; profil zawiera tylko wybrane i zweryfikowane ROI |
| R04 | ReleaseStore mógł opublikować kanoniczny plik ASCII >512 KiB, którego nie mógł później odczytać | Odrzucenie przed utworzeniem pliku i zablokowaniem rewizji |
| R05 | Globalna i recepturowa polityka jakości fotografii mogły zostać pominięte, choć profil zawierał ich identyfikatory | Obie grupy polityk są obowiązkowo sprawdzane, a komplet jest przekazywany w ExecutionBundle |
| R06 | Receptura fotograficzna mogła osiągnąć PASS bez rewizji manifestu zasobów | Wymóg niepustej rewizji manifestu związanego z zatwierdzonym profilem |

Regresje R01–R04 najpierw wykazały błąd (4 testy RED), a następnie przeszły po naprawie. Regresje R05–R06 również odtworzono przed korektą (4 kolejne testy RED). Dodano również szczegółowe warianty brakujących dowodów, niejednoznaczności wariantu, ujęć opcjonalnych i wieloobszarowego PCB.

## Wynik testów i ograniczenia

- Przebieg offline: **330 / 330 testów PASS**, w tym wcześniejsze testy Vision, kod katalogu ECU, moduł Thermal i nowe testy Reference Profile.
- Uruchomiono pełne unittest discover oraz compileall w odizolowanym Docker z --network none, --read-only, --cap-drop ALL; żadnych urządzeń ani sterowników.
- Potwierdzono brak zmian w src/vision_core i src/vision_modules/ecu_profiles.
- SHA-256 świadczy o integralności, nie uwierzytelnia recenzenta, oprogramowania sensora ani rzeczywistego rozpoznania ECU. Magazyn plików nie jest certyfikowanym WORM.
- Bundle wykonawczy nie uruchamia migawki, trajektorii ani ruchu robota.
- Fizyczne potwierdzenie wariantu ECU i stanu otwarcia, aktualne TF, planowanie MoveIt, stabilność rejestracji oraz odrębne bramki S01–S11 będą realizowane przez zaufaną integrację. Testy offline tego nie zastępują.

**Warunek kolejnego etapu:** zaakceptowanie oddzielnego PR kodu po zielonym CI i przeglądzie; implementacja GUI oraz kompletnego profilu ETC3 z rzeczywistymi pomiarami i zdjęciami pozostają do osobnej decyzji.
