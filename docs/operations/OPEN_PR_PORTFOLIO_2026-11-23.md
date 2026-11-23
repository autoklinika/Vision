# Vision — przegląd historycznych PR po akceptacji VGP V1

**Audyt:** 23 listopada 2026, publiczne repozytorium autoklinika/Vision.
**Punkt odniesienia:** docs/baselines/VISION_GUIDED_POSITIONING_V1_2026-11-23.md.

Pierwotnie otwarte było **29 PR-ów**, w większości projektowanych jako odizolowane szkice. Baza VGP V1 została przetestowana na NERO/ETC3/PTM, dlatego nie wolno traktować starszych testów offline ani starszych deklaracji możliwości ROS2 jako aktualnego stanu systemu. Zamknięte PR-y zachowują całą historię GitHub i gałęzie z kodem.

## Archiwizowane jako zastąpione / historyczne

| PR | Powód decyzji |
|---|---|
| [#35](https://github.com/autoklinika/Vision/pull/35) | C8 — autorski wykonawca ROS2 FollowJointTrajectory. Zastąpiony fabrycznym MoveIt2/AgileX. |
| [#34](https://github.com/autoklinika/Vision/pull/34) | C7 — IK i kolizje w starym zestawie hipotetycznych transformacji. Zastąpiony zweryfikowanym eksperymentem VGP V1. |
| [#33](https://github.com/autoklinika/Vision/pull/33) | C7 — pierwotne cele ujęć z plan-only, bez obecnych danych Luxonis. Zachować jako historię. |
| [#29](https://github.com/autoklinika/Vision/pull/29) | Stary roboczy SCN-001 ETC3 offline, dziś zatwierdzono rzeczywiste dojazdy przez Luxonis/MoveIt. |
| [#27](https://github.com/autoklinika/Vision/pull/27) | Wczesny raport migracji ROS2, dokumentujący dawne niepowodzenie połączenia kamery; VGP V1 ma nowsze pozytywne testy. |
| [#22](https://github.com/autoklinika/Vision/pull/22) | Perception Engine jako osobna usługa i własny synchronizator — kierunek zastąpiony oficjalnym ROS 2 i węzłami specjalizacji ECU. |
| [#21](https://github.com/autoklinika/Vision/pull/21) | Stary ADR rozdzielający Camera/Perception/Core jako własne serwisy — sprzeczny z później zatwierdzonym ROS2-first. |
| [#20](https://github.com/autoklinika/Vision/pull/20) | Osobny Camera Service, zastąpiony oficjalnym DepthAI ROS 2 v3. |
| [#15](https://github.com/autoklinika/Vision/pull/15) | Jawne archiwum dużego snapshotu. Nie jest PR-em do scalenia. |
| [#18](https://github.com/autoklinika/Vision/pull/18) | Datowany raport starego stanu Stream Deck / UH720. Nowy zaakceptowany stan w VGP V1. |
| [#17](https://github.com/autoklinika/Vision/pull/17) | Historyczny pierwszy bring-up Luxonis; obecnie ROS2 driver działa. |
| [#10](https://github.com/autoklinika/Vision/pull/10) | Historyczny audyt protokołów Sony, nie aktualny tor fotografowania Vision. |
| [#9](https://github.com/autoklinika/Vision/pull/9) | Historyczne próby HDMI/Wi-Fi Sony, nie wdrożenie produkcyjne. |
| [#8](https://github.com/autoklinika/Vision/pull/8) | Historyczna dokumentacja Sony A6100A. |
| [#7](https://github.com/autoklinika/Vision/pull/7) | Historyczne testy sprzętu z 10.10, zachowane w archiwum. |
| [#6](https://github.com/autoklinika/Vision/pull/6) | Historyczny audyt STM32, CSI i CAN — nie jest aktualnym scenariuszem Vision. |
| [#1](https://github.com/autoklinika/Vision/pull/1) | Pierwszy raport VENTUNO z 10.10; nie scalać jako aktualnego stanu urządzenia. |

## Zachowane do dalszego przeglądu — nadal wymagają rebase/triage

| PR | Możliwe wykorzystanie po V1 |
|---|---|
| [#31](https://github.com/autoklinika/Vision/pull/31) | Niezależna kontrola danych RAW16 / replay — kandydat do małego PR od main. |
| [#26](https://github.com/autoklinika/Vision/pull/26), [#25](https://github.com/autoklinika/Vision/pull/25), [#24](https://github.com/autoklinika/Vision/pull/24), [#23](https://github.com/autoklinika/Vision/pull/23) | Algorytmy pomiaru głębi i optyki Luxonis. Wykorzystać selektywnie bez wznawiania starego Camera Service. |
| [#19](https://github.com/autoklinika/Vision/pull/19) | Podgląd przeglądarkowy DEV — możliwy jako niezależna funkcja HMI, nie główny driver. |
| [#13](https://github.com/autoklinika/Vision/pull/13), [#12](https://github.com/autoklinika/Vision/pull/12), [#11](https://github.com/autoklinika/Vision/pull/11) | Historyczne prototypy Sony; później ocenić pod kątem integracji migawki i przesyłu zdjęć. |
| [#4](https://github.com/autoklinika/Vision/pull/4), [#3](https://github.com/autoklinika/Vision/pull/3), [#2](https://github.com/autoklinika/Vision/pull/2) | Infrastruktura NVMe/remote MCP — oceniana oddzielnie od wizji i sterowania NERO. |

**Uwaga:** Z powodu stacked branches nie należy scalać PR #23–26 oraz #11–13 w przypadkowej kolejności. Ich nowa, użyteczna funkcjonalność powinna zostać przeniesiona przez ograniczone, niezależne zmiany od aktualnego main, po testach.

## Reguły archiwizacji i odtworzenia

- Zamknięcie PR nie kasuje jego gałęzi, diffu, dyskusji ani historii; nie usuwamy referencji Git.
- Wszystkie testy z dawnych PR zachowują status datowany (w tym dawne wyniki FAIL i PLAN-ONLY); nie zastępują potwierdzonego 23.11.2026 fizycznego VGP V1.
- Nikt nie powinien wykonywać starych skryptów ruchu na produkcyjnym CAN bez nowej, osobnej weryfikacji; archiwalny C8 i C9 nie są wykonawcami Vision.
