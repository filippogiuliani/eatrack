<script>
  // The pediatrician's weekly plan for the selected child: frequencies per category and/or a menu per day.
  import { get, post, put } from '../lib/api.js';
  import { activeChildren, app, currentChild, food, showError, toast } from '../lib/store.svelte.js';
  import { categoryName, mealTypeName, t } from '../lib/i18n.svelte.js';
  import { weekdayName } from '../lib/date.js';
  import { MEAL_TYPES } from '../lib/constants.js';
  import ChildSwitch from '../components/ChildSwitch.svelte';
  import FoodChip from '../components/FoodChip.svelte';
  import FoodPicker from '../components/FoodPicker.svelte';
  import Sheet from '../components/Sheet.svelte';

  const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];

  let frequencies = $state({}); // macro -> { min, max } (input values)
  let menu = $state([]);        // [{ weekday, meal_type, notes, foods: [id] }]
  let loaded = $state(false);
  let slotEditor = $state(null); // { weekday, meal_type, notes, foods, alsoOn: [weekdays] }
  let copyFrom = $state('');

  // doTrack: the week's foods go to the family's shopping list
  let dotrack = $state(null);
  let shopping = $state(null); // { names: [...], chosen: [...] } while choosing what to send
  $effect(() => { get('/integrations/dotrack').then((d) => (dotrack = d)).catch(() => {}); });
  function openShopping() {
    const names = [...new Set(menu.flatMap((s) => s.foods).map((id) => food(id)?.name).filter(Boolean))].sort((a, b) => a.localeCompare(b));
    shopping = { names, chosen: [...names] };
  }
  const toggleName = (n) => (shopping.chosen = shopping.chosen.includes(n) ? shopping.chosen.filter((x) => x !== n) : [...shopping.chosen, n]);
  let sending = $state(false);
  async function sendShopping() {
    sending = true;
    try {
      const r = await post('/integrations/dotrack/send', { items: shopping.chosen });
      toast(t('dotrack.sent', { n: r.added, list: r.list_name }) + (r.skipped ? ' ' + t('dotrack.skipped', { n: r.skipped }) : ''));
      shopping = null;
    } catch (e) { showError(e); } finally { sending = false; }
  }

  const macros = $derived([...new Set(app.categories.map((c) => c.macro))]);
  const siblings = $derived(activeChildren().filter((c) => c.id !== app.childId));

  function apply(p) {
    const saved = Object.fromEntries(p.frequencies.map((f) => [f.macro, f]));
    frequencies = Object.fromEntries(macros.map((m) => [m, { min: saved[m]?.min ?? null, max: saved[m]?.max ?? null }]));
    menu = p.menu;
  }
  async function load() {
    loaded = false;
    if (!app.childId) return;
    try { apply(await get(`/plan?child=${app.childId}`)); loaded = true; } catch (e) { showError(e); }
  }
  $effect(() => { app.childId; load(); });

  async function save(message = t('common.saved')) {
    const body = {
      child_id: app.childId,
      frequencies: Object.entries(frequencies).map(([macro, f]) => ({ macro, min: f.min, max: f.max })),
      menu,
    };
    try { apply(await put('/plan', body)); toast(message); return true; } catch (e) { showError(e); await load(); return false; }
  }

  const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const filled = (v) => v !== null && v !== undefined && v !== '';
  const slot = (weekday, mealType) => menu.find((s) => s.weekday === weekday && s.meal_type === mealType);
  const hasMenu = $derived(menu.length > 0);
  const hasFrequencies = $derived(Object.values(frequencies).some((f) => filled(f.min) || filled(f.max)));

  function openSlot(weekday, mealType) {
    const s = slot(weekday, mealType);
    slotEditor = { weekday, meal_type: mealType, notes: s?.notes ?? '', foods: [...(s?.foods ?? [])], alsoOn: [] };
  }
  function toggleFood(id) {
    const i = slotEditor.foods.indexOf(id);
    if (i >= 0) slotEditor.foods.splice(i, 1);
    else slotEditor.foods.push(id);
  }
  const toggleWeekday = (d) => {
    const i = slotEditor.alsoOn.indexOf(d);
    if (i >= 0) slotEditor.alsoOn.splice(i, 1);
    else slotEditor.alsoOn.push(d);
  };
  async function saveSlot() {
    const { meal_type, notes, foods } = slotEditor;
    for (const d of [slotEditor.weekday, ...slotEditor.alsoOn]) {
      menu = menu.filter((s) => !(s.weekday === d && s.meal_type === meal_type));
      menu.push({ weekday: d, meal_type, notes, foods: [...foods] });
    }
    if (await save()) slotEditor = null;
  }
  async function clearSlot() {
    menu = menu.filter((s) => !(s.weekday === slotEditor.weekday && s.meal_type === slotEditor.meal_type));
    if (await save(t('plan.entry_removed'))) slotEditor = null;
  }

  async function clear(part) {
    if (!confirm(t(part === 'menu' ? 'plan.confirm_clear_menu' : 'plan.confirm_clear_frequencies'))) return;
    if (part === 'menu') menu = [];
    else for (const f of Object.values(frequencies)) { f.min = null; f.max = null; }
    await save(t('plan.cleared'));
  }

  async function copy() {
    const source = siblings.find((c) => c.id === Number(copyFrom));
    if (!source || !confirm(t('plan.confirm_copy', { from: source.name, to: currentChild()?.name }))) return;
    try { apply(await post('/plan/copy', { from: source.id, to: app.childId })); toast(t('plan.copied')); copyFrom = ''; } catch (e) { showError(e); }
  }
</script>

<header class="head">
  <div>
    <a class="small back" href="#/diary">‹ {t('diary.title')}</a>
    <h1>{t('plan.title')}</h1>
    <p class="muted">{currentChild()?.name ?? ''}</p>
  </div>
</header>
<div class="hide-desktop switch"><ChildSwitch /></div>

{#if !app.childId}
  <p class="empty">{t('children.none')} <a href="#/family">{t('children.add_link')}</a></p>
{:else if loaded}
  <p class="muted small intro">{t('plan.intro')}</p>

  <div class="layout">
    <section class="card stack">
      <div class="spread">
        <h2>{t('plan.frequencies')}</h2>
        {#if hasFrequencies}<button class="btn ghost sm" onclick={() => clear('frequencies')}>{t('plan.clear')}</button>{/if}
      </div>
      <p class="muted small">{t('plan.frequencies_note')}</p>
      <table class="freq">
        <thead>
          <tr><th></th><th>{t('plan.min')}</th><th>{t('plan.max')}</th></tr>
        </thead>
        <tbody>
          {#each macros.filter((m) => frequencies[m]) as m (m)}
            {@const f = frequencies[m]}
            <tr>
              <th scope="row">{categoryName(m)}</th>
              <td><input class="input num" type="number" min="0" max="28" inputmode="numeric" bind:value={f.min} onchange={() => save()} aria-label={t('plan.min_of', { name: categoryName(m) })} /></td>
              <td><input class="input num" type="number" min="0" max="28" inputmode="numeric" bind:value={f.max} onchange={() => save()} aria-label={t('plan.max_of', { name: categoryName(m) })} /></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>

    <section class="card stack">
      <div class="spread">
        <h2>{t('plan.menu')}</h2>
        {#if hasMenu}<button class="btn ghost sm" onclick={() => clear('menu')}>{t('plan.clear')}</button>{/if}
      </div>
      <p class="muted small">{t('plan.menu_note')}</p>
      {#if hasMenu && dotrack?.connected && dotrack.list_id}
        <button class="btn soft sm shop" onclick={openShopping}>🛒 {t('dotrack.send_button', { list: dotrack.list_name })}</button>
      {/if}
      <div class="days">
        {#each WEEKDAYS as d (d)}
          <div class="day">
            <h3>{weekdayName(d)}</h3>
            {#each MEAL_TYPES.filter((m) => slot(d, m)) as mealType (mealType)}
              {@const s = slot(d, mealType)}
              <button class="entry" onclick={() => openSlot(d, mealType)}>
                <span class="type">{mealTypeName(mealType)}</span>
                <span class="what">{s.foods.map((id) => food(id)?.name ?? '?').join(', ')}{s.foods.length && s.notes ? ' · ' : ''}{#if s.notes}<i>{s.notes}</i>{/if}</span>
              </button>
            {/each}
            <div class="empty-slots">
              {#each MEAL_TYPES.filter((m) => !slot(d, m)) as mealType (mealType)}
                <button class="add" onclick={() => openSlot(d, mealType)}>+ {mealTypeName(mealType)}</button>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    </section>

    {#if siblings.length}
      <section class="card stack">
        <h2>{t('plan.copy_title')}</h2>
        <div class="row wrap">
          <select class="input grow" bind:value={copyFrom} aria-label={t('plan.copy_from')}>
            <option value="">{t('plan.copy_from')}</option>
            {#each siblings as c (c.id)}<option value={String(c.id)}>{c.name}</option>{/each}
          </select>
          <button class="btn" disabled={!copyFrom} onclick={copy}>{t('plan.copy')}</button>
        </div>
      </section>
    {/if}
  </div>
{/if}

{#if shopping}
  <Sheet title={t('dotrack.send_title', { list: dotrack.list_name })} onclose={() => (shopping = null)}>
    <div class="stack">
      <p class="muted small">{t('dotrack.send_note')}</p>
      <div class="chips">
        {#each shopping.names as n (n)}
          <button type="button" class="chip" class:on={shopping.chosen.includes(n)} aria-pressed={shopping.chosen.includes(n)} onclick={() => toggleName(n)}>{n}</button>
        {/each}
      </div>
    </div>
    {#snippet footer()}
      <button class="btn primary grow" disabled={!shopping.chosen.length || sending} onclick={sendShopping}>
        {sending ? t('common.wait') : t('dotrack.send', { n: shopping.chosen.length })}</button>
    {/snippet}
  </Sheet>
{/if}

{#if slotEditor}
  <Sheet title={`${capitalize(weekdayName(slotEditor.weekday))} · ${mealTypeName(slotEditor.meal_type)}`} onclose={() => (slotEditor = null)} wide>
    <div class="stack gap">
      <section class="stack">
        <span class="label">{t('plan.planned_foods')}</span>
        {#if slotEditor.foods.length}
          <div class="chips">
            {#each slotEditor.foods as id (id)}
              <FoodChip name={food(id)?.name ?? '?'} on onclick={() => toggleFood(id)} />
            {/each}
          </div>
        {:else}
          <p class="muted small">{t('plan.no_foods')}</p>
        {/if}
        <div class="picker"><FoodPicker selected={slotEditor.foods} ontoggle={toggleFood} /></div>
      </section>
      <label class="field">
        <span class="label">{t('meal.notes')}</span>
        <textarea class="input" bind:value={slotEditor.notes} rows="2" maxlength="500" placeholder={t('plan.notes_example')}></textarea>
      </label>
      <div class="stack">
        <span class="label">{t('plan.also_on')}</span>
        <div class="chips">
          {#each WEEKDAYS.filter((d) => d !== slotEditor.weekday) as d (d)}
            <button type="button" class="chip" class:on={slotEditor.alsoOn.includes(d)} aria-pressed={slotEditor.alsoOn.includes(d)} onclick={() => toggleWeekday(d)}>{weekdayName(d, 'short')}</button>
          {/each}
        </div>
      </div>
    </div>
    {#snippet footer()}
      {#if slot(slotEditor.weekday, slotEditor.meal_type)}<button class="btn danger" onclick={clearSlot}>{t('plan.remove')}</button>{/if}
      <button class="btn primary grow" disabled={!slotEditor.foods.length && !slotEditor.notes.trim()} onclick={saveSlot}>{t('common.save')}</button>
    {/snippet}
  </Sheet>
{/if}

<style>
  .head { margin-bottom: 12px; }
  .back { color: var(--muted); text-decoration: none; }
  .back:hover { color: var(--primary); }
  .switch { margin-bottom: 14px; }
  .intro { margin: 0 0 14px; max-width: 70ch; }
  .layout { display: grid; gap: 14px; grid-template-columns: 1fr; }
  @media (min-width: 1000px) { .layout { grid-template-columns: minmax(280px, 1fr) 2fr; align-items: start; } }
  .gap { gap: 20px; }
  .freq { border-collapse: collapse; width: 100%; }
  .freq th, .freq td { padding: 4px 0; text-align: left; font-weight: 500; }
  .freq thead th { font-size: 0.75rem; color: var(--muted); text-align: center; }
  .freq td { width: 84px; padding-left: 8px; }
  .num { width: 76px; text-align: center; }
  .days { display: grid; gap: 12px; grid-template-columns: 1fr; }
  @media (min-width: 640px) { .days { grid-template-columns: 1fr 1fr; } }
  .day h3 { margin: 0 0 6px; font-size: 0.92rem; text-transform: capitalize; }
  .entry {
    display: flex; gap: 10px; width: 100%; padding: 7px 10px; margin-bottom: 4px; text-align: left; cursor: pointer;
    border: 1px solid var(--line); border-radius: var(--r-sm); background: var(--surface); color: var(--ink); font: inherit;
  }
  .empty-slots { display: flex; flex-wrap: wrap; gap: 4px; }
  .add {
    padding: 3px 9px; border: 1px dashed var(--line-strong); border-radius: var(--r-xs); background: transparent;
    color: var(--muted); font: inherit; font-size: 0.8rem; cursor: pointer;
  }
  .add:hover { border-color: var(--primary); color: var(--primary); }
  .entry:hover { border-color: var(--primary); }
  .type { flex: 0 0 72px; font-size: 0.8rem; font-weight: 600; color: var(--muted); padding-top: 1px; }
  .what { font-size: 0.88rem; min-width: 0; overflow-wrap: anywhere; }
  .what i { color: var(--muted); }
  .picker { max-height: 46vh; overflow-y: auto; }
  .shop { align-self: flex-start; }
</style>
