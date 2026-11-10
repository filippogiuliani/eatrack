<script>
  import { del, post, put } from '../lib/api.js';
  import { app, currentChild, loadCatalog, showError, toast } from '../lib/store.svelte.js';
  import { categoryName, t } from '../lib/i18n.svelte.js';
  import { fmtDate } from '../lib/date.js';
  import Sheet from '../components/Sheet.svelte';
  import ChildSwitch from '../components/ChildSwitch.svelte';

  let q = $state('');
  let categoryFilter = $state(null);
  let showArchived = $state(false);
  let editor = $state(null); // { id?, name, category_id, archived }

  // The "tried since…" figures refer to the selected child
  $effect(() => { app.childId; loadCatalog().catch(showError); });

  const norm = (s) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const groups = $derived(
    app.categories
      .filter((c) => !categoryFilter || c.id === categoryFilter)
      .map((c) => ({
        c,
        items: app.foods.filter((f) => f.category_id === c.id && !!f.archived === showArchived && (!q.trim() || norm(f.name).includes(norm(q.trim())))),
      }))
      .filter((g) => g.items.length)
  );
  const tried = $derived(app.foods.filter((f) => f.first_time).length);
  const archivedCount = $derived(app.foods.filter((f) => f.archived).length);

  async function save() {
    const { id, ...body } = editor;
    try {
      if (id) await put(`/foods/${id}`, body);
      else await post('/foods', body);
      toast(id ? t('foods.updated') : t('foods.added', { name: body.name }));
      editor = null;
      await loadCatalog();
    } catch (e) { showError(e); }
  }
  async function remove() {
    if (!confirm(t('foods.confirm_delete', { name: editor.name }))) return;
    try {
      const r = await del(`/foods/${editor.id}`);
      toast(r.archived ? t('foods.archived_msg') : t('foods.deleted'));
      editor = null;
      await loadCatalog();
    } catch (e) { showError(e); }
  }
</script>

<header class="head">
  <div>
    <h1>{t('nav.foods')}</h1>
    <p class="muted">
      {#if currentChild()}{t('foods.tried', { n: tried, total: app.foods.length - archivedCount, name: currentChild().name })}{/if}
    </p>
  </div>
  <button class="btn primary" onclick={() => (editor = { name: q.trim(), category_id: categoryFilter ?? app.categories[0]?.id, archived: false })}>{t('foods.new')}</button>
</header>
<div class="hide-desktop switch"><ChildSwitch /></div>

<div class="stack filters">
  <div class="search"><input class="input" type="search" bind:value={q} placeholder={t('foods.search')} aria-label={t('foods.search')} /></div>
  <div class="chips scroll">
    <button class="chip" class:on={!categoryFilter} onclick={() => (categoryFilter = null)}>{t('common.all_f')}</button>
    {#each app.categories as c (c.id)}
      <button class="chip" class:on={categoryFilter === c.id} onclick={() => (categoryFilter = categoryFilter === c.id ? null : c.id)}>{categoryName(c.key)}</button>
    {/each}
  </div>
</div>

{#each groups as g (g.c.id)}
  <section class="section">
    <h2>{categoryName(g.c.key)} <span class="badge">{g.items.length}</span></h2>
    <div class="grid">
      {#each g.items as f (f.id)}
        <button class="card item" onclick={() => (editor = { id: f.id, name: f.name, category_id: f.category_id, archived: !!f.archived })}>
          <span class="name">{f.name}</span>
          <span class="meta">
            {#if f.first_time}
              <span class="badge ok">{t('foods.since', { date: fmtDate(f.first_time) })}</span>
              <span class="badge">{t('foods.times', { n: f.times })}</span>
            {:else if f.times}
              <span class="badge">{t('foods.times', { n: f.times })}</span>
            {:else}
              <span class="badge primary">{t('foods.never')}</span>
            {/if}
            {#if f.refused}<span class="badge warn">{t('foods.refused_n', { n: f.refused })}</span>{/if}
            {#if f.reactions}<span class="badge danger">{t('foods.reactions_n', { n: f.reactions })}</span>{/if}
          </span>
        </button>
      {/each}
    </div>
  </section>
{:else}
  <p class="empty">{t('foods.none_found')}</p>
{/each}

{#if archivedCount}
  <button class="btn ghost" onclick={() => (showArchived = !showArchived)}>
    {showArchived ? t('foods.restore') : t('foods.archived', { n: archivedCount })}
  </button>
{/if}

{#if editor}
  <Sheet title={editor.id ? t('foods.edit') : t('foods.new')} onclose={() => (editor = null)}>
    <div class="stack">
      <label class="field">
        <span class="label">{t('common.name')}</span>
        <input class="input" bind:value={editor.name} />
      </label>
      <div class="field">
        <span class="label">{t('foods.category')}</span>
        <div class="chips">
          {#each app.categories as c (c.id)}
            <button type="button" class="chip" class:on={editor.category_id === c.id} onclick={() => (editor.category_id = c.id)}>{categoryName(c.key)}</button>
          {/each}
        </div>
      </div>
      {#if editor.id}
        <label class="toggle"><input type="checkbox" bind:checked={editor.archived} /> {t('foods.archive')}</label>
      {/if}
    </div>
    {#snippet footer()}
      {#if editor.id}<button class="btn danger" onclick={remove}>{t('common.delete')}</button>{/if}
      <button class="btn primary grow" disabled={!editor.name?.trim() || !editor.category_id} onclick={save}>{t('common.save')}</button>
    {/snippet}
  </Sheet>
{/if}

<style>
  .head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
  .switch { margin-bottom: 14px; }
  .filters { margin-bottom: 20px; }
  .section { margin-bottom: 22px; }
  .section h2 { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
  .item { text-align: left; cursor: pointer; padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; }
  .item:hover { border-color: var(--line-strong); }
  .name { font-weight: 600; }
  .meta { display: flex; flex-wrap: wrap; gap: 4px; }
</style>
