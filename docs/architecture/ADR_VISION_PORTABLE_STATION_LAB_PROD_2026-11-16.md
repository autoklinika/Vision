# ADR-VISION-STATION-001 — Jedno Vision, profile środowiska LAB i PROD

- **Data:** 2026-11-16
- **Status:** **PROPOSED** — uzgodniony w rozmowie kierunek projektowy, do formalnego zatwierdzenia przy przeglądzie PR.
- **Dotyczy:** ROS 2 / MoveIt 2, kinematyki NERO, geometrii stanowiska, kalibracji i pierwszego scenariusza ETC3.
- **Raport źródłowy:** [ROS 2, NERO i przenośne stanowisko](VISION_ROS2_NERO_LAB_TO_PROD_TECHNICAL_REPORT_2026-11-16.md).
- **Granica:** nie zmienia uruchomionych usług, nie stanowi zgody na ruch robota.

## Kontekst

Vision powstaje obecnie w laboratorium z tymczasowo mocowanym NERO. Docelowo robot ma zostać przeniesiony na stabilny, dedykowany stół i zamontowany przez fabryczne otwory. Zmianie ulegną co najmniej: geometria blatu, pozycja i orientacja podstawy, przeszkody stałe, strefy robocze i prawdopodobnie prowadzenie kabli. Jednocześnie chcemy od razu rozwijać i testować ROS 2, MoveIt 2, Luxonis, Sony oraz profile ECU bez oczekiwania na finalny stół.

## Decyzja proponowana

1. **Portable Station Architecture:** jeden kod i jeden zestaw kontraktów Vision; co najmniej dwa identyfikowane profile `laboratory` i `production` z oddzielnymi kalibracjami i wersjonowanymi modelami sceny.
2. **Calibration Required:** zmiana pozycji podstawy, mocowania kamery/narzędzia, geometrii stołu lub komponentu mającego wpływ na kalibrację unieważnia odpowiednie dopuszczenie ruchu. System wraca do `NOT_READY` do czasu nowej walidacji.
3. **ECU-Relative Inspection:** cele inspekcji opisujemy w układzie współrzędnych ECU lub jego cech, a nie współrzędnych laboratoryjnego stołu. Bieżąca transformacja ECU + aktywny profil stanowiska pozwalają przeliczyć cel na pozycję robota.
4. **No trajectory reuse:** trajektorii `LAB` nie przenosimy automatycznie do `PROD`; każda zmiana stanowiska wymusza ponowne planowanie i test kolizji.
5. **Fail closed:** brak wymiarów, kalibracji, wersji modelu narzędzia, odczytu pozycji albo ważnej mapy przeszkód blokuje zadania ruchu. Nie dopuszcza się „domyślnego zera” ani odzyskania starego profilu bez weryfikacji.
6. **Właściciel geometryczny:** jeden kontrolowany profil transformacji świata/robota/narzędzi; brak konkurujących źródeł tego samego TF w działającym ROS 2.
7. **Granica bezpieczeństwa:** oznaczenie profilu `READY` jest tylko warunkiem aplikacyjnym. Nigdy nie zastępuje niezależnych zabezpieczeń wymaganych dla ruchu fizycznego.

## Proponowana dekompozycja danych

| Artefakt | Zawartość | Wymaga zmiany przy przenosinach? |
| --- | --- | --- |
| `RobotConfig` | NERO, model URDF/SRDF, ograniczenia osi, sterownik | nie, o ile bez zmiany hardware |
| `ToolingConfig` | adapter J7, Sony, Luxonis, masy, obwiednie i ekstrynsyki | sprawdzenie / aktualizacja, gdy zmienia się mocowanie |
| `StationProfile` | płaszczyzna stołu, podstawa NERO, przeszkody, strefy, rewizje | **tak** |
| `Calibration` | hand–eye, transformacje world/base, intrinsics i walidacja | **wymagana nowa kwalifikacja odpowiedniego zakresu** |
| `ECUProfile` | nominalne wymiary i cechy ETC3, obszary inspekcji | nie, jeśli zmienia się tylko stanowisko |
| `SessionState` | rzeczywista pozycja egzemplarza, scena, zdjęcia, dowody | każdorazowo nowa sesja |

Dane geometryczne w jednostkach SI, jawne `frame_id`, konwencja orientacji, data kalibracji, identyfikator urządzenia/narzędzia, poziom wiarygodności i wersja każdej zależności. Kalibracja posiada identyfikator, wynik testu i ślad dowodowy.

## Warunki wdrożenia

- Wybrana nazwa ramki świata (roboczo `table`) i konwencja osi muszą być opisane w jednym miejscu.
- Launch nie może automatycznie uruchomić rzeczywistego kontrolera z `auto_enable`/`control_enabled` bez nadzoru.
- Aktywny profil jest jawny w HMI, logach, metadanych zdjęć i sesji ROS.
- Operator nie przełącza środowiska w trakcie zadania lub ruchu; przełączenie wymaga nowego preflight.
- Po relokacji: pomiar podstawy, rewizja sceny, weryfikacja tool frames i kalibracji, testy kolizji, testy zatrzymania i niezależnych zabezpieczeń.
- Dopóki nowy profil nie przejdzie bramek, dozwolone są tylko diagnostyka i symulacja offline.

## Konsekwencje

**Korzyści:** rozwój bez oczekiwania na mebel docelowy, jeden stos robotyczny, większa powtarzalność testów i reużywalność profili ECU, łatwiejsza wymiana stanowiska lub kamery.

**Koszty:** wersjonowanie geometrii i kalibracji, jawne stany unieważnienia, procedura relokacji i dodatkowe testy. Nie gwarantuje automatycznej przenośności gotowych trajektorii ani dokładności metrologicznej.

## Alternatywy odrzucone / odłożone

- Twarde współrzędne stołu w planie ETC3 — odrzucone, wiążą plan z jednym stanowiskiem.
- Osobne aplikacje `Vision-LAB` i `Vision-PROD` — odrzucone, prowadzą do dryftu kodu.
- Skopiowanie starej kalibracji po przenosinach — odrzucone, może powodować błędne obliczenia i kolizje.
- Wdrożenie pełnej autonomii NERO już w laboratorium — **odłożone** do czasu niezależnej oceny bezpieczeństwa i wyników testów fizycznych.

## Weryfikacja tej decyzji

1. Ten sam scenariusz ETC3 offline działa na dwóch **syntetycznych** geometriach stanowiska bez modyfikacji profilu ECU.
2. Przy braku `calibration_revision`, `station_geometry_revision` lub niezgodnym `tooling_revision` system odmawia wykonania ruchu.
3. Zmiana profilu unieważnia poprzedni plan trajektorii i zostaje odnotowana w sesji.
4. Test regresyjny: zaplanowany przejazd kolidujący z obiektem w `PROD` musi zostać odrzucony, choć mógł być poprawny w `LAB`.
5. Fizyczny ruch pozostaje zablokowany do odrębnego dopuszczenia i oceny niezależnego bezpieczeństwa.

**Status końcowy:** ADR jest propozycją architektoniczną, nie oznacza implementacji ROS 2 ani fizycznego uruchomienia NERO.
