# Vision — rejestr po odbiorze Luxonis V1 (DEV)

**Snapshot 26.11.2026, przed commitem dokumentacyjnym.** Lekki porządek
repozytorium, bez merge i bez wdrożenia produkcyjnego. Poprzedni [rejestr
25.11](REPOSITORY_REGISTER_2026-11-25.md) pozostaje ewidencją historyczną.

## Aktualne gałęzie i PR

| Obszar | Stan |
| --- | --- |
| main | [1a5538c2](https://github.com/autoklinika/Vision/tree/1a5538c28717858dd0a5403dedbc8de6f3e0de3f), #79 i #80 scalone przed tym porządkowaniem |
| DEV | [#81](https://github.com/autoklinika/Vision/pull/81) DRAFT — `feat/vision-fluent-system-status-v1`, odbiór funkcjonalny na [57dfb1e9](https://github.com/autoklinika/Vision/tree/57dfb1e952ee1bbdd82704f8abf32df966fb9d42), 18 commitów przed aktualizacją dokumentacji |
| [#76](https://github.com/autoklinika/Vision/pull/76) | DRAFT, niezależny workflow review/release ECU; pozostaje do porównania z zakresem #81, nie zakładać równoważności |
| [#51](https://github.com/autoklinika/Vision/pull/51) | DRAFT LAB, eksperymentalna lokalizacja RGB-D; zachować materiał i osobną bramkę S03/S04 |
| [#77](https://github.com/autoklinika/Vision/pull/77) | Zamknięty bez merge — wcześniejszy wariant workspace, zastąpiony kierunkiem #79/#80 |
| [#78](https://github.com/autoklinika/Vision/pull/78) | Zamknięty bez merge — porównanie Carbon/Fluent 2 zakończone wyborem Fluent 2 |

71 gałęzi zdalnych, 28 lokalnych i 31 zarejestrowanych worktree po odświeżeniu
referencji origin; brak prunable worktrees. Zachowano wszystkie gałęzie,
katalogi, przypięte wydania, backupy i historię. Nie wykonywano rebase, squash,
force-push, git clean ani zmian main. Zbiorczy Draft #81 obejmuje istniejący
pakiet, nie jest małym niezależnym PR-em; nie rozdzielano go teraz przez
przepisywanie historii.

## DEV — zaakceptowany zakres i dowody

- System Status: diagnostyka usług, USB, ROS 2.
- Biblioteka ECU: [cykl życia](../implementation/VISION_ECU_LIBRARY_LIFECYCLE_V1.md)
  i [deklaracja V2](../implementation/VISION_ECU_DECLARATION_V2.md).
  Deklaracja nie jest zatwierdzoną recepturą inspekcji.
- [Luxonis V1](../implementation/VISION_DEVICES_LUXONIS_V1.md):
  operator zaakceptował obecny diagnostyczny podgląd po stabilizacji.
  RGB/Depth, odczyt parametrów, [autostart](../implementation/VISION_LUXONIS_AUTOSTART_V1.md)
  oraz [IR](../implementation/VISION_LUXONIS_IR_V1.md). Wysoka rozdzielczość
  akwizycji zachowana; nie utożsamiać jej z natywną głębią stereo ani
  zatwierdzoną metrologią.
- Odbiór etapowy: 225/225 API na etapie IR, później 12/12 celowanych
  testów Luxonis; 86/86 unit GUI oraz celowane Chromium/Firefox PASS.
  Na 57dfb1e9 rzeczywisty test HTTPS 45 s: 153/153 obserwacji obu obrazów,
  85/85 odpowiedzi API, bez restartu kamery. Nie jest to pełny audyt
  całego pakietu ani odbiór długotrwały. Opóźnione klatki głębi nadal możliwe.

## Rozdzielenie kodu od usług

Stan odczytany bez restartu podczas porządkowania:

- Produkcyjny WebGUI: przypięte wydanie 1a5538c2; Core: niezależne
  f98bb97f. Lokalny main zgodny z origin/main.
- DEV: bieżąca gałąź; Core/GUI DEV i obserwator działają.
- Stała usługa Luxonis działa niezależnie, autostart aktywny zgodnie
  z wcześniejszą decyzją operatora. NERO pozostaje bez zmian.
- Aktualizacja samej dokumentacji nie jest nowym buildem ani wdrożeniem.
  Nie wykonano operacji na urządzeniach ani danych ECU.

## Przed merge #81

Pełny audyt aktualnego diffu, komplet aktualnych testów i CI, ocena #76
względem #81, procedura skoordynowanego wydania Core/API/GUI i zachowania
danych przy rollbacku, a następnie jawna decyzja operatora. Pełny zimny
rozruch kamery, fizyczne rozłączenie USB i metrologia pozostają osobnymi
bramkami sprzętowymi. Nie uruchamiać kolejnych eksperymentów tylko po to,
żeby uporządkować Git.

Następny moduł urządzenia: NERO (propozycja, nie rozpoczęto). Backlog
[#71](https://github.com/autoklinika/Vision/issues/71),
[#72](https://github.com/autoklinika/Vision/issues/72),
[#73](https://github.com/autoklinika/Vision/issues/73) pozostaje otwarty.
