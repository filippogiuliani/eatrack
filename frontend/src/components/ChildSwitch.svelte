<script>
  // Choose the child whose diary and statistics are shown
  import { activeChildren, app, chooseChild } from '../lib/store.svelte.js';
  import { t } from '../lib/i18n.svelte.js';
  const children = $derived(activeChildren());
</script>

{#if children.length > 1}
  <div class="seg" role="radiogroup" aria-label={t('children.choose')}>
    {#each children as c (c.id)}
      <button role="radio" aria-checked={app.childId === c.id} class:on={app.childId === c.id} onclick={() => chooseChild(c.id)}>{c.name}</button>
    {/each}
  </div>
{:else if children.length === 1}
  <span class="only">{children[0].name}</span>
{/if}

<style>
  .only { font-weight: 600; font-size: 0.9rem; color: var(--muted); }
</style>
