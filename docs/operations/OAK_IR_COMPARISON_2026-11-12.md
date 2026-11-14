# Vision OAK-D Pro AF — kontrolowany test obrazu IR (12.11.2026)

**Status:** `IR_DOT_FLOOD_COMPARE_PASS / EMITTERS_OFF_PASS / CAMERA_PROD_RESTORED_PASS`  
**Sprzęt:** Luxonis OAK-D Pro AF, VENTUNO Q (Ubuntu ARM64), DepthAI 3.12.0, USB3 `UsbSpeed.SUPER`.  
**Testowany pipeline:** RGB 1920×1080 / 30 FPS, sprzętowy VideoEncoder MJPEG; StereoDepth 1280×800, `LeftRightCheck=True`, `ExtendedDisparity=False`, **bez wbudowanego AI**. Robot NERO bez ruchu i bez komend. Emitery IR sterowane wyłącznie przez SDK, bez zapisu EEPROM.

## Warunki i ograniczenia

- Operator wcześniej zadeklarował podłączenie niezależnego zasilania kamery przez fabryczny adapter Y. Parametrów elektrycznych zasilacza **nie mierzono** podczas tej próby. Połączenie aktywne zgłaszało `UsbSpeed.SUPER`.
- Przed próbą sprawdzono `vision-oak-camera.service`: `active / running`, `enabled`, `NRestarts=0`. Czasowo zatrzymano ją z poziomu systemd użytkownika, aby zwolnić kamerę dla wyłącznego procesu testowego.
- Wykonano pięć faz po 10 s, bez zmiany konfiguracji stereo: `IR OFF → dot 15% → flood 20% → dot 15% + flood 20% → IR OFF`.
- W każdej fazie zapisano **tylko na prywatnym NVMe** pojedynczy JPEG RGB 1080p, podgląd kolorowanej głębi i pełne `uint16` PNG mapy głębi [mm]. Nie umieszczono materiału fotograficznego w publicznym GitHub.
- Test odbył się w tej samej niekalibrowanej scenie. Wskaźnik „poprawne piksele” oznacza udział wartości głębi 1–4999 mm, **nie dokładność pomiaru odległości** ani pewność detekcji obiektów.
- Kontrola temperatury: abort powyżej 65°C; w testowanych fazach nie odnotowano przekroczenia progu (próg był testowy, a nie deklarowany producentem).
- `finally` zlecił wyłączenie obu emiterów: `IR_OFF_ACK True True`. Po teście skrypt zakończył pipeline, a mechanizm `trap` w powłoce automatycznie przywrócił `vision-oak-camera.service`.

## Wyniki rzeczywiste

| Faza | RGB FPS | Depth FPS | Poprawne pełen obraz % | Poprawne centrum % | Mediana odległości centrum [mm] | Temperatura [°C] |
|---|---:|---:|---:|---:|---:|---:|
| OFF przed | 30,20 | 29,00 | 73,64 | 95,05 | 814 | 53,0 |
| Dot projector 15% | 30,19 | 29,09 | **75,12** | 97,27 | 814 | 53,3 |
| Flood 20% | 30,30 | 29,50 | 73,59 | 96,88 | 814 | 53,4 |
| Dot 15% + flood 20% | 30,19 | 29,29 | **75,14** | 97,29 | 813 | 54,0 |
| OFF po | 30,30 | 29,30 | 73,56 | 96,77 | 814 | 53,9 |

Interpretacja: względem obu pomiarów OFF projektor punktowy 15% zwiększył pokrycie pełnej mapy głębi o około 1,5 punktu procentowego. Flood nie przyniósł poprawy w całym obrazie; kombinacja dot + flood dała zasadniczo tyle samo co dot sam. Centralny ROI już bez IR miał bardzo wysokie pokrycie, a jego wyniki między dwiema fazami OFF zmieniały się — nie należy więc przypisywać całej różnicy centralnego ROI wyłącznie IR.

Kamera działała przez USB3 podczas testu bez AI. Nie odnotowano nieplanowanej utraty komunikacji. Zmiany enumeracji USB między instancjami pipeline są spodziewanym zachowaniem start/stop.

## Artefakty lokalne

- Skrypt: `/srv/vision-data/staging/oak-overhead-v0/ir_visual_compare_20261112.py`
- Wyniki i zdjęcia: `/srv/vision-data/vision/sessions/oak-ir-compare-20261112/` (w tym `results.json`, 5 zestawów RGB/depth JPEG + PNG RAW16).
- Statyczna galeria porównawcza: `index.html` w katalogu wyników; czasowo udostępniana w sieci Tailscale na porcie 18093 przez testowy serwer HTTP ograniczony do 30 minut. **Nie jest częścią produkcyjnego Camera Service.**

## Stan po teście

- `IR_OFF_ACK True True` z testowego pipeline.
- `vision-oak-camera.service` przywrócona automatycznie: `ActiveState=active`, `SubState=running`, `NRestarts=0`, profil `balanced`, bez włączania IR.
- Z AI Platform przez Tailscale odczytano `online=true`, `UsbSpeed.SUPER`, około 30 FPS RGB i 29 FPS głębi; bez błędu. Galeria i obrazy kontrolnie pobrane z drugiego hosta (HTTP 200).

## Wniosek / kolejny krok

- **Dot projector 15%** jest rozsądnym kandydatem do przyszłego profilu aktywnego stereo, ale obecnie nie jest automatycznie włączany w produkcji. W tej scenie zysk pełnego kadru jest niewielki (~1,5 p.p.).
- Nie zaleca się pozostawiać flood 20% ciągle włączonego bez uzasadnienia wynikami w rzeczywistym położeniu ECU, szczególnie przy poborze dodatkowej mocy i pracy ciągłej.
- Przed zatwierdzeniem aktywnego IR dla produkcji: wykonać A/B na **nieruchomym PCB/ECU** z matowym wzorcem, w znanej odległości i po docelowym montażu; sprawdzić błąd głębi, powtarzalność, wpływ odbić i nagrzewanie podczas długiej sesji.
- Stan funkcji bezpieczeństwa NERO pozostaje niezależny od kamery; nie są dopuszczone żadne autonomiczne ruchy na podstawie tych pomiarów.


## Uzupełnienie: bezpośredni obraz monochromatyczny stereo / IR

Dodatkowa, osobna sesja kontrolowana (bez AI, bez NERO) na kamerze mono `CAM_B`, wyjście 1280×800 przy ~15 FPS. Zarejestrowano na NVMe pięć zdjęć `*_mono.jpg` przy OFF / dot 15% / flood 20% / dot+flood / OFF. Porównanie jest wizualne; **RGB i mapy głębi powstały w innej sesji i nie są zsynchronizowane czasowo z fotografiami mono.** Nie wprowadzano ręcznego blokowania autoekspozycji.

| Faza | Odebrane ramki / 6 s | Średnia jasność mono (0–255) | Odchylenie standardowe | Temp. [°C] |
|---|---:|---:|---:|---:|
| OFF przed | 91 | 103,89 | 66,24 | 49,9 |
| Dot 15% | 91 | 105,00 | 66,68 | 50,1 |
| Flood 20% | 91 | 105,33 | 66,56 | 49,4 |
| Dot 15% + flood 20% | 90 | 103,62 | 65,96 | 49,4 |
| OFF po | 92 | 103,99 | 66,28 | 49,4 |

Obserwacja wizualna: przy dot 15% na jasnej powierzchni stołu wyraźnie widać **rzutowaną siatkę punktów IR**; przy OFF ta tekstura znika. W centrum ujęcia leży ECU; rzeczywistej dokładności położenia ECU nie badano. Zmiany średniej jasności mono są niewielkie, co jest zgodne z tym, że efekt projektora polega przede wszystkim na dodaniu lokalnej tekstury ułatwiającej stereo, a nie na równomiernym rozjaśnieniu kadru. Flood może zwiększać oświetlenie bez analogicznego wzrostu jakości mapy głębi.

**Zakończenie:** `IR_MONO_PASS`, `MONO_IR_OFF_ACK True True`, produkcyjna usługa systemd przywrócona automatycznie. Po zakończeniu zdalny odczyt `/api/status`: `online=true`, profil `balanced`, `UsbSpeed.SUPER`, około 30 FPS RGB i 29 FPS głębi, IR domyślnie wyłączone. Galeria lokalna uzupełniona o fotografie monochromatyczne i sprawdzona z AI Platform (HTTP 200); pliki nie wychodzą do GitHub.
