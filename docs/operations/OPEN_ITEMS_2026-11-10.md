# Vision — lista otwartych elementów po audycie 2026-11-10

Używamy stanów `BLOCKED / PLANNED / NEEDS VALIDATION`. Pozycje opisują zakres dalszej pracy, **nie** polecenie uruchamiania aktuatorów.

| Priorytet | Obszar | Status | Warunek domknięcia |
|---|---|---|---|
| P0 | Bezpieczne zatrzymanie AgileX NERO | BLOCKED / SAFETY | Niezależne zabezpieczenie wynikające z oceny ryzyka, mechaniczne zabezpieczenie przed opadnięciem, wiarygodny pomiar drogi/czasu hamowania |
| P0 | Centralny NERO motion interlock | PLANNED | Wszystkie źródła ruchu przechodzą przez jedną bramkę, STOP zablokowany do jawnego recovery, testy restartu/utraty CAN |
| P0 | Reakcja na POWER FAILURE przy ramieniu z aparatem | PLANNED | Zdefiniowane granice energii UPS, bezpieczna kolejność stop/parkowanie/poweroff, brak ruchu przy STOP |
| P1 | Niezawodność USB / switch | BLOCKED | Stream Deck, Sony i AgileX CAN wykrywane stabilnie po restartach i przełączeniu hostów, logi enumeracji |
| P1 | OpenDeck autostart przy braku panelu USB | NEEDS FIX | Brak ciągłej pętli restartów podczas braku HID, reaktywacja po powrocie urządzenia, test unplug/replug |
| P1 | Menu po STOP na Stream Deck | PLANNED | Zatwierdzone opcje i uprawnienia, odróżnienie STOP/FAULT/POWER FAILURE, bez samoczynnego restartu |
| P1 | Miejsce i układ elektryczny fizycznego przycisku (etap 2) | PLANNED | Pinout VENTUNO, monitorowanie styku, fail-safe przy odłączeniu, osobna ocena poziomu bezpieczeństwa |
| P1 | Test pierwszego ruchu NERO | BLOCKED / COMMISSIONING | Stabilne mocowanie, wolna przestrzeń, właściwe zabezpieczenia, zatwierdzona procedura i odrębna zgoda operatora |
| P2 | Sony automatyczna sekwencja HDMI/Wi-Fi/SD/USB | NEEDS VALIDATION | Automatyczny recovery z Wi-Fi, import z hashami, test serii, kontrola AF i stabilizacji |
| P2 | Thermal v0.6 metrologia | FROZEN | Weryfikacja temperatur wzorcem, kalibracja, retest USB, decyzja o dalszym DEV |
| P2 | Vision Core / integracja kamery głębi i oświetlenia | PLANNED | Interfejsy modułów i testy kinematyki bezpieczne dla sprzętu, zatwierdzona integracja |
| P2 | Publikacja źródeł Thermal | PRIVATE BY DESIGN | Osobna decyzja o repo prywatnym i audyt zależności GPL oraz praw redystrybucji |
| P2 | Aktualizowanie `main` | REVIEW REQUIRED | Przegląd PR, zatwierdzenie właściciela, dopiero wtedy merge |

**Ochrona:** przy braku gwarantowanego podtrzymania ramienia nie wolno automatycznie odcinać 24 V jako normalnej metody STOP. Grzybek GPIO wywołujący SDK jest wejściem STOP programowego, a nie niezależnym bezpieczeństwem sprzętowym.
