# Vision Station Calibration V1 — karta pomiarowa

W każdym wpisie: wartość, jednostka, przyrząd, jego niepewność, czas, osoba, numer powtórzenia, identyfikator punktu, odsyłacz do zdjęcia/pliku. Nie zastępować pomiaru TF uzyskanym z optymalizacji.

| ID | Zadanie | Minimum |
|---|---|---|
| C0 | Sprzęt, zdjęcia, wersje oprogramowania, instrumenty i progi dokładności | 1 komplet |
| C1-1 | Szerokość/głębokość blatu, narożnik bazowy | 3× X i 3× Y |
| C1-2 | Siatka Z blatu i grubość, przeszkody i zaciski | 3×3 Z + wszystkie bryły |
| C2-1 | Otwory podstawy o **znanym ID w CAD**, położenie XY | ≥3 nieskoliniowane, 3× każdy |
| C2-2 | Wysokość podstawy, zgodność osi CAD +X | ≥3 Z i kontrola znaku |
| C3 | Wersja/sha oficjalnego modelu NERO i osi J1–J7 | 1 komplet |
| C4 | Siatka wydruku ChArUco, 5 kwadratów w obu osiach | ≥12 odczytów |
| C5-1 | Rozproszone PnP nieruchomej kamery | ≥10 kadrów / 5 pozycji |
| C5-2 | Fizycznie zmierzone przesunięcie planszy XY | ≥1 wektor 2D |
| C6 | Wzorce 3 wysokości w 5 XY, 10 ramek każda | ≥150 / tryb IR |
| C7-1 | Głębokość adaptera, obrót yaw, offset TCP i obrys | 3× każdy kluczowy wymiar |
| C7-2 | Masa Sony+adapter, środek masy gdy potrzebny | 1 masa |
| C8-1 | Niezależne kontrolne punkty XYZ | ≥5 |
| C8-2 | Przebieg walidacji MoveIt offline, test hash i raport | wszystkie PASS |
| C8-3 | Zatwierdzenie operatora, identyfikator wersji | 1 podpis |

**Porażki poprzednich testów do rozstrzygnięcia:** różnica przekątnej A/B od CAD 5.81mm; błąd przesunięcia ChArUco w XYZ 5.67mm; przesunięcie płaszczyzny depth względem modelu ~6.84mm; czerwony wzorzec IR OFF zaniżony o 10.87mm i IR Dot o 14.25mm. To punkty diagnostyczne, nie wartości do „wpisania” w nową kalibrację.
