import { useId } from 'react';
import { Label, Select } from '@fluentui/react-components';
import { useTranslation } from './LanguageProvider';
export function LanguageSelector() {
  const {language,setLanguage,t}=useTranslation();
  const id=useId();
  return <div className="vision-language-selector">
    <Label htmlFor={id}>{t('Interface language')}</Label>
    <Select id={id} value={language} onChange={(_,data)=>{if(data.value==='pl'||data.value==='en')setLanguage(data.value);}}>
      <option value="pl" lang="pl">Polski</option>
      <option value="en" lang="en">English</option>
    </Select>
  </div>;
}
