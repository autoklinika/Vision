# Sony A6100 — weryfikacja USB/PTP, Live View, RAW i stabilności (2026-10-10)

**Projekt:** Vision — automatyczne stanowisko akwizycji PCB/ECU.
**Aparat:** Sony ILCE-6100A (A6100), USB `054c:0f0d`, USB 2.0 High Speed 480 Mb/s, tryb **PC Remote**.
**Host:** Arduino VENTUNO Q / Ubuntu 24.04.4 ARM64 / `6.8.0-1084-qcom`.
**Status:** sterowanie i akwizycja **PASS warunkowo**; długotrwała/bezprzerwowa stabilność i focus stepping optyczny **UNVERIFIED**.
**Dowody:** [rejestr lokalnych sesji i narzędzi](EVIDENCE_REGISTER_2026-10-10.md). Zdjęć i surowych logów nie publikujemy w Git.

## 1. Przygotowanie środowiska i polityka zmian

- `gphoto2 2.5.28`, `libgphoto2 2.5.31`, `libgphoto2_port 0.12.2`.
- Narzędzie lokalne: `/srv/vision-data/tools/sony-a6100-verify/root/usr/bin/gphoto2` — brak globalnego `gphoto2` w PATH nie oznacza braku narzędzia.
- Dodatkowe biblioteki narzędzia: `/srv/vision-data/tools/sony-a6100-verify/root/usr/lib/aarch64-linux-gnu`; wymagają ustawienia `LD_LIBRARY_PATH` w procesie testowym.
- Reguła `/etc/udev/rules.d/99-vision-sony-a6100.rules` zapewnia grupie `arduino` dostęp do węzła USB z uprawnieniami `0660`; po instalacji sterowanie aparatem działa **bez sudo**.
- W czasie testów aparat miał ekspozycję **M**, domyślnie **AF-A**, format **JPEG Fine**, tryb **Single Shot**, Capture Target **sdram**.
- Wszystkie nowe zdjęcia i dane robocze zapisywano wyłącznie na `/srv/vision-data/vision/sessions/` (NVMe). Aparatu nie resetowano ani nie aktualizowano firmware.
- Opcja `--keep` zapobiega usunięciu pobranych obiektów przez gPhoto2. **Nie jest dowodem trwałego zapisania plików na karcie SD**, ponieważ Capture Target pozostawał `sdram`.

## 2. Początkowa komunikacja oraz fotografia

| Test | Zakres i obserwacja | Wynik |
|---|---|---|
| SONY-USB | Poprawna enumeracja `054c:0f0d`; uprawnienia `root:arduino` `0660` | PASS |
| SONY-PTP | Sony PTP Extensions, model `ILCE-6100A`, odczyt `--summary` i parametrów | PASS |
| SONY-JPEG | Zdalne wyzwolenie przez `--capture-image-and-download`, pobranie JPEG **6000×4000 (24 MP)** | PASS |
| SONY-KEEP | Zapis na NVMe oraz `--keep`, bez usuwania obiektu przez gPhoto2 | PASS |
| SONY-FOCUS-MODE | Zmiana AF-A → MF i przywrócenie AF-A przez PTP | PASS — sterowanie |
| SONY-FOCUS-NEAR/FAR | Przyjmowanie poleceń `Near Far` przez Sony PTP | PASS — protokół |
| SONY-OPTICAL-FOCUS | Jednoznaczne przesunięcie optycznej płaszczyzny ostrości | UNVERIFIED |

**Ograniczenie drivera:** `gphoto2 --abilities` zgłaszało ogólny sterownik `USB PTP Class Camera`, m.in. `Image` i `Preview`. Sam ten wpis nie dowodził działającego Live View; potwierdzono je dopiero testami poniżej.

### Próby focus stepping — odłożone

- **Krok +1:** zmiany detali były niewielkie; brak jednoznacznego dowodu przemieszczenia soczewek.
- **Krok +3:** obserwowano zmianę szczegółowości obrazu, m.in. około **−4,36%** dla faktury ubrania i **−5,11%** dla obszaru centralnego według użytych metryk. **Jednocześnie zmieniła się ekspozycja/jasność**, co uniemożliwia niezależne przypisanie wyniku zmianie płaszczyzny ostrości.
- Test oparto o scenę zastępczą, bez docelowej płytki PCB i obiektywu makro. Nie uznawać focus stackingu za gotowy.
- Aparat przywrócono do AF-A. Powrót do testów po doborze makro, stabilnym oświetleniu i geometrii stanowiska.

## 3. Live View / Preview: LV-01–LV-05

| ID | Test | Wynik | Zastrzeżenie |
|---|---|---|---|
| LV-01 | USB/PTP + `--abilities` i `--list-config`, bez zapisu zdjęcia | PASS | `Preview` był początkowo tylko deklaracją; `Live View Setting Effect` nie jest strumieniem |
| LV-02 | Jedno `--capture-preview` | PASS | Plik JPEG 1024×680, około 114 KiB |
| LV-03 | 10 klatek / 10 osobnych procesów gPhoto2 | PASS | 3896 ms, **2,57 pobrania/s** (wliczony start procesów) |
| LV-04 | 10 klatek / 1 proces i sesja `gphoto2 --shell` | PASS | 693 ms, **14,43 pobrania/s** (przepustowość serii, nie niezależnie zmierzony sensor FPS) |
| LV-05 | 85 klatek / 27 769 ms, ruch ręki przed aparatem | PASS | Optyczne potwierdzenie aktualizacji sceny; opóźnienie obrazu nadal UNVERIFIED |

**Uwaga implementacyjna LV-02:** pierwszy zapis przez `--filename=lv02_preview.%C` zwrócił `Bad parameters` z powodu braku suffixu nazwy `capture_preview`. `--filename=lv02_preview.jpg` zadziałało; gPhoto2 zapisał `thumb_lv02_preview.jpg`.

**Rozmiar podglądu:** każda z klatek pomiarowych została rozpoznana jako JPEG 1024×680 (8-bit, 3 komponenty). Nie należy mylić go z pełnym zdjęciem 6000×4000.

**Porównanie pikselowe:**
- LV-04, scena względnie nieruchoma: różnice szarości między sąsiednimi klatkami `MAE ≈ 1,74–1,75/255`, typowe również dla szumu/kompresji.
- LV-05, scena z ruchem ręki: maksymalna różnica między sąsiednimi klatkami `MAE ≈ 78,98/255`; w tej parze około **72,37%** pikseli różniło się o ponad 30 poziomów.
- Obejrzane klatki potwierdziły faktyczny ruch ręki i powrót do niezastawionej sceny. To dowód **żywego obrazu**, nie tylko zmiennych hashy JPEG.
- 85 klatek w 27,77 s daje około **3,06 pobrania/s** podczas testu ruchu, ograniczone m.in. zamierzonymi przerwami. Ani 14,43, ani 3,06 nie są pomiarem maksymalnej przepustowości sensora.
- **Nie zmierzono** opóźnienia pomiędzy zdarzeniem w scenie a dostarczeniem klatki. Podgląd pomaga przy kadrowaniu i pozycjonowaniu, ale nie jest niezależnym systemem antykolizyjnym.

## 4. RAW/ARW — RAW-01 i RAW-02

RAW-01 (odczyt) ustalił: `Image Quality=Fine`, dostępne `RAW`, `RAW+JPEG (Fine)`, `RAW+JPEG (X.Fine)`, `RAW+JPEG (Std)`; `Capture Target=sdram`. NVMe był zamontowany ext4 rw.

RAW-02 (jedno zdjęcie):
1. Zapisano `Image Quality` początkowe `Fine`.
2. Tymczasowo ustawiono **RAW+JPEG (Fine)** przez PTP.
3. Wyzwolono **jedną** fotografię z `--keep`, pobrano dwa obiekty.
4. Zweryfikowano pliki na NVMe i przywrócono **JPEG Fine** — `RESTORE=PASS`.

| Plik | Rozmiar | Format / odczyt | SHA-256 |
|---|---:|---|---|
| `sony_raw02.arw` | **24 894 208 B** | TIFF little-endian/SONY, model ILCE-6100A — nagłówek PASS | `d1fc49b47f4aaafda38aa4dd9fdbabe47d41571a34faf48dc8089cd52616afa0` |
| `sony_raw02.jpg` | **7 689 886 B** | JPEG, 6000×4000, dekodowanie PASS | `e79da7664d90f59364133aa99cff80580a37638d15814930575d2498d29ea118` |

Pliki mają zgodny znacznik czasu w metadanych. `file` rozpoznaje JPEG, a Pillow może raportować `MPO` z uwagi na metadane MPF. **Nie wykonano pełnego dekodowania mozaiki sensora ARW** ani weryfikacji przetwarzania obrazu RAW — `UNVERIFIED`.

## 5. Stabilność JPEG 24 MP — STAB-01–STAB-06

| ID | Metoda | Poprawne zdjęcia | Wynik | Najważniejsza obserwacja |
|---|---|---:|---|---|
| STAB-01 | Osobny proces/sesja dla każdej próby, niemal natychmiastowe ponawianie, AF-A | 2 z 4 prób (nr 1 i 3) | **FAIL** | Próby 2 i 4: `Could not capture image`; próba 2 trwała **39,849 s** |
| STAB-02 | Diagnostyka tylko do odczytu | — | PASS — diagnostyka | AF-A, Wide, SDRAM, Single Shot; przyczyna błędu UNVERIFIED |
| STAB-03 | Osobne sesje, **MF** zamiast AF-A, bez innych zmian | 1 z 2 prób | **FAIL** | Próba 2 `Could not capture` po **38,621 s**; AF-A przywrócono |
| STAB-04 | **Jedna sesja PTP**, 2 zdjęcia, bez przelogowania aparatu | **2/2** | PASS | Prawidłowe `capt0000.jpg`, `capt0001.jpg` |
| STAB-05 | **Jedna sesja PTP**, 10 zdjęć, przerwy ≥3 s | **10/10** | PASS | Łącznie 78 579 557 B JPEG; żadnych błędów |
| STAB-06 | **Osobne sesje PTP**, 4 zdjęcia, przerwy ≥10 s | **4/4** | PASS | Czas pojedynczej operacji 1,994–2,029 s; średnia **2,017 s** |

**STAB-01 — pułapka:** gPhoto2 zwracał `exit code=0` nawet gdy w logu były `ERROR: Could not capture image.` i nie powstał plik. Skrypt nie zatrzymał się po próbie 2, ponieważ początkowo sprawdzał tylko exit code. Nie wolno traktować `rc=0` jako wystarczającego dowodu sukcesu.

**STAB-03:** zmiana AF-A → Manual i przywrócenie AF-A były zweryfikowane; nie wyeliminowało to błędu. AF-A nie jest zatem koniecznym warunkiem wystąpienia problemu; nie dowiedziono konkretnej przyczyny.

**STAB-04:** podczas jednej sesji PTP zadziałało 2/2, ale tak mała próbka nie rozstrzygała o stabilności.

**STAB-05:** 10 osobnych wyzwoleń wewnątrz `gphoto2 --shell`, z walidacją kompletności każdego JPEG, zachowaniem odstępów i uniknięciem otwierania nowej sesji. Sumy SHA-256 wszystkich 10 plików były różne, dekodowanie 6000×4000 PASS. Odstępy między datami modyfikacji plików wynosiły **9–40 s** (wliczając narzut MCP/weryfikacji); nie są to czyste czasy aparatu. Weryfikacja 9. klatki wymagała ponownego wykonania *kontroli pliku* po błędzie cytowania polecenia; samo zdjęcie wykonano tylko raz.

**STAB-06:** po każdym pobraniu proces gPhoto2 był zakończony, nowy proces uruchamiano dopiero po pełnych 10 s przerwy. 4/4 poprawne; czasy **2,028 / 2,018 / 2,029 / 1,994 s** dla całej operacji zdjęcie+pobranie w pojedynczym procesie. To istotna przesłanka, że **odstęp między wyzwoleniami ma znaczenie**, lecz nie potwierdza jeszcze przyczyny błędu przy szybkich próbach.

**Wniosek po STAB-06:** problemy STAB-01/STAB-03 nie dowodzą awarii USB/NVMe ani konieczności utrzymywania jednej sesji. Działają zarówno trwała sesja z odstępami, jak i osobne sesje z odstępami 10 s. Nie rozdzielono izolowanym eksperymentem wpływu odstępów, gotowości bufora aparatu i sterownika. Długotrwała stabilność (setki/tysiące zdjęć) pozostaje `UNVERIFIED`.

## 6. Wymagania na przyszły adapter Sony (projekt, nie wdrożenie)

- Preferować **jedną trwałą sesję PTP** dla sekwencji; bez instalacji Sony SDK, dopóki gPhoto2 spełnia wymagania.
- Przed kolejnym wyzwoleniem stosować kontrolowany odstęp **10 s jako konserwatywną wartość początkową**; STAB-05 potwierdził też 10/10 w jednej sesji przy odstępach ≥3 s, ale bez formalnej charakterystyki granicy.
- Potwierdzać sukces **łącznie**: odpowiedź aparatu, brak błędów w logu, istnienie pliku, rozmiar, dekodowanie, hash. W przypadku błędu — fail-closed, bez „ślepego” natychmiastowego retry.
- Zachować źródłowe ARW/JPEG, UTC i znaczniki monotoniczne, parametry aparatu i pozycję robota; zapisy wyłącznie na NVMe.
- `--keep` nie zastępuje jawnej polityki retencji i obsługi SDRAM/karty.
- Oddzielić adapter Sony od Core i od innych kamer; Live View 1024×680 traktować jako pomoc w pozycjonowaniu, nigdy jako jedyny czujnik ochrony robota.
- Focus stacking wymaga ponownej walidacji ze szkłem makro, stabilnym oświetleniem i poprawną metryką optyczną.

## 7. Stan końcowy i nierozstrzygnięte zagadnienia

Po STAB-06 na fizycznym aparacie potwierdzono: USB/PTP **PASS**, `Focus=AF-A`, `Image Quality=Fine`, `Single Shot`, `Capture Target=sdram`, `Exposure=M` — bez zmian; bateria **94%**, brak aktywnych procesów gPhoto2. Odłączenie aparatu po zamknięciu sesji jest bezpieczne; przed wyjęciem USB zalecane jest wyłączenie aparatu.

| Zagadnienie | Status |
|---|---|
| Wykonywanie pojedynczych JPEG 24 MP na NVMe | PASS |
| RAW+JPEG / transfer pliku ARW | PASS |
| Pełne dekodowanie sensora RAW | UNVERIFIED |
| Pobieranie **żywego** podglądu USB | PASS |
| Opóźnienie Live View i FPS sensora | UNVERIFIED |
| Powtarzalność 10 zdjęć w 1 sesji PTP z odstępami | PASS |
| Powtarzalność 4 zdjęć w oddzielnych sesjach z odstępami 10 s | PASS |
| Wyjaśnienie awarii szybkich powtórek | UNVERIFIED |
| Elektryczne sterowanie Near/Far | PASS — przyjęcie komendy |
| Optyczny focus stepping z makro | UNVERIFIED |
| Pełny test długoterminowy | UNVERIFIED |

## 8. Dowody i odtwarzalność

Pełne ścieżki narzędzi, sesji LV-01–LV-05, RAW-02 oraz STAB-01–STAB-06: [EVIDENCE_REGISTER_2026-10-10.md](EVIDENCE_REGISTER_2026-10-10.md).

**Uwaga dla przyszłego operatora:** polecenia `capture-image-and-download`, `capture-preview` i `--set-config` oddziałują na fizyczny aparat; nie uruchamiać ich automatycznie bez zgody na dany test. Właściwy Vision Core/adapter Sony nie został jeszcze wdrożony.
