# Vision — zakres synchronizacji GitHub / 2026-11-10

**Cel:** skonsolidować dokumentację i pierwszostronny kod z prac lokalnych i istniejących gałęzi GH w gałęzi integracyjnej, **bez naruszania** `main` i bez modyfikowania usług na Vision.

## Pochodzenie

- Bazą jest publiczne `origin/main` z historycznymi testami VENTUNO i Sony (2026-10-10).
- Dokumenty, publiczne ograniczone JSON-y, skrypty eksperymentalne i testy zostały zebrane z otwartych gałęzi: `audit/ventuno-baseline-20261010`, `chore/vision-remote-mcp-autostart`, `feature/nvme-write-guard-v1`, `docs/hardware-verification-20261010`, `docs/ventuno-stm32-csi-can-20261011`, `docs/sony-a6100-hdmi-wifi-20261013`, `docs/sony-a6100a-hdmi-wifi-usb-20261013`, `docs/sony-protocol-audit-20261013`, `feature/sony-stability-50-100-20261014`, `docs/vision-thermal-v06-freeze-20261015`, `docs/adr-nero-two-stage-stop-20261110`. Wybrane nowsze gałęzie Sony zawierają już przyrosty prototypów AF/BLE.
- Pierwszostronne skrypty START/STOP i profil Stream Deck zostały skopiowane z aktywnego w przeszłości katalogu `/srv/vision-data/tools/streamdeck-prod`; referencyjny próbnkik odczytu SDK NERO z `/srv/vision-data/tools/nero-sdk`.
- Oba katalogi są **poza** oryginalnym repo. Do Git trafiły tylko zanonimizowane kopie w `ops/nero`, `ops/streamdeck` i `scripts/robot`.

## Ochrona i sanitizacja

- Usunięto z publicznych kopii **identyfikator seryjny adaptera AgileX USB-CAN**; podczas użycia wzoru należy przekazać lokalną zmienną `VISION_NERO_CAN_SERIAL` poza repozytorium.
- Nie przeniesiono katalogów `~/.ssh`, `~/.config/gh`, agenta Remote MCP, tożsamości, tokenów, logów i historii, zdjęć JPEG/RAW, sesji kamer, danych pomiarowych, katalogów Docker, binariów i całych SDK firm trzecich.
- Ograniczone dowody JSON są już opublikowanymi elementami istniejących gałęzi GitHub; przeszły automatyczny skan typowych identyfikatorów i prywatnych adresów, jednak nie zastępuje to pełnej kontroli człowieka.
- Pełny kod Thermal v0.6, środowisko kontenera i zewnętrzne zależności licencyjne pozostają **tylko na NVMe**, zgodnie z raportem zamrożenia.
- Nie publikujemy pełnego archiwum `/srv/vision-data`; to repozytorium kodu i dokumentacji, nie obraz systemu.

## Rozdzielenie wersji kodu

| Katalog w repo | Znaczenie |
|---|---|
| `docs/architecture` | architektura, ADR NERO i Sony, polityka NVMe |
| `docs/hardware`, `docs/audits` | dowody i raporty z testów, także testy historyczne |
| `docs/operations` | nowy stan faktyczny, instalacja/odtwarzalność i lista ryzyk |
| `scripts/audit` | narzędzia eksperymentalne do testowania aparatu |
| `scripts/experiments` | archiwalne autorskie testy Sony USB/PTP, Stream Deck/BLE, GPU i NPU; adresy BLE zanonimizowane, bez SDK i plików RAW |
| `scripts/robot` | odczyt przez SDK; **może konfigurować CAN** po użyciu z `sudo`, nie uruchamiać automatycznie |
| `ops/nero` | zanonimizowana referencja produkcyjnego skryptu STOP SW, nie certyfikowana funkcja bezpieczeństwa |
| `ops/streamdeck` | profil i pliki usług/wtyczek jako wzory. Binarny OpenDeck zostaje lokalnie na NVMe |
| `ops/remote-mcp` | wersjonowane źródło wdrożonej usługi Remote MCP z wcześniejszej gałęzi |
| `scripts/storage`, `tests/` | kod, testy i CI z niezintegrowanych wcześniej gałęzi |

## Walidacja przed publikacją

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`: **96 testów PASS** na VENTUNO, z atrapami sprzętu; brak faktycznych komend ruchu, zdjęć lub zmian CAN.
- Parser `ast.parse`: **41 plików Python PASS**; `bash -n`: wszystkie skrypty powłoki PASS.
- Skan typowych sekretów, prywatnych adresów IP, Bluetooth MAC i seryjnych numerów USB: **brak dopasowań w publikowanych źródłach**. To kontrola automatyczna, nie pełny audyt bezpieczeństwa.

## Status po przygotowaniu

Zmiany są publikowane przez nowy PR z osobnej gałęzi integracyjnej. Inne PR-y nie są automatycznie zamykane, a `main` nie ulega zmianie do czasu jawnej zgody. Nie uruchomiono przy tym ani jednego polecenia ruchu robota, migawki aparatu, ani zmiany firmware.
