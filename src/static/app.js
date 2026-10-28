//#region node_modules/svelte/src/internal/shared/utils.js
var is_array = Array.isArray;
var index_of = Array.prototype.indexOf;
var includes = Array.prototype.includes;
var array_from = Array.from;
var define_property = Object.defineProperty;
var get_descriptor = Object.getOwnPropertyDescriptor;
var get_descriptors = Object.getOwnPropertyDescriptors;
var object_prototype = Object.prototype;
var array_prototype = Array.prototype;
var get_prototype_of = Object.getPrototypeOf;
var is_extensible = Object.isExtensible;
var noop = () => {};
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
var CLEAN = 1024;
var DIRTY = 2048;
var MAYBE_DIRTY = 4096;
var INERT = 8192;
var DESTROYED = 16384;
/** Set once a reaction has run for the first time */
var REACTION_RAN = 32768;
/** Effect is in the process of getting destroyed. Can be observed in child teardown functions */
var DESTROYING = 1 << 25;
/**
* 'Transparent' effects do not create a transition boundary.
* This is on a block effect 99% of the time but may also be on a branch effect if its parent block effect was pruned
*/
var EFFECT_TRANSPARENT = 65536;
var HEAD_EFFECT = 1 << 18;
var EFFECT_PRESERVED = 1 << 19;
var USER_EFFECT = 1 << 20;
var EFFECT_OFFSCREEN = 1 << 25;
var REACTION_IS_UPDATING = 1 << 21;
var ASYNC = 1 << 22;
var ERROR_VALUE = 1 << 23;
var STATE_SYMBOL = Symbol("$state");
/** Marks component export objects, so that `proxy(...)` leaves them untouched */
var COMPONENT_SYMBOL = Symbol("component");
var LEGACY_PROPS = Symbol("legacy props");
var LOADING_ATTR_SYMBOL = Symbol("");
var ATTRIBUTES_CACHE = Symbol("attributes");
var CLASS_CACHE = Symbol("class");
var STYLE_CACHE = Symbol("style");
var TEXT_CACHE = Symbol("text");
var FORM_RESET_HANDLER = Symbol("form reset");
/** allow users to ignore aborted signal errors if `reason.name === 'StaleReactionError` */
var STALE_REACTION = new class StaleReactionError extends Error {
	name = "StaleReactionError";
	message = "The reaction that called `getAbortSignal()` was re-run or destroyed";
}();
var IS_XHTML = !!globalThis.document?.contentType && /* @__PURE__ */ globalThis.document.contentType.includes("xml");
//#endregion
//#region node_modules/svelte/src/constants.js
var HYDRATION_ERROR = {};
var UNINITIALIZED = Symbol("uninitialized");
var NAMESPACE_HTML = "http://www.w3.org/1999/xhtml";
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
* The `value` property of a `<select multiple>` element should be an array, but it received a non-array value. The selection will be kept as is.
*/
function select_multiple_invalid_value() {
	console.warn(`https://svelte.dev/e/select_multiple_invalid_value`);
}
/**
* A `<svelte:boundary>` `reset` function only resets the boundary the first time it is called
*/
function svelte_boundary_reset_noop() {
	console.warn(`https://svelte.dev/e/svelte_boundary_reset_noop`);
}
//#endregion
//#region node_modules/svelte/src/internal/client/dom/hydration.js
/** @import { TemplateNode } from '#client' */
/**
* Use this variable to guard everything related to hydration code so it can be treeshaken out
* if the user doesn't use the `hydrate` method and these code paths are therefore not needed.
*/
var hydrating = false;
/** @param {boolean} value */
function set_hydrating(value) {
	hydrating = value;
}
/**
* The node that is currently being hydrated. This starts out as the first node inside the opening
* <!--[--> comment, and updates each time a component calls `$.child(...)` or `$.sibling(...)`.
* When entering a block (e.g. `{#if ...}`), `hydrate_node` is the block opening comment; by the
* time we leave the block it is the closing comment, which serves as the block's anchor.
* @type {TemplateNode}
*/
var hydrate_node;
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
/**
* `%name%(...)` can only be used during component initialisation
* @param {string} name
* @returns {never}
*/
function lifecycle_outside_component(name) {
	throw new Error(`https://svelte.dev/e/lifecycle_outside_component`);
}
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
* `%rune%` cannot be used inside an effect cleanup function
* @param {string} rune
* @returns {never}
*/
function effect_in_teardown(rune) {
	throw new Error(`https://svelte.dev/e/effect_in_teardown`);
}
/**
* Effect cannot be created inside a `$derived` value that was not itself created inside an effect
* @returns {never}
*/
function effect_in_unowned_derived() {
	throw new Error(`https://svelte.dev/e/effect_in_unowned_derived`);
}
/**
* `%rune%` can only be used inside an effect (e.g. during component initialisation)
* @param {string} rune
* @returns {never}
*/
function effect_orphan(rune) {
	throw new Error(`https://svelte.dev/e/effect_orphan`);
}
/**
* Maximum update depth exceeded. This typically indicates that an effect reads and writes the same piece of state
* @returns {never}
*/
function effect_update_depth_exceeded() {
	throw new Error(`https://svelte.dev/e/effect_update_depth_exceeded`);
}
/**
* Cannot do `bind:%key%={undefined}` when `%key%` has a fallback value
* @param {string} key
* @returns {never}
*/
function props_invalid_value(key) {
	throw new Error(`https://svelte.dev/e/props_invalid_value`);
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
//#endregion
//#region node_modules/svelte/src/internal/flags/index.js
/** True if experimental.async=true */
var async_mode_flag = false;
/** True if we're not certain that we only have Svelte 5 code in the compilation */
var legacy_mode_flag = false;
//#endregion
//#region node_modules/svelte/src/internal/client/context.js
/** @import { ComponentContext, DevStackEntry, Effect } from '#client' */
/** @type {ComponentContext | null} */
var component_context = null;
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
//#endregion
//#region node_modules/svelte/src/internal/client/dom/task.js
/** @type {Array<() => void>} */
var micro_tasks = [];
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
/**
* Synchronously run any queued tasks.
*/
function flush_tasks() {
	while (micro_tasks.length > 0) run_micro_tasks();
}
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/status.js
/** @import { Derived, Signal } from '#client' */
var STATUS_MASK = ~(DIRTY | MAYBE_DIRTY | CLEAN);
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
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/utils.js
/** @import { Effect } from '#client' */
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
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/misc.js
/**
* The child of a textarea actually corresponds to the defaultValue property, so we need
* to remove it upon hydration to avoid a bug when someone resets the form value.
* @param {HTMLTextAreaElement} dom
* @returns {void}
*/
function remove_textarea_child(dom) {
	if (hydrating && /* @__PURE__ */ get_first_child(dom) !== null) clear_text_content(dom);
}
var listening_to_form_reset = false;
function add_form_reset_listener() {
	if (!listening_to_form_reset) {
		listening_to_form_reset = true;
		document.addEventListener("reset", (evt) => {
			Promise.resolve().then(() => {
				if (!evt.defaultPrevented) for (const e of evt.target.elements)
 /** @type {any} */ e[FORM_RESET_HANDLER]?.();
			});
		}, { capture: true });
	}
}
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
/**
* Listen to the given event, and then instantiate a global form reset listener if not already done,
* to notify all bindings when the form is reset
* @param {HTMLElement} element
* @param {string} event
* @param {(is_reset?: true) => void} handler
* @param {(is_reset?: true) => void} [on_reset]
*/
function listen_to_event_and_reset_event(element, event, handler, on_reset = handler) {
	element.addEventListener(event, () => without_reactive_context(handler));
	const prev = element[FORM_RESET_HANDLER];
	if (prev)
 /** @type {any} */ element[FORM_RESET_HANDLER] = () => {
		prev();
		on_reset(true);
	};
	else
 /** @type {any} */ element[FORM_RESET_HANDLER] = () => on_reset(true);
	add_form_reset_listener();
}
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/async.js
/** @import { Blocker, Effect, Source, Value } from '#client' */
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
var OBSOLETE = Symbol("obsolete");
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
function user_derived(fn) {
	const d = /* @__PURE__ */ derived(fn);
	if (!async_mode_flag) push_reaction_value(d);
	return d;
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
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/batch.js
/** @import { Fork } from 'svelte' */
/** @import { Derived, Effect, Reaction, Source, Value } from '#client' */
/** @type {Batch | null} */
var first_batch = null;
/** @type {Batch | null} */
var last_batch = null;
/** @type {Batch | null} */
var current_batch = null;
/**
* This is needed to avoid overwriting inputs
* @type {Batch | null}
*/
var previous_batch = null;
/**
* When time travelling (i.e. working in one batch, while other batches
* still have ongoing work), we ignore the real values of affected
* signals in favour of their values within the batch
* @type {Map<Value, any> | null}
*/
var batch_values = null;
/** @type {Effect | null} */
var last_scheduled_effect = null;
var is_flushing_sync = false;
var is_processing = false;
/**
* During traversal, this is an array. Newly created effects are (if not immediately
* executed) pushed to this array, rather than going through the scheduling
* rigamarole that would cause another turn of the flush loop.
* @type {Effect[] | null}
*/
var collected_effects = null;
/**
* An array of effects that are marked during traversal as a result of a `set`
* (not `internal_set`) call. These will be added to the next batch and
* trigger another `batch.process()`
* @type {Effect[] | null}
* @deprecated when we get rid of legacy mode and stores, we can get rid of this
*/
var legacy_updates = null;
var flush_count = 0;
var uid = 1;
var Batch = class Batch {
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
/**
* Synchronously flush any pending updates.
* Returns void if no callback is provided, otherwise returns the result of calling the callback.
* @template [T=void]
* @param {(() => T) | undefined} [fn]
* @returns {T}
*/
function flushSync(fn) {
	var was_flushing_sync = is_flushing_sync;
	is_flushing_sync = true;
	try {
		var result;
		if (fn) {
			if (current_batch !== null && !current_batch.is_fork) current_batch.flush();
			result = fn();
		}
		while (true) {
			flush_tasks();
			if (current_batch === null) return result;
			current_batch.flush();
		}
	} finally {
		is_flushing_sync = was_flushing_sync;
	}
}
function infinite_loop_guard() {
	try {
		effect_update_depth_exceeded();
	} catch (error) {
		invoke_error_boundary(error, last_scheduled_effect);
	}
}
/** @type {Set<Effect> | null} */
var eager_block_effects = null;
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
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/sources.js
/** @import { Derived, Effect, Source, Value } from '#client' */
/** @type {Set<Effect>} */
var eager_effects = /* @__PURE__ */ new Set();
/** @type {Map<Source, any>} */
var old_values = /* @__PURE__ */ new Map();
var eager_effects_deferred = false;
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
function state(v, stack) {
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
* A set of signals we have already seen while traversing in mark_reactions.
* Not always set to balance the common case of sources only having a couple
* of (transitive) dependencies (where always creating a Set would be bad for perf)
* with the edge case of extremely deep or wide dependency arrays with cycles.
* @type {Set<any> | null}
*/
var seen = null;
/** Number of transitive dependencies, see {@link seen} for more info */
var count_deps = 0;
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
	var version = /* @__PURE__ */ state(0);
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
	if (is_proxied_array) sources.set("length", /* @__PURE__ */ state(
		/** @type {any[]} */
		value.length,
		stack
	));
	return new Proxy(value, {
		defineProperty(_, prop, descriptor) {
			if (!("value" in descriptor) || descriptor.configurable === false || descriptor.enumerable === false || descriptor.writable === false) state_descriptors_fixed();
			var s = sources.get(prop);
			if (s === void 0) with_parent(() => {
				var s = /* @__PURE__ */ state(descriptor.value, stack);
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
					const s = with_parent(() => /* @__PURE__ */ state(UNINITIALIZED, stack));
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
					return /* @__PURE__ */ state(proxy(exists ? target[prop] : UNINITIALIZED), stack);
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
						return /* @__PURE__ */ state(has ? proxy(target[prop]) : UNINITIALIZED, stack);
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
					other_s = with_parent(() => /* @__PURE__ */ state(UNINITIALIZED, stack));
					sources.set(i + "", other_s);
				}
			}
			if (s === void 0) {
				if (!has || get_descriptor(target, prop)?.writable) {
					s = with_parent(() => /* @__PURE__ */ state(void 0, stack));
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
/**
* @param {any} value
*/
function get_proxied_value(value) {
	try {
		if (value !== null && typeof value === "object" && STATE_SYMBOL in value) return value[STATE_SYMBOL];
	} catch {}
	return value;
}
/**
* @param {any} a
* @param {any} b
*/
function is(a, b) {
	return Object.is(get_proxied_value(a), get_proxied_value(b));
}
//#endregion
//#region node_modules/svelte/src/internal/client/dom/operations.js
/** @import { Effect, TemplateNode } from '#client' */
/** @type {Window} */
var $window;
/** @type {Document} */
var $document;
/** @type {boolean} */
var is_firefox;
/** @type {() => Node | null} */
var first_child_getter;
/** @type {() => Node | null} */
var next_sibling_getter;
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
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/effects.js
/** @import { Blocker, ComponentContext, ComponentContextLegacy, Derived, Effect, TemplateNode, TransitionManager } from '#client' */
/**
* @param {'$effect' | '$effect.pre' | '$inspect'} rune
*/
function validate_effect(rune) {
	if (active_effect === null) {
		if (active_reaction === null) effect_orphan(rune);
		effect_in_unowned_derived();
	}
	if (is_destroying_effect) effect_in_teardown(rune);
}
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
* Internal representation of `$effect(...)`
* @param {() => void | (() => void)} fn
*/
function user_effect(fn) {
	validate_effect("$effect");
	var flags = active_effect.f;
	if (!active_reaction && (flags & 32) !== 0 && component_context !== null && !component_context.i) {
		var context = component_context;
		(context.e ??= []).push(fn);
	} else return create_user_effect(fn);
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
function effect(fn) {
	return create_effect(4, fn);
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
* Like `template_effect`, but with an effect which is deferred until the batch commits
* @param {(...expressions: any) => void | (() => void)} fn
* @param {Array<() => any>} sync
* @param {Array<() => Promise<any>>} async
* @param {Blocker[]} blockers
*/
function deferred_template_effect(fn, sync = [], async = [], blockers = []) {
	flatten(blockers, sync, async, (values) => {
		create_effect(4, () => fn(...values.map(get)));
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
//#endregion
//#region node_modules/svelte/src/internal/client/legacy.js
/**
* @type {Set<Value> | null}
* @deprecated
*/
var captured_signals = null;
//#endregion
//#region node_modules/svelte/src/internal/client/runtime.js
/** @import { Derived, Effect, Reaction, Source, Value } from '#client' */
/**
* True if updating in an effect context that is reactive (i.e. not branch/root effects)
*/
var is_updating_effect = false;
var is_destroying_effect = false;
/** @param {boolean} value */
function set_is_destroying_effect(value) {
	is_destroying_effect = value;
}
/** @type {null | Reaction} */
var active_reaction = null;
var untracking = false;
/** @param {null | Reaction} reaction */
function set_active_reaction(reaction) {
	active_reaction = reaction;
}
/** @type {null | Effect} */
var active_effect = null;
/** @param {null | Effect} effect */
function set_active_effect(effect) {
	active_effect = effect;
}
/**
* When sources are created within a reaction, reading and writing
* them within that reaction should not cause a re-run
* @type {null | Set<Source>}
*/
var current_sources = null;
/** @param {Value} value */
function push_reaction_value(value) {
	if (active_reaction !== null && (!async_mode_flag && (active_reaction.f & 2097152) !== 0 || (active_reaction.f & 2) !== 0)) (current_sources ??= /* @__PURE__ */ new Set()).add(value);
}
/**
* The dependencies of the reaction that is currently being executed. In many cases,
* the dependencies are unchanged between runs, and so this will be `null` unless
* and until a new dependency is accessed — we track this via `skipped_deps`
* @type {null | Value[]}
*/
var new_deps = null;
var skipped_deps = 0;
/**
* Tracks writes that the effect it's executed in doesn't listen to yet,
* so that the dependency can be added to the effect later on if it then reads it
* @type {null | Source[]}
*/
var untracked_writes = null;
/** @param {null | Source[]} value */
function set_untracked_writes(value) {
	untracked_writes = value;
}
/**
* @type {number} Used by sources and deriveds for handling updates.
* Version starts from 1 so that unowned deriveds differentiate between a created effect and a run one for tracing
**/
var write_version = 1;
/** @type {number} Used to version each read of a source of derived to avoid duplicating dependencies inside a reaction */
var read_version = 0;
var update_version = read_version;
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
* Returns a promise that resolves once any pending state changes have been applied.
* @returns {Promise<void>}
*/
async function tick() {
	if (async_mode_flag) return new Promise((f) => {
		requestAnimationFrame(() => f());
		setTimeout(() => f());
	});
	await Promise.resolve();
	flushSync();
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
/**
* Subset of delegated events which should be passive by default.
* These two are already passive via browser defaults on window, document and body.
* But since
* - we're delegating them
* - they happen often
* - they apply to mobile which is generally less performant
* we're marking them as passive by default for other elements, too.
*/
var PASSIVE_EVENTS = ["touchstart", "touchmove"];
/**
* Returns `true` if `name` is a passive event
* @param {string} name
*/
function is_passive_event(name) {
	return PASSIVE_EVENTS.includes(name);
}
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/events.js
/**
* Used on elements, as a map of event type -> event handler,
* and on events themselves to track which element handled an event
*/
var event_symbol = Symbol("events");
/** @type {Set<string>} */
var all_registered_events = /* @__PURE__ */ new Set();
/** @type {Set<(events: Array<string>) => void>} */
var root_event_handles = /* @__PURE__ */ new Set();
/**
* @param {string} event_name
* @param {EventTarget} dom
* @param {EventListener} [handler]
* @param {AddEventListenerOptions} [options]
*/
function create_event(event_name, dom, handler, options = {}) {
	/**
	* @this {EventTarget}
	*/
	function target_handler(event) {
		if (!options.capture) handle_event_propagation.call(dom, event);
		if (!event.cancelBubble) return without_reactive_context(() => {
			return handler?.call(this, event);
		});
	}
	if (event_name.startsWith("pointer") || event_name.startsWith("touch") || event_name === "wheel") {
		target_handler.__removed = false;
		queue_micro_task(() => {
			if (!target_handler.__removed) dom.addEventListener(event_name, target_handler, options);
		});
	} else dom.addEventListener(event_name, target_handler, options);
	return target_handler;
}
/**
* @param {string} event_name
* @param {Element} dom
* @param {EventListener} [handler]
* @param {boolean} [capture]
* @param {boolean} [passive]
* @returns {void}
*/
function event(event_name, dom, handler, capture, passive) {
	var options = {
		capture,
		passive
	};
	var target_handler = create_event(event_name, dom, handler, options);
	if (dom === document.body || dom === window || dom === document || dom instanceof HTMLMediaElement) teardown(() => {
		target_handler.__removed = true;
		dom.removeEventListener(event_name, target_handler, options);
	});
}
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
var last_propagated_event = null;
var last_propagated_event_clear_scheduled = false;
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
//#endregion
//#region node_modules/svelte/src/internal/client/dom/reconciler.js
var policy = globalThis?.window?.trustedTypes && /* @__PURE__ */ globalThis.window.trustedTypes.createPolicy("svelte-trusted-html", {
/** @param {string} html */
createHTML: (html) => {
	return html;
} });
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
//#endregion
//#region node_modules/svelte/src/internal/client/dom/template.js
/** @import { Effect, EffectNodes, TemplateNode } from '#client' */
/** @import { TemplateStructure } from './types' */
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
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/boundary.js
/** @import { Effect, Source, TemplateNode, } from '#client' */
/**
* @typedef {{
* 	 onerror?: ((error: unknown, reset: () => void) => void) | null;
*   failed?: ((anchor: Node, error: () => unknown, reset: () => () => void) => void) | null;
*   pending?: ((anchor: Node) => void) | null;
* }} BoundaryProps
*/
var flags = EFFECT_TRANSPARENT | EFFECT_PRESERVED;
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
var Boundary = class {
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
/** @type {Map<EventTarget, Map<string, number>>} */
var listeners = /* @__PURE__ */ new Map();
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
			component = Component(anchor_node, props) || mark_as_component();
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
/**
* References of the components that were mounted or hydrated.
* Uses a `WeakMap` to avoid memory leaks.
*/
var mounted_components = /* @__PURE__ */ new WeakMap();
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/branches.js
/** @import { Effect, TemplateNode } from '#client' */
/**
* @typedef {{ effect: Effect, fragment: DocumentFragment }} Branch
*/
/**
* @template Key
*/
var BranchManager = class {
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
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/if.js
/** @import { TemplateNode } from '#client' */
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
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/each.js
/** @import { EachItem, EachOutroGroup, EachState, Effect, EffectNodes, MaybeSource, Source, TemplateNode, TransitionManager, Value } from '#client' */
/** @import { Batch } from '../../reactivity/batch.js'; */
/**
* @param {any} _
* @param {number} i
*/
function index(_, i) {
	return i;
}
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
/** @type {TemplateNode} */
var offscreen_anchor;
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
//#endregion
//#region node_modules/svelte/src/internal/client/dom/blocks/svelte-head.js
/** @import { TemplateNode } from '#client' */
/**
* @param {string} hash
* @param {(anchor: Node) => void} render_fn
* @returns {void}
*/
function head(hash, render_fn) {
	let previous_hydrate_node = null;
	let was_hydrating = hydrating;
	/** @type {Comment | Text} */
	var anchor;
	if (hydrating) {
		previous_hydrate_node = hydrate_node;
		var head_anchor = /* @__PURE__ */ get_first_child(document.head);
		while (head_anchor !== null && (head_anchor.nodeType !== 8 || head_anchor.data !== hash)) head_anchor = /* @__PURE__ */ get_next_sibling(head_anchor);
		if (head_anchor === null) set_hydrating(false);
		else {
			var start = /* @__PURE__ */ get_next_sibling(head_anchor);
			head_anchor.remove();
			set_hydrate_node(start);
		}
	}
	if (!hydrating) anchor = document.head.appendChild(create_text());
	try {
		block(() => {
			var e = branch(() => render_fn(anchor));
			e.f |= HEAD_EFFECT;
			if (!hydrating) {
				if (e.nodes === null) e.nodes = {
					start: anchor,
					end: anchor,
					a: null,
					t: null
				};
				else e.nodes.end = anchor;
			}
		});
	} finally {
		if (was_hydrating) {
			set_hydrating(true);
			set_hydrate_node(previous_hydrate_node);
		}
	}
}
//#endregion
//#region node_modules/clsx/dist/clsx.mjs
function r(e) {
	var t, f, n = "";
	if ("string" == typeof e || "number" == typeof e) n += e;
	else if ("object" == typeof e) if (Array.isArray(e)) {
		var o = e.length;
		for (t = 0; t < o; t++) e[t] && (f = r(e[t])) && (n && (n += " "), n += f);
	} else for (f in e) e[f] && (n && (n += " "), n += f);
	return n;
}
function clsx$1() {
	for (var e, t, f = 0, n = "", o = arguments.length; f < o; f++) (e = arguments[f]) && (t = r(e)) && (n && (n += " "), n += t);
	return n;
}
//#endregion
//#region node_modules/svelte/src/internal/shared/attributes.js
/**
* Small wrapper around clsx to preserve Svelte's (weird) handling of falsy values.
* TODO Svelte 6 revisit this, and likely turn all falsy values into the empty string (what clsx also does)
* @param  {any} value
*/
function clsx(value) {
	if (typeof value === "object") return clsx$1(value);
	else return value ?? "";
}
var whitespace = [..." 	\n\r\f\xA0\v﻿"];
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
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/select.js
/**
* Sets the `selected` attribute on an option so form reset can restore it.
* @param {HTMLOptionElement} option
* @param {boolean} selected
*/
function set_selected(option, selected) {
	if (selected) {
		if (!option.hasAttribute("selected")) option.setAttribute("selected", "");
	} else option.removeAttribute("selected");
}
/**
* Marks the options matching `__defaultValue` as selected. Without `preserve`
* a newly matching option gets selected, as an inserted `<option selected>` would.
* @param {HTMLSelectElement} select
* @param {boolean} preserve
*/
function apply_default_select_value(select, preserve) {
	var value = select.__defaultValue;
	var multiple = select.multiple;
	var values = multiple ? value ?? [] : null;
	if (multiple && !is_array(values)) return;
	var index = select.selectedIndex;
	var selected = preserve && multiple ? new Set(select.selectedOptions) : null;
	for (var option of select.options) {
		var option_value = get_option_value(option);
		set_selected(option, multiple ? values.includes(option_value) : is(option_value, value));
	}
	if (!preserve) return;
	if (selected !== null) for (option of select.options) {
		var was_selected = selected.has(option);
		if (option.selected !== was_selected) option.selected = was_selected;
	}
	else if (select.selectedIndex !== index) select.selectedIndex = index;
}
/**
* Selects the correct option(s) (depending on whether this is a multiple select)
* @template V
* @param {HTMLSelectElement} select
* @param {V} value
* @param {boolean} mounting
*/
function select_option(select, value, mounting = false) {
	if (select.multiple) {
		if (value == void 0) return;
		if (!is_array(value)) return select_multiple_invalid_value();
		for (var option of select.options) option.selected = value.includes(get_option_value(option));
		return;
	}
	for (option of select.options) if (is(get_option_value(option), value)) {
		option.selected = true;
		return;
	}
	if (!mounting || value !== void 0) select.selectedIndex = -1;
}
/**
* Sets up a mutation observer to sync the current selection
* and default to the dom when the options change, for example
* when they are inside an `#each` block. Called once per `<select>`,
* by the compiled output or by `attribute_effect` for spreads.
* @param {HTMLSelectElement} select
*/
function init_select(select) {
	var observer = new MutationObserver((entries) => {
		if (entries.every(is_selectedcontent_mutation)) return;
		if ("__defaultValue" in select) apply_default_select_value(select, false);
		if ("__value" in select) select_option(select, select.__value);
	});
	observer.observe(select, {
		childList: true,
		subtree: true,
		attributes: true,
		attributeFilter: ["value"]
	});
	teardown(() => {
		observer.disconnect();
	});
}
/**
* @param {HTMLSelectElement} select
* @param {() => unknown} get
* @param {(value: unknown) => void} set
* @returns {void}
*/
function bind_select_value(select, get, set = get) {
	var batches = /* @__PURE__ */ new WeakSet();
	var mounting = true;
	listen_to_event_and_reset_event(select, "change", (is_reset) => {
		var query = is_reset ? "[selected]" : ":checked";
		/** @type {unknown} */
		var value;
		if (select.multiple) value = [].map.call(select.querySelectorAll(query), get_option_value);
		else {
			/** @type {HTMLOptionElement | null} */
			var selected_option = select.querySelector(query) ?? select.querySelector("option:not([disabled])");
			value = selected_option && get_option_value(selected_option);
		}
		set(value);
		select.__value = value;
		if (current_batch !== null) batches.add(current_batch);
	});
	effect(() => {
		var value = get();
		if (select === document.activeElement) {
			var batch = async_mode_flag ? previous_batch : current_batch;
			if (batches.has(batch)) return;
		}
		select_option(select, value, mounting);
		if (mounting && value === void 0) {
			/** @type {HTMLOptionElement | null} */
			var selected_option = select.querySelector(":checked");
			if (selected_option !== null) {
				value = get_option_value(selected_option);
				set(value);
			}
		}
		select.__value = value;
		mounting = false;
	});
}
/** @param {HTMLOptionElement} option */
function get_option_value(option) {
	if ("__value" in option) return option.__value;
	else return option.value;
}
/**
* Returns `true` if the mutation stems from the browser mirroring the selected
* option's content into `<selectedcontent>`, or from us replacing the
* `<selectedcontent>` element with a clone of itself
* @param {MutationRecord} entry
*/
function is_selectedcontent_mutation(entry) {
	if (entry.target.closest("selectedcontent") !== null) return true;
	if (entry.type === "childList") {
		var nodes = [...entry.addedNodes, ...entry.removedNodes];
		return nodes.length > 0 && nodes.every((node) => node.nodeName === "SELECTEDCONTENT");
	}
	return false;
}
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/attributes.js
/** @import { Blocker, Effect } from '#client' */
var IS_CUSTOM_ELEMENT = Symbol("is custom element");
var IS_HTML = Symbol("is html");
var LINK_TAG = IS_XHTML ? "link" : "LINK";
/**
* The value/checked attribute in the template actually corresponds to the defaultValue property, so we need
* to remove it upon hydration to avoid a bug when someone resets the form value.
* @param {HTMLInputElement} input
* @returns {void}
*/
function remove_input_defaults(input) {
	if (!hydrating) return;
	var already_removed = false;
	var remove_defaults = () => {
		if (already_removed) return;
		already_removed = true;
		if (input.hasAttribute("value")) {
			var value = input.value;
			set_attribute(input, "value", null);
			input.value = value;
		}
		if (input.hasAttribute("checked")) {
			var checked = input.checked;
			set_attribute(input, "checked", null);
			input.checked = checked;
		}
	};
	/** @type {any} */ input[FORM_RESET_HANDLER] = remove_defaults;
	queue_micro_task(remove_defaults);
	add_form_reset_listener();
}
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
/** @type {Map<string, Set<string>>} */
var setters_cache = /* @__PURE__ */ new Map();
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
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/input.js
/** @import { Batch } from '../../../reactivity/batch.js' */
/**
* @param {HTMLInputElement} input
* @param {() => unknown} get
* @param {(value: unknown) => void} set
* @returns {void}
*/
function bind_value(input, get, set = get) {
	var batches = /* @__PURE__ */ new WeakSet();
	listen_to_event_and_reset_event(input, "input", async (is_reset) => {
		/** @type {any} */
		var value = is_reset ? input.defaultValue : input.value;
		value = is_numberlike_input(input) ? to_number(value) : value;
		set(value);
		if (current_batch !== null) batches.add(current_batch);
		await tick();
		if (value !== (value = get())) {
			var start = input.selectionStart;
			var end = input.selectionEnd;
			var length = input.value.length;
			input.value = value ?? "";
			if (end !== null) {
				var new_length = input.value.length;
				if (start === end && end === length && new_length > length) {
					input.selectionStart = new_length;
					input.selectionEnd = new_length;
				} else {
					input.selectionStart = start;
					input.selectionEnd = Math.min(end, new_length);
				}
			}
		}
	});
	if (hydrating && input.defaultValue !== input.value || untrack(get) == null && input.value) {
		set(is_numberlike_input(input) ? to_number(input.value) : input.value);
		if (current_batch !== null) batches.add(current_batch);
	}
	render_effect(() => {
		var value = get();
		if (input === document.activeElement) {
			var batch = async_mode_flag ? previous_batch : current_batch;
			if (batches.has(batch)) return;
		}
		if (is_numberlike_input(input) && value === to_number(input.value)) return;
		if (input.type === "date" && !value && !input.value) return;
		if (value !== input.value) input.value = value ?? "";
	});
}
/**
* @param {HTMLInputElement} input
* @param {() => unknown} get
* @param {(value: unknown) => void} set
* @returns {void}
*/
function bind_checked(input, get, set = get) {
	listen_to_event_and_reset_event(input, "change", (is_reset) => {
		set(is_reset ? input.defaultChecked : input.checked);
	});
	if (hydrating && input.defaultChecked !== input.checked || untrack(get) == null) set(input.checked);
	render_effect(() => {
		var value = get();
		input.checked = Boolean(value);
	});
}
/**
* @param {HTMLInputElement} input
*/
function is_numberlike_input(input) {
	var type = input.type;
	return type === "number" || type === "range";
}
/**
* @param {string} value
*/
function to_number(value) {
	return value === "" ? null : +value;
}
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/bindings/this.js
/** @import { ComponentContext, Effect } from '#client' */
/**
* @param {any} bound_value
* @param {Element} element_or_component
* @returns {boolean}
*/
function is_bound_this(bound_value, element_or_component) {
	return bound_value === element_or_component || bound_value?.[STATE_SYMBOL] === element_or_component;
}
/**
* @param {any} element_or_component
* @param {(value: unknown, ...parts: unknown[]) => void} update
* @param {(...parts: unknown[]) => unknown} get_value
* @param {() => unknown[]} [get_parts] Set if the this binding is used inside an each block,
* 										returns all the parts of the each block context that are used in the expression
* @returns {void}
*/
function bind_this(element_or_component = mark_as_component(), update, get_value, get_parts) {
	var component_effect = component_context.r;
	var parent = active_effect;
	effect(() => {
		/** @type {unknown[]} */
		var old_parts;
		/** @type {unknown[]} */
		var parts;
		render_effect(() => {
			old_parts = parts;
			parts = get_parts?.() || [];
			untrack(() => {
				if (!is_bound_this(get_value(...parts), element_or_component)) {
					update(element_or_component, ...parts);
					if (old_parts && is_bound_this(get_value(...old_parts), element_or_component)) update(null, ...old_parts);
				}
			});
		});
		return () => {
			let p = parent;
			while (p !== component_effect && p.parent !== null && p.parent.f & 33554432) p = p.parent;
			const teardown = () => {
				if (parts && is_bound_this(get_value(...parts), element_or_component)) update(null, ...parts);
			};
			const original_teardown = p.teardown;
			p.teardown = () => {
				teardown();
				original_teardown?.();
			};
		};
	});
	return element_or_component;
}
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/store.js
/**
* Whether or not the prop currently being read is a store binding, as in
* `<Child bind:x={$y} />`. If it is, we treat the prop as mutable even in
* runes mode, and skip `binding_property_non_reactive` validation
*/
var is_store_binding = false;
/**
* Returns a tuple that indicates whether `fn()` reads a prop that is a store binding.
* Used to prevent `binding_property_non_reactive` validation false positives and
* ensure that these props are treated as mutable even in runes mode
* @template T
* @param {() => T} fn
* @returns {[T, boolean]}
*/
function capture_store_binding(fn) {
	var previous_is_store_binding = is_store_binding;
	try {
		is_store_binding = false;
		return [fn(), is_store_binding];
	} finally {
		is_store_binding = previous_is_store_binding;
	}
}
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/props.js
/** @import { Derived, Effect, Source } from './types.js' */
/**
* This function is responsible for synchronizing a possibly bound prop with the inner component state.
* It is used whenever the compiler sees that the component writes to the prop, or when it has a default prop_value.
* @template V
* @param {Record<string, unknown>} props
* @param {string} key
* @param {number} flags
* @param {V | (() => V)} [fallback]
* @returns {(() => V | ((arg: V) => V) | ((arg: V, mutation: boolean) => V))}
*/
function prop(props, key, flags, fallback) {
	var runes = !legacy_mode_flag || (flags & 2) !== 0;
	var bindable = (flags & 8) !== 0;
	var lazy = (flags & 16) !== 0;
	var fallback_value = fallback;
	var fallback_dirty = true;
	var fallback_signal = void 0;
	var get_fallback = () => {
		if (lazy && runes) {
			fallback_signal ??= /* @__PURE__ */ derived(fallback);
			return get(fallback_signal);
		}
		if (fallback_dirty) {
			fallback_dirty = false;
			fallback_value = lazy ? untrack(fallback) : fallback;
		}
		return fallback_value;
	};
	/** @type {((v: V) => void) | undefined} */
	let setter;
	if (bindable) {
		var is_entry_props = STATE_SYMBOL in props || LEGACY_PROPS in props;
		setter = get_descriptor(props, key)?.set ?? (is_entry_props && key in props ? (v) => props[key] = v : void 0);
	}
	/** @type {V} */
	var initial_value;
	var is_store_sub = false;
	if (bindable) [initial_value, is_store_sub] = capture_store_binding(() => props[key]);
	else initial_value = props[key];
	if (initial_value === void 0 && fallback !== void 0) {
		initial_value = get_fallback();
		if (setter) {
			if (runes) props_invalid_value(key);
			setter(initial_value);
		}
	}
	/** @type {() => V} */
	var getter;
	if (runes) getter = () => {
		var value = props[key];
		if (value === void 0) return get_fallback();
		fallback_dirty = true;
		return value;
	};
	else getter = () => {
		var value = props[key];
		if (value !== void 0) fallback_value = void 0;
		return value === void 0 ? fallback_value : value;
	};
	if (runes && (flags & 4) === 0) return getter;
	if (setter) {
		var legacy_parent = props.$$legacy;
		return (function(value, mutation) {
			if (arguments.length > 0) {
				if (!runes || !mutation || legacy_parent || is_store_sub)
 /** @type {Function} */ setter(mutation ? getter() : value);
				return value;
			}
			return getter();
		});
	}
	var overridden = false;
	var d = ((flags & 1) !== 0 ? derived : derived_safe_equal)(() => {
		overridden = false;
		return getter();
	});
	if (bindable) get(d);
	var parent_effect = active_effect;
	return (function(value, mutation) {
		if (arguments.length > 0) {
			const new_value = mutation ? get(d) : runes && bindable ? proxy(value) : value;
			set(d, new_value);
			overridden = true;
			if (fallback_value !== void 0) fallback_value = new_value;
			return value;
		}
		if (is_destroying_effect && overridden || (parent_effect.f & 16384) !== 0) return d.v;
		return get(d);
	});
}
if (typeof HTMLElement === "function");
/**
* `onMount`, like [`$effect`](https://svelte.dev/docs/svelte/$effect), schedules a function to run as soon as the component has been mounted to the DOM.
* Unlike `$effect`, the provided function only runs once.
*
* It must be called during the component's initialisation (but doesn't need to live _inside_ the component;
* it can be called from an external module). If a function is returned _synchronously_ from `onMount`,
* it will be called when the component is unmounted.
*
* `onMount` functions do not run during [server-side rendering](https://svelte.dev/docs/svelte/svelte-server#render).
*
* @template T
* @param {() => NotFunction<T> | Promise<NotFunction<T>> | (() => any)} fn
* @returns {void}
*/
function onMount(fn) {
	if (component_context === null) lifecycle_outside_component("onMount");
	if (legacy_mode_flag && component_context.l !== null) init_update_callbacks(component_context).m.push(fn);
	else user_effect(() => {
		const cleanup = untrack(fn);
		if (typeof cleanup === "function") return cleanup;
	});
}
/**
* Legacy-mode: Init callbacks object for onMount/beforeUpdate/afterUpdate
* @param {ComponentContext} context
*/
function init_update_callbacks(context) {
	var l = context.l;
	return l.u ??= {
		a: [],
		b: [],
		m: []
	};
}
//#endregion
//#region node_modules/svelte/src/internal/disclose-version.js
if (typeof window !== "undefined") ((window.__svelte ??= {}).v ??= /* @__PURE__ */ new Set()).add("5");
//#endregion
//#region src/ui/jobSorting.ts
function isLongJob(job) {
	return job.run_at_epoch !== null || !job.daily_at && job.interval_minutes > 1440;
}
function frequencyMinutes(job) {
	if (job.run_at_epoch) return Number.POSITIVE_INFINITY;
	if (job.daily_at) return 1440;
	return job.interval_minutes;
}
function compareJobs(left, right) {
	const leftFrequency = frequencyMinutes(left);
	const rightFrequency = frequencyMinutes(right);
	if (leftFrequency !== rightFrequency) return leftFrequency < rightFrequency ? -1 : 1;
	return right.created_order - left.created_order || left.name.localeCompare(right.name);
}
function sortJobs(jobs) {
	return [...jobs].sort(compareJobs);
}
//#endregion
//#region src/ui/JobsPage.svelte
var root$4 = /* @__PURE__ */ from_html(`<button type="button"> <span> </span></button>`);
var root_1$4 = /* @__PURE__ */ from_html(`<div class="empty-row"> </div>`);
var root_2$3 = /* @__PURE__ */ from_html(`<div class="job-image-count"> </div>`);
var root_3$3 = /* @__PURE__ */ from_html(`<span> </span>`);
var root_4$3 = /* @__PURE__ */ from_html(`<span class="job-message"> </span>`);
var root_5$2 = /* @__PURE__ */ from_html(`<button class="row-action" type="button">Edit</button>`);
var root_6$2 = /* @__PURE__ */ from_html(`<div class="job-row" role="row"><div class="job-main" role="cell"><div class="job-name"> </div> <div class="job-prompt"> </div> <!> <div class="job-submeta"><span> </span> <!></div></div> <div class="job-cell schedule-cell" role="cell"><span class="cell-label">Schedule</span> <span> </span></div> <div class="job-cell" role="cell"><span class="cell-label">Next run</span> <span> </span></div> <div class="job-cell state-cell" role="cell"><span class="cell-label">State</span> <span><span class="state-dot"></span> </span> <!></div> <div class="job-actions" role="cell"><button class="row-action" type="button">Fire now</button> <!> <button class="row-action" type="button"> </button> <button class="row-action danger-text" type="button">Remove</button></div></div>`);
var root_7$2 = /* @__PURE__ */ from_html(`<nav class="pagination" aria-label="Job pages"><span> </span> <div class="pagination-actions"><button class="toolbar-button" type="button">Previous</button> <button class="toolbar-button" type="button">Next</button></div></nav>`);
var root_8$2 = /* @__PURE__ */ from_html(`<section class="jobs-panel" aria-labelledby="jobs-title"><div class="jobs-toolbar"><div class="toolbar-title"><h1 id="jobs-title">Jobs</h1> <span> </span></div> <div class="toolbar-actions"><span class="status-line" role="status" aria-live="polite"> </span> <button class="toolbar-button visible-toggle" type="button"> </button> <button class="toolbar-button" type="button">Refresh</button> <button class="toolbar-button" type="button">Run once</button> <button class="primary-button" type="button">New job</button></div></div> <div class="jobs-summary" role="group" aria-label="Filter jobs"><!> <button type="button" title="Include jobs running less often than daily and scheduled one-time jobs">Long jobs <span> </span></button></div> <div class="jobs-table" role="table" aria-label="Scheduled jobs"><div class="jobs-table-head" role="row"><span role="columnheader">Job</span> <span role="columnheader">Schedule</span> <span role="columnheader">Next run</span> <span role="columnheader">State</span> <span role="columnheader" class="actions-heading">Actions</span></div> <!> <!></div> <!> <footer class="jobs-footer"><button class="row-action danger-text" type="button">Clear all jobs</button></footer></section>`);
var root_9$2 = /* @__PURE__ */ from_html(`<label class="name-field"><span>Name</span> <input autocomplete="off" required=""/></label>`);
var root_10$2 = /* @__PURE__ */ from_html(`<label><span>Every (minutes)</span> <input type="number" min="0.1" max="43200" step="0.1" required=""/></label>`);
var root_11$2 = /* @__PURE__ */ from_html(`<label><span>Delay (minutes, 0 = now)</span> <input type="number" min="0" max="43200" step="0.1" required=""/></label>`);
var root_12$2 = /* @__PURE__ */ from_html(`<label><span>At (local time)</span> <input type="time" required=""/></label>`);
var root_13$2 = /* @__PURE__ */ from_html(`<label class="checkbox-row"><input type="checkbox"/> <span>Exact interval</span></label>`);
var root_14$2 = /* @__PURE__ */ from_html(`<div class="job-image-preview"><img/> <span> </span> <button type="button">×</button></div>`);
var root_15$2 = /* @__PURE__ */ from_html(`<div class="job-image-previews"></div>`);
var root_16$2 = /* @__PURE__ */ from_html(`<span>Discard unsaved changes?</span> <button class="toolbar-button" type="button">Keep editing</button> <button class="toolbar-button danger-text" type="button">Discard</button>`, 1);
var root_17$2 = /* @__PURE__ */ from_html(`<span class="editor-error"> </span>`);
var root_18$2 = /* @__PURE__ */ from_html(`<span class="editor-error">This job already exists. Choose another name.</span>`);
var root_19$2 = /* @__PURE__ */ from_html(`<span>Unsaved changes</span>`);
var root_20$2 = /* @__PURE__ */ from_html(`<span>No changes</span>`);
var root_21$2 = /* @__PURE__ */ from_html(`<section class="editor-page" aria-labelledby="editor-title" tabindex="-1"><form id="job-editor" class="job-editor"><div class="editor-heading"><button class="toolbar-button editor-back" type="button"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m12 19-7-7 7-7"></path><path d="M5 12h14"></path></svg> Jobs</button> <div class="editor-title"><h2 id="editor-title"> </h2> <!></div></div> <div><div class="editor-settings"><!> <label><span>Schedule</span> <select><option>Interval</option><option>Daily</option><option>Once</option></select></label> <!></div> <!> <label class="prompt-field"><span>Prompt</span> <textarea rows="14" required=""></textarea></label> <div class="prompt-counter"> </div> <div class="job-image-picker"><button class="toolbar-button" type="button">Add images</button> <input class="image-input" type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple=""/> <span> </span></div> <!></div> <div class="editor-footer"><div class="editor-feedback" role="status" aria-live="polite"><!></div> <div class="editor-actions"><span class="keyboard-hint"> </span> <button class="toolbar-button" type="button">Cancel</button> <button class="primary-button" type="submit"> </button></div></div></form></section>`);
var root_22$1 = /* @__PURE__ */ from_html(`<!> <!>`, 1);
function JobsPage($$anchor, $$props) {
	push($$props, true);
	const filterOptions = [
		{
			key: "pending",
			label: "Pending",
			title: "Pending or queued jobs"
		},
		{
			key: "healthy",
			label: "Healthy",
			title: "Jobs whose last dispatch succeeded"
		},
		{
			key: "paused",
			label: "Paused",
			title: "Paused jobs"
		},
		{
			key: "unhealthy",
			label: "Unhealthy",
			title: "Failing, rate-limited, or unconfirmed jobs"
		}
	];
	const pageSize = 10;
	const refreshIntervalMs = 5e3;
	let jobs = /* @__PURE__ */ state(proxy([]));
	let activeFilters = /* @__PURE__ */ state(proxy({
		pending: true,
		healthy: true,
		paused: true,
		unhealthy: true
	}));
	let showLongJobs = /* @__PURE__ */ state(true);
	let longJobsCount = /* @__PURE__ */ user_derived(() => get(jobs).filter(isLongJob).length);
	let cadenceJobs = /* @__PURE__ */ user_derived(() => get(jobs).filter((job) => get(showLongJobs) || !isLongJob(job)));
	let filteredJobs = /* @__PURE__ */ user_derived(() => get(cadenceJobs).filter((job) => get(activeFilters)[jobFilter(job)]));
	let filterCounts = /* @__PURE__ */ user_derived(() => get(cadenceJobs).reduce((counts, job) => {
		counts[jobFilter(job)] += 1;
		return counts;
	}, {
		pending: 0,
		healthy: 0,
		paused: 0,
		unhealthy: 0
	}));
	let page = /* @__PURE__ */ state(1);
	let pageCount = /* @__PURE__ */ user_derived(() => Math.max(1, Math.ceil(get(filteredJobs).length / pageSize)));
	let pageStart = /* @__PURE__ */ user_derived(() => (get(page) - 1) * pageSize);
	let pageEnd = /* @__PURE__ */ user_derived(() => Math.min(get(pageStart) + pageSize, get(filteredJobs).length));
	let visibleJobs = /* @__PURE__ */ user_derived(() => get(filteredJobs).slice(get(pageStart), get(pageEnd)));
	let allVisiblePaused = /* @__PURE__ */ user_derived(() => get(visibleJobs).length > 0 && get(visibleJobs).every((job) => job.paused));
	let status = /* @__PURE__ */ state("");
	let saving = /* @__PURE__ */ state(false);
	let editing = /* @__PURE__ */ state("");
	let name = /* @__PURE__ */ state("");
	let prompt = /* @__PURE__ */ state("");
	let images = /* @__PURE__ */ state(proxy([]));
	let uploadingImage = /* @__PURE__ */ state(false);
	let imageInput;
	let schedule = /* @__PURE__ */ state("once");
	let interval = /* @__PURE__ */ state("40");
	let onceDelay = /* @__PURE__ */ state("0");
	let initialOnceDelay = "0";
	let originalRunAtEpoch = null;
	let dailyAt = /* @__PURE__ */ state("09:00");
	let exact = /* @__PURE__ */ state(false);
	let editorOpen = /* @__PURE__ */ state(false);
	let editorPage = /* @__PURE__ */ state(void 0);
	let activeEditorRoute = "";
	let listScrollY = 0;
	let editorError = /* @__PURE__ */ state("");
	let confirmDiscard = /* @__PURE__ */ state(false);
	let initialForm = /* @__PURE__ */ state("");
	let dirty = /* @__PURE__ */ user_derived(() => get(editorOpen) && formSnapshot() !== get(initialForm));
	let runOnce = /* @__PURE__ */ user_derived(() => !get(editing) && get(schedule) === "once");
	let duplicateName = /* @__PURE__ */ user_derived(() => !get(runOnce) && !get(editing) && get(jobs).some((job) => job.name === get(name).trim()));
	let promptCharacters = /* @__PURE__ */ user_derived(() => get(prompt).length);
	let promptLines = /* @__PURE__ */ user_derived(() => get(prompt) ? get(prompt).split("\n").length : 0);
	let loadInFlight = false;
	let dataGeneration = 0;
	function reset$1() {
		set(editing, "");
		set(name, "");
		set(prompt, "");
		set(images, [], true);
		set(schedule, "once");
		set(interval, "40");
		set(onceDelay, "0");
		initialOnceDelay = "0";
		originalRunAtEpoch = null;
		set(dailyAt, "09:00");
		set(exact, false);
	}
	function formSnapshot() {
		return JSON.stringify({
			name: get(name),
			prompt: get(prompt),
			images: get(images).map((image) => image.ref),
			schedule: get(schedule),
			interval: get(interval),
			onceDelay: get(onceDelay),
			dailyAt: get(dailyAt),
			exact: get(exact)
		});
	}
	function closeEditorState() {
		set(editorOpen, false);
		activeEditorRoute = "";
		set(confirmDiscard, false);
		set(editorError, "");
		reset$1();
	}
	function editorRouteFromUrl() {
		const url = new URL(window.location.href);
		if (url.searchParams.has("new")) return {
			kind: "new",
			once: url.searchParams.get("new") === "once"
		};
		const jobName = url.searchParams.get("edit");
		return jobName === null ? null : {
			kind: "edit",
			name: jobName
		};
	}
	function routeKey(route) {
		return route?.kind === "new" ? route.once ? "new:once" : "new" : route?.kind === "edit" ? "edit:" + route.name : "";
	}
	function jobsUrl() {
		const url = new URL(window.location.href);
		url.searchParams.delete("new");
		url.searchParams.delete("edit");
		return url;
	}
	function leaveEditor() {
		if (window.history.state?.promptaEditor === true) window.history.back();
		else {
			window.history.replaceState(null, "", jobsUrl());
			closeEditorState();
			requestAnimationFrame(() => window.scrollTo(0, listScrollY));
		}
	}
	function requestClose() {
		if (get(saving)) return;
		if (get(dirty)) {
			set(confirmDiscard, true);
			return;
		}
		leaveEditor();
	}
	function discardEditor() {
		set(initialForm, formSnapshot(), true);
		leaveEditor();
	}
	function openEditor(focusName) {
		set(editorError, "");
		set(confirmDiscard, false);
		set(initialForm, formSnapshot(), true);
		set(editorOpen, true);
		requestAnimationFrame(() => {
			window.scrollTo(0, 0);
			if (focusName) get(editorPage)?.querySelector(".name-field input")?.focus();
			else if (window.matchMedia("(pointer: coarse)").matches) get(editorPage)?.focus();
			else {
				const textarea = get(editorPage)?.querySelector(".prompt-field textarea");
				textarea?.focus();
				textarea?.setSelectionRange(0, 0);
			}
		});
	}
	function showEditor(route) {
		if (route.kind === "new") {
			reset$1();
			if (route.once) set(schedule, "once");
		} else {
			const job = get(jobs).find((item) => item.name === route.name);
			if (!job) {
				set(status, "Job not found: " + route.name);
				window.history.replaceState(null, "", jobsUrl());
				closeEditorState();
				return;
			}
			set(editing, job.name, true);
			set(name, job.name, true);
			set(prompt, job.prompt, true);
			set(images, [...job.images || []], true);
			set(schedule, job.run_at_epoch ? "once" : job.daily_at ? "daily" : "interval", true);
			originalRunAtEpoch = job.run_at_epoch;
			set(onceDelay, String(job.run_at_epoch ? Math.max(0, Math.round((job.run_at_epoch - Date.now() / 1e3) / 6) / 10) : 0), true);
			initialOnceDelay = get(onceDelay);
			set(dailyAt, job.daily_at || "09:00", true);
			set(interval, String(job.interval_minutes || 40), true);
			set(exact, job.exact_interval, true);
		}
		activeEditorRoute = routeKey(route);
		openEditor(route.kind === "new" && get(schedule) !== "once");
	}
	function pushEditor(route) {
		listScrollY = window.scrollY;
		const url = jobsUrl();
		if (route.kind === "new") url.searchParams.set("new", route.once ? "once" : "1");
		else url.searchParams.set("edit", route.name);
		window.history.pushState({ promptaEditor: true }, "", url);
		showEditor(route);
	}
	function syncEditorFromUrl() {
		const route = editorRouteFromUrl();
		if (routeKey(route) === activeEditorRoute) return;
		if (get(saving) || get(dirty) && !window.confirm("Discard unsaved job changes?")) {
			window.history.forward();
			return;
		}
		if (route) showEditor(route);
		else {
			closeEditorState();
			requestAnimationFrame(() => window.scrollTo(0, listScrollY));
		}
	}
	function beginNew() {
		pushEditor({ kind: "new" });
	}
	function beginOnce() {
		pushEditor({
			kind: "new",
			once: true
		});
	}
	function onEditorKeydown(event) {
		if (!get(editorOpen) || get(saving)) return;
		if (event.key === "Escape") {
			event.preventDefault();
			requestClose();
			return;
		}
		if (!get(dirty) || get(duplicateName)) return;
		if (!(event.ctrlKey || event.metaKey) || event.key !== "Enter") return;
		if (!(event.target instanceof Node) || !get(editorPage)?.contains(event.target)) return;
		event.preventDefault();
		get(editorPage).querySelector("#job-editor")?.requestSubmit();
	}
	function formatDate(epoch) {
		if (!epoch) return "—";
		return (/* @__PURE__ */ new Date(epoch * 1e3)).toLocaleString([], {
			year: "numeric",
			month: "short",
			day: "numeric",
			hour: "numeric",
			minute: "2-digit"
		});
	}
	function scheduleText(job) {
		if (job.run_at_epoch) return "once · " + formatDate(job.run_at_epoch);
		if (job.daily_at) return "daily · " + job.daily_at;
		const minutes = Number(job.interval_minutes);
		return "every " + (minutes >= 60 && minutes % 60 === 0 ? String(minutes / 60) + " hour" + (minutes === 60 ? "" : "s") : String(minutes) + " minute" + (minutes === 1 ? "" : "s")) + (job.exact_interval ? " · exact" : "");
	}
	function jobFilter(job) {
		if (job.paused) return "paused";
		if (job.last_uncertain_send_at > job.last_sent_at || job.status === "failing" || job.status === "rate-limited") return "unhealthy";
		if (job.status === "healthy") return "healthy";
		return "pending";
	}
	function toggleFilter(filter) {
		set(activeFilters, {
			...get(activeFilters),
			[filter]: !get(activeFilters)[filter]
		}, true);
		set(page, 1);
	}
	function jobStateText(job) {
		if (job.paused) return "paused";
		if (job.last_uncertain_send_at > job.last_sent_at || job.status === "failing" && /lost send confirmation after dispatch/i.test(job.status_message)) return "unconfirmed";
		return job.status || "pending";
	}
	function sameJob(left, right) {
		return left.name === right.name && left.created_order === right.created_order && left.prompt === right.prompt && JSON.stringify(left.images) === JSON.stringify(right.images) && left.status === right.status && left.status_message === right.status_message && left.paused === right.paused && left.run_at_epoch === right.run_at_epoch && left.daily_at === right.daily_at && left.interval_minutes === right.interval_minutes && left.exact_interval === right.exact_interval && left.source_revision === right.source_revision && left.next_due_at_epoch === right.next_due_at_epoch && left.last_sent_at === right.last_sent_at && left.last_uncertain_send_at === right.last_uncertain_send_at;
	}
	function applyJobs(nextJobs) {
		const sortedJobs = sortJobs(nextJobs);
		if (get(jobs).length === sortedJobs.length && get(jobs).every((job, index) => sameJob(job, sortedJobs[index]))) return;
		set(jobs, sortedJobs, true);
		clampPage();
	}
	function clampPage() {
		set(page, Math.max(1, Math.min(get(page), get(pageCount))), true);
	}
	function changePage(nextPage) {
		set(page, Math.max(1, Math.min(nextPage, get(pageCount))), true);
		document.getElementById("jobs-title")?.scrollIntoView({
			behavior: "smooth",
			block: "start"
		});
	}
	async function load({ quiet = false } = {}) {
		if (loadInFlight || quiet && document.visibilityState !== "visible") return;
		loadInFlight = true;
		const requestGeneration = dataGeneration;
		if (!quiet) set(status, "Loading jobs…");
		try {
			const response = await fetch("./api/jobs", { cache: "no-store" });
			if (!response.ok) throw new Error(String(response.status) + " " + response.statusText);
			const result = await response.json();
			if (requestGeneration !== dataGeneration) return;
			applyJobs(Array.isArray(result.jobs) ? result.jobs : []);
			if (!quiet) set(status, String(get(jobs).length) + " configured job" + (get(jobs).length === 1 ? "" : "s") + ".");
		} catch (error) {
			if (!quiet) set(status, "Could not load jobs: " + String(error).replace(/^Error:\s*/, ""));
		} finally {
			loadInFlight = false;
		}
	}
	async function command(payload, success) {
		set(saving, true);
		dataGeneration += 1;
		set(status, payload.action === "fire_now" || payload.action === "run_once" ? "Queuing fresh chat…" : "Saving…", true);
		try {
			const response = await fetch("./api/jobs", {
				method: "POST",
				headers: { "content-type": "application/json" },
				body: JSON.stringify(payload)
			});
			const result = await response.json();
			if (!response.ok) throw new Error(String(result.error || String(response.status) + " " + response.statusText));
			applyJobs(Array.isArray(result.jobs) ? result.jobs : []);
			set(status, success, true);
			return true;
		} catch (error) {
			set(status, "Job update failed: " + String(error).replace(/^Error:\s*/, ""));
			return false;
		} finally {
			set(saving, false);
		}
	}
	async function addImages(input) {
		const files = Array.from(input.files || []);
		input.value = "";
		if (!files.length || get(uploadingImage)) return;
		if (get(images).length + files.length > 4) {
			set(editorError, "At most four images per job.");
			return;
		}
		const route = activeEditorRoute;
		set(uploadingImage, true);
		set(editorError, "");
		try {
			for (const file of files) {
				if (file.size > 8388608) throw new Error("Images must be 8 MiB or smaller.");
				const data = await new Promise((resolve, reject) => {
					const reader = new FileReader();
					reader.onerror = () => reject(/* @__PURE__ */ new Error("Could not read image."));
					reader.onload = () => {
						const value = reader.result;
						if (typeof value !== "string" || !value.includes(",")) reject(/* @__PURE__ */ new Error("Could not encode image."));
						else resolve(value.split(",", 2)[1]);
					};
					reader.readAsDataURL(file);
				});
				const response = await fetch("./api/images", {
					method: "POST",
					headers: { "content-type": "application/json" },
					body: JSON.stringify({
						name: file.name,
						data
					})
				});
				const result = await response.json();
				if (!response.ok) throw new Error(String(result.error || "Image upload failed."));
				if (activeEditorRoute !== route) return;
				set(images, [...get(images), result.image], true);
				await tick();
				get(editorPage)?.querySelector(".job-image-preview:last-child")?.scrollIntoView({
					block: "nearest",
					behavior: "smooth"
				});
			}
		} catch (error) {
			if (activeEditorRoute === route) set(editorError, String(error).replace(/^Error:\s*/, ""), true);
		} finally {
			set(uploadingImage, false);
		}
	}
	async function submit() {
		if (get(saving) || get(uploadingImage) || !get(dirty) || get(duplicateName)) return;
		set(editorError, "");
		const jobName = get(name).trim();
		const jobPrompt = get(prompt).trim();
		if (!jobPrompt || !get(runOnce) && !jobName) return;
		if (get(runOnce)) {
			const delayMinutes = Number(get(onceDelay));
			if (await command({
				action: "run_once",
				prompt: jobPrompt,
				images: get(images).map((image) => image.ref),
				delay_minutes: delayMinutes
			}, delayMinutes ? `Scheduled once in ${delayMinutes} minutes (under Long jobs).` : "Queued one fresh chat.")) {
				set(initialForm, formSnapshot(), true);
				leaveEditor();
			} else set(editorError, get(status), true);
			return;
		}
		const daily = get(schedule) === "daily";
		if (await command({
			action: "add",
			name: jobName,
			prompt: jobPrompt,
			images: get(images).map((image) => image.ref),
			schedule: get(schedule),
			daily_at: daily ? get(dailyAt) : "",
			interval_minutes: get(schedule) === "interval" ? Number(get(interval)) : null,
			exact_interval: get(schedule) === "interval" && get(exact),
			...get(schedule) === "once" && (!originalRunAtEpoch || get(onceDelay) !== initialOnceDelay) ? { delay_minutes: Number(get(onceDelay)) } : {}
		}, "Saved " + jobName + ".")) {
			set(initialForm, formSnapshot(), true);
			leaveEditor();
		} else set(editorError, get(status), true);
	}
	function edit(job) {
		pushEditor({
			kind: "edit",
			name: job.name
		});
	}
	async function remove(job) {
		if (!window.confirm("Remove “" + job.name + "”?")) return;
		if (await command({
			action: "remove",
			name: job.name
		}, "Removed " + job.name + ".") && get(editing) === job.name) leaveEditor();
	}
	async function toggleVisible() {
		const names = get(visibleJobs).map((job) => job.name);
		if (!names.length) return;
		const action = get(allVisiblePaused) ? "resume_many" : "pause_many";
		const success = get(allVisiblePaused) ? "Resumed visible jobs." : "Paused visible jobs.";
		await command({
			action,
			names
		}, success);
	}
	async function clearAll() {
		if (!get(jobs).length || !window.confirm("Remove all " + String(get(jobs).length) + " configured jobs?")) return;
		if (await command({ action: "clear" }, "Cleared all scheduled jobs.") && get(editorOpen)) leaveEditor();
	}
	onMount(() => {
		const onBeforeUnload = (event) => {
			if (!get(dirty)) return;
			event.preventDefault();
			event.returnValue = "";
		};
		window.addEventListener("beforeunload", onBeforeUnload);
		load().then(syncEditorFromUrl);
		window.addEventListener("popstate", syncEditorFromUrl);
		const timer = window.setInterval(() => {
			load({ quiet: true });
		}, refreshIntervalMs);
		return () => {
			window.clearInterval(timer);
			window.removeEventListener("beforeunload", onBeforeUnload);
			window.removeEventListener("popstate", syncEditorFromUrl);
		};
	});
	var fragment = root_22$1();
	event("keydown", $window, onEditorKeydown);
	var node = first_child(fragment);
	var consequent_6 = ($$anchor) => {
		var section = root_8$2();
		var div = child(section);
		var div_1 = child(div);
		var text = only_child(sibling(child(div_1), 2), true);
		reset(div_1);
		var div_2 = sibling(div_1, 2);
		var span_1 = child(div_2);
		var text_1 = only_child(span_1, true);
		var button = sibling(span_1, 2);
		var text_2 = only_child(button);
		var button_1 = sibling(button, 2);
		var button_2 = sibling(button_1, 2);
		var button_3 = sibling(button_2, 2);
		reset(div_2);
		reset(div);
		var div_3 = sibling(div, 2);
		var node_1 = child(div_3);
		each(node_1, 17, () => filterOptions, (option) => option.key, ($$anchor, option) => {
			var button_4 = root$4();
			let classes;
			var text_3 = child(button_4);
			var text_4 = only_child(sibling(text_3), true);
			reset(button_4);
			template_effect(() => {
				classes = set_class(button_4, 1, "filter-chip", null, classes, { chosen: get(activeFilters)[get(option).key] });
				set_attribute(button_4, "aria-pressed", get(activeFilters)[get(option).key]);
				set_attribute(button_4, "title", get(option).title);
				set_text(text_3, `${get(option).label ?? ""} `);
				set_text(text_4, get(filterCounts)[get(option).key]);
			});
			delegated("click", button_4, () => toggleFilter(get(option).key));
			append($$anchor, button_4);
		});
		var button_5 = sibling(node_1, 2);
		let classes_1;
		var text_5 = only_child(sibling(child(button_5)), true);
		reset(button_5);
		reset(div_3);
		var div_4 = sibling(div_3, 2);
		var node_2 = sibling(child(div_4), 2);
		var consequent = ($$anchor) => {
			var div_5 = root_1$4();
			var text_6 = only_child(div_5, true);
			template_effect(() => set_text(text_6, get(jobs).length ? "No jobs match these filters." : "No scheduled jobs."));
			append($$anchor, div_5);
		};
		if_block(node_2, ($$render) => {
			if (get(filteredJobs).length === 0) $$render(consequent);
		});
		each(sibling(node_2, 2), 17, () => get(visibleJobs), (job) => job.name, ($$anchor, job) => {
			var div_6 = root_6$2();
			var div_7 = child(div_6);
			var div_8 = child(div_7);
			var text_7 = only_child(div_8, true);
			var div_9 = sibling(div_8, 2);
			var text_8 = only_child(div_9, true);
			var node_4 = sibling(div_9, 2);
			var consequent_1 = ($$anchor) => {
				var div_10 = root_2$3();
				var text_9 = only_child(div_10);
				template_effect(() => set_text(text_9, `${get(job).images.length ?? ""} image${get(job).images.length === 1 ? "" : "s"}`));
				append($$anchor, div_10);
			};
			if_block(node_4, ($$render) => {
				if (get(job).images?.length) $$render(consequent_1);
			});
			var div_11 = sibling(node_4, 2);
			var span_4 = child(div_11);
			var text_10 = only_child(span_4);
			var node_5 = sibling(span_4, 2);
			var consequent_2 = ($$anchor) => {
				var span_5 = root_3$3();
				var text_11 = only_child(span_5);
				template_effect(($0) => {
					set_attribute(span_5, "title", get(job).source_revision);
					set_text(text_11, `rev ${$0 ?? ""}`);
				}, [() => get(job).source_revision.slice(0, 8)]);
				append($$anchor, span_5);
			};
			if_block(node_5, ($$render) => {
				if (get(job).source_revision) $$render(consequent_2);
			});
			reset(div_11);
			reset(div_7);
			var div_12 = sibling(div_7, 2);
			var text_12 = only_child(sibling(child(div_12), 2), true);
			reset(div_12);
			var div_13 = sibling(div_12, 2);
			var text_13 = only_child(sibling(child(div_13), 2), true);
			reset(div_13);
			var div_14 = sibling(div_13, 2);
			var span_8 = sibling(child(div_14), 2);
			let classes_2;
			var text_14 = sibling(child(span_8));
			reset(span_8);
			var node_6 = sibling(span_8, 2);
			var consequent_3 = ($$anchor) => {
				var span_9 = root_4$3();
				var text_15 = only_child(span_9, true);
				template_effect(() => set_text(text_15, get(job).status_message));
				append($$anchor, span_9);
			};
			if_block(node_6, ($$render) => {
				if (get(job).status_message) $$render(consequent_3);
			});
			reset(div_14);
			var div_15 = sibling(div_14, 2);
			var button_6 = child(div_15);
			var node_7 = sibling(button_6, 2);
			var consequent_4 = ($$anchor) => {
				var button_7 = root_5$2();
				template_effect(() => button_7.disabled = get(saving));
				delegated("click", button_7, () => edit(get(job)));
				append($$anchor, button_7);
			};
			if_block(node_7, ($$render) => {
				if (!get(job).run_at_epoch) $$render(consequent_4);
			});
			var button_8 = sibling(node_7, 2);
			var text_16 = only_child(button_8, true);
			var button_9 = sibling(button_8, 2);
			reset(div_15);
			reset(div_6);
			template_effect(($0, $1, $2, $3) => {
				set_text(text_7, get(job).name);
				set_attribute(div_9, "title", get(job).prompt);
				set_text(text_8, get(job).prompt);
				set_text(text_10, `Last sent ${$0 ?? ""}`);
				set_text(text_12, $1);
				set_text(text_13, $2);
				classes_2 = set_class(span_8, 1, "state-value", null, classes_2, { error: get(job).status === "failing" });
				set_text(text_14, ` ${$3 ?? ""}`);
				button_6.disabled = get(saving);
				set_attribute(button_6, "title", get(job).daily_at || get(job).run_at_epoch ? "Launch a fresh chat without moving the fixed schedule" : "Launch a fresh chat and restart the interval countdown");
				button_8.disabled = get(saving);
				set_text(text_16, get(job).paused ? "Resume" : "Pause");
				button_9.disabled = get(saving);
			}, [
				() => formatDate(get(job).last_sent_at),
				() => scheduleText(get(job)),
				() => get(job).paused ? "Paused" : formatDate(get(job).next_due_at_epoch),
				() => jobStateText(get(job))
			]);
			delegated("click", button_6, () => void command({
				action: "fire_now",
				name: get(job).name
			}, "Queued one fresh chat for " + get(job).name + "."));
			delegated("click", button_8, () => void command({
				action: get(job).paused ? "resume" : "pause",
				name: get(job).name
			}, (get(job).paused ? "Resumed " : "Paused ") + get(job).name + "."));
			delegated("click", button_9, () => void remove(get(job)));
			append($$anchor, div_6);
		});
		reset(div_4);
		var node_8 = sibling(div_4, 2);
		var consequent_5 = ($$anchor) => {
			var nav = root_7$2();
			var span_10 = child(nav);
			var text_17 = only_child(span_10);
			var div_16 = sibling(span_10, 2);
			var button_10 = child(div_16);
			var button_11 = sibling(button_10, 2);
			reset(div_16);
			reset(nav);
			template_effect(() => {
				set_text(text_17, `Page ${get(page) ?? ""} of ${get(pageCount) ?? ""}`);
				button_10.disabled = get(page) <= 1;
				button_11.disabled = get(page) >= get(pageCount);
			});
			delegated("click", button_10, () => changePage(get(page) - 1));
			delegated("click", button_11, () => changePage(get(page) + 1));
			append($$anchor, nav);
		};
		if_block(node_8, ($$render) => {
			if (get(filteredJobs).length > pageSize) $$render(consequent_5);
		});
		var button_12 = only_child(sibling(node_8, 2));
		reset(section);
		template_effect(() => {
			set_text(text, get(cadenceJobs).length);
			set_text(text_1, get(status));
			button.disabled = !get(visibleJobs).length || get(saving);
			set_attribute(button, "title", get(allVisiblePaused) ? "Resume the jobs shown on this page" : "Pause the jobs shown on this page");
			set_text(text_2, `${get(allVisiblePaused) ? "Resume visible" : "Pause visible"} (${get(visibleJobs).length ?? ""})`);
			button_1.disabled = get(saving);
			button_2.disabled = get(saving);
			button_3.disabled = get(saving);
			classes_1 = set_class(button_5, 1, "filter-chip", null, classes_1, { chosen: get(showLongJobs) });
			set_attribute(button_5, "aria-pressed", get(showLongJobs));
			set_text(text_5, get(longJobsCount));
			button_12.disabled = !get(jobs).length || get(saving);
		});
		delegated("click", button, () => void toggleVisible());
		delegated("click", button_1, () => void load());
		delegated("click", button_2, beginOnce);
		delegated("click", button_3, beginNew);
		delegated("click", button_5, () => {
			set(showLongJobs, !get(showLongJobs));
			set(page, 1);
		});
		delegated("click", button_12, () => void clearAll());
		append($$anchor, section);
	};
	if_block(node, ($$render) => {
		if (!get(editorOpen)) $$render(consequent_6);
	});
	var node_9 = sibling(node, 2);
	var consequent_19 = ($$anchor) => {
		var section_1 = root_21$2();
		var form = child(section_1);
		var div_17 = child(form);
		var button_13 = child(div_17);
		var div_18 = sibling(button_13, 2);
		var h2 = child(div_18);
		var text_18 = only_child(h2, true);
		var node_10 = sibling(h2, 2);
		var consequent_7 = ($$anchor) => {
			var span_11 = root_3$3();
			var text_19 = only_child(span_11, true);
			template_effect(() => {
				set_attribute(span_11, "title", get(editing));
				set_text(text_19, get(editing));
			});
			append($$anchor, span_11);
		};
		if_block(node_10, ($$render) => {
			if (get(editing)) $$render(consequent_7);
		});
		reset(div_18);
		reset(div_17);
		var div_19 = sibling(div_17, 2);
		var div_20 = child(div_19);
		var node_11 = child(div_20);
		var consequent_8 = ($$anchor) => {
			var label = root_9$2();
			var input_1 = sibling(child(label), 2);
			remove_input_defaults(input_1);
			reset(label);
			template_effect(($0) => input_1.readOnly = $0, [() => Boolean(get(editing))]);
			bind_value(input_1, () => get(name), ($$value) => set(name, $$value));
			append($$anchor, label);
		};
		if_block(node_11, ($$render) => {
			if (!get(runOnce)) $$render(consequent_8);
		});
		var label_1 = sibling(node_11, 2);
		var select = sibling(child(label_1), 2);
		var option_1 = child(select);
		option_1.value = option_1.__value = "interval";
		var option_2 = sibling(option_1);
		option_2.value = option_2.__value = "daily";
		var option_3 = sibling(option_2);
		option_3.value = option_3.__value = "once";
		reset(select);
		init_select(select);
		reset(label_1);
		var node_12 = sibling(label_1, 2);
		var consequent_9 = ($$anchor) => {
			var label_2 = root_10$2();
			var input_2 = sibling(child(label_2), 2);
			remove_input_defaults(input_2);
			reset(label_2);
			bind_value(input_2, () => get(interval), ($$value) => set(interval, $$value));
			append($$anchor, label_2);
		};
		var consequent_10 = ($$anchor) => {
			var label_3 = root_11$2();
			var input_3 = sibling(child(label_3), 2);
			remove_input_defaults(input_3);
			reset(label_3);
			bind_value(input_3, () => get(onceDelay), ($$value) => set(onceDelay, $$value));
			append($$anchor, label_3);
		};
		var consequent_11 = ($$anchor) => {
			var label_4 = root_12$2();
			var input_4 = sibling(child(label_4), 2);
			remove_input_defaults(input_4);
			reset(label_4);
			bind_value(input_4, () => get(dailyAt), ($$value) => set(dailyAt, $$value));
			append($$anchor, label_4);
		};
		if_block(node_12, ($$render) => {
			if (get(schedule) === "interval") $$render(consequent_9);
			else if (get(schedule) === "once") $$render(consequent_10, 1);
			else if (get(schedule) === "daily") $$render(consequent_11, 2);
		});
		reset(div_20);
		var node_13 = sibling(div_20, 2);
		var consequent_12 = ($$anchor) => {
			var label_5 = root_13$2();
			var input_5 = child(label_5);
			remove_input_defaults(input_5);
			next(2);
			reset(label_5);
			bind_checked(input_5, () => get(exact), ($$value) => set(exact, $$value));
			append($$anchor, label_5);
		};
		if_block(node_13, ($$render) => {
			if (get(schedule) === "interval") $$render(consequent_12);
		});
		var label_6 = sibling(node_13, 2);
		var textarea_1 = sibling(child(label_6), 2);
		remove_textarea_child(textarea_1);
		reset(label_6);
		var div_21 = sibling(label_6, 2);
		var text_20 = only_child(div_21);
		var div_22 = sibling(div_21, 2);
		var button_14 = child(div_22);
		var input_6 = sibling(button_14, 2);
		bind_this(input_6, ($$value) => imageInput = $$value, () => imageInput);
		var text_21 = only_child(sibling(input_6, 2), true);
		reset(div_22);
		var node_14 = sibling(div_22, 2);
		var consequent_13 = ($$anchor) => {
			var div_23 = root_15$2();
			each(div_23, 21, () => get(images), (image) => image.ref, ($$anchor, image) => {
				var div_24 = root_14$2();
				var img = child(div_24);
				var span_13 = sibling(img, 2);
				var text_22 = only_child(span_13, true);
				var button_15 = sibling(span_13, 2);
				reset(div_24);
				template_effect(() => {
					set_attribute(img, "src", get(image).url);
					set_attribute(img, "alt", get(image).name);
					set_attribute(span_13, "title", get(image).name);
					set_text(text_22, get(image).name);
					set_attribute(button_15, "title", "Remove " + get(image).name);
					set_attribute(button_15, "aria-label", "Remove " + get(image).name);
					button_15.disabled = get(saving) || get(uploadingImage);
				});
				delegated("click", button_15, () => set(images, get(images).filter((item) => item.ref !== get(image).ref), true));
				append($$anchor, div_24);
			});
			reset(div_23);
			append($$anchor, div_23);
		};
		if_block(node_14, ($$render) => {
			if (get(images).length) $$render(consequent_13);
		});
		reset(div_19);
		var div_25 = sibling(div_19, 2);
		var div_26 = child(div_25);
		var node_15 = child(div_26);
		var consequent_14 = ($$anchor) => {
			var fragment_1 = root_16$2();
			var button_16 = sibling(first_child(fragment_1), 2);
			var button_17 = sibling(button_16, 2);
			delegated("click", button_16, () => set(confirmDiscard, false));
			delegated("click", button_17, discardEditor);
			append($$anchor, fragment_1);
		};
		var consequent_15 = ($$anchor) => {
			var span_14 = root_17$2();
			var text_23 = only_child(span_14, true);
			template_effect(() => set_text(text_23, get(editorError)));
			append($$anchor, span_14);
		};
		var consequent_16 = ($$anchor) => {
			append($$anchor, root_18$2());
		};
		var consequent_17 = ($$anchor) => {
			append($$anchor, root_19$2());
		};
		var consequent_18 = ($$anchor) => {
			append($$anchor, root_20$2());
		};
		if_block(node_15, ($$render) => {
			if (get(confirmDiscard)) $$render(consequent_14);
			else if (get(editorError)) $$render(consequent_15, 1);
			else if (get(duplicateName)) $$render(consequent_16, 2);
			else if (get(dirty)) $$render(consequent_17, 3);
			else if (get(editing)) $$render(consequent_18, 4);
		});
		reset(div_26);
		var div_27 = sibling(div_26, 2);
		var span_18 = child(div_27);
		var text_24 = only_child(span_18);
		var button_18 = sibling(span_18, 2);
		var button_19 = sibling(button_18, 2);
		var text_25 = only_child(button_19, true);
		reset(div_27);
		reset(div_25);
		reset(form);
		reset(section_1);
		bind_this(section_1, ($$value) => set(editorPage, $$value), () => get(editorPage));
		template_effect(($0, $1, $2, $3) => {
			button_13.disabled = get(saving);
			set_text(text_18, get(editing) ? "Edit job" : get(runOnce) ? "Run once" : "New job");
			set_class(div_19, 1, "editor-body" + (get(images).length ? " has-images" : ""));
			set_text(text_20, `${$0 ?? ""} characters · ${$1 ?? ""} lines`);
			button_14.disabled = get(uploadingImage) || get(saving) || get(images).length >= 4;
			input_6.disabled = get(uploadingImage) || get(saving) || get(images).length >= 4;
			set_text(text_21, get(uploadingImage) ? "Uploading…" : get(images).length + "/4 images");
			set_text(text_24, `Ctrl/⌘ + Enter to ${get(runOnce) ? "run" : "save"}`);
			button_18.disabled = get(saving);
			button_19.disabled = $2;
			set_text(text_25, $3);
		}, [
			() => get(promptCharacters).toLocaleString(),
			() => get(promptLines).toLocaleString(),
			() => get(saving) || get(uploadingImage) || !get(dirty) || get(duplicateName) || !get(prompt).trim() || !get(runOnce) && !get(name).trim(),
			() => get(saving) ? get(runOnce) ? "Queuing…" : "Saving…" : get(editing) ? "Save changes" : get(runOnce) ? Number(get(onceDelay)) > 0 ? "Schedule once" : "Run once" : "Create job"
		]);
		event("submit", form, (event) => {
			event.preventDefault();
			submit();
		});
		delegated("click", button_13, requestClose);
		bind_select_value(select, () => get(schedule), ($$value) => set(schedule, $$value));
		bind_value(textarea_1, () => get(prompt), ($$value) => set(prompt, $$value));
		delegated("click", button_14, () => imageInput?.click());
		delegated("change", input_6, (event) => void addImages(event.currentTarget));
		delegated("click", button_18, requestClose);
		append($$anchor, section_1);
	};
	if_block(node_9, ($$render) => {
		if (get(editorOpen)) $$render(consequent_19);
	});
	append($$anchor, fragment);
	pop();
}
delegate(["click", "change"]);
//#endregion
//#region src/ui/ChatComposer.svelte
var root$3 = /* @__PURE__ */ from_html(`<div class="composer-preview"><img/> <button type="button">×</button></div>`);
var root_1$3 = /* @__PURE__ */ from_html(`<div class="composer-previews" aria-label="Images to attach"></div>`);
var root_2$2 = /* @__PURE__ */ from_html(`<button type="button" aria-label="Attach images" title="Attach images">＋</button> <input type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple="" aria-label="Choose images"/>`, 1);
var root_3$2 = /* @__PURE__ */ from_html(`<p role="status"> </p>`);
var root_4$2 = /* @__PURE__ */ from_html(`<form><div class="chat-composer"><!> <textarea rows="2" maxlength="32000"></textarea> <div class="composer-actions"><div class="composer-attach"><!> <small> </small></div> <button class="composer-send" type="submit"> </button></div></div> <!> <p class="composer-disclaimer"> </p></form>`);
function ChatComposer($$anchor, $$props) {
	push($$props, true);
	let disabled = prop($$props, "disabled", 3, false);
	let draft = /* @__PURE__ */ state("");
	let images = /* @__PURE__ */ state(proxy([]));
	let uploading = /* @__PURE__ */ state(false);
	let sending = /* @__PURE__ */ state(false);
	let locked = /* @__PURE__ */ state(false);
	let feedback = /* @__PURE__ */ state("");
	let dragging = /* @__PURE__ */ state(false);
	let textarea = /* @__PURE__ */ state(void 0);
	let fileInput = /* @__PURE__ */ state(void 0);
	const canAttach = /* @__PURE__ */ user_derived(() => $$props.mode === "fresh" && !disabled() && !get(locked) && !get(sending) && !get(uploading));
	const canSend = /* @__PURE__ */ user_derived(() => !disabled() && !get(locked) && !get(sending) && !get(uploading) && !!get(draft).trim());
	onMount(() => {
		if ($$props.mode === "fresh") get(textarea)?.focus();
	});
	async function addFiles(files) {
		if (!files.length) return;
		if (!get(canAttach)) {
			set(feedback, $$props.mode === "reply" ? "Images can only be sent with fresh chats." : "Wait for the current upload.", true);
			return;
		}
		if (get(images).length + files.length > 4) {
			set(feedback, "At most four images per fresh chat.");
			return;
		}
		set(uploading, true);
		set(feedback, "");
		try {
			for (const file of files) {
				if (![
					"image/png",
					"image/jpeg",
					"image/gif",
					"image/webp"
				].includes(file.type)) throw new Error("Only PNG, JPEG, GIF or WebP images are supported.");
				if (file.size > 8388608) throw new Error("Images must be 8 MiB or smaller.");
				const data = await new Promise((resolve, reject) => {
					const reader = new FileReader();
					reader.onerror = () => reject(/* @__PURE__ */ new Error("Could not read image."));
					reader.onload = () => {
						const encoded = reader.result;
						if (typeof encoded !== "string" || !encoded.includes(",")) reject(/* @__PURE__ */ new Error("Could not encode image."));
						else resolve(encoded.slice(encoded.indexOf(",") + 1));
					};
					reader.readAsDataURL(file);
				});
				const response = await fetch("./api/images", {
					method: "POST",
					headers: { "content-type": "application/json" },
					body: JSON.stringify({
						name: file.name,
						data
					})
				});
				if (!response.ok) throw new Error("Image upload failed.");
				const result = await response.json();
				if (!result.image?.ref || !result.image.url.startsWith("./api/images/")) throw new Error("Image upload receipt was invalid.");
				set(images, [...get(images), result.image], true);
			}
		} catch (error) {
			set(feedback, error instanceof Error ? error.message : "Image upload failed.", true);
		} finally {
			set(uploading, false);
		}
	}
	async function submit() {
		if (!get(canSend)) return;
		set(sending, true);
		set(feedback, "");
		try {
			const result = await $$props.onSend(get(draft), get(images).map((image) => image.ref));
			if (result.ok) {
				set(draft, "");
				set(images, [], true);
				set(feedback, result.message, true);
			} else {
				set(feedback, result.message, true);
				set(locked, !!result.ambiguous);
			}
		} catch {
			set(locked, true);
			set(feedback, "Send confirmation was lost. Check local Chats before making a separate new request; this draft will not retry.");
		} finally {
			set(sending, false);
		}
	}
	function keydown(event) {
		if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
			event.preventDefault();
			submit();
		}
	}
	function pasted(event) {
		const files = Array.from(event.clipboardData?.files || []);
		if (!files.length) return;
		if (!event.clipboardData?.getData("text/plain")) event.preventDefault();
		addFiles(files);
	}
	function dropped(event) {
		event.preventDefault();
		set(dragging, false);
		addFiles(Array.from(event.dataTransfer?.files || []));
	}
	var form = root_4$2();
	let classes;
	var div = child(form);
	var node = child(div);
	var consequent = ($$anchor) => {
		var div_1 = root_1$3();
		each(div_1, 21, () => get(images), (image) => image.ref, ($$anchor, image) => {
			var div_2 = root$3();
			var img = child(div_2);
			var button = sibling(img, 2);
			reset(div_2);
			template_effect(() => {
				set_attribute(img, "src", get(image).url);
				set_attribute(img, "alt", get(image).name);
				set_attribute(button, "aria-label", "Remove " + get(image).name);
				button.disabled = !get(canAttach);
			});
			delegated("click", button, () => set(images, get(images).filter((item) => item.ref !== get(image).ref), true));
			append($$anchor, div_2);
		});
		reset(div_1);
		append($$anchor, div_1);
	};
	if_block(node, ($$render) => {
		if (get(images).length) $$render(consequent);
	});
	var textarea_1 = sibling(node, 2);
	remove_textarea_child(textarea_1);
	bind_this(textarea_1, ($$value) => set(textarea, $$value), () => get(textarea));
	var div_3 = sibling(textarea_1, 2);
	var div_4 = child(div_3);
	var node_1 = child(div_4);
	var consequent_1 = ($$anchor) => {
		var fragment = root_2$2();
		var button_1 = first_child(fragment);
		var input = sibling(button_1, 2);
		bind_this(input, ($$value) => set(fileInput, $$value), () => get(fileInput));
		template_effect(() => {
			button_1.disabled = !get(canAttach);
			input.disabled = !get(canAttach);
		});
		delegated("click", button_1, () => get(fileInput)?.click());
		delegated("change", input, (event) => {
			addFiles(Array.from(event.currentTarget.files || []));
			event.currentTarget.value = "";
		});
		append($$anchor, fragment);
	};
	if_block(node_1, ($$render) => {
		if ($$props.mode === "fresh") $$render(consequent_1);
	});
	var text = only_child(sibling(node_1, 2), true);
	reset(div_4);
	var button_2 = sibling(div_4, 2);
	var text_1 = only_child(button_2, true);
	reset(div_3);
	reset(div);
	var node_2 = sibling(div, 2);
	var consequent_2 = ($$anchor) => {
		var p = root_3$2();
		let classes_1;
		var text_2 = only_child(p, true);
		template_effect(() => {
			classes_1 = set_class(p, 1, "composer-feedback", null, classes_1, { "composer-error": get(locked) });
			set_text(text_2, get(feedback));
		});
		append($$anchor, p);
	};
	if_block(node_2, ($$render) => {
		if (get(feedback)) $$render(consequent_2);
	});
	var text_3 = only_child(sibling(node_2, 2), true);
	reset(form);
	template_effect(() => {
		classes = set_class(form, 1, "chat-composer-wrap", null, classes, { dragging: get(dragging) });
		set_attribute(form, "aria-label", $$props.mode === "fresh" ? "New chat composer" : "Reply composer");
		textarea_1.disabled = disabled() || get(locked) || get(sending);
		set_attribute(textarea_1, "aria-label", $$props.mode === "fresh" ? "Message for new chat" : "Reply to this chat");
		set_attribute(textarea_1, "placeholder", $$props.mode === "fresh" ? "Message Prompta…" : "Reply to this chat…");
		set_text(text, get(uploading) ? "Uploading…" : $$props.mode === "fresh" ? get(images).length + "/4 images · paste or drop" : "Exact saved branch only");
		button_2.disabled = !get(canSend);
		set_attribute(button_2, "aria-label", get(sending) ? "Sending" : $$props.mode === "fresh" ? "Send fresh chat" : "Send reply");
		set_text(text_1, get(sending) ? "Sending…" : "↑");
		set_text(text_3, $$props.mode === "fresh" ? "Queues one fresh ChatGPT chat using Prompta delivery. Enter sends · Shift+Enter adds a line." : "Only an explicit send can reopen this exact saved conversation. Enter sends · Shift+Enter adds a line.");
	});
	event("submit", form, (event) => {
		event.preventDefault();
		submit();
	});
	event("dragover", form, (event) => {
		event.preventDefault();
		set(dragging, $$props.mode === "fresh");
	});
	event("dragleave", form, () => set(dragging, false));
	event("drop", form, dropped);
	delegated("keydown", textarea_1, keydown);
	event("paste", textarea_1, pasted);
	bind_value(textarea_1, () => get(draft), ($$value) => set(draft, $$value));
	append($$anchor, form);
	pop();
}
delegate([
	"click",
	"keydown",
	"change"
]);
//#endregion
//#region node_modules/marked/lib/marked.esm.js
/**
* marked v16.4.2 - a markdown parser
* Copyright (c) 2018-2025, MarkedJS. (MIT License)
* Copyright (c) 2011-2018, Christopher Jeffrey. (MIT License)
* https://github.com/markedjs/marked
*/
/**
* DO NOT EDIT THIS FILE
* The code in this file is generated from files in ./src/
*/
function L() {
	return {
		async: !1,
		breaks: !1,
		extensions: null,
		gfm: !0,
		hooks: null,
		pedantic: !1,
		renderer: null,
		silent: !1,
		tokenizer: null,
		walkTokens: null
	};
}
var T = L();
function G(l) {
	T = l;
}
var E = { exec: () => null };
function d(l, e = "") {
	let t = typeof l == "string" ? l : l.source, n = {
		replace: (r, i) => {
			let s = typeof i == "string" ? i : i.source;
			return s = s.replace(m.caret, "$1"), t = t.replace(r, s), n;
		},
		getRegex: () => new RegExp(t, e)
	};
	return n;
}
var be = (() => {
	try {
		return true;
	} catch {
		return !1;
	}
})();
var m = {
	codeRemoveIndent: /^(?: {1,4}| {0,3}\t)/gm,
	outputLinkReplace: /\\([\[\]])/g,
	indentCodeCompensation: /^(\s+)(?:```)/,
	beginningSpace: /^\s+/,
	endingHash: /#$/,
	startingSpaceChar: /^ /,
	endingSpaceChar: / $/,
	nonSpaceChar: /[^ ]/,
	newLineCharGlobal: /\n/g,
	tabCharGlobal: /\t/g,
	multipleSpaceGlobal: /\s+/g,
	blankLine: /^[ \t]*$/,
	doubleBlankLine: /\n[ \t]*\n[ \t]*$/,
	blockquoteStart: /^ {0,3}>/,
	blockquoteSetextReplace: /\n {0,3}((?:=+|-+) *)(?=\n|$)/g,
	blockquoteSetextReplace2: /^ {0,3}>[ \t]?/gm,
	listReplaceTabs: /^\t+/,
	listReplaceNesting: /^ {1,4}(?=( {4})*[^ ])/g,
	listIsTask: /^\[[ xX]\] /,
	listReplaceTask: /^\[[ xX]\] +/,
	anyLine: /\n.*\n/,
	hrefBrackets: /^<(.*)>$/,
	tableDelimiter: /[:|]/,
	tableAlignChars: /^\||\| *$/g,
	tableRowBlankLine: /\n[ \t]*$/,
	tableAlignRight: /^ *-+: *$/,
	tableAlignCenter: /^ *:-+: *$/,
	tableAlignLeft: /^ *:-+ *$/,
	startATag: /^<a /i,
	endATag: /^<\/a>/i,
	startPreScriptTag: /^<(pre|code|kbd|script)(\s|>)/i,
	endPreScriptTag: /^<\/(pre|code|kbd|script)(\s|>)/i,
	startAngleBracket: /^</,
	endAngleBracket: />$/,
	pedanticHrefTitle: /^([^'"]*[^\s])\s+(['"])(.*)\2/,
	unicodeAlphaNumeric: /[\p{L}\p{N}]/u,
	escapeTest: /[&<>"']/,
	escapeReplace: /[&<>"']/g,
	escapeTestNoEncode: /[<>"']|&(?!(#\d{1,7}|#[Xx][a-fA-F0-9]{1,6}|\w+);)/,
	escapeReplaceNoEncode: /[<>"']|&(?!(#\d{1,7}|#[Xx][a-fA-F0-9]{1,6}|\w+);)/g,
	unescapeTest: /&(#(?:\d+)|(?:#x[0-9A-Fa-f]+)|(?:\w+));?/gi,
	caret: /(^|[^\[])\^/g,
	percentDecode: /%25/g,
	findPipe: /\|/g,
	splitPipe: / \|/,
	slashPipe: /\\\|/g,
	carriageReturn: /\r\n|\r/g,
	spaceLine: /^ +$/gm,
	notSpaceStart: /^\S*/,
	endingNewline: /\n$/,
	listItemRegex: (l) => new RegExp(`^( {0,3}${l})((?:[	 ][^\\n]*)?(?:\\n|$))`),
	nextBulletRegex: (l) => new RegExp(`^ {0,${Math.min(3, l - 1)}}(?:[*+-]|\\d{1,9}[.)])((?:[ 	][^\\n]*)?(?:\\n|$))`),
	hrRegex: (l) => new RegExp(`^ {0,${Math.min(3, l - 1)}}((?:- *){3,}|(?:_ *){3,}|(?:\\* *){3,})(?:\\n+|$)`),
	fencesBeginRegex: (l) => new RegExp(`^ {0,${Math.min(3, l - 1)}}(?:\`\`\`|~~~)`),
	headingBeginRegex: (l) => new RegExp(`^ {0,${Math.min(3, l - 1)}}#`),
	htmlBeginRegex: (l) => new RegExp(`^ {0,${Math.min(3, l - 1)}}<(?:[a-z].*>|!--)`, "i")
};
var Re = /^(?:[ \t]*(?:\n|$))+/;
var Te = /^((?: {4}| {0,3}\t)[^\n]+(?:\n(?:[ \t]*(?:\n|$))*)?)+/;
var Oe = /^ {0,3}(`{3,}(?=[^`\n]*(?:\n|$))|~{3,})([^\n]*)(?:\n|$)(?:|([\s\S]*?)(?:\n|$))(?: {0,3}\1[~`]* *(?=\n|$)|$)/;
var I = /^ {0,3}((?:-[\t ]*){3,}|(?:_[ \t]*){3,}|(?:\*[ \t]*){3,})(?:\n+|$)/;
var we = /^ {0,3}(#{1,6})(?=\s|$)(.*)(?:\n+|$)/;
var F = /(?:[*+-]|\d{1,9}[.)])/;
var ie = /^(?!bull |blockCode|fences|blockquote|heading|html|table)((?:.|\n(?!\s*?\n|bull |blockCode|fences|blockquote|heading|html|table))+?)\n {0,3}(=+|-+) *(?:\n+|$)/;
var oe = d(ie).replace(/bull/g, F).replace(/blockCode/g, /(?: {4}| {0,3}\t)/).replace(/fences/g, / {0,3}(?:`{3,}|~{3,})/).replace(/blockquote/g, / {0,3}>/).replace(/heading/g, / {0,3}#{1,6}/).replace(/html/g, / {0,3}<[^\n>]+>\n/).replace(/\|table/g, "").getRegex();
var ye = d(ie).replace(/bull/g, F).replace(/blockCode/g, /(?: {4}| {0,3}\t)/).replace(/fences/g, / {0,3}(?:`{3,}|~{3,})/).replace(/blockquote/g, / {0,3}>/).replace(/heading/g, / {0,3}#{1,6}/).replace(/html/g, / {0,3}<[^\n>]+>\n/).replace(/table/g, / {0,3}\|?(?:[:\- ]*\|)+[\:\- ]*\n/).getRegex();
var j = /^([^\n]+(?:\n(?!hr|heading|lheading|blockquote|fences|list|html|table| +\n)[^\n]+)*)/;
var Pe = /^[^\n]+/;
var Q = /(?!\s*\])(?:\\[\s\S]|[^\[\]\\])+/;
var Se = d(/^ {0,3}\[(label)\]: *(?:\n[ \t]*)?([^<\s][^\s]*|<.*?>)(?:(?: +(?:\n[ \t]*)?| *\n[ \t]*)(title))? *(?:\n+|$)/).replace("label", Q).replace("title", /(?:"(?:\\"?|[^"\\])*"|'[^'\n]*(?:\n[^'\n]+)*\n?'|\([^()]*\))/).getRegex();
var $e = d(/^( {0,3}bull)([ \t][^\n]+?)?(?:\n|$)/).replace(/bull/g, F).getRegex();
var v = "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|meta|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul";
var U = /<!--(?:-?>|[\s\S]*?(?:-->|$))/;
var _e = d("^ {0,3}(?:<(script|pre|style|textarea)[\\s>][\\s\\S]*?(?:</\\1>[^\\n]*\\n+|$)|comment[^\\n]*(\\n+|$)|<\\?[\\s\\S]*?(?:\\?>\\n*|$)|<![A-Z][\\s\\S]*?(?:>\\n*|$)|<!\\[CDATA\\[[\\s\\S]*?(?:\\]\\]>\\n*|$)|</?(tag)(?: +|\\n|/?>)[\\s\\S]*?(?:(?:\\n[ 	]*)+\\n|$)|<(?!script|pre|style|textarea)([a-z][\\w-]*)(?:attribute)*? */?>(?=[ \\t]*(?:\\n|$))[\\s\\S]*?(?:(?:\\n[ 	]*)+\\n|$)|</(?!script|pre|style|textarea)[a-z][\\w-]*\\s*>(?=[ \\t]*(?:\\n|$))[\\s\\S]*?(?:(?:\\n[ 	]*)+\\n|$))", "i").replace("comment", U).replace("tag", v).replace("attribute", / +[a-zA-Z:_][\w.:-]*(?: *= *"[^"\n]*"| *= *'[^'\n]*'| *= *[^\s"'=<>`]+)?/).getRegex();
var ae = d(j).replace("hr", I).replace("heading", " {0,3}#{1,6}(?:\\s|$)").replace("|lheading", "").replace("|table", "").replace("blockquote", " {0,3}>").replace("fences", " {0,3}(?:`{3,}(?=[^`\\n]*\\n)|~{3,})[^\\n]*\\n").replace("list", " {0,3}(?:[*+-]|1[.)]) ").replace("html", "</?(?:tag)(?: +|\\n|/?>)|<(?:script|pre|style|textarea|!--)").replace("tag", v).getRegex();
var K = {
	blockquote: d(/^( {0,3}> ?(paragraph|[^\n]*)(?:\n|$))+/).replace("paragraph", ae).getRegex(),
	code: Te,
	def: Se,
	fences: Oe,
	heading: we,
	hr: I,
	html: _e,
	lheading: oe,
	list: $e,
	newline: Re,
	paragraph: ae,
	table: E,
	text: Pe
};
var re = d("^ *([^\\n ].*)\\n {0,3}((?:\\| *)?:?-+:? *(?:\\| *:?-+:? *)*(?:\\| *)?)(?:\\n((?:(?! *\\n|hr|heading|blockquote|code|fences|list|html).*(?:\\n|$))*)\\n*|$)").replace("hr", I).replace("heading", " {0,3}#{1,6}(?:\\s|$)").replace("blockquote", " {0,3}>").replace("code", "(?: {4}| {0,3}	)[^\\n]").replace("fences", " {0,3}(?:`{3,}(?=[^`\\n]*\\n)|~{3,})[^\\n]*\\n").replace("list", " {0,3}(?:[*+-]|1[.)]) ").replace("html", "</?(?:tag)(?: +|\\n|/?>)|<(?:script|pre|style|textarea|!--)").replace("tag", v).getRegex();
var Me = {
	...K,
	lheading: ye,
	table: re,
	paragraph: d(j).replace("hr", I).replace("heading", " {0,3}#{1,6}(?:\\s|$)").replace("|lheading", "").replace("table", re).replace("blockquote", " {0,3}>").replace("fences", " {0,3}(?:`{3,}(?=[^`\\n]*\\n)|~{3,})[^\\n]*\\n").replace("list", " {0,3}(?:[*+-]|1[.)]) ").replace("html", "</?(?:tag)(?: +|\\n|/?>)|<(?:script|pre|style|textarea|!--)").replace("tag", v).getRegex()
};
var ze = {
	...K,
	html: d(`^ *(?:comment *(?:\\n|\\s*$)|<(tag)[\\s\\S]+?</\\1> *(?:\\n{2,}|\\s*$)|<tag(?:"[^"]*"|'[^']*'|\\s[^'"/>\\s]*)*?/?> *(?:\\n{2,}|\\s*$))`).replace("comment", U).replace(/tag/g, "(?!(?:a|em|strong|small|s|cite|q|dfn|abbr|data|time|code|var|samp|kbd|sub|sup|i|b|u|mark|ruby|rt|rp|bdi|bdo|span|br|wbr|ins|del|img)\\b)\\w+(?!:|[^\\w\\s@]*@)\\b").getRegex(),
	def: /^ *\[([^\]]+)\]: *<?([^\s>]+)>?(?: +(["(][^\n]+[")]))? *(?:\n+|$)/,
	heading: /^(#{1,6})(.*)(?:\n+|$)/,
	fences: E,
	lheading: /^(.+?)\n {0,3}(=+|-+) *(?:\n+|$)/,
	paragraph: d(j).replace("hr", I).replace("heading", ` *#{1,6} *[^
]`).replace("lheading", oe).replace("|table", "").replace("blockquote", " {0,3}>").replace("|fences", "").replace("|list", "").replace("|html", "").replace("|tag", "").getRegex()
};
var Ae = /^\\([!"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])/;
var Ee = /^(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)/;
var le = /^( {2,}|\\)\n(?!\s*$)/;
var Ie = /^(`+|[^`])(?:(?= {2,}\n)|[\s\S]*?(?:(?=[\\<!\[`*_]|\b_|$)|[^ ](?= {2,}\n)))/;
var D = /[\p{P}\p{S}]/u;
var W = /[\s\p{P}\p{S}]/u;
var ue = /[^\s\p{P}\p{S}]/u;
var Ce = d(/^((?![*_])punctSpace)/, "u").replace(/punctSpace/g, W).getRegex();
var pe = /(?!~)[\p{P}\p{S}]/u;
var Be = /(?!~)[\s\p{P}\p{S}]/u;
var qe = /(?:[^\s\p{P}\p{S}]|~)/u;
var ve = d(/link|precode-code|html/, "g").replace("link", /\[(?:[^\[\]`]|(?<a>`+)[^`]+\k<a>(?!`))*?\]\((?:\\[\s\S]|[^\\\(\)]|\((?:\\[\s\S]|[^\\\(\)])*\))*\)/).replace("precode-", be ? "(?<!`)()" : "(^^|[^`])").replace("code", /(?<b>`+)[^`]+\k<b>(?!`)/).replace("html", /<(?! )[^<>]*?>/).getRegex();
var ce = /^(?:\*+(?:((?!\*)punct)|[^\s*]))|^_+(?:((?!_)punct)|([^\s_]))/;
var De = d(ce, "u").replace(/punct/g, D).getRegex();
var He = d(ce, "u").replace(/punct/g, pe).getRegex();
var he = "^[^_*]*?__[^_*]*?\\*[^_*]*?(?=__)|[^*]+(?=[^*])|(?!\\*)punct(\\*+)(?=[\\s]|$)|notPunctSpace(\\*+)(?!\\*)(?=punctSpace|$)|(?!\\*)punctSpace(\\*+)(?=notPunctSpace)|[\\s](\\*+)(?!\\*)(?=punct)|(?!\\*)punct(\\*+)(?!\\*)(?=punct)|notPunctSpace(\\*+)(?=notPunctSpace)";
var Ze = d(he, "gu").replace(/notPunctSpace/g, ue).replace(/punctSpace/g, W).replace(/punct/g, D).getRegex();
var Ge = d(he, "gu").replace(/notPunctSpace/g, qe).replace(/punctSpace/g, Be).replace(/punct/g, pe).getRegex();
var Ne = d("^[^_*]*?\\*\\*[^_*]*?_[^_*]*?(?=\\*\\*)|[^_]+(?=[^_])|(?!_)punct(_+)(?=[\\s]|$)|notPunctSpace(_+)(?!_)(?=punctSpace|$)|(?!_)punctSpace(_+)(?=notPunctSpace)|[\\s](_+)(?!_)(?=punct)|(?!_)punct(_+)(?!_)(?=punct)", "gu").replace(/notPunctSpace/g, ue).replace(/punctSpace/g, W).replace(/punct/g, D).getRegex();
var Fe = d(/\\(punct)/, "gu").replace(/punct/g, D).getRegex();
var je = d(/^<(scheme:[^\s\x00-\x1f<>]*|email)>/).replace("scheme", /[a-zA-Z][a-zA-Z0-9+.-]{1,31}/).replace("email", /[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+(@)[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+(?![-_])/).getRegex();
var Qe = d(U).replace("(?:-->|$)", "-->").getRegex();
var Ue = d("^comment|^</[a-zA-Z][\\w:-]*\\s*>|^<[a-zA-Z][\\w-]*(?:attribute)*?\\s*/?>|^<\\?[\\s\\S]*?\\?>|^<![a-zA-Z]+\\s[\\s\\S]*?>|^<!\\[CDATA\\[[\\s\\S]*?\\]\\]>").replace("comment", Qe).replace("attribute", /\s+[a-zA-Z:_][\w.:-]*(?:\s*=\s*"[^"]*"|\s*=\s*'[^']*'|\s*=\s*[^\s"'=<>`]+)?/).getRegex();
var q = /(?:\[(?:\\[\s\S]|[^\[\]\\])*\]|\\[\s\S]|`+[^`]*?`+(?!`)|[^\[\]\\`])*?/;
var Ke = d(/^!?\[(label)\]\(\s*(href)(?:(?:[ \t]*(?:\n[ \t]*)?)(title))?\s*\)/).replace("label", q).replace("href", /<(?:\\.|[^\n<>\\])+>|[^ \t\n\x00-\x1f]*/).replace("title", /"(?:\\"?|[^"\\])*"|'(?:\\'?|[^'\\])*'|\((?:\\\)?|[^)\\])*\)/).getRegex();
var de = d(/^!?\[(label)\]\[(ref)\]/).replace("label", q).replace("ref", Q).getRegex();
var ke = d(/^!?\[(ref)\](?:\[\])?/).replace("ref", Q).getRegex();
var We = d("reflink|nolink(?!\\()", "g").replace("reflink", de).replace("nolink", ke).getRegex();
var se = /[hH][tT][tT][pP][sS]?|[fF][tT][pP]/;
var X = {
	_backpedal: E,
	anyPunctuation: Fe,
	autolink: je,
	blockSkip: ve,
	br: le,
	code: Ee,
	del: E,
	emStrongLDelim: De,
	emStrongRDelimAst: Ze,
	emStrongRDelimUnd: Ne,
	escape: Ae,
	link: Ke,
	nolink: ke,
	punctuation: Ce,
	reflink: de,
	reflinkSearch: We,
	tag: Ue,
	text: Ie,
	url: E
};
var Xe = {
	...X,
	link: d(/^!?\[(label)\]\((.*?)\)/).replace("label", q).getRegex(),
	reflink: d(/^!?\[(label)\]\s*\[([^\]]*)\]/).replace("label", q).getRegex()
};
var N = {
	...X,
	emStrongRDelimAst: Ge,
	emStrongLDelim: He,
	url: d(/^((?:protocol):\/\/|www\.)(?:[a-zA-Z0-9\-]+\.?)+[^\s<]*|^email/).replace("protocol", se).replace("email", /[A-Za-z0-9._+-]+(@)[a-zA-Z0-9-_]+(?:\.[a-zA-Z0-9-_]*[a-zA-Z0-9])+(?![-_])/).getRegex(),
	_backpedal: /(?:[^?!.,:;*_'"~()&]+|\([^)]*\)|&(?![a-zA-Z0-9]+;$)|[?!.,:;*_'"~)]+(?!$))+/,
	del: /^(~~?)(?=[^\s~])((?:\\[\s\S]|[^\\])*?(?:\\[\s\S]|[^\s~\\]))\1(?=[^~]|$)/,
	text: d(/^([`~]+|[^`~])(?:(?= {2,}\n)|(?=[a-zA-Z0-9.!#$%&'*+\/=?_`{\|}~-]+@)|[\s\S]*?(?:(?=[\\<!\[`*~_]|\b_|protocol:\/\/|www\.|$)|[^ ](?= {2,}\n)|[^a-zA-Z0-9.!#$%&'*+\/=?_`{\|}~-](?=[a-zA-Z0-9.!#$%&'*+\/=?_`{\|}~-]+@)))/).replace("protocol", se).getRegex()
};
var Je = {
	...N,
	br: d(le).replace("{2,}", "*").getRegex(),
	text: d(N.text).replace("\\b_", "\\b_| {2,}\\n").replace(/\{2,\}/g, "*").getRegex()
};
var C = {
	normal: K,
	gfm: Me,
	pedantic: ze
};
var M = {
	normal: X,
	gfm: N,
	breaks: Je,
	pedantic: Xe
};
var Ve = {
	"&": "&amp;",
	"<": "&lt;",
	">": "&gt;",
	"\"": "&quot;",
	"'": "&#39;"
};
var ge = (l) => Ve[l];
function w(l, e) {
	if (e) {
		if (m.escapeTest.test(l)) return l.replace(m.escapeReplace, ge);
	} else if (m.escapeTestNoEncode.test(l)) return l.replace(m.escapeReplaceNoEncode, ge);
	return l;
}
function J(l) {
	try {
		l = encodeURI(l).replace(m.percentDecode, "%");
	} catch {
		return null;
	}
	return l;
}
function V(l, e) {
	let n = l.replace(m.findPipe, (i, s, a) => {
		let o = !1, p = s;
		for (; --p >= 0 && a[p] === "\\";) o = !o;
		return o ? "|" : " |";
	}).split(m.splitPipe), r = 0;
	if (n[0].trim() || n.shift(), n.length > 0 && !n.at(-1)?.trim() && n.pop(), e) if (n.length > e) n.splice(e);
	else for (; n.length < e;) n.push("");
	for (; r < n.length; r++) n[r] = n[r].trim().replace(m.slashPipe, "|");
	return n;
}
function z(l, e, t) {
	let n = l.length;
	if (n === 0) return "";
	let r = 0;
	for (; r < n;) {
		let i = l.charAt(n - r - 1);
		if (i === e && !t) r++;
		else if (i !== e && t) r++;
		else break;
	}
	return l.slice(0, n - r);
}
function fe(l, e) {
	if (l.indexOf(e[1]) === -1) return -1;
	let t = 0;
	for (let n = 0; n < l.length; n++) if (l[n] === "\\") n++;
	else if (l[n] === e[0]) t++;
	else if (l[n] === e[1] && (t--, t < 0)) return n;
	return t > 0 ? -2 : -1;
}
function me(l, e, t, n, r) {
	let i = e.href, s = e.title || null, a = l[1].replace(r.other.outputLinkReplace, "$1");
	n.state.inLink = !0;
	let o = {
		type: l[0].charAt(0) === "!" ? "image" : "link",
		raw: t,
		href: i,
		title: s,
		text: a,
		tokens: n.inlineTokens(a)
	};
	return n.state.inLink = !1, o;
}
function Ye(l, e, t) {
	let n = l.match(t.other.indentCodeCompensation);
	if (n === null) return e;
	let r = n[1];
	return e.split(`
`).map((i) => {
		let s = i.match(t.other.beginningSpace);
		if (s === null) return i;
		let [a] = s;
		return a.length >= r.length ? i.slice(r.length) : i;
	}).join(`
`);
}
var y = class {
	options;
	rules;
	lexer;
	constructor(e) {
		this.options = e || T;
	}
	space(e) {
		let t = this.rules.block.newline.exec(e);
		if (t && t[0].length > 0) return {
			type: "space",
			raw: t[0]
		};
	}
	code(e) {
		let t = this.rules.block.code.exec(e);
		if (t) {
			let n = t[0].replace(this.rules.other.codeRemoveIndent, "");
			return {
				type: "code",
				raw: t[0],
				codeBlockStyle: "indented",
				text: this.options.pedantic ? n : z(n, `
`)
			};
		}
	}
	fences(e) {
		let t = this.rules.block.fences.exec(e);
		if (t) {
			let n = t[0], r = Ye(n, t[3] || "", this.rules);
			return {
				type: "code",
				raw: n,
				lang: t[2] ? t[2].trim().replace(this.rules.inline.anyPunctuation, "$1") : t[2],
				text: r
			};
		}
	}
	heading(e) {
		let t = this.rules.block.heading.exec(e);
		if (t) {
			let n = t[2].trim();
			if (this.rules.other.endingHash.test(n)) {
				let r = z(n, "#");
				(this.options.pedantic || !r || this.rules.other.endingSpaceChar.test(r)) && (n = r.trim());
			}
			return {
				type: "heading",
				raw: t[0],
				depth: t[1].length,
				text: n,
				tokens: this.lexer.inline(n)
			};
		}
	}
	hr(e) {
		let t = this.rules.block.hr.exec(e);
		if (t) return {
			type: "hr",
			raw: z(t[0], `
`)
		};
	}
	blockquote(e) {
		let t = this.rules.block.blockquote.exec(e);
		if (t) {
			let n = z(t[0], `
`).split(`
`), r = "", i = "", s = [];
			for (; n.length > 0;) {
				let a = !1, o = [], p = 0;
				for (; p < n.length; p++) if (this.rules.other.blockquoteStart.test(n[p])) o.push(n[p]), a = !0;
				else if (!a) o.push(n[p]);
				else break;
				n = n.slice(p);
				let u = o.join(`
`), c = u.replace(this.rules.other.blockquoteSetextReplace, `
    $1`).replace(this.rules.other.blockquoteSetextReplace2, "");
				r = r ? `${r}
${u}` : u, i = i ? `${i}
${c}` : c;
				let g = this.lexer.state.top;
				if (this.lexer.state.top = !0, this.lexer.blockTokens(c, s, !0), this.lexer.state.top = g, n.length === 0) break;
				let h = s.at(-1);
				if (h?.type === "code") break;
				if (h?.type === "blockquote") {
					let R = h, f = R.raw + `
` + n.join(`
`), O = this.blockquote(f);
					s[s.length - 1] = O, r = r.substring(0, r.length - R.raw.length) + O.raw, i = i.substring(0, i.length - R.text.length) + O.text;
					break;
				} else if (h?.type === "list") {
					let R = h, f = R.raw + `
` + n.join(`
`), O = this.list(f);
					s[s.length - 1] = O, r = r.substring(0, r.length - h.raw.length) + O.raw, i = i.substring(0, i.length - R.raw.length) + O.raw, n = f.substring(s.at(-1).raw.length).split(`
`);
					continue;
				}
			}
			return {
				type: "blockquote",
				raw: r,
				tokens: s,
				text: i
			};
		}
	}
	list(e) {
		let t = this.rules.block.list.exec(e);
		if (t) {
			let n = t[1].trim(), r = n.length > 1, i = {
				type: "list",
				raw: "",
				ordered: r,
				start: r ? +n.slice(0, -1) : "",
				loose: !1,
				items: []
			};
			n = r ? `\\d{1,9}\\${n.slice(-1)}` : `\\${n}`, this.options.pedantic && (n = r ? n : "[*+-]");
			let s = this.rules.other.listItemRegex(n), a = !1;
			for (; e;) {
				let p = !1, u = "", c = "";
				if (!(t = s.exec(e)) || this.rules.block.hr.test(e)) break;
				u = t[0], e = e.substring(u.length);
				let g = t[2].split(`
`, 1)[0].replace(this.rules.other.listReplaceTabs, (H) => " ".repeat(3 * H.length)), h = e.split(`
`, 1)[0], R = !g.trim(), f = 0;
				if (this.options.pedantic ? (f = 2, c = g.trimStart()) : R ? f = t[1].length + 1 : (f = t[2].search(this.rules.other.nonSpaceChar), f = f > 4 ? 1 : f, c = g.slice(f), f += t[1].length), R && this.rules.other.blankLine.test(h) && (u += h + `
`, e = e.substring(h.length + 1), p = !0), !p) {
					let H = this.rules.other.nextBulletRegex(f), ee = this.rules.other.hrRegex(f), te = this.rules.other.fencesBeginRegex(f), ne = this.rules.other.headingBeginRegex(f), xe = this.rules.other.htmlBeginRegex(f);
					for (; e;) {
						let Z = e.split(`
`, 1)[0], A;
						if (h = Z, this.options.pedantic ? (h = h.replace(this.rules.other.listReplaceNesting, "  "), A = h) : A = h.replace(this.rules.other.tabCharGlobal, "    "), te.test(h) || ne.test(h) || xe.test(h) || H.test(h) || ee.test(h)) break;
						if (A.search(this.rules.other.nonSpaceChar) >= f || !h.trim()) c += `
` + A.slice(f);
						else {
							if (R || g.replace(this.rules.other.tabCharGlobal, "    ").search(this.rules.other.nonSpaceChar) >= 4 || te.test(g) || ne.test(g) || ee.test(g)) break;
							c += `
` + h;
						}
						!R && !h.trim() && (R = !0), u += Z + `
`, e = e.substring(Z.length + 1), g = A.slice(f);
					}
				}
				i.loose || (a ? i.loose = !0 : this.rules.other.doubleBlankLine.test(u) && (a = !0));
				let O = null, Y;
				this.options.gfm && (O = this.rules.other.listIsTask.exec(c), O && (Y = O[0] !== "[ ] ", c = c.replace(this.rules.other.listReplaceTask, ""))), i.items.push({
					type: "list_item",
					raw: u,
					task: !!O,
					checked: Y,
					loose: !1,
					text: c,
					tokens: []
				}), i.raw += u;
			}
			let o = i.items.at(-1);
			if (o) o.raw = o.raw.trimEnd(), o.text = o.text.trimEnd();
			else return;
			i.raw = i.raw.trimEnd();
			for (let p = 0; p < i.items.length; p++) if (this.lexer.state.top = !1, i.items[p].tokens = this.lexer.blockTokens(i.items[p].text, []), !i.loose) {
				let u = i.items[p].tokens.filter((g) => g.type === "space");
				i.loose = u.length > 0 && u.some((g) => this.rules.other.anyLine.test(g.raw));
			}
			if (i.loose) for (let p = 0; p < i.items.length; p++) i.items[p].loose = !0;
			return i;
		}
	}
	html(e) {
		let t = this.rules.block.html.exec(e);
		if (t) return {
			type: "html",
			block: !0,
			raw: t[0],
			pre: t[1] === "pre" || t[1] === "script" || t[1] === "style",
			text: t[0]
		};
	}
	def(e) {
		let t = this.rules.block.def.exec(e);
		if (t) {
			let n = t[1].toLowerCase().replace(this.rules.other.multipleSpaceGlobal, " "), r = t[2] ? t[2].replace(this.rules.other.hrefBrackets, "$1").replace(this.rules.inline.anyPunctuation, "$1") : "", i = t[3] ? t[3].substring(1, t[3].length - 1).replace(this.rules.inline.anyPunctuation, "$1") : t[3];
			return {
				type: "def",
				tag: n,
				raw: t[0],
				href: r,
				title: i
			};
		}
	}
	table(e) {
		let t = this.rules.block.table.exec(e);
		if (!t || !this.rules.other.tableDelimiter.test(t[2])) return;
		let n = V(t[1]), r = t[2].replace(this.rules.other.tableAlignChars, "").split("|"), i = t[3]?.trim() ? t[3].replace(this.rules.other.tableRowBlankLine, "").split(`
`) : [], s = {
			type: "table",
			raw: t[0],
			header: [],
			align: [],
			rows: []
		};
		if (n.length === r.length) {
			for (let a of r) this.rules.other.tableAlignRight.test(a) ? s.align.push("right") : this.rules.other.tableAlignCenter.test(a) ? s.align.push("center") : this.rules.other.tableAlignLeft.test(a) ? s.align.push("left") : s.align.push(null);
			for (let a = 0; a < n.length; a++) s.header.push({
				text: n[a],
				tokens: this.lexer.inline(n[a]),
				header: !0,
				align: s.align[a]
			});
			for (let a of i) s.rows.push(V(a, s.header.length).map((o, p) => ({
				text: o,
				tokens: this.lexer.inline(o),
				header: !1,
				align: s.align[p]
			})));
			return s;
		}
	}
	lheading(e) {
		let t = this.rules.block.lheading.exec(e);
		if (t) return {
			type: "heading",
			raw: t[0],
			depth: t[2].charAt(0) === "=" ? 1 : 2,
			text: t[1],
			tokens: this.lexer.inline(t[1])
		};
	}
	paragraph(e) {
		let t = this.rules.block.paragraph.exec(e);
		if (t) {
			let n = t[1].charAt(t[1].length - 1) === `
` ? t[1].slice(0, -1) : t[1];
			return {
				type: "paragraph",
				raw: t[0],
				text: n,
				tokens: this.lexer.inline(n)
			};
		}
	}
	text(e) {
		let t = this.rules.block.text.exec(e);
		if (t) return {
			type: "text",
			raw: t[0],
			text: t[0],
			tokens: this.lexer.inline(t[0])
		};
	}
	escape(e) {
		let t = this.rules.inline.escape.exec(e);
		if (t) return {
			type: "escape",
			raw: t[0],
			text: t[1]
		};
	}
	tag(e) {
		let t = this.rules.inline.tag.exec(e);
		if (t) return !this.lexer.state.inLink && this.rules.other.startATag.test(t[0]) ? this.lexer.state.inLink = !0 : this.lexer.state.inLink && this.rules.other.endATag.test(t[0]) && (this.lexer.state.inLink = !1), !this.lexer.state.inRawBlock && this.rules.other.startPreScriptTag.test(t[0]) ? this.lexer.state.inRawBlock = !0 : this.lexer.state.inRawBlock && this.rules.other.endPreScriptTag.test(t[0]) && (this.lexer.state.inRawBlock = !1), {
			type: "html",
			raw: t[0],
			inLink: this.lexer.state.inLink,
			inRawBlock: this.lexer.state.inRawBlock,
			block: !1,
			text: t[0]
		};
	}
	link(e) {
		let t = this.rules.inline.link.exec(e);
		if (t) {
			let n = t[2].trim();
			if (!this.options.pedantic && this.rules.other.startAngleBracket.test(n)) {
				if (!this.rules.other.endAngleBracket.test(n)) return;
				let s = z(n.slice(0, -1), "\\");
				if ((n.length - s.length) % 2 === 0) return;
			} else {
				let s = fe(t[2], "()");
				if (s === -2) return;
				if (s > -1) {
					let o = (t[0].indexOf("!") === 0 ? 5 : 4) + t[1].length + s;
					t[2] = t[2].substring(0, s), t[0] = t[0].substring(0, o).trim(), t[3] = "";
				}
			}
			let r = t[2], i = "";
			if (this.options.pedantic) {
				let s = this.rules.other.pedanticHrefTitle.exec(r);
				s && (r = s[1], i = s[3]);
			} else i = t[3] ? t[3].slice(1, -1) : "";
			return r = r.trim(), this.rules.other.startAngleBracket.test(r) && (this.options.pedantic && !this.rules.other.endAngleBracket.test(n) ? r = r.slice(1) : r = r.slice(1, -1)), me(t, {
				href: r && r.replace(this.rules.inline.anyPunctuation, "$1"),
				title: i && i.replace(this.rules.inline.anyPunctuation, "$1")
			}, t[0], this.lexer, this.rules);
		}
	}
	reflink(e, t) {
		let n;
		if ((n = this.rules.inline.reflink.exec(e)) || (n = this.rules.inline.nolink.exec(e))) {
			let i = t[(n[2] || n[1]).replace(this.rules.other.multipleSpaceGlobal, " ").toLowerCase()];
			if (!i) {
				let s = n[0].charAt(0);
				return {
					type: "text",
					raw: s,
					text: s
				};
			}
			return me(n, i, n[0], this.lexer, this.rules);
		}
	}
	emStrong(e, t, n = "") {
		let r = this.rules.inline.emStrongLDelim.exec(e);
		if (!r || r[3] && n.match(this.rules.other.unicodeAlphaNumeric)) return;
		if (!(r[1] || r[2] || "") || !n || this.rules.inline.punctuation.exec(n)) {
			let s = [...r[0]].length - 1, a, o, p = s, u = 0, c = r[0][0] === "*" ? this.rules.inline.emStrongRDelimAst : this.rules.inline.emStrongRDelimUnd;
			for (c.lastIndex = 0, t = t.slice(-1 * e.length + s); (r = c.exec(t)) != null;) {
				if (a = r[1] || r[2] || r[3] || r[4] || r[5] || r[6], !a) continue;
				if (o = [...a].length, r[3] || r[4]) {
					p += o;
					continue;
				} else if ((r[5] || r[6]) && s % 3 && !((s + o) % 3)) {
					u += o;
					continue;
				}
				if (p -= o, p > 0) continue;
				o = Math.min(o, o + p + u);
				let g = [...r[0]][0].length, h = e.slice(0, s + r.index + g + o);
				if (Math.min(s, o) % 2) {
					let f = h.slice(1, -1);
					return {
						type: "em",
						raw: h,
						text: f,
						tokens: this.lexer.inlineTokens(f)
					};
				}
				let R = h.slice(2, -2);
				return {
					type: "strong",
					raw: h,
					text: R,
					tokens: this.lexer.inlineTokens(R)
				};
			}
		}
	}
	codespan(e) {
		let t = this.rules.inline.code.exec(e);
		if (t) {
			let n = t[2].replace(this.rules.other.newLineCharGlobal, " "), r = this.rules.other.nonSpaceChar.test(n), i = this.rules.other.startingSpaceChar.test(n) && this.rules.other.endingSpaceChar.test(n);
			return r && i && (n = n.substring(1, n.length - 1)), {
				type: "codespan",
				raw: t[0],
				text: n
			};
		}
	}
	br(e) {
		let t = this.rules.inline.br.exec(e);
		if (t) return {
			type: "br",
			raw: t[0]
		};
	}
	del(e) {
		let t = this.rules.inline.del.exec(e);
		if (t) return {
			type: "del",
			raw: t[0],
			text: t[2],
			tokens: this.lexer.inlineTokens(t[2])
		};
	}
	autolink(e) {
		let t = this.rules.inline.autolink.exec(e);
		if (t) {
			let n, r;
			return t[2] === "@" ? (n = t[1], r = "mailto:" + n) : (n = t[1], r = n), {
				type: "link",
				raw: t[0],
				text: n,
				href: r,
				tokens: [{
					type: "text",
					raw: n,
					text: n
				}]
			};
		}
	}
	url(e) {
		let t;
		if (t = this.rules.inline.url.exec(e)) {
			let n, r;
			if (t[2] === "@") n = t[0], r = "mailto:" + n;
			else {
				let i;
				do
					i = t[0], t[0] = this.rules.inline._backpedal.exec(t[0])?.[0] ?? "";
				while (i !== t[0]);
				n = t[0], t[1] === "www." ? r = "http://" + t[0] : r = t[0];
			}
			return {
				type: "link",
				raw: t[0],
				text: n,
				href: r,
				tokens: [{
					type: "text",
					raw: n,
					text: n
				}]
			};
		}
	}
	inlineText(e) {
		let t = this.rules.inline.text.exec(e);
		if (t) {
			let n = this.lexer.state.inRawBlock;
			return {
				type: "text",
				raw: t[0],
				text: t[0],
				escaped: n
			};
		}
	}
};
var x = class l {
	tokens;
	options;
	state;
	tokenizer;
	inlineQueue;
	constructor(e) {
		this.tokens = [], this.tokens.links = Object.create(null), this.options = e || T, this.options.tokenizer = this.options.tokenizer || new y(), this.tokenizer = this.options.tokenizer, this.tokenizer.options = this.options, this.tokenizer.lexer = this, this.inlineQueue = [], this.state = {
			inLink: !1,
			inRawBlock: !1,
			top: !0
		};
		let t = {
			other: m,
			block: C.normal,
			inline: M.normal
		};
		this.options.pedantic ? (t.block = C.pedantic, t.inline = M.pedantic) : this.options.gfm && (t.block = C.gfm, this.options.breaks ? t.inline = M.breaks : t.inline = M.gfm), this.tokenizer.rules = t;
	}
	static get rules() {
		return {
			block: C,
			inline: M
		};
	}
	static lex(e, t) {
		return new l(t).lex(e);
	}
	static lexInline(e, t) {
		return new l(t).inlineTokens(e);
	}
	lex(e) {
		e = e.replace(m.carriageReturn, `
`), this.blockTokens(e, this.tokens);
		for (let t = 0; t < this.inlineQueue.length; t++) {
			let n = this.inlineQueue[t];
			this.inlineTokens(n.src, n.tokens);
		}
		return this.inlineQueue = [], this.tokens;
	}
	blockTokens(e, t = [], n = !1) {
		for (this.options.pedantic && (e = e.replace(m.tabCharGlobal, "    ").replace(m.spaceLine, "")); e;) {
			let r;
			if (this.options.extensions?.block?.some((s) => (r = s.call({ lexer: this }, e, t)) ? (e = e.substring(r.raw.length), t.push(r), !0) : !1)) continue;
			if (r = this.tokenizer.space(e)) {
				e = e.substring(r.raw.length);
				let s = t.at(-1);
				r.raw.length === 1 && s !== void 0 ? s.raw += `
` : t.push(r);
				continue;
			}
			if (r = this.tokenizer.code(e)) {
				e = e.substring(r.raw.length);
				let s = t.at(-1);
				s?.type === "paragraph" || s?.type === "text" ? (s.raw += (s.raw.endsWith(`
`) ? "" : `
`) + r.raw, s.text += `
` + r.text, this.inlineQueue.at(-1).src = s.text) : t.push(r);
				continue;
			}
			if (r = this.tokenizer.fences(e)) {
				e = e.substring(r.raw.length), t.push(r);
				continue;
			}
			if (r = this.tokenizer.heading(e)) {
				e = e.substring(r.raw.length), t.push(r);
				continue;
			}
			if (r = this.tokenizer.hr(e)) {
				e = e.substring(r.raw.length), t.push(r);
				continue;
			}
			if (r = this.tokenizer.blockquote(e)) {
				e = e.substring(r.raw.length), t.push(r);
				continue;
			}
			if (r = this.tokenizer.list(e)) {
				e = e.substring(r.raw.length), t.push(r);
				continue;
			}
			if (r = this.tokenizer.html(e)) {
				e = e.substring(r.raw.length), t.push(r);
				continue;
			}
			if (r = this.tokenizer.def(e)) {
				e = e.substring(r.raw.length);
				let s = t.at(-1);
				s?.type === "paragraph" || s?.type === "text" ? (s.raw += (s.raw.endsWith(`
`) ? "" : `
`) + r.raw, s.text += `
` + r.raw, this.inlineQueue.at(-1).src = s.text) : this.tokens.links[r.tag] || (this.tokens.links[r.tag] = {
					href: r.href,
					title: r.title
				}, t.push(r));
				continue;
			}
			if (r = this.tokenizer.table(e)) {
				e = e.substring(r.raw.length), t.push(r);
				continue;
			}
			if (r = this.tokenizer.lheading(e)) {
				e = e.substring(r.raw.length), t.push(r);
				continue;
			}
			let i = e;
			if (this.options.extensions?.startBlock) {
				let s = 1 / 0, a = e.slice(1), o;
				this.options.extensions.startBlock.forEach((p) => {
					o = p.call({ lexer: this }, a), typeof o == "number" && o >= 0 && (s = Math.min(s, o));
				}), s < 1 / 0 && s >= 0 && (i = e.substring(0, s + 1));
			}
			if (this.state.top && (r = this.tokenizer.paragraph(i))) {
				let s = t.at(-1);
				n && s?.type === "paragraph" ? (s.raw += (s.raw.endsWith(`
`) ? "" : `
`) + r.raw, s.text += `
` + r.text, this.inlineQueue.pop(), this.inlineQueue.at(-1).src = s.text) : t.push(r), n = i.length !== e.length, e = e.substring(r.raw.length);
				continue;
			}
			if (r = this.tokenizer.text(e)) {
				e = e.substring(r.raw.length);
				let s = t.at(-1);
				s?.type === "text" ? (s.raw += (s.raw.endsWith(`
`) ? "" : `
`) + r.raw, s.text += `
` + r.text, this.inlineQueue.pop(), this.inlineQueue.at(-1).src = s.text) : t.push(r);
				continue;
			}
			if (e) {
				let s = "Infinite loop on byte: " + e.charCodeAt(0);
				if (this.options.silent) {
					console.error(s);
					break;
				} else throw new Error(s);
			}
		}
		return this.state.top = !0, t;
	}
	inline(e, t = []) {
		return this.inlineQueue.push({
			src: e,
			tokens: t
		}), t;
	}
	inlineTokens(e, t = []) {
		let n = e, r = null;
		if (this.tokens.links) {
			let o = Object.keys(this.tokens.links);
			if (o.length > 0) for (; (r = this.tokenizer.rules.inline.reflinkSearch.exec(n)) != null;) o.includes(r[0].slice(r[0].lastIndexOf("[") + 1, -1)) && (n = n.slice(0, r.index) + "[" + "a".repeat(r[0].length - 2) + "]" + n.slice(this.tokenizer.rules.inline.reflinkSearch.lastIndex));
		}
		for (; (r = this.tokenizer.rules.inline.anyPunctuation.exec(n)) != null;) n = n.slice(0, r.index) + "++" + n.slice(this.tokenizer.rules.inline.anyPunctuation.lastIndex);
		let i;
		for (; (r = this.tokenizer.rules.inline.blockSkip.exec(n)) != null;) i = r[2] ? r[2].length : 0, n = n.slice(0, r.index + i) + "[" + "a".repeat(r[0].length - i - 2) + "]" + n.slice(this.tokenizer.rules.inline.blockSkip.lastIndex);
		n = this.options.hooks?.emStrongMask?.call({ lexer: this }, n) ?? n;
		let s = !1, a = "";
		for (; e;) {
			s || (a = ""), s = !1;
			let o;
			if (this.options.extensions?.inline?.some((u) => (o = u.call({ lexer: this }, e, t)) ? (e = e.substring(o.raw.length), t.push(o), !0) : !1)) continue;
			if (o = this.tokenizer.escape(e)) {
				e = e.substring(o.raw.length), t.push(o);
				continue;
			}
			if (o = this.tokenizer.tag(e)) {
				e = e.substring(o.raw.length), t.push(o);
				continue;
			}
			if (o = this.tokenizer.link(e)) {
				e = e.substring(o.raw.length), t.push(o);
				continue;
			}
			if (o = this.tokenizer.reflink(e, this.tokens.links)) {
				e = e.substring(o.raw.length);
				let u = t.at(-1);
				o.type === "text" && u?.type === "text" ? (u.raw += o.raw, u.text += o.text) : t.push(o);
				continue;
			}
			if (o = this.tokenizer.emStrong(e, n, a)) {
				e = e.substring(o.raw.length), t.push(o);
				continue;
			}
			if (o = this.tokenizer.codespan(e)) {
				e = e.substring(o.raw.length), t.push(o);
				continue;
			}
			if (o = this.tokenizer.br(e)) {
				e = e.substring(o.raw.length), t.push(o);
				continue;
			}
			if (o = this.tokenizer.del(e)) {
				e = e.substring(o.raw.length), t.push(o);
				continue;
			}
			if (o = this.tokenizer.autolink(e)) {
				e = e.substring(o.raw.length), t.push(o);
				continue;
			}
			if (!this.state.inLink && (o = this.tokenizer.url(e))) {
				e = e.substring(o.raw.length), t.push(o);
				continue;
			}
			let p = e;
			if (this.options.extensions?.startInline) {
				let u = 1 / 0, c = e.slice(1), g;
				this.options.extensions.startInline.forEach((h) => {
					g = h.call({ lexer: this }, c), typeof g == "number" && g >= 0 && (u = Math.min(u, g));
				}), u < 1 / 0 && u >= 0 && (p = e.substring(0, u + 1));
			}
			if (o = this.tokenizer.inlineText(p)) {
				e = e.substring(o.raw.length), o.raw.slice(-1) !== "_" && (a = o.raw.slice(-1)), s = !0;
				let u = t.at(-1);
				u?.type === "text" ? (u.raw += o.raw, u.text += o.text) : t.push(o);
				continue;
			}
			if (e) {
				let u = "Infinite loop on byte: " + e.charCodeAt(0);
				if (this.options.silent) {
					console.error(u);
					break;
				} else throw new Error(u);
			}
		}
		return t;
	}
};
var P = class {
	options;
	parser;
	constructor(e) {
		this.options = e || T;
	}
	space(e) {
		return "";
	}
	code({ text: e, lang: t, escaped: n }) {
		let r = (t || "").match(m.notSpaceStart)?.[0], i = e.replace(m.endingNewline, "") + `
`;
		return r ? "<pre><code class=\"language-" + w(r) + "\">" + (n ? i : w(i, !0)) + `</code></pre>
` : "<pre><code>" + (n ? i : w(i, !0)) + `</code></pre>
`;
	}
	blockquote({ tokens: e }) {
		return `<blockquote>
${this.parser.parse(e)}</blockquote>
`;
	}
	html({ text: e }) {
		return e;
	}
	def(e) {
		return "";
	}
	heading({ tokens: e, depth: t }) {
		return `<h${t}>${this.parser.parseInline(e)}</h${t}>
`;
	}
	hr(e) {
		return `<hr>
`;
	}
	list(e) {
		let t = e.ordered, n = e.start, r = "";
		for (let a = 0; a < e.items.length; a++) {
			let o = e.items[a];
			r += this.listitem(o);
		}
		let i = t ? "ol" : "ul", s = t && n !== 1 ? " start=\"" + n + "\"" : "";
		return "<" + i + s + `>
` + r + "</" + i + `>
`;
	}
	listitem(e) {
		let t = "";
		if (e.task) {
			let n = this.checkbox({ checked: !!e.checked });
			e.loose ? e.tokens[0]?.type === "paragraph" ? (e.tokens[0].text = n + " " + e.tokens[0].text, e.tokens[0].tokens && e.tokens[0].tokens.length > 0 && e.tokens[0].tokens[0].type === "text" && (e.tokens[0].tokens[0].text = n + " " + w(e.tokens[0].tokens[0].text), e.tokens[0].tokens[0].escaped = !0)) : e.tokens.unshift({
				type: "text",
				raw: n + " ",
				text: n + " ",
				escaped: !0
			}) : t += n + " ";
		}
		return t += this.parser.parse(e.tokens, !!e.loose), `<li>${t}</li>
`;
	}
	checkbox({ checked: e }) {
		return "<input " + (e ? "checked=\"\" " : "") + "disabled=\"\" type=\"checkbox\">";
	}
	paragraph({ tokens: e }) {
		return `<p>${this.parser.parseInline(e)}</p>
`;
	}
	table(e) {
		let t = "", n = "";
		for (let i = 0; i < e.header.length; i++) n += this.tablecell(e.header[i]);
		t += this.tablerow({ text: n });
		let r = "";
		for (let i = 0; i < e.rows.length; i++) {
			let s = e.rows[i];
			n = "";
			for (let a = 0; a < s.length; a++) n += this.tablecell(s[a]);
			r += this.tablerow({ text: n });
		}
		return r && (r = `<tbody>${r}</tbody>`), `<table>
<thead>
` + t + `</thead>
` + r + `</table>
`;
	}
	tablerow({ text: e }) {
		return `<tr>
${e}</tr>
`;
	}
	tablecell(e) {
		let t = this.parser.parseInline(e.tokens), n = e.header ? "th" : "td";
		return (e.align ? `<${n} align="${e.align}">` : `<${n}>`) + t + `</${n}>
`;
	}
	strong({ tokens: e }) {
		return `<strong>${this.parser.parseInline(e)}</strong>`;
	}
	em({ tokens: e }) {
		return `<em>${this.parser.parseInline(e)}</em>`;
	}
	codespan({ text: e }) {
		return `<code>${w(e, !0)}</code>`;
	}
	br(e) {
		return "<br>";
	}
	del({ tokens: e }) {
		return `<del>${this.parser.parseInline(e)}</del>`;
	}
	link({ href: e, title: t, tokens: n }) {
		let r = this.parser.parseInline(n), i = J(e);
		if (i === null) return r;
		e = i;
		let s = "<a href=\"" + e + "\"";
		return t && (s += " title=\"" + w(t) + "\""), s += ">" + r + "</a>", s;
	}
	image({ href: e, title: t, text: n, tokens: r }) {
		r && (n = this.parser.parseInline(r, this.parser.textRenderer));
		let i = J(e);
		if (i === null) return w(n);
		e = i;
		let s = `<img src="${e}" alt="${n}"`;
		return t && (s += ` title="${w(t)}"`), s += ">", s;
	}
	text(e) {
		return "tokens" in e && e.tokens ? this.parser.parseInline(e.tokens) : "escaped" in e && e.escaped ? e.text : w(e.text);
	}
};
var $ = class {
	strong({ text: e }) {
		return e;
	}
	em({ text: e }) {
		return e;
	}
	codespan({ text: e }) {
		return e;
	}
	del({ text: e }) {
		return e;
	}
	html({ text: e }) {
		return e;
	}
	text({ text: e }) {
		return e;
	}
	link({ text: e }) {
		return "" + e;
	}
	image({ text: e }) {
		return "" + e;
	}
	br() {
		return "";
	}
};
var b = class l {
	options;
	renderer;
	textRenderer;
	constructor(e) {
		this.options = e || T, this.options.renderer = this.options.renderer || new P(), this.renderer = this.options.renderer, this.renderer.options = this.options, this.renderer.parser = this, this.textRenderer = new $();
	}
	static parse(e, t) {
		return new l(t).parse(e);
	}
	static parseInline(e, t) {
		return new l(t).parseInline(e);
	}
	parse(e, t = !0) {
		let n = "";
		for (let r = 0; r < e.length; r++) {
			let i = e[r];
			if (this.options.extensions?.renderers?.[i.type]) {
				let a = i, o = this.options.extensions.renderers[a.type].call({ parser: this }, a);
				if (o !== !1 || ![
					"space",
					"hr",
					"heading",
					"code",
					"table",
					"blockquote",
					"list",
					"html",
					"def",
					"paragraph",
					"text"
				].includes(a.type)) {
					n += o || "";
					continue;
				}
			}
			let s = i;
			switch (s.type) {
				case "space":
					n += this.renderer.space(s);
					continue;
				case "hr":
					n += this.renderer.hr(s);
					continue;
				case "heading":
					n += this.renderer.heading(s);
					continue;
				case "code":
					n += this.renderer.code(s);
					continue;
				case "table":
					n += this.renderer.table(s);
					continue;
				case "blockquote":
					n += this.renderer.blockquote(s);
					continue;
				case "list":
					n += this.renderer.list(s);
					continue;
				case "html":
					n += this.renderer.html(s);
					continue;
				case "def":
					n += this.renderer.def(s);
					continue;
				case "paragraph":
					n += this.renderer.paragraph(s);
					continue;
				case "text": {
					let a = s, o = this.renderer.text(a);
					for (; r + 1 < e.length && e[r + 1].type === "text";) a = e[++r], o += `
` + this.renderer.text(a);
					t ? n += this.renderer.paragraph({
						type: "paragraph",
						raw: o,
						text: o,
						tokens: [{
							type: "text",
							raw: o,
							text: o,
							escaped: !0
						}]
					}) : n += o;
					continue;
				}
				default: {
					let a = "Token with \"" + s.type + "\" type was not found.";
					if (this.options.silent) return console.error(a), "";
					throw new Error(a);
				}
			}
		}
		return n;
	}
	parseInline(e, t = this.renderer) {
		let n = "";
		for (let r = 0; r < e.length; r++) {
			let i = e[r];
			if (this.options.extensions?.renderers?.[i.type]) {
				let a = this.options.extensions.renderers[i.type].call({ parser: this }, i);
				if (a !== !1 || ![
					"escape",
					"html",
					"link",
					"image",
					"strong",
					"em",
					"codespan",
					"br",
					"del",
					"text"
				].includes(i.type)) {
					n += a || "";
					continue;
				}
			}
			let s = i;
			switch (s.type) {
				case "escape":
					n += t.text(s);
					break;
				case "html":
					n += t.html(s);
					break;
				case "link":
					n += t.link(s);
					break;
				case "image":
					n += t.image(s);
					break;
				case "strong":
					n += t.strong(s);
					break;
				case "em":
					n += t.em(s);
					break;
				case "codespan":
					n += t.codespan(s);
					break;
				case "br":
					n += t.br(s);
					break;
				case "del":
					n += t.del(s);
					break;
				case "text":
					n += t.text(s);
					break;
				default: {
					let a = "Token with \"" + s.type + "\" type was not found.";
					if (this.options.silent) return console.error(a), "";
					throw new Error(a);
				}
			}
		}
		return n;
	}
};
var S = class {
	options;
	block;
	constructor(e) {
		this.options = e || T;
	}
	static passThroughHooks = /* @__PURE__ */ new Set([
		"preprocess",
		"postprocess",
		"processAllTokens",
		"emStrongMask"
	]);
	static passThroughHooksRespectAsync = /* @__PURE__ */ new Set([
		"preprocess",
		"postprocess",
		"processAllTokens"
	]);
	preprocess(e) {
		return e;
	}
	postprocess(e) {
		return e;
	}
	processAllTokens(e) {
		return e;
	}
	emStrongMask(e) {
		return e;
	}
	provideLexer() {
		return this.block ? x.lex : x.lexInline;
	}
	provideParser() {
		return this.block ? b.parse : b.parseInline;
	}
};
var B = class {
	defaults = L();
	options = this.setOptions;
	parse = this.parseMarkdown(!0);
	parseInline = this.parseMarkdown(!1);
	Parser = b;
	Renderer = P;
	TextRenderer = $;
	Lexer = x;
	Tokenizer = y;
	Hooks = S;
	constructor(...e) {
		this.use(...e);
	}
	walkTokens(e, t) {
		let n = [];
		for (let r of e) switch (n = n.concat(t.call(this, r)), r.type) {
			case "table": {
				let i = r;
				for (let s of i.header) n = n.concat(this.walkTokens(s.tokens, t));
				for (let s of i.rows) for (let a of s) n = n.concat(this.walkTokens(a.tokens, t));
				break;
			}
			case "list": {
				let i = r;
				n = n.concat(this.walkTokens(i.items, t));
				break;
			}
			default: {
				let i = r;
				this.defaults.extensions?.childTokens?.[i.type] ? this.defaults.extensions.childTokens[i.type].forEach((s) => {
					let a = i[s].flat(1 / 0);
					n = n.concat(this.walkTokens(a, t));
				}) : i.tokens && (n = n.concat(this.walkTokens(i.tokens, t)));
			}
		}
		return n;
	}
	use(...e) {
		let t = this.defaults.extensions || {
			renderers: {},
			childTokens: {}
		};
		return e.forEach((n) => {
			let r = { ...n };
			if (r.async = this.defaults.async || r.async || !1, n.extensions && (n.extensions.forEach((i) => {
				if (!i.name) throw new Error("extension name required");
				if ("renderer" in i) {
					let s = t.renderers[i.name];
					s ? t.renderers[i.name] = function(...a) {
						let o = i.renderer.apply(this, a);
						return o === !1 && (o = s.apply(this, a)), o;
					} : t.renderers[i.name] = i.renderer;
				}
				if ("tokenizer" in i) {
					if (!i.level || i.level !== "block" && i.level !== "inline") throw new Error("extension level must be 'block' or 'inline'");
					let s = t[i.level];
					s ? s.unshift(i.tokenizer) : t[i.level] = [i.tokenizer], i.start && (i.level === "block" ? t.startBlock ? t.startBlock.push(i.start) : t.startBlock = [i.start] : i.level === "inline" && (t.startInline ? t.startInline.push(i.start) : t.startInline = [i.start]));
				}
				"childTokens" in i && i.childTokens && (t.childTokens[i.name] = i.childTokens);
			}), r.extensions = t), n.renderer) {
				let i = this.defaults.renderer || new P(this.defaults);
				for (let s in n.renderer) {
					if (!(s in i)) throw new Error(`renderer '${s}' does not exist`);
					if (["options", "parser"].includes(s)) continue;
					let a = s, o = n.renderer[a], p = i[a];
					i[a] = (...u) => {
						let c = o.apply(i, u);
						return c === !1 && (c = p.apply(i, u)), c || "";
					};
				}
				r.renderer = i;
			}
			if (n.tokenizer) {
				let i = this.defaults.tokenizer || new y(this.defaults);
				for (let s in n.tokenizer) {
					if (!(s in i)) throw new Error(`tokenizer '${s}' does not exist`);
					if ([
						"options",
						"rules",
						"lexer"
					].includes(s)) continue;
					let a = s, o = n.tokenizer[a], p = i[a];
					i[a] = (...u) => {
						let c = o.apply(i, u);
						return c === !1 && (c = p.apply(i, u)), c;
					};
				}
				r.tokenizer = i;
			}
			if (n.hooks) {
				let i = this.defaults.hooks || new S();
				for (let s in n.hooks) {
					if (!(s in i)) throw new Error(`hook '${s}' does not exist`);
					if (["options", "block"].includes(s)) continue;
					let a = s, o = n.hooks[a], p = i[a];
					S.passThroughHooks.has(s) ? i[a] = (u) => {
						if (this.defaults.async && S.passThroughHooksRespectAsync.has(s)) return (async () => {
							let g = await o.call(i, u);
							return p.call(i, g);
						})();
						let c = o.call(i, u);
						return p.call(i, c);
					} : i[a] = (...u) => {
						if (this.defaults.async) return (async () => {
							let g = await o.apply(i, u);
							return g === !1 && (g = await p.apply(i, u)), g;
						})();
						let c = o.apply(i, u);
						return c === !1 && (c = p.apply(i, u)), c;
					};
				}
				r.hooks = i;
			}
			if (n.walkTokens) {
				let i = this.defaults.walkTokens, s = n.walkTokens;
				r.walkTokens = function(a) {
					let o = [];
					return o.push(s.call(this, a)), i && (o = o.concat(i.call(this, a))), o;
				};
			}
			this.defaults = {
				...this.defaults,
				...r
			};
		}), this;
	}
	setOptions(e) {
		return this.defaults = {
			...this.defaults,
			...e
		}, this;
	}
	lexer(e, t) {
		return x.lex(e, t ?? this.defaults);
	}
	parser(e, t) {
		return b.parse(e, t ?? this.defaults);
	}
	parseMarkdown(e) {
		return (n, r) => {
			let i = { ...r }, s = {
				...this.defaults,
				...i
			}, a = this.onError(!!s.silent, !!s.async);
			if (this.defaults.async === !0 && i.async === !1) return a(/* @__PURE__ */ new Error("marked(): The async option was set to true by an extension. Remove async: false from the parse options object to return a Promise."));
			if (typeof n > "u" || n === null) return a(/* @__PURE__ */ new Error("marked(): input parameter is undefined or null"));
			if (typeof n != "string") return a(/* @__PURE__ */ new Error("marked(): input parameter is of type " + Object.prototype.toString.call(n) + ", string expected"));
			if (s.hooks && (s.hooks.options = s, s.hooks.block = e), s.async) return (async () => {
				let o = s.hooks ? await s.hooks.preprocess(n) : n, u = await (s.hooks ? await s.hooks.provideLexer() : e ? x.lex : x.lexInline)(o, s), c = s.hooks ? await s.hooks.processAllTokens(u) : u;
				s.walkTokens && await Promise.all(this.walkTokens(c, s.walkTokens));
				let h = await (s.hooks ? await s.hooks.provideParser() : e ? b.parse : b.parseInline)(c, s);
				return s.hooks ? await s.hooks.postprocess(h) : h;
			})().catch(a);
			try {
				s.hooks && (n = s.hooks.preprocess(n));
				let p = (s.hooks ? s.hooks.provideLexer() : e ? x.lex : x.lexInline)(n, s);
				s.hooks && (p = s.hooks.processAllTokens(p)), s.walkTokens && this.walkTokens(p, s.walkTokens);
				let c = (s.hooks ? s.hooks.provideParser() : e ? b.parse : b.parseInline)(p, s);
				return s.hooks && (c = s.hooks.postprocess(c)), c;
			} catch (o) {
				return a(o);
			}
		};
	}
	onError(e, t) {
		return (n) => {
			if (n.message += `
Please report this to https://github.com/markedjs/marked.`, e) {
				let r = "<p>An error occurred:</p><pre>" + w(n.message + "", !0) + "</pre>";
				return t ? Promise.resolve(r) : r;
			}
			if (t) return Promise.reject(n);
			throw n;
		};
	}
};
var _ = new B();
function k(l, e) {
	return _.parse(l, e);
}
k.options = k.setOptions = function(l) {
	return _.setOptions(l), k.defaults = _.defaults, G(k.defaults), k;
};
k.getDefaults = L;
k.defaults = T;
k.use = function(...l) {
	return _.use(...l), k.defaults = _.defaults, G(k.defaults), k;
};
k.walkTokens = function(l, e) {
	return _.walkTokens(l, e);
};
k.parseInline = _.parseInline;
k.Parser = b;
k.parser = b.parse;
k.Renderer = P;
k.TextRenderer = $;
k.Lexer = x;
k.lexer = x.lex;
k.Tokenizer = y;
k.Hooks = S;
k.parse = k;
k.options;
k.setOptions;
k.use;
k.walkTokens;
k.parseInline;
b.parse;
x.lex;
//#endregion
//#region src/ui/resultFormatting.ts
function turnStatus(status) {
	switch (status) {
		case "prepared": return "Reply saved locally · not sent";
		case "dispatching": return "Sending · confirmation pending";
		case "outcome_unknown": return "Send outcome unknown · no automatic retry";
		case "accepted": return "Awaiting captured response";
		case "generating": return "Response is generating";
		case "interrupted": return "Response capture interrupted";
		case "unavailable": return "Response unavailable";
		case "queued": return "Waiting for job dispatch";
		case "completed": return "Completed";
	}
}
var dateOptions = {
	timeZone: "Pacific/Auckland",
	day: "numeric",
	month: "short",
	year: "numeric"
};
function dateGroup(epoch) {
	return new Intl.DateTimeFormat("en-NZ", dateOptions).format(epoch * 1e3);
}
function nzTime(epoch) {
	if (epoch <= 0) return "Time unavailable";
	return new Intl.DateTimeFormat("en-NZ", {
		...dateOptions,
		hour: "numeric",
		minute: "2-digit",
		hour12: true
	}).format(epoch * 1e3);
}
function statusLabel(status) {
	switch (status) {
		case "queued": return "Queued";
		case "accepted": return "Accepted";
		case "generating": return "Generating";
		case "completed": return "Completed";
		case "interrupted": return "Interrupted";
		case "unavailable": return "Unavailable";
	}
}
function safeHref(href) {
	try {
		const url = new URL(href);
		return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
	} catch {
		return null;
	}
}
function plainPreview(text) {
	return text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").replace(/```[^\n]*\n?/g, " ").replace(/^[#>]+\s*/gm, "").replace(/\*\*|__|~~|[`*_]/g, "").replace(/\s+/g, " ").trim();
}
function groupRuns(items) {
	const groups = [];
	for (const item of items) {
		const date = dateGroup(item.updated_at || item.created_at);
		const last = groups[groups.length - 1];
		if (last?.date === date) last.items.push(item);
		else groups.push({
			date,
			items: [item]
		});
	}
	return groups;
}
//#endregion
//#region src/ui/ResultMarkdown.svelte
var root$2 = /* @__PURE__ */ from_html(`<strong><!></strong>`);
var root_1$2 = /* @__PURE__ */ from_html(`<em><!></em>`);
var root_2$1 = /* @__PURE__ */ from_html(`<del><!></del>`);
var root_3$1 = /* @__PURE__ */ from_html(`<code> </code>`);
var root_4$1 = /* @__PURE__ */ from_html(`<a target="_blank" rel="noopener noreferrer"><!></a>`);
var root_5$1 = /* @__PURE__ */ from_html(`<br/>`);
var root_6$1 = /* @__PURE__ */ from_html(`<h1><!></h1>`);
var root_7$1 = /* @__PURE__ */ from_html(`<h2><!></h2>`);
var root_8$1 = /* @__PURE__ */ from_html(`<h3><!></h3>`);
var root_9$1 = /* @__PURE__ */ from_html(`<p><!></p>`);
var root_10$1 = /* @__PURE__ */ from_html(`<div class="code-snippet"><div class="code-toolbar"><span> </span><button type="button" aria-label="Copy code"> </button></div> <pre><code> </code></pre></div>`);
var root_11$1 = /* @__PURE__ */ from_html(`<li><!></li>`);
var root_12$1 = /* @__PURE__ */ from_html(`<ol></ol>`);
var root_13$1 = /* @__PURE__ */ from_html(`<ul></ul>`);
var root_14$1 = /* @__PURE__ */ from_html(`<blockquote><!></blockquote>`);
var root_15$1 = /* @__PURE__ */ from_html(`<th><!></th>`);
var root_16$1 = /* @__PURE__ */ from_html(`<td><!></td>`);
var root_17$1 = /* @__PURE__ */ from_html(`<tr></tr>`);
var root_18$1 = /* @__PURE__ */ from_html(`<div class="result-table-scroll"><table><thead><tr></tr></thead><tbody></tbody></table></div>`);
var root_19$1 = /* @__PURE__ */ from_html(`<hr/>`);
var root_20$1 = /* @__PURE__ */ from_html(`<p> </p>`);
var root_21$1 = /* @__PURE__ */ from_html(`<div class="result-markdown"><!></div>`);
function ResultMarkdown($$anchor, $$props) {
	push($$props, true);
	const inline = ($$anchor, items = noop) => {
		var fragment = comment();
		each(first_child(fragment), 17, items, index, ($$anchor, token) => {
			var fragment_1 = comment();
			var node_1 = first_child(fragment_1);
			var consequent_1 = ($$anchor) => {
				var fragment_2 = comment();
				var node_2 = first_child(fragment_2);
				var consequent = ($$anchor) => {
					{
						let $0 = /* @__PURE__ */ user_derived(() => children(get(token)));
						inline($$anchor, () => get($0));
					}
				};
				var d = /* @__PURE__ */ user_derived(() => children(get(token)).length);
				var alternate = ($$anchor) => {
					var text_1 = text();
					template_effect(() => set_text(text_1, get(token).text));
					append($$anchor, text_1);
				};
				if_block(node_2, ($$render) => {
					if (get(d)) $$render(consequent);
					else $$render(alternate, -1);
				});
				append($$anchor, fragment_2);
			};
			var consequent_2 = ($$anchor) => {
				var strong = root$2();
				var node_3 = child(strong);
				{
					let $0 = /* @__PURE__ */ user_derived(() => children(get(token)));
					inline(node_3, () => get($0));
				}
				reset(strong);
				append($$anchor, strong);
			};
			var consequent_3 = ($$anchor) => {
				var em = root_1$2();
				var node_4 = child(em);
				{
					let $0 = /* @__PURE__ */ user_derived(() => children(get(token)));
					inline(node_4, () => get($0));
				}
				reset(em);
				append($$anchor, em);
			};
			var consequent_4 = ($$anchor) => {
				var del = root_2$1();
				var node_5 = child(del);
				{
					let $0 = /* @__PURE__ */ user_derived(() => children(get(token)));
					inline(node_5, () => get($0));
				}
				reset(del);
				append($$anchor, del);
			};
			var consequent_5 = ($$anchor) => {
				var code = root_3$1();
				var text_2 = only_child(code, true);
				template_effect(() => set_text(text_2, get(token).text));
				append($$anchor, code);
			};
			var consequent_7 = ($$anchor) => {
				var fragment_5 = comment();
				var node_6 = first_child(fragment_5);
				var consequent_6 = ($$anchor) => {
					var a = root_4$1();
					var node_7 = child(a);
					{
						let $0 = /* @__PURE__ */ user_derived(() => children(get(token)));
						inline(node_7, () => get($0));
					}
					reset(a);
					template_effect(($0) => set_attribute(a, "href", $0), [() => safeHref(get(token).href) ?? void 0]);
					append($$anchor, a);
				};
				var d_1 = /* @__PURE__ */ user_derived(() => safeHref(get(token).href));
				var alternate_1 = ($$anchor) => {
					{
						let $0 = /* @__PURE__ */ user_derived(() => children(get(token)));
						inline($$anchor, () => get($0));
					}
				};
				if_block(node_6, ($$render) => {
					if (get(d_1)) $$render(consequent_6);
					else $$render(alternate_1, -1);
				});
				append($$anchor, fragment_5);
			};
			var consequent_8 = ($$anchor) => {
				append($$anchor, root_5$1());
			};
			var consequent_9 = ($$anchor) => {
				var text_3 = text();
				template_effect(() => set_text(text_3, get(token).type === "image" ? get(token).text : get(token).text));
				append($$anchor, text_3);
			};
			if_block(node_1, ($$render) => {
				if (get(token).type === "text") $$render(consequent_1);
				else if (get(token).type === "strong") $$render(consequent_2, 1);
				else if (get(token).type === "em") $$render(consequent_3, 2);
				else if (get(token).type === "del") $$render(consequent_4, 3);
				else if (get(token).type === "codespan") $$render(consequent_5, 4);
				else if (get(token).type === "link") $$render(consequent_7, 5);
				else if (get(token).type === "br") $$render(consequent_8, 6);
				else if (get(token).type === "escape" || get(token).type === "html" || get(token).type === "image") $$render(consequent_9, 7);
			});
			append($$anchor, fragment_1);
		});
		append($$anchor, fragment);
	};
	const blocks = ($$anchor, items = noop) => {
		var fragment_8 = comment();
		each(first_child(fragment_8), 17, items, index, ($$anchor, token) => {
			var fragment_9 = comment();
			var node_9 = first_child(fragment_9);
			var consequent_12 = ($$anchor) => {
				var fragment_10 = comment();
				var node_10 = first_child(fragment_10);
				var consequent_10 = ($$anchor) => {
					var h1 = root_6$1();
					var node_11 = child(h1);
					{
						let $0 = /* @__PURE__ */ user_derived(() => children(get(token)));
						inline(node_11, () => get($0));
					}
					reset(h1);
					append($$anchor, h1);
				};
				var consequent_11 = ($$anchor) => {
					var h2 = root_7$1();
					var node_12 = child(h2);
					{
						let $0 = /* @__PURE__ */ user_derived(() => children(get(token)));
						inline(node_12, () => get($0));
					}
					reset(h2);
					append($$anchor, h2);
				};
				var alternate_2 = ($$anchor) => {
					var h3 = root_8$1();
					var node_13 = child(h3);
					{
						let $0 = /* @__PURE__ */ user_derived(() => children(get(token)));
						inline(node_13, () => get($0));
					}
					reset(h3);
					append($$anchor, h3);
				};
				if_block(node_10, ($$render) => {
					if (get(token).depth === 1) $$render(consequent_10);
					else if (get(token).depth === 2) $$render(consequent_11, 1);
					else $$render(alternate_2, -1);
				});
				append($$anchor, fragment_10);
			};
			var consequent_13 = ($$anchor) => {
				var p = root_9$1();
				var node_14 = child(p);
				{
					let $0 = /* @__PURE__ */ user_derived(() => children(get(token)).length ? children(get(token)) : [get(token)]);
					inline(node_14, () => get($0));
				}
				reset(p);
				append($$anchor, p);
			};
			var consequent_14 = ($$anchor) => {
				var div = root_10$1();
				var div_1 = child(div);
				var span = child(div_1);
				var text_4 = only_child(span, true);
				var button = sibling(span);
				var text_5 = only_child(button, true);
				reset(div_1);
				var pre = sibling(div_1, 2);
				var code_1 = child(pre);
				var text_6 = only_child(code_1, true);
				reset(pre);
				reset(div);
				template_effect(($0) => {
					set_text(text_4, get(token).lang || "Code");
					set_text(text_5, get(copiedCode) === get(token).text ? "Copied" : "Copy code");
					set_class(code_1, 1, $0);
					set_text(text_6, get(token).text);
				}, [() => clsx(get(token).lang ? "language-" + get(token).lang.split(/\s+/)[0] : "")]);
				delegated("click", button, () => copyCode(get(token).text));
				append($$anchor, div);
			};
			var consequent_16 = ($$anchor) => {
				var fragment_11 = comment();
				var node_15 = first_child(fragment_11);
				var consequent_15 = ($$anchor) => {
					var ol = root_12$1();
					each(ol, 21, () => get(token).items, index, ($$anchor, item) => {
						var li = root_11$1();
						var node_16 = child(li);
						blocks(node_16, () => get(item).tokens);
						reset(li);
						append($$anchor, li);
					});
					reset(ol);
					template_effect(() => set_attribute(ol, "start", get(token).start || 1));
					append($$anchor, ol);
				};
				var alternate_3 = ($$anchor) => {
					var ul = root_13$1();
					each(ul, 21, () => get(token).items, index, ($$anchor, item) => {
						var li_1 = root_11$1();
						var node_17 = child(li_1);
						blocks(node_17, () => get(item).tokens);
						reset(li_1);
						append($$anchor, li_1);
					});
					reset(ul);
					append($$anchor, ul);
				};
				if_block(node_15, ($$render) => {
					if (get(token).ordered) $$render(consequent_15);
					else $$render(alternate_3, -1);
				});
				append($$anchor, fragment_11);
			};
			var consequent_17 = ($$anchor) => {
				var blockquote = root_14$1();
				var node_18 = child(blockquote);
				blocks(node_18, () => get(token).tokens ?? []);
				reset(blockquote);
				append($$anchor, blockquote);
			};
			var consequent_18 = ($$anchor) => {
				var div_2 = root_18$1();
				var table = child(div_2);
				var thead = child(table);
				var tr = child(thead);
				each(tr, 21, () => get(token).header, index, ($$anchor, cell) => {
					var th = root_15$1();
					var node_19 = child(th);
					inline(node_19, () => get(cell).tokens);
					reset(th);
					append($$anchor, th);
				});
				reset(tr);
				reset(thead);
				var tbody = sibling(thead);
				each(tbody, 21, () => get(token).rows, index, ($$anchor, row) => {
					var tr_1 = root_17$1();
					each(tr_1, 21, () => get(row), index, ($$anchor, cell) => {
						var td = root_16$1();
						var node_20 = child(td);
						inline(node_20, () => get(cell).tokens);
						reset(td);
						append($$anchor, td);
					});
					reset(tr_1);
					append($$anchor, tr_1);
				});
				reset(tbody);
				reset(table);
				reset(div_2);
				append($$anchor, div_2);
			};
			var consequent_19 = ($$anchor) => {
				append($$anchor, root_19$1());
			};
			var consequent_20 = ($$anchor) => {
				var p_1 = root_20$1();
				var text_7 = only_child(p_1, true);
				template_effect(() => set_text(text_7, get(token).text));
				append($$anchor, p_1);
			};
			if_block(node_9, ($$render) => {
				if (get(token).type === "heading") $$render(consequent_12);
				else if (get(token).type === "paragraph" || get(token).type === "text") $$render(consequent_13, 1);
				else if (get(token).type === "code") $$render(consequent_14, 2);
				else if (get(token).type === "list") $$render(consequent_16, 3);
				else if (get(token).type === "blockquote") $$render(consequent_17, 4);
				else if (get(token).type === "table") $$render(consequent_18, 5);
				else if (get(token).type === "hr") $$render(consequent_19, 6);
				else if (get(token).type === "html") $$render(consequent_20, 7);
			});
			append($$anchor, fragment_9);
		});
		append($$anchor, fragment_8);
	};
	let tokens = /* @__PURE__ */ user_derived(() => k.lexer($$props.source, {
		gfm: true,
		breaks: false
	}));
	let copiedCode = /* @__PURE__ */ state("");
	async function copyCode(text) {
		try {
			await navigator.clipboard.writeText(text);
			set(copiedCode, text, true);
		} catch {
			set(copiedCode, "");
		}
	}
	function children(token) {
		return "tokens" in token && Array.isArray(token.tokens) ? token.tokens : [];
	}
	var div_3 = root_21$1();
	blocks(child(div_3), () => get(tokens));
	reset(div_3);
	append($$anchor, div_3);
	pop();
}
delegate(["click"]);
//#endregion
//#region src/ui/ChatsPage.svelte
var root$1 = /* @__PURE__ */ from_html(`<span class="unread-indicator" title="Unread activity"><span class="sr-only">Unread</span></span>`);
var root_1$1 = /* @__PURE__ */ from_html(`<span class="chat-job"> </span>`);
var root_2 = /* @__PURE__ */ from_html(`<div><button type="button" class="chat-row"><span class="chat-row-top"><!> <strong> </strong> <small> </small></span> <span class="chat-row-meta"><span></span> <!></span> <span class="chat-preview"> </span></button> <button type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6ZM12 14v7"></path></svg></button></div>`);
var root_3 = /* @__PURE__ */ from_html(`<button type="button" class="drawer-backdrop" aria-label="Close chat sidebar"></button>`);
var root_4 = /* @__PURE__ */ from_html(`<option> </option>`);
var root_5 = /* @__PURE__ */ from_html(`<div class="result-error" role="alert"> </div>`);
var root_6 = /* @__PURE__ */ from_html(`<div class="chats-date">Pinned</div> <!>`, 1);
var root_7 = /* @__PURE__ */ from_html(`<p class="chats-empty">Loading local results…</p>`);
var root_8 = /* @__PURE__ */ from_html(`<p class="chats-empty"> </p>`);
var root_9 = /* @__PURE__ */ from_html(`<div class="chats-date"> </div> <!>`, 1);
var root_10 = /* @__PURE__ */ from_html(`<div class="jobs-workspace"><!></div>`);
var root_11 = /* @__PURE__ */ from_html(`<div class="new-chat-empty"><div class="empty-icon">✦</div><h2>Start a fresh chat</h2></div> <!>`, 1);
var root_12 = /* @__PURE__ */ from_html(`<div class="chats-detail-empty"><div class="empty-icon">✦</div><h2>What would you like to revisit?</h2><p>Select a locally captured run from the sidebar, or start a fresh chat.</p><button class="sidebar-primary">New chat</button></div>`);
var root_13 = /* @__PURE__ */ from_html(`<span> </span>`);
var root_14 = /* @__PURE__ */ from_html(`<p class="chats-empty">Loading run…</p>`);
var root_15 = /* @__PURE__ */ from_html(`<p class="result-error" role="alert"> </p>`);
var root_16 = /* @__PURE__ */ from_html(`<a target="_blank" rel="noopener noreferrer"><img loading="lazy"/></a>`);
var root_17 = /* @__PURE__ */ from_html(`<div class="chat-attachments" aria-label="Attached images"></div>`);
var root_18 = /* @__PURE__ */ from_html(`<span class="capture-live">· Capturing</span>`);
var root_19 = /* @__PURE__ */ from_html(`<button class="copy-message" type="button"> </button>`);
var root_20 = /* @__PURE__ */ from_html(`<p class="partial-note"> </p>`);
var root_21 = /* @__PURE__ */ from_html(`<!> <!>`, 1);
var root_22 = /* @__PURE__ */ from_html(`<p class="no-response"> </p>`);
var root_23 = /* @__PURE__ */ from_html(`<p class="capture-note"> </p>`);
var root_24 = /* @__PURE__ */ from_html(`<div class="message-group user-group"><div class="message-role">You <!></div> <div class="prompt-message"> </div> <!></div> <div class="message-group assistant-group"><div class="message-role"><span>Assistant <!></span> <!></div> <!> <!></div>`, 1);
var root_25 = /* @__PURE__ */ from_html(`<div class="chat-detail-content"><header class="chat-detail-title"><h2> </h2><p> </p></header> <!> <!></div>`);
var root_26 = /* @__PURE__ */ from_html(`<div class="chat-prepared-action"><span>Reply saved locally, not yet sent.</span> <button type="button">Send saved reply</button></div>`);
var root_27 = /* @__PURE__ */ from_html(`<div class="chat-reply-status"> </div>`);
var root_28 = /* @__PURE__ */ from_html(`<div class="chat-detail-toolbar"><button class="chat-detail-back">‹ <span>All chats</span></button> <!></div> <div class="chat-transcript-scroll"><!> <!> <!></div> <!>`, 1);
var root_29 = /* @__PURE__ */ from_html(`<section aria-label="Prompta local chats and jobs"><!> <aside class="chats-sidebar" aria-label="Local chat sidebar"><div class="sidebar-brand"><div><strong>Prompta</strong><span> </span></div> <button class="sidebar-close" type="button" aria-label="Close sidebar">×</button></div> <nav class="sidebar-actions" aria-label="Main navigation"><button class="sidebar-primary" type="button"><span aria-hidden="true">＋</span> New chat</button> <button type="button"><span aria-hidden="true">▤</span> Chats</button> <button type="button"><span aria-hidden="true">▦</span> Jobs</button></nav> <div class="chats-heading"><h2>Recent <span class="chats-count"> </span></h2> <button class="chats-refresh" type="button" aria-label="Refresh local results" title="Refresh local results">↻</button></div> <div class="chats-controls"><label class="search-label"><span class="sr-only">Search job results</span> <input type="search" placeholder="Search chats"/></label> <label><span class="sr-only">Filter results by state</span> <select></select></label></div> <!> <div class="chats-list"><!> <!></div> <div class="chats-pagination"><span> </span> <div><button>Previous</button><button>Next</button></div></div> <div class="sidebar-footnote">Local Prompta runs only</div></aside> <div class="chats-detail"><div class="workspace-header"><button class="sidebar-menu" type="button" aria-label="Open chat sidebar">☰</button> <strong> </strong> <span> </span></div> <!></div></section>`);
function ChatsPage($$anchor, $$props) {
	push($$props, true);
	const chatItem = ($$anchor, item = noop) => {
		var div = root_2();
		let classes;
		var button = child(div);
		var span = child(button);
		var node = child(span);
		var consequent = ($$anchor) => {
			append($$anchor, root$1());
		};
		var d = /* @__PURE__ */ user_derived(() => isUnread(item()));
		if_block(node, ($$render) => {
			if (get(d)) $$render(consequent);
		});
		var strong = sibling(node, 2);
		var text_1 = only_child(strong, true);
		var text_2 = only_child(sibling(strong, 2), true);
		reset(span);
		var span_2 = sibling(span, 2);
		var span_3 = child(span_2);
		var text_3 = sibling(span_3, 1, true);
		var node_1 = sibling(text_3);
		var consequent_1 = ($$anchor) => {
			var span_4 = root_1$1();
			var text_4 = only_child(span_4, true);
			template_effect(() => set_text(text_4, item().job_name));
			append($$anchor, span_4);
		};
		if_block(node_1, ($$render) => {
			if (item().job_name) $$render(consequent_1);
		});
		reset(span_2);
		var text_5 = only_child(sibling(span_2, 2), true);
		reset(button);
		var button_1 = sibling(button, 2);
		let classes_1;
		reset(div);
		template_effect(($0, $1, $2, $3, $4, $5, $6, $7) => {
			classes = set_class(div, 1, "chat-entry", null, classes, {
				chosen: $$props.view === "chats" && $$props.selectedRunId === item().send_id,
				unread: $0
			});
			set_attribute(button, "aria-current", $$props.view === "chats" && $$props.selectedRunId === item().send_id ? "true" : void 0);
			set_text(text_1, item().title || "Untitled run");
			set_text(text_2, $1);
			set_class(span_3, 1, "result-dot status-" + item().status);
			set_text(text_3, $2);
			set_text(text_5, $3);
			classes_1 = set_class(button_1, 1, "chat-pin", null, classes_1, { active: $4 });
			set_attribute(button_1, "title", $5);
			set_attribute(button_1, "aria-label", $6);
			set_attribute(button_1, "aria-pressed", $7);
		}, [
			() => isUnread(item()),
			() => nzTime(activity(item())).split(", ").at(-1),
			() => statusLabel(item().status),
			() => plainPreview(item().preview) || "No response captured yet",
			() => get(pinnedIds).includes(item().send_id),
			() => get(pinnedIds).includes(item().send_id) ? "Unpin local chat" : "Pin local chat",
			() => get(pinnedIds).includes(item().send_id) ? "Unpin " + item().title : "Pin " + item().title,
			() => get(pinnedIds).includes(item().send_id)
		]);
		delegated("click", button, () => selectRun(item()));
		delegated("click", button_1, () => togglePin(item()));
		append($$anchor, div);
	};
	const pageSize = 20;
	const preferencesKey = "prompta.local-sidebar.v1";
	const statuses = [
		{
			value: "",
			label: "All states"
		},
		{
			value: "accepted",
			label: "Accepted"
		},
		{
			value: "generating",
			label: "Generating"
		},
		{
			value: "completed",
			label: "Completed"
		},
		{
			value: "interrupted",
			label: "Interrupted"
		},
		{
			value: "unavailable",
			label: "Unavailable"
		},
		{
			value: "queued",
			label: "Queued"
		}
	];
	let items = /* @__PURE__ */ state(proxy([]));
	let pinnedItems = /* @__PURE__ */ state(proxy([]));
	let pinnedIds = /* @__PURE__ */ state(proxy([]));
	let readAt = /* @__PURE__ */ state(proxy({}));
	let baselineAt = /* @__PURE__ */ state(0);
	let drawerOpen = /* @__PURE__ */ state(false);
	let total = /* @__PURE__ */ state(0);
	let page = /* @__PURE__ */ state(0);
	let search = /* @__PURE__ */ state("");
	let statusFilter = /* @__PURE__ */ state("");
	let detail = /* @__PURE__ */ state(null);
	let turns = /* @__PURE__ */ state(proxy([]));
	let turnsError = /* @__PURE__ */ state("");
	let copyState = /* @__PURE__ */ state("");
	let scrollPane;
	let loadingList = /* @__PURE__ */ state(true);
	let loadingDetail = /* @__PURE__ */ state(false);
	let listError = /* @__PURE__ */ state("");
	let detailError = /* @__PURE__ */ state("");
	let listGeneration = 0;
	let pinsGeneration = 0;
	let detailGeneration = 0;
	let searchTimer;
	const activity = (item) => item.updated_at || item.created_at;
	const newestFirst = (a, b) => activity(b) - activity(a) || b.created_at - a.created_at || a.send_id.localeCompare(b.send_id);
	let pinned = /* @__PURE__ */ user_derived(() => {
		const byId = new Map([...get(pinnedItems), ...get(items)].map((item) => [item.send_id, item]));
		const filtered = get(search).trim() || get(statusFilter);
		return get(pinnedIds).map((id) => byId.get(id)).filter((item) => !!item).filter((item) => !filtered || get(items).some((listed) => listed.send_id === item.send_id)).sort(newestFirst);
	});
	let groups = /* @__PURE__ */ user_derived(() => groupRuns(get(items).filter((item) => !get(pinnedIds).includes(item.send_id)).sort(newestFirst)));
	let pageCount = /* @__PURE__ */ user_derived(() => Math.min(5001, Math.max(1, Math.ceil(get(total) / pageSize))));
	function loadPreferences() {
		try {
			const saved = localStorage.getItem(preferencesKey);
			if (saved) {
				const prefs = JSON.parse(saved);
				set(baselineAt, Number.isFinite(prefs.baselineAt) ? Number(prefs.baselineAt) : Date.now() / 1e3, true);
				set(pinnedIds, Array.isArray(prefs.pinnedIds) ? prefs.pinnedIds.filter((id) => typeof id === "string").slice(0, 24) : [], true);
				set(readAt, prefs.readAt && typeof prefs.readAt === "object" ? prefs.readAt : {}, true);
			} else set(baselineAt, Date.now() / 1e3);
		} catch {
			set(baselineAt, Date.now() / 1e3);
		}
		savePreferences();
	}
	function savePreferences() {
		try {
			const recent = Object.entries(get(readAt)).sort((a, b) => b[1] - a[1]).slice(0, 2e3);
			localStorage.setItem(preferencesKey, JSON.stringify({
				baselineAt: get(baselineAt),
				pinnedIds: get(pinnedIds),
				readAt: Object.fromEntries(recent)
			}));
		} catch {}
	}
	function isUnread(item) {
		return activity(item) > (get(readAt)[item.send_id] ?? get(baselineAt));
	}
	function markRead(item) {
		set(readAt, {
			...get(readAt),
			[item.send_id]: Math.max(Date.now() / 1e3, activity(item))
		}, true);
		savePreferences();
	}
	async function loadPins() {
		const generation = ++pinsGeneration;
		const loaded = await Promise.all(get(pinnedIds).map(async (id) => {
			try {
				const response = await fetch("./api/results/" + encodeURIComponent(id), { cache: "no-store" });
				if (!response.ok) return null;
				return await response.json();
			} catch {
				return null;
			}
		}));
		if (generation === pinsGeneration) set(pinnedItems, loaded.filter((item) => item !== null), true);
	}
	function togglePin(item) {
		if (get(pinnedIds).includes(item.send_id)) {
			set(pinnedIds, get(pinnedIds).filter((id) => id !== item.send_id), true);
			set(pinnedItems, get(pinnedItems).filter((pinnedItem) => pinnedItem.send_id !== item.send_id), true);
		} else {
			set(pinnedIds, [item.send_id, ...get(pinnedIds)].slice(0, 24), true);
			set(pinnedItems, [item, ...get(pinnedItems)], true);
		}
		savePreferences();
	}
	async function loadList() {
		const generation = ++listGeneration;
		set(loadingList, get(items).length === 0);
		const params = new URLSearchParams({
			limit: String(pageSize),
			offset: String(get(page) * pageSize)
		});
		if (get(search).trim()) params.set("q", get(search).trim());
		if (get(statusFilter)) params.set("status", get(statusFilter));
		try {
			const response = await fetch("./api/results?" + params, { cache: "no-store" });
			if (!response.ok) throw new Error("Results could not be loaded");
			const body = await response.json();
			if (generation !== listGeneration) return;
			set(items, body.items, true);
			set(total, body.total, true);
			set(listError, "");
		} catch {
			if (generation === listGeneration) set(listError, "Local results are temporarily unavailable.");
		} finally {
			if (generation === listGeneration) set(loadingList, false);
		}
	}
	async function loadDetail(id) {
		const generation = ++detailGeneration;
		const newSelection = get(detail)?.send_id !== id;
		if (newSelection) {
			set(detail, null);
			set(turns, [], true);
		}
		const followTail = newSelection || !!scrollPane && scrollPane.scrollHeight - scrollPane.scrollTop - scrollPane.clientHeight < 96;
		set(loadingDetail, true);
		try {
			const path = "./api/results/" + encodeURIComponent(id);
			const [response, replyResponse] = await Promise.all([fetch(path, { cache: "no-store" }), fetch(path + "/turns", { cache: "no-store" })]);
			if (!response.ok) throw new Error("Result not found");
			const body = await response.json();
			const saved = replyResponse.ok ? await replyResponse.json() : null;
			if (generation !== detailGeneration) return;
			set(detail, body, true);
			set(turns, saved?.turns?.length ? saved.turns : [{
				reply_id: "",
				user_text: body.user_text,
				assistant_text: body.assistant_text,
				status: body.status,
				created_at: body.created_at,
				updated_at: body.updated_at
			}], true);
			set(turnsError, !replyResponse.ok ? "Saved replies are temporarily unavailable locally." : "", true);
			set(detailError, "");
			if ($$props.view === "chats" && $$props.selectedRunId === id) markRead(body);
			await tick();
			if (followTail && scrollPane && $$props.selectedRunId === id) scrollPane.scrollTop = scrollPane.scrollHeight;
		} catch {
			if (generation === detailGeneration) set(detailError, "This run is unavailable locally.");
		} finally {
			if (generation === detailGeneration) set(loadingDetail, false);
		}
	}
	async function sendFresh(text, images) {
		const requestId = crypto.randomUUID().replaceAll("-", "");
		try {
			const response = await fetch("./api/chats", {
				method: "POST",
				headers: { "content-type": "application/json" },
				body: JSON.stringify({
					request_id: requestId,
					prompt: text,
					images
				})
			});
			if (!response.ok) return {
				ok: false,
				ambiguous: response.status >= 500,
				message: response.status >= 500 ? "The queue result is uncertain. Check local Chats; no automatic resend." : "The fresh chat was rejected. Review the prompt or images."
			};
			const body = await response.json();
			if (!body.send_id) throw new Error("Missing queue receipt");
			$$props.onQueued(body.send_id);
			return {
				ok: true,
				message: "Queued one fresh chat."
			};
		} catch {
			return {
				ok: false,
				ambiguous: true,
				message: "Queue confirmation was lost. Check local Chats before another explicit send; no automatic retry."
			};
		}
	}
	async function sendReply(text, _images) {
		const latest = get(turns).at(-1);
		if (!$$props.selectedRunId || latest?.status !== "completed" || !latest.conversation_id || !latest.message_id) return {
			ok: false,
			message: "This saved branch is not eligible for a reply."
		};
		return sendExactReply($$props.selectedRunId, {
			reply_id: crypto.randomUUID().replaceAll("-", ""),
			conversation_id: latest.conversation_id,
			parent_id: latest.message_id,
			text
		});
	}
	async function sendExactReply(sendId, payload) {
		try {
			const response = await fetch("./api/results/" + encodeURIComponent(sendId) + "/reply-send", {
				method: "POST",
				headers: { "content-type": "application/json" },
				body: JSON.stringify(payload)
			});
			if (!response.ok) return {
				ok: false,
				ambiguous: response.status >= 500,
				message: response.status >= 500 ? "Reply outcome could not be confirmed. Check local turns; do not resubmit blindly." : "Reply was not queued. Check the account-wide send gap and saved branch."
			};
			loadDetail(sendId);
			return {
				ok: true,
				message: "Reply intent saved; explicit dispatch is starting."
			};
		} catch {
			return {
				ok: false,
				ambiguous: true,
				message: "Reply acknowledgment was lost. Check local turns; no automatic retry."
			};
		}
	}
	async function sendPreparedReply(turn) {
		if (!$$props.selectedRunId || !turn.reply_id || !turn.conversation_id || !turn.parent_id) return;
		const result = await sendExactReply($$props.selectedRunId, {
			reply_id: turn.reply_id,
			conversation_id: turn.conversation_id,
			parent_id: turn.parent_id,
			text: turn.user_text
		});
		if (!result.ok) set(turnsError, result.message, true);
	}
	async function copyText(value, key) {
		try {
			await navigator.clipboard.writeText(value);
			set(copyState, key, true);
		} catch {
			set(copyState, "error:" + key);
		}
	}
	function refresh() {
		loadList();
		loadPins();
		if ($$props.view === "chats" && $$props.selectedRunId) loadDetail($$props.selectedRunId);
	}
	function applyFilter() {
		set(page, 0);
		loadList();
	}
	function searchChanged() {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(applyFilter, 300);
	}
	function movePage(next) {
		set(page, Math.max(0, Math.min(get(pageCount) - 1, next)), true);
		loadList();
	}
	function selectRun(item) {
		markRead(item);
		set(drawerOpen, false);
		$$props.onSelect(item.send_id);
	}
	function showJobs() {
		set(drawerOpen, false);
		$$props.onNavigate("jobs");
	}
	function showChats() {
		set(drawerOpen, false);
		$$props.onSelect(null);
	}
	function createChat() {
		set(drawerOpen, false);
		$$props.onNewChat();
	}
	function escapeDrawer(event) {
		if (event.key === "Escape" && get(drawerOpen)) set(drawerOpen, false);
	}
	user_effect(() => {
		const id = $$props.view === "chats" ? $$props.selectedRunId : null;
		untrack(() => {
			if (id) loadDetail(id);
			else {
				detailGeneration += 1;
				set(detail, null);
				set(turns, [], true);
				set(turnsError, "");
				set(detailError, "");
			}
		});
	});
	onMount(() => {
		loadPreferences();
		loadList();
		loadPins();
		const interval = setInterval(() => {
			if (document.visibilityState === "visible") refresh();
		}, 15e3);
		return () => {
			clearInterval(interval);
			clearTimeout(searchTimer);
		};
	});
	var section = root_29();
	event("keydown", $window, escapeDrawer);
	let classes_2;
	var node_2 = child(section);
	var consequent_2 = ($$anchor) => {
		var button_2 = root_3();
		delegated("click", button_2, () => set(drawerOpen, false));
		append($$anchor, button_2);
	};
	if_block(node_2, ($$render) => {
		if (get(drawerOpen)) $$render(consequent_2);
	});
	var aside = sibling(node_2, 2);
	var div_1 = child(aside);
	var div_2 = child(div_1);
	var text_6 = only_child(sibling(child(div_2)), true);
	reset(div_2);
	var button_3 = sibling(div_2, 2);
	reset(div_1);
	var nav = sibling(div_1, 2);
	var button_4 = child(nav);
	var button_5 = sibling(button_4, 2);
	let classes_3;
	var button_6 = sibling(button_5, 2);
	let classes_4;
	reset(nav);
	var div_3 = sibling(nav, 2);
	var h2 = child(div_3);
	var text_7 = only_child(sibling(child(h2)), true);
	reset(h2);
	var button_7 = sibling(h2, 2);
	reset(div_3);
	var div_4 = sibling(div_3, 2);
	var label = child(div_4);
	var input = sibling(child(label), 2);
	remove_input_defaults(input);
	reset(label);
	var label_1 = sibling(label, 2);
	var select = sibling(child(label_1), 2);
	each(select, 21, () => statuses, index, ($$anchor, choice) => {
		var option = root_4();
		var text_8 = only_child(option, true);
		var option_value = {};
		template_effect(() => {
			set_text(text_8, get(choice).label);
			if (option_value !== (option_value = get(choice).value)) option.value = (option.__value = option_value) ?? "";
		});
		append($$anchor, option);
	});
	reset(select);
	init_select(select);
	reset(label_1);
	reset(div_4);
	var node_3 = sibling(div_4, 2);
	var consequent_3 = ($$anchor) => {
		var div_5 = root_5();
		var text_9 = only_child(div_5, true);
		template_effect(() => set_text(text_9, get(listError)));
		append($$anchor, div_5);
	};
	if_block(node_3, ($$render) => {
		if (get(listError)) $$render(consequent_3);
	});
	var div_6 = sibling(node_3, 2);
	var node_4 = child(div_6);
	var consequent_4 = ($$anchor) => {
		var fragment = root_6();
		each(sibling(first_child(fragment), 2), 17, () => get(pinned), (item) => item.send_id, ($$anchor, item) => {
			chatItem($$anchor, () => get(item));
		});
		append($$anchor, fragment);
	};
	if_block(node_4, ($$render) => {
		if (get(pinned).length) $$render(consequent_4);
	});
	var node_6 = sibling(node_4, 2);
	var consequent_5 = ($$anchor) => {
		append($$anchor, root_7());
	};
	var consequent_6 = ($$anchor) => {
		var p_1 = root_8();
		var text_10 = only_child(p_1, true);
		template_effect(() => set_text(text_10, get(search) || get(statusFilter) ? "No runs match these filters." : "No captured job runs yet."));
		append($$anchor, p_1);
	};
	var alternate = ($$anchor) => {
		var fragment_2 = comment();
		each(first_child(fragment_2), 17, () => get(groups), (group) => group.date, ($$anchor, group) => {
			var fragment_3 = root_9();
			var div_7 = first_child(fragment_3);
			var text_11 = only_child(div_7, true);
			each(sibling(div_7, 2), 17, () => get(group).items, (item) => item.send_id, ($$anchor, item) => {
				chatItem($$anchor, () => get(item));
			});
			template_effect(() => set_text(text_11, get(group).date));
			append($$anchor, fragment_3);
		});
		append($$anchor, fragment_2);
	};
	if_block(node_6, ($$render) => {
		if (get(loadingList) && !get(items).length) $$render(consequent_5);
		else if (!get(items).length && !get(pinned).length) $$render(consequent_6, 1);
		else $$render(alternate, -1);
	});
	reset(div_6);
	var div_8 = sibling(div_6, 2);
	var span_8 = child(div_8);
	var text_12 = only_child(span_8);
	var div_9 = sibling(span_8, 2);
	var button_8 = child(div_9);
	var button_9 = sibling(button_8);
	reset(div_9);
	reset(div_8);
	next(2);
	reset(aside);
	var div_10 = sibling(aside, 2);
	var div_11 = child(div_10);
	var button_10 = child(div_11);
	var strong_1 = sibling(button_10, 2);
	var text_13 = only_child(strong_1, true);
	var text_14 = only_child(sibling(strong_1, 2), true);
	reset(div_11);
	var node_9 = sibling(div_11, 2);
	var consequent_7 = ($$anchor) => {
		var div_12 = root_10();
		JobsPage(child(div_12), {});
		reset(div_12);
		append($$anchor, div_12);
	};
	var consequent_8 = ($$anchor) => {
		var fragment_5 = root_11();
		ChatComposer(sibling(first_child(fragment_5), 2), {
			mode: "fresh",
			onSend: sendFresh
		});
		append($$anchor, fragment_5);
	};
	var consequent_9 = ($$anchor) => {
		var div_13 = root_12();
		var button_11 = sibling(child(div_13), 3);
		reset(div_13);
		delegated("click", button_11, createChat);
		append($$anchor, div_13);
	};
	var alternate_3 = ($$anchor) => {
		var fragment_6 = root_28();
		var div_14 = first_child(fragment_6);
		var button_12 = child(div_14);
		var node_12 = sibling(button_12, 2);
		var consequent_10 = ($$anchor) => {
			var span_10 = root_13();
			var text_15 = only_child(span_10, true);
			template_effect(($0, $1) => {
				set_class(span_10, 1, $0);
				set_text(text_15, $1);
			}, [() => "result-pill status-" + (get(turns).at(-1)?.status || get(detail).status), () => get(turns).length > 1 ? "Latest reply · " + turnStatus(get(turns).at(-1)?.status || get(detail).status) : statusLabel(get(detail).status)]);
			append($$anchor, span_10);
		};
		if_block(node_12, ($$render) => {
			if (get(detail)) $$render(consequent_10);
		});
		reset(div_14);
		var div_15 = sibling(div_14, 2);
		var node_13 = child(div_15);
		var consequent_11 = ($$anchor) => {
			var div_16 = root_5();
			var text_16 = only_child(div_16, true);
			template_effect(() => set_text(text_16, get(detailError)));
			append($$anchor, div_16);
		};
		if_block(node_13, ($$render) => {
			if (get(detailError)) $$render(consequent_11);
		});
		var node_14 = sibling(node_13, 2);
		var consequent_12 = ($$anchor) => {
			append($$anchor, root_14());
		};
		if_block(node_14, ($$render) => {
			if (get(loadingDetail) && !get(detail)) $$render(consequent_12);
		});
		var node_15 = sibling(node_14, 2);
		var consequent_21 = ($$anchor) => {
			var div_17 = root_25();
			var header = child(div_17);
			var h2_1 = child(header);
			var text_17 = only_child(h2_1, true);
			var text_18 = only_child(sibling(h2_1));
			reset(header);
			var node_16 = sibling(header, 2);
			var consequent_13 = ($$anchor) => {
				var p_4 = root_15();
				var text_19 = only_child(p_4, true);
				template_effect(() => set_text(text_19, get(turnsError)));
				append($$anchor, p_4);
			};
			if_block(node_16, ($$render) => {
				if (get(turnsError)) $$render(consequent_13);
			});
			each(sibling(node_16, 2), 19, () => get(turns), (turn) => turn.reply_id || get(detail).send_id, ($$anchor, turn, index) => {
				var fragment_7 = root_24();
				var div_18 = first_child(fragment_7);
				var div_19 = child(div_18);
				var node_18 = sibling(child(div_19));
				var consequent_14 = ($$anchor) => {
					append($$anchor, text("· Job prompt"));
				};
				var alternate_1 = ($$anchor) => {
					var text_21 = text();
					template_effect(() => set_text(text_21, `· Reply ${get(index) ?? ""}`));
					append($$anchor, text_21);
				};
				if_block(node_18, ($$render) => {
					if (get(index) === 0) $$render(consequent_14);
					else $$render(alternate_1, -1);
				});
				reset(div_19);
				var div_20 = sibling(div_19, 2);
				var text_22 = only_child(div_20, true);
				var node_19 = sibling(div_20, 2);
				var consequent_15 = ($$anchor) => {
					var div_21 = root_17();
					each(div_21, 21, () => get(detail).images, (attachment) => attachment.url, ($$anchor, attachment) => {
						var a_1 = root_16();
						var img = only_child(a_1);
						template_effect(() => {
							set_attribute(a_1, "href", get(attachment).url);
							set_attribute(a_1, "title", get(attachment).name);
							set_attribute(img, "src", get(attachment).url);
							set_attribute(img, "alt", get(attachment).name);
						});
						append($$anchor, a_1);
					});
					reset(div_21);
					append($$anchor, div_21);
				};
				if_block(node_19, ($$render) => {
					if (get(index) === 0 && get(detail).images?.length) $$render(consequent_15);
				});
				reset(div_18);
				var div_22 = sibling(div_18, 2);
				var div_23 = child(div_22);
				var span_11 = child(div_23);
				var node_20 = sibling(child(span_11));
				var consequent_16 = ($$anchor) => {
					append($$anchor, root_18());
				};
				if_block(node_20, ($$render) => {
					if (get(turn).status === "generating") $$render(consequent_16);
				});
				reset(span_11);
				var node_21 = sibling(span_11, 2);
				var consequent_17 = ($$anchor) => {
					var button_13 = root_19();
					var text_23 = only_child(button_13, true);
					template_effect(() => {
						set_attribute(button_13, "aria-label", "Copy assistant reply " + (get(index) + 1));
						set_text(text_23, get(copyState) === (get(turn).reply_id || get(detail).send_id) ? "Copied" : get(copyState) === "error:" + (get(turn).reply_id || get(detail).send_id) ? "Copy failed" : "Copy");
					});
					delegated("click", button_13, () => copyText(get(turn).assistant_text, get(turn).reply_id || $$props.selectedRunId || ""));
					append($$anchor, button_13);
				};
				if_block(node_21, ($$render) => {
					if (get(turn).assistant_text) $$render(consequent_17);
				});
				reset(div_23);
				var node_22 = sibling(div_23, 2);
				var consequent_19 = ($$anchor) => {
					var fragment_9 = root_21();
					var node_23 = first_child(fragment_9);
					ResultMarkdown(node_23, { get source() {
						return get(turn).assistant_text;
					} });
					var node_24 = sibling(node_23, 2);
					var consequent_18 = ($$anchor) => {
						var p_5 = root_20();
						var text_24 = only_child(p_5);
						template_effect(($0) => set_text(text_24, `${get(turn).status === "generating" ? "Partial response · " : ""}${$0 ?? ""}`), [() => turnStatus(get(turn).status)]);
						append($$anchor, p_5);
					};
					if_block(node_24, ($$render) => {
						if (get(turn).status !== "completed") $$render(consequent_18);
					});
					append($$anchor, fragment_9);
				};
				var alternate_2 = ($$anchor) => {
					var p_6 = root_22();
					var text_25 = only_child(p_6, true);
					template_effect(($0) => set_text(text_25, $0), [() => turnStatus(get(turn).status)]);
					append($$anchor, p_6);
				};
				if_block(node_22, ($$render) => {
					if (get(turn).assistant_text) $$render(consequent_19);
					else $$render(alternate_2, -1);
				});
				var node_25 = sibling(node_22, 2);
				var consequent_20 = ($$anchor) => {
					var p_7 = root_23();
					var text_26 = only_child(p_7);
					template_effect(($0) => set_text(text_26, `${$0 ?? ""}. No automatic history fetch or retry.`), [() => turnStatus(get(turn).status)]);
					append($$anchor, p_7);
				};
				if_block(node_25, ($$render) => {
					if (get(turn).status === "interrupted" || get(turn).status === "unavailable" || get(turn).status === "outcome_unknown") $$render(consequent_20);
				});
				reset(div_22);
				template_effect(() => set_text(text_22, get(turn).user_text));
				append($$anchor, fragment_7);
			});
			reset(div_17);
			template_effect(($0) => {
				set_text(text_17, get(detail).job_name || "Prompta run");
				set_text(text_18, `${$0 ?? ""} · Prompta job run`);
			}, [() => nzTime(get(detail).created_at)]);
			append($$anchor, div_17);
		};
		if_block(node_15, ($$render) => {
			if (get(detail)) $$render(consequent_21);
		});
		reset(div_15);
		bind_this(div_15, ($$value) => scrollPane = $$value, () => scrollPane);
		var node_26 = sibling(div_15, 2);
		var consequent_22 = ($$anchor) => {
			ChatComposer($$anchor, {
				mode: "reply",
				onSend: sendReply
			});
		};
		var d_1 = /* @__PURE__ */ user_derived(() => get(detail) && get(turns).at(-1)?.status === "completed" && get(turns).at(-1)?.conversation_id && get(turns).at(-1)?.message_id);
		var consequent_23 = ($$anchor) => {
			var div_24 = root_26();
			var button_14 = sibling(child(div_24), 2);
			reset(div_24);
			delegated("click", button_14, () => {
				const latest = get(turns).at(-1);
				if (latest) sendPreparedReply(latest);
			});
			append($$anchor, div_24);
		};
		var d_2 = /* @__PURE__ */ user_derived(() => get(turns).at(-1)?.status === "prepared");
		var consequent_24 = ($$anchor) => {
			var div_25 = root_27();
			var text_27 = only_child(div_25);
			template_effect(($0) => set_text(text_27, `${$0 ?? ""} · No automatic retry`), [() => turnStatus(get(turns).at(-1)?.status || get(detail).status)]);
			append($$anchor, div_25);
		};
		if_block(node_26, ($$render) => {
			if (get(d_1)) $$render(consequent_22);
			else if (get(d_2)) $$render(consequent_23, 1);
			else if (get(detail) && get(turns).length > 1) $$render(consequent_24, 2);
		});
		delegated("click", button_12, () => $$props.onSelect(null));
		append($$anchor, fragment_6);
	};
	if_block(node_9, ($$render) => {
		if ($$props.view === "jobs") $$render(consequent_7);
		else if (!$$props.selectedRunId && $$props.newChatOpen) $$render(consequent_8, 1);
		else if (!$$props.selectedRunId) $$render(consequent_9, 2);
		else $$render(alternate_3, -1);
	});
	reset(div_10);
	reset(section);
	template_effect(($0) => {
		classes_2 = set_class(section, 1, "chats-layout", null, classes_2, {
			"drawer-open": get(drawerOpen),
			"show-list": $$props.view === "chats" && !$$props.selectedRunId && !$$props.newChatOpen
		});
		set_text(text_6, $$props.serverName);
		classes_3 = set_class(button_5, 1, "", null, classes_3, { active: $$props.view === "chats" });
		classes_4 = set_class(button_6, 1, "", null, classes_4, { active: $$props.view === "jobs" });
		set_text(text_7, get(total));
		set_text(text_12, `${get(total) ? get(page) * pageSize + 1 : 0}–${$0 ?? ""} of ${get(total) ?? ""}`);
		button_8.disabled = get(page) === 0;
		button_9.disabled = get(page) + 1 >= get(pageCount);
		set_attribute(button_10, "aria-expanded", get(drawerOpen));
		set_text(text_13, $$props.view === "jobs" ? "Jobs" : get(detail)?.title || get(detail)?.job_name || "Chats");
		set_text(text_14, $$props.serverName);
	}, [() => Math.min(get(total), (get(page) + 1) * pageSize)]);
	delegated("click", button_3, () => set(drawerOpen, false));
	delegated("click", button_4, createChat);
	delegated("click", button_5, showChats);
	delegated("click", button_6, showJobs);
	delegated("click", button_7, refresh);
	delegated("input", input, searchChanged);
	bind_value(input, () => get(search), ($$value) => set(search, $$value));
	delegated("change", select, applyFilter);
	bind_select_value(select, () => get(statusFilter), ($$value) => set(statusFilter, $$value));
	delegated("click", button_8, () => movePage(get(page) - 1));
	delegated("click", button_9, () => movePage(get(page) + 1));
	delegated("click", button_10, () => set(drawerOpen, true));
	append($$anchor, section);
	pop();
}
delegate([
	"click",
	"input",
	"change"
]);
//#endregion
//#region src/ui/App.svelte
var root = /* @__PURE__ */ from_html(`<meta name="apple-mobile-web-app-title"/>`);
var root_1 = /* @__PURE__ */ from_html(`<main class="jobs-app"><!></main>`);
function App($$anchor, $$props) {
	push($$props, true);
	let view = /* @__PURE__ */ state("jobs");
	let selectedRunId = /* @__PURE__ */ state(null);
	let newChatOpen = /* @__PURE__ */ state(false);
	function syncRoute() {
		const params = new URLSearchParams(window.location.search);
		set(view, params.get("view") === "chats" ? "chats" : "jobs", true);
		set(selectedRunId, get(view) === "chats" ? params.get("run") : null, true);
		set(newChatOpen, get(view) === "chats" && !get(selectedRunId) && params.get("draft") === "new", true);
	}
	function navigate(nextView, run = null) {
		const url = new URL(window.location.href);
		url.searchParams.delete("new");
		url.searchParams.delete("edit");
		url.searchParams.delete("run");
		url.searchParams.delete("draft");
		if (nextView === "chats") {
			url.searchParams.set("view", "chats");
			if (run) url.searchParams.set("run", run);
		} else url.searchParams.delete("view");
		window.history.pushState(null, "", url);
		syncRoute();
	}
	function newChat() {
		const url = new URL(window.location.href);
		url.searchParams.set("view", "chats");
		url.searchParams.delete("run");
		url.searchParams.delete("edit");
		url.searchParams.delete("new");
		url.searchParams.set("draft", "new");
		window.history.pushState(null, "", url);
		syncRoute();
	}
	onMount(() => {
		syncRoute();
		window.addEventListener("popstate", syncRoute);
		return () => window.removeEventListener("popstate", syncRoute);
	});
	var main = root_1();
	head("1ocnzw1", ($$anchor) => {
		var meta = root();
		template_effect(() => set_attribute(meta, "content", "Prompta " + $$props.serverName));
		deferred_template_effect(() => {
			$document.title = `Prompta · ${get(view) === "chats" ? "Chats" : "Jobs"} · ${$$props.serverName ?? ""}`;
		});
		append($$anchor, meta);
	});
	ChatsPage(child(main), {
		get view() {
			return get(view);
		},
		get serverName() {
			return $$props.serverName;
		},
		get selectedRunId() {
			return get(selectedRunId);
		},
		get newChatOpen() {
			return get(newChatOpen);
		},
		onSelect: (id) => navigate("chats", id),
		onNavigate: (nextView) => navigate(nextView),
		onNewChat: newChat,
		onQueued: (id) => navigate("chats", id)
	});
	reset(main);
	append($$anchor, main);
	pop();
}
//#endregion
//#region src/ui/main.ts
window.addEventListener("beforeinstallprompt", (event) => {
	event.preventDefault();
});
if ("serviceWorker" in navigator && window.isSecureContext) window.addEventListener("load", () => {
	navigator.serviceWorker.register("./sw.js", { scope: "./" }).catch((error) => {
		console.warn("Prompta service worker registration failed", error);
	});
});
var target = document.querySelector("#app");
if (!target) throw new Error("Missing #app mount target");
mount(App, {
	target,
	props: { serverName: target.dataset.serverName?.trim() || "local" }
});
//#endregion
