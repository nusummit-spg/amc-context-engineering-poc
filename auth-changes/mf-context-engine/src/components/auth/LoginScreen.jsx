import React, { useState, useRef, useEffect } from "react";
import { useAppState } from "../../state/AppState";
import { validateLoginForm } from "../../utils/authValidation";
import SealMotif from "./SealMotif";
import "./LoginScreen.css";

export default function LoginScreen() {
  const { login } = useAppState();

  const [userId, setUserId] = useState(() => {
    try {
      return localStorage.getItem("ns_cg_remembered_user_v1") || "";
    } catch {
      return "";
    }
  });
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(() => {
    try {
      const pref = localStorage.getItem("ns_cg_remember_me_v1");
      if (pref !== null) {
        return pref === "true";
      }
      return Boolean(localStorage.getItem("ns_cg_remembered_user_v1"));
    } catch {
      return false;
    }
  });

  const [fieldErrors, setFieldErrors] = useState({});
  const [authError, setAuthError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successUser, setSuccessUser] = useState(null);
  const [isExiting, setIsExiting] = useState(false);
  const [animState, setAnimState] = useState("settle");
  const [showRegisterHint, setShowRegisterHint] = useState(false);

  const userIdInputRef = useRef(null);
  const passwordInputRef = useRef(null);
  const isMountedRef = useRef(true);

  // Autofocus: focus Password if User ID is already remembered, else focus User ID
  useEffect(() => {
    isMountedRef.current = true;
    if (userId.trim() && passwordInputRef.current) {
      passwordInputRef.current.focus();
    } else if (userIdInputRef.current) {
      userIdInputRef.current.focus();
    }
    return () => {
      isMountedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRememberMeChange = (e) => {
    const checked = e.target.checked;
    setRememberMe(checked);
    try {
      if (checked) {
        localStorage.setItem("ns_cg_remember_me_v1", "true");
        if (userId.trim()) {
          localStorage.setItem("ns_cg_remembered_user_v1", userId.trim());
        }
      } else {
        localStorage.setItem("ns_cg_remember_me_v1", "false");
        localStorage.removeItem("ns_cg_remembered_user_v1");
      }
    } catch {}
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isSubmitting || successUser) return;

    setAuthError(null);

    const cleanUserId = userId.trim();
    const errors = validateLoginForm({ userId: cleanUserId, password });

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);

    try {
      // Credential validation always happens on the backend — this call hits
      // POST /api/auth/login and never inspects a local password list.
      const res = await login(cleanUserId, password, rememberMe);

      if (res?.success) {
        // Persist or clear remembered user based on rememberMe checkbox
        try {
          if (rememberMe) {
            localStorage.setItem("ns_cg_remembered_user_v1", cleanUserId);
            localStorage.setItem("ns_cg_remember_me_v1", "true");
          } else {
            localStorage.removeItem("ns_cg_remembered_user_v1");
            localStorage.setItem("ns_cg_remember_me_v1", "false");
          }
        } catch {}

        // Successful authentication transition
        setSuccessUser(res.user);
        setAnimState("success");

        // Hold display name confirmation on button for ~400ms, then trigger exit transition
        setTimeout(() => {
          setIsExiting(true);
          // Allow exit animation (~320ms) to complete before handing off
          setTimeout(() => {
            if (res.commit) {
              res.commit();
            }
          }, 320);
        }, 400);
      } else {
        setIsSubmitting(false);
        setAuthError(res?.error || "That User ID or password doesn't match our records.");
      }
    } catch (err) {
      setIsSubmitting(false);
      setAuthError(err?.message || "Sign-in failed. Please try again.");
    }
  };

  const handleUserIdChange = (e) => {
    const val = e.target.value;
    setUserId(val);
    if (fieldErrors.userId) {
      setFieldErrors((prev) => ({ ...prev, userId: null }));
    }
    if (authError) {
      setAuthError(null);
    }
    if (rememberMe) {
      try {
        if (val.trim()) {
          localStorage.setItem("ns_cg_remembered_user_v1", val.trim());
        } else {
          localStorage.removeItem("ns_cg_remembered_user_v1");
        }
      } catch {}
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

  const isFormDisabled = isSubmitting || !!successUser;

  return (
    <div className="login-viewport">
      {/* Left Form Panel */}
      <div className={`login-panel login-panel--form ${isExiting ? "is-exiting" : ""}`}>
        <div className="login-panel-inner">
          <div className="login-brand">
            <div className="login-logo" aria-hidden="true">
              <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="1" y="1" width="30" height="30" rx="7" stroke="#15181D" strokeWidth="1.4" />
                <path
                  d="M11 20V12l5-2.5 5 2.5v8"
                  stroke="#15181D"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path d="M11 20h10" stroke="#15181D" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </div>
            <span className="login-brand-name">AMC Context Engine</span>
          </div>

          <h1 className="login-title">Welcome back</h1>
          <p className="login-subhead">Sign in to continue to your regulatory intelligence workspace.</p>

          <form className="login-form" onSubmit={handleSubmit} noValidate>
            {/* User ID Field */}
            <div className="login-field-group">
              <label htmlFor="login-user-id" className="login-label">
                User ID
              </label>
              <div className="login-input-wrapper">
                <span className="login-input-icon" aria-hidden="true">
                  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 6.5 10 11l7-4.5" />
                    <rect x="3" y="4" width="14" height="12" rx="2" />
                  </svg>
                </span>
                <input
                  id="login-user-id"
                  ref={userIdInputRef}
                  type="text"
                  className={`login-input ${fieldErrors.userId ? "has-error" : ""}`}
                  placeholder="e.g. sarah.compliance"
                  value={userId}
                  onChange={handleUserIdChange}
                  disabled={isFormDisabled}
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck="false"
                  aria-invalid={!!fieldErrors.userId}
                  aria-describedby={fieldErrors.userId ? "login-user-id-error" : undefined}
                />
              </div>
              {fieldErrors.userId && (
                <div className="login-inline-error" id="login-user-id-error" role="alert">
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
                <span className="login-input-icon" aria-hidden="true">
                  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="4" y="9" width="12" height="8" rx="2" />
                    <path d="M6.5 9V6a3.5 3.5 0 0 1 7 0v3" />
                  </svg>
                </span>
                <input
                  id="login-password"
                  ref={passwordInputRef}
                  type={showPassword ? "text" : "password"}
                  className={`login-input login-input--password ${fieldErrors.password ? "has-error" : ""}`}
                  placeholder="••••••••"
                  value={password}
                  onChange={handlePasswordChange}
                  disabled={isFormDisabled}
                  autoComplete="current-password"
                  aria-invalid={!!fieldErrors.password}
                  aria-describedby={fieldErrors.password ? "login-password-error" : undefined}
                />
                <button
                  type="button"
                  className="login-password-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  tabIndex={0}
                  disabled={isFormDisabled}
                >
                  {showPassword ? (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
              {fieldErrors.password && (
                <div className="login-inline-error" id="login-password-error" role="alert">
                  {fieldErrors.password}
                </div>
              )}
            </div>

            {/* Remember Me + Forgot Password Row */}
            <div className="login-options-row">
              <label className="login-remember-me">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={handleRememberMeChange}
                  disabled={isFormDisabled}
                />
                <span>Remember me</span>
              </label>
              <button
                type="button"
                className="login-forgot-link"
                disabled={isFormDisabled}
                onClick={() => setAuthError("Password resets aren't available yet. Contact your administrator.")}
              >
                Forgot password?
              </button>
            </div>

            {/* Quiet Feedback Area */}
            <div className="login-feedback-area" aria-live="polite">
              {authError && (
                <p className="login-auth-error" role="alert">
                  {authError}
                </p>
              )}
            </div>

            {/* Primary Action */}
            <div className="login-action-group">
              <button
                type="submit"
                className={`login-submit-btn ${successUser ? "is-success" : ""}`}
                disabled={isFormDisabled}
              >
                {successUser ? (
                  `Welcome, ${successUser.display_name}…`
                ) : isSubmitting ? (
                  <>
                    <span className="login-spinner" aria-hidden="true" />
                    Signing in…
                  </>
                ) : (
                  "Sign In"
                )}
              </button>
            </div>

            {/* Registration — architecture is in place; disabled pending DB-backed accounts */}
            <div className="login-register-row">
              <span>New here?</span>
              <span
                className="login-register-tooltip-wrapper"
                onMouseEnter={() => setShowRegisterHint(true)}
                onMouseLeave={() => setShowRegisterHint(false)}
                onFocus={() => setShowRegisterHint(true)}
                onBlur={() => setShowRegisterHint(false)}
              >
                <button
                  type="button"
                  className="login-register-link"
                  disabled
                  aria-describedby="login-register-tooltip"
                >
                  Create account
                </button>
                <span className="login-register-badge">Coming soon</span>
                {showRegisterHint && (
                  <span className="login-register-tooltip" role="tooltip" id="login-register-tooltip">
                    Self-service registration is on the way — for now, ask your administrator to set up your account.
                  </span>
                )}
              </span>
            </div>
          </form>

          <p className="login-footnote">© {new Date().getFullYear()} NuSummit Technologies. All rights reserved.</p>
        </div>
      </div>

      {/* Right Visual Panel */}
      <div className="login-panel login-panel--visual" aria-hidden="true">
        <div className="login-visual-inner">
          <SealMotif animState={animState} className="login-seal" />
          <p className="login-visual-caption">NuSummit SPG</p>
        </div>
      </div>
    </div>
  );
}
