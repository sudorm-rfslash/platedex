<script lang="ts">
	import { blurInfo } from '../format';
	let { value }: { value: number | null | undefined } = $props();
	const b = $derived(blurInfo(value));
</script>

<div class="row">
	<span class="lbl" style="flex: none">Blur</span>
	<div class="meter" role="meter" aria-label="Blur score" aria-valuenow={value ?? 0} aria-valuemin="0" aria-valuemax="1">
		<span style="width: {b.pct}%; background: {b.color}"></span>
	</div>
	<span class="mono" style="font-size: 13px; font-weight: 700">{b.value}</span>
	<span style="font-size: 13px; font-weight: 700; color: {b.color}">{b.word}</span>
</div>

<style>
	.row {
		display: flex;
		align-items: center;
		gap: 10px;
	}
</style>
