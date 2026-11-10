<script>
  import { onMount, untrack } from 'svelte';
  import { del, get, post, put } from '../lib/api.js';
  import { activeChildren, app, food, loadCatalog, showError, toast } from '../lib/store.svelte.js';
  import { inSentence, locationName, mealTypeName, t } from '../lib/i18n.svelte.js';
  import { AMOUNTS, MEAL_TYPES } from '../lib/constants.js';
  import { fmtLong, fmtShort } from '../lib/date.js';
  import Sheet from './Sheet.svelte';
  import FoodChip from './FoodChip.svelte';
  import FoodPicker from './FoodPicker.svelte';

  // meal: an existing meal to edit, or null. initial: { date, mealType, foods } for a new one
  let { meal: mealProp = null, initial: initialProp = {}, onclose, onsaved } = $props();
  // Read once: the editor is recreated every time it opens
  const meal = untrack(() => mealProp);
  const initial = untrack(() => initialProp);

  let childId = $state(meal?.child_id ?? untrack(() => app.childId));
  let date = $state(meal?.date ?? initial.date);
  let mealType = $state(meal?.meal_type ?? initial.mealType ?? 'lunch');
  let notes = $state(meal?.notes ?? '');
  let reaction = $state(!!meal?.reaction);
  // items: [{ id, amount, jar }] – jar = id of the jar the food comes from
  let items = $state(meal
    ? meal.foods.map((f) => ({ id: f.id, amount: f.amount, jar: null }))
    : (initial.foods ?? []).map((id) => ({ id, amount: 'full', jar: null }))); // from the weekly plan
  let chosenJars = $state((meal?.jars ?? []).map((j) => j.id));
  let jars = $state([]);
  let previous = $state(null);
  let showPicker = $state(!meal);
  let saving = $state(false);
  const children = $derived(activeChildren());

  onMount(async () => {
    try {
      const available = await get('/jars');
      // When editing, also show the jars already used in this meal
      jars = [...(meal?.jars ?? []).map((j) => ({ ...j, foods: [], usedHere: true })), ...available];
    } catch (e) { showError(e); }
  });

  const selected = $derived(items.map((i) => i.id));

  function toggleFood(id) {
    const i = items.findIndex((x) => x.id === id);
    if (i >= 0) items.splice(i, 1);
    else items.push({ id, amount: 'full', jar: null });
  }

  function toggleJar(j) {
    const i = chosenJars.indexOf(j.id);
    if (i >= 0) {
      chosenJars.splice(i, 1);
      items = items.filter((x) => x.jar !== j.id);
    } else {
      chosenJars.push(j.id);
      for (const f of j.foods) if (!items.some((x) => x.id === f.id)) items.push({ id: f.id, amount: 'full', jar: j.id });
    }
  }

  async function loadPrevious() {
    try { previous = await get(`/meals/recent?child=${childId}&meal_type=${encodeURIComponent(mealType)}`); } catch (e) { showError(e); }
  }
  function copyFrom(m) {
    for (const f of m.foods) {
      const x = items.find((i) => i.id === f.id);
      if (x) x.amount = f.amount;
      else items.push({ id: f.id, amount: f.amount, jar: null });
    }
    previous = null;
    toast(t('meal.copied'));
  }

  async function save() {
    saving = true;
    const body = { child_id: childId, date, meal_type: mealType, notes, reaction,
                   foods: items.map(({ id, amount }) => ({ id, amount })), jars: chosenJars };
    try {
      if (meal) await put(`/meals/${meal.id}`, body);
      else await post('/meals', body);
      toast(meal ? t('meal.updated') : t('meal.saved'));
      loadCatalog();
      onsaved?.();
    } catch (e) { showError(e); } finally { saving = false; }
  }

  async function remove() {
    if (!confirm(t('meal.confirm_delete'))) return;
    try { await del(`/meals/${meal.id}`); toast(t('meal.deleted')); onsaved?.(); } catch (e) { showError(e); }
  }
</script>

<Sheet title={meal ? t('meal.edit') : t('meal.new')} {onclose} wide>
  <div class="stack gap">
    {#if children.length > 1}
      <div class="field">
        <span class="label">{t('children.child')}</span>
        <div class="seg">
          {#each children as c (c.id)}
            <button type="button" class:on={childId === c.id} onclick={() => (childId = c.id)}>{c.name}</button>
          {/each}
        </div>
      </div>
    {/if}
    <div class="top">
      <label class="field">
        <span class="label">{t('meal.day')}</span>
        <input class="input" type="date" bind:value={date} required />
      </label>
      <div class="field grow">
        <span class="label">{t('meal.meal')}</span>
        <div class="seg types" role="radiogroup" aria-label={t('meal.meal')}>
          {#each MEAL_TYPES as m (m)}
            <button type="button" role="radio" aria-checked={mealType === m} class:on={mealType === m} onclick={() => (mealType = m)}>{mealTypeName(m)}</button>
          {/each}
        </div>
      </div>
    </div>
    {#if date}<p class="muted small date">{fmtLong(date)}</p>{/if}

    {#if jars.length}
      <section class="stack">
        <span class="label">{t('meal.from_pantry')}</span>
        <div class="jars">
          {#each jars as j (j.id)}
            <button type="button" class="jar" class:on={chosenJars.includes(j.id)} onclick={() => toggleJar(j)}>
              <span class="n">{t('pantry.n', { label: j.label })} · {locationName(j.location)}</span>
              <span class="c">{j.usedHere ? t('meal.used_here') : j.foods.map((f) => f.name).join(' + ')}</span>
            </button>
          {/each}
        </div>
      </section>
    {/if}

    <section class="stack">
      <div class="spread">
        <span class="label">{t('meal.what_eaten')}</span>
        <button type="button" class="btn ghost sm" onclick={loadPrevious}>{t('meal.repeat', { meal: inSentence(mealTypeName(mealType)) })}</button>
      </div>

      {#if previous}
        <div class="prev">
          {#if !previous.length}<p class="muted small">{t('meal.no_previous')}</p>{/if}
          {#each previous as m (m.id)}
            <button type="button" class="prev-item" onclick={() => copyFrom(m)}>
              <b>{fmtShort(m.date)}</b>
              <span>{m.foods.map((f) => f.name).join(', ')}</span>
            </button>
          {/each}
          <button type="button" class="btn ghost sm" onclick={() => (previous = null)}>{t('common.close')}</button>
        </div>
      {/if}

      {#if items.length}
        <ul class="items">
          {#each items as item (item.id)}
            {@const f = food(item.id)}
            <li>
              <div class="spread">
                <FoodChip name={f?.name ?? '?'} />
                <button type="button" class="btn icon sm ghost" onclick={() => toggleFood(item.id)} aria-label={t('meal.remove', { name: f?.name })}>✕</button>
              </div>
              <div class="qty" role="radiogroup" aria-label={t('meal.portion_of', { name: f?.name })}>
                {#each AMOUNTS as a (a)}
                  <button type="button" role="radio" aria-checked={item.amount === a} class:on={item.amount === a} class:no={a === 'refused'} onclick={() => (item.amount = a)}>{t('amount.short.' + a)}</button>
                {/each}
              </div>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="empty small">{t('meal.empty')}</p>
      {/if}

      {#if showPicker}
        <div class="picker"><FoodPicker {selected} ontoggle={toggleFood} /></div>
      {:else}
        <button type="button" class="btn soft" onclick={() => (showPicker = true)}>{t('meal.add_foods')}</button>
      {/if}
    </section>

    <section class="stack">
      <label class="field">
        <span class="label">{t('meal.notes')}</span>
        <textarea class="input" bind:value={notes} rows="2" placeholder={t('meal.notes_example')}></textarea>
      </label>
      <label class="toggle"><input type="checkbox" bind:checked={reaction} /> {t('meal.reaction')}</label>
    </section>
  </div>

  {#snippet footer()}
    {#if meal}<button class="btn danger" onclick={remove}>{t('common.delete')}</button>{/if}
    <button class="btn primary grow" disabled={saving || (!items.length && !chosenJars.length) || !date || !childId} onclick={save}>
      {saving ? t('common.saving') : meal ? t('common.save_changes') : t('meal.save')}
    </button>
  {/snippet}
</Sheet>

<style>
  .gap { gap: 20px; }
  /* Meal types wrap onto two rows when the names are long (e.g. German) */
  .types { flex-wrap: wrap; }
  .types button { flex: 1 0 auto; }
  .top { display: flex; flex-direction: column; gap: 14px; }
  @media (min-width: 640px) { .top { flex-direction: row; } .top > .field:first-child { width: 190px; flex-shrink: 0; } }
  .date { margin-top: -10px; text-transform: capitalize; }
  .jars { display: flex; gap: 8px; overflow-x: auto; padding: 2px 2px 6px; scrollbar-width: thin; }
  .jar {
    flex-shrink: 0; max-width: 220px; text-align: left; cursor: pointer;
    display: flex; flex-direction: column; gap: 2px; padding: 10px 14px; border-radius: var(--r-md);
    border: 1px solid var(--line); background: var(--surface-2);
  }
  .jar.on { border-color: var(--primary); background: var(--primary-soft); }
  .jar .n { font-weight: 600; font-size: 0.85rem; }
  .jar .c { font-size: 0.8rem; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .items { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
  .items li { padding: 10px 10px 10px 12px; border-radius: var(--r-md); background: var(--surface-2); display: flex; flex-direction: column; gap: 8px; }
  .qty { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; }
  .qty button {
    border: 1px solid var(--line); cursor: pointer; min-height: 34px; padding: 0 2px; border-radius: var(--r-xs);
    background: var(--surface); color: var(--muted); font-weight: 500; font-size: 0.78rem;
  }
  .qty button.on { background: var(--primary); border-color: var(--primary); color: var(--primary-ink); }
  .qty button.no.on { background: var(--danger); border-color: var(--danger); color: white; }
  @media (min-width: 640px) { .qty { display: flex; } .qty button { padding: 0 14px; font-size: 0.84rem; } }
  .picker { padding: 14px; border-radius: var(--r-md); border: 1px dashed var(--line-strong); }
  .prev { display: flex; flex-direction: column; gap: 6px; padding: 12px; border-radius: var(--r-md); background: var(--primary-soft); }
  .prev-item { text-align: left; border: 0; cursor: pointer; padding: 10px 12px; border-radius: var(--r-sm); background: var(--surface); display: flex; gap: 10px; font-size: 0.9rem; }
  .prev-item b { flex-shrink: 0; color: var(--primary); font-weight: 600; }
  .prev-item span { color: var(--muted); }
</style>
