# Integracja urządzeń — plan weryfikacji

Żaden poniższy punkt nie stanowi potwierdzenia kompatybilności z VENTUNO Q.

## Sony A6100 (zamówiony)

Cel: pełnorozdzielcze ujęcia PCB i serie z kontrolowanymi parametrami. Testy: enumeracja USB, `gphoto2 --auto-detect` jeśli dostępny, lista funkcji zdalnych, zapis na hosta, powtarzalność wyzwalania, RAW/JPEG, ewentualny tethering. Nie zakładamy, że focus, zoom ani wszystkie funkcje aparatu można sterować programowo.

## Kamera radiometryczna (do wyboru)

Wymagane surowe dane temperatur per piksel, parametry kalibracji i możliwość zapisania korekt. Ujęcie pseudokolorowe bez danych radiometrycznych nie spełnia celu. Test: format, jednostki, zakres, emisyjność i współrzędne RGB→IR.

## Ramię (do wyboru)

Wymagane potwierdzenie udźwigu z Sony i obiektywem, zasięgu, powtarzalności, ograniczeń zakresu oraz interfejsu programowego. Tryb początkowy: obserwacja i pozycjonowanie ręczne, następnie testy na sucho w przestrzeni wolnej od DUT.

## Kamera głębi / 3D (opcjonalna)

Ma obserwować całe stanowisko z nieruchomego punktu, wykrywać przeszkody (złącza, radiatory, uchwyty) i pomagać planować bezkolizyjne ruchy. Nie traktujemy jej jako funkcji bezpieczeństwa. Nie używamy jej do metrologii mikropęknięć ani kontroli lutów.

## Oświetlenie

Ring + światła boczne, sterowalne i powtarzalne profile. Ważna jest synchronizacja ze zdjęciem i zapisywanie ustawień per ujęcie.

## Kryterium zamknięcia integracji

Dla każdego urządzenia wymagamy: fizycznego identyfikatora, sposobu połączenia, wersji sterownika, małego testu odczytu, testu błędu/odłączenia, dokumentacji ograniczeń oraz zgody na podłączenie do stanowiska produkcyjnego.
