<script>
  import FoodChip from './FoodChip.svelte';
  import { app } from '../lib/store.svelte.js';
  import { mealTypeName, t } from '../lib/i18n.svelte.js';
  let { meal, onclick } = $props();
  // "added by" only when another family member logged it
  const author = $derived(meal.created_by && meal.created_by !== app.me?.user?.id ? meal.created_by_name : null);
</script>

<button type="button" class="meal" {onclick} aria-label={t('meal.edit_aria', { meal: mealTypeName(meal.meal_type) })}>
  <div class="spread">
    <span class="type">{mealTypeName(meal.meal_type)}</span>
    <span class="row">
      {#if meal.reaction}<span class="badge danger">{t('meal.reaction_badge')}</span>{/if}
      {#each meal.jars as j (j.id)}<span class="badge">{t('pantry.n', { label: j.label })}</span>{/each}
    </span>
  </div>
  <div class="chips">
    {#each meal.foods as f (f.id)}
      <FoodChip name={f.name} amount={f.amount} />
    {/each}
  </div>
  {#if meal.notes}<p class="notes">{meal.notes}</p>{/if}
  {#if author}<p class="author tiny muted">{t('meal.added_by', { name: author })}</p>{/if}
</button>

<style>
  .meal {
    width: 100%; text-align: left; cursor: pointer; font: inherit; color: inherit;
    display: flex; flex-direction: column; gap: 10px; padding: 14px;
    border: 0; border-radius: var(--r-md);
    background: var(--surface); box-shadow: inset 0 0 0 1px var(--line);
    transition: box-shadow 0.15s ease;
  }
  .meal:hover { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary) 45%, transparent); }
  .type { font-weight: 600; }
  .chips :global(.chip) { min-height: 28px; font-size: 0.84rem; padding: 2px 9px; }
  .notes { font-size: 0.86rem; color: var(--muted); white-space: pre-line; }
  .author { margin-top: -4px; }
</style>
