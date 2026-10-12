"""Signup, login, password reset and email verification pages, plus the styled 404."""
from html import escape
from typing import Optional

from app.pages.player import PlayerView
from app.pages.shell import _shell


def render_signup() -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>SIGN UP</h2>
        <div class="auth-error" id="formError"></div>
        <form id="signupForm">
          <div class="field">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" placeholder="you@example.com" required />
          </div>
          <div class="field">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" placeholder="At least 8 characters" required minlength="8" />
          </div>
          <div class="field">
            <label for="confirmPassword">Confirm password</label>
            <input type="password" id="confirmPassword" name="confirmPassword" placeholder="Re-enter your password" required minlength="8" />
          </div>
          <button class="primary" type="submit">SIGN UP</button>
        </form>
        <div class="auth-switch">Already have an account? <a href="/login">LOG IN</a></div>
      </div>
    </div>
    """
    script = """
    document.getElementById('signupForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const errorEl = document.getElementById('formError');
      errorEl.classList.remove('show');
      const password = document.getElementById('password').value;
      const confirmPassword = document.getElementById('confirmPassword').value;
      if (password !== confirmPassword) {
        errorEl.textContent = 'Passwords do not match.';
        errorEl.classList.add('show');
        return;
      }
      const submitBtn = e.target.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        const res = await fetch('/api/auth/signup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: document.getElementById('email').value,
            password: password,
          }),
        });
        if (res.ok) {
          // Straight to the dashboard, same as the login redirect below.
          window.location.href = '/dashboard';
          return;
        }
        const data = await res.json().catch(() => ({}));
        errorEl.textContent = describeError(data, 'Could not create your account.');
        errorEl.classList.add('show');
      } catch (err) {
        errorEl.textContent = 'Something went wrong. Please try again.';
        errorEl.classList.add('show');
      } finally {
        submitBtn.disabled = false;
      }
    });
    """
    return _shell(title="Sign up — myscape", player=None, body=body, extra_script=script)


def render_signup_coming_soon() -> str:
    """What /signup shows while sign-ups are switched off (see
    app/site_flags.py). Stands in for render_signup, which is untouched so
    re-enabling is just flipping the flag. Existing accounts can still log in,
    hence the link.
    """
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>SIGN UP</h2>
        <p class="verify-email-message signup-closed-message">myscape is coming soon.</p>
        <div class="auth-switch">Already have an account? <a href="/login">LOG IN</a></div>
      </div>
    </div>
    """
    return _shell(title="Coming soon — myscape", player=None, body=body)


def render_login() -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>LOG IN</h2>
        <div class="auth-error" id="formError"></div>
        <form id="loginForm">
          <div class="field">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" placeholder="you@example.com" required />
          </div>
          <div class="field">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" placeholder="Your password" required />
          </div>
          <div class="auth-forgot"><a href="/forgot-password">FORGOT PASSWORD?</a></div>
          <button class="primary" type="submit">LOG IN</button>
        </form>
        <div class="auth-switch">Don't have an account? <a href="/signup">SIGN UP</a></div>
      </div>
    </div>
    """
    script = """
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const errorEl = document.getElementById('formError');
      errorEl.classList.remove('show');
      const submitBtn = e.target.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: document.getElementById('email').value,
            password: document.getElementById('password').value,
          }),
        });
        if (res.ok) {
          // Go straight to the dashboard rather than the landing page.
          window.location.href = '/dashboard';
          return;
        }
        const data = await res.json().catch(() => ({}));
        errorEl.textContent = describeError(data, 'Incorrect email or password.');
        errorEl.classList.add('show');
      } catch (err) {
        errorEl.textContent = 'Something went wrong. Please try again.';
        errorEl.classList.add('show');
      } finally {
        submitBtn.disabled = false;
      }
    });
    """
    return _shell(title="Log in — myscape", player=None, body=body, extra_script=script)


def render_forgot_password() -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>FORGOT PASSWORD</h2>
        <div class="auth-error" id="formError"></div>
        <div class="auth-success" id="formSuccess"></div>
        <form id="forgotForm">
          <div class="field">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" placeholder="you@example.com" required />
          </div>
          <button class="primary" type="submit">SEND RESET LINK</button>
        </form>
        <div class="auth-switch"><a href="/login">BACK TO LOG IN</a></div>
      </div>
    </div>
    """
    script = """
    document.getElementById('forgotForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const form = e.target;
      const errorEl = document.getElementById('formError');
      const successEl = document.getElementById('formSuccess');
      errorEl.classList.remove('show');
      successEl.classList.remove('show');
      const submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        const res = await fetch('/api/auth/forgot-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: document.getElementById('email').value,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
          // The backend returns the same generic message whether or not the
          // email has an account (see forgot_password in app/routers/auth.py),
          // so any 200 just swaps it in.
          form.style.display = 'none';
          successEl.textContent = data.detail || "If that email has an account, we've sent a password reset link.";
          successEl.classList.add('show');
          return;
        }
        errorEl.textContent = describeError(data, 'Something went wrong. Please try again.');
        errorEl.classList.add('show');
      } catch (err) {
        errorEl.textContent = 'Something went wrong. Please try again.';
        errorEl.classList.add('show');
      } finally {
        submitBtn.disabled = false;
      }
    });
    """
    return _shell(title="Forgot password — myscape", player=None, body=body, extra_script=script)


def render_reset_password() -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>RESET PASSWORD</h2>
        <div class="auth-error" id="formError"></div>
        <div class="auth-error" id="noTokenError">
          This password reset link is missing or invalid.
          <a href="/forgot-password">Request a new one</a>.
        </div>
        <form id="resetForm">
          <div class="field">
            <label for="password">New password</label>
            <input type="password" id="password" name="password" placeholder="At least 8 characters" required minlength="8" />
          </div>
          <div class="field">
            <label for="confirmPassword">Confirm new password</label>
            <input type="password" id="confirmPassword" name="confirmPassword" placeholder="Re-enter your new password" required minlength="8" />
          </div>
          <button class="primary" type="submit">RESET PASSWORD</button>
        </form>
      </div>
    </div>
    """
    script = """
    (function () {
      const token = new URLSearchParams(window.location.search).get('token');
      const form = document.getElementById('resetForm');
      const noTokenError = document.getElementById('noTokenError');
      if (!token) {
        // No token in the URL: nothing to submit, so offer a fresh reset request
        // instead of an empty form.
        form.style.display = 'none';
        noTokenError.classList.add('show');
        return;
      }
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const errorEl = document.getElementById('formError');
        errorEl.classList.remove('show');
        const password = document.getElementById('password').value;
        const confirmPassword = document.getElementById('confirmPassword').value;
        if (password !== confirmPassword) {
          errorEl.textContent = 'Passwords do not match.';
          errorEl.classList.add('show');
          return;
        }
        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        try {
          const res = await fetch('/api/auth/reset-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: token, password: password }),
          });
          if (res.ok) {
            // reset_password logs the player in on success
            // (app/routers/auth.py), so go straight into the app.
            window.location.href = '/dashboard';
            return;
          }
          const data = await res.json().catch(() => ({}));
          errorEl.textContent = describeError(data, 'Could not reset your password. The link may have expired.');
          errorEl.classList.add('show');
        } catch (err) {
          errorEl.textContent = 'Something went wrong. Please try again.';
          errorEl.classList.add('show');
        } finally {
          submitBtn.disabled = false;
        }
      });
    })();
    """
    return _shell(title="Reset password — myscape", player=None, body=body, extra_script=script)


def render_verify_email_required(player: PlayerView) -> str:
    body = f"""
    <div class="auth-shell">
      <div class="auth-card">
        <h2>VERIFY YOUR EMAIL</h2>
        <div class="auth-error" id="formError"></div>
        <div class="auth-success" id="formSuccess"></div>
        <p class="verify-email-message">We sent a confirmation link to <strong>{escape(player.email or "your email address")}</strong>.<br>Click it to finish setting up your account.</p>
        <button class="primary" id="resendBtn" type="button">RESEND EMAIL</button>
      </div>
    </div>
    """
    script = """
    document.getElementById('resendBtn').addEventListener('click', async (e) => {
      const btn = e.target;
      const errorEl = document.getElementById('formError');
      const successEl = document.getElementById('formSuccess');
      errorEl.classList.remove('show');
      successEl.classList.remove('show');
      btn.disabled = true;
      try {
        const res = await fetch('/api/auth/resend-verification-email', { method: 'POST' });
        if (res.ok) {
          successEl.textContent = "A new confirmation link is on its way.";
          successEl.classList.add('show');
          return;
        }
        const data = await res.json().catch(() => ({}));
        errorEl.textContent = describeError(data, 'Could not resend the email. Please try again.');
        errorEl.classList.add('show');
      } catch (err) {
        errorEl.textContent = 'Something went wrong. Please try again.';
        errorEl.classList.add('show');
      } finally {
        btn.disabled = false;
      }
    });
    """
    return _shell(title="Verify your email — myscape", player=player, body=body, extra_script=script)


def render_verify_email(player: Optional[PlayerView] = None) -> str:
    body = """
    <div class="auth-shell">
      <div class="auth-card">
        <h2>VERIFY EMAIL</h2>
        <div class="auth-error" id="formError"></div>
        <div class="auth-error" id="noTokenError">
          You need to verify your email to access this content.<br>Your code may be expired — please try again.
        </div>
        <p class="verify-email-message" id="verifyingMessage">Confirming your email&hellip;</p>
      </div>
    </div>
    """
    script = """
    (function () {
      const token = new URLSearchParams(window.location.search).get('token');
      const noTokenError = document.getElementById('noTokenError');
      const verifyingMessage = document.getElementById('verifyingMessage');
      const errorEl = document.getElementById('formError');
      if (!token) {
        // No token in the URL: same no-token case as render_reset_password.
        verifyingMessage.style.display = 'none';
        noTokenError.classList.add('show');
        return;
      }
      (async () => {
        try {
          const res = await fetch('/api/auth/verify-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: token }),
          });
          if (res.ok) {
            // verify_email logs the player in on success (app/routers/auth.py),
            // so go straight into the app.
            window.location.href = '/dashboard';
            return;
          }
          const data = await res.json().catch(() => ({}));
          verifyingMessage.style.display = 'none';
          errorEl.textContent = describeError(data, 'Could not verify your email. The link may have expired.');
          errorEl.classList.add('show');
        } catch (err) {
          verifyingMessage.style.display = 'none';
          errorEl.textContent = 'Something went wrong. Please try again.';
          errorEl.classList.add('show');
        }
      })();
    })();
    """
    return _shell(title="Verify email — myscape", player=player, body=body, extra_script=script)


def render_not_found(player: Optional[PlayerView] = None) -> str:
    """The styled 404 page, used by the exception handler in app/main.py. The
    handler loads the player itself and passes it in, so the header shows
    Dashboard/Log out for signed-in visitors. The same check points the
    home-teleport icon at /dashboard when signed in and / otherwise.
    """
    teleport_href = "/dashboard" if player else "/"
    body = f"""
    <div class="auth-shell not-found-shell">
      <div class="auth-card">
        <h2>PAGE NOT FOUND</h2>
        <div class="not-found-code">404</div>
        <a href="{teleport_href}" class="not-found-teleport" title="Cast Home Teleport">
          <img class="not-found-icon" src="/static/img/icon-home-teleport.png" alt="Home Teleport icon" />
        </a>
        <p class="verify-email-message">You must be lost, friend.<br>Try casting your home teleport.</p>
      </div>
    </div>
    """
    return _shell(title="Page not found — myscape", player=player, body=body)
