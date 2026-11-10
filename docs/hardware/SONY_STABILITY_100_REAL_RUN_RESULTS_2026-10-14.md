# Sony A6100A — wynik rzeczywistego testu 100 zdjęć (PTP ↔ SD)

**Data:** 2026-10-14 (Europe/Warsaw)  
**Projekt:** Vision / Arduino VENTUNO Q / Sony ILCE-6100A  
**Protokół:** `scripts/audit/sony_stability_test.py`, `run --mode both --shots 50`  
**Status danych:** **AKWIZYCJA PASS / PORÓWNANIE SD PASS / IMPORT SD PASS**.  
**Status automatycznego `assess`:** **FAIL — znany błąd metadanych `phase`**; nie interpretować jako awarii zdjęć lub niezgodności plików.

> To zapis wyników **rzeczywistego testu hardware**, a nie wcześniejszych testów z atrapami.
> Dokument przygotowania pozostaje odrębnym, historycznym zapisem sprzed uruchomienia:
> [SONY_STABILITY_50_100_TEST_2026-10-14.md](SONY_STABILITY_50_100_TEST_2026-10-14.md).
> Nie dokonano korekty surowych dowodów ani zmian w kodzie podczas archiwizacji tego wyniku.

## 1. Identyfikacja przebiegu i warunki

| Pole | Wartość |
| --- | --- |
| Sesja | `sony-stability-20261014T133013301256Z` |
| Początek | 2026-10-14 13:30:13 UTC (15:30:13 CEST) |
| Koniec akwizycji | 2026-10-14 13:55:21 UTC (15:55:21 CEST) |
| Czas akwizycji | 1508,655 s (25 min 8,655 s) |
| Plan | 50 × fixed + 50 × zoom = **100 ekspozycji** |
| Zapis | 100 par ARW + JPEG, `RAW+JPEG (X.Fine)`, JPEG 6000 × 4000 |
| Aparat | Sony ILCE-6100A, Power Zoom 16–50 mm |
| Kontrola | USB PTP (`054c:0f0d`), `gphoto2`; zoom BLE; Live View HDMI → UVC `/dev/video0` |
| Tryby odczytane z aparatu | `AF-A` / `Single Shot` / `card+sdram` / `RAW+JPEG (X.Fine)` |
| Odstęp po parze | 10 s; impuls zoomu 0,65 s; odczekanie po zoomie 1 s |
| PTP/rejestr zdjęć | jedna trwała sesja; automatycznych powtórzeń migawki: 0 |

Ścieżka **lokalna, poza GitHub**:
`/srv/vision-data/vision/sessions/sony-stability-20261014T133013301256Z/`.

Pierwszy rozruch tego dnia zatrzymał się przed pierwszą ekspozycją na
`UVC_WARMUP_TIMEOUT`: grabber emitował pasy testowe HDMI. Po fizycznym ponownym
podłączeniu HDMI potwierdzono rzeczywisty obraz PCB i powtórzono preflight
(ostatnie 45 sprawdzonych klatek bez wzorca testowego). Dopiero wtedy rozpoczęto
opisaną tutaj pełną serię. **Nie doliczać nieudanej próby preflight do 100 ekspozycji.**

## 2. Akwizycja i autofocus

| Pomiar | Fixed | Zoom |
| --- | ---: | ---: |
| Zweryfikowane ekspozycje | **50/50** | **50/50** |
| Ogniskowe EXIF w fazie | 16 mm (stała) | 16–21 mm |
| Mediana potwierdzenia AF | 1,023 s | 0,724 s |
| AF p95 | 1,101 s | 1,095 s |
| AF max | 1,117 s | 1,117 s |
| Mediana kompletnego pobrania pary | 4,213 s | 4,018 s |
| Pobranie pary p95 | 4,349 s | 4,362 s |
| Pobranie pary max | 4,355 s | 4,386 s |

Zweryfikowano **100/100 statusów pojedynczych prób `PASS`**, **100/100**
wywołań pełnego naciśnięcia migawki i **0** automatycznych ponowień.
Wszystkie **49/49** impulsów BLE w fazie zoom mają `PASS`; zmiany kierunku
i ogniskowej były weryfikowane przez EXIF. Ogniskowa przy impulsach nie stanowi
pomiaru dokładnej, absolutnej pozycji obiektywu.

W oryginalnym `result.json`:
- `capture_status=PASS`, `verified_shots=100`, `planned_shots=100`;
- `ptp_release_ack=true`, `uvc_final_gate=PASS`, `ble_postflight=PASS`;
- `automatic_shutter_retries=0`;
- `status=PENDING_SD` — stan zapisany **w chwili zakończenia akwizycji**,
  nieaktualizowany przez późniejsze porównanie SD.

## 3. Live View przez HDMI/UVC

| Wskaźnik | Wynik |
| --- | ---: |
| Odebrane klatki 1920 × 1080 | 45 235 |
| Unikalne hashe zawartości klatek | 37 630 |
| Największa przerwa odbioru po gotowości | 0,138 s |
| Testowe pasy wykryte **po** osiągnięciu gotowości | **0** |
| Łączna liczba kontroli treści | 3012 |
| Błędy kolektora | 0 |
| Najdłuższy identyczny fragment po rozruchu | 9 klatek / ok. 0,269 s |

Zarejestrowano pojedynczą kontrolę pasów testowych **w rozruchu przed
gotowością**; nie było takich wykryć w monitorowanym okresie roboczym.
To statystyki odbioru danych w hoście, **nie** dowód świeżości każdej klatki
sceny ani pomiar opóźnienia sensor→ekran.

## 4. Porównanie PTP ↔ karta SD

Po akwizycji operator przełączył Sony do `Mass Storage` (`054c:0f0b`).
Kartę `exFAT` widziano w tym przebiegu jako `/dev/sda1` i montowano tylko do
odczytu (`ro,nosuid,nodev,noexec`). To numer urządzenia z tego przebiegu;
nie wolno zakładać go dla przyszłych uruchomień.

Z 138 ARW i 157 JPEG obecnych na karcie wybrano wyłącznie pliki odpowiadające
100 ekspozycjom z sesji. Każde ujęcie miało unikalną kombinację
`EXIF DateTimeOriginal + FocalLength`; dopasowano **100/100** bez kolizji
kluczy EXIF.

| Kontrola | Wynik |
| --- | ---: |
| Dopasowane pary PTP↔SD | **100/100 PASS** |
| ARW identyczne bajtowo (pełen plik) | **100/100** |
| JPEG identyczne bajtowo (pełen plik) | **0/100** |
| JPEG — cała zawartość PTP identyczna, tylko dodatkowe zera na końcu pliku SD | **100/100** |
| JPEG — zgodność zdekodowanych danych RGB 6000 × 4000 | **100/100** |
| Błędy dopasowania i porównania | **0** |

Zatem **nie należy twierdzić, że 100 JPEG ma identyczny SHA-256 w PTP i SD**:
całe pliki nie są identyczne, ponieważ wariant SD zawiera dopuszczalne zera
końcowe. Jest natomiast identyczna zawartość PTP oraz dekodowany obraz RGB,
zgodnie z przyjętą polityką porównywarki. Pełne pliki ARW są identyczne bajtowo.

`sd-comparison.json`: `status=PASS`, `verified_pairs=100`,
`raw_exact_files=100`, `jpeg_exact_files=0`,
`jpeg_zero_padding_only=100`.

## 5. Import kopii SD i weryfikacja

Na NVMe zachowano **200/200** oryginałów z SD: 100 ARW + 100 JPEG w katalogu
sesji `sd-originals/`. Łączny rozmiar kopii: **3 754 400 768 bajtów**
(ok. 3,75 GB / 3,50 GiB). Kontrola SHA-256 każdej kopii względem
odpowiedniego oryginału SD w imporcie i ponowna weryfikacja na zapisanych
kopiach zakończyły się **PASS**.

Artefakty pozostawione na VENTUNO (nie commitować ich zawartości):
- `result.json` — dane oryginalnego przebiegu i status `capture_status=PASS`;
- `ptp-manifest-private.json` — prywatny manifest PTP z hashami;
- `sd-comparison.json` — **PASS 100/100**;
- `sd-import.json` — **PASS 200/200**;
- `assessment.json` oraz `REPORT.md` — automatyczna ocena (patrz błąd poniżej);
- `sd-originals/` — 200 kopii SD; katalogi `fixed-shot-*/` i `zoom-shot-*/` — oryginały PTP.

## 6. Znany defekt metadanych: automatyczny `assessment.json` daje FAIL

**Defekt skryptu, nie dowód uszkodzenia zdjęć.** Podczas akwizycji
`attempt.update(af.af_then_shutter(...))` nadpisuje początkowe
`attempt["phase"]` (`fixed` / `zoom`) wartością `"RELEASE"` z wewnętrznego
stanu migawki. W konsekwencji:

1. Wszystkie 100 prób w `result.json` ma `phase=RELEASE`, mimo że oryginalne
   katalogi nadal rozróżniają `fixed-shot-001..050` i `zoom-shot-001..050`.
2. `ptp-manifest-private.json` i wynik porównania korzystają z etykiety
   `.../RELEASE`. Daje to **50 powtórzeń** klucza `(session, shot)` pomiędzy
   fazami, choć klucze EXIF dla rzeczywistych ekspozycji pozostają unikalne.
3. `assessment()` szuka prób według `fixed/zoom`, widzi po 0 dla każdej fazy
   i raportuje `capture_status=FAIL` oraz `status=FAIL`, mimo że
   `result.json` zawiera `capture_status=PASS`, `sd-comparison.json` ma
   `status=PASS`, a import i jego ponowna kontrola SHA-256 mają `PASS`.

Nie korygowano dowodów ani nie nadpisywano wyników. **Decyzja operatora:
priorytetem było porównanie i skopiowanie zdjęć; poprawkę raportera odłożono.**
Nie wolno traktować wadliwego automatycznego `assessment.json` jako
wiarygodnego certyfikatu `PASS` ani `FAIL` całej sesji. Ocena warstw
akwizycja / porównanie / import została potwierdzona osobno na oryginalnych
artefaktach. Jeśli automatyczna ocena ma stać się bramką produkcyjną,
wymaga osobnej poprawki i testu regresji.

## 7. Zakres potwierdzonej jakości i ograniczenia

**Potwierdzone w jednej realnej sesji:** 100 ekspozycji RAW+JPEG, brak
automatycznych ponowień migawki, sterowanie BLE w 49 impulsach, poprawny
odbiór Live View na hoście, kontrola kompletności transferu, zgodność RAW
i obrazu JPEG z kartą SD oraz integralny import 200 plików.

**Nie zostało potwierdzone:** pełna dekodowalność danych sensora ARW,
optyczna jakość / ostrość zdjęć PCB, dokładne pozycjonowanie zoomu,
świeżość każdej klatki HDMI, opóźnienie sensor→ekran, bezpieczeństwo ruchu
ramienia robotycznego i odtwarzalność w wielu kolejnych długich sesjach.
Kolejność fixed→zoom nie izoluje efektów temperatury lub baterii.

**Polityka dowodowa:** na GitHub umieszczono wyłącznie ten raport tekstowy.
Nie wysyłano fotografii, plików ARW/JPEG, pełnych manifestów, numerów
seryjnych ani prywatnych logów. Dowody i ich hashe pozostają na NVMe
VENTUNO, poza repozytorium.

## 8. Identyfikacja wersji testowanych skryptów (SHA-256)

| Skrypt | SHA-256 |
| --- | --- |
| `sony_stability_test.py` | `68c7de45a377a8644f90841a05bafe65d8f1986058c935ddeb2f7a46703bee12` |
| `sony_af_prototype.py` | `73cc86479b7d519fe7b12fd37756c412aa581186dbfe493f21526146a9a385f3` |
| `sony_zoom_af_test.py` | `4b04d24e36d04ab2e98a3f5f917ec7e1350c1d98f63d7f7d2899b6919153b182` |
| `sony_ptp_sd_compare.py` | `655a14bd50646682de97eada386cd3bae0992762161d708b9866dbc9def687b9` |

**Powiązany PR:** [#13 — Sony stability 50/100 photos](https://github.com/autoklinika/Vision/pull/13).
