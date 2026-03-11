/**
 * auth-gate.js — Unified Auth for annagraboski.com sites
 *
 * Usage:
 *   <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
 *   <script src="auth-gate.js"></script>
 *   <script>
 *     AuthGate.init({ site: 'apgia' });
 *   </script>
 *
 * Config options:
 *   site: 'apgia' | 'scout' | 'linktree-admin'
 *   onAuth: callback(user, permissions) — called after successful auth
 *   onDenied: callback() — called if user has no access to this site
 *   loginContainerId: DOM id for login form (default: 'auth-gate-login')
 *   redirectAfterLogin: URL to redirect to after login (optional)
 */

const AuthGate = (() => {
  // ============================================
  // CONFIG — UPDATE THESE
  // ============================================
  const SUPABASE_URL = 'https://rqiwrlygeduzaaejlmrx.supabase.co';
  const SUPABASE_ANON_KEY = 'sb_publishable_GzPnmabRnXBq1OMNKcyrAA_DMUbesm7';

  let supabase = null;
  let config = {};

  // ============================================
  // INIT
  // ============================================
  async function init(opts = {}) {
    config = {
      site: opts.site || 'apgia',
      onAuth: opts.onAuth || null,
      onDenied: opts.onDenied || null,
      loginContainerId: opts.loginContainerId || 'auth-gate-login',
      redirectAfterLogin: opts.redirectAfterLogin || null,
      ...opts
    };

    // Init Supabase client
    supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

    // Check current session
    const { data: { session } } = await supabase.auth.getSession();

    if (session) {
      await handleAuthenticated(session.user);
    } else {
      showLoginForm();
    }

    // Listen for auth changes (magic link, OAuth callback, etc.)
    supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === 'SIGNED_IN' && session) {
        await handleAuthenticated(session.user);
      } else if (event === 'SIGNED_OUT') {
        showLoginForm();
      }
    });
  }

  // ============================================
  // AUTH FLOW
  // ============================================
  async function handleAuthenticated(user) {
    // Check site permission
    const { data: hasAccess } = await supabase.rpc('has_site_access', {
      site_name: config.site
    });

    if (!hasAccess) {
      if (config.onDenied) {
        config.onDenied();
      } else {
        showAccessDenied(user.email);
      }
      return;
    }

    // Get role & permissions
    const { data: siteRole } = await supabase.rpc('get_site_role', {
      site_name: config.site
    });

    // Hide login, show content
    hideLoginForm();
    showProtectedContent();

    // Callback
    if (config.onAuth) {
      config.onAuth(user, siteRole);
    }
  }

  // ============================================
  // LOGIN METHODS
  // ============================================
  async function loginWithEmail(email, password) {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password
    });
    if (error) throw error;
    return data;
  }

  async function loginWithMagicLink(email) {
    const { data, error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: window.location.href
      }
    });
    if (error) throw error;
    return data;
  }

  async function loginWithGitHub() {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'github',
      options: {
        redirectTo: window.location.href
      }
    });
    if (error) throw error;
    return data;
  }

  async function logout() {
    await supabase.auth.signOut();
    showLoginForm();
  }

  // ============================================
  // UI — Login Form
  // ============================================
  function showLoginForm() {
    // Hide protected content
    document.querySelectorAll('[data-auth="protected"]').forEach(el => {
      el.style.display = 'none';
    });

    let container = document.getElementById(config.loginContainerId);
    if (!container) {
      container = document.createElement('div');
      container.id = config.loginContainerId;
      document.body.prepend(container);
    }

    container.innerHTML = `
      <div style="
        position: fixed; inset: 0; z-index: 9999;
        display: flex; align-items: center; justify-content: center;
        background: #0a0a0a; font-family: -apple-system, sans-serif;
      ">
        <div style="
          width: 340px; padding: 40px;
          border: 1px solid #222; border-radius: 12px;
          background: #111; color: #ccc;
        ">
          <h1 style="
            font-size: 14px; letter-spacing: 4px; text-align: center;
            color: #666; margin-bottom: 32px; font-weight: 300;
          ">${config.site.toUpperCase()}</h1>

          <div id="auth-gate-tabs" style="
            display: flex; gap: 0; margin-bottom: 24px;
            border-bottom: 1px solid #333;
          ">
            <button onclick="AuthGate._showTab('email')" id="tab-email" style="
              flex: 1; padding: 8px; background: none; border: none;
              color: #fff; cursor: pointer; border-bottom: 2px solid #fff;
              font-size: 13px;
            ">Email</button>
            <button onclick="AuthGate._showTab('magic')" id="tab-magic" style="
              flex: 1; padding: 8px; background: none; border: none;
              color: #666; cursor: pointer; border-bottom: 2px solid transparent;
              font-size: 13px;
            ">Magic Link</button>
          </div>

          <!-- Email/Password -->
          <div id="auth-form-email">
            <input id="auth-email" type="email" placeholder="email"
              style="
                width: 100%; padding: 10px 12px; margin-bottom: 12px;
                background: #0a0a0a; border: 1px solid #333; border-radius: 6px;
                color: #fff; font-size: 14px; box-sizing: border-box;
              "
            />
            <input id="auth-password" type="password" placeholder="senha"
              style="
                width: 100%; padding: 10px 12px; margin-bottom: 16px;
                background: #0a0a0a; border: 1px solid #333; border-radius: 6px;
                color: #fff; font-size: 14px; box-sizing: border-box;
              "
            />
            <button onclick="AuthGate._handleEmailLogin()" style="
              width: 100%; padding: 10px; background: #222; border: 1px solid #444;
              border-radius: 8px; color: #fff; cursor: pointer; font-size: 14px;
              transition: background 0.2s;
            ">Entrar</button>
          </div>

          <!-- Magic Link -->
          <div id="auth-form-magic" style="display: none;">
            <input id="auth-magic-email" type="email" placeholder="email"
              style="
                width: 100%; padding: 10px 12px; margin-bottom: 16px;
                background: #0a0a0a; border: 1px solid #333; border-radius: 6px;
                color: #fff; font-size: 14px; box-sizing: border-box;
              "
            />
            <button onclick="AuthGate._handleMagicLink()" style="
              width: 100%; padding: 10px; background: #222; border: 1px solid #444;
              border-radius: 8px; color: #fff; cursor: pointer; font-size: 14px;
            ">Enviar link</button>
          </div>

          <!-- GitHub OAuth -->
          <div style="
            margin-top: 16px; padding-top: 16px;
            border-top: 1px solid #222;
          ">
            <button onclick="AuthGate._handleGitHub()" style="
              width: 100%; padding: 10px; background: #161b22;
              border: 1px solid #333; border-radius: 8px;
              color: #fff; cursor: pointer; font-size: 14px;
              display: flex; align-items: center; justify-content: center; gap: 8px;
            ">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="white">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
                0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13
                -.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66
                .07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15
                -.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0
                1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56
                .82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07
                -.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
              </svg>
              GitHub
            </button>
          </div>

          <div id="auth-gate-msg" style="
            margin-top: 16px; text-align: center;
            font-size: 12px; color: #666; min-height: 18px;
          "></div>
        </div>
      </div>
    `;

    container.style.display = 'block';
  }

  function hideLoginForm() {
    const container = document.getElementById(config.loginContainerId);
    if (container) container.style.display = 'none';
  }

  function showProtectedContent() {
    document.querySelectorAll('[data-auth="protected"]').forEach(el => {
      el.style.display = '';
    });
  }

  function showAccessDenied(email) {
    const container = document.getElementById(config.loginContainerId);
    if (container) {
      container.innerHTML = `
        <div style="
          position: fixed; inset: 0; z-index: 9999;
          display: flex; align-items: center; justify-content: center;
          background: #0a0a0a; font-family: -apple-system, sans-serif;
        ">
          <div style="
            width: 340px; padding: 40px; text-align: center;
            border: 1px solid #222; border-radius: 12px;
            background: #111; color: #ccc;
          ">
            <div style="font-size: 32px; margin-bottom: 16px;">🔒</div>
            <p style="color: #888; font-size: 14px; margin-bottom: 8px;">
              Logado como <strong style="color: #fff;">${email}</strong>
            </p>
            <p style="color: #666; font-size: 13px; margin-bottom: 24px;">
              Sem permissão para acessar <strong>${config.site}</strong>.
            </p>
            <button onclick="AuthGate.logout()" style="
              padding: 8px 24px; background: #222; border: 1px solid #444;
              border-radius: 6px; color: #fff; cursor: pointer; font-size: 13px;
            ">Sair</button>
          </div>
        </div>
      `;
    }
  }

  function showMessage(text, isError = false) {
    const msg = document.getElementById('auth-gate-msg');
    if (msg) {
      msg.textContent = text;
      msg.style.color = isError ? '#e74c3c' : '#4a9';
    }
  }

  // ============================================
  // INTERNAL HANDLERS (exposed for onclick)
  // ============================================
  async function _handleEmailLogin() {
    const email = document.getElementById('auth-email')?.value;
    const password = document.getElementById('auth-password')?.value;
    if (!email || !password) return showMessage('Preenche email e senha', true);
    try {
      await loginWithEmail(email, password);
    } catch (e) {
      showMessage(e.message, true);
    }
  }

  async function _handleMagicLink() {
    const email = document.getElementById('auth-magic-email')?.value;
    if (!email) return showMessage('Preenche o email', true);
    try {
      await loginWithMagicLink(email);
      showMessage('Link enviado! Checa teu email.');
    } catch (e) {
      showMessage(e.message, true);
    }
  }

  async function _handleGitHub() {
    try {
      await loginWithGitHub();
    } catch (e) {
      showMessage(e.message, true);
    }
  }

  function _showTab(tab) {
    const emailForm = document.getElementById('auth-form-email');
    const magicForm = document.getElementById('auth-form-magic');
    const tabEmail = document.getElementById('tab-email');
    const tabMagic = document.getElementById('tab-magic');

    if (tab === 'email') {
      emailForm.style.display = 'block';
      magicForm.style.display = 'none';
      tabEmail.style.color = '#fff';
      tabEmail.style.borderBottomColor = '#fff';
      tabMagic.style.color = '#666';
      tabMagic.style.borderBottomColor = 'transparent';
    } else {
      emailForm.style.display = 'none';
      magicForm.style.display = 'block';
      tabMagic.style.color = '#fff';
      tabMagic.style.borderBottomColor = '#fff';
      tabEmail.style.color = '#666';
      tabEmail.style.borderBottomColor = 'transparent';
    }
  }

  // ============================================
  // SESSION HELPERS
  // ============================================
  async function getUser() {
    const { data: { user } } = await supabase.auth.getUser();
    return user;
  }

  async function getSession() {
    const { data: { session } } = await supabase.auth.getSession();
    return session;
  }

  function getClient() {
    return supabase;
  }

  // ============================================
  // PUBLIC API
  // ============================================
  return {
    init,
    logout,
    loginWithEmail,
    loginWithMagicLink,
    loginWithGitHub,
    getUser,
    getSession,
    getClient,
    // Internal (for onclick handlers)
    _handleEmailLogin,
    _handleMagicLink,
    _handleGitHub,
    _showTab
  };
})();