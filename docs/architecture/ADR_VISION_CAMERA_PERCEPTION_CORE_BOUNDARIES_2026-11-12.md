# ADR-VISION-ARCH-001 — Rozdzielenie akwizycji kamer, percepcji i sterowania stanowiskiem

- **Data decyzji:** 2026-11-12
- **Status decyzji:** **ACCEPTED** — właściciel projektu zatwierdził podział architektoniczny
- **Status implementacji:** **PARTIAL / DESIGN CONTRACT** — Camera Service działa na VENTUNO Q w odrębnej gałęzi DEV/PROD-runtime; Perception Engine i Vision Core nie są jeszcze wdrożone jako ukończone usługi
- **Zakres:** Vision / VENTUNO Q / kamera overhead Luxonis OAK-D Pro AF / planowana Luxonis Eye-in-Hand / AgileX NERO / Sony A6100 / AI Platform
- **Rodzaj decyzji:** granice odpowiedzialności i kontrakty; **bez zgody na autonomiczny ruch robota, publikację kodu produkcyjnego ani zmianę mechanizmów bezpieczeństwa**
- **Powiązane dokumenty:** [ADR-VISION-ROBOT-001](ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md), [architektura historyczna](OVERVIEW.md), [release gates](../operations/RELEASE_GATES_2026-11-10.md)

## 1. Kontekst i problem

Vision ma wykrywać rodzaj i położenie ECU, wyznaczać geometrię 3D stanowiska, dostarczać robotowi NERO dane do planowania oraz wspierać obserwację zmian podczas pracy. Stanowisko **nie jest przede wszystkim przeglądarką obrazu**; WebGUI służy diagnostyce i konfiguracji.

Działa już eksperymentalnie wdrożony na VENTUNO Q **Vision Camera Service** z DepthAI 3.12.0: jeden właściciel USB, RGB, StereoDepth RAW16, lokalne API/HTTP, profil balanced i profile dodatkowe. Wykonano krótkie pomiary RGB-D i IR bez NN. Ten stan nie dowodzi jeszcze synchronizacji kompletów RGB–Depth, kalibracji względem stołu i NERO, długotrwałej stabilności, bezpiecznego wykrywania przeszkód ani gotowości ruchu autonomicznego. Kod Camera Service pozostaje w osobnym [PR #20](https://github.com/autoklinika/Vision/pull/20), nie został niniejszym ADR włączony do `main`.

Wcześniejszy pomysł włączenia całej geometrii, rozpoznawania ECU, nadzoru sceny i interfejsu ruchu do Camera Service prowadziłby do sprzężenia sterownika kamery z algorytmami i robotem, zwiększałby promień skutków awarii i utrudniał dodanie kamery Eye-in-Hand. Potrzebne są jasne granice.

## 2. Decyzja — trzy warstwy główne, osobne adaptery i system bezpieczeństwa

Zatwierdzamy następujący logiczny podział:

```text
Kamera overhead OAK-D Pro AF       Kamera Eye-in-Hand (przyszła)
             |                                  |
             v                                  v
       Camera Service                    Camera Service
       (akwizycja i USB)                 (akwizycja i USB)
             +------------------+---------------+
                                |
                wersjonowane, zsynchronizowane dane
                                v
                        Perception Engine
                (scena, lokalizacja ECU, geometria,
                 transformacje, jakość, zmiany sceny)
                                |
                obserwacje + niepewność + ważność
                                v
                          Vision Core
               (orkiestracja etapów analizy ECU,
                 decyzje i zarządzanie zadaniami)
                       /                  \
                      v                    v
               NERO Controller          AI Platform / RM
             (jedyny właściciel         (modele, inferencja
              komend ruchu)              i obliczenia AI)

  Niezależne zabezpieczenia i sprzętowy E-STOP:
  poza powyższym torem percepcji; priorytet nad ruchem.
```

**Warstwy logiczne nie są automatycznie osobnymi procesami systemd.** Wydzielenie procesu uzasadniamy wymaganiami izolacji awarii, wydajności, współdzielenia urządzeń i możliwości wdrożenia. Projektujemy interfejsy modułów teraz; nie uruchamiamy pełnego Vision Core przed przygotowaniem danych.

### 2.1. Camera Service — sterownik akwizycji

Camera Service odpowiada wyłącznie za:

- pojedyncze, wyłączne otwarcie danego urządzenia Luxonis i zarządzanie jego cyklem życia (USB, DepthAI, reconnect, health);
- konfigurację i wykonanie pipeline RGB, mono, stereo i IR, sterowanie ostrością, ekspozycją i parametrami obrazu w ramach jawnych profili;
- synchronizację strumieni i propagację znaczników czasu, numerów klatek, kalibracji **wewnętrznej** oraz oznaczenia źródła danych;
- publikację surowych lub bezstratnie reprezentowanych pomiarów głębi, RGB oraz diagnostyki (FPS, temperatura, utrata klatek, opóźnienia, stan połączenia);
- buforowanie o ograniczonym rozmiarze, udostępnienie wielu odbiorcom bez wielu właścicieli USB;
- diagnostyczne WebGUI, **nie** logikę procesu ECU ani autonomiczny planer ruchu.

Camera Service nie identyfikuje biznesowo ECU, nie zleca zadań AI Platform, nie rezerwuje RTX/GPU, nie ustala trajektorii NERO i nie wysyła komend ruchu. Nie implementuje niezależnej funkcji bezpieczeństwa.

Do jednego fizycznego OAK przypada jeden właściciel sprzętowy; dla kolejnej kamery dopuszczamy drugą instancję lub wspólną usługę obsługującą wiele urządzeń, ale **bez współdzielenia jednej sesji USB między procesami**.

### 2.2. Perception Engine — znaczenie i geometria sceny

Perception Engine jest odbiorcą danych Camera Service i odpowiada za:

- łączenie pomiarów w spójny stan sceny i odrzucanie nieaktualnych/niespójnych danych;
- przeliczenia `pixel + depth -> XYZ`, segmentację płaszczyzn, chmury punktów, powierzchnie, wymiary i orientację **w jednoznacznie nazwanym układzie odniesienia**;
- identyfikację i lokalizację ECU (na początku klasyczne algorytmy, w przyszłości AI), z informacją o jakości, niepewności i braku rozpoznania;
- wykrywanie zmian sceny, utraty widoczności i potencjalnych przeszkód jako **niesafety telemetry / ograniczenie operacyjne**;
- stosowanie zweryfikowanych kalibracji `camera -> table -> robot_base` i ich wersjonowanie;
- odtwarzalne działanie offline na zapisanych ramkach do testów bez robota.

Wyniki w układzie `robot_base` są **NIEDOSTĘPNE / INVALID**, dopóki nie zostanie wykonana i zweryfikowana właściwa kalibracja na docelowym stanowisku. Sama mapa głębi kamery nie potwierdza ani identyfikacji ECU, ani dokładności XYZ robota.

Perception Engine nie zarządza portem USB i nie wysyła CAN/ruchów do NERO. W późniejszym etapie może delegować ciężkie obliczenia do AI Platform, ale nie steruje Resource Managerem poza ustalonym API zleceń.

### 2.3. Vision Core — koordynacja procesu

Vision Core realizuje workflow: gotowość urządzeń, stan zadania ECU, sekwencję fotografowania/inspekcji, warunki przejścia do kolejnego etapu, wymianę danych i rejestrację wyników. Konsumuje **wyniki percepcji** z ich ważnością i źródłem, zamiast przejmować USB albo interpretować surowe klatki w pętli sterowania.

Na obecnym etapie nie wymagamy uruchomienia pełnego Vision Core. Definiujemy minimalny kontrakt klienta i symulator odbiorcy do testów integracyjnych (bez ruchu NERO).

### 2.4. NERO Controller — wyłączny tor komend ruchu

NERO Controller pozostaje jedynym właścicielem komunikacji i komend ruchu NERO. Weryfikuje gotowość, kontrolę stanów i dopuszczenie poleceń; żądanie z Vision Core to tylko **propozycja zadania/ruchu**, nie bezwarunkowa komenda napędowa. Wymagane są centralne interlocki, STOP latch i procedura odzyskiwania zgodne z [ADR-VISION-ROBOT-001](ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md).

**Percepcja nie jest funkcją bezpieczeństwa.** Jej ostrzeżenie może zatrzymać lub zablokować zadanie na poziomie programowym, ale brak danych, opóźnienie obrazu, błąd sieci czy awaria Linuxa nie mogą zostać potraktowane jako dowód bezpiecznej przestrzeni. Niezależny układ ochronny/E-STOP i ocena ryzyka pozostają konieczne przed dopuszczeniem ruchów.

### 2.5. AI Platform i Resource Manager

VENTUNO Q odpowiada za lokalną akwizycję i bieżący stan sceny, natomiast Minisforum AI Platform za zadania modelowe / cięższą analizę wykonywaną przez jego Resource Manager. Camera Service **nie** kontroluje alokacji GPU. Kontrakty między systemami są asynchroniczne, wersjonowane i tolerują brak AI Platform; zadania nie powinny blokować podstawowej akwizycji.

## 3. Minimalny kontrakt danych — wymagania do ustalenia przed implementacją

Dla zestawu danych kamerowych przygotowujemy wersjonowany schemat (roboczo `camera.frame_bundle.v1`, **jeszcze nie istnieje jako działające API**), który jednoznacznie przenosi co najmniej:

| Pole / grupa | Semantyka |
|---|---|
| `schema_version`, `camera_id`, `stream_id`, `frame_id`, `sequence` | pochodzenie i tożsamość danych |
| `device_timestamp`, `host_monotonic_timestamp`, `capture_age_ms` | zegary z oznaczoną domeną; nie traktować dowolnych timestampów jako zsynchronizowanych |
| `rgb`, `depth`, `pairing_delta_ms`, `sync_state` | identyfikatory sparowanych ramek, rozdzielczości i informacja o synchronizacji |
| `depth_unit=mm`, `invalid_depth_mask`, `aligned_to`, `coordinate_frame` | wartości, zera/braki, wyrównanie stereo/RGB i układ odniesienia |
| `intrinsics_id`, `extrinsics_id`, `calibration_revision` | identyfikatory i wiarygodność konfiguracji optyki oraz transformacji |
| `quality`, `valid_depth_fraction`, `drop_count`, `error` | jakość i diagnostyka, bez ukrywania niepewności |

Schemat wyników percepcji (roboczo `perception.scene_observation.v1`) opisuje: `object_id`/klasę lub `unknown`, pozycję i orientację z jednostkami, `frame_of_reference`, wersję kalibracji, przedziały/niepewność pomiarową, znacznik czasu, `source_frame_ids`, `validity`, ograniczenia oraz stan sceny. **Brak lub przeterminowanie klatki, niespójne timestampy, kalibracja niepasująca do montażu i nieznane układy odniesienia muszą prowadzić do `INVALID/NOT_READY`, nie do domyślnej pozycji 0,0,0 ani automatycznej akceptacji przez kontroler.**

Na poziomie transportu:

- HTTP/WebGUI pozostaje diagnostyką i dostępem operatorskim;
- sposób transportu szybkich ramek i geometrii (np. lokalne IPC, pamięć współdzielona, kolejka ograniczona, RPC) **jest do benchmarku**, nie narzucamy JSON/HTTP do pełnej chmury 3D 30 FPS;
- algorytmy pracują też na sztucznych/zapisanych danych z tym samym schematem;
- brak nieograniczonych kolejek; preferujemy najnowszy poprawny zestaw danych plus jawne liczniki odrzuceń;
- progi opóźnień i dopuszczalnego błędu pomiarowego ustalamy **po** testach, nie deklarujemy ich arbitralnie.

## 4. Kolejność wdrażania i bramki

1. **Camera Service**: jawna synchronizacja RGB–Depth, urządzeniowe timestampy, stabilność i reconnect, status jakości; walidacja na VENTUNO, bez IR/AI jeśli test tego nie wymaga.
2. **Perception Engine**: osobny moduł uruchamiany offline na nagraniach/replay; XYZ w układzie kamery, detekcja płaszczyzn, jakość, wersjonowane komunikaty i fałszywe obserwacje do testów.
3. **Kontrakt Vision Core**: prosty symulator klienta, brak uruchamiania ramienia; test utraty klatek, niespójnych zegarów, restartu i braku kalibracji.
4. **Docelowy montaż**: kalibracja `camera -> table -> robot_base`, wzorce, odchyłki i powtarzalność; aktualizacja ważności kalibracji przy fizycznej zmianie ustawienia kamery.
5. **NERO**: integracja tylko po spełnieniu odrębnych bramek sterowania i bezpieczeństwa, testów odczytu oraz świadomej zgody operatora na próby ruchu.

Nie włączamy nowego automatycznego rozpoznawania ECU, planera ani ruchu do obecnej usługi tylko dlatego, że podgląd RGB-D działa.

## 5. Konsekwencje i odrzucone alternatywy

**Korzyści:** testy bez robota, brak powielania uchwytów USB, wymienne algorytmy dla różnych ECU, przygotowanie Eye-in-Hand, mniejsza zależność podsystemów, łatwiejsza izolacja awarii i odtwarzanie próbek.

**Koszty:** potrzeba wersjonowania schematów, kontrolowania zegarów, backpressure, jakości oraz zgodności kalibracji; więcej testów integracyjnych. Nie rozwiązujemy automatycznie problemów deterministycznego czasu sterowania na zwykłym Linuxie.

**Odrzucamy:** (a) monolityczny Camera Service zawierający rozpoznawanie ECU i komendy NERO; (b) przenoszenie całej akwizycji USB do Vision Core; (c) uzależnienie lokalnej kamery od przydziałów GPU AI Platform; (d) uznawanie detekcji kamery za niezależne zabezpieczenie ramienia.

## 6. Zapis decyzji i ograniczenie zakresu zatwierdzenia

Właściciel **zatwierdził podział logiczny i kierunek prac** 2026-11-12. Niniejszy ADR jest decyzją **ACCEPTED** niezależnie od stanu wdrożenia. Nie jest protokołem uruchomienia produkcyjnego całego Vision, walidacją bezpieczeństwa NERO ani pozwoleniem na merge eksperymentalnego kodu.

Zasada [release gates](../operations/RELEASE_GATES_2026-11-10.md) pozostaje w mocy: osobna gałąź, PR, przegląd i **wyraźna zgoda na merge do `main`**. Utworzenie i zaakceptowanie ADR nie scala automatycznie PR #19, #20 ani archiwum PR #15.
