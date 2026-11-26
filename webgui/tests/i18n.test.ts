import {describe,expect,it} from 'vitest';
import polish from '../src/i18n/pl.json';
import {resolveLanguage,translate} from '../src/i18n/catalog';
import {editorSections} from '../src/station/editorFields';
import type {Field} from '../src/station/editorFields';
describe('Vision interface localization',()=>{
  it('prefers a supported stored choice, otherwise follows Polish browser locale or English',()=>{
    expect(resolveLanguage('en','pl-PL')).toBe('en');
    expect(resolveLanguage('pl','en-US')).toBe('pl');
    expect(resolveLanguage(null,'pl-PL')).toBe('pl');
    expect(resolveLanguage('invalid','de-DE')).toBe('en');
  });
  it('preserves identifiers and interpolation values exactly',()=>{
    expect(translate('pl','Browse {name} {revision}',{name:'ECU {test}',revision:'r1'})).toBe('Przeglądaj ECU {test} r1');
    expect(translate('en','Close {module}',{module:'ECU Library'})).toBe('Close ECU Library');
    expect(translate('pl','NOT_READY')).toBe('NOT_READY');
    expect(translate('pl','unexpected identifier')).toBe('unexpected identifier');
  });
  it('uses identical interpolation placeholders in both catalogs',()=>{
    const names=(s:string)=>Array.from(s.matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g),m=>m[1]).sort();
    for(const [key,value] of Object.entries(polish))expect(names(value),key).toEqual(names(key));
  });
  it('covers all schema-driven section labels, help, enum options and vector axes',()=>{
    const needed=new Set<string>();
    function collect(f:Field){
      needed.add(f.label);
      if(f.help)needed.add(f.help);
      if(f.kind==='text'&&f.placeholder)needed.add(f.placeholder);
      if(f.kind==='enum')f.options.forEach(v=>needed.add(v));
      if(f.kind==='vector')f.components.forEach(v=>needed.add(v));
      if(f.kind==='rows')needed.add(f.title);
      if(f.kind==='object'||f.kind==='rows')Object.values(f.fields).forEach(collect);
      if(f.kind==='list')collect(f.item);
    }
    Object.values(editorSections).forEach(section=>{needed.add(section.title);needed.add(section.description);collect(section.field);});
    expect([...needed].filter(k=>!Object.hasOwn(polish,k)).sort()).toEqual([]);
  });
});
