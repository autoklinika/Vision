# Sony ILCE-6100A — zamknięcie porównania PTP ↔ SD

Data: 2026-10-13. Status: **ZAMKNIĘTE / PASS 13/13 par RAW+JPEG (26 plików)**.
Zakres: te same ekspozycje z próby BLE zoom + AF + HDMI/UVC: 3 zdjęcia i seria 10 zdjęć.
Powiązanie: [raport zoom/AF](SONY_BLE_ZOOM_AF_TEST_2026-10-13.md), [PR #12](https://github.com/autoklinika/Vision/pull/12).

## Wynik i kryteria

| Kontrola | Wynik |
| --- | --- |
| Jednoznaczne dopasowanie EXIF DateTimeOriginal + FocalLength | 13/13 |
| Zgodność 26 plików PTP z wcześniejszym manifestem: rozmiar + SHA-256 | PASS |
| RAW ARW: porównanie całych plików bajt po bajcie i SHA-256 | 13/13 identycznych |
| JPEG: identyczny cały plik PTP jako początek pliku SD | 13/13 |
| JPEG: dodatkowe bajty SD wyłącznie zerowe | 13/13; 1076–27093 B |
| JPEG: pełne dekodowanie obu wersji i identyczne RGB | 13/13; 6000×4000 |
| JPEG: identyczny SHA-256 całego pliku PTP i SD | 0/13, ze względu na dodatkowe zera |
| Dokładne oryginały SD skopiowane na NVMe i zweryfikowane | 26/26; 510181120 B |

**Brak utraty zawartości zdjęć lub metadanych podczas transferu PTP w tej próbie.**
Nie należy wymagać identycznego SHA-256 całego JPEG PTP i SD: wszystkie badane JPEG na SD
zawierają dodatkowe zera po pełnej zawartości pliku PTP. SHA-256 całych plików pozostają
zapisane osobno. RAW są identyczne również jako całe pliki.

Sony JPEG zawierają także niezerową zawartość za EOI głównego obrazu
(w badanych plikach 411324–439395 B). Porównanie zachowuje **cały plik PTP**,
łącznie z tą zawartością; nie obcina danych na pierwszym EOI. Akceptowane zera
to wyłącznie dodatkowy sufiks SD poza końcem całego PTP.
Dowód zgodności metadanych i zakodowanej zawartości to pełna zgodność tego prefiksu,
a zgodność zdekodowanych pikseli sprawdzono niezależnie przez SHA-256 RGB.

## Dopasowane pary

| Próba | Zdjęcie | Plik SD bez rozszerzenia | EXIF mm | Dodatkowe zera JPEG SD, B | Wynik |
| --- | --- | --- | --- | --- | --- |
| Krótka | 1 | DSC00045 | 50 | 7033 | PASS |
| Krótka | 2 | DSC00046 | 39 | 24958 | PASS |
| Krótka | 3 | DSC00047 | 50 | 11271 | PASS |
| Seria10 | 1 | DSC00048 | 50 | 7665 | PASS |
| Seria10 | 2 | DSC00049 | 39 | 1076 | PASS |
| Seria10 | 3 | DSC00050 | 50 | 10181 | PASS |
| Seria10 | 4 | DSC00051 | 40 | 10339 | PASS |
| Seria10 | 5 | DSC00052 | 50 | 14007 | PASS |
| Seria10 | 6 | DSC00053 | 38 | 25705 | PASS |
| Seria10 | 7 | DSC00054 | 50 | 14276 | PASS |
| Seria10 | 8 | DSC00055 | 39 | 27093 | PASS |
| Seria10 | 9 | DSC00056 | 50 | 4268 | PASS |
| Seria10 | 10 | DSC00057 | 39 | 21170 | PASS |

## Dowody i wykonanie

Ograniczony wynik maszynowy: [SONY_PTP_SD_13PAIRS_EVIDENCE_2026-10-13.json](SONY_PTP_SD_13PAIRS_EVIDENCE_2026-10-13.json).
Bez zdjęć, identyfikatorów osobistych i surowego debug w repozytorium.

Sesja na VENTUNO:
`/srv/vision-data/vision/sessions/sony-ptp-sd-13pairs-20261013T214305Z`.

- `ptp-manifest-private.json`: wcześniejszy manifest 26 plików PTP.
- `ptp-sd-comparison.json`: wynik istniejącego skryptu repozytorium
  `scripts/audit/sony_ptp_sd_compare.py`; SHA-256
  `72deb37341ab722eb0002c0193cee5c44158c862b60df3861d47e1681bf9855c`.
- `sd-ptp-integrity.json`: niezależne porównanie i kontrola kopii SD;
  SHA-256 `b0c01d30f660d7318acba918499a9cdee36319564b5f7b2da05c7bdb7a323053`.
- `sd-originals/`: dokładne kopie wszystkich 26 plików SD, bez modyfikowania paddingu.
- `compare-sd-readonly.py`: jednorazowy skrypt sesji wykonujący porównanie i import.

Oba przebiegi zakończyły się PASS i kodem 0. Istniejący skrypt porównawczy:
SHA-256 `b9f8abedd92806f7533feabc24f1eadc291edcc15336f91995fd71aa8a592d61`.
Jego 11/11 testów regresji na VENTUNO ARM64 zaliczono, w tym:
EOI w metadanych, dane po głównym JPEG, różny drugi JPEG, niezerowy sufiks,
zmienione metadane i uszkodzony strumień.

Zapis wyłącznie na sprawdzonym NVMe VISION_DATA; karta Sony 054c:0f0b exFAT
zamontowana jako ro,nosuid,nodev,noexec. Zero nowych ekspozycji, zapisów na SD
i usunięć. Po porównaniu karta pozostaje zamontowana tylko do odczytu:
przed odłączeniem lub zmianą trybu USB trzeba ją bezpiecznie odmontować.

## Zamknięcie i granice

**Etap integralności PTP ↔ SD dla nowych 13 par zakończony.**
Wstępna weryfikacja wspólnego przepływu HDMI/UVC + PTP AF/RAW/JPEG + BLE zoom
ma już potwierdzony transfer tych zdjęć względem karty SD.

Pełne dekodowanie RAW pozostaje nieprzetestowane; zgodność bajtowa dowodzi
integralności transferu, nie jakości optycznej. Osobne przyszłe próby obejmują
QC rzeczywistej PCB, focus stacking/mozaikę, kalibrację oraz stabilność 50/100
zdjęć i wielu godzin. Ten wynik nie zamyka historycznych nieudanych wyzwoleń
ani innych sesji, w tym 10 zdjęć AF bez zoomu z PR #11.

Wyniki dodane do brancha PR #12. Merge do produkcyjnego main wymaga osobnej
decyzji właściciela; niniejsza weryfikacja nie wdraża usług ani zmienia firmware.
