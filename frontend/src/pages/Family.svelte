<script>
  import { api, del, get, post, put } from '../lib/api.js';
  import { app, loadCatalog, loadMe, showError, toast } from '../lib/store.svelte.js';
  import { t } from '../lib/i18n.svelte.js';
  import { ageInMonths, today } from '../lib/date.js';
  import Sheet from '../components/Sheet.svelte';
  import LanguageSwitch from '../components/LanguageSwitch.svelte';

  let { onlogout, initialError = '' } = $props();
  let family = $state(null);
  let invite = $state(null);
  let childEditor = $state(null);
  let familyName = $state('');
  let userName = $state(app.me?.user?.name ?? '');
  let pwd = $state({ current: '', new: '' });
  let file = $state(null);
  let importing = $state(false);
  let fileInput = $state();
  let chosen = $state([]); // children selected in the Data section (empty = all of them)

  const admin = $derived(family?.role === 'admin');

  // --- doTrack (family organizer): where the weekly menu's foods go shopping
  let dt = $state(null);
  let dtForm = $state({ url: '', token: '' });
  let dtLists = $state([]);
  $effect(() => {
    app.me?.family?.id;
    get('/integrations/dotrack').then((d) => {
      dt = d; dtForm.url = d.url ?? '';
      // Through weHub nothing to connect: the admin only needs the lists to pick from
      if (d.via_hub && admin) get('/integrations/dotrack/lists').then((l) => (dtLists = l)).catch(showError);
    }).catch(() => {});
  });
  async function dtConnect(e) {
    e?.preventDefault();
    try {
      const r = await put('/integrations/dotrack', { url: dtForm.url, token: dtForm.token });
      dt = r; dtLists = r.lists; dtForm.token = '';
      toast(t('dotrack.connected'));
    } catch (err) { showError(err); }
  }
  async function dtChoose(id) {
    try { const r = await put('/integrations/dotrack', { list_id: Number(id) }); dt = r; dtLists = r.lists; } catch (err) { showError(err); }
  }
  async function dtDisconnect() {
    if (!confirm(t('dotrack.confirm_disconnect'))) return;
    try { dt = await del('/integrations/dotrack'); dtLists = []; dtForm = { url: '', token: '' }; } catch (err) { showError(err); }
  }
  const user = $derived(app.me?.user);

  async function load() {
    try { family = await get('/family'); familyName = family.name; } catch (e) { showError(e); }
  }
  $effect(() => { app.me?.family?.id; load(); });
  $effect(() => { if (initialError) toast(initialError, 'error'); });

  async function run(fn, message) {
    try { await fn(); if (message) toast(message); await loadMe(); await load(); return true; } catch (e) { showError(e); return false; }
  }

  // --- Family
  const rename = () => run(() => put('/family', { name: familyName }), t('common.saved'));
  const switchFamily = (id) => run(async () => { await post('/family/switch', { family_id: id }); await loadCatalog(); });

  // --- Children
  async function saveChild() {
    const { id, ...body } = childEditor;
    if (await run(() => (id ? put(`/children/${id}`, body) : post('/children', body)), t('common.saved'))) childEditor = null;
  }
  async function deleteChild() {
    if (!confirm(t('children.confirm_delete', { name: childEditor.name }))) return;
    if (await run(() => del(`/children/${childEditor.id}`), t('children.deleted'))) childEditor = null;
  }

  // --- Members and invitations
  async function createInvite() {
    try { invite = await post('/family/invites'); } catch (e) { showError(e); }
  }
  async function shareInvite() {
    const text = t('invite.message', { family: family.name });
    if (navigator.share) {
      try { await navigator.share({ title: 'eaTrack', text, url: invite.link }); return; } catch { /* cancelled */ }
    }
    try { await navigator.clipboard.writeText(invite.link); toast(t('invite.copied')); } catch { /* the link stays visible */ }
  }
  async function remove(m) {
    const self = m.me;
    if (!confirm(self ? t('family.confirm_leave') : t('family.confirm_remove', { name: m.name }))) return;
    await run(async () => { await del(`/family/members/${m.id}`); if (self) await loadCatalog(); },
              self ? t('family.left') : t('family.removed'));
  }

  // --- Account
  const saveName = () => run(() => put('/account', { name: userName }), t('common.saved'));
  const saveLanguage = (l) => run(() => put('/account', { language: l }));
  const resend = () => run(() => post('/account/resend-verification'), t('account.verification_sent'));
  async function changePassword(e) {
    e.preventDefault();
    if (await run(() => post('/account/password', pwd), t('account.password_changed'))) pwd = { current: '', new: '' };
  }
  const unlink = (p) => run(() => del(`/account/identities/${p}`), t('account.unlinked'));
  async function deleteAccount() {
    const confirmation = user.has_password
      ? prompt(t('account.delete_password'))
      : prompt(t('account.delete_email', { email: user.email }));
    if (!confirmation) return;
    try {
      await del('/account', user.has_password ? { password: confirmation } : { confirm_email: confirmation });
      toast(t('account.deleted'));
      onlogout(true);
    } catch (e) { showError(e); }
  }

  // --- Data
  const children = $derived(app.me?.children ?? []);
  // Only children that still exist (after a deletion the choice may hold ids that are gone)
  const valid = $derived(chosen.filter((id) => children.some((c) => c.id === id)));
  const selection = $derived(valid.length ? children.filter((c) => valid.includes(c.id)) : children);
  const all = $derived(!valid.length || valid.length === children.length);
  const query = $derived(all ? '' : '?' + selection.map((c) => `child=${c.id}`).join('&'));
  const names = $derived(selection.map((c) => c.name).join(', '));
  const toggleChild = (id) => (chosen = valid.includes(id) ? valid.filter((x) => x !== id) : [...valid, id]);

  async function deleteData(profile) {
    if (!selection.length) return;
    if (!confirm(t(profile ? 'data.confirm_delete_children' : 'data.confirm_delete_meals', { names }))) return;
    const ids = selection.map((c) => c.id);
    if (await run(() => post('/children/delete-data', { ids, profile }), t(profile ? 'data.children_deleted' : 'data.meals_deleted'))) chosen = [];
  }

  async function importBackup() {
    if (!file || !confirm(t('data.confirm_import', { file: file.name }))) return;
    importing = true;
    const form = new FormData();
    form.append('file', file);
    try {
      await api('/import', { method: 'POST', form });
      toast(t('data.imported'));
      file = null; fileInput.value = '';
      await loadMe(); await loadCatalog();
    } catch (e) { showError(e); } finally { importing = false; }
  }
</script>

<header class="head"><h1>{t('nav.family')}</h1></header>

{#if family && user}
<div class="layout">
  <!-- Family and children -->
  <section class="card stack">
    <h2>{t('family.family')}</h2>
    {#if app.me.hub}
      <p><b>{family.name}</b></p>
      <p class="small muted">{t('hub.managed')} <a href="{app.me.hub.url}/#/family">{t('hub.open')}</a></p>
    {:else if admin}
      <form class="row" onsubmit={(e) => { e.preventDefault(); rename(); }}>
        <input class="input grow" bind:value={familyName} maxlength="80" aria-label={t('family.name')} />
        <button class="btn" disabled={!familyName.trim() || familyName === family.name}>{t('common.save')}</button>
      </form>
    {:else}
      <p><b>{family.name}</b></p>
    {/if}
    {#if app.me.families.length > 1}
      <div class="field">
        <span class="label">{t('family.switch')}</span>
        <div class="seg">
          {#each app.me.families as f (f.id)}
            <button class:on={f.id === app.me.family.id} onclick={() => switchFamily(f.id)}>{f.name}</button>
          {/each}
        </div>
      </div>
    {/if}

    <div class="spread sub">
      <h3>{t('children.title')}</h3>
      {#if !app.me.hub}<button class="btn soft sm" onclick={() => (childEditor = { name: '', birth_date: '', archived: false })}>{t('children.add')}</button>{/if}
    </div>
    {#if !app.me.children.length}<p class="muted small">{t('children.none')}</p>{/if}
    <ul class="list">
      {#each app.me.children as c (c.id)}
        <li>
          <div class="grow">
            <b>{c.name}</b>
            {#if c.birth_date}<span class="muted small"> · {t('children.months', { n: ageInMonths(c.birth_date) })}</span>{/if}
            {#if c.archived}<span class="badge">{t('children.archived')}</span>{/if}
          </div>
          <button class="btn ghost sm" onclick={() => (childEditor = { id: c.id, name: c.name, birth_date: c.birth_date ?? '', archived: !!c.archived })}>{t('common.edit')}</button>
        </li>
      {/each}
    </ul>
  </section>

  <!-- Members -->
  <section class="card stack">
    <h2>{t('family.members')}</h2>
    <ul class="list">
      {#each family.members as m (m.id)}
        <li>
          <div class="grow">
            <b>{m.name}</b>{#if m.me}<span class="muted small you">({t('family.you')})</span>{/if}
            <div class="tiny muted">{m.email} · {m.role === 'admin' ? t('family.role_admin') : t('family.role_member')}</div>
          </div>
          {#if app.me.hub}
          {:else if m.me && family.members.length > 1}
            <button class="btn ghost sm" onclick={() => remove(m)}>{t('family.leave')}</button>
          {:else if admin && !m.me}
            <button class="btn ghost sm" onclick={() => remove(m)}>{t('family.remove')}</button>
          {/if}
        </li>
      {/each}
    </ul>
    {#if admin && !app.me.hub}
      {#if invite}
        <div class="invite stack">
          <p class="small">{t('invite.instructions')}</p>
          <input class="input" readonly value={invite.link} onfocus={(e) => e.currentTarget.select()} aria-label={t('invite.link')} />
          <button class="btn primary" onclick={shareInvite}>{t('invite.share')}</button>
        </div>
      {:else}
        <button class="btn primary" onclick={createInvite}>{t('invite.create')}</button>
        <p class="tiny muted">{t('invite.explanation')}</p>
      {/if}
    {/if}
  </section>

  <!-- Account -->
  <section class="card stack">
    <h2>{t('account.title')}</h2>
    <form class="row" onsubmit={(e) => { e.preventDefault(); saveName(); }}>
      <input class="input grow" bind:value={userName} maxlength="80" aria-label={t('auth.your_name')} />
      <button class="btn" disabled={!userName.trim() || userName === user.name}>{t('common.save')}</button>
    </form>
    <div class="spread">
      <span class="small">{user.email}</span>
      {#if user.email_verified}<span class="badge ok">{t('account.verified')}</span>
      {:else}<button class="btn ghost sm" onclick={resend}>{t('account.resend')}</button>{/if}
    </div>
    <div class="spread">
      <span class="small">{t('common.language')}</span>
      <LanguageSwitch onchoose={saveLanguage} />
    </div>

    {#if !app.me.hub}
    <h3 class="sub">{user.has_password ? t('account.change_password') : t('account.set_password')}</h3>
    <form class="stack" onsubmit={changePassword}>
      {#if user.has_password}
        <input class="input" type="password" bind:value={pwd.current} placeholder={t('account.current_password')} autocomplete="current-password" required />
      {/if}
      <input class="input" type="password" bind:value={pwd.new} placeholder={t('auth.new_password')} autocomplete="new-password" minlength="8" required />
      <button class="btn">{t('auth.save_password')}</button>
    </form>
    {/if}

    {#if app.me.oidc?.length && !app.me.hub}
      <h3 class="sub">{t('account.sign_ins')}</h3>
      <ul class="list">
        {#each app.me.oidc as p (p.id)}
          <li>
            <span class="grow">{p.name}</span>
            {#if user.identities.includes(p.id)}
              <span class="badge ok">{t('account.linked')}</span>
              <button class="btn ghost sm" onclick={() => unlink(p.id)}>{t('account.unlink')}</button>
            {:else}
              <a class="btn ghost sm" href="/api/oidc/{encodeURIComponent(p.id)}/login?link=1">{t('account.link')}</a>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}

    <div class="row wrap sub">
      <button class="btn" onclick={() => onlogout()}>{t('account.sign_out')}</button>
      {#if !app.me.hub}<button class="btn danger" onclick={deleteAccount}>{t('account.delete')}</button>{/if}
    </div>
    <p class="tiny muted">{#if !app.me.hub}{t('account.delete_note')} {/if}<a href="#/privacy">{t('auth.privacy_notice')}</a></p>
  </section>

  <!-- doTrack -->
  <section class="card stack">
    <h2>🛒 {t('dotrack.title')}</h2>
    <p class="muted small">{t('dotrack.intro')}</p>
    {#if dt?.via_hub}
      <p class="small">{t('dotrack.via_hub')}{#if dt.list_name} · <b>{dt.list_name}</b>{/if}</p>
      {#if admin}
        {#if dtLists.length}
          <label class="field"><span class="label">{t('dotrack.list')}</span>
            <select class="input" value={dt.list_id ?? ''} onchange={(e) => dtChoose(e.currentTarget.value)}>
              <option value="" disabled>{t('dotrack.choose_list')}</option>
              {#each dtLists as l (l.id)}<option value={l.id}>{l.name}</option>{/each}
            </select></label>
        {:else}
          <p class="small">{t('dotrack.no_list_hub')}</p>
        {/if}
      {:else if !dt.list_id}
        <p class="small muted">{t('dotrack.admin_only')}</p>
      {/if}
    {:else}
    {#if dt?.connected}
      <p class="small">{t('dotrack.connected_to', { url: dt.url })}{#if dt.list_name} · <b>{dt.list_name}</b>{/if}</p>
    {/if}
    {#if admin}
      <form class="stack" onsubmit={dtConnect}>
        <label class="field"><span class="label">{t('dotrack.url')}</span>
          <input class="input" type="url" bind:value={dtForm.url} placeholder="https://dotrack.example.com" required /></label>
        <label class="field"><span class="label">{t('dotrack.token')}</span>
          <input class="input" bind:value={dtForm.token} placeholder={dt?.connected ? t('dotrack.token_keep') : 'dt_…'} autocomplete="off" /></label>
        <p class="tiny muted">{t('dotrack.token_note')}</p>
        <button class="btn" disabled={!dtForm.url.trim() || (!dt?.connected && !dtForm.token.trim())}>{dt?.connected ? t('dotrack.check') : t('dotrack.connect')}</button>
      </form>
      {#if dt?.connected && dtLists.length}
        <label class="field"><span class="label">{t('dotrack.list')}</span>
          <select class="input" value={dt.list_id ?? ''} onchange={(e) => dtChoose(e.currentTarget.value)}>
            <option value="" disabled>{t('dotrack.choose_list')}</option>
            {#each dtLists as l (l.id)}<option value={l.id}>{l.name}</option>{/each}
          </select></label>
      {:else if dt?.connected && !dt.list_id}
        <p class="small">{t('dotrack.no_list')}</p>
      {/if}
      {#if dt?.connected}<button class="btn ghost sm" onclick={dtDisconnect}>{t('dotrack.disconnect')}</button>{/if}
    {:else if !dt?.connected}
      <p class="small muted">{t('dotrack.admin_only')}</p>
    {/if}
    {/if}
  </section>

  <!-- Data -->
  <section class="card stack">
    <h2>{t('data.title')}</h2>
    <p class="muted small">{t('data.export_note')}</p>
    {#if children.length > 1}
      <div class="stack-sm">
        <span class="label">{t('data.children')}</span>
        <div class="chips">
          <button class="chip" class:on={all} onclick={() => (chosen = [])}>{t('data.all')}</button>
          {#each children as c (c.id)}
            <button class="chip" class:on={!all && valid.includes(c.id)} aria-pressed={!all && valid.includes(c.id)} onclick={() => toggleChild(c.id)}>{c.name}</button>
          {/each}
        </div>
      </div>
    {/if}
    <div class="row wrap">
      <a class="btn primary" href="/api/export/excel{query}" download>{t('data.excel')}</a>
      <a class="btn soft" href="/api/export/csv{query}" download>CSV</a>
    </div>
    <p class="tiny muted">{children.length > 1 ? t('data.export_of', { names: all ? t('data.all').toLowerCase() : names }) : ''}</p>
    <h3 class="sub">{t('data.backup')}</h3>
    <p class="muted small">{t('data.backup_note')}</p>
    <div class="row wrap">
      <a class="btn soft" href="/api/export/json" download>{t('data.json')}</a>
    </div>
    {#if admin}
      <h3 class="sub">{t('data.import')}</h3>
      <p class="muted small">{t('data.import_note')}</p>
      <label class="file">
        <input bind:this={fileInput} class="sr-only" type="file" accept=".json" onchange={(e) => (file = e.currentTarget.files[0] ?? null)} />
        <span class="btn soft sm">{t('data.choose_file')}</span>
        <span class="small grow filename">{file ? file.name : t('data.no_file')}</span>
      </label>
      <button class="btn" disabled={!file || importing} onclick={importBackup}>{importing ? t('common.wait') : t('data.import')}</button>

      {#if children.length}
        <h3 class="sub">{t('data.delete')}</h3>
        <p class="muted small">{t('data.delete_note', { names })}</p>
        <div class="row wrap">
          <button class="btn danger" onclick={() => deleteData(false)}>{t('data.delete_meals')}</button>
          {#if !app.me.hub}<button class="btn danger" onclick={() => deleteData(true)}>{t('data.delete_children')}</button>{/if}
        </div>
      {/if}
    {/if}
  </section>
</div>
{/if}

{#if childEditor}
  <Sheet title={childEditor.id ? t('children.edit') : t('children.add')} onclose={() => (childEditor = null)}>
    <div class="stack">
      <label class="field"><span class="label">{t('common.name')}</span>
        <input class="input" bind:value={childEditor.name} maxlength="60" disabled={!!app.me.hub} /></label>
      <label class="field"><span class="label">{t('auth.birth_date')}</span>
        <input class="input" type="date" bind:value={childEditor.birth_date} max={today()} disabled={!!app.me.hub} /></label>
      {#if app.me.hub}<p class="tiny muted">{t('hub.child_from_hub')}</p>{/if}
      {#if childEditor.id}
        <label class="toggle"><input type="checkbox" bind:checked={childEditor.archived} /> {t('children.archive')}</label>
      {/if}
    </div>
    {#snippet footer()}
      {#if childEditor.id && admin && !app.me.hub}<button class="btn danger" onclick={deleteChild}>{t('common.delete')}</button>{/if}
      <button class="btn primary grow" disabled={!childEditor.name.trim()} onclick={saveChild}>{t('common.save')}</button>
    {/snippet}
  </Sheet>
{/if}

<style>
  .head { margin-bottom: 18px; }
  .layout { display: grid; gap: 14px; grid-template-columns: 1fr; }
  @media (min-width: 1000px) { .layout { grid-template-columns: 1fr 1fr; align-items: start; } }
  .sub { margin-top: 8px; }
  .stack-sm { display: flex; flex-direction: column; gap: 6px; }
  .list { list-style: none; margin: 0; padding: 0; }
  .list li { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--line); }
  .list li:last-child { border: 0; }
  .list b { font-weight: 600; }
  .you { margin-left: 4px; }
  .invite { padding: 12px; border-radius: var(--r-md); background: var(--primary-soft); }
  .file { display: flex; align-items: center; gap: 10px; cursor: pointer; padding: 8px; border-radius: var(--r-md); border: 1px dashed var(--line-strong); }
  .file:focus-within { border-color: var(--primary); }
  .filename { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
</style>
