# Vision Station Calibration V1

W tym katalogu przechowujemy procedurę i kartę pomiarową, a w `config/vision_station_v1` szablony. Dane źródłowe i obrazy z nowej sesji są zapisywane na NVMe w `/srv/vision-data/calibration`. Projekt jest przygotowany, ale profil nie jest jeszcze zatwierdzony.

## Nowa sesja
```bash
python3 scripts/calibration/vision_station_profile.py prepare \
  --session 20261119-vision-station-v1
```

Sesja: `/srv/vision-data/calibration/sessions/20261119-vision-station-v1/`. Surowe obserwacje dopisywać do `measurements.csv`; obrazy do `captures/charuco` i `captures/depth`. Wypełnić `session.yaml`, `obstacles.yaml` i `sources.yaml`; progi dokładności ustalić **przed pomiarami**. Zakończyć walidację zgodnie z procedurą i utworzyć `validation/report.json` z wynikami `tf`, `camera`, `depth`, `tool`, `moveit_offline` oraz niezależnymi punktami kontrolnymi. Dopiero potem operator podpisuje `approval.yaml`.

## Blokada niezatwierdzonych wyników
```bash
python3 scripts/calibration/vision_station_profile.py freeze \
  --session-dir /srv/vision-data/calibration/sessions/20261119-vision-station-v1
```

Jeżeli brakuje wymaganych pomiarów, progów, testów lub podpisu, freeze zgłosi `REJECTED`; nie utworzy profilu. Po pomyślnej walidacji powstaje **niemodyfikowalna kopia** pod `/srv/vision-data/calibration/approved/<session_id>/` z manifestem SHA256. Sprawdzenie integralności:

```bash
python3 scripts/calibration/vision_station_profile.py verify \
  --approved-dir /srv/vision-data/calibration/approved/20261119-vision-station-v1
```

Nie aktywuje to TF, MoveIt ani CAN. Publikacja i aktywacja geometrycznych `static_transform_publisher` oraz PlanningScene powinna zostać wdrożona osobnym, przetestowanym `vision_station_bringup`, które dopuszcza wyłącznie zatwierdzony profil. Nie tworzyć produkcyjnej konfiguracji z kandydatów.

**Po każdorazowym uruchomieniu:** weryfikować hash profilu, fizyczny stan urządzeń, hamulców i J1–J7; nie kalibrować ponownie, jeśli nie zmieniono sprzętu lub konfiguracji. Zmiana narzędzia, pozycji podstawy/kamery, parametrów stereo/IR lub naruszenie mocowania powoduje rewizję odpowiedniego podprofilu.
