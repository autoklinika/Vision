#!/usr/bin/env python3
"""Vision BLE-06: temporary Stream Deck Plus encoder 1 -> Sony BLE zoom.

Default: input-only DRY RUN. --preflight and --self-test never move the lens.
Live mode requires --execute --ack-physical. In live mode: ONE WIDE and ONE
TELE pulse maximum (one per direction); no buffered rotation replay.
No USB PTP, pairing, scanning, settings changes, autostart or installations.
Linux HID/BlueZ adapters are for bench evaluation, not the portable Vision core.
"""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import subprocess
import sys
import time

ROOT = Path('/srv/vision-data/tools/streamdeck-eval')
HID = Path('/dev/hidraw0')
DEVICE_UEVENT = Path('/sys/class/hidraw/hidraw0/device/uevent')
CAMERA_ADDRESS = '<LOCAL_BLE_ADDRESS>'
SONY_SERVICE = '8000ff00-ff00-ffff-ffff-ffffffffffff'
SONY_WRITE = '0000ff01-0000-1000-8000-00805f9b34fb'
SONY_NOTIFY = '0000ff02-0000-1000-8000-00805f9b34fb'
COMMANDS = {
    'WIDE': (bytes.fromhex('02 47 10'), bytes.fromhex('02 46 00')),
    'TELE': (bytes.fromhex('02 45 10'), bytes.fromhex('02 44 00')),
}
PULSE_SECONDS = 0.65
COOLDOWN_SECONDS = 0.75
SESSION_SECONDS = 90
MAX_TOTAL_PULSES = 2
MAX_EACH_DIRECTION = 1


def now_utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def event_from_report(report):
    """Validated Elgato 0fd9:0084 encoder 1 input; no key/display writes."""
    if len(report) < 9 or report[:2] != b'\x01\x03' or report[2] != 5:
        return None
    if report[4] == 0 and report[5] != 0:
        return ('STOP', 0)  # Encoder-1 button is an input-side stop request
    if report[4] != 1:
        return None
    delta = int.from_bytes(report[5:6], 'little', signed=True)
    if delta < 0:
        return ('WIDE', delta)  # CCW = zoom out
    if delta > 0:
        return ('TELE', delta)  # CW = zoom in
    return None


def synthetic_tests():
    def report(kind, vals):
        return bytes([1, 3, 5, 0, kind, *vals])
    assert event_from_report(report(1, [255, 0, 0, 0])) == ('WIDE', -1)
    assert event_from_report(report(1, [1, 0, 0, 0])) == ('TELE', 1)
    assert event_from_report(report(1, [0, 255, 0, 0])) is None
    assert event_from_report(report(0, [1, 0, 0, 0])) == ('STOP', 0)
    assert event_from_report(report(0, [0, 0, 0, 0])) is None
    assert event_from_report(b'\x00\x03\x05\x00\x01\x01\x00\x00\x00') is None
    assert COMMANDS['WIDE'] == (b'\x02\x47\x10', b'\x02\x46\x00')
    assert COMMANDS['TELE'] == (b'\x02\x45\x10', b'\x02\x44\x00')
    print('BLE06_SYNTHETIC_TESTS=PASS; GATT_WRITES=0; HID_OPENS=0', flush=True)


def check_nvme_and_identity():
    if socket.gethostname() != 'vision':
        raise RuntimeError('WRONG_HOST')
    source = subprocess.check_output(
        ['findmnt', '-n', '-o', 'SOURCE', '-T', str(ROOT)],
        text=True, timeout=3).strip()
    if source != '/dev/nvme0n1p1':
        raise RuntimeError('NVME_WRITE_GUARD_FAILED: ' + source)
    ident = DEVICE_UEVENT.read_text()
    if 'HID_NAME=Elgato Stream Deck Plus' not in ident or '00000FD9:00000084' not in ident:
        raise RuntimeError('UNEXPECTED_STREAM_DECK_HID')
    if not os.access(HID, os.R_OK):
        raise RuntimeError('NO_HID_READ_PERMISSION')
    # Do not compete with an OpenDeck process for the same HID events.
    processes = subprocess.check_output(['ps', '-eo', 'comm='], text=True, timeout=3)
    if any(line.strip().lower() == 'opendeck' for line in processes.splitlines()):
        raise RuntimeError('OPENDECK_RUNNING_HID_CONFLICT')


def ensure_usb_absent():
    for vendor in Path('/sys/bus/usb/devices').glob('*/idVendor'):
        try:
            if vendor.read_text().strip().lower() == '054c':
                raise RuntimeError('SONY_USB_PRESENT_ABORT')
        except FileNotFoundError:
            continue


def dbus_plain(v):
    if isinstance(v, dict):
        return {str(k): dbus_plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [dbus_plain(x) for x in v]
    return str(v) if hasattr(v, 'signature') else v


def discover_sony():
    import dbus
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object('org.bluez', '/'),
                             'org.freedesktop.DBus.ObjectManager')
    objects = manager.GetManagedObjects(timeout=3)
    matches = [(str(path), props['org.bluez.Device1']) for path, props in objects.items()
               if 'org.bluez.Device1' in props and
               str(props['org.bluez.Device1'].get('Address')) == CAMERA_ADDRESS]
    if len(matches) != 1:
        raise RuntimeError('SONY_BLE_DEVICE_NOT_UNIQUE')
    device_path, state = matches[0]
    if str(state.get('Name')) != 'ILCE-6100A':
        raise RuntimeError('SONY_IDENTITY_MISMATCH')
    for key in ('Paired', 'Bonded', 'Connected', 'ServicesResolved'):
        if not bool(state.get(key, False)):
            raise RuntimeError('BLE_NOT_READY_'+key)
    if bool(state.get('Blocked', False)):
        raise RuntimeError('SONY_BLE_BLOCKED')
    service_paths = [str(path) for path, p in objects.items()
                     if 'org.bluez.GattService1' in p
                     and str(p['org.bluez.GattService1'].get('Device')) == device_path
                     and str(p['org.bluez.GattService1'].get('UUID')).lower() == SONY_SERVICE]
    if len(service_paths) != 1:
        raise RuntimeError('SONY_REMOTE_GATT_SERVICE_UNAVAILABLE')
    chars = {str(p['org.bluez.GattCharacteristic1'].get('UUID')).lower():
             (str(path), p['org.bluez.GattCharacteristic1'])
             for path, p in objects.items() if 'org.bluez.GattCharacteristic1' in p
             and str(p['org.bluez.GattCharacteristic1'].get('Service')) == service_paths[0]}
    if SONY_WRITE not in chars or 'write' not in chars[SONY_WRITE][1].get('Flags', []):
        raise RuntimeError('SONY_REMOTE_GATT_WRITE_UNAVAILABLE')
    if SONY_NOTIFY not in chars or 'notify' not in chars[SONY_NOTIFY][1].get('Flags', []):
        raise RuntimeError('SONY_REMOTE_GATT_NOTIFY_UNAVAILABLE')
    return bus, device_path, chars[SONY_WRITE][0]


def send_gatt(interface, data, label):
    import dbus
    item = {'label': label, 'hex': data.hex(' '), 'utc': now_utc()}
    started = time.monotonic()
    try:
        interface.WriteValue(
            dbus.Array(data, signature='y'),
            dbus.Dictionary({'type': dbus.String('request')}, signature='sv'),
            timeout=2.0)
        item['success'] = True
    except BaseException as exc:
        item['success'] = False
        item['error'] = repr(exc)
    item['elapsed_s'] = round(time.monotonic() - started, 4)
    return item


def pulse_safely(interface, direction, emit):
    """Single bounded pulse; no PRESS retry, RELEASE tried on every exit path."""
    ensure_usb_absent()
    press, release = COMMANDS[direction]
    entry = {'direction': direction, 'utc': now_utc(), 'pulse_ms': int(PULSE_SECONDS*1000),
             'writes': []}
    press_result = None
    release_result = None
    old_term = signal.getsignal(signal.SIGTERM)
    old_int = signal.getsignal(signal.SIGINT)
    try:
        emit('PRESS='+direction+' '+press.hex(' '))
        press_result = send_gatt(interface, press, direction+'_PRESS')
        entry['writes'].append(press_result)
        emit('PRESS_RESULT='+json.dumps(press_result))
        if not press_result['success']:
            raise RuntimeError('GATT_PRESS_UNCONFIRMED')
        time.sleep(PULSE_SECONDS)
    except BaseException as exc:
        entry['error'] = repr(exc)
    finally:
        # Protect the release section from ordinary SIGINT/SIGTERM.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            release_result = send_gatt(interface, release, direction+'_RELEASE')
            entry['writes'].append(release_result)
            emit('RELEASE_RESULT='+json.dumps(release_result))
            if not release_result['success']:
                retry = send_gatt(interface, release, direction+'_RELEASE_SAFETY_RETRY')
                entry['writes'].append(retry)
                release_result = retry
                emit('RELEASE_RETRY='+json.dumps(retry))
        finally:
            signal.signal(signal.SIGTERM, old_term)
            signal.signal(signal.SIGINT, old_int)
    entry['transport_result'] = ('PASS' if press_result and press_result['success']
                                 and release_result and release_result['success']
                                 and 'error' not in entry else 'FAIL_OR_PARTIAL')
    if entry['transport_result'] != 'PASS':
        raise RuntimeError('PULSE_OR_RELEASE_FAILED '+json.dumps(entry))
    return entry


def run(args):
    import dbus
    check_nvme_and_identity()
    ensure_usb_absent()
    bus, _, char_path = discover_sony()
    interface = dbus.Interface(bus.get_object('org.bluez', char_path),
                               'org.bluez.GattCharacteristic1')
    print('BLE06_PREFLIGHT=PASS', flush=True)
    print('HID='+str(HID)+' CAMERA='+CAMERA_ADDRESS+' WRITE='+char_path, flush=True)
    print('ENCODER_1_LEFT=WIDE; RIGHT=TELE; PULSE_MS=650', flush=True)
    print('USB_ABSENT=YES; AUTO_PAIR=NO; AUTO_CONNECT=NO', flush=True)
    if args.preflight:
        print('PREFLIGHT_ONLY=PASS; HID_NOT_OPENED; GATT_WRITES=0', flush=True)
        return 0
    mode = 'EXECUTE' if args.execute else 'INPUT_DRY_RUN'
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report_path = ROOT / ('BLE06_ENCODER_'+mode+'_'+stamp+'.json')
    log_path = report_path.with_suffix('.log')
    record = {'test': 'BLE-06', 'mode': mode, 'started_utc': now_utc(),
              'camera': CAMERA_ADDRESS, 'hid': str(HID),
              'mappings': {'CCW':'WIDE', 'CW':'TELE'},
              'max_pulses': 2, 'max_each_direction': 1,
              'pulse_ms': 650, 'time_limit_seconds': SESSION_SECONDS,
              'usb_present': False, 'events': [], 'pulses': [],
              'optical_result': 'NOT_YET_OBSERVED'}
    logfile = log_path.open('x', buffering=1)
    def emit(message):
        line = now_utc()+' '+message
        print(line, flush=True)
        logfile.write(line+'\n')
    fd = None
    selector = selectors.DefaultSelector()
    locker = None
    direction_done = set()
    cooldown_until = 0.0
    stop_reason = 'TIMEOUT'
    def interrupted(signum, _frame):
        raise InterruptedError('SIGNAL_'+str(signum))
    old_int = signal.signal(signal.SIGINT, interrupted)
    old_term = signal.signal(signal.SIGTERM, interrupted)
    try:
        locker = (ROOT/'sony-ble-one-shot.lock').open('a')
        fcntl.flock(locker, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd = os.open(str(HID), os.O_RDONLY | os.O_NONBLOCK)
        selector.register(fd, selectors.EVENT_READ)
        # Initial input buffer flushed before arming. Do not replay old ticks.
        warm_until = time.monotonic()+0.6
        while time.monotonic() < warm_until:
            for _, _ in selector.select(timeout=0.05):
                try:
                    os.read(fd, 512)
                except BlockingIOError:
                    pass
        deadline = time.monotonic()+SESSION_SECONDS
        emit('ARMED=YES; MAX_ONE_WIDE_ONE_TELE; PRESS_ENCODER1_TO_STOP')
        emit('MODE='+mode+'; NO_BUFFERED_ROTATION_REPLAY')
        while time.monotonic() < deadline:
            for _, _ in selector.select(timeout=0.15):
                try:
                    report = os.read(fd, 512)
                except BlockingIOError:
                    continue
                if not report:
                    raise RuntimeError('STREAM_DECK_DISCONNECTED')
                event = event_from_report(report)
                if event is None:
                    continue
                direction, ticks = event
                if direction == 'STOP':
                    stop_reason = 'ENCODER1_PUSH_STOP'
                    emit('STOP_REQUEST=ENCODER1_PUSH')
                    break
                now = time.monotonic()
                if now < cooldown_until or direction in direction_done:
                    continue
                # No queued pulses or direction repeats. Explicit max 2 pulses.
                if len(direction_done) >= MAX_TOTAL_PULSES:
                    break
                ensure_usb_absent()
                _, _, current_write_path = discover_sony()
                if current_write_path != char_path:
                    raise RuntimeError('GATT_PATH_CHANGED_ABORT')
                direction_done.add(direction)  # prevent replay after exceptions
                record['events'].append({'utc':now_utc(), 'direction':direction, 'ticks':ticks})
                emit('ENCODER_1='+('CCW' if direction=='WIDE' else 'CW')+
                     ' -> '+direction+' ticks='+str(ticks))
                if args.execute:
                    result = pulse_safely(interface, direction, emit)
                    record['pulses'].append(result)
                else:
                    emit('DRY_RUN_NO_GATT_WRITE='+direction)
                cooldown_until = time.monotonic()+COOLDOWN_SECONDS
                # Discard all queued encoder reports after a pulse while cooling down.
                # This prevents an older, delayed opposite-direction tick from replay.
                while time.monotonic() < cooldown_until:
                    for _, _ in selector.select(timeout=0.04):
                        try:
                            pending = os.read(fd, 512)
                        except BlockingIOError:
                            continue
                        if not pending:
                            raise RuntimeError('STREAM_DECK_DISCONNECTED')
                        if event_from_report(pending) == ('STOP', 0):
                            stop_reason = 'ENCODER1_PUSH_STOP'
                            emit('STOP_REQUEST=ENCODER1_PUSH_DURING_COOLDOWN')
                            break
                    if stop_reason == 'ENCODER1_PUSH_STOP':
                        break
                if stop_reason == 'ENCODER1_PUSH_STOP':
                    break
                if len(direction_done) >= MAX_TOTAL_PULSES:
                    stop_reason = 'MAX_TWO_DIRECTIONS_REACHED'
                    break
                emit('READY_FOR_NEXT_DIRECTION_AFTER_COOLDOWN')
            if stop_reason in ('ENCODER1_PUSH_STOP', 'MAX_TWO_DIRECTIONS_REACHED'):
                break
        emit('STOP_REASON='+stop_reason)
        record['stop_reason'] = stop_reason
        record['transport_result'] = 'PASS' if (not args.execute or all(
            row.get('transport_result')=='PASS' for row in record['pulses'])) else 'FAIL'
        return 0
    except BaseException as exc:
        record['error'] = repr(exc)
        record['stop_reason'] = 'ERROR_OR_INTERRUPTION'
        emit('STOP_ERROR='+repr(exc))
        return 2
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
        selector.close()
        if fd is not None:
            os.close(fd)
        if locker is not None:
            locker.close()
        record['completed_utc'] = now_utc()
        report_path.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
        emit('RESULT_JSON='+str(report_path))
        emit('RESULT_LOG='+str(log_path))
        emit('HID_CLOSED=YES; SESSION_ENDED=YES')
        logfile.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group()
    g.add_argument('--self-test', action='store_true', help='synthetic report parser tests, no devices')
    g.add_argument('--preflight', action='store_true', help='read-only host, Sony GATT, USB checks')
    g.add_argument('--execute', action='store_true', help='two physical pulses maximum, one per direction')
    parser.add_argument('--ack-physical', action='store_true', help='explicitly acknowledge motor movement')
    args = parser.parse_args()
    if args.execute and not args.ack_physical:
        parser.error('--execute requires --ack-physical')
    if args.ack_physical and not args.execute:
        parser.error('--ack-physical only with --execute')
    if args.self_test:
        synthetic_tests()
        return 0
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
