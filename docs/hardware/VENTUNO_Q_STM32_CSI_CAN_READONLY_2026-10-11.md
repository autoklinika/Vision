# Vision — VENTUNO Q: STM32-01/02, CSI-01 i CAN-01 (2026-10-11)

**Typ raportu:** hardware read-only, kontynuacja [raportu bazowego](VENTUNO_Q_HARDWARE_VERIFICATION_2026-10-10.md). **Status:** wyniki etapów, nie finalny Vision Hardware Baseline v1.
**Środowisko:** Arduino VENTUNO Q, Qualcomm QCS8275, Ubuntu 24.04.4 LTS arm64, kernel `6.8.0-1084-qcom`; host `vision`.
**Metoda:** bezpośredni odczyt przez Desktop Commander MCP, głównie `sysfs`, Device Tree, `udevadm`, `ip`, `lsusb`, `systemctl`, `journalctl`, `dpkg-query` oraz odczyt dokumentacji z GitHub `main`. Zrzut terminalowy pozostał w sesji MCP; nie publikowano pełnych logów ani identyfikatorów prywatnych.

## 1. Matryca testów

| ID | Zakres | Wynik | Granica potwierdzenia |
|---|---|---|---|
| STM32-01 | Identyfikacja i kanał USB/Router | **PASS — wykrycie** | Nie dowodzi responsywności funkcji MCU |
| STM32-02A | RPC klient Linux -> Arduino Router `$/version` | **PASS** | Odpowiedź Routera, NIE STM32 |
| STM32-02B | RPC Linux -> STM32 -> Linux | **BLOCKED / UNVERIFIED** | Nie znaleziono potwierdzonej bezskutkowej metody MCU; nie wysyłano żądań nieudokumentowanych |
| CSI-01A | Konfiguracja subsystemu kamer w DT | **PASS — obecność wpisów** | Wpis `status=ok` nie potwierdza działającego sterownika |
| CSI-01B | Bind sterownika CSI i realna akwizycja | **UNVERIFIED / BLOCKED** | Brak aktywnego toru kamery i odpowiedniego sensora |
| CAN-01A | Enumeracja trzech interfejsów SocketCAN | **PASS — wykrycie** | Wszystkie `DOWN` / `STOPPED` |
| CAN-01B | Ruch CAN, transceivery, fizyczna magistrala i FD | **UNVERIFIED** | Żadnego TX/RX i żadnej zmiany konfiguracji |

## 2. STM32H5: identyfikacja i połączenie

- Lokalny core Zephyr 1.0.0 i pliki firmware dla wariantu `arduino_ventuno_q_stm32h5f5xx`; model potwierdzony po stronie build target jako **STM32H5F5xx**. Pełnego oznaczenia układu z nadruku fizycznego nie odczytywano.
- Urządzenie USB Arduino: `1209:ca01`, `Arduino Generic board`, USB High Speed 480 Mb/s; `bcdDevice=0404` to deskryptor USB, **nie** wiarygodny odczyt wersji działającego firmware.
- Interfejs `/dev/ttySTM0` jest symlinkiem na `/dev/ttyACM0`, sterownik `cdc_acm`; reguła `/etc/udev/rules.d/99-stm-tty.rules` tworzy alias.
- Usługa `arduino-router 0.10.0` uruchomiona: `--unix-port /var/run/arduino-router.sock --serial-port /dev/ttySTM0 --serial-baudrate 115200`. Systemd `active/running`, w czasie pomiarów PID 1862, brak restartów od aktualnego uruchomienia. Log zawiera `Opened serial connection`.
- Pakiety: `arduino-ventunoq 0.3.0`, `arduino-ventunoq-config 0.4.0`. Biblioteka `Arduino_RouterBridge 0.4.3` w lokalnym katalogu Arduino. Zawiera mechanizm rejestracji funkcji `Bridge.provide()` / `provide_safe()`.
- Wykonane pojedyncze zapytanie `arduino-router-cli '$/version'` zwróciło `0.10.0`, exit 0. **Metoda obsługiwana wewnętrznie przez Router; nie wolno przedstawiać tego jako dwukierunkowego RPC z MCU.**
- Nie znaleziono zweryfikowanej bezskutkowej funkcji MCU dostępnej do bezpiecznego wywołania. Nie otwierano bezpośrednio portu zajętego przez Router; nie resetowano ani nie flashowano STM32.
- W generatorze systemd znajdują się warianty `gpioset` 1.x i 2.x. Na VENTUNO działa `libgpiod 1.6.3`; w logach widoczne są komunikaty `invalid option -- 'c'` dla składni 2.x. Router jest mimo to aktywny. Nie poprawiano konfiguracji.
- Wersja faktycznie działającego firmware MCU i sukces wymiany z aplikacją MCU: **UNVERIFIED**. Lokalne obrazy `.elf`, `.bin`, `.hex` nie dowodzą zgodności z aktualnym flash.

## 3. CSI/ISP: konfiguracja i dostępność

- Device Tree zawiera 3 kontrolery `csiphy0..2`, 2 `csid0..1`, 5 `csid-lite0..4`, 2 `ife0..1`, 5 `ife-lite0..4`, CCI/CPAS oraz bloki ISP/SFE/ICP/IPE. Te wpisy oznaczają opis sprzętu, nie pełne uruchomienie.
- W opisach vendorowych CCI znajdują się deklaracje pięciu sensorów `qcom,cam-sensor23..27` ze statusem `ok`; nie jest to dowód podłączenia fizycznych sensorów. Osobny węzeł `cci@ac14000` ma `status=disabled`, co nie pozwala wyprowadzać wniosku o całym subsystemie CCI.
- Przeanalizowane urządzenia platformowe wejścia kamery (`qcom,csiphy*`, `qcom,csid*`, `qcom,ife*`, `qcom,cam-*`) w badanym stanie nie miały skojarzonego aktywnego sterownika.
- Na dysku jest moduł `qcom-camss.ko.zst`, z aliasami m.in. `qcom,qcs8300-camss` / `qcom,sa8775p-camss`, ale nie był załadowany. Nie podjęto próby `modprobe`.
- Istnieją `/dev/media0`, `/dev/video32`, `/dev/video33`, ale należą do `aa00000.video-codec` / `iris_vpu` (kodek wideo), **nie** są dowodem działającej akwizycji CSI. Liczba `/dev/v4l-subdev*`: 0.
- `v4l2-ctl` i `media-ctl` nie były zainstalowane; niczego nie instalowano. Żadnego stream-on, capture, przełączania pinów ani sensor probing.
- Weryfikacja funkcjonalna wymaga potwierdzonego modułu MIPI, schematu/pinoutu oraz kompatybilnego stosu kamer. Nie należy uznawać CSI/ISP za produkcyjnie gotowe.

## 4. CAN-01: rzeczywisty stan SocketCAN

| Właściwość | can0 | can1 | can2 |
|---|---|---|---|
| Netdev | dostępny | dostępny | dostępny |
| Sterownik | `gs_usb` | `gs_usb` | `gs_usb` |
| Powiązanie USB | `3-1:1.0` | `3-1:1.0` | `3-1:1.0` |
| Stan Linux | `DOWN` | `DOWN` | `DOWN` |
| Stan CAN | `STOPPED` | `STOPPED` | `STOPPED` |
| RX packets / errors / dropped | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| TX packets / errors / dropped | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| MTU podczas odczytu | 16 B | 16 B | 16 B |
| Zegar zgłaszany przez driver | 48 MHz | 48 MHz | 48 MHz |

- Kernel wykrył urządzenie USB `1209:ca01` i zarejestrował `gs_usb`; log: `gs_usb 3-1:1.0: Configuring for 3 interfaces`. Ten sam sprzęt udostępnia CDC ACM STM32 i kanały CAN.
- `ip -details -statistics link show dev can0/can1/can2` pokazuje zakresy nominalnego i data bit timing drivera. Same zakresy nie potwierdzają CAN-FD. Aktualne `mtu=16` nie jest stanem interfejsu skonfigurowanego w trybie FD.
- Brak bitrate i stanu `ERROR-ACTIVE` wynika z `DOWN/STOPPED`; nie zakładamy transmisji, terminacji, obecności transceivera w gotowości ani poprawnego podłączenia przewodów. Liczniki zero nie są pomiarem zdrowia magistrali, jeśli interfejs jest wyłączony.
- W tym etapie nie instalowano `can-utils`, nie wykonywano `ip link set`, `candump`, `cansend`, żadnych ramek TX, testów loopback ani przełączenia FD.
- Następny test, wyłącznie po osobnej zgodzie i z podłączonym układem testowym: identyfikacja pinów/transceiverów/terminacji, skonfigurowanie bitrate i `listen-only`, test RX na znanym źródle, potem izolowany test TX oraz CAN-FD i bezpieczne przywrócenie stanu.

## 5. Ograniczenia i decyzje

1. `PASS` dotyczy odczytu, enumeracji lub diagnostyki Routera, nie gotowości do aktywnego sterowania.
2. **STM32** nadaje się architektonicznie do przyszłych zadań GPIO/PWM i synchronizacji, lecz dostępność pinów, deterministyczność oraz program MCU pozostają do sprawdzenia. Nie wolno przyjmować MCU jako certyfikowanego kontrolera bezpieczeństwa robota.
3. **CSI** — brak obecnie dowodu działającego toru capture; nie zmieniano sterowników.
4. **CAN** — trzy niezależne interfejsy widoczne w Ubuntu, ale aktywny ruch i FD niezweryfikowane.
5. Bez nowych instalacji, zmian firmware, konfiguracji MCU/CAN, uruchamiania Vision Core lub modyfikacji innych projektów.
6. Wpisy i pomiary pochodzą z sesji MCP 2026-10-10 UTC / 2026-10-11 Europe/Warsaw; surowe wyjścia pozostają w sesji, nie zapisano pliku dowodowego na urządzeniu.

## 6. Dalsza roadmapa po ponownym uruchomieniu

- NET-01: Ethernet 2.5 Gb/s, link i pomiar transferu po akceptacji.
- USB 3.0 / USB-C: rzeczywisty SuperSpeed, DP Alt Mode i dotyk na odpowiednim monitorze.
- NVMe: SMART/temperatura, bez ponownego otwierania wątku Write Guard.
- THERM-01: telemetry CPU/GPU/NPU i throttling, bez zbędnego stresowania urządzenia.
- Osobna decyzja o testach funkcjonalnych STM32, MIPI CSI i CAN oraz ostatecznym Hardware Baseline v1.

Powiązane dokumenty: [raport VENTUNO 2026-10-10](VENTUNO_Q_HARDWARE_VERIFICATION_2026-10-10.md), [baseline](VENTUNO_Q_BASELINE.md), [rejestr dowodów](EVIDENCE_REGISTER_2026-10-10.md).
