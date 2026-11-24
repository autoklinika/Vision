# GUI-02 — niezależny audyt kodu (2026-11-24)

**Decyzja: CONDITIONAL / HOLD przed PR i merge.** Architektura CLIENT ONLY zachowana. Trzy ustalenia wymagają poprawki lub jawnego uzgodnienia. Audyt dotyczy zmian roboczych na feat/webgui-startup-v1, baza 276e954. Nie jest to odbiór produkcyjny.

## Wyniki powtórzone niezależnie

- Typecheck, lint, build: PASS.
- Vitest: 9/9; Python importer: 3/3.
- Chromium dev: 13 PASS, 1 skip (prywatny oryginał).
- Chromium build: 11 PASS, 3 skip (2 testy z podmianą modułu dev i prywatny oryginał).
- Chromium prywatny oryginał: 1/1 PASS w osobnym przebiegu.
- npm audit: 0 zgłoszonych podatności; znane ostrzeżenie ESLint 9.
- Niezależne porównanie Pillow: SHA-256 oryginału zgodne; wszystkie 29 klatek GIF i opóźnienia identyczne; suma 3490 ms; brak pętli; końcowa klatka czarna; PNG identyczny pikselowo z klatką 12.
- Brak prywatnych assetów w indeksie i dist; wszystkie zmiany ograniczone do webgui/. Brak modyfikacji backendu, konfiguracji urządzeń i usług.

## Ustalenia

### G02-R01 — brak wskaźnika postępu (P2, niezgodność UX)

Startup.tsx:85–88 oraz startup.css. Specyfikacja WebGUI V1, sekcja 3B (linie 41 i 54), wymaga segmentowego paska, z indeterminate, gdy brak wiarygodnego miernika. Aktualny raport ma tylko opis i tabelę; w Chromium liczba elementów progress/[role=progressbar] wyniosła 0. Należy dodać klasyczny wskaźnik oczekiwania na raport, nie wymyślać procentów; po odpowiedzi lub błędzie jednoznacznie zakończyć oczekiwanie klienta i nadal prezentować UNKNOWN/UNAVAILABLE. Rozdzielić etykiety oczekiwania na raport i gotowości urządzeń. Dodać test pending, resolved i rejected.

### G02-R02 — manifest nie zapewnia autentyczności pochodnych (P2)

brand.ts:17–26. Kod porównuje deklarowany hash źródła ze stałą, ale sprawdza hashe pochodnych względem wartości z tego samego, modyfikowalnego manifestu. W niezależnym teście Chromium podstawiono istniejący syntetyczny GIF i PNG 8×8 oraz ich poprawne hashe; manifest deklarował hash oryginału i 3490 ms. Obraz został zaakceptowany jako Original Vision handwriting intro. Nie jest to ścieżka do sterowania systemem; to wada integralności tożsamości wizualnej. Potwierdza też ograniczenie obecnego testu fixture. Związać pochodne z zaufanym punktem odniesienia (np. przypięty hash GIF i deterministyczny hash pikseli/kanonicznego PNG lub manifest podpisany zaufanym kluczem); fixture testowe wstrzykiwać przez odrębny mechanizm testowy, bez produkcyjnego obejścia. Test zmienionych bytes+manifest musi odrzucać podmianę.

### G02-R03 — zwykły zdalny HTTP nie wyświetla intro (P2, kontrakt wdrożeniowy)

brand.ts:10: crypto.subtle wymaga bezpiecznego kontekstu. W Chromium uruchomiono ten sam build i autentyczny lokalny asset na tymczasowym serwerze loopback: localhost/127.0.0.1 -> secure=true, subtle=true, intro działa. Host testowy vision-audit.test odwzorowany na ten sam serwer -> secure=false, subtle=false, intro pomijane z ogólnym komunikatem unavailable or corrupt. To ograniczenie Web Crypto, nie uszkodzenie assetu. Wymagać HTTPS dla zdalnego klienta, zachować lokalny loopback, jawnie rozróżnić komunikat insecure context i dodać test. Nie wyłączać weryfikacji dla HTTP. Konfiguracja HTTPS i dystrybucja assetu pozostają do odrębnego odbioru wdrożeniowego.

## Dalsze bramki i ograniczenia

- readClientReport w report.ts:5–7 sprawdza jedynie source; przed GUI-07 trzeba wprowadzić walidację całego rzeczywistego schematu na granicy API oraz obsługę aktualności/reconnect. Obecne adaptery są zamkniętymi lokalnymi stubami. Nie jest to stwierdzenie awarii działającego API, bo transportu jeszcze nie ma.
- Ekran logowania jest wyłącznie prezentacją; rzeczywiste uwierzytelnienie i polityka dostępu do danych przed logowaniem wymagają GUI-07/08.
- Domyślny publiczny build z założenia nie zawiera animacji, także po lokalnym imporcie. Oryginał jest zweryfikowany prywatnie; brak zatwierdzonych praw dystrybucji i procedury wydania assetu. Nie publikować.
- Audyt nie zmienił kodu implementacji; dodano wyłącznie ten raport. Nie commitowano ani nie publikowano. Po korektach wykonać ponownie testy dev/build i prywatnego oryginału oraz testy regresji R01–R03.

## Decyzja

CLIENT ONLY: PASS. Testy istniejące: PASS w zakresie uruchomionych przypadków. GUI-02 jako kompletny pakiet: HOLD do zamknięcia R01–R03. Brak odbioru na VENTUNO, rzeczywistego API, auth, Kiosk lub sprzętu.
