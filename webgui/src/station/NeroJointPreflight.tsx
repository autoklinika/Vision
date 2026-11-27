import {Badge,MessageBar,MessageBarBody} from '@fluentui/react-components';
import type {JointCheck} from './neroJointLimitsContract';
import {useTranslation} from '../i18n/LanguageProvider';
const angle=(x:number|null)=>x===null?'—':(x*180/Math.PI).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:3})+'°';
export function NeroJointPreflight({check}:{check:JointCheck|null}){
 const {t}=useTranslation();
 const state=check?.state??'UNKNOWN';
 const outside=check?.rows.filter(r=>r.state==='OUTSIDE_LIMITS')??[];
 return <section className="luxonis-settings-card" aria-label={t('Joint limit preflight')}>
  <div className="nero-tcp-drive-row"><h3>{t('Joint limit preflight')}</h3>
   <Badge appearance="tint" color={state==='OUTSIDE_LIMITS'?'danger':state==='WITHIN_LIMITS'?'success':'informative'}>{t(state)}</Badge></div>
  {state==='OUTSIDE_LIMITS'&&<MessageBar intent="error"><MessageBarBody>
   {t('Drive enable blocked: measured joint position exceeds a software reference limit.')} {outside.map(r=>'J'+r.joint.slice(5)+' · '+angle(r.positionRad)).join('; ')}
  </MessageBarBody></MessageBar>}
  {check&&<div className="nero-limit-scroll"><table className="nero-limit-table">
   <thead><tr><th>{t('Joint')}</th><th>{t('Actual position')}</th><th>SDK</th><th>MoveIt</th><th>{t('Status')}</th></tr></thead>
   <tbody>{check.rows.map(r=><tr key={r.joint} data-joint={r.joint}><th scope="row">J{r.joint.slice(5)}</th><td>{angle(r.positionRad)}</td>
    <td>{angle(r.sdkRad[0])} … {angle(r.sdkRad[1])}</td><td>{angle(r.modelRad[0])} … {angle(r.modelRad[1])}</td>
    <td><Badge appearance="tint" color={r.state==='OUTSIDE_LIMITS'?'danger':r.state==='WITHIN_LIMITS'?'success':'informative'}>{t(r.state)}</Badge></td></tr>)}</tbody>
  </table></div>}
  <p className="fine-print">{t('Reference: installed SDK V121 and official MoveIt model. In-range does not certify physical readiness. No limits are changed.')}</p>
 </section>;
}
