# Vision — Replay First: testuj na danych, nie na sprzęcie

**Status:** eksperymentalny proces DEV. Nie uruchamia kamery, NERO, MoveIt ani usług VENTUNO Q. Dokument uzupełnia istniejące zasady `DEVELOPMENT.md` i `RELEASE_GATES`, nie zmienia architektury.

## Pięć reguł inżynierskich

1. **Zamrożony baseline:** każdy sprawdzony tor akwizycji, algorytm, wersja oprogramowania, układ odniesienia, K i wynik testu dostają jawne identyfikatory. Nie poprawiamy baseline w miejscu: nowy profil = nowa wersja, test porównawczy i PR.
2. **Dane jako trwały zasób:** RAW16/RGB, zdjęcia PCB, logi NERO i manifesty konkretnych sesji zostają na prywatnym NVMe/NAS. Publiczny GitHub otrzymuje wyłącznie kod, syntetyczne testy i zagregowane wyniki bez danych identyfikujących stanowisko.
3. **Replay przed testami sprzętowymi:** dla zmiany algorytmu/kontraktu najpierw uruchamiamy zapisane dane; później integrację ROS bez aktuatorów; fizyczne testy robimy tylko na końcowych bramkach wymagających sprzętu.
4. **Fail closed:** brak danych, hash niezgodny z baseline, zmiana 800p→400p, inna macierz K, błędne znaczniki czasu, niekompletna głębia albo brak zatwierdzonego TF oznaczają odmowę dalszego kroku. Żaden wynik replay nie przyznaje `SAFE_TO_MOVE`.
5. **Prace niezależne:** SCN-001-A dla ETC3 z [PR #29](https://github.com/autoklinika/Vision/pull/29) rozwijamy na zapisach RGB/RAW16, równolegle do kalibracji TF i MoveIt. Istniejący algorytm `top_surface` z [PR #26](https://github.com/autoklinika/Vision/pull/26) jest punktem odniesienia, nie czymś do przepisywania bez dowodu regresji.

## Pierwszy wykonany krok: kontrola integralności RAW16

`scripts/replay/check_capture.py` (Python + NumPy) sprawdza lokalny prywatny plik `.npz` zawierający `depth_mm` (N×H×W, uint16), macierz `K` oraz opcjonalne `device_timestamp_ns`. Kontroluje SHA-256, liczbę klatek, wymiar, typ danych, K, monotoniczność timestampów i procent pikseli głębi w zadanym zakresie.

Przykładowy **format** manifestu (wartości poniżej są ilustracyjne; lokalny manifest musi zawierać prawdziwy SHA-256 i parametry z własnej sesji; nie commitować go do publicznego repo):

```json
{
  "schema_version": "vision.capture-baseline.v1",
  "session_id": "LOCAL-PRIVATE-001",
  "capture": {
    "format": "npz-raw16-v1",
    "file": "capture.npz",
    "sha256": "REPLACE_WITH_REAL_64_CHAR_LOWERCASE_SHA256"
  },
  "expected": {
    "frames": 25,
    "depth_hw": [800, 1280],
    "depth_dtype": "uint16",
    "declared_optical_frame": "stereo_left_rectified_optical",
    "K": [800.0, 800.0, 640.0, 400.0],
    "K_tolerance_px": 0.2
  },
  "quality": {
    "valid_depth_mm": [250, 2000],
    "min_valid_fraction": 0.65
  }
}
```

```bash
python3 -m pip install numpy
python3 scripts/replay/check_capture.py \
  --manifest /private/session/manifest.json \
  --capture-root /private/session \
  --output /private/session/validation.json
python3 -m unittest discover -s tests -p 'test_capture_replay.py' -v
```

Wynik `PASS` = kod wyjścia 0; `FAIL` = kod 2 i lista przyczyn. Żadne obrazy ani klatki nie są drukowane. **Deklaracja `declared_optical_frame` nie potwierdza niezależnie poprawności TF ani wyrównania RGB–stereo.** Ta bramka sprawdza integralność danych, nie metrologiczną dokładność ECU.

## Kolejność następnych małych PR

| Zadanie | Kryterium | Wymaga fizycznego stanowiska? |
| --- | --- | --- |
| A2 — ETC3 Replay RGB/RAW16 | manifest ECU1, dobór sesji, adapter frame/stamp, replay z kontrolą hashy | Nie |
| Benchmark 34 / 50,4 / 101 mm | niezmieniony algorytm, porównanie bias/std/odrzuceń i wymagane minima jakości | Nie |
| A3 — analiza PCB ETC3 | wyrównanie zdjęć OpenCV, mapa zmian, raport z niepewnością i `REVIEW_REQUIRED` | Nie |
| TF kamera–stół–NERO | testy geometrii i macierzy offline + jeden niezależny odbiór na stanowisku | Tylko końcowy odbiór |
| MoveIt i NERO | wirtualna scena i testy STOP/HOLD; wykonanie ruchu po odrębnej ocenie bezpieczeństwa | Dopiero na końcu |

**Bramka publikacji:** mały PR, testy offline PASS, opis rollback, bez merge do `main` bez zgody właściciela. SCN-001-A i analiza PCB nie czekają na kalibrację robota.
