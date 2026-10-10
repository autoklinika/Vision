# Vision — wymuszenie zapisu wyłącznie na NVMe (runtime v1)

**Status:** IMPLEMENTED / TESTED (logika lokalnie), HARDWARE GATE PENDING.
Rozwiązanie jest adapterem uruchomieniowym dla Linux/Ubuntu na VENTUNO Q, a nie zależnością logiki fotografii od Linuxa.

## Gwarancja i granice

Mechanizm `scripts/storage/vision_run.py` wykonuje dwa kroki:

1. **Fail-closed preflight**: weryfikuje montowanie dokładnie `/dev/nvme0n1p1` pod `/srv/vision-data`, system ext4, opcję rw, UUID `80f1f04c-490c-49cd-8c7a-1baf56bf0c9d`, etykietę `VISION_DATA`, odrębne urządzenie plikowe, dostęp do zapisu i katalog repozytorium na NVMe.
2. **Ograniczenie operacji zapisu procesów Vision**: uruchamia aplikację w odrębnej przestrzeni montowania Bubblewrap (`bwrap`). Całe drzewo systemowe jest widoczne *tylko do odczytu*; jedynym dodanym zapisywalnym drzewem trwałych plików jest zweryfikowane `/srv/vision-data`. HOME, TMPDIR, XDG cache/state/config/data, HF/PIP/Torch/Python cache trafiają na NVMe.

Próba uruchomienia bez NVMe, z nieodpowiednim UUID/etykietą, bez dostępu do danych lub bez Bubblewrap kończy się kodem 77 i komunikatem `VISION_STORAGE_BLOCKED`. **Brak automatycznego fallbacku na eMMC.**

**Granica odpowiedzialności:** zabezpieczenie obejmuje procesy uruchamiane **przez launcher** i zwykłe operacje na systemie plików. Nie jest to zakaz zapisów dla całego Ubuntu, dla arbitralnych procesów uruchomionych z pominięciem launchera ani ochrona przed celowo złośliwym kodem komunikującym się np. z zewnętrznym uprzywilejowanym demonem/urządzeniem blokowym. Przyszłe usługi i aplikacje Vision MUSZĄ używać tego punktu wejścia; brak jego użycia oznacza brak gwarancji polityki.

Nie zmieniamy globalnego `HOME`, `/tmp`, `/var`, systemowego `docker` ani plików uwierzytelniania GitHub. Normalne zapisy wykonywane przez Ubuntu i usługi producenta pozostają poza zakresem.

## Uruchomienie na VENTUNO — dopiero po synchronizacji gałęzi

```bash
cd /home/arduino/Vision
git fetch origin feature/nvme-write-guard-v1
git switch --track -c feature/nvme-write-guard-v1 origin/feature/nvme-write-guard-v1

# Test jednostkowy (bez testu hardware):
python3 -m unittest discover -s tests -p 'test_vision_storage.py' -v

# Test montowania: nic nie tworzy:
python3 scripts/storage/vision_run.py --check

# Test fizycznej izolacji: tworzy tylko krótkotrwały plik na NVMe,
# weryfikuje readonly eMMC PRZED próbą zapisu i oczekuje jej odrzucenia:
python3 scripts/storage/vision_run.py --smoke
```

Oczekiwany wynik:

```text
VISION_STORAGE=PASS (NVMe verified; sandbox executable available)
NVME_WRITE=PASS
EMMC_READONLY_MOUNT=PASS
EMMC_WRITE_DENIED=PASS
VISION_STORAGE_SANDBOX=PASS
```

Jeżeli `--smoke` zgłasza problem z Bubblewrap / namespace, **nie uruchamiać programu z pominięciem zabezpieczenia**. Sprawdzić zgodność `bwrap` i politykę user namespaces na obrazie Qualcomm. Nie zmieniać ustawień kernela ani uprawnień systemowych bez osobnej decyzji.

Uruchamianie dowolnego przyszłego programu Vision:

```bash
python3 /home/arduino/Vision/scripts/storage/vision_run.py -- python3 -c 'import os; print(os.environ["TMPDIR"])'
```

W procesie aplikacji można korzystać z /home/arduino/Vision (symlink do NVMe); zapis do innych katalogów eMMC zostanie odrzucony. Należy projektować zapisy do jawnych ścieżek `/srv/vision-data/...`.

## Przyszłe usługi Vision

- Konfiguracja startowa usług musi wykonać preflight i uruchomić launcher przed procesem aplikacji. Nie dopuszczać bezpośredniego uruchomienia binarki aplikacji jako obejścia.
- W systemd, jeżeli będzie użyty, dodatkowo ustawić `RequiresMountsFor=/srv/vision-data`, `ProtectSystem=strict`, `ReadWritePaths=/srv/vision-data` (po teście zgodności); to ochrona warstwowa, nie wymaganie dla przenośnego kodu.
- Logi użytkownika aplikacji i wolumeny kontenerów aplikacyjnych muszą wskazywać NVMe. Sam Bubblewrap nie ogranicza zapisów realizowanych poza procesem przez zewnętrzne API (np. Docker Engine); do takich integracji potrzebna osobna polityka wolumenów.
- Runtime ma blokować uruchomienie bez walidacji i dokumentować osobny test odłączenia/uszkodzenia NVMe.
- Serwer VS Code Remote i cache narzędzi niezwiązane bezpośrednio z uruchomioną aplikacją mogą nadal zapisywać na eMMC; ich ewentualna migracja wymaga osobnego etapu.

## Testy i kryteria przyjęcia

- Unit: 9 przypadków testowych (dobry mount; złe: device/fs/ro/UUID/label; niedozwolona symlinka cache; budowanie przestrzeni montowania).
- Gate sprzętowy: na rzeczywistym VENTUNO `--check=PASS` i `--smoke=PASS`.
- Gate awaryjny: na urządzeniu testowym / w bezpiecznym oknie, bez montowania NVMe, proces Vision odmawia startu z kodem 77. Nie odmontowywać produkcyjnego NVMe, gdy działa VS Code i repozytorium.
- Gate aplikacji: wszystkie entrypointy aplikacji uruchamiane przez launcher, brak miejsc zapisu do eMMC w testach integracyjnych.

Nie ogłaszać pełnego PASS na sprzęcie przed otrzymaniem logów z wykonania na VENTUNO.
