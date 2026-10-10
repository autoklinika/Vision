# Vision

Stanowisko akwizycji obrazu i inspekcji fotograficznej płytek PCB / sterowników ECU, rozwijane na Arduino VENTUNO Q (Qualcomm QCS8275).

> **Status:** szkielet projektu. Repozytorium nie zawiera jeszcze uruchomionej aplikacji, sterowników urządzeń ani zweryfikowanego potoku akwizycji. Każda integracja sprzętowa wymaga osobnego testu.

## Cel i podział odpowiedzialności

**VENTUNO (Vision)** jest lokalnym kontrolerem stanowiska: obsługuje wykonywanie zdjęć, pozyskiwanie termowizji radiometrycznej, ocenę ostrości/ekspozycji/pokrycia, rejestrację przestrzenną, mozaiki i focus stacking, kalibrację oraz wspomaganie ustawiania kamery i planowania ruchu ramienia. Może wykorzystywać OpenCV i lekki model detekcyjny *wyłącznie po weryfikacji kompatybilności*.

**AI Platform** wykonuje wnikliwą analizę zdjęć PCB, wnioskowanie i przygotowanie raportów. Nie przenosimy dużych modeli analitycznych na VENTUNO. Sposób przekazywania wyników do AI Platform pozostaje do zaprojektowania; projekty i repozytoria są odrębne.

## Planowany sprzęt

- Arduino VENTUNO Q — lokalny komputer/sterownik stanowiska, Ubuntu 24.04 ARM64.
- Sony A6100 — aparat fotograficzny, **zamówiony**; sterowanie przewodowe i lista dostępnych funkcji wymagają testu.
- Kamera termowizyjna **radiometryczna** — model/interfejs jeszcze niezatwierdzone; nie wystarczy zwykły obraz pseudokolorowy.
- Ramię robota — model jeszcze niezatwierdzony; wymagana ocena zasięgu, udźwigu, sztywności i bezpieczeństwa.
- Nieruchoma kamera głębi/3D — rozważana do mapowania przeszkód i wspomagania unikania kolizji; nie jest czujnikiem bezpieczeństwa funkcjonalnego.
- Sterowane oświetlenie (ring + światło boczne) i uchwyty/kalibratory stanowiska.

Wpis na liście nie oznacza, że dane urządzenie jest już podłączone lub wspierane przez sterowniki.

## Zasady inżynierskie

1. Rozdzielamy akwizycję, jakość/kalibrację, przetwarzanie obrazu, termowizję, sterowanie robotem i integracje.
2. Warstwa sterowania robotem nie może traktować predykcji AI ani kamery głębi jako gwarancji bezpieczeństwa; ograniczenia ruchu, E-stop i interlocki muszą być niezależne.
3. Zachowujemy oryginalne zdjęcia i dane radiometryczne oraz ich metadane; dane pochodne są odtwarzalne.
4. Nie modyfikujemy środowiska Qualcomm/Arduino bez audytu i udokumentowanej potrzeby.
5. Na razie nie wykonujemy operacji sterowania mechaniką, grzania ani zasilania DUT.
6. Kod rozwijamy na gałęziach i przez PR. Merge do `main` wymaga wyraźnej zgody właściciela projektu.
7. Nie publikujemy tokenów, kluczy prywatnych, danych dostępowych, zrzutów środowiska z sekretami ani surowych sesji roboczych.

## Plan prac

1. Repozytorium i dokumentacja bazowa.
2. Audyt VENTUNO (tylko odczyt): system, storage, Qualcomm GPU/NPU, USB/kamery, biblioteki.
3. Prototyp akwizycji zdjęcia i zapis pełnej metadanej.
4. Kontrola jakości ujęć i kalibracja.
5. Mozaika i focus stacking; testy na rzeczywistych PCB.
6. Radiometria, kalibracja wspólnej przestrzeni i mapa stanowiska.
7. Sterowanie ramieniem z niezależnymi zabezpieczeniami.
8. Eksport danych do AI Platform według jawnego kontraktu.

Szczegóły: `docs/architecture/`, `docs/hardware/`, `docs/process/`, `scripts/audit/`.

## Stan połączeń administracyjnych

SSH przez sieć lokalną / Tailscale oraz SSH przekierowany przez ADB USB-C zostały ręcznie potwierdzone na urządzeniu `vision`. Adresy i dane sieciowe nie są elementem konfiguracji repozytorium.
