# Vision — historia pierwszostronnych eksperymentów sprzętowych

Zapisujemy tutaj wybrane **autorskie narzędzia laboratoryjne** z NVMe VENTUNO Q (stan z 2026-11-10) i bez dołączania instalacji SDK, kontenerów, surowych zdjęć lub danych paczek producentów.

## Zawartość

- `sony-a6100-verify/` — oryginalne skrypty eksperymentalne Sony USB/PTP, analiza zdjęć, porównywanie ostrości i diagnostyka bez przebudowy głównego Vision Core.
- `streamdeck-eval/` — skrypty ewaluacyjne Elgato HID/OpenDeck oraz testy BLE Sony; **mogą sterować migawką, zoomem i wyświetlaczem**.
- `npu-verify/` — autorskie próby działania HTP/QNN; bez binarnych bibliotek Qualcomm i modeli.
- `ventuno_gpu_verify.py` — test GPU; zależności Qualcomm/Vulkan instalowane oddzielnie.

## Status i ostrzeżenia

1. **ARCHIVE / EXPERIMENT**, a nie kod produkcyjny ani gotowe instalatory.
2. Wszystkie prywatne adresy BLE i ścieżki BlueZ zawierające MAC zostały zastąpione placeholderami (np. `<LOCAL_BLE_ADDRESS>`). W obecnej postaci mogą celowo nie działać bez ręcznej rekonfiguracji — dzięki temu nie wykonają przypadkowych akcji na złym urządzeniu.
3. Nie uruchamiać skryptów sterujących sprzętem automatycznie, z CI, z cron ani przez sam `git checkout`.
4. Nie uruchamiać serii zdjęć, akcji zoomu, konfiguracji CAN/GPIO ani kodu NPU bez osobnej zgody operatora i weryfikacji sprzętu.
5. Osoby odtwarzające próby powinny stosować raporty z katalogów `docs/hardware` i `docs/audits`; część narzędzi zależy od oryginalnej struktury NVMe i od pakietów istniejących tylko lokalnie.

Publiczne wersje źródeł nie są dokładną kopią prywatnych ustawień urządzenia. Nie zawierają logów, sekretów, zdjęć ani numerów seryjnych.
