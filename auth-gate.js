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
  let _tempAccess = false;
  let _tempToken = null;
  let _tempLinkData = null;

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

    // Check for temp access token in URL: ?token=XXXX
    const urlParams = new URLSearchParams(window.location.search);
    const tempToken = urlParams.get('token');

    if (tempToken) {
      // Primeiro: checar se o token existe e tá ativo (sem filtrar expires_at, porque pode ser null no primeiro acesso)
      const { data: linkData, error: linkErr } = await supabase
        .from('temp_links')
        .select('*')
        .eq('token', tempToken)
        .eq('active', true)
        .maybeSingle();

      if (linkErr || !linkData) {
        showTempExpired();
        return;
      }

      // Se já foi ativado e expirou
      if (linkData.expires_at && new Date(linkData.expires_at) < new Date()) {
        showTempExpired();
        return;
      }

      // Token válido — guardar referência e mostrar welcome
      _tempToken = tempToken;
      _tempLinkData = linkData;
      _tempAccess = true;

      // Se já tem email registrado (visita de retorno), pula welcome
      if (linkData.visitor_email) {
        await activateAndShow(tempToken, linkData.visitor_email);
      } else {
        showWelcomeScreen(linkData);
      }
      return;
    }

    // Check current session
    const { data: { session } } = await supabase.auth.getSession();

    if (session) {
      await handleAuthenticated(session.user);
    } else {
      showLoginForm();
    }

    // Listen for auth changes (OAuth callback)
    supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === 'SIGNED_IN' && session) {
        await handleAuthenticated(session.user);
      } else if (event === 'SIGNED_OUT') {
        showLoginForm();
      }
    });
  }

  // ============================================
  // TEMP LINK — WELCOME, ACTIVATION, BANNER
  // ============================================

  function showWelcomeScreen(linkData) {
    document.querySelectorAll('[data-auth="protected"]').forEach(el => {
      el.style.display = 'none';
    });

    const hours = linkData.duration_hours || 1;
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
          width: 420px; padding: 48px 40px;
          border: 1px solid #222; border-radius: 12px;
          background: #111; color: #ccc;
        ">
          <h1 style="
            font-size: 20px; color: #fff; margin-bottom: 16px;
            font-weight: 400; line-height: 1.4;
          ">Bem-vindo ao meu mundo.</h1>

          <p style="font-size: 14px; color: #888; line-height: 1.7; margin-bottom: 12px;">
            Esse é um link temporário e tá válido por <strong style="color: #f0c040;">${hours}h</strong> desde o primeiro acesso.
          </p>
          <p style="font-size: 14px; color: #888; line-height: 1.7; margin-bottom: 24px;">
            Se eu te dei esse acesso, é pra você ver e entender um pouco do que estou fazendo. Aproveite.
          </p>

          <div style="margin-bottom: 24px;">
            <label style="font-size: 12px; color: #666; display: block; margin-bottom: 6px;">
              Digite seu email pra deixar de rastro, por favor.
            </label>
            <input id="temp-visitor-email" type="email" placeholder="seu@email.com"
              style="
                width: 100%; padding: 10px 12px;
                background: #0a0a0a; border: 1px solid #333; border-radius: 6px;
                color: #fff; font-size: 14px; box-sizing: border-box;
              "
            />
          </div>

          <button onclick="AuthGate._handleTempEnter()" style="
            width: 100%; padding: 12px; background: #1a2a1a;
            border: 1px solid #2a5a3a; border-radius: 8px;
            color: #4a9; cursor: pointer; font-size: 14px;
            font-weight: 500; transition: background 0.2s;
          ">Entrar</button>

          <div style="
            margin-top: 24px; padding-top: 20px;
            border-top: 1px solid #1a1a1a;
            font-size: 12px; color: #555; line-height: 1.8;
          ">
            Se precisar de mais tempo, só me pedir que te dou acesso novamente.<br>
            <a href="mailto:eu@annagraboski.com" style="color: #68f; text-decoration: none;">eu@annagraboski.com</a>
            &nbsp;·&nbsp;
            <a href="https://wa.me/5521984142399" style="color: #4a9; text-decoration: none;">WhatsApp</a>
          </div>

          <div id="auth-gate-msg" style="
            margin-top: 12px; text-align: center;
            font-size: 12px; color: #666; min-height: 18px;
          "></div>
        </div>
      </div>
    `;
    container.style.display = 'block';
  }

  async function _handleTempEnter() {
    const emailInput = document.getElementById('temp-visitor-email');
    const email = emailInput?.value?.trim();
    if (!email || !email.includes('@')) {
      showMessage('Preciso do seu email pra liberar o acesso', true);
      return;
    }
    await activateAndShow(_tempToken, email);
  }

  async function activateAndShow(token, email) {
    // Chamar RPC que ativa no primeiro acesso ou valida nos subsequentes
    const { data, error } = await supabase.rpc('activate_temp_link', {
      link_token: token,
      email: email
    });

    if (error || (data && data.error)) {
      showTempExpired();
      return;
    }

    // Sucesso — mostrar conteúdo
    hideLoginForm();
    showProtectedContent();
    showTempCTA(data.expires_at, data.duration_hours);

    if (config.onAuth) {
      config.onAuth(
        { email: email, id: null },
        { role: 'viewer', can_read: true, can_write: false, can_admin: false }
      );
    }
  }

  function showTempCTA(expiresAt, hours) {
    const exp = new Date(expiresAt);

    // Top banner com countdown
    const banner = document.createElement('div');
    banner.id = 'temp-access-banner';
    banner.style.cssText = `
      position: fixed; top: 0; left: 0; right: 0; z-index: 10000;
      background: #1a1a2e; border-bottom: 1px solid #333;
      padding: 8px 16px; font-family: -apple-system, sans-serif;
      font-size: 12px; color: #f0c040; text-align: center;
    `;
    updateBannerText(banner, exp);
    document.body.prepend(banner);

    // Bottom CTA fixo
    const cta = document.createElement('div');
    cta.id = 'temp-access-cta';
    cta.style.cssText = `
      position: fixed; bottom: 0; left: 0; right: 0; z-index: 10000;
      background: #111; border-top: 1px solid #222;
      padding: 10px 16px; font-family: -apple-system, sans-serif;
      font-size: 12px; color: #666; text-align: center;
      display: flex; align-items: center; justify-content: center; gap: 16px;
    `;
    cta.innerHTML = `
      <span>Acesso temporário · Precisa de mais tempo?</span>
      <a href="mailto:eu@annagraboski.com" style="color: #68f; text-decoration: none; font-weight: 500;">Email</a>
      <a href="https://wa.me/5521984142399" style="color: #4a9; text-decoration: none; font-weight: 500;">WhatsApp</a>
    `;
    document.body.appendChild(cta);

    // Ajustar padding do body pra não cobrir conteúdo
    document.body.style.paddingTop = '36px';
    document.body.style.paddingBottom = '40px';

    // Countdown a cada 30s
    const interval = setInterval(() => {
      const rem = Math.max(0, Math.round((exp - Date.now()) / 60000));
      if (rem <= 0) {
        clearInterval(interval);
        banner.textContent = 'Acesso expirado';
        banner.style.background = '#2e1a1a';
        banner.style.color = '#e74c3c';
        cta.innerHTML = '<span style="color: #e74c3c;">Acesso expirado</span>';
        setTimeout(() => location.reload(), 5000);
      } else {
        updateBannerText(banner, exp);
      }
    }, 30000);
  }

  function updateBannerText(banner, exp) {
    const diff = exp - Date.now();
    const mins = Math.max(0, Math.round(diff / 60000));
    if (mins >= 60) {
      const h = Math.floor(mins / 60);
      const m = mins % 60;
      banner.textContent = `Acesso temporário · expira em ${h}h${m > 0 ? m + 'min' : ''}`;
    } else {
      banner.textContent = `Acesso temporário · expira em ${mins} min`;
    }
  }

  function showTempExpired() {
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
          width: 380px; padding: 40px; text-align: center;
          border: 1px solid #222; border-radius: 12px;
          background: #111; color: #ccc;
        ">
          <div style="font-size: 32px; margin-bottom: 16px;">⏰</div>
          <h2 style="font-size: 16px; color: #e74c3c; margin-bottom: 12px; font-weight: 400;">
            Link expirado ou inválido
          </h2>
          <p style="font-size: 13px; color: #666; line-height: 1.7; margin-bottom: 24px;">
            Se precisar de mais tempo, só me pedir que te dou acesso novamente.
          </p>
          <div style="display: flex; gap: 12px; justify-content: center;">
            <a href="mailto:eu@annagraboski.com" style="
              padding: 8px 20px; background: #1a1a2e; border: 1px solid #333;
              border-radius: 6px; color: #68f; text-decoration: none; font-size: 13px;
            ">Email</a>
            <a href="https://wa.me/5521984142399" style="
              padding: 8px 20px; background: #1a2a1a; border: 1px solid #2a5a3a;
              border-radius: 6px; color: #4a9; text-decoration: none; font-size: 13px;
            ">WhatsApp</a>
          </div>
        </div>
      </div>
    `;
    container.style.display = 'block';
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
  // LOGIN METHODS (GitHub only)
  // ============================================
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
  // UI — Login Form (GitHub only)
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

          <button onclick="AuthGate._handleGitHub()" style="
            width: 100%; padding: 12px; background: #161b22;
            border: 1px solid #333; border-radius: 8px;
            color: #fff; cursor: pointer; font-size: 14px;
            display: flex; align-items: center; justify-content: center; gap: 8px;
          ">
            <svg width="18" height="18" viewBox="0 0 16 16" fill="white">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
              0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13
              -.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66
              .07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15
              -.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0
              1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56
              .82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07
              -.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
            </svg>
            Entrar com GitHub
          </button>

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
  // INTERNAL HANDLERS
  // ============================================
  async function _handleGitHub() {
    try {
      await loginWithGitHub();
    } catch (e) {
      showMessage(e.message, true);
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
    loginWithGitHub,
    getUser,
    getSession,
    getClient,
    isTempAccess: () => _tempAccess,
    // Internal (for onclick)
    _handleGitHub,
    _handleTempEnter
  };
})();