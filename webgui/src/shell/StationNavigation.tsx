import { useTranslation } from '../i18n/LanguageProvider';
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Button, DrawerBody, DrawerFooter, DrawerHeader, DrawerHeaderTitle, FluentProvider, OverlayDrawer, webLightTheme } from '@fluentui/react-components';
import { NavigationRegular, DismissRegular, AppsRegular, LibraryRegular, ClipboardTaskList16Regular, CameraRegular, VideoRegular, ImageRegular, SettingsRegular, SignOutRegular, PulseRegular, WrenchRegular, DocumentRegular } from '@fluentui/react-icons';
import { stationAppTitle } from './model';
import type { AppId } from './model';
import { loadStationLogo } from '../startup/brand';
import './station-navigation.css';

const icons = { status: PulseRegular, ecu: LibraryRegular, inspection: ClipboardTaskList16Regular, luxonis: VideoRegular, nero: AppsRegular, sony: CameraRegular, images: ImageRegular, control: WrenchRegular, events: DocumentRegular, settings: SettingsRegular };
const groups: { name: string; ids: AppId[] }[] = [
  { name: 'Workspace', ids: ['status', 'luxonis', 'ecu', 'inspection', 'images'] },
  { name: 'System', ids: ['events', 'control', 'settings'] },
];

function StationLogo() {
  const {t}=useTranslation();
  const [logo, setLogo] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    const timeout = window.setTimeout(() => controller.abort(), 2000);
    void loadStationLogo(controller.signal).then(url => {
      if (controller.signal.aborted) { URL.revokeObjectURL(url); return; }
      objectUrl = url;
      setLogo(url);
    }).catch(() => { /* Optional private asset; the plain text product name is not a substitute logo. */ })
      .finally(() => window.clearTimeout(timeout));
    return () => { controller.abort(); window.clearTimeout(timeout); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, []);
  return logo ? <img className="vision-header-logo" src={logo} alt={t("Original Vision logo")} onError={() => setLogo(null)}/> : <span className="vision-product-name">VISION</span>;
}

export function StationNavigation({active, onNavigate, onSignOut, accountBusy, available, tabs}: {
  active: AppId | null; tabs: ReactNode;
  onNavigate: (id: AppId) => void; onSignOut: () => void; accountBusy: boolean; available: boolean;
}) {
  const {t}=useTranslation();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const [previousAvailable, setPreviousAvailable] = useState(available);
  if (available !== previousAvailable) { setPreviousAvailable(available); setOpen(false); }
  return <FluentProvider theme={webLightTheme} className="vision-station-navigation">
    <header className="mode-banner vision-topbar">
      <Button id="vision-open-navigation" ref={trigger} appearance="subtle" icon={<NavigationRegular/>} aria-label={t("Open navigation")} aria-haspopup="dialog" aria-expanded={available && open} onClick={() => setOpen(true)}/>
      <div className="vision-topbar-brand"><StationLogo/></div>
      {tabs}
    </header>
    <OverlayDrawer className="vision-navigation-drawer" position="start" size="small" modalType="modal" open={available && open} onOpenChange={(_, data) => setOpen(available && data.open)} aria-labelledby="vision-navigation-title">
      <DrawerHeader>
        <DrawerHeaderTitle action={<Button appearance="subtle" icon={<DismissRegular/>} aria-label={t("Close navigation")} onClick={() => setOpen(false)}/>}>
          <span id="vision-navigation-title">{t("Navigation")}</span>
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody>
        <nav aria-label={t("Vision modules")} className="vision-navigation-groups">
          {groups.map(group => <section key={group.name} aria-label={t(group.name)}>
            <h2>{t(group.name)}</h2>
            {group.ids.map(id => {
              const ModuleIcon = icons[id];
              return <Button key={id} appearance="subtle" icon={<ModuleIcon/>} className="vision-navigation-item" aria-current={active === id ? 'page' : undefined} onClick={() => { setOpen(false); onNavigate(id); }}>{t(stationAppTitle(id))}</Button>;
            })}
          </section>)}
        </nav>
      </DrawerBody>
      <DrawerFooter className="vision-navigation-footer">
        <Button appearance="subtle" icon={<SignOutRegular/>} disabled={accountBusy} onClick={() => { setOpen(false); trigger.current?.focus({preventScroll:true}); onSignOut(); }}>{t("Sign out")}</Button>
      </DrawerFooter>
    </OverlayDrawer>
  </FluentProvider>;
}
