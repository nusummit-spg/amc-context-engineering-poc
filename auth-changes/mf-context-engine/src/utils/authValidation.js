/**
 * Client-side validation for the login form.
 *
 * These checks only exist to give fast, friendly inline feedback before a
 * network round-trip — they are never the source of truth for whether
 * credentials are valid. The backend (`/api/auth/login`) always re-validates
 * everything server-side regardless of what passes here.
 */

export function validateUserId(rawUserId) {
  const value = (rawUserId || "").trim();
  if (!value) return "Enter your user ID";
  if (value.length > 128) return "User ID is too long";
  return null;
}

export function validatePassword(rawPassword) {
  if (!rawPassword) return "Enter your password";
  if (rawPassword.length > 256) return "Password is too long";
  return null;
}

/** Runs both field validators; returns an errors object (empty when the form is valid). */
export function validateLoginForm({ userId, password }) {
  const errors = {};
  const userIdError = validateUserId(userId);
  if (userIdError) errors.userId = userIdError;
  const passwordError = validatePassword(password);
  if (passwordError) errors.password = passwordError;
  return errors;
}
