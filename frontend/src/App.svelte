<script>
  import { post, setUnauthorizedHandler } from './lib/api.js';
  import { app, loadCatalog, loadMe, showError, toast } from './lib/store.svelte.js';
  import { setLanguage, t } from './lib/i18n.svelte.js';
  import AppSwitcher from './components/AppSwitcher.svelte';
  import Toast from './components/Toast.svelte';
  import ChildSwitch from './components/ChildSwitch.svelte';
  import LanguageSwitch from './components/LanguageSwitch.svelte';
  import Login from './pages/Login.svelte';
  import Signup from './pages/Signup.svelte';
  import ForgotPassword from './pages/ForgotPassword.svelte';
  import ResetPassword from './pages/ResetPassword.svelte';
  import VerifyEmail from './pages/VerifyEmail.svelte';
  import Invite from './pages/Invite.svelte';
  import Privacy from './pages/Privacy.svelte';
  import Diary from './pages/Diary.svelte';
  import Pantry from './pages/Pantry.svelte';
  import Foods from './pages/Foods.svelte';
  import Stats from './pages/Stats.svelte';
  import Family from './pages/Family.svelte';
  import Plan from './pages/Plan.svelte';

  const PAGES = [
    { id: 'diary', comp: Diary, icon: '<rect x="3" y="4" width="18" height="18" rx="3"/><path d="M16 2v4M8 2v4M3 10h18"/>' },
    { id: 'pantry', comp: Pantry, icon: '<path d="M7 3h10v3H7z"/><path d="M6 6h12v13a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2z"/><path d="M6 11h12"/>' },
    { id: 'foods', comp: Foods, icon: '<path d="M12 21c-4.4 0-8-3.6-8-8 0-3.3 2.2-6 5-6 1.2 0 2.2.4 3 1 .8-.6 1.8-1 3-1 2.8 0 5 2.7 5 6 0 4.4-3.6 8-8 8z"/><path d="M12 8c0-2 1-4 3-5"/>' },
    { id: 'stats', comp: Stats, icon: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>' },
    { id: 'family', comp: Family, icon: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.3-6 6.5-6s5.9 2.4 6.5 6"/><circle cx="17" cy="9" r="2.5"/><path d="M16.5 14c2.6.2 4.4 2.3 5 5"/>' },
  ];
  // App pages that are not in the navigation bar (with the bar item to highlight)
  const SECONDARY = { plan: { comp: Plan, section: 'diary' } };
  // Pages reachable without an account
  const PUBLIC = ['login', 'signup', 'forgot-password', 'reset', 'verify', 'invite', 'privacy'];
  // Route names used before v5: links already sent by email keep working
  const LEGACY_ROUTES = { diario: 'diary', dispensa: 'pantry', alimenti: 'foods', statistiche: 'stats', famiglia: 'family',
                          piano: 'plan', registrati: 'signup', recupero: 'forgot-password', verifica: 'verify', invito: 'invite' };

  let status = $state('loading'); // loading | ready | error
  let route = $state(readHash());

  function readHash() {
    const [path, query = ''] = location.hash.replace(/^#\/?/, '').split('?');
    const [name = '', param = ''] = path.split('/');
    return { name: LEGACY_ROUTES[name] ?? name, param: decodeURIComponent(param), query: new URLSearchParams(query) };
  }
  $effect(() => {
    const onHash = () => { route = readHash(); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  });

  const authenticated = $derived(!!app.me?.authenticated);
  // Page actually shown: only public pages without an account, app pages once signed in
  const page = $derived.by(() => {
    if (!authenticated) return PUBLIC.includes(route.name) ? route.name : 'login';
    if (['verify', 'invite', 'privacy'].includes(route.name)) return route.name;
    if (route.name === 'signup' && route.query.get('external')) return 'diary';
    return PAGES.some((p) => p.id === route.name) || SECONDARY[route.name] ? route.name : 'diary';
  });
  const Current = $derived(PAGES.find((p) => p.id === page)?.comp ?? SECONDARY[page]?.comp);
  const section = $derived(SECONDARY[page]?.section ?? page);

  setUnauthorizedHandler(() => { if (app.me) app.me = { ...app.me, authenticated: false }; });

  async function start() {
    try {
      const me = await loadMe();
      // The language saved in the profile wins over the browser's
      if (me.authenticated && me.user.language) setLanguage(me.user.language);
      if (me.authenticated) await loadCatalog();
      status = 'ready';
    } catch (e) { showError(e); status = 'error'; }
  }
  start();

  async function logout(alreadyDeleted = false) {
    if (!alreadyDeleted) await post('/logout').catch(() => {});
    await loadMe().catch(() => {});
    location.hash = '#/login';
  }
  async function resend() {
    try { await post('/account/resend-verification'); toast(t('account.verification_sent')); } catch (e) { showError(e); }
  }
</script>

{#if status === 'loading'}
  <main class="center"><img class="pulse" src="/icon.svg" alt={t('common.wait')} width="56" height="56" /></main>
{:else if status === 'error'}
  <main class="center"><p class="empty">{t('error.server')}<br /><button class="btn soft" onclick={start}>{t('common.retry')}</button></p></main>
{:else if !authenticated || ['verify', 'invite', 'privacy'].includes(page)}
  <div class="public-language"><LanguageSwitch /></div>
  {#if page === 'signup'}<Signup ondone={start} external={!!route.query.get('external')} />
  {:else if page === 'forgot-password'}<ForgotPassword />
  {:else if page === 'reset'}<ResetPassword token={route.param} ondone={start} />
  {:else if page === 'verify'}<VerifyEmail token={route.param} ondone={start} />
  {:else if page === 'invite'}<Invite token={route.param} ondone={start} />
  {:else if page === 'privacy'}<Privacy />
  {:else}<Login ondone={start} initialError={route.query.get('error') ?? ''} />{/if}
{:else}
  <div class="shell">
    <nav class="nav" aria-label={t('nav.sections')}>
      <a class="logo" href="#/diary"><img src="/icon.svg" alt="" width="28" height="28" /><span>eaTrack</span></a>
      <div class="nav-apps hide-mobile"><AppSwitcher hub={app.me.hub} label /></div>
      <div class="children hide-mobile"><ChildSwitch /></div>
      {#each PAGES as p (p.id)}
        <a href="#/{p.id}" class:on={section === p.id} aria-current={page === p.id ? 'page' : undefined}>
          <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{@html p.icon}</svg>
          <span class="lbl">{t('nav.' + p.id)}</span>
        </a>
      {/each}
      <button class="logout hide-mobile" onclick={() => logout()} title={app.me.user.email}>
        <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>
        <span class="lbl">{t('account.sign_out')}</span>
      </button>
    </nav>
    <main class="main">
      <!-- Phone: a slim top bar so signing out is always one tap away -->
      <div class="topbar hide-desktop">
        <a class="brand" href="#/diary"><img src="/icon.svg" alt="" width="24" height="24" /><span>eaTrack</span></a>
        <AppSwitcher hub={app.me.hub} />
        <button class="btn ghost sm" onclick={() => logout()} aria-label={t('account.sign_out')}>
          <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg><span>{t('account.sign_out')}</span>
        </button>
      </div>
      {#if !app.me.user.email_verified}
        <div class="notice small">
          <span>{t('account.not_verified', { email: app.me.user.email })}</span>
          <button class="btn ghost sm" onclick={resend}>{t('account.resend')}</button>
        </div>
      {/if}
      {#key page + ':' + app.me.family?.id}
        {#if page === 'family'}
          <Family onlogout={logout} initialError={route.query.get('error') ?? ''} />
        {:else}
          <Current />
        {/if}
      {/key}
    </main>
  </div>
{/if}
<Toast />

<style>
  .nav-apps { margin: -10px 0 8px; }
  .center { min-height: 100dvh; display: grid; place-items: center; padding: 16px; }
  .pulse { border-radius: 12px; animation: pulse 1s ease-in-out infinite alternate; }
  @keyframes pulse { to { opacity: 0.5; } }
  .public-language { position: absolute; top: 12px; right: 12px; z-index: 5; }

  .main { padding: 20px 16px calc(var(--nav-h) + 96px + env(safe-area-inset-bottom)); max-width: 1280px; margin: 0 auto; }
  .notice { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
    padding: 8px 12px; margin-bottom: 16px; border-radius: var(--r-sm); background: var(--primary-soft); }

  /* Phone: bottom bar */
  .nav {
    position: fixed; z-index: 50; left: 0; right: 0; bottom: 0;
    height: calc(var(--nav-h) + env(safe-area-inset-bottom)); padding: 6px 6px env(safe-area-inset-bottom);
    display: flex; background: var(--surface); border-top: 1px solid var(--line);
  }
  .logo { display: none; }
  .nav a:not(.logo) {
    flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
    text-decoration: none; color: var(--muted); font-weight: 500; font-size: 0.7rem; border-radius: var(--r-sm);
    -webkit-tap-highlight-color: transparent;
  }
  .lbl { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ico { width: 22px; height: 22px; }
  .nav a.on { color: var(--primary); }
  .topbar { display: flex; align-items: center; justify-content: space-between; margin: -8px 0 12px; }
  .brand { display: flex; align-items: center; gap: 8px; text-decoration: none; color: var(--ink); font-weight: 650; letter-spacing: -0.02em; }
  .brand img { border-radius: 6px; }
  .topbar .btn { gap: 6px; }
  .topbar .ico { width: 18px; height: 18px; }

  /* Desktop: sidebar */
  @media (min-width: 900px) {
    .shell { display: grid; grid-template-columns: 220px 1fr; }
    .nav { position: sticky; top: 0; height: 100dvh; flex-direction: column; gap: 2px; padding: 20px 12px; border-top: 0; border-right: 1px solid var(--line); }
    .logo { display: flex; align-items: center; gap: 10px; padding: 4px 10px 18px; text-decoration: none; color: var(--ink); font-size: 1.15rem; font-weight: 650; letter-spacing: -0.02em; }
    .logo img { border-radius: 7px; }
    .children { display: block; padding: 0 2px 14px; }
    .children :global(.seg) { flex-wrap: wrap; }
    .children :global(.only) { padding: 0 10px; }
    .nav a:not(.logo) { flex: none; flex-direction: row; justify-content: flex-start; gap: 10px; padding: 9px 12px; font-size: 0.92rem; }
    .nav a:not(.logo) .ico { width: 18px; height: 18px; }
    .nav a.on { background: var(--primary-soft); }
    .main { padding: 32px 32px 48px; width: 100%; max-width: 1680px; }
    .logout {
      margin-top: auto; display: flex; align-items: center; gap: 10px; padding: 9px 12px; border: 0; border-radius: var(--r-sm);
      background: transparent; color: var(--muted); font: inherit; font-weight: 500; font-size: 0.92rem; cursor: pointer; text-align: left;
    }
    .logout:hover { color: var(--ink); background: var(--surface-2); }
    .logout .ico { width: 18px; height: 18px; }
  }
</style>
