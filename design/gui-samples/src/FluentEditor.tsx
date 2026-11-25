import {
  Badge,
  Button,
  Field,
  FluentProvider,
  Input,
  webLightTheme,
  type Theme,
} from '@fluentui/react-components';
import {
  CheckmarkCircle20Regular,
  DocumentEdit24Regular,
  Eraser20Regular,
  Info20Regular,
  Save20Regular,
} from '@fluentui/react-icons';
import { fields, type EditorProps, type FieldName } from './shared';
import './fluent.css';

const visionTheme: Theme = {
  ...webLightTheme,
  fontFamilyBase: '"Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, Arial, sans-serif',
  fontSizeBase300: '16px',
  lineHeightBase300: '22px',
};

export function FluentEditor({
  draft, errors, created, dirty, notice, onChange, onSubmit, onReset,
}: EditorProps) {
  const title = created && draft.name.trim() ? draft.name.trim() : 'Nowy profil ECU';
  const status = !created ? 'Nowy szkic' : dirty ? 'Niezapisane zmiany' : 'Zapisano w podglądzie';

  function renderField(name: FieldName) {
    const definition = fields[name];
    const error = errors[name];
    return (
      <Field
        className={`fluent-field fluent-field-${name}`}
        label={{children: definition.label, htmlFor: `field-${name}`}}
        required
        validationState={error ? 'error' : 'none'}
        validationMessage={error || undefined}
        hint={definition.hint}
      >
        <Input
          id={`field-${name}`}
          name={name}
          size="large"
          appearance="outline"
          value={draft[name]}
          maxLength={definition.maxLength}
          autoComplete="off"
          spellCheck={name === 'name'}
          onChange={(_, data) => onChange(name, data.value)}
        />
      </Field>
    );
  }

  return (
    <FluentProvider theme={visionTheme} className="sample-fluent">
      <header className="fluent-titlebar">
        <strong className="fluent-wordmark">VISION</strong>
        <span className="fluent-titlebar-rule" aria-hidden="true" />
        <span className="fluent-product-area">Profile ECU</span>
        <span className="fluent-preview-label">Podgląd</span>
      </header>

      <div className="fluent-editor-layout">
        <aside className="fluent-outline" aria-label="Struktura profilu">
          <p className="fluent-outline-label">Bieżący dokument</p>
          <div className="fluent-document-item">
            <DocumentEdit24Regular aria-hidden="true" />
            <span>{created && draft.name.trim() ? draft.name.trim() : 'Nowy profil'}</span>
          </div>
          <nav aria-label="Przejdź do sekcji">
            <a href="#fluent-general">Dane podstawowe</a>
            <a href="#fluent-identifiers">Oznaczenie w bibliotece</a>
          </nav>
          <div className="fluent-outline-footer">
            <span className="fluent-outline-rule" />
            <p>Profil wzorcowy ECU</p>
            <small>Identyfikacja i wersja definicji</small>
          </div>
        </aside>

        <div className="fluent-document">
          <main className="fluent-content" aria-labelledby="fluent-profile-title">
            <div className="fluent-document-heading">
              <div>
                <h1 id="fluent-profile-title">{title}</h1>
                <p>Nadaj nazwę i określ oznaczenia profilu.</p>
              </div>
              <Badge appearance="tint" color="informative" size="large">Szkic</Badge>
            </div>

            {notice && (
              <div className="fluent-notice" role="status">
                <CheckmarkCircle20Regular aria-hidden="true" />
                <span>{notice}</span>
              </div>
            )}

            <form
              id="fluent-profile-form"
              className="fluent-profile-form"
              noValidate
              autoComplete="off"
              onSubmit={event => { event.preventDefault(); onSubmit(); }}
            >
              <section id="fluent-general" aria-label="Dane podstawowe">
                {renderField('name')}
                <div className="fluent-field-pair">
                  {renderField('family')}
                  {renderField('variantId')}
                </div>
              </section>

              <section id="fluent-identifiers" className="fluent-identifiers" aria-labelledby="fluent-identifiers-title">
                <h2 id="fluent-identifiers-title">Oznaczenie w bibliotece</h2>
                <div className="fluent-field-pair fluent-identifier-pair">
                  {renderField('profileId')}
                  {renderField('revision')}
                </div>
              </section>
            </form>

            <p className="fluent-draft-note">
              <Info20Regular aria-hidden="true" />
              <span>Utworzony szkic pozostanie w tym podglądzie.</span>
            </p>
          </main>

          <div className="fluent-commandbar" role="region" aria-label="Działania profilu">
            <span className="fluent-save-state">
              {created && !dirty ? <CheckmarkCircle20Regular aria-hidden="true" /> : <span className="fluent-state-dot" aria-hidden="true" />}
              {status}
            </span>
            <div className="fluent-actions">
              <Button appearance="subtle" icon={<Eraser20Regular />} size="large" onClick={onReset}>
                Wyczyść
              </Button>
              <Button
                appearance="primary"
                icon={<Save20Regular />}
                size="large"
                type="submit"
                form="fluent-profile-form"
              >
                {created ? 'Zapisz zmiany' : 'Utwórz szkic'}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </FluentProvider>
  );
}
