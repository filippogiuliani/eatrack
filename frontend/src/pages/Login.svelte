<script>
  import { post } from '../lib/api.js';
  import { t } from '../lib/i18n.svelte.js';
  import { app } from '../lib/store.svelte.js';
  import AuthCard from '../components/AuthCard.svelte';
  import OidcButtons from '../components/OidcButtons.svelte';
  import HubSignIn from '../components/HubSignIn.svelte';
  // embedded: used inside another page (e.g. an invitation), without the frame
  let { ondone, embedded = false, invite = null, initialError = '' } = $props();
  let email = $state('');
  let password = $state('');
  let error = $state('');
  let sending = $state(false);
  $effect(() => { if (initialError) error = initialError; });

  async function signIn(e) {
    e.preventDefault();
    sending = true; error = '';
    try { await post('/login', { email, password }); await ondone(); }
    catch (err) { error = err.message; password = ''; }
    finally { sending = false; }
  }
</script>

{#snippet form()}
  {#if app.me?.hub}
  <HubSignIn {error} />
  {:else}
  <OidcButtons {invite} />
  <form class="stack" onsubmit={signIn}>
    <label class="field"><span class="label">{t('auth.email')}</span>
      <input class="input" type="email" bind:value={email} autocomplete="email" required /></label>
    <label class="field"><span class="label">{t('auth.password')}</span>
      <input class="input" type="password" bind:value={password} autocomplete="current-password" required /></label>
    {#if error}<p class="err small" role="alert">{error}</p>{/if}
    <button class="btn primary block" disabled={sending}>{sending ? t('auth.signing_in') : t('auth.sign_in')}</button>
    {#if !embedded}
      <div class="spread small">
        <a href="#/forgot-password">{t('auth.forgot_password')}</a>
        <a href="#/signup">{t('auth.create_account')}</a>
      </div>
    {/if}
  </form>
  {/if}
{/snippet}

{#if embedded}
  {@render form()}
{:else}
  <AuthCard title={t('auth.sign_in')} subtitle={t('auth.subtitle')}>{@render form()}</AuthCard>
{/if}

<style>
  .err { color: var(--danger); font-weight: 500; }
</style>
