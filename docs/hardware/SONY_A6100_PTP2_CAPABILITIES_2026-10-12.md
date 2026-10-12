# Vision / VENTUNO Q — diagnostyka możliwości Sony ILCE-6100A przez USB PTP 2

**Data:** 2026-10-12

**Etap:** jednorazowa diagnostyka wyłącznie odczytowa, bez wdrożenia produkcyjnego

**Źródło protokołu:** dostarczony przez użytkownika `CameraRemoteCommand-2.02.00.zip`, dokument `Camera Control PTP 2 Reference.pdf`, zwłaszcza str. 15–16, 23–25, 33–38, 60.

## Cel

Zweryfikować bezpośrednio na Sony ILCE-6100A listę obsługiwanych właściwości i komend PTP 2, szczególnie możliwość sterowania fizycznym napędem zoomu w obiektywie Sony E PZ 16–50mm F3.5–5.6 OSS II.

## Bezpieczeństwo i ograniczenia

- Bez zmiany trybu aparatu, ekspozycji, zoomu, ostrości i firmware.
- Bez wyzwalania migawki oraz bez przesyłania sterowania napędem.
- Bez `SDIO_SetExtDevicePropValue (0x9205)` ani `SDIO_ControlDevice (0x9207)`.
- Dopuszczone wyłącznie `GetDeviceInfo (0x1001)`, tymczasowe `OpenSession (0x1002)`/`CloseSession (0x1003)`, fazy uwierzytelnienia `SDIO_Connect (0x9201)`, odczyt `SDIO_GetExtDeviceInfo (0x9202)` i odczyt `SDIO_GetAllExtDevicePropInfo (0x9209)`.
- Brak resetu USB, odłączania sterownika jądra, instalacji pakietów, usług, reguł udev, modyfikacji repozytorium produkcyjnego Vision.
- Zastosowano libusb z systemu, w Pythonie `ctypes`, nie uruchamiano pobranego przykładu producenta. Wszystkie operacje mają limit wielkości danych i czasu.

## Identyfikacja sprzętu

- Host: VENTUNO Q `vision`, Linux ARM64, aparat na USB 001:005.
- USB VID:PID: `054c:0f0d`.
- Model odczytany z `0x1001`: `Sony Corporation / ILCE-6100A`.
- VendorExtensionDescription: `Sony PTP Extensions`.
- Obsługiwane operacje PTP na etapie `GetDeviceInfo`: 16, w tym `0x9201`, `0x9202`, `0x9205`, `0x9207`, `0x9209`. **Deklarowanie operacji Set/Control nie oznacza ich wywołania.**

## Wyniki — odczyt fizycznego aparatu

| Próba | Wynik | Dane |
|---|---|---|
| `GetDeviceInfo 0x1001` | PASS | `0x2001 OK`, 16 operacji |
| `OpenSession 0x1002` | PASS | `0x2001 OK` |
| `SDIO_Connect` fazy 1 i 2 | PASS | `0x2001 OK`, po 8 B danych |
| `GetExtDeviceInfo 0x9202` | PASS | `0x2001 OK`, 136 B |
| Rozszerzenie protokołu | PASS | `0x00C8` = PTP 2.00 |
| Lista właściwości | PASS | 45 identyfikatorów |
| Lista komend sterujących | PASS | 18 identyfikatorów |
| `SDIO_Connect` faza 3 | PASS | `0x2001 OK` |
| `GetAllExtDevicePropInfo 0x9209` | PASS | `0x2001 OK`, 1759 B |
| Parsowanie deskryptorów | PASS | 62/62 rekordów, całość 1759/1759 B |
| Zamknięcie sesji | PASS | `CloseSession 0x1003 → 0x2001 OK` |
| Zwolnienie USB | PASS | `libusb_release_interface = 0` |
| Stan aparatu po próbie | PASS | aparat wykrywalny, można wykonać odczyt `gphoto2` |

**Uwaga techniczna:** aparat ogłosił 45 właściwości + 18 komend, lecz odczyt zbiorczy przekazał 62 deskryptory. Brakuje tylko deskryptora `0xD220` — wszystkie pozostałe identyfikatory pokrywają się. Nie jest to dowód awarii.

## Pełna lista 18 komend sterujących PTP 2 na tym aparacie

| Kod | Znaczenie według referencji Sony |
|---|---|
| `0xD2C1` | Shutter Half-Release (S1) |
| `0xD2C2` | Shutter Release (S2) |
| `0xD2C3` | AEL |
| `0xD2C9` | FEL |
| `0xD2C8` | Movie Rec Button |
| `0xD2D9` | AWBL |
| `0xD2C5` | Release Lock |
| `0xD2C7` | RequestOneShooting |
| `0xD2CB` | Focus Magnifier |
| `0xD2CC` | Focus Magnifier Cancel |
| `0xD2CD` | Remote Key UP |
| `0xD2CE` | Remote Key DOWN |
| `0xD2CF` | Remote Key LEFT |
| `0xD2D0` | Remote Key RIGHT |
| `0xD2D2` | AF/MF Hold |
| `0xD2D3` | Cancel Pixel Shift Shooting |
| `0xD2D4` | Pixel Shift Shooting Mode |
| `0xD2D1` | Near/Far (regulacja ostrości, **nie zoom**) |

**Brak udokumentowanej komendy TELE/WIDE/Power Zoom w tej liście.**

## Kluczowe potwierdzenie: `0xD214` ≠ Zoom

W dostarczonej dokumentacji Sony `Camera Control PTP 2 Reference` str. 60 `0xD214` to **Predicted Maximum File Size**, typ `UINT32`, `GetSet=0` (tylko odczyt).

Odczytane bezpośrednio z rzeczywistej kamery za pomocą `0x9209`:

| Pole deskryptora `0xD214` | Wartość |
|---|---|
| PropertyCode | `0xD214` |
| DataType | `0x0006` = UINT32 |
| GetSet | **`0x00` = tylko GET** |
| IsEnabled | `0x01` |
| CurrentValue | **`34497536`** |
| DefaultValue | `0xFFFFFFFF` |
| FormFlag | `0x01`, Range |
| Min / Max / Step | `0` / `4294967295` / `1` |

W poprzednich testach `gphoto2` błędnie przedstawiał ten sam kod `0xD214` jako `Zoom` i wartość `34.4975`. Wynik ten nie był ustawieniem ogniskowej. Różnica semantyczna jest teraz potwierdzona z dwóch źródeł: oficjalnej dokumentacji Sony i prawdziwego deskryptora zwróconego przez aparat.

## Wniosek techniczny

**Dla ILCE-6100A w trybie Sony Camera Control PTP 2 nie ma udokumentowanej, reklamowanej przez urządzenie komendy poruszania silnikiem Power Zoom.** Potwierdzono to z rzeczywistej listy 18 komend. Nie należy mylić `Near/Far (0xD2D1)` ze zoomem optycznym.

Nie dowodzi to, że sterowanie zoomem jest niemożliwe przez wszelkie formy połączenia przewodowego. W szczególności nie przesądza o dodatkowych stykach złącza Multi Terminal ani ewentualnych nieudokumentowanych komendach producenta. PTP 3 nie jest potwierdzony dla naszego modelu; nie próbowano jego komend.

## Pliki dowodowe — lokalnie tylko na NVMe VENTUNO

W katalogu `/srv/vision-data/tools/sony-a6100-verify/ptp2-capabilities-test/`:

- `get-device-info.json` — operacje zgłoszone przez USB.
- `get-ext-device-info.json` oraz `.bin` — komplet 45 właściwości i 18 komend.
- `get-all-ext-properties.json` oraz `.bin` — zbiorczy deskryptor z `0xD214` i polem GetSet.
- `all-property-descriptors-parsed.json` — 62 zdekodowane deskryptory.
- `REPORT-PTP2-2026-10-12.md` — niniejszy raport.

Narzędzia testowe: `ptp2-get-device-info.py`, `ptp2-get-ext-info.py`, `ptp2-get-all-properties.py`, `ptp2-parse-property-snapshot.py` w `/srv/vision-data/tools/sony-a6100-verify/`. Nie są częścią wdrożenia, nie dodano ich do `main`.

**Status: TEST READ-ONLY PASS; produkcja Vision BEZ ZMIAN.**
