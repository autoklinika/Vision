import { useTranslation } from '../i18n/LanguageProvider';
import { Button, Checkbox, Input, Select } from '@fluentui/react-components';
import {useId} from 'react';
import type {Field,Fields,FormDocument,Row} from './editorFields';
import {array,row,emptyRow,emptyValue,referenceOptions} from './editorFields';

type Common={doc:FormDocument;disabled:boolean};
type Props=Common&{field:Field;value:unknown;onChange:(value:unknown)=>void;labelOverride?:string};
const setItem=(values:unknown[],i:number,value:unknown)=>values.map((v,index)=>index===i?value:v);
const removeItem=(values:unknown[],i:number)=>values.filter((_,index)=>i!==index);


function ObjectFields({fields,value,onChange,doc,disabled}:Common&{fields:Fields;value:Row;onChange:(value:Row)=>void}) {
  return <div className="editor-object-fields">{Object.entries(fields).map(([k,f])=>
    <FieldControl key={k} field={f} value={value[k]} onChange={v=>onChange({...value,[k]:v})} doc={doc} disabled={disabled}/>)}</div>;
}
function numberText(value:unknown){return typeof value==='number'||typeof value==='string'?String(value):'';}


export function FieldControl({field,value,onChange,doc,disabled,labelOverride}:Props) {
  const {t}=useTranslation();
  const control=useId(),label=labelOverride??t(field.label);
  const optionalLabel=field.optional?t('{label} (optional)',{label}):label;
  const labelText=(v:unknown)=>v==null?t('Not set'):Array.isArray(v)?v.length===0?t('None'):t('{count} entries',{count:v.length}):typeof v==='boolean'?t(v?'Yes':'No'):String(v);
  const confirmRemove=(name:string)=>window.confirm(t('Remove {label} from the working draft? Related references are not changed automatically.',{label:name}));
  const help=field.help?<small className="editor-field-help">{t(field.help)}</small>:null;
  switch(field.kind) {
    case 'locked':return <div className="editor-field editor-locked"><span>{label}</span><div><output aria-label={label}>{labelText(value)}</output>{help}</div></div>;
    case 'text':return <div className="editor-field"><label htmlFor={control}>{optionalLabel}</label><div>
      <Input id={control} type="text" value={typeof value==='string'?value:''} maxLength={field.max??4096} placeholder={field.placeholder?t(field.placeholder):undefined} disabled={disabled}
        onChange={e=>onChange(field.optional&&e.target.value===''?null:e.target.value)} autoComplete="off"/>{help}</div></div>;
    case 'number':return <div className="editor-field"><label htmlFor={control}>{field.optional?t("{label} (optional)",{label:label+(field.unit?" ("+field.unit+")":"")}):label+(field.unit?" ("+field.unit+")":"")}</label><div>
      <Input id={control} type="text" inputMode={field.integer?'numeric':'decimal'} value={numberText(value)} maxLength={32} placeholder={field.optional?t("Not measured"):t("Enter value")} disabled={disabled}
        onChange={e=>onChange(field.optional&&e.target.value===''?null:e.target.value)}/>{help}</div></div>;
    case 'bool':return <div className="editor-field editor-checkbox"><label htmlFor={control}>{label}</label><div>
      <Checkbox id={control} checked={value===true} disabled={disabled} onChange={e=>onChange(e.target.checked)}/>{help}</div></div>;
    case 'enum':
    case 'ref':{
      const options=field.kind==='ref'?referenceOptions(doc,field.target):field.options.map(x=>({value:x,label:x}));
      const current=typeof value==='string'?value:'';
      const unknown=current!==''&&!options.some(o=>o.value===current);
      return <div className="editor-field"><label htmlFor={control}>{optionalLabel}</label><div>
        <Select id={control} value={current} disabled={disabled} onChange={e=>onChange(e.target.value===''&&field.optional?null:e.target.value)}>
          <option value="">{field.optional?t("Not set"):t("Select…")}</option>
          {unknown&&<option value={current}>{t("{value} (unresolved)",{value:current})}</option>}
          {options.map(o=><option key={o.value} value={o.value}>{field.kind==='enum'?t(o.label):o.label}</option>)}
        </Select>
        {field.kind==='ref'&&options.length===0&&<small className="editor-field-help">{t("Define the referenced items in their section first.")}</small>}
        {unknown&&<small className="editor-warning">{t("Unresolved or unsupported reference. Correct it before saving.")}</small>}{help}
      </div></div>;
    }
    case 'vector':{
      const values=value===null?null:array(value);
      return <fieldset className="editor-vector"><legend>{label}{field.unit?' ('+field.unit+')':''}</legend>
        {field.optional&&<Checkbox className="editor-optional-toggle" label={t('Specify {label}',{label:label.toLowerCase()})} checked={values!==null} disabled={disabled} onChange={(_,data)=>onChange(data.checked===true?field.components.map(()=>''):null)}/>}
        {values!==null&&<div className="editor-vector-fields" style={{gridTemplateColumns:'repeat('+field.components.length+',minmax(0,1fr))'}}>
          {field.components.map((axis,i)=><label key={axis} htmlFor={control+'-'+i}>{t(axis)}
            <Input id={control+'-'+i} aria-label={label+' '+t(axis)+(field.unit?' ('+field.unit+')':'')} type="text" inputMode="decimal" value={numberText(values[i])} disabled={disabled} placeholder="—" maxLength={32}
              onChange={e=>onChange(setItem(values,i,e.target.value))}/>
          </label>)}</div>}
        {help}
      </fieldset>;
    }
    case 'object':return <fieldset className="editor-group"><legend>{label}</legend><ObjectFields fields={field.fields} value={row(value)} onChange={onChange} doc={doc} disabled={disabled}/>{help}</fieldset>;
    case 'rows':{
      const values=array(value);
      return <fieldset className="editor-collection"><legend>{label} ({values.length})</legend>
        {values.length===0&&<p className="fine-print">{t("No {type} entries. Add only values you intend to define.",{type:t(field.title)})}</p>}
        {values.map((v,i)=>{
          const data=row(v);
          const first=Object.keys(field.fields)[0]; const name=typeof data[first]==='string'&&data[first]?String(data[first]):t('New {type}',{type:t(field.title)});
          return <fieldset className="editor-row" key={i} aria-label={t(field.title)+' '+(i+1)}>
            <legend>{i+1}. {name}</legend>
            <div className="editor-row-toolbar"><Button type="button" disabled={disabled} onClick={()=>{if(confirmRemove(t(field.title)+' '+(i+1)))onChange(removeItem(values,i));}}>{t("Remove {label}",{label:t(field.title)})}</Button></div>
            <ObjectFields fields={field.fields} value={data} onChange={next=>onChange(setItem(values,i,next))} doc={doc} disabled={disabled}/>
          </fieldset>;
        })}
        <Button appearance="secondary" type="button" disabled={disabled||values.length>=128} onClick={()=>onChange([...values,emptyRow(field.fields)])}>{t("Add {label}",{label:t(field.title)})}</Button>{help}
      </fieldset>;
    }
    case 'list':{
      const values=array(value);
      return <fieldset className="editor-collection editor-list"><legend>{label} ({values.length})</legend>
        {values.map((v,i)=><div key={i} className="editor-list-row">
          <FieldControl field={field.item} labelOverride={label+' '+(i+1)} value={v} onChange={x=>onChange(setItem(values,i,x))} doc={doc} disabled={disabled}/>
          <Button type="button" aria-label={t('Remove {label}',{label:label+' '+(i+1)})} disabled={disabled} onClick={()=>onChange(removeItem(values,i))}>{t("Remove")}</Button>
        </div>)}
        <Button appearance="secondary" type="button" disabled={disabled||values.length>=128} onClick={()=>onChange([...values,emptyValue(field.item)])}>{t("Add {label} entry",{label:label.toLowerCase()})}</Button>{help}
      </fieldset>;
    }
    case 'thresholds':{
      const values=array(value);
      return <fieldset className="editor-collection"><legend>{label} ({values.length})</legend>
        {values.map((v,i)=>{
          const data=row(v);
          return <div className="editor-threshold" key={i}>
            <label>{t("Metric {number}",{number:i+1})}<Input value={String(data.name??'')} disabled={disabled} maxLength={128} onChange={e=>onChange(setItem(values,i,{...data,name:e.target.value}))}/></label>
            <label>{t("Value {number}",{number:i+1})}<Input inputMode="decimal" value={numberText(data.value)} disabled={disabled} maxLength={32} onChange={e=>onChange(setItem(values,i,{...data,value:e.target.value}))}/></label>
            <Button type="button" disabled={disabled} onClick={()=>onChange(removeItem(values,i))}>{t("Remove metric")}</Button>
          </div>;
        })}
        <Button appearance="secondary" type="button" disabled={disabled||values.length>=128} onClick={()=>onChange([...values,{name:'',value:''}])}>{t("Add threshold")}</Button>{help}
      </fieldset>;
    }
  }
}
