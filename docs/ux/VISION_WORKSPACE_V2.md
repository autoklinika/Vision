# Vision Workspace V2 — czytelna nawigacja i formularze

- **Data:** 2026-11-25.
- **Status:** IMPLEMENTED w izolowanej gałęzi; przegląd i weryfikacja przed decyzją o merge/wdrożeniu.
- **Zakres:** prezentacja WebGUI i nawigacja. Kontrakty Core, autoryzacja, biblioteka i cykl życia inspekcji pozostają po stronie systemu.

## Powód zmiany

Pikselowe fonty i obsługa wielu przesuwanych okien utrudniały odczyt oraz edycję profili, szczególnie na małym ekranie. Workspace V2 zastępuje wizualny kierunek Windows 98 opisany w specyfikacji V1: system wizualny, Desktop Shell, menu Start, geometrię okien i odpowiadające im kryterium WEB-02. Zasady architektury klienta, pochodzenia danych, bezpieczeństwa i rozdzielenia profilu od inspekcji pozostają obowiązujące.

## Interfejs

| Obszar | Zachowanie V2 |
| --- | --- |
| Typografia | Systemowy krój, podstawowy tekst i pola 16 px, czytelna interlinia; bez fontów bitmapowych i zewnętrznych usług fontów. |
| Nawigacja | Stały panel z grupami Workspace, Devices i Preferences; jeden aktywny obszar roboczy z nagłówkiem. |
| Mały ekran | Do 900 px nawigacja przechodzi w wysuwane menu; Escape, przycisk zamknięcia i wybór sekcji zamykają menu. |
| Formularze | Pełna dostępna szerokość, zawijane paski akcji, układ pól dostosowany do szerokości i kontrolki co najmniej 44 px wysokości. |
| Biblioteka | ECU Library → New profile → Create draft; zapis dalszych zmian przez Save draft generation. |
| Edytor | Lista sekcji na szerokim ekranie, selektor sekcji na wąskim; długie tabele przewijają się we własnym obszarze. |
| Komunikacja | Stan połączenia Core oddzielony od stanu sesji. Niedostępny Core oznacza Session status unavailable. |
| Wygląd | Neutralne tło, białe powierzchnie, ciemna nawigacja, niebieskie akcje i widoczny fokus klawiatury. |

Aplikacje pozostają tymi samymi klientami istniejących raportów. Moduły bez integracji nadal wskazują brak danych i mają nieaktywne akcje. Nowa nawigacja nie uruchamia urządzeń ani sesji.

## Stan formularzy i dostępność

Zmiana sekcji nie zamyka otwartego edytora ECU: odwiedzone widoki są zachowane w pamięci, a nieaktywny widok jest ukryty. Wylogowanie i reset przestrzeni sprawdzają także ukryty edytor. Niezapisane dane wymagają potwierdzenia odrzucenia; operacja oczekująca na wynik blokuje te działania.

Settings jest wyjątkiem: opuszczenie widoku usuwa wpisane hasła z pól. Rozpoczęta zmiana hasła pozostaje obsługiwana przez nadrzędny komponent uwierzytelniania, tak jak wcześniej.

Przejściowa niedostępność HTTP/auth nadal zachowuje bufor edytora. Ukryta przestrzeń jest nieinteraktywna i zwalnia obsługę Tab/Escape z menu, aby dostępne były przyciski odzyskania połączenia. Potwierdzone 401, zmiana użytkownika/roli albo rzeczywistego właściciela Core zachowują dotychczasowe reguły unieważniania danych.

Nawigacja ma nazwany obszar, aktywną pozycję, fokus nagłówka po przejściu, zamknięcie menu z powrotem do przycisku oraz ograniczenie fokusu wewnątrz otwartego menu mobilnego. Skrót Skip to content omija panel nawigacyjny.

## Preferencje i zależności

Klucz `vision.workspace.v2` przechowuje wyłącznie `{schema, activeApp}`. Nie zapisuje formularzy, haseł, tokenów ani stanu inspekcji. Niepoprawna lub niedostępna preferencja otwiera System Status. Dawna geometria okien nie jest odtwarzana.

Usunięto zależność `98.css`, jej import i dystrybuowane fonty. Pozostają dotychczasowe React/TypeScript/Vite. Ikony są własnymi prostymi SVG; systemowy tekst VISION nie wykorzystuje prywatnego assetu marki. Standardowy build nadal wyklucza prywatne materiały.

## Weryfikacja

Weryfikacja obejmuje typy, lint, jednostkowy kontrakt preferencji, start LAB i produkcyjny build stanowiskowy. Testy przeglądarkowe sprawdzają nawigację i klawiaturę, 360 px, brak przewijania całej strony w poziomie, działanie edytora po zmianie sekcji, ochronę niezapisanych i oczekujących zmian, obsługę utraty połączenia oraz czyszczenie pól hasła.

Testy stanowiska i edytora korzystają wyłącznie z izolowanych kont, bibliotek i Core fixture. Nie wskazują produkcyjnego konta, socketu ani magazynu. Szczegółowe wyniki znajdują się w opisie PR i jego CI.

## Wdrożenie i wycofanie

Zmiana przechodzi przez PR i zatwierdzenie właściciela. Implementacja nie oznacza przełączenia produkcji. Wdrożenie używa istniejącego instalatora przypiętego wydania i zachowuje stan kont, bibliotekę oraz niezależny Core. Wycofanie polega na przywróceniu poprzedniego wydania klienta zgodnie z runbookiem; nie wymaga cofania danych profili.

Powiązania: [kontrakt stanowiskowy](../implementation/VISION_STATION_WEBGUI_V1.md), [edytor ECU](../implementation/VISION_ECU_DRAFT_EDITOR_V1.md), [wdrożenie](../operations/VISION_WEBGUI_DEPLOYMENT.md), [architektura klienta](../decisions/ADR_VISION_WEBGUI_CLIENT_ONLY_2026-11-24.md).
