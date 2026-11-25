/** Form feedback only. The server enforces its credential policy independently. */
export function passwordChangeProblem(currentPassword: string, newPassword: string, confirmation: string): string | null {
  if (!currentPassword) return 'Enter your current password.';
  if (new TextEncoder().encode(currentPassword).length > 1024) return 'The current password is too long.';
  if (Array.from(newPassword).length < 12) return 'Use at least 12 characters for your new password.';
  if (new TextEncoder().encode(newPassword).length > 1024) return 'The new password is too long. Use at most 1024 UTF-8 bytes.';
  if (newPassword === currentPassword) return 'Choose a different password from your current one.';
  if (newPassword !== confirmation) return 'The new passwords do not match.';
  return null;
}
