# Luxonis permanent camera service V1

Owner approval: automatic camera startup with VENTUNO, independently of the
GUI, inspection manager, NERO and MoveIt. This is a device lifecycle service,
not an operational inspection or a second camera implementation.

## Service contract

- User unit: `vision-luxonis.service`, enabled in `default.target` on the
  VENTUNO station user whose linger is already enabled. No desktop login is
  required. All program, configuration and ROS logs live on NVMe.
- Stable launcher: `/srv/vision-data/tools/vision-luxonis/vision_luxonis_supervisor.py`.
  Install the exact reviewed source from `scripts/deploy`. Install the unit
  in the local user systemd directory, not as a symlink into a development
  worktree. Keep the private camera configuration in
  `/srv/vision-data/config/luxonis/rgbd.yaml`.
- Owner decision, 2026-11-26: the default boot profile is restored from the
  frozen Vision Guided Positioning V1 baseline of 2026-11-23,
  `fixed/camera/luxonis_rgb1080_stereo800_ros2.yaml`. Its source manifest
  checksum was verified and the installed profile is a byte-identical copy.
  Do not silently return to the earlier 640x400 diagnostic profile.
  RGB is configured to 1920x1080, stereo output parameters to 1280x800,
  both at 15 FPS, FAST_ACCURACY, no NN and no automatic calibration.
  The later manual IR feature enables the driver capability but sets both
  emitter intensities to zero at startup (see VISION_LUXONIS_IR_V1.md). The live source topics were both verified at 1920x1080
  (depth aligned to RGB, 16UC1). The driver reports left/right settings
  of 640x400; this profile is not proof of native 800p stereo acquisition.
  Subpixel and left-right check are enabled; extended disparity is disabled.
  GUI previews remain reduced independently of source images.
  Do not copy station-private configuration into the repository.
- Historical regression audit of 2026-11-17 established that the earlier
  400p diagnostic pipeline was unsuitable for the 34 mm reference:
  23.842 mm versus 33.401 mm in the isolated native 800p stereo-only test
  using the same top-surface estimator. The simultaneous unaligned RGB
  1080p/native 800p candidate of that date did not pass measurement QA.
  The later VGP baseline is a different aligned RGB-D profile accepted for
  guided positioning, not a certification of metrological accuracy.
  Native 800p measurement qualification must not be inferred from the
  aligned 1920x1080 output or configured stereo dimensions. Preserve
  the frozen baseline, and do not change calibration, TF, robot or MoveIt
  based on this resolution-only camera service deployment.
- Keep ROS domain 186 and localhost-only discovery. The future operational
  Runtime domain and camera-to-station transform are separate acceptance tasks.
- Start only after checking that NVMe is mounted and exactly one recognized
  OAK USB device is present. No USB reset or SDK access by the supervisor.
  Refuse a second camera node discovered in the configured local domain.
- The official installed DepthAI ROS v3 launch remains the sole camera driver.
  The supervisor samples each raw stream in brief best-effort windows every
  ten seconds, retaining only advancing source timestamps. It does not store
  images or depend on GUI preview interest, valid scene depth, NERO, or Core.
- Allow sixty seconds for initialization; after this grace, if the last
  advancing sample of either stream is older than thirty seconds (or is
  absent), or the launch exits, stop the owned launch
  process group and let systemd restart after fifteen seconds. If USB is
  absent, wait for re-enumeration before opening another driver. These bounds
  are policy choices, not measurements of actual reconnect latency.
- `Conflicts` and `After` serialize ownership with the old camera service,
  temporary preview owner and two legacy scene launches. An explicit start of
  a conflicting legacy unit switches ownership and stops the standalone unit;
  do not use that as an automatic production scene integration. No robot or
  planning unit is a dependency of the new service. Arbitrary manual drivers
  outside the known systemd owners remain prohibited.
- The diagnostic System Status recognizes standalone service liveness but does
  not reuse domain-181 camera observations to assert domain-186 readiness.
  Luxonis tab reads the actual local domain-186 node, parameters and previews.

## Station commands

Run in the station user's systemd manager (no sudo required):
```sh
systemctl --user status vision-luxonis.service
systemctl --user is-enabled vision-luxonis.service
systemctl --user restart vision-luxonis.service
systemctl --user stop vision-luxonis.service
journalctl --user -u vision-luxonis.service -n 40 --no-pager
```

Install and validate the service before enabling it. Back up the previous
owner definition/configuration; stop the temporary owner before launching the
permanent one. Verify the two real image streams and automatic recovery after
an intentional camera-only main-process termination. Do not reboot VENTUNO or
disconnect USB remotely to test boot/reconnect. Offline tests cover watchdog
deadlines, advancing timestamps, absent USB and accepted USB re-enumeration.
Full cold-boot and physical unplug/replug acceptance remain separate.
