# GUI-02 — niezależny odbiór końcowy (2026-11-24)

**Decyzja: PASS dla izolowanego GUI-02; dopuszczony do PR.** Nie jest to odbiór produkcyjny, wdrożenie HTTPS ani zgoda na dystrybucję prywatnego brandingu.

Baza: GUI-01, commit 276e954. Poprawki Codexa odnoszą się do niezależnego audytu [GUI-02_INDEPENDENT_REVIEW_2026-11-24.md](GUI-02_INDEPENDENT_REVIEW_2026-11-24.md); szczegóły implementacji w [GUI-02_REMEDIATION_2026-11-24.md](GUI-02_REMEDIATION_2026-11-24.md).

## Zamknięcie ustaleń

- G02-R01 PASS: dostępny wskaźnik segmentowy oczekiwania klienta na odczyt raportu, bez wartości/procentów i READY. Testy pending, resolved, rejected, reduced motion i nawigacji diagnostycznej pozytywne.
- G02-R02 PASS: referencje SHA-256 pochodnych przypięte w kodzie, niezależnie od edytowalnego manifestu; importer sprawdza te same referencje. Deterministyczny PNG; podstawiony manifest wraz z obrazami oraz jednobajtowa mutacja odrzucone. Ograniczone odczyty, same-origin, przekierowania odrzucane.
- G02-R03 PASS: secure context wymagany przed pobraniem plików marki. Zdalny zwykły HTTP wykryty w Chromium; osobny komunikat, brak requestów brandingu, diagnostyka dostępna. HTTPS pozostaje wymaganiem wdrożeniowym, loopback działa lokalnie.

## Niezależnie powtórzone testy

| Test | Wynik |
| --- | --- |
| TypeScript, ESLint | PASS |
| Vitest | 12 PASS |
| Python importer | 5 PASS |
| Chromium DEV | 15 PASS, 4 SKIP (prywatne testy opt-in) |
| Build | PASS |
| Chromium build smoke | 11 PASS, 8 SKIP (4 prywatne, 4 wymagające dev module substitution) |
| Chromium prywatny oryginał | 4 PASS w osobnym przebiegu |
| npm audit | 0 zgłoszonych podatności |
| git diff --check | PASS |

Niezależne porównanie Pillow źródła z pochodnymi: dokładne przypięte SHA-256; 29 zdekodowanych klatek z identycznymi pikselami i opóźnieniami; 3490 ms, brak pętli, końcowa czarna klatka, kanoniczny PNG identyczny pikselowo z klatką 12.

Przed utworzeniem raportu sprawdzono 22 zmienione pliki: wyłącznie webgui/, brak prywatnego assetu, jego pełnego kodowania base64 i prywatnych ścieżek. Brak dist/local-brand. Nie zmieniano backendu, CI, konfiguracji VENTUNO ani urządzeń. Kod GUI pozostaje klientem bez operacyjnych komend i rzeczywistej autoryzacji.

## Ograniczenia

Oryginał i pochodne pozostają prywatne, wykluczone z Git i standardowego builda. Weryfikacja praw dystrybucji i procedury dostarczenia marki, prawdziwe API, walidacja schematów, uwierzytelnianie, HTTPS i Kiosk pozostają osobnymi zagadnieniami. Testy nie stanowią odbioru sprzętowego ani wieloprzeglądarkowego. Ostrzeżenie ESLint 9 pozostaje do odrębnego przeglądu. Merge dopiero po pozytywnym CI.
