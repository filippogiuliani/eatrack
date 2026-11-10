<script>
  import { untrack } from 'svelte';
  import { del, post, put } from '../lib/api.js';
  import { food, showError, toast } from '../lib/store.svelte.js';
  import { locationName, t } from '../lib/i18n.svelte.js';
  import { LOCATIONS } from '../lib/constants.js';
  import { today } from '../lib/date.js';
  import Sheet from './Sheet.svelte';
  import FoodChip from './FoodChip.svelte';
  import FoodPicker from './FoodPicker.svelte';

  // jar: the jar to edit (null = new ones). template: contents to copy. freeLabels: suggested labels
  let { jar: jarProp = null, template: templateProp = null, freeLabels: freeProp = [], onclose, onsaved } = $props();
  // Read once: the editor is recreated every time it opens
  const jar = untrack(() => jarProp), template = untrack(() => templateProp), freeLabels = untrack(() => freeProp);
  const source = jar ?? template;

  let labels = $state(jar ? [jar.label] : [String(freeLabels[0] ?? 1)]);
  let location = $state(source?.location ?? 'freezer');
  let madeOn = $state(source?.made_on ?? today());
  let notes = $state(source?.notes ?? '');
  let foods = $state((source?.foods ?? []).map((f) => f.id));
  let saving = $state(false);

  function toggle(id) {
    const i = foods.indexOf(id);
    if (i >= 0) foods.splice(i, 1); else foods.push(id);
  }
  function addLabel() {
    const used = new Set(labels);
    const next = freeLabels.find((n) => !used.has(String(n))) ?? labels.length + 1;
    labels.push(String(next));
  }

  async function save() {
    saving = true;
    const body = { location, made_on: madeOn, notes, foods };
    try {
      if (jar) await put(`/jars/${jar.id}`, { ...body, label: labels[0] });
      else await post('/jars', { ...body, labels });
      toast(jar ? t('pantry.updated') : t('pantry.added', { n: labels.length }));
      onsaved?.();
    } catch (e) { showError(e); } finally { saving = false; }
  }
  async function remove() {
    if (!confirm(t('pantry.confirm_delete', { label: jar.label }))) return;
    try { await del(`/jars/${jar.id}`); toast(t('pantry.deleted')); onsaved?.(); } catch (e) { showError(e); }
  }
</script>

<Sheet title={jar ? t('pantry.n', { label: jar.label }) : t('pantry.new')} {onclose} wide>
  <div class="stack gap">
    <div class="field">
      <span class="label">{jar ? t('pantry.label') : t('pantry.labels')}</span>
      <div class="row wrap">
        {#each labels as _, i}
          <div class="num">
            <input class="input" bind:value={labels[i]} aria-label={t('pantry.label_n', { n: i + 1 })} />
            {#if labels.length > 1}<button type="button" class="x" onclick={() => labels.splice(i, 1)} aria-label={t('common.remove')}>✕</button>{/if}
          </div>
        {/each}
        {#if !jar}<button type="button" class="btn soft sm" onclick={addLabel}>{t('pantry.another')}</button>{/if}
      </div>
      {#if !jar}<p class="tiny muted">{t('pantry.same_contents')}</p>{/if}
    </div>

    <div class="field">
      <span class="label">{t('pantry.where')}</span>
      <div class="seg">
        {#each LOCATIONS as l (l.id)}
          <button type="button" class:on={location === l.id} onclick={() => (location = l.id)}>{locationName(l.id)}</button>
        {/each}
      </div>
    </div>

    <label class="field">
      <span class="label">{t('pantry.made_on')}</span>
      <input class="input" type="date" bind:value={madeOn} max={today()} />
    </label>

    <div class="field">
      <span class="label">{t('pantry.contents')}</span>
      {#if foods.length}
        <div class="chips">
          {#each foods as id (id)}
            <FoodChip name={food(id)?.name ?? '?'} on onclick={() => toggle(id)} />
          {/each}
        </div>
      {/if}
      <div class="picker"><FoodPicker selected={foods} ontoggle={toggle} /></div>
    </div>

    <label class="field">
      <span class="label">{t('meal.notes')}</span>
      <input class="input" bind:value={notes} placeholder={t('pantry.notes_example')} />
    </label>
  </div>

  {#snippet footer()}
    {#if jar}<button class="btn danger" onclick={remove}>{t('common.delete')}</button>{/if}
    <button class="btn primary grow" disabled={saving || !foods.length || !labels.some((n) => n.trim())} onclick={save}>
      {saving ? t('common.saving') : jar ? t('common.save') : t('pantry.add_n', { n: labels.length })}
    </button>
  {/snippet}
</Sheet>

<style>
  .gap { gap: 18px; }
  .num { position: relative; width: 92px; }
  .num .input { text-align: center; font-weight: 600; padding-right: 26px; }
  .x { position: absolute; right: 4px; top: 50%; transform: translateY(-50%); border: 0; background: none; color: var(--muted); cursor: pointer; padding: 6px; }
  .picker { padding: 14px; border-radius: var(--r-md); border: 1px dashed var(--line-strong); }
</style>
