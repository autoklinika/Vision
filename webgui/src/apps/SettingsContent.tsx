import { useEffect, useRef, useState } from 'react';
import type { StationPresentation } from '../station/client';
import { passwordChangeProblem } from '../station/password';

export function SettingsContent({station}: {station?: StationPresentation}) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [message, setMessage] = useState('');
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const clear = () => { setCurrentPassword(''); setNewPassword(''); setConfirmation(''); };

  async function submit() {
    if (!station || station.accountBusy) return;
    const problem = passwordChangeProblem(currentPassword, newPassword, confirmation);
    if (problem) { setMessage(problem); return; }
    const previous = currentPassword, next = newPassword;
    clear(); setMessage('Changing your password…');
    const result = await station.changePassword(previous, next);
    if (!mounted.current) return;
    if (result.status === 'CURRENT_PASSWORD_INVALID') setMessage('The current password is incorrect. Enter your passwords again.');
    else if (result.status === 'PASSWORD_REJECTED') setMessage('The new password was not accepted. Use a different password with at least 12 characters.');
    else if (result.status === 'RATE_LIMITED') setMessage('Too many attempts. Wait a minute before trying again.');
    // Success, expired session and uncertain outcome are handled by the
    // authentication owner, including when this window has already closed.
  }

  return <div className="settings-content">
    <div className="app-heading"><span className="status-mark" aria-hidden="true">⚙</span><div><h2>Your account</h2><p>{station ? `Signed in as ${station.identity.username}` : 'Account settings require a signed-in station session.'}</p></div></div>
    <fieldset><legend>Change password</legend>
      {station ? <form onSubmit={event => { event.preventDefault(); void submit(); }}>
        <p>Choose a new password for your Vision account.</p>
        <div className="password-fields">
          <label htmlFor="settings-current-password">Current password</label><input id="settings-current-password" name="currentPassword" type="password" autoComplete="current-password" maxLength={1024} value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} disabled={station.accountBusy} required/>
          <label htmlFor="settings-new-password">New password</label><input id="settings-new-password" name="newPassword" type="password" autoComplete="new-password" maxLength={1024} value={newPassword} onChange={event => setNewPassword(event.target.value)} disabled={station.accountBusy} required aria-describedby="password-guidance"/>
          <label htmlFor="settings-confirm-password">Confirm new password</label><input id="settings-confirm-password" name="confirmation" type="password" autoComplete="new-password" maxLength={1024} value={confirmation} onChange={event => setConfirmation(event.target.value)} disabled={station.accountBusy} required/>
        </div>
        <p id="password-guidance" className="fine-print">Use at least 12 characters. Changing your password signs out all sessions for this account.</p>
        <p role="status" className="password-message">{message}</p>
        <div className="app-actions"><button type="submit" disabled={station.accountBusy || !currentPassword || !newPassword || !confirmation}>{station.accountBusy ? 'Changing password…' : 'Change password'}</button><button type="button" disabled={station.accountBusy} onClick={() => { clear(); setMessage(''); }}>Clear fields</button></div>
      </form> : <><p>Open the station WebGUI and sign in to change your own password.</p><button disabled>Change password</button></>}
    </fieldset>
  </div>;
}
