# Vision — krótki test sprzętowy optyki, IR, autofocus i ROI

**Data:** 2026-11-13 (VENTUNO Q). **Gałąź:** feature/oak-optics-ir-af-roi-20261113, PR #23, baza PR #22. **Status:** SHORT_HARDWARE_PASS / PRODUCTION_RESTORED_PASS / METROLOGY_PENDING / LONG_SOAK_PENDING.

## Warunki i bezpieczeństwo

- Po restarcie VENTUNO Q powróciło wykrywanie USB3 Genesys hubów i kamery OAK-D Pro AF / Movidius. Wcześniejszy brak urządzeń z 12–13 listopada wciąż ma NIEUSTALONĄ przyczynę.
- Przy każdym teście: zdrowy baseline produkcyjny i SuperSpeed, pojedynczy właściciel USB, kontrolowane zatrzymanie unit Camera Service, próba lokalna na porcie 18111, zamknięcie kopii, przywrócenie produkcyjnego unit i kontrola ONLINE. Skrypt: scripts/camera/oak/controlled_optics_smoke.py.
- Emitter IR 15% dot / 20% flood sterowany wyłącznie w eksperymencie; w bloku finally wysyłano wyłączenie obu emiterów. Wysłane polecenie nie oznacza sprzętowego potwierdzenia optycznego.
- Obrazy są pobierane tylko do pamięci na potrzeby odczytu parametrów, bez publikowania i bez archiwizacji fotografii do GitHub; lokalne wyniki JSON i logi 0600 na NVMe poza repo.
- Zero kodu ruchu NERO, zmian E-STOP/STOP, AI Luxonis, AI Platform/GPU, ROS2, EEPROM lub plików produkcyjnych.

## Geometria wyjściowa rectified-left

Prawdziwy ImgFrame.getTransformation() dla StereoDepth 1280x800 zwrócił:
- fx **796.59625 px**, fy **796.73950 px**, cx **634.99469 px**, cy **378.50885 px**, stereo_left_rectified_optical.
- RGB 1920x1080: fx **1454.92639 px**, fy **1454.20642 px**, cx **954.50824 px**, cy **512.74609 px**, rgb_optical.
- Read-only EEPROM calibration state: EEPROM_READ_ONLY. K wyjściowe i source K zostały odczytane oddzielnie.
- Status pozostaje FRAME_TRANSFORM_REPORTED_UNVERIFIED: samo istnienie spójnej macierzy nie oznacza walidacji dokładności XYZ lub poprawności rectification na wzorcu. Kalibracje table i robot_base są UNAVAILABLE.
- Pierwszy pilot SURVEY: RGB **30.1 FPS**, depth **29.35 FPS**, **271** sparowanych zestawów, **79.65%** ważnych pikseli głębi, T median **42.2°C**. Atomowy JPEG + depth uint16 1280x800 przeszedł replay; 50 884 punktów przy stride 4, płaszczyzna PASS, 8 UNKNOWN, wynik EXPLORATORY_UNVERIFIED_PROJECTION.

## Porównanie IR i profili na rzeczywistej kamerze

| Etap | RGB FPS mediana | Depth FPS mediana | Depth valid % | T chip °C mediana | Sparowane zestawy |
|---|---:|---:|---:|---:|---:|
| SURVEY IR OFF przed | 30.10 | 29.35 | 79.65 | 42.2 | 271 |
| DEPTH_PRECISION IR Dot 15% | 30.15 | 29.45 | 80.70 | 42.6 | 267 |
| LOW_LIGHT IR Flood 20% | 30.40 | 29.45 | 79.70 | 42.6 | 267 |
| DETAIL 4K/AF/ROI | 20.10 | 20.00 | 79.85 | 43.0 | 187 |
| SURVEY IR OFF po | 30.10 | 29.40 | 79.80 | 42.1 | 272 |

W tej scenie Dot 15% dał **+1.05 punktu procentowego** względem pierwszego OFF; Flood 20% dał +0.05 p.p. Przy ponownym OFF różnica względem pierwszego wyniosła +0.15 p.p. To wskaźniki poprawności pikseli w krótkich przedziałach, a NIE błąd metrologiczny ani wyznaczona poprawa dokładności. Nie zaobserwowano wyraźnej degradacji FPS ani temperatury w tak krótkim teście.

We wszystkich fazach otrzymano SYNCED bundle camera.frame_bundle.v1, zgodne rozdzielczości i JPEG + RAW16 uint16. Niesparowane lub zgubione sekwencje są liczone, nie ukrywane.

## Zoom cyfrowy

- Po stronie Camera Service diagnostyczne JPEG ROI (centralne x=.25 y=.25 w=.5 h=.5) zwróciło 960x540 pikseli w profilu 1080p i 1920x1080 w profilu 4K. Nie ma optycznego zoomu i nie generowano syntetycznych szczegółów.
- ROI w rgb_optical nie jest automatycznie wyrównane do depth, nie zmienia kalibracji stereo. Błędny ROI: HTTP 400; stale/odłączone RGB: HTTP 503.

## Autofocus — kontrolowana weryfikacja siłownika

Pierwsza faza DETAIL przyjęła komendy AF i AF ROI, ale odczyt lens position pozostawał 99, co nie dowodziło ruchu.

Druga próba DETAIL z osobnym opt-in diagnostycznym:
- manual focus **160** wysłany ok. 2 s po uruchomieniu;
- AF AUTO (z ROI) ponownie wysłany ok. 5 s po uruchomieniu;
- końcowy powrót do AF AUTO wysłany przy shutdown;
- raport z 187 klatek: lens_position_min=0 (włączając start), lens_position_max=160, lens_position_last=127, actuator_diagnostic_step=2; brak błędu odczytu;
- 4K RGB ok. 20.0 FPS, Depth ok. 20.0 FPS, crop ROI 1920x1080.

**PASS:** przyjęcie komend i zmiana pozycji soczewki raportowana przez ImgFrame, **PENDING:** metrologiczna i powtarzalna jakość ostrości rzeczywistego ECU. Wartości lens_position_raw=0 nie stanowią odrębnego dowodu.

## Testy offline, recovery i produkcja

Po dodatkowych testach fokusowych: **40/40 testów offline PASS**, kompilacja Pythona PASS.
Seria wielokrotnych startów i zatrzymań pilota oraz przywracania produkcji zakończyła się sukcesem. Ostatnia kontrola po stabilizacji:
- systemd ActiveState=active, SubState=running, **NRestarts=0** i **dokładnie jeden** proces Camera Service;
- produkcyjne RGB **30.1 FPS**, Depth **29.0 FPS**, USB **SUPER**, temperatura **47.6°C**, RSS **980 MiB**, profile balanced, error=null, uptime ok. 62 s.
- Działający skrypt i unit produkcyjny nie zostały zmienione, brak merge do main.

## PENDING — bramki następnego etapu

1. Rzeczywisty wzorzec kalibracyjny i pomiar znanych długości dla rectified-left K, reprojection oraz XYZ; pozycja table i robot_base wciąż UNAVAILABLE.
2. Dłuższy test (2–3 h) Camera Service + Perception, kwartyle opóźnień p50/p95/p99, stale/drop, bounded queues, obciążenie, USB i temperatura. Nie wolno traktować testów 10-sekundowych jako długotrwałej stabilności.
3. Próba powtórnego uruchomienia kontrolera USB/huba po zimnym starcie i po przerwach zasilania; wcześniejsza awaria enumeracji nie wyjaśniona.
4. Weryfikacja AF na fizycznym ECU, zmiennej odległości i oświetleniu.
5. A/B IR na różnych powierzchniach ECU: lakierowany metal, tworzywo i PCB, z oceną refleksów i powtarzalności.

**Wniosek:** krótkie testy zakończone PASS, geometria metrologiczna i trwałość niezatwierdzone, kod wyłącznie w PR #23; brak zgody na produkcyjne wdrożenie lub sterowanie NERO.
