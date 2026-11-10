# Autostart Desktop Commander Remote MCP — VENTUNO Q

Status: **STAGED / manual systemd activation required**. Kod wersjonowany; autoryzacja agenta jest przechowywana wyłącznie lokalnie na NVMe i **nie jest umieszczana w Git**.

## Architektura

- Host: `vision`, Ubuntu 24.04 ARM64, usługa systemd (`/etc/systemd/system/vision-remote-mcp.service`).
- Proces pracuje jako `arduino`, nie root.
- Node.js: `/srv/vision-data/tools/node/bin/node`.
- Desktop Commander: wersja **0.2.52**, instalacja trwała na NVMe: `/srv/vision-data/tools/remote-agent/runtime`.
- Dane autoryzacyjne, konfiguracja, cache, pliki tymczasowe i logi w `/srv/vision-data/tools/remote-agent`.
- Zależność systemd `RequiresMountsFor=/srv/vision-data` oraz preflight weryfikujący `/dev/nvme0n1p1`, ext4, UUID, etykietę `VISION_DATA`, RW i obecność istniejącej tożsamości agenta.
- Gdy NVMe jest nieobecny, nie uruchamiamy agenta i nie zapisujemy jego danych na eMMC.
- Usługa ponawia uruchomienie (Restart=always), działa po restarcie bez terminala VS Code.
- Logi do `logs/remote-mcp.log` na NVMe; rotacja `10M * 5`.
- Pliki systemd i logrotate w `/etc` są minimalną konfiguracją systemową (dozwolone na eMMC).

## Instalacja jednorazowa

Na urządzeniu z działającym Remote MCP:

```bash
sudo bash /srv/vision-data/tools/remote-agent/service/activate.sh
```

Skrypt bezpiecznie sprawdza NVMe, kopiuje przygotowaną usługę do `/etc/systemd/system`, konfigurację rotacji do `/etc/logrotate.d` i uruchamia `systemctl daemon-reload` oraz `systemctl enable --now vision-remote-mcp.service`.

**Nie uruchamiać dwóch instancji przez długi czas:** po potwierdzeniu aktywnej usługi zakończyć ręczny proces `npx ... remote`.

## Weryfikacja

```bash
systemctl is-enabled vision-remote-mcp.service
systemctl is-active vision-remote-mcp.service
systemctl status vision-remote-mcp.service --no-pager
tail -n 30 /srv/vision-data/tools/remote-agent/logs/remote-mcp.log
```

Następnie zamknąć dotychczasowy terminal ręcznie uruchomionego agenta i potwierdzić status `vision: Online` w panelu Remote MCP. Ostateczny test trwałości wymaga restartu VENTUNO w uzgodnionym oknie i ponownej weryfikacji statusu Online; nie wykonywać restartu wyłącznie w celu audytu bez zgody użytkownika.

## Rollback

```bash
sudo systemctl disable --now vision-remote-mcp.service
```

Powrót do trybu ręcznego:

```bash
# Po ręcznym ustawieniu PATH i HOME/XDG na NVMe:
npx --yes @wonderwhy-er/desktop-commander@0.2.52 remote
```

**Bezpieczeństwo:** agent udostępnia narzędzia terminala na autoryzowanym urządzeniu; autostart zwiększa stały okres dostępności. Stosować ograniczenia uprawnień po stronie konta i dostępu do Remote MCP.
