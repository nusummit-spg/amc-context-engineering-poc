import React, { useState, useRef, useEffect } from "react";
import { useAppState } from "../../state/AppState";
import SealMotif from "./SealMotif";
import "./LoginScreen.css";

export default function LoginScreen() {
  const { login } = useAppState();

  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const [fieldErrors, setFieldErrors] = useState({});
  const [authError, setAuthError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successUser, setSuccessUser] = useState(null);
  const [isExiting, setIsExiting] = useState(false);
  const [animState, setAnimState] = useState("settle");

  const userIdInputRef = useRef(null);

  // Autofocus User ID field on mount
  useEffect(() => {
    if (userIdInputRef.current) {
      userIdInputRef.current.focus();
    }
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (isSubmitting || successUser) return;

    // Reset previous errors
    setAuthError(null);
    const errors = {};

    const cleanUserId = userId.trim();
    if (!cleanUserId) {
      errors.userId = "Enter your user ID";
    }

    if (!password) {
      errors.password = "Enter your password";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);

    // Call login helper in AppState
    const res = login(cleanUserId, password);

    if (res.success) {
      // Successful authentication transition
      setSuccessUser(res.user);
      setAnimState("success");

      // Hold display name confirmation on button for ~500ms, then trigger exit transition
      setTimeout(() => {
        setIsExiting(true);
        // Allow exit animation (~400ms) to complete before handing off
        setTimeout(() => {
          if (res.commit) {
            res.commit();
          }
        }, 400);
      }, 500);
    } else {
      setIsSubmitting(false);
      setAuthError("That User ID or password doesn't match our records.");
    }
  };

  const handleUserIdChange = (e) => {
    setUserId(e.target.value);
    if (fieldErrors.userId) {
      setFieldErrors((prev) => ({ ...prev, userId: null }));
    }
    if (authError) {
      setAuthError(null);
    }
  };

  const handlePasswordChange = (e) => {
    setPassword(e.target.value);
    if (fieldErrors.password) {
      setFieldErrors((prev) => ({ ...prev, password: null }));
    }
    if (authError) {
      setAuthError(null);
    }
  };

  return (
    <div className="login-viewport">
      <div className="login-layout">
        {/* Left Form Pane */}
        <div className={`login-form-pane ${isExiting ? "is-exiting" : ""}`}>
          <header className="login-header">
            <h1 className="login-title">
              <span className="login-seal-glyph" aria-hidden="true">⬩</span>
              AMC Context Engine
            </h1>
            <p className="login-subhead">
              Regulatory intelligence, with provenance.
            </p>
          </header>

          <form className="login-form" onSubmit={handleSubmit} noValidate>
            {/* User ID Field */}
            <div className="login-field-group">
              <label htmlFor="login-user-id" className="login-label">
                User ID
              </label>
              <div className="login-input-wrapper">
                <input
                  id="login-user-id"
                  ref={userIdInputRef}
                  type="text"
                  className={`login-input ${fieldErrors.userId ? "has-error" : ""}`}
                  placeholder="e.g. sarah.compliance"
                  value={userId}
                  onChange={handleUserIdChange}
                  disabled={isSubmitting || !!successUser}
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck="false"
                />
              </div>
              {fieldErrors.userId && (
                <div className="login-inline-error" role="alert">
                  {fieldErrors.userId}
                </div>
              )}
            </div>

            {/* Password Field */}
            <div className="login-field-group">
              <label htmlFor="login-password" className="login-label">
                Password
              </label>
              <div className="login-input-wrapper">
                <input
                  id="login-password"
                  type={showPassword ? "text" : "password"}
                  className={`login-input login-input--password ${fieldErrors.password ? "has-error" : ""}`}
                  placeholder="••••••••"
                  value={password}
                  onChange={handlePasswordChange}
                  disabled={isSubmitting || !!successUser}
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="login-password-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  tabIndex={0}
                  disabled={isSubmitting || !!successUser}
                >
                  {showPassword ? (
                    // Eye slash icon
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    // Eye icon
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
              {fieldErrors.password && (
                <div className="login-inline-error" role="alert">
                  {fieldErrors.password}
                </div>
              )}
            </div>

            {/* Primary Action */}
            <div className="login-action-group">
              <button
                type="submit"
                className={`login-submit-btn ${successUser ? "is-success" : ""}`}
                disabled={isSubmitting}
              >
                {successUser
                  ? `Signing in as ${successUser.display_name}…`
                  : "Sign in"}
              </button>
            </div>

            {/* Quiet Feedback Area */}
            <div className="login-feedback-area" aria-live="polite">
              {authError && (
                <p className="login-auth-error">
                  {authError}
                </p>
              )}
            </div>
          </form>
        </div>

        {/* Right Seal Graphic Motif */}
        <SealMotif animState={animState} />
      </div>
    </div>
  );
}
