<script>
  import { t } from '../lib/i18n.svelte.js';
  let { name, amount = null, onclick = null, on = false } = $props();
  // Short mark next to the name for partial portions
  const MARKS = { half: 'amount.mark.half', puree: 'amount.mark.puree', taste: 'amount.mark.taste' };
  const mark = $derived(amount && MARKS[amount] ? t(MARKS[amount]) : '');
  const refused = $derived(amount === 'refused');
</script>

{#if onclick}
  <button type="button" class="chip" class:on {onclick} aria-pressed={on}>{name}</button>
{:else}
  <span class="chip" class:off={refused} title={refused ? t('amount.refused') : ''}>
    {name}{#if mark}<span class="q">{mark}</span>{/if}
  </span>
{/if}
