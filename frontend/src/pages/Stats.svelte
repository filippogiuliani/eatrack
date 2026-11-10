<script>
  import { get } from '../lib/api.js';
  import { app, category, showError } from '../lib/store.svelte.js';
  import { categoryName, t } from '../lib/i18n.svelte.js';
  import { fmtRange, fmtShort, today } from '../lib/date.js';
  import ChildSwitch from '../components/ChildSwitch.svelte';

  const PERIODS = [7, 14, 30, 90];
  let days = $state(7);
  let s = $state(null);

  $effect(() => {
    const d = days, child = app.childId;
    if (!child) { s = null; return; }
    get(`/stats?child=${child}&days=${d}&today=${today()}`).then((r) => (s = r)).catch(showError);
  });

  const maxTop = $derived(Math.max(1, ...(s?.top ?? []).map((x) => x.times)));
</script>

<header class="head">
  <div>
    <h1>{t('nav.stats')}</h1>
    {#if s}<p class="muted">{fmtRange(s.start, s.end)}</p>{/if}
  </div>
  <div class="seg period" role="radiogroup" aria-label={t('stats.period')}>
    {#each PERIODS as p (p)}
      <button role="radio" aria-checked={days === p} class:on={days === p} onclick={() => (days = p)}>{t('stats.days_' + p)}</button>
    {/each}
  </div>
</header>
<div class="hide-desktop switch"><ChildSwitch /></div>

{#if !app.childId}
  <p class="empty">{t('children.none')} <a href="#/family">{t('children.add_link')}</a></p>
{:else if s}
  <div class="tiles">
    <div class="card tile"><span class="v">{s.main_meals}</span><span class="k">{t('stats.main_meals')}</span></div>
    <div class="card tile"><span class="v">{s.snacks}</span><span class="k">{t('stats.snacks')}</span></div>
    <div class="card tile"><span class="v">{s.variety}</span><span class="k">{t('stats.variety')}</span></div>
    <div class="card tile"><span class="v">{s.new.length}</span><span class="k">{t('stats.new')}</span></div>
    <div class="card tile" class:alert={s.reactions}><span class="v">{s.reactions}</span><span class="k">{t('stats.reactions')}</span></div>
  </div>

  <div class="layout">
    <section class="card">
      <h2>{t('stats.balance')}</h2>
      <p class="muted small sub">{t('stats.balance_note', { n: s.main_meals })}</p>
      {#if !s.main_meals}
        <p class="empty small">{t('stats.no_main_meals')}</p>
      {:else}
        <ul class="bars">
          {#each s.categories as c (c.macro)}
            <li title={t('stats.bar_title', { name: categoryName(c.macro), n: c.main, total: s.main_meals, pct: c.pct, snacks: c.snack })}>
              <span class="name">{categoryName(c.macro)}</span>
              <span class="track"><span class="fill" style="width: {Math.max(c.pct, c.main ? 2 : 0)}%"></span></span>
              <span class="val"><b>{c.main}</b> <span class="muted">· {c.pct}%</span></span>
              {#if c.snack}<span class="snack tiny muted">{t('stats.at_snack', { n: c.snack })}</span>{/if}
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <section class="card">
      <h2>{t('stats.most_eaten')}</h2>
      {#if !s.top.length}<p class="muted small sub">{t('stats.no_data')}</p>{/if}
      <ul class="bars top">
        {#each s.top.slice(0, 12) as x (x.name)}
          <li title={t('foods.times', { n: x.times })}>
            <span class="name">{x.name}</span>
            <span class="track"><span class="fill" style="width: {(x.times / maxTop) * 100}%"></span></span>
            <span class="val"><b>{x.times}</b></span>
          </li>
        {/each}
      </ul>
    </section>

    {#if s.new.length}
      <section class="card">
        <h2>{t('stats.new_foods')}</h2>
        <ul class="list">
          {#each s.new as n (n.id)}
            <li><span>{n.name} <span class="muted small">· {categoryName(category(n.category_id).key)}</span></span><span class="badge ok">{fmtShort(n.first_time)}</span></li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if s.refused.length}
      <section class="card">
        <h2>{t('stats.refused')}</h2>
        <ul class="list">
          {#each s.refused as r (r.name)}
            <li><span>{r.name}</span><span class="badge warn">{t('foods.times', { n: r.times })}</span></li>
          {/each}
        </ul>
      </section>
    {/if}
  </div>
{/if}

<style>
  .head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 18px; }
  .switch { margin-bottom: 14px; }
  .period { max-width: 100%; }
  .tiles { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); margin-bottom: 14px; }
  .tile { display: flex; flex-direction: column; gap: 2px; padding: 16px; }
  .tile .v { font-weight: 600; font-size: 1.9rem; line-height: 1.1; letter-spacing: -0.02em; }
  .tile .k { font-weight: 500; color: var(--muted); font-size: 0.85rem; }
  .tile.alert .v { color: var(--danger); }
  .layout { display: grid; gap: 14px; grid-template-columns: 1fr; }
  @media (min-width: 1000px) { .layout { grid-template-columns: 1fr 1fr; align-items: start; } }
  h2 { margin-bottom: 4px; }
  .sub { margin-bottom: 14px; }
  .bars { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
  .bars.top { margin-top: 12px; }
  .bars li { display: grid; grid-template-columns: minmax(110px, 38%) 1fr auto; align-items: center; gap: 4px 10px; }
  .name { font-weight: 500; font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .track { height: 10px; border-radius: 4px; background: var(--surface-2); overflow: hidden; }
  .fill { display: block; height: 100%; border-radius: 4px; background: var(--primary); transition: width 0.4s ease; }
  .val { font-size: 0.9rem; min-width: 56px; text-align: right; }
  .val b { font-weight: 600; }
  .top .val { min-width: 28px; }
  .snack { grid-column: 2 / -1; margin-top: -4px; }
  .list { list-style: none; margin: 10px 0 0; padding: 0; }
  .list li { display: flex; justify-content: space-between; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--line); font-weight: 500; }
  .list li:last-child { border: 0; }
</style>
