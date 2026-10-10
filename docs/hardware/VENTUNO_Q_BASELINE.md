# VENTUNO Q — bazowy stan stanowiska

**Źródło:** ręczne polecenia i logi z uruchamiania stanowiska w październiku 2026. To nie jest wynik pełnego audytu.

## Potwierdzone z terminala użytkownika

- Ubuntu 24.04.4 LTS / aarch64.
- Po aktualizacji i ponownym uruchomieniu: `6.8.0-1084-qcom`.
- Lokalny użytkownik: `arduino`; hostname: `vision`.
- OpenSSH: połączenie sieciowe i sesja SSH przekierowana przez USB-C/ADB działają.
- Tailscale: urządzenie widoczne jako `vision` i połączone z siecią VPN.
- NetworkManager: Wi-Fi działa i można je konfigurować przez `nmcli`.
- `git`, `gh`: instalacja, uwierzytelnianie SSH i konto GitHub zweryfikowane.
- Obecny jest interfejs `docker0`; sama obecność nie potwierdza stanu kontenerów.
- W systemie widoczne były interfejsy `can0`, `can1`, `can2`; ich działanie i przeznaczenie nie zostały przetestowane.

Nie zapisujemy tutaj prywatnych adresów IP, identyfikatorów urządzenia ADB, kluczy ani innych danych dostępowych.

## Wymaga pomiaru na rzeczywistym urządzeniu

- CPU/SOC, liczba rdzeni, RAM, swap, throttling i temperatury pod obciążeniem.
- eMMC vs NVMe: rzeczywiste wykrycie, format, mount i wolne miejsce (54,9 GB systemu root **nie dowodzi obecności NVMe**).
- Adreno: obecność i działanie sterowników/API akceleracji.
- Hexagon/NPU: biblioteki, urządzenia FastRPC/QNN, zgodność i test rzeczywistej inferencji.
- CSI/MIPI, USB, V4L2 i wykrywanie kamer.
- Stan pakietów OEM Arduino/Qualcomm i ścieżka odtwarzania systemu.
- Obsługa aparatu Sony A6100 przez bibliotekę/SDK dopiero po podłączeniu i teście.

## Ochrona środowiska producenta

Nie wykonujemy `do-release-upgrade`, `apt full-upgrade` ani zamiany pakietów kernela/sterowników bez osobnej decyzji i planu wycofania zmian.

Audyt tylko do odczytu: `scripts/audit/vision_audit_v1.sh`. Wynik zachowujemy początkowo poza repozytorium i przeglądamy pod kątem danych wrażliwych.
