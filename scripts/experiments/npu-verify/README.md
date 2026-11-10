# VENTUNO Q: izolowany test NPU HTP

Data testu: 2026-10-10

Wynik: **PASS_STRICT_HTP** — model ONNX Conv+ReLU uruchomiony przez QNNExecutionProvider na Hexagon HTP, z wyłączonym CPU fallback. Profil ORT: 1 uruchomienie węzła QNN, 0 uruchomień węzłów CPU. Maksymalny błąd wobec CPU: 0.000489.

## Reprodukcja

```bash
bash /srv/vision-data/tools/npu-verify/run_htp.sh
```

Powyższy skrypt ponawia inferencję na NPU i generuje pliki profilu w katalogu `logs/`. Nie wymaga sudo i nie instaluje pakietów.

## Wersje i pochodzenie

- Ubuntu 24.04 / Python 3.12
- ONNX Runtime QNN 1.23.0, wheel udostępniony w oficjalnym poradniku Arduino: https://docs.arduino.cc/tutorials/ventuno-q/onnx-runtime/
- QAIRT 2.46.0, pakiety `qairt-libs` i `qairt-dsp-binaries` z Ubuntu Qualcomm IoT PPA, rozpakowane przez `dpkg-deb -x`, a nie instalowane.
- Python pip uruchomiony z pakietu Ubuntu `python3-pip-whl`, bez `python3-venv` i bez systemowej instalacji.
- Dodatkowe zależności Pythona zainstalowane tylko w `.venv`.
- Dowiązanie `pkgroot/usr/lib/libcdsprpc.so` do fabrycznej biblioteki systemowej `libcdsprpc.so.1`; brak zmian w `/usr/lib`.
- Test i logi: `verify_htp.py`, `models/tiny_conv_relu.onnx`, `logs/verify_htp_run2.txt`, `logs/qnn_htp_profile.csv`, `logs/ort_qnn_strict_*.json`.

## Ograniczenia

To test poprawnego oddelegowania obliczeń, nie benchmark TOPS, wydajności czy stabilności termicznej. GPU/DRM może emitować niezwiązane ostrzeżenie o braku sysfs `vendor`; nie zatrzymuje ono testu HTP.
