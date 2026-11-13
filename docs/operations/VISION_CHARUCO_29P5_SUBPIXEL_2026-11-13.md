# Vision — ChArUco 29,5 mm i test StereoDepth Subpixel

Data: 2026-11-13. Host VENTUNO Q, OAK-D Pro AF, Ubuntu ARM64, DepthAI 3.12.0.
ADR-VISION-ARCH-001. Gałąź: feature/perception-parallel-plane-height-20261113, PR #24, oparty na PR #23. **Tylko DEV, bez merge i produkcyjnej instalacji.**

## 1. Wymiary planszy

Użytkownik zmierzył bok **czarnego kwadratu = 29,5 mm**. Dla board (5,7) nominalny rozmiar siatki to 147,5 × 206,5 mm. Fizyczne wymiary całej kartki i bok markera ArUco nie zostały jeszcze zweryfikowane; do detekcji przyjęto roboczo marker = 0,5 boku kwadratu.

Na wcześniej zapisanym prywatnym obrazie RGB 1920×1080:
- Detekcja 17/17 markerów ArUco, 24/24 narożniki ChArUco.
- Reprojekcja homografii: RMS 0,226 px, p95 0,365 px.
- PnP z wcześniejszą macierzą K RGB po transformacji: 24 inliers, RMS 0,310 px, p95 0,463 px.
- Szacunkowe położenie początku planszy w rgb_optical: [0,142128; -0,102936; 0,804304] m. Długość wektora 0,8232 m. Normalna planszy nachylona ~6,712° względem osi widzenia RGB.
- Zakładano brak zniekształcenia po przetworzeniu strumienia RGB — nie potwierdzono tego metrologicznie. PnP to wynik eksperymentalny, nie niezależna walidacja skali: znaną skalę 29,5 mm podajemy jako wejście.
- Brak transformacji RGB -> rectified-left i camera -> robot_base; table i robot_base: UNAVAILABLE.

Kod: scripts/perception/verify_charuco_scale.py. Test syntetycznej planszy: tests/test_charuco_square_scale.py.

## 2. Krótka próba trybu StereoDepth Subpixel

Wyniki uzyskane na prawdziwej kamerze w trzech osobnych, następujących po sobie sesjach. Profil pozostał bez AI, bez extended disparity, z left-right-check i rectification; RGB 1920×1080, depth RAW16 1280×800 w mm. Przed każdą próbą ok. 12 sekund stabilizacji; następnie 24 sekundy pomiaru co ósmą klatkę. Po każdej próbie uruchamiano ponownie pierwotną usługę produkcyjną Camera Service.

Subpixel: StereoDepth.setSubpixel(False/True), 3 domyślne bity ułamkowe. Algorytm wysokości jest ten sam w każdej sesji: dwa dopasowania RANSAC, ROI głębi nieruchome, brak użycia referencji 50,4 mm w obliczeniu. Zmiana trybu wymaga osobnego startu pipeline, co uniemożliwia dokładnie jednoczesne porównanie.

| Konfiguracja | Ważne pomiary | Mediana wysokości | Błąd względem 50,4 mm | Std. klatek | Ważne piksele depth w ROI | RGB / Depth FPS |
|---|---:|---:|---:|---:|---:|---:|
| Subpixel OFF, IR OFF | 29/79 (36,71%) | 56,593 mm | +6,193 mm | 3,810 mm | 88,776% | 30,12 / 30,17 |
| Subpixel ON, IR OFF | 74/76 (97,37%) | 51,843 mm | +1,443 mm | 1,456 mm | 88,869% | 30,04 / 29,25 |
| Subpixel ON, IR Dot 5% | 76/76 (100%) | 47,666 mm | -2,734 mm | 0,735 mm | 95,447% | 30,04 / 29,29 |

Interpretacja:
1. Subpixel poprawił w tych próbach stabilność dopasowania geometrycznego i poprawność pomiarów, zmniejszył błąd mediany i rozrzut w stanie IR OFF.
2. Dot 5% przy subpixel zwiększył pokrycie i obniżył rozrzut, ale nadal wprowadza istotny błąd systematyczny w estymatorze wysokości. Dokładność ±1 mm **FAIL**.
3. W integer mode pojawiło się wiele odrzuconych dopasowań i nadmiernie optymistyczne residuale (czasem 0), które nie dowodzą jakości przy dyskretyzacji disparity.
4. Wyniki z jednego obiektu i pojedynczych, niejednoczesnych sesji są wskazówką rozwojową, nie specyfikacją dokładności sensora. Odchylenia klatek są skorelowane w czasie.
5. Dot nie powinien być włączany automatycznie do pomiarów precyzyjnych. Subpixel jest obiecującym kandydatem do dalszych testów, ale nie gotową opcją produkcyjną.

## 3. Bezpieczeństwo, prywatność i przywrócenie systemu

- Tylko jeden właściciel USB. Stop produkcyjnej usługi -> jedna sesja testowa -> IR OFF w finally -> restart oryginalnej usługi -> potwierdzenie ONLINE.
- Wszystkie trzy próby: COMPLETE, production_restored=true, IR OFF SDK ACK dot=true/flood=true. Brak niezależnego optycznego potwierdzenia emiterów.
- Końcowy baseline: Camera Service active/running, NRestarts=0, jeden proces, RGB 30,1 FPS, Depth 29,4 FPS, USB SUPER, 50,9°C, error=null.
- Zero zmian w katalogu produkcyjnym, systemd, firmware, EEPROM, STOP/E-STOP, NERO, Vision Core, NN Luxonis, GPU AI Platform, ROS 2.
- Surowe mapy depth i szczegółowe metryki pozostają WYŁĄCZNIE na prywatnym NVMe pod:
  /srv/vision-data/staging/oak-height-planes-private-20261113/
  oraz: /srv/vision-data/staging/oak-calibration-check-20261113/charuco_29p5_scale_results.json.
- Do repozytorium trafiają tylko testy syntetyczne, kod i zagregowane dane; brak prywatnych obrazów i adresów.

## 4. Kolejna bramka

Weryfikować skalę i głębię na co najmniej jeszcze dwóch obiektach o innych zmierzonych wysokościach i różnych powierzchniach. Potwierdzić faktyczny rozmiar markera, model zniekształceń RGB, dokładność rectified-left i transformacje kamer. Dopiero wtedy rozważyć ewentualną kompensację systematyki, bez przeuczania się do jednego wzorca.

Długi test 2–3 h Camera Service + Perception Engine pozostaje PENDING do czasu przygotowania konfiguracji diagnostycznej, ale sam może sprawdzać stabilność akwizycji niezależnie od certyfikacji metrologicznej.

**Status: CHARUCO_2D_PASS / SUBPIXEL_SHORT_TEST_PASS / OBJECT_HEIGHT_1MM_FAIL / PRODUCTION_RESTORED_PASS.**
