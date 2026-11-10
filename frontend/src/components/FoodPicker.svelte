<script>
  // Foods grouped by category, with search; tap to select. A new food can be created on the fly.
  import { app, loadCatalog, showError, toast } from '../lib/store.svelte.js';
  import { categoryName, t } from '../lib/i18n.svelte.js';
  import { post } from '../lib/api.js';
  import FoodChip from './FoodChip.svelte';

  let { selected = [], ontoggle } = $props();
  let q = $state('');
  let newCategory = $state(null);

  const norm = (s) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const active = $derived(app.foods.filter((f) => !f.archived || selected.includes(f.id)));
  const filtered = $derived(q.trim() ? active.filter((f) => norm(f.name).includes(norm(q.trim()))) : active);
  const groups = $derived(
    app.categories.map((c) => ({ c, items: filtered.filter((f) => f.category_id === c.id) })).filter((g) => g.items.length)
  );
  const exists = $derived(app.foods.some((f) => norm(f.name) === norm(q.trim())));

  async function create() {
    if (!newCategory) return;
    try {
      const name = q.trim();
      const { id } = await post('/foods', { name, category_id: newCategory });
      await loadCatalog();
      toast(t('foods.added', { name }));
      ontoggle(id);
      q = '';
      newCategory = null;
    } catch (e) { showError(e); }
  }
</script>

<div class="stack">
  <div class="search"><input class="input" type="search" placeholder={t('foods.search')} bind:value={q} aria-label={t('foods.search')} /></div>

  {#if q.trim() && !exists}
    <div class="new">
      <p class="small">{t('foods.new_choose_category', { name: q.trim() })}</p>
      <div class="chips">
        {#each app.categories as c (c.id)}
          <button type="button" class="chip" class:on={newCategory === c.id} onclick={() => (newCategory = c.id)}>{categoryName(c.key)}</button>
        {/each}
      </div>
      <button type="button" class="btn soft sm" disabled={!newCategory} onclick={create}>{t('foods.add_and_select')}</button>
    </div>
  {/if}

  {#each groups as g (g.c.id)}
    <section>
      <h4 class="tiny muted">{categoryName(g.c.key)}</h4>
      <div class="chips">
        {#each g.items as f (f.id)}
          <FoodChip name={f.name} on={selected.includes(f.id)} onclick={() => ontoggle(f.id)} />
        {/each}
      </div>
    </section>
  {/each}
  {#if !groups.length && !q.trim()}<p class="muted small">{t('foods.empty_catalog')}</p>{/if}
</div>

<style>
  h4 { font-family: var(--font-body); font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; margin: 4px 0 8px; }
  .new { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; padding: 14px; border-radius: var(--r-md); background: var(--primary-soft); }
</style>
