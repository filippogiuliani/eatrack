<script>
  import { get, post } from '../lib/api.js';
  import { showError, toast } from '../lib/store.svelte.js';
  import { locationName, t } from '../lib/i18n.svelte.js';
  import { LOCATIONS, locationInfo } from '../lib/constants.js';
  import { daysBetween, fmtShort, today } from '../lib/date.js';
  import JarEditor from '../components/JarEditor.svelte';

  let jars = $state([]);
  let used = $state(null);
  let filter = $state('all');
  let editor = $state(null);

  async function load() {
    try { jars = await get('/jars'); } catch (e) { showError(e); }
  }
  $effect(() => { load(); });

  // Group jars with the same contents and location
  const sections = $derived(
    LOCATIONS.filter((l) => filter === 'all' || filter === l.id).map((l) => {
      const groups = new Map();
      for (const j of jars.filter((x) => x.location === l.id)) {
        const key = j.foods.map((f) => f.id).sort((x, y) => x - y).join(',');
        if (!groups.has(key)) groups.set(key, { key, foods: j.foods, items: [] });
        groups.get(key).items.push(j);
      }
      for (const g of groups.values()) g.items.sort((a, b) => a.made_on.localeCompare(b.made_on));
      return { location: l, groups: [...groups.values()], total: jars.filter((x) => x.location === l.id).length };
    })
  );

  const freeLabels = $derived.by(() => {
    const taken = new Set(jars.map((j) => j.label));
    const out = [];
    for (let n = 1; out.length < 30; n++) if (!taken.has(String(n))) out.push(n);
    return out;
  });

  function age(j) {
    const days = daysBetween(today(), j.made_on);
    const l = locationInfo(j.location);
    return { days, level: days >= l.expired ? 'danger' : days >= l.warn ? 'warn' : '' };
  }

  async function move(j, location) {
    try { await post(`/jars/${j.id}/move`, { location }); toast(t('pantry.moved', { label: j.label })); load(); } catch (e) { showError(e); }
  }
  async function showUsed() {
    try { used = await get('/jars?status=used'); } catch (e) { showError(e); }
  }
  const saved = () => { editor = null; load(); };
</script>

<header class="head">
  <div>
    <h1>{t('nav.pantry')}</h1>
    <p class="muted">{t('pantry.ready', { n: jars.length })}</p>
  </div>
  <button class="btn primary" onclick={() => (editor = {})}>{t('pantry.new')}</button>
</header>

<div class="seg filter">
  <button class:on={filter === 'all'} onclick={() => (filter = 'all')}>{t('common.all')}</button>
  {#each LOCATIONS as l (l.id)}
    <button class:on={filter === l.id} onclick={() => (filter = l.id)}>{locationName(l.id)}</button>
  {/each}
</div>

{#each sections as s (s.location.id)}
  {#if s.total || filter !== 'all'}
    <section class="section">
      <h2>{locationName(s.location.id)} <span class="badge">{s.total}</span></h2>
      {#if !s.groups.length}
        <p class="empty small">{t('pantry.empty')}</p>
      {/if}
      <div class="grid">
        {#each s.groups as g (g.key)}
          <article class="card group">
            <div class="spread top">
              <div class="foods">
                {#each g.foods as f (f.id)}
                  <span class="food">{f.name}</span>
                {/each}
              </div>
              <span class="count">×{g.items.length}</span>
            </div>
            <ul>
              {#each g.items as j (j.id)}
                {@const a = age(j)}
                <li>
                  <button class="jar" onclick={() => (editor = { jar: j })}>
                    <b>{t('pantry.n', { label: j.label })}</b>
                    <span class="badge {a.level}">{fmtShort(j.made_on)} · {a.days === 0 ? t('date.today').toLowerCase() : t('pantry.days', { n: a.days })}</span>
                    {#if j.notes}<span class="tiny muted notes">{j.notes}</span>{/if}
                  </button>
                  {#if j.location === 'freezer'}
                    <button class="btn sm ghost" title={t('pantry.thaw_title')} onclick={() => move(j, 'fridge')}>{t('pantry.to_fridge')}</button>
                  {/if}
                </li>
              {/each}
            </ul>
            <button class="btn ghost sm" onclick={() => (editor = { template: g.items[0] })}>{t('pantry.make_again')}</button>
          </article>
        {/each}
      </div>
    </section>
  {/if}
{/each}

{#if !jars.length}
  <p class="empty">{t('pantry.none')}</p>
{/if}

<section class="section">
  {#if used}
    <h2>{t('pantry.used')}</h2>
    <div class="card">
      {#if !used.length}<p class="muted">{t('common.none')}</p>{/if}
      <ul class="used">
        {#each used as j (j.id)}
          <li><b>{t('pantry.n', { label: j.label })}</b> <span class="muted">{j.foods.map((f) => f.name).join(' + ')}</span> <span class="badge ok">{fmtShort(j.used_on)}</span></li>
        {/each}
      </ul>
    </div>
  {:else}
    <button class="btn ghost" onclick={showUsed}>{t('pantry.show_used')}</button>
  {/if}
</section>

{#if editor}
  <JarEditor jar={editor.jar ?? null} template={editor.template ?? null} {freeLabels} onclose={() => (editor = null)} onsaved={saved} />
{/if}

<style>
  .head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
  .filter { margin-bottom: 18px; max-width: 520px; }
  .section { margin-bottom: 24px; }
  .section h2 { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
  .grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); }
  .group { display: flex; flex-direction: column; gap: 10px; padding: 16px; }
  .top { align-items: flex-start; }
  .foods { display: flex; flex-wrap: wrap; gap: 4px 12px; font-weight: 600; }
  .count { font-family: var(--font-title); font-size: 0.95rem; font-weight: 600; color: var(--ink); background: var(--surface-2); border-radius: var(--r-sm); padding: 2px 12px; }
  ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  li { display: flex; align-items: center; gap: 6px; }
  .jar {
    flex: 1; min-width: 0; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; text-align: left;
    border: 0; cursor: pointer; padding: 9px 12px; border-radius: var(--r-sm); background: var(--surface-2);
  }
  .jar:hover { background: var(--primary-soft); }
  .notes { width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .used li { display: block; padding: 6px 0; border-bottom: 1px solid var(--line); }
  .used li:last-child { border: 0; }
</style>
