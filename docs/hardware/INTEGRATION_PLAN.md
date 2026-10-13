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

## Sony A6100A — nowy wariant toru HDMI + Wi-Fi + USB (2026-10-13)

**Preferowany kierunek do dalszej walidacji, nie wdrożony produkcyjnie:** clean HDMI do kadrowania; Wi-Fi ScalarWebAPI do zoomu, ekspozycji i migawki; RAW+JPEG zapisywane na karcie SD; **po sesji** USB Mass Storage do importu oryginałów na NVMe.

**Rzeczywisty PASS pojedynczego cyklu:** użytkownik widział czysty obraz HDMI podczas aktywnego Wi-Fi; VENTUNO wykonał zdjęcie przez Wi-Fi; Sony zapisał na SD parę `DSC00020.JPG` (**6000×4000**) + `DSC00020.ARW`; po fizycznym podłączeniu USB aparat sam zgłosił Mass Storage; źródłowe pliki skopiowano z zamontowanej read-only karty na NVMe i zweryfikowano zgodność SHA-256.

**BLOKER automatyzacji:** programowe `usb1-port2/disable` odłącza urządzenie od Linux, lecz Sony nadal wyświetlało „Tryb USB” i nie uruchamiało sieci Wi-Fi. Po fizycznym odłączeniu USB wraca obraz HDMI, ale sieć Wi-Fi nie pojawiła się automatycznie. Wpływ opcji `Zawsze połączony` pozostaje **NOT TESTED do końca** (rozładowanie akumulatora). Grabber HDMI/UVC i niezawodność długiej serii nadal **NOT TESTED**.

Wariant **USB PC Remote + Bluetooth** ma odrębne potwierdzenie działania USB Preview wraz z BLE zoom (EXIF 16→20 mm), ale nie jest aktualnie preferowanym docelowym przepływem.

- [Wyniki testów Sony — 13 października](SONY_A6100A_MULTITRANSPORT_VERIFICATION_2026-10-13.md)
- [ADR — etapowy transfer i bramki bezpieczeństwa](../architecture/ADR_SONY_STAGED_ACQUISITION_2026-10-13.md)
- [Rejestr lokalnych dowodów na NVMe](EVIDENCE_REGISTER_SONY_2026-10-13.md)

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
