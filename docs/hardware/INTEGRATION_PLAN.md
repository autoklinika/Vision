# Integracja urządzeń — plan weryfikacji i stan

**Aktualizacja:** 2026-10-10. Statusy dotyczą wyłącznie przeprowadzonych prób, nie ogólnej kompatybilności wszystkich akcesoriów.

## Sony A6100 — fizycznie przetestowany, PASS warunkowy

Sony ILCE-6100A jest podłączany przez USB w trybie PC Remote. Zweryfikowano sterowanie PTP bez `sudo`, wykonywanie JPEG 24 MP, pobieranie RAW+JPEG na NVMe, rzeczywisty podgląd USB 1024×680 i serię zdjęć.

**Wyniki stabilności:**
- STAB-01 i STAB-03: **FAIL** — szybkie kolejne osobne sesje PTP czasami kończyły się `Could not capture`, nawet z `exit code=0` i niezależnie od AF-A/MF.
- STAB-04: **PASS 2/2** w jednej sesji.
- STAB-05: **PASS 10/10** w jednej sesji z odstępami ≥3 s.
- STAB-06: **PASS 4/4** w osobnych sesjach z odstępami ≥10 s.
- Near/Far: polecenia przyjęte, ale fizyczne przesunięcie ostrości **UNVERIFIED**; focus stacking odłożony do testu z obiektywem makro.
- RAW: nagłówek i pobranie pliku ARW **PASS**, pełna dekodowalność danych sensora **UNVERIFIED**.

**Decyzja dla przyszłego adaptera (nie wdrożony):** preferować trwałą sesję PTP, początkowy konserwatywny odstęp 10 s, walidację pliku i logu oraz fail-closed. Nie traktować samego kodu wyjścia gPhoto2 jako dowodu zdjęcia. Live View nie zastępuje niezależnych zabezpieczeń robota.

Raport: [SONY_A6100_VERIFICATION_2026-10-10.md](SONY_A6100_VERIFICATION_2026-10-10.md). Dowody zdjęciowe i logi przechowujemy poza Git.

### Rozszerzenie 2026-10-13 — HDMI/UVC oraz bezpośrednie Wi-Fi Sony

Rzeczywista weryfikacja przyniosła dwa dodatkowe kanały komunikacji, **bez wdrożenia Vision Core**:

- **HDMI → MacroSilicon USB UVC:** 1920×1080 MJPEG przy około 30 FPS, prawdziwy obraz Sony po około 2,1 s rozruchu w jednym zmierzonym przebiegu; wcześniejsze krótkie sesje zwracały pasy testowe. Rekomendowany ciągły stream i niezależne sprawdzanie gotowości obrazu; źródło opóźnienia pozostaje nierozstrzygnięte.
- **Druga karta Wi-Fi → Sony Camera Remote API:** połączenie WPA2, DHCP i bezpośredni ping **PASS**. `getAvailableApiList`, `getApplicationInfo` i `getShootMode` zwróciły HTTP 200. Główna sieć z Tailscale i trasa domyślna pozostały aktywne.
- **NIEPRZETESTOWANE:** zoom, wyzwalanie migawki i Wi-Fi Live View metodami API, współbieżność z USB/PTP, opóźnienia końcowe i stabilność długoterminowa.

**Dokument dowodowy:** [SONY_A6100_HDMI_WIFI_VERIFICATION_2026-10-13.md](SONY_A6100_HDMI_WIFI_VERIFICATION_2026-10-13.md). Wyniki te rozszerzają wcześniejszy raport USB/PTP, nie zastępują go. Szczegółowe adresy sieci, sekret WPA2 i pliki obrazu pozostają poza publicznym repo.

## Kamera radiometryczna (do wyboru)

Wymagane surowe dane temperatur per piksel, parametry kalibracji i możliwość zapisania korekt. Ujęcie pseudokolorowe bez danych radiometrycznych nie spełnia celu. Test: format, jednostki, zakres, emisyjność i współrzędne RGB→IR. **UNVERIFIED.**

## Ramię (do wyboru)

Wymagane potwierdzenie udźwigu z Sony i obiektywem, zasięgu, powtarzalności, ograniczeń zakresu oraz interfejsu programowego. Tryb początkowy: obserwacja i pozycjonowanie ręczne, następnie testy na sucho w przestrzeni wolnej od DUT. **UNVERIFIED.**

## Kamera głębi / 3D (opcjonalna)

Ma obserwować całe stanowisko z nieruchomego punktu, wykrywać przeszkody (złącza, radiatory, uchwyty) i pomagać planować bezkolizyjne ruchy. Nie traktujemy jej jako funkcji bezpieczeństwa. Nie używamy jej do metrologii mikropęknięć ani kontroli lutów. **UNVERIFIED.**

## Oświetlenie

Ring + światła boczne, sterowalne i powtarzalne profile. Ważna jest synchronizacja ze zdjęciem i zapisywanie ustawień per ujęcie. **UNVERIFIED.**

## Kryterium zamknięcia integracji

Dla każdego urządzenia wymagamy: identyfikatora typu/połączenia (bez upubliczniania numeru seryjnego), wersji sterownika, małego testu odczytu, rzeczywistego testu funkcjonalnego, testu awarii/odłączenia, dokumentacji ograniczeń oraz osobnej zgody na wdrożenie.

Nie rozpoczynamy Vision Core ani integracji autonomicznego ramienia przed ustalonym zakresem weryfikacji sprzętu. Matryca: [VENTUNO_Q_HARDWARE_VERIFICATION_2026-10-10.md](VENTUNO_Q_HARDWARE_VERIFICATION_2026-10-10.md).
