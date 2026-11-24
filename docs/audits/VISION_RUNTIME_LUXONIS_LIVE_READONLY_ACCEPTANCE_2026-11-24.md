# Vision Runtime V1 — fizyczny odbiór Luxonis (read-only)

**Data testu:** 2026-11-24
**Status końcowy:** **PARTIAL ACCEPTANCE — ROS2 STREAM & ADAPTER PASS; ECU S03/S04 NOT READY**.
**Urządzenie:** istniejąca OAK-D Pro AF na stanowisku Vision; ROS 2 Jazzy, oficjalny DepthAI ROS v3.
**Tryb:** wyłącznie subskrypcje już uruchomionych tematów ROS 2; bez startu drugiego sterownika, zmian parametrów, zapisu do VGP, poleceń do NERO/Sony/CAN lub deploymentu.
**Kod:** kandydat Vision Runtime V1 z PR #50 (nie scalono do main).

## 1. Pomiary sprzętowe z działającego sterownika

Sterownik już pracował przed testem. Użyto istniejących publikatorów domeny ROS 186 i osobnego, krótkotrwałego odbiornika. Nie uruchamiano ani nie restartowano żadnego sterownika czy systemowej usługi.

| Obserwacja | Rzeczywisty wynik | Status |
| --- | --- | --- |
| USB i graf ROS2 | OAK widoczna; węzeł `/oak` i odpowiednie publikatory ROS 2 | PASS |
| RGB | `/oak/rgb/image_raw`; `bgr8`, 1920×1080, 6 220 800 B; 59 odebranych wiadomości w pierwszej 19-sekundowej sondzie | PASS |
| Depth | `/oak/stereo/image_raw`; `16UC1`, 1920×1080, metryczna głębia **mm**, 4 147 200 B; 66 wiadomości | PASS |
| CameraInfo | RGB 193 i Depth 197 wiadomości; 1920×1080; ramki i intrinsics zgodne z obrazami | PASS |
| RGB/Depth frame | Oba `oak_rgb_camera_optical_frame` w aktualnym wyrównanym strumieniu | PASS |
| Jakość głębi | 2109/2400 i 2119/2400 ważnych próbek w dwóch pierwszych klatkach (~88%); mediana pierwszej próbki 786 mm | PASS — próbkowany obraz, nie pomiar geometrii ECU |
| PointCloud2 | `/oak/rgbd/points`; odczyt z `RELIABLE` QoS; 1920×1080, 33 177 600 B, pola x/y/z/rgb | PASS |
| Chmura — próbki XYZ | 2122/2400 ważnych punktów (88,4%); mediana Z = 0,791 m | PASS — zgodne z głębią |
| TF lokalny Luxonis | `oak_parent_frame → oak → oak_rgb_camera_optical_frame` | PASS |
| TF stacja/robot | Brak dostępnej transformacji `world → oak_rgb_camera_optical_frame` w aktywnym grafie | **BLOCKER dla lokalizacji w świecie stanowiska** |

Wynik mediany w zakresie 786–791 mm jest zbliżony do wcześniejszego pomiaru wysokości kamery 793 mm. Nie służy jednak do nowej kalibracji ani zatwierdzenia modelu stanowiska.

Pierwsza próba z `BEST_EFFORT` nie odebrała PointCloud2; oddzielny odbiornik z `RELIABLE` odebrał i sprawdził wiadomości. Nie ustalono przyczyn pierwszej próby ani trwałej wydajności chmury.

## 2. Bezpośredni test kodu PR #50 na rzeczywistych wiadomościach

Kolektor `SnapshotCollector` z PR #50 odbierał istniejące obrazy, CameraInfo i TF. Po usunięciu niezgodności typu numerycznego i poprawnym przekazaniu znaczników czasu do tf2:

- **3 rzeczywiste pakiety RGB-D + CameraInfo + lokalny TF przeszły walidację**.
- Jeden przy limicie synchronizacji **100 ms**: różnica RGB–Depth około **0,06 ms**, rozrzut wszystkich znaczników około **66,67 ms**.
- Dwa przy limicie **200 ms**: różnice RGB–Depth około **66,61 ms** i **199,96 ms**.
- Pozostałe próby bywały odrzucane jako `no synchronized stream set`. To prawidłowe `fail-closed`, ale osiąganie ciągłej synchronizacji i FPS wymaga dalszych pomiarów.
- TF do `oak_parent_frame` działa; brak `world → kamera` pozostaje nierozwiązany.
- PointCloud2 został zweryfikowany **oddzielnie**. Obecny `RGBDFramePacket` Runtime nie używa PointCloud2 jako dowodu lokalizacji ECU.

## 3. Defekt ujawniony przez rzeczywisty ROS2 Jazzy

Przy pierwszym uruchomieniu PR #50 błędnie odrzucono rzeczywiste CameraInfo. W Jazzy macierze K/R/P mogą być dostarczane jako tablice NumPy z elementami `numpy.float64`. Adapter wcześniej wymagał dokładnie wbudowanych typów `int` lub `float`.

Naprawa w gałęzi PR #50: akceptować skończone `numbers.Real` (łącznie z NumPy `float64`), nadal odrzucać `bool`, NaN/Inf, ciągi i błędne typy. Dodano cztery testy regresyjne z danymi typu odpowiadającego rzeczywistym CameraInfo.

Sonda tf2 musi konwertować wewnętrzny, niezmienny znacznik czasu adaptera do `rclpy.time.Time(seconds=stamp.sec, nanoseconds=stamp.nanosec)`; nie można użyć `Time.from_msg` dla nie-ROS-owego obiektu `_Stamp`. Zmiana dotyczy sondy integracyjnej; sposób wywołania TF należy zachować w przyszłym uruchomieniu produkcyjnym.

## 4. Czego NIE zatwierdzono

- Fizycznych etapów Core **S03/S04**: brak uruchomionej, niezależnie zweryfikowanej estymacji bryły i landmarków ECU powiązanej z danymi RGB-D; kod nie wytwarza takiej estymacji sam.
- Tożsamości ETC3: referencyjny profil rzeczywistego ETC3 pozostaje `DRAFT / NOT_READY`. Nie wolno na podstawie poprawnych strumieni oznaczyć sterownika jako potwierdzonego.
- Kalibracji `world → kamera`: aktywne drzewa TF robota i OAK nie mają wspólnego połączenia. Nie zakładano ani nie wstrzykiwano niezatwierdzonej transformacji.
- Wydajności ciągłej synchronizacji i wielosekundowej niezawodności PointCloud2: wykonano ograniczone, kontrolowane próby, nie test długotrwały.
- Wdrożenia Runtime PR #50 do uruchomionych usług Vision; zamrożony VGP V1 zachowany bez zmian.

## 5. Werdykt i następne kroki

**PASS:** urządzenie Luxonis, aktualne strumienie RGB / Depth / CameraInfo / PointCloud2, poprawne jednostki głębi, lokalne TF oraz poprawność parsowania rzeczywistych wiadomości przez adapter Runtime V1.

**BLOCKED / NOT READY:** pełny fizyczny odbiór S03/S04 z identyfikacją ECU i pozycją w `world`. Niezbędne są zatwierdzona transformacja stanowiska, niezależny estimator pozy oraz rzeczywisty zatwierdzony profil ECU.

Prace wykonywano w oddzielnym prywatnym katalogu staging; przechowywane są tylko metadane, statystyki, hashe i krótkotrwałe sondy. Nie publikowano surowych zdjęć, numerów urządzeń, prywatnych adresów ani danych dostępowych. Aktywny VENTUNO i baza VGP V1 pozostały bez zmian.
