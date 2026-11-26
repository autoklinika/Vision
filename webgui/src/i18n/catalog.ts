import polish from './pl.json';
export type Language = 'en' | 'pl';
export type Params = Record<string, string | number>;
export const LANGUAGE_KEY = 'vision.ui.language.v1';
const translations: Readonly<Record<string,string>> = polish;
export function resolveLanguage(saved: unknown, browser: string = ''): Language {
  if (saved === 'pl' || saved === 'en') return saved;
  return /^pl(?:-|$)/i.test(browser) ? 'pl' : 'en';
}
/** English source messages are catalog keys. Parameters are never translated. */
export function translate(language: Language, key: string, params: Params = {}): string {
  const message = language === 'pl' && Object.hasOwn(translations, key) ? translations[key] : key;
  return message.replace(/\{([A-Za-z][A-Za-z0-9_]*)\}/g, (match,name: string) => Object.hasOwn(params,name) ? String(params[name]) : match);
}
