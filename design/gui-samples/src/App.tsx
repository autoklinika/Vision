import {useEffect, useState} from 'react';
import type {ComponentType} from 'react';
import {emptyDraft, fields, fieldOrder} from './shared';
import type {Draft, EditorProps, Errors, FieldName, Variant} from './shared';
import './comparison.css';

const STORAGE = 'vision.gui-samples.v1';
type SampleState = {draft: Draft; created: boolean; saved: Draft | null};
const initialState = (): SampleState => ({draft: {...emptyDraft}, created: false, saved: null});
function validDraft(value: unknown): value is Draft {
  return typeof value === 'object' && value !== null &&
    fieldOrder.every(key => typeof (value as Draft)[key] === 'string' && (value as Draft)[key].length <= fields[key].maxLength);
}
function readSample(): SampleState {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(STORAGE) ?? 'null');
    if (typeof value === 'object' && value !== null && 'draft' in value && validDraft(value.draft) &&
        'created' in value && typeof value.created === 'boolean' && 'saved' in value &&
        (value.saved === null || validDraft(value.saved))) return value as SampleState;
  } catch { /* A browser may disable session storage; the sample still works. */ }
  return initialState();
}

export function App({variant, Editor}: {variant: Variant; Editor: ComponentType<EditorProps>}) {
  const [state, setState] = useState<SampleState>(readSample);
  const [errors, setErrors] = useState<Errors>({});
  const [notice, setNotice] = useState('');
  const baseline = state.saved ?? emptyDraft;
  const dirty = fieldOrder.some(key => state.draft[key] !== baseline[key]);
  useEffect(() => {
    try {sessionStorage.setItem(STORAGE, JSON.stringify(state));} catch { /* Optional convenience only. */ }
  }, [state]);

  function change(field: FieldName, value: string) {
    setState(previous => ({...previous, draft: {...previous.draft, [field]: value}}));
    setErrors(previous => {const next = {...previous}; delete next[field]; return next;});
    setNotice('');
  }
  function submit() {
    const nextErrors: Errors = {};
    for (const key of fieldOrder) if (!state.draft[key].trim()) nextErrors[key] = 'Uzupełnij to pole.';
    setErrors(nextErrors);
    const first = fieldOrder.find(key => nextErrors[key]);
    if (first) {
      setNotice('');
      requestAnimationFrame(() => document.getElementById('field-' + first)?.focus());
      return;
    }
    setState(previous => ({...previous, created: true, saved: {...previous.draft}}));
    setNotice('Zapisano szkic w podglądzie. Dane nie trafiają do biblioteki Vision.');
  }
  function reset() {
    setState(initialState());
    setErrors({});
    setNotice('Formularz wyczyszczony.');
    requestAnimationFrame(() => document.getElementById('field-name')?.focus());
  }
  return <div className={'comparison-root comparison-' + variant}>
    <a className="sample-skip" href="#sample-content">Przejdź do formularza</a>
    <header className="comparison-bar">
      <span className="comparison-label">Próbki GUI</span>
      <nav aria-label="Wariant interfejsu" className="comparison-switch">
        <a href="/design/carbon/" aria-current={variant === 'carbon' ? 'page' : undefined}>A <span>Carbon</span></a>
        <a href="/design/fluent/" aria-current={variant === 'fluent' ? 'page' : undefined}>B <span>Fluent 2</span></a>
      </nav>
      <span className="comparison-kind">Ten sam formularz · dane testowe</span>
      <a className="comparison-back" href="/" aria-label="Wróć do obecnego podglądu Vision"><span>Obecny podgląd</span><svg aria-hidden="true" viewBox="0 0 20 20"><path d="M7 5h8v8M15 5 5 15" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg></a>
    </header>
    <div id="sample-content" tabIndex={-1}>
      <Editor draft={state.draft} errors={errors} created={state.created} dirty={dirty} notice={notice} onChange={change} onSubmit={submit} onReset={reset}/>
    </div>
  </div>;
}
