<script>
  import { app } from '../lib/store.svelte.js';
</script>

{#if app.toast}
  {#key app.toast.id}
    <div class="toast" class:err={app.toast.kind === 'error'} role="status">{app.toast.message}</div>
  {/key}
{/if}

<style>
  .toast {
    position: fixed; left: 50%; transform: translateX(-50%); z-index: 200;
    bottom: calc(var(--nav-h) + 20px + env(safe-area-inset-bottom));
    max-width: calc(100vw - 32px); padding: 12px 20px; border-radius: var(--r-xs);
    background: var(--ink); color: var(--bg); font-weight: 600; box-shadow: var(--shadow-lg);
    animation: pop 0.2s ease;
  }
  .toast.err { background: var(--danger); color: white; }
  @media (min-width: 900px) { .toast { bottom: 28px; } }
</style>
