import { useState } from 'react';
import { Button, Tag, TextInput } from '@carbon/react';
import type { EditorProps, FieldName } from './shared';
import { fields } from './shared';
import './carbon.scss';

export function CarbonEditor({
  draft, errors, created, dirty, notice, onChange, onSubmit, onReset,
}: EditorProps) {
  const [activeSection, setActiveSection] = useState('definition');
  function input(field: FieldName, className = '') {
    const spec = fields[field];
    return <div className={className}>
      <TextInput
        id={`field-${field}`}
        name={field}
        labelText={spec.label}
        helperText={spec.hint}
        value={draft[field]}
        onChange={event => onChange(field, event.currentTarget.value)}
        onFocus={() => setActiveSection(field === 'profileId' || field === 'revision' ? 'identifiers' : 'definition')}
        invalid={Boolean(errors[field])}
        invalidText={errors[field] ?? ''}
        maxLength={spec.maxLength}
        size="lg"
        required
        autoComplete="off"
        autoCapitalize={field === 'profileId' || field === 'variantId' || field === 'revision' ? 'none' : 'sentences'}
        spellCheck={false}
      />
    </div>;
  }

  return <div className="carbon-sample" data-ui-system="carbon">
    <header className="carbon-station-bar">
      <span className="carbon-wordmark">VISION</span>
      <span className="carbon-station-divider" aria-hidden="true" />
      <span className="carbon-module-name">Profile ECU</span>
      <span className="carbon-preview-mark">Podgląd</span>
    </header>

    <div className="carbon-workspace">
      <aside className="carbon-outline" aria-label="Sekcje formularza">
        <p className="carbon-outline-label">Zawartość profilu</p>
        <nav>
          <a className={activeSection === 'definition' ? 'carbon-outline-current' : undefined} aria-current={activeSection === 'definition' ? 'location' : undefined} href="#carbon-definition" onClick={() => setActiveSection('definition')}>
            <span className="carbon-outline-index" aria-hidden="true">01</span>
            Nazwa i wariant
          </a>
          <a className={activeSection === 'identifiers' ? 'carbon-outline-current' : undefined} aria-current={activeSection === 'identifiers' ? 'location' : undefined} href="#carbon-identifiers" onClick={() => setActiveSection('identifiers')}>
            <span className="carbon-outline-index" aria-hidden="true">02</span>
            Oznaczenia
          </a>
        </nav>
        <div className="carbon-outline-note">
          <span className="carbon-outline-rule" aria-hidden="true" />
          <p>Profil określa rodzaj ECU.<br />Dane egzemplarza należą do inspekcji.</p>
        </div>
      </aside>

      <main className="carbon-editor-main" aria-labelledby="carbon-editor-title">
        <div className="carbon-editor-heading">
          <div className="carbon-title-line">
            <h1 id="carbon-editor-title">{created ? draft.name || 'Profil ECU' : 'Nowy profil ECU'}</h1>
            <Tag type="gray" size="md">{created ? 'Szkic' : 'Nowy'}</Tag>
          </div>
          <p>Wszystkie pola są wymagane.</p>
        </div>

        <form id="carbon-profile-form" className="carbon-profile-form" noValidate onSubmit={event => {
          event.preventDefault();
          onSubmit();
        }}>
          <section id="carbon-definition" className="carbon-definition" aria-label="Nazwa i wariant">
            {input('name', 'carbon-name-field')}
            <div className="carbon-field-pair">
              {input('family')}
              {input('variantId')}
            </div>
          </section>

          <section id="carbon-identifiers" className="carbon-identifiers" aria-labelledby="carbon-identifiers-title">
            <h2 id="carbon-identifiers-title">Oznaczenia w bibliotece</h2>
            <div className="carbon-identifier-fields">
              {input('profileId')}
              {input('revision')}
            </div>
          </section>
        </form>

        <footer className="carbon-command-bar">
          <div className="carbon-save-state" role="status" aria-live="polite">
            <span className={dirty ? 'carbon-state-indicator is-dirty' : 'carbon-state-indicator'} aria-hidden="true" />
            <span>{notice || (dirty ? 'Niezapisane zmiany' : created ? 'Szkic zapisany w podglądzie' : 'Nowy szkic')}</span>
          </div>
          <div className="carbon-command-actions">
            <Button kind="ghost" type="button" size="lg" onClick={onReset}>Wyczyść</Button>
            <Button kind="primary" type="submit" size="lg" form="carbon-profile-form">
              {created ? 'Zapisz zmiany' : 'Utwórz szkic'}
              <svg className="cds--btn__icon" width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M3 10h13M11 4l6 6-6 6" stroke="currentColor" strokeWidth="1.4" />
              </svg>
            </Button>
          </div>
        </footer>
      </main>
    </div>
  </div>;
}
