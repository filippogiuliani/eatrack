<script>
  import { get } from '../lib/api.js';
  import { app, currentChild, food, showError } from '../lib/store.svelte.js';
  import { categoryName, mealTypeName, t } from '../lib/i18n.svelte.js';
  import { addDays, fmtLong, fmtRange, relative, today, weekdayOf } from '../lib/date.js';
  import { DIARY_SLOTS, MEAL_TYPES, mealTypeForTime } from '../lib/constants.js';
  import MealCard from '../components/MealCard.svelte';
  import MealEditor from '../components/MealEditor.svelte';
  import ChildSwitch from '../components/ChildSwitch.svelte';

  let end = $state(today());
  let meals = $state([]);
  let loading = $state(true);
  let editor = $state(null); // { meal } or { initial }
  let plan = $state({ frequencies: [], menu: [] });
  let week = $state(null); // progress against the frequencies in the Monday–Sunday week containing "end"

  const start = $derived(addDays(end, -6));
  const atToday = $derived(end >= today());
  const days = $derived(Array.from({ length: 7 }, (_, i) => addDays(end, -i)));

  async function load() {
    if (!app.childId) { meals = []; loading = false; return; }
    loading = true;
    try { meals = await get(`/meals?child=${app.childId}&from=${start}&to=${end}`); } catch (e) { showError(e); } finally { loading = false; }
  }
  $effect(() => { end; app.childId; load(); });

  async function loadPlan() {
    if (!app.childId) { plan = { frequencies: [], menu: [] }; return; }
    try { plan = await get(`/plan?child=${app.childId}`); } catch (e) { showError(e); }
  }
  async function loadWeek() {
    if (!app.childId || !plan.frequencies.length) { week = null; return; }
    try { week = await get(`/plan/week?child=${app.childId}&date=${end}`); } catch (e) { showError(e); }
  }
  $effect(() => { app.childId; loadPlan(); });
  $effect(() => { end; plan; loadWeek(); });

  const planned = (day, mealType) => plan.menu.find((m) => m.weekday === weekdayOf(day) && m.meal_type === mealType);
  const describe = (m) => [m.foods.map((id) => food(id)?.name ?? '?').join(', '), m.notes].filter(Boolean).join(' · ');
  function status(f) {
    if (f.max !== null && f.times > f.max) return { cls: 'over', text: t('plan.over', { n: f.times - f.max }) };
    if (f.min !== null && f.times < f.min) return { cls: '', text: t('plan.to_go', { n: f.min - f.times }) };
    return { cls: 'ok', text: t('plan.on_track') };
  }
  const target = (f) => (f.min !== null && f.max !== null ? (f.min === f.max ? `${f.min}` : `${f.min}–${f.max}`)
    : f.min !== null ? `≥ ${f.min}` : `≤ ${f.max}`);

  function slotsOf(day) {
    const ofDay = meals.filter((m) => m.date === day);
    const fromPlan = plan.menu.filter((m) => m.weekday === weekdayOf(day)).map((m) => m.meal_type);
    const types = [...new Set([...ofDay.map((m) => m.meal_type), ...DIARY_SLOTS, ...fromPlan])]
      .sort((a, b) => MEAL_TYPES.indexOf(a) - MEAL_TYPES.indexOf(b));
    return types.map((mealType) => ({ mealType, meals: ofDay.filter((m) => m.meal_type === mealType) }));
  }

  const newMeal = (date = today(), mealType = mealTypeForTime(), foods = []) => (editor = { initial: { date, mealType, foods } });
  const saved = () => { editor = null; load(); loadWeek(); };
</script>

<header class="head">
  <div>
    <h1>{t('diary.title')}</h1>
    <p class="muted">{currentChild()?.name ?? ''}{currentChild() ? ' · ' : ''}{fmtRange(start, end)}</p>
  </div>
  <div class="row">
    <button class="btn icon" onclick={() => (end = addDays(end, -7))} aria-label={t('diary.previous')}>‹</button>
    <button class="btn sm" disabled={atToday} onclick={() => (end = today())}>{t('date.today')}</button>
    <button class="btn icon" disabled={atToday} onclick={() => (end = addDays(end, 7))} aria-label={t('diary.next')}>›</button>
    <a class="btn soft" href="#/plan">{t('plan.short_title')}</a>
    <button class="btn primary hide-mobile" disabled={!app.childId} onclick={() => newMeal()}>{t('meal.new')}</button>
  </div>
</header>
<div class="hide-desktop switch"><ChildSwitch /></div>

{#if !app.childId}
  <p class="empty">{t('children.none')} <a href="#/family">{t('children.add_link')}</a></p>
{:else}
  {#if week?.frequencies.length}
    <section class="card targets">
      <div class="spread">
        <h2>{t('plan.week', { range: fmtRange(week.start, week.end) })}</h2>
        <a class="small" href="#/plan">{t('common.edit')}</a>
      </div>
      <ul>
        {#each week.frequencies as f (f.macro)}
          {@const st = status(f)}
          {@const ceiling = Math.max(f.max ?? f.min ?? 1, f.min ?? 0, f.times, 1)}
          <li class={st.cls}>
            <span class="name">{categoryName(f.macro)}</span>
            <span class="bar" aria-hidden="true"><span style="width: {Math.min(100, (f.times / ceiling) * 100)}%"></span></span>
            <span class="num">{f.times}<span class="muted">&nbsp;/ {target(f)}</span></span>
            <span class="tiny status">{st.text}</span>
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  <div class="days" class:loading>
    {#each days as day (day)}
      <section class="day card">
        <h2 class="heading">
          {#if relative(day)}<span class="rel">{relative(day)}</span>{/if}
          <span class="date">{fmtLong(day)}</span>
        </h2>
        <div class="slots">
          {#each slotsOf(day) as s (s.mealType)}
            <div class="slot">
              {#each s.meals as m (m.id)}
                <MealCard meal={m} onclick={() => (editor = { meal: m })} />
              {:else}
                {@const p = planned(day, s.mealType)}
                {#if p}
                  <button class="slot-empty planned" onclick={() => newMeal(day, s.mealType, p.foods)} title={t('plan.log_planned')}>
                    <span>+ {mealTypeName(s.mealType)}</span>
                    <span class="planned-text">{describe(p)}</span>
                  </button>
                {:else}
                  <button class="slot-empty" onclick={() => newMeal(day, s.mealType)}>+ {mealTypeName(s.mealType)}</button>
                {/if}
              {/each}
            </div>
          {/each}
        </div>
      </section>
    {/each}
  </div>
  <button class="fab hide-desktop" onclick={() => newMeal()} aria-label={t('meal.new')}>+</button>
{/if}

{#if editor}
  <MealEditor meal={editor.meal ?? null} initial={editor.initial ?? {}} onclose={() => (editor = null)} onsaved={saved} />
{/if}

<style>
  .head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
  .switch { margin-bottom: 14px; }
  .days { display: flex; flex-direction: column; gap: 14px; transition: opacity 0.2s; }
  .days.loading { opacity: 0.55; }
  .heading { display: flex; align-items: baseline; gap: 10px; margin-bottom: 12px; font-size: 1.05rem; }
  .rel { color: var(--primary); }
  .date { text-transform: capitalize; }
  .rel + .date { color: var(--muted); font-size: 0.92rem; font-weight: 500; text-transform: none; }
  .slots { display: grid; gap: 10px; grid-template-columns: 1fr; }
  @media (min-width: 900px) { .slots { grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); align-items: start; } }
  .slot { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .slot-empty {
    min-height: 52px; border: 1px dashed var(--line-strong); border-radius: var(--r-md); background: transparent;
    color: var(--muted); font-weight: 500; cursor: pointer; transition: border-color 0.15s, color 0.15s, background 0.15s;
  }
  .slot-empty:hover { border-color: var(--primary); color: var(--primary); background: var(--primary-soft); }
  .slot-empty.planned { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 8px 12px; text-align: left; }
  .planned-text { font-weight: 400; font-size: 0.82rem; color: var(--ink); opacity: 0.75; overflow-wrap: anywhere; }
  .targets { margin-bottom: 14px; }
  .targets h2 { font-size: 1rem; margin: 0; }
  .targets a { color: var(--primary); }
  .targets ul { list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 6px 18px; grid-template-columns: 1fr; }
  @media (min-width: 900px) { .targets ul { grid-template-columns: 1fr 1fr; } }
  .targets li { display: grid; grid-template-columns: 92px 1fr auto; grid-template-areas: 'name bar num' '. status status'; align-items: center; gap: 0 10px; }
  .targets .name { grid-area: name; font-size: 0.88rem; font-weight: 500; }
  .targets .bar { grid-area: bar; height: 6px; border-radius: 3px; background: var(--surface-2); overflow: hidden; }
  .targets .bar span { display: block; height: 100%; background: var(--line-strong); }
  .targets li.ok .bar span { background: var(--primary); }
  .targets li.over .bar span { background: var(--danger); }
  .targets .num { grid-area: num; font-size: 0.85rem; font-variant-numeric: tabular-nums; }
  .targets .status { grid-area: status; color: var(--muted); }
  .targets li.over .status { color: var(--danger); }
  .fab {
    position: fixed; right: 18px; bottom: calc(var(--nav-h) + 18px + env(safe-area-inset-bottom)); z-index: 40;
    width: 56px; height: 56px; border-radius: var(--r-md); border: 0; cursor: pointer;
    background: var(--primary); color: var(--primary-ink); font-size: 1.8rem; box-shadow: var(--shadow-lg);
  }
</style>
