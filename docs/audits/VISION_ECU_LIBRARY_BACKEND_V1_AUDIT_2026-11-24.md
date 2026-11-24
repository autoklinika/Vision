# Vision ECU Library Backend V1 — audyt offline

Data: 2026-11-24.
Status: backend przygotowany do Draft PR. Bez GUI, WebGUI, HTTP, wdrożenia i urządzeń.
Zależności: dokumentacja PR #47 jest w main; katalog ECU Profiles V1 to Draft PR #46, ECU Reference Profile V1 to Draft PR #48.

## Zakres

Niezależny od transportu moduł Python vision_modules.ecu_library_backend zapewnia jawny wybór rodziny, wariantu i rewizji ECU, tworzenie roboczego ReferenceProfile DRAFT z oryginalnego 15-sekcyjnego szablonu, walidację i listę braków, prywatny zapis, atomowe publikowanie generacji, niezmienną historię i ETag.

Dodatkowo udostępnia bezpieczny import zdjęć PNG/JPEG jako prywatnych i niezweryfikowanych zasobów oraz metadane pól do późniejszego WebGUI, bez implementacji interfejsu lub transportu.

Nie ma własnego wykonawcy trajektorii, możliwości zatwierdzenia ECU, rozpoznawania automatycznego, dostępu do kamery ani serwera.

## Odtworzone i naprawione błędy

| ID | Błąd przed naprawą | Mechanizm korekty |
| --- | --- | --- |
| B01 | Kanoniczny ASCII JSON przekraczał 512 KiB po zapisaniu poprawnego Unicode; kolejny odczyt nie działał | Kontrola rozmiaru dokumentu i snapshotu przed zapisem |
| B02 | Awaria między historią a plikiem bieżącym mogła zostawić fałszywą ukończoną zmianę | Atomowy wskaźnik generacji; historia tylko w łańcuchu zatwierdzonego wskaźnika |
| B03 | Przywrócenie treści A→B→A odtwarzało stary ETag | Nowy ETag powstaje z unikalnego identyfikatora generacji |
| B04 | PNG mały na dysku mógł zająć ogromną pamięć po dekodowaniu | Limity liczby pikseli przed i po dekodowaniu; maksymalnie 30 MP |
| B05 | Uszkodzony albo brakujący starszy snapshot nie blokował odczytu obecnego | Weryfikacja całej historii podczas odczytu i zapisu |
| B06 | Zmieniony link poprzedniej generacji mógł skrócić historię bez sygnału | Snapshot SHA-256 obejmuje tożsamość, generację i pole previous |

Każda klasa została odtworzona testami RED przed poprawką. Testy dodatkowe obejmują symulowane przerwania zapisu, złą historię, konflikt ETag między procesami, symlinki, niepoprawne obrazy i rozdzielczość Sony 24 MP.

## Granice

ETC3 ma status DRAFT / NOT_READY, układ 2 czarnych i 1 szarej wtyczki oraz niezweryfikowane notatki 65/69 mm. Brak zatwierdzonej bryły, zdjęć i kalibracji.

Importowany obraz pozostaje UNVERIFIED. Weryfikacja hashów służy spójności, a nie podpisowi recenzenta albo autentyczności sensora. Lokalny magazyn nie jest certyfikowanym WORM; jego prawa dostępu, kopie zapasowe i zatwierdzenia należą do przyszłego zaufanego procesu. Osierocone pliki po awarii nie są uznawane za zatwierdzone rewizje.

WebGUI jest odłożone decyzją właściciela. Nie wprowadzono HTML, JS, HTTP, serwera lub usługi uruchamianej samoczynnie.

## Wynik

- 395/395 testów PASS w niezależnym Docker bez sieci i urządzeń.
- compileall PASS.
- Sprawdzenie zakresu i braku zmian Core, PR46, PR48 oraz aktywnego VENTUNO PASS.
- GitHub CI wymaga końcowego potwierdzenia po publikacji PR.
- Nie scalać modułu bez osobnej decyzji właściciela.
