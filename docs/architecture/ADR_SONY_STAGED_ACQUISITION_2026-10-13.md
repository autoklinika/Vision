# ADR-VISION-SONY-001 — etapowa akwizycja HDMI + Wi-Fi + USB

**Data:** 2026-10-13  
**Status:** **PROPOSED — preferowany wariant do walidacji; brak zatwierdzenia produkcyjnego**  
**Zakres:** wyłącznie tor Sony ILCE-6100A na VENTUNO Q. Nie dotyczy AI Platform, ECU Platform ani warstw robota.

## 1. Kontekst i przesłanki

Użytkownik preferuje niezależne kanały:

- **HDMI:** nieprzerwany, czysty podgląd sceny do kadrowania i wstępnej oceny jakości;
- **Wi-Fi Sony ScalarWebAPI:** autofocus, zoom, przysłona, ekspozycja, parametry i wyzwolenie fotografii;
- **karta SD aparatu:** bufor oryginalnych plików RAW+JPEG z całej sesji PCB;
- **USB Mass Storage:** import z karty dopiero po zakończeniu sesji; weryfikacja kopii na NVMe.

W testach 2026-10-13 potwierdzono kompletny **ręcznie przełączany** cykl: HDMI + Wi-Fi, wykonanie zdjęcia, oryginalne JPG 24 MP + ARW na SD, fizyczne wpięcie USB (auto Mass Storage), bezpieczny import i równe SHA-256.

**BLOKER:** firmware Sony nie dopuścił jednoczesnej aktywności PC Remote USB i ScalarWebAPI Wi-Fi. Programowe `usb1-port2/disable` usunęło aparat z enumeracji Linux, ale Sony pozostał w trybie USB; po fizycznym odłączeniu kabel przestał blokować obraz HDMI, jednak Wi-Fi DIRECT nie pojawiło się automatycznie. Funkcja `Zawsze połączony` nie została sprawdzona po pełnym cyklu (bateria się rozładowała).

## 2. Decyzja robocza

**Preferujemy etapowy transfer z pamięci SD zamiast wymagania równoczesnego USB i Wi-Fi.**

To **kandydat** na docelowy tor, a nie zaakceptowana implementacja. USB PC Remote + BLE pozostaje poprawnym wariantem awaryjnym i narzędziem diagnostycznym.

Nie wolno wprowadzać na tej podstawie automatycznej kontroli portów, firmware hacków, trwałego autostartu lub ostatecznej zmiany adaptera aparatu bez osobnego przeglądu.

## 3. Projektowany diagram stanów

```text
OFF / DISCOVERY
       |
       v
WIFI_READY -- HDMI_READY --> ACQUIRE
    |                         |
    |                    n x CAPTURE + CONFIRM
    |                         |
    |                       COMPLETE
    |                         v
    +--- (stop shutter) --> WIFI_QUIESCE
                              |
                       USB_CONNECT_REQUEST
                              |
                              v
                        USB_STORAGE_READY
                              |
                        SD_MOUNT_READ_ONLY
                              |
                          IMPORT_VERIFY
                         /           \
                    PASS             FAIL
                      |               |
                    UNMOUNT       HOLD/RETRY_IMPORT
                      |               |   (no SD deletion)
                    USB_DISCONNECT <--+
                      |
                 WIFI_RECOVERY
                    /       \
                 PASS       FAIL -> OPERATOR_INTERVENTION
                      |
                  NEXT_PCB
```

Każde przejście jest **warunkowe** i powinno mieć timeout, postcondition i rollback, a nie opierać się na sztywnym `sleep`.

| Stan | Warunki wejścia | Warunki wyjścia / dowód |
| --- | --- | --- |
| `WIFI_READY` | Sony ScalarWebAPI `getApplicationInfo`, `getEvent`; aparatu nie ma w USB Mass Storage | Wi-Fi stabilne, karta SD dostępna do zapisu (weryfikacja praktyczna) |
| `ACQUIRE` | Clean HDMI i kontrola kadru, ustawienia jakości RAW+JPEG, identyfikator sesji | Wszystkie zamówione ujęcia mają ACK + czas i spójne referencje |
| `WIFI_QUIESCE` | Brak aktywnego wyzwolenia i bezpieczny stan aparatu | Rozłączenie wyłącznie dedykowanego interfejsu Wi-Fi |
| `USB_STORAGE_READY` | Dostępny port aparatu; Linux rozpoznaje `054c:0f0b`; karta niezamontowana | `/dev/` poprawnie zweryfikowane po sygnaturze/modelu, bez zakładania stałego `sda1` |
| `IMPORT_VERIFY` | SD mounted `ro,nodev,nosuid,noexec`; NVMe dostępny | Zgodna liczba par JPG+ARW, rozmiary, dekodowanie JPEG, SHA-256 źródło/kopia, manifest |
| `WIFI_RECOVERY` | SD odmontowana, port USB fizycznie odłączony/odcięty | Sony rozgłasza Wi-Fi i API ponownie odpowiada; `Zawsze połączony` wymaga testu |
| `OPERATOR_INTERVENTION` | Brak udanego recovery przed deadline | Brak autonomicznych zdjęć i sterowania robotem; zapis kontekstu błędu |

## 4. Wymagania techniczne

### HDMI / UVC

- Testy z monitorem potwierdzają *clean HDMI*, ale brak przechwytywania cyfrowego. Do wdrożenia potrzebny grabber UVC, test rzeczywistych formatów (np. 1080p/30), dropów, latencji, ekspozycji i zachowania podczas `actTakePicture`.
- Podgląd nie zastępuje oryginału RAW/JPEG ani systemu bezpieczeństwa robota.
- Jakość końcowych zdjęć i focus stackingu oceniać z oryginałów; podgląd HDMI umożliwia ocenę wstępną przed długą serią.

### Wi-Fi / ScalarWebAPI

- Wykorzystywać **oddzielny adapter** w VENTUNO, `never-default`, bez nadpisania routingu/DNS systemowego.
- Jawny handshake i health-check API; gotowość aparatu odczytywać przed następnym zdjęciem, nie wykonywać natychmiastowych ślepych powtórek.
- Zoom: pozycja API **0–100**, nie mm; mierzyć stabilizację po ruchu i kalibrować w relacji do EXIF.
- Wszystkie zdjęcia z sesji numerować w lokalnym manifestcie, łączyć indeks ujęcia/pozycję robota/ustawienia. Odpowiedź HTTP/ScalarWebAPI nie jest dowodem istnienia ARW na SD.
- Ochrona haseł i identyfikatorów sieci: brak sekretów i adresów w publicznym Git.

### USB i karta SD

- Importować **Mass Storage**, nie mylić z PC Remote/PTP. Urządzenia `/dev/sdX` mogą się zmieniać między sesjami.
- Bezpieczna procedura: sprawdzenie tożsamości urządzenia, `mount -o ro`, walidacja plików na SD, kopia atomowa `.partial` → `final` na NVMe, `fsync`, hash źródło/kopia, manifest, `umount`.
- Przy utracie NVMe **fail-closed**: żadnego fallbacku na eMMC.
- Nie usuwać plików z karty automatycznie, dopóki polityka retencji, redundantny backup i potwierdzona integralność nie zostaną zatwierdzone.
- Błąd jednej fotografii nie może spowodować mylnego oznaczenia całej sesji jako kompletnej.

### Przełączanie portu USB

- Linux `authorized`, `unbind` lub `usb1-port2/disable` nie gwarantują fizycznego odcięcia USB **VBUS 5 V**. W realnym teście `disable` nie wyprowadziło Sony z trybu USB.
- Przed zakupem elektronicznego przełącznika/huba z rzeczywistym per-port power switching: potwierdzić zachowanie aparatu po fizycznym odłączeniu oraz odzyskanie sieci po restarcie i opcji `Zawsze połączony`.
- Ewentualny sterownik portu: izolować Sony od innych urządzeń; sprzętowy default-safe, ograniczony czas, niezależny rollback; nigdy nie przełączać pod zamontowanym SD.

## 5. Porównanie wariantów

| Wariant | Zalety | Blokady/ryzyka | Status |
| --- | --- | --- | --- |
| HDMI + Wi-Fi + po sesji USB Mass Storage | Rozbudowane sterowanie, zoom z odczytem pozycji, oryginały SD, małe obciążenie sieci dużymi zdjęciami | Powrót Wi-Fi po USB nieautomatyczny w badanej próbie; brak grabbera | **PREFEROWANY DO TESTÓW** |
| USB PC Remote + Bluetooth | 24 MP i RAW do NVMe, USB preview, ruch zoomu BLE działał równolegle | Słabsze odczyty parametrów zoomu przez BLE, błędy niektórych wyzwoleń PTP | **ALTERNATYWA** |
| HDMI-CEC jako sterowanie | Podstawowa nawigacja pilotem telewizora | Brak potwierdzonych komend sterowania ekspozycją/focus/zoom/shutter; konflikt trybów | **NIE REKOMENDOWANY** |
| Wi-Fi Remote API do pobierania RAW bez SD/USB | Brak etapu USB | Remote API zwracało jedynie JPEG postview; brak komend pobierania pełnego ARW | **NIEPOTWIERDZONY / NIE PRZYJMOWAĆ** |

## 6. Kryteria bramki produkcyjnej

**Wszystkie warunki wymagają PASS:**

1. Zimny start aparatu po wymianie akumulatora: jednoznaczne odzyskiwanie Wi-Fi bez menu, nie tylko widoczność SSID; test opcji `Zawsze połączony`.
2. Pełny cykl USB przy stale fizycznie podłączonym przewodzie, z elektrycznym odłączeniem rozpoznawanym przez Sony albo inną bezobsługową metodą (bez ingerencji w firmware).
3. Grabber HDMI-UVC poprawnie dostarcza wymagane 1080p i potwierdzoną latencję przy sterowaniu Wi-Fi.
4. Testy wielosesyjne i seria co najmniej 100 zdjęć, a następnie test docelowej liczby ujęć PCB, z walidacją braków, duplikatów i timingów.
5. Weryfikacja zapisu RAW+JPEG na SD dla każdego ujęcia oraz idempotentny import, hash i bezpieczny recovery po rozłączeniu.
6. Mechanizm zabezpieczenia przed niezamierzonym ruchem robota oraz poprawna reakcja na utratę połączenia (poza torem Sony).

Dokładna klasyfikacja dotychczasowych dowodów i ścieżek: [raport testów](../hardware/SONY_A6100A_MULTITRANSPORT_VERIFICATION_2026-10-13.md).

**Właściciel projektu podejmuje decyzję o zatwierdzeniu i merge do `main`.**
