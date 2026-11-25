"""Local reader authentication; all credentials and files are synthetic."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from vision_api import identity
from vision_api.access import AccessDenied
from vision_api.identity import (CurrentPasswordInvalid, IdentityStore, InvalidIdentityStore,
                                 PasswordRejected, RateLimited, parse_session_cookie, provision_account)

PASSWORD = 'synthetic-reader-password-only'


class Clock:
    def __init__(self):
        self.now = 1_800_000_000

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class IdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'accounts.json'
        self.clock = Clock()
        provision_account(self.path, 'operator', PASSWORD)
        self.store = IdentityStore(self.path, clock=self.clock)

    def login(self, username='operator', password=PASSWORD, client='local-peer'):
        return self.store.login(username, password, client)

    def test_private_persistent_scrypt_records_use_random_salts(self):
        provision_account(self.path, 'second', PASSWORD)
        document = json.loads(self.path.read_text())
        self.assertEqual(document['schema'], identity.ACCOUNT_SCHEMA)
        self.assertNotIn(PASSWORD, self.path.read_text())
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        one, two = document['accounts']
        self.assertEqual(one['role'], 'reader')
        self.assertEqual(one['kdf'], 'scrypt-n32768-r8-p1')
        self.assertRegex(one['salt'], r'^[0-9a-f]{64}$')
        self.assertRegex(one['hash'], r'^[0-9a-f]{64}$')
        self.assertNotEqual(one['salt'], two['salt'])
        self.assertNotEqual(one['hash'], two['hash'])

    def test_login_has_closed_reader_report_and_only_hashed_tokens_in_store(self):
        before = self.path.read_bytes()
        token, report = self.login()
        self.assertRegex(token, r'^[A-Za-z0-9_-]{43}$')
        self.assertEqual(set(report), {'schema', 'authenticated', 'username', 'role', 'expiresAt'})
        self.assertEqual(report['schema'], 'vision.api.identity.v1')
        self.assertIs(report['authenticated'], True)
        self.assertEqual(report['username'], 'operator')
        self.assertEqual(report['role'], 'reader')
        self.assertRegex(report['expiresAt'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        self.assertEqual(self.store.session(token, touch=False), report)
        self.assertEqual(list(self.store._sessions), [hashlib.sha256(token.encode('ascii')).digest()])
        self.assertNotIn(token, repr(self.store._sessions))
        self.assertEqual(self.path.read_bytes(), before)

    def test_wrong_and_unknown_credentials_use_scrypt_and_constant_time_comparison(self):
        with (patch.object(identity, '_derive', wraps=identity._derive) as derive,
              patch.object(identity.hmac, 'compare_digest', wraps=identity.hmac.compare_digest) as compare):
            for username in ('operator', 'unknown'):
                with self.assertRaises(AccessDenied):
                    self.login(username, 'wrong-synthetic-password')
            self.assertEqual(derive.call_count, 2)
            self.assertEqual(compare.call_count, 2)
            for call in compare.call_args_list:
                self.assertEqual([len(value) for value in call.args], [32, 32])
        self.assertEqual(self.store._sessions, {})

    def test_logout_is_idempotent_and_revokes_only_selected_session(self):
        first, _ = self.login()
        second, _ = self.login()
        self.store.logout(first)
        self.store.logout(first)
        with self.assertRaises(AccessDenied):
            self.store.session(first)
        self.assertTrue(self.store.session(second)['authenticated'])

    def test_restart_revokes_sessions_but_preserves_accounts(self):
        token, _ = self.login()
        restarted = IdentityStore(self.path, clock=self.clock)
        with self.assertRaises(AccessDenied):
            restarted.session(token)
        replacement, report = restarted.login('operator', PASSWORD, 'local-peer')
        self.assertNotEqual(token, replacement)
        self.assertTrue(report['authenticated'])

    def test_idle_expiry_is_exact_and_observation_does_not_refresh(self):
        token, report = self.login()
        self.clock.advance(identity.IDLE_SECONDS - 1)
        self.assertEqual(self.store.session(token, touch=False)['expiresAt'], report['expiresAt'])
        self.clock.advance(1)
        with self.assertRaises(AccessDenied):
            self.store.session(token, touch=False)

    def test_touch_extends_idle_but_keeps_an_absolute_deadline(self):
        token, original = self.login()
        self.clock.advance(identity.IDLE_SECONDS - 1)
        updated = self.store.session(token, touch=True)
        self.assertGreater(updated['expiresAt'], original['expiresAt'])
        self.clock.advance(1)
        self.assertTrue(self.store.session(token, touch=False)['authenticated'])
        self.clock.advance(identity.IDLE_SECONDS - 1)
        with self.assertRaises(AccessDenied):
            self.store.session(token)

    def test_absolute_expiry_despite_active_client(self):
        token, _ = self.login()
        for _ in range(47):
            self.clock.advance(600)
            self.store.session(token, touch=True)
        self.clock.advance(599)
        self.store.session(token, touch=True)
        self.clock.advance(1)
        with self.assertRaises(AccessDenied):
            self.store.session(token)

    def test_session_capacity_evicts_oldest_authenticated_session(self):
        with patch.object(identity, 'MAX_SESSIONS', 2):
            first, _ = self.login()
            self.clock.advance(1)
            second, _ = self.login()
            self.clock.advance(1)
            third, _ = self.login()
        self.assertEqual(len(self.store._sessions), 2)
        with self.assertRaises(AccessDenied):
            self.store.session(first)
        for token in (second, third):
            self.assertTrue(self.store.session(token)['authenticated'])

    def test_reset_from_other_owner_revokes_even_when_password_is_reused(self):
        token, _ = self.login()
        before = self.path.read_bytes()
        provision_account(self.path, 'operator', PASSWORD, replace=True)
        self.assertNotEqual(self.path.read_bytes(), before)
        with self.assertRaises(AccessDenied):
            self.store.session(token)
        self.assertTrue(self.login()[1]['authenticated'])

    def test_password_reset_rejects_old_password(self):
        new_password = 'new-synthetic-reader-password'
        provision_account(self.path, 'operator', new_password, replace=True)
        with self.assertRaises(AccessDenied):
            self.login()
        self.assertTrue(self.login(password=new_password)[1]['authenticated'])

    def test_account_removal_and_explicit_revoke_remove_sessions(self):
        token, _ = self.login()
        self.store.revoke_user('operator')
        with self.assertRaises(AccessDenied):
            self.store.session(token)
        token, _ = self.login()
        self.path.write_text(json.dumps({'schema': identity.ACCOUNT_SCHEMA, 'accounts': []}))
        with self.assertRaises(AccessDenied):
            self.store.session(token)

    def test_malformed_store_invalidates_sessions_without_repair(self):
        token, _ = self.login()
        original = self.path.read_bytes()
        self.path.write_text('{private-malformed-secret')
        with self.assertRaises(InvalidIdentityStore) as error:
            self.store.session(token)
        self.assertEqual(str(error.exception), 'identity store unavailable')
        self.assertNotIn('private-malformed-secret', str(error.exception))
        self.assertEqual(self.path.read_text(), '{private-malformed-secret')
        self.path.write_bytes(original)
        with self.assertRaises(AccessDenied):
            self.store.session(token)

    def test_malformed_account_documents_are_rejected(self):
        original = json.loads(self.path.read_text())
        variants = []
        for key, value in (('role', 'admin'), ('kdf', 'scrypt-n2-r1-p1'),
                           ('salt', '00'), ('hash', '../secret'), ('username', 'bad user')):
            document = json.loads(json.dumps(original))
            document['accounts'][0][key] = value
            variants.append(json.dumps(document).encode())
        extra = json.loads(json.dumps(original))
        extra['accounts'][0]['extra'] = 'private-secret'
        variants.append(json.dumps(extra).encode())
        duplicate = json.loads(json.dumps(original))
        duplicate['accounts'].append(duplicate['accounts'][0])
        variants.append(json.dumps(duplicate).encode())
        variants.extend([b'{}', b'[]', b'NaN', b'{"schema":"x","schema":"y"}',
                         b'x' * (identity.MAX_ACCOUNT_BYTES + 1)])
        for raw in variants:
            with self.subTest(raw=raw[:32]):
                self.path.write_bytes(raw)
                with self.assertRaises(InvalidIdentityStore):
                    IdentityStore(self.path)

    def test_permission_changes_are_rejected(self):
        token, _ = self.login()
        self.path.chmod(0o644)
        with self.assertRaises(InvalidIdentityStore):
            self.store.session(token)
        with self.assertRaises(InvalidIdentityStore):
            IdentityStore(self.path)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o644)

    def test_symlink_file_and_directory_are_rejected_without_writing_target(self):
        link = self.root / 'link.json'
        link.symlink_to(self.path)
        directory = self.root / 'linkdir'
        directory.symlink_to(self.root, target_is_directory=True)
        original = self.path.read_bytes()
        for path in (link, directory / self.path.name):
            with self.subTest(path=path.name):
                with self.assertRaises(InvalidIdentityStore):
                    IdentityStore(path)
                with self.assertRaises(InvalidIdentityStore):
                    provision_account(path, 'operator', PASSWORD, replace=True)
        self.assertEqual(self.path.read_bytes(), original)

    def test_hardlinks_and_nonregular_files_are_rejected(self):
        os.link(self.path, self.root / 'duplicate.json')
        with self.assertRaises(InvalidIdentityStore):
            IdentityStore(self.path)
        directory = self.root / 'directory'
        directory.mkdir(mode=0o700)
        with self.assertRaises(InvalidIdentityStore):
            IdentityStore(directory)

    def test_repository_and_served_docroot_cannot_contain_account_files(self):
        forbidden = self.root / 'public'
        forbidden.mkdir()
        targets = (identity._REPO / 'not-created-identity-test.json', forbidden / 'accounts.json')
        for path in targets:
            with self.assertRaises(InvalidIdentityStore):
                provision_account(path, 'operator', PASSWORD, forbidden_roots=(forbidden,))
            self.assertFalse(path.exists())

    def test_account_count_and_username_limits_do_not_modify_store(self):
        original = self.path.read_bytes()
        with patch.object(identity, 'MAX_ACCOUNTS', 1):
            with self.assertRaises(ValueError):
                provision_account(self.path, 'second', PASSWORD)
        for username in ('', 'a' * 65, 'bad user', '../bad', 'żółw'):
            with self.subTest(username=username), self.assertRaises(ValueError):
                provision_account(self.path, username, PASSWORD)
        self.assertEqual(self.path.read_bytes(), original)

    def test_password_bounds_apply_before_hashing_and_unicode_is_exact(self):
        original = self.path.read_bytes()
        with patch.object(identity, '_derive', side_effect=AssertionError('must not hash invalid input')):
            for password in ('short', 'x' * 1025, 'ą' * 513, None, 'x\ud800' * 12):
                with self.subTest(password_type=type(password).__name__):
                    with self.assertRaises(ValueError):
                        provision_account(self.path, 'second', password)
                    with self.assertRaises(AccessDenied):
                        self.login(password=password)
        self.assertEqual(self.path.read_bytes(), original)
        provision_account(self.path, 'unicode', 'ąęćłńóśźż-12345')
        self.assertTrue(self.login('unicode', 'ąęćłńóśźż-12345', 'new-peer')[1]['authenticated'])

    def test_interrupted_atomic_reset_keeps_original_file(self):
        original = self.path.read_bytes()
        with patch.object(identity.os, 'replace', side_effect=OSError('private-path')):
            with self.assertRaises(InvalidIdentityStore):
                provision_account(self.path, 'operator', 'another-synthetic-password', replace=True)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.root.glob('.identity-*')), [])

    def test_concurrent_provisioning_preserves_both_accounts(self):
        errors = []

        def provision(username):
            try:
                provision_account(self.path, username, PASSWORD)
            except Exception as exc:
                errors.append(type(exc).__name__)

        threads = [threading.Thread(target=provision, args=(name,)) for name in ('second', 'third')]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual({row['username'] for row in json.loads(self.path.read_text())['accounts']},
                         {'operator', 'second', 'third'})

    def test_client_rate_limit_cannot_be_bypassed_by_changing_username(self):
        with patch.object(identity, '_derive', return_value=b'\0' * 32) as derive:
            for i in range(identity.MAX_CLIENT_ATTEMPTS):
                with self.assertRaises(AccessDenied):
                    self.login(username='unknown_' + str(i), password='wrong-synthetic-password')
            with self.assertRaises(RateLimited) as error:
                self.login()
            self.assertEqual(error.exception.retry_after, identity.LOGIN_WINDOW_SECONDS)
            self.assertEqual(derive.call_count, identity.MAX_CLIENT_ATTEMPTS)
        self.clock.advance(identity.LOGIN_WINDOW_SECONDS)
        self.assertTrue(self.login()[1]['authenticated'])

    def test_global_rate_limit_applies_across_client_keys(self):
        with patch.object(identity, '_derive', return_value=b'\0' * 32) as derive:
            for i in range(identity.MAX_GLOBAL_ATTEMPTS):
                with self.assertRaises(AccessDenied):
                    self.login(password='wrong-synthetic-password', client='peer-' + str(i))
            with self.assertRaises(RateLimited):
                self.login(client='another-peer')
            self.assertEqual(derive.call_count, identity.MAX_GLOBAL_ATTEMPTS)
        self.assertLessEqual(len(self.store._client_attempts), identity.MAX_GLOBAL_ATTEMPTS)

    def test_malformed_peer_and_token_inputs_fail_without_anonymous_report(self):
        with patch.object(identity, '_derive', side_effect=AssertionError('must not hash')):
            for peer in (None, '', 'a' * 129, 'space peer', 'a\nb'):
                with self.assertRaises(AccessDenied):
                    self.login(client=peer)
        for token in (None, '', 'a' * 42, 'a' * 44, 'a' * 42 + '/', 'a' * 43):
            with self.assertRaises(AccessDenied):
                self.store.session(token)

    def test_clock_rollback_revokes_sessions(self):
        token, _ = self.login()
        self.clock.advance(10)
        self.store.session(token)
        self.clock.advance(-1)
        with self.assertRaises(AccessDenied):
            self.store.session(token)
        self.clock.advance(2)
        with self.assertRaises(AccessDenied):
            self.store.session(token)

    def test_generate_cli_creates_private_password_without_printing_it(self):
        output = self.root / 'initial-password'
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = identity.main(['--accounts', str(self.path), 'provision', 'initial', '--generate-to', str(output)])
        self.assertEqual(status, 0)
        password = output.read_text().rstrip('\n')
        self.assertRegex(password, r'^[A-Za-z0-9_-]{43}$')
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertEqual(stdout.getvalue(), '')
        self.assertNotIn(password, stderr.getvalue())
        self.assertTrue(self.login('initial', password)[1]['authenticated'])

    def test_generate_cli_never_overwrites_existing_password_file_or_account(self):
        output = self.root / 'initial-password'
        output.write_text('existing-secret')
        original = self.path.read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            status = identity.main(['--accounts', str(self.path), 'reset', 'operator', '--generate-to', str(output)])
        self.assertEqual(status, 2)
        self.assertEqual(output.read_text(), 'existing-secret')
        self.assertEqual(self.path.read_bytes(), original)

    def test_failed_provision_removes_only_its_new_password_file(self):
        output = self.root / 'initial-password'
        original = self.path.read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            status = identity.main(['--accounts', str(self.path), 'provision', 'operator', '--generate-to', str(output)])
        self.assertEqual(status, 2)
        self.assertFalse(output.exists())
        self.assertEqual(self.path.read_bytes(), original)

    def test_interactive_cli_reads_getpass_and_confirms_without_stdout(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (patch.object(identity.getpass, 'getpass', side_effect=[PASSWORD, PASSWORD]),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            status = identity.main(['--accounts', str(self.path), 'provision', 'interactive'])
        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), '')
        self.assertNotIn(PASSWORD, stderr.getvalue())

    def test_self_change_persists_and_revokes_all_old_account_sessions_only(self):
        provision_account(self.path, 'second', PASSWORD)
        other_owner = IdentityStore(self.path, clock=self.clock)
        first, _ = self.login()
        second, _ = self.login()
        other_token, _ = other_owner.login('operator', PASSWORD, 'peer')
        unaffected, _ = self.login(username='second')
        original = json.loads(self.path.read_text())
        new_password = 'new-synthetic-self-service-password'
        report = self.store.change_password(first, PASSWORD, new_password)
        self.assertEqual(report, {'schema': 'vision.api.password-change.v1', 'changed': True})
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        replacement = json.loads(self.path.read_text())
        self.assertEqual(original['accounts'][1], replacement['accounts'][1])
        self.assertNotEqual(original['accounts'][0]['salt'], replacement['accounts'][0]['salt'])
        for owner, token in ((self.store, first), (self.store, second), (other_owner, other_token)):
            with self.assertRaises(AccessDenied):
                owner.session(token)
        self.assertTrue(self.store.session(unaffected)['authenticated'])
        with self.assertRaises(AccessDenied):
            other_owner.login('operator', PASSWORD, 'peer')
        self.assertTrue(IdentityStore(self.path).login('operator', new_password, 'peer')[1]['authenticated'])
        self.assertNotIn(new_password, self.path.read_text())
        self.assertNotIn(PASSWORD, repr(report))

    def test_wrong_current_password_preserves_accounts_and_authenticated_session(self):
        token, _ = self.login()
        before = self.path.read_bytes()
        for wrong in ('short', 'wrong-synthetic-current-password'):
            with self.assertRaises(CurrentPasswordInvalid):
                self.store.change_password(token, wrong, 'new-synthetic-reader-password')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(self.store.session(token)['authenticated'])

    def test_new_password_policy_and_unchanged_password_never_modify_store(self):
        token, _ = self.login()
        before = self.path.read_bytes()
        for new in (None, 'short', 'x' * 1025, 'ą' * 513, 'x\ud800' * 12, PASSWORD):
            self.clock.advance(identity.LOGIN_WINDOW_SECONDS)
            with self.assertRaises(PasswordRejected):
                self.store.change_password(token, PASSWORD, new)
            self.assertEqual(self.path.read_bytes(), before)
            self.assertTrue(self.store.session(token)['authenticated'])
        new = 'ąęćłńóśźż-new-password-2026'
        self.store.change_password(token, PASSWORD, new)
        self.assertTrue(self.login(password=new)[1]['authenticated'])

    def test_self_change_authenticates_before_hashing_and_expires_during_hashing(self):
        token, _ = self.login()
        before = self.path.read_bytes()
        with patch.object(identity, '_derive', side_effect=AssertionError('unauthenticated hash')):
            with self.assertRaises(AccessDenied):
                self.store.change_password('x' * 43, PASSWORD, 'new-synthetic-password')
        original_derive = identity._derive
        advanced = False
        def slow_derive(encoded, salt):
            nonlocal advanced
            result = original_derive(encoded, salt)
            if not advanced:
                advanced = True
                self.clock.advance(identity.IDLE_SECONDS)
            return result
        with patch.object(identity, '_derive', side_effect=slow_derive):
            with self.assertRaises(AccessDenied):
                self.store.change_password(token, PASSWORD, 'new-synthetic-password')
        self.assertEqual(self.path.read_bytes(), before)

    def test_password_change_throttle_is_shared_by_account_sessions_but_separate_from_login(self):
        first, _ = self.login()
        second, _ = self.login()
        for index in range(identity.MAX_PASSWORD_CHANGE_ATTEMPTS):
            with self.assertRaises(CurrentPasswordInvalid):
                self.store.change_password((first, second)[index % 2], 'wrong-synthetic-password', 'new-synthetic-password')
        with patch.object(identity, '_derive', side_effect=AssertionError('throttled hash')):
            with self.assertRaises(RateLimited) as error:
                self.store.change_password(second, PASSWORD, 'new-synthetic-password')
        self.assertEqual(error.exception.retry_after, identity.LOGIN_WINDOW_SECONDS)
        self.assertTrue(self.login()[1]['authenticated'])
        self.clock.advance(identity.LOGIN_WINDOW_SECONDS)
        self.assertTrue(self.store.change_password(first, PASSWORD, 'new-synthetic-password')['changed'])

    def test_external_reset_during_current_password_verification_wins(self):
        token, _ = self.login()
        original_derive = identity._derive
        reset = False
        reset_document = None
        def concurrent_reset(encoded, salt):
            nonlocal reset, reset_document
            result = original_derive(encoded, salt)
            if not reset:
                reset = True
                provision_account(self.path, 'operator', 'external-reset-password', replace=True)
                reset_document = self.path.read_bytes()
            return result
        with patch.object(identity, '_derive', side_effect=concurrent_reset):
            with self.assertRaises(AccessDenied):
                self.store.change_password(token, PASSWORD, 'losing-self-service-password')
        self.assertEqual(self.path.read_bytes(), reset_document)
        self.assertTrue(self.login(password='external-reset-password')[1]['authenticated'])

    def test_external_account_removal_cannot_be_undone_by_self_change(self):
        token, _ = self.login()
        original_derive = identity._derive
        removed = False
        def concurrent_remove(encoded, salt):
            nonlocal removed
            result = original_derive(encoded, salt)
            if not removed:
                removed = True
                self.path.write_text(json.dumps({'schema': identity.ACCOUNT_SCHEMA, 'accounts': []}))
            return result
        with patch.object(identity, '_derive', side_effect=concurrent_remove):
            with self.assertRaises(AccessDenied):
                self.store.change_password(token, PASSWORD, 'new-synthetic-password')
        self.assertEqual(json.loads(self.path.read_text())['accounts'], [])

    def test_other_account_added_during_hashing_is_preserved(self):
        token, _ = self.login()
        original_derive = identity._derive
        added = False
        def concurrent_provision(encoded, salt):
            nonlocal added
            result = original_derive(encoded, salt)
            if not added:
                added = True
                provision_account(self.path, 'second', PASSWORD)
            return result
        with patch.object(identity, '_derive', side_effect=concurrent_provision):
            self.store.change_password(token, PASSWORD, 'new-synthetic-password')
        self.assertEqual({row['username'] for row in json.loads(self.path.read_text())['accounts']}, {'operator', 'second'})
        self.assertTrue(self.login(username='second')[1]['authenticated'])

    def test_concurrent_self_changes_have_one_winner_without_lost_updates(self):
        other = IdentityStore(self.path, clock=self.clock)
        first, _ = self.login()
        second, _ = other.login('operator', PASSWORD, 'peer')
        barrier = threading.Barrier(2)
        original_derive = identity._derive
        def synchronized_current(encoded, salt):
            result = original_derive(encoded, salt)
            if encoded == PASSWORD.encode():
                barrier.wait(timeout=3)
            return result
        outcomes = []
        def change(owner, token, password):
            try:
                owner.change_password(token, PASSWORD, password)
                outcomes.append(('changed', password))
            except AccessDenied:
                outcomes.append(('denied', password))
            except Exception as error:
                outcomes.append((type(error).__name__, password))
        with patch.object(identity, '_derive', side_effect=synchronized_current):
            threads = [threading.Thread(target=change, args=(owner, token, password))
                       for owner, token, password in ((self.store, first, 'first-synthetic-password'),
                                                      (other, second, 'second-synthetic-password'))]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(5)
                self.assertFalse(thread.is_alive())
        self.assertEqual(sorted(status for status, _ in outcomes), ['changed', 'denied'])
        winner = next(password for status, password in outcomes if status == 'changed')
        self.assertTrue(self.login(password=winner)[1]['authenticated'])

    def test_failed_publish_preserves_original_and_post_replace_failure_revokes_old_sessions(self):
        provision_account(self.path, 'second', PASSWORD)
        token, _ = self.login()
        before = self.path.read_bytes()
        with patch.object(identity.os, 'replace', side_effect=OSError('private path')):
            with self.assertRaises(InvalidIdentityStore):
                self.store.change_password(token, PASSWORD, 'new-synthetic-password')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(self.store.session(token)['authenticated'])
        fsync = identity.os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError('private directory failed')
            return fsync(fd)
        with patch.object(identity.os, 'fsync', side_effect=fail_directory):
            with self.assertRaises(InvalidIdentityStore):
                self.store.change_password(token, PASSWORD, 'new-synthetic-password')
        with self.assertRaises(AccessDenied):
            self.store.session(token)
        self.assertTrue(self.login(password='new-synthetic-password')[1]['authenticated'])
        self.assertEqual(json.loads(before)['accounts'][1], json.loads(self.path.read_text())['accounts'][1])
        self.assertEqual(list(self.root.glob('.identity-*')), [])


class CookieTests(unittest.TestCase):
    token = 'a' * 43

    def test_only_an_exact_named_token_is_returned(self):
        self.assertIsNone(parse_session_cookie(None))
        self.assertIsNone(parse_session_cookie('preference=dark'))
        self.assertEqual(parse_session_cookie('preference=dark; vision_session=' + self.token), self.token)
        self.assertEqual(parse_session_cookie('__Host-vision_session=' + self.token,
                                             name='__Host-vision_session'), self.token)

    def test_duplicate_or_malformed_cookie_headers_are_denied(self):
        valid = 'vision_session=' + self.token
        bad = [valid + '; ' + valid, 'x=one; x=two; ' + valid,
               valid + ', ' + valid, 'vision_session="' + self.token + '"',
               'vision_session=' + self.token + '=', valid + ';', valid + '\r\nX-User: admin',
               'vision_session=short', 'vision_session=' + self.token + '/',
               'vision_session = ' + self.token, 'x=space here; ' + valid,
               'x=ą; ' + valid, 'x=' + 'a' * identity.MAX_COOKIE_BYTES, '']
        for value in bad:
            with self.subTest(header=value[:50]), self.assertRaises(AccessDenied):
                parse_session_cookie(value)


if __name__ == '__main__':
    unittest.main()
