<script lang="ts">
	type U = { username: string; color?: string } | null | undefined;
	let { user, size = 28 }: { user: U; size?: number } = $props();
</script>

<span
	class="ava"
	title={user?.username}
	style="background: {user?.color ?? '#555C64'}; width: {size}px; height: {size}px; font-size: {Math.round(size * 0.43)}px"
	>{(user?.username ?? '?')[0].toUpperCase()}</span
>
