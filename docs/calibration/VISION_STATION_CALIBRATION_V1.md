# Vision Station Calibration V1

**Stan:** PROTOCOL_READY, pomiary nowej sesji jeszcze nie rozpoczęte. Kalibracja nie jest zaakceptowana; pakiet nie uruchamia NERO.

## Zasada podstawowa
Jedno `table` (początek: lewy przedni narożnik blatu; +X w prawo, +Y w głąb, +Z w górę), jednostki surowych odczytów mm i stopnie, transformacje TF w m i rad. Rozdzielamy: pomiar fizyczny, oficjalny model CAD/URDF, kandydat TF oraz niezależny wynik walidacji. Stare TF pozostają archiwum i nigdy nie są automatyczną podstawą nowego profilu.

## Etapy i wymagane pomiary
**C0 — stan sprzętu i przyrządów:** Data, operator, identyfikatory NERO, OAK-D, instrumentów, wersje ROS2/DepthAI/firmware, rozdzielczość, tryb autofocus/IR/stereo, fotosy stanowiska i jednoznaczne mocowania. Przed pomiarem zapisać tolerancje odbioru właściwe dla zadania: foto PCB vs pozycjonowanie TCP.

**C1 — blat:** 3 odczyty szerokości, 3 głębokości, grubość, 9 punktów pomiaru płaskości Z (3×3), przekątne, położenie bazowego narożnika; obrysy i wysokości stałych przeszkód oraz zacisków. Dotychczasowe 2100×750 mm było założeniem symulacyjnym, nie zweryfikowanym wymiarem.

**C2 — podstawa NERO:** Minimum 3 *nieskoliniowane*, zidentyfikowane otwory mocujące z jednoznaczną korespondencją do CAD i 3 powtórzenia każdego odczytu XY; minimum 3 odczyty wysokości powierzchni mocowania. Niezależne potwierdzenie kierunku +X w `base_link` z fizycznym detalem modelu. Wyznaczyć `T_table_base_link` dopasowaniem rigid, zapisać RMS i maksimum residuum oraz sprawdzić rozstaw/diagonale. Odróżnić środek otworów od osi J1 i źródła base_link. Wczorajsze A=(645,50), B=(723,120) mm i wyliczone −93.094° to tylko archiwalne kandydaty.

**C3 — fabryczny robot:** Zidentyfikować oficjalną rewizję URDF/mesh i jej SHA256, nazwy J1–J7, osie, limity i `link7 → flange_link`. Zapisany snapshot J1–J7 jest runtime, nie kalibracją. Fabryczny flange: xyz=(.031,0,-.0235)m; rpy=(-1.5708,0,-1.5708)rad; zgodność z modelem to nie zatwierdzenie fizycznego adaptera.

**C4 — plansza ChArUco:** Jednoznacznie nazwać słownik ArUco, układ 5×7, mierzyć **zewnętrzną krawędź siatki**, nie margines lub format papieru. Mierzyć szerokość/długość zewnętrznej siatki oraz co najmniej 5 kwadratów w obu osiach. Projekt nominalny kwadratu 29.5mm; poprzedni pomiar wydruku 205×147mm nie miał potwierdzenia krawędzi. 217×145mm to unieważniona korekta, nie wejście.

**C5 — kamera Luxonis względem stołu:** Z nieruchomą kamerą min. 10 obrazów ChArUco w ≥5 rozproszonych pozycjach stołu (środek, rogi, krawędzie) plus znane, niezależnie zmierzone przesunięcie planszy w XY. Każda próbka: obraz oryginalny, camera_info, czas, wykryte narożniki, reprojection residual i PnP. Dopasować jeden `T_table_rgb_optical`, zweryfikować wariancję między ujęciami i porównać fabryczne TF `oak_parent → rgb_optical`. Podawać błędy translacji i rotacji; samo RMS w pikselach nie potwierdza mm.

**C6 — niezależna geometria 3D / DepthAI:** Co najmniej 3 niezależnie zmierzone wysokości (w tym 50.4mm można ponownie wykorzystać) × ≥5 lokalizacji XY × ≥10 ramek = ≥150 próbek *na konfigurację*. Oddzielne serie IR OFF i IR DOT jeśli mają być używane w pracy. Przechować surową głębię oraz XYZ po TF, lokalną płaszczyznę, błędy absolutne XYZ i wysokości, rozrzut MAD/RMS, synchronizację RGB/depth. Stary odczyt wzorca: 39.53mm IR OFF / 36.149mm IR DOT vs 50.4mm; to FAIL starej geometrii, nie korekta nowej.

**C7 — Sony/J7:** Z oficjalnego CAD adaptera v7 i makiety Sony A6000 V2 wyprowadzić bryłę i TCP, ale fizycznie zmierzyć osadzenie w J7, kąt/yaw wokół śruby, rzeczywiste obrysy, mocowanie i położenie osi obiektywu. Zważyć komplet (w razie wymaganej kompensacji wyznaczyć środek masy); osobno zapisać niepewność. Wczorajszy walec R89.148mm/L89mm to model diagnostyczny, nie finalna geometria.

**C8 — walidacja końcowa:** ≥5 punktów kontrolnych *nieużytych do dopasowania* (różne XY, co najmniej dwa Z), test projekcji i odwrotnego XYZ, relacji TF table/base/oak/tool, rozrzutu, bias i residuów. Dodatkowa izolowana regresja MoveIt 2: stolik, zaciski, adapter, samokolizje, kontrola wszystkich próbkowanych waypointów i brak nieoczekiwanego kontaktu. Nie wykonywać trajektorii fizycznej jako części walidacji kalibracji.

## Kryterium akceptacji
Ustalić przed zbieraniem danych dopuszczalne błędy dla konkretnego zadania. Odrzucić wyniki powyżej progu, nie maskować ich „korektą po fakcie”. `APPROVED` tylko po kompletnym rejestrze pomiarów, teście na niezależnych punktach, raporcie walidacji i podpisie operatora. `CANDIDATE` nigdy nie publikuje TF produkcyjnych ani nie jest używany do zapewnienia bezkolizyjności.

## Trwały profil
`capture` → `candidate` → `validate` → `approve` → jawne `activate`. Przechować w repo szablony, definicje i małe raporty; duże obrazy/chmury na NVMe w `/srv/vision-data/calibration/sessions/<session_id>/`. Po zatwierdzeniu utworzyć unikalny identyfikator wersji i manifest SHA256 dla modelu, TF, instrumentów, sesji i sceny MoveIt. Nie nadpisywać zatwierdzonych profili; zmieniać tylko nową rewizją z procedurą rollback. Zmiana fizycznego położenia kamery/podstawy, narzędzia lub trybu stereo unieważnia powiązane etapy. Ponowny start bez zmian wymaga sprawdzenia zdrowia urządzeń i spójności hashy, a nie nowej kalibracji. Status hamulców, CAN i J1–J7 to runtime.
