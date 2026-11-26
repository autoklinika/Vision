import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { LANGUAGE_KEY, resolveLanguage, translate } from './catalog';
import type { Language, Params } from './catalog';
type LanguageContextValue = {language: Language; setLanguage: (value: Language) => void; t: (key: string, params?: Params) => string};
const LanguageContext = createContext<LanguageContextValue>({language:'en',setLanguage:()=>{},t:(key,params)=>translate('en',key,params)});
function initialLanguage(): Language {
  let saved: string | null = null;
  try { saved = localStorage.getItem(LANGUAGE_KEY); } catch { /* optional browser storage */ }
  return resolveLanguage(saved, navigator.language);
}
export function LanguageProvider({children}: {children:ReactNode}) {
  const [language,setLanguage] = useState<Language>(initialLanguage);
  useEffect(()=>{
    document.documentElement.lang = language;
    try { localStorage.setItem(LANGUAGE_KEY,language); } catch { /* in-memory preference still works */ }
  },[language]);
  const value=useMemo<LanguageContextValue>(()=>({language,setLanguage,t:(key,params)=>translate(language,key,params)}),[language]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}
export function useTranslation() { return useContext(LanguageContext); }
