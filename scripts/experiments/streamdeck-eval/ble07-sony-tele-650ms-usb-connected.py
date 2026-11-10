#!/usr/bin/env python3
"""BLE-07: approved, one-shot TELE with USB physically connected; defaults to read-only dry-run.
No connect, pair, scan, configuration changes, shutter, or repeated PRESS.
Source: https://github.com/coral/freemote (RemoteCommand table).
RELEASE is best effort if the radio/device fails; observe the lens locally.
"""
import argparse
import datetime as dt
import fcntl
import json
import pathlib
import signal
import socket
import subprocess
import sys
import time
import dbus

ROOT = pathlib.Path('/srv/vision-data/tools/streamdeck-eval')
CAMERA = '<LOCAL_BLE_ADDRESS>'
SERVICE = '8000ff00-ff00-ffff-ffff-ffffffffffff'
WRITE = '0000ff01-0000-1000-8000-00805f9b34fb'
NOTIFY = '0000ff02-0000-1000-8000-00805f9b34fb'
PRESS = bytes.fromhex('02 45 10')
RELEASE = bytes.fromhex('02 44 00')
PULSE_SECONDS = 0.65


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def plain(value):
    if isinstance(value, dbus.Boolean):
        return bool(value)
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, (str, dbus.ObjectPath)):
        return str(value)
    return value


def discover():
    bus = dbus.SystemBus()
    objects = dbus.Interface(bus.get_object('org.bluez', '/'),
                            'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=3)
    devices = [(str(p), q['org.bluez.Device1']) for p, q in objects.items()
               if 'org.bluez.Device1' in q and str(q['org.bluez.Device1'].get('Address')) == CAMERA]
    if len(devices) != 1:
        raise RuntimeError('TARGET_NOT_UNIQUE')
    device_path, state = devices[0]
    if str(state.get('Name')) != 'ILCE-6100A':
        raise RuntimeError('TARGET_NAME_MISMATCH')
    for key in ('Paired', 'Bonded', 'Connected', 'ServicesResolved'):
        if not bool(state.get(key, False)):
            raise RuntimeError('REQUIRES_APPROVAL_OR_DIAGNOSIS: ' + key + '=false')
    if bool(state.get('Blocked', False)):
        raise RuntimeError('DEVICE_BLOCKED')
    services = [str(p) for p, q in objects.items() if 'org.bluez.GattService1' in q
                and str(q['org.bluez.GattService1'].get('Device')) == device_path
                and str(q['org.bluez.GattService1'].get('UUID')).lower() == SERVICE]
    if len(services) != 1:
        raise RuntimeError('REMOTE_SERVICE_NOT_UNIQUE')
    chars = {str(q['org.bluez.GattCharacteristic1'].get('UUID')).lower():
             (str(p), q['org.bluez.GattCharacteristic1']) for p, q in objects.items()
             if 'org.bluez.GattCharacteristic1' in q
             and str(q['org.bluez.GattCharacteristic1'].get('Service')) == services[0]}
    if WRITE not in chars or 'write' not in chars[WRITE][1].get('Flags', []):
        raise RuntimeError('WRITE_NOT_AVAILABLE')
    if NOTIFY not in chars or 'notify' not in chars[NOTIFY][1].get('Flags', []):
        raise RuntimeError('NOTIFY_NOT_AVAILABLE')
    state = {k: plain(state.get(k)) for k in
             ('Name', 'Address', 'Paired', 'Bonded', 'Trusted', 'Blocked', 'Connected', 'ServicesResolved')}
    return bus, device_path, chars[WRITE][0], state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if socket.gethostname() != 'vision':
        raise RuntimeError('WRONG_HOST')
    source = subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '-T', str(ROOT)],
                                     text=True, timeout=3).strip()
    if source != '/dev/nvme0n1p1':
        raise RuntimeError('NVME_GUARD_FAILED')
    # BLE-07 requires USB to be physically attached; no PTP call here.
    usb = []
    for vendor_file in pathlib.Path('/sys/bus/usb/devices').glob('*/idVendor'):
        try:
            if vendor_file.read_text().strip().lower() == '054c':
                if (vendor_file.parent/'idProduct').read_text().strip().lower() != '0f0d':
                    raise RuntimeError('OTHER_SONY_USB_DEVICE_PRESENT_ABORT')
                usb.append(str(vendor_file.parent))
        except FileNotFoundError:
            continue
    if len(usb) != 1:
        raise RuntimeError('EXPECTED_EXACTLY_ONE_SONY_ILCE6100_USB; found=' + str(usb))
    bus, device_path, char_path, state = discover()
    print('USB_CONNECTED_CHECK=PASS Sony_054c_0f0d; PTP_OPEN=NO', flush=True)
    print('PREFLIGHT=PASS; STATE=' + json.dumps(state), flush=True)
    print('WRITE_PATH=' + char_path, flush=True)
    print('TELE_PRESS=02 45 10; TELE_RELEASE=02 44 00; HOLD_MS=650', flush=True)
    if not args.execute:
        print('DRY_RUN=PASS; GATT_WRITES=0; NO_LENS_COMMANDS', flush=True)
        return 0
    lock = (ROOT / 'sony-ble-one-shot.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    marker = ROOT / 'ble07-sony-tele-650ms-usb-connected.execution-started'
    with marker.open('x') as f:
        f.write(utc() + '\nSingle authorization consumed; do not rerun this test.\n')
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report_path = ROOT / ('BLE07_TELE_USB_CONNECTED_' + stamp + '.json')
    log_path = ROOT / ('BLE07_TELE_USB_CONNECTED_' + stamp + '.log')
    log = log_path.open('x', buffering=1)
    record = dict(test='BLE-07_TELE_USB_CONNECTED', started_utc=utc(), camera=CAMERA, before=state,
                  write_path=char_path, press_hex=PRESS.hex(' '), release_hex=RELEASE.hex(' '),
                  pulse_ms=650, protocol_source='https://github.com/coral/freemote',
                  physical_movement='AWAITING_USER_CONFIRMATION', writes=[])
    with report_path.open('x') as f:
        json.dump(record, f, indent=2)
    interface = dbus.Interface(bus.get_object('org.bluez', char_path), 'org.bluez.GattCharacteristic1')

    def emit(text):
        line = utc() + ' ' + text
        print(line, flush=True)
        log.write(line + '\n')

    def write(payload, label):
        entry = dict(label=label, hex=payload.hex(' '), started_utc=utc())
        record['writes'].append(entry)
        start = time.monotonic()
        try:
            interface.WriteValue(dbus.Array(payload, signature='y'),
                                 dbus.Dictionary({'type': dbus.String('request')}, signature='sv'),
                                 timeout=2.0)
            entry['success'] = True
        except BaseException as exc:
            entry['success'] = False
            entry['error'] = repr(exc)
        entry['duration_s'] = round(time.monotonic() - start, 6)
        return entry

    def interrupted(sig, _frame):
        raise InterruptedError('SIGNAL_' + str(sig))

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    press = None
    release = None
    try:
        emit('EXECUTE_ONCE=TELE_USB_CONNECTED; NO_PRESS_RETRY')
        press = write(PRESS, 'TELE_PRESS')
        emit('PRESS_RESULT=' + json.dumps(press))
        if not press['success']:
            raise RuntimeError('PRESS_NOT_CONFIRMED')
        hold_start = time.monotonic()
        deadline = hold_start + PULSE_SECONDS
        while time.monotonic() < deadline:
            time.sleep(max(0.0, deadline - time.monotonic()))
        record['hold_after_press_ack_s'] = round(time.monotonic() - hold_start, 6)
    except BaseException as exc:
        record['error'] = repr(exc)
    finally:
        # Do not allow a second termination signal to interrupt safety release.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        release = write(RELEASE, 'TELE_RELEASE')
        if not release['success']:
            # Only RELEASE may be retried, once, with a bounded D-Bus timeout.
            retry = write(RELEASE, 'TELE_RELEASE_SAFETY_RETRY')
            record['release_retry'] = retry
        record['completed_utc'] = utc()
        record['transport_result'] = ('PASS' if press and press['success']
                                      and release['success'] and 'error' not in record else 'FAIL_OR_PARTIAL')
        try:
            properties = dbus.Interface(bus.get_object('org.bluez', device_path),
                                        'org.freedesktop.DBus.Properties')
            after = properties.GetAll('org.bluez.Device1', timeout=2)
            record['after'] = {k: plain(after.get(k)) for k in
                              ('Paired', 'Bonded', 'Connected', 'ServicesResolved')}
        except BaseException as exc:
            record['after_error'] = repr(exc)
        report_path.write_text(json.dumps(record, indent=2) + '\n')
        emit('RELEASE_RESULT=' + json.dumps(release))
        emit('TRANSPORT_RESULT=' + record['transport_result'])
        emit('PHYSICAL_MOVEMENT=AWAITING_USER_CONFIRMATION')
        emit('AFTER=' + json.dumps(record.get('after', {})))
        emit('REPORT_JSON=' + str(report_path))
        emit('REPORT_LOG=' + str(log_path))
        log.close()
        lock.close()
    return 0 if record['transport_result'] == 'PASS' else 2


if __name__ == '__main__':
    sys.exit(main())
