#!/usr/bin/env python3
"""Offline decode of previously captured Sony PTP2 0x9209 dataset. No USB calls."""
import struct, json
from pathlib import Path
root=Path('/srv/vision-data/tools/sony-a6100-verify/ptp2-capabilities-test')
data=(root/'get-all-ext-properties.bin').read_bytes()
pos=0
def take(n):
    global pos
    if n<0 or pos+n>len(data):raise ValueError(f'TRUNCATED offset={pos} need={n}')
    res=data[pos:pos+n]
    pos+=n
    return res
def read(fmt):
    return struct.unpack(fmt,take(struct.calcsize(fmt)))[0]
def vread(dtype):
    if dtype==0xffff:
        n=read('<B')
        return take(n*2).decode('utf-16-le',errors='replace').rstrip(chr(0))
    szmap={1:1,2:1,3:2,4:2,5:4,6:4,7:8,8:8,9:16,10:16}
    d=dtype
    if d>=0x4000 and d<0x4010:
        sz=szmap.get(d&0xff)
        if sz is None:raise ValueError(f'UNKNOWN_ARRAY_TYPE=0x{d:04X}')
        count=read('<I')
        if count>2000:raise ValueError(f'ARRAY_OVERSIZED {count}')
        return [int.from_bytes(take(sz),'little') for _ in range(count)]
    sz=szmap.get(d)
    if sz is None:raise ValueError(f'UNKNOWN_TYPE=0x{d:04X}')
    return int.from_bytes(take(sz),'little')

n=read('<Q')
assert 1<=n<=200,'INVALID_DATASET_COUNT'
rows=[]
try:
    for i in range(n):
        start=pos
        code=read('<H');dtype=read('<H');getset=read('<B');enabled=read('<B')
        default=vread(dtype);current=vread(dtype)
        form=read('<B')
        bounds=None;enum_count=None
        if form==1:
            bounds=[vread(dtype) for _ in range(3)]
        elif form==2:
            enum_count=read('<H')
            if enum_count>2000:raise ValueError('ENUM_OVERSIZED')
            for _ in range(enum_count):vread(dtype)
        elif form!=0:raise ValueError(f'UNKNOWN_FORM={form}')
        rows.append({
            'code':f'0x{code:04X}','data_type':f'0x{dtype:04X}',
            'getset':getset,'enabled':enabled,'form':form,
            'current':current if code==0xd214 else None,
            'range':bounds if code==0xd214 else None,
            'offset':start,'length':pos-start,
        })
except Exception as exc:
    print('PARSE_FAILED_AT_INDEX=',i,'OFFSET=',pos,'ERROR=',str(exc),flush=True)
    raise
print('RECORDS=',n,'PARSED=',len(rows),'BYTES=',pos,'TOTAL_BYTES=',len(data),flush=True)
assert len(rows)==n and pos==len(data),f'DATASET_PARSE_INCOMPLETE {pos}/{len(data)}'
seen={row['code'] for row in rows}
print('ALL_RECORD_CODES='+' '.join(row['code'] for row in rows),flush=True)
print('D214_ITEM='+json.dumps([r for r in rows if r['code']=='0xD214']),flush=True)
print('UNKNOWN_D2XX_CODES='+str([r['code'] for r in rows if r['code'].startswith('0xD2')]),flush=True)
(root/'all-property-descriptors-parsed.json').write_text(json.dumps({'count':n,'descriptors':rows},indent=2,ensure_ascii=False)+'\n')
print('PARSER_PASS=YES',flush=True)
