<script lang="ts">
	// Plate text editor shared by Verify and Identify: per-character confidence, top readings, state.
	import { STATE_NAMES } from '../format';

	type EditorItem = { text: string; char_conf: number[]; candidates: [string, number][]; state_is_guess: boolean };
	let {
		item,
		text = $bindable(''),
		st = $bindable('??'),
		stTouched = $bindable(false),
		compact = false
	}: { item: EditorItem; text?: string; st?: string; stTouched?: boolean; compact?: boolean } = $props();

	const chars = $derived(
		text.split('').map((ch, k) => {
			const same = item.text[k] === ch;
			const c = item.char_conf[k] ?? 0;
			return { ch, cls: !same ? 'c-ed' : c >= 0.85 ? 'c-hi' : c >= 0.6 ? 'c-md' : 'c-lo' };
		})
	);
	const isGuess = $derived(item.state_is_guess && !stTouched && st !== '??');
	const states = Object.entries(STATE_NAMES);
</script>

<div class="editor" class:compact>
		<div class="stack">
		<span class="lbl">Plate text</span>
		<div class="chars" aria-hidden="true">
			{#each chars as c}<span class="cbox {c.cls}">{c.ch}</span>{/each}
		</div>
		<label class="muted edit">
			Edit if wrong · use ? for an unreadable character
			<input
				class="field mono plateinput"
				value={text}
				oninput={(e) => (text = e.currentTarget.value.toUpperCase().replace(/[^A-Z0-9? -]/g, ''))}
				aria-label="Plate text"
				autocapitalize="characters"
				autocomplete="off"
				spellcheck="false"
			/>
		</label>
		<div class="legend">
			<span class="lg"><i class="c-hi"></i>sure</span><span class="lg"><i class="c-md"></i>unsure</span><span class="lg"><i class="c-lo"></i>doubtful</span><span class="lg"><i class="c-ed"></i>edited</span>
		</div>
	</div>

	{#if item.candidates.length}
		<div class="stack">
			<span class="lbl">Top readings</span>
			<div class="cands">
				{#each item.candidates as [t, p], i}
					<button class="cand" class:on={t === text} onclick={() => (text = t)}>
						<span class="kbd desk-only">{i + 1}</span>{t}<small>{p}%</small>
					</button>
				{/each}
			</div>
		</div>
	{/if}

	<label class="stack">
		<span class="srow"><span class="lbl">State</span>{#if isGuess}<span class="guess">guess</span>{/if}</span>
		<select class="field" bind:value={st} onchange={() => (stTouched = true)}>
			{#each states as [code, name]}<option value={code}>{code} · {name}</option>{/each}
			<option value="??">Unknown</option>
		</select>
	</label>
</div>

<style>
	.editor {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.stack {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.compact .cbox {
		min-width: 26px;
		height: 36px;
		font-size: 20px;
	}
	.chars {
		display: flex;
		gap: 4px;
		flex-wrap: wrap;
	}
	.cbox {
		min-width: 32px;
		height: 44px;
		padding: 0 3px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border-radius: 6px;
		font-family: 'JetBrains Mono', monospace;
		font-feature-settings: 'zero' 1;
		font-weight: 800;
		font-size: 25px;
		border-bottom: 3px solid transparent;
	}
	.c-hi {
		background: var(--ok-soft);
		color: var(--ok);
	}
	.c-md {
		background: var(--warn-soft);
		color: var(--warn);
		border-bottom: 3px dashed var(--warn);
	}
	.c-lo {
		background: var(--bad-soft);
		color: var(--bad);
		border-bottom: 3px solid var(--bad);
	}
	.c-ed {
		background: var(--surface2);
		color: var(--ink);
	}
	.edit {
		font-size: 13px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.plateinput {
		font-size: 20px;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}
	.legend {
		display: flex;
		gap: 12px;
		flex-wrap: wrap;
	}
	.lg {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 12px;
		color: var(--muted);
	}
	.lg i {
		width: 12px;
		height: 12px;
		border-radius: 3px;
		display: inline-block;
		border: 0;
	}
	.cands {
		display: flex;
		gap: 8px;
	}
	.cand {
		flex: 1;
		min-width: 0;
		min-height: 48px;
		border-radius: 10px;
		border: 1px solid var(--line);
		background: var(--surface);
		color: var(--ink);
		font-family: 'JetBrains Mono', monospace;
		font-feature-settings: 'zero' 1;
		font-weight: 700;
		font-size: 15px;
		cursor: pointer;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		line-height: 1.2;
		position: relative;
	}
	.cand small {
		font-family: 'Public Sans', sans-serif;
		font-size: 11px;
		color: var(--muted);
		font-weight: 600;
	}
	.cand.on {
		border-color: var(--accent);
		background: var(--accent-soft);
		color: var(--accent);
	}
	.cand .kbd {
		position: absolute;
		left: 6px;
		top: 6px;
	}
	.srow {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.guess {
		font-size: 11px;
		font-weight: 800;
		padding: 1px 8px;
		border-radius: 999px;
		background: var(--amber-bg);
		color: var(--amber-ink);
		border: 1px dashed var(--amber-line);
	}
</style>
