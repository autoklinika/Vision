# GUI-02 — remediacja G02-R01–R03 (2026-11-24)

Lokalny zapis wykonawcy na `feat/webgui-startup-v1`, bez commita, push, merge i publikacji. Nie jest niezależnym odbiorem ani zmianą decyzji HOLD z historycznego `GUI-02_INDEPENDENT_REVIEW_2026-11-24.md`. Oba wcześniejsze raporty pozostawiono bez zmian. Przeczytano raport niezależny, GUI-02_AUDIT, ADR-VISION-WEBGUI-001 i specyfikację UX V1. Zastane niecommitowane zmiany zachowano; zakres niniejszej korekty wyłącznie `webgui/`, R01–R03.

## Zmiany

- **R01:** segmentowy granatowy wskaźnik Win98 wyłącznie podczas oczekiwania na raport wybranego adaptera; `role=progressbar`, dostępna nazwa/opis, brak wartości procentowej. Reduced motion zatrzymuje ruch segmentów. Po resolve/reject wskaźnik znika, komunikat rozróżnia zakończenie odczytu klienta od inicjalizacji/gotowości systemu. UNKNOWN/UNAVAILABLE pozostają jawne, diagnostyka dostępna także przy nigdy nierozwiązanym odczycie.
- **R02:** zaufana referencja w kodzie `src/startup/brand-reference.json`, wspólna dla importera i przeglądarki, niezależna od manifestu lokalnego. GIF przypięty do dokładnego SHA `dc95e8dc36505189fbb185d0b779a9874d2e4a1d49b55c45a4a4b7a73c430e9b`. PNG ma deterministyczne kodowanie RGB8/filter 0/stored DEFLATE, bez metadanych i zależności od wersji kompresora; SHA `65f1e7f2f909691467d7e4752b909b53676953043555c99e30a09cd6a2a4f7ea`. Zastępuje poprzednie kodowanie PNG o SHA `7f26b139db1677b310db154be14e7136e2bb1fa41c0a39b58551700ab27ae747`, zachowując piksele klatki 12. Importer sprawdza obie pochodne przed zapisem. Syntetyczne fixture nie są już akceptowane jako autentyczny znak. Brak produkcyjnego obejścia URL/env/query; wstrzykiwanie odpowiedzi adaptera odbywa się tylko przez testową podmianę modułu w Playwright dev, mocki fetch tylko w Vitest.
- **R03:** kontrola secure context przed fetch/digest. Dostępny komunikat odróżnia niezabezpieczony HTTP od braku/uszkodzenia assetu. Zdalnie wymagane HTTPS, lokalnie dopuszczalny loopback. Test używa rzeczywistego origin `http://vision-audit.test`, którego żądania Playwright przekazuje do lokalnego serwera: Chromium zwraca `isSecureContext=false`, brak requestów brandingu, diagnostyka działa. Bez wyłączania zabezpieczeń przeglądarki, TLS i zmian konfiguracji hosta.
- Odczyty strumieniowe ograniczone do 2048 bajtów manifestu / 300000 bajtów assetu, same-origin, przekierowania odrzucane. Błąd dekodowania usuwa obrazy ze stanu i zwalnia blob URLs. Limit czasu opcjonalnego assetu pozostaje 2 s.

## Faktyczne wyniki

Wszystkie komendy npm i Chromium z cache lokalnym pakietu (`.npm-cache`, `.browser-cache`), bez instalacji globalnych, sudo i osłabiania sandboxa.

| Sprawdzenie | Wynik |
| --- | --- |
| `npm run typecheck` | PASS |
| `npm run lint` | PASS |
| `npm test` | 12 PASS (4 pliki) |
| `python3 -B tests/test_prepare_brand.py` | 5 PASS; niezależne syntetyczne dane |
| Import autoryzowanego oryginału | PASS; SHA źródła zgodne, wszystkie 29 klatek i opóźnienia identyczne, 3490 ms, brak pętli |
| Ponowny import + porównanie | PASS; wszystkie 3 pliki identyczne bajtowo; PNG identyczny pikselowo z klatką 12 źródła |
| Chromium dev | 15 PASS / 4 SKIP (prywatne testy opt-in) |
| `npm run build` | PASS |
| Chromium build smoke | 11 PASS / 8 SKIP (4 prywatne, 4 wymagające testowej podmiany modułu dev) |
| `GUI_PRIVATE_ORIGINAL=1 … --grep 'private original'` | 4 PASS: odtwarzanie i wymiary, Skip, reduced motion, mutacja jednego bajtu GIF |
| `npm audit --registry=https://registry.npmjs.org/` | 0 podatności |
| `git diff --check` | PASS |
| Zakres, indeks Git, pliki nieignorowane i dist | Wyłącznie webgui; brak bajtów źródła/pochodnych i ich pełnych kodowań base64; brak poprzedniego PNG według SHA; brak dist/local-brand |

Regresje GUI-01: wszystkie 4 testy Chromium przeszły zarówno dev, jak i build. R01: pending widoczny także przy 360×640, bez aria-valuenow, reduced motion bez animacji, przycisk diagnostyki w viewport; osobne przejścia pending→resolved/rejected kończą wskaźnik bez READY/procentów. R02: podmienione obrazy z odpowiadającymi im hashami manifestu odrzucane; jednobajtowy niepoprawny asset ze zaufanym manifestem odrzucany; prywatny GIF zmieniony dokładnie o jeden bajt odrzucany. R03 sprawdzono w dev i build. Testy jednostkowe dodatkowo sprawdzają brak fetch w insecure context, granicę rozmiaru i politykę redirect/same-origin.

Prywatne testy bez screenshots/video/trace. Standardowe fixture zawierają tylko niezależną geometrię 8×8; nie dodano prywatnych bajtów. Oryginał tylko odczytano. Pochodne i manifest pozostają lokalnie ignorowane w `public/local-brand/`. Build ich nie kopiuje. Sprawdzono diff plików śledzonych oraz nowe pliki implementacji/testów. Brak zmian backendu/CI, sprzętu, VENTUNO, auth i realnego API. Testy zachowują kontrolę braku zewnętrznych requestów runtime i żądań zapisu.

## Pozostałe ograniczenia / bramki

Dystrybucja prywatnego znaku nadal **blokuje wydanie z brandingiem**: prawa i procedura dostarczenia wymagają osobnej zgody. HTTPS zdalny jest wymaganiem wdrożeniowym, nie wdrożono TLS. Testy nie potwierdzają odbioru sprzętu, produkcji, Kiosk ani uwierzytelnienia. Zaufany kod aplikacji/referencja wymagają integralności procesu wydania; hash manifestu nie chroni przed zastąpieniem samego kodu aplikacji. Nie wykonywano macierzy wielu wersji Pillow/przeglądarek; przypięty hash odrzuci ewentualny odmienny wynik dekodera.

Walidację rzeczywistego pełnego schematu, aktualność i reconnect pozostawiono do GUI-07; istniejące adaptery są zamkniętymi lokalnymi stubami. Nie tworzono nowego schematu API. Następny niezależny przegląd i decyzja supervisor pozostają wymagane; ten zapis nie deklaruje niezależnej akceptacji ani zgody na merge.
