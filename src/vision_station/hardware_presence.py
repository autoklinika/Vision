"""Passive hardware enumeration; never open USB devices, CAN or ROS control."""
from pathlib import Path
import re
from types import MappingProxyType

# OAK USB waiting/booted/bootloader modes per the official USB deployment guide:
# https://docs.luxonis.com/hardware/platform/deploy/usb-deployment-guide
# Sony PC Remote/storage IDs confirmed in docs/hardware/SONY_A6100_VERIFICATION_2026-10-10.md
# and docs/architecture/ADR_SONY_STAGED_ACQUISITION_2026-10-13.md.
USB_IDS = MappingProxyType({
    "luxonis": frozenset({("03e7", "2485"), ("03e7", "f63b"), ("03e7", "f63c")}),
    "sony": frozenset({("054c", "0f0d"), ("054c", "0f0b")}),
})
_USB_DEVICE = re.compile(r"(?:usb[0-9]+|[0-9]+-[0-9]+(?:\.[0-9]+)*)", re.ASCII)
_HEX4 = re.compile(r"[0-9a-f]{4}", re.ASCII)


def valid_hardware_connection(device, value):
    """Only the explicitly supported observation classes; no readiness claim."""
    if value == "UNKNOWN":
        return True
    if device in USB_IDS:
        return value in ("USB_DETECTED", "USB_NOT_DETECTED")
    return device == "moveit" and value == "NOT_APPLICABLE"


def usb_hardware_connections(root=Path("/sys/bus/usb/devices")):
    """Report recognized USB enumeration only; no device opens or transfers.

    A complete readable USB inventory with a root hub is needed for a negative
    observation. A partial/racing/unavailable inventory cannot prove absence.
    An enumerated CAN adapter does not identify the NERO arm behind it.
    """
    result = {"luxonis": "UNKNOWN", "nero": "UNKNOWN",
              "moveit": "NOT_APPLICABLE", "sony": "UNKNOWN"}
    try:
        entries = [entry for entry in root.iterdir() if _USB_DEVICE.fullmatch(entry.name)]
        if len(entries) > 256:
            return result
        pairs = set()
        complete = True
        root_hub_seen = False
        for entry in entries:
            try:
                vendor = (entry / "idVendor").read_text(encoding="ascii").strip().lower()
                product = (entry / "idProduct").read_text(encoding="ascii").strip().lower()
                if not _HEX4.fullmatch(vendor) or not _HEX4.fullmatch(product):
                    complete = False
                    continue
                pairs.add((vendor, product))
                root_hub_seen |= entry.name.startswith("usb")
            except (OSError, UnicodeError):
                complete = False
        for device, ids in USB_IDS.items():
            if pairs & ids:
                result[device] = "USB_DETECTED"
            elif complete and root_hub_seen:
                result[device] = "USB_NOT_DETECTED"
    except OSError:
        pass
    return result
