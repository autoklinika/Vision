# Devices workspace — Luxonis V1

The approved navigation retains the Devices group with separate Luxonis, NERO
and Sony tabs. Luxonis is the first implemented device; NERO and Sony remain
placeholders. The LAB shell is unchanged. This is not an inspection workflow.

## Read-only architecture

- Core projects the configured OAK-D Pro AF model, passive USB enumeration,
  the observed camera graph, exact stream endpoints, selected allowlisted ROS
  parameters, and saved diagnostic configurations. Hardware enumeration alone
  does not establish that the driver is running or identify the specific serial.
- The optional observer discovers only /oak and /oak800 in local ROS domain 181
  and /oak in local domain 186. Multiple matching nodes or ambiguous topic
  publishers cannot yield a live preview. Graph identity is diagnostic, not an
  authenticated Runtime receipt.
- The observer uses the installed ROS Jazzy system Python and OpenCV. It lists
  parameters by known prefixes, then calls GetParameters only for supported
  names actually declared. It never creates SetParameters clients, opens USB,
  changes IR/focus/exposure, launches drivers, calls motion or planning services.
- Saved configuration values come from explicitly supplied existing YAML files,
  restricted to the same scalar allowlist. A value not present in the file is
  omitted; it is not treated as a default or current camera setting.
- RGB and depth are independently sampled from the exact existing image topics.
  Native stride, endian and encoding are checked. RGB is converted correctly
  to BGR for JPEG. Depth in 16UC1 (mm) or 32FC1 (m) is colorized using a fixed
  0–2000 mm scale; invalid pixels are black. This is a visual aid, not a depth
  measurement export. Display images are at most 640×480 and 40 KiB JPEG per
  stream. Source image dimensions, encoding and source timestamp are retained.
  The first target is a low-rate diagnostic preview, not full-rate video.
- The observer has no image subscriptions without a short viewer lease.
  A preview request renews a four-second lease in a private volatile directory.
  Image subscriptions are released after samples and after lease expiry. The
  browser only polls while Luxonis is selected, visible, authenticated and
  explicitly enabled by an operator on an idle Core. This does not authorize
  inspection or change physical device state. Preview is withheld during an
  active session in that Core. The independent DEV Core does not govern PROD
  inspection scheduling; physical commissioning must remain separate.
- The monitor snapshot is atomically replaced in a private 0700 tmpfs
  directory, owner-only 0600 files. It is never an image archive, repository
  artifact, inspection evidence or durable capture. Core validates the closed
  schema, parameter names, source, size and freshness; unavailable/stale data
  are not presented as live. Images expire after 2.5 seconds, parameter reads
  after 8 seconds and observer observations after 4 seconds.

## API and deployment

The normal same-UID Core IPC carries two fixed operations, luxonis and
luxonis_preview, with empty queries. Authenticated GET
/api/v1/devices/luxonis returns metadata without images. The exact
/api/v1/devices/luxonis/preview endpoint requires operator role and returns
the bounded preview report. Responses are no-store. The web process has no
access to ROS or the observer directory and cannot query arbitrary topics or
parameters. The Core owner must be explicitly configured with
--luxonis-directory; otherwise it truthfully reports monitor unavailable.

The optional observer is supervised separately from the hardware drivers.
Use an existing private volatile directory created by a service
RuntimeDirectory with mode 0700. Example observer arguments:

```sh
source /opt/ros/jazzy/setup.bash
export ROS_LOCALHOST_ONLY=1
export PYTHONPATH="<pinned-release>/src:${PYTHONPATH:-}"
/usr/bin/python3 -B -m vision_station.ros_luxonis \
  --directory "<private-tmpfs-directory>" \
  --rgbd-config "<existing-rgbd-yaml>" \
  --stereo-config "<existing-stereo-yaml>"
```

The optional observer uses the system ROS/OpenCV/PyYAML environment, not a
new dependency of the station API venv. DEV uses its own observer and Core
configuration, existing private preview access, no production socket or
library writes. Only the image source, when explicitly viewed, is real.
A coordinated Core/API/GUI release and separately approved physical camera
acceptance are required for production. No driver autostart or setting change
is part of this feature.

## Verification

Offline tests exercise JPEG encoding, RGB order, metric depth/endian/stride,
invalid/stale data, permissions and the actual authenticated HTTP/IPC boundary.
The explicit ROS test uses a synthetic publisher and parameter server in an
unused local domain 219, never a real camera topic in domain 181 or 186:

```sh
ROS_LOCALHOST_ONLY=1 PYTHONPATH=src /usr/bin/python3 -B tests/ros/test_luxonis_observer.py -v
```

The installed Jazzy Python callback MessageInfo does not expose publisher_gid;
the observer verifies the exact unique endpoint before and after a sample
in that environment. A separate physical live-stream acceptance and measured
preview throughput remain required.
