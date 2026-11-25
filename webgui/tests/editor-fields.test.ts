import {describe,expect,it} from 'vitest';
import fixture from './fixtures/editor-profile.json';
import {librarySections} from '../src/api/libraryContract';
import {editorSections,emptyRow,hydrateDocument,serializeDocument,referenceOptions,row,array} from '../src/station/editorFields';
import type {DraftDocument} from '../src/station/draftContract';

const document=()=>structuredClone(fixture) as DraftDocument;
describe('reference form presentation schema',()=>{
  it('round-trips all 15 sections and nested rows without losing fields',()=>{
    const form=hydrateDocument(document());
    expect(Object.keys(editorSections)).toEqual([...librarySections]);
    expect(JSON.parse(serializeDocument(form))).toEqual(document());
  });
  it('preserves optional nulls, declared false and explicit zero values',()=>{
    const d=document();row(row(d.coordinate_systems).ecu_local).origin_description=null;
    const connector=row(array(row(d.connectors_landmarks).connectors)[0]);connector.position_mm=null;
    connector.uncertainty_mm=null;connector.verified=false;
    expect(JSON.parse(serializeDocument(hydrateDocument(d)))).toEqual(d);
  });
  it('creates blank measurements rather than fabricating dimensions',()=>{
    const field=editorSections.geometry.field;
    if(field.kind!=='object')throw new Error('schema changed');
    const envelopes=field.fields.per_physical_state;
    if(envelopes.kind!=='rows')throw new Error('schema changed');
    const item=emptyRow(envelopes.fields);
    expect(item.envelope_xyz_mm).toEqual(['','','']);
    expect(item.uncertainty_mm).toBe('');
    expect(item.verified).toBe(false);
    const form=hydrateDocument(document());row(form.geometry).per_physical_state=[item];
    expect(()=>serializeDocument(form)).toThrow(/Envelope/i);
  });
  it('accepts decimal comma and does not convert empty input into zero',()=>{
    const form=hydrateDocument(document());
    const geo=row(array(row(form.geometry).per_physical_state)[0]);
    geo.envelope_xyz_mm=['100,25','80','20'];
    expect(JSON.parse(serializeDocument(form)).geometry.per_physical_state[0].envelope_xyz_mm).toEqual([100.25,80,20]);
    geo.envelope_xyz_mm=['','80','20'];
    expect(()=>serializeDocument(form)).toThrow(/Maximum envelope \/ X/);
  });
  it('constructs reference choices from the same working document',()=>{
    const form=hydrateDocument(document());
    expect(referenceOptions(form,'feature').map(x=>x.value)).toEqual(['connector','test-landmark']);
    expect(referenceOptions(form,'view').map(x=>x.value)).toEqual(['view']);
    expect(referenceOptions(form,'recipe').map(x=>x.value)).toContain('thermal-test');
    row(form.pcb_definition).regions_of_interest=[];
    expect(referenceOptions(form,'roi')).toEqual([]);
  });
  it('rejects unsupported nested fields instead of silently dropping them',()=>{
    const d=document();row(d.geometry).future_field='unexpected';
    expect(()=>hydrateDocument(d)).toThrow(/Unsupported fields/);
  });
  it('rejects duplicate threshold keys',()=>{
    const form=hydrateDocument(document());
    row(array(row(form.validation_policies).policies)[0]).thresholds=[{name:'m',value:'1'},{name:'m',value:'2'}];
    expect(()=>serializeDocument(form)).toThrow(/unique identifier/);
  });
});
