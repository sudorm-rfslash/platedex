<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';

	let {
		open = $bindable(false),
		title,
		subtitle,
		children,
		footer,
		wide = false,
		onclose
	}: {
		open?: boolean;
		title: string;
		subtitle?: string;
		children: Snippet;
		footer?: Snippet;
		wide?: boolean;
		onclose?: () => void;
	} = $props();

	function close() {
		open = false;
		onclose?.();
	}
</script>

<svelte:window onkeydown={(e) => open && e.key === 'Escape' && close()} />

{#if open}
	<button class="scrim" aria-label="Close" onclick={close}></button>
	<div class="sheet" class:wide role="dialog" aria-label={title} aria-modal="true">
		<div class="grab"></div>
		<div class="head">
			<div style="min-width: 0">
				<h2>{title}</h2>
				{#if subtitle}<p class="mono muted sub">{subtitle}</p>{/if}
			</div>
			<button class="iconbtn" aria-label="Close" onclick={close}><Icon name="close" size={20} stroke={2} /></button>
		</div>
		<div class="body">{@render children()}</div>
		{#if footer}<div class="foot">{@render footer()}</div>{/if}
	</div>
{/if}

<style>
	.scrim {
		position: fixed;
		inset: 0;
		background: rgba(10, 12, 16, 0.5);
		border: 0;
		padding: 0;
		cursor: pointer;
		z-index: 40;
	}
	.sheet {
		position: fixed;
		left: 0;
		right: 0;
		bottom: 0;
		max-height: 90dvh;
		background: var(--surface);
		border-radius: 18px 18px 0 0;
		box-shadow: var(--shadow);
		z-index: 41;
		display: flex;
		flex-direction: column;
		animation: rise 0.2s ease;
	}
	.grab {
		width: 40px;
		height: 5px;
		border-radius: 3px;
		background: var(--line);
		margin: 8px auto 0;
		flex: none;
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
		padding: 4px 8px 4px 16px;
	}
	h2 {
		font-size: 18px;
		font-weight: 800;
	}
	.sub {
		font-size: 12.5px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.body {
		flex: 1;
		overflow-y: auto;
		padding: 4px 16px 16px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.foot {
		display: flex;
		gap: 8px;
		padding: 12px 16px calc(16px + var(--safe-bottom));
		border-top: 1px solid var(--line);
	}
	@media (min-width: 900px) {
		.sheet {
			left: 50%;
			right: auto;
			bottom: auto;
			top: 50%;
			transform: translate(-50%, -50%);
			width: min(520px, calc(100vw - 48px));
			border-radius: 16px;
			max-height: 86dvh;
			animation: none;
		}
		.sheet.wide {
			width: min(760px, calc(100vw - 48px));
		}
		.grab {
			display: none;
		}
		.head {
			padding-top: 12px;
		}
	}
	@keyframes rise {
		from {
			transform: translateY(24px);
			opacity: 0.6;
		}
	}
</style>
