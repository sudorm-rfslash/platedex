<script lang="ts">
	import { toast, clear } from '../state/toast.svelte';
	import Icon from './Icon.svelte';
</script>

{#if toast.msg}
	{#key toast.id}
		<div class="toast" role="status">
			<Icon name="check" size={18} stroke={2.2} />
			<span style="flex: 1">{toast.msg}</span>
			{#if toast.undo}
				<button
					onclick={() => {
						toast.undo?.();
						clear();
					}}>Undo</button
				>
			{/if}
		</div>
	{/key}
{/if}

<style>
	.toast {
		position: fixed;
		left: 16px;
		right: 16px;
		bottom: calc(96px + var(--safe-bottom));
		max-width: 480px;
		margin: 0 auto;
		background: var(--ink);
		color: var(--bg);
		border-radius: 12px;
		padding: 10px 10px 10px 14px;
		display: flex;
		align-items: center;
		gap: 10px;
		box-shadow: var(--shadow);
		font-weight: 600;
		font-size: 14px;
		z-index: 60;
		animation: up 0.18s ease;
	}
	button {
		background: none;
		border: 0;
		color: inherit;
		font: inherit;
		font-weight: 800;
		text-decoration: underline;
		min-height: 36px;
		cursor: pointer;
	}
	@media (min-width: 900px) {
		.toast {
			bottom: 24px;
			left: 280px;
		}
	}
	@keyframes up {
		from {
			transform: translateY(8px);
			opacity: 0;
		}
	}
</style>
