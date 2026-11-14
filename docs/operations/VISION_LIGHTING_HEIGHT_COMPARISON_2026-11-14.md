# Vision — wpływ dodatkowego oświetlenia na pomiar głębi

**Data:** 2026-11-14. **Stan:** HARDWARE_CAPTURE_PASS / LIGHTING_COMPARISON_PASS / PRELIMINARY_IMPROVED_REPEATABILITY / CAUSALITY_NOT_PROVEN / PROD_RESTORED_PASS.

## Przygotowanie i kontekst

Przed rozpoczęciem OAK-D Pro AF oraz cały koncentrator USB3 zniknęły z magistrali VENTUNO Q (`No available devices`, restart-loop Camera Service). Po ponownym uruchomieniu VENTUNO urządzenia wróciły na USB SUPER 5 Gb/s, a produkcyjny Camera Service był ONLINE z `NRestarts=0`. To incydent niezawodności wymagający osobnej diagnostyki, nie dowód wpływu światła.

Operator włączył dodatkowe oświetlenie bez zmiany zaplanowanych trzech elementów. Rzeczywisty bieżący obraz RGB został wizualnie zweryfikowany; wszystkie elementy były w kadrze, ale ich pozycje projekcyjne różniły się od poprzednich zapisów. W konsekwencji **osobno ustalono grube ROI nowych elementów w rectified-left na podstawie aktualnej mapy głębi**. Nie zakładano identycznej pozycji i transformacji kamery.

W kontrolowanej sesji jednego właściciela USB nagrano **25 pełnych RAW16 1280×800** w odstępach około 0,5 s. Parametry, jak w poprzedniej serii: DepthAI 3.12.0, RGB 1080p/30, StereoDepth 800p/30, rectification ON, LR check ON, `setSubpixel(True)`, extended disparity OFF, IR Dot 0%, Flood 0%. Rzeczywiste `K` pobrano z każdej klatki; profil nie stanowi implementacji PR #25 `FAST_ACCURACY`. Nie było ruchu NERO ani dotykania EEPROM.

Raport sprzętowy: `CAPTURE_PASS`, Depth RAW16 valid (0<z<5 m) **79,841%**, 25 klatek, 373 RGB packets, 360 depth packets, 10 przerw sekwencji konsumenta. IR OFF ACK `true/true`, oryginalny Camera Service wrócił ONLINE/USB SUPER/error=null. Próbki i zdjęcia zachowane wyłącznie prywatnie na NVMe.

## Porównanie

Za punkt odniesienia przyjęto **50 wcześniejszych klatek** z faz `subpixel_on / off_before` i `subpixel_on / off_after`, nie wykorzystując sesji z IR Dot. Analizę przeprowadzono na identycznym kodzie `top_surface.py` z PR #26, bez użycia znanej wysokości do estymacji; metryka `Luxonis BoxEstimator core` z osobnym dopasowaniem stołu służy jako kontrola.

Wartości = mediana wysokości [mm] **spośród geometrycznie zaakceptowanych pomiarów**. Referencje operatora: beżowe 34,0, czerwone 50,4, biało-czerwone 101,0 mm.

| Obiekt | Referencja | Przed (50 klatek) | Po (25 klatek) | Liczba akceptowanych przed/po |
|---|---:|---:|---:|---:|
| Beżowe | 34,0 | 33,372 (bias −0,628) | 34,329 (+0,329) | 14/50 → 21/25 |
| Czerwone | 50,4 | 48,852 (−1,548) | 49,002 (−1,398) | 32/50 → 19/25 |
| Biało-czerwone | 101,0 | 100,426 (−0,574) | 100,273 (−0,727) | 50/50 → 25/25 |

**Odchylenie standardowe zaakceptowanych pomiarów [mm]:**

| Obiekt | Przed | Po | Zmiana |
|---|---:|---:|---:|
| Beżowe | 0,755 | 0,667 | około −12% |
| Czerwone | 2,863 | 1,083 | około −62% |
| Biało-czerwone | 0,497 | 0,285 | około −43% |

**Ważne piksele głębi:**

| Obszar | Przed | Po |
|---|---:|---:|
| Cały obraz (ważność 0,25–2 m) | 78,846% | 79,820% |
| Beżowe, zgrubny ROI | 93,506% | 93,381% |
| Czerwone, zgrubny ROI | 88,188% | 91,879% |
| Biało-czerwone, zgrubny ROI | 90,404% | 92,242% |

Udział poprawnych pikseli ROI nie jest w pełni porównywalny między sesjami, bo obszary i pozycje w polu widzenia uległy zmianie; różnice mogą wynikać również z widoczności i powierzchni tła.

**Kontrola inną metodą (rdzeń Luxonis BoxEstimator, adaptacja do ROI/stołu)**: mediany przed→po: beżowe 32,634→34,289; czerwone 49,618→49,208; biało-czerwone 100,762→100,380. Odchylenie standardowe czerwonego 2,394→1,078 mm. Zysk powtarzalności utrzymuje się również dla tej metody; bias nie poprawia się jednoznacznie dla wszystkich obiektów.

## Decyzja

**Dodatkowe oświetlenie jest korzystne jako warunek pracy Vision**: w tej sesji uzyskano mniejszy rozrzut wysokości, zwłaszcza na czerwonym elemencie, i nieco lepszą kompletność stereo. **Nie udowodniono jednak zależności przyczynowej wyłącznie od lamp**, ponieważ nie wykonano kontrolowanego A/B OFF–ON z nieruchomą kamerą, stałą sceną i stałą ekspozycją.

Bramka badawcza `top_surface` (min. 95% klatek przyjętych, bias <= 1 mm, std <= 1 mm, percentyle p05/p95 w ±2 mm): obecnie **101 mm PASS**, 34 mm FAIL (akceptacja 84%), 50,4 mm FAIL (akceptacja 76%, bias −1,398 mm, std 1,083 mm). Wszystkie `metrology_verified=false`, `robot_base_frame=UNAVAILABLE`, brak możliwości bezpiecznego sterowania NERO na podstawie tych wyników.

**Dane prywatne:** `/srv/vision-data/staging/vision-lighting-check-20261114` (RAW16, RGB, analysis JSON), nie publikować obrazów ani K w publicznym GH. Po zakończeniu testu nie modyfikowano produkcyjnych plików ani usług.
