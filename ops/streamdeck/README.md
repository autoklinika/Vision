# Vision / Stream Deck Plus — źródłowy snapshot OpenDeck

**Status po restarcie 2026-11-10:** usługa `vision-opendeck.service` jest włączona, lecz podczas audytu nie wykrywała panelu USB i wielokrotnie się restartowała. To problem otwarty; **nie deklarować bieżącej dostępności STOP SW**.

## Co wdrożono i potwierdzono wcześniej

- OpenDeck **2.14.1 ARM64** na VENTUNO Q, uruchamiany z NVMe przez Xvfb (bez aktywnego pulpitu operatora).
- Urządzenie Elgato Stream Deck Plus z układem 2 × 4, podłączane przez HID; reguła udev dopuszcza tylko `0fd9:0084` do grupy `input`.
- Prawy dolny klawisz (slot indeks 7, `Keypad.7.0`) wyświetla czerwony `STOP SW` i wywołuje lokalny skrypt `nero_stop.py --send`.
- Fizyczne naciśnięcie w sesji laboratoryjnej wywołało żądanie STOP; NERO odpowiedział `EMERGENCY_STOP(0x1)`.
- Operator zaakceptował chwilowe zmniejszenie ikony podczas wciśnięcia. Brak pełnego panelu menu po STOP.

## Co zawiera repozytorium

- `vision-opendeck.service` — kopia jednostki użytkownika systemd; istniejący deployment uruchamiany z katalogu lokalnego `/srv/vision-data/tools/streamdeck-prod`.
- `start-opendeck.sh` — skrypt uruchamiający OpenDeck z lokalnej rozpakowanej paczki testowej i izolowanego profilu XDG.
- `activate.sh` — historyczny lokalny aktywator, **odwołuje się do oryginalnych ścieżek produkcyjnych na NVMe**, wymaga `sudo` i nie może być używany jako uniwersalny instalator z checkout.
- `71-vision-streamdeck-plus.rules` — dedykowana reguła udev.
- `profile/Default.example.json` — zanonimizowany przykład przypisania jednego przycisku; nie zawiera nazwy folderu/serialu sprzętu.
- `icons/nero-stop-sw.png` — pierwszostronna grafika przycisku.
- Faktyczny binarny OpenDeck, wtyczki, hasła urządzeń, profile tożsamości i pliki lokalnego runtime **nie zostały dodane do Git**.

## Ważne ograniczenia

- Zależność od USB HID, Linuxa, Xvfb, OpenDeck, wtyczki Run Command, Python, SDK i CAN wyklucza niezależne bezpieczeństwo funkcjonalne.
- Brak HID w momencie uruchomienia powoduje zakończenie programu z kodem 10; aktualna jednostka ma `Restart=always` i nieograniczone ponawianie. Wymaga korekty przed określeniem jej jako odpornej produkcyjnie.
- Program nie stanowi centralnego interlocka dla innych sterowników ruchu.
- Prawidłowe przywrócenie po restartach oraz end-to-end test po fizycznym ponownym podłączeniu panelu wciąż wymagają weryfikacji.
- Nie odcinać zasilania NERO jako normalnej reakcji na STOP.

Dokument architektury: [ADR NERO STOP](../../docs/architecture/ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md). Audyt bieżący: [AS-BUILT](../../docs/operations/VISION_AS_BUILT_2026-11-10.md).
