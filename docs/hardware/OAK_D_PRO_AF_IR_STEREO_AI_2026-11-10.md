# Vision — test IR, StereoDepth i AI na OAK-D Pro AF (2026-11-10)

**Host:** VENTUNO Q, Ubuntu 24.04 ARM64, DepthAI 3.12.0, izolowane środowisko NVMe  
**Kamera:** Luxonis OAK-D-PRO-AF, RVC2 / Intel Movidius Myriad X  
**Cel:** porównać passive stereo / active stereo IR (dot/flood) i równoległą inferencję YOLOv6 Nano na urządzeniu.  
**Werdykt:** stereo i sterowanie IR PASS; AI+StereoDepth PASS; kombinacja AI+IR NIESTABILNA — wykryto utratę USB `X_LINK_ERROR`.

## Metoda i bezpieczeństwo
- Na jednej sesji StereoDepth przetestowano po 6 s konfiguracje OFF, dot 15%, dot 30%, flood 20%, dot+flood 20%, OFF. Między fazami 1,2 s na stabilizację.
- StereoDepth: 1280×800, LR-check, rectification, extended disparity. Poprawny piksel: 1–4999 mm.
- W oddzielnej sesji równolegle do stereo uruchomiono RVC2 YOLOv6 Nano z Luxonis Model Zoo; próbę IR+AI przerwało rozłączenie urządzenia.
- Następnie wykonano osobny 30-sekundowy test kontrolny AI+Stereo przy IR OFF.
- Emiterów nie ustawiano powyżej 30%; fabryczna kalibracja/EEPROM, firmware, usługi Vision, NERO bez zmian. Z testu nie zapisywano nowych zdjęć.
- Sterownik IR zgłasza: `[('LM3644', 2, 99)]`; API `setIrLaserDotProjectorIntensity` i `setIrFloodLightIntensity` potwierdza przyjęcie ustawień.
- Użytkownik nie potwierdził dedykowanego zasilania 15W; podłączenie przez hub USB nie gwarantuje wystarczającego zapasu mocy. BRAK pomiaru poboru prądu i napięcia.

## StereoDepth bez AI — zakończony test

| Emisja IR | FPS stereo | Poprawne % cały kadr | Poprawne % centrum | Mediana centrum mm | Chip °C |
|---|---:|---:|---:|---:|---:|
| OFF początek | 15,83 | 18,69 | 24,01 | 1734 | 39,2 |
| Dot 15% | 16,00 | 48,39 | 60,97 | 2364 | 39,5 |
| Dot 30% | 16,00 | 44,64 | 54,12 | 2344 | 40,2 |
| Flood 20% | 16,00 | 20,25 | 26,47 | 2424 | 40,3 |
| Dot 20% + Flood 20% | 15,83 | 20,55 | 26,73 | 2418 | 41,3 |
| OFF koniec | 15,83 | 20,17 | 26,93 | 2427 | 40,7 |

- Sterownik IR i aktywne stereo działają; największa poprawa pokrycia w tym teście pochodziła od dot-projectora 15%.
- Większa moc (30%) nie przyniosła poprawy; flood sam i jednoczesny dot+flood także nie. Nie ustalono optymalnych nastaw dla stanowiska, ponieważ scena była niekalibrowana i mogła zmieniać się między fazami.
- Zmiana mediany głębi centrum 1734→2427 mm między OFF początek/koniec oznacza zmianę zawartości obszaru ROI albo odsetka wybranych punktów: NIE jest to test dokładności głębi w nieruchomej scenie.
- Po zakończeniu komendy `DOT_OFF=True`, `FLOOD_OFF=True`.

## AI + stereo — wyniki i incydent USB
- Faza AI+stereo IR OFF (6 s): **15,00 FPS** stereo, **19,33 wyników AI/s**, 20,06% poprawnych punktów w całym kadrze, procesor **44,0°C**.
- Faza AI+stereo dot 15%: przed rozłączeniem 71 odebranych klatek stereo i 92 wyników AI w 6 s, ale pomiar jest NIEWAŻNY jako stabilny benchmark (rozłączenie w trakcie). Pokrycie w zebranych próbkach 47,88% całego kadru, 56,44% centrum.
- DepthAI zgłosił `X_LINK_ERROR` na wielu strumieniach oraz `Watchdog stopped, closing device connection`; log jądra potwierdził fizyczną utratę urządzenia SuperSpeed i jego ponowną enumerację. Proces zakończył się kodem **1**.
- Próba programowego wyłączenia IR w `finally` nie mogła dotrzeć do rozłączonego urządzenia; urządzenie ponownie enumerowało jako stan nieuruchomiony `03e7:2485` (emitery domyślnie wyłączone).
- W logu brak jednoznacznego komunikatu undervoltage/overcurrent i brak crash-dump; nie ustalono źródła problemu. Przyczyny do sprawdzenia: zasilanie podczas szczytów prądu, hub/kabel USB, firmware/pipeline.
- Temperatura 44°C nie wskazuje na wyłączenie termiczne.

## Kontrola bez IR — 30 sekund po incydencie
- AI YOLOv6 Nano + StereoDepth + USB `SUPER`, IR OFF: **447** klatek stereo (**14,90 FPS**) i **577** pakietów AI (**19,23/s**).
- 23,38% poprawnych punktów w pełnej klatce, 32,88% w centralnym ROI; procesor **46,4°C**.
- `BENCHMARK_COMPLETE`, `DOT_OFF=True`, `FLOOD_OFF=True`, **exit 0**. DepthAI wykrył kamerę po zakończeniu testu.
- Dowodzi działania AI+stereo przez 30 s, nie gwarantuje stabilności godzinowej.

## Decyzja / następne kroki
1. **Blokada łącznego IR+AI** do potwierdzenia prawidłowego zasilania Pro: dedykowany zasilacz 5 V o wydajności >=15 W przez kompatybilny adapter Y albo hub z potwierdzonym przydziałem mocy.
2. Sprawdzić kabel USB3, port huba oraz ryzyko spadku napięcia; przed dalszym testem nie zmieniać obecnych urządzeń Vision.
3. Po zapewnieniu zasilania wykonać powtarzalny test A/B/A/B (IR OFF / dot 15%) na nieruchomym, matowym wzorcu w znanej odległości; osobno AI + IR.
4. Zarejestrować stabilność USB, ewentualny crash dump, chip temp, FPS, odsetek poprawnych punktów i błąd pomiaru odległości.
5. Testowy skrypt `ir_stereo_ai_benchmark.py` pozostaje DEV: bez `--enable-ir` domyślnie pracuje tylko przy IR OFF; `--ai --enable-ir` jest zablokowane (fail-closed).
6. Nie używać tych danych do automatycznych ruchów NERO ani jako dowodu bezpieczeństwa.

Dokumentacja: https://docs.luxonis.com/hardware/products/OAK-D%20Pro oraz https://docs.luxonis.com/hardware/platform/deploy/usb-deployment-guide
