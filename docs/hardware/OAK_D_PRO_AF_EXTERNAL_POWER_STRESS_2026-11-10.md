# Vision OAK-D Pro AF — external power stress test (2026-11-10)

**Environment:** VENTUNO Q Ubuntu 24.04.4 ARM64; Luxonis OAK-D-PRO-AF RVC2; DepthAI 3.12.0; YOLOv6 Nano RVC2.  
**Context:** Previously, AI + StereoDepth + 15% IR dot disconnected at USB3 (`X_LINK_ERROR`). Operator reported a separately powered USB hub and subsequently connected *independent camera power*. This power change is operator-reported; output voltage, current capability, voltage drop and Y-adapter hardware were **not electrically measured**.

## Important link-speed regression
- Earlier active sessions before separate camera power: `UsbSpeed.SUPER` / USB3; successful AI+StereoDepth at 14.9 Stereo FPS and 19.23 AI outputs/s, IR OFF.
- **After** camera power/wiring change: `UsbSpeed.HIGH` / USB2 (480 Mb/s) **even while firmware runs**; confirmed by both DepthAI and `lsusb -t` while pipeline was active, with active ID `03e7:f63b` on a 480 Mb/s tier.
- Hence the results below do **not** prove full USB3 bandwidth stability. Possible USB2-only data cable/Y adapter/wiring or SuperSpeed link problem; not proven which. Do not confuse with expected USB2 boot state after pipeline shutdown.
- Official Luxonis recommends 5V Y-adapter and 15W power for OAK Pro. See https://docs.luxonis.com/hardware/platform/deploy/usb-deployment-guide and https://docs.luxonis.com/hardware/products/Y-Adapter

## Test A — six configurations, AI + StereoDepth, separate camera power
- Script: `ir_stereo_ai_benchmark.py --ai --enable-ir --external-power-confirmed --duration 8 --warmup 1.5`.
- StereoDepth 1280x800; YOLOv6 Nano RVC2; dot/flood percentages as fractions of device intensity range.
- All six phases completed, `SHORT_STRESS_EXIT=0`; no X_LINK_ERROR; IR OFF confirmed on shutdown.

| IR mode | Stereo FPS | AI outputs/s | Full-frame valid depth % | Center valid % | Chip °C |
|---|---:|---:|---:|---:|---:|
| OFF initial | 12.12 | 12.12 | 23.80 | 39.63 | 40.6 |
| Dot 15% | 12.00 | 12.00 | 46.19 | 62.26 | 42.0 |
| Dot 30% | 12.12 | 12.00 | 49.09 | 66.94 | 42.8 |
| Flood 20% | 11.87 | 11.87 | 25.07 | 42.76 | 42.8 |
| Dot 20% + Flood 20% | 12.00 | 12.12 | 48.74 | 68.72 | 43.6 |
| OFF final | 12.00 | 11.87 | 24.50 | 41.08 | 44.6 |

*Valid depth means unsigned depth pixel in 1–4999 mm. Current scene is not a calibrated fixed target, so valid fraction is not metrological accuracy and differences are not necessarily attributable only to IR.*

## Test B — 180-second continuous load (AI + StereoDepth + IR dot 15%)
- Command: `ir_stereo_ai_benchmark.py --ai --enable-ir --external-power-confirmed --only-phase dot_15pct --duration 180 --warmup 2 --max-chip-temp 65`.
- Result `BENCHMARK_COMPLETE`, `SOAK_EXIT=0`; **no X_LINK_ERROR during the 180-second measurement**.
- 2226 StereoDepth output frames, effective **12.37 FPS**.
- 2269 AI output packets, effective **12.61 outputs/s**.
- 2250 detection outputs summed across frames (not unique objects).
- Full-frame valid depth **47.31%**, central ROI valid **65.84%**; center valid median **2364 mm**.
- Chip temperature: 44.9°C at 15 sec; 47.5°C at 60 sec; 49.9°C at 120 sec; 52.0°C at 165 sec; **52.6°C at 180 sec**. Temp was still increasing, not demonstrated to have reached equilibrium. Conservative script abort threshold 65°C did not trigger.
- `EMITTER_SHUTDOWN`, `DOT_OFF True`, `FLOOD_OFF True`. USB discovery post-test: `1 device / DISCOVERY_PASS`. Kernel USB disconnect at session end corresponds to normal firmware mode transition.
- The script tracks host-received packets; counts do not guarantee absence of internal skipped sensor frames or strict RGB/depth/NN timestamp synchronization.

## Comparison with previous incident
- Before separate camera power, an IR+AI run on **USB3** failed with `X_LINK_ERROR` and device reconnection.
- With new power/wiring the same features were stable during short and 180s runs, BUT speed reduced to **USB2**. Therefore one must **not claim power was proven to be root cause or that USB3+AI+IR is solved**.
- Temperature alone is not a reliable explanation for previous crash (prior recorded 44°C). Need separate electrical and USB3 link investigation.

## Safe next steps
1. Verify exact camera power adapter/Y-adapter and **USB3-capable data leg**; keep the new independent 5V power. Restore `UsbSpeed.SUPER` / 5000M on an active pipeline.
2. Repeat AI + StereoDepth + dot 15% at USB3 for >=180s with identical resolution/settings, monitor XLink and board temperature. Only after successful USB3 soak plan full feature/latency/temperature validation.
3. For geometric accuracy and IR optimization, retest using a static matte known-distance target under identical scene conditions; final overhead mounting requires calibration.
4. No merges to main, no robot actuation, no EEPROM or camera firmware changes.

## Artifacts on VENTUNO (NVMe only)
`/srv/vision-data/staging/oak-overhead-v0/IR_AI_EXTERNAL_POWER_SHORT_20261110.log`
`/srv/vision-data/staging/oak-overhead-v0/IR_AI_EXTERNAL_POWER_SOAK_20261110.log`
`/srv/vision-data/staging/oak-overhead-v0/ir_stereo_ai_benchmark.py`

Both logs contain only the test stream and telemetry; do not publish raw logs without checking for serial identifiers and other private metadata.
