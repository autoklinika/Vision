# Kod aplikacji Vision (plan)

Katalog modułów jest rezerwowany do kolejnych etapów. **Nie ma jeszcze wdrożonego runtime ani potwierdzonego doboru języka/frameworka.**

- `acquisition/` — urządzenia kamerowe, oryginały, metadane.
- `quality/` — ocena ostrości, ekspozycji i poprawności pokrycia.
- `registration/` — transformacje i kalibracje geometryczne.
- `mosaic/` — łączenie pól widzenia.
- `focus_stack/` — fuzja ujęć na różnych głębokościach.
- `thermal/` — dane radiometryczne i rejestracja względem RGB.
- `robot/` — interfejs pozycji i trajektorii ze sprzętowymi zabezpieczeniami.
- `export/` — wersjonowane pakiety danych do analizy na AI Platform.

Interfejsy niezależne od producenta; biblioteki OpenCV, libgphoto2, QNN i sterowniki robotyczne podłączamy dopiero po weryfikacji zgodności.
