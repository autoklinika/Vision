# Vision — biblioteka profili, wybór ECU i edytor wzorca (UX V1)

**Status:** ACCEPTED jako kierunek projektowy interakcji; szczegóły ekranów stanowią wymagania do następnego etapu GUI, bez implementacji w tej zmianie.

## Wybór ECU po uruchomieniu Vision

```text
VISION START
    ↓
KATALOG ECU (wyszukiwanie producenta/rodziny/wariantu, miniatury, wersje)
    ↓ operator wybiera konkretny wariant, rewizję, stan fizyczny i recepturę inspekcji
PODGLĄD PROFILU (zdjęcia, bryła, złącza, plan ujęć, wymagania)
    ↓ walidacja katalogu, zatwierdzenia, assetów, stanów i capabilities
LUXONIS / ROS 2 — aktywna obserwacja ECU (RGB-D, Depth, TF, cechy)
    ↓
S04: MATCHED / MISMATCHED / AMBIGUOUS / INSUFFICIENT_EVIDENCE
    ├─ MISMATCHED, AMBIGUOUS, NOT_READY → BLOKADA I DECYZJA OPERATORA
    └─ MATCHED → S05 przygotowanie ujęć, dalej zwykłe bramki Core
```

**Wyjątek:** obiekty oznaczone DRAFT są widoczne w katalogu tylko do wglądu i edycji. Ekran nie pokazuje dla nich przycisku uruchomienia niezatwierdzonej receptury.

## Edytor ECU Reference Profile

Edytor prezentuje 15 sekcji specyfikacji z walidacją zależną od stanu fizycznego i wybranego rodzaju inspekcji. Dla każdej wartości: źródło, jednostka, datum, niepewność, data, autor pomiaru i stan weryfikacji. Osobno obsługujemy źródła obrazów i modeli z kontrolowanego Asset Store oraz manifest SHA-256.

Przepływ autora: wybór DRAFT → uzupełnianie → podgląd braków → REVIEW_READY → niezależny przegląd → APPROVED dla określonych zakresów. Zatwierdzenie jest powiązane z hashami; późniejsza poprawka tworzy nową rewizję. UI pokazuje pełną historię i nie pozwala edytować zatwierdzonej rewizji w miejscu.

## Karta badanego egzemplarza

**Nie należy mylić dwóch ekranów:**

- *Edytor profilu wzorcowego* buduje wiedzę wspólną dla rodziny/wariantu ECU.
- *Formularz badanego egzemplarza* zapisuje wyniki obserwacji i sesji konkretnej sztuki; nie modyfikuje automatycznie profilu wzorcowego.

Uzupełnienie z rzeczywistego egzemplarza może być zaproponowaną nową rewizją profilu, ale wymaga oddzielnego przeglądu i zatwierdzenia.

## Kryteria UX

System wyświetla powód odmowy, wykryte i niewykryte cechy, możliwe alternatywne warianty, źródła referencyjnych zdjęć i status kompletności dla wybranej receptury. Operator nie musi znać numerycznych współrzędnych stołu ani przegubów robota. Brak danych, stara obserwacja lub niezgodność wariantu nie uruchamiają ruchu. Nie przewiduje się własnego sterowania ramieniem w bibliotece.
