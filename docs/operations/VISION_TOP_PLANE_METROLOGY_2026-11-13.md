# Vision — lokalna płaszczyzna stołu i płaszczyzna górna, wzorzec 50,4 mm

**Data pomiaru:** 2026-11-13. **Host:** VENTUNO Q, OAK-D Pro AF, DepthAI 3.12.0.
**Gałąź DEV:** feature/perception-parallel-plane-height-20261113 (nad PR #23).
**Wynik:** SOFTWARE_OFFLINE_PASS / SHORT_HARDWARE_ACQUISITION_PASS / METROLOGY_1MM_FAIL / PROD_RESTORED_PASS.
**ADR:** ADR-VISION-ARCH-001 — Camera Service / Perception Engine / Vision Core; brak kodu robota.

## 1. Implementacja

Nowy, samodzielny moduł: scripts/perception/height_planes.py.
- Przyjmuje surowe RAW16 w mm, K wyjściowe StereoDepth i **ręcznie określone** ROI elementu i otaczającego go stołu. Nie zakłada zarejestrowania RGB do stereo i nie pobiera danych przez USB.
- Wyklucza obiekt z lokalnego RANSAC płaszczyzny stołu, a następnie wyznacza wysokości punktów obiektu względem normalnej stołu.
- Odrzuca niski pas wysokości, wybiera górne 40% kandydatów i dopasowuje **odrębną** płaszczyznę górnej powierzchni (RANSAC). Przy niezgodności orientacji >14°, zbyt małej liczbie punktów lub za dużych residualach zwraca NOT_READY.
- Raportuje wysokość *w punkcie centralnym dopasowanej górnej płaszczyzny wzdłuż normalnej stołu*. Dwie niewspółpłaszczyznowe powierzchnie nie mają stałej odległości w każdym punkcie.
- Metadane: schema_version=perception.height_planes.v1, normalne, residual RMSE, odsetek punktów ważnych, liczba inlierów, różnica normalnych, błędy walidacji, UNAVAILABLE dla układów stołu i robot_base oraz safety_function=false.
- Wyliczenie wysokości NIE korzysta z prawdziwych 50,4 mm. Osobna funkcja evaluate_reference_gate porównuje wyniki z niezależnym wzorcem i **nie** nadaje sama certyfikacji metrologicznej ani współrzędnych robota.
- Kontrakt schema JSON i testy syntetyczne; bez dodatkowych frameworków, ROS2, AI, ruchu NERO i zmian EEPROM.

## 2. Testy bez kamery

- 50/50 testów offline (po ostatnim teście odrzucania nierównoległej górnej płaszczyzny), obejmujących dotychczasowe regresje oraz nową geometrię i bramkę jakości. Do potwierdzenia końcowym uruchomieniem pełnego zestawu.
- Zapisana pojedyncza mapa RAW16 (IR OFF, 12:06 UTC): nowy estymator 49,482 mm, błąd -0,918 mm, top/table normal angle 3,64°, table residual RMSE 2,62 mm, top residual RMSE 1,47 mm.
- **Jedna klatka nie dowodzi ±1 mm dokładności**, więc wynik był tylko bramką poprawności obliczeń.

## 3. Krótki test rzeczywisty IR OFF / Dot 5% / OFF / Dot 10% / OFF

Przed testem prawdziwy Camera Service online (USB SUPER, RGB ~30,1, Depth ~29,2 FPS), NVMe zamontowane. Testowy skrypt:
scripts/perception/bench_plane_height_oak.py

Próba z jednym właścicielem USB: stop systemd; start jednej kopii testowej, 12 s warmup, pięć faz po 11 s (settle 2,5 s); w każdej fazie 31 prób geometrii (każda 8. klatka); zamknięcie, wyłączenie IR, restart dotychczasowego unit i sprawdzenie zdrowia. Wyniki prywatne na NVMe; surowe RAW16 .npy z pięciu faz zachowane WYŁĄCZNIE lokalnie do replay/analizy (bez GitHub).

| Faza | Ważne próbki | Mediana wysokości mm | Błąd względem 50,4 mm | Poprawne piksele ROI % | RMSE górnej płaszczyzny mm |
|---|---:|---:|---:|---:|---:|
| OFF #1 | 28/31 | 52,074 | +1,674 | 89,105 | 1,422 |
| Dot 5% | 31/31 | 47,136 | -3,264 | 95,921 | 1,403 |
| OFF #2 | 28/31 | 51,926 | +1,526 | 89,191 | 1,435 |
| Dot 10% | 31/31 | 47,044 | -3,356 | 95,789 | 1,361 |
| OFF #3 | 29/31 | 51,585 | +1,185 | 88,711 | 1,393 |

- RGB ~29,73–30,36 FPS; depth ~29,09–29,45 FPS; OAK 53,49–54,04°C podczas faz.
- Licznik luk sekwencji głębi: 9–13 na fazę; nie ukrywamy strat po stronie konsumenta.
- Prawidłowe punkty w ROI przy Dot wzrosły z ~89% do ~96%, a liczba inlierów górnej płaszczyzny z ok. 195 do 560. To dowodzi zmiany dostępnych danych, nie poprawy dokładności XYZ.
- RMSE dopasowania top ok. 1,36–1,44 mm NIE jest błędem absolutnego pomiaru wysokości.
- Rozrzut pojedynczych szacowań: OFF 1,25–1,64 mm std; Dot5 1,16 mm, Dot10 0,74 mm. Punktów nie traktujemy jako niezależnych statystycznie; fazy są krótkie i klatki czasowo skorelowane.
- Bramkę badawczą ±1 mm (bias ≤1 mm, odchylenie standardowe ≤1 mm, ≥95% poprawnych prób, błąd ogonów ≤2 mm) **oblewają wszystkie pięć faz**. Dot10 ma niższy rozrzut, lecz nadal -3,356 mm błędu systematycznego.
- ON i OFF przechodzą pozytywnie test geometrii oraz akwizycji; nie spełniają kryterium rzeczywistej metrologii.

## 4. Dochodzenie przyczyny rozbieżności

Prywatne zrzuty RAW16 zostały porównane na **tych samych pikselach rectified-left** dla pięciu faz.
- Na rozległym otaczającym obszarze stołu mediany różnicy Depth (Dot5/10 minus OFF1) wyniosły ok. **0 mm**, z rozkładem 10–90% ok. -5 do +5 mm.
- W środkowej części czerwonego elementu mediany różnic na wspólnych pikselach wyniosły ok. **-2 mm** (zależnie od fazy); przy wyłączonym IR powtórzona klatka dawała w tym obszarze medianę ok. -1 mm.
- Regiony, które dotychczas były bez ważnych pikseli, są po włączeniu IR wypełniane; ich mieszanie ze ścianami bocznymi może zniekształcać estymację. Wyniki nie pozwalają jeszcze jednoznacznie odróżnić błędu dopasowania stereo od doboru punktów, lokalnej geometrii i wpływu oświetlenia.
- Nie wolno korygować wyniku przez stałe przesunięcie dobrane tylko do jednego wzorca 50,4 mm. To byłoby przeuczenie kalibracji na jednym obiekcie.

## 5. Status produkcji i ryzyka

- IR OFF (oba emitery) — SDK zwróciło true/true po końcowym poleceniu.
- Oryginalny Camera Service **przywrócony**. Ostatnie testy potwierdziły USB SuperSpeed i brak błędów, profil balanced oraz dokładnie jednego właściciela USB.
- Produkcyjnych plików / systemd nie zmieniono. Kod pozostaje wyłącznie w osobnej gałęzi i PR. Brak merge do main.
- Nie uruchomiono NERO, Vision Core, żadnych komend ruchu ani sterowania STOP/E-STOP, AI Platform/GPU lub kamerowego NN.
- Historyczna awaria enumeracji huba USB3 nadal nie ma udowodnionej przyczyny; długie testy tego nie zastąpią.

## 6. Kolejna bramka

1. Do dalszej kalibracji potrzebne są faktycznie zmierzone wymiary boków kwadratów ChArUco i sztywne, płaskie zamocowanie wydruku.
2. Sprawdzić konfigurację subpixel/stereo matching, dokładność projekcji rectified-left oraz selekcję górnej powierzchni na **kilku różnych wysokościach/obiektach**, z odrębnym zbiorem walidacyjnym. Dopiero potem ewentualna kompensacja systematyki.
3. Rozważyć maskowanie rzeczywistego dysku górnego za pomocą geometrii i zarejestrowanego RGB/depth (po walidacji extrinsics), nie wyłącznie ręcznego ROI i percentyla.
4. Długi test stabilności 2–3 h z Perception pozostaje PENDING, ponieważ dokładność w tym zastosowaniu nie uzyskała jeszcze bramki.
5. Żaden wynik z aktualnego pomiaru nie jest współrzędną robota; table i robot_base nadal UNAVAILABLE.

**Podsumowanie:** udało się wydzielić dwa dopasowania płaszczyzn, przetestować je offline i na kamerze oraz ujawnić trwały błąd IR. Nie ma podstaw do deklarowania ±1 mm dokładności ani aktywacji profilu IR precyzyjnego w produkcji.


## 7. Dodatkowa kontrola geometrii planszy ChArUco (offline)

Na aktualnie zapisanym RGB 1920×1080, bez ponownego otwierania USB: **17 znaczników ArUco i 24 narożniki ChArUco** poprawnie wykryte. Dopasowanie płaskiej homografii do narożników (w **umownych jednostkach** kwadratu, jeszcze bez prawdziwych wymiarów wydruku) dało RMS reprojected corner error **0,226 px**, p95 **0,365 px**, max **0,373 px**. To wskazuje spójność wykrywania punktów i płaskości obrazu w tej próbce, ale **nie** mierzy rzeczywistej skali X/Y, dokładności 3D, korekcji soczewki ani kalibracji względem robota. Wymagany fizyczny pomiar boku wydrukowanego kwadratu (mm) i sztywne zamocowanie planszy.
