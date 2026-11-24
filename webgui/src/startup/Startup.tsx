import { useEffect, useRef, useState } from 'react';
import type { ReadOnlyVisionClient, Snapshot } from '../api/types';
import { Desktop } from '../shell/Desktop';
import { AppContent } from '../apps/AppContent';
import { introDuration, loadBrand, releaseBrand, InsecureBrandContext } from './brand';
import type { Brand } from './brand';
import './startup.css';

type Phase = 'intro' | 'report' | 'login' | 'desktop';

export function Startup({ client, report }: { client: ReadOnlyVisionClient; report: Promise<Snapshot> }) {
  const [phase, setPhase] = useState<Phase>(() => matchMedia('(prefers-reduced-motion: reduce)').matches ? 'report' : 'intro');
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [brand, setBrand] = useState<Brand | null>(null);
  const [assetMessage, setAssetMessage] = useState('Checking optional local intro.');
  const [reduced, setReduced] = useState(() => matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [playing, setPlaying] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    let alive = true;
    void report.then(value => { if (alive) setSnapshot(value); });
    return () => { alive = false; };
  }, [report]);

  useEffect(() => {
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => {
      setReduced(media.matches);
      if (media.matches) setPhase(current => current === 'intro' ? 'report' : current);
    };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let local: Brand | null = null;
    let alive = true;
    const timeout = window.setTimeout(() => controller.abort(), 2000);
    void loadBrand(controller.signal).then(value => {
      if (controller.signal.aborted) { releaseBrand(value); return; }
      local = value;
      setBrand(value);
      setAssetMessage('Private local original · distribution rights unverified.');
    }).catch((error: unknown) => {
      if (!alive) return;
      setAssetMessage(error instanceof InsecureBrandContext
        ? 'Intro verification requires a secure context: use HTTPS remotely or loopback locally. No brand files were fetched.'
        : 'Original intro unavailable or corrupt. Optional local preparation required; no substitute logo.');
      setPhase(current => current === 'intro' ? 'report' : current);
    }).finally(() => window.clearTimeout(timeout));
    return () => { alive = false; controller.abort(); window.clearTimeout(timeout); if (local) releaseBrand(local); };
  }, []);

  useEffect(() => {
    if (phase !== 'intro' || !playing || reduced) return;
    const timer = window.setTimeout(() => setPhase('report'), introDuration);
    return () => window.clearTimeout(timer);
  }, [phase, playing, reduced]);

  useEffect(() => { heading.current?.focus(); }, [phase]);

  const discardBrand = (message: string) => {
    if (brand) releaseBrand(brand);
    setBrand(null);
    setPlaying(false);
    setAssetMessage(message);
    setPhase(current => current === 'intro' ? 'report' : current);
  };

  const showIntro = phase === 'intro' && !reduced;
  if (phase === 'desktop') return <Desktop client={client} snapshot={snapshot}/>;
  return <main className={`startup ${showIntro ? 'intro-stage' : ''}`}>
    <header className="mode-banner">
      <strong>{client.mode === 'demo' ? 'DEMO' : 'REAL · UNAVAILABLE'}</strong>
      <span>{client.mode === 'demo' ? 'Synthetic fixtures only · No connection to Vision or hardware' : 'Disconnected read-only client · No transport integrated'}</span>
    </header>
    {showIntro ? <div className="intro-content">
      {brand && <img className="intro-logo" src={brand.intro} alt="Original Vision handwriting intro" onLoad={() => setPlaying(true)} onError={() => { discardBrand('Original intro could not be decoded.'); }}/>}
      <div className="intro-actions"><p>{assetMessage}</p><button autoFocus onClick={() => setPhase('report')}>Skip intro</button></div>
    </div> : <section className="window startup-dialog" role="dialog" aria-labelledby="startup-title">
      <div className="title-bar"><h1 className="title-bar-text" id="startup-title" tabIndex={-1} ref={heading}>{phase === 'login' ? 'Welcome to Vision' : 'Vision Workstation Startup'}</h1></div>
      <div className="window-body">
        {brand && <img className="hold-logo" src={brand.logo} alt="Original Vision logo" onError={() => { discardBrand('Local logo could not be decoded.'); }}/>}
        <p className="fine-print" role="status">{assetMessage}</p>
        {phase === 'login' ? <>
          <h2>Login presentation · unavailable</h2>
          <p id="login-explanation">Authentication is not integrated. These disabled fields collect no credentials. Continuing opens only this client; it does not authenticate or authorize any operation.</p>
          <div className="login-fields" aria-describedby="login-explanation">
            <label htmlFor="username">User name</label><input id="username" disabled autoComplete="off"/>
            <label htmlFor="password">Password</label><input id="password" type="password" disabled autoComplete="off"/>
          </div>
          <div className="startup-actions"><button onClick={() => setPhase('report')}>Back to report</button><button onClick={() => setPhase('desktop')}>{client.mode === 'demo' ? 'Continue to DEMO desktop' : 'Open read-only disconnected view'}</button></div>
        </> : <>
          <p role="status" id="report-read-status">{snapshot
            ? 'Client report read finished. System initialization and readiness are not established.'
            : 'Waiting for selected adapter report. No system initialization is performed.'}</p>
          {!snapshot && <div className="report-progress" role="progressbar" aria-label="Waiting for selected adapter report" aria-describedby="report-read-status"><span aria-hidden="true"/></div>}
          <AppContent id="status" snapshot={snapshot} reset={() => {}} persistence=""/>
          <p>Report acquisition starts independently of the intro. No device initialization or automatic commands.</p>
          <div className="startup-actions"><button onClick={() => setPhase('login')}>Continue to login presentation</button><button onClick={() => setPhase('desktop')}>Open read-only diagnostics</button></div>
        </>}
      </div>
    </section>}
  </main>;
}
