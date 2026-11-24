# ETC3 — karta profilu PoC V1 (robocza)

**Rodzina ECU:** ETC3
**Identyfikator profilu:** etc3_poc
**Wariant:** provisional_3connector — wewnętrzny identyfikator roboczy, **nie** potwierdzony numer producenta
**Rewizja:** v1
**Status:** DRAFT / NIEZATWIERDZONY
**Źródło główne:** ustalenia Vision 14.11.2026, docs/architecture/VISION_FOUNDATION_2026-11-14.md
**Plik danych:** config/ecu_profiles/etc3_poc_v1.json

## Co jest udokumentowane

| Cecha | Wartość robocza | Status |
| --- | --- | --- |
| Złącza | 3: dwie czarne, jedna szara | Obserwacja operatora, wymaga weryfikacji konkretnego wariantu |
| Wysokość przy szarej wtyczce | 69 mm | NOTATKA TERENOWA — brak zatwierdzonego początku układu i niepewności |
| Wysokość przy czarnej wtyczce | 65 mm | NOTATKA TERENOWA — brak zatwierdzonego początku układu i niepewności |
| Wymiary obudowy (X/Y/Z) | nieustalone | BLOKADA |
| Obramowanie, punkty mocowania i przeszkody | nieustalone | BLOKADA |
| Pozycje XYZ złączy w układzie ECU | nieustalone | BLOKADA |
| Obszar(y) PCB przy otwartym sterowniku | nieustalone | BLOKADA |
| Wymagane ujęcia i orientacje aparatu | nieustalone | BLOKADA |
| Tolerancje, źródła i rewizje kalibracji | niezatwierdzone | BLOKADA |
| Ostateczny wariant / numer producenta | niepotwierdzony | DO USTALENIA |

**Uwaga metrologiczna:** wartości 69 i 65 mm to przekazane wcześniej orientacyjne notatki o wysokościach wtyczek, nie zatwierdzona wysokość obudowy ani bezpieczny prześwit. Nie wolno ich bez dodatkowych pomiarów wykorzystywać w MoveIt, przy wyborze trajektorii ani do obliczenia wysokości narzędzia.

## Kolejność uzupełniania profilu

1. Ustalić lokalny początek współrzędnych ECU, osie X/Y/Z i fizyczny datum, wspólny dla wszystkich pomiarów. Oddzielić geometrię ECU od geometrii stołu i NERO.
2. Zmierzyć obudowę X/Y i maksymalną wysokość Z, z uwzględnieniem wystających złączy i elementów. Zapisać przyrząd, datę, źródło, niepewność i referencję.
3. Zmierzyć osobno złącza black_1, black_2, gray_1: ich środki XYZ, orientację i najwyższe punkty z tego samego datumu. Potwierdzić, do którego złącza odnosiły się wcześniejsze notatki 65 i 69 mm.
4. Dla otwartej płytki wyznaczyć lokalne prostokąty inspekcji PCB i ewentualne strefy niedostępne. Odrębnie potwierdzić ich geometrię.
5. Zapisać zestaw ujęć fotograficznych jako cele XYZ oraz kwaterniony XYZW **w układzie ECU**. Zapisane XYZ reprezentuje zadany punkt narzędzia/aparatu, a nie obszar widoczności PCB. Zdjęcia skośne mogą mieć pozycje XY poza obrysem płytki.
6. Zdefiniować wymagania RAW/JPEG, ostrości i jakości, oczekiwaną dokładność i źródła pomiarowe dla położenia i orientacji każdego ujęcia. Zweryfikować możliwości aparatu i kalibracji.
7. Porównać rzeczywistą obserwację z deklarowanym profilem: pozycje złączy i cechy rozróżniające od innych zarejestrowanych wariantów ETC3. W przypadku niejednoznaczności blokować przejście.
8. Po komplecie źródeł wykonać niezależny przegląd, nadać nową rewizję, zatwierdzić jej SHA-256 oraz opublikować niezmienny snapshot. Dopiero wtedy wolno użyć kontrolowanej ścieżki promocji do Core.

## Obowiązujące blokady

- DRAFT nie przechodzi aktywacji jako approved Core ECUProfile.
- Nie wystarcza sama deklaracja operatora ani rozpoznanie kolorów złączy.
- Nie wolno automatycznie dopasowywać profilu innego wariantu.
- Akceptacja pomiaru i potwierdzenie rzeczywistego ECU należą do osobnych bramek.
- Obecny PoC służy do opracowania i weryfikacji kontraktu danych, **nie** do ruchu NERO ani wykonywania zdjęć.
