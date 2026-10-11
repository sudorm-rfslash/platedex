export const toast = $state({ msg: null as string | null, undo: null as null | (() => void), id: 0 });
let timer: ReturnType<typeof setTimeout> | undefined;

export function flash(msg: string, undo?: () => void, ms?: number) {
	clearTimeout(timer);
	toast.msg = msg;
	toast.undo = undo ?? null;
	toast.id++;
	timer = setTimeout(clear, ms ?? (undo ? 5000 : 2600));
}

export function clear() {
	toast.msg = null;
	toast.undo = null;
}
