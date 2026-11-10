# AgileX NERO — referencyjny snapshot pierwszostronnego STOP SW

**Status:** skrypt `nero_stop.py` jest zanonymizowaną kopią obecnego lokalnego programu obsługi STOP na Stream Deck Plus (stan 2026-11-10). **Nie jest certyfikowanym systemem E-STOP ani gotowym do użytkowania pakietem wydaniowym.** Nie uruchamiaj do robota bez osobnej procedury commissioning.

## Funkcja

- `--send`: sprawdza obecność właściwego adaptera USB-CAN, podłącza się do firmware `NeroFW.V121` i wysyła jedną komendę `electronic_emergency_stop()`.
- Nie wysyła komend `enable()`, `disable()`, `move_j()` ani poleceń wyłączenia 24 V.
- Zapisuje trwały lokalny **latch**, rejestruje pośrednie stany `STOP_REQUESTED` / `STOP_COMMAND_SENT_UNVERIFIED` i odczytuje odpowiedź sterownika. Sama odpowiedź `EMERGENCY_STOP(0x1)` **nie gwarantuje fizycznego zatrzymania w ustalonym czasie**.
- `--dry-run` sprawdza import SDK i nie wysyła nic do magistrali CAN.
- Lokalny latch to rejestr/diagnostyka. **Nie ma jeszcze centralnego interlocka** chroniącego przed innymi procesami sterowania.

## Konfiguracja prywatna

W repozytorium **nie publikujemy** numeru seryjnego adaptera USB-CAN. Snapshot korzysta z `VISION_NERO_CAN_SERIAL`; brak tej zmiennej blokuje transmisję (guard adaptera nie zostanie zaliczony). Właściwą wartość należy odczytać bezpośrednio na uprawnionym stanowisku i przekazać poza repo/konfiguracją publiczną.

Przed właściwym użyciem sprawdź również, czy `can0` rzeczywiście należy do dedykowanego adaptera AgileX. Wbudowany CAN Arduino VENTUNO Q może otrzymywać nazwy `can0...can2` po zmianach USB i nie jest zamiennikiem bez weryfikacji.

Ścieżki runtime w skrypcie są nadal zgodne z lokalną instalacją `/srv/vision-data/tools/streamdeck-prod`. Nie zmieniono pracującego kodu na urządzeniu przy przygotowaniu tej kopii.

## Nie wykonywać automatycznie

- Nie aktywować napędów ani nie uruchamiać skryptów ruchu z SDK w procesie instalacji lub CI.
- Nie używać STOP programowego jako niezależnego zabezpieczenia operatora.
- Przed pierwszym testem ruchu zapewnić stabilne mocowanie, podparcie przed opadnięciem i zweryfikowane warunki ochrony.
- Nie resetować kontrolera automatycznie po STOP.

Ustalenia i bramki: [ADR-VISION-ROBOT-001](../../docs/architecture/ADR_VISION_NERO_TWO_STAGE_STOP_2026-11-10.md).
