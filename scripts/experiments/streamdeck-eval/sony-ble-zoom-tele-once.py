#!/usr/bin/env python3
"""One-shot experimental TELE BLE test, Sony ILCE-6100A + VENTUNO Q.
This script defaults to dry-run. Only --execute sends GATT writes.
Sony camera lens motor may move. Never run unattended.
Freemote Sony BLE protocol: 02 45 10 = Zoom Tele Press (slowest);
02 44 00 = Zoom Tele Release. No shutter command.
"""
import argparse, datetime, json, pathlib, re, signal, subprocess, sys, time
ROOT=pathlib.Path('/srv/vision-data/tools/streamdeck-eval')
CAMERA='<LOCAL_BLE_ADDRESS>'
GATT='/org/bluez/hci0/dev_<LOCAL_BLE_ADDRESS>/service0036/char003a'
EXPECTED='0000ff01-0000-1000-8000-00805f9b34fb'
PRESS=(2,0x45,0x10)
RELEASE=(2,0x44,0x00)
PULSE_SECONDS=0.16

def call(args,timeout=4):
    return subprocess.run(args,text=True,capture_output=True,timeout=timeout)

def check():
    info=call(['bluetoothctl','info',CAMERA])
    if info.returncode or not re.search(r'^\s*Name:\s*ILCE-6100A\s*$',info.stdout,re.M):
        raise RuntimeError('TARGET_NOT_CONFIRMED_ILCE_6100A')
    for field in ('Connected: yes','Paired: yes','Bonded: yes'):
        if field not in info.stdout:raise RuntimeError('BLE_STATE_INVALID: '+field)
    uuid=call(['busctl','--system','get-property','org.bluez',GATT,'org.bluez.GattCharacteristic1','UUID'])
    if uuid.returncode or EXPECTED not in uuid.stdout:
        raise RuntimeError('UNEXPECTED_GATT_CHARACTERISTIC')
    flags=call(['busctl','--system','get-property','org.bluez',GATT,'org.bluez.GattCharacteristic1','Flags'])
    if flags.returncode or '"write"' not in flags.stdout:
        raise RuntimeError('GATT_CHARACTERISTIC_NOT_WRITABLE')
    return True

def write(payload):
    # D-Bus signature ay,a{sv}; array length + bytes + empty options dictionary.
    cmd=['busctl','--system','--timeout=2','call','org.bluez',GATT,
         'org.bluez.GattCharacteristic1','WriteValue','aya{sv}',
         str(len(payload)),*(str(x) for x in payload),'0']
    started=time.monotonic()
    result=call(cmd,timeout=3)
    return {'code':result.returncode,
            'duration_s':round(time.monotonic()-started,3),
            'output':(result.stdout+result.stderr)[-400:]}

def main():
    p=argparse.ArgumentParser(description='Single experimental BLE TELE pulse')
    p.add_argument('--execute',action='store_true',
                   help='physically operate Sony Power Zoom for 160 ms')
    args=p.parse_args()
    check()
    record={'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'device':'ILCE-6100A',
            'mode':'EXECUTE' if args.execute else 'DRY_RUN',
            'characteristic':EXPECTED,
            'press_hex':'02 45 10',
            'release_hex':'02 44 00',
            'pulse_ms':160}
    print('SONY_BLE_PRECHECK=PASS',flush=True)
    print('PRESS=02 45 10, RELEASE=02 44 00, DURATION_MS=160',flush=True)
    if not args.execute:
        print('DRY_RUN=PASS; NOT WRITING TO BLE, NO LENS MOVEMENT',flush=True)
        return 0
    is_pressed=False
    def stop_signal(sig,_):
        raise InterruptedError(f'SIGNAL_{sig}')
    signal.signal(signal.SIGTERM,stop_signal)
    result=None
    try:
        is_pressed=True
        result=write(PRESS)
        record['press_result']=result
        print('PRESS_RESULT='+json.dumps(result),flush=True)
        if result['code']!=0:raise RuntimeError('PRESS_GATT_FAILED')
        time.sleep(PULSE_SECONDS)
    except BaseException as exc:
        record['error']=repr(exc)
        print('BLE_PRESS_OR_SLEEP_ERROR='+repr(exc),flush=True)
    finally:
        # Attempt RELEASE even if press failed or signal interrupted.
        release=write(RELEASE)
        record['release_result']=release
        print('RELEASE_RESULT='+json.dumps(release),flush=True)
        if release['code']!=0:
            try:
                time.sleep(0.10)
                retry=write(RELEASE)
                record['release_retry']=retry
                print('RELEASE_RETRY_RESULT='+json.dumps(retry),flush=True)
            except BaseException as retry_error:
                record['release_retry_error']=repr(retry_error)
        record['outcome']='PRESS_AND_RELEASE_OK' if result and result['code']==0 and release['code']==0 else 'FAILED_OR_PARTIAL'
        record['completed_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        output=ROOT/'sony-ble-zoom-tele-once-result.json'
        output.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
        print('RESULT_FILE='+str(output),flush=True)
    if record['outcome']!='PRESS_AND_RELEASE_OK':
        print('CHECK_CAMERA_MANUALLY: TELE RELEASE NOT FULLY CONFIRMED',flush=True)
        return 2
    print('BLE_COMMAND_SEQUENCE_SENT=PASS; ACTUAL_OPTICAL_MOTION_UNVERIFIED',flush=True)
    return 0
if __name__=='__main__':sys.exit(main())
