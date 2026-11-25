import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Desktop } from '../shell/Desktop';
import type { Snapshot } from '../api/types';
import { createStationClient } from './client';
import type { IdentityReport, StationReport } from './contract';
import { readIdentity, readStation, signIn, signOut } from './transport';
import '../startup/startup.css';
import './station.css';

type AuthPhase = 'CHECKING' | 'SIGNED_OUT' | 'SIGNING_IN' | 'SIGNED_IN' | 'UNAVAILABLE' | 'SIGNING_OUT' | 'LOGOUT_PENDING';
type AuthState = {phase: AuthPhase; identity: IdentityReport | null; message: string; epoch?: number};

function StationDesktop({identity, epoch, denied, logout}: {identity: IdentityReport; epoch: number; denied: (epoch: number) => void; logout: () => void}) {
  const expired = useCallback(() => denied(epoch), [denied, epoch]);
  const [report, setReport] = useState<StationReport | null>(null);
  const [connecting, setConnecting] = useState(true);
  const refreshRef = useRef<(() => void) | null>(null);
  useEffect(() => {
    let alive = true, busy = false;
    async function refresh() {
      if (busy || !alive) return;
      busy = true;
      try {
        const result = await readStation();
        if (!alive) return;
        if (result.status === 'AVAILABLE') setReport(result.report);
        else { setReport(null); if (result.status === 'ACCESS_DENIED') expired(); }
        setConnecting(false);
      } finally { busy = false; }
    }
    refreshRef.current = () => { void refresh(); };
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 5000);
    return () => { alive = false; refreshRef.current = null; window.clearInterval(timer); };
  }, [expired]);
  const client = useMemo(() => report ? createStationClient(report, expired) : null, [report, expired]);
  const refresh = () => refreshRef.current?.();
  if (!report || !client) return <main className="startup station-startup"><header className="mode-banner"><strong>VISION</strong><span>VENTUNO · read-only access</span></header><section className="window station-login" role="dialog" aria-labelledby="station-connection-title"><div className="title-bar"><h1 className="title-bar-text" id="station-connection-title">{connecting ? 'Connecting to VENTUNO' : 'Connection lost'}</h1></div><div className="window-body"><p role="status">{connecting ? 'Waiting for the station report…' : 'Station data is unavailable. Retrying automatically.'}</p><p>Signed in as {identity.username}.</p><div className="startup-actions"><button onClick={refresh}>Retry connection</button><button onClick={logout}>Sign out</button></div></div></section></main>;
  const snapshot: Snapshot = {
    schema: 'client-view-v1', source: 'real', connection: 'API_AVAILABLE', readiness: 'UNKNOWN', observedAt: null,
    reportTime: report.capturedAt, reason: report.coreConnection === 'NOT_CONNECTED' ? 'Vision Core is not connected.' : 'Station report received. Readiness is unknown.', components: [],
  };
  const owner = `${identity.username}:${report.instanceId}:${report.sessionId ?? ''}:${report.sessionViewId ?? ''}`;
  return <Desktop key={owner} client={client} snapshot={snapshot} refresh={refresh} station={{identity, report, refresh, logout}}/>;
}

/** A station build has real authentication and cannot switch to demo by URL. */
export function StationStartup() {
  const [auth, setAuth] = useState<AuthState>({phase: 'CHECKING', identity: null, message: 'Checking your session…'});
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const control = useRef({version: 0, busy: false, pendingLogout: false, identity: null as IdentityReport | null, unavailable: false});
  const denied = useCallback((epoch: number) => {
    if (control.current.pendingLogout || epoch !== control.current.version) return;
    control.current.version++; control.current.busy = false; control.current.identity = null; control.current.unavailable = false;
    setAuth({phase: 'SIGNED_OUT', identity: null, message: 'Your session ended. Sign in again.'});
  }, []);
  const logout = useCallback(async () => {
    const version = ++control.current.version;
    control.current.busy = true; control.current.pendingLogout = true; control.current.identity = null;
    setAuth({phase: 'SIGNING_OUT', identity: null, message: 'Signing out…'});
    const result = await signOut();
    if (version !== control.current.version) return;
    control.current.busy = false;
    if (result.status === 'AVAILABLE' || result.status === 'ACCESS_DENIED') {
      control.current.pendingLogout = false; control.current.unavailable = false;
      setAuth({phase: 'SIGNED_OUT', identity: null, message: 'Signed out.'});
    } else {
      control.current.unavailable = true;
      setAuth({phase: 'LOGOUT_PENDING', identity: null, message: 'Connection unavailable. Sign-out is not confirmed yet; retrying automatically.'});
    }
  }, []);
  const checkSession = useCallback(async () => {
    if (control.current.busy) return;
    if (control.current.pendingLogout) { await logout(); return; }
    const version = control.current.version;
    control.current.busy = true;
    const result = await readIdentity();
    if (version !== control.current.version) return;
    control.current.busy = false;
    if (result.status === 'AVAILABLE') {
      if (control.current.identity && (control.current.identity.username !== result.report.username || control.current.identity.expiresAt !== result.report.expiresAt)) control.current.version++;
      control.current.identity = result.report; control.current.unavailable = false;
      setAuth({phase: 'SIGNED_IN', identity: result.report, message: '', epoch: control.current.version});
    } else if (result.status === 'ACCESS_DENIED') {
      const expired = control.current.identity !== null;
      control.current.identity = null; control.current.unavailable = false;
      setAuth({phase: 'SIGNED_OUT', identity: null, message: expired ? 'Your session ended. Sign in again.' : 'Sign in to the Vision workstation.'});
    } else {
      control.current.identity = null; control.current.unavailable = true;
      setAuth({phase: 'UNAVAILABLE', identity: null, message: 'Connection unavailable. Retrying automatically.'});
    }
  }, [logout]);
  useEffect(() => {
    const state = control.current;
    let alive = true;
    let timer: number | undefined;
    async function poll() {
      await checkSession();
      if (alive) timer = window.setTimeout(() => { void poll(); }, control.current.unavailable || control.current.pendingLogout ? 5000 : 15000);
    }
    void poll();
    return () => { alive = false; window.clearTimeout(timer); state.version++; state.busy = false; };
  }, [checkSession]);

  async function login() {
    if (control.current.pendingLogout) return;
    const secret = password;
    setPassword('');
    const version = ++control.current.version;
    control.current.busy = true;
    setAuth({phase: 'SIGNING_IN', identity: null, message: 'Signing in…'});
    const result = await signIn(username, secret);
    if (version !== control.current.version) return;
    control.current.busy = false;
    if (result.status === 'AVAILABLE') {
      control.current.identity = result.report; control.current.unavailable = false;
      setAuth({phase: 'SIGNED_IN', identity: result.report, message: '', epoch: version});
    } else {
      control.current.identity = null;
      control.current.unavailable = result.status === 'UNAVAILABLE';
      setAuth({phase: result.status === 'UNAVAILABLE' ? 'UNAVAILABLE' : 'SIGNED_OUT', identity: null, message:
        result.status === 'ACCESS_DENIED' ? 'Incorrect user name or password.' : result.status === 'RATE_LIMITED' ? 'Too many attempts. Try again shortly.' : 'Connection unavailable. Try again when the station is reachable.'});
    }
  }

  if (auth.phase === 'SIGNED_IN' && auth.identity) return <StationDesktop identity={auth.identity} epoch={auth.epoch!} denied={denied} logout={() => { void logout(); }}/>;
  const busy = ['CHECKING','SIGNING_IN','SIGNING_OUT'].includes(auth.phase);
  const pendingLogout = auth.phase === 'LOGOUT_PENDING' || auth.phase === 'SIGNING_OUT';
  return <main className="startup station-startup">
    <header className="mode-banner"><strong>VISION</strong><span>VENTUNO workstation</span></header>
    <section className="window station-login" role="dialog" aria-labelledby="station-login-title">
      <div className="title-bar"><h1 className="title-bar-text" id="station-login-title">{pendingLogout ? 'Vision sign out' : 'Welcome to Vision'}</h1></div>
      <div className="window-body">
        <div className="station-login-heading"><span aria-hidden="true">V</span><div><h2>Vision Workstation</h2><p>Read-only access to VENTUNO</p></div></div>
        <p role="status" className="station-login-message">{globalThis.isSecureContext ? auth.message : 'A secure connection is required. Open the station HTTPS address.'}</p>
        {!pendingLogout && <form onSubmit={event => { event.preventDefault(); if (!busy) void login(); }}>
          <div className="login-fields">
            <label htmlFor="station-username">User name</label><input id="station-username" name="username" autoComplete="username" maxLength={64} value={username} onChange={event => setUsername(event.target.value)} disabled={busy || !globalThis.isSecureContext} required/>
            <label htmlFor="station-password">Password</label><input id="station-password" name="password" type="password" autoComplete="current-password" maxLength={1024} value={password} onChange={event => setPassword(event.target.value)} disabled={busy || !globalThis.isSecureContext} required/>
          </div>
          <div className="startup-actions">{auth.phase === 'UNAVAILABLE' && <button type="button" onClick={() => { void checkSession(); }}>Retry connection</button>}<button type="submit" disabled={busy || !username || !password || !globalThis.isSecureContext}>Sign in</button></div>
        </form>}
        {pendingLogout && <div className="startup-actions"><button onClick={() => { void logout(); }} disabled={busy}>Retry sign out</button></div>}
        <p className="fine-print">Vision keeps control of the system. Signing in opens its desktop client.</p>
      </div>
    </section>
  </main>;
}
