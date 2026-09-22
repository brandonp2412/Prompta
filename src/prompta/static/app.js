//#region \0rolldown/runtime.js
var __defProp = Object.defineProperty;
var __esmMin = (fn, res, err) => () => {
	if (err) throw err[0];
	try {
		return fn && (res = fn(fn = 0)), res;
	} catch (e) {
		throw err = [e], e;
	}
};
var __exportAll = (all, no_symbols) => {
	let target = {};
	for (var name in all) __defProp(target, name, {
		get: all[name],
		enumerable: true
	});
	if (!no_symbols) __defProp(target, Symbol.toStringTag, { value: "Module" });
	return target;
};
//#endregion
//#region node_modules/esm-env/false.js
var init_false = __esmMin((() => {}));
//#endregion
//#region node_modules/esm-env/index.js
var init_esm_env = __esmMin((() => {
	init_false();
}));
//#endregion
//#region node_modules/svelte/src/internal/shared/utils.js
/** @param {Array<() => void>} arr */
function run_all(arr) {
	for (var i = 0; i < arr.length; i++) arr[i]();
}
/**
* TODO replace with Promise.withResolvers once supported widely enough
* @template [T=void]
*/
function deferred() {
	/** @type {(value: T) => void} */
	var resolve;
	/** @type {(reason: any) => void} */
	var reject;
	return {
		promise: new Promise((res, rej) => {
			resolve = res;
			reject = rej;
		}),
		resolve,
		reject
	};
}
var is_array, index_of, includes, array_from, define_property, get_descriptor, get_descriptors, object_prototype, array_prototype, get_prototype_of, is_extensible, noop, init_utils$3 = __esmMin((() => {
	is_array = Array.isArray;
	index_of = Array.prototype.indexOf;
	includes = Array.prototype.includes;
	array_from = Array.from;
	define_property = Object.defineProperty;
	get_descriptor = Object.getOwnPropertyDescriptor;
	get_descriptors = Object.getOwnPropertyDescriptors;
	object_prototype = Object.prototype;
	array_prototype = Array.prototype;
	get_prototype_of = Object.getPrototypeOf;
	is_extensible = Object.isExtensible;
	noop = () => {};
})), CLEAN, DIRTY, MAYBE_DIRTY, INERT, DESTROYED, REACTION_RAN, DESTROYING, EFFECT_TRANSPARENT, EFFECT_PRESERVED, USER_EFFECT, EFFECT_OFFSCREEN, REACTION_IS_UPDATING, ASYNC, ERROR_VALUE, STATE_SYMBOL, COMPONENT_SYMBOL, LOADING_ATTR_SYMBOL, ATTRIBUTES_CACHE, CLASS_CACHE, STYLE_CACHE, TEXT_CACHE, STALE_REACTION, IS_XHTML;
var init_constants$1 = __esmMin((() => {
	CLEAN = 1024;
	DIRTY = 2048;
	MAYBE_DIRTY = 4096;
	INERT = 8192;
	DESTROYED = 16384;
	REACTION_RAN = 32768;
	DESTROYING = 1 << 25;
	EFFECT_TRANSPARENT = 65536;
	EFFECT_PRESERVED = 1 << 19;
	USER_EFFECT = 1 << 20;
	EFFECT_OFFSCREEN = 1 << 25;
	REACTION_IS_UPDATING = 1 << 21;
	ASYNC = 1 << 22;
	ERROR_VALUE = 1 << 23;
	STATE_SYMBOL = Symbol("$state");
	COMPONENT_SYMBOL = Symbol("component");
	LOADING_ATTR_SYMBOL = Symbol("");
	ATTRIBUTES_CACHE = Symbol("attributes");
	CLASS_CACHE = Symbol("class");
	STYLE_CACHE = Symbol("style");
	TEXT_CACHE = Symbol("text");
	STALE_REACTION = new class StaleReactionError extends Error {
		name = "StaleReactionError";
		message = "The reaction that called `getAbortSignal()` was re-run or destroyed";
	}();
	IS_XHTML = !!globalThis.document?.contentType && /* @__PURE__ */ globalThis.document.contentType.includes("xml");
})), HYDRATION_ERROR, UNINITIALIZED, NAMESPACE_HTML;
var init_constants = __esmMin((() => {
	HYDRATION_ERROR = {};
	UNINITIALIZED = Symbol("uninitialized");
	NAMESPACE_HTML = "http://www.w3.org/1999/xhtml";
}));
/**
* Reading a derived belonging to a now-destroyed effect may result in stale values
*/
function derived_inert() {
	console.warn(`https://svelte.dev/e/derived_inert`);
}
/**
* Hydration failed because the initial UI does not match what was rendered on the server. The error occurred near %location%
* @param {string | undefined | null} [location]
*/
function hydration_mismatch(location) {
	console.warn(`https://svelte.dev/e/hydration_mismatch`);
}
/**
* A `<svelte:boundary>` `reset` function only resets the boundary the first time it is called
*/
function svelte_boundary_reset_noop() {
	console.warn(`https://svelte.dev/e/svelte_boundary_reset_noop`);
}
var init_warnings = __esmMin((() => {
	init_esm_env();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/hydration.js
/** @param {boolean} value */
function set_hydrating(value) {
	hydrating = value;
}
/** @param {TemplateNode | null} node */
function set_hydrate_node(node) {
	if (node === null) {
		hydration_mismatch();
		throw HYDRATION_ERROR;
	}
	return hydrate_node = node;
}
function hydrate_next() {
	return set_hydrate_node(/* @__PURE__ */ get_next_sibling(hydrate_node));
}
/** @param {TemplateNode} node */
function reset(node) {
	if (!hydrating) return;
	if (/* @__PURE__ */ get_next_sibling(hydrate_node) !== null) {
		hydration_mismatch();
		throw HYDRATION_ERROR;
	}
	hydrate_node = node;
}
function next(count = 1) {
	if (hydrating) {
		var i = count;
		var node = hydrate_node;
		while (i--) node = /* @__PURE__ */ get_next_sibling(node);
		hydrate_node = node;
	}
}
/**
* Skips or removes (depending on {@link remove}) all nodes starting at `hydrate_node` up until the next hydration end comment
* @param {boolean} remove
*/
function skip_nodes(remove = true) {
	var depth = 0;
	var node = hydrate_node;
	while (true) {
		if (node.nodeType === 8) {
			var data = node.data;
			if (data === "]") {
				if (depth === 0) return node;
				depth -= 1;
			} else if (data === "[" || data === "[!" || data[0] === "[" && !isNaN(Number(data.slice(1)))) depth += 1;
		}
		var next = /* @__PURE__ */ get_next_sibling(node);
		if (remove) node.remove();
		node = next;
	}
}
/**
*
* @param {TemplateNode} node
*/
function read_hydration_instruction(node) {
	if (!node || node.nodeType !== 8) {
		hydration_mismatch();
		throw HYDRATION_ERROR;
	}
	return node.data;
}
var hydrating, hydrate_node;
var init_hydration = __esmMin((() => {
	init_constants$1();
	init_constants();
	init_warnings();
	init_operations$1();
	hydrating = false;
}));
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/equality.js
/** @import { Equals } from '#client' */
/** @type {Equals} */
function equals(value) {
	return value === this.v;
}
/**
* @param {unknown} a
* @param {unknown} b
* @returns {boolean}
*/
function safe_not_equal(a, b) {
	return a != a ? b == b : a !== b || a !== null && typeof a === "object" || typeof a === "function";
}
/** @type {Equals} */
function safe_equals(value) {
	return !safe_not_equal(value, this.v);
}
var init_equality$1 = __esmMin((() => {}));
var init_errors$1 = __esmMin((() => {
	init_esm_env();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/errors.js
/**
* Cannot create a `$derived(...)` with an `await` expression outside of an effect tree
* @returns {never}
*/
function async_derived_orphan() {
	throw new Error(`https://svelte.dev/e/async_derived_orphan`);
}
/**
* Keyed each block has duplicate key `%value%` at indexes %a% and %b%
* @param {string} a
* @param {string} b
* @param {string | undefined | null} [value]
* @returns {never}
*/
function each_key_duplicate(a, b, value) {
	throw new Error(`https://svelte.dev/e/each_key_duplicate`);
}
/**
* Maximum update depth exceeded. This typically indicates that an effect reads and writes the same piece of state
* @returns {never}
*/
function effect_update_depth_exceeded() {
	throw new Error(`https://svelte.dev/e/effect_update_depth_exceeded`);
}
/**
* Property descriptors defined on `$state` objects must contain `value` and always be `enumerable`, `configurable` and `writable`.
* @returns {never}
*/
function state_descriptors_fixed() {
	throw new Error(`https://svelte.dev/e/state_descriptors_fixed`);
}
/**
* Cannot set prototype of `$state` object
* @returns {never}
*/
function state_prototype_fixed() {
	throw new Error(`https://svelte.dev/e/state_prototype_fixed`);
}
/**
* Updating state inside `$derived(...)`, `$inspect(...)` or a template expression is forbidden. If the value should not be reactive, declare it without `$state`
* @returns {never}
*/
function state_unsafe_mutation() {
	throw new Error(`https://svelte.dev/e/state_unsafe_mutation`);
}
/**
* A `<svelte:boundary>` `reset` function cannot be called while an error is still being handled
* @returns {never}
*/
function svelte_boundary_reset_onerror() {
	throw new Error(`https://svelte.dev/e/svelte_boundary_reset_onerror`);
}
var init_errors = __esmMin((() => {
	init_esm_env();
	init_errors$1();
})), async_mode_flag, legacy_mode_flag;
var init_flags = __esmMin((() => {
	async_mode_flag = false;
	legacy_mode_flag = false;
}));
//#endregion
//#region node_modules/svelte/src/internal/shared/clone.js
var init_clone = __esmMin((() => {
	init_utils$3();
}));
var init_tracing = __esmMin((() => {
	init_clone();
	init_constants$1();
	init_effects();
	init_runtime();
}));
var init_dev = __esmMin((() => {
	init_esm_env();
	init_utils$3();
	init_errors$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/context.js
/** @param {ComponentContext | null} context */
function set_component_context(context) {
	component_context = context;
}
/**
* @param {Record<string, unknown>} props
* @param {any} runes
* @param {Function} [fn]
* @returns {void}
*/
function push(props, runes = false, fn) {
	component_context = {
		p: component_context,
		i: false,
		c: null,
		e: null,
		s: props,
		x: null,
		r: active_effect,
		l: legacy_mode_flag && !runes ? {
			s: null,
			u: null,
			$: []
		} : null
	};
}
/**
* @template {Record<string, any>} T
* @param {T} [component]
* @returns {T}
*/
function pop(component) {
	var context = component_context;
	var effects = context.e;
	if (effects !== null) {
		context.e = null;
		for (var fn of effects) create_user_effect(fn);
	}
	if (component !== void 0) context.x = component;
	context.i = true;
	component_context = context.p;
	return mark_as_component(component);
}
/**
* Add a symbol to the object (or create one if undefined) to mark it as a component so it isn't proxified.
* @param {any} component
*/
function mark_as_component(component = {}) {
	define_property(component, COMPONENT_SYMBOL, { value: true });
	return component;
}
/** @returns {boolean} */
function is_runes() {
	return !legacy_mode_flag || component_context !== null && component_context.l === null;
}
var component_context;
var init_context = __esmMin((() => {
	init_esm_env();
	init_errors();
	init_runtime();
	init_effects();
	init_flags();
	init_constants$1();
	init_utils$3();
	component_context = null;
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/task.js
function run_micro_tasks() {
	var tasks = micro_tasks;
	micro_tasks = [];
	run_all(tasks);
}
/**
* @param {() => void} fn
*/
function queue_micro_task(fn) {
	if (micro_tasks.length === 0 && !is_flushing_sync) {
		var tasks = micro_tasks;
		queueMicrotask(() => {
			if (tasks === micro_tasks) run_micro_tasks();
		});
	}
	micro_tasks.push(fn);
}
var micro_tasks;
var init_task = __esmMin((() => {
	init_utils$3();
	init_batch();
	micro_tasks = [];
}));
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/status.js
/**
* @param {Signal} signal
* @param {number} status
*/
function set_signal_status(signal, status) {
	signal.f = signal.f & STATUS_MASK | status;
}
/**
* Set a derived's status to CLEAN or MAYBE_DIRTY based on its connection state.
* @param {Derived} derived
*/
function update_derived_status(derived) {
	if ((derived.f & 512) !== 0 || derived.deps === null) set_signal_status(derived, CLEAN);
	else set_signal_status(derived, MAYBE_DIRTY);
}
var STATUS_MASK;
var init_status = __esmMin((() => {
	init_constants$1();
	STATUS_MASK = ~(DIRTY | MAYBE_DIRTY | CLEAN);
}));
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/utils.js
/**
* @param {Effect} effect
* @param {Set<Effect>} dirty_effects
* @param {Set<Effect>} maybe_dirty_effects
*/
function defer_effect(effect, dirty_effects, maybe_dirty_effects) {
	if ((effect.f & 2048) !== 0) dirty_effects.add(effect);
	else if ((effect.f & 4096) !== 0) maybe_dirty_effects.add(effect);
	set_signal_status(effect, CLEAN);
}
var init_utils$2 = __esmMin((() => {
	init_constants$1();
	init_status();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dev/debug.js
var init_debug = __esmMin((() => {
	init_constants$1();
	init_clone();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/misc.js
var init_misc$1 = __esmMin((() => {
	init_hydration();
	init_operations$1();
	init_task();
	init_constants$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/shared.js
/**
* @template T
* @param {() => T} fn
*/
function without_reactive_context(fn) {
	var previous_reaction = active_reaction;
	var previous_effect = active_effect;
	set_active_reaction(null);
	set_active_effect(null);
	try {
		return fn();
	} finally {
		set_active_reaction(previous_reaction);
		set_active_effect(previous_effect);
	}
}
var init_shared$1 = __esmMin((() => {
	init_effects();
	init_runtime();
	init_constants$1();
	init_misc$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/async.js
/**
* @param {Blocker[]} blockers
* @param {Array<() => any>} sync
* @param {Array<() => Promise<any>>} async
* @param {(values: Value[]) => any} fn
*/
function flatten(blockers, sync, async, fn) {
	const d = is_runes() ? derived : derived_safe_equal;
	var pending = blockers.filter((b) => !b.settled);
	var deriveds = sync.map(d);
	if (async.length === 0 && pending.length === 0) {
		fn(deriveds);
		return;
	}
	var parent = active_effect;
	var restore = capture();
	var blocker_promise = pending.length === 1 ? pending[0].promise : pending.length > 1 ? Promise.all(pending.map((b) => b.promise)) : null;
	/**
	* @param {Source[]} async
	*/
	function finish(async) {
		if ((parent.f & 16384) !== 0) return;
		restore();
		try {
			fn([...deriveds, ...async]);
		} catch (error) {
			invoke_error_boundary(error, parent);
		}
		unset_context();
	}
	var decrement_pending = increment_pending();
	if (async.length === 0) {
		/** @type {Promise<any>} */ blocker_promise.then(() => finish([])).finally(decrement_pending);
		return;
	}
	function run() {
		Promise.all(async.map((expression) => /* @__PURE__ */ async_derived(expression))).then(finish).catch((error) => invoke_error_boundary(error, parent)).finally(decrement_pending);
	}
	if (blocker_promise) blocker_promise.then(() => {
		restore();
		run();
		unset_context();
	});
	else run();
}
/**
* Captures the current effect context so that we can restore it after
* some asynchronous work has happened (so that e.g. `await a + b`
* causes `b` to be registered as a dependency).
*/
function capture() {
	var previous_effect = active_effect;
	var previous_reaction = active_reaction;
	var previous_component_context = component_context;
	var previous_batch = current_batch;
	return function restore(activate_batch = true) {
		set_active_effect(previous_effect);
		set_active_reaction(previous_reaction);
		set_component_context(previous_component_context);
		if (activate_batch && (previous_effect.f & 16384) === 0) {
			previous_batch?.activate();
			previous_batch?.apply();
		}
	};
}
function unset_context(deactivate_batch = true) {
	restored = false;
	set_active_effect(null);
	set_active_reaction(null);
	set_component_context(null);
	if (deactivate_batch) current_batch?.deactivate();
}
/**
* @returns {(skip?: boolean) => void}
*/
function increment_pending() {
	var effect = active_effect;
	var boundary = effect.b;
	var batch = current_batch;
	var blocking = !!boundary?.is_rendered();
	boundary?.update_pending_count(1, batch);
	batch.increment(blocking, effect);
	return () => {
		boundary?.update_pending_count(-1, batch);
		batch.decrement(blocking, effect);
	};
}
var restored;
var init_async$1 = __esmMin((() => {
	init_constants$1();
	init_esm_env();
	init_context();
	init_error_handling();
	init_runtime();
	init_batch();
	init_deriveds();
	init_effects();
}));
/**
* @template V
* @param {() => V} fn
* @returns {Derived<V>}
*/
/*#__NO_SIDE_EFFECTS__*/
function derived(fn) {
	var flags = 2 | DIRTY;
	if (active_effect !== null) active_effect.f |= EFFECT_PRESERVED;
	return {
		ctx: component_context,
		deps: null,
		effects: null,
		equals,
		f: flags,
		fn,
		reactions: null,
		rv: 0,
		v: UNINITIALIZED,
		wv: 0,
		parent: active_effect,
		ac: null
	};
}
/**
* @template V
* @param {() => V | Promise<V>} fn
* @param {string} [label]
* @param {string} [location] If provided, print a warning if the value is not read immediately after update
* @returns {Promise<Source<V>>}
*/
/*#__NO_SIDE_EFFECTS__*/
function async_derived(fn, label, location) {
	let parent = active_effect;
	if (parent === null) async_derived_orphan();
	var promise = void 0;
	var signal = source(UNINITIALIZED);
	var should_suspend = !active_reaction;
	/** @type {Set<ReturnType<typeof deferred<V>>>} */
	var deferreds = /* @__PURE__ */ new Set();
	async_effect(() => {
		var effect = active_effect;
		/** @type {ReturnType<typeof deferred<V>>} */
		var d = deferred();
		promise = d.promise;
		try {
			Promise.resolve(fn()).then(d.resolve, (e) => {
				if (e !== STALE_REACTION) d.reject(e);
			}).finally(unset_context);
		} catch (error) {
			d.reject(error);
			unset_context();
		}
		var batch = current_batch;
		if (should_suspend) {
			if ((effect.f & 32768) !== 0) var decrement_pending = increment_pending();
			if (parent.b?.is_rendered()) batch.async_deriveds.get(effect)?.reject(OBSOLETE);
			else for (const d of deferreds.values()) d.reject(OBSOLETE);
			deferreds.add(d);
			batch.async_deriveds.set(effect, d);
		}
		/**
		* @param {any} value
		* @param {unknown} error
		*/
		const handler = (value, error = void 0) => {
			decrement_pending?.();
			deferreds.delete(d);
			if (error === OBSOLETE) return;
			batch.activate();
			if (error) {
				signal.f |= ERROR_VALUE;
				internal_set(signal, error);
			} else {
				if ((signal.f & 8388608) !== 0) signal.f ^= ERROR_VALUE;
				internal_set(signal, value);
			}
			batch.deactivate();
		};
		d.promise.then(handler, (e) => handler(null, e || "unknown"));
	});
	teardown(() => {
		for (const d of deferreds) d.reject(OBSOLETE);
	});
	return new Promise((fulfil) => {
		/** @param {Promise<V>} p */
		function next(p) {
			function go() {
				if (p === promise) fulfil(signal);
				else next(promise);
			}
			p.then(go, go);
		}
		next(promise);
	});
}
/**
* @template V
* @param {() => V} fn
* @returns {Derived<V>}
*/
/*#__NO_SIDE_EFFECTS__*/
function derived_safe_equal(fn) {
	const signal = /* @__PURE__ */ derived(fn);
	signal.equals = safe_equals;
	return signal;
}
/**
* @param {Derived} derived
* @returns {void}
*/
function destroy_derived_effects(derived) {
	var effects = derived.effects;
	if (effects !== null) {
		derived.effects = null;
		for (var i = 0; i < effects.length; i += 1) destroy_effect(effects[i]);
	}
}
/**
* @template T
* @param {Derived} derived
* @returns {T}
*/
function execute_derived(derived) {
	var value;
	var prev_active_effect = active_effect;
	var parent = derived.parent;
	if (!is_destroying_effect && parent !== null && derived.v !== UNINITIALIZED && (parent.f & 24576) !== 0) {
		derived_inert();
		return derived.v;
	}
	set_active_effect(parent);
	try {
		destroy_derived_effects(derived);
		value = update_reaction(derived);
	} finally {
		set_active_effect(prev_active_effect);
	}
	return value;
}
/**
* @param {Derived} derived
* @returns {void}
*/
function update_derived(derived) {
	var value = execute_derived(derived);
	if (!derived.equals(value)) {
		derived.wv = increment_write_version();
		if (!current_batch?.is_fork || derived.deps === null) {
			if (current_batch !== null) {
				current_batch.capture(derived, value, true);
				previous_batch?.capture(derived, value, true);
			} else derived.v = value;
			if (derived.deps === null) {
				set_signal_status(derived, CLEAN);
				return;
			}
		}
	}
	if (is_destroying_effect) return;
	if (batch_values !== null) {
		if (effect_tracking() || current_batch?.is_fork) batch_values.set(derived, value);
	} else update_derived_status(derived);
}
/**
* @param {Derived} derived
*/
function freeze_derived_effects(derived) {
	if (derived.effects === null) return;
	for (const e of derived.effects) if (e.teardown || e.ac) {
		e.teardown?.();
		if (e.ac !== null) without_reactive_context(() => {
			/** @type {AbortController} */ e.ac.abort(STALE_REACTION);
			e.ac = null;
		});
		if (e.fn !== null) e.teardown = noop;
		remove_reactions(e, 0);
		destroy_effect_children(e);
	}
}
/**
* @param {Derived} derived
*/
function unfreeze_derived_effects(derived) {
	if (derived.effects === null) return;
	for (const e of derived.effects) if (e.teardown && e.fn !== null) update_effect(e);
}
var OBSOLETE;
var init_deriveds = __esmMin((() => {
	init_esm_env();
	init_constants$1();
	init_runtime();
	init_shared$1();
	init_equality$1();
	init_errors();
	init_warnings();
	init_effects();
	init_sources();
	init_dev();
	init_flags();
	init_context();
	init_constants();
	init_batch();
	init_async$1();
	init_utils$3();
	init_status();
	OBSOLETE = Symbol("obsolete");
}));
function infinite_loop_guard() {
	try {
		effect_update_depth_exceeded();
	} catch (error) {
		invoke_error_boundary(error, last_scheduled_effect);
	}
}
/**
* @param {Array<Effect>} effects
* @returns {void}
*/
function flush_queued_effects(effects) {
	var length = effects.length;
	if (length === 0) return;
	var i = 0;
	while (i < length) {
		var effect = effects[i++];
		if ((effect.f & 24576) === 0 && is_dirty(effect)) {
			eager_block_effects = /* @__PURE__ */ new Set();
			update_effect(effect);
			if (effect.deps === null && effect.first === null && effect.nodes === null && effect.teardown === null && effect.ac === null) unlink_effect(effect);
			if (eager_block_effects?.size > 0) {
				old_values.clear();
				for (const e of eager_block_effects) {
					if ((e.f & 24576) !== 0) continue;
					/** @type {Effect[]} */
					const ordered_effects = [e];
					let ancestor = e.parent;
					while (ancestor !== null) {
						if (eager_block_effects.has(ancestor)) {
							eager_block_effects.delete(ancestor);
							ordered_effects.push(ancestor);
						}
						ancestor = ancestor.parent;
					}
					for (let j = ordered_effects.length - 1; j >= 0; j--) {
						const e = ordered_effects[j];
						if ((e.f & 24576) !== 0) continue;
						update_effect(e);
					}
				}
				eager_block_effects.clear();
			}
		}
	}
	eager_block_effects = null;
}
/**
* This is similar to `mark_reactions`, but it only marks async/block effects
* depending on `value` and at least one of the other `sources`, so that
* these effects can re-run after another batch has been committed
* @param {Value} value
* @param {Source[]} sources
* @param {Set<Value>} marked
* @param {Map<Reaction, boolean>} checked
*/
function mark_effects(value, sources, marked, checked) {
	if (marked.has(value)) return;
	marked.add(value);
	if (value.reactions !== null) for (const reaction of value.reactions) {
		const flags = reaction.f;
		if ((flags & 2) !== 0) mark_effects(reaction, sources, marked, checked);
		else if ((flags & 4194320) !== 0 && (flags & 2048) === 0 && depends_on(reaction, sources, checked)) {
			set_signal_status(reaction, DIRTY);
			schedule_effect(reaction);
		}
	}
}
/**
* @param {Reaction} reaction
* @param {Source[]} sources
* @param {Map<Reaction, boolean>} checked
*/
function depends_on(reaction, sources, checked) {
	const depends = checked.get(reaction);
	if (depends !== void 0) return depends;
	if (reaction.deps !== null) for (const dep of reaction.deps) {
		if (includes.call(sources, dep)) return true;
		if ((dep.f & 2) !== 0 && depends_on(dep, sources, checked)) {
			checked.set(dep, true);
			return true;
		}
	}
	checked.set(reaction, false);
	return false;
}
/**
* @param {Effect} effect
* @returns {void}
*/
function schedule_effect(effect) {
	/** @type {Batch} */ current_batch.schedule(effect);
}
/**
* Mark all the effects inside a skipped branch CLEAN, so that
* they can be correctly rescheduled later. Tracks dirty and maybe_dirty
* effects so they can be rescheduled if the branch survives.
* @param {Effect} effect
* @param {{ d: Effect[], m: Effect[] }} tracked
*/
function reset_branch(effect, tracked) {
	if ((effect.f & 32) !== 0 && (effect.f & 1024) !== 0) return;
	if ((effect.f & 2048) !== 0) tracked.d.push(effect);
	else if ((effect.f & 4096) !== 0) tracked.m.push(effect);
	set_signal_status(effect, CLEAN);
	var e = effect.first;
	while (e !== null) {
		reset_branch(e, tracked);
		e = e.next;
	}
}
/**
* Mark an entire effect tree clean following an error
* @param {Effect} effect
*/
function reset_all(effect) {
	set_signal_status(effect, CLEAN);
	var e = effect.first;
	while (e !== null) {
		reset_all(e);
		e = e.next;
	}
}
var first_batch, last_batch, current_batch, previous_batch, batch_values, last_scheduled_effect, is_flushing_sync, is_processing, collected_effects, legacy_updates, flush_count, uid, Batch, eager_block_effects;
var init_batch = __esmMin((() => {
	init_constants$1();
	init_flags();
	init_utils$3();
	init_runtime();
	init_errors();
	init_task();
	init_esm_env();
	init_error_handling();
	init_sources();
	init_effects();
	init_utils$2();
	init_constants();
	init_status();
	init_dev();
	init_debug();
	init_deriveds();
	first_batch = null;
	last_batch = null;
	current_batch = null;
	previous_batch = null;
	batch_values = null;
	last_scheduled_effect = null;
	is_flushing_sync = false;
	is_processing = false;
	collected_effects = null;
	legacy_updates = null;
	flush_count = 0;
	uid = 1;
	Batch = class Batch {
		id = uid++;
		/** True as soon as `#process` was called */
		#started = false;
		linked = true;
		/** @type {Batch | null} */
		#prev = null;
		/** @type {Batch | null} */
		#next = null;
		/** @type {Map<Effect, ReturnType<typeof deferred<any>>>} */
		async_deriveds = /* @__PURE__ */ new Map();
		/**
		* The current values of any signals that are updated in this batch.
		* Tuple format: [value, is_derived] (note: is_derived is false for deriveds, too, if they were overridden via assignment)
		* They keys of this map are identical to `this.#previous`
		* @type {Map<Value, [any, boolean]>}
		*/
		current = /* @__PURE__ */ new Map();
		/**
		* The values of any signals (sources and deriveds) that are updated in this batch _before_ those updates took place.
		* They keys of this map are identical to `this.#current`
		* @type {Map<Value, any>}
		*/
		previous = /* @__PURE__ */ new Map();
		/**
		* When the batch is committed (and the DOM is updated), we need to remove old branches
		* and append new ones by calling the functions added inside (if/each/key/etc) blocks
		* @type {Set<(batch: Batch) => void>}
		*/
		#commit_callbacks = /* @__PURE__ */ new Set();
		/**
		* If a fork is discarded, we need to destroy any effects that are no longer needed
		* @type {Set<(batch: Batch) => void>}
		*/
		#discard_callbacks = /* @__PURE__ */ new Set();
		/**
		* The number of async effects that are currently in flight
		*/
		#pending = 0;
		/**
		* Async effects that are currently in flight, _not_ inside a pending boundary
		* @type {Map<Effect, number>}
		*/
		#blocking_pending = /* @__PURE__ */ new Map();
		/**
		* A deferred that resolves when the batch is committed, used with `settled()`
		* TODO replace with Promise.withResolvers once supported widely enough
		* @type {{ promise: Promise<void>, resolve: (value?: any) => void, reject: (reason: unknown) => void } | null}
		*/
		#deferred = null;
		/**
		* Effects that were scheduled in this batch but not yet 'resolved' into the
		* root effects that need to be flushed. Resolving — the upwards traversal that
		* marks the path to each effect on the shared effect tree (see #resolve) — is
		* deferred until the batch is processed, so that the markers are created and
		* consumed within a single traversal. Scheduling into other batches (which can
		* happen concurrently, e.g. while a batch is committed) can therefore never
		* observe (and be confused by) this batch's markers.
		* May contain duplicates — deduplication happens during resolving
		* @type {Effect[]}
		*/
		#scheduled = [];
		/**
		* Effects created while this batch was active.
		* @type {Effect[]}
		*/
		#new_effects = [];
		/**
		* Deferred effects (which run after async work has completed) that are DIRTY
		* @type {Set<Effect>}
		*/
		#dirty_effects = /* @__PURE__ */ new Set();
		/**
		* Deferred effects that are MAYBE_DIRTY
		* @type {Set<Effect>}
		*/
		#maybe_dirty_effects = /* @__PURE__ */ new Set();
		/**
		* A map of branches that still exist, but will be destroyed when this batch
		* is committed — we skip over these during `process`.
		* The value contains child effects that were dirty/maybe_dirty before being reset,
		* so they can be rescheduled if the branch survives.
		* @type {Map<Effect, { d: Effect[], m: Effect[] }>}
		*/
		#skipped_branches = /* @__PURE__ */ new Map();
		/**
		* Inverse of #skipped_branches which we need to tell prior batches to unskip them when committing
		* @type {Set<Effect>}
		*/
		#unskipped_branches = /* @__PURE__ */ new Set();
		is_fork = false;
		#decrement_queued = false;
		constructor() {
			if (last_batch === null) first_batch = last_batch = this;
			else {
				last_batch.#next = this;
				this.#prev = last_batch;
			}
			last_batch = this;
		}
		#is_deferred() {
			if (this.is_fork) return true;
			for (const effect of this.#blocking_pending.keys()) {
				var e = effect;
				var skipped = false;
				while (e.parent !== null) {
					if (this.#skipped_branches.has(e)) {
						skipped = true;
						break;
					}
					e = e.parent;
				}
				if (!skipped) return true;
			}
			return false;
		}
		/**
		* Add an effect to the #skipped_branches map and reset its children
		* @param {Effect} effect
		*/
		skip_effect(effect) {
			if (!this.#skipped_branches.has(effect)) this.#skipped_branches.set(effect, {
				d: [],
				m: []
			});
			this.#unskipped_branches.delete(effect);
		}
		/**
		* Remove an effect from the #skipped_branches map and reschedule
		* any tracked dirty/maybe_dirty child effects
		* @param {Effect} effect
		* @param {(e: Effect) => void} callback
		*/
		unskip_effect(effect, callback = (e) => this.schedule(e)) {
			var tracked = this.#skipped_branches.get(effect);
			if (tracked) {
				this.#skipped_branches.delete(effect);
				for (var e of tracked.d) {
					set_signal_status(e, DIRTY);
					callback(e);
				}
				for (e of tracked.m) {
					set_signal_status(e, MAYBE_DIRTY);
					callback(e);
				}
			}
			this.#unskipped_branches.add(effect);
		}
		/**
		* Convert the effects that were scheduled in this batch into the root effects
		* that need to be traversed, marking the path to each effect (by clearing the
		* `CLEAN` flag on ancestor branches) so that the traversal can find them.
		* This happens right before traversal rather than at scheduling time, so that
		* the markers left on the (shared) effect tree are created and consumed within
		* a single traversal — scheduling into other batches can never observe them
		* @returns {Effect[]}
		*/
		#resolve() {
			/** @type {Effect[]} */
			var roots = [];
			for (const effect of this.#scheduled) {
				if ((effect.f & 16384) !== 0 || (effect.f & 6144) === 0) continue;
				var e = effect;
				var covered = false;
				while (e.parent !== null) {
					e = e.parent;
					var flags = e.f;
					if ((flags & 96) !== 0) {
						if ((flags & 1024) === 0) {
							covered = true;
							break;
						}
						e.f ^= CLEAN;
					}
				}
				if (!covered) roots.push(e);
			}
			this.#scheduled = [];
			return roots;
		}
		#process() {
			this.#started = true;
			for (const e of this.#dirty_effects) {
				this.#maybe_dirty_effects.delete(e);
				set_signal_status(e, DIRTY);
				this.schedule(e);
			}
			for (const e of this.#maybe_dirty_effects) {
				set_signal_status(e, MAYBE_DIRTY);
				this.schedule(e);
			}
			this.apply();
			/** @type {Effect[]} */
			var effects = collected_effects = [];
			/** @type {Effect[]} */
			var render_effects = [];
			/**
			* @type {Effect[]}
			* @deprecated when we get rid of legacy mode and stores, we can get rid of this
			*/
			var updates = legacy_updates = [];
			while (this.#scheduled.length > 0) {
				if (flush_count++ > 1e3) {
					this.#unlink();
					infinite_loop_guard();
				}
				for (const root of this.#resolve()) try {
					this.#traverse(root, effects, render_effects);
				} catch (e) {
					reset_all(root);
					if (!this.#is_deferred()) this.discard();
					throw e;
				}
			}
			current_batch = null;
			if (updates.length > 0) {
				var batch = Batch.ensure();
				for (const e of updates) batch.schedule(e);
			}
			collected_effects = null;
			legacy_updates = null;
			if (this.#is_deferred()) {
				this.#defer_effects(render_effects);
				this.#defer_effects(effects);
				for (const [e, t] of this.#skipped_branches) reset_branch(e, t);
				if (updates.length > 0)
 /** @type {Batch} */ current_batch.#process();
				return;
			}
			const earlier_batch = this.#find_earlier_batch();
			if (earlier_batch) {
				this.#defer_effects(render_effects);
				this.#defer_effects(effects);
				earlier_batch.#merge(this);
				return;
			}
			this.#dirty_effects.clear();
			this.#maybe_dirty_effects.clear();
			for (const fn of this.#commit_callbacks) fn(this);
			this.#commit_callbacks.clear();
			previous_batch = this;
			flush_queued_effects(render_effects);
			flush_queued_effects(effects);
			previous_batch = null;
			this.#deferred?.resolve();
			var next_batch = current_batch;
			if (this.#pending === 0 && (this.#scheduled.length === 0 || next_batch !== null)) {
				this.#unlink();
				if (async_mode_flag) {
					this.#commit();
					current_batch = next_batch;
				}
			}
			if (this.#scheduled.length > 0) {
				if (next_batch !== null) {
					for (const e of this.#scheduled) next_batch.#scheduled.push(e);
					this.#scheduled = [];
				} else next_batch = this;
			}
			if (next_batch !== null) {
				old_values.clear();
				next_batch.#process();
			}
		}
		/**
		* Traverse the effect tree, executing effects or stashing
		* them for later execution as appropriate
		* @param {Effect} root
		* @param {Effect[]} effects
		* @param {Effect[]} render_effects
		*/
		#traverse(root, effects, render_effects) {
			root.f ^= CLEAN;
			var effect = root.first;
			while (effect !== null) {
				var flags = effect.f;
				var is_branch = (flags & 96) !== 0;
				if (!(is_branch && (flags & 1024) !== 0 || (flags & 8192) !== 0 || this.#skipped_branches.has(effect)) && effect.fn !== null) {
					if (is_branch) effect.f ^= CLEAN;
					else if ((flags & 4) !== 0) effects.push(effect);
					else if (async_mode_flag && (flags & 16777224) !== 0) render_effects.push(effect);
					else if (is_dirty(effect)) {
						if ((flags & 16) !== 0) this.#maybe_dirty_effects.add(effect);
						update_effect(effect);
					}
					var child = effect.first;
					if (child !== null) {
						effect = child;
						continue;
					}
				}
				while (effect !== null) {
					var next = effect.next;
					if (next !== null) {
						effect = next;
						break;
					}
					effect = effect.parent;
				}
			}
		}
		#find_earlier_batch() {
			var batch = this.#prev;
			while (batch !== null) {
				if (!batch.is_fork) {
					for (const [value, [, is_derived]] of this.current) if (batch.current.has(value) && !is_derived) return batch;
				}
				batch = batch.#prev;
			}
			return null;
		}
		/**
		* @param {Batch} batch
		*/
		#merge(batch) {
			for (const [source, value] of batch.current) {
				if (!this.previous.has(source) && batch.previous.has(source)) this.previous.set(source, batch.previous.get(source));
				this.current.set(source, value);
			}
			for (const [effect, deferred] of batch.async_deriveds) {
				const d = this.async_deriveds.get(effect);
				if (d) deferred.promise.then(d.resolve).catch(d.reject);
			}
			batch.async_deriveds.clear();
			this.transfer_effects(batch.#dirty_effects, batch.#maybe_dirty_effects);
			/**
			* mark all effects that depend on `batch.current`, except the
			* async effects that we just resolved (TODO unless they depend
			* on values in this batch that are NOT in the later batch?).
			* Through this we also will populate the correct #skipped_branches,
			* oncommit callbacks etc, so we don't need to merge them separately.
			* @param {Value} value
			*/
			const mark = (value) => {
				var reactions = value.reactions;
				if (reactions === null) return;
				if ((value.f & 2) !== 0 && (value.f & 6144) === 0) return;
				for (const reaction of reactions) {
					var flags = reaction.f;
					if ((flags & 2) !== 0) mark(reaction);
					else {
						var effect = reaction;
						if (flags & 4194320 && !this.async_deriveds.has(effect)) {
							this.#maybe_dirty_effects.delete(effect);
							set_signal_status(effect, DIRTY);
							this.schedule(effect);
						}
					}
				}
			};
			for (const source of this.current.keys()) mark(source);
			this.oncommit(() => batch.discard());
			batch.#unlink();
			current_batch = this;
			this.#process();
		}
		/**
		* @param {Effect[]} effects
		*/
		#defer_effects(effects) {
			for (var i = 0; i < effects.length; i += 1) defer_effect(effects[i], this.#dirty_effects, this.#maybe_dirty_effects);
		}
		/**
		* Associate a change to a given source with the current
		* batch, noting its previous and current values
		* @param {Value} source
		* @param {any} value
		* @param {boolean} [is_derived]
		*/
		capture(source, value, is_derived = false) {
			if (source.v !== UNINITIALIZED && !this.previous.has(source)) this.previous.set(source, source.v);
			if ((source.f & 8388608) === 0) {
				this.current.set(source, [value, is_derived]);
				batch_values?.set(source, value);
			}
			if (!this.is_fork) source.v = value;
		}
		activate() {
			current_batch = this;
		}
		deactivate() {
			current_batch = null;
			batch_values = null;
		}
		flush() {
			try {
				is_processing = true;
				current_batch = this;
				this.#process();
			} finally {
				flush_count = 0;
				last_scheduled_effect = null;
				collected_effects = null;
				legacy_updates = null;
				is_processing = false;
				current_batch = null;
				batch_values = null;
				old_values.clear();
			}
		}
		discard() {
			for (const fn of this.#discard_callbacks) fn(this);
			this.#discard_callbacks.clear();
			for (const deferred of this.async_deriveds.values()) deferred.reject(OBSOLETE);
			this.#unlink();
			this.#deferred?.resolve();
		}
		/**
		* @param {Effect} effect
		*/
		register_created_effect(effect) {
			this.#new_effects.push(effect);
		}
		#commit() {
			for (let batch = first_batch; batch !== null; batch = batch.#next) {
				var is_earlier = batch.id < this.id;
				/** @type {Source[]} */
				var sources = [];
				for (const [source, [value, is_derived]] of this.current) {
					if (batch.current.has(source)) {
						var batch_value = batch.current.get(source)[0];
						if (is_earlier && value !== batch_value) batch.current.set(source, [value, is_derived]);
						else continue;
					}
					sources.push(source);
				}
				if (is_earlier) for (const [effect, deferred] of this.async_deriveds) {
					const d = batch.async_deriveds.get(effect);
					if (d) deferred.promise.then(d.resolve).catch(d.reject);
				}
				var current = [...batch.current.keys()].filter((source) => !batch.current.get(source)[1]);
				if (!batch.#started || current.length === 0) continue;
				var others = current.filter((source) => !this.current.has(source));
				if (others.length === 0) {
					if (is_earlier) batch.discard();
				} else if (sources.length > 0) {
					if (is_earlier) for (const unskipped of this.#unskipped_branches) batch.unskip_effect(unskipped, (e) => {
						if ((e.f & 4194320) !== 0) batch.schedule(e);
						else batch.#defer_effects([e]);
					});
					batch.activate();
					/** @type {Set<Value>} */
					var marked = /* @__PURE__ */ new Set();
					/** @type {Map<Reaction, boolean>} */
					var checked = /* @__PURE__ */ new Map();
					for (var source of sources) mark_effects(source, others, marked, checked);
					checked = /* @__PURE__ */ new Map();
					var current_unequal = [...batch.current].filter(([c, v1]) => {
						const v2 = this.current.get(c);
						if (!v2) return true;
						return v2[0] !== v1[0] || v2[1] !== v1[1];
					}).map(([c]) => c);
					if (current_unequal.length > 0) {
						for (const effect of this.#new_effects) if ((effect.f & 155648) === 0 && depends_on(effect, current_unequal, checked)) {
							if ((effect.f & 4194320) !== 0) {
								set_signal_status(effect, DIRTY);
								batch.schedule(effect);
							} else batch.#dirty_effects.add(effect);
						}
					}
					if (batch.#scheduled.length > 0 && !batch.#decrement_queued) {
						batch.apply();
						for (var root of batch.#resolve()) batch.#traverse(root, [], []);
					}
					batch.deactivate();
				}
			}
		}
		/**
		* @param {boolean} blocking
		* @param {Effect} effect
		*/
		increment(blocking, effect) {
			this.#pending += 1;
			if (blocking) {
				let blocking_pending_count = this.#blocking_pending.get(effect) ?? 0;
				this.#blocking_pending.set(effect, blocking_pending_count + 1);
			}
		}
		/**
		* @param {boolean} blocking
		* @param {Effect} effect
		*/
		decrement(blocking, effect) {
			this.#pending -= 1;
			if (blocking) {
				let blocking_pending_count = this.#blocking_pending.get(effect) ?? 0;
				if (blocking_pending_count === 1) this.#blocking_pending.delete(effect);
				else this.#blocking_pending.set(effect, blocking_pending_count - 1);
			}
			if (this.#decrement_queued) return;
			this.#decrement_queued = true;
			queue_micro_task(() => {
				this.#decrement_queued = false;
				if (this.linked) this.flush();
			});
		}
		/**
		* @param {Set<Effect>} dirty_effects
		* @param {Set<Effect>} maybe_dirty_effects
		*/
		transfer_effects(dirty_effects, maybe_dirty_effects) {
			for (const e of dirty_effects) this.#dirty_effects.add(e);
			for (const e of maybe_dirty_effects) this.#maybe_dirty_effects.add(e);
			dirty_effects.clear();
			maybe_dirty_effects.clear();
		}
		/** @param {(batch: Batch) => void} fn */
		oncommit(fn) {
			this.#commit_callbacks.add(fn);
		}
		/** @param {(batch: Batch) => void} fn */
		ondiscard(fn) {
			this.#discard_callbacks.add(fn);
		}
		settled() {
			return (this.#deferred ??= deferred()).promise;
		}
		static ensure() {
			if (current_batch === null) {
				const batch = current_batch = new Batch();
				if (!is_processing && !is_flushing_sync) queue_micro_task(() => {
					if (!batch.#started) batch.flush();
				});
			}
			return current_batch;
		}
		apply() {
			if (!async_mode_flag || !this.is_fork && this.#prev === null && this.#next === null) {
				batch_values = null;
				return;
			}
			batch_values = /* @__PURE__ */ new Map();
			for (const [source, [value]] of this.current) batch_values.set(source, value);
			for (let batch = first_batch; batch !== null; batch = batch.#next) {
				if (batch === this || batch.is_fork) continue;
				var intersects = false;
				if (batch.id < this.id) for (const [source, [, is_derived]] of batch.current) {
					if (is_derived) continue;
					if (this.current.has(source)) {
						intersects = true;
						break;
					}
				}
				if (!intersects) {
					for (const [source, previous] of batch.previous) if (!batch_values.has(source)) batch_values.set(source, previous);
				}
			}
		}
		/**
		*
		* @param {Effect} effect
		*/
		schedule(effect) {
			last_scheduled_effect = effect;
			if (effect.b?.is_pending && (effect.f & 16777228) !== 0 && (effect.f & 32768) === 0) {
				effect.b.defer_effect(effect);
				return;
			}
			this.#scheduled.push(effect);
		}
		#unlink() {
			if (!this.linked) return;
			var prev = this.#prev;
			var next = this.#next;
			if (prev === null) first_batch = next;
			else prev.#next = next;
			if (next === null) last_batch = prev;
			else next.#prev = prev;
			this.linked = false;
		}
	};
	eager_block_effects = null;
}));
/**
* @template V
* @param {V} v
* @param {Error | null} [stack]
* @returns {Source<V>}
*/
function source(v, stack) {
	return {
		f: 0,
		v,
		reactions: null,
		equals,
		rv: 0,
		wv: 0
	};
}
/**
* @template V
* @param {V} v
* @param {Error | null} [stack]
*/
/*#__NO_SIDE_EFFECTS__*/
function state$1(v, stack) {
	const s = source(v, stack);
	push_reaction_value(s);
	return s;
}
/**
* @template V
* @param {V} initial_value
* @param {boolean} [immutable]
* @returns {Source<V>}
*/
/*#__NO_SIDE_EFFECTS__*/
function mutable_source(initial_value, immutable = false, trackable = true) {
	const s = source(initial_value);
	if (!immutable) s.equals = safe_equals;
	if (legacy_mode_flag && trackable && component_context !== null && component_context.l !== null) (component_context.l.s ??= []).push(s);
	return s;
}
/**
* @template V
* @param {Source<V>} source
* @param {V} value
* @param {boolean} [should_proxy]
* @returns {V}
*/
function set(source, value, should_proxy = false) {
	if (active_reaction !== null && (!untracking || (active_reaction.f & 131072) !== 0) && is_runes() && (active_reaction.f & 4325394) !== 0 && (current_sources === null || !current_sources.has(source))) state_unsafe_mutation();
	return internal_set(source, should_proxy ? proxy(value) : value, legacy_updates);
}
/**
* @template V
* @param {Source<V>} source
* @param {V} value
* @param {Effect[] | null} [updated_during_traversal]
* @returns {V}
*/
function internal_set(source, value, updated_during_traversal = null) {
	if (!source.equals(value)) {
		if (is_destroying_effect) old_values.set(source, value);
		else if (!old_values.has(source)) old_values.set(source, source.v);
		var batch = Batch.ensure();
		batch.capture(source, value);
		if ((source.f & 2) !== 0) {
			const derived = source;
			if ((source.f & 2048) !== 0) execute_derived(derived);
			if (batch_values === null) update_derived_status(derived);
		}
		source.wv = increment_write_version();
		seen = null;
		count_deps = 0;
		mark_reactions(source, DIRTY, updated_during_traversal);
		seen = null;
		if (is_runes() && active_effect !== null && (active_effect.f & 1024) !== 0 && (active_effect.f & 96) === 0) {
			if (untracked_writes === null) set_untracked_writes([source]);
			else untracked_writes.push(source);
		}
		if (!batch.is_fork && eager_effects.size > 0 && !eager_effects_deferred) flush_eager_effects();
	}
	return value;
}
function flush_eager_effects() {
	eager_effects_deferred = false;
	for (const effect of eager_effects) {
		if ((effect.f & 1024) !== 0) set_signal_status(effect, MAYBE_DIRTY);
		let dirty;
		try {
			dirty = is_dirty(effect);
		} catch {
			dirty = true;
		}
		if (dirty) update_effect(effect);
	}
	eager_effects.clear();
}
/**
* Silently (without using `get`) increment a source
* @param {Source<number>} source
*/
function increment(source) {
	set(source, source.v + 1);
}
/**
* @param {Value} signal
* @param {number} status should be DIRTY or MAYBE_DIRTY
* @param {Effect[] | null} updated_during_traversal
* @returns {void}
*/
function mark_reactions(signal, status, updated_during_traversal) {
	var reactions = signal.reactions;
	if (reactions === null) return;
	var runes = is_runes();
	var length = reactions.length;
	count_deps += length;
	if (count_deps > 1e5 && seen === null) seen = /* @__PURE__ */ new Set();
	if (seen !== null) {
		if (seen.has(signal)) return;
		seen.add(signal);
	}
	for (var i = 0; i < length; i++) {
		var reaction = reactions[i];
		var flags = reaction.f;
		if (!runes && reaction === active_effect) continue;
		var not_dirty = (flags & DIRTY) === 0;
		if (not_dirty) set_signal_status(reaction, status);
		if ((flags & 131072) !== 0) eager_effects.add(reaction);
		else if ((flags & 2) !== 0) {
			var derived = reaction;
			batch_values?.delete(derived);
			mark_reactions(derived, MAYBE_DIRTY, updated_during_traversal);
		} else if (not_dirty) {
			var effect = reaction;
			if ((flags & 16) !== 0 && eager_block_effects !== null) eager_block_effects.add(effect);
			if (updated_during_traversal !== null) updated_during_traversal.push(effect);
			else schedule_effect(effect);
		}
	}
}
var eager_effects, old_values, eager_effects_deferred, seen, count_deps;
var init_sources = __esmMin((() => {
	init_esm_env();
	init_runtime();
	init_equality$1();
	init_constants$1();
	init_errors();
	init_flags();
	init_tracing();
	init_dev();
	init_context();
	init_batch();
	init_proxy();
	init_deriveds();
	init_status();
	eager_effects = /* @__PURE__ */ new Set();
	old_values = /* @__PURE__ */ new Map();
	eager_effects_deferred = false;
	seen = null;
	count_deps = 0;
}));
//#endregion
//#region node_modules/svelte/src/internal/client/proxy.js
/**
* @template T
* @param {T} value
* @returns {T}
*/
function proxy(value) {
	if (typeof value !== "object" || value === null || STATE_SYMBOL in value || COMPONENT_SYMBOL in value) return value;
	const prototype = get_prototype_of(value);
	if (prototype !== object_prototype && prototype !== array_prototype) return value;
	/** @type {Map<any, Source<any>>} */
	var sources = /* @__PURE__ */ new Map();
	var is_proxied_array = is_array(value);
	var version = /* @__PURE__ */ state$1(0);
	var stack = null;
	var parent_version = update_version;
	/**
	* Executes the proxy in the context of the reaction it was originally created in, if any
	* @template T
	* @param {() => T} fn
	*/
	var with_parent = (fn) => {
		if (update_version === parent_version) return fn();
		var reaction = active_reaction;
		var version = update_version;
		set_active_reaction(null);
		set_update_version(parent_version);
		var result = fn();
		set_active_reaction(reaction);
		set_update_version(version);
		return result;
	};
	if (is_proxied_array) sources.set("length", /* @__PURE__ */ state$1(
		/** @type {any[]} */
		value.length,
		stack
	));
	return new Proxy(value, {
		defineProperty(_, prop, descriptor) {
			if (!("value" in descriptor) || descriptor.configurable === false || descriptor.enumerable === false || descriptor.writable === false) state_descriptors_fixed();
			var s = sources.get(prop);
			if (s === void 0) with_parent(() => {
				var s = /* @__PURE__ */ state$1(descriptor.value, stack);
				sources.set(prop, s);
				return s;
			});
			else set(s, descriptor.value, true);
			return true;
		},
		deleteProperty(target, prop) {
			var s = sources.get(prop);
			if (s === void 0) {
				if (prop in target) {
					const s = with_parent(() => /* @__PURE__ */ state$1(UNINITIALIZED, stack));
					sources.set(prop, s);
					increment(version);
				}
			} else {
				set(s, UNINITIALIZED);
				increment(version);
			}
			return true;
		},
		get(target, prop, receiver) {
			if (prop === STATE_SYMBOL) return value;
			var s = sources.get(prop);
			var exists = prop in target;
			if (s === void 0 && (!exists || get_descriptor(target, prop)?.writable)) {
				s = with_parent(() => {
					return /* @__PURE__ */ state$1(proxy(exists ? target[prop] : UNINITIALIZED), stack);
				});
				sources.set(prop, s);
			}
			if (s !== void 0) {
				var v = get(s);
				return v === UNINITIALIZED ? void 0 : v;
			}
			return Reflect.get(target, prop, receiver);
		},
		getOwnPropertyDescriptor(target, prop) {
			this.has?.(target, prop);
			var descriptor = Reflect.getOwnPropertyDescriptor(target, prop);
			var s = sources.get(prop);
			if (s !== void 0) {
				var value = get(s);
				if (value === UNINITIALIZED) return;
				if (descriptor && "value" in descriptor) descriptor.value = value;
				else return {
					enumerable: true,
					configurable: true,
					value,
					writable: true
				};
			}
			return descriptor;
		},
		has(target, prop) {
			if (prop === STATE_SYMBOL) return true;
			var s = sources.get(prop);
			var has = s !== void 0 && s.v !== UNINITIALIZED || Reflect.has(target, prop);
			if (s !== void 0 || active_effect !== null && (!has || get_descriptor(target, prop)?.writable)) {
				if (s === void 0) {
					s = with_parent(() => {
						return /* @__PURE__ */ state$1(has ? proxy(target[prop]) : UNINITIALIZED, stack);
					});
					sources.set(prop, s);
				}
				if (get(s) === UNINITIALIZED) return false;
			}
			return has;
		},
		set(target, prop, value, receiver) {
			var s = sources.get(prop);
			var has = prop in target;
			if (is_proxied_array && prop === "length") for (var i = value; i < s.v; i += 1) {
				var other_s = sources.get(i + "");
				if (other_s !== void 0) set(other_s, UNINITIALIZED);
				else if (i in target) {
					other_s = with_parent(() => /* @__PURE__ */ state$1(UNINITIALIZED, stack));
					sources.set(i + "", other_s);
				}
			}
			if (s === void 0) {
				if (!has || get_descriptor(target, prop)?.writable) {
					s = with_parent(() => /* @__PURE__ */ state$1(void 0, stack));
					set(s, proxy(value));
					sources.set(prop, s);
				}
			} else {
				has = s.v !== UNINITIALIZED;
				var p = with_parent(() => proxy(value));
				set(s, p);
			}
			var descriptor = Reflect.getOwnPropertyDescriptor(target, prop);
			if (descriptor?.set) descriptor.set.call(receiver, value);
			if (!has) {
				if (is_proxied_array && typeof prop === "string") {
					var ls = sources.get("length");
					var n = Number(prop);
					if (Number.isInteger(n) && n >= ls.v) set(ls, n + 1);
				}
				increment(version);
			}
			return true;
		},
		ownKeys(target) {
			get(version);
			var own_keys = Reflect.ownKeys(target).filter((key) => {
				var source = sources.get(key);
				return source === void 0 || source.v !== UNINITIALIZED;
			});
			for (var [key, source] of sources) if (source.v !== UNINITIALIZED && !(key in target)) own_keys.push(key);
			return own_keys;
		},
		setPrototypeOf() {
			state_prototype_fixed();
		}
	});
}
var init_proxy = __esmMin((() => {
	init_esm_env();
	init_runtime();
	init_utils$3();
	init_sources();
	init_constants$1();
	init_constants();
	init_errors();
	init_tracing();
	init_dev();
	init_flags();
}));
var init_equality = __esmMin((() => {
	init_warnings();
	init_proxy();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/operations.js
/**
* Initialize these lazily to avoid issues when using the runtime in a server context
* where these globals are not available while avoiding a separate server entry point
*/
function init_operations() {
	if ($window !== void 0) return;
	$window = window;
	$document = document;
	is_firefox = /Firefox/.test(navigator.userAgent);
	var element_prototype = Element.prototype;
	var node_prototype = Node.prototype;
	var text_prototype = Text.prototype;
	first_child_getter = get_descriptor(node_prototype, "firstChild").get;
	next_sibling_getter = get_descriptor(node_prototype, "nextSibling").get;
	if (is_extensible(element_prototype)) {
		/** @type {any} */ element_prototype[CLASS_CACHE] = void 0;
		/** @type {any} */ element_prototype[ATTRIBUTES_CACHE] = null;
		/** @type {any} */ element_prototype[STYLE_CACHE] = void 0;
		element_prototype.__e = void 0;
	}
	if (is_extensible(text_prototype))
 /** @type {any} */ text_prototype[TEXT_CACHE] = void 0;
}
/**
* @param {string} value
* @returns {Text}
*/
function create_text(value = "") {
	return document.createTextNode(value);
}
/**
* @template {Node} N
* @param {N} node
*/
/*@__NO_SIDE_EFFECTS__*/
function get_first_child(node) {
	return first_child_getter.call(node);
}
/**
* @template {Node} N
* @param {N} node
*/
/*@__NO_SIDE_EFFECTS__*/
function get_next_sibling(node) {
	return next_sibling_getter.call(node);
}
/**
* Don't mark this as side-effect-free, hydration needs to walk all nodes
* @template {Node} N
* @param {N} node
* @param {boolean} is_text
* @returns {TemplateNode | null}
*/
function child(node, is_text) {
	if (!hydrating) return /* @__PURE__ */ get_first_child(node);
	var child = /* @__PURE__ */ get_first_child(hydrate_node);
	if (child === null) child = hydrate_node.appendChild(create_text());
	else if (is_text && child.nodeType !== 3) {
		var text = create_text();
		child?.before(text);
		set_hydrate_node(text);
		return text;
	}
	if (is_text) merge_text_nodes(child);
	set_hydrate_node(child);
	return child;
}
/**
* Don't mark this as side-effect-free, hydration needs to walk all nodes
* @param {TemplateNode} node
* @param {boolean} [is_text]
* @returns {TemplateNode | null}
*/
function first_child(node, is_text = false) {
	if (!hydrating) {
		var first = /* @__PURE__ */ get_first_child(node);
		if (first instanceof Comment && first.data === "") return /* @__PURE__ */ get_next_sibling(first);
		return first;
	}
	if (is_text) {
		if (hydrate_node?.nodeType !== 3) {
			var text = create_text();
			hydrate_node?.before(text);
			set_hydrate_node(text);
			return text;
		}
		merge_text_nodes(hydrate_node);
	}
	return hydrate_node;
}
/**
* `child`, for the very common case of an element with exactly one child. Resetting the
* hydration cursor is part of the same step, so the compiler doesn't have to emit a
* separate `reset` call for every `<p>{text}</p>` in an app.
* Don't mark this as side-effect-free, hydration needs to walk all nodes
* @param {TemplateNode} node
* @param {boolean} [is_text]
* @returns {TemplateNode | null}
*/
function only_child(node, is_text = false) {
	if (!hydrating) return /* @__PURE__ */ get_first_child(node);
	var first = child(node, is_text);
	reset(node);
	return first;
}
/**
* Don't mark this as side-effect-free, hydration needs to walk all nodes
* @param {TemplateNode} node
* @param {number} count
* @param {boolean} is_text
* @returns {TemplateNode | null}
*/
function sibling(node, count = 1, is_text = false) {
	let next_sibling = hydrating ? hydrate_node : node;
	var last_sibling;
	while (count--) {
		last_sibling = next_sibling;
		next_sibling = /* @__PURE__ */ get_next_sibling(next_sibling);
	}
	if (!hydrating) return next_sibling;
	if (is_text) {
		if (next_sibling?.nodeType !== 3) {
			var text = create_text();
			if (next_sibling === null) last_sibling?.after(text);
			else next_sibling.before(text);
			set_hydrate_node(text);
			return text;
		}
		merge_text_nodes(next_sibling);
	}
	set_hydrate_node(next_sibling);
	return next_sibling;
}
/**
* @template {Node} N
* @param {N} node
* @returns {void}
*/
function clear_text_content(node) {
	node.textContent = "";
}
/**
* Returns `true` if we're updating the current block, for example `condition` in
* an `{#if condition}` block just changed. In this case, the branch should be
* appended (or removed) at the same time as other updates within the
* current `<svelte:boundary>`
*/
function should_defer_append() {
	if (!async_mode_flag) return false;
	if (eager_block_effects !== null) return false;
	return (active_effect.f & REACTION_RAN) !== 0;
}
/**
* Branching here is intentional and load-bearing for perf. `createElement(tag)`
* hits a fast path in Blink that `createElementNS(NAMESPACE_HTML, tag)` doesn't,
* and passing an explicit `undefined` as the trailing options arg measurably
* slows both APIs. Funnelling every case through a single `createElementNS(ns,
* tag, options)` call would be smaller but slower on the HTML path.
*
* @template {keyof HTMLElementTagNameMap | string} T
* @param {T} tag
* @param {string} [namespace]
* @param {string} [is]
* @returns {T extends keyof HTMLElementTagNameMap ? HTMLElementTagNameMap[T] : Element}
*/
function create_element(tag, namespace, is) {
	if (namespace == null || namespace === "http://www.w3.org/1999/xhtml") return is ? document.createElement(tag, { is }) : document.createElement(tag);
	return is ? document.createElementNS(namespace, tag, { is }) : document.createElementNS(namespace, tag);
}
/**
* Browsers split text nodes larger than 65536 bytes when parsing.
* For hydration to succeed, we need to stitch them back together
* @param {Text} text
*/
function merge_text_nodes(text) {
	if (text.nodeValue.length < 65536) return;
	let next = text.nextSibling;
	while (next !== null && next.nodeType === 3) {
		next.remove();
		/** @type {string} */ text.nodeValue += next.nodeValue;
		next = text.nextSibling;
	}
}
var $window, $document, is_firefox, first_child_getter, next_sibling_getter;
var init_operations$1 = __esmMin((() => {
	init_hydration();
	init_esm_env();
	init_equality();
	init_utils$3();
	init_runtime();
	init_flags();
	init_constants$1();
	init_batch();
	init_constants();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/error-handling.js
/**
* @param {unknown} error
*/
function handle_error(error) {
	var effect = active_effect;
	if (effect === null) {
		/** @type {Derived} */ active_reaction.f |= ERROR_VALUE;
		return error;
	}
	if ((effect.f & 32768) === 0 && (effect.f & 4) === 0) throw error;
	invoke_error_boundary(error, effect);
}
/**
* @param {unknown} error
* @param {Effect | null} effect
*/
function invoke_error_boundary(error, effect) {
	if (effect !== null && (effect.f & 16384) !== 0) return;
	while (effect !== null) {
		if ((effect.f & 128) !== 0 && (effect.f & 33570816) === 0) {
			if ((effect.f & 32768) === 0) throw error;
			try {
				/** @type {Boundary} */ effect.b.error(error);
				return;
			} catch (e) {
				error = e;
			}
		}
		effect = effect.parent;
	}
	throw error;
}
var init_error_handling = __esmMin((() => {
	init_esm_env();
	init_constants();
	init_operations$1();
	init_constants$1();
	init_utils$3();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/effects.js
/**
* @param {Effect} effect
* @param {Effect} parent_effect
*/
function push_effect(effect, parent_effect) {
	var parent_last = parent_effect.last;
	if (parent_last === null) parent_effect.last = parent_effect.first = effect;
	else {
		parent_last.next = effect;
		effect.prev = parent_last;
		parent_effect.last = effect;
	}
}
/**
* @param {number} type
* @param {null | (() => void | (() => void))} fn
* @returns {Effect}
*/
function create_effect(type, fn) {
	var parent = active_effect;
	if (parent !== null && (parent.f & 8192) !== 0) type |= INERT;
	/** @type {Effect} */
	var effect = {
		ctx: component_context,
		deps: null,
		nodes: null,
		f: type | DIRTY | 512,
		first: null,
		fn,
		last: null,
		next: null,
		parent,
		b: parent && parent.b,
		prev: null,
		teardown: null,
		wv: 0,
		ac: null
	};
	current_batch?.register_created_effect(effect);
	/** @type {Effect | null} */
	var e = effect;
	if ((type & 4) !== 0) {
		if (collected_effects !== null) collected_effects.push(effect);
		else Batch.ensure().schedule(effect);
	} else if (fn !== null) {
		try {
			update_effect(effect);
		} catch (e) {
			destroy_effect(effect);
			throw e;
		}
		if (e.deps === null && e.teardown === null && e.nodes === null && e.first === e.last && (e.f & 524288) === 0) {
			e = e.first;
			if ((type & 16) !== 0 && (type & 65536) !== 0 && e !== null) e.f |= EFFECT_TRANSPARENT;
		}
	}
	if (e !== null) {
		e.parent = parent;
		if (parent !== null) push_effect(e, parent);
		if (active_reaction !== null && (active_reaction.f & 2) !== 0 && (type & 64) === 0) {
			var derived = active_reaction;
			(derived.effects ??= []).push(e);
		}
	}
	return effect;
}
/**
* Internal representation of `$effect.tracking()`
* @returns {boolean}
*/
function effect_tracking() {
	return active_reaction !== null && !untracking;
}
/**
* @param {() => void} fn
*/
function teardown(fn) {
	const effect = create_effect(8, null);
	set_signal_status(effect, CLEAN);
	effect.teardown = fn;
	return effect;
}
/**
* @param {() => void | (() => void)} fn
*/
function create_user_effect(fn) {
	return create_effect(4 | USER_EFFECT, fn);
}
/**
* An effect root whose children can transition out
* @param {() => void} fn
* @returns {(options?: { outro?: boolean }) => Promise<void>}
*/
function component_root(fn) {
	Batch.ensure();
	const effect = create_effect(64 | EFFECT_PRESERVED, fn);
	return (options = {}) => {
		return new Promise((fulfil) => {
			if (options.outro) pause_effect(effect, () => {
				destroy_effect(effect);
				fulfil(void 0);
			});
			else {
				destroy_effect(effect);
				fulfil(void 0);
			}
		});
	};
}
/**
* @param {() => void | (() => void)} fn
* @returns {Effect}
*/
function async_effect(fn) {
	return create_effect(ASYNC | EFFECT_PRESERVED, fn);
}
/**
* @param {() => void | (() => void)} fn
* @returns {Effect}
*/
function render_effect(fn, flags = 0) {
	return create_effect(8 | flags, fn);
}
/**
* @param {(...expressions: any) => void | (() => void)} fn
* @param {Array<() => any>} sync
* @param {Array<() => Promise<any>>} async
* @param {Blocker[]} blockers
*/
function template_effect(fn, sync = [], async = [], blockers = []) {
	flatten(blockers, sync, async, (values) => {
		create_effect(8, () => {
			fn(...values.map(get));
		});
	});
}
/**
* @param {(() => void)} fn
* @param {number} flags
*/
function block(fn, flags = 0) {
	return create_effect(16 | flags, fn);
}
/**
* @param {(() => void)} fn
*/
function branch(fn) {
	return create_effect(32 | EFFECT_PRESERVED, fn);
}
/**
* @param {Effect} effect
*/
function execute_effect_teardown(effect) {
	var teardown = effect.teardown;
	if (teardown !== null) {
		const previously_destroying_effect = is_destroying_effect;
		const previous_reaction = active_reaction;
		set_is_destroying_effect(true);
		set_active_reaction(null);
		try {
			teardown.call(null);
		} catch (error) {
			invoke_error_boundary(error, effect.parent);
		} finally {
			set_is_destroying_effect(previously_destroying_effect);
			set_active_reaction(previous_reaction);
		}
	}
}
/**
* @param {Effect} signal
* @param {boolean} remove_dom
* @returns {void}
*/
function destroy_effect_children(signal, remove_dom = false) {
	var effect = signal.first;
	signal.first = signal.last = null;
	while (effect !== null) {
		const controller = effect.ac;
		if (controller !== null) without_reactive_context(() => {
			controller.abort(STALE_REACTION);
		});
		var next = effect.next;
		if ((effect.f & 64) !== 0) effect.parent = null;
		else destroy_effect(effect, remove_dom);
		effect = next;
	}
}
/**
* @param {Effect} signal
* @returns {void}
*/
function destroy_block_effect_children(signal) {
	var effect = signal.first;
	while (effect !== null) {
		var next = effect.next;
		if ((effect.f & 32) === 0) destroy_effect(effect);
		effect = next;
	}
}
/**
* @param {Effect} effect
* @param {boolean} [remove_dom]
* @returns {void}
*/
function destroy_effect(effect, remove_dom = true) {
	var removed = false;
	if ((remove_dom || (effect.f & 262144) !== 0) && effect.nodes !== null && effect.nodes.end !== null) {
		remove_effect_dom(effect.nodes.start, effect.nodes.end);
		removed = true;
	}
	effect.f |= DESTROYING;
	destroy_effect_children(effect, remove_dom && !removed);
	remove_reactions(effect, 0);
	var transitions = effect.nodes && effect.nodes.t;
	if (transitions !== null) for (const transition of transitions) transition.stop();
	execute_effect_teardown(effect);
	effect.f ^= DESTROYING;
	effect.f |= DESTROYED;
	var parent = effect.parent;
	if (parent !== null && parent.first !== null) unlink_effect(effect);
	effect.next = effect.prev = effect.teardown = effect.ctx = effect.deps = effect.fn = effect.nodes = effect.ac = effect.b = null;
}
/**
*
* @param {TemplateNode | null} node
* @param {TemplateNode} end
*/
function remove_effect_dom(node, end) {
	while (node !== null) {
		/** @type {TemplateNode | null} */
		var next = node === end ? null : /* @__PURE__ */ get_next_sibling(node);
		node.remove();
		node = next;
	}
}
/**
* Detach an effect from the effect tree, freeing up memory and
* reducing the amount of work that happens on subsequent traversals
* @param {Effect} effect
*/
function unlink_effect(effect) {
	var parent = effect.parent;
	var prev = effect.prev;
	var next = effect.next;
	if (prev !== null) prev.next = next;
	if (next !== null) next.prev = prev;
	if (parent !== null) {
		if (parent.first === effect) parent.first = next;
		if (parent.last === effect) parent.last = prev;
	}
}
/**
* When a block effect is removed, we don't immediately destroy it or yank it
* out of the DOM, because it might have transitions. Instead, we 'pause' it.
* It stays around (in memory, and in the DOM) until outro transitions have
* completed, and if the state change is reversed then we _resume_ it.
* A paused effect does not update, and the DOM subtree becomes inert.
* @param {Effect} effect
* @param {() => void} [callback]
* @param {boolean} [destroy]
*/
function pause_effect(effect, callback, destroy = true) {
	/** @type {TransitionManager[]} */
	var transitions = [];
	effect.f |= 256;
	pause_children(effect, transitions, true);
	var fn = () => {
		if (destroy) destroy_effect(effect);
		if (callback) callback();
	};
	var remaining = transitions.length;
	if (remaining > 0) {
		var check = () => --remaining || fn();
		for (var transition of transitions) transition.out(check);
	} else fn();
}
/**
* @param {Effect} effect
* @param {TransitionManager[]} transitions
* @param {boolean} local
*/
function pause_children(effect, transitions, local) {
	if ((effect.f & 8192) !== 0) return;
	effect.f ^= INERT;
	var t = effect.nodes && effect.nodes.t;
	if (t !== null) {
		for (const transition of t) if (transition.is_global || local) transitions.push(transition);
	}
	var child = effect.first;
	while (child !== null) {
		var sibling = child.next;
		if ((child.f & 64) === 0) {
			var transparent = (child.f & 65536) !== 0 || (child.f & 32) !== 0 && (effect.f & 16) !== 0;
			pause_children(child, transitions, transparent ? local : false);
		}
		child = sibling;
	}
}
/**
* The opposite of `pause_effect`. We call this if (for example)
* `x` becomes falsy then truthy: `{#if x}...{/if}`
* @param {Effect} effect
*/
function resume_effect(effect) {
	effect.f &= -257;
	resume_children(effect, true);
}
/**
* @param {Effect} effect
* @param {boolean} local
*/
function resume_children(effect, local) {
	if ((effect.f & 256) !== 0) return;
	if ((effect.f & 8192) === 0) return;
	effect.f ^= INERT;
	if ((effect.f & 1024) === 0) {
		set_signal_status(effect, DIRTY);
		Batch.ensure().schedule(effect);
	}
	var child = effect.first;
	while (child !== null) {
		var sibling = child.next;
		var transparent = (child.f & 65536) !== 0 || (child.f & 32) !== 0;
		resume_children(child, transparent ? local : false);
		child = sibling;
	}
	var t = effect.nodes && effect.nodes.t;
	if (t !== null) {
		for (const transition of t) if (transition.is_global || local) transition.in();
	}
}
/**
* @param {Effect} effect
* @param {DocumentFragment} fragment
*/
function move_effect(effect, fragment) {
	if (!effect.nodes) return;
	/** @type {TemplateNode | null} */
	var node = effect.nodes.start;
	var end = effect.nodes.end;
	while (node !== null) {
		/** @type {TemplateNode | null} */
		var next = node === end ? null : /* @__PURE__ */ get_next_sibling(node);
		fragment.append(node);
		node = next;
	}
}
var init_effects = __esmMin((() => {
	init_runtime();
	init_constants$1();
	init_error_handling();
	init_errors();
	init_esm_env();
	init_utils$3();
	init_operations$1();
	init_context();
	init_batch();
	init_async$1();
	init_shared$1();
	init_status();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/legacy.js
var captured_signals;
var init_legacy$1 = __esmMin((() => {
	init_sources();
	init_runtime();
	captured_signals = null;
}));
//#endregion
//#region node_modules/svelte/src/internal/client/runtime.js
/** @param {boolean} value */
function set_is_destroying_effect(value) {
	is_destroying_effect = value;
}
/** @param {null | Reaction} reaction */
function set_active_reaction(reaction) {
	active_reaction = reaction;
}
/** @param {null | Effect} effect */
function set_active_effect(effect) {
	active_effect = effect;
}
/** @param {Value} value */
function push_reaction_value(value) {
	if (active_reaction !== null && (!async_mode_flag && (active_reaction.f & 2097152) !== 0 || (active_reaction.f & 2) !== 0)) (current_sources ??= /* @__PURE__ */ new Set()).add(value);
}
/** @param {null | Source[]} value */
function set_untracked_writes(value) {
	untracked_writes = value;
}
/** @param {number} value */
function set_update_version(value) {
	update_version = value;
}
function increment_write_version() {
	return ++write_version;
}
/**
* Determines whether a derived or effect is dirty.
* If it is MAYBE_DIRTY, will set the status to CLEAN
* @param {Reaction} reaction
* @returns {boolean}
*/
function is_dirty(reaction) {
	var flags = reaction.f;
	if ((flags & 2048) !== 0) return true;
	if ((flags & 4096) !== 0) {
		var dependencies = reaction.deps;
		var length = dependencies.length;
		for (var i = 0; i < length; i++) {
			var dependency = dependencies[i];
			if (is_dirty(dependency)) update_derived(dependency);
			if (dependency.wv > reaction.wv) return true;
		}
		if ((flags & 512) !== 0 && batch_values === null) set_signal_status(reaction, CLEAN);
	}
	return false;
}
/**
* @param {Value} signal
* @param {Effect} effect
* @param {boolean} [root]
*/
function schedule_possible_effect_self_invalidation(signal, effect, root = true) {
	var reactions = signal.reactions;
	if (reactions === null) return;
	if (!async_mode_flag && current_sources !== null && current_sources.has(signal)) return;
	for (var i = 0; i < reactions.length; i++) {
		var reaction = reactions[i];
		if ((reaction.f & 2) !== 0) schedule_possible_effect_self_invalidation(reaction, effect, false);
		else if (effect === reaction) {
			if (root) set_signal_status(reaction, DIRTY);
			else if ((reaction.f & 1024) !== 0) set_signal_status(reaction, MAYBE_DIRTY);
			schedule_effect(reaction);
		}
	}
}
/** @param {Reaction} reaction */
function update_reaction(reaction) {
	var previous_deps = new_deps;
	var previous_skipped_deps = skipped_deps;
	var previous_untracked_writes = untracked_writes;
	var previous_reaction = active_reaction;
	var previous_sources = current_sources;
	var previous_component_context = component_context;
	var previous_untracking = untracking;
	var previous_update_version = update_version;
	var flags = reaction.f;
	new_deps = null;
	skipped_deps = 0;
	untracked_writes = null;
	active_reaction = (flags & 96) === 0 ? reaction : null;
	current_sources = null;
	set_component_context(reaction.ctx);
	untracking = false;
	update_version = ++read_version;
	if (reaction.ac !== null) {
		without_reactive_context(() => {
			/** @type {AbortController} */ reaction.ac.abort(STALE_REACTION);
		});
		reaction.ac = null;
	}
	try {
		reaction.f |= REACTION_IS_UPDATING;
		var fn = reaction.fn;
		var result = fn();
		reaction.f |= REACTION_RAN;
		var deps = update_dependencies(reaction);
		if (is_runes() && untracked_writes !== null && !untracking && deps !== null && (reaction.f & 6146) === 0) for (var i = 0; i < untracked_writes.length; i++) schedule_possible_effect_self_invalidation(untracked_writes[i], reaction);
		if (previous_reaction !== null && previous_reaction !== reaction) {
			read_version++;
			if (previous_reaction.deps !== null) for (let i = 0; i < previous_skipped_deps; i += 1) previous_reaction.deps[i].rv = read_version;
			if (previous_deps !== null) for (const dep of previous_deps) dep.rv = read_version;
			if (untracked_writes !== null) {
				if (previous_untracked_writes === null) previous_untracked_writes = untracked_writes;
				else previous_untracked_writes.push(...untracked_writes);
			}
		}
		if ((reaction.f & 8388608) !== 0) reaction.f ^= ERROR_VALUE;
		return result;
	} catch (error) {
		update_dependencies(reaction);
		return handle_error(error);
	} finally {
		reaction.f ^= REACTION_IS_UPDATING;
		new_deps = previous_deps;
		skipped_deps = previous_skipped_deps;
		untracked_writes = previous_untracked_writes;
		active_reaction = previous_reaction;
		current_sources = previous_sources;
		set_component_context(previous_component_context);
		untracking = previous_untracking;
		update_version = previous_update_version;
	}
}
/**
* @param {Reaction} reaction
*/
function update_dependencies(reaction) {
	var deps = reaction.deps;
	var is_fork = current_batch?.is_fork;
	if (new_deps !== null) {
		var i;
		if (!is_fork) remove_reactions(reaction, skipped_deps);
		if (deps !== null && skipped_deps > 0) {
			deps.length = skipped_deps + new_deps.length;
			for (i = 0; i < new_deps.length; i++) deps[skipped_deps + i] = new_deps[i];
		} else reaction.deps = deps = new_deps;
		if (effect_tracking() && (reaction.f & 512) !== 0) for (i = skipped_deps; i < deps.length; i++) (deps[i].reactions ??= []).push(reaction);
	} else if (!is_fork && deps !== null && skipped_deps < deps.length) {
		remove_reactions(reaction, skipped_deps);
		deps.length = skipped_deps;
	}
	return deps;
}
/**
* @template V
* @param {Reaction} signal
* @param {Value<V>} dependency
* @returns {void}
*/
function remove_reaction(signal, dependency) {
	let reactions = dependency.reactions;
	if (reactions !== null) {
		var index = index_of.call(reactions, signal);
		if (index !== -1) {
			var new_length = reactions.length - 1;
			if (new_length === 0) reactions = dependency.reactions = null;
			else {
				reactions[index] = reactions[new_length];
				reactions.pop();
			}
		}
	}
	if (reactions === null && (dependency.f & 2) !== 0 && (new_deps === null || !includes.call(new_deps, dependency))) {
		var derived = dependency;
		if ((derived.f & 512) !== 0) derived.f ^= 512;
		if (derived.v !== UNINITIALIZED) update_derived_status(derived);
		if (derived.ac !== null) without_reactive_context(() => {
			/** @type {AbortController} */ derived.ac.abort(STALE_REACTION);
			derived.ac = null;
			set_signal_status(derived, DIRTY);
		});
		freeze_derived_effects(derived);
		remove_reactions(derived, 0);
	}
}
/**
* @param {Reaction} signal
* @param {number} start_index
* @returns {void}
*/
function remove_reactions(signal, start_index) {
	var dependencies = signal.deps;
	if (dependencies === null) return;
	for (var i = start_index; i < dependencies.length; i++) remove_reaction(signal, dependencies[i]);
}
/**
* @param {Effect} effect
* @returns {void}
*/
function update_effect(effect) {
	var flags = effect.f;
	if ((flags & 16384) !== 0) return;
	set_signal_status(effect, CLEAN);
	var previous_effect = active_effect;
	var was_updating_effect = is_updating_effect;
	active_effect = effect;
	is_updating_effect = (flags & 96) === 0;
	try {
		if ((flags & 16777232) !== 0) destroy_block_effect_children(effect);
		else destroy_effect_children(effect);
		execute_effect_teardown(effect);
		var teardown = update_reaction(effect);
		effect.teardown = typeof teardown === "function" ? teardown : null;
		effect.wv = write_version;
	} finally {
		is_updating_effect = was_updating_effect;
		active_effect = previous_effect;
	}
}
/**
* @template V
* @param {Value<V>} signal
* @returns {V}
*/
function get(signal) {
	var is_derived = (signal.f & 2) !== 0;
	captured_signals?.add(signal);
	if (active_reaction !== null && !untracking) {
		if (!(active_effect !== null && (active_effect.f & 16384) !== 0) && (current_sources === null || !current_sources.has(signal))) {
			var deps = active_reaction.deps;
			if ((active_reaction.f & 2097152) !== 0) {
				if (signal.rv < read_version) {
					signal.rv = read_version;
					if (new_deps === null && deps !== null && deps[skipped_deps] === signal) skipped_deps++;
					else if (new_deps === null) new_deps = [signal];
					else new_deps.push(signal);
				}
			} else {
				active_reaction.deps ??= [];
				if (!includes.call(active_reaction.deps, signal)) active_reaction.deps.push(signal);
				var reactions = signal.reactions;
				if (reactions === null) signal.reactions = [active_reaction];
				else if (!includes.call(reactions, active_reaction)) reactions.push(active_reaction);
			}
		}
	}
	if (is_destroying_effect && old_values.has(signal)) return old_values.get(signal);
	if (is_derived) {
		var derived = signal;
		if (is_destroying_effect) {
			var value = derived.v;
			if ((derived.f & 1024) === 0 && derived.reactions !== null || depends_on_old_values(derived)) value = execute_derived(derived);
			old_values.set(derived, value);
			return value;
		}
		var should_connect = (derived.f & 512) === 0 && !untracking && active_reaction !== null && (is_updating_effect || (active_reaction.f & 512) !== 0);
		var is_new = (derived.f & REACTION_RAN) === 0;
		if (is_dirty(derived)) {
			if (should_connect) derived.f |= 512;
			update_derived(derived);
		}
		if (should_connect && !is_new) {
			unfreeze_derived_effects(derived);
			reconnect(derived);
		}
	}
	if (batch_values?.has(signal)) return batch_values.get(signal);
	if ((signal.f & 8388608) !== 0) throw signal.v;
	return signal.v;
}
/**
* (Re)connect a disconnected derived, so that it is notified
* of changes in `mark_reactions`
* @param {Derived} derived
*/
function reconnect(derived) {
	derived.f |= 512;
	if (derived.deps === null) return;
	for (const dep of derived.deps) {
		(dep.reactions ??= []).push(derived);
		if ((dep.f & 2) !== 0 && (dep.f & 512) === 0) {
			unfreeze_derived_effects(dep);
			reconnect(dep);
		}
	}
}
/** @param {Derived} derived */
function depends_on_old_values(derived) {
	if (derived.v === UNINITIALIZED) return true;
	if (derived.deps === null) return false;
	for (const dep of derived.deps) {
		if (old_values.has(dep)) return true;
		if ((dep.f & 2) !== 0 && depends_on_old_values(dep)) return true;
	}
	return false;
}
/**
* When used inside a [`$derived`](https://svelte.dev/docs/svelte/$derived) or [`$effect`](https://svelte.dev/docs/svelte/$effect),
* any state read inside `fn` will not be treated as a dependency.
*
* ```ts
* $effect(() => {
*   // this will run when `data` changes, but not when `time` changes
*   save(data, {
*     timestamp: untrack(() => time)
*   });
* });
* ```
* @template T
* @param {() => T} fn
* @returns {T}
*/
function untrack(fn) {
	var previous_untracking = untracking;
	try {
		untracking = true;
		return fn();
	} finally {
		untracking = previous_untracking;
	}
}
var is_updating_effect, is_destroying_effect, active_reaction, untracking, active_effect, current_sources, new_deps, skipped_deps, untracked_writes, write_version, read_version, update_version;
var init_runtime = __esmMin((() => {
	init_esm_env();
	init_utils$3();
	init_effects();
	init_constants$1();
	init_sources();
	init_deriveds();
	init_flags();
	init_tracing();
	init_dev();
	init_context();
	init_batch();
	init_error_handling();
	init_constants();
	init_legacy$1();
	init_shared$1();
	init_status();
	init_warnings();
	is_updating_effect = false;
	is_destroying_effect = false;
	active_reaction = null;
	untracking = false;
	active_effect = null;
	current_sources = null;
	new_deps = null;
	skipped_deps = 0;
	untracked_writes = null;
	write_version = 1;
	read_version = 0;
	update_version = read_version;
}));
//#endregion
//#region node_modules/svelte/src/attachments/index.js
var init_attachments$1 = __esmMin((() => {
	init_client();
	init_index_client();
	init_effects();
}));
//#endregion
//#region node_modules/svelte/src/utils.js
/**
* Returns `true` if `name` is a passive event
* @param {string} name
*/
function is_passive_event(name) {
	return PASSIVE_EVENTS.includes(name);
}
var DOM_BOOLEAN_ATTRIBUTES, PASSIVE_EVENTS, STATE_CREATION_RUNES;
var init_utils$1 = __esmMin((() => {
	DOM_BOOLEAN_ATTRIBUTES = [
		"allowfullscreen",
		"async",
		"autofocus",
		"autoplay",
		"checked",
		"controls",
		"default",
		"disabled",
		"formnovalidate",
		"indeterminate",
		"inert",
		"ismap",
		"loop",
		"multiple",
		"muted",
		"nomodule",
		"novalidate",
		"open",
		"playsinline",
		"readonly",
		"required",
		"reversed",
		"seamless",
		"selected",
		"webkitdirectory",
		"defer",
		"disablepictureinpicture",
		"disableremoteplayback"
	];
	[...DOM_BOOLEAN_ATTRIBUTES];
	PASSIVE_EVENTS = ["touchstart", "touchmove"];
	STATE_CREATION_RUNES = [
		"$state",
		"$state.raw",
		"$derived",
		"$derived.by"
	];
	[...STATE_CREATION_RUNES];
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dev/assign.js
var init_assign = __esmMin((() => {
	init_constants$1();
	init_utils$1();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dev/elements.js
var init_elements = __esmMin((() => {
	init_constants$1();
	init_hydration();
	init_context();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/events.js
/**
* @param {string} event_name
* @param {Element} element
* @param {EventListener} [handler]
* @returns {void}
*/
function delegated(event_name, element, handler) {
	(element[event_symbol] ??= {})[event_name] = handler;
}
/**
* @param {Array<string>} events
* @returns {void}
*/
function delegate(events) {
	for (var i = 0; i < events.length; i++) all_registered_events.add(events[i]);
	for (var fn of root_event_handles) fn(events);
}
/**
* @this {EventTarget}
* @param {Event} event
* @returns {void}
*/
function handle_event_propagation(event) {
	var handler_element = this;
	var owner_document = handler_element.ownerDocument;
	var event_name = event.type;
	var path = event.composedPath?.() || [];
	var current_target = path[0] || event.target;
	last_propagated_event = event;
	if (!last_propagated_event_clear_scheduled) {
		last_propagated_event_clear_scheduled = true;
		setTimeout(() => {
			last_propagated_event_clear_scheduled = false;
			last_propagated_event = null;
		});
	}
	var path_idx = 0;
	var handled_at = last_propagated_event === event && event[event_symbol];
	if (handled_at) {
		var at_idx = path.indexOf(handled_at);
		if (at_idx !== -1 && (handler_element === document || handler_element === window)) {
			event[event_symbol] = handler_element;
			return;
		}
		var handler_idx = path.indexOf(handler_element);
		if (handler_idx === -1) return;
		if (at_idx <= handler_idx) path_idx = at_idx;
	}
	current_target = path[path_idx] || event.target;
	if (current_target === handler_element) return;
	define_property(event, "currentTarget", {
		configurable: true,
		get() {
			return current_target || owner_document;
		}
	});
	var previous_reaction = active_reaction;
	var previous_effect = active_effect;
	set_active_reaction(null);
	set_active_effect(null);
	try {
		/**
		* @type {unknown}
		*/
		var throw_error;
		/**
		* @type {unknown[]}
		*/
		var other_errors = [];
		while (current_target !== null) {
			if (current_target === handler_element) break;
			try {
				var delegated = current_target[event_symbol]?.[event_name];
				if (delegated != null && (!current_target.disabled || event.target === current_target)) delegated.call(current_target, event);
			} catch (error) {
				if (throw_error) other_errors.push(error);
				else throw_error = error;
			}
			if (event.cancelBubble) break;
			path_idx++;
			current_target = path_idx < path.length ? path[path_idx] : null;
		}
		if (throw_error) {
			for (let error of other_errors) queueMicrotask(() => {
				throw error;
			});
			throw throw_error;
		}
	} finally {
		event[event_symbol] = handler_element;
		delete event.currentTarget;
		set_active_reaction(previous_reaction);
		set_active_effect(previous_effect);
	}
}
var event_symbol, all_registered_events, root_event_handles, last_propagated_event, last_propagated_event_clear_scheduled;
var init_events = __esmMin((() => {
	init_effects();
	init_utils$3();
	init_hydration();
	init_task();
	init_runtime();
	init_shared$1();
	event_symbol = Symbol("events");
	all_registered_events = /* @__PURE__ */ new Set();
	root_event_handles = /* @__PURE__ */ new Set();
	last_propagated_event = null;
	last_propagated_event_clear_scheduled = false;
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/reconciler.js
/** @param {string} html */
function create_trusted_html(html) {
	return policy?.createHTML(html) ?? html;
}
/**
* @param {string} html
*/
function create_fragment_from_html(html) {
	var elem = create_element("template");
	elem.innerHTML = create_trusted_html(html.replaceAll("<!>", "<!---->"));
	return elem.content;
}
var policy;
var init_reconciler = __esmMin((() => {
	init_operations$1();
	policy = globalThis?.window?.trustedTypes && /* @__PURE__ */ globalThis.window.trustedTypes.createPolicy("svelte-trusted-html", { 
	/** @param {string} html */
createHTML: (html) => {
		return html;
	} });
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/template.js
/**
* @param {TemplateNode} start
* @param {TemplateNode | null} end
*/
function assign_nodes(start, end) {
	var effect = active_effect;
	if (effect.nodes === null) effect.nodes = {
		start,
		end,
		a: null,
		t: null
	};
}
/**
* @param {string} content
* @param {number} flags
* @returns {() => Node | Node[]}
*/
/*#__NO_SIDE_EFFECTS__*/
function from_html(content, flags) {
	var is_fragment = (flags & 1) !== 0;
	var use_import_node = (flags & 2) !== 0;
	/** @type {Node} */
	var node;
	/**
	* Whether or not the first item is a text/element node. If not, we need to
	* create an additional comment node to act as `effect.nodes.start`
	*/
	var has_start = !content.startsWith("<!>");
	return () => {
		if (hydrating) {
			assign_nodes(hydrate_node, null);
			return hydrate_node;
		}
		if (node === void 0) {
			node = create_fragment_from_html(has_start ? content : "<!>" + content);
			if (!is_fragment) node = /* @__PURE__ */ get_first_child(node);
		}
		var clone = use_import_node || is_firefox ? document.importNode(node, true) : node.cloneNode(true);
		if (is_fragment) {
			var start = /* @__PURE__ */ get_first_child(clone);
			var end = clone.lastChild;
			assign_nodes(start, end);
		} else assign_nodes(clone, clone);
		return clone;
	};
}
/**
* Don't mark this as side-effect-free, hydration needs to walk all nodes
* @param {any} value
*/
function text(value = "") {
	if (!hydrating) {
		var t = create_text(value + "");
		assign_nodes(t, t);
		return t;
	}
	var node = hydrate_node;
	if (node.nodeType !== 3) {
		node.before(node = create_text());
		set_hydrate_node(node);
	} else merge_text_nodes(node);
	assign_nodes(node, node);
	return node;
}
/**
* @returns {TemplateNode | DocumentFragment}
*/
function comment() {
	if (hydrating) {
		assign_nodes(hydrate_node, null);
		return hydrate_node;
	}
	var frag = document.createDocumentFragment();
	var start = document.createComment("");
	var anchor = create_text();
	frag.append(start, anchor);
	assign_nodes(start, anchor);
	return frag;
}
/**
* Assign the created (or in hydration mode, traversed) dom elements to the current block
* and insert the elements into the dom (in client mode).
* @param {Text | Comment | Element} anchor
* @param {DocumentFragment | Element} dom
*/
function append(anchor, dom) {
	if (hydrating) {
		var effect = active_effect;
		if ((effect.f & 32768) === 0 || effect.nodes.end === null) effect.nodes.end = hydrate_node;
		hydrate_next();
		return;
	}
	if (anchor === null) return;
	anchor.before(dom);
}
var init_template = __esmMin((() => {
	init_hydration();
	init_operations$1();
	init_reconciler();
	init_runtime();
	init_constants();
	init_constants$1();
}));
//#endregion
//#region node_modules/svelte/src/reactivity/create-subscriber.js
/**
* Returns a `subscribe` function that integrates external event-based systems with Svelte's reactivity.
* It's particularly useful for integrating with web APIs like `MediaQuery`, `IntersectionObserver`, or `WebSocket`.
*
* If `subscribe` is called inside an effect (including indirectly, for example inside a getter),
* the `start` callback will be called with an `update` function. Whenever `update` is called, the effect re-runs.
*
* If `start` returns a cleanup function, it will be called when the effect is destroyed.
*
* If `subscribe` is called in multiple effects, `start` will only be called once as long as the effects
* are active, and the returned teardown function will only be called when all effects are destroyed.
*
* It's best understood with an example. Here's an implementation of [`MediaQuery`](https://svelte.dev/docs/svelte/svelte-reactivity#MediaQuery):
*
* ```js
* import { createSubscriber } from 'svelte/reactivity';
* import { on } from 'svelte/events';
*
* export class MediaQuery {
* 	#query;
* 	#subscribe;
*
* 	constructor(query) {
* 		this.#query = window.matchMedia(`(${query})`);
*
* 		this.#subscribe = createSubscriber((update) => {
* 			// when the `change` event occurs, re-run any effects that read `this.current`
* 			const off = on(this.#query, 'change', update);
*
* 			// stop listening when all the effects are destroyed
* 			return () => off();
* 		});
* 	}
*
* 	get current() {
* 		// This makes the getter reactive, if read in an effect
* 		this.#subscribe();
*
* 		// Return the current state of the query, whether or not we're in an effect
* 		return this.#query.matches;
* 	}
* }
* ```
* @param {(update: () => void) => (() => void) | void} start
* @since 5.7.0
*/
function createSubscriber(start) {
	let subscribers = 0;
	let version = source(0);
	/** @type {(() => void) | void} */
	let stop;
	return () => {
		if (effect_tracking()) {
			get(version);
			render_effect(() => {
				if (subscribers === 0) stop = untrack(() => start(() => increment(version)));
				subscribers += 1;
				return () => {
					queue_micro_task(() => {
						subscribers -= 1;
						if (subscribers === 0) {
							stop?.();
							stop = void 0;
							increment(version);
						}
					});
				};
			});
		}
	};
}
var init_create_subscriber = __esmMin((() => {
	init_runtime();
	init_effects();
	init_sources();
	init_tracing();
	init_esm_env();
	init_task();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/boundary.js
/**
* @param {TemplateNode} node
* @param {BoundaryProps} props
* @param {((anchor: Node) => void)} children
* @param {((error: unknown) => unknown) | undefined} [transform_error]
* @returns {void}
*/
function boundary(node, props, children, transform_error) {
	new Boundary(node, props, children, transform_error);
}
var flags, Boundary;
var init_boundary = __esmMin((() => {
	init_constants$1();
	init_constants();
	init_context();
	init_error_handling();
	init_effects();
	init_runtime();
	init_hydration();
	init_task();
	init_errors();
	init_warnings();
	init_esm_env();
	init_batch();
	init_sources();
	init_tracing();
	init_create_subscriber();
	init_operations$1();
	init_utils$2();
	flags = EFFECT_TRANSPARENT | EFFECT_PRESERVED;
	Boundary = class {
		/** @type {Boundary | null} */
		parent;
		is_pending = false;
		/**
		* API-level transformError transform function. Transforms errors before they reach the `failed` snippet.
		* Inherited from parent boundary, or defaults to identity.
		* @type {(error: unknown) => unknown}
		*/
		transform_error;
		/** @type {TemplateNode} */
		#anchor;
		/** @type {TemplateNode | null} */
		#hydrate_open = hydrating ? hydrate_node : null;
		/** @type {BoundaryProps} */
		#props;
		/** @type {((anchor: Node) => void)} */
		#children;
		/** @type {Effect} */
		#effect;
		/** @type {Effect | null} */
		#main_effect = null;
		/** @type {Effect | null} */
		#pending_effect = null;
		/** @type {Effect | null} */
		#failed_effect = null;
		/** @type {DocumentFragment | null} */
		#offscreen_fragment = null;
		#local_pending_count = 0;
		#pending_count = 0;
		#pending_count_update_queued = false;
		/** @type {Set<Effect>} */
		#dirty_effects = /* @__PURE__ */ new Set();
		/** @type {Set<Effect>} */
		#maybe_dirty_effects = /* @__PURE__ */ new Set();
		/**
		* A source containing the number of pending async deriveds/expressions.
		* Only created if `$effect.pending()` is used inside the boundary,
		* otherwise updating the source results in needless `Batch.ensure()`
		* calls followed by no-op flushes
		* @type {Source<number> | null}
		*/
		#effect_pending = null;
		#effect_pending_subscriber = createSubscriber(() => {
			this.#effect_pending = source(this.#local_pending_count);
			return () => {
				this.#effect_pending = null;
			};
		});
		/**
		* @param {TemplateNode} node
		* @param {BoundaryProps} props
		* @param {((anchor: Node) => void)} children
		* @param {((error: unknown) => unknown) | undefined} [transform_error]
		*/
		constructor(node, props, children, transform_error) {
			this.#anchor = node;
			this.#props = props;
			this.#children = (anchor) => {
				var effect = active_effect;
				effect.b = this;
				effect.f |= 128;
				children(anchor);
			};
			this.parent = active_effect.b;
			this.transform_error = transform_error ?? this.parent?.transform_error ?? ((e) => e);
			this.#effect = block(() => {
				if (hydrating) {
					const comment = this.#hydrate_open;
					hydrate_next();
					const server_rendered_pending = comment.data === "[!";
					if (comment.data.startsWith("[?")) {
						const serialized_error = JSON.parse(comment.data.slice(2));
						this.#hydrate_failed_content(serialized_error);
					} else if (server_rendered_pending) this.#hydrate_pending_content();
					else this.#hydrate_resolved_content();
				} else this.#render();
			}, flags);
			if (hydrating) this.#anchor = hydrate_node;
		}
		#hydrate_resolved_content() {
			try {
				this.#main_effect = branch(() => this.#children(this.#anchor));
			} catch (error) {
				this.error(error);
			}
		}
		/**
		* @param {unknown} error The deserialized error from the server's hydration comment
		*/
		#hydrate_failed_content(error) {
			const failed = this.#props.failed;
			const { reset, invoke_onerror } = this.#create_reset(error);
			queue_micro_task(invoke_onerror);
			if (!failed) return;
			this.#failed_effect = branch(() => {
				failed(this.#anchor, () => error, () => reset);
			});
		}
		/**
		* Creates the `reset` function for a failed boundary, along with a function
		* that invokes `onerror` with it (if provided)
		* @param {unknown} error
		* @returns {{ reset: () => void, invoke_onerror: () => void }}
		*/
		#create_reset(error) {
			var did_reset = false;
			var calling_on_error = false;
			const reset = () => {
				if (did_reset) {
					svelte_boundary_reset_noop();
					return;
				}
				did_reset = true;
				if (calling_on_error) svelte_boundary_reset_onerror();
				if (this.#failed_effect !== null) pause_effect(this.#failed_effect, () => {
					this.#failed_effect = null;
				});
				this.#run(() => {
					this.#render();
				});
			};
			const invoke_onerror = () => {
				try {
					calling_on_error = true;
					this.#props.onerror?.(error, reset);
					calling_on_error = false;
				} catch (err) {
					invoke_error_boundary(err, this.#effect && this.#effect.parent);
				}
			};
			return {
				reset,
				invoke_onerror
			};
		}
		#hydrate_pending_content() {
			const pending = this.#props.pending;
			if (!pending) return;
			this.is_pending = true;
			this.#pending_effect = branch(() => pending(this.#anchor));
			queue_micro_task(() => {
				var fragment = this.#offscreen_fragment = document.createDocumentFragment();
				var anchor = create_text();
				var handled = false;
				fragment.append(anchor);
				this.#main_effect = this.#run(() => {
					try {
						return branch(() => this.#children(anchor));
					} catch (error) {
						try {
							this.error(error);
							handled = true;
						} catch (error) {
							invoke_error_boundary(error, this.#effect.parent);
						}
						return null;
					}
				});
				if (this.#main_effect === null) {
					this.#offscreen_fragment = null;
					if (handled) this.#resolve(current_batch);
					return;
				}
				if (this.#pending_count === 0) {
					this.#anchor.before(fragment);
					this.#offscreen_fragment = null;
					pause_effect(this.#pending_effect, () => {
						this.#pending_effect = null;
					});
					this.#resolve(current_batch);
				}
			});
		}
		#render() {
			try {
				this.is_pending = this.has_pending_snippet();
				this.#pending_count = 0;
				this.#local_pending_count = 0;
				this.#main_effect = branch(() => {
					this.#children(this.#anchor);
				});
				if (this.#pending_count > 0) {
					var fragment = this.#offscreen_fragment = document.createDocumentFragment();
					move_effect(this.#main_effect, fragment);
					const pending = this.#props.pending;
					this.#pending_effect = branch(() => pending(this.#anchor));
				} else this.#resolve(current_batch);
			} catch (error) {
				this.error(error);
			}
		}
		/**
		* @param {Batch} batch
		*/
		#resolve(batch) {
			this.is_pending = false;
			batch.transfer_effects(this.#dirty_effects, this.#maybe_dirty_effects);
		}
		/**
		* Defer an effect inside a pending boundary until the boundary resolves
		* @param {Effect} effect
		*/
		defer_effect(effect) {
			defer_effect(effect, this.#dirty_effects, this.#maybe_dirty_effects);
		}
		/**
		* Returns `false` if the effect exists inside a boundary whose pending snippet is shown
		* @returns {boolean}
		*/
		is_rendered() {
			return !this.is_pending && (!this.parent || this.parent.is_rendered());
		}
		has_pending_snippet() {
			return !!this.#props.pending;
		}
		/**
		* @template T
		* @param {() => T} fn
		*/
		#run(fn) {
			var previous_effect = active_effect;
			var previous_reaction = active_reaction;
			var previous_ctx = component_context;
			set_active_effect(this.#effect);
			set_active_reaction(this.#effect);
			set_component_context(this.#effect.ctx);
			try {
				Batch.ensure();
				return fn();
			} finally {
				set_active_effect(previous_effect);
				set_active_reaction(previous_reaction);
				set_component_context(previous_ctx);
			}
		}
		/**
		* Updates the pending count associated with the currently visible pending snippet,
		* if any, such that we can replace the snippet with content once work is done
		* @param {1 | -1} d
		* @param {Batch} batch
		*/
		#update_pending_count(d, batch) {
			if (!this.has_pending_snippet()) {
				if (this.parent) this.parent.#update_pending_count(d, batch);
				return;
			}
			this.#pending_count += d;
			if (this.#pending_count === 0) {
				this.#resolve(batch);
				if (this.#pending_effect) pause_effect(this.#pending_effect, () => {
					this.#pending_effect = null;
				});
				if (this.#offscreen_fragment) {
					this.#anchor.before(this.#offscreen_fragment);
					this.#offscreen_fragment = null;
				}
			}
		}
		/**
		* Update the source that powers `$effect.pending()` inside this boundary,
		* and controls when the current `pending` snippet (if any) is removed.
		* Do not call from inside the class
		* @param {1 | -1} d
		* @param {Batch} batch
		*/
		update_pending_count(d, batch) {
			this.#update_pending_count(d, batch);
			this.#local_pending_count += d;
			if (!this.#effect_pending || this.#pending_count_update_queued) return;
			this.#pending_count_update_queued = true;
			queue_micro_task(() => {
				this.#pending_count_update_queued = false;
				if (this.#effect_pending) internal_set(this.#effect_pending, this.#local_pending_count);
			});
		}
		get_effect_pending() {
			this.#effect_pending_subscriber();
			return get(this.#effect_pending);
		}
		/** @param {unknown} error */
		error(error) {
			if (!this.#props.onerror && !this.#props.failed) throw error;
			if (current_batch?.is_fork) {
				if (this.#main_effect) current_batch.skip_effect(this.#main_effect);
				if (this.#pending_effect) current_batch.skip_effect(this.#pending_effect);
				if (this.#failed_effect) current_batch.skip_effect(this.#failed_effect);
				current_batch.oncommit(() => {
					this.#handle_error(error);
				});
			} else this.#handle_error(error);
		}
		/**
		* @param {unknown} error
		*/
		#handle_error(error) {
			if (this.#main_effect) {
				destroy_effect(this.#main_effect);
				this.#main_effect = null;
			}
			if (this.#pending_effect) {
				destroy_effect(this.#pending_effect);
				this.#pending_effect = null;
			}
			if (this.#failed_effect) {
				destroy_effect(this.#failed_effect);
				this.#failed_effect = null;
			}
			if (hydrating) {
				set_hydrate_node(this.#hydrate_open);
				next();
				set_hydrate_node(skip_nodes());
			}
			let failed = this.#props.failed;
			/** @param {unknown} transformed_error */
			const handle_error_result = (transformed_error) => {
				const { reset, invoke_onerror } = this.#create_reset(transformed_error);
				invoke_onerror();
				if (failed) this.#failed_effect = this.#run(() => {
					try {
						return branch(() => {
							var effect = active_effect;
							effect.b = this;
							effect.f |= 128;
							failed(this.#anchor, () => transformed_error, () => reset);
						});
					} catch (error) {
						invoke_error_boundary(error, this.#effect.parent);
						return null;
					}
				});
			};
			queue_micro_task(() => {
				/** @type {unknown} */
				var result;
				try {
					result = this.transform_error(error);
				} catch (e) {
					invoke_error_boundary(e, this.#effect && this.#effect.parent);
					return;
				}
				if (result !== null && typeof result === "object" && typeof result.then === "function")
 /** @type {any} */ result.then(
					handle_error_result,
					/** @param {unknown} e */
					(e) => invoke_error_boundary(e, this.#effect && this.#effect.parent)
				);
				else handle_error_result(result);
			});
		}
	};
}));
//#endregion
//#region node_modules/svelte/src/internal/client/render.js
/**
* @param {Element} text
* @param {string} value
* @returns {void}
*/
function set_text(text, value) {
	var str = value == null ? "" : typeof value === "object" ? `${value}` : value;
	if (str !== (text[TEXT_CACHE] ??= text.nodeValue)) {
		/** @type {any} */ text[TEXT_CACHE] = str;
		text.nodeValue = `${str}`;
	}
}
/**
* Mounts a component to the given target and returns the exports and potentially the props (if compiled with `accessors: true`) of the component.
* Transitions will play during the initial render unless the `intro` option is set to `false`.
*
* @template {Record<string, any>} Props
* @template {Record<string, any>} Exports
* @param {ComponentType<SvelteComponent<Props>> | Component<Props, Exports, any>} component
* @param {MountOptions<Props>} options
* @returns {Exports}
*/
function mount(component, options) {
	return _mount(component, options);
}
/**
* @template {Record<string, any>} Exports
* @param {ComponentType<SvelteComponent<any>> | Component<any>} Component
* @param {MountOptions} options
* @returns {Exports}
*/
function _mount(Component, { target, anchor, props = {}, events, context, intro = true, transformError }) {
	init_operations();
	/** @type {Exports} */
	var component = void 0;
	var unmount = component_root(() => {
		var anchor_node = anchor ?? target.appendChild(create_text());
		boundary(anchor_node, { pending: () => {} }, (anchor_node) => {
			push({});
			var ctx = component_context;
			if (context) ctx.c = context;
			if (events)
 /** @type {any} */ props.$$events = events;
			if (hydrating) assign_nodes(anchor_node, null);
			should_intro = intro;
			component = Component(anchor_node, props) || mark_as_component();
			should_intro = true;
			if (hydrating) {
				/** @type {Effect & { nodes: EffectNodes }} */ active_effect.nodes.end = hydrate_node;
				if (hydrate_node === null || hydrate_node.nodeType !== 8 || hydrate_node.data !== "]") {
					hydration_mismatch();
					throw HYDRATION_ERROR;
				}
			}
			pop();
		}, transformError);
		/** @type {Set<string>} */
		var registered_events = /* @__PURE__ */ new Set();
		/** @param {Array<string>} events */
		var event_handle = (events) => {
			for (var i = 0; i < events.length; i++) {
				var event_name = events[i];
				if (registered_events.has(event_name)) continue;
				registered_events.add(event_name);
				var passive = is_passive_event(event_name);
				for (const node of [target, document]) {
					var counts = listeners.get(node);
					if (counts === void 0) {
						counts = /* @__PURE__ */ new Map();
						listeners.set(node, counts);
					}
					var count = counts.get(event_name);
					if (count === void 0) {
						node.addEventListener(event_name, handle_event_propagation, { passive });
						counts.set(event_name, 1);
					} else counts.set(event_name, count + 1);
				}
			}
		};
		event_handle(array_from(all_registered_events));
		root_event_handles.add(event_handle);
		return () => {
			for (var event_name of registered_events) for (const node of [target, document]) {
				var counts = listeners.get(node);
				var count = counts.get(event_name);
				if (--count == 0) {
					node.removeEventListener(event_name, handle_event_propagation);
					counts.delete(event_name);
					if (counts.size === 0) listeners.delete(node);
				} else counts.set(event_name, count);
			}
			root_event_handles.delete(event_handle);
			if (anchor_node !== anchor) anchor_node.parentNode?.removeChild(anchor_node);
		};
	});
	mounted_components.set(component, unmount);
	return component;
}
var should_intro, listeners, mounted_components;
var init_render = __esmMin((() => {
	init_esm_env();
	init_operations$1();
	init_constants();
	init_runtime();
	init_context();
	init_effects();
	init_hydration();
	init_utils$3();
	init_events();
	init_warnings();
	init_errors();
	init_template();
	init_utils$1();
	init_constants$1();
	init_boundary();
	listeners = /* @__PURE__ */ new Map();
	mounted_components = /* @__PURE__ */ new WeakMap();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dev/hmr.js
var init_hmr = __esmMin((() => {
	init_constants$1();
	init_hydration();
	init_effects();
	init_sources();
	init_render();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dev/ownership.js
var init_ownership = __esmMin((() => {
	init_utils$3();
	init_constants$1();
	init_context();
	init_utils$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dev/legacy.js
var init_legacy = __esmMin((() => {
	init_errors();
	init_context();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dev/inspect.js
var init_inspect = __esmMin((() => {
	init_clone();
	init_effects();
	init_runtime();
	init_dev();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/async.js
var init_async = __esmMin((() => {
	init_async$1();
	init_runtime();
	init_hydration();
	init_template();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dev/validation.js
var init_validation = __esmMin((() => {
	init_errors();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/branches.js
var BranchManager;
var init_branches = __esmMin((() => {
	init_batch();
	init_effects();
	init_constants$1();
	init_hydration();
	init_operations$1();
	init_esm_env();
	BranchManager = class {
		/** @type {TemplateNode} */
		anchor;
		/** @type {Map<Batch, Key>} */
		#batches = /* @__PURE__ */ new Map();
		/**
		* Map of keys to effects that are currently rendered in the DOM.
		* These effects are visible and actively part of the document tree.
		* Example:
		* ```
		* {#if condition}
		* 	foo
		* {:else}
		* 	bar
		* {/if}
		* ```
		* Can result in the entries `true->Effect` and `false->Effect`
		* @type {Map<Key, Effect>}
		*/
		#onscreen = /* @__PURE__ */ new Map();
		/**
		* Similar to #onscreen with respect to the keys, but contains branches that are not yet
		* in the DOM, because their insertion is deferred.
		* @type {Map<Key, Branch>}
		*/
		#offscreen = /* @__PURE__ */ new Map();
		/**
		* Keys of effects that are currently outroing
		* @type {Set<Key>}
		*/
		#outroing = /* @__PURE__ */ new Set();
		/**
		* Whether to pause (i.e. outro) on change, or destroy immediately.
		* This is necessary for `<svelte:element>`
		*/
		#transition = true;
		/**
		* @param {TemplateNode} anchor
		* @param {boolean} transition
		*/
		constructor(anchor, transition = true) {
			this.anchor = anchor;
			this.#transition = transition;
		}
		/**
		* @param {Batch} batch
		*/
		#commit = (batch) => {
			if (!this.#batches.has(batch)) return;
			var key = this.#batches.get(batch);
			var onscreen = this.#onscreen.get(key);
			if (onscreen) {
				resume_effect(onscreen);
				this.#outroing.delete(key);
			} else {
				var offscreen = this.#offscreen.get(key);
				if (offscreen) {
					resume_effect(offscreen.effect);
					this.#onscreen.set(key, offscreen.effect);
					this.#offscreen.delete(key);
					/** @type {TemplateNode} */ offscreen.fragment.lastChild.remove();
					this.anchor.before(offscreen.fragment);
					onscreen = offscreen.effect;
				}
			}
			for (const [b, k] of this.#batches) {
				this.#batches.delete(b);
				if (b === batch) break;
				const offscreen = this.#offscreen.get(k);
				if (offscreen) {
					destroy_effect(offscreen.effect);
					this.#offscreen.delete(k);
				}
			}
			for (const [k, effect] of this.#onscreen) {
				if (k === key || this.#outroing.has(k)) continue;
				const on_destroy = () => {
					if (Array.from(this.#batches.values()).includes(k)) {
						var fragment = document.createDocumentFragment();
						move_effect(effect, fragment);
						fragment.append(create_text());
						this.#offscreen.set(k, {
							effect,
							fragment
						});
					} else destroy_effect(effect);
					this.#outroing.delete(k);
					this.#onscreen.delete(k);
				};
				if (this.#transition || !onscreen) {
					this.#outroing.add(k);
					pause_effect(effect, on_destroy, false);
				} else on_destroy();
			}
		};
		/**
		* @param {Batch} batch
		*/
		#discard = (batch) => {
			this.#batches.delete(batch);
			const keys = Array.from(this.#batches.values());
			for (const [k, branch] of this.#offscreen) if (!keys.includes(k)) {
				destroy_effect(branch.effect);
				this.#offscreen.delete(k);
			}
		};
		/**
		*
		* @param {any} key
		* @param {null | ((target: TemplateNode) => void)} fn
		*/
		ensure(key, fn) {
			var batch = current_batch;
			var defer = should_defer_append();
			if (fn && !this.#onscreen.has(key) && !this.#offscreen.has(key)) {
				if (defer) {
					var fragment = document.createDocumentFragment();
					var target = create_text();
					fragment.append(target);
					this.#offscreen.set(key, {
						effect: branch(() => fn(target)),
						fragment
					});
				} else this.#onscreen.set(key, branch(() => fn(this.anchor)));
			}
			this.#batches.set(batch, key);
			if (defer) {
				for (const [k, effect] of this.#onscreen) if (k === key) batch.unskip_effect(effect);
				else batch.skip_effect(effect);
				for (const [k, branch] of this.#offscreen) if (k === key) batch.unskip_effect(branch.effect);
				else batch.skip_effect(branch.effect);
				batch.oncommit(this.#commit);
				batch.ondiscard(this.#discard);
			} else {
				if (hydrating) this.anchor = hydrate_node;
				this.#commit(batch);
			}
		}
	};
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/await.js
var init_await = __esmMin((() => {
	init_utils$3();
	init_effects();
	init_sources();
	init_hydration();
	init_task();
	init_context();
	init_batch();
	init_branches();
	init_async$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/if.js
/**
* @param {TemplateNode} node
* @param {(branch: (fn: (anchor: Node) => void, key?: number | false) => void) => void} fn
* @param {boolean} [elseif] True if this is an `{:else if ...}` block rather than an `{#if ...}`, as that affects which transitions are considered 'local'
* @returns {void}
*/
function if_block(node, fn, elseif = false) {
	/** @type {TemplateNode | undefined} */
	var marker;
	if (hydrating) {
		marker = hydrate_node;
		hydrate_next();
	}
	var branches = new BranchManager(node);
	var flags = elseif ? EFFECT_TRANSPARENT : 0;
	/**
	* @param {number | false} key
	* @param {null | ((anchor: Node) => void)} fn
	*/
	function update_branch(key, fn) {
		if (hydrating) {
			var data = read_hydration_instruction(marker);
			if (key !== parseInt(data.substring(1))) {
				var anchor = skip_nodes();
				set_hydrate_node(anchor);
				branches.anchor = anchor;
				set_hydrating(false);
				branches.ensure(key, fn);
				set_hydrating(true);
				return;
			}
		}
		branches.ensure(key, fn);
	}
	block(() => {
		var has_branch = false;
		fn((fn, key = 0) => {
			has_branch = true;
			update_branch(key, fn);
		});
		if (!has_branch) update_branch(-1, null);
	}, flags);
}
var init_if = __esmMin((() => {
	init_constants$1();
	init_hydration();
	init_effects();
	init_branches();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/key.js
var init_key = __esmMin((() => {
	init_context();
	init_effects();
	init_hydration();
	init_branches();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/css-props.js
var init_css_props = __esmMin((() => {
	init_effects();
	init_hydration();
	init_operations$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/each.js
/**
* Pause multiple effects simultaneously, and coordinate their
* subsequent destruction. Used in each blocks
* @param {EachState} state
* @param {Effect[]} to_destroy
* @param {null | Node} controlled_anchor
*/
function pause_effects(state, to_destroy, controlled_anchor) {
	/** @type {TransitionManager[]} */
	var transitions = [];
	var length = to_destroy.length;
	/** @type {EachOutroGroup} */
	var group;
	var remaining = to_destroy.length;
	for (var i = 0; i < length; i++) {
		let effect = to_destroy[i];
		pause_effect(effect, () => {
			if (group) {
				group.pending.delete(effect);
				group.done.add(effect);
				if (group.pending.size === 0) {
					var groups = state.outrogroups;
					destroy_effects(state, array_from(group.done));
					groups.delete(group);
					if (groups.size === 0) state.outrogroups = null;
				}
			} else remaining -= 1;
		}, false);
	}
	if (remaining === 0) {
		var fast_path = transitions.length === 0 && controlled_anchor !== null && state.pending.size === 0;
		if (fast_path) {
			var anchor = controlled_anchor;
			var parent_node = anchor.parentNode;
			clear_text_content(parent_node);
			parent_node.append(anchor);
			state.items.clear();
		}
		destroy_effects(state, to_destroy, !fast_path);
	} else {
		group = {
			pending: new Set(to_destroy),
			done: /* @__PURE__ */ new Set()
		};
		(state.outrogroups ??= /* @__PURE__ */ new Set()).add(group);
	}
}
/**
* @param {EachState} state
* @param {Effect[]} to_destroy
* @param {boolean} remove_dom
*/
function destroy_effects(state, to_destroy, remove_dom = true) {
	/** @type {Set<Effect> | undefined} */
	var preserved_effects;
	if (state.pending.size > 0) {
		preserved_effects = /* @__PURE__ */ new Set();
		for (const keys of state.pending.values()) for (const key of keys) preserved_effects.add(
			/** @type {EachItem} */
			state.items.get(key).e
		);
	}
	for (var i = 0; i < to_destroy.length; i++) {
		var e = to_destroy[i];
		if (preserved_effects?.has(e)) {
			e.f |= EFFECT_OFFSCREEN;
			move_effect(e, document.createDocumentFragment());
		} else destroy_effect(to_destroy[i], remove_dom);
	}
}
/**
* @template V
* @param {Element | Comment} node The next sibling node, or the parent node if this is a 'controlled' block
* @param {number} flags
* @param {() => V[]} get_collection
* @param {(value: V, index: number) => any} get_key
* @param {(anchor: Node, item: MaybeSource<V>, index: MaybeSource<number>) => void} render_fn
* @param {null | ((anchor: Node) => void)} fallback_fn
* @returns {void}
*/
function each(node, flags, get_collection, get_key, render_fn, fallback_fn = null) {
	var anchor = node;
	/** @type {Map<any, EachItem>} */
	var items = /* @__PURE__ */ new Map();
	if ((flags & 4) !== 0) {
		var parent_node = node;
		anchor = hydrating ? set_hydrate_node(/* @__PURE__ */ get_first_child(parent_node)) : parent_node.appendChild(create_text());
	}
	if (hydrating) hydrate_next();
	/** @type {Effect | null} */
	var fallback = null;
	var each_array = /* @__PURE__ */ derived_safe_equal(() => {
		var collection = get_collection();
		return is_array(collection) ? collection : collection == null ? [] : array_from(collection);
	});
	/** @type {V[]} */
	var array;
	/** @type {Map<Batch, Set<any>>} */
	var pending = /* @__PURE__ */ new Map();
	var first_run = true;
	/**
	* @param {Batch} batch
	*/
	function commit(batch) {
		if ((state.effect.f & 16384) !== 0) return;
		state.pending.delete(batch);
		state.fallback = fallback;
		reconcile(state, array, anchor, flags, get_key);
		if (fallback !== null) {
			if (array.length === 0) {
				if ((fallback.f & 33554432) === 0) resume_effect(fallback);
				else {
					fallback.f ^= EFFECT_OFFSCREEN;
					move(fallback, null, anchor);
				}
			} else pause_effect(fallback, () => {
				fallback = null;
			});
		}
	}
	/**
	* @param {Batch} batch
	*/
	function discard(batch) {
		state.pending.delete(batch);
	}
	/** @type {EachState} */
	var state = {
		effect: block(() => {
			array = get(each_array);
			var length = array.length;
			/** `true` if there was a hydration mismatch. Needs to be a `let` or else it isn't treeshaken out */
			let mismatch = false;
			if (hydrating) {
				if (read_hydration_instruction(anchor) === "[!" !== (length === 0)) {
					anchor = skip_nodes();
					set_hydrate_node(anchor);
					set_hydrating(false);
					mismatch = true;
				}
			}
			var keys = /* @__PURE__ */ new Set();
			var batch = current_batch;
			var defer = should_defer_append();
			for (var index = 0; index < length; index += 1) {
				if (hydrating && hydrate_node.nodeType === 8 && hydrate_node.data === "]") {
					anchor = hydrate_node;
					mismatch = true;
					set_hydrating(false);
				}
				var value = array[index];
				var key = get_key(value, index);
				var item = first_run ? null : items.get(key);
				if (item) {
					if (item.v) internal_set(item.v, value);
					if (item.i) internal_set(item.i, index);
					if (defer) batch.unskip_effect(item.e);
				} else {
					item = create_item(items, first_run ? anchor : offscreen_anchor ??= create_text(), value, key, index, render_fn, flags, get_collection);
					if (!first_run) item.e.f |= EFFECT_OFFSCREEN;
					items.set(key, item);
				}
				keys.add(key);
			}
			if (length === 0 && fallback_fn && !fallback) {
				if (first_run) fallback = branch(() => fallback_fn(anchor));
				else {
					fallback = branch(() => fallback_fn(offscreen_anchor ??= create_text()));
					fallback.f |= EFFECT_OFFSCREEN;
				}
			}
			if (length > keys.size) each_key_duplicate("", "", "");
			if (hydrating && length > 0) set_hydrate_node(skip_nodes());
			if (!first_run) {
				pending.set(batch, keys);
				if (defer) {
					for (const [key, item] of items) if (!keys.has(key)) batch.skip_effect(item.e);
					batch.oncommit(commit);
					batch.ondiscard(discard);
				} else commit(batch);
			}
			if (mismatch) set_hydrating(true);
			get(each_array);
		}),
		flags,
		items,
		pending,
		outrogroups: null,
		fallback
	};
	first_run = false;
	if (hydrating) anchor = hydrate_node;
}
/**
* Skip past any non-branch effects (which could be created with `createSubscriber`, for example) to find the next branch effect
* @param {Effect | null} effect
* @returns {Effect | null}
*/
function skip_to_branch(effect) {
	while (effect !== null && (effect.f & 32) === 0) effect = effect.next;
	return effect;
}
/**
* Add, remove, or reorder items output by an each block as its input changes
* @template V
* @param {EachState} state
* @param {Array<V>} array
* @param {Element | Comment | Text} anchor
* @param {number} flags
* @param {(value: V, index: number) => any} get_key
* @returns {void}
*/
function reconcile(state, array, anchor, flags, get_key) {
	var is_animated = (flags & 8) !== 0;
	var length = array.length;
	var items = state.items;
	var current = skip_to_branch(state.effect.first);
	/** @type {undefined | Set<Effect>} */
	var seen;
	/** @type {Effect | null} */
	var prev = null;
	/** @type {undefined | Set<Effect>} */
	var to_animate;
	/** @type {Effect[]} */
	var matched = [];
	/** @type {Effect[]} */
	var stashed = [];
	/** @type {V} */
	var value;
	/** @type {any} */
	var key;
	/** @type {Effect | undefined} */
	var effect;
	/** @type {number} */
	var i;
	if (is_animated) for (i = 0; i < length; i += 1) {
		value = array[i];
		key = get_key(value, i);
		effect = items.get(key).e;
		if ((effect.f & 33554432) === 0) {
			effect.nodes?.a?.measure();
			(to_animate ??= /* @__PURE__ */ new Set()).add(effect);
		}
	}
	for (i = 0; i < length; i += 1) {
		value = array[i];
		key = get_key(value, i);
		effect = items.get(key).e;
		if (state.outrogroups !== null) for (const group of state.outrogroups) {
			group.pending.delete(effect);
			group.done.delete(effect);
		}
		if ((effect.f & 8192) !== 0) {
			resume_effect(effect);
			if (is_animated) {
				effect.nodes?.a?.unfix();
				(to_animate ??= /* @__PURE__ */ new Set()).delete(effect);
			}
		}
		if ((effect.f & 33554432) !== 0) {
			effect.f ^= EFFECT_OFFSCREEN;
			if (effect === current) move(effect, null, anchor);
			else {
				var next = prev ? prev.next : current;
				if (effect === state.effect.last) state.effect.last = effect.prev;
				if (effect.prev) effect.prev.next = effect.next;
				if (effect.next) effect.next.prev = effect.prev;
				link(state, prev, effect);
				link(state, effect, next);
				move(effect, next, anchor);
				prev = effect;
				matched = [];
				stashed = [];
				current = skip_to_branch(prev.next);
				continue;
			}
		}
		if (effect !== current) {
			if (seen !== void 0 && seen.has(effect)) {
				if (matched.length < stashed.length) {
					var start = stashed[0];
					var j;
					prev = start.prev;
					var a = matched[0];
					var b = matched[matched.length - 1];
					for (j = 0; j < matched.length; j += 1) move(matched[j], start, anchor);
					for (j = 0; j < stashed.length; j += 1) seen.delete(stashed[j]);
					link(state, a.prev, b.next);
					link(state, prev, a);
					link(state, b, start);
					current = start;
					prev = b;
					i -= 1;
					matched = [];
					stashed = [];
				} else {
					seen.delete(effect);
					move(effect, current, anchor);
					link(state, effect.prev, effect.next);
					link(state, effect, prev === null ? state.effect.first : prev.next);
					link(state, prev, effect);
					prev = effect;
				}
				continue;
			}
			matched = [];
			stashed = [];
			while (current !== null && current !== effect) {
				(seen ??= /* @__PURE__ */ new Set()).add(current);
				stashed.push(current);
				current = skip_to_branch(current.next);
			}
			if (current === null) continue;
		}
		if ((effect.f & 33554432) === 0) matched.push(effect);
		prev = effect;
		current = skip_to_branch(effect.next);
	}
	if (state.outrogroups !== null) {
		for (const group of state.outrogroups) if (group.pending.size === 0) {
			destroy_effects(state, array_from(group.done));
			state.outrogroups?.delete(group);
		}
		if (state.outrogroups.size === 0) state.outrogroups = null;
	}
	if (current !== null || seen !== void 0) {
		/** @type {Effect[]} */
		var to_destroy = [];
		if (seen !== void 0) {
			for (effect of seen) if ((effect.f & 8192) === 0) to_destroy.push(effect);
		}
		while (current !== null) {
			if ((current.f & 8192) === 0 && current !== state.fallback) to_destroy.push(current);
			current = skip_to_branch(current.next);
		}
		var destroy_length = to_destroy.length;
		if (destroy_length > 0) {
			var controlled_anchor = (flags & 4) !== 0 && length === 0 ? anchor : null;
			if (is_animated) {
				for (i = 0; i < destroy_length; i += 1) to_destroy[i].nodes?.a?.measure();
				for (i = 0; i < destroy_length; i += 1) to_destroy[i].nodes?.a?.fix();
			}
			pause_effects(state, to_destroy, controlled_anchor);
		}
	}
	if (is_animated) queue_micro_task(() => {
		if (to_animate === void 0) return;
		for (effect of to_animate) effect.nodes?.a?.apply();
	});
}
/**
* @template V
* @param {Map<any, EachItem>} items
* @param {Node} anchor
* @param {V} value
* @param {unknown} key
* @param {number} index
* @param {(anchor: Node, item: V | Source<V>, index: number | Value<number>, collection: () => V[]) => void} render_fn
* @param {number} flags
* @param {() => V[]} get_collection
* @returns {EachItem}
*/
function create_item(items, anchor, value, key, index, render_fn, flags, get_collection) {
	var v = (flags & 1) !== 0 ? (flags & 16) === 0 ? /* @__PURE__ */ mutable_source(value, false, false) : source(value) : null;
	var i = (flags & 2) !== 0 ? source(index) : null;
	return {
		v,
		i,
		e: branch(() => {
			render_fn(anchor, v ?? value, i ?? index, get_collection);
			return () => {
				items.delete(key);
			};
		})
	};
}
/**
* @param {Effect} effect
* @param {Effect | null} next
* @param {Text | Element | Comment} anchor
*/
function move(effect, next, anchor) {
	if (!effect.nodes) return;
	var node = effect.nodes.start;
	var end = effect.nodes.end;
	var dest = next && (next.f & 33554432) === 0 ? next.nodes.start : anchor;
	while (node !== null) {
		var next_node = /* @__PURE__ */ get_next_sibling(node);
		dest.before(node);
		if (node === end) return;
		node = next_node;
	}
}
/**
* @param {EachState} state
* @param {Effect | null} prev
* @param {Effect | null} next
*/
function link(state, prev, next) {
	if (prev === null) state.effect.first = next;
	else prev.next = next;
	if (next === null) state.effect.last = prev;
	else next.prev = prev;
}
var offscreen_anchor;
var init_each = __esmMin((() => {
	init_constants();
	init_hydration();
	init_operations$1();
	init_effects();
	init_sources();
	init_utils$3();
	init_constants$1();
	init_task();
	init_runtime();
	init_esm_env();
	init_deriveds();
	init_batch();
	init_errors();
	init_tracing();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/html.js
var init_html = __esmMin((() => {
	init_effects();
	init_hydration();
	init_template();
	init_utils$1();
	init_context();
	init_operations$1();
	init_runtime();
	init_constants$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/slot.js
var init_slot = __esmMin((() => {
	init_hydration();
	init_operations$1();
	init_template();
}));
//#endregion
//#region node_modules/svelte/src/internal/shared/validate.js
var init_validate$1 = __esmMin((() => {
	init_utils$1();
	init_errors$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/snippet.js
var init_snippet = __esmMin((() => {
	init_constants$1();
	init_effects();
	init_context();
	init_hydration();
	init_reconciler();
	init_template();
	init_errors();
	init_operations$1();
	init_validate$1();
	init_branches();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/svelte-component.js
var init_svelte_component = __esmMin((() => {
	init_constants$1();
	init_effects();
	init_hydration();
	init_branches();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/timing.js
var init_timing = __esmMin((() => {
	init_utils$3();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/loop.js
var init_loop = __esmMin((() => {
	init_timing();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/transitions.js
var init_transitions = __esmMin((() => {
	init_utils$3();
	init_effects();
	init_runtime();
	init_loop();
	init_render();
	init_constants$1();
	init_task();
	init_shared$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/svelte-element.js
var init_svelte_element = __esmMin((() => {
	init_hydration();
	init_operations$1();
	init_effects();
	init_render();
	init_runtime();
	init_context();
	init_constants$1();
	init_template();
	init_utils$1();
	init_branches();
	init_transitions();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/svelte-head.js
var init_svelte_head = __esmMin((() => {
	init_hydration();
	init_operations$1();
	init_effects();
	init_constants$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/css.js
var init_css = __esmMin((() => {
	init_effects();
	init_operations$1();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/actions.js
var init_actions = __esmMin((() => {
	init_effects();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/attachments.js
var init_attachments = __esmMin((() => {
	init_effects();
}));
//#endregion
//#region node_modules/svelte/src/internal/shared/attributes.js
/**
* @param {any} value
* @param {string | null} [hash]
* @param {Record<string, boolean>} [directives]
* @returns {string | null}
*/
function to_class(value, hash, directives) {
	var classname = value == null ? "" : "" + value;
	if (hash) classname = classname ? classname + " " + hash : hash;
	if (directives) {
		for (var key of Object.keys(directives)) if (directives[key]) classname = classname ? classname + " " + key : key;
		else if (classname.length) {
			var len = key.length;
			var a = 0;
			while ((a = classname.indexOf(key, a)) >= 0) {
				var b = a + len;
				if ((a === 0 || whitespace.includes(classname[a - 1])) && (b === classname.length || whitespace.includes(classname[b]))) classname = (a === 0 ? "" : classname.substring(0, a)) + classname.substring(b + 1);
				else a = b;
			}
		}
	}
	return classname === "" ? null : classname;
}
var whitespace;
var init_attributes$1 = __esmMin((() => {
	init_utils$3();
	whitespace = [..." 	\n\r\f\xA0\v﻿"];
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/class.js
/**
* @param {Element} dom
* @param {boolean | number} is_html
* @param {string | null} value
* @param {string} [hash]
* @param {Record<string, any>} [prev_classes]
* @param {Record<string, any>} [next_classes]
* @returns {Record<string, boolean> | undefined}
*/
function set_class(dom, is_html, value, hash, prev_classes, next_classes) {
	var prev = dom[CLASS_CACHE];
	if (hydrating || prev !== value || prev === void 0) {
		var next_class_name = to_class(value, hash, next_classes);
		if (!hydrating || next_class_name !== dom.getAttribute("class")) {
			if (next_class_name == null) dom.removeAttribute("class");
			else if (is_html) dom.className = next_class_name;
			else dom.setAttribute("class", next_class_name);
		}
		/** @type {any} */ dom[CLASS_CACHE] = value;
	} else if (next_classes && prev_classes !== next_classes) for (var key in next_classes) {
		var is_present = !!next_classes[key];
		if (prev_classes == null || is_present !== !!prev_classes[key]) dom.classList.toggle(key, is_present);
	}
	return next_classes;
}
var init_class = __esmMin((() => {
	init_attributes$1();
	init_constants$1();
	init_hydration();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/style.js
var init_style = __esmMin((() => {
	init_attributes$1();
	init_constants$1();
	init_hydration();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/select.js
var init_select = __esmMin((() => {
	init_effects();
	init_shared$1();
	init_proxy();
	init_utils$3();
	init_batch();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/attributes.js
/**
* @param {Element} element
* @param {string} attribute
* @param {string | null} value
* @param {boolean} [skip_warning]
*/
function set_attribute(element, attribute, value, skip_warning) {
	var attributes = get_attributes(element);
	if (hydrating) {
		attributes[attribute] = element.getAttribute(attribute);
		if (attribute === "src" || attribute === "srcset" || attribute === "href" && element.nodeName === LINK_TAG) {
			if (!skip_warning);
			return;
		}
	}
	if (attributes[attribute] === (attributes[attribute] = value)) return;
	if (attribute === "loading") element[LOADING_ATTR_SYMBOL] = value;
	if (value == null) element.removeAttribute(attribute);
	else if (typeof value !== "string" && get_setters(element).has(attribute)) element[attribute] = value;
	else element.setAttribute(attribute, value);
}
/**
*
* @param {Element} element
*/
function get_attributes(element) {
	return element[ATTRIBUTES_CACHE] ??= {
		[IS_CUSTOM_ELEMENT]: element.nodeName.includes("-"),
		[IS_HTML]: element.namespaceURI === NAMESPACE_HTML
	};
}
/** @param {Element} element */
function get_setters(element) {
	var cache_key = element.getAttribute("is") || element.nodeName;
	var setters = setters_cache.get(cache_key);
	if (setters) return setters;
	setters_cache.set(cache_key, setters = /* @__PURE__ */ new Set());
	var descriptors;
	var proto = element;
	var element_proto = Element.prototype;
	while (element_proto !== proto) {
		descriptors = get_descriptors(proto);
		for (var key in descriptors) if (descriptors[key].set && key !== "innerHTML" && key !== "textContent" && key !== "innerText") setters.add(key);
		proto = get_prototype_of(proto);
	}
	return setters;
}
var IS_CUSTOM_ELEMENT, IS_HTML, LINK_TAG, setters_cache;
var init_attributes = __esmMin((() => {
	init_esm_env();
	init_hydration();
	init_utils$3();
	init_events();
	init_misc$1();
	init_warnings();
	init_constants$1();
	init_task();
	init_utils$1();
	init_runtime();
	init_attachments();
	init_attributes$1();
	init_class();
	init_style();
	init_constants();
	init_effects();
	init_select();
	init_async$1();
	IS_CUSTOM_ELEMENT = Symbol("is custom element");
	IS_HTML = Symbol("is html");
	LINK_TAG = IS_XHTML ? "link" : "LINK";
	setters_cache = /* @__PURE__ */ new Map();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/customizable-select.js
var init_customizable_select = __esmMin((() => {
	init_hydration();
	init_operations$1();
	init_reconciler();
	init_attachments();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/document.js
var init_document = __esmMin((() => {
	init_shared$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/input.js
var init_input = __esmMin((() => {
	init_effects();
	init_shared$1();
	init_errors();
	init_proxy();
	init_task();
	init_hydration();
	init_runtime();
	init_batch();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/media.js
var init_media = __esmMin((() => {
	init_effects();
	init_shared$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/navigator.js
var init_navigator = __esmMin((() => {
	init_shared$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/props.js
var init_props$1 = __esmMin((() => {
	init_effects();
	init_utils$3();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/size.js
var init_size = __esmMin((() => {
	init_effects();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/this.js
var init_this = __esmMin((() => {
	init_constants$1();
	init_context();
	init_effects();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/universal.js
var init_universal = __esmMin((() => {
	init_effects();
	init_shared$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/window.js
var init_window = __esmMin((() => {
	init_effects();
	init_shared$1();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/legacy/event-modifiers.js
var init_event_modifiers = __esmMin((() => {
	init_utils$3();
	init_effects();
	init_events();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/legacy/lifecycle.js
var init_lifecycle = __esmMin((() => {
	init_utils$3();
	init_context();
	init_deriveds();
	init_effects();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/legacy/misc.js
var init_misc = __esmMin((() => {
	init_sources();
	init_runtime();
	init_utils$3();
}));
//#endregion
//#region node_modules/svelte/src/store/utils.js
var init_utils = __esmMin((() => {
	init_runtime();
	init_utils$3();
}));
//#endregion
//#region node_modules/svelte/src/store/shared/index.js
var init_shared = __esmMin((() => {
	init_utils$3();
	init_utils();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/store.js
var init_store = __esmMin((() => {
	init_utils();
	init_shared();
	init_utils$3();
	init_runtime();
	init_effects();
	init_sources();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/props.js
var init_props = __esmMin((() => {
	init_utils$3();
	init_sources();
	init_deriveds();
	init_runtime();
	init_errors();
	init_constants$1();
	init_proxy();
	init_store();
	init_effects();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/validate.js
var init_validate = __esmMin((() => {
	init_context();
	init_effects();
	init_store();
	init_async$1();
}));
var init_legacy_client = __esmMin((() => {
	init_constants$1();
	init_effects();
	init_sources();
	init_render();
	init_runtime();
	init_batch();
	init_utils$3();
	init_errors();
	init_context();
	init_flags();
	init_status();
	init_event_modifiers();
}));
var init_custom_element = __esmMin((() => {
	init_legacy_client();
	init_effects();
	init_template();
	init_utils$3();
	init_operations$1();
	if (typeof HTMLElement === "function");
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dev/console-log.js
var init_console_log = __esmMin((() => {
	init_constants$1();
	init_clone();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/index.js
var init_client = __esmMin((() => {
	init_attachments$1();
	init_constants();
	init_context();
	init_assign();
	init_elements();
	init_hmr();
	init_ownership();
	init_legacy();
	init_tracing();
	init_inspect();
	init_async();
	init_validation();
	init_await();
	init_if();
	init_key();
	init_css_props();
	init_each();
	init_html();
	init_slot();
	init_snippet();
	init_svelte_component();
	init_svelte_element();
	init_svelte_head();
	init_css();
	init_actions();
	init_attachments();
	init_attributes();
	init_class();
	init_events();
	init_misc$1();
	init_customizable_select();
	init_style();
	init_transitions();
	init_document();
	init_input();
	init_media();
	init_navigator();
	init_props$1();
	init_select();
	init_size();
	init_this();
	init_universal();
	init_window();
	init_hydration();
	init_event_modifiers();
	init_lifecycle();
	init_misc();
	init_template();
	init_async$1();
	init_batch();
	init_deriveds();
	init_effects();
	init_sources();
	init_props();
	init_store();
	init_boundary();
	init_legacy$1();
	init_render();
	init_runtime();
	init_validate();
	init_timing();
	init_proxy();
	init_custom_element();
	init_operations$1();
	init_attributes$1();
	init_clone();
	init_utils$3();
	init_validate$1();
	init_equality();
	init_console_log();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/hydratable.js
var init_hydratable = __esmMin((() => {
	init_hydration();
	init_errors();
}));
//#endregion
//#region node_modules/svelte/src/index-client.js
var init_index_client = __esmMin((() => {
	init_runtime();
	init_utils$3();
	init_client();
	init_errors();
	init_context();
	init_esm_env();
	init_batch();
	init_hydratable();
	init_render();
	init_snippet();
}));
//#endregion
//#region node_modules/svelte/src/version.js
var init_version = __esmMin((() => {}));
//#endregion
//#region node_modules/svelte/src/internal/disclose-version.js
var init_disclose_version = __esmMin((() => {
	init_version();
	if (typeof window !== "undefined") ((window.__svelte ??= {}).v ??= /* @__PURE__ */ new Set()).add("5");
}));
//#endregion
//#region src/prompta/ui/App.svelte
init_disclose_version();
init_client();
var root$1 = /* @__PURE__ */ from_html(`<div class="app-shell"><aside class="sidebar" id="sidebar"><div class="sidebar-top"><div class="brand-row"><button class="icon-button mobile-only" id="closeSidebar" aria-label="Close sidebar" aria-controls="sidebar"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6"></path></svg></button> <div class="brand-mark" aria-hidden="true">P</div> <div class="brand-copy"><strong>Prompta</strong> <span id="serverLabel"> </span></div> <div class="live-orb" id="globalLiveOrb" title="Cache status"></div></div> <label class="search-box"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg> <input id="searchInput" type="search" placeholder="Search cached chats" aria-label="Search cached chats" aria-keyshortcuts="/" autocomplete="off"/> <kbd>/</kbd></label></div> <div class="sidebar-scroll"><button type="button" class="sidebar-action" id="jobsSidebarButton"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3v3M17 3v3M4.5 8.5h15M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"></path><path d="M8 12h3M8 16h3M14 12h2M14 16h2"></path></svg> <span>Jobs</span></button> <nav class="chat-list" id="chatList" aria-label="Cached conversations"></nav></div> <div class="sidebar-footer"><div class="cache-summary"><span class="summary-dot"></span> <span id="cacheSummary">Reading local cache</span></div> <button type="button" class="read-only-pill" id="headLabel" title="View changelog" aria-haspopup="dialog" aria-controls="changelogDialog">…</button></div></aside> <div class="sidebar-scrim" id="sidebarScrim"></div> <main class="main-panel"><header class="topbar"><button class="icon-button mobile-only" id="openSidebar" aria-label="Open sidebar" aria-controls="sidebar" aria-expanded="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"></path></svg></button> <div class="chat-heading" id="chatHeading"><div class="heading-title">Prompta</div> <div class="heading-meta">Local conversation history</div></div> <div class="topbar-actions" aria-label="Prompta actions"><button class="icon-button" id="pinChatButton" aria-label="Pin chat" title="Pin chat" aria-pressed="false" disabled=""><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6ZM12 14v7"></path></svg></button> <button class="icon-button" id="shareChatButton" aria-label="Copy chat link" title="Share chat" disabled=""><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15V3M7 8l5-5 5 5M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"></path></svg></button> <span class="status-icon sync neutral" id="syncLabel" role="img" aria-label="Local cache" title="Local cache"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 6c0-1.1 3.1-2 7-2s7 .9 7 2-3.1 2-7 2-7-.9-7-2Zm0 0v6c0 1.1 3.1 2 7 2s7-.9 7-2V6M5 12v6c0 1.1 3.1 2 7 2s7-.9 7-2v-6"></path></svg></span></div></header> <section class="conversation-viewport" id="conversationViewport"><div class="empty-state" id="emptyState"><div class="empty-logo">P</div> <h1>Your Prompta chats, locally.</h1> <p>Active runs and completed history stream from Prompta's SQLite cache.</p> <div class="empty-features"><span>Reply from here</span> <span>Live SSE updates</span> <span>SQLite source of truth</span></div></div> <article class="conversation" id="conversation" hidden=""></article></section> <section class="logs-viewport" id="logsViewport" hidden=""><div class="logs-shell"><div class="logs-header"><div><strong id="logsServerTitle">Prompta · prompta.service</strong> <span id="logsMeta">Waiting for synced journal</span></div> <span class="logs-live"><i></i> live</span></div> <pre class="log-output" id="logOutput">Loading logs…</pre></div></section> <footer class="composer-footer" id="composerFooter"><form class="composer-bar" id="messageForm"><div class="composer-input-shell"><div class="attachment-chips" id="attachmentChips" hidden=""></div> <textarea id="messageInput" rows="1" placeholder="Message Prompta…" aria-label="Message Prompta" role="combobox" aria-controls="slashMenu" aria-autocomplete="list" aria-haspopup="listbox" aria-expanded="false" disabled=""></textarea> <div class="slash-menu" id="slashMenu" role="listbox" aria-label="Prompta commands" hidden=""><button type="button" id="slashCommandAdd" role="option" aria-selected="false" data-slash-command="/add "><strong>/add</strong><span>Add a repeating scheduled job</span></button> <button type="button" id="slashCommandList" role="option" aria-selected="false" data-slash-command="/list"><strong>/list</strong><span>List and manage scheduled jobs</span></button> <button type="button" id="slashCommandLogs" role="option" aria-selected="false" data-slash-command="/logs"><strong>/logs</strong><span>View Prompta service logs</span></button> <button type="button" id="slashCommandAt" role="option" aria-selected="false" data-slash-command="/at "><strong>/at</strong><span>Run a prompt at a date and time</span></button></div></div> <div class="composer-tools"><button type="button" class="icon-button attachment-button" id="attachmentButton" aria-label="Add attachment" title="Add file or photo" aria-haspopup="menu" aria-controls="attachmentMenu" aria-expanded="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"></path></svg></button> <div class="attachment-menu" id="attachmentMenu" role="menu" aria-label="Add attachment" hidden=""><button type="button" role="menuitem" data-attachment-kind="file">Upload file</button> <button type="button" role="menuitem" data-attachment-kind="photo">Upload photo</button> <button type="button" role="menuitem" data-attachment-kind="camera">Take photo</button></div> <input id="fileUploadInput" type="file" hidden=""/> <input id="photoUploadInput" type="file" accept="image/*" hidden=""/> <input id="cameraUploadInput" type="file" accept="image/*" capture="environment" hidden=""/></div> <div class="composer-submit"><button type="button" class="icon-button composer-new-chat-button" id="newChatButton" aria-label="Start a new chat" title="New chat"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 4H7a4 4 0 0 0-4 4v8a4 4 0 0 0 4 4h8l4 2v-7"></path><path d="M18 3v6M15 6h6"></path></svg></button> <button type="submit" class="send-button" id="sendButton" aria-label="Send message" disabled=""><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6"></path></svg></button></div></form> <div class="composer-status" id="composerStatus"></div></footer></main></div> <button type="button" class="version-update-notice" id="versionUpdateNotice" aria-label="New Prompta version available. Tap to update" aria-live="polite" hidden="">Update available</button> <dialog class="jobs-dialog" id="jobsDialog" aria-labelledby="jobsDialogTitle"><div class="jobs-dialog-shell"><header class="jobs-dialog-header"><div class="chat-heading"><div class="heading-title" id="jobsDialogTitle">Scheduled jobs</div> <div class="heading-meta">Create and manage scheduled prompts.</div></div> <button type="button" class="jobs-icon-button" id="closeJobsDialog" aria-label="Close scheduled jobs">×</button></header> <div class="jobs-dialog-status" id="jobsDialogStatus" role="status"></div> <div class="jobs-list" id="jobsList"></div> <form class="jobs-form" id="jobsForm"><h3 id="jobsFormTitle">Add job</h3> <label><span>Name</span> <input id="jobNameInput" name="name" autocomplete="off" required=""/></label> <label><span>Prompt</span> <textarea id="jobPromptInput" name="prompt" rows="3" required=""></textarea></label> <div class="jobs-form-grid"><label><span>Schedule</span> <select id="jobScheduleType"><option>Interval</option><option>Daily</option></select></label> <label id="jobIntervalField"><span>Every (minutes)</span> <input id="jobIntervalInput" type="number" min="0.1" step="0.1" value="40"/></label> <label id="jobDailyField" hidden=""><span>At</span> <input id="jobDailyInput" type="time" value="09:00"/></label></div> <label class="jobs-check" id="jobExactField"><input id="jobExactInput" type="checkbox"/> <span>Exact interval</span></label> <div class="jobs-form-actions"><button type="button" class="jobs-secondary-button" id="resetJobForm">Reset</button> <button type="submit" class="jobs-primary-button" id="saveJobButton">Save job</button></div></form> <div class="jobs-dialog-footer"><button type="button" class="jobs-danger-button" id="clearJobsButton">Clear all jobs</button></div></div></dialog> <dialog class="changelog-dialog" id="changelogDialog" aria-labelledby="changelogDialogTitle"><div class="changelog-dialog-shell"><header class="changelog-dialog-header"><div><h2 id="changelogDialogTitle">Changelog</h2> <p id="changelogDialogStatus">Commit titles from this Prompta checkout.</p></div> <button type="button" class="changelog-close-button" id="closeChangelogDialog" aria-label="Close changelog">×</button></header> <ol class="changelog-list" id="changelogList"></ol></div></dialog>`, 1);
function App($$anchor, $$props) {
	var fragment = root$1();
	var div = first_child(fragment);
	var aside = child(div);
	var div_1 = child(aside);
	var div_2 = child(div_1);
	var div_3 = sibling(child(div_2), 4);
	var text = only_child(sibling(child(div_3), 2));
	reset(div_3);
	next(2);
	reset(div_2);
	next(2);
	reset(div_1);
	next(4);
	reset(aside);
	next(4);
	reset(div);
	var dialog = sibling(div, 4);
	var div_4 = child(dialog);
	var form = sibling(child(div_4), 6);
	var div_5 = sibling(child(form), 6);
	var label = child(div_5);
	var select = sibling(child(label), 2);
	var option = child(select);
	option.value = option.__value = "interval";
	var option_1 = sibling(option);
	option_1.value = option_1.__value = "daily";
	reset(select);
	reset(label);
	next(4);
	reset(div_5);
	next(4);
	reset(form);
	next(2);
	reset(div_4);
	reset(dialog);
	next(2);
	template_effect(() => set_text(text, `Server · ${$$props.serverName ?? ""}`));
	append($$anchor, fragment);
}
//#endregion
//#region src/prompta/ui/SidebarList.svelte
function SidebarList($$anchor, $$props) {
	push($$props, true);
	let model = /* @__PURE__ */ state$1(proxy({
		emptyState: "none",
		groups: []
	}));
	function update(next) {
		set(model, next, true);
	}
	var $$exports = { update };
	var fragment = comment();
	var node = first_child(fragment);
	var consequent_1 = ($$anchor) => {
		var div = root_1();
		var node_1 = child(div);
		var consequent = ($$anchor) => {
			append($$anchor, text("No cached chats match your search."));
		};
		var alternate = ($$anchor) => {
			var fragment_1 = root();
			next(2);
			append($$anchor, fragment_1);
		};
		if_block(node_1, ($$render) => {
			if (get(model).emptyState === "search") $$render(consequent);
			else $$render(alternate, -1);
		});
		reset(div);
		append($$anchor, div);
	};
	var alternate_1 = ($$anchor) => {
		var fragment_2 = comment();
		each(first_child(fragment_2), 17, () => get(model).groups, (group) => group.label, ($$anchor, group) => {
			var section = root_5();
			var div_1 = child(section);
			var text_1 = only_child(div_1, true);
			each(sibling(div_1, 2), 17, () => get(group).chats, (chat) => chat.id, ($$anchor, chat) => {
				var div_2 = root_4();
				let classes;
				var button = child(div_2);
				var div_3 = child(button);
				var node_4 = child(div_3);
				var consequent_2 = ($$anchor) => {
					var span = root_2();
					template_effect(() => {
						set_class(span, 1, "item-status-dot " + get(chat).statusClass);
						set_attribute(span, "title", get(chat).statusLabel || void 0);
						set_attribute(span, "aria-label", get(chat).statusLabel || void 0);
					});
					append($$anchor, span);
				};
				if_block(node_4, ($$render) => {
					if (get(chat).statusClass) $$render(consequent_2);
				});
				var span_1 = sibling(node_4, 2);
				var text_2 = only_child(span_1, true);
				var node_5 = sibling(span_1, 2);
				var consequent_3 = ($$anchor) => {
					append($$anchor, root_3());
				};
				if_block(node_5, ($$render) => {
					if (get(chat).broken) $$render(consequent_3);
				});
				reset(div_3);
				var div_4 = sibling(div_3, 2);
				var text_3 = only_child(div_4, true);
				var div_5 = sibling(div_4, 2);
				var span_3 = child(div_5);
				var text_4 = only_child(span_3, true);
				var span_4 = sibling(span_3, 2);
				var text_5 = only_child(span_4, true);
				reset(div_5);
				reset(button);
				var button_1 = sibling(button, 2);
				let classes_1;
				reset(div_2);
				template_effect(() => {
					classes = set_class(div_2, 1, "chat-item", null, classes, { selected: get(chat).selected });
					set_attribute(div_2, "data-dom-key", "chat:" + get(chat).id);
					set_attribute(button, "data-chat-id", get(chat).id);
					set_attribute(button, "data-optimistic-new", get(chat).optimisticNew ? "true" : "false");
					set_attribute(button, "aria-current", get(chat).selected ? "true" : void 0);
					set_text(text_2, get(chat).title);
					set_text(text_3, get(chat).preview);
					set_text(text_4, get(chat).jobLabel);
					set_attribute(span_4, "data-activity-at", get(chat).activityAt);
					set_text(text_5, get(chat).relativeTime);
					classes_1 = set_class(button_1, 1, "chat-row-pin", null, classes_1, { active: get(chat).pinned });
					set_attribute(button_1, "data-pin-chat-id", get(chat).id);
					set_attribute(button_1, "aria-label", get(chat).pinned ? "Unpin chat" : "Pin chat");
					set_attribute(button_1, "title", get(chat).pinned ? "Unpin chat" : "Pin chat");
					set_attribute(button_1, "aria-pressed", get(chat).pinned);
				});
				delegated("click", button, () => $$props.onSelect(get(chat).id, get(chat).optimisticNew));
				delegated("click", button_1, () => $$props.onPin(get(chat).id));
				append($$anchor, div_2);
			});
			reset(section);
			template_effect(() => {
				set_attribute(section, "data-dom-key", "group:" + get(group).label);
				set_text(text_1, get(group).label);
			});
			append($$anchor, section);
		});
		append($$anchor, fragment_2);
	};
	if_block(node, ($$render) => {
		if (get(model).groups.length === 0) $$render(consequent_1);
		else $$render(alternate_1, -1);
	});
	append($$anchor, fragment);
	return pop($$exports);
}
var root, root_1, root_2, root_3, root_4, root_5;
var init_SidebarList = __esmMin((() => {
	init_disclose_version();
	init_client();
	root = /* @__PURE__ */ from_html(`No cached conversations yet.<br/>Prompta runs will appear here live.`, 1);
	root_1 = /* @__PURE__ */ from_html(`<div class="list-empty"><!></div>`);
	root_2 = /* @__PURE__ */ from_html(`<span></span>`);
	root_3 = /* @__PURE__ */ from_html(`<span class="chat-broken-badge" title="No ChatGPT response for at least 40 minutes">Broken</span>`);
	root_4 = /* @__PURE__ */ from_html(`<div><button type="button" class="chat-item-select"><div class="chat-item-top"><!> <span class="chat-title"> </span> <!></div> <div class="chat-preview"> </div> <div class="chat-meta"><span class="chat-job"> </span> <span class="chat-time"> </span></div></button> <button type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6l-.8 5 3.3 3.3v1.4H13v7.8l-1 1-1-1v-7.8H6.5v-1.4L9.8 8 9 3z"></path></svg></button></div>`);
	root_5 = /* @__PURE__ */ from_html(`<section class="chat-group"><div class="chat-group-label"> </div> <!></section>`);
	delegate(["click"]);
}));
//#endregion
//#region src/prompta/ui/clientLogic.ts
function chatListRequestUrl(search, pinnedIds) {
	const params = new URLSearchParams();
	if (search.trim()) params.set("q", search);
	else {
		const seen = /* @__PURE__ */ new Set();
		for (const rawId of pinnedIds) {
			const id = String(rawId || "").trim();
			if (!id || seen.has(id)) continue;
			seen.add(id);
			params.append("include", id);
		}
	}
	const suffix = params.toString();
	return suffix ? `api/chats?${suffix}` : "api/chats";
}
function sidebarChatCountSummary(chatCount, activeCount, search) {
	return `${search.trim() ? `${chatCount} ${chatCount === 1 ? "result" : "results"}` : `${chatCount} cached`} · ${activeCount} active`;
}
function sidebarChatCreatedAt(chat) {
	const createdAt = Number(chat?.created_at || 0);
	return Number.isFinite(createdAt) && createdAt > 0 ? createdAt : 0;
}
function sidebarChatIsPending(chat) {
	return Boolean(chat?._pending_send || chat?._optimisticNew || chat?._optimisticReply);
}
function positiveEpoch(value) {
	const epoch = Number(value || 0);
	return Number.isFinite(epoch) && epoch > 0 ? epoch : 0;
}
function roleActivityAt(chat, role) {
	if (!chat) return 0;
	let latest = positiveEpoch(role === "assistant" ? chat.last_assistant_at : chat.last_user_at);
	for (const message of chat.messages || []) {
		if ((typeof message?.role === "string" ? message.role : "") !== role) continue;
		latest = Math.max(latest, positiveEpoch(message.activity_at), positiveEpoch(message.created_at));
	}
	return latest;
}
function chatLastAssistantAt(chat) {
	return roleActivityAt(chat, "assistant");
}
function chatBrokenReferenceAt(chat) {
	if (!chat) return 0;
	return Math.max(chatLastAssistantAt(chat), roleActivityAt(chat, "user"), positiveEpoch(chat.created_at));
}
function chatIsBroken(chat, nowSeconds = Date.now() / 1e3) {
	if (!chat || sidebarChatIsPending(chat)) return false;
	const status = typeof chat.status === "string" ? chat.status : "";
	if (status !== "active" && status !== "interrupted") return false;
	const referenceAt = chatBrokenReferenceAt(chat);
	if (!referenceAt) return false;
	return nowSeconds - referenceAt >= BROKEN_CHAT_AFTER_SECONDS;
}
function sidebarSelectedConversationId(selectedId, composingNew, pendingNewDisplayId) {
	const pendingId = String(pendingNewDisplayId || "");
	if (composingNew && pendingId) return pendingId;
	return String(selectedId || "");
}
function sidebarChatIsSelected(chat, selectedId, composingNew, pendingNewDisplayId) {
	const chatId = String(chat?.id || "");
	if (!chatId) return false;
	return chatId === sidebarSelectedConversationId(selectedId, composingNew, pendingNewDisplayId);
}
function selectedConversationAfterChatRefresh(selectedId, composingNew, chats) {
	const current = String(selectedId || "").trim();
	if (current) return current;
	if (composingNew) return null;
	return String(chats[0]?.id || "").trim() || null;
}
function clientIdBelongsToSession(clientId, sessionId) {
	const client = String(clientId || "").trim();
	const session = String(sessionId || "").trim();
	return Boolean(client && session && client.startsWith(`${session}:`));
}
function sortSidebarChats(chats, pinnedIds) {
	const pinnedOrder = new Map(Array.from(pinnedIds, (id, index) => [id, index]));
	return [...chats].sort((left, right) => {
		const leftPinnedIndex = pinnedOrder.get(left.id);
		const rightPinnedIndex = pinnedOrder.get(right.id);
		if (leftPinnedIndex !== void 0 || rightPinnedIndex !== void 0) {
			if (leftPinnedIndex === void 0) return 1;
			if (rightPinnedIndex === void 0) return -1;
			return leftPinnedIndex - rightPinnedIndex;
		}
		const createdDelta = sidebarChatCreatedAt(right) - sidebarChatCreatedAt(left);
		if (createdDelta) return createdDelta;
		return left.id.localeCompare(right.id);
	});
}
function textValue(value, fallback = "") {
	if (typeof value === "string") return value;
	if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") return String(value);
	return fallback;
}
function readableRichMarkerFallback(parts) {
	return parts.find((part) => {
		const value = part.trim();
		return Boolean(value) && value.length <= 200 && !/^turn\d+[a-z]+\d+$/i.test(value) && !/^https?:\/\//i.test(value) && !/^[{[]/.test(value);
	})?.trim() || "";
}
function replaceChatGptRichMarkers(value, renderUrl = (label) => label) {
	const source = textValue(value);
	let output = "";
	let cursor = 0;
	while (cursor < source.length) {
		const start = source.indexOf(CHATGPT_RICH_START, cursor);
		if (start < 0) {
			output += source.slice(cursor);
			break;
		}
		output += source.slice(cursor, start);
		const end = source.indexOf(CHATGPT_RICH_END, start + 1);
		if (end < 0) break;
		const [rawType, ...parts] = source.slice(start + 1, end).split(CHATGPT_RICH_SEPARATOR);
		const type = rawType.trim().toLowerCase();
		let replacement = "";
		if (type === "url") {
			const label = String(parts[0] || parts[1] || "").trim();
			const url = String(parts[1] || "").trim();
			replacement = /^https?:\/\//i.test(url) ? renderUrl(label || url, url) : label || readableRichMarkerFallback(parts);
		} else if (type !== "cite" && type !== "memcite") replacement = readableRichMarkerFallback(parts);
		output += replacement;
		cursor = end + 1;
	}
	return output;
}
function retryDelayText(seconds) {
	const value = Number(seconds);
	if (!Number.isFinite(value) || value <= 0) return "soon";
	if (value < 60) return "<1m";
	const minutes = Math.ceil(value / 60);
	if (minutes < 60) return `${minutes}m`;
	return `${Math.ceil(minutes / 60)}h`;
}
function pendingSendActivity(status, hasSendId, retryAfterSeconds = 0, retryAtEpoch = 0, nowEpoch = Date.now() / 1e3, queuePosition = 0) {
	const normalized = textValue(status, "queued").trim().toLowerCase();
	if (["failed", "dead_lettered"].includes(normalized)) return null;
	if (!hasSendId) return {
		label: "sending",
		statusText: "Sending…"
	};
	if (normalized === "queued") {
		const position = Number(queuePosition);
		if (Number.isFinite(position) && position > 0) return {
			label: "queued · #" + Math.floor(position),
			statusText: "Queued in Prompta · #" + Math.floor(position)
		};
		return {
			label: "queued",
			statusText: "Queued in Prompta…"
		};
	}
	if (normalized === "retrying") {
		const deadline = Number(retryAtEpoch);
		const now = Number(nowEpoch);
		const remaining = Number.isFinite(deadline) && deadline > 0 && Number.isFinite(now) ? Math.max(0, deadline - now) : Number(retryAfterSeconds);
		if (remaining <= 0) return {
			label: "retrying now",
			statusText: "Retry backoff elapsed; retrying now…"
		};
		const delay = retryDelayText(remaining);
		return {
			label: `retrying · ${delay}`,
			statusText: `Send failed transiently — retrying automatically in ${delay}.`
		};
	}
	if (normalized === "rate_limited") {
		const deadline = Number(retryAtEpoch);
		const now = Number(nowEpoch);
		const hasDeadline = Number.isFinite(deadline) && deadline > 0 && Number.isFinite(now);
		const remaining = hasDeadline ? Math.max(0, deadline - now) : Number(retryAfterSeconds);
		if (hasDeadline && remaining <= 0) return {
			label: "rate limited · retrying now",
			statusText: "Rate limited — backoff elapsed; retrying now…"
		};
		const delay = retryDelayText(remaining);
		return {
			label: `rate limited · retry in ${delay}`,
			statusText: `Rate limited — backing off; retrying automatically in ${delay}.`
		};
	}
	return {
		label: "waiting",
		statusText: "Waiting for ChatGPT…"
	};
}
function conversationIdFromHash(hash) {
	const encoded = textValue(hash).replace(/^#\/?/, "").trim();
	if (!encoded) return "";
	try {
		return decodeURIComponent(encoded);
	} catch {
		return "";
	}
}
function toolCallDisplayName(value) {
	const name = textValue(value).replace(/\s+/g, " ").trim();
	return name && !TOOL_UI_NOISE.test(name) ? name : "";
}
function toolCallIsInvocationPlaceholder(value) {
	return /^called tool$/i.test(textValue(value).trim());
}
function toolCallHasUsefulDetail(value) {
	return textValue(value).split(/\n+/).map((line) => line.trim()).some((line) => Boolean(toolCallDisplayName(line)));
}
function parsedToolPayload(value) {
	let current = value;
	for (let depth = 0; depth < 3; depth += 1) {
		if (typeof current !== "string") return current;
		const trimmed = current.trim();
		if (!trimmed || !/^[{[]/.test(trimmed)) return current;
		try {
			current = JSON.parse(trimmed);
		} catch {
			return current;
		}
	}
	return current;
}
function toolCallSummary(value) {
	const payload = parsedToolPayload(value);
	if (!payload || typeof payload !== "object" || Array.isArray(payload)) return "";
	const record = payload;
	for (const candidate of [
		record.summary,
		record.reasoning_title,
		record.title
	]) if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
	return "";
}
function toolCallTimestampMillis(value) {
	const payload = parsedToolPayload(value);
	if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
	const record = payload;
	for (const candidate of [
		record.created_at,
		record.createdAt,
		record.timestamp,
		record.time
	]) {
		const numeric = Number(candidate);
		if (!Number.isFinite(numeric) || numeric <= 0) continue;
		const millis = numeric > 0xe8d4a51000 ? numeric : numeric * 1e3;
		if (Number.isNaN(new Date(millis).getTime())) continue;
		return millis;
	}
	return null;
}
function pythonToolCallCode(toolName, value) {
	const name = textValue(toolName).trim().toLowerCase();
	if (!(name.includes("execute_python") || name.includes("python") && (name.includes("nox") || name.includes("glass") || name.includes("mcp")))) return "";
	const payload = parsedToolPayload(value);
	if (!payload || typeof payload !== "object" || Array.isArray(payload)) return "";
	const record = payload;
	const argumentPayload = parsedToolPayload(record.arguments ?? record.args ?? record);
	if (!argumentPayload || typeof argumentPayload !== "object" || Array.isArray(argumentPayload)) return "";
	const code = argumentPayload.code;
	return typeof code === "string" ? code.replace(/^(?:[ \t]*\r?\n)+/, "") : "";
}
function sidebarPreviewText(value) {
	return replaceChatGptRichMarkers(value).replace(/```(?:tool|tool-call|function|function-call)(?::[^\n\x60]*)?\n?[\s\S]*?```/gi, " ").replace(/\s+/g, " ").trim();
}
function sidebarChatPreviewText(preview, prompt) {
	return sidebarPreviewText(preview) || sidebarPreviewText(prompt);
}
function missingPendingConversationSummaries(chats, pendingReplies, query = "") {
	const existingIds = new Set(chats.map((chat) => String(chat.id)));
	const needle = query.trim().toLowerCase();
	const summaries = [];
	for (const [conversationId, replies] of pendingReplies) {
		if (!conversationId || existingIds.has(conversationId) || !replies.length) continue;
		const latest = replies[replies.length - 1];
		const message = textValue(latest.message).trim();
		const title = message.slice(0, 72) || "New chat";
		const status = ["failed", "dead_lettered"].includes(textValue(latest.status)) ? textValue(latest.status) : "active";
		if (needle && ![
			title,
			message,
			"new chat"
		].some((value) => value.toLowerCase().includes(needle))) continue;
		const createdAt = Number(latest.createdAt || latest.updatedAt || 0);
		const updatedAt = Number(latest.updatedAt || latest.createdAt || 0);
		summaries.push({
			id: conversationId,
			status,
			title,
			preview: message,
			message_count: 1,
			job_name: "new chat",
			created_at: Number.isFinite(createdAt) ? createdAt : 0,
			updated_at: Number.isFinite(updatedAt) ? updatedAt : 0,
			_optimisticReply: true
		});
	}
	return summaries.sort((left, right) => right.updated_at - left.updated_at);
}
function pendingConversationDisplayId(pending) {
	if (!pending) return "";
	if (pending.conversationId) return String(pending.conversationId);
	const clientId = String(pending.clientId || "").trim();
	return clientId ? `pending-new-${clientId}` : "";
}
function promotePinnedConversationId(pinnedIds, pending, nextConversationId) {
	const nextId = String(nextConversationId || "").trim();
	if (!nextId) return false;
	const previousId = pendingConversationDisplayId(pending);
	if (!previousId || previousId === nextId || !pinnedIds.has(previousId)) return false;
	pinnedIds.delete(previousId);
	pinnedIds.add(nextId);
	return true;
}
function comparableTimestampSeconds(value) {
	const timestamp = Number(value);
	if (!Number.isFinite(timestamp) || timestamp <= 0) return 0;
	return timestamp >= 0xe8d4a51000 ? timestamp / 1e3 : timestamp;
}
function comparablePrompt(value) {
	return textValue(value).trim().replace(/\s+/g, " ");
}
function matchingOptimisticConversation(chats, pending, knownConversationIds = /* @__PURE__ */ new Set()) {
	if (!pending) return null;
	const clientId = textValue(pending.clientId).trim();
	if (clientId) {
		const exactClient = chats.find((chat) => textValue(chat._client_id).trim() === clientId);
		if (exactClient) return exactClient;
	}
	if (pending.conversationId) {
		const exact = chats.find((chat) => chat.id === pending.conversationId);
		if (exact) return exact;
	}
	const prompt = comparablePrompt(pending.message);
	if (!prompt) return null;
	const createdAt = comparableTimestampSeconds(pending.createdAt);
	let best = null;
	let bestDistance = Number.POSITIVE_INFINITY;
	if (createdAt > 0) for (const chat of chats) {
		if (comparablePrompt(chat.prompt) !== prompt) continue;
		const chatCreatedAt = comparableTimestampSeconds(chat.created_at);
		if (chatCreatedAt <= 0) continue;
		const distance = Math.abs(chatCreatedAt - createdAt);
		if (distance > 30 || distance >= bestDistance) continue;
		best = chat;
		bestDistance = distance;
	}
	if (best) return best;
	if (!knownConversationIds.size) return null;
	const unseenMatches = chats.filter((chat) => !knownConversationIds.has(chat.id) && comparablePrompt(chat.prompt) === prompt);
	return unseenMatches.length === 1 ? unseenMatches[0] : null;
}
function messageTimestampMillis(createdAt, updatedAt) {
	for (const candidate of [createdAt, updatedAt]) {
		const raw = Number(candidate);
		if (!Number.isFinite(raw) || raw <= 0) continue;
		const millis = raw < 0xe8d4a51000 ? raw * 1e3 : raw;
		if (!Number.isFinite(millis)) continue;
		const date = new Date(millis);
		if (!Number.isNaN(date.getTime())) return millis;
	}
	return null;
}
function formatClockTime12Hour(value, includeSeconds = false) {
	const date = value instanceof Date ? value : new Date(value);
	if (Number.isNaN(date.getTime())) return "";
	const hour24 = date.getHours();
	return `${hour24 % 12 || 12}:${String(date.getMinutes()).padStart(2, "0")}${includeSeconds ? `:${String(date.getSeconds()).padStart(2, "0")}` : ""}${hour24 < 12 ? "am" : "pm"}`;
}
function formatDailyTime12Hour(value) {
	const raw = textValue(value);
	const match = raw.match(/^([01]\d|2[0-3]):([0-5]\d)$/);
	if (!match) return raw;
	const hour24 = Number(match[1]);
	return `${hour24 % 12 || 12}:${match[2]}${hour24 < 12 ? "am" : "pm"}`;
}
function messageAgeText(timestampMillis, nowMillis = Date.now()) {
	const timestamp = Number(timestampMillis);
	const now = Number(nowMillis);
	if (!Number.isFinite(timestamp) || timestamp <= 0 || !Number.isFinite(now)) return "";
	const elapsed = Math.max(0, now - timestamp);
	if (elapsed < 45e3) return "now";
	if (elapsed < 36e5) return `${Math.max(1, Math.floor(elapsed / 6e4))}m ago`;
	if (elapsed < 864e5) return `${Math.max(1, Math.floor(elapsed / 36e5))}h ago`;
	if (elapsed < 6048e5) return `${Math.max(1, Math.floor(elapsed / 864e5))}d ago`;
	if (elapsed < 2592e6) return `${Math.max(1, Math.floor(elapsed / 6048e5))}w ago`;
	if (elapsed < 31536e6) return `${Math.max(1, Math.floor(elapsed / 2592e6))}mo ago`;
	return `${Math.max(1, Math.floor(elapsed / 31536e6))}y ago`;
}
function shouldRenderNewChatView(enteringNewChat, fingerprint, previousFingerprint) {
	return enteringNewChat || fingerprint !== previousFingerprint;
}
function pendingConversationSends(conversationId, replies, pendingNew) {
	if (!pendingNew || pendingNew.conversationId !== conversationId) return replies;
	return replies.some((item) => item === pendingNew || pendingNew.clientId && item.clientId === pendingNew.clientId || pendingNew.sendId && item.sendId === pendingNew.sendId) ? replies : [...replies, pendingNew];
}
function matchingPendingReplyMessageIndex(messages, pending, claimedIndexes = /* @__PURE__ */ new Set()) {
	const content = comparablePrompt(pending.message);
	if (!content) return -1;
	if (pending.origin === "new") {
		const firstDurableUserIndex = messages.findIndex((message, index) => !claimedIndexes.has(index) && message.role === "user" && comparablePrompt(message.content) === content);
		if (firstDurableUserIndex >= 0) return firstDurableUserIndex;
	}
	const pendingTimes = [pending.createdAt, pending.updatedAt].map(comparableTimestampSeconds).filter((timestamp) => timestamp > 0);
	if (!pendingTimes.length) return -1;
	let bestIndex = -1;
	let bestDistance = Number.POSITIVE_INFINITY;
	for (let index = messages.length - 1; index >= 0; index -= 1) {
		if (claimedIndexes.has(index)) continue;
		const message = messages[index];
		if (message.role !== "user" || comparablePrompt(message.content) !== content) continue;
		const messageTime = comparableTimestampSeconds(message.created_at || message.updated_at);
		if (messageTime <= 0) continue;
		const distance = Math.min(...pendingTimes.map((pendingTime) => Math.abs(messageTime - pendingTime)));
		if (distance > 30 || distance >= bestDistance) continue;
		bestIndex = index;
		bestDistance = distance;
	}
	return bestIndex;
}
function parseScheduleSlashCommand(message) {
	if (!/^\/(?:add|every)(?:\s|$)/i.test(message)) return null;
	const match = message.match(/^\/(?:add|every)\s+(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)?\s+([\s\S]+)$/i);
	if (!match) return { error: "Use /add <interval> <prompt>, for example: /add 30 fix bugs or /add 2h review failures" };
	const amount = Number(match[1]);
	const unit = String(match[2] || "m").toLowerCase();
	const intervalMinutes = amount * (unit.startsWith("s") ? 1 / 60 : unit.startsWith("h") ? 60 : unit.startsWith("d") ? 1440 : 1);
	const prompt = match[3].trim();
	if (!Number.isFinite(intervalMinutes) || intervalMinutes <= 0) return { error: "Schedule interval must be a finite value greater than zero." };
	if (intervalMinutes < .1) return { error: "Schedule interval must be at least 6 seconds." };
	if (intervalMinutes > 43200) return { error: "Schedule interval cannot exceed 30 days." };
	if (!prompt) return { error: "Schedule prompt is required." };
	return {
		intervalMinutes,
		prompt
	};
}
function formatScheduleInterval(minutes) {
	if (minutes < 1) {
		const seconds = minutes * 60;
		return `${seconds} second${seconds === 1 ? "" : "s"}`;
	}
	if (minutes >= 1440 && minutes % 1440 === 0) {
		const days = minutes / 1440;
		return `${days} day${days === 1 ? "" : "s"}`;
	}
	if (minutes >= 60 && minutes % 60 === 0) {
		const hours = minutes / 60;
		return `${hours} hour${hours === 1 ? "" : "s"}`;
	}
	return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}
async function postJsonRequest(url, payload, attempts = 1, timeoutMs = 45e3, fetchImpl = fetch) {
	let lastError = /* @__PURE__ */ new Error("Request failed");
	for (let attempt = 0; attempt < Math.max(1, attempts); attempt += 1) {
		const controller = new AbortController();
		const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
		let response;
		let data = {};
		try {
			response = await fetchImpl(url, {
				method: "POST",
				cache: "no-store",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(payload),
				signal: controller.signal
			});
			try {
				data = await response.json();
			} catch {
				if (controller.signal.aborted) throw new Error("Request timed out");
				if (response.ok) throw new Error("Prompta returned an invalid response");
			}
		} catch (error) {
			lastError = controller.signal.aborted ? /* @__PURE__ */ new Error("Request timed out") : error instanceof Error ? error : new Error(String(error));
			if (attempt + 1 >= attempts) throw lastError;
			await new Promise((resolve) => globalThis.setTimeout(resolve, 350 * (attempt + 1)));
			continue;
		} finally {
			globalThis.clearTimeout(timeout);
		}
		if (response.ok) return data;
		const errorMessage = typeof data === "object" && data !== null && "error" in data && typeof data.error === "string" ? data.error : "";
		lastError = new Error(errorMessage || `${response.status} ${response.statusText}`);
		if (response.status < 500 || attempt + 1 >= attempts) throw lastError;
		await new Promise((resolve) => globalThis.setTimeout(resolve, 350 * (attempt + 1)));
	}
	throw lastError;
}
async function deleteRequest(url, timeoutMs = 1e4, fetchImpl = fetch) {
	const controller = new AbortController();
	const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
	try {
		const response = await fetchImpl(url, {
			method: "DELETE",
			cache: "no-store",
			signal: controller.signal
		});
		if (!response.ok && response.status !== 404) throw new Error((String(response.status) + " " + response.statusText).trim());
	} catch (error) {
		if (controller.signal.aborted) throw new Error("Request timed out");
		throw error instanceof Error ? error : new Error(String(error));
	} finally {
		globalThis.clearTimeout(timeout);
	}
}
function nextSlashCommandIndex(itemCount, currentIndex, direction) {
	const count = Math.max(0, Math.trunc(itemCount));
	if (count === 0) return -1;
	const step = direction < 0 ? -1 : 1;
	if (currentIndex < 0 || currentIndex >= count) return step < 0 ? count - 1 : 0;
	return (currentIndex + step + count) % count;
}
function composerHasContent(message, attachmentCount) {
	return Boolean(String(message || "").trim()) || attachmentCount > 0;
}
function shouldShowStopAction(chatStatus, composingNew, hasComposerContent = false) {
	return !hasComposerContent && !composingNew && textValue(chatStatus).trim().toLowerCase() === "active";
}
function shouldProbeHistoricalActivity(chatStatus) {
	return textValue(chatStatus).trim().toLowerCase() === "interrupted";
}
function shouldRefreshSelectedChat(summary, selectedUpdatedAt, selectedFingerprint, force = false) {
	return force || !summary || summary.status === "active" || selectedUpdatedAt !== summary.updated_at || !selectedFingerprint;
}
function parseAtSlashCommand(message, now = /* @__PURE__ */ new Date()) {
	if (!/^\/at(?:\s|$)/i.test(message)) return null;
	const match = message.match(/^\/at\s+(today|tomorrow|\d{4}-\d{2}-\d{2})(?:[T\s]+)([01]\d|2[0-3]):([0-5]\d)\s+([\s\S]+)$/i);
	if (!match) return { error: "Use /at <date> <time> <prompt>, for example: /at 2026-09-21 09:30 review failures" };
	const dateToken = match[1].toLowerCase();
	const hour = Number(match[2]);
	const minute = Number(match[3]);
	const prompt = match[4].trim();
	let target;
	let expectedYear;
	let expectedMonth;
	let expectedDay;
	if (dateToken === "today" || dateToken === "tomorrow") {
		target = new Date(now);
		if (dateToken === "tomorrow") target.setDate(target.getDate() + 1);
		expectedYear = target.getFullYear();
		expectedMonth = target.getMonth();
		expectedDay = target.getDate();
		target.setHours(hour, minute, 0, 0);
	} else {
		const parts = dateToken.split("-").map(Number);
		expectedYear = parts[0];
		expectedMonth = parts[1] - 1;
		expectedDay = parts[2];
		target = new Date(expectedYear, expectedMonth, expectedDay, hour, minute, 0, 0);
		if (target.getFullYear() !== expectedYear || target.getMonth() !== expectedMonth || target.getDate() !== expectedDay) return { error: "Schedule date is invalid." };
	}
	if (target.getFullYear() !== expectedYear || target.getMonth() !== expectedMonth || target.getDate() !== expectedDay || target.getHours() !== hour || target.getMinutes() !== minute) return { error: "Schedule time does not exist in the local timezone." };
	if (!prompt) return { error: "Schedule prompt is required." };
	const runAtEpoch = target.getTime() / 1e3;
	if (!Number.isFinite(runAtEpoch) || runAtEpoch <= now.getTime() / 1e3) return { error: "Schedule time must be in the future." };
	return {
		runAtEpoch,
		runAtLabel: `${target.toLocaleDateString([], {
			year: "numeric",
			month: "short",
			day: "numeric"
		})} ${formatClockTime12Hour(target)}`,
		prompt
	};
}
var BROKEN_CHAT_AFTER_SECONDS, CHATGPT_RICH_START, CHATGPT_RICH_END, CHATGPT_RICH_SEPARATOR, TOOL_UI_NOISE;
var init_clientLogic = __esmMin((() => {
	BROKEN_CHAT_AFTER_SECONDS = 2400;
	CHATGPT_RICH_START = "";
	CHATGPT_RICH_END = "";
	CHATGPT_RICH_SEPARATOR = "";
	TOOL_UI_NOISE = /^(?:open tool call list|close tool call list|tool|tool call|expand|collapse|cot-v5-[\w-]+)$/i;
}));
//#endregion
//#region src/prompta/ui/recentChatCache.ts
var DATABASE_NAME, DATABASE_VERSION, STORE_NAME, ACCESSED_AT_INDEX_NAME, SUMMARY_STORE_NAME, SUMMARY_LIMIT, RecentChatCache;
var init_recentChatCache = __esmMin((() => {
	DATABASE_NAME = "prompta-recent-chats";
	DATABASE_VERSION = 3;
	STORE_NAME = "chats";
	ACCESSED_AT_INDEX_NAME = "scope-accessed-at";
	SUMMARY_STORE_NAME = "summaries";
	SUMMARY_LIMIT = 200;
	RecentChatCache = class {
		scope;
		limit;
		memory = /* @__PURE__ */ new Map();
		databasePromise = null;
		constructor(scope, limit = 20) {
			this.scope = scope;
			this.limit = limit;
		}
		getMemory(conversationId) {
			const chat = this.memory.get(conversationId);
			if (!chat) return null;
			this.memory.delete(conversationId);
			this.memory.set(conversationId, chat);
			return chat;
		}
		async get(conversationId) {
			const memoryChat = this.getMemory(conversationId);
			if (memoryChat) return memoryChat;
			const database = await this.database();
			if (!database) return null;
			const record = await new Promise((resolve) => {
				const request = database.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).get(this.key(conversationId));
				request.onsuccess = () => resolve(request.result || null);
				request.onerror = () => resolve(null);
			});
			if (!record?.chat || record.scope !== this.scope) return null;
			this.rememberMemory(conversationId, record.chat);
			this.persist(record.chat);
			return record.chat;
		}
		remember(chat) {
			const conversationId = String(chat?.id || "");
			if (!conversationId) return;
			this.rememberMemory(conversationId, chat);
			this.persist(chat);
		}
		rememberSummaries(chats) {
			const summaries = chats.filter((chat) => String(chat?.id || "")).slice(0, SUMMARY_LIMIT);
			this.persistSummaries(summaries);
		}
		async warmSummaries() {
			const database = await this.database();
			if (!database) return [];
			return (await new Promise((resolve) => {
				const request = database.transaction(SUMMARY_STORE_NAME, "readonly").objectStore(SUMMARY_STORE_NAME).getAll();
				request.onsuccess = () => resolve(request.result || []);
				request.onerror = () => resolve([]);
			})).filter((record) => record.scope === this.scope && record.chat).sort((left, right) => left.position - right.position).slice(0, SUMMARY_LIMIT).map((record) => record.chat);
		}
		async warm() {
			const database = await this.database();
			if (!database) return [];
			const chats = (await new Promise((resolve) => {
				const request = database.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).getAll();
				request.onsuccess = () => resolve(request.result || []);
				request.onerror = () => resolve([]);
			})).filter((record) => record.scope === this.scope && record.chat).sort((left, right) => right.accessedAt - left.accessedAt).slice(0, this.limit).map((record) => record.chat);
			for (const chat of chats) {
				const conversationId = String(chat?.id || "");
				if (conversationId) this.rememberMemory(conversationId, chat);
			}
			return chats;
		}
		async remove(conversationId) {
			this.memory.delete(conversationId);
			const database = await this.database();
			if (!database) return;
			await new Promise((resolve) => {
				const transaction = database.transaction([STORE_NAME, SUMMARY_STORE_NAME], "readwrite");
				transaction.objectStore(STORE_NAME).delete(this.key(conversationId));
				transaction.objectStore(SUMMARY_STORE_NAME).delete(this.key(conversationId));
				transaction.oncomplete = () => resolve();
				transaction.onerror = () => resolve();
				transaction.onabort = () => resolve();
			});
		}
		rememberMemory(conversationId, chat) {
			this.memory.delete(conversationId);
			this.memory.set(conversationId, chat);
			while (this.memory.size > this.limit) {
				const oldest = this.memory.keys().next().value;
				if (!oldest) break;
				this.memory.delete(oldest);
			}
		}
		key(conversationId) {
			return this.scope + ":" + conversationId;
		}
		async persist(chat) {
			const conversationId = String(chat?.id || "");
			if (!conversationId) return;
			const database = await this.database();
			if (!database) return;
			await new Promise((resolve) => {
				const transaction = database.transaction(STORE_NAME, "readwrite");
				const store = transaction.objectStore(STORE_NAME);
				store.put({
					key: this.key(conversationId),
					scope: this.scope,
					conversationId,
					chat,
					accessedAt: Date.now()
				});
				const range = IDBKeyRange.bound([this.scope, 0], [this.scope, Number.MAX_SAFE_INTEGER]);
				const cursorRequest = store.index(ACCESSED_AT_INDEX_NAME).openKeyCursor(range, "prev");
				let retained = 0;
				cursorRequest.onsuccess = () => {
					const cursor = cursorRequest.result;
					if (!cursor) return;
					retained += 1;
					if (retained > this.limit) store.delete(cursor.primaryKey);
					cursor.continue();
				};
				transaction.oncomplete = () => resolve();
				transaction.onerror = () => resolve();
				transaction.onabort = () => resolve();
			});
		}
		async persistSummaries(chats) {
			const database = await this.database();
			if (!database) return;
			const retainedIds = new Set(chats.map((chat) => String(chat.id)));
			await new Promise((resolve) => {
				const transaction = database.transaction(SUMMARY_STORE_NAME, "readwrite");
				const store = transaction.objectStore(SUMMARY_STORE_NAME);
				const allRequest = store.getAll();
				allRequest.onsuccess = () => {
					for (const record of allRequest.result || []) if (record.scope === this.scope && !retainedIds.has(String(record.conversationId || ""))) store.delete(record.key);
					chats.forEach((chat, position) => {
						const conversationId = String(chat.id);
						store.put({
							key: this.key(conversationId),
							scope: this.scope,
							conversationId,
							chat,
							position
						});
					});
				};
				transaction.oncomplete = () => resolve();
				transaction.onerror = () => resolve();
				transaction.onabort = () => resolve();
			});
		}
		database() {
			if (this.databasePromise) return this.databasePromise;
			this.databasePromise = new Promise((resolve) => {
				if (!("indexedDB" in globalThis)) {
					resolve(null);
					return;
				}
				let request;
				try {
					request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
				} catch {
					resolve(null);
					return;
				}
				request.onupgradeneeded = (event) => {
					const database = request.result;
					const transaction = request.transaction;
					const chatStore = database.objectStoreNames.contains(STORE_NAME) ? transaction?.objectStore(STORE_NAME) : database.createObjectStore(STORE_NAME, { keyPath: "key" });
					if (chatStore && !chatStore.indexNames.contains(ACCESSED_AT_INDEX_NAME)) chatStore.createIndex(ACCESSED_AT_INDEX_NAME, ["scope", "accessedAt"]);
					if (chatStore && event.oldVersion > 0 && event.oldVersion < DATABASE_VERSION) chatStore.clear();
					if (!database.objectStoreNames.contains(SUMMARY_STORE_NAME)) database.createObjectStore(SUMMARY_STORE_NAME, { keyPath: "key" });
				};
				request.onsuccess = () => {
					const database = request.result;
					database.onversionchange = () => database.close();
					resolve(database);
				};
				request.onerror = () => resolve(null);
			});
			return this.databasePromise;
		}
	};
}));
//#endregion
//#region src/prompta/ui/domPatch.ts
function domPatchKey$2(node) {
	if (!(node instanceof HTMLElement)) return "";
	return node.dataset.domKey || "";
}
function patchDomNode$2(current, next) {
	if (current.nodeType !== next.nodeType || current instanceof Element && next instanceof Element && current.tagName !== next.tagName) {
		const replacement = next.cloneNode(true);
		const parent = current.parentNode;
		if (!parent) return current;
		parent.replaceChild(replacement, current);
		return replacement;
	}
	if (current.nodeType === Node.TEXT_NODE && next.nodeType === Node.TEXT_NODE) {
		if (current.textContent !== next.textContent) current.textContent = next.textContent;
		return current;
	}
	if (!(current instanceof Element) || !(next instanceof Element)) return current;
	for (const attribute of Array.from(current.attributes)) if (!next.hasAttribute(attribute.name)) current.removeAttribute(attribute.name);
	for (const attribute of Array.from(next.attributes)) if (current.getAttribute(attribute.name) !== attribute.value) current.setAttribute(attribute.name, attribute.value);
	patchDomChildren$2(current, next);
	return current;
}
function patchDomChildren$2(currentParent, nextParent) {
	let index = 0;
	while (index < nextParent.childNodes.length || index < currentParent.childNodes.length) {
		let current = currentParent.childNodes[index];
		const next = nextParent.childNodes[index];
		if (!next) {
			current.remove();
			continue;
		}
		if (!current) {
			currentParent.append(next.cloneNode(true));
			index += 1;
			continue;
		}
		const nextKey = domPatchKey$2(next);
		if (nextKey && domPatchKey$2(current) !== nextKey) {
			const match = Array.from(currentParent.childNodes).slice(index + 1).find((candidate) => domPatchKey$2(candidate) === nextKey);
			if (match) {
				currentParent.insertBefore(match, current);
				current = match;
			} else {
				currentParent.insertBefore(next.cloneNode(true), current);
				index += 1;
				continue;
			}
		}
		patchDomNode$2(current, next);
		index += 1;
	}
}
function patchHtmlChildren$2(element, html) {
	const template = document.createElement("template");
	template.innerHTML = html;
	patchDomChildren$2(element, template.content);
}
var init_domPatch = __esmMin((() => {}));
//#endregion
//#region src/prompta/ui/jobsDialog.ts
function requiredElement$6(selector) {
	const element = document.querySelector(selector);
	if (!element) throw new Error(`Missing required jobs UI element: ${selector}`);
	return element;
}
function escapeHtml$4(value) {
	return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll("\"", "&quot;").replaceAll("'", "&#039;");
}
function setTextIfChanged$4(element, value) {
	const text = String(value ?? "");
	if (element.textContent !== text) element.textContent = text;
}
function renderJobPrompt(promptValue) {
	const prompt = String(promptValue ?? "").trim();
	const escapedPrompt = escapeHtml$4(prompt);
	if (prompt.length <= JOB_PROMPT_PREVIEW_LIMIT && !prompt.includes("\n")) return `<div class="job-row-prompt">${escapedPrompt}</div>`;
	return `
    <details class="job-prompt-details">
      <summary class="job-prompt-summary">
        <span class="job-prompt-preview" aria-hidden="true">${escapedPrompt}</span>
        <span class="job-prompt-toggle-label">
          <span class="job-prompt-show">Show full prompt</span>
          <span class="job-prompt-hide">Hide prompt</span>
        </span>
      </summary>
      <div class="job-row-prompt job-row-prompt-full">${escapedPrompt}</div>
    </details>
  `;
}
async function fetchJson$1(url, timeoutMs = 1e4) {
	const controller = new AbortController();
	const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
	try {
		const response = await fetch(url, {
			cache: "no-store",
			signal: controller.signal
		});
		if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
		return await response.json();
	} finally {
		window.clearTimeout(timeout);
	}
}
function formatJobMinutes(value) {
	const minutes = Number(value);
	if (!Number.isFinite(minutes)) return "";
	if (minutes >= 60 && minutes % 60 === 0) {
		const hours = minutes / 60;
		return `${hours} hour${hours === 1 ? "" : "s"}`;
	}
	return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}
function jobScheduleText(job) {
	if (job.run_at_epoch) {
		const date = /* @__PURE__ */ new Date(Number(job.run_at_epoch) * 1e3);
		return `once · ${date.toLocaleDateString([], {
			year: "numeric",
			month: "short",
			day: "numeric"
		})} ${formatClockTime12Hour(date)}`;
	}
	if (job.daily_at) return `daily · ${formatDailyTime12Hour(job.daily_at)}`;
	return `every ${formatJobMinutes(job.interval_minutes)}${job.exact_interval ? " · exact" : ""}`;
}
function createJobsDialog({ closeSidebar, resizeComposer, syncSendButton }) {
	const els = {
		jobsSidebarButton: requiredElement$6("#jobsSidebarButton"),
		jobsDialog: requiredElement$6("#jobsDialog"),
		closeJobsDialog: requiredElement$6("#closeJobsDialog"),
		jobsDialogStatus: requiredElement$6("#jobsDialogStatus"),
		jobsList: requiredElement$6("#jobsList"),
		jobsForm: requiredElement$6("#jobsForm"),
		jobsFormTitle: requiredElement$6("#jobsFormTitle"),
		jobNameInput: requiredElement$6("#jobNameInput"),
		jobPromptInput: requiredElement$6("#jobPromptInput"),
		jobScheduleType: requiredElement$6("#jobScheduleType"),
		jobIntervalField: requiredElement$6("#jobIntervalField"),
		jobIntervalInput: requiredElement$6("#jobIntervalInput"),
		jobDailyField: requiredElement$6("#jobDailyField"),
		jobDailyInput: requiredElement$6("#jobDailyInput"),
		jobExactField: requiredElement$6("#jobExactField"),
		jobExactInput: requiredElement$6("#jobExactInput"),
		resetJobForm: requiredElement$6("#resetJobForm"),
		saveJobButton: requiredElement$6("#saveJobButton"),
		clearJobsButton: requiredElement$6("#clearJobsButton"),
		messageInput: requiredElement$6("#messageInput"),
		slashMenu: requiredElement$6("#slashMenu")
	};
	let scheduledJobs = [];
	const mobileJobsScreen = window.matchMedia("(max-width: 600px)");
	const appShell = document.querySelector(".app-shell");
	function closeJobsView() {
		if (!els.jobsDialog.open) return;
		els.jobsDialog.close();
	}
	function resetJobForm() {
		els.jobsForm.reset();
		setTextIfChanged$4(els.jobsFormTitle, "Add job");
		els.jobNameInput.readOnly = false;
		els.jobScheduleType.value = "interval";
		els.jobIntervalInput.value = "40";
		els.jobDailyInput.value = "09:00";
		els.jobExactInput.checked = false;
		syncJobScheduleFields();
	}
	function syncJobScheduleFields() {
		const daily = els.jobScheduleType.value === "daily";
		els.jobIntervalField.hidden = daily;
		els.jobDailyField.hidden = !daily;
		els.jobExactField.hidden = daily;
	}
	function renderJobs(jobs) {
		scheduledJobs = Array.isArray(jobs) ? jobs : [];
		els.clearJobsButton.disabled = scheduledJobs.length === 0;
		if (!scheduledJobs.length) {
			patchHtmlChildren$2(els.jobsList, "<div class=\"jobs-empty\">No scheduled jobs.</div>");
			return;
		}
		patchHtmlChildren$2(els.jobsList, scheduledJobs.map((job) => {
			const paused = Boolean(job.paused);
			const canEdit = !job.run_at_epoch;
			return `
        <article class="job-row" data-job-name="${escapeHtml$4(job.name)}">
          <div class="job-row-top">
            <div>
              <div class="job-row-name">${escapeHtml$4(job.name)}</div>
              <div class="job-row-meta">${escapeHtml$4(jobScheduleText(job))}</div>
            </div>
            <span class="job-status">${escapeHtml$4(job.status || (paused ? "paused" : "pending"))}</span>
          </div>
          ${renderJobPrompt(job.prompt)}
          <div class="job-row-actions">
            ${canEdit ? "<button type=\"button\" class=\"job-action\" data-job-action=\"edit\">Edit</button>" : ""}
            <button type="button" class="job-action" data-job-action="${paused ? "resume" : "pause"}">${paused ? "Resume" : "Pause"}</button>
            <button type="button" class="job-action" data-job-action="remove">Remove</button>
          </div>
        </article>
      `;
		}).join(""));
	}
	async function loadJobs() {
		setTextIfChanged$4(els.jobsDialogStatus, "Loading jobs…");
		try {
			const result = await fetchJson$1("api/jobs");
			renderJobs(result.jobs);
			setTextIfChanged$4(els.jobsDialogStatus, `${result.jobs?.length || 0} configured job${result.jobs?.length === 1 ? "" : "s"}.`);
		} catch (error) {
			setTextIfChanged$4(els.jobsDialogStatus, `Could not load jobs: ${String(error).replace(/^Error:\s*/, "")}`);
		}
	}
	async function runJobCommand(payload, successText) {
		setTextIfChanged$4(els.jobsDialogStatus, "Running Prompta CLI command…");
		els.saveJobButton.disabled = true;
		try {
			const result = await postJsonRequest("api/jobs", payload);
			renderJobs(result.jobs);
			const command = Array.isArray(result.command) ? result.command.join(" ") : "";
			setTextIfChanged$4(els.jobsDialogStatus, command ? `${successText} · ${command}` : successText);
			return true;
		} catch (error) {
			setTextIfChanged$4(els.jobsDialogStatus, `Jobs command failed: ${String(error).replace(/^Error:\s*/, "")}`);
			return false;
		} finally {
			els.saveJobButton.disabled = false;
		}
	}
	async function open(clearComposer = false) {
		if (clearComposer) {
			els.messageInput.value = "";
			els.slashMenu.hidden = true;
			resizeComposer();
			syncSendButton();
		}
		resetJobForm();
		if (!els.jobsDialog.open) {
			const stacked = mobileJobsScreen.matches;
			els.jobsDialog.dataset.presentation = stacked ? "stack" : "modal";
			if (stacked) {
				els.jobsDialog.show();
				if (appShell) appShell.inert = true;
			} else els.jobsDialog.showModal();
		}
		await loadJobs();
	}
	els.jobsSidebarButton.addEventListener("click", async () => {
		closeSidebar();
		await open();
	});
	els.closeJobsDialog.addEventListener("click", closeJobsView);
	els.jobsDialog.addEventListener("click", (event) => {
		if (event.target === els.jobsDialog && els.jobsDialog.dataset.presentation !== "stack") closeJobsView();
	});
	els.jobsDialog.addEventListener("close", () => {
		if (appShell) appShell.inert = false;
		delete els.jobsDialog.dataset.presentation;
	});
	els.jobScheduleType.addEventListener("change", syncJobScheduleFields);
	els.resetJobForm.addEventListener("click", resetJobForm);
	els.jobsForm.addEventListener("submit", async (event) => {
		event.preventDefault();
		const daily = els.jobScheduleType.value === "daily";
		const payload = {
			action: "add",
			name: els.jobNameInput.value.trim(),
			prompt: els.jobPromptInput.value.trim(),
			daily_at: daily ? els.jobDailyInput.value : "",
			interval_minutes: daily ? null : Number(els.jobIntervalInput.value),
			exact_interval: !daily && els.jobExactInput.checked
		};
		if (await runJobCommand(payload, `Saved ${payload.name}`)) resetJobForm();
	});
	els.jobsList.addEventListener("click", async (event) => {
		const button = event.target.closest("[data-job-action]");
		const row = button?.closest("[data-job-name]");
		if (!button || !row) return;
		const name = String(row.dataset.jobName || "");
		const job = scheduledJobs.find((item) => item.name === name);
		if (!job) return;
		const action = String(button.dataset.jobAction || "");
		if (action === "edit") {
			setTextIfChanged$4(els.jobsFormTitle, `Edit ${job.name}`);
			els.jobNameInput.value = job.name;
			els.jobNameInput.readOnly = true;
			els.jobPromptInput.value = job.prompt || "";
			els.jobScheduleType.value = job.daily_at ? "daily" : "interval";
			els.jobDailyInput.value = job.daily_at || "09:00";
			els.jobIntervalInput.value = String(job.interval_minutes || 40);
			els.jobExactInput.checked = Boolean(job.exact_interval);
			syncJobScheduleFields();
			els.jobPromptInput.focus();
			return;
		}
		await runJobCommand({
			action,
			name
		}, `${action === "remove" ? "Removed" : action === "pause" ? "Paused" : "Resumed"} ${name}`);
	});
	els.clearJobsButton.addEventListener("click", async () => {
		if (!scheduledJobs.length) return;
		if (!window.confirm(`Clear all ${scheduledJobs.length} scheduled jobs?`)) return;
		if (await runJobCommand({ action: "clear" }, "Cleared all scheduled jobs")) resetJobForm();
	});
	function close() {
		closeJobsView();
	}
	return {
		open,
		close
	};
}
var JOB_PROMPT_PREVIEW_LIMIT;
var init_jobsDialog = __esmMin((() => {
	init_clientLogic();
	init_domPatch();
	JOB_PROMPT_PREVIEW_LIMIT = 220;
}));
//#endregion
//#region src/prompta/ui/sidebar.ts
function requiredElement$5(selector) {
	const element = document.querySelector(selector);
	if (!element) throw new Error(`Missing required sidebar UI element: ${selector}`);
	return element;
}
function createSidebar({ onMotionEnd }) {
	const els = {
		sidebar: requiredElement$5("#sidebar"),
		openSidebar: requiredElement$5("#openSidebar"),
		closeSidebar: requiredElement$5("#closeSidebar"),
		sidebarScrim: requiredElement$5("#sidebarScrim"),
		mainPanel: requiredElement$5(".main-panel")
	};
	const mobileSidebarMedia = window.matchMedia("(max-width: 780px)");
	const swipe = {
		startX: 0,
		startY: 0,
		lastX: 0,
		lastTime: 0,
		velocityX: 0,
		sidebarWidth: 0,
		progress: 0,
		wasOpen: false,
		tracking: false,
		directionLocked: false,
		horizontal: false,
		frameId: 0,
		pendingX: 0,
		cleanupTimer: 0
	};
	let moving = false;
	function isOpen() {
		return els.sidebar.classList.contains("is-open");
	}
	function isMoving() {
		return moving;
	}
	function beginMotion() {
		moving = true;
	}
	function endMotion() {
		if (!moving) return;
		moving = false;
		syncSidebarVisibility();
		onMotionEnd();
	}
	function mobileEnabled() {
		return mobileSidebarMedia.matches;
	}
	function sidebarHidden() {
		return mobileSidebarMedia.matches && !isOpen();
	}
	function syncExpandedState() {
		els.openSidebar.setAttribute("aria-expanded", String(!sidebarHidden()));
	}
	function syncSidebarVisibility() {
		const hidden = sidebarHidden();
		const backgroundBlocked = mobileEnabled() && isOpen();
		els.sidebar.toggleAttribute("inert", hidden);
		els.mainPanel.toggleAttribute("inert", backgroundBlocked);
		if (hidden) els.sidebar.setAttribute("aria-hidden", "true");
		else els.sidebar.removeAttribute("aria-hidden");
	}
	function syncAccessibility() {
		syncExpandedState();
		syncSidebarVisibility();
	}
	function resetDragStyles() {
		if (swipe.frameId) {
			cancelAnimationFrame(swipe.frameId);
			swipe.frameId = 0;
		}
		if (swipe.cleanupTimer) {
			clearTimeout(swipe.cleanupTimer);
			swipe.cleanupTimer = 0;
		}
		els.sidebar.style.removeProperty("transition");
		els.sidebar.style.removeProperty("transform");
		els.sidebarScrim.style.removeProperty("transition");
		els.sidebarScrim.style.removeProperty("opacity");
		endMotion();
	}
	function open() {
		resetDragStyles();
		if (mobileEnabled() && !isOpen()) beginMotion();
		els.sidebar.classList.add("is-open");
		els.sidebarScrim.classList.add("is-open");
		syncAccessibility();
	}
	function close(restoreFocus = false) {
		resetDragStyles();
		if (mobileEnabled() && isOpen()) beginMotion();
		const shouldRestoreFocus = restoreFocus && mobileEnabled() && isOpen();
		els.sidebar.classList.remove("is-open");
		els.sidebarScrim.classList.remove("is-open");
		syncAccessibility();
		if (shouldRestoreFocus) requestAnimationFrame(() => els.openSidebar.focus({ preventScroll: true }));
	}
	function applyDragPosition(x) {
		const width = swipe.sidebarWidth || els.sidebar.getBoundingClientRect().width;
		swipe.progress = Math.max(0, Math.min(1, 1 + x / width));
		els.sidebar.style.transform = `translate3d(${x}px, 0, 0)`;
		els.sidebarScrim.style.opacity = String(swipe.progress);
	}
	function queueDragPosition(x) {
		swipe.pendingX = x;
		if (swipe.frameId) return;
		swipe.frameId = requestAnimationFrame(() => {
			swipe.frameId = 0;
			applyDragPosition(swipe.pendingX);
		});
	}
	function settleDrag(opened) {
		const width = swipe.sidebarWidth || els.sidebar.getBoundingClientRect().width;
		if (swipe.frameId) {
			cancelAnimationFrame(swipe.frameId);
			swipe.frameId = 0;
			applyDragPosition(swipe.pendingX);
		}
		const currentX = -width * (1 - swipe.progress);
		const targetX = opened ? 0 : -width;
		const remaining = Math.abs(targetX - currentX);
		const speed = Math.max(.6, Math.abs(swipe.velocityX));
		const duration = Math.max(90, Math.min(180, Math.round(remaining / speed)));
		els.sidebar.classList.toggle("is-open", opened);
		els.sidebarScrim.classList.toggle("is-open", opened);
		syncAccessibility();
		els.sidebar.style.transition = `transform ${duration}ms cubic-bezier(0.2, 0, 0, 1)`;
		els.sidebar.style.transform = `translate3d(${targetX}px, 0, 0)`;
		els.sidebarScrim.style.transition = `opacity ${duration}ms linear`;
		els.sidebarScrim.style.opacity = opened ? "1" : "0";
		if (swipe.cleanupTimer) clearTimeout(swipe.cleanupTimer);
		swipe.cleanupTimer = window.setTimeout(() => {
			swipe.cleanupTimer = 0;
			els.sidebar.style.removeProperty("transition");
			els.sidebar.style.removeProperty("transform");
			els.sidebarScrim.style.removeProperty("transition");
			els.sidebarScrim.style.removeProperty("opacity");
			endMotion();
		}, duration + 30);
	}
	els.openSidebar.addEventListener("click", () => {
		open();
		if (mobileEnabled()) requestAnimationFrame(() => els.closeSidebar.focus({ preventScroll: true }));
	});
	els.closeSidebar.addEventListener("click", () => close(true));
	els.sidebarScrim.addEventListener("click", () => close());
	mobileSidebarMedia.addEventListener("change", syncAccessibility);
	window.addEventListener("resize", syncAccessibility);
	syncAccessibility();
	els.sidebar.addEventListener("transitionrun", (event) => {
		if (event.propertyName === "transform" && mobileEnabled()) beginMotion();
	});
	els.sidebar.addEventListener("transitionend", (event) => {
		if (event.propertyName === "transform") endMotion();
	});
	els.sidebar.addEventListener("transitioncancel", (event) => {
		if (event.propertyName === "transform") endMotion();
	});
	document.addEventListener("touchstart", (event) => {
		if (!mobileEnabled() || event.touches.length !== 1) return;
		resetDragStyles();
		const touch = event.touches[0];
		const sidebarOpen = isOpen();
		if (!sidebarOpen && touch.clientX > 144) return;
		swipe.startX = touch.clientX;
		swipe.startY = touch.clientY;
		swipe.lastX = touch.clientX;
		swipe.lastTime = performance.now();
		swipe.velocityX = 0;
		swipe.sidebarWidth = els.sidebar.getBoundingClientRect().width;
		swipe.progress = sidebarOpen ? 1 : 0;
		swipe.wasOpen = sidebarOpen;
		swipe.tracking = true;
		swipe.directionLocked = false;
		swipe.horizontal = false;
		swipe.pendingX = sidebarOpen ? 0 : -swipe.sidebarWidth;
	}, { passive: true });
	document.addEventListener("touchmove", (event) => {
		if (!swipe.tracking || event.touches.length !== 1) return;
		const touch = event.touches[0];
		const deltaX = touch.clientX - swipe.startX;
		const deltaY = touch.clientY - swipe.startY;
		if (!swipe.directionLocked && (Math.abs(deltaX) > 8 || Math.abs(deltaY) > 8)) {
			swipe.directionLocked = true;
			swipe.horizontal = Math.abs(deltaX) > Math.abs(deltaY) * 1.15;
			if (swipe.horizontal) {
				beginMotion();
				els.sidebar.style.transition = "none";
				els.sidebarScrim.style.transition = "none";
			}
		}
		if (!swipe.horizontal) return;
		event.preventDefault();
		const width = swipe.sidebarWidth;
		const startX = swipe.wasOpen ? 0 : -width;
		const x = Math.max(-width, Math.min(0, startX + deltaX));
		const now = performance.now();
		const elapsed = Math.max(1, now - swipe.lastTime);
		swipe.velocityX = (touch.clientX - swipe.lastX) / elapsed;
		swipe.lastX = touch.clientX;
		swipe.lastTime = now;
		queueDragPosition(x);
	}, { passive: false });
	document.addEventListener("touchend", () => {
		if (!swipe.tracking) return;
		if (swipe.horizontal) {
			const fastOpen = swipe.velocityX > .35;
			const fastClose = swipe.velocityX < -.35;
			settleDrag(fastOpen || !fastClose && swipe.progress >= .5);
		}
		swipe.tracking = false;
	}, { passive: true });
	document.addEventListener("touchcancel", () => {
		if (swipe.tracking && swipe.horizontal) settleDrag(swipe.wasOpen);
		swipe.tracking = false;
	}, { passive: true });
	return {
		open,
		close,
		isMoving
	};
}
var init_sidebar = __esmMin((() => {}));
//#endregion
//#region src/prompta/ui/markdown.ts
function escapeHtml$3(value) {
	return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll("\"", "&quot;").replaceAll("'", "&#039;");
}
function normalizeLanguage(language) {
	const raw = String(language || "").trim().toLowerCase().split(/\s+/)[0];
	return LANGUAGE_ALIASES[raw] || raw || "code";
}
function syntaxToken(className, value) {
	return `<span class="syntax-${className}">${escapeHtml$3(value)}</span>`;
}
function highlightCode(raw, language) {
	const source = String(raw || "");
	const normalized = normalizeLanguage(language);
	const keywords = CODE_KEYWORDS[normalized] || /* @__PURE__ */ new Set();
	const sql = normalized === "sql";
	const hashComments = [
		"python",
		"bash",
		"yaml"
	].includes(normalized);
	let html = "";
	let index = 0;
	while (index < source.length) {
		if (normalized === "markup" && source.startsWith("<!--", index)) {
			const end = source.indexOf("-->", index + 4);
			const next = end < 0 ? source.length : end + 3;
			html += syntaxToken("comment", source.slice(index, next));
			index = next;
			continue;
		}
		if (source.startsWith("/*", index)) {
			const end = source.indexOf("*/", index + 2);
			const next = end < 0 ? source.length : end + 2;
			html += syntaxToken("comment", source.slice(index, next));
			index = next;
			continue;
		}
		if (source.startsWith("//", index) && normalized !== "json") {
			const end = source.indexOf("\n", index + 2);
			const next = end < 0 ? source.length : end;
			html += syntaxToken("comment", source.slice(index, next));
			index = next;
			continue;
		}
		if (hashComments && source[index] === "#") {
			const end = source.indexOf("\n", index + 1);
			const next = end < 0 ? source.length : end;
			html += syntaxToken("comment", source.slice(index, next));
			index = next;
			continue;
		}
		const quote = source[index];
		if (quote === "\"" || quote === "'" || quote === "`") {
			let cursor = index + 1;
			while (cursor < source.length) {
				if (source[cursor] === "\\") {
					cursor += 2;
					continue;
				}
				if (source[cursor] === quote) {
					cursor += 1;
					break;
				}
				cursor += 1;
			}
			const value = source.slice(index, cursor);
			const property = normalized === "json" && /^\s*:/.test(source.slice(cursor));
			html += syntaxToken(property ? "property" : "string", value);
			index = cursor;
			continue;
		}
		const number = source.slice(index).match(/^-?(?:0x[\da-f]+|0b[01]+|\d+(?:\.\d+)?(?:e[+-]?\d+)?)/i);
		if (number) {
			html += syntaxToken("number", number[0]);
			index += number[0].length;
			continue;
		}
		if (/[A-Za-z_$]/.test(source[index])) {
			let cursor = index + 1;
			while (/[A-Za-z0-9_$]/.test(source[cursor] || "")) cursor += 1;
			const value = source.slice(index, cursor);
			const lookup = sql ? value.toUpperCase() : value;
			if (keywords.has(lookup)) html += syntaxToken("keyword", value);
			else if (/^\s*\(/.test(source.slice(cursor))) html += syntaxToken("function", value);
			else html += escapeHtml$3(value);
			index = cursor;
			continue;
		}
		html += /[[\]{}(),.:;]/.test(source[index]) ? syntaxToken("punctuation", source[index]) : escapeHtml$3(source[index]);
		index += 1;
	}
	return html;
}
function inlineMarkdown(text) {
	const placeholders = [];
	let source = String(text || "");
	const stash = (html) => {
		let token = `\uE000PROMPTA_INLINE_${placeholders.length}\uE001`;
		while (source.includes(token)) token += "";
		placeholders.push([token, html]);
		return token;
	};
	source = replaceChatGptRichMarkers(source, (label, url) => stash(`<a href="${escapeHtml$3(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml$3(label)}</a>`));
	source = source.replace(/`([^`\n]+)`/g, (_, code) => stash(`<code class="inline-code">${escapeHtml$3(code)}</code>`));
	source = source.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)(?:\s+"[^"]*")?\)/g, (_, label, url) => stash(`<a href="${escapeHtml$3(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml$3(label)}</a>`));
	let html = escapeHtml$3(source);
	html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
	html = html.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
	html = html.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
	html = html.replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,!?:;])/g, "$1<em>$2</em>");
	for (const [token, value] of placeholders) html = html.replaceAll(token, value);
	return html;
}
function splitTableRow(line) {
	return line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
}
function renderListItem(content) {
	const task = content.match(/^\[([ xX])\]\s+(.+)$/);
	if (!task) return `<li>${inlineMarkdown(content)}</li>`;
	return `<li class="task-item"><input type="checkbox" disabled${task[1].toLowerCase() === "x" ? " checked" : ""}> <span>${inlineMarkdown(task[2])}</span></li>`;
}
function listLine(line) {
	const match = line.match(/^(\s*)([-+*]|\d+[.)])\s+(.+)$/);
	if (!match) return null;
	return {
		indent: match[1].replace(/\t/g, "    ").length,
		ordered: /^\d/.test(match[2]),
		content: match[3]
	};
}
function renderListBlock(lines, startIndex, baseIndent = null) {
	const first = listLine(lines[startIndex]);
	if (!first) return {
		html: "",
		index: startIndex
	};
	const indent = baseIndent ?? first.indent;
	const ordered = first.ordered;
	const tag = ordered ? "ol" : "ul";
	const items = [];
	let index = startIndex;
	while (index < lines.length) {
		const current = listLine(lines[index]);
		if (!current || current.indent < indent) break;
		if (current.indent === indent && current.ordered !== ordered) break;
		if (current.indent > indent) {
			if (!items.length) break;
			const nested = renderListBlock(lines, index, current.indent);
			if (!nested.html || nested.index === index) break;
			items[items.length - 1] = items[items.length - 1].replace(/<\/li>$/, `${nested.html}</li>`);
			index = nested.index;
			continue;
		}
		items.push(renderListItem(current.content));
		index += 1;
	}
	return {
		html: `<${tag}>${items.join("")}</${tag}>`,
		index
	};
}
function renderTextBlock(text) {
	const lines = String(text || "").replace(/\r/g, "").split("\n");
	const out = [];
	let index = 0;
	const startsBlock = (line, next = "") => !line.trim() || /^(#{1,6})\s+/.test(line) || /^\s*([-+*]|\d+[.)])\s+/.test(line) || /^\s*>\s?/.test(line) || /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line) || line.includes("|") && /^\s*\|?\s*:?-{3,}/.test(next);
	while (index < lines.length) {
		const line = lines[index];
		const next = lines[index + 1] || "";
		if (!line.trim()) {
			index += 1;
			continue;
		}
		const heading = line.match(/^(#{1,6})\s+(.+)$/);
		if (heading) {
			const level = heading[1].length;
			out.push(`<h${level}>${inlineMarkdown(heading[2].replace(/\s+#+\s*$/, ""))}</h${level}>`);
			index += 1;
			continue;
		}
		if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
			out.push("<hr>");
			index += 1;
			continue;
		}
		if (line.includes("|") && /^\s*\|?\s*:?-{3,}/.test(next)) {
			const headers = splitTableRow(line);
			const aligns = splitTableRow(next).map((cell) => {
				const left = cell.startsWith(":");
				const right = cell.endsWith(":");
				return left && right ? "center" : right ? "right" : left ? "left" : "";
			});
			index += 2;
			const rows = [];
			while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
				rows.push(splitTableRow(lines[index]));
				index += 1;
			}
			const tableScrollClass = headers.length >= 3 ? "table-scroll table-scroll-wide" : "table-scroll";
			out.push(`<div class="${tableScrollClass}"><table><thead><tr>${headers.map((cell, column) => `<th${aligns[column] ? ` style="text-align:${aligns[column]}"` : ""}>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${headers.map((_, column) => `<td${aligns[column] ? ` style="text-align:${aligns[column]}"` : ""}>${inlineMarkdown(row[column] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
			continue;
		}
		if (/^\s*>\s?/.test(line)) {
			const quoted = [];
			while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
				quoted.push(lines[index].replace(/^\s*>\s?/, ""));
				index += 1;
			}
			out.push(`<blockquote>${renderTextBlock(quoted.join("\n"))}</blockquote>`);
			continue;
		}
		if (listLine(line)) {
			const rendered = renderListBlock(lines, index);
			out.push(rendered.html);
			index = rendered.index;
			continue;
		}
		const paragraph = [line.trim()];
		index += 1;
		while (index < lines.length && !startsBlock(lines[index], lines[index + 1] || "")) {
			paragraph.push(lines[index].trim());
			index += 1;
		}
		out.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
	}
	return out.join("");
}
function expandedToolMetaAddsInformation(summary, action) {
	return Boolean(summary && action);
}
function renderDeferredToolCode(body) {
	return body.highlight ? highlightCode(body.code, body.language) : escapeHtml$3(body.code);
}
function renderCodeBlock(code, language, deferredToolBodies = null) {
	const rawLanguage = String(language || "").trim();
	const normalized = normalizeLanguage(rawLanguage);
	const toolMatch = rawLanguage.match(/^(?:tool|tool-call|function|function-call)(?::\s*(.+))?$/i);
	const inlineToolMatch = code.match(/^\s*(?:tool|function|to)\s*[:=]\s*([\w.-]+)/i);
	const toolish = Boolean(toolMatch || inlineToolMatch);
	const rawToolName = toolMatch?.[1]?.trim() || inlineToolMatch?.[1] || "";
	const toolName = toolCallDisplayName(rawToolName);
	const trimmedCode = code.trim();
	const genericToolInvocation = toolish && toolCallIsInvocationPlaceholder(trimmedCode);
	const hasUsefulToolDetail = !toolish || toolCallHasUsefulDetail(trimmedCode);
	if (toolish && !toolName && !hasUsefulToolDetail && !genericToolInvocation) return "";
	const pythonCode = toolish ? pythonToolCallCode(rawToolName, trimmedCode) : "";
	const toolSummary = toolish ? toolCallSummary(trimmedCode) : "";
	const toolTimestamp = toolish ? toolCallTimestampMillis(trimmedCode) : null;
	const toolTimeText = toolTimestamp === null ? "" : formatClockTime12Hour(toolTimestamp, true);
	const toolTime = toolTimestamp === null ? "" : `<time class="tool-time" datetime="${new Date(toolTimestamp).toISOString()}">${escapeHtml$3(toolTimeText)}</time>`;
	const renderedCode = pythonCode || (toolish && (!hasUsefulToolDetail || genericToolInvocation) ? "" : code);
	const highlightLanguage = pythonCode ? "python" : toolish ? trimmedCode.startsWith("{") || trimmedCode.startsWith("[") ? "json" : "code" : normalized;
	const label = pythonCode ? "python" : toolish ? "tool call" : rawLanguage || "code";
	const copyButton = renderedCode.trim() ? "<button type=\"button\" class=\"copy-code\">copy</button>" : "";
	const collapsedLabel = toolish && toolName ? toolName : label;
	const toolIdentityParts = toolName.split(/\s*·\s*/).filter(Boolean);
	const expandedAction = toolIdentityParts.length > 1 ? toolIdentityParts[toolIdentityParts.length - 1] : toolName;
	const expandedConnector = toolIdentityParts.length > 1 ? toolIdentityParts.slice(0, -1).join(" · ") : "";
	const inlineToolMeta = toolSummary && expandedAction ? `<span class="tool-inline-meta"><span class="tool-expanded-separator">|</span><span class="tool-expanded-action">${escapeHtml$3(expandedAction)}</span>${expandedConnector ? `<span class="tool-expanded-separator">|</span><span class="tool-expanded-connector">${escapeHtml$3(expandedConnector)}</span>` : ""}</span>` : "";
	const header = toolish ? toolSummary ? `<span class="tool-summary">${escapeHtml$3(toolSummary)}</span>${inlineToolMeta}${toolTime}` : `
        <span class="${toolName ? "tool-primary-name" : "code-language"}">${escapeHtml$3(collapsedLabel)}</span>
        ${toolTime}` : `
      <span class="code-language">${escapeHtml$3(label)}</span>
      ${copyButton}`;
	let deferredToolBodyIndex = -1;
	let body = "";
	if (renderedCode.trim()) {
		if (toolish && deferredToolBodies) {
			deferredToolBodyIndex = deferredToolBodies.push({
				code: renderedCode,
				language: highlightLanguage,
				highlight: Boolean(pythonCode)
			}) - 1;
			body = "<div class=\"deferred-tool-body\" aria-hidden=\"true\"></div>";
		} else {
			const renderedBody = pythonCode ? highlightCode(renderedCode, highlightLanguage) : toolish ? escapeHtml$3(renderedCode) : highlightCode(renderedCode, highlightLanguage);
			body = `<pre><code class="language-${escapeHtml$3(highlightLanguage)}">${renderedBody}</code></pre>`;
		}
	}
	if (toolish) {
		const expandedToolHeader = expandedToolMetaAddsInformation(toolSummary, expandedAction) ? `<div class="tool-expanded-meta"><span class="tool-expanded-action">${escapeHtml$3(expandedAction)}</span>${expandedConnector ? `<span class="tool-expanded-separator">|</span><span class="tool-expanded-connector">${escapeHtml$3(expandedConnector)}</span>` : ""}</div>` : "";
		const deferredAttribute = deferredToolBodyIndex < 0 ? "" : ` data-deferred-tool-body-index="${deferredToolBodyIndex}"`;
		return `
      <details class="code-block tool-call-block${toolSummary ? " tool-has-summary" : ""}${expandedToolHeader ? " tool-has-meta" : ""}"${deferredAttribute}>
        <summary class="code-header">${header}</summary>
        ${expandedToolHeader}
        ${body}
      </details>`;
	}
	return `
    <div class="code-block">
      <div class="code-header">${header}</div>
      ${body}
    </div>`;
}
function renderMarkdown(raw, deferredToolBodies = null, { renderIncompleteFence = false } = {}) {
	const source = String(raw || "");
	const pattern = /^ {0,3}```([^\n`]*)\r?\n([\s\S]*?)^ {0,3}```[ \t]*\r?$/gm;
	let lastIndex = 0;
	let html = "";
	let match;
	while ((match = pattern.exec(source)) !== null) {
		html += renderTextBlock(source.slice(lastIndex, match.index));
		const language = match[1].trim() || "code";
		const code = match[2].replace(/\n$/, "");
		html += renderCodeBlock(code, language, deferredToolBodies);
		lastIndex = pattern.lastIndex;
	}
	const remainder = source.slice(lastIndex);
	if (renderIncompleteFence) {
		const incompleteMatch = /^ {0,3}```([^\n`]*)(?:\r?\n|$)/gm.exec(remainder);
		if (incompleteMatch) {
			html += renderTextBlock(remainder.slice(0, incompleteMatch.index));
			const language = incompleteMatch[1].trim() || "code";
			const code = remainder.slice(incompleteMatch.index + incompleteMatch[0].length);
			html += renderCodeBlock(code, language, deferredToolBodies);
		} else html += renderTextBlock(remainder);
	} else html += renderTextBlock(remainder);
	return html || "<p></p>";
}
var LANGUAGE_ALIASES, CODE_KEYWORDS;
var init_markdown = __esmMin((() => {
	init_clientLogic();
	LANGUAGE_ALIASES = {
		js: "javascript",
		jsx: "javascript",
		mjs: "javascript",
		cjs: "javascript",
		ts: "typescript",
		tsx: "typescript",
		py: "python",
		sh: "bash",
		shell: "bash",
		zsh: "bash",
		yml: "yaml",
		c: "cpp",
		cxx: "cpp",
		h: "cpp",
		hpp: "cpp",
		html: "markup",
		xml: "markup",
		svg: "markup",
		md: "markdown"
	};
	CODE_KEYWORDS = {
		javascript: new Set("as async await break case catch class const continue default delete do else export extends false finally for from function get if import in instanceof let new null of return set static super switch this throw true try typeof undefined var void while yield".split(" ")),
		typescript: new Set("abstract any as async await boolean break case catch class const constructor continue declare default do else enum export extends false finally for from function get if implements import in infer instanceof interface keyof let namespace never new null number object of private protected public readonly return satisfies set static string super switch symbol this throw true try type typeof undefined unknown var void while yield".split(" ")),
		python: new Set("and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield".split(" ")),
		bash: new Set("case do done elif else esac export fi for function if in local readonly return select then time until while".split(" ")),
		cpp: new Set("auto bool break case catch char class const constexpr continue default delete do double else enum explicit extern false float for friend if inline int long namespace new nullptr operator private protected public return short signed sizeof static struct switch template this throw true try typedef typename union unsigned using virtual void volatile while".split(" ")),
		dart: new Set("abstract as assert async await break case catch class const continue default deferred do dynamic else enum export extends extension external factory false final finally for Function get hide if implements import in interface is late library mixin new null of on operator part required rethrow return set show static super switch sync this throw true try typedef var void while with yield".split(" ")),
		sql: new Set("ADD ALL ALTER AND ANY AS ASC BETWEEN BY CASE CHECK COLUMN CONSTRAINT CREATE DATABASE DEFAULT DELETE DESC DISTINCT DROP ELSE END EXISTS FOREIGN FROM FULL GROUP HAVING IN INDEX INNER INSERT INTO IS JOIN KEY LEFT LIKE LIMIT NOT NULL OR ORDER OUTER PRIMARY RIGHT SELECT SET TABLE UNION UNIQUE UPDATE VALUES VIEW WHEN WHERE WITH".split(" ")),
		json: /* @__PURE__ */ new Set([
			"true",
			"false",
			"null"
		])
	};
}));
//#endregion
//#region src/prompta/ui/conversationRenderer.ts
function requiredElement$4(selector) {
	const element = document.querySelector(selector);
	if (!element) throw new Error("Missing required conversation UI element: " + selector);
	return element;
}
function escapeHtml$2(value) {
	return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll("\"", "&quot;").replaceAll("'", "&#039;");
}
function setTextIfChanged$3(element, value) {
	const text = String(value ?? "");
	if (element.textContent !== text) element.textContent = text;
}
function canMorphPendingMessageNode(messageKey, role, sendError = false) {
	if (sendError) return false;
	if (role === "user") return String(messageKey).startsWith("pending-user-");
	return String(messageKey).startsWith("pending-activity-");
}
function imageAttachments(message) {
	return (Array.isArray(message?.attachments) ? message.attachments : []).filter((attachment) => {
		if (!attachment || typeof attachment !== "object") return false;
		const type = String(attachment.type || "");
		const src = String(attachment.src || "");
		return type.startsWith("image/") && (Boolean(attachment.id) || src.startsWith("data:image/"));
	});
}
function imageAttachmentSrc(attachment) {
	const inline = String(attachment?.src || "");
	if (inline.startsWith("data:image/")) return inline;
	const id = String(attachment?.id || "");
	return id ? `api/attachment-previews/${encodeURIComponent(id)}` : "";
}
function renderMessageAttachments(message) {
	const images = imageAttachments(message);
	if (!images.length) return "";
	return `<div class="message-attachments">${images.map((attachment) => {
		const src = imageAttachmentSrc(attachment);
		const name = String(attachment.name || "Attached image");
		return `<img class="message-image-preview" src="${escapeHtml$2(src)}" alt="${escapeHtml$2(name)}" loading="lazy" decoding="async">`;
	}).join("")}</div>`;
}
function renderPendingDeleteButton(deleteKey) {
	return `<button type="button"
                  class="delete-pending-button"
                  data-delete-pending-key="${escapeHtml$2(deleteKey)}"
                  aria-label="Delete queued message"
                  title="Delete queued message">
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5"></path>
            </svg>
          </button>`;
}
function pendingImageAttachments(serializedAttachments) {
	return serializedAttachments.filter((attachment) => String(attachment.type || "").startsWith("image/")).map((attachment) => ({
		name: attachment.name,
		type: attachment.type,
		src: `data:${attachment.type};base64,${attachment.data}`
	}));
}
function shouldHandlePendingLongPress(pointerType, coarsePointer) {
	return pointerType !== "mouse" || coarsePointer;
}
function pendingLongPressMoved(startX, startY, currentX, currentY, tolerance = 12) {
	return Math.hypot(currentX - startX, currentY - startY) > tolerance;
}
function createConversationRenderer({ onRetry, onDelete, onEdit }) {
	const conversation = requiredElement$4("#conversation");
	const viewport = requiredElement$4("#conversationViewport");
	function messageTimestamp(message) {
		const millis = messageTimestampMillis(message.display_at, message.created_at ?? message.updated_at);
		if (millis === null) return {
			text: "Time unavailable",
			iso: "",
			millis: null,
			age: ""
		};
		const date = new Date(millis);
		return {
			text: `${date.getDate()} ${[
				"Jan",
				"Feb",
				"Mar",
				"Apr",
				"May",
				"Jun",
				"Jul",
				"Aug",
				"Sept",
				"Oct",
				"Nov",
				"Dec"
			][date.getMonth()]} ${[
				"Sun",
				"Mon",
				"Tue",
				"Wed",
				"Thu",
				"Fri",
				"Sat"
			][date.getDay()]} ${formatClockTime12Hour(date)}`,
			iso: date.toISOString(),
			millis,
			age: messageAgeText(millis)
		};
	}
	function renderMessageSection(message, allowStreaming = true, deferredToolBodies = null) {
		const role = message.role === "user" ? "user" : "assistant";
		const streaming = Boolean(message.pending_activity) || allowStreaming && message.status === "streaming";
		const activityLabel = message.pending_activity_label || "writing";
		const label = message.send_error ? "Send error" : "Prompta run";
		const timestamp = messageTimestamp(message);
		const contentHtml = message.pending_activity ? "" : renderMarkdown(message.content, deferredToolBodies, { renderIncompleteFence: streaming });
		const attachmentsHtml = message.pending_activity ? "" : renderMessageAttachments(message);
		return `
      <section class="message ${role}${message.send_error ? " send-error" : ""}${message.pending_activity ? " pending-activity" : ""}">
        <div class="message-inner">
          ${role === "assistant" ? `
            <div class="message-label"><span class="assistant-avatar">${message.send_error ? "!" : "P"}</span> ${label}</div>
          ` : ""}
          ${attachmentsHtml}
          <div class="message-content">${contentHtml}</div>
          ${message.send_error && message.retry_scope && message.retry_key ? `
            <button type="button"
                    class="retry-send-button"
                    data-retry-scope="${escapeHtml$2(message.retry_scope)}"
                    data-retry-key="${escapeHtml$2(message.retry_key)}">Retry</button>
          ` : ""}
          ${message.pending_delete_key ? renderPendingDeleteButton(message.pending_delete_key) : ""}
          ${streaming ? `
            <div class="streaming-indicator">
              <span class="streaming-dots"><i></i><i></i><i></i></span>
              ${escapeHtml$2(activityLabel)}
            </div>
          ` : ""}
          <time class="message-timestamp" datetime="${timestamp.iso}"${timestamp.millis === null ? "" : ` data-message-at="${timestamp.millis}"`}>
            <span class="message-clock">${escapeHtml$2(timestamp.text)}</span>${timestamp.age ? `<span class="message-age"> · ${escapeHtml$2(timestamp.age)}</span>` : ""}
          </time>
        </div>
      </section>`;
	}
	function messageNodeFingerprint(message, allowStreaming) {
		return JSON.stringify([
			message.role,
			message.status,
			message.content,
			imageAttachments(message).map((attachment) => [
				attachment.id || "",
				attachment.name || "",
				attachment.type || "",
				String(attachment.src || "").length
			]),
			Boolean(message.send_error),
			Boolean(message.pending_activity),
			message.pending_activity_label,
			message.retry_scope,
			message.retry_key,
			message.pending_delete_key,
			message.created_at,
			message.updated_at,
			message.display_at,
			allowStreaming
		]);
	}
	const boundCopyButtons = /* @__PURE__ */ new WeakSet();
	const boundRetryButtons = /* @__PURE__ */ new WeakSet();
	const boundDeleteButtons = /* @__PURE__ */ new WeakSet();
	const boundPendingActionTargets = /* @__PURE__ */ new WeakSet();
	const deferredToolBodyData = /* @__PURE__ */ new WeakMap();
	const boundDeferredToolBodies = /* @__PURE__ */ new WeakSet();
	let pendingActionsSheet = null;
	let activePendingActionKey = "";
	function getPendingActionsSheet() {
		if (pendingActionsSheet) return pendingActionsSheet;
		const dialog = document.createElement("dialog");
		dialog.className = "pending-message-actions";
		dialog.setAttribute("aria-labelledby", "pendingMessageActionsTitle");
		const shell = document.createElement("div");
		shell.className = "pending-message-actions-shell";
		const title = document.createElement("div");
		title.id = "pendingMessageActionsTitle";
		title.className = "pending-message-actions-title";
		title.textContent = "Pending message";
		const editButton = document.createElement("button");
		editButton.type = "button";
		editButton.className = "pending-message-action";
		editButton.textContent = "Edit message";
		const deleteButton = document.createElement("button");
		deleteButton.type = "button";
		deleteButton.className = "pending-message-action danger";
		deleteButton.textContent = "Delete message";
		const cancelButton = document.createElement("button");
		cancelButton.type = "button";
		cancelButton.className = "pending-message-action cancel";
		cancelButton.textContent = "Cancel";
		shell.append(title, editButton, deleteButton, cancelButton);
		dialog.append(shell);
		document.body.append(dialog);
		editButton.addEventListener("click", () => {
			const key = activePendingActionKey;
			dialog.close();
			activePendingActionKey = "";
			if (key) onEdit(key);
		});
		deleteButton.addEventListener("click", () => {
			const key = activePendingActionKey;
			dialog.close();
			activePendingActionKey = "";
			if (key) onDelete(key);
		});
		cancelButton.addEventListener("click", () => dialog.close());
		dialog.addEventListener("close", () => {
			activePendingActionKey = "";
		});
		dialog.addEventListener("click", (event) => {
			if (event.target === dialog) dialog.close();
		});
		pendingActionsSheet = dialog;
		return dialog;
	}
	function openPendingActions(deleteKey) {
		if (!deleteKey) return;
		activePendingActionKey = deleteKey;
		const dialog = getPendingActionsSheet();
		if (!dialog.open) dialog.showModal();
	}
	function bindPendingActionTargets(root) {
		const targets = root.matches?.(".message.user") ? [root] : Array.from(root.querySelectorAll(".message.user"));
		for (const target of targets) {
			const node = target;
			if (boundPendingActionTargets.has(node)) continue;
			if (!node.querySelector(".delete-pending-button")) continue;
			boundPendingActionTargets.add(node);
			node.classList.add("pending-message-action-target");
			let timer = 0;
			let startX = 0;
			let startY = 0;
			const cancelLongPress = () => {
				if (!timer) return;
				clearTimeout(timer);
				timer = 0;
			};
			const actionKey = () => node.querySelector(".delete-pending-button")?.dataset.deletePendingKey || "";
			node.addEventListener("pointerdown", (event) => {
				if (!shouldHandlePendingLongPress(event.pointerType, matchMedia("(pointer: coarse)").matches)) return;
				cancelLongPress();
				startX = event.clientX;
				startY = event.clientY;
				timer = window.setTimeout(() => {
					timer = 0;
					openPendingActions(actionKey());
				}, 480);
			});
			node.addEventListener("pointermove", (event) => {
				if (timer && pendingLongPressMoved(startX, startY, event.clientX, event.clientY)) cancelLongPress();
			});
			node.addEventListener("pointerup", cancelLongPress);
			node.addEventListener("pointercancel", cancelLongPress);
			node.addEventListener("lostpointercapture", cancelLongPress);
			node.addEventListener("contextmenu", (event) => {
				if (!matchMedia("(pointer: coarse)").matches) return;
				event.preventDefault();
				cancelLongPress();
				openPendingActions(actionKey());
			});
		}
	}
	function bindRetryButtons(root) {
		for (const button of root.querySelectorAll(".retry-send-button")) {
			if (boundRetryButtons.has(button)) continue;
			boundRetryButtons.add(button);
			button.addEventListener("click", () => {
				onRetry(button.dataset.retryScope || "", button.dataset.retryKey || "");
			});
		}
	}
	function bindDeleteButtons(root) {
		for (const button of root.querySelectorAll(".delete-pending-button")) {
			if (boundDeleteButtons.has(button)) continue;
			boundDeleteButtons.add(button);
			button.addEventListener("click", () => {
				onDelete(button.dataset.deletePendingKey || "");
			});
		}
	}
	function renderDeferredToolBody(details) {
		const deferred = deferredToolBodyData.get(details);
		const placeholder = details.querySelector(":scope > .deferred-tool-body");
		const existing = details.querySelector(":scope > pre[data-deferred-tool-body]");
		if (!deferred) return;
		if (details.open) {
			if (existing) return;
			const pre = document.createElement("pre");
			pre.dataset.deferredToolBody = "true";
			const code = document.createElement("code");
			code.className = `language-${deferred.language}`;
			if (deferred.highlight) {
				const template = document.createElement("template");
				template.innerHTML = renderDeferredToolCode(deferred);
				code.append(template.content);
			} else code.textContent = deferred.code;
			pre.append(code);
			placeholder?.replaceWith(pre);
			return;
		}
		if (!existing) return;
		const nextPlaceholder = document.createElement("div");
		nextPlaceholder.className = "deferred-tool-body";
		nextPlaceholder.setAttribute("aria-hidden", "true");
		existing.replaceWith(nextPlaceholder);
	}
	function bindDeferredToolBodies(root, bodies) {
		for (const details of root.querySelectorAll(".tool-call-block[data-deferred-tool-body-index]")) {
			const index = Number(details.dataset.deferredToolBodyIndex);
			const deferred = Number.isInteger(index) ? bodies[index] : void 0;
			if (!deferred) continue;
			deferredToolBodyData.set(details, deferred);
			if (!boundDeferredToolBodies.has(details)) {
				boundDeferredToolBodies.add(details);
				details.addEventListener("toggle", () => renderDeferredToolBody(details));
			}
			renderDeferredToolBody(details);
		}
	}
	function bindCopyButtons(root) {
		for (const button of root.querySelectorAll(".copy-code")) {
			if (boundCopyButtons.has(button)) continue;
			boundCopyButtons.add(button);
			button.addEventListener("click", async (event) => {
				event.preventDefault();
				event.stopPropagation();
				const code = button.closest(".code-block")?.querySelector("pre code")?.textContent || "";
				try {
					await navigator.clipboard.writeText(code);
					const previous = button.textContent;
					setTextIfChanged$3(button, "copied");
					setTimeout(() => {
						setTextIfChanged$3(button, previous);
					}, 1e3);
				} catch {
					setTextIfChanged$3(button, "copy unavailable");
				}
			});
		}
	}
	function createMessageNode(message, allowStreaming, messageKey) {
		const deferredToolBodies = [];
		const template = document.createElement("template");
		template.innerHTML = renderMessageSection(message, allowStreaming, deferredToolBodies).trim();
		const node = template.content.firstElementChild;
		node.dataset.messageKey = messageKey;
		node.dataset.renderFingerprint = messageNodeFingerprint(message, allowStreaming);
		bindDeferredToolBodies(node, deferredToolBodies);
		bindCopyButtons(node);
		bindRetryButtons(node);
		bindDeleteButtons(node);
		bindPendingActionTargets(node);
		return node;
	}
	function patchDomNode(current, next) {
		if (current.nodeType !== next.nodeType || current.nodeType === Node.ELEMENT_NODE && current.tagName !== next.tagName) {
			const replacement = next.cloneNode(true);
			current.replaceWith(replacement);
			return replacement;
		}
		if (current.nodeType === Node.TEXT_NODE) {
			if (current.data !== next.data) current.data = next.data;
			return current;
		}
		if (current.nodeType !== Node.ELEMENT_NODE) return current;
		const preserveDetailsOpen = current.tagName === "DETAILS" && next.tagName === "DETAILS";
		const detailsOpen = preserveDetailsOpen ? current.open : false;
		for (const attribute of Array.from(current.attributes)) {
			if (preserveDetailsOpen && attribute.name === "open") continue;
			if (!next.hasAttribute(attribute.name)) current.removeAttribute(attribute.name);
		}
		for (const attribute of Array.from(next.attributes)) {
			if (preserveDetailsOpen && attribute.name === "open") continue;
			if (current.getAttribute(attribute.name) !== attribute.value) current.setAttribute(attribute.name, attribute.value);
		}
		patchDomChildren(current, next);
		if (preserveDetailsOpen) current.open = detailsOpen;
		return current;
	}
	function domPatchKey(node) {
		if (!node || node.nodeType !== Node.ELEMENT_NODE) return "";
		return node.dataset.domKey || "";
	}
	function patchDomChildren(currentParent, nextParent) {
		let index = 0;
		while (index < nextParent.childNodes.length || index < currentParent.childNodes.length) {
			let current = currentParent.childNodes[index];
			const next = nextParent.childNodes[index];
			if (!next) {
				current.remove();
				continue;
			}
			if (!current) {
				currentParent.append(next.cloneNode(true));
				index += 1;
				continue;
			}
			const nextKey = domPatchKey(next);
			if (nextKey && domPatchKey(current) !== nextKey) {
				const match = Array.from(currentParent.childNodes).slice(index + 1).find((candidate) => domPatchKey(candidate) === nextKey);
				if (match) {
					currentParent.insertBefore(match, current);
					current = match;
				} else {
					currentParent.insertBefore(next.cloneNode(true), current);
					index += 1;
					continue;
				}
			}
			patchDomNode(current, next);
			index += 1;
		}
	}
	function updateMessageNode(node, message, allowStreaming) {
		const role = message.role === "user" ? "user" : "assistant";
		const sendError = Boolean(message.send_error);
		if ((node.classList.contains("user") ? "user" : "assistant") !== role || node.classList.contains("send-error") !== sendError) return false;
		const content = node.querySelector(".message-content");
		if (!content) return false;
		let currentAttachments = node.querySelector(".message-attachments");
		const nextAttachments = message.pending_activity ? "" : renderMessageAttachments(message);
		if (!nextAttachments) {
			currentAttachments?.remove();
			currentAttachments = null;
		} else if (!currentAttachments) {
			const template = document.createElement("template");
			template.innerHTML = nextAttachments;
			const nextNode = template.content.firstElementChild;
			if (nextNode) content.before(nextNode);
		} else if (currentAttachments.outerHTML !== nextAttachments) {
			const template = document.createElement("template");
			template.innerHTML = nextAttachments;
			const nextNode = template.content.firstElementChild;
			if (nextNode) patchDomNode(currentAttachments, nextNode);
		}
		const deferredToolBodies = [];
		const nextContent = message.pending_activity ? "" : renderMarkdown(message.content, deferredToolBodies, { renderIncompleteFence: allowStreaming && message.status === "streaming" });
		if (content.innerHTML !== nextContent) {
			const template = document.createElement("template");
			template.innerHTML = nextContent;
			patchDomChildren(content, template.content);
			bindCopyButtons(content);
		}
		bindDeferredToolBodies(content, deferredToolBodies);
		const deleteButton = node.querySelector(".delete-pending-button");
		const deleteKey = String(message.pending_delete_key || "");
		if (deleteKey) {
			if (deleteButton) deleteButton.dataset.deletePendingKey = deleteKey;
			else {
				content.insertAdjacentHTML("afterend", renderPendingDeleteButton(deleteKey));
				bindDeleteButtons(node);
				bindPendingActionTargets(node);
			}
		} else if (deleteButton) deleteButton.remove();
		const retryButton = node.querySelector(".retry-send-button");
		if (sendError && Boolean(message.retry_scope) && Boolean(message.retry_key)) {
			if (retryButton) {
				retryButton.dataset.retryScope = String(message.retry_scope);
				retryButton.dataset.retryKey = String(message.retry_key);
			} else {
				content.insertAdjacentHTML("afterend", `
          <button type="button"
                  class="retry-send-button"
                  data-retry-scope="${escapeHtml$2(message.retry_scope)}"
                  data-retry-key="${escapeHtml$2(message.retry_key)}">Retry</button>
        `);
				bindRetryButtons(node);
				bindDeleteButtons(node);
			}
		} else if (retryButton) retryButton.remove();
		const timestamp = node.querySelector(".message-timestamp");
		if (!timestamp) return false;
		const nextTimestamp = messageTimestamp(message);
		const clock = timestamp.querySelector(".message-clock");
		if (!clock) return false;
		setTextIfChanged$3(clock, nextTimestamp.text);
		if (timestamp.dateTime !== nextTimestamp.iso) timestamp.dateTime = nextTimestamp.iso;
		if (nextTimestamp.millis === null) delete timestamp.dataset.messageAt;
		else if (timestamp.dataset.messageAt !== String(nextTimestamp.millis)) timestamp.dataset.messageAt = String(nextTimestamp.millis);
		let age = timestamp.querySelector(".message-age");
		if (nextTimestamp.age) {
			if (!age) {
				timestamp.insertAdjacentHTML("beforeend", "<span class=\"message-age\"></span>");
				age = timestamp.querySelector(".message-age");
			}
			if (age) setTextIfChanged$3(age, ` · ${nextTimestamp.age}`);
		} else age?.remove();
		const shouldStream = Boolean(message.pending_activity) || allowStreaming && message.status === "streaming";
		const activityLabel = message.pending_activity_label || "writing";
		const indicator = node.querySelector(".streaming-indicator");
		if (shouldStream && !indicator) timestamp.insertAdjacentHTML("beforebegin", `
        <div class="streaming-indicator">
          <span class="streaming-dots"><i></i><i></i><i></i></span>
          ${escapeHtml$2(activityLabel)}
        </div>
      `);
		else if (shouldStream && indicator) {
			const labelNode = indicator.lastChild;
			if (labelNode?.nodeType === Node.TEXT_NODE && labelNode.textContent !== ` ${activityLabel}`) labelNode.textContent = ` ${activityLabel}`;
		} else if (!shouldStream && indicator) indicator.remove();
		node.dataset.renderFingerprint = messageNodeFingerprint(message, allowStreaming);
		return true;
	}
	function reusablePendingNode(node, message) {
		if (!(node instanceof HTMLElement) || message.send_error) return null;
		const key = node.dataset.messageKey || "";
		const role = message.role === "user" ? "user" : "assistant";
		if (!canMorphPendingMessageNode(key, role, Boolean(message.send_error))) return null;
		return node.classList.contains(role) ? node : null;
	}
	function renderMessageNodes(messages, allowStreaming) {
		const existing = new Map(Array.from(conversation.children).map((node) => [node.dataset.messageKey, node]));
		const desiredKeys = /* @__PURE__ */ new Set();
		const lastUserIndex = messages.findLastIndex((message) => message.role === "user");
		const lastAssistantIndex = messages.findLastIndex((message) => message.role === "assistant" && !message.send_error);
		const streamingIndex = allowStreaming && lastAssistantIndex > lastUserIndex && messages[lastAssistantIndex]?.status === "streaming" ? lastAssistantIndex : -1;
		messages.forEach((message, index) => {
			const messageKey = String(message.message_key || `${message.role || "message"}:${index}`);
			const streamThisMessage = index === streamingIndex;
			desiredKeys.add(messageKey);
			const fingerprint = messageNodeFingerprint(message, streamThisMessage);
			let node = existing.get(messageKey);
			if (!node) {
				const candidate = reusablePendingNode(conversation.children[index], message);
				if (candidate && updateMessageNode(candidate, message, streamThisMessage)) {
					candidate.dataset.messageKey = messageKey;
					node = candidate;
				} else node = createMessageNode(message, streamThisMessage, messageKey);
			} else if (node.dataset.renderFingerprint !== fingerprint) {
				if (!updateMessageNode(node, message, streamThisMessage)) {
					const replacement = createMessageNode(message, streamThisMessage, messageKey);
					node.replaceWith(replacement);
					node = replacement;
				}
			}
			const currentAtIndex = conversation.children[index];
			if (currentAtIndex !== node) conversation.insertBefore(node, currentAtIndex || null);
		});
		for (const node of Array.from(conversation.children)) if (!desiredKeys.has(node.dataset.messageKey)) node.remove();
	}
	function renderLoadingState() {
		if (conversation.children.length) return;
		const loading = document.createElement("div");
		loading.className = "conversation-loading";
		loading.dataset.messageKey = "__loading__";
		loading.setAttribute("aria-live", "polite");
		loading.setAttribute("aria-label", "Loading conversation");
		for (const className of [
			"conversation-loading-row conversation-loading-user",
			"conversation-loading-row conversation-loading-assistant",
			"conversation-loading-row conversation-loading-assistant short"
		]) {
			const row = document.createElement("div");
			row.className = className;
			loading.append(row);
		}
		conversation.append(loading);
	}
	const CONVERSATION_BOTTOM_SLOP = 24;
	let trackedViewport = null;
	function scrollAnchorCandidates(root) {
		return Array.from(root.querySelectorAll(".message-attachments, .message-content > *, .streaming-indicator, .message-timestamp"));
	}
	function scrollAnchorFingerprint(element) {
		const text = String(element.textContent || "").replace(/\s+/g, " ").trim().slice(0, 160);
		return [
			element.tagName,
			element.className,
			text
		].join("|");
	}
	function captureConversationViewport() {
		const maxScrollTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
		const pinnedToBottom = Math.max(0, maxScrollTop - viewport.scrollTop) <= CONVERSATION_BOTTOM_SLOP;
		const snapshot = {
			pinnedToBottom,
			scrollTop: viewport.scrollTop,
			anchorElement: null,
			anchorKey: "",
			anchorIndex: -1,
			anchorFingerprint: "",
			anchorOffset: 0
		};
		if (pinnedToBottom) return snapshot;
		const viewportTop = viewport.getBoundingClientRect().top;
		const message = Array.from(conversation.children).find((node) => node.getBoundingClientRect().bottom > viewportTop + 1);
		if (!message) return snapshot;
		snapshot.anchorKey = String(message.dataset.messageKey || "");
		const candidates = scrollAnchorCandidates(message);
		const anchor = candidates.find((node) => node.getBoundingClientRect().bottom > viewportTop + 1) || message;
		snapshot.anchorElement = anchor;
		snapshot.anchorIndex = candidates.indexOf(anchor);
		snapshot.anchorFingerprint = scrollAnchorFingerprint(anchor);
		snapshot.anchorOffset = anchor.getBoundingClientRect().top - viewportTop;
		return snapshot;
	}
	function resolveConversationAnchor(snapshot) {
		const direct = snapshot.anchorElement;
		if (direct && direct.isConnected && conversation.contains(direct) && scrollAnchorFingerprint(direct) === snapshot.anchorFingerprint) return direct;
		const message = Array.from(conversation.children).find((node) => node.dataset.messageKey === snapshot.anchorKey);
		if (!message) return null;
		const candidates = scrollAnchorCandidates(message);
		if (snapshot.anchorFingerprint) {
			const matching = candidates.map((node, index) => ({
				node,
				index
			})).filter(({ node }) => scrollAnchorFingerprint(node) === snapshot.anchorFingerprint).sort((left, right) => Math.abs(left.index - snapshot.anchorIndex) - Math.abs(right.index - snapshot.anchorIndex));
			if (matching.length) return matching[0].node;
		}
		return candidates[snapshot.anchorIndex] || message;
	}
	function restoreConversationViewport(snapshot, forceBottom = false) {
		if (forceBottom || snapshot.pinnedToBottom) {
			viewport.scrollTop = viewport.scrollHeight;
			trackedViewport = captureConversationViewport();
			return;
		}
		const anchor = resolveConversationAnchor(snapshot);
		if (anchor) {
			const viewportTop = viewport.getBoundingClientRect().top;
			const delta = anchor.getBoundingClientRect().top - viewportTop - snapshot.anchorOffset;
			if (Math.abs(delta) > .5) viewport.scrollTop += delta;
		} else {
			const maxScrollTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
			viewport.scrollTop = Math.min(snapshot.scrollTop, maxScrollTop);
		}
		trackedViewport = captureConversationViewport();
	}
	viewport.addEventListener("scroll", () => {
		trackedViewport = captureConversationViewport();
	}, { passive: true });
	conversation.addEventListener("load", (event) => {
		if (!(event.target instanceof HTMLImageElement) || !trackedViewport) return;
		restoreConversationViewport(trackedViewport);
	}, true);
	if ("ResizeObserver" in window) {
		const resizeObserver = new ResizeObserver(() => {
			if (!trackedViewport) trackedViewport = captureConversationViewport();
			restoreConversationViewport(trackedViewport);
		});
		resizeObserver.observe(conversation);
		resizeObserver.observe(viewport);
	}
	trackedViewport = captureConversationViewport();
	return {
		renderMessageNodes,
		renderLoadingState,
		messageNodeFingerprint,
		captureConversationViewport,
		restoreConversationViewport
	};
}
var init_conversationRenderer = __esmMin((() => {
	init_clientLogic();
	init_markdown();
}));
//#endregion
//#region src/prompta/ui/attachmentPicker.ts
function requiredElement$3(selector) {
	const element = document.querySelector(selector);
	if (!element) throw new Error("Missing required attachment UI element: " + selector);
	return element;
}
function escapeHtml$1(value) {
	return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll("\"", "&quot;").replaceAll("'", "&#039;");
}
function truncate$1(value, length = 88) {
	const text = String(value || "");
	return text.length > length ? text.slice(0, Math.max(1, length - 1)).trimEnd() + "…" : text;
}
function patchDomNode$1(current, next) {
	if (current.nodeType !== next.nodeType) {
		current.replaceWith(next.cloneNode(true));
		return;
	}
	if (current.nodeType === Node.TEXT_NODE) {
		if (current.textContent !== next.textContent) current.textContent = next.textContent;
		return;
	}
	if (!(current instanceof Element) || !(next instanceof Element) || current.tagName !== next.tagName) {
		current.replaceWith(next.cloneNode(true));
		return;
	}
	for (const attribute of Array.from(current.attributes)) if (!next.hasAttribute(attribute.name)) current.removeAttribute(attribute.name);
	for (const attribute of Array.from(next.attributes)) if (current.getAttribute(attribute.name) !== attribute.value) current.setAttribute(attribute.name, attribute.value);
	patchDomChildren$1(current, next);
}
function domPatchKey$1(node) {
	return node instanceof Element ? node.getAttribute("data-dom-key") || "" : "";
}
function patchDomChildren$1(currentParent, nextParent) {
	const nextChildren = Array.from(nextParent.childNodes);
	for (let index = 0; index < nextChildren.length; index += 1) {
		const next = nextChildren[index];
		let current = currentParent.childNodes[index];
		const nextKey = domPatchKey$1(next);
		if (nextKey && domPatchKey$1(current) !== nextKey) {
			const keyed = Array.from(currentParent.childNodes).slice(index + 1).find((node) => domPatchKey$1(node) === nextKey);
			if (keyed) {
				currentParent.insertBefore(keyed, current || null);
				current = keyed;
			}
		}
		if (!current) {
			currentParent.appendChild(next.cloneNode(true));
			continue;
		}
		patchDomNode$1(current, next);
	}
	while (currentParent.childNodes.length > nextChildren.length) currentParent.lastChild?.remove();
}
function patchHtmlChildren$1(element, html) {
	const template = document.createElement("template");
	template.innerHTML = html;
	patchDomChildren$1(element, template.content);
}
function createAttachmentPicker({ onChange, setStatus }) {
	const els = {
		button: requiredElement$3("#attachmentButton"),
		menu: requiredElement$3("#attachmentMenu"),
		fileInput: requiredElement$3("#fileUploadInput"),
		photoInput: requiredElement$3("#photoUploadInput"),
		cameraInput: requiredElement$3("#cameraUploadInput"),
		chips: requiredElement$3("#attachmentChips")
	};
	let files = [];
	function render() {
		els.chips.hidden = files.length === 0;
		patchHtmlChildren$1(els.chips, files.map((file, index) => "<span class=\"attachment-chip\" data-dom-key=\"attachment:" + index + ":" + escapeHtml$1(file.name) + "\"><span title=\"" + escapeHtml$1(file.name) + "\">" + escapeHtml$1(truncate$1(file.name, 28)) + "</span><button type=\"button\" data-remove-attachment=\"" + index + "\" aria-label=\"Remove attachment\">×</button></span>").join(""));
		onChange();
	}
	function clear() {
		files = [];
		els.fileInput.value = "";
		els.photoInput.value = "";
		els.cameraInput.value = "";
		render();
	}
	function setDisabled(disabled) {
		els.button.disabled = disabled;
		if (disabled) closeMenu();
		for (const button of els.chips.querySelectorAll("button")) button.disabled = disabled;
	}
	function add(nextFiles) {
		const current = [...files];
		for (const file of nextFiles) {
			if (current.length >= 5) break;
			if (!current.some((existing) => existing.name === file.name && existing.size === file.size && existing.lastModified === file.lastModified)) current.push(file);
		}
		files = current;
		render();
		if (nextFiles.length && current.length >= 5) setStatus("Prompta supports up to 5 attachments per message.");
	}
	async function payload(file) {
		if (file.size > 26214400) throw new Error(file.name + " is larger than 25 MB");
		const dataUrl = await new Promise((resolve, reject) => {
			const reader = new FileReader();
			reader.onerror = () => reject(reader.error || /* @__PURE__ */ new Error("Could not read " + file.name));
			reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
			reader.readAsDataURL(file);
		});
		const comma = dataUrl.indexOf(",");
		return {
			name: file.name,
			type: file.type || "application/octet-stream",
			data: comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl
		};
	}
	async function serialize() {
		if (files.reduce((sum, file) => sum + Number(file.size || 0), 0) > 26214400) throw new Error("Attachments exceed the 25 MB Prompta upload limit");
		return Promise.all(files.map(payload));
	}
	function menuButtons() {
		return Array.from(els.menu.querySelectorAll("[data-attachment-kind]"));
	}
	function openMenu(focusIndex = 0) {
		els.menu.hidden = false;
		els.button.setAttribute("aria-expanded", "true");
		menuButtons()[focusIndex]?.focus();
	}
	function closeMenu(restoreFocus = false) {
		els.menu.hidden = true;
		els.button.setAttribute("aria-expanded", "false");
		if (restoreFocus) els.button.focus();
	}
	els.button.addEventListener("click", () => {
		if (els.menu.hidden) openMenu();
		else closeMenu();
	});
	els.button.addEventListener("keydown", (event) => {
		if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
		event.preventDefault();
		const buttons = menuButtons();
		openMenu(event.key === "ArrowUp" ? Math.max(0, buttons.length - 1) : 0);
	});
	els.menu.addEventListener("keydown", (event) => {
		const buttons = menuButtons();
		const current = buttons.indexOf(document.activeElement);
		if (event.key === "Escape") {
			event.preventDefault();
			closeMenu(true);
			return;
		}
		if (event.key === "Tab") {
			closeMenu();
			return;
		}
		let next = current;
		if (event.key === "ArrowDown") next = (current + 1 + buttons.length) % buttons.length;
		else if (event.key === "ArrowUp") next = (current - 1 + buttons.length) % buttons.length;
		else if (event.key === "Home") next = 0;
		else if (event.key === "End") next = Math.max(0, buttons.length - 1);
		else return;
		event.preventDefault();
		buttons[next]?.focus();
	});
	els.menu.addEventListener("click", (event) => {
		const button = event.target.closest("[data-attachment-kind]");
		if (!button) return;
		closeMenu();
		const kind = button.dataset.attachmentKind;
		if (kind === "photo") els.photoInput.click();
		else if (kind === "camera") els.cameraInput.click();
		else els.fileInput.click();
	});
	for (const input of [
		els.fileInput,
		els.photoInput,
		els.cameraInput
	]) input.addEventListener("change", () => {
		const selected = Array.from(input.files || []);
		input.value = "";
		add(selected);
	});
	els.chips.addEventListener("click", (event) => {
		const button = event.target.closest("[data-remove-attachment]");
		if (!button) return;
		const index = Number(button.dataset.removeAttachment);
		if (!Number.isInteger(index)) return;
		files.splice(index, 1);
		render();
	});
	document.addEventListener("click", (event) => {
		const target = event.target;
		if (!els.menu.hidden && !els.menu.contains(target) && !els.button.contains(target)) closeMenu();
	});
	return {
		clear,
		closeMenu,
		count: () => files.length,
		serialize,
		setDisabled,
		snapshot: () => [...files]
	};
}
var init_attachmentPicker = __esmMin((() => {}));
//#endregion
//#region src/prompta/ui/logsPanel.ts
function requiredElement$2(selector) {
	const element = document.querySelector(selector);
	if (!element) throw new Error("Missing required logs UI element: " + selector);
	return element;
}
function setTextIfChanged$2(element, value) {
	const text = String(value ?? "");
	if (element.textContent !== text) element.textContent = text;
}
function createLogsPanel({ fetchJson, formatRelativeTime }) {
	const els = {
		viewport: requiredElement$2("#logsViewport"),
		output: requiredElement$2("#logOutput"),
		meta: requiredElement$2("#logsMeta"),
		serverTitle: requiredElement$2("#logsServerTitle")
	};
	let fingerprint = "";
	let refreshTimer = null;
	let visible = false;
	function render(payload) {
		const lines = Array.isArray(payload.lines) ? payload.lines : [];
		const nextFingerprint = JSON.stringify([payload.updated_at, lines]);
		const wasNearBottom = els.viewport.scrollHeight - els.viewport.scrollTop - els.viewport.clientHeight < 120;
		const isInitial = !fingerprint;
		if (nextFingerprint !== fingerprint) {
			fingerprint = nextFingerprint;
			setTextIfChanged$2(els.output, lines.length ? lines.join("\n") : "No Prompta service logs are available yet.");
			if (isInitial || wasNearBottom) requestAnimationFrame(() => {
				els.viewport.scrollTop = els.viewport.scrollHeight;
			});
		}
		setTextIfChanged$2(els.meta, payload.exists ? payload.source === "journal" ? lines.length + " lines · live journal" : lines.length + " lines · synced " + formatRelativeTime(payload.updated_at) : "Waiting for Prompta service logs");
	}
	async function load() {
		try {
			render(await fetchJson("api/logs?limit=800"));
		} catch (error) {
			setTextIfChanged$2(els.meta, "Logs unavailable");
			console.error(error);
		}
	}
	function stopRefresh() {
		if (refreshTimer === null) return;
		clearInterval(refreshTimer);
		refreshTimer = null;
	}
	function setVisible(nextVisible) {
		visible = Boolean(nextVisible);
		els.viewport.hidden = !visible;
		stopRefresh();
		if (!visible) return;
		load();
		refreshTimer = setInterval(() => {
			if (visible && document.visibilityState === "visible") load();
		}, 2e3);
	}
	function setServerTitle(display) {
		setTextIfChanged$2(els.serverTitle, String(display || "") + " · prompta.service");
	}
	return {
		load,
		setServerTitle,
		setVisible
	};
}
var init_logsPanel = __esmMin((() => {}));
//#endregion
//#region src/prompta/ui/deploymentMonitor.ts
function createDeploymentMonitor({ onUpdateAvailable = () => {} } = {}) {
	let head = "";
	let updateAvailable = false;
	let reloading = false;
	async function updateServiceWorker() {
		try {
			if ("serviceWorker" in navigator) await (await navigator.serviceWorker.getRegistration())?.update();
		} catch (error) {
			console.warn("Could not update Prompta service worker for deployment", error);
		}
	}
	async function applyUpdate() {
		if (reloading) return;
		reloading = true;
		await updateServiceWorker();
		window.location.reload();
	}
	function observeHead(value) {
		const nextHead = String(value || "").trim().toLowerCase();
		if (!nextHead) return;
		if (!head) {
			head = nextHead;
			return;
		}
		if (nextHead === head) return;
		head = nextHead;
		updateAvailable = true;
		onUpdateAvailable(head);
	}
	function handleVisibilityChange() {
		if (updateAvailable) onUpdateAvailable(head);
	}
	function registerServiceWorker() {
		if (!("serviceWorker" in navigator)) return;
		navigator.serviceWorker.register("./sw.js", { updateViaCache: "none" }).catch((error) => {
			console.warn("Could not register Prompta service worker", error);
		});
	}
	return {
		applyUpdate,
		handleVisibilityChange,
		observeHead,
		registerServiceWorker
	};
}
var init_deploymentMonitor = __esmMin((() => {}));
//#endregion
//#region src/prompta/ui/liveUpdates.ts
function createLiveUpdates({ loadChats, loadServerIdentity, setServerStatus, observeHead, refreshDisplayedTimes, onStreamError, onPageShow, presenceStaleMs = 16e3, presenceCheckMs = 1e3 }) {
	let eventSource = null;
	let fallbackTimer = null;
	let timeRefreshTimer = null;
	let presenceTimer = null;
	let paused = false;
	let refreshRunning = false;
	let refreshAgain = false;
	let lastPresenceAt = 0;
	let lastServer = "";
	async function drainRefreshes() {
		try {
			do {
				refreshAgain = false;
				await loadChats();
			} while (refreshAgain && !paused);
		} finally {
			refreshRunning = false;
			if (refreshAgain && !paused) queueRefresh();
		}
	}
	function queueRefresh() {
		if (refreshRunning) {
			refreshAgain = true;
			return;
		}
		refreshRunning = true;
		drainRefreshes();
	}
	function stopTimeRefresh() {
		if (timeRefreshTimer === null) return;
		clearInterval(timeRefreshTimer);
		timeRefreshTimer = null;
	}
	function startTimeRefresh() {
		if (timeRefreshTimer !== null) return;
		timeRefreshTimer = setInterval(() => refreshDisplayedTimes(), 3e4);
	}
	function stopFallbackRefresh() {
		if (fallbackTimer === null) return;
		clearInterval(fallbackTimer);
		fallbackTimer = null;
	}
	function startFallbackRefresh() {
		if (fallbackTimer !== null) return;
		fallbackTimer = setInterval(() => {
			loadChats();
			loadServerIdentity();
		}, 5e3);
	}
	function markPresence(payload) {
		const server = String(payload.server || lastServer || "");
		if (server) lastServer = server;
		lastPresenceAt = Date.now();
		if (server && typeof payload.online === "boolean") setServerStatus(server, payload.online);
	}
	function markStreamOffline() {
		lastPresenceAt = 0;
		if (lastServer) setServerStatus(lastServer, false);
		onStreamError();
	}
	function handleStatusEvent(event, refreshChats) {
		stopFallbackRefresh();
		try {
			const payload = JSON.parse(event.data || "{}");
			markPresence(payload);
			if (payload.head) observeHead(payload.head);
		} catch (error) {
			console.warn("Could not parse Prompta SSE status", error);
		}
		if (refreshChats) queueRefresh();
	}
	function stopPresenceWatchdog() {
		if (presenceTimer === null) return;
		clearInterval(presenceTimer);
		presenceTimer = null;
	}
	function startPresenceWatchdog() {
		if (presenceTimer !== null) return;
		presenceTimer = setInterval(() => {
			if (!lastPresenceAt || Date.now() - lastPresenceAt <= presenceStaleMs) return;
			markStreamOffline();
			startFallbackRefresh();
		}, presenceCheckMs);
	}
	function stopEventStream() {
		if (eventSource) {
			eventSource.close();
			eventSource = null;
		}
		stopFallbackRefresh();
	}
	function startEventStream() {
		if (eventSource) return;
		if (!("EventSource" in window)) {
			startFallbackRefresh();
			return;
		}
		const events = new EventSource("api/events");
		eventSource = events;
		events.addEventListener("refresh", (event) => {
			handleStatusEvent(event, true);
		});
		events.addEventListener("heartbeat", (event) => {
			handleStatusEvent(event, false);
		});
		events.addEventListener("error", () => {
			markStreamOffline();
			startFallbackRefresh();
		});
	}
	function start() {
		startEventStream();
		startPresenceWatchdog();
		startTimeRefresh();
	}
	function stop() {
		stopEventStream();
		stopPresenceWatchdog();
		stopTimeRefresh();
	}
	window.addEventListener("pagehide", () => {
		paused = true;
		stop();
	});
	window.addEventListener("pageshow", () => {
		onPageShow();
		if (!paused) return;
		paused = false;
		loadServerIdentity();
		loadChats();
		start();
	});
	return {
		start,
		stop
	};
}
var init_liveUpdates = __esmMin((() => {}));
//#endregion
//#region src/prompta/ui/completionNotifications.ts
function createCompletionNotifications({ displayServerName, getServerName, chatTitle }) {
	const chatStatuses = /* @__PURE__ */ new Map();
	const explicitlyActive = /* @__PURE__ */ new Set();
	const pendingFinishedChats = /* @__PURE__ */ new Map();
	const notifiedCompletions = /* @__PURE__ */ new Set();
	let baselineReady = false;
	let permissionRequest = null;
	let flushingNotifications = false;
	function completionKey(chat) {
		return String(chat.id || "") + ":" + String(chat.completed_at ?? chat.updated_at ?? "");
	}
	async function showChatFinished(chat) {
		if (!("Notification" in window) || Notification.permission !== "granted") return false;
		const display = displayServerName(getServerName() || location.hostname);
		const options = {
			body: chatTitle(chat) + " finished",
			tag: "prompta-finished-" + chat.id,
			icon: "./icon.svg",
			badge: "./icon.svg",
			data: { url: "./#/" + encodeURIComponent(chat.id) }
		};
		if ("serviceWorker" in navigator) try {
			let registration = typeof navigator.serviceWorker.getRegistration === "function" ? await navigator.serviceWorker.getRegistration() : null;
			if (!registration) registration = await Promise.race([navigator.serviceWorker.ready, new Promise((resolve) => setTimeout(() => resolve(null), 1500))]);
			if (registration) {
				await registration.showNotification("Prompta · " + display, options);
				return true;
			}
		} catch (error) {
			console.warn("Could not show Prompta service worker notification", error);
		}
		try {
			new Notification("Prompta · " + display, options);
			return true;
		} catch (error) {
			console.warn("Could not show Prompta completion notification", error);
			return false;
		}
	}
	async function flushPendingNotifications() {
		if (flushingNotifications || !("Notification" in window) || Notification.permission !== "granted") return;
		flushingNotifications = true;
		try {
			while (pendingFinishedChats.size) {
				const [key, chat] = pendingFinishedChats.entries().next().value;
				if (!await showChatFinished(chat)) break;
				pendingFinishedChats.delete(key);
				notifiedCompletions.add(key);
			}
		} finally {
			flushingNotifications = false;
		}
	}
	async function requestPermissionFromGesture() {
		if (!("Notification" in window)) return;
		if (Notification.permission === "granted") {
			await flushPendingNotifications();
			return;
		}
		if (Notification.permission !== "default") return;
		if (!permissionRequest) permissionRequest = Notification.requestPermission().catch((error) => {
			console.warn("Could not request notification permission", error);
			return "default";
		}).finally(() => {
			permissionRequest = null;
		});
		if (await permissionRequest === "granted") await flushPendingNotifications();
	}
	function queueFinishedChat(chat) {
		const key = completionKey(chat);
		if (!chat.id || notifiedCompletions.has(key) || pendingFinishedChats.has(key)) return;
		pendingFinishedChats.set(key, chat);
		flushPendingNotifications();
	}
	function markActive(conversationId) {
		const id = String(conversationId || "");
		if (!id) return;
		chatStatuses.set(id, "active");
		explicitlyActive.add(id);
	}
	function trackCompletions(chats) {
		for (const chat of chats) {
			const wasActive = chatStatuses.get(chat.id) === "active" || explicitlyActive.has(chat.id);
			if ((baselineReady || explicitlyActive.has(chat.id)) && wasActive && chat.status === "complete") {
				queueFinishedChat(chat);
				explicitlyActive.delete(chat.id);
			} else if (!["active", "complete"].includes(chat.status)) explicitlyActive.delete(chat.id);
		}
		for (const chat of chats) chatStatuses.set(chat.id, chat.status);
		baselineReady = true;
		flushPendingNotifications();
	}
	return {
		markActive,
		requestPermissionFromGesture,
		trackCompletions
	};
}
var init_completionNotifications = __esmMin((() => {}));
//#endregion
//#region src/prompta/ui/changelogDialog.ts
function requiredElement$1(selector) {
	const element = document.querySelector(selector);
	if (!element) throw new Error("Missing required changelog UI element: " + selector);
	return element;
}
function escapeHtml(value) {
	return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll("\"", "&quot;").replaceAll("'", "&#039;");
}
function setTextIfChanged$1(element, value) {
	const text = String(value ?? "");
	if (element.textContent !== text) element.textContent = text;
}
function renderChangelogEntry(change) {
	const title = escapeHtml(change?.title || "");
	const hash = String(change?.hash || "").trim();
	const hashSuffix = hash ? "<span class=\"changelog-entry-hash\">#" + escapeHtml(hash) + "</span>" : "";
	return "<li class=\"changelog-entry\"><span class=\"changelog-entry-title\">" + title + "</span>" + hashSuffix + "</li>";
}
function createChangelogDialog({ fetchJson, closeSidebar }) {
	const els = {
		headLabel: requiredElement$1("#headLabel"),
		dialog: requiredElement$1("#changelogDialog"),
		closeButton: requiredElement$1("#closeChangelogDialog"),
		list: requiredElement$1("#changelogList"),
		status: requiredElement$1("#changelogDialogStatus")
	};
	const mobileChangelogScreen = window.matchMedia("(max-width: 600px)");
	const appShell = document.querySelector(".app-shell");
	function close() {
		if (els.dialog.open) els.dialog.close();
	}
	async function open() {
		closeSidebar();
		if (!els.dialog.open) {
			const stacked = mobileChangelogScreen.matches;
			els.dialog.dataset.presentation = stacked ? "stack" : "modal";
			if (stacked) {
				els.dialog.show();
				if (appShell) appShell.inert = true;
			} else els.dialog.showModal();
		}
		setTextIfChanged$1(els.status, "Loading changelog…");
		patchHtmlChildren$2(els.list, "<li class=\"changelog-empty\">Loading changes…</li>");
		try {
			const payload = await fetchJson("api/changelog");
			const changes = Array.isArray(payload.changes) ? payload.changes : [];
			patchHtmlChildren$2(els.list, changes.length ? changes.map(renderChangelogEntry).join("") : "<li class=\"changelog-empty\">No Git commit history is available.</li>");
			setTextIfChanged$1(els.status, changes.length + " commit" + (changes.length === 1 ? "" : "s") + " · newest first");
		} catch (error) {
			patchHtmlChildren$2(els.list, "<li class=\"changelog-empty\">Could not load changelog.</li>");
			setTextIfChanged$1(els.status, "Changelog unavailable: " + String(error).replace(/^Error:\s*/, ""));
		}
	}
	els.headLabel.addEventListener("click", () => void open());
	els.closeButton.addEventListener("click", close);
	els.dialog.addEventListener("click", (event) => {
		if (event.target === els.dialog && els.dialog.dataset.presentation !== "stack") close();
	});
	els.dialog.addEventListener("close", () => {
		if (appShell) appShell.inert = false;
		delete els.dialog.dataset.presentation;
	});
	return {
		open,
		close
	};
}
var init_changelogDialog = __esmMin((() => {
	init_domPatch();
}));
//#endregion
//#region src/prompta/ui/clientStorage.ts
function createClientSessionId() {
	return globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
function loadClientSessionId() {
	try {
		const existing = sessionStorage.getItem(CLIENT_SESSION_ID_KEY);
		if (existing) return existing;
		const created = createClientSessionId();
		sessionStorage.setItem(CLIENT_SESSION_ID_KEY, created);
		return created;
	} catch {
		return createClientSessionId();
	}
}
function loadPinnedIds() {
	try {
		const stored = JSON.parse(localStorage.getItem(PINNED_CHATS_KEY) || "[]");
		return new Set(Array.isArray(stored) ? stored.map((id) => String(id)) : []);
	} catch {
		return /* @__PURE__ */ new Set();
	}
}
function savePinnedIds(pinnedIds) {
	try {
		localStorage.setItem(PINNED_CHATS_KEY, JSON.stringify(Array.from(pinnedIds)));
	} catch {}
}
function loadComposerDrafts() {
	try {
		const stored = JSON.parse(localStorage.getItem(COMPOSER_DRAFTS_KEY) || "{}");
		if (!stored || Array.isArray(stored) || typeof stored !== "object") return /* @__PURE__ */ new Map();
		return new Map(Object.entries(stored).filter(([, value]) => typeof value === "string" && value).map(([key, value]) => [key, typeof value === "string" ? value : ""]));
	} catch {
		return /* @__PURE__ */ new Map();
	}
}
function saveComposerDrafts(composerDrafts) {
	try {
		localStorage.setItem(COMPOSER_DRAFTS_KEY, JSON.stringify(Object.fromEntries(composerDrafts)));
	} catch {}
}
var PINNED_CHATS_KEY, COMPOSER_DRAFTS_KEY, CLIENT_SESSION_ID_KEY;
var init_clientStorage = __esmMin((() => {
	PINNED_CHATS_KEY = "prompta:pinned-chats";
	COMPOSER_DRAFTS_KEY = "prompta:composer-drafts";
	CLIENT_SESSION_ID_KEY = "prompta:client-session-id";
}));
//#endregion
//#region src/prompta/ui/app.ts
var app_exports = /* @__PURE__ */ __exportAll({});
function persistPinChange(chatId, pinned) {
	postJsonRequest("api/pins", {
		id: chatId,
		pinned
	}, 2, 5e3).catch((error) => {
		console.warn("Could not persist Prompta pin change", error);
	});
}
function persistPinPromotion(previousId, nextId) {
	if (!previousId || !nextId || previousId === nextId) return;
	postJsonRequest("api/pins/promote", {
		from: previousId,
		to: nextId
	}, 2, 5e3).catch((error) => {
		console.warn("Could not persist Prompta pin promotion", error);
	});
}
function setChatPinned(chatId, pinned) {
	if (pinned) state.pinnedIds.add(chatId);
	else state.pinnedIds.delete(chatId);
	savePinnedIds(state.pinnedIds);
	persistPinChange(chatId, pinned);
	state.sidebarFingerprint = "";
}
function promotePendingConversationPin(pending, nextConversationId) {
	const previousId = pendingConversationDisplayId(pending);
	const changed = promotePinnedConversationId(state.pinnedIds, pending, nextConversationId);
	if (changed) {
		savePinnedIds(state.pinnedIds);
		persistPinPromotion(previousId, String(nextConversationId || ""));
		state.sidebarFingerprint = "";
	}
	return changed;
}
function promoteServerPendingPins(chats) {
	let changed = false;
	for (const chat of chats) {
		const clientId = String(chat._client_id || "").trim();
		if (!chat._pending_send || !clientId) continue;
		const pending = { clientId };
		const previousId = pendingConversationDisplayId(pending);
		const nextId = String(chat.id || "");
		const promoted = promotePinnedConversationId(state.pinnedIds, pending, nextId);
		if (promoted) persistPinPromotion(previousId, nextId);
		changed = promoted || changed;
	}
	if (changed) {
		savePinnedIds(state.pinnedIds);
		state.sidebarFingerprint = "";
	}
}
function syncViewportHeight() {
	const viewportHeight = window.visualViewport?.height || window.innerHeight;
	document.documentElement.style.setProperty("--app-height", `${Math.round(viewportHeight)}px`);
}
function requiredElement(selector) {
	const element = document.querySelector(selector);
	if (!element) throw new Error(`Missing required UI element: ${selector}`);
	return element;
}
function composerDraftTarget() {
	if (state.composingNew) return "new";
	return state.selectedId ? "chat:" + state.selectedId : "";
}
function setStoredComposerDraft(target, value) {
	if (!target) return;
	const draft = String(value || "");
	if (draft) state.composerDrafts.set(target, draft);
	else state.composerDrafts.delete(target);
	saveComposerDrafts(state.composerDrafts);
}
function persistComposerDraft() {
	const target = composerDraftTarget();
	if (!target) return;
	state.composerDraftTarget = target;
	setStoredComposerDraft(target, els.messageInput.value);
}
function clearComposerDraft(target = composerDraftTarget()) {
	if (!target) return;
	if (state.composerDrafts.delete(target)) saveComposerDrafts(state.composerDrafts);
}
function syncComposerDraftTarget() {
	const nextTarget = composerDraftTarget();
	if (nextTarget === state.composerDraftTarget) return;
	if (state.composerDraftTarget && !state.sending) setStoredComposerDraft(state.composerDraftTarget, els.messageInput.value);
	state.composerDraftTarget = nextTarget;
	const draft = nextTarget ? state.composerDrafts.get(nextTarget) || "" : "";
	if (els.messageInput.value !== draft) els.messageInput.value = draft;
	resizeComposer();
	updateSlashMenu();
	syncSendButton();
}
function setTextIfChanged(element, value) {
	const text = String(value ?? "");
	if (element.textContent !== text) element.textContent = text;
}
function setHiddenIfChanged(element, hidden) {
	if (element.hidden !== hidden) element.hidden = hidden;
}
function patchDomNode(current, next) {
	if (current.nodeType !== next.nodeType || current.nodeType === Node.ELEMENT_NODE && current.tagName !== next.tagName) {
		const replacement = next.cloneNode(true);
		current.replaceWith(replacement);
		return replacement;
	}
	if (current.nodeType === Node.TEXT_NODE) {
		if (current.data !== next.data) current.data = next.data;
		return current;
	}
	if (current.nodeType !== Node.ELEMENT_NODE) return current;
	const preserveDetailsOpen = current.tagName === "DETAILS" && next.tagName === "DETAILS";
	const detailsOpen = preserveDetailsOpen ? current.open : false;
	for (const attribute of Array.from(current.attributes)) {
		if (preserveDetailsOpen && attribute.name === "open") continue;
		if (!next.hasAttribute(attribute.name)) current.removeAttribute(attribute.name);
	}
	for (const attribute of Array.from(next.attributes)) {
		if (preserveDetailsOpen && attribute.name === "open") continue;
		if (current.getAttribute(attribute.name) !== attribute.value) current.setAttribute(attribute.name, attribute.value);
	}
	patchDomChildren(current, next);
	if (preserveDetailsOpen) current.open = detailsOpen;
	return current;
}
function domPatchKey(node) {
	if (!node || node.nodeType !== Node.ELEMENT_NODE) return "";
	return node.dataset.domKey || "";
}
function patchDomChildren(currentParent, nextParent) {
	let index = 0;
	while (index < nextParent.childNodes.length || index < currentParent.childNodes.length) {
		let current = currentParent.childNodes[index];
		const next = nextParent.childNodes[index];
		if (!next) {
			current.remove();
			continue;
		}
		if (!current) {
			currentParent.append(next.cloneNode(true));
			index += 1;
			continue;
		}
		const nextKey = domPatchKey(next);
		if (nextKey && domPatchKey(current) !== nextKey) {
			const match = Array.from(currentParent.childNodes).slice(index + 1).find((candidate) => domPatchKey(candidate) === nextKey);
			if (match) {
				currentParent.insertBefore(match, current);
				current = match;
			} else {
				currentParent.insertBefore(next.cloneNode(true), current);
				index += 1;
				continue;
			}
		}
		patchDomNode(current, next);
		index += 1;
	}
}
function patchHtmlChildren(element, html) {
	const template = document.createElement("template");
	template.innerHTML = html;
	patchDomChildren(element, template.content);
}
function setConversationHeading(title, meta) {
	let titleNode = els.chatHeading.querySelector(".heading-title");
	let metaNode = els.chatHeading.querySelector(".heading-meta");
	if (!titleNode) {
		titleNode = document.createElement("div");
		titleNode.className = "heading-title";
		els.chatHeading.prepend(titleNode);
	}
	if (!metaNode) {
		metaNode = document.createElement("div");
		metaNode.className = "heading-meta";
		els.chatHeading.append(metaNode);
	}
	setTextIfChanged(titleNode, title);
	setTextIfChanged(metaNode, meta);
}
function syncSendButton() {
	const waitingNew = state.composingNew && state.pendingNewSend && ![
		"failed",
		"dead_lettered",
		"succeeded"
	].includes(state.pendingNewSend.status);
	const hasTarget = state.composingNew || Boolean(state.selectedId);
	const hasContent = composerHasContent(els.messageInput.value, attachmentPicker.count());
	const canCompose = state.mode === "chats" && !els.messageInput.disabled && hasTarget;
	const stopMode = canCompose && shouldShowStopAction(state.selectedChat?.status, state.composingNew, hasContent);
	const probingActivity = Boolean(state.selectedId && state.activityProbes.has(state.selectedId));
	const action = stopMode ? "stop" : "send";
	if (els.sendButton.dataset.action !== action) {
		els.sendButton.dataset.action = action;
		patchHtmlChildren(els.sendButton, stopMode ? STOP_ICON : SEND_ICON);
		els.sendButton.setAttribute("aria-label", stopMode ? "Stop response" : "Send message");
		els.sendButton.title = stopMode ? "Stop response" : "Send message";
	}
	els.sendButton.disabled = !canCompose || state.sending || state.stopping || probingActivity || !stopMode && (Boolean(waitingNew) || !hasContent);
}
function updateComposerActionButton() {
	syncSendButton();
}
function displayServerName(value) {
	const raw = String(value || "").trim();
	if (!raw) return "";
	return raw.split(/[-_\s]+/).filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}
function setServerStatus(server, online) {
	const raw = String(server || "").trim();
	if (raw) state.serverName = raw;
	if (typeof online === "boolean") state.serverOnline = online;
	const display = displayServerName(state.serverName || location.hostname);
	const knownOnline = state.serverOnline;
	setTextIfChanged(els.serverLabel, knownOnline === false ? `Server · ${display} · offline` : `Server · ${display}`);
	document.title = `Prompta · ${display}`;
	logsPanel.setServerTitle(display);
	const appleTitle = document.querySelector("meta[name=\"apple-mobile-web-app-title\"]");
	if (appleTitle) appleTitle.setAttribute("content", `Prompta ${display}`);
	els.globalLiveOrb.classList.toggle("live", knownOnline === true);
	els.globalLiveOrb.title = knownOnline === false ? `${display} is offline` : knownOnline === true ? `${display} is online` : `${display} status unknown`;
}
function formatRelativeTime(epochSeconds) {
	if (!epochSeconds) return "";
	const delta = Date.now() - epochSeconds * 1e3;
	const abs = Math.abs(delta);
	if (abs < 45e3) return "now";
	if (abs < 36e5) return `${Math.max(1, Math.round(abs / 6e4))}m`;
	if (abs < 864e5) return `${Math.round(abs / 36e5)}h`;
	if (abs < 6048e5) return `${Math.round(abs / 864e5)}d`;
	return new Intl.DateTimeFormat(void 0, {
		month: "short",
		day: "numeric"
	}).format(/* @__PURE__ */ new Date(epochSeconds * 1e3));
}
function chatActivityAt(chat) {
	if (!chat) return 0;
	if (chat._optimisticNew || chat._optimisticReply || chat.status === "active") return Number(chat.updated_at || chat.last_message_at || 0);
	return Number(chat.last_message_at || chat.updated_at || 0);
}
function brokenChatLabel(chat) {
	const lastAssistantAt = chatLastAssistantAt(chat);
	if (lastAssistantAt) return "broken · ChatGPT last responded " + formatRelativeTime(lastAssistantAt);
	const referenceAt = chatBrokenReferenceAt(chat);
	return referenceAt ? "broken · no ChatGPT response · " + formatRelativeTime(referenceAt) : "broken";
}
function sameLocalDay(epochSeconds, offsetDays = 0) {
	if (!epochSeconds) return false;
	const d = /* @__PURE__ */ new Date(epochSeconds * 1e3);
	const target = /* @__PURE__ */ new Date();
	target.setDate(target.getDate() - offsetDays);
	return d.getFullYear() === target.getFullYear() && d.getMonth() === target.getMonth() && d.getDate() === target.getDate();
}
function chatTitle(chat) {
	const title = (chat.title || "").replace(/^ChatGPT\s*[-–—:]?\s*/i, "").trim();
	if (title && title.toLowerCase() !== "chatgpt") return title;
	if (chat.job_name) return chat.job_name.replaceAll("-", " ");
	const preview = sidebarPreviewText(chat.preview);
	if (preview) return preview.slice(0, 72);
	return "Untitled conversation";
}
function truncate(value, length = 88) {
	const text = String(value || "").replace(/\s+/g, " ").trim();
	return text.length <= length ? text : `${text.slice(0, length - 1)}…`;
}
function sidebarGroupAt(chat) {
	return sidebarChatCreatedAt(chat);
}
function groupChats(chats) {
	const ordered = sortSidebarChats(chats, state.pinnedIds);
	const pinned = ordered.filter((chat) => state.pinnedIds.has(chat.id));
	const unpinned = ordered.filter((chat) => !state.pinnedIds.has(chat.id));
	return [
		["Pinned", pinned],
		["Today", unpinned.filter((chat) => sameLocalDay(sidebarGroupAt(chat)))],
		["Yesterday", unpinned.filter((chat) => sameLocalDay(sidebarGroupAt(chat), 1))],
		["Previous", unpinned.filter((chat) => !sameLocalDay(sidebarGroupAt(chat)) && !sameLocalDay(sidebarGroupAt(chat), 1))]
	].filter(([, items]) => items.length);
}
function setStatusIcon(element, status, label, kind = "") {
	element.className = [
		"status-icon",
		kind,
		iconStatusClasses.has(status) ? status : "neutral"
	].filter(Boolean).join(" ");
	element.title = label;
	element.setAttribute("aria-label", label);
}
function reconcileOptimisticNew(chats) {
	const pending = state.pendingNewSend;
	if (!pending) return;
	const matched = matchingOptimisticConversation(chats, pending, new Set(state.chats.map((chat) => String(chat.id))));
	if (!matched) return;
	promotePendingConversationPin(pending, matched.id);
	pending.conversationId = matched.id;
	state.pendingNewId = matched.id;
	if (pending.status === "succeeded" && !matched._pending_send && !state.composingNew && state.selectedId !== matched.id) {
		state.pendingNewSend = null;
		state.pendingNewId = null;
	}
}
function sidebarChats() {
	const chats = state.chats.map((chat) => {
		const pending = state.pendingReplies.get(chat.id) || [];
		if (!pending.length) return chat;
		const latest = pending[pending.length - 1];
		return {
			...chat,
			status: ["failed", "dead_lettered"].includes(latest.status || "") ? chat.status : "active",
			preview: latest.message,
			updated_at: Math.max(Number(chat.updated_at || 0), Number(latest.updatedAt || 0)),
			_optimisticReply: true
		};
	});
	chats.unshift(...missingPendingConversationSummaries(chats, state.pendingReplies, state.search));
	const pending = state.pendingNewSend;
	if (!pending) return chats;
	const matched = matchingOptimisticConversation(chats, pending);
	if (matched) {
		promotePendingConversationPin(pending, matched.id);
		pending.conversationId = matched.id;
		state.pendingNewId = matched.id;
		return chats;
	}
	const optimistic = {
		id: pendingConversationDisplayId(pending),
		status: ["failed", "dead_lettered"].includes(pending.status) ? pending.status : "active",
		title: truncate(pending.message, 72) || "New chat",
		preview: pending.message,
		message_count: 1,
		job_name: "new chat",
		created_at: pending.createdAt,
		updated_at: pending.updatedAt,
		_optimisticNew: true
	};
	const needle = state.search.trim().toLowerCase();
	if (needle && ![
		optimistic.title,
		optimistic.preview,
		optimistic.job_name
	].some((value) => String(value || "").toLowerCase().includes(needle))) return chats;
	return [optimistic, ...chats];
}
function scrollSidebarToNewest() {
	if (els.sidebarScroll.scrollTop) els.sidebarScroll.scrollTop = 0;
}
function renderSidebar(force = false) {
	if (sidebar.isMoving()) {
		sidebarRenderDeferred = true;
		return;
	}
	const chats = sidebarChats();
	const pendingNewDisplayId = state.composingNew ? pendingConversationDisplayId(state.pendingNewSend) : "";
	const selectionId = sidebarSelectedConversationId(state.selectedId, state.composingNew, pendingNewDisplayId);
	const fingerprint = JSON.stringify(chats.map((chat) => [
		chat.id,
		chat.status,
		chat.title,
		sidebarChatPreviewText(chat.preview, chat.prompt),
		chat.message_count,
		chat.job_name,
		chatActivityAt(chat),
		chatIsBroken(chat),
		Boolean(chat._optimisticNew),
		Boolean(chat._optimisticReply),
		state.pinnedIds.has(chat.id)
	])) + (/* @__PURE__ */ new Date()).toDateString() + selectionId;
	if (!force && fingerprint === state.sidebarFingerprint) return;
	state.sidebarFingerprint = fingerprint;
	if (!chats.length) {
		sidebarList.update({
			emptyState: state.search ? "search" : "empty",
			groups: []
		});
		return;
	}
	sidebarList.update({
		emptyState: "none",
		groups: groupChats(chats).map(([label, groupedChats]) => ({
			label,
			chats: groupedChats.map((chat) => {
				const selected = sidebarChatIsSelected(chat, state.selectedId, state.composingNew, pendingNewDisplayId);
				const broken = chatIsBroken(chat);
				let statusClass = null;
				if (broken) statusClass = "broken";
				else if (chat.status !== "interrupted") statusClass = chat.status === "active" || chat.status === "complete" ? chat.status : "neutral";
				const activityAt = chatActivityAt(chat);
				return {
					id: chat.id,
					selected,
					optimisticNew: Boolean(chat._optimisticNew),
					statusClass,
					broken,
					statusLabel: broken ? "No ChatGPT response for at least 40 minutes" : String(chat.status || ""),
					title: String(chatTitle(chat)),
					preview: truncate(sidebarChatPreviewText(chat.preview, chat.prompt) || "Waiting for messages…"),
					jobLabel: String(chat.job_name || String(chat.message_count || 0) + " messages"),
					activityAt,
					relativeTime: formatRelativeTime(activityAt),
					pinned: state.pinnedIds.has(chat.id)
				};
			})
		}))
	});
}
function pendingReplyMessages(conversationId, cachedMessages) {
	const pending = pendingConversationSends(conversationId, state.pendingReplies.get(conversationId) || [], state.pendingNewSend);
	const claimedCachedIndexes = /* @__PURE__ */ new Set();
	for (const item of pending) {
		const matchedIndex = matchingPendingReplyMessageIndex(cachedMessages, item, claimedCachedIndexes);
		if (matchedIndex >= 0) {
			claimedCachedIndexes.add(matchedIndex);
			item.observedInCache = true;
			item.responseObservedInCache = cachedMessages.slice(matchedIndex + 1).some((message) => message.role === "assistant" && !message.send_error);
			const cachedMessage = cachedMessages[matchedIndex];
			if (cachedMessage && !imageAttachments(cachedMessage).length && imageAttachments(item).length) cachedMessage.attachments = item.attachments;
		}
	}
	const remaining = pending.filter((item) => {
		if (!item.observedInCache) return true;
		if (item.responseObservedInCache) return false;
		return Boolean(pendingSendActivity(item.status, Boolean(item.sendId), item.retryAfterSeconds, item.retryAt, void 0, item.queuePosition));
	});
	if (remaining.length) state.pendingReplies.set(conversationId, remaining);
	else state.pendingReplies.delete(conversationId);
	return remaining.flatMap((item) => {
		const messages = [];
		if (!item.observedInCache) messages.push({
			message_key: `pending-user-${item.clientId || item.sendId}`,
			role: "user",
			content: item.message,
			attachments: item.attachments || [],
			status: "complete",
			updated_at: item.updatedAt,
			pending_delete_key: item.clientId || item.sendId || ""
		});
		const activity = pendingSendActivity(item.status, Boolean(item.sendId), item.retryAfterSeconds, item.retryAt, void 0, item.queuePosition);
		if (activity) messages.push({
			message_key: `pending-activity-${item.clientId || item.sendId}`,
			role: "assistant",
			content: "",
			status: "pending",
			updated_at: item.updatedAt,
			pending_activity: true,
			pending_activity_label: activity.label
		});
		else if (["failed", "dead_lettered"].includes(item.status || "")) messages.push({
			message_key: `pending-error-${item.clientId || item.sendId}`,
			role: "assistant",
			content: `Send failed: ${item.error || "Unknown Prompta send error"}`,
			status: "complete",
			updated_at: item.updatedAt,
			send_error: true,
			retry_scope: "reply",
			retry_key: item.clientId || item.sendId || ""
		});
		return messages;
	});
}
function updatePinButton() {
	const chatId = state.selectedId;
	const available = Boolean(chatId) && !state.composingNew;
	const pinned = Boolean(available && chatId && state.pinnedIds.has(chatId));
	els.pinChatButton.disabled = !available;
	els.pinChatButton.classList.toggle("active", Boolean(pinned));
	els.pinChatButton.setAttribute("aria-pressed", String(Boolean(pinned)));
	const label = pinned ? "Unpin chat" : "Pin chat";
	els.pinChatButton.title = label;
	els.pinChatButton.setAttribute("aria-label", label);
}
function toggleSelectedPin() {
	const chatId = state.selectedId;
	if (!chatId || state.composingNew) return;
	setChatPinned(chatId, !state.pinnedIds.has(chatId));
	renderSidebar(true);
	updatePinButton();
}
function renderConversationMeta(chat, visibleMessageCount) {
	const title = chatTitle(chat);
	const broken = chatIsBroken(chat);
	const activityLabel = broken ? brokenChatLabel(chat) : chat.status === "active" ? "updating live" : chat.status === "interrupted" ? `interrupted · ${formatRelativeTime(chatActivityAt(chat))}` : formatRelativeTime(chatActivityAt(chat));
	const meta = [
		chat.job_name || "one-shot",
		`${visibleMessageCount} message${visibleMessageCount === 1 ? "" : "s"}`,
		activityLabel
	].join(" · ");
	const metaFingerprint = JSON.stringify([
		title,
		meta,
		chat.status,
		broken
	]);
	if (metaFingerprint === state.selectedMetaFingerprint) return;
	state.selectedMetaFingerprint = metaFingerprint;
	setConversationHeading(title, meta);
	const syncStatus = broken ? "broken" : chat.status === "active" ? "active" : chat.status === "interrupted" ? "interrupted" : "cached";
	const syncLabel = broken ? "No ChatGPT response for at least 40 minutes" : chat.status === "active" ? "Syncing from SQLite" : chat.status === "interrupted" ? "Last run was interrupted" : "Cached in SQLite";
	setStatusIcon(els.syncLabel, syncStatus, syncLabel, "sync");
}
function rememberConversationViewport(conversationId) {
	if (!conversationId || state.renderedConversationId !== conversationId) return;
	const snapshot = {
		...conversationRenderer.captureConversationViewport(),
		anchorElement: null
	};
	state.conversationViewports.delete(conversationId);
	state.conversationViewports.set(conversationId, snapshot);
	while (state.conversationViewports.size > 20) {
		const oldest = state.conversationViewports.keys().next().value;
		if (!oldest) break;
		state.conversationViewports.delete(oldest);
	}
}
function beginChatSwitch() {
	state.chatSwitchToken += 1;
	els.viewport.classList.add("chat-switching");
	els.viewport.setAttribute("aria-busy", "true");
}
function cancelChatSwitch() {
	state.chatSwitchToken += 1;
	els.viewport.classList.remove("chat-switching");
	els.viewport.removeAttribute("aria-busy");
}
function finishChatSwitch(conversationId) {
	if (!els.viewport.classList.contains("chat-switching")) return;
	const token = state.chatSwitchToken;
	requestAnimationFrame(() => {
		if (token !== state.chatSwitchToken || state.selectedId !== conversationId) return;
		getComputedStyle(els.conversation).opacity;
		els.viewport.classList.remove("chat-switching");
		els.viewport.removeAttribute("aria-busy");
	});
}
function renderConversation(chat) {
	state.selectedChat = chat;
	const messages = Array.isArray(chat.messages) ? chat.messages : [];
	const visibleMessages = [...messages, ...pendingReplyMessages(chat.id, messages)];
	state.selectedVisibleMessageCount = visibleMessages.length;
	const allowStreaming = chat.status === "active";
	const fingerprint = JSON.stringify([chat.status, visibleMessages.map((message) => [message.message_key, conversationRenderer.messageNodeFingerprint(message, allowStreaming)])]);
	if (fingerprint !== state.selectedFingerprint) {
		const isInitial = state.renderedConversationId !== chat.id;
		const rememberedViewport = isInitial ? state.conversationViewports.get(chat.id) : null;
		const viewportSnapshot = rememberedViewport || conversationRenderer.captureConversationViewport();
		state.selectedFingerprint = fingerprint;
		conversationRenderer.renderMessageNodes(visibleMessages, allowStreaming);
		state.renderedConversationId = chat.id;
		conversationRenderer.restoreConversationViewport(viewportSnapshot, isInitial && !rememberedViewport);
	}
	finishChatSwitch(chat.id);
	renderConversationMeta(chat, visibleMessages.length);
	setHiddenIfChanged(els.emptyState, true);
	setHiddenIfChanged(els.conversation, false);
	els.messageInput.disabled = false;
	state.composingNew = false;
	syncComposerDraftTarget();
	syncSendButton();
	els.shareChatButton.disabled = false;
	updatePinButton();
	syncSendButton();
	const pendingActivity = [...state.pendingReplies.get(chat.id) || []].reverse().map((item) => pendingSendActivity(item.status, Boolean(item.sendId), item.retryAfterSeconds, item.retryAt, void 0, item.queuePosition)).find(Boolean);
	if (pendingActivity) setTextIfChanged(els.composerStatus, pendingActivity.statusText);
	else if (!state.sending) setTextIfChanged(els.composerStatus, chat.status === "active" ? "Uses the existing live ChatGPT tab." : chat.status === "interrupted" ? "The last run was interrupted. Sending will reopen this chat." : "Sending will reopen this chat once if its retained tab has expired.");
}
function showMode(mode) {
	state.mode = mode === "logs" ? "logs" : "chats";
	const logsMode = state.mode === "logs";
	els.viewport.hidden = logsMode;
	logsPanel.setVisible(logsMode);
	els.composerFooter.hidden = logsMode;
	if (logsMode) {
		cancelChatSwitch();
		state.selectedMetaFingerprint = "";
		const display = displayServerName(state.serverName || location.hostname);
		setConversationHeading(`${display} Prompta logs`, `journalctl · prompta.service · ${display}`);
		setStatusIcon(els.syncLabel, "journal", `${display} journal`, "sync");
		els.messageInput.disabled = true;
		els.sendButton.disabled = true;
		els.shareChatButton.disabled = true;
		setTextIfChanged(els.composerStatus, "Switch back to chats to send a message.");
		updateComposerActionButton();
		return;
	}
	if (state.selectedId) loadSelectedChat();
	else if (state.composingNew) renderNewChat();
	else clearConversation();
}
function clearConversation() {
	cancelChatSwitch();
	state.composingNew = false;
	state.selectedId = null;
	state.selectedUpdatedAt = null;
	state.selectedFingerprint = "";
	state.selectedMetaFingerprint = "";
	state.selectedChat = null;
	state.renderedConversationId = "";
	setHiddenIfChanged(els.emptyState, false);
	setHiddenIfChanged(els.conversation, true);
	conversationRenderer.renderMessageNodes([], false);
	setConversationHeading("Prompta", "Local conversation history");
	setStatusIcon(els.syncLabel, "local", "Local cache", "sync");
	els.messageInput.disabled = true;
	els.sendButton.disabled = true;
	els.shareChatButton.disabled = true;
	updatePinButton();
	els.messageInput.placeholder = "Message Prompta…";
	setTextIfChanged(els.composerStatus, "");
	syncComposerDraftTarget();
	updateComposerActionButton();
}
function renderNewChat() {
	cancelChatSwitch();
	const enteringNewChat = !state.composingNew;
	state.composingNew = true;
	state.selectedId = null;
	state.selectedUpdatedAt = null;
	state.selectedFingerprint = "";
	state.selectedChat = null;
	state.renderedConversationId = "";
	state.mode = "chats";
	syncComposerDraftTarget();
	const pending = state.pendingNewSend;
	const waiting = pending && ![
		"failed",
		"dead_lettered",
		"succeeded"
	].includes(pending.status);
	const fingerprint = JSON.stringify([
		pending?.sendId || "",
		pending?.message || "",
		pending?.status || "",
		pending?.error || "",
		pending?.conversationId || "",
		pending?.retryAfterSeconds || 0,
		pending?.retryAt || 0,
		pending?.retryAttempt || 0,
		pending?.queuePosition || 0,
		imageAttachments(pending).map((attachment) => [
			attachment.id || "",
			attachment.name || "",
			attachment.type || "",
			String(attachment.src || "").length
		])
	]);
	if (shouldRenderNewChatView(enteringNewChat, fingerprint, state.newChatFingerprint)) {
		state.newChatFingerprint = fingerprint;
		if (pending) {
			const messages = [{
				message_key: `pending-user-${pending.clientId || pending.sendId}`,
				role: "user",
				content: pending.message,
				attachments: pending.attachments || [],
				status: "complete",
				updated_at: pending.updatedAt,
				pending_delete_key: pending.clientId || pending.sendId || ""
			}];
			const activity = pendingSendActivity(pending.status, Boolean(pending.sendId), pending.retryAfterSeconds, pending.retryAt, void 0, pending.queuePosition);
			if (activity) messages.push({
				message_key: `pending-activity-${pending.clientId || pending.sendId}`,
				role: "assistant",
				content: "",
				status: "pending",
				updated_at: pending.updatedAt,
				pending_activity: true,
				pending_activity_label: activity.label
			});
			else if (["failed", "dead_lettered"].includes(pending.status)) messages.push({
				message_key: `pending-error-${pending.clientId || pending.sendId}`,
				role: "assistant",
				content: `Send failed: ${pending.error || "Unknown Prompta send error"}`,
				status: "complete",
				updated_at: pending.updatedAt,
				send_error: true,
				retry_scope: "new",
				retry_key: pending.clientId || pending.sendId
			});
			const viewportSnapshot = conversationRenderer.captureConversationViewport();
			setHiddenIfChanged(els.emptyState, true);
			setHiddenIfChanged(els.conversation, false);
			conversationRenderer.renderMessageNodes(messages, true);
			conversationRenderer.restoreConversationViewport(viewportSnapshot, enteringNewChat);
		} else {
			setHiddenIfChanged(els.emptyState, false);
			setHiddenIfChanged(els.conversation, true);
			conversationRenderer.renderMessageNodes([], false);
		}
		setConversationHeading("New chat", pending ? "Queued through the live Prompta session" : "Starts a fresh ChatGPT conversation");
		setStatusIcon(els.syncLabel, pending ? "queued" : "new", pending ? "Send queued" : "Fresh conversation", "sync");
		els.messageInput.disabled = false;
		syncSendButton();
		els.shareChatButton.disabled = true;
		updatePinButton();
		els.messageInput.placeholder = "Start a new chat…";
		const activity = pending ? pendingSendActivity(pending.status, Boolean(pending.sendId), pending.retryAfterSeconds, pending.retryAt, void 0, pending.queuePosition) : null;
		setTextIfChanged(els.composerStatus, pending ? ["failed", "dead_lettered"].includes(pending.status) ? pending.status === "dead_lettered" ? "Send exhausted its retry budget. Retry to enqueue it again." : "Send failed. The error is shown in the chat." : activity?.statusText || "Sent. Waiting for the cached response…" : "");
	}
	updateComposerActionButton();
	if (enteringNewChat) {
		els.viewport.hidden = false;
		logsPanel.setVisible(false);
		history.replaceState(null, "", `${location.pathname}${location.search}`);
		renderSidebar();
		scrollSidebarToNewest();
		sidebar.close();
		if (!waiting && matchMedia("(pointer: fine)").matches) requestAnimationFrame(() => els.messageInput.focus());
	}
}
async function fetchJson(url, timeoutMs = 1e4, controller = new AbortController()) {
	const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
	try {
		const response = await fetch(url, {
			cache: "no-store",
			signal: controller.signal
		});
		if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
		return await response.json();
	} finally {
		window.clearTimeout(timeout);
	}
}
async function hydratePinnedIds() {
	const cachedIds = new Set(state.pinnedIds);
	try {
		let payload = await fetchJson("api/pins", 2e3);
		if (!payload?.initialized && cachedIds.size) payload = await postJsonRequest("api/pins/seed", { ids: Array.from(cachedIds) }, 1, 2e3);
		if (!payload?.initialized || !Array.isArray(payload.ids)) return;
		state.pinnedIds = new Set(payload.ids.map((id) => String(id || "").trim()).filter(Boolean));
		savePinnedIds(state.pinnedIds);
		state.sidebarFingerprint = "";
	} catch (error) {
		console.warn("Could not hydrate Prompta pins; using browser cache", error);
	}
}
async function hydrateRecentChatCache() {
	let timeout;
	const cached = await Promise.race([Promise.all([recentChatCache.warm(), recentChatCache.warmSummaries()]), new Promise((resolve) => {
		timeout = window.setTimeout(() => resolve(null), 500);
	})]);
	if (timeout !== void 0) window.clearTimeout(timeout);
	if (!cached) return false;
	const [cachedChats, cachedSummaries] = cached;
	const sidebarSnapshot = cachedSummaries.length ? cachedSummaries : cachedChats;
	if (!sidebarSnapshot.length || state.search) return false;
	const unique = /* @__PURE__ */ new Map();
	for (const chat of sidebarSnapshot) if (chat?.id && !unique.has(chat.id)) unique.set(chat.id, chat);
	state.chats = sortSidebarChats(Array.from(unique.values()), state.pinnedIds);
	state.chatOrderScope = "";
	const activeCount = state.chats.filter((chat) => chat.status === "active").length;
	setTextIfChanged(els.cacheSummary, sidebarChatCountSummary(state.chats.length, activeCount, state.search));
	const initialId = conversationIdFromHash(location.hash) || state.chats[0]?.id || "";
	if (initialId) {
		state.selectedId = initialId;
		const chat = recentChatCache.getMemory(initialId);
		if (chat) {
			state.selectedUpdatedAt = chat.updated_at;
			renderConversation(chat);
		} else {
			conversationRenderer.renderLoadingState();
			setHiddenIfChanged(els.emptyState, true);
			setHiddenIfChanged(els.conversation, false);
		}
	}
	renderSidebar();
	return true;
}
async function loadServerIdentity() {
	try {
		const payload = await fetchJson("api/health");
		setServerStatus(payload.server, payload.online);
		const head = String(payload.head || "").trim().toLowerCase();
		deploymentMonitor.observeHead(head);
		setTextIfChanged(els.headLabel, head ? head : "unknown");
		els.headLabel.title = head ? "UI commit " + head : "UI commit unavailable";
	} catch (error) {
		setServerStatus(state.serverName || location.hostname, false);
		console.warn("Could not load Prompta server identity", error);
	}
}
async function hydratePendingSends() {
	try {
		const payload = await fetchJson("api/sends");
		const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
		for (const job of jobs) {
			const status = String(job.status || "queued");
			const sendId = String(job.send_id || "");
			if (!sendId || [
				"succeeded",
				"failed",
				"dead_lettered"
			].includes(status)) continue;
			const conversationId = String(job.conversation_id || "");
			const pending = {
				sendId,
				clientId: String(job.client_id || ""),
				message: String(job.message || ""),
				status,
				error: String(job.error || ""),
				conversationId,
				origin: job.operation === "once" ? "new" : "reply",
				createdAt: Number(job.created_at || Date.now() / 1e3),
				updatedAt: Number(job.updated_at || Date.now() / 1e3),
				retryAfterSeconds: Number(job.retry_after_seconds || 0),
				retryAt: Number(job.retry_at || 0),
				retryAttempt: Number(job.retry_attempt || 0),
				queuePosition: Number(job.queue_position || 0),
				attachmentNames: Array.isArray(job.attachment_names) ? job.attachment_names.map((value) => String(value)) : []
			};
			if (job.operation === "reply" && conversationId) {
				const items = state.pendingReplies.get(conversationId) || [];
				if (!items.some((item) => item.sendId === sendId)) {
					items.push(pending);
					items.sort((left, right) => Number(left.createdAt || 0) - Number(right.createdAt || 0));
					state.pendingReplies.set(conversationId, items);
				}
				watchSend(sendId, false, conversationId);
			} else if (job.operation === "once" && !conversationId && !state.pendingNewSend && clientIdBelongsToSession(pending.clientId, clientSessionId)) {
				state.pendingNewSend = pending;
				state.composingNew = true;
				watchSend(sendId, true, "");
			}
		}
	} catch (error) {
		console.warn("Could not hydrate pending Prompta sends", error);
	}
}
async function loadChats(forceSelectedRefresh = false) {
	const requestId = ++state.chatsRequestId;
	chatsRequestController?.abort();
	const requestController = new AbortController();
	chatsRequestController = requestController;
	try {
		const payload = await fetchJson(chatListRequestUrl(state.search, state.pinnedIds), 1e4, requestController);
		if (requestId !== state.chatsRequestId) return;
		const chats = payload.chats || [];
		promoteServerPendingPins(chats);
		reconcileOptimisticNew(chats);
		const orderedChats = sortSidebarChats(chats, state.pinnedIds);
		if (!state.search) recentChatCache.rememberSummaries(orderedChats);
		completionNotifications.trackCompletions(chats);
		state.chats = orderedChats;
		state.chatOrderScope = state.search;
		const activeCount = state.chats.filter((chat) => chat.status === "active").length;
		setTextIfChanged(els.cacheSummary, sidebarChatCountSummary(state.chats.length, activeCount, state.search));
		const hashId = conversationIdFromHash(location.hash);
		if (!state.selectedId && hashId) state.selectedId = hashId;
		state.selectedId = selectedConversationAfterChatRefresh(state.selectedId, state.composingNew, state.chats);
		renderSidebar();
		if (state.mode === "chats") {
			if (state.selectedId) {
				if (shouldRefreshSelectedChat(state.chats.find((chat) => chat.id === state.selectedId), state.selectedUpdatedAt, state.selectedFingerprint, forceSelectedRefresh)) await loadSelectedChat();
			} else if (!state.composingNew) clearConversation();
		} else await logsPanel.load();
	} catch (error) {
		if (requestId !== state.chatsRequestId) return;
		if (els.globalLiveOrb.classList.contains("live")) els.globalLiveOrb.classList.remove("live");
		setTextIfChanged(els.cacheSummary, "Cache unavailable");
		console.error(error);
	} finally {
		if (chatsRequestController === requestController) chatsRequestController = null;
	}
}
async function probeHistoricalActivity(conversationId) {
	if (!conversationId || !shouldProbeHistoricalActivity(state.selectedChat?.status)) return;
	const now = Date.now();
	const lastProbeAt = Number(state.activityProbeAt.get(conversationId) || 0);
	if (state.activityProbes.has(conversationId) || now - lastProbeAt < HISTORICAL_ACTIVITY_PROBE_TTL_MS) return;
	state.activityProbeAt.set(conversationId, now);
	state.activityProbes.add(conversationId);
	if (state.selectedId === conversationId) {
		setTextIfChanged(els.composerStatus, "Checking whether ChatGPT is still running…");
		syncSendButton();
	}
	try {
		const payload = await postJsonRequest("api/chats/" + encodeURIComponent(conversationId) + "/probe", {}, 1, 3e4);
		if (state.selectedId !== conversationId || state.mode !== "chats") return;
		const chat = payload?.chat;
		if (!chat || chat.id !== conversationId) return;
		state.selectedUpdatedAt = chat.updated_at;
		recentChatCache.remember(chat);
		renderConversation(chat);
		await loadChats();
	} catch (error) {
		if (state.selectedId === conversationId) setTextIfChanged(els.composerStatus, "Could not verify whether this interrupted chat is still running.");
		console.warn("Could not probe historical chat activity", error);
	} finally {
		state.activityProbes.delete(conversationId);
		if (state.selectedId === conversationId) syncSendButton();
	}
}
function renderRecentChatSnapshot(conversationId) {
	if (!conversationId || state.mode !== "chats") return;
	const memoryChat = recentChatCache.getMemory(conversationId);
	if (memoryChat) {
		state.selectedUpdatedAt = memoryChat.updated_at;
		renderConversation(memoryChat);
		return;
	}
	if (!state.renderedConversationId) {
		conversationRenderer.renderLoadingState();
		setHiddenIfChanged(els.emptyState, true);
		setHiddenIfChanged(els.conversation, false);
	}
	recentChatCache.get(conversationId).then((chat) => {
		if (!chat || state.mode !== "chats" || state.selectedId !== conversationId || state.selectedChat?.id === conversationId) return;
		state.selectedUpdatedAt = chat.updated_at;
		renderConversation(chat);
	});
}
async function loadSelectedChat() {
	if (!state.selectedId || state.mode !== "chats") return;
	const selectedId = state.selectedId;
	if (!state.selectedChat || state.selectedChat.id !== selectedId) renderRecentChatSnapshot(selectedId);
	const requestId = ++state.selectedRequestId;
	try {
		const chat = await fetchJson(`api/chats/${encodeURIComponent(selectedId)}`, 3e4);
		if (requestId !== state.selectedRequestId || selectedId !== state.selectedId || chat.id !== state.selectedId) return;
		if (state.pendingNewId === chat.id && !state.pendingNewSend) state.pendingNewId = null;
		state.selectedUpdatedAt = chat.updated_at;
		recentChatCache.remember(chat);
		renderConversation(chat);
		if (shouldProbeHistoricalActivity(chat.status)) probeHistoricalActivity(chat.id);
	} catch (error) {
		if (requestId !== state.selectedRequestId || selectedId !== state.selectedId) return;
		const missing = String(error).startsWith("Error: 404");
		if (missing && state.pendingNewId !== state.selectedId) {
			recentChatCache.remove(selectedId);
			if (conversationIdFromHash(location.hash) === selectedId) history.replaceState(null, "", `${location.pathname}${location.search}`);
			clearConversation();
		}
		if (!missing || state.pendingNewId !== state.selectedId) console.error(error);
		finishChatSwitch(selectedId);
	}
}
async function selectChat(id) {
	if (!id) return;
	if (state.mode !== "chats") showMode("chats");
	sidebar.close();
	if (id === state.selectedId) {
		if (!state.selectedChat || state.selectedChat.id !== id) await loadSelectedChat();
		return;
	}
	rememberConversationViewport(state.selectedId);
	beginChatSwitch();
	const pendingNew = state.pendingNewSend?.conversationId === id ? state.pendingNewSend : null;
	state.composingNew = false;
	state.pendingNewId = pendingNew ? id : null;
	els.messageInput.placeholder = "Message Prompta…";
	state.selectedId = id;
	state.selectedUpdatedAt = null;
	state.selectedFingerprint = "";
	state.selectedMetaFingerprint = "";
	state.selectedChat = null;
	history.replaceState(null, "", `#/${encodeURIComponent(id)}`);
	renderSidebar();
	await loadSelectedChat();
}
function resizeComposer() {
	els.messageInput.style.overflowY = "hidden";
	if (!els.messageInput.value) {
		els.messageInput.style.height = "34px";
		return;
	}
	els.messageInput.style.height = "auto";
	const contentHeight = els.messageInput.scrollHeight;
	els.messageInput.style.height = `${Math.min(180, contentHeight)}px`;
	els.messageInput.style.overflowY = contentHeight > 180 ? "auto" : "hidden";
}
async function runScheduleSlashCommand(command, originalMessage) {
	state.sending = true;
	els.messageInput.disabled = true;
	els.sendButton.disabled = true;
	attachmentPicker.setDisabled(true);
	clearComposerDraft();
	els.messageInput.value = "";
	resizeComposer();
	updateComposerActionButton();
	setTextIfChanged(els.composerStatus, "Saving schedule…");
	try {
		const result = await postJsonRequest("api/schedule", {
			interval_minutes: command.intervalMinutes,
			prompt: command.prompt
		});
		const server = displayServerName(result.server || state.serverName || location.hostname);
		const interval = formatScheduleInterval(Number(result.interval_minutes));
		const prefix = result.created === false ? "Already scheduled" : "Scheduled";
		setTextIfChanged(els.composerStatus, `${prefix} on ${server}: every ${interval} · ${command.prompt}`);
	} catch (error) {
		els.messageInput.value = originalMessage;
		persistComposerDraft();
		resizeComposer();
		updateSlashMenu();
		setTextIfChanged(els.composerStatus, `Schedule failed: ${String(error).replace(/^Error:\s*/, "")}`);
		console.error(error);
	} finally {
		state.sending = false;
		els.messageInput.disabled = false;
		attachmentPicker.setDisabled(false);
		syncSendButton();
		if (matchMedia("(pointer: fine)").matches) els.messageInput.focus();
	}
}
async function runAtSlashCommand(command, originalMessage) {
	state.sending = true;
	els.messageInput.disabled = true;
	els.sendButton.disabled = true;
	attachmentPicker.setDisabled(true);
	clearComposerDraft();
	els.messageInput.value = "";
	resizeComposer();
	updateSlashMenu();
	setTextIfChanged(els.composerStatus, "Saving one-time schedule…");
	try {
		const server = displayServerName((await postJsonRequest("api/schedule-at", {
			run_at_epoch: command.runAtEpoch,
			prompt: command.prompt
		})).server || state.serverName || location.hostname);
		setTextIfChanged(els.composerStatus, `Scheduled on ${server}: ${command.runAtLabel} · ${command.prompt}`);
	} catch (error) {
		els.messageInput.value = originalMessage;
		persistComposerDraft();
		resizeComposer();
		updateSlashMenu();
		setTextIfChanged(els.composerStatus, `Schedule failed: ${String(error).replace(/^Error:\s*/, "")}`);
		console.error(error);
	} finally {
		state.sending = false;
		els.messageInput.disabled = false;
		attachmentPicker.setDisabled(false);
		syncSendButton();
		if (matchMedia("(pointer: fine)").matches) els.messageInput.focus();
	}
}
function pendingReply(conversationId, sendId) {
	return (state.pendingReplies.get(conversationId) || []).find((item) => item.sendId === sendId);
}
function updatePendingReply(conversationId, sendId, updates) {
	const item = pendingReply(conversationId, sendId);
	if (!item) return false;
	const previous = JSON.stringify([
		item.status || "",
		item.error || "",
		item.retryAfterSeconds || 0,
		item.retryAt || 0,
		item.retryAttempt || 0,
		item.queuePosition || 0
	]);
	Object.assign(item, updates);
	const changed = JSON.stringify([
		item.status || "",
		item.error || "",
		item.retryAfterSeconds || 0,
		item.retryAt || 0,
		item.retryAttempt || 0,
		item.queuePosition || 0
	]) !== previous;
	if (changed) item.updatedAt = Date.now() / 1e3;
	return changed;
}
function setPendingDeleteBusy(deleteKey, busy) {
	for (const button of els.conversation.querySelectorAll(".delete-pending-button")) {
		if (button.dataset.deletePendingKey !== deleteKey) continue;
		button.disabled = busy;
		button.toggleAttribute("aria-busy", busy);
		button.closest(".message")?.classList.toggle("pending-message-deleting", busy);
	}
}
async function deletePendingSend(deleteKey) {
	let pending = null;
	let creatingNew = false;
	const conversationId = state.selectedId || "";
	if (state.pendingNewSend && (state.pendingNewSend.clientId === deleteKey || state.pendingNewSend.sendId === deleteKey)) {
		pending = state.pendingNewSend;
		creatingNew = true;
	} else if (conversationId) pending = (state.pendingReplies.get(conversationId) || []).find((item) => item.clientId === deleteKey || item.sendId === deleteKey) || null;
	if (!pending) return;
	const sendId = String(pending.sendId || "");
	if (!sendId) {
		setTextIfChanged(els.composerStatus, "Message is still entering the queue. Try deleting again.");
		return;
	}
	setPendingDeleteBusy(deleteKey, true);
	try {
		await deleteRequest("api/sends/" + encodeURIComponent(sendId));
	} catch (error) {
		setPendingDeleteBusy(deleteKey, false);
		console.warn("Could not delete pending Prompta send", error);
		setTextIfChanged(els.composerStatus, "Could not delete the pending message.");
		return;
	}
	if (creatingNew) {
		if (state.pendingNewSend === pending) {
			state.pendingNewSend = null;
			state.pendingNewId = null;
			state.newChatFingerprint = "";
		}
	} else {
		const remaining = (state.pendingReplies.get(conversationId) || []).filter((item) => item !== pending);
		if (remaining.length) state.pendingReplies.set(conversationId, remaining);
		else state.pendingReplies.delete(conversationId);
		if (state.selectedId === conversationId) state.selectedFingerprint = "";
	}
	if (creatingNew && state.composingNew) renderNewChat();
	else if (state.selectedChat?.id === conversationId) renderConversation(state.selectedChat);
	renderSidebar();
}
async function editPendingSend(editKey) {
	let pending = null;
	let creatingNew = false;
	const conversationId = state.selectedId || "";
	if (state.pendingNewSend && (state.pendingNewSend.clientId === editKey || state.pendingNewSend.sendId === editKey)) {
		pending = state.pendingNewSend;
		creatingNew = true;
	} else if (conversationId) pending = (state.pendingReplies.get(conversationId) || []).find((item) => item.clientId === editKey || item.sendId === editKey) || null;
	if (!pending) return;
	const sendId = String(pending.sendId || "");
	if (!sendId) {
		setTextIfChanged(els.composerStatus, "Message is still entering the queue. Try editing again.");
		return;
	}
	try {
		await deleteRequest("api/sends/" + encodeURIComponent(sendId));
	} catch (error) {
		console.warn("Could not cancel pending Prompta send for editing", error);
		setTextIfChanged(els.composerStatus, "Could not edit the pending message.");
		return;
	}
	if (creatingNew) {
		state.pendingNewSend = null;
		state.pendingNewId = null;
		state.newChatFingerprint = "";
		state.composingNew = true;
		renderNewChat();
	} else {
		const remaining = (state.pendingReplies.get(conversationId) || []).filter((item) => item !== pending);
		if (remaining.length) state.pendingReplies.set(conversationId, remaining);
		else state.pendingReplies.delete(conversationId);
		state.selectedFingerprint = "";
		if (state.selectedChat?.id === conversationId) renderConversation(state.selectedChat);
	}
	els.messageInput.value = pending.message || "";
	persistComposerDraft();
	resizeComposer();
	updateSlashMenu();
	syncSendButton();
	renderSidebar();
	if ((pending.attachmentNames || []).length) setTextIfChanged(els.composerStatus, "Editing pending message. Reattach the files before sending.");
	else setTextIfChanged(els.composerStatus, "Editing pending message.");
	els.messageInput.focus();
	els.messageInput.setSelectionRange(els.messageInput.value.length, els.messageInput.value.length);
}
async function watchSend(sendId, creatingNew, conversationId) {
	let statusFailures = 0;
	while (true) {
		await new Promise((resolve) => setTimeout(resolve, 400));
		let job;
		try {
			job = await fetchJson(`api/sends/${encodeURIComponent(sendId)}`);
			statusFailures = 0;
		} catch {
			statusFailures += 1;
			if (statusFailures >= 3) {
				await loadChats();
				if (creatingNew) {
					const pending = state.pendingNewSend;
					if (!pending || pending.sendId !== sendId) return;
					if (pending.conversationId && state.composingNew && state.mode === "chats") {
						state.composingNew = false;
						state.selectedId = pending.conversationId;
						state.pendingNewId = pending.conversationId;
						history.replaceState(null, "", `#/${encodeURIComponent(pending.conversationId)}`);
						await loadSelectedChat();
						return;
					}
				} else {
					if (!pendingReply(conversationId, sendId)) return;
					if (state.selectedId === conversationId) await loadSelectedChat();
					if (!pendingReply(conversationId, sendId)) return;
				}
				setTextIfChanged(els.composerStatus, "Send status unavailable. Prompta may still be running it; reconnecting…");
			}
			await new Promise((resolve) => setTimeout(resolve, Math.min(5e3, 250 * statusFailures)));
			continue;
		}
		const status = job.status || "running";
		if (creatingNew) {
			const pendingNewSend = state.pendingNewSend;
			if (!pendingNewSend || pendingNewSend.sendId !== sendId) return;
			const nextError = job.error || "";
			const nextConversationId = job.conversation_id || pendingNewSend.conversationId || "";
			const nextRetryAfterSeconds = Number(job.retry_after_seconds || 0);
			const nextRetryAt = Number(job.retry_at || 0);
			const nextRetryAttempt = Number(job.retry_attempt || 0);
			const nextQueuePosition = Number(job.queue_position || 0);
			if (nextConversationId) {
				completionNotifications.markActive(nextConversationId);
				promotePendingConversationPin(pendingNewSend, nextConversationId);
			}
			const changed = pendingNewSend.status !== status || pendingNewSend.error !== nextError || pendingNewSend.conversationId !== nextConversationId || pendingNewSend.retryAfterSeconds !== nextRetryAfterSeconds || pendingNewSend.retryAt !== nextRetryAt || pendingNewSend.retryAttempt !== nextRetryAttempt || pendingNewSend.queuePosition !== nextQueuePosition;
			Object.assign(pendingNewSend, {
				status,
				error: nextError,
				conversationId: nextConversationId,
				retryAfterSeconds: nextRetryAfterSeconds,
				retryAt: nextRetryAt,
				retryAttempt: nextRetryAttempt,
				queuePosition: nextQueuePosition
			});
			if (changed) pendingNewSend.updatedAt = Date.now() / 1e3;
			if (status === "succeeded") {
				const newId = job.conversation_id;
				if (!newId) {
					pendingNewSend.status = "failed";
					pendingNewSend.error = "Prompta reported success without a conversation id";
					if (state.composingNew) renderNewChat();
					return;
				}
				const completedPending = pendingNewSend;
				promotePendingConversationPin(completedPending, newId);
				completedPending.conversationId = newId;
				state.pendingNewId = newId;
				const pendingReplies = state.pendingReplies.get(newId) || [];
				if (!pendingReplies.some((item) => item.clientId === completedPending.clientId)) {
					pendingReplies.push(completedPending);
					state.pendingReplies.set(newId, pendingReplies);
				}
				state.pendingNewSend = null;
				if (!(state.composingNew && state.mode === "chats")) {
					renderSidebar();
					await loadChats();
					return;
				}
				state.composingNew = false;
				state.selectedId = newId;
				history.replaceState(null, "", `#/${encodeURIComponent(newId)}`);
				els.messageInput.placeholder = "Message Prompta…";
				setTextIfChanged(els.composerStatus, "Sent. Waiting for the cached response…");
				state.selectedUpdatedAt = null;
				await loadChats();
				await loadSelectedChat();
				return;
			}
			if (["failed", "dead_lettered"].includes(status)) {
				if (state.composingNew) renderNewChat();
				renderSidebar();
				return;
			}
			if (changed) {
				if (state.composingNew) renderNewChat();
				renderSidebar();
			}
			continue;
		}
		if (updatePendingReply(conversationId, sendId, {
			status,
			error: job.error || "",
			retryAfterSeconds: Number(job.retry_after_seconds || 0),
			retryAt: Number(job.retry_at || 0),
			retryAttempt: Number(job.retry_attempt || 0),
			queuePosition: Number(job.queue_position || 0)
		})) renderSidebar();
		if (state.selectedId === conversationId) await loadSelectedChat();
		if (status === "succeeded") {
			setTextIfChanged(els.composerStatus, "Sent. Waiting for the cached response…");
			await loadChats();
			return;
		}
		if (["failed", "dead_lettered"].includes(status)) {
			setTextIfChanged(els.composerStatus, status === "dead_lettered" ? "Send exhausted its retry budget. Retry to enqueue it again." : "Send failed. The error is shown in the chat.");
			return;
		}
	}
}
async function retryFailedSend(scope, retryKey) {
	if (!retryKey || state.sending) return;
	let pending = null;
	if (scope === "new") {
		if (state.pendingNewSend && (state.pendingNewSend.clientId === retryKey || state.pendingNewSend.sendId === retryKey)) {
			pending = state.pendingNewSend;
			state.pendingNewSend = null;
			state.newChatFingerprint = "";
			state.composingNew = true;
			renderNewChat();
		}
	} else if (scope === "reply" && state.selectedId) {
		const selectedId = state.selectedId;
		const items = state.pendingReplies.get(selectedId) || [];
		pending = items.find((item) => item.clientId === retryKey || item.sendId === retryKey) || null;
		if (pending) {
			const remaining = items.filter((item) => item !== pending);
			if (remaining.length) state.pendingReplies.set(selectedId, remaining);
			else state.pendingReplies.delete(selectedId);
			state.selectedFingerprint = "";
			if (state.selectedChat?.id === state.selectedId) renderConversation(state.selectedChat);
		}
	}
	if (!pending) return;
	els.messageInput.value = pending.message || "";
	resizeComposer();
	syncSendButton();
	if ((pending.attachmentNames || []).length) {
		setTextIfChanged(els.composerStatus, "Reattach the files, then send again.");
		els.messageInput.focus();
		return;
	}
	await sendSelectedMessage();
}
async function stopSelectedChat() {
	const conversationId = state.selectedId;
	if (!conversationId || state.mode !== "chats" || state.stopping) return;
	state.stopping = true;
	syncSendButton();
	setTextIfChanged(els.composerStatus, "Stopping response…");
	try {
		await postJsonRequest("api/chats/" + encodeURIComponent(conversationId) + "/stop", {});
		setTextIfChanged(els.composerStatus, "Stopped.");
		state.selectedFingerprint = "";
		state.selectedUpdatedAt = null;
		await loadSelectedChat();
		await loadChats();
	} catch (error) {
		setTextIfChanged(els.composerStatus, "Stop failed: " + String(error).replace(/^Error:\s*/, ""));
		console.error(error);
	} finally {
		state.stopping = false;
		syncSendButton();
	}
}
async function sendSelectedMessage() {
	const message = els.messageInput.value.trim();
	const creatingNew = state.composingNew;
	const conversationId = state.selectedId;
	const attachments = attachmentPicker.snapshot();
	if (!message || state.mode !== "chats" || state.sending) return;
	if (message.toLowerCase() === "/logs") {
		clearComposerDraft();
		els.messageInput.value = "";
		closeSlashMenu();
		resizeComposer();
		showMode("logs");
		return;
	}
	if (["/list", "/jobs"].includes(message.toLowerCase())) {
		await jobsDialog.open(true);
		return;
	}
	completionNotifications.requestPermissionFromGesture();
	const scheduleCommand = parseScheduleSlashCommand(message);
	if (scheduleCommand) {
		if (attachments.length) {
			setTextIfChanged(els.composerStatus, "Scheduled prompts do not include attachments.");
			return;
		}
		if ("error" in scheduleCommand) {
			setTextIfChanged(els.composerStatus, scheduleCommand.error);
			return;
		}
		await runScheduleSlashCommand(scheduleCommand, message);
		return;
	}
	const atCommand = parseAtSlashCommand(message);
	if (atCommand) {
		if (attachments.length) {
			setTextIfChanged(els.composerStatus, "Scheduled prompts do not include attachments.");
			return;
		}
		if ("error" in atCommand) {
			setTextIfChanged(els.composerStatus, atCommand.error);
			return;
		}
		await runAtSlashCommand(atCommand, message);
		return;
	}
	if (!creatingNew && !conversationId) return;
	let serializedAttachments = [];
	if (attachments.length) {
		state.sending = true;
		els.messageInput.disabled = true;
		els.sendButton.disabled = true;
		attachmentPicker.setDisabled(true);
		setTextIfChanged(els.composerStatus, "Preparing attachments…");
		try {
			serializedAttachments = await attachmentPicker.serialize();
		} catch (error) {
			state.sending = false;
			els.messageInput.disabled = false;
			attachmentPicker.setDisabled(false);
			syncSendButton();
			setTextIfChanged(els.composerStatus, "Attachment failed: " + String(error).replace(/^Error:\s*/, ""));
			return;
		}
		state.sending = false;
	}
	const now = Date.now() / 1e3;
	const pending = {
		sendId: "",
		clientId: `${clientSessionId}:${Date.now()}-${++state.optimisticSequence}`,
		message,
		status: "queued",
		error: "",
		conversationId: conversationId || "",
		origin: creatingNew ? "new" : "reply",
		createdAt: now,
		updatedAt: now,
		attachmentNames: attachments.map((file) => file.name),
		attachments: pendingImageAttachments(serializedAttachments)
	};
	state.sending = true;
	els.sendButton.disabled = true;
	clearComposerDraft();
	els.messageInput.value = "";
	resizeComposer();
	if (creatingNew) {
		state.pendingNewSend = pending;
		state.newChatFingerprint = "";
		renderNewChat();
		renderSidebar();
		scrollSidebarToNewest();
	} else {
		const targetConversationId = conversationId || "";
		const items = state.pendingReplies.get(targetConversationId) || [];
		items.push(pending);
		state.pendingReplies.set(targetConversationId, items);
		state.selectedFingerprint = "";
		if (state.selectedChat?.id === targetConversationId) renderConversation(state.selectedChat);
		renderSidebar();
	}
	try {
		const result = creatingNew ? await postJsonRequest("api/chats", {
			message,
			attachments: serializedAttachments,
			client_id: pending.clientId
		}, attachments.length ? 1 : 3) : await postJsonRequest(`api/chats/${encodeURIComponent(conversationId || "")}/messages`, {
			message,
			attachments: serializedAttachments,
			client_id: pending.clientId
		}, attachments.length ? 1 : 3);
		if (!result.send_id) throw new Error("Prompta did not return a send id");
		if (!creatingNew) completionNotifications.markActive(conversationId);
		pending.sendId = result.send_id;
		pending.status = result.status || "queued";
		pending.queuePosition = Number(result.queue_position || 0);
		pending.updatedAt = Date.now() / 1e3;
		if (attachments.length) attachmentPicker.clear();
		if (creatingNew) {
			state.newChatFingerprint = "";
			renderNewChat();
		} else {
			state.selectedFingerprint = "";
			if (state.selectedChat?.id === conversationId) renderConversation(state.selectedChat);
		}
		renderSidebar();
		watchSend(result.send_id, creatingNew, conversationId);
	} catch (error) {
		pending.status = "failed";
		pending.error = String(error).replace(/^Error:\s*/, "");
		pending.updatedAt = Date.now() / 1e3;
		if (creatingNew) {
			state.newChatFingerprint = "";
			renderNewChat();
		} else {
			state.selectedFingerprint = "";
			if (state.selectedChat?.id === conversationId) renderConversation(state.selectedChat);
		}
		renderSidebar();
		console.error(error);
	} finally {
		state.sending = false;
		if (attachments.length) attachmentPicker.setDisabled(false);
		if (!creatingNew && state.selectedId && state.mode === "chats") {
			els.messageInput.disabled = false;
			syncSendButton();
			if (matchMedia("(pointer: fine)").matches) els.messageInput.focus();
		} else if (creatingNew && state.pendingNewSend?.status === "failed" && state.mode === "chats") {
			els.messageInput.disabled = false;
			syncSendButton();
			if (matchMedia("(pointer: fine)").matches) els.messageInput.focus();
		}
		updateComposerActionButton();
	}
}
async function copySelectedChatUrl() {
	if (!state.selectedId) return;
	const url = new URL(location.href);
	url.hash = `/${encodeURIComponent(state.selectedId)}`;
	try {
		await navigator.clipboard.writeText(url.toString());
		setTextIfChanged(els.composerStatus, "Chat link copied.");
	} catch {
		const textarea = document.createElement("textarea");
		textarea.value = url.toString();
		textarea.style.position = "fixed";
		textarea.style.opacity = "0";
		document.body.append(textarea);
		textarea.select();
		const copied = document.execCommand("copy");
		textarea.remove();
		setTextIfChanged(els.composerStatus, copied ? "Chat link copied." : "Could not copy the chat link.");
	}
}
function visibleSlashCommandButtons() {
	return Array.from(els.slashMenu.querySelectorAll("[data-slash-command]:not([hidden])"));
}
function setSlashMenuSelection(button) {
	activeSlashCommand = button ? String(button.dataset.slashCommand || "") : "";
	for (const candidate of els.slashMenu.querySelectorAll("[data-slash-command]")) candidate.setAttribute("aria-selected", String(candidate === button));
	if (button?.id) els.messageInput.setAttribute("aria-activedescendant", button.id);
	else els.messageInput.removeAttribute("aria-activedescendant");
}
function closeSlashMenu() {
	els.slashMenu.hidden = true;
	els.messageInput.setAttribute("aria-expanded", "false");
	setSlashMenuSelection(null);
}
function updateSlashMenu() {
	const value = els.messageInput.value;
	const firstToken = value.split(/\s/, 1)[0].toLowerCase();
	const candidates = Array.from(els.slashMenu.querySelectorAll("[data-slash-command]"));
	const show = value.startsWith("/") && !value.includes("\n") && !value.includes(" ");
	for (const button of candidates) {
		const command = String(button.dataset.slashCommand || "").trim().toLowerCase();
		button.hidden = !(show && command.startsWith(firstToken));
	}
	const visible = visibleSlashCommandButtons();
	if (!visible.length) {
		closeSlashMenu();
		return;
	}
	els.slashMenu.hidden = false;
	els.messageInput.setAttribute("aria-expanded", "true");
	setSlashMenuSelection(visible.find((button) => String(button.dataset.slashCommand || "") === activeSlashCommand) || visible[0]);
}
function moveSlashMenuSelection(direction) {
	const visible = visibleSlashCommandButtons();
	if (!visible.length) return null;
	const currentIndex = visible.findIndex((button) => String(button.dataset.slashCommand || "") === activeSlashCommand);
	const next = visible[nextSlashCommandIndex(visible.length, currentIndex, direction)] || null;
	setSlashMenuSelection(next);
	return next;
}
function insertSlashCommand(command) {
	els.messageInput.value = command;
	closeSlashMenu();
	resizeComposer();
	syncSendButton();
	els.messageInput.focus();
	els.messageInput.setSelectionRange(command.length, command.length);
}
function refreshDisplayedTimes() {
	if (state.composingNew && ["rate_limited", "retrying"].includes(state.pendingNewSend?.status || "")) {
		state.newChatFingerprint = "";
		renderNewChat();
	} else if (state.selectedId && (state.pendingReplies.get(state.selectedId) || []).some((item) => ["rate_limited", "retrying"].includes(item.status || ""))) {
		state.selectedFingerprint = "";
		loadSelectedChat();
	}
	renderSidebar();
	for (const time of els.chatList.querySelectorAll(".chat-time[data-activity-at]")) setTextIfChanged(time, formatRelativeTime(Number(time.dataset.activityAt || 0)));
	for (const time of els.conversation.querySelectorAll(".message-timestamp[data-message-at]")) {
		const age = time.querySelector(".message-age");
		if (!age) continue;
		const ageText = messageAgeText(Number(time.dataset.messageAt || 0));
		setTextIfChanged(age, ageText ? ` · ${ageText}` : "");
	}
	if (state.mode === "chats" && state.selectedChat && state.selectedChat.id === state.selectedId && !state.composingNew) renderConversationMeta(state.selectedChat, state.selectedVisibleMessageCount);
}
async function startApp() {
	deploymentMonitor.registerServiceWorker();
	loadServerIdentity();
	await hydratePinnedIds();
	await hydratePendingSends();
	resizeComposer();
	if (!await hydrateRecentChatCache()) {
		conversationRenderer.renderLoadingState();
		setHiddenIfChanged(els.emptyState, true);
		setHiddenIfChanged(els.conversation, false);
	}
	document.documentElement.classList.remove("booting");
	await loadChats(true);
	liveUpdates.start();
}
var recentChatCache, clientSessionId, state, els, sidebarRenderDeferred, sidebar, sidebarList, jobsDialog, conversationRenderer, attachmentPicker, logsPanel, deploymentMonitor, completionNotifications, liveUpdates, SEND_ICON, STOP_ICON, iconStatusClasses, chatsRequestController, HISTORICAL_ACTIVITY_PROBE_TTL_MS, searchTimer, activeSlashCommand;
var init_app = __esmMin((() => {
	init_index_client();
	init_SidebarList();
	init_clientLogic();
	init_recentChatCache();
	init_jobsDialog();
	init_sidebar();
	init_conversationRenderer();
	init_attachmentPicker();
	init_logsPanel();
	init_deploymentMonitor();
	init_liveUpdates();
	init_completionNotifications();
	init_changelogDialog();
	init_clientStorage();
	recentChatCache = new RecentChatCache(location.pathname.replace(/\/$/, "") || "/", 20);
	clientSessionId = loadClientSessionId();
	state = {
		chats: [],
		selectedId: null,
		selectedUpdatedAt: null,
		selectedFingerprint: "",
		search: "",
		sidebarFingerprint: "",
		mode: "chats",
		sending: false,
		stopping: false,
		composingNew: false,
		pendingNewId: null,
		pendingNewSend: null,
		pendingReplies: /* @__PURE__ */ new Map(),
		newChatFingerprint: "",
		selectedMetaFingerprint: "",
		chatsRequestId: 0,
		chatOrderScope: null,
		selectedRequestId: 0,
		selectedChat: null,
		selectedVisibleMessageCount: 0,
		renderedConversationId: "",
		conversationViewports: /* @__PURE__ */ new Map(),
		chatSwitchToken: 0,
		optimisticSequence: 0,
		serverName: "",
		serverOnline: null,
		pinnedIds: loadPinnedIds(),
		composerDrafts: loadComposerDrafts(),
		composerDraftTarget: "",
		activityProbes: /* @__PURE__ */ new Set(),
		activityProbeAt: /* @__PURE__ */ new Map()
	};
	syncViewportHeight();
	window.setTimeout(() => document.documentElement.classList.remove("booting"), 1200);
	window.addEventListener("resize", syncViewportHeight);
	window.visualViewport?.addEventListener("resize", syncViewportHeight);
	els = {
		chatList: requiredElement("#chatList"),
		sidebarScroll: requiredElement(".sidebar-scroll"),
		searchInput: requiredElement("#searchInput"),
		conversation: requiredElement("#conversation"),
		emptyState: requiredElement("#emptyState"),
		viewport: requiredElement("#conversationViewport"),
		chatHeading: requiredElement("#chatHeading"),
		syncLabel: requiredElement("#syncLabel"),
		cacheSummary: requiredElement("#cacheSummary"),
		headLabel: requiredElement("#headLabel"),
		versionUpdateNotice: requiredElement("#versionUpdateNotice"),
		globalLiveOrb: requiredElement("#globalLiveOrb"),
		serverLabel: requiredElement("#serverLabel"),
		newChatButton: requiredElement("#newChatButton"),
		pinChatButton: requiredElement("#pinChatButton"),
		shareChatButton: requiredElement("#shareChatButton"),
		slashMenu: requiredElement("#slashMenu"),
		composerFooter: requiredElement("#composerFooter"),
		messageForm: requiredElement("#messageForm"),
		messageInput: requiredElement("#messageInput"),
		sendButton: requiredElement("#sendButton"),
		composerStatus: requiredElement("#composerStatus")
	};
	sidebarRenderDeferred = false;
	sidebar = createSidebar({ onMotionEnd: () => {
		if (!sidebarRenderDeferred) return;
		sidebarRenderDeferred = false;
		renderSidebar();
	} });
	sidebarList = mount(SidebarList, {
		target: els.chatList,
		props: {
			onSelect: (chatId, optimisticNew) => {
				if (optimisticNew && state.pendingNewSend) {
					renderNewChat();
					sidebar.close();
					return;
				}
				selectChat(chatId);
			},
			onPin: (chatId) => {
				setChatPinned(chatId, !state.pinnedIds.has(chatId));
				renderSidebar(true);
				updatePinButton();
			}
		}
	});
	jobsDialog = createJobsDialog({
		closeSidebar: sidebar.close,
		resizeComposer,
		syncSendButton
	});
	conversationRenderer = createConversationRenderer({
		onRetry: retryFailedSend,
		onDelete: deletePendingSend,
		onEdit: editPendingSend
	});
	attachmentPicker = createAttachmentPicker({
		onChange: syncSendButton,
		setStatus: (message) => setTextIfChanged(els.composerStatus, message)
	});
	logsPanel = createLogsPanel({
		fetchJson: (url, timeoutMs) => fetchJson(url, timeoutMs),
		formatRelativeTime
	});
	deploymentMonitor = createDeploymentMonitor({ onUpdateAvailable: () => {
		els.versionUpdateNotice.hidden = false;
	} });
	els.versionUpdateNotice.addEventListener("click", () => {
		els.versionUpdateNotice.disabled = true;
		els.versionUpdateNotice.textContent = "Updating…";
		els.versionUpdateNotice.setAttribute("aria-label", "Updating Prompta");
		deploymentMonitor.applyUpdate();
	});
	createChangelogDialog({
		fetchJson: (url, timeoutMs) => fetchJson(url, timeoutMs),
		closeSidebar: sidebar.close
	});
	completionNotifications = createCompletionNotifications({
		displayServerName,
		getServerName: () => state.serverName,
		chatTitle
	});
	liveUpdates = createLiveUpdates({
		loadChats: () => loadChats(),
		loadServerIdentity: () => loadServerIdentity(),
		setServerStatus,
		observeHead: (head) => deploymentMonitor.observeHead(head),
		refreshDisplayedTimes,
		onStreamError: () => els.globalLiveOrb.classList.remove("live"),
		onPageShow: () => deploymentMonitor.handleVisibilityChange()
	});
	SEND_ICON = "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M12 19V5M6 11l6-6 6 6\"/></svg>";
	STOP_ICON = "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><rect x=\"7.5\" y=\"7.5\" width=\"9\" height=\"9\" rx=\"1.5\" fill=\"currentColor\" stroke=\"none\"/></svg>";
	iconStatusClasses = /* @__PURE__ */ new Set([
		"active",
		"running",
		"succeeded",
		"complete",
		"cached",
		"local",
		"interrupted",
		"queued",
		"pending",
		"retrying",
		"failed",
		"broken",
		"dead_lettered",
		"live",
		"journal",
		"new",
		"idle"
	]);
	chatsRequestController = null;
	HISTORICAL_ACTIVITY_PROBE_TTL_MS = 3e4;
	els.searchInput.addEventListener("input", () => {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(() => {
			state.search = els.searchInput.value.trim();
			state.sidebarFingerprint = "";
			loadChats();
		}, 140);
	});
	document.addEventListener("keydown", (event) => {
		const searchFocused = document.activeElement === els.searchInput;
		const typing = searchFocused || document.activeElement === els.messageInput;
		if (event.key === "/" && !typing) {
			event.preventDefault();
			sidebar.open();
			els.searchInput.focus({ preventScroll: true });
		}
		if (event.key === "Escape") {
			if (searchFocused && els.searchInput.value) {
				event.preventDefault();
				clearTimeout(searchTimer);
				els.searchInput.value = "";
				state.search = "";
				state.sidebarFingerprint = "";
				loadChats();
				return;
			}
			attachmentPicker.closeMenu();
			closeSlashMenu();
			jobsDialog.close();
			els.searchInput.blur();
			sidebar.close(true);
		}
	});
	els.newChatButton.addEventListener("click", () => {
		state.pendingNewSend = null;
		state.newChatFingerprint = "";
		renderNewChat();
	});
	activeSlashCommand = "";
	els.pinChatButton.addEventListener("click", toggleSelectedPin);
	els.shareChatButton.addEventListener("click", copySelectedChatUrl);
	els.slashMenu.addEventListener("pointermove", (event) => {
		const button = event.target.closest("[data-slash-command]");
		if (button && !button.hidden) setSlashMenuSelection(button);
	});
	els.slashMenu.addEventListener("click", (event) => {
		const button = event.target.closest("[data-slash-command]");
		if (!button) return;
		insertSlashCommand(String(button.dataset.slashCommand || ""));
	});
	els.messageForm.addEventListener("submit", (event) => {
		event.preventDefault();
		if (els.sendButton.dataset.action === "stop") stopSelectedChat();
		else sendSelectedMessage();
	});
	els.messageInput.addEventListener("input", () => {
		persistComposerDraft();
		resizeComposer();
		updateSlashMenu();
		syncSendButton();
	});
	els.messageInput.addEventListener("keydown", (event) => {
		if (!els.slashMenu.hidden) {
			if (event.key === "ArrowDown" || event.key === "ArrowUp") {
				event.preventDefault();
				moveSlashMenuSelection(event.key === "ArrowUp" ? -1 : 1);
				return;
			}
			if (event.key === "Tab" || event.key === "Enter" && !event.isComposing) {
				const selected = visibleSlashCommandButtons().find((button) => String(button.dataset.slashCommand || "") === activeSlashCommand);
				if (selected) {
					event.preventDefault();
					insertSlashCommand(String(selected.dataset.slashCommand || ""));
					return;
				}
			}
			if (event.key === "Escape") {
				event.preventDefault();
				event.stopPropagation();
				closeSlashMenu();
				return;
			}
		}
		const mobileInput = matchMedia("(max-width: 780px)").matches || matchMedia("(pointer: coarse)").matches;
		if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !mobileInput) {
			event.preventDefault();
			if (els.sendButton.dataset.action === "stop") stopSelectedChat();
			else sendSelectedMessage();
		}
	});
	window.addEventListener("hashchange", () => {
		const id = conversationIdFromHash(location.hash);
		if (id && id !== state.selectedId) selectChat(id);
	});
	startApp();
}));
//#endregion
//#region src/prompta/ui/main.ts
init_index_client();
var target = document.querySelector("#app");
if (!target) throw new Error("Missing #app mount target");
mount(App, {
	target,
	props: { serverName: target.dataset.serverName?.trim() || "local" }
});
await Promise.resolve().then(() => (init_app(), app_exports));
//#endregion
