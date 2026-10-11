<script lang="ts">
	import { filters, RANGES, saveFilters, toggleIn } from '../state/filters.svelte';
	import Avatar from './Avatar.svelte';
	import Icon from './Icon.svelte';

	type Meta = { users: { username: string; color: string }[]; tags: string[]; states: string[]; missing_location: number };
	let {
		meta,
		compact = false,
		onMissing
	}: { meta: Meta | null; compact?: boolean; onMissing?: () => void } = $props();

	const MINS = [1, 2, 3, 5];
</script>

<div class="fp">
	{#if !compact && meta && meta.missing_location > 0 && !filters.missing}
		<button class="missing" onclick={() => ((filters.missing = true), saveFilters(), onMissing?.())}>
			<Icon name="pin-off" size={18} stroke={2} />
			<span style="flex: 1">{meta.missing_location} sighting{meta.missing_location === 1 ? '' : 's'} missing location</span>
			<Icon name="chevron" size={18} stroke={2} />
		</button>
	{/if}

	<section>
		<span class="lbl">Date range</span>
		<div class="wrap">
			{#each RANGES as [k, label]}
				<button class="tog" class:on={filters.range === k} onclick={() => ((filters.range = k), saveFilters())}>{label}</button>
			{/each}
		</div>
		{#if !compact}
			<div class="dates">
				<label
					>From<input
						class="field"
						type="date"
						value={filters.from}
						onchange={(e) => ((filters.from = e.currentTarget.value), (filters.range = 'custom'), saveFilters())}
					/></label
				>
				<label
					>To<input
						class="field"
						type="date"
						value={filters.to}
						onchange={(e) => ((filters.to = e.currentTarget.value), (filters.range = 'custom'), saveFilters())}
					/></label
				>
			</div>
		{/if}
	</section>

	{#if meta?.states.length}
		<section>
			<span class="lbl">State</span>
			<div class="wrap">
				{#each meta.states as v}
					<button class="tog" class:on={filters.states.includes(v)} aria-pressed={filters.states.includes(v)} onclick={() => toggleIn('states', v)}>{v}</button>
				{/each}
			</div>
		</section>
	{/if}

	{#if meta?.users.length}
		<section>
			<span class="lbl">Uploader</span>
			<div class="wrap">
				{#each meta.users as u}
					<button class="tog" class:on={filters.users.includes(u.username)} aria-pressed={filters.users.includes(u.username)} onclick={() => toggleIn('users', u.username)}>
						<Avatar user={u} size={22} />{u.username}
					</button>
				{/each}
			</div>
		</section>
	{/if}

	{#if compact}
		<a href="/plates" class="more">Tags, seen ≥ N and more in the Plates list</a>
	{:else}
		{#if meta?.tags.length}
			<section>
				<span class="lbl">Tags</span>
				<div class="wrap">
					{#each meta.tags as v}
						<button class="tog" class:on={filters.tags.includes(v)} aria-pressed={filters.tags.includes(v)} onclick={() => toggleIn('tags', v)}>#{v}</button>
					{/each}
				</div>
			</section>
		{/if}
		<section>
			<span class="lbl">Seen at least</span>
			<div class="seg" style="align-self: flex-start">
				{#each MINS as v}
					<button class:on={filters.minN === v} onclick={() => ((filters.minN = v), saveFilters())}>{v === 1 ? 'Any' : `${v}+`}</button>
				{/each}
			</div>
		</section>
		<section>
			<span class="lbl">Map area</span>
			{#if filters.area}
				<button class="tog on" style="align-self: flex-start" onclick={() => ((filters.area = null), saveFilters())}>
					<Icon name="radius" size={16} stroke={2} />Within {filters.area.mi} mi of {filters.area.label}
					<Icon name="x" size={18} stroke={2.2} />
				</button>
			{/if}
			<a href="/map?radius=1" class="more">{filters.area ? 'Draw a different area on the map' : 'Draw an area on the map'}</a>
		</section>
		<section>
			<span class="lbl">Location</span>
			<button class="tog" class:on={filters.missing} style="align-self: flex-start" onclick={() => ((filters.missing = !filters.missing), saveFilters())}>
				Only sightings missing location
			</button>
		</section>
	{/if}
</div>

<style>
	.fp {
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	section {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.wrap {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}
	.dates {
		display: flex;
		gap: 8px;
	}
	.dates label {
		flex: 1;
		font-size: 13px;
		font-weight: 600;
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
	}
	.dates .field {
		padding: 0 6px;
		font-size: 13px;
	}
	.more {
		font-size: 14px;
		font-weight: 700;
		min-height: 32px;
		display: inline-flex;
		align-items: center;
	}
</style>
