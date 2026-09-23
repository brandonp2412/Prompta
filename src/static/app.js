//#region \0rolldown/runtime.js
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __esmMin = (fn, res, err) => () => {
	if (err) throw err[0];
	try {
		return fn && (res = fn(fn = 0)), res;
	} catch (e) {
		throw err = [e], e;
	}
};
var __commonJSMin = (cb, mod) => () => (mod || (cb((mod = { exports: {} }).exports, mod), cb = null), mod.exports);
var __exportAll = (all, no_symbols) => {
	let target = {};
	for (var name in all) __defProp(target, name, {
		get: all[name],
		enumerable: true
	});
	if (!no_symbols) __defProp(target, Symbol.toStringTag, { value: "Module" });
	return target;
};
var __copyProps = (to, from, except, desc) => {
	if (from && typeof from === "object" || typeof from === "function") for (var keys = __getOwnPropNames(from), i = 0, n = keys.length, key; i < n; i++) {
		key = keys[i];
		if (!__hasOwnProp.call(to, key) && key !== except) __defProp(to, key, {
			get: ((k) => from[k]).bind(null, key),
			enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable
		});
	}
	return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(isNodeMode || !mod || !mod.__esModule || !__hasOwnProp.call(mod, "default") ? __defProp(target, "default", {
	value: mod,
	enumerable: true
}) : target, mod));
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
})), MANAGED_EFFECT, CLEAN, DIRTY, MAYBE_DIRTY, INERT, DESTROYED, REACTION_RAN, DESTROYING, EFFECT_TRANSPARENT, HEAD_EFFECT, EFFECT_PRESERVED, USER_EFFECT, EFFECT_OFFSCREEN, REACTION_IS_UPDATING, ASYNC, ERROR_VALUE, STATE_SYMBOL, COMPONENT_SYMBOL, LEGACY_PROPS, LOADING_ATTR_SYMBOL, ATTRIBUTES_CACHE, CLASS_CACHE, STYLE_CACHE, TEXT_CACHE, FORM_RESET_HANDLER, STALE_REACTION, IS_XHTML;
var init_constants$1 = __esmMin((() => {
	MANAGED_EFFECT = 1 << 24;
	CLEAN = 1024;
	DIRTY = 2048;
	MAYBE_DIRTY = 4096;
	INERT = 8192;
	DESTROYED = 16384;
	REACTION_RAN = 32768;
	DESTROYING = 1 << 25;
	EFFECT_TRANSPARENT = 65536;
	HEAD_EFFECT = 1 << 18;
	EFFECT_PRESERVED = 1 << 19;
	USER_EFFECT = 1 << 20;
	EFFECT_OFFSCREEN = 1 << 25;
	REACTION_IS_UPDATING = 1 << 21;
	ASYNC = 1 << 22;
	ERROR_VALUE = 1 << 23;
	STATE_SYMBOL = Symbol("$state");
	COMPONENT_SYMBOL = Symbol("component");
	LEGACY_PROPS = Symbol("legacy props");
	LOADING_ATTR_SYMBOL = Symbol("");
	ATTRIBUTES_CACHE = Symbol("attributes");
	CLASS_CACHE = Symbol("class");
	STYLE_CACHE = Symbol("style");
	TEXT_CACHE = Symbol("text");
	FORM_RESET_HANDLER = Symbol("form reset");
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
/**
* Synchronously run any queued tasks.
*/
function flush_tasks() {
	while (micro_tasks.length > 0) run_micro_tasks();
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
/**
* The child of a textarea actually corresponds to the defaultValue property, so we need
* to remove it upon hydration to avoid a bug when someone resets the form value.
* @param {HTMLTextAreaElement} dom
* @returns {void}
*/
function remove_textarea_child(dom) {
	if (hydrating && /* @__PURE__ */ get_first_child(dom) !== null) clear_text_content(dom);
}
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
var listening_to_form_reset;
var init_misc$1 = __esmMin((() => {
	init_hydration();
	init_operations$1();
	init_task();
	init_constants$1();
	listening_to_form_reset = false;
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
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/batch.js
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
* @param {number} flags
*/
function managed(fn, flags = 0) {
	return create_effect(MANAGED_EFFECT | flags, fn);
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
	init_index_client$1();
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
* Attaches an event handler to an element and returns a function that removes the handler. Using this
* rather than `addEventListener` will preserve the correct order relative to handlers added declaratively
* (with attributes like `onclick`), which use event delegation for performance reasons
*
* @param {EventTarget} element
* @param {string} type
* @param {EventListener} handler
* @param {AddEventListenerOptions} [options]
*/
function on(element, type, handler, options = {}) {
	var target_handler = create_event(type, element, handler, options);
	return () => {
		target_handler.__removed = true;
		element.removeEventListener(type, target_handler, options);
	};
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
var init_events$1 = __esmMin((() => {
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
* @param {string} content
* @param {number} flags
* @param {'svg' | 'math'} ns
* @returns {() => Node | Node[]}
*/
/*#__NO_SIDE_EFFECTS__*/
function from_namespace(content, flags, ns = "svg") {
	/**
	* Whether or not the first item is a text/element node. If not, we need to
	* create an additional comment node to act as `effect.nodes.start`
	*/
	var has_start = !content.startsWith("<!>");
	var is_fragment = (flags & 1) !== 0;
	var wrapped = `<${ns}>${has_start ? content : "<!>" + content}</${ns}>`;
	/** @type {Element | DocumentFragment} */
	var node;
	return () => {
		if (hydrating) {
			assign_nodes(hydrate_node, null);
			return hydrate_node;
		}
		if (!node) {
			var root = /* @__PURE__ */ get_first_child(create_fragment_from_html(wrapped));
			if (is_fragment) {
				node = document.createDocumentFragment();
				while (/* @__PURE__ */ get_first_child(root)) node.appendChild(/* @__PURE__ */ get_first_child(root));
			} else node = /* @__PURE__ */ get_first_child(root);
		}
		var clone = node.cloneNode(true);
		if (is_fragment) {
			var start = /* @__PURE__ */ get_first_child(clone);
			var end = clone.lastChild;
			assign_nodes(start, end);
		} else assign_nodes(clone, clone);
		return clone;
	};
}
/**
* @param {string} content
* @param {number} flags
*/
/*#__NO_SIDE_EFFECTS__*/
function from_svg(content, flags) {
	return /* @__PURE__ */ from_namespace(content, flags, "svg");
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
	init_events$1();
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
/**
* @template {(node: TemplateNode, ...args: any[]) => void} SnippetFn
* @param {TemplateNode} node
* @param {() => SnippetFn | null | undefined} get_snippet
* @param {(() => any)[]} args
* @returns {void}
*/
function snippet(node, get_snippet, ...args) {
	var branches = new BranchManager(node);
	block(() => {
		const snippet = get_snippet() ?? null;
		branches.ensure(snippet, snippet && ((anchor) => snippet(anchor, ...args)));
	}, EFFECT_TRANSPARENT);
}
var init_snippet = __esmMin((() => {
	init_constants$1();
	init_effects();
	init_context();
	init_hydration();
	init_reconciler();
	init_template();
	init_errors();
	init_esm_env();
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
/**
* @param {Element} node
* @param {() => (node: Element) => void} get_fn
*/
function attach(node, get_fn) {
	/** @type {false | undefined | ((node: Element) => void)} */
	var fn = void 0;
	/** @type {Effect | null} */
	var e;
	managed(() => {
		if (fn !== (fn = get_fn())) {
			if (e) {
				destroy_effect(e);
				e = null;
			}
			if (fn) e = branch(() => {
				effect(() => fn(node));
			});
		}
	});
}
var init_attachments = __esmMin((() => {
	init_effects();
}));
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
var init_clsx = __esmMin((() => {}));
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
/**
*
* @param {Record<string,any>} styles
* @param {boolean} important
*/
function append_styles(styles, important = false) {
	var separator = important ? " !important;" : ";";
	var css = "";
	for (var key of Object.keys(styles)) {
		var value = styles[key];
		if (value != null && value !== "") css += " " + key + ": " + value + separator;
	}
	return css;
}
/**
* @param {string} name
* @returns {string}
*/
function to_css_name(name) {
	if (name[0] !== "-" || name[1] !== "-") return name.toLowerCase();
	return name;
}
/**
* @param {any} value
* @param {Record<string, any> | [Record<string, any>, Record<string, any>]} [styles]
* @returns {string | null}
*/
function to_style(value, styles) {
	if (styles) {
		var new_style = "";
		/** @type {Record<string,any> | undefined} */
		var normal_styles;
		/** @type {Record<string,any> | undefined} */
		var important_styles;
		if (Array.isArray(styles)) {
			normal_styles = styles[0];
			important_styles = styles[1];
		} else normal_styles = styles;
		if (value) {
			value = String(value).replaceAll(/\/\*.*?\*\//g, "").trim();
			/** @type {boolean | '"' | "'"} */
			var in_str = false;
			var in_apo = 0;
			var in_comment = false;
			var reserved_names = [];
			if (normal_styles) reserved_names.push(...Object.keys(normal_styles).map(to_css_name));
			if (important_styles) reserved_names.push(...Object.keys(important_styles).map(to_css_name));
			var start_index = 0;
			var name_index = -1;
			const len = value.length;
			for (var i = 0; i < len; i++) {
				var c = value[i];
				if (in_comment) {
					if (c === "/" && value[i - 1] === "*") in_comment = false;
				} else if (in_str) {
					if (in_str === c) in_str = false;
				} else if (c === "/" && value[i + 1] === "*") in_comment = true;
				else if (c === "\"" || c === "'") in_str = c;
				else if (c === "(") in_apo++;
				else if (c === ")") in_apo--;
				if (!in_comment && in_str === false && in_apo === 0) {
					if (c === ":" && name_index === -1) name_index = i;
					else if (c === ";" || i === len - 1) {
						if (name_index !== -1) {
							var name = to_css_name(value.substring(start_index, name_index).trim());
							if (!reserved_names.includes(name)) {
								if (c !== ";") i++;
								var property = value.substring(start_index, i).trim();
								new_style += " " + property + ";";
							}
						}
						start_index = i + 1;
						name_index = -1;
					}
				}
			}
		}
		if (normal_styles) new_style += append_styles(normal_styles);
		if (important_styles) new_style += append_styles(important_styles, true);
		new_style = new_style.trim();
		return new_style === "" ? null : new_style;
	}
	return value == null ? null : String(value);
}
var whitespace;
var init_attributes$1 = __esmMin((() => {
	init_clsx();
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
/**
* @param {Element & ElementCSSInlineStyle} dom
* @param {Record<string, any>} prev
* @param {Record<string, any>} next
* @param {string} [priority]
*/
function update_styles(dom, prev = {}, next, priority) {
	for (var key in next) {
		var value = next[key];
		if (prev[key] !== value) {
			if (next[key] == null) dom.style.removeProperty(key);
			else dom.style.setProperty(key, value, priority);
		}
	}
}
/**
* @param {Element & ElementCSSInlineStyle} dom
* @param {string | null} value
* @param {Record<string, any> | [Record<string, any>, Record<string, any>]} [prev_styles]
* @param {Record<string, any> | [Record<string, any>, Record<string, any>]} [next_styles]
*/
function set_style(dom, value, prev_styles, next_styles) {
	var prev = dom[STYLE_CACHE];
	if (hydrating || prev !== value) {
		var next_style_attr = to_style(value, next_styles);
		if (!hydrating || next_style_attr !== dom.getAttribute("style")) {
			if (next_style_attr == null) dom.removeAttribute("style");
			else dom.style.cssText = next_style_attr;
		}
		/** @type {any} */ dom[STYLE_CACHE] = value;
	} else if (next_styles) {
		if (Array.isArray(next_styles)) {
			update_styles(dom, prev_styles?.[0], next_styles[0]);
			update_styles(dom, prev_styles?.[1], next_styles[1], "important");
		} else update_styles(dom, prev_styles, next_styles);
	}
	return next_styles;
}
var init_style = __esmMin((() => {
	init_attributes$1();
	init_constants$1();
	init_hydration();
}));
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
var init_select$1 = __esmMin((() => {
	init_effects();
	init_shared$1();
	init_proxy();
	init_utils$3();
	init_warnings();
	init_batch();
	init_flags();
}));
//#endregion
//#region node_modules/svelte/src/internal/client/dom/elements/attributes.js
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
* @param {boolean} checked
*/
function set_checked(element, checked) {
	var attributes = get_attributes(element);
	if (attributes.checked === (attributes.checked = checked ?? void 0)) return;
	element.checked = checked;
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
	init_events$1();
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
	init_select$1();
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
var init_input = __esmMin((() => {
	init_esm_env();
	init_effects();
	init_shared$1();
	init_errors();
	init_proxy();
	init_task();
	init_hydration();
	init_runtime();
	init_batch();
	init_flags();
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
	init_events$1();
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
var is_store_binding;
var init_store = __esmMin((() => {
	init_utils();
	init_shared();
	init_utils$3();
	init_runtime();
	init_effects();
	init_sources();
	is_store_binding = false;
}));
//#endregion
//#region node_modules/svelte/src/internal/client/reactivity/props.js
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
var init_props = __esmMin((() => {
	init_esm_env();
	init_constants();
	init_utils$3();
	init_sources();
	init_deriveds();
	init_runtime();
	init_errors();
	init_constants$1();
	init_proxy();
	init_store();
	init_flags();
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
	init_events$1();
	init_misc$1();
	init_customizable_select();
	init_style();
	init_transitions();
	init_document();
	init_input();
	init_media();
	init_navigator();
	init_props$1();
	init_select$1();
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
var init_index_client$1 = __esmMin((() => {
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
//#region node_modules/svelte/src/internal/disclose-version.js
if (typeof window !== "undefined") ((window.__svelte ??= {}).v ??= /* @__PURE__ */ new Set()).add("5");
//#endregion
//#region node_modules/svelte/src/reactivity/date.js
var init_date = __esmMin((() => {
	init_client();
	init_sources();
	init_tracing();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/reactivity/set.js
var init_set = __esmMin((() => {
	init_sources();
	init_tracing();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/reactivity/map.js
var init_map = __esmMin((() => {
	init_sources();
	init_tracing();
	init_runtime();
}));
//#endregion
//#region node_modules/svelte/src/reactivity/url-search-params.js
var init_url_search_params = __esmMin((() => {
	init_sources();
	init_tracing();
	init_runtime();
	init_url();
}));
//#endregion
//#region node_modules/svelte/src/reactivity/url.js
var init_url = __esmMin((() => {
	init_sources();
	init_tracing();
	init_runtime();
	init_url_search_params();
}));
//#endregion
//#region node_modules/svelte/src/events/index.js
var init_events = __esmMin((() => {
	init_events$1();
}));
//#endregion
//#region node_modules/svelte/src/reactivity/reactive-value.js
var ReactiveValue;
var init_reactive_value = __esmMin((() => {
	init_create_subscriber();
	ReactiveValue = class {
		#fn;
		#subscribe;
		/**
		*
		* @param {() => T} fn
		* @param {(update: () => void) => void} onsubscribe
		*/
		constructor(fn, onsubscribe) {
			this.#fn = fn;
			this.#subscribe = createSubscriber(onsubscribe);
		}
		get current() {
			this.#subscribe();
			return this.#fn();
		}
	};
}));
//#endregion
//#region node_modules/svelte/src/reactivity/media-query.js
var parenthesis_regex, non_parenthesized_keywords, MediaQuery;
var init_media_query = __esmMin((() => {
	init_events();
	init_reactive_value();
	parenthesis_regex = /\(.+\)/;
	non_parenthesized_keywords = /* @__PURE__ */ new Set([
		"all",
		"print",
		"screen",
		"and",
		"or",
		"not",
		"only"
	]);
	MediaQuery = class extends ReactiveValue {
		/**
		* @param {string} query A media query string
		* @param {boolean} [fallback] Fallback value for the server
		*/
		constructor(query, fallback) {
			let final_query = parenthesis_regex.test(query) || query.split(/[\s,]+/).some((keyword) => non_parenthesized_keywords.has(keyword.trim())) ? query : `(${query})`;
			const q = window.matchMedia(final_query);
			super(() => q.matches, (update) => on(q, "change", update));
		}
	};
}));
//#endregion
//#region node_modules/svelte/src/reactivity/index-client.js
var init_index_client = __esmMin((() => {
	init_date();
	init_set();
	init_map();
	init_url();
	init_url_search_params();
	init_media_query();
	init_create_subscriber();
}));
//#endregion
//#region src/ui/browserAttachments.svelte.ts
function viewportPinnedToBottom(element) {
	const maxScrollTop = Math.max(0, element.scrollHeight - element.clientHeight);
	return Math.max(0, maxScrollTop - element.scrollTop) <= CONVERSATION_BOTTOM_SLOP;
}
function keepConversationViewportAtBottom(element) {
	const restoreToken = ++conversationViewportRestoreToken;
	requestAnimationFrame(() => {
		if (restoreToken !== conversationViewportRestoreToken || conversationViewportElement !== element || !conversationViewportPinnedToBottom) return;
		element.scrollTop = element.scrollHeight;
	});
}
function conversationViewport(onPinnedChange) {
	return (element) => {
		conversationViewportElement = element;
		conversationViewportPinnedChange = onPinnedChange ?? null;
		conversationViewportPinnedToBottom = true;
		conversationViewportPinnedChange?.(true);
		const handleScroll = () => {
			const pinned = viewportPinnedToBottom(element);
			conversationViewportPinnedToBottom = pinned;
			conversationViewportPinnedChange?.(pinned);
		};
		element.addEventListener("scroll", handleScroll, { passive: true });
		const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
			if (conversationViewportElement === element && conversationViewportPinnedToBottom) keepConversationViewportAtBottom(element);
		});
		resizeObserver?.observe(element);
		for (const child of Array.from(element.children)) resizeObserver?.observe(child);
		return () => {
			element.removeEventListener("scroll", handleScroll);
			resizeObserver?.disconnect();
			if (conversationViewportElement === element) {
				conversationViewportElement = null;
				conversationViewportPinnedChange = null;
			}
			conversationViewportRestoreToken += 1;
			conversationViewportPinnedToBottom = true;
		};
	};
}
function preserveConversationViewportPosition() {
	const element = conversationViewportElement;
	if (!element) return () => {};
	const scrollTop = element.scrollTop;
	conversationViewportPinnedToBottom = false;
	conversationViewportRestoreToken += 1;
	return () => {
		requestAnimationFrame(() => {
			if (conversationViewportElement !== element) return;
			const maxScrollTop = Math.max(0, element.scrollHeight - element.clientHeight);
			element.scrollTop = Math.min(scrollTop, maxScrollTop);
			conversationViewportPinnedToBottom = viewportPinnedToBottom(element);
		});
	};
}
function captureConversationViewport() {
	const element = conversationViewportElement;
	if (!element) return {
		pinnedToBottom: true,
		scrollTop: 0
	};
	return {
		pinnedToBottom: viewportPinnedToBottom(element),
		scrollTop: element.scrollTop
	};
}
function restoreConversationViewport(snapshot, forceBottom = false) {
	const element = conversationViewportElement;
	if (!element) return;
	const shouldPinToBottom = forceBottom || Boolean(snapshot.pinnedToBottom);
	conversationViewportPinnedToBottom = shouldPinToBottom;
	conversationViewportPinnedChange?.(shouldPinToBottom);
	if (shouldPinToBottom) element.scrollTop = element.scrollHeight;
	const restoreToken = ++conversationViewportRestoreToken;
	requestAnimationFrame(() => {
		if (restoreToken !== conversationViewportRestoreToken || conversationViewportElement !== element) return;
		if (shouldPinToBottom) {
			element.scrollTop = element.scrollHeight;
			keepConversationViewportAtBottom(element);
			return;
		}
		const maxScrollTop = Math.max(0, element.scrollHeight - element.clientHeight);
		const rememberedScrollTop = Math.max(0, Number(snapshot.scrollTop) || 0);
		element.scrollTop = Math.min(rememberedScrollTop, maxScrollTop);
	});
}
function scrollConversationToBottom() {
	const element = conversationViewportElement;
	if (!element) return;
	conversationViewportPinnedToBottom = true;
	conversationViewportPinnedChange?.(true);
	element.scrollTop = element.scrollHeight;
	keepConversationViewportAtBottom(element);
}
function focusOnRequest(getRequest) {
	return (element) => {
		let lastRequest = 0;
		user_effect(() => {
			const request = getRequest();
			if (!request || request === lastRequest) return;
			lastRequest = request;
			requestAnimationFrame(() => element.focus({ preventScroll: true }));
		});
	};
}
function clickOnRequest(getRequest) {
	return (element) => {
		let lastRequest = 0;
		user_effect(() => {
			const request = getRequest();
			if (!request || request === lastRequest) return;
			lastRequest = request;
			element.click();
		});
	};
}
function blurOnRequest(getRequest) {
	return (element) => {
		let lastRequest = 0;
		user_effect(() => {
			const request = getRequest();
			if (!request || request === lastRequest) return;
			lastRequest = request;
			element.blur();
		});
	};
}
function composerTextarea(getValue, getFocusRequest, getSelectEndRequest) {
	return (element) => {
		let lastFocusRequest = 0;
		let lastSelectEndRequest = 0;
		user_effect(() => {
			const value = getValue();
			element.style.overflowY = "hidden";
			element.style.height = value ? "auto" : "34px";
			if (value) {
				const contentHeight = element.scrollHeight;
				element.style.height = String(Math.min(180, contentHeight)) + "px";
				element.style.overflowY = contentHeight > 180 ? "auto" : "hidden";
			}
		});
		user_effect(() => {
			const request = getFocusRequest();
			if (!request || request === lastFocusRequest) return;
			lastFocusRequest = request;
			requestAnimationFrame(() => element.focus());
		});
		user_effect(() => {
			const request = getSelectEndRequest();
			if (!request || request === lastSelectEndRequest) return;
			lastSelectEndRequest = request;
			requestAnimationFrame(() => {
				element.focus();
				const end = getValue().length;
				element.setSelectionRange(end, end);
			});
		});
	};
}
function scrollToTopOnRequest(getRequest) {
	return (element) => {
		let lastRequest = 0;
		user_effect(() => {
			const request = getRequest();
			if (!request || request === lastRequest) return;
			lastRequest = request;
			requestAnimationFrame(() => {
				element.scrollTop = 0;
			});
		});
	};
}
function stickToBottom(getFingerprint) {
	return (element) => {
		let nearBottom = true;
		let initialized = false;
		const updateNearBottom = () => {
			nearBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 120;
		};
		element.addEventListener("scroll", updateNearBottom, { passive: true });
		user_effect(() => {
			getFingerprint();
			const shouldScroll = !initialized || nearBottom;
			initialized = true;
			if (shouldScroll) requestAnimationFrame(() => {
				element.scrollTop = element.scrollHeight;
				updateNearBottom();
			});
		});
		return () => element.removeEventListener("scroll", updateNearBottom);
	};
}
function clickOutside(onOutside) {
	return (element) => {
		const handlePointerDown = (event) => {
			if (event.target instanceof Node && !element.contains(event.target)) onOutside();
		};
		document.addEventListener("pointerdown", handlePointerDown);
		return () => document.removeEventListener("pointerdown", handlePointerDown);
	};
}
function dialogVisibility(getOpen, getModal, onNativeClose) {
	return (element) => {
		const handleClose = () => onNativeClose();
		element.addEventListener("close", handleClose);
		user_effect(() => {
			const shouldOpen = getOpen();
			const modal = getModal();
			if (shouldOpen && !element.open) {
				if (modal) element.showModal();
				else element.show();
			} else if (!shouldOpen && element.open) element.close();
		});
		return () => element.removeEventListener("close", handleClose);
	};
}
function fitVisualViewport() {
	return (element) => {
		const viewport = window.visualViewport;
		if (!viewport) return;
		let animationFrame = 0;
		const syncViewport = () => {
			cancelAnimationFrame(animationFrame);
			animationFrame = requestAnimationFrame(() => {
				element.style.setProperty("--app-visual-viewport-height", `${viewport.height}px`);
				element.style.setProperty("--app-visual-viewport-offset-top", `${viewport.offsetTop}px`);
			});
		};
		viewport.addEventListener("resize", syncViewport, { passive: true });
		viewport.addEventListener("scroll", syncViewport, { passive: true });
		window.addEventListener("resize", syncViewport, { passive: true });
		syncViewport();
		return () => {
			cancelAnimationFrame(animationFrame);
			viewport.removeEventListener("resize", syncViewport);
			viewport.removeEventListener("scroll", syncViewport);
			window.removeEventListener("resize", syncViewport);
			element.style.removeProperty("--app-visual-viewport-height");
			element.style.removeProperty("--app-visual-viewport-offset-top");
		};
	};
}
function reportElementWidth(onWidth) {
	return (element) => {
		const updateWidth = () => onWidth(element.getBoundingClientRect().width);
		const observer = new ResizeObserver(updateWidth);
		updateWidth();
		observer.observe(element);
		return () => observer.disconnect();
	};
}
var CONVERSATION_BOTTOM_SLOP, conversationViewportElement, conversationViewportRestoreToken, conversationViewportPinnedToBottom, conversationViewportPinnedChange;
var init_browserAttachments_svelte = __esmMin((() => {
	init_client();
	CONVERSATION_BOTTOM_SLOP = 24;
	conversationViewportElement = null;
	conversationViewportRestoreToken = 0;
	conversationViewportPinnedToBottom = true;
	conversationViewportPinnedChange = null;
}));
//#endregion
//#region src/ui/changelog.ts
init_index_client();
init_browserAttachments_svelte();
function changelogPage(payload) {
	if (!payload || typeof payload !== "object" || !Array.isArray(payload.changes)) return {
		changes: [],
		hasMore: false,
		total: 0
	};
	const source = payload;
	const total = Number(source.total);
	return {
		changes: source.changes,
		hasMore: Boolean(source.has_more),
		total: Number.isFinite(total) ? Math.max(source.changes.length, Math.floor(total)) : source.changes.length
	};
}
//#endregion
//#region src/ui/uiControllers.ts
function registerAttachmentPicker(controller) {
	attachmentPicker$1 = controller;
}
function getAttachmentPicker() {
	if (!attachmentPicker$1) throw new Error("Attachment picker was not mounted");
	return attachmentPicker$1;
}
function registerJobsDialog(controller) {
	jobsDialog$1 = controller;
}
function getJobsDialog() {
	if (!jobsDialog$1) throw new Error("Jobs dialog was not mounted");
	return jobsDialog$1;
}
function registerChangelogDialog(controller) {
	changelogDialog = controller;
}
function getChangelogDialog() {
	if (!changelogDialog) throw new Error("Changelog dialog was not mounted");
	return changelogDialog;
}
function registerLogsPanel(controller) {
	logsPanel$1 = controller;
}
function getLogsPanel() {
	if (!logsPanel$1) throw new Error("Logs panel was not mounted");
	return logsPanel$1;
}
var attachmentPicker$1, jobsDialog$1, changelogDialog, logsPanel$1;
var init_uiControllers = __esmMin((() => {
	attachmentPicker$1 = null;
	jobsDialog$1 = null;
	changelogDialog = null;
	logsPanel$1 = null;
}));
//#endregion
//#region src/ui/ChangelogDialog.svelte
init_client();
init_uiControllers();
var root$8 = /* @__PURE__ */ from_html(`<li class="changelog-empty">Could not load changelog.</li>`);
var root_1$7 = /* @__PURE__ */ from_html(`<span class="changelog-entry-hash"> </span>`);
var root_2$7 = /* @__PURE__ */ from_html(`<li class="changelog-entry"><span class="changelog-entry-title"> </span> <!></li>`);
var root_3$6 = /* @__PURE__ */ from_html(`<li class="changelog-load-more-row"><button type="button" class="changelog-load-more"> </button></li>`);
var root_4$6 = /* @__PURE__ */ from_html(`<!> <!>`, 1);
var root_5$5 = /* @__PURE__ */ from_html(`<li class="changelog-empty"> </li>`);
var root_6$5 = /* @__PURE__ */ from_html(`<dialog class="changelog-dialog" id="changelogDialog" aria-labelledby="changelogDialogTitle"><div class="changelog-dialog-shell"><header class="changelog-dialog-header"><div><h2 id="changelogDialogTitle">Changelog</h2> <p id="changelogDialogStatus"> </p></div> <button type="button" class="changelog-close-button" id="closeChangelogDialog" aria-label="Close changelog">×</button></header> <ol class="changelog-list" id="changelogList"><!></ol></div></dialog>`);
function ChangelogDialog($$anchor, $$props) {
	push($$props, true);
	const CHANGELOG_PAGE_SIZE = 100;
	const mobile = new MediaQuery("(max-width: 600px)");
	let status = /* @__PURE__ */ state$1("Commit titles from this Prompta checkout.");
	let changes = /* @__PURE__ */ state$1([]);
	let failed = /* @__PURE__ */ state$1(false);
	let hasMore = /* @__PURE__ */ state$1(false);
	let loadingMore = /* @__PURE__ */ state$1(false);
	let currentLimit = /* @__PURE__ */ state$1(CHANGELOG_PAGE_SIZE);
	let open = /* @__PURE__ */ state$1(false);
	let presentation = /* @__PURE__ */ state$1("modal");
	async function load(limit, reset = false) {
		if (reset) {
			set(status, "Loading changelog…");
			set(failed, false);
			set(changes, []);
		}
		try {
			const response = await fetch("api/changelog?limit=" + limit, { cache: "no-store" });
			if (!response.ok) throw new Error(String(response.status) + " " + response.statusText);
			const page = changelogPage(await response.json());
			set(changes, page.changes);
			set(hasMore, page.hasMore, true);
			set(failed, false);
			set(status, "Showing " + get(changes).length + " of " + page.total + " commits · newest first");
		} catch (error) {
			set(failed, reset, true);
			if (reset) set(hasMore, false);
			set(status, (reset ? "Changelog unavailable: " : "Could not load older changes: ") + String(error).replace(/^Error:\s*/, ""));
		}
	}
	async function loadMore() {
		if (get(loadingMore) || !get(hasMore)) return;
		set(loadingMore, true);
		set(currentLimit, get(currentLimit) + CHANGELOG_PAGE_SIZE);
		try {
			await load(get(currentLimit));
		} finally {
			set(loadingMore, false);
		}
	}
	async function show() {
		set(presentation, mobile.current ? "stack" : "modal", true);
		set(currentLimit, CHANGELOG_PAGE_SIZE);
		set(open, true);
		await load(get(currentLimit), true);
	}
	function close() {
		set(open, false);
	}
	registerChangelogDialog({
		open: show,
		close
	});
	var $$exports = {
		show,
		close
	};
	var dialog = root_6$5();
	var div = child(dialog);
	var header = child(div);
	var div_1 = child(header);
	var text = only_child(sibling(child(div_1), 2), true);
	reset(div_1);
	var button = sibling(div_1, 2);
	reset(header);
	var ol = sibling(header, 2);
	var node = child(ol);
	var consequent = ($$anchor) => {
		append($$anchor, root$8());
	};
	var consequent_3 = ($$anchor) => {
		var fragment = root_4$6();
		var node_1 = first_child(fragment);
		each(node_1, 17, () => get(changes), (change) => (change.hash || "") + (change.title || ""), ($$anchor, change) => {
			var li_1 = root_2$7();
			var span = child(li_1);
			var text_1 = only_child(span, true);
			var node_2 = sibling(span, 2);
			var consequent_1 = ($$anchor) => {
				var span_1 = root_1$7();
				var text_2 = only_child(span_1);
				template_effect(() => set_text(text_2, `#${get(change).hash ?? ""}`));
				append($$anchor, span_1);
			};
			if_block(node_2, ($$render) => {
				if (get(change).hash) $$render(consequent_1);
			});
			reset(li_1);
			template_effect(() => set_text(text_1, get(change).title || ""));
			append($$anchor, li_1);
		});
		var node_3 = sibling(node_1, 2);
		var consequent_2 = ($$anchor) => {
			var li_2 = root_3$6();
			var button_1 = child(li_2);
			var text_3 = only_child(button_1, true);
			reset(li_2);
			template_effect(() => {
				button_1.disabled = get(loadingMore);
				set_attribute(button_1, "aria-busy", get(loadingMore));
				set_text(text_3, get(loadingMore) ? "Loading older changes…" : "Load older changes");
			});
			delegated("click", button_1, loadMore);
			append($$anchor, li_2);
		};
		if_block(node_3, ($$render) => {
			if (get(hasMore)) $$render(consequent_2);
		});
		append($$anchor, fragment);
	};
	var alternate = ($$anchor) => {
		var li_3 = root_5$5();
		var text_4 = only_child(li_3, true);
		template_effect(($0) => set_text(text_4, $0), [() => get(status).startsWith("Loading") ? "Loading changes…" : "No Git commit history is available."]);
		append($$anchor, li_3);
	};
	if_block(node, ($$render) => {
		if (get(failed)) $$render(consequent);
		else if (get(changes).length) $$render(consequent_3, 1);
		else $$render(alternate, -1);
	});
	reset(ol);
	reset(div);
	reset(dialog);
	attach(dialog, () => dialogVisibility(() => get(open), () => get(presentation) === "modal", close));
	template_effect(() => {
		set_attribute(dialog, "data-presentation", get(presentation));
		set_text(text, get(status));
	});
	delegated("click", dialog, (event) => {
		if (event.target === event.currentTarget && get(presentation) !== "stack") close();
	});
	delegated("click", button, close);
	append($$anchor, dialog);
	return pop($$exports);
}
delegate(["click"]);
//#endregion
//#region src/ui/AttachmentPicker.svelte
init_client();
init_browserAttachments_svelte();
init_uiControllers();
var root$7 = /* @__PURE__ */ from_html(`<span class="attachment-chip"><span> </span> <button type="button" aria-label="Remove attachment">×</button></span>`);
var root_1$6 = /* @__PURE__ */ from_html(`<div class="attachment-menu" id="attachmentMenu" role="menu" tabindex="-1" aria-label="Add attachment"><button type="button" role="menuitem">Upload file</button> <button type="button" role="menuitem">Upload photo</button> <button type="button" role="menuitem">Take photo</button></div>`);
var root_2$6 = /* @__PURE__ */ from_html(`<div class="composer-input-shell"><div class="attachment-chips" id="attachmentChips"></div> <!></div> <div class="composer-tools"><button type="button" class="icon-button attachment-button" id="attachmentButton" aria-label="Add attachment" title="Add file or photo" aria-haspopup="menu" aria-controls="attachmentMenu"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"></path></svg></button> <!> <input id="fileUploadInput" type="file" hidden=""/> <input id="photoUploadInput" type="file" accept="image/*" hidden=""/> <input id="cameraUploadInput" type="file" accept="image/*" capture="environment" hidden=""/></div>`, 1);
function AttachmentPicker($$anchor, $$props) {
	push($$props, true);
	let files = /* @__PURE__ */ state$1([]);
	let menuOpen = /* @__PURE__ */ state$1(false);
	let disabled = /* @__PURE__ */ state$1(false);
	let pickerFocusRequest = /* @__PURE__ */ state$1(0);
	let fileClickRequest = /* @__PURE__ */ state$1(0);
	let photoClickRequest = /* @__PURE__ */ state$1(0);
	let cameraClickRequest = /* @__PURE__ */ state$1(0);
	let options = null;
	function notifyChange() {
		options?.onChange();
	}
	function truncate(value, length = 28) {
		return value.length > length ? value.slice(0, Math.max(1, length - 1)).trimEnd() + "…" : value;
	}
	function add(nextFiles) {
		const next = [...get(files)];
		for (const file of nextFiles) {
			if (next.length >= 5) break;
			if (!next.some((item) => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified)) next.push(file);
		}
		set(files, next);
		notifyChange();
		if (nextFiles.length && next.length >= 5) options?.setStatus("Prompta supports up to 5 attachments per message.");
	}
	function select(kind) {
		set(menuOpen, false);
		if (kind === "file") set(fileClickRequest, get(fileClickRequest) + 1);
		else if (kind === "photo") set(photoClickRequest, get(photoClickRequest) + 1);
		else set(cameraClickRequest, get(cameraClickRequest) + 1);
	}
	function read(event) {
		const input = event.currentTarget;
		const selected = Array.from(input.files || []);
		input.value = "";
		add(selected);
	}
	function payload(file) {
		if (file.size > 26214400) throw new Error(file.name + " is larger than 25 MB");
		return new Promise((resolve, reject) => {
			const reader = new FileReader();
			reader.onerror = () => reject(reader.error || /* @__PURE__ */ new Error("Could not read " + file.name));
			reader.onload = () => {
				const result = typeof reader.result === "string" ? reader.result : "";
				resolve({
					name: file.name,
					type: file.type || "application/octet-stream",
					data: result.slice(result.indexOf(",") + 1)
				});
			};
			reader.readAsDataURL(file);
		});
	}
	function configure(next) {
		options = next;
	}
	function clear() {
		set(files, []);
		notifyChange();
	}
	function closeMenu(restoreFocus = false) {
		set(menuOpen, false);
		if (restoreFocus) set(pickerFocusRequest, get(pickerFocusRequest) + 1);
	}
	function count() {
		return get(files).length;
	}
	function snapshot() {
		return [...get(files)];
	}
	function setDisabled(next) {
		set(disabled, next, true);
		if (next) set(menuOpen, false);
	}
	async function serialize() {
		if (get(files).reduce((total, file) => total + file.size, 0) > 26214400) throw new Error("Attachments exceed the 25 MB Prompta upload limit");
		return Promise.all(get(files).map(payload));
	}
	registerAttachmentPicker({
		configure,
		clear,
		closeMenu,
		count,
		serialize,
		setDisabled,
		snapshot
	});
	var $$exports = {
		configure,
		clear,
		closeMenu,
		count,
		snapshot,
		setDisabled,
		serialize
	};
	var fragment = root_2$6();
	var div = first_child(fragment);
	var div_1 = child(div);
	each(div_1, 23, () => get(files), (file) => file.name + file.size + file.lastModified, ($$anchor, file, index) => {
		var span = root$7();
		var span_1 = child(span);
		var text = only_child(span_1, true);
		var button = sibling(span_1, 2);
		reset(span);
		template_effect(($0) => {
			set_attribute(span, "data-dom-key", "attachment:" + get(index) + ":" + get(file).name);
			set_attribute(span_1, "title", get(file).name);
			set_text(text, $0);
			button.disabled = get(disabled);
		}, [() => truncate(get(file).name)]);
		delegated("click", button, () => {
			set(files, get(files).filter((_, itemIndex) => itemIndex !== get(index)));
			notifyChange();
		});
		append($$anchor, span);
	});
	reset(div_1);
	snippet(sibling(div_1, 2), () => $$props.children);
	reset(div);
	var div_2 = sibling(div, 2);
	var button_1 = child(div_2);
	attach(button_1, () => focusOnRequest(() => get(pickerFocusRequest)));
	var node_1 = sibling(button_1, 2);
	var consequent = ($$anchor) => {
		var div_3 = root_1$6();
		var button_2 = child(div_3);
		var button_3 = sibling(button_2, 2);
		var button_4 = sibling(button_3, 2);
		reset(div_3);
		delegated("keydown", div_3, (event) => {
			if (event.key === "Escape") closeMenu(true);
		});
		delegated("click", button_2, () => select("file"));
		delegated("click", button_3, () => select("photo"));
		delegated("click", button_4, () => select("camera"));
		append($$anchor, div_3);
	};
	if_block(node_1, ($$render) => {
		if (get(menuOpen)) $$render(consequent);
	});
	var input_1 = sibling(node_1, 2);
	attach(input_1, () => clickOnRequest(() => get(fileClickRequest)));
	var input_2 = sibling(input_1, 2);
	attach(input_2, () => clickOnRequest(() => get(photoClickRequest)));
	var input_3 = sibling(input_2, 2);
	attach(input_3, () => clickOnRequest(() => get(cameraClickRequest)));
	reset(div_2);
	attach(div_2, () => clickOutside(() => set(menuOpen, false)));
	template_effect(() => {
		set_attribute(div_1, "hidden", get(files).length === 0);
		set_attribute(button_1, "aria-expanded", get(menuOpen));
		button_1.disabled = get(disabled);
	});
	delegated("click", button_1, () => set(menuOpen, !get(menuOpen)));
	delegated("change", input_1, read);
	delegated("change", input_2, read);
	delegated("change", input_3, read);
	append($$anchor, fragment);
	return pop($$exports);
}
delegate([
	"click",
	"keydown",
	"change"
]);
//#endregion
//#region src/ui/appActions.svelte.ts
var appActions;
var init_appActions_svelte = __esmMin((() => {
	init_client();
	appActions = proxy({
		onSearch: (_value) => {},
		onSidebarFilter: (_filter) => {},
		onMarkAllRead: () => {},
		onNewChat: () => {},
		onPin: () => {},
		onShare: () => {},
		onUnattendedMode: () => {},
		onSubmit: () => {},
		onComposerInput: (_value) => {},
		onApplyUpdate: () => {},
		onHashChange: () => {},
		onPageHide: () => {},
		onPageShow: () => {}
	});
}));
//#endregion
//#region src/ui/appViewState.svelte.ts
function requestComposerFocus(selectEnd = false) {
	appViewState.composerFocusRequest += 1;
	if (selectEnd) appViewState.composerSelectEndRequest += 1;
}
function requestSearchFocus() {
	appViewState.searchFocusRequest += 1;
}
function requestSearchBlur() {
	appViewState.searchBlurRequest += 1;
}
function requestSidebarTop() {
	appViewState.sidebarTopRequest += 1;
}
var appViewState;
var init_appViewState_svelte = __esmMin((() => {
	init_client();
	appViewState = proxy({
		serverDisplay: "",
		serverLabel: "Server · local",
		serverOnline: null,
		live: false,
		liveTitle: "Cache status",
		headingTitle: "Prompta",
		headingMeta: "Local conversation history",
		syncStatus: "local",
		syncLabel: "Local cache",
		cacheSummary: "Reading local cache",
		headLabel: "…",
		headTitle: "View changelog",
		mode: "chats",
		emptyVisible: true,
		conversationVisible: false,
		conversationPinnedToBottom: true,
		chatSwitching: false,
		composerValue: "",
		composerPlaceholder: "Message Prompta…",
		composerDisabled: true,
		composerStatus: "",
		actionToast: "",
		composerAction: "send",
		composerActionDisabled: true,
		shareDisabled: true,
		pinDisabled: true,
		pinActive: false,
		pinLabel: "Pin chat",
		unattended: false,
		unattendedUpdating: false,
		unattendedSendGapSeconds: 60,
		updateAvailable: false,
		updateApplying: false,
		searchValue: "",
		sidebarFilters: {
			unread: false,
			active: false,
			broken: false
		},
		activeSlashCommand: "",
		clockTick: Math.floor(Date.now() / 6e4) * 6e4,
		bootComplete: false,
		composerFocusRequest: 0,
		composerSelectEndRequest: 0,
		searchFocusRequest: 0,
		searchBlurRequest: 0,
		sidebarTopRequest: 0
	});
}));
//#endregion
//#region src/ui/clientLogic.ts
function chatListRequestUrl(search, pinnedIds, limit) {
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
	if (Number.isFinite(limit)) params.set("limit", String(Math.max(1, Math.min(500, Math.floor(Number(limit))))));
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
function sidebarChatLastUserAt(chat) {
	const lastUserAt = Number(chat?.last_user_at || 0);
	if (Number.isFinite(lastUserAt) && lastUserAt > 0) return lastUserAt;
	return sidebarChatCreatedAt(chat);
}
function sidebarChatIsPending(chat) {
	return Boolean(chat?._pending_send || chat?._optimisticNew || chat?._optimisticReply);
}
function pendingConversationStatus(existingStatus, pendingStatus) {
	const current = String(existingStatus || "").trim();
	if (current) return current;
	const pending = String(pendingStatus || "").trim();
	return ["failed", "dead_lettered"].includes(pending) ? pending : "pending";
}
function positiveEpoch(value) {
	const epoch = Number(value || 0);
	return Number.isFinite(epoch) && epoch > 0 ? epoch : 0;
}
function formatRelativeTime(epochSeconds, nowMillis = Date.now()) {
	const epoch = positiveEpoch(epochSeconds);
	if (!epoch) return "";
	const delta = nowMillis - epoch * 1e3;
	const abs = Math.abs(delta);
	if (abs < 45e3) return "now";
	if (abs < 36e5) return `${Math.max(1, Math.round(abs / 6e4))}m`;
	if (abs < 864e5) return `${Math.round(abs / 36e5)}h`;
	if (abs < 6048e5) return `${Math.round(abs / 864e5)}d`;
	return new Intl.DateTimeFormat(void 0, {
		month: "short",
		day: "numeric"
	}).format(/* @__PURE__ */ new Date(epoch * 1e3));
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
function sidebarHealthNeedsRefresh(rows, chats, brokenFilterActive = false, nowSeconds = Date.now() / 1e3) {
	if (brokenFilterActive) return true;
	const chatsById = new Map(chats.map((chat) => [String(chat.id || ""), chat]));
	return rows.some((row) => {
		const chat = chatsById.get(String(row.id || ""));
		return Boolean(chat) && row.broken !== chatIsBroken(chat, nowSeconds);
	});
}
function sidebarChatMatchesFilters(chat, filters, nowSeconds = Date.now() / 1e3) {
	if (!filters.unread && !filters.active && !filters.broken) return true;
	if (!chat) return false;
	return filters.unread && Boolean(chat.unread) || filters.active && chat.status === "active" || filters.broken && chatIsBroken(chat, nowSeconds);
}
function sidebarSelectedConversationId(selectedId, composingNew, pendingNewDisplayId) {
	const pendingId = String(pendingNewDisplayId || "");
	if (composingNew && pendingId) return pendingId;
	return String(selectedId || "");
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
		const userActivityDelta = sidebarChatLastUserAt(right) - sidebarChatLastUserAt(left);
		if (userActivityDelta) return userActivityDelta;
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
function queueEtaText(seconds) {
	const value = Number(seconds);
	if (!Number.isFinite(value) || value <= 0) return "<1m";
	const minutes = Math.max(1, Math.ceil(value / 60));
	if (minutes < 60) return String(minutes) + "m";
	const hours = Math.floor(minutes / 60);
	const remainingMinutes = minutes % 60;
	if (hours < 24) return remainingMinutes ? hours + "h " + remainingMinutes + "m" : hours + "h";
	const days = Math.floor(hours / 24);
	const remainingHours = hours % 24;
	return remainingHours ? days + "d " + remainingHours + "h" : days + "d";
}
function retryDelayText(seconds) {
	const value = Number(seconds);
	if (!Number.isFinite(value) || value <= 0) return "soon";
	if (value < 60) return "<1m";
	const minutes = Math.ceil(value / 60);
	if (minutes < 60) return `${minutes}m`;
	return `${Math.ceil(minutes / 60)}h`;
}
function pendingSendActivity(status, hasSendId, retryAfterSeconds = 0, retryAtEpoch = 0, nowEpoch = Date.now() / 1e3, queuePosition = 0, queueEtaAtEpoch = 0) {
	const normalized = textValue(status, "queued").trim().toLowerCase();
	if (["failed", "dead_lettered"].includes(normalized)) return null;
	if (!hasSendId) return {
		label: "sending",
		statusText: "Sending…"
	};
	if (normalized === "queued") {
		const position = Number(queuePosition);
		if (Number.isFinite(position) && position > 0) {
			const queueLabel = "queued · #" + Math.floor(position);
			const statusLabel = "Queued in Prompta · #" + Math.floor(position);
			const etaAt = Number(queueEtaAtEpoch);
			const now = Number(nowEpoch);
			const etaRemaining = Number.isFinite(etaAt) && etaAt > 0 && Number.isFinite(now) ? Math.max(0, etaAt - now) : 0;
			const eta = etaRemaining > 0 ? " · ETA ~" + queueEtaText(etaRemaining) : "";
			return {
				label: queueLabel + eta,
				statusText: statusLabel + eta
			};
		}
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
			last_user_at: Number.isFinite(createdAt) ? createdAt : 0,
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
function isUnresolvedPendingNewConversation(pending, conversationId) {
	if (!pending || !conversationId) return false;
	return String(pending.status || "").trim().toLowerCase() !== "succeeded" && pendingConversationDisplayId(pending) === conversationId;
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
	const delayedCandidates = [];
	const earliestPendingTime = Math.min(...pendingTimes);
	for (let index = 0; index < messages.length; index += 1) {
		if (claimedIndexes.has(index)) continue;
		const message = messages[index];
		if (message.role !== "user" || comparablePrompt(message.content) !== content) continue;
		const messageTime = comparableTimestampSeconds(message.created_at || message.updated_at);
		if (messageTime <= 0) continue;
		const distance = Math.min(...pendingTimes.map((pendingTime) => Math.abs(messageTime - pendingTime)));
		if (distance <= 30 && distance < bestDistance) {
			bestIndex = index;
			bestDistance = distance;
		}
		if (messageTime >= earliestPendingTime - 30) delayedCandidates.push(index);
	}
	if (bestIndex >= 0) return bestIndex;
	return delayedCandidates[0] ?? -1;
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
function isPostJsonTransportError(error) {
	return error instanceof PostJsonTransportError;
}
async function postJsonRequest(url, payload, attempts = 1, timeoutMs = 45e3, fetchImpl = fetch) {
	let lastError = /* @__PURE__ */ new Error("Request failed");
	for (let attempt = 0; attempt < Math.max(1, attempts); attempt += 1) {
		const controller = new AbortController();
		const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
		let response;
		let data = {};
		try {
			try {
				response = await fetchImpl(url, {
					method: "POST",
					cache: "no-store",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify(payload),
					signal: controller.signal
				});
			} catch (error) {
				throw new PostJsonTransportError(controller.signal.aborted ? "Request timed out" : error instanceof Error ? error.message : String(error));
			}
			try {
				data = await response.json();
			} catch {
				if (controller.signal.aborted) throw new PostJsonTransportError("Request timed out");
				if (response.ok) throw new Error("Prompta returned an invalid response");
			}
		} catch (error) {
			lastError = error instanceof Error ? error : new Error(String(error));
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
	return ["interrupted", "unattended"].includes(textValue(chatStatus).trim().toLowerCase());
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
var BROKEN_CHAT_AFTER_SECONDS, CHATGPT_RICH_START, CHATGPT_RICH_END, CHATGPT_RICH_SEPARATOR, TOOL_UI_NOISE, PostJsonTransportError;
var init_clientLogic = __esmMin((() => {
	BROKEN_CHAT_AFTER_SECONDS = 2400;
	CHATGPT_RICH_START = "";
	CHATGPT_RICH_END = "";
	CHATGPT_RICH_SEPARATOR = "";
	TOOL_UI_NOISE = /^(?:open tool call list|close tool call list|tool|tool call|expand|collapse|cot-v5-[\w-]+)$/i;
	PostJsonTransportError = class extends Error {
		constructor(message) {
			super(message);
			this.name = "PostJsonTransportError";
		}
	};
}));
//#endregion
//#region src/ui/Composer.svelte
init_client();
init_index_client();
init_appActions_svelte();
init_appViewState_svelte();
init_browserAttachments_svelte();
init_clientLogic();
var root$6 = /* @__PURE__ */ from_html(`<button type="button" class="composer-jump-latest-button" aria-label="Jump to latest message" title="Jump to latest message"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 5v14m-6-6 6 6 6-6"></path></svg> <span>Latest</span></button>`);
var root_1$5 = /* @__PURE__ */ from_html(`<button type="button" role="option"><strong> </strong><span> </span></button>`);
var root_2$5 = /* @__PURE__ */ from_html(`<div class="slash-menu" id="slashMenu" role="listbox" tabindex="-1" aria-label="Prompta commands"></div>`);
var root_3$5 = /* @__PURE__ */ from_html(`<textarea id="messageInput" rows="1" aria-label="Message Prompta" role="combobox" aria-controls="slashMenu" aria-autocomplete="list" aria-haspopup="listbox"></textarea> <!>`, 1);
var root_4$5 = /* @__PURE__ */ from_svg(`<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7.5" y="7.5" width="9" height="9" rx="1.5" fill="currentColor" stroke="none"></rect></svg>`);
var root_5$4 = /* @__PURE__ */ from_svg(`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6"></path></svg>`);
var root_6$4 = /* @__PURE__ */ from_html(`<footer class="composer-footer" id="composerFooter"><!> <form class="composer-bar" id="messageForm"><!> <div class="composer-submit"><button type="button" class="icon-button composer-new-chat-button" id="newChatButton" aria-label="Start a new chat" title="New chat"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 4H7a4 4 0 0 0-4 4v8a4 4 0 0 0 4 4h8l4 2v-7"></path><path d="M18 3v6M15 6h6"></path></svg></button> <button type="submit" class="send-button" id="sendButton"><!></button></div></form> <div class="composer-status" id="composerStatus"> </div></footer>`);
function Composer($$anchor, $$props) {
	push($$props, true);
	const commands = [
		{
			command: "/add ",
			name: "/add",
			description: "Add a repeating scheduled job",
			id: "slashCommandAdd"
		},
		{
			command: "/list",
			name: "/list",
			description: "List and manage scheduled jobs",
			id: "slashCommandList"
		},
		{
			command: "/logs",
			name: "/logs",
			description: "View Prompta service logs",
			id: "slashCommandLogs"
		},
		{
			command: "/at ",
			name: "/at",
			description: "Run a prompt at a date and time",
			id: "slashCommandAt"
		}
	];
	const mobileInput = new MediaQuery("(max-width: 780px), (pointer: coarse)");
	let slashDismissed = /* @__PURE__ */ state$1(false);
	const visibleCommands = /* @__PURE__ */ user_derived(() => {
		const value = appViewState.composerValue;
		const firstToken = value.split(/\s/, 1)[0].toLowerCase();
		return !get(slashDismissed) && value.startsWith("/") && !value.includes("\n") && !value.includes(" ") ? commands.filter((item) => item.command.trim().toLowerCase().startsWith(firstToken)) : [];
	});
	const slashOpen = /* @__PURE__ */ user_derived(() => get(visibleCommands).length > 0);
	const activeCommand = /* @__PURE__ */ user_derived(() => get(visibleCommands).find((item) => item.command === appViewState.activeSlashCommand) ?? get(visibleCommands)[0] ?? null);
	function insertSlashCommand(command) {
		set(slashDismissed, true);
		appViewState.activeSlashCommand = "";
		appViewState.composerValue = command;
		appActions.onComposerInput(command);
		requestComposerFocus(true);
	}
	function moveSlashSelection(direction) {
		if (!get(visibleCommands).length) return;
		const currentIndex = get(visibleCommands).findIndex((item) => item.command === (get(activeCommand)?.command ?? ""));
		const nextIndex = nextSlashCommandIndex(get(visibleCommands).length, currentIndex, direction);
		appViewState.activeSlashCommand = get(visibleCommands)[nextIndex]?.command ?? "";
	}
	function handleInput() {
		set(slashDismissed, false);
		appViewState.activeSlashCommand = "";
		appActions.onComposerInput(appViewState.composerValue);
	}
	function handleKeydown(event) {
		if (get(slashOpen)) {
			if (event.key === "ArrowDown" || event.key === "ArrowUp") {
				event.preventDefault();
				moveSlashSelection(event.key === "ArrowUp" ? -1 : 1);
				return;
			}
			if (event.key === "Tab" || event.key === "Enter" && !event.isComposing) {
				if (get(activeCommand)) {
					event.preventDefault();
					insertSlashCommand(get(activeCommand).command);
					return;
				}
			}
			if (event.key === "Escape") {
				event.preventDefault();
				event.stopPropagation();
				set(slashDismissed, true);
				appViewState.activeSlashCommand = "";
				return;
			}
		}
		if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !mobileInput.current) {
			event.preventDefault();
			appActions.onSubmit();
		}
	}
	var footer = root_6$4();
	var node = child(footer);
	var consequent = ($$anchor) => {
		var button = root$6();
		delegated("click", button, function(...$$args) {
			scrollConversationToBottom?.apply(this, $$args);
		});
		append($$anchor, button);
	};
	if_block(node, ($$render) => {
		if (appViewState.conversationVisible && !appViewState.conversationPinnedToBottom) $$render(consequent);
	});
	var form = sibling(node, 2);
	var node_1 = child(form);
	AttachmentPicker(node_1, {
		children: ($$anchor, $$slotProps) => {
			var fragment = root_3$5();
			var textarea = first_child(fragment);
			remove_textarea_child(textarea);
			attach(textarea, () => composerTextarea(() => appViewState.composerValue, () => appViewState.composerFocusRequest, () => appViewState.composerSelectEndRequest));
			var node_2 = sibling(textarea, 2);
			var consequent_1 = ($$anchor) => {
				var div = root_2$5();
				each(div, 21, () => get(visibleCommands), (item) => item.command, ($$anchor, item) => {
					var button_1 = root_1$5();
					var strong = child(button_1);
					var text = only_child(strong, true);
					var text_1 = only_child(sibling(strong), true);
					reset(button_1);
					template_effect(() => {
						set_attribute(button_1, "id", get(item).id);
						set_attribute(button_1, "aria-selected", get(activeCommand)?.command === get(item).command);
						set_text(text, get(item).name);
						set_text(text_1, get(item).description);
					});
					delegated("pointermove", button_1, () => appViewState.activeSlashCommand = get(item).command);
					delegated("click", button_1, () => void insertSlashCommand(get(item).command));
					append($$anchor, button_1);
				});
				reset(div);
				append($$anchor, div);
			};
			if_block(node_2, ($$render) => {
				if (get(slashOpen)) $$render(consequent_1);
			});
			template_effect(() => {
				set_attribute(textarea, "placeholder", appViewState.composerPlaceholder);
				set_attribute(textarea, "aria-expanded", get(slashOpen));
				set_attribute(textarea, "aria-activedescendant", get(slashOpen) && get(activeCommand) ? get(activeCommand).id : void 0);
				textarea.disabled = appViewState.composerDisabled;
			});
			delegated("input", textarea, handleInput);
			delegated("keydown", textarea, handleKeydown);
			bind_value(textarea, () => appViewState.composerValue, ($$value) => appViewState.composerValue = $$value);
			append($$anchor, fragment);
		},
		$$slots: { default: true }
	});
	var div_1 = sibling(node_1, 2);
	var button_2 = child(div_1);
	var button_3 = sibling(button_2, 2);
	var node_3 = child(button_3);
	var consequent_2 = ($$anchor) => {
		append($$anchor, root_4$5());
	};
	var alternate = ($$anchor) => {
		append($$anchor, root_5$4());
	};
	if_block(node_3, ($$render) => {
		if (appViewState.composerAction === "stop") $$render(consequent_2);
		else $$render(alternate, -1);
	});
	reset(button_3);
	reset(div_1);
	reset(form);
	var text_2 = only_child(sibling(form, 2), true);
	reset(footer);
	template_effect(() => {
		set_attribute(button_3, "data-action", appViewState.composerAction);
		set_attribute(button_3, "aria-label", appViewState.composerAction === "stop" ? "Stop response" : "Send message");
		set_attribute(button_3, "title", appViewState.composerAction === "stop" ? "Stop response" : "Send message");
		button_3.disabled = appViewState.composerActionDisabled;
		set_text(text_2, appViewState.composerStatus);
	});
	event("submit", form, (event) => {
		event.preventDefault();
		appActions.onSubmit();
	});
	delegated("click", button_2, function(...$$args) {
		appActions.onNewChat?.apply(this, $$args);
	});
	append($$anchor, footer);
	pop();
}
delegate([
	"click",
	"input",
	"keydown",
	"pointermove"
]);
//#endregion
//#region src/ui/clipboard.ts
async function copyText(value) {
	try {
		await navigator.clipboard.writeText(value);
		return true;
	} catch {
		return false;
	}
}
var init_clipboard = __esmMin((() => {}));
//#endregion
//#region node_modules/highlight.js/es/languages/bash.js
init_clipboard();
/** @type LanguageFn */
function bash(hljs) {
	const regex = hljs.regex;
	const VAR = {};
	const BRACED_VAR = {
		begin: /\$\{/,
		end: /\}/,
		contains: ["self", {
			begin: /:-/,
			contains: [VAR]
		}]
	};
	Object.assign(VAR, {
		className: "variable",
		variants: [{ begin: regex.concat(/\$[\w\d#@][\w\d_]*/, `(?![\\w\\d])(?![$])`) }, BRACED_VAR]
	});
	const SUBST = {
		className: "subst",
		begin: /\$\(/,
		end: /\)/,
		contains: [hljs.BACKSLASH_ESCAPE]
	};
	const COMMENT = hljs.inherit(hljs.COMMENT(), {
		match: [/(^|\s)/, /#.*$/],
		scope: { 2: "comment" }
	});
	const HERE_DOC = {
		begin: /<<-?\s*(?=\w+)/,
		starts: { contains: [hljs.END_SAME_AS_BEGIN({
			begin: /(\w+)/,
			end: /(\w+)/,
			className: "string"
		})] }
	};
	const QUOTE_STRING = {
		className: "string",
		begin: /"/,
		end: /"/,
		contains: [
			hljs.BACKSLASH_ESCAPE,
			VAR,
			SUBST
		]
	};
	SUBST.contains.push(QUOTE_STRING);
	const ESCAPED_QUOTE = { match: /\\"/ };
	const APOS_STRING = {
		className: "string",
		begin: /'/,
		end: /'/
	};
	const ESCAPED_APOS = { match: /\\'/ };
	const ARITHMETIC = {
		begin: /\$?\(\(/,
		end: /\)\)/,
		contains: [
			{
				begin: /\d+#[0-9a-f]+/,
				className: "number"
			},
			hljs.NUMBER_MODE,
			VAR
		]
	};
	const KNOWN_SHEBANG = hljs.SHEBANG({
		binary: `(${[
			"fish",
			"bash",
			"zsh",
			"sh",
			"csh",
			"ksh",
			"tcsh",
			"dash",
			"scsh"
		].join("|")})`,
		relevance: 10
	});
	const FUNCTION = {
		className: "function",
		begin: /\w[\w\d_]*\s*\(\s*\)\s*\{/,
		returnBegin: true,
		contains: [hljs.inherit(hljs.TITLE_MODE, { begin: /\w[\w\d_]*/ })],
		relevance: 0
	};
	const KEYWORDS = [
		"if",
		"then",
		"else",
		"elif",
		"fi",
		"time",
		"for",
		"while",
		"until",
		"in",
		"do",
		"done",
		"case",
		"esac",
		"coproc",
		"function",
		"select"
	];
	const LITERALS = ["true", "false"];
	const PATH_MODE = { match: /(\/[a-z._-]+)+/ };
	const SHELL_BUILT_INS = [
		"break",
		"cd",
		"continue",
		"eval",
		"exec",
		"exit",
		"export",
		"getopts",
		"hash",
		"pwd",
		"readonly",
		"return",
		"shift",
		"test",
		"times",
		"trap",
		"umask",
		"unset"
	];
	const BASH_BUILT_INS = [
		"alias",
		"bind",
		"builtin",
		"caller",
		"command",
		"declare",
		"echo",
		"enable",
		"help",
		"let",
		"local",
		"logout",
		"mapfile",
		"printf",
		"read",
		"readarray",
		"source",
		"sudo",
		"type",
		"typeset",
		"ulimit",
		"unalias"
	];
	const ZSH_BUILT_INS = [
		"autoload",
		"bg",
		"bindkey",
		"bye",
		"cap",
		"chdir",
		"clone",
		"comparguments",
		"compcall",
		"compctl",
		"compdescribe",
		"compfiles",
		"compgroups",
		"compquote",
		"comptags",
		"comptry",
		"compvalues",
		"dirs",
		"disable",
		"disown",
		"echotc",
		"echoti",
		"emulate",
		"fc",
		"fg",
		"float",
		"functions",
		"getcap",
		"getln",
		"history",
		"integer",
		"jobs",
		"kill",
		"limit",
		"log",
		"noglob",
		"popd",
		"print",
		"pushd",
		"pushln",
		"rehash",
		"sched",
		"setcap",
		"setopt",
		"stat",
		"suspend",
		"ttyctl",
		"unfunction",
		"unhash",
		"unlimit",
		"unsetopt",
		"vared",
		"wait",
		"whence",
		"where",
		"which",
		"zcompile",
		"zformat",
		"zftp",
		"zle",
		"zmodload",
		"zparseopts",
		"zprof",
		"zpty",
		"zregexparse",
		"zsocket",
		"zstyle",
		"ztcp"
	];
	const GNU_CORE_UTILS = [
		"chcon",
		"chgrp",
		"chown",
		"chmod",
		"cp",
		"dd",
		"df",
		"dir",
		"dircolors",
		"ln",
		"ls",
		"mkdir",
		"mkfifo",
		"mknod",
		"mktemp",
		"mv",
		"realpath",
		"rm",
		"rmdir",
		"shred",
		"sync",
		"touch",
		"truncate",
		"vdir",
		"b2sum",
		"base32",
		"base64",
		"cat",
		"cksum",
		"comm",
		"csplit",
		"cut",
		"expand",
		"fmt",
		"fold",
		"head",
		"join",
		"md5sum",
		"nl",
		"numfmt",
		"od",
		"paste",
		"ptx",
		"pr",
		"sha1sum",
		"sha224sum",
		"sha256sum",
		"sha384sum",
		"sha512sum",
		"shuf",
		"sort",
		"split",
		"sum",
		"tac",
		"tail",
		"tr",
		"tsort",
		"unexpand",
		"uniq",
		"wc",
		"arch",
		"basename",
		"chroot",
		"date",
		"dirname",
		"du",
		"echo",
		"env",
		"expr",
		"factor",
		"groups",
		"hostid",
		"id",
		"link",
		"logname",
		"nice",
		"nohup",
		"nproc",
		"pathchk",
		"pinky",
		"printenv",
		"printf",
		"pwd",
		"readlink",
		"runcon",
		"seq",
		"sleep",
		"stat",
		"stdbuf",
		"stty",
		"tee",
		"test",
		"timeout",
		"tty",
		"uname",
		"unlink",
		"uptime",
		"users",
		"who",
		"whoami",
		"yes"
	];
	return {
		name: "Bash",
		aliases: ["sh", "zsh"],
		keywords: {
			$pattern: /\b[a-z][a-z0-9._-]+\b/,
			keyword: KEYWORDS,
			literal: LITERALS,
			built_in: [
				...SHELL_BUILT_INS,
				...BASH_BUILT_INS,
				"set",
				"shopt",
				...ZSH_BUILT_INS,
				...GNU_CORE_UTILS
			]
		},
		contains: [
			KNOWN_SHEBANG,
			hljs.SHEBANG(),
			FUNCTION,
			ARITHMETIC,
			COMMENT,
			HERE_DOC,
			PATH_MODE,
			QUOTE_STRING,
			ESCAPED_QUOTE,
			APOS_STRING,
			ESCAPED_APOS,
			VAR
		]
	};
}
//#endregion
//#region node_modules/highlight.js/es/languages/cpp.js
/** @type LanguageFn */
function cpp(hljs) {
	const regex = hljs.regex;
	const C_LINE_COMMENT_MODE = hljs.COMMENT("//", "$", { contains: [{ begin: /\\\n/ }] });
	const DECLTYPE_AUTO_RE = "decltype\\(auto\\)";
	const NAMESPACE_RE = "[a-zA-Z_]\\w*::";
	const FUNCTION_TYPE_RE = "(?!struct)(decltype\\(auto\\)|" + regex.optional(NAMESPACE_RE) + "[a-zA-Z_]\\w*" + regex.optional("<[^<>]+>") + ")";
	const CPP_PRIMITIVE_TYPES = {
		className: "type",
		begin: "\\b[a-z\\d_]*_t\\b"
	};
	const STRINGS = {
		className: "string",
		variants: [
			{
				begin: "(u8?|U|L)?\"",
				end: "\"",
				illegal: "\\n",
				contains: [hljs.BACKSLASH_ESCAPE]
			},
			{
				begin: "(u8?|U|L)?'(\\\\(x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4,8}|[0-7]{3}|\\S)|.)",
				end: "'",
				illegal: "."
			},
			hljs.END_SAME_AS_BEGIN({
				begin: /(?:u8?|U|L)?R"([^()\\\s"]{0,16})\(/,
				end: /\)([^()\\\s"]{0,16})"/
			})
		]
	};
	const NUMBERS = {
		className: "number",
		variants: [{ begin: "[+-]?(?:(?:\\b[0-9](?:'?[0-9])*\\.(?:[0-9](?:'?[0-9])*)?|\\.[0-9](?:'?[0-9])*)(?:[Ee][+-]?[0-9](?:'?[0-9])*)?|\\b[0-9](?:'?[0-9])*[Ee][+-]?[0-9](?:'?[0-9])*|\\b0[Xx](?:[0-9A-Fa-f](?:'?[0-9A-Fa-f])*(?:\\.(?:[0-9A-Fa-f](?:'?[0-9A-Fa-f])*)?)?|\\.[0-9A-Fa-f](?:'?[0-9A-Fa-f])*)[Pp][+-]?[0-9](?:'?[0-9])*)(?:[Ff](?:16|32|64|128)?|(BF|bf)16|[Ll]|)" }, { begin: "[+-]?\\b(?:0[Bb][01](?:'?[01])*|0[Xx][0-9A-Fa-f](?:'?[0-9A-Fa-f])*|0(?:'?[0-7])*|[1-9](?:'?[0-9])*)(?:[Uu](?:LL?|ll?)|[Uu][Zz]?|(?:LL?|ll?)[Uu]?|[Zz][Uu]|)" }],
		relevance: 0
	};
	const PREPROCESSORS = [{
		scope: "meta",
		begin: /#\s*include\b/,
		end: /$/,
		keywords: { keyword: "include" },
		contains: [
			{ begin: /\\\n/ },
			STRINGS,
			{
				scope: "string",
				begin: /<.*?>/
			},
			C_LINE_COMMENT_MODE,
			hljs.C_BLOCK_COMMENT_MODE
		]
	}, {
		className: "meta",
		begin: /#\s*[a-z]+\b/,
		end: /$/,
		keywords: { keyword: "if else elif endif define undef warning error line pragma _Pragma ifdef ifndef include" },
		contains: [
			{
				begin: /\\\n/,
				relevance: 0
			},
			hljs.inherit(STRINGS, { className: "string" }),
			C_LINE_COMMENT_MODE,
			hljs.C_BLOCK_COMMENT_MODE
		]
	}];
	const TITLE_MODE = {
		className: "title",
		begin: regex.optional(NAMESPACE_RE) + hljs.IDENT_RE,
		relevance: 0
	};
	const FUNCTION_TITLE = regex.optional(NAMESPACE_RE) + hljs.IDENT_RE + "\\s*\\(";
	const RESERVED_KEYWORDS = [
		"alignas",
		"alignof",
		"and",
		"and_eq",
		"asm",
		"atomic_cancel",
		"atomic_commit",
		"atomic_noexcept",
		"auto",
		"bitand",
		"bitor",
		"break",
		"case",
		"catch",
		"class",
		"co_await",
		"co_return",
		"co_yield",
		"compl",
		"concept",
		"const_cast|10",
		"consteval",
		"constexpr",
		"constinit",
		"continue",
		"decltype",
		"default",
		"delete",
		"do",
		"dynamic_cast|10",
		"else",
		"enum",
		"explicit",
		"export",
		"extern",
		"false",
		"final",
		"for",
		"friend",
		"goto",
		"if",
		"import",
		"inline",
		"module",
		"mutable",
		"namespace",
		"new",
		"noexcept",
		"not",
		"not_eq",
		"nullptr",
		"operator",
		"or",
		"or_eq",
		"override",
		"private",
		"protected",
		"public",
		"reflexpr",
		"register",
		"reinterpret_cast|10",
		"requires",
		"return",
		"sizeof",
		"static_assert",
		"static_cast|10",
		"struct",
		"switch",
		"synchronized",
		"template",
		"this",
		"thread_local",
		"throw",
		"transaction_safe",
		"transaction_safe_dynamic",
		"true",
		"try",
		"typedef",
		"typeid",
		"typename",
		"union",
		"using",
		"virtual",
		"volatile",
		"while",
		"xor",
		"xor_eq"
	];
	const RESERVED_TYPES = [
		"bool",
		"char",
		"char16_t",
		"char32_t",
		"char8_t",
		"double",
		"float",
		"int",
		"long",
		"short",
		"void",
		"wchar_t",
		"unsigned",
		"signed",
		"const",
		"static"
	];
	const TYPE_HINTS = [
		"any",
		"auto_ptr",
		"barrier",
		"binary_semaphore",
		"bitset",
		"complex",
		"condition_variable",
		"condition_variable_any",
		"counting_semaphore",
		"deque",
		"false_type",
		"flat_map",
		"flat_set",
		"future",
		"imaginary",
		"initializer_list",
		"istringstream",
		"jthread",
		"latch",
		"lock_guard",
		"multimap",
		"multiset",
		"mutex",
		"optional",
		"ostringstream",
		"packaged_task",
		"pair",
		"promise",
		"priority_queue",
		"queue",
		"recursive_mutex",
		"recursive_timed_mutex",
		"scoped_lock",
		"set",
		"shared_future",
		"shared_lock",
		"shared_mutex",
		"shared_timed_mutex",
		"shared_ptr",
		"stack",
		"string_view",
		"stringstream",
		"timed_mutex",
		"thread",
		"true_type",
		"tuple",
		"unique_lock",
		"unique_ptr",
		"unordered_map",
		"unordered_multimap",
		"unordered_multiset",
		"unordered_set",
		"variant",
		"vector",
		"weak_ptr",
		"wstring",
		"wstring_view"
	];
	const FUNCTION_HINTS = [
		"abort",
		"abs",
		"acos",
		"apply",
		"as_const",
		"asin",
		"atan",
		"atan2",
		"calloc",
		"ceil",
		"cerr",
		"cin",
		"clog",
		"cos",
		"cosh",
		"cout",
		"declval",
		"endl",
		"exchange",
		"exit",
		"exp",
		"fabs",
		"floor",
		"fmod",
		"forward",
		"fprintf",
		"fputs",
		"free",
		"frexp",
		"fscanf",
		"future",
		"invoke",
		"isalnum",
		"isalpha",
		"iscntrl",
		"isdigit",
		"isgraph",
		"islower",
		"isprint",
		"ispunct",
		"isspace",
		"isupper",
		"isxdigit",
		"labs",
		"launder",
		"ldexp",
		"log",
		"log10",
		"make_pair",
		"make_shared",
		"make_shared_for_overwrite",
		"make_tuple",
		"make_unique",
		"malloc",
		"memchr",
		"memcmp",
		"memcpy",
		"memset",
		"modf",
		"move",
		"pow",
		"printf",
		"putchar",
		"puts",
		"realloc",
		"scanf",
		"sin",
		"sinh",
		"snprintf",
		"sprintf",
		"sqrt",
		"sscanf",
		"std",
		"stderr",
		"stdin",
		"stdout",
		"strcat",
		"strchr",
		"strcmp",
		"strcpy",
		"strcspn",
		"strlen",
		"strncat",
		"strncmp",
		"strncpy",
		"strpbrk",
		"strrchr",
		"strspn",
		"strstr",
		"swap",
		"tan",
		"tanh",
		"terminate",
		"to_underlying",
		"tolower",
		"toupper",
		"vfprintf",
		"visit",
		"vprintf",
		"vsprintf"
	];
	const CPP_KEYWORDS = {
		type: RESERVED_TYPES,
		keyword: RESERVED_KEYWORDS,
		literal: [
			"NULL",
			"false",
			"nullopt",
			"nullptr",
			"true"
		],
		built_in: ["_Pragma"],
		_type_hints: TYPE_HINTS
	};
	const FUNCTION_DISPATCH = {
		className: "function.dispatch",
		relevance: 0,
		keywords: { _hint: FUNCTION_HINTS },
		begin: regex.concat(/\b/, `(?!${RESERVED_KEYWORDS.join("|")})`, hljs.IDENT_RE, regex.lookahead(/(<[^<>]+>|)\s*\(/))
	};
	const EXPRESSION_CONTAINS = [
		FUNCTION_DISPATCH,
		...PREPROCESSORS,
		CPP_PRIMITIVE_TYPES,
		C_LINE_COMMENT_MODE,
		hljs.C_BLOCK_COMMENT_MODE,
		NUMBERS,
		STRINGS
	];
	const EXPRESSION_CONTEXT = {
		variants: [
			{
				begin: /=/,
				end: /;/
			},
			{
				begin: /\(/,
				end: /\)/
			},
			{
				beginKeywords: "new throw return else",
				end: /;/
			}
		],
		keywords: CPP_KEYWORDS,
		contains: EXPRESSION_CONTAINS.concat([{
			begin: /\(/,
			end: /\)/,
			keywords: CPP_KEYWORDS,
			contains: EXPRESSION_CONTAINS.concat(["self"]),
			relevance: 0
		}]),
		relevance: 0
	};
	const FUNCTION_DECLARATION = {
		className: "function",
		begin: "(" + FUNCTION_TYPE_RE + "[\\*&\\s]+){1,12}" + FUNCTION_TITLE,
		returnBegin: true,
		end: /[{;=]/,
		excludeEnd: true,
		keywords: CPP_KEYWORDS,
		illegal: /[^\w\s\*&:<>.]/,
		contains: [
			{
				begin: DECLTYPE_AUTO_RE,
				keywords: CPP_KEYWORDS,
				relevance: 0
			},
			{
				begin: FUNCTION_TITLE,
				returnBegin: true,
				contains: [TITLE_MODE],
				relevance: 0
			},
			{
				begin: /::/,
				relevance: 0
			},
			{
				begin: /:/,
				endsWithParent: true,
				contains: [STRINGS, NUMBERS]
			},
			{
				relevance: 0,
				match: /,/
			},
			{
				className: "params",
				begin: /\(/,
				end: /\)/,
				keywords: CPP_KEYWORDS,
				relevance: 0,
				contains: [
					C_LINE_COMMENT_MODE,
					hljs.C_BLOCK_COMMENT_MODE,
					STRINGS,
					NUMBERS,
					CPP_PRIMITIVE_TYPES,
					{
						begin: /\(/,
						end: /\)/,
						keywords: CPP_KEYWORDS,
						relevance: 0,
						contains: [
							"self",
							C_LINE_COMMENT_MODE,
							hljs.C_BLOCK_COMMENT_MODE,
							STRINGS,
							NUMBERS,
							CPP_PRIMITIVE_TYPES
						]
					}
				]
			},
			CPP_PRIMITIVE_TYPES,
			C_LINE_COMMENT_MODE,
			hljs.C_BLOCK_COMMENT_MODE,
			...PREPROCESSORS
		]
	};
	return {
		name: "C++",
		aliases: [
			"cc",
			"c++",
			"h++",
			"hpp",
			"hh",
			"hxx",
			"cxx"
		],
		keywords: CPP_KEYWORDS,
		illegal: "</",
		classNameAliases: { "function.dispatch": "built_in" },
		contains: [].concat(EXPRESSION_CONTEXT, FUNCTION_DECLARATION, FUNCTION_DISPATCH, EXPRESSION_CONTAINS, [
			...PREPROCESSORS,
			{
				begin: "\\b(deque|list|queue|priority_queue|pair|stack|vector|map|set|bitset|multiset|multimap|unordered_map|unordered_set|unordered_multiset|unordered_multimap|array|tuple|optional|variant|function|flat_map|flat_set)\\s*<(?!<)",
				end: ">",
				keywords: CPP_KEYWORDS,
				contains: ["self", CPP_PRIMITIVE_TYPES]
			},
			{
				begin: hljs.IDENT_RE + "::",
				keywords: CPP_KEYWORDS
			},
			{
				match: [
					/\b(?:enum(?:\s+(?:class|struct))?|class|struct|union)/,
					/\s+/,
					/\w+/
				],
				className: {
					1: "keyword",
					3: "title.class"
				}
			}
		])
	};
}
//#endregion
//#region node_modules/highlight.js/es/languages/dart.js
/** @type LanguageFn */
function dart(hljs) {
	const regex = hljs.regex;
	const SUBST = {
		className: "subst",
		variants: [{ begin: "\\$[A-Za-z0-9_]+" }]
	};
	const BRACED_SUBST = {
		className: "subst",
		variants: [{
			begin: /\$\{/,
			end: /\}/
		}],
		keywords: "true false null this is new super"
	};
	const NUMBER = {
		className: "number",
		relevance: 0,
		variants: [{ match: /\b[0-9][0-9_]*(\.[0-9][0-9_]*)?([eE][+-]?[0-9][0-9_]*)?\b/ }, { match: /\b0[xX][0-9A-Fa-f][0-9A-Fa-f_]*\b/ }]
	};
	const STRING = {
		className: "string",
		variants: [
			{
				begin: "r'''",
				end: "'''"
			},
			{
				begin: "r\"\"\"",
				end: "\"\"\""
			},
			{
				begin: "r'",
				end: "'",
				illegal: "\\n"
			},
			{
				begin: "r\"",
				end: "\"",
				illegal: "\\n"
			},
			{
				begin: "'''",
				end: "'''",
				contains: [
					hljs.BACKSLASH_ESCAPE,
					SUBST,
					BRACED_SUBST
				]
			},
			{
				begin: "\"\"\"",
				end: "\"\"\"",
				contains: [
					hljs.BACKSLASH_ESCAPE,
					SUBST,
					BRACED_SUBST
				]
			},
			{
				begin: "'",
				end: "'",
				illegal: "\\n",
				contains: [
					hljs.BACKSLASH_ESCAPE,
					SUBST,
					BRACED_SUBST
				]
			},
			{
				begin: "\"",
				end: "\"",
				illegal: "\\n",
				contains: [
					hljs.BACKSLASH_ESCAPE,
					SUBST,
					BRACED_SUBST
				]
			}
		]
	};
	BRACED_SUBST.contains = [NUMBER, STRING];
	const BUILT_IN_TYPES = [
		"Comparable",
		"DateTime",
		"Duration",
		"Function",
		"Iterable",
		"Iterator",
		"List",
		"Map",
		"Match",
		"Object",
		"Pattern",
		"RegExp",
		"Set",
		"Stopwatch",
		"String",
		"StringBuffer",
		"StringSink",
		"Symbol",
		"Type",
		"Uri",
		"bool",
		"double",
		"int",
		"num",
		"Element",
		"ElementList"
	];
	const NULLABLE_BUILT_IN_TYPES = BUILT_IN_TYPES.map((e) => `${e}?`);
	const KEYWORDS = {
		keyword: [
			"abstract",
			"as",
			"assert",
			"async",
			"await",
			"base",
			"break",
			"case",
			"catch",
			"class",
			"const",
			"continue",
			"covariant",
			"default",
			"deferred",
			"do",
			"dynamic",
			"else",
			"enum",
			"export",
			"extends",
			"extension",
			"external",
			"factory",
			"false",
			"final",
			"finally",
			"for",
			"Function",
			"get",
			"hide",
			"if",
			"implements",
			"import",
			"in",
			"interface",
			"is",
			"late",
			"library",
			"mixin",
			"new",
			"null",
			"on",
			"operator",
			"part",
			"required",
			"rethrow",
			"return",
			"sealed",
			"set",
			"show",
			"static",
			"super",
			"switch",
			"sync",
			"this",
			"throw",
			"true",
			"try",
			"typedef",
			"var",
			"void",
			"when",
			"while",
			"with",
			"yield"
		],
		built_in: BUILT_IN_TYPES.concat(NULLABLE_BUILT_IN_TYPES).concat([
			"Never",
			"Null",
			"dynamic",
			"print",
			"document",
			"querySelector",
			"querySelectorAll",
			"window"
		]),
		$pattern: /[A-Za-z][A-Za-z0-9_]*\??/
	};
	const CLASS_REFERENCE = {
		match: regex.concat(/\b_?/, regex.either(/(?:[A-Z]+[a-z0-9]+)+/, /(?:[A-Z]+[a-z0-9]+)+[A-Z]+/), /(?![A-Za-z0-9_])/),
		scope: "title.class"
	};
	return {
		name: "Dart",
		keywords: KEYWORDS,
		contains: [
			STRING,
			hljs.COMMENT(/\/\*\*(?!\/)/, /\*\//, {
				subLanguage: "markdown",
				relevance: 0
			}),
			hljs.COMMENT(/\/{3,} ?/, /$/, { contains: [{
				subLanguage: "markdown",
				begin: ".",
				end: "$",
				relevance: 0
			}] }),
			hljs.C_LINE_COMMENT_MODE,
			hljs.C_BLOCK_COMMENT_MODE,
			{
				className: "class",
				beginKeywords: "class interface",
				end: /\{/,
				excludeEnd: true,
				contains: [{ beginKeywords: "extends implements" }, hljs.UNDERSCORE_TITLE_MODE]
			},
			CLASS_REFERENCE,
			{
				match: /\b(?!(?:assert|catch|for|if|switch|while)\b)[a-z_][A-Za-z0-9_]*(?=\()/,
				scope: "title.function"
			},
			NUMBER,
			{
				className: "meta",
				begin: "@[A-Za-z]+"
			}
		]
	};
}
//#endregion
//#region node_modules/highlight.js/es/languages/javascript.js
var IDENT_RE$2 = "[A-Za-z$_][0-9A-Za-z$_]*";
var KEYWORDS$2 = [
	"as",
	"in",
	"of",
	"if",
	"for",
	"while",
	"finally",
	"var",
	"new",
	"function",
	"do",
	"return",
	"void",
	"else",
	"break",
	"catch",
	"instanceof",
	"with",
	"throw",
	"case",
	"default",
	"try",
	"switch",
	"continue",
	"typeof",
	"delete",
	"let",
	"yield",
	"const",
	"class",
	"debugger",
	"async",
	"await",
	"static",
	"import",
	"from",
	"export",
	"extends",
	"using"
];
var LITERALS$1 = [
	"true",
	"false",
	"null",
	"undefined",
	"NaN",
	"Infinity"
];
var TYPES$1 = [
	"Object",
	"Function",
	"Boolean",
	"Symbol",
	"Math",
	"Date",
	"Number",
	"BigInt",
	"String",
	"RegExp",
	"Array",
	"Float32Array",
	"Float64Array",
	"Int8Array",
	"Uint8Array",
	"Uint8ClampedArray",
	"Int16Array",
	"Int32Array",
	"Uint16Array",
	"Uint32Array",
	"BigInt64Array",
	"BigUint64Array",
	"Set",
	"Map",
	"WeakSet",
	"WeakMap",
	"ArrayBuffer",
	"SharedArrayBuffer",
	"Atomics",
	"DataView",
	"JSON",
	"Promise",
	"Generator",
	"GeneratorFunction",
	"AsyncFunction",
	"Reflect",
	"Proxy",
	"Intl",
	"WebAssembly"
];
var ERROR_TYPES$1 = [
	"Error",
	"EvalError",
	"InternalError",
	"RangeError",
	"ReferenceError",
	"SyntaxError",
	"TypeError",
	"URIError"
];
var BUILT_IN_GLOBALS$1 = [
	"setInterval",
	"setTimeout",
	"clearInterval",
	"clearTimeout",
	"require",
	"exports",
	"eval",
	"isFinite",
	"isNaN",
	"parseFloat",
	"parseInt",
	"decodeURI",
	"decodeURIComponent",
	"encodeURI",
	"encodeURIComponent",
	"escape",
	"unescape"
];
var BUILT_IN_VARIABLES$1 = [
	"arguments",
	"this",
	"super",
	"console",
	"window",
	"document",
	"localStorage",
	"sessionStorage",
	"module",
	"self",
	"global"
];
var BUILT_INS$1 = [].concat(BUILT_IN_GLOBALS$1, TYPES$1, ERROR_TYPES$1);
/** @type LanguageFn */
function javascript$1(hljs) {
	const regex = hljs.regex;
	/**
	* Takes a string like "<Booger" and checks to see
	* if we can find a matching "</Booger" later in the
	* content.
	* @param {RegExpMatchArray} match
	* @param {{after:number}} param1
	*/
	const hasClosingTag = (match, { after }) => {
		const tag = "</" + match[0].slice(1);
		return match.input.indexOf(tag, after) !== -1;
	};
	const IDENT_RE$1 = IDENT_RE$2;
	const FRAGMENT = {
		begin: "<>",
		end: "</>"
	};
	const XML_SELF_CLOSING = /<[A-Za-z0-9\\._:-]+\s*\/>/;
	const XML_TAG = {
		begin: /<[A-Za-z0-9\\._:-]+/,
		end: /\/[A-Za-z0-9\\._:-]+>|\/>/,
		/**
		* @param {RegExpMatchArray} match
		* @param {CallbackResponse} response
		*/
		isTrulyOpeningTag: (match, response) => {
			const afterMatchIndex = match[0].length + match.index;
			const nextChar = match.input[afterMatchIndex];
			if (nextChar === "<" || nextChar === ",") {
				response.ignoreMatch();
				return;
			}
			if (nextChar === ">") {
				if (!hasClosingTag(match, { after: afterMatchIndex })) response.ignoreMatch();
			}
			let m;
			const afterMatch = match.input.substring(afterMatchIndex);
			if (m = afterMatch.match(/^\s*=/)) {
				response.ignoreMatch();
				return;
			}
			if (m = afterMatch.match(/^\s+extends\s+/)) {
				if (m.index === 0) {
					response.ignoreMatch();
					return;
				}
			}
		}
	};
	const KEYWORDS$1 = {
		$pattern: IDENT_RE$2,
		keyword: KEYWORDS$2,
		literal: LITERALS$1,
		built_in: BUILT_INS$1,
		"variable.language": BUILT_IN_VARIABLES$1
	};
	const decimalDigits = "[0-9](_?[0-9])*";
	const frac = `\\.(${decimalDigits})`;
	const decimalInteger = `0|[1-9](_?[0-9])*|0[0-7]*[89][0-9]*`;
	const NUMBER = {
		className: "number",
		variants: [
			{ begin: `(\\b(${decimalInteger})((${frac})|\\.)?|(${frac}))[eE][+-]?(${decimalDigits})\\b` },
			{ begin: `\\b(${decimalInteger})\\b((${frac})\\b|\\.)?|(${frac})\\b` },
			{ begin: `\\b(0|[1-9](_?[0-9])*)n\\b` },
			{ begin: "\\b0[xX][0-9a-fA-F](_?[0-9a-fA-F])*n?\\b" },
			{ begin: "\\b0[bB][0-1](_?[0-1])*n?\\b" },
			{ begin: "\\b0[oO][0-7](_?[0-7])*n?\\b" },
			{ begin: "\\b0[0-7]+n?\\b" }
		],
		relevance: 0
	};
	const SUBST = {
		className: "subst",
		begin: "\\$\\{",
		end: "\\}",
		keywords: KEYWORDS$1,
		contains: []
	};
	const HTML_TEMPLATE = {
		begin: ".?html`",
		end: "",
		starts: {
			end: "`",
			returnEnd: false,
			contains: [hljs.BACKSLASH_ESCAPE, SUBST],
			subLanguage: "xml"
		}
	};
	const CSS_TEMPLATE = {
		begin: ".?css`",
		end: "",
		starts: {
			end: "`",
			returnEnd: false,
			contains: [hljs.BACKSLASH_ESCAPE, SUBST],
			subLanguage: "css"
		}
	};
	const GRAPHQL_TEMPLATE = {
		begin: ".?gql`",
		end: "",
		starts: {
			end: "`",
			returnEnd: false,
			contains: [hljs.BACKSLASH_ESCAPE, SUBST],
			subLanguage: "graphql"
		}
	};
	const TEMPLATE_STRING = {
		className: "string",
		begin: "`",
		end: "`",
		contains: [hljs.BACKSLASH_ESCAPE, SUBST]
	};
	const COMMENT = {
		className: "comment",
		variants: [
			hljs.COMMENT(/\/\*\*(?!\/)/, "\\*/", {
				relevance: 0,
				contains: [{
					begin: "(?=@[A-Za-z]+)",
					relevance: 0,
					contains: [
						{
							className: "doctag",
							begin: "@[A-Za-z]+"
						},
						{
							className: "type",
							begin: "\\{",
							end: "\\}",
							excludeEnd: true,
							excludeBegin: true,
							relevance: 0
						},
						{
							className: "variable",
							begin: IDENT_RE$1 + "(?=\\s*(-)|$)",
							endsParent: true,
							relevance: 0
						},
						{
							begin: /(?=[^\n])\s/,
							relevance: 0
						}
					]
				}]
			}),
			hljs.C_BLOCK_COMMENT_MODE,
			hljs.C_LINE_COMMENT_MODE
		]
	};
	const SUBST_INTERNALS = [
		hljs.APOS_STRING_MODE,
		hljs.QUOTE_STRING_MODE,
		HTML_TEMPLATE,
		CSS_TEMPLATE,
		GRAPHQL_TEMPLATE,
		TEMPLATE_STRING,
		{ match: /\$\d+/ },
		NUMBER
	];
	SUBST.contains = SUBST_INTERNALS.concat({
		begin: /\{/,
		end: /\}/,
		keywords: KEYWORDS$1,
		contains: ["self"].concat(SUBST_INTERNALS)
	});
	const SUBST_AND_COMMENTS = [].concat(COMMENT, SUBST.contains);
	const PARAMS_CONTAINS = SUBST_AND_COMMENTS.concat([{
		begin: /(\s*)\(/,
		end: /\)/,
		keywords: KEYWORDS$1,
		contains: ["self"].concat(SUBST_AND_COMMENTS)
	}]);
	const PARAMS = {
		className: "params",
		begin: /(\s*)\(/,
		end: /\)/,
		excludeBegin: true,
		excludeEnd: true,
		keywords: KEYWORDS$1,
		contains: PARAMS_CONTAINS
	};
	const CLASS_OR_EXTENDS = { variants: [{
		match: [
			/class/,
			/\s+/,
			IDENT_RE$1,
			/\s+/,
			/extends/,
			/\s+/,
			regex.concat(IDENT_RE$1, "(", regex.concat(/\./, IDENT_RE$1), ")*")
		],
		scope: {
			1: "keyword",
			3: "title.class",
			5: "keyword",
			7: "title.class.inherited"
		}
	}, {
		match: [
			/class/,
			/\s+/,
			IDENT_RE$1
		],
		scope: {
			1: "keyword",
			3: "title.class"
		}
	}] };
	const CLASS_REFERENCE = {
		relevance: 0,
		match: regex.either(/\bJSON/, /\b[A-Z][a-z]+([A-Z][a-z]*|\d)*/, /\b[A-Z]{2,}([A-Z][a-z]+|\d)+([A-Z][a-z]*)*/, /\b[A-Z]{2,}[a-z]+([A-Z][a-z]+|\d)*([A-Z][a-z]*)*/),
		className: "title.class",
		keywords: { _: [...TYPES$1, ...ERROR_TYPES$1] }
	};
	const USE_STRICT = {
		label: "use_strict",
		className: "meta",
		relevance: 10,
		begin: /^\s*['"]use (strict|asm)['"]/
	};
	const FUNCTION_DEFINITION = {
		variants: [{ match: [
			/function/,
			/\s+/,
			IDENT_RE$1,
			/(?=\s*\()/
		] }, { match: [/function/, /\s*(?=\()/] }],
		className: {
			1: "keyword",
			3: "title.function"
		},
		label: "func.def",
		contains: [PARAMS],
		illegal: /%/
	};
	const UPPER_CASE_CONSTANT = {
		relevance: 0,
		match: /\b[A-Z][A-Z_0-9]+\b/,
		className: "variable.constant"
	};
	function noneOf(list) {
		return regex.concat("(?!", list.join("|"), ")");
	}
	const FUNCTION_CALL = {
		match: regex.concat(/\b/, noneOf([
			...BUILT_IN_GLOBALS$1,
			"super",
			"import",
			"await"
		].map((x) => `${x}\\s*\\(`)), IDENT_RE$1, regex.lookahead(/\s*\(/)),
		className: "title.function",
		relevance: 0
	};
	const PROPERTY_ACCESS = {
		begin: regex.concat(/\./, regex.lookahead(regex.concat(IDENT_RE$1, /(?![0-9A-Za-z$_(])/))),
		end: IDENT_RE$1,
		excludeBegin: true,
		keywords: "prototype",
		className: "property",
		relevance: 0
	};
	const GETTER_OR_SETTER = {
		match: [
			/get|set/,
			/\s+/,
			IDENT_RE$1,
			/(?=\()/
		],
		className: {
			1: "keyword",
			3: "title.function"
		},
		contains: [{ begin: /\(\)/ }, PARAMS]
	};
	const FUNC_LEAD_IN_RE = "(\\([^()]*(\\([^()]*(\\([^()]*\\)[^()]*)*\\)[^()]*)*\\)|" + hljs.UNDERSCORE_IDENT_RE + ")\\s*=>";
	const FUNCTION_VARIABLE = {
		match: [
			/const|var|let/,
			/\s+/,
			IDENT_RE$1,
			/\s*/,
			/=\s*/,
			/(async\s*)?/,
			regex.lookahead(FUNC_LEAD_IN_RE)
		],
		keywords: "async",
		className: {
			1: "keyword",
			3: "title.function"
		},
		contains: [PARAMS]
	};
	return {
		name: "JavaScript",
		aliases: [
			"js",
			"jsx",
			"mjs",
			"cjs"
		],
		keywords: KEYWORDS$1,
		exports: {
			PARAMS_CONTAINS,
			CLASS_REFERENCE
		},
		illegal: /#(?![$_A-Za-z])/,
		contains: [
			hljs.SHEBANG({
				label: "shebang",
				binary: "node",
				relevance: 5
			}),
			USE_STRICT,
			hljs.APOS_STRING_MODE,
			hljs.QUOTE_STRING_MODE,
			HTML_TEMPLATE,
			CSS_TEMPLATE,
			GRAPHQL_TEMPLATE,
			TEMPLATE_STRING,
			COMMENT,
			{ match: /\$\d+/ },
			NUMBER,
			CLASS_REFERENCE,
			{
				scope: "attr",
				match: IDENT_RE$1 + regex.lookahead(":"),
				relevance: 0
			},
			FUNCTION_VARIABLE,
			{
				begin: "(" + hljs.RE_STARTERS_RE + "|\\b(case|return|throw)\\b)\\s*",
				keywords: "return throw case",
				relevance: 0,
				contains: [
					COMMENT,
					hljs.REGEXP_MODE,
					{
						className: "function",
						begin: FUNC_LEAD_IN_RE,
						returnBegin: true,
						end: "\\s*=>",
						contains: [{
							className: "params",
							variants: [
								{
									begin: hljs.UNDERSCORE_IDENT_RE,
									relevance: 0
								},
								{
									className: null,
									begin: /\(\s*\)/,
									skip: true
								},
								{
									begin: /(\s*)\(/,
									end: /\)/,
									excludeBegin: true,
									excludeEnd: true,
									keywords: KEYWORDS$1,
									contains: PARAMS_CONTAINS
								}
							]
						}]
					},
					{
						begin: /,/,
						relevance: 0
					},
					{
						match: /\s+/,
						relevance: 0
					},
					{
						variants: [
							{
								begin: FRAGMENT.begin,
								end: FRAGMENT.end
							},
							{ match: XML_SELF_CLOSING },
							{
								begin: XML_TAG.begin,
								"on:begin": XML_TAG.isTrulyOpeningTag,
								end: XML_TAG.end
							}
						],
						subLanguage: "xml",
						contains: [{
							begin: XML_TAG.begin,
							end: XML_TAG.end,
							skip: true,
							contains: ["self"]
						}]
					}
				]
			},
			FUNCTION_DEFINITION,
			{ beginKeywords: "while if switch catch for" },
			{
				begin: "\\b(?!function)" + hljs.UNDERSCORE_IDENT_RE + "\\([^()]*(\\([^()]*(\\([^()]*\\)[^()]*)*\\)[^()]*)*\\)\\s*\\{",
				returnBegin: true,
				label: "func.def",
				contains: [PARAMS, hljs.inherit(hljs.TITLE_MODE, {
					begin: IDENT_RE$1,
					className: "title.function"
				})]
			},
			{
				match: /\.\.\./,
				relevance: 0
			},
			PROPERTY_ACCESS,
			{
				match: "\\$" + IDENT_RE$1,
				relevance: 0
			},
			{
				match: [/\bconstructor(?=\s*\()/],
				className: { 1: "title.function" },
				contains: [PARAMS]
			},
			FUNCTION_CALL,
			UPPER_CASE_CONSTANT,
			CLASS_OR_EXTENDS,
			GETTER_OR_SETTER,
			{ match: /\$[(.]/ }
		]
	};
}
//#endregion
//#region node_modules/highlight.js/es/languages/json.js
var EXTENDED_NUMBER_MODE = {
	scope: "number",
	match: "([-+]?)(\\b0[xX][a-fA-F0-9]+|(\\b\\d+(\\.\\d*)?|\\.\\d+)([eE][-+]?\\d+)?)|NaN|[-+]?Infinity",
	relevance: 0
};
function json(hljs) {
	const ATTRIBUTE = {
		className: "attr",
		begin: /(("(\\.|[^\\"\r\n])*")|('(\\.|[^\\'\r\n])*'))(?=\s*:)/,
		relevance: 1.01
	};
	const PUNCTUATION = {
		match: /[{}[\],:]/,
		className: "punctuation",
		relevance: 0
	};
	const LITERALS = [
		"true",
		"false",
		"null"
	];
	const LITERALS_MODE = {
		scope: "literal",
		beginKeywords: LITERALS.join(" ")
	};
	return {
		name: "JSON",
		aliases: ["jsonc", "json5"],
		keywords: { literal: LITERALS },
		contains: [
			ATTRIBUTE,
			PUNCTUATION,
			hljs.APOS_STRING_MODE,
			hljs.QUOTE_STRING_MODE,
			LITERALS_MODE,
			EXTENDED_NUMBER_MODE,
			hljs.C_LINE_COMMENT_MODE,
			hljs.C_BLOCK_COMMENT_MODE
		],
		illegal: "\\S"
	};
}
//#endregion
//#region node_modules/highlight.js/es/languages/markdown.js
function markdown(hljs) {
	const regex = hljs.regex;
	const INLINE_HTML = {
		begin: /<\/?[A-Za-z_]/,
		end: ">",
		subLanguage: "xml",
		relevance: 0
	};
	const HORIZONTAL_RULE = { match: /^ {0,3}([-*_])[ \t]*(?:\1[ \t]*){2,}$/ };
	const CODE = {
		className: "code",
		variants: [
			{ begin: "(`{3,})[^`](.|\\n)*?\\1`*[ ]*" },
			{ begin: "(~{3,})[^~](.|\\n)*?\\1~*[ ]*" },
			{
				begin: "```",
				end: "```+[ ]*$"
			},
			{
				begin: "~~~",
				end: "~~~+[ ]*$"
			},
			{ begin: "`.+?`" },
			{
				begin: "(?=^( {4}|\\t))",
				contains: [{
					begin: "^( {4}|\\t)",
					end: "(\\n)$"
				}],
				relevance: 0
			}
		]
	};
	const LIST = {
		className: "bullet",
		begin: "^[ 	]*([*+-]|(\\d+\\.))(?=\\s+)",
		end: "\\s+",
		excludeEnd: true
	};
	const LINK_REFERENCE = {
		begin: /^\[[^\n]+\]:/,
		returnBegin: true,
		contains: [{
			className: "symbol",
			begin: /\[/,
			end: /\]/,
			excludeBegin: true,
			excludeEnd: true
		}, {
			className: "link",
			begin: /:\s*/,
			end: /$/,
			excludeBegin: true
		}]
	};
	const LINK = {
		variants: [
			{
				begin: /\[.+?\]\[.*?\]/,
				relevance: 0
			},
			{
				begin: /\[.+?\]\(((data|javascript|mailto):|(?:http|ftp)s?:\/\/).*?\)/,
				relevance: 2
			},
			{
				begin: regex.concat(/\[.+?\]\(/, /[A-Za-z][A-Za-z0-9+.-]*/, /:\/\/.*?\)/),
				relevance: 2
			},
			{
				begin: /\[.+?\]\([./?&#].*?\)/,
				relevance: 1
			},
			{
				begin: /\[.*?\]\(.*?\)/,
				relevance: 0
			}
		],
		returnBegin: true,
		contains: [
			{ match: /\[(?=\])/ },
			{
				className: "string",
				relevance: 0,
				begin: "\\[",
				end: "\\]",
				excludeBegin: true,
				returnEnd: true
			},
			{
				className: "link",
				relevance: 0,
				begin: "\\]\\(",
				end: "\\)",
				excludeBegin: true,
				excludeEnd: true
			},
			{
				className: "symbol",
				relevance: 0,
				begin: "\\]\\[",
				end: "\\]",
				excludeBegin: true,
				excludeEnd: true
			}
		]
	};
	const BOLD = {
		className: "strong",
		contains: [],
		variants: [{
			begin: /_{2}(?!\s)/,
			end: /_{2}/
		}, {
			begin: /\*{2}(?!\s)/,
			end: /\*{2}/
		}]
	};
	const ITALIC = {
		className: "emphasis",
		contains: [],
		variants: [{
			begin: /\*(?![*\s])/,
			end: /\*/
		}, {
			begin: /_(?![_\s])/,
			end: /_/,
			relevance: 0
		}]
	};
	const BOLD_WITHOUT_ITALIC = hljs.inherit(BOLD, { contains: [] });
	const ITALIC_WITHOUT_BOLD = hljs.inherit(ITALIC, { contains: [] });
	BOLD.contains.push(ITALIC_WITHOUT_BOLD);
	ITALIC.contains.push(BOLD_WITHOUT_ITALIC);
	let CONTAINABLE = [INLINE_HTML, LINK];
	[
		BOLD,
		ITALIC,
		BOLD_WITHOUT_ITALIC,
		ITALIC_WITHOUT_BOLD
	].forEach((m) => {
		m.contains = m.contains.concat(CONTAINABLE);
	});
	CONTAINABLE = CONTAINABLE.concat(BOLD, ITALIC);
	return {
		name: "Markdown",
		aliases: [
			"md",
			"mkdown",
			"mkd"
		],
		contains: [
			{
				className: "section",
				variants: [{
					begin: "^#{1,6}",
					end: "$",
					contains: CONTAINABLE
				}, {
					begin: "(?=^.+?\\n[=-]{2,}$)",
					contains: [{ begin: "^[=-]*$" }, {
						begin: "^",
						end: "\\n",
						contains: CONTAINABLE
					}]
				}]
			},
			INLINE_HTML,
			LIST,
			HORIZONTAL_RULE,
			BOLD,
			ITALIC,
			{
				className: "quote",
				begin: "^>\\s+",
				contains: CONTAINABLE,
				end: "$"
			},
			CODE,
			LINK,
			LINK_REFERENCE,
			{
				scope: "literal",
				match: /&([a-zA-Z0-9]+|#[0-9]{1,7}|#[Xx][0-9a-fA-F]{1,6});/
			}
		]
	};
}
//#endregion
//#region node_modules/highlight.js/es/languages/python.js
function python(hljs) {
	const regex = hljs.regex;
	const IDENT_RE = /[\p{XID_Start}_]\p{XID_Continue}*/u;
	const RESERVED_WORDS = [
		"and",
		"as",
		"assert",
		"async",
		"await",
		"break",
		"case",
		"class",
		"continue",
		"def",
		"del",
		"elif",
		"else",
		"except",
		"finally",
		"for",
		"from",
		"global",
		"if",
		"import",
		"in",
		"is",
		"lambda",
		"lazy",
		"match",
		"nonlocal|10",
		"not",
		"or",
		"pass",
		"raise",
		"return",
		"try",
		"while",
		"with",
		"yield"
	];
	const KEYWORDS = {
		$pattern: /[A-Za-z]\w+|__\w+__/,
		keyword: RESERVED_WORDS,
		built_in: [
			"__import__",
			"abs",
			"aiter",
			"all",
			"anext",
			"any",
			"ascii",
			"bin",
			"bool",
			"breakpoint",
			"bytearray",
			"bytes",
			"callable",
			"chr",
			"classmethod",
			"compile",
			"complex",
			"delattr",
			"dict",
			"dir",
			"divmod",
			"enumerate",
			"eval",
			"exec",
			"filter",
			"float",
			"format",
			"frozendict",
			"frozenset",
			"getattr",
			"globals",
			"hasattr",
			"hash",
			"help",
			"hex",
			"id",
			"input",
			"int",
			"isinstance",
			"issubclass",
			"iter",
			"len",
			"list",
			"locals",
			"map",
			"max",
			"memoryview",
			"min",
			"next",
			"object",
			"oct",
			"open",
			"ord",
			"pow",
			"print",
			"property",
			"range",
			"repr",
			"reversed",
			"round",
			"sentinel",
			"set",
			"setattr",
			"slice",
			"sorted",
			"staticmethod",
			"str",
			"sum",
			"super",
			"tuple",
			"type",
			"vars",
			"zip"
		],
		literal: [
			"__debug__",
			"Ellipsis",
			"False",
			"None",
			"NotImplemented",
			"True"
		],
		type: [
			"Any",
			"Callable",
			"Coroutine",
			"Dict",
			"List",
			"Literal",
			"Generic",
			"Optional",
			"Sequence",
			"Set",
			"Tuple",
			"Type",
			"Union"
		]
	};
	const PROMPT = {
		className: "meta",
		begin: /^(>>>|\.\.\.) /
	};
	const SUBST = {
		className: "subst",
		begin: /\{/,
		end: /\}/,
		keywords: KEYWORDS,
		illegal: /#/
	};
	const LITERAL_BRACKET = {
		begin: /\{\{/,
		relevance: 0
	};
	const STRING = {
		className: "string",
		contains: [hljs.BACKSLASH_ESCAPE],
		variants: [
			{
				begin: /([uU]|[bB]|[rR]|[bB][rR]|[rR][bB])?'''/,
				end: /'''/,
				contains: [hljs.BACKSLASH_ESCAPE, PROMPT],
				relevance: 10
			},
			{
				begin: /([uU]|[bB]|[rR]|[bB][rR]|[rR][bB])?"""/,
				end: /"""/,
				contains: [hljs.BACKSLASH_ESCAPE, PROMPT],
				relevance: 10
			},
			{
				begin: /([fFtT][rR]|[rR][fFtT]|[fFtT])'''/,
				end: /'''/,
				contains: [
					hljs.BACKSLASH_ESCAPE,
					PROMPT,
					LITERAL_BRACKET,
					SUBST
				]
			},
			{
				begin: /([fFtT][rR]|[rR][fFtT]|[fFtT])"""/,
				end: /"""/,
				contains: [
					hljs.BACKSLASH_ESCAPE,
					PROMPT,
					LITERAL_BRACKET,
					SUBST
				]
			},
			{
				begin: /([uU]|[rR])'/,
				end: /'/,
				relevance: 10
			},
			{
				begin: /([uU]|[rR])"/,
				end: /"/,
				relevance: 10
			},
			{
				begin: /([bB]|[bB][rR]|[rR][bB])'/,
				end: /'/
			},
			{
				begin: /([bB]|[bB][rR]|[rR][bB])"/,
				end: /"/
			},
			{
				begin: /([fFtT][rR]|[rR][fFtT]|[fFtT])'/,
				end: /'/,
				contains: [
					hljs.BACKSLASH_ESCAPE,
					LITERAL_BRACKET,
					SUBST
				]
			},
			{
				begin: /([fFtT][rR]|[rR][fFtT]|[fFtT])"/,
				end: /"/,
				contains: [
					hljs.BACKSLASH_ESCAPE,
					LITERAL_BRACKET,
					SUBST
				]
			},
			hljs.APOS_STRING_MODE,
			hljs.QUOTE_STRING_MODE
		]
	};
	const digitpart = "[0-9](_?[0-9])*";
	const pointfloat = `(\\b(${digitpart}))?\\.(${digitpart})|\\b(${digitpart})\\.`;
	const lookahead = `\\b|${RESERVED_WORDS.join("|")}`;
	const NUMBER = {
		className: "number",
		relevance: 0,
		variants: [
			{ begin: `(\\b(${digitpart})|(${pointfloat}))[eE][+-]?(${digitpart})[jJ]?(?=${lookahead})` },
			{ begin: `(${pointfloat})[jJ]?` },
			{ begin: `\\b([1-9](_?[0-9])*|0+(_?0)*)[lLjJ]?(?=${lookahead})` },
			{ begin: `\\b0[bB](_?[01])+[lL]?(?=${lookahead})` },
			{ begin: `\\b0[oO](_?[0-7])+[lL]?(?=${lookahead})` },
			{ begin: `\\b0[xX](_?[0-9a-fA-F])+[lL]?(?=${lookahead})` },
			{ begin: `\\b(${digitpart})[jJ](?=${lookahead})` }
		]
	};
	const COMMENT_TYPE = {
		className: "comment",
		begin: regex.lookahead(/# type:/),
		end: /$/,
		keywords: KEYWORDS,
		contains: [{ begin: /# type:/ }, {
			begin: /#/,
			end: /\b\B/,
			endsWithParent: true
		}]
	};
	const PARAMS = {
		className: "params",
		variants: [{
			className: "",
			begin: /\(\s*\)/,
			skip: true
		}, {
			begin: /\(/,
			end: /\)/,
			excludeBegin: true,
			excludeEnd: true,
			keywords: KEYWORDS,
			contains: [
				"self",
				PROMPT,
				NUMBER,
				STRING,
				hljs.HASH_COMMENT_MODE
			]
		}]
	};
	SUBST.contains = [
		STRING,
		NUMBER,
		PROMPT
	];
	return {
		name: "Python",
		aliases: [
			"py",
			"gyp",
			"ipython"
		],
		unicodeRegex: true,
		keywords: KEYWORDS,
		illegal: /(<\/|\?)|=>/,
		contains: [
			PROMPT,
			NUMBER,
			{
				scope: "variable.language",
				match: /\bself\b/
			},
			{
				beginKeywords: "if",
				relevance: 0
			},
			{
				match: /\bor\b/,
				scope: "keyword"
			},
			STRING,
			COMMENT_TYPE,
			hljs.HASH_COMMENT_MODE,
			{
				match: [
					/\bdef/,
					/\s+/,
					IDENT_RE
				],
				scope: {
					1: "keyword",
					3: "title.function"
				},
				contains: [PARAMS]
			},
			{
				variants: [{ match: [
					/\bclass/,
					/\s+/,
					IDENT_RE,
					/\s*/,
					/\(\s*/,
					IDENT_RE,
					/\s*\)/
				] }, { match: [
					/\bclass/,
					/\s+/,
					IDENT_RE
				] }],
				scope: {
					1: "keyword",
					3: "title.class",
					6: "title.class.inherited"
				}
			},
			{
				className: "meta",
				begin: /^[\t ]*@/,
				end: /(?=#)|$/,
				contains: [
					NUMBER,
					PARAMS,
					STRING
				]
			}
		]
	};
}
//#endregion
//#region node_modules/highlight.js/es/languages/sql.js
function sql(hljs) {
	const regex = hljs.regex;
	const COMMENT_MODE = hljs.COMMENT("--", "$");
	const STRING = {
		scope: "string",
		variants: [{
			begin: /'/,
			end: /'/,
			contains: [{ match: /''/ }]
		}]
	};
	const QUOTED_IDENTIFIER = {
		begin: /"/,
		end: /"/,
		contains: [{ match: /""/ }]
	};
	const LITERALS = [
		"true",
		"false",
		"unknown"
	];
	const MULTI_WORD_TYPES = [
		"double precision",
		"large object",
		"with timezone",
		"without timezone"
	];
	const TYPES = [
		"bigint",
		"binary",
		"blob",
		"boolean",
		"char",
		"character",
		"clob",
		"date",
		"dec",
		"decfloat",
		"decimal",
		"float",
		"int",
		"integer",
		"interval",
		"nchar",
		"nclob",
		"national",
		"numeric",
		"real",
		"row",
		"smallint",
		"time",
		"timestamp",
		"varchar",
		"varying",
		"varbinary"
	];
	const NON_RESERVED_WORDS = [
		"add",
		"asc",
		"collation",
		"desc",
		"final",
		"first",
		"last",
		"view"
	];
	const RESERVED_WORDS = [
		"abs",
		"acos",
		"all",
		"allocate",
		"alter",
		"and",
		"any",
		"are",
		"array",
		"array_agg",
		"array_max_cardinality",
		"as",
		"asensitive",
		"asin",
		"asymmetric",
		"at",
		"atan",
		"atomic",
		"authorization",
		"avg",
		"begin",
		"begin_frame",
		"begin_partition",
		"between",
		"bigint",
		"binary",
		"blob",
		"boolean",
		"both",
		"by",
		"call",
		"called",
		"cardinality",
		"cascaded",
		"case",
		"cast",
		"ceil",
		"ceiling",
		"char",
		"char_length",
		"character",
		"character_length",
		"check",
		"classifier",
		"clob",
		"close",
		"coalesce",
		"collate",
		"collect",
		"column",
		"commit",
		"condition",
		"connect",
		"constraint",
		"contains",
		"convert",
		"copy",
		"corr",
		"corresponding",
		"cos",
		"cosh",
		"count",
		"covar_pop",
		"covar_samp",
		"create",
		"cross",
		"cube",
		"cume_dist",
		"current",
		"current_catalog",
		"current_date",
		"current_default_transform_group",
		"current_path",
		"current_role",
		"current_row",
		"current_schema",
		"current_time",
		"current_timestamp",
		"current_path",
		"current_role",
		"current_transform_group_for_type",
		"current_user",
		"cursor",
		"cycle",
		"date",
		"day",
		"deallocate",
		"dec",
		"decimal",
		"decfloat",
		"declare",
		"default",
		"define",
		"delete",
		"dense_rank",
		"deref",
		"describe",
		"deterministic",
		"disconnect",
		"distinct",
		"double",
		"drop",
		"dynamic",
		"each",
		"element",
		"else",
		"empty",
		"end",
		"end_frame",
		"end_partition",
		"end-exec",
		"equals",
		"escape",
		"every",
		"except",
		"exec",
		"execute",
		"exists",
		"exp",
		"external",
		"extract",
		"false",
		"fetch",
		"filter",
		"first_value",
		"float",
		"floor",
		"for",
		"foreign",
		"frame_row",
		"free",
		"from",
		"full",
		"function",
		"fusion",
		"get",
		"global",
		"grant",
		"group",
		"grouping",
		"groups",
		"having",
		"hold",
		"hour",
		"identity",
		"in",
		"indicator",
		"initial",
		"inner",
		"inout",
		"insensitive",
		"insert",
		"int",
		"integer",
		"intersect",
		"intersection",
		"interval",
		"into",
		"is",
		"join",
		"json_array",
		"json_arrayagg",
		"json_exists",
		"json_object",
		"json_objectagg",
		"json_query",
		"json_table",
		"json_table_primitive",
		"json_value",
		"lag",
		"language",
		"large",
		"last_value",
		"lateral",
		"lead",
		"leading",
		"left",
		"like",
		"like_regex",
		"listagg",
		"ln",
		"local",
		"localtime",
		"localtimestamp",
		"log",
		"log10",
		"lower",
		"match",
		"match_number",
		"match_recognize",
		"matches",
		"max",
		"member",
		"merge",
		"method",
		"min",
		"minute",
		"mod",
		"modifies",
		"module",
		"month",
		"multiset",
		"national",
		"natural",
		"nchar",
		"nclob",
		"new",
		"no",
		"none",
		"normalize",
		"not",
		"nth_value",
		"ntile",
		"null",
		"nullif",
		"numeric",
		"octet_length",
		"occurrences_regex",
		"of",
		"offset",
		"old",
		"omit",
		"on",
		"one",
		"only",
		"open",
		"or",
		"order",
		"out",
		"outer",
		"over",
		"overlaps",
		"overlay",
		"parameter",
		"partition",
		"pattern",
		"per",
		"percent",
		"percent_rank",
		"percentile_cont",
		"percentile_disc",
		"period",
		"portion",
		"position",
		"position_regex",
		"power",
		"precedes",
		"precision",
		"prepare",
		"primary",
		"procedure",
		"ptf",
		"range",
		"rank",
		"reads",
		"real",
		"recursive",
		"ref",
		"references",
		"referencing",
		"regr_avgx",
		"regr_avgy",
		"regr_count",
		"regr_intercept",
		"regr_r2",
		"regr_slope",
		"regr_sxx",
		"regr_sxy",
		"regr_syy",
		"release",
		"result",
		"return",
		"returns",
		"revoke",
		"right",
		"rollback",
		"rollup",
		"row",
		"row_number",
		"rows",
		"running",
		"savepoint",
		"scope",
		"scroll",
		"search",
		"second",
		"seek",
		"select",
		"sensitive",
		"session_user",
		"set",
		"show",
		"similar",
		"sin",
		"sinh",
		"skip",
		"smallint",
		"some",
		"specific",
		"specifictype",
		"sql",
		"sqlexception",
		"sqlstate",
		"sqlwarning",
		"sqrt",
		"start",
		"static",
		"stddev_pop",
		"stddev_samp",
		"submultiset",
		"subset",
		"substring",
		"substring_regex",
		"succeeds",
		"sum",
		"symmetric",
		"system",
		"system_time",
		"system_user",
		"table",
		"tablesample",
		"tan",
		"tanh",
		"then",
		"time",
		"timestamp",
		"timezone_hour",
		"timezone_minute",
		"to",
		"trailing",
		"translate",
		"translate_regex",
		"translation",
		"treat",
		"trigger",
		"trim",
		"trim_array",
		"true",
		"truncate",
		"uescape",
		"union",
		"unique",
		"unknown",
		"unnest",
		"update",
		"upper",
		"user",
		"using",
		"value",
		"values",
		"value_of",
		"var_pop",
		"var_samp",
		"varbinary",
		"varchar",
		"varying",
		"versioning",
		"when",
		"whenever",
		"where",
		"width_bucket",
		"window",
		"with",
		"within",
		"without",
		"year"
	];
	const RESERVED_FUNCTIONS = [
		"abs",
		"acos",
		"array_agg",
		"asin",
		"atan",
		"avg",
		"cast",
		"ceil",
		"ceiling",
		"coalesce",
		"corr",
		"cos",
		"cosh",
		"count",
		"covar_pop",
		"covar_samp",
		"cume_dist",
		"dense_rank",
		"deref",
		"element",
		"exp",
		"extract",
		"first_value",
		"floor",
		"json_array",
		"json_arrayagg",
		"json_exists",
		"json_object",
		"json_objectagg",
		"json_query",
		"json_table",
		"json_table_primitive",
		"json_value",
		"lag",
		"last_value",
		"lead",
		"listagg",
		"ln",
		"log",
		"log10",
		"lower",
		"max",
		"min",
		"mod",
		"nth_value",
		"ntile",
		"nullif",
		"percent_rank",
		"percentile_cont",
		"percentile_disc",
		"position",
		"position_regex",
		"power",
		"rank",
		"regr_avgx",
		"regr_avgy",
		"regr_count",
		"regr_intercept",
		"regr_r2",
		"regr_slope",
		"regr_sxx",
		"regr_sxy",
		"regr_syy",
		"row_number",
		"sin",
		"sinh",
		"sqrt",
		"stddev_pop",
		"stddev_samp",
		"substring",
		"substring_regex",
		"sum",
		"tan",
		"tanh",
		"translate",
		"translate_regex",
		"treat",
		"trim",
		"trim_array",
		"unnest",
		"upper",
		"value_of",
		"var_pop",
		"var_samp",
		"width_bucket"
	];
	const POSSIBLE_WITHOUT_PARENS = [
		"current_catalog",
		"current_date",
		"current_default_transform_group",
		"current_path",
		"current_role",
		"current_schema",
		"current_transform_group_for_type",
		"current_user",
		"session_user",
		"system_time",
		"system_user",
		"current_time",
		"localtime",
		"current_timestamp",
		"localtimestamp"
	];
	const COMBOS = [
		"create table",
		"insert into",
		"primary key",
		"foreign key",
		"not null",
		"alter table",
		"add constraint",
		"grouping sets",
		"on overflow",
		"character set",
		"respect nulls",
		"ignore nulls",
		"nulls first",
		"nulls last",
		"depth first",
		"breadth first"
	];
	const FUNCTIONS = RESERVED_FUNCTIONS;
	const KEYWORDS = [...RESERVED_WORDS, ...NON_RESERVED_WORDS].filter((keyword) => {
		return !RESERVED_FUNCTIONS.includes(keyword);
	});
	const VARIABLE = {
		scope: "variable",
		match: /@[a-z0-9][a-z0-9_]*/
	};
	const OPERATOR = {
		scope: "operator",
		match: /[-+*/=%^~]|&&?|\|\|?|!=?|<(?:=>?|<|>)?|>[>=]?/,
		relevance: 0
	};
	const FUNCTION_CALL = {
		match: regex.concat(/\b/, regex.either(...FUNCTIONS), /\s*\(/),
		relevance: 0,
		keywords: { built_in: FUNCTIONS }
	};
	function kws_to_regex(list) {
		return regex.concat(/\b/, regex.either(...list.map((kw) => {
			return kw.replace(/\s+/, "\\s+");
		})), /\b/);
	}
	const MULTI_WORD_KEYWORDS = {
		scope: "keyword",
		match: kws_to_regex(COMBOS),
		relevance: 0
	};
	function reduceRelevancy(list, { exceptions, when } = {}) {
		const qualifyFn = when;
		exceptions = exceptions || [];
		return list.map((item) => {
			if (item.match(/\|\d+$/) || exceptions.includes(item)) return item;
			else if (qualifyFn(item)) return `${item}|0`;
			else return item;
		});
	}
	return {
		name: "SQL",
		case_insensitive: true,
		illegal: /[{}]|<\//,
		keywords: {
			$pattern: /\b[\w\.]+/,
			keyword: reduceRelevancy(KEYWORDS, { when: (x) => x.length < 3 }),
			literal: LITERALS,
			type: TYPES,
			built_in: POSSIBLE_WITHOUT_PARENS
		},
		contains: [
			{
				scope: "type",
				match: kws_to_regex(MULTI_WORD_TYPES)
			},
			MULTI_WORD_KEYWORDS,
			FUNCTION_CALL,
			VARIABLE,
			STRING,
			QUOTED_IDENTIFIER,
			hljs.C_NUMBER_MODE,
			hljs.C_BLOCK_COMMENT_MODE,
			COMMENT_MODE,
			OPERATOR
		]
	};
}
//#endregion
//#region node_modules/highlight.js/es/languages/typescript.js
var IDENT_RE = "[A-Za-z$_][0-9A-Za-z$_]*";
var KEYWORDS = [
	"as",
	"in",
	"of",
	"if",
	"for",
	"while",
	"finally",
	"var",
	"new",
	"function",
	"do",
	"return",
	"void",
	"else",
	"break",
	"catch",
	"instanceof",
	"with",
	"throw",
	"case",
	"default",
	"try",
	"switch",
	"continue",
	"typeof",
	"delete",
	"let",
	"yield",
	"const",
	"class",
	"debugger",
	"async",
	"await",
	"static",
	"import",
	"from",
	"export",
	"extends",
	"using"
];
var LITERALS = [
	"true",
	"false",
	"null",
	"undefined",
	"NaN",
	"Infinity"
];
var TYPES = [
	"Object",
	"Function",
	"Boolean",
	"Symbol",
	"Math",
	"Date",
	"Number",
	"BigInt",
	"String",
	"RegExp",
	"Array",
	"Float32Array",
	"Float64Array",
	"Int8Array",
	"Uint8Array",
	"Uint8ClampedArray",
	"Int16Array",
	"Int32Array",
	"Uint16Array",
	"Uint32Array",
	"BigInt64Array",
	"BigUint64Array",
	"Set",
	"Map",
	"WeakSet",
	"WeakMap",
	"ArrayBuffer",
	"SharedArrayBuffer",
	"Atomics",
	"DataView",
	"JSON",
	"Promise",
	"Generator",
	"GeneratorFunction",
	"AsyncFunction",
	"Reflect",
	"Proxy",
	"Intl",
	"WebAssembly"
];
var ERROR_TYPES = [
	"Error",
	"EvalError",
	"InternalError",
	"RangeError",
	"ReferenceError",
	"SyntaxError",
	"TypeError",
	"URIError"
];
var BUILT_IN_GLOBALS = [
	"setInterval",
	"setTimeout",
	"clearInterval",
	"clearTimeout",
	"require",
	"exports",
	"eval",
	"isFinite",
	"isNaN",
	"parseFloat",
	"parseInt",
	"decodeURI",
	"decodeURIComponent",
	"encodeURI",
	"encodeURIComponent",
	"escape",
	"unescape"
];
var BUILT_IN_VARIABLES = [
	"arguments",
	"this",
	"super",
	"console",
	"window",
	"document",
	"localStorage",
	"sessionStorage",
	"module",
	"self",
	"global"
];
var BUILT_INS = [].concat(BUILT_IN_GLOBALS, TYPES, ERROR_TYPES);
/** @type LanguageFn */
function javascript(hljs) {
	const regex = hljs.regex;
	/**
	* Takes a string like "<Booger" and checks to see
	* if we can find a matching "</Booger" later in the
	* content.
	* @param {RegExpMatchArray} match
	* @param {{after:number}} param1
	*/
	const hasClosingTag = (match, { after }) => {
		const tag = "</" + match[0].slice(1);
		return match.input.indexOf(tag, after) !== -1;
	};
	const IDENT_RE$1 = IDENT_RE;
	const FRAGMENT = {
		begin: "<>",
		end: "</>"
	};
	const XML_SELF_CLOSING = /<[A-Za-z0-9\\._:-]+\s*\/>/;
	const XML_TAG = {
		begin: /<[A-Za-z0-9\\._:-]+/,
		end: /\/[A-Za-z0-9\\._:-]+>|\/>/,
		/**
		* @param {RegExpMatchArray} match
		* @param {CallbackResponse} response
		*/
		isTrulyOpeningTag: (match, response) => {
			const afterMatchIndex = match[0].length + match.index;
			const nextChar = match.input[afterMatchIndex];
			if (nextChar === "<" || nextChar === ",") {
				response.ignoreMatch();
				return;
			}
			if (nextChar === ">") {
				if (!hasClosingTag(match, { after: afterMatchIndex })) response.ignoreMatch();
			}
			let m;
			const afterMatch = match.input.substring(afterMatchIndex);
			if (m = afterMatch.match(/^\s*=/)) {
				response.ignoreMatch();
				return;
			}
			if (m = afterMatch.match(/^\s+extends\s+/)) {
				if (m.index === 0) {
					response.ignoreMatch();
					return;
				}
			}
		}
	};
	const KEYWORDS$1 = {
		$pattern: IDENT_RE,
		keyword: KEYWORDS,
		literal: LITERALS,
		built_in: BUILT_INS,
		"variable.language": BUILT_IN_VARIABLES
	};
	const decimalDigits = "[0-9](_?[0-9])*";
	const frac = `\\.(${decimalDigits})`;
	const decimalInteger = `0|[1-9](_?[0-9])*|0[0-7]*[89][0-9]*`;
	const NUMBER = {
		className: "number",
		variants: [
			{ begin: `(\\b(${decimalInteger})((${frac})|\\.)?|(${frac}))[eE][+-]?(${decimalDigits})\\b` },
			{ begin: `\\b(${decimalInteger})\\b((${frac})\\b|\\.)?|(${frac})\\b` },
			{ begin: `\\b(0|[1-9](_?[0-9])*)n\\b` },
			{ begin: "\\b0[xX][0-9a-fA-F](_?[0-9a-fA-F])*n?\\b" },
			{ begin: "\\b0[bB][0-1](_?[0-1])*n?\\b" },
			{ begin: "\\b0[oO][0-7](_?[0-7])*n?\\b" },
			{ begin: "\\b0[0-7]+n?\\b" }
		],
		relevance: 0
	};
	const SUBST = {
		className: "subst",
		begin: "\\$\\{",
		end: "\\}",
		keywords: KEYWORDS$1,
		contains: []
	};
	const HTML_TEMPLATE = {
		begin: ".?html`",
		end: "",
		starts: {
			end: "`",
			returnEnd: false,
			contains: [hljs.BACKSLASH_ESCAPE, SUBST],
			subLanguage: "xml"
		}
	};
	const CSS_TEMPLATE = {
		begin: ".?css`",
		end: "",
		starts: {
			end: "`",
			returnEnd: false,
			contains: [hljs.BACKSLASH_ESCAPE, SUBST],
			subLanguage: "css"
		}
	};
	const GRAPHQL_TEMPLATE = {
		begin: ".?gql`",
		end: "",
		starts: {
			end: "`",
			returnEnd: false,
			contains: [hljs.BACKSLASH_ESCAPE, SUBST],
			subLanguage: "graphql"
		}
	};
	const TEMPLATE_STRING = {
		className: "string",
		begin: "`",
		end: "`",
		contains: [hljs.BACKSLASH_ESCAPE, SUBST]
	};
	const COMMENT = {
		className: "comment",
		variants: [
			hljs.COMMENT(/\/\*\*(?!\/)/, "\\*/", {
				relevance: 0,
				contains: [{
					begin: "(?=@[A-Za-z]+)",
					relevance: 0,
					contains: [
						{
							className: "doctag",
							begin: "@[A-Za-z]+"
						},
						{
							className: "type",
							begin: "\\{",
							end: "\\}",
							excludeEnd: true,
							excludeBegin: true,
							relevance: 0
						},
						{
							className: "variable",
							begin: IDENT_RE$1 + "(?=\\s*(-)|$)",
							endsParent: true,
							relevance: 0
						},
						{
							begin: /(?=[^\n])\s/,
							relevance: 0
						}
					]
				}]
			}),
			hljs.C_BLOCK_COMMENT_MODE,
			hljs.C_LINE_COMMENT_MODE
		]
	};
	const SUBST_INTERNALS = [
		hljs.APOS_STRING_MODE,
		hljs.QUOTE_STRING_MODE,
		HTML_TEMPLATE,
		CSS_TEMPLATE,
		GRAPHQL_TEMPLATE,
		TEMPLATE_STRING,
		{ match: /\$\d+/ },
		NUMBER
	];
	SUBST.contains = SUBST_INTERNALS.concat({
		begin: /\{/,
		end: /\}/,
		keywords: KEYWORDS$1,
		contains: ["self"].concat(SUBST_INTERNALS)
	});
	const SUBST_AND_COMMENTS = [].concat(COMMENT, SUBST.contains);
	const PARAMS_CONTAINS = SUBST_AND_COMMENTS.concat([{
		begin: /(\s*)\(/,
		end: /\)/,
		keywords: KEYWORDS$1,
		contains: ["self"].concat(SUBST_AND_COMMENTS)
	}]);
	const PARAMS = {
		className: "params",
		begin: /(\s*)\(/,
		end: /\)/,
		excludeBegin: true,
		excludeEnd: true,
		keywords: KEYWORDS$1,
		contains: PARAMS_CONTAINS
	};
	const CLASS_OR_EXTENDS = { variants: [{
		match: [
			/class/,
			/\s+/,
			IDENT_RE$1,
			/\s+/,
			/extends/,
			/\s+/,
			regex.concat(IDENT_RE$1, "(", regex.concat(/\./, IDENT_RE$1), ")*")
		],
		scope: {
			1: "keyword",
			3: "title.class",
			5: "keyword",
			7: "title.class.inherited"
		}
	}, {
		match: [
			/class/,
			/\s+/,
			IDENT_RE$1
		],
		scope: {
			1: "keyword",
			3: "title.class"
		}
	}] };
	const CLASS_REFERENCE = {
		relevance: 0,
		match: regex.either(/\bJSON/, /\b[A-Z][a-z]+([A-Z][a-z]*|\d)*/, /\b[A-Z]{2,}([A-Z][a-z]+|\d)+([A-Z][a-z]*)*/, /\b[A-Z]{2,}[a-z]+([A-Z][a-z]+|\d)*([A-Z][a-z]*)*/),
		className: "title.class",
		keywords: { _: [...TYPES, ...ERROR_TYPES] }
	};
	const USE_STRICT = {
		label: "use_strict",
		className: "meta",
		relevance: 10,
		begin: /^\s*['"]use (strict|asm)['"]/
	};
	const FUNCTION_DEFINITION = {
		variants: [{ match: [
			/function/,
			/\s+/,
			IDENT_RE$1,
			/(?=\s*\()/
		] }, { match: [/function/, /\s*(?=\()/] }],
		className: {
			1: "keyword",
			3: "title.function"
		},
		label: "func.def",
		contains: [PARAMS],
		illegal: /%/
	};
	const UPPER_CASE_CONSTANT = {
		relevance: 0,
		match: /\b[A-Z][A-Z_0-9]+\b/,
		className: "variable.constant"
	};
	function noneOf(list) {
		return regex.concat("(?!", list.join("|"), ")");
	}
	const FUNCTION_CALL = {
		match: regex.concat(/\b/, noneOf([
			...BUILT_IN_GLOBALS,
			"super",
			"import",
			"await"
		].map((x) => `${x}\\s*\\(`)), IDENT_RE$1, regex.lookahead(/\s*\(/)),
		className: "title.function",
		relevance: 0
	};
	const PROPERTY_ACCESS = {
		begin: regex.concat(/\./, regex.lookahead(regex.concat(IDENT_RE$1, /(?![0-9A-Za-z$_(])/))),
		end: IDENT_RE$1,
		excludeBegin: true,
		keywords: "prototype",
		className: "property",
		relevance: 0
	};
	const GETTER_OR_SETTER = {
		match: [
			/get|set/,
			/\s+/,
			IDENT_RE$1,
			/(?=\()/
		],
		className: {
			1: "keyword",
			3: "title.function"
		},
		contains: [{ begin: /\(\)/ }, PARAMS]
	};
	const FUNC_LEAD_IN_RE = "(\\([^()]*(\\([^()]*(\\([^()]*\\)[^()]*)*\\)[^()]*)*\\)|" + hljs.UNDERSCORE_IDENT_RE + ")\\s*=>";
	const FUNCTION_VARIABLE = {
		match: [
			/const|var|let/,
			/\s+/,
			IDENT_RE$1,
			/\s*/,
			/=\s*/,
			/(async\s*)?/,
			regex.lookahead(FUNC_LEAD_IN_RE)
		],
		keywords: "async",
		className: {
			1: "keyword",
			3: "title.function"
		},
		contains: [PARAMS]
	};
	return {
		name: "JavaScript",
		aliases: [
			"js",
			"jsx",
			"mjs",
			"cjs"
		],
		keywords: KEYWORDS$1,
		exports: {
			PARAMS_CONTAINS,
			CLASS_REFERENCE
		},
		illegal: /#(?![$_A-Za-z])/,
		contains: [
			hljs.SHEBANG({
				label: "shebang",
				binary: "node",
				relevance: 5
			}),
			USE_STRICT,
			hljs.APOS_STRING_MODE,
			hljs.QUOTE_STRING_MODE,
			HTML_TEMPLATE,
			CSS_TEMPLATE,
			GRAPHQL_TEMPLATE,
			TEMPLATE_STRING,
			COMMENT,
			{ match: /\$\d+/ },
			NUMBER,
			CLASS_REFERENCE,
			{
				scope: "attr",
				match: IDENT_RE$1 + regex.lookahead(":"),
				relevance: 0
			},
			FUNCTION_VARIABLE,
			{
				begin: "(" + hljs.RE_STARTERS_RE + "|\\b(case|return|throw)\\b)\\s*",
				keywords: "return throw case",
				relevance: 0,
				contains: [
					COMMENT,
					hljs.REGEXP_MODE,
					{
						className: "function",
						begin: FUNC_LEAD_IN_RE,
						returnBegin: true,
						end: "\\s*=>",
						contains: [{
							className: "params",
							variants: [
								{
									begin: hljs.UNDERSCORE_IDENT_RE,
									relevance: 0
								},
								{
									className: null,
									begin: /\(\s*\)/,
									skip: true
								},
								{
									begin: /(\s*)\(/,
									end: /\)/,
									excludeBegin: true,
									excludeEnd: true,
									keywords: KEYWORDS$1,
									contains: PARAMS_CONTAINS
								}
							]
						}]
					},
					{
						begin: /,/,
						relevance: 0
					},
					{
						match: /\s+/,
						relevance: 0
					},
					{
						variants: [
							{
								begin: FRAGMENT.begin,
								end: FRAGMENT.end
							},
							{ match: XML_SELF_CLOSING },
							{
								begin: XML_TAG.begin,
								"on:begin": XML_TAG.isTrulyOpeningTag,
								end: XML_TAG.end
							}
						],
						subLanguage: "xml",
						contains: [{
							begin: XML_TAG.begin,
							end: XML_TAG.end,
							skip: true,
							contains: ["self"]
						}]
					}
				]
			},
			FUNCTION_DEFINITION,
			{ beginKeywords: "while if switch catch for" },
			{
				begin: "\\b(?!function)" + hljs.UNDERSCORE_IDENT_RE + "\\([^()]*(\\([^()]*(\\([^()]*\\)[^()]*)*\\)[^()]*)*\\)\\s*\\{",
				returnBegin: true,
				label: "func.def",
				contains: [PARAMS, hljs.inherit(hljs.TITLE_MODE, {
					begin: IDENT_RE$1,
					className: "title.function"
				})]
			},
			{
				match: /\.\.\./,
				relevance: 0
			},
			PROPERTY_ACCESS,
			{
				match: "\\$" + IDENT_RE$1,
				relevance: 0
			},
			{
				match: [/\bconstructor(?=\s*\()/],
				className: { 1: "title.function" },
				contains: [PARAMS]
			},
			FUNCTION_CALL,
			UPPER_CASE_CONSTANT,
			CLASS_OR_EXTENDS,
			GETTER_OR_SETTER,
			{ match: /\$[(.]/ }
		]
	};
}
/** @type LanguageFn */
function typescript(hljs) {
	const regex = hljs.regex;
	const tsLanguage = javascript(hljs);
	const IDENT_RE$1 = IDENT_RE;
	const TYPES = [
		"any",
		"void",
		"number",
		"boolean",
		"string",
		"object",
		"never",
		"symbol",
		"bigint",
		"unknown"
	];
	const NAMESPACE = {
		begin: [
			/namespace/,
			/\s+/,
			hljs.IDENT_RE
		],
		beginScope: {
			1: "keyword",
			3: "title.class"
		}
	};
	const INTERFACE = {
		beginKeywords: "interface",
		end: /\{/,
		excludeEnd: true,
		keywords: {
			keyword: "interface extends",
			built_in: TYPES
		},
		contains: [tsLanguage.exports.CLASS_REFERENCE]
	};
	const USE_STRICT = {
		className: "meta",
		relevance: 10,
		begin: /^\s*['"]use strict['"]/
	};
	const KEYWORDS$1 = {
		$pattern: IDENT_RE,
		keyword: KEYWORDS.concat([
			"type",
			"interface",
			"public",
			"private",
			"protected",
			"implements",
			"declare",
			"abstract",
			"readonly",
			"enum",
			"override",
			"satisfies"
		]),
		literal: LITERALS,
		built_in: BUILT_INS.concat(TYPES),
		"variable.language": BUILT_IN_VARIABLES
	};
	const DECORATOR = {
		className: "meta",
		begin: "@" + IDENT_RE$1
	};
	const swapMode = (mode, label, replacement) => {
		const indx = mode.contains.findIndex((m) => m.label === label);
		if (indx === -1) throw new Error("can not find mode to replace");
		mode.contains.splice(indx, 1, replacement);
	};
	Object.assign(tsLanguage.keywords, KEYWORDS$1);
	tsLanguage.exports.PARAMS_CONTAINS.push(DECORATOR);
	const ATTRIBUTE_HIGHLIGHT = tsLanguage.contains.find((c) => c.scope === "attr");
	const OPTIONAL_KEY_OR_ARGUMENT = Object.assign({}, ATTRIBUTE_HIGHLIGHT, { match: regex.concat(IDENT_RE$1, regex.lookahead(/\s*\?:/)) });
	tsLanguage.exports.PARAMS_CONTAINS.push([
		tsLanguage.exports.CLASS_REFERENCE,
		ATTRIBUTE_HIGHLIGHT,
		OPTIONAL_KEY_OR_ARGUMENT
	]);
	tsLanguage.contains = tsLanguage.contains.concat([
		DECORATOR,
		NAMESPACE,
		INTERFACE,
		OPTIONAL_KEY_OR_ARGUMENT
	]);
	swapMode(tsLanguage, "shebang", hljs.SHEBANG());
	swapMode(tsLanguage, "use_strict", USE_STRICT);
	const functionDeclaration = tsLanguage.contains.find((m) => m.label === "func.def");
	functionDeclaration.relevance = 0;
	Object.assign(tsLanguage, {
		name: "TypeScript",
		aliases: [
			"ts",
			"tsx",
			"mts",
			"cts"
		]
	});
	return tsLanguage;
}
//#endregion
//#region node_modules/highlight.js/es/languages/xml.js
/** @type LanguageFn */
function xml(hljs) {
	const regex = hljs.regex;
	const TAG_NAME_RE = regex.concat(/[\p{L}_]/u, regex.optional(/[\p{L}0-9_.-]*:/u), /[\p{L}0-9_.-]*/u);
	const XML_IDENT_RE = /[\p{L}0-9._:-]+/u;
	const XML_ENTITIES = {
		className: "symbol",
		begin: /&[a-z]+;|&#[0-9]+;|&#x[a-f0-9]+;/
	};
	const XML_META_KEYWORDS = {
		begin: /\s/,
		contains: [{
			className: "keyword",
			begin: /#?[a-z_][a-z1-9_-]+/,
			illegal: /\n/
		}]
	};
	const XML_META_PAR_KEYWORDS = hljs.inherit(XML_META_KEYWORDS, {
		begin: /\(/,
		end: /\)/
	});
	const APOS_META_STRING_MODE = hljs.inherit(hljs.APOS_STRING_MODE, { className: "string" });
	const QUOTE_META_STRING_MODE = hljs.inherit(hljs.QUOTE_STRING_MODE, { className: "string" });
	const TAG_INTERNALS = {
		endsWithParent: true,
		illegal: /</,
		relevance: 0,
		contains: [{
			className: "attr",
			begin: XML_IDENT_RE,
			relevance: 0
		}, {
			begin: /=\s*/,
			relevance: 0,
			contains: [{
				className: "string",
				endsParent: true,
				variants: [
					{
						begin: /"/,
						end: /"/,
						contains: [XML_ENTITIES]
					},
					{
						begin: /'/,
						end: /'/,
						contains: [XML_ENTITIES]
					},
					{ begin: /[^\s"'=<>`]+/ }
				]
			}]
		}]
	};
	return {
		name: "HTML, XML",
		aliases: [
			"html",
			"xhtml",
			"rss",
			"atom",
			"xjb",
			"xsd",
			"xsl",
			"plist",
			"wsf",
			"svg"
		],
		case_insensitive: true,
		unicodeRegex: true,
		contains: [
			{
				className: "meta",
				begin: /<![a-z]/,
				end: />/,
				relevance: 10,
				contains: [
					XML_META_KEYWORDS,
					QUOTE_META_STRING_MODE,
					APOS_META_STRING_MODE,
					XML_META_PAR_KEYWORDS,
					{
						begin: /\[/,
						end: /\]/,
						contains: [{
							className: "meta",
							begin: /<![a-z]/,
							end: />/,
							contains: [
								XML_META_KEYWORDS,
								XML_META_PAR_KEYWORDS,
								QUOTE_META_STRING_MODE,
								APOS_META_STRING_MODE
							]
						}]
					}
				]
			},
			hljs.COMMENT(/<!--/, /-->/, { relevance: 10 }),
			{
				begin: /<!\[CDATA\[/,
				end: /\]\]>/,
				relevance: 10
			},
			XML_ENTITIES,
			{
				className: "meta",
				end: /\?>/,
				variants: [{
					begin: /<\?xml/,
					relevance: 10,
					contains: [QUOTE_META_STRING_MODE]
				}, { begin: /<\?[a-z][a-z0-9]+/ }]
			},
			{
				className: "tag",
				begin: /<style(?=\s|>)/,
				end: />/,
				keywords: { name: "style" },
				contains: [TAG_INTERNALS],
				starts: {
					end: /<\/style>/,
					returnEnd: true,
					subLanguage: "css"
				}
			},
			{
				className: "tag",
				begin: /<script(?=\s|>)/,
				end: />/,
				keywords: { name: "script" },
				contains: [TAG_INTERNALS],
				starts: {
					end: /<\/script>/,
					returnEnd: true,
					subLanguage: "javascript"
				}
			},
			{
				className: "tag",
				begin: /<>|<\/>/
			},
			{
				className: "tag",
				begin: regex.concat(/</, regex.lookahead(regex.concat(TAG_NAME_RE, regex.either(/\/>/, />/, /\s/)))),
				end: /\/?>/,
				contains: [{
					className: "name",
					begin: TAG_NAME_RE,
					relevance: 0,
					starts: TAG_INTERNALS
				}]
			},
			{
				className: "tag",
				begin: regex.concat(/<\//, regex.lookahead(regex.concat(TAG_NAME_RE, />/))),
				contains: [{
					className: "name",
					begin: TAG_NAME_RE,
					relevance: 0
				}, {
					begin: />/,
					relevance: 0,
					endsParent: true
				}]
			}
		]
	};
}
//#endregion
//#region node_modules/highlight.js/es/languages/yaml.js
function yaml(hljs) {
	const LITERALS = "true false yes no null";
	const URI_CHARACTERS = "[\\w#;/?:@&=+$,.~*'()[\\]]+";
	const KEY = {
		className: "attr",
		variants: [
			{ begin: /[\w*@][\w*@ :()\./-]*:(?=[ \t]|$)/ },
			{ begin: /"[\w*@][\w*@ :()\./-]*":(?=[ \t]|$)/ },
			{ begin: /'[\w*@][\w*@ :()\./-]*':(?=[ \t]|$)/ }
		]
	};
	const TEMPLATE_VARIABLES = {
		className: "template-variable",
		variants: [{
			begin: /\{\{/,
			end: /\}\}/
		}, {
			begin: /%\{/,
			end: /\}/
		}]
	};
	const SINGLE_QUOTE_STRING = {
		className: "string",
		relevance: 0,
		begin: /'/,
		end: /'/,
		contains: [{
			match: /''/,
			scope: "char.escape",
			relevance: 0
		}]
	};
	const STRING = {
		className: "string",
		relevance: 0,
		variants: [{
			begin: /"/,
			end: /"/
		}, { begin: /\S+/ }],
		contains: [hljs.BACKSLASH_ESCAPE, TEMPLATE_VARIABLES]
	};
	const CONTAINER_STRING = hljs.inherit(STRING, { variants: [
		{
			begin: /'/,
			end: /'/,
			contains: [{
				begin: /''/,
				relevance: 0
			}]
		},
		{
			begin: /"/,
			end: /"/
		},
		{ begin: /[^\s,{}[\]]+/ }
	] });
	const TIMESTAMP = {
		className: "number",
		begin: "\\b[0-9]{4}(-[0-9][0-9]){0,2}([Tt \\t][0-9][0-9]?(:[0-9][0-9]){2})?(\\.[0-9]*)?([ \\t])*(Z|[-+][0-9][0-9]?(:[0-9][0-9])?)?\\b"
	};
	const VALUE_CONTAINER = {
		end: ",",
		endsWithParent: true,
		excludeEnd: true,
		keywords: LITERALS,
		relevance: 0
	};
	const OBJECT = {
		begin: /\{/,
		end: /\}/,
		contains: [VALUE_CONTAINER],
		illegal: "\\n",
		relevance: 0
	};
	const ARRAY = {
		begin: "\\[",
		end: "\\]",
		contains: [VALUE_CONTAINER],
		illegal: "\\n",
		relevance: 0
	};
	const MODES = [
		KEY,
		{
			className: "meta",
			begin: "^---\\s*$",
			relevance: 10
		},
		{
			className: "string",
			begin: "[\\|>]([1-9]?[+-])?[ ]*\\n( +)[^ ][^\\n]*\\n(\\2[^\\n]+\\n?)*"
		},
		{
			begin: "<%[%=-]?",
			end: "[%-]?%>",
			subLanguage: "ruby",
			excludeBegin: true,
			excludeEnd: true,
			relevance: 0
		},
		{
			className: "type",
			begin: "!\\w+!" + URI_CHARACTERS
		},
		{
			className: "type",
			begin: "!<" + URI_CHARACTERS + ">"
		},
		{
			className: "type",
			begin: "!" + URI_CHARACTERS
		},
		{
			className: "type",
			begin: "!!" + URI_CHARACTERS
		},
		{
			className: "meta",
			begin: "&" + hljs.UNDERSCORE_IDENT_RE + "$"
		},
		{
			className: "meta",
			begin: "\\*" + hljs.UNDERSCORE_IDENT_RE + "$"
		},
		{
			className: "bullet",
			begin: "-(?=[ ]|$)",
			relevance: 0
		},
		hljs.HASH_COMMENT_MODE,
		{
			beginKeywords: LITERALS,
			keywords: { literal: LITERALS }
		},
		TIMESTAMP,
		{
			className: "number",
			begin: hljs.C_NUMBER_RE + "\\b",
			relevance: 0
		},
		OBJECT,
		ARRAY,
		SINGLE_QUOTE_STRING,
		STRING
	];
	const VALUE_MODES = [...MODES];
	VALUE_MODES.pop();
	VALUE_MODES.push(CONTAINER_STRING);
	VALUE_CONTAINER.contains = VALUE_MODES;
	return {
		name: "YAML",
		case_insensitive: true,
		aliases: ["yml"],
		contains: MODES
	};
}
var core_default = (/* @__PURE__ */ __toESM((/* @__PURE__ */ __commonJSMin(((exports, module) => {
	function deepFreeze(obj) {
		if (obj instanceof Map) obj.clear = obj.delete = obj.set = function() {
			throw new Error("map is read-only");
		};
		else if (obj instanceof Set) obj.add = obj.clear = obj.delete = function() {
			throw new Error("set is read-only");
		};
		Object.freeze(obj);
		Object.getOwnPropertyNames(obj).forEach((name) => {
			const prop = obj[name];
			const type = typeof prop;
			if ((type === "object" || type === "function") && !Object.isFrozen(prop)) deepFreeze(prop);
		});
		return obj;
	}
	/** @typedef {import('highlight.js').CallbackResponse} CallbackResponse */
	/** @typedef {import('highlight.js').CompiledMode} CompiledMode */
	/** @implements CallbackResponse */
	var Response = class {
		/**
		* @param {CompiledMode} mode
		*/
		constructor(mode) {
			if (mode.data === void 0) mode.data = {};
			this.data = mode.data;
			this.isMatchIgnored = false;
		}
		ignoreMatch() {
			this.isMatchIgnored = true;
		}
	};
	/**
	* @param {string} value
	* @returns {string}
	*/
	function escapeHTML(value) {
		return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
	}
	/**
	* performs a shallow merge of multiple objects into one
	*
	* @template T
	* @param {T} original
	* @param {Record<string,any>[]} objects
	* @returns {T} a single new object
	*/
	function inherit$1(original, ...objects) {
		/** @type Record<string,any> */
		const result = Object.create(null);
		for (const key in original) result[key] = original[key];
		objects.forEach(function(obj) {
			for (const key in obj) result[key] = obj[key];
		});
		return result;
	}
	/**
	* @typedef {object} Renderer
	* @property {(text: string) => void} addText
	* @property {(node: Node) => void} openNode
	* @property {(node: Node) => void} closeNode
	* @property {() => string} value
	*/
	/** @typedef {{scope?: string, language?: string, sublanguage?: boolean}} Node */
	/** @typedef {{walk: (r: Renderer) => void}} Tree */
	/** */
	var SPAN_CLOSE = "</span>";
	/**
	* Determines if a node needs to be wrapped in <span>
	*
	* @param {Node} node */
	var emitsWrappingTags = (node) => {
		return !!node.scope;
	};
	/**
	*
	* @param {string} name
	* @param {{prefix:string}} options
	*/
	var scopeToCSSClass = (name, { prefix }) => {
		if (name.startsWith("language:")) return name.replace("language:", "language-");
		if (name.includes(".")) {
			const pieces = name.split(".");
			return [`${prefix}${pieces.shift()}`, ...pieces.map((x, i) => `${x}${"_".repeat(i + 1)}`)].join(" ");
		}
		return `${prefix}${name}`;
	};
	/** @type {Renderer} */
	var HTMLRenderer = class {
		/**
		* Creates a new HTMLRenderer
		*
		* @param {Tree} parseTree - the parse tree (must support `walk` API)
		* @param {{classPrefix: string}} options
		*/
		constructor(parseTree, options) {
			this.buffer = "";
			this.classPrefix = options.classPrefix;
			parseTree.walk(this);
		}
		/**
		* Adds texts to the output stream
		*
		* @param {string} text */
		addText(text) {
			this.buffer += escapeHTML(text);
		}
		/**
		* Adds a node open to the output stream (if needed)
		*
		* @param {Node} node */
		openNode(node) {
			if (!emitsWrappingTags(node)) return;
			const className = scopeToCSSClass(node.scope, { prefix: this.classPrefix });
			this.span(className);
		}
		/**
		* Adds a node close to the output stream (if needed)
		*
		* @param {Node} node */
		closeNode(node) {
			if (!emitsWrappingTags(node)) return;
			this.buffer += SPAN_CLOSE;
		}
		/**
		* returns the accumulated buffer
		*/
		value() {
			return this.buffer;
		}
		/**
		* Builds a span element
		*
		* @param {string} className */
		span(className) {
			this.buffer += `<span class="${className}">`;
		}
	};
	/** @typedef {{scope?: string, language?: string, children: Node[]} | string} Node */
	/** @typedef {{scope?: string, language?: string, children: Node[]} } DataNode */
	/** @typedef {import('highlight.js').Emitter} Emitter */
	/**  */
	/** @returns {DataNode} */
	var newNode = (opts = {}) => {
		/** @type DataNode */
		const result = { children: [] };
		Object.assign(result, opts);
		return result;
	};
	var TokenTree = class TokenTree {
		constructor() {
			/** @type DataNode */
			this.rootNode = newNode();
			this.stack = [this.rootNode];
		}
		get top() {
			return this.stack[this.stack.length - 1];
		}
		get root() {
			return this.rootNode;
		}
		/** @param {Node} node */
		add(node) {
			this.top.children.push(node);
		}
		/** @param {string} scope */
		openNode(scope) {
			/** @type Node */
			const node = newNode({ scope });
			this.add(node);
			this.stack.push(node);
		}
		closeNode() {
			if (this.stack.length > 1) return this.stack.pop();
		}
		closeAllNodes() {
			while (this.closeNode());
		}
		toJSON() {
			return JSON.stringify(this.rootNode, null, 4);
		}
		/**
		* @typedef { import("./html_renderer").Renderer } Renderer
		* @param {Renderer} builder
		*/
		walk(builder) {
			return this.constructor._walk(builder, this.rootNode);
		}
		/**
		* @param {Renderer} builder
		* @param {Node} node
		*/
		static _walk(builder, node) {
			if (typeof node === "string") builder.addText(node);
			else if (node.children) {
				builder.openNode(node);
				node.children.forEach((child) => this._walk(builder, child));
				builder.closeNode(node);
			}
			return builder;
		}
		/**
		* @param {Node} node
		*/
		static _collapse(node) {
			if (typeof node === "string") return;
			if (!node.children) return;
			if (node.children.every((el) => typeof el === "string")) node.children = [node.children.join("")];
			else node.children.forEach((child) => {
				TokenTree._collapse(child);
			});
		}
	};
	/**
	Currently this is all private API, but this is the minimal API necessary
	that an Emitter must implement to fully support the parser.

	Minimal interface:

	- addText(text)
	- __addSublanguage(emitter, subLanguageName)
	- startScope(scope)
	- endScope()
	- finalize()
	- toHTML()

	*/
	/**
	* @implements {Emitter}
	*/
	var TokenTreeEmitter = class extends TokenTree {
		/**
		* @param {*} options
		*/
		constructor(options) {
			super();
			this.options = options;
		}
		/**
		* @param {string} text
		*/
		addText(text) {
			if (text === "") return;
			this.add(text);
		}
		/** @param {string} scope */
		startScope(scope) {
			this.openNode(scope);
		}
		endScope() {
			this.closeNode();
		}
		/**
		* @param {Emitter & {root: DataNode}} emitter
		* @param {string} name
		*/
		__addSublanguage(emitter, name) {
			/** @type DataNode */
			const node = emitter.root;
			if (name) node.scope = `language:${name}`;
			this.add(node);
		}
		toHTML() {
			return new HTMLRenderer(this, this.options).value();
		}
		finalize() {
			this.closeAllNodes();
			return true;
		}
	};
	/**
	* @param {string} value
	* @returns {RegExp}
	* */
	/**
	* @param {RegExp | string } re
	* @returns {string}
	*/
	function source(re) {
		if (!re) return null;
		if (typeof re === "string") return re;
		return re.source;
	}
	/**
	* @param {RegExp | string } re
	* @returns {string}
	*/
	function lookahead(re) {
		return concat("(?=", re, ")");
	}
	/**
	* @param {RegExp | string } re
	* @returns {string}
	*/
	function anyNumberOfTimes(re) {
		return concat("(?:", re, ")*");
	}
	/**
	* @param {RegExp | string } re
	* @returns {string}
	*/
	function optional(re) {
		return concat("(?:", re, ")?");
	}
	/**
	* @param {...(RegExp | string) } args
	* @returns {string}
	*/
	function concat(...args) {
		return args.map((x) => source(x)).join("");
	}
	/**
	* @param { Array<string | RegExp | Object> } args
	* @returns {object}
	*/
	function stripOptionsFromArgs(args) {
		const opts = args[args.length - 1];
		if (typeof opts === "object" && opts.constructor === Object) {
			args.splice(args.length - 1, 1);
			return opts;
		} else return {};
	}
	/** @typedef { {capture?: boolean} } RegexEitherOptions */
	/**
	* Any of the passed expresssions may match
	*
	* Creates a huge this | this | that | that match
	* @param {(RegExp | string)[] | [...(RegExp | string)[], RegexEitherOptions]} args
	* @returns {string}
	*/
	function either(...args) {
		return "(" + (stripOptionsFromArgs(args).capture ? "" : "?:") + args.map((x) => source(x)).join("|") + ")";
	}
	/**
	* @param {RegExp | string} re
	* @returns {number}
	*/
	function countMatchGroups(re) {
		return new RegExp(re.toString() + "|").exec("").length - 1;
	}
	/**
	* Does lexeme start with a regular expression match at the beginning
	* @param {RegExp} re
	* @param {string} lexeme
	*/
	function startsWith(re, lexeme) {
		const match = re && re.exec(lexeme);
		return match && match.index === 0;
	}
	var BACKREF_RE = /\[(?:[^\\\]]|\\.)*\]|\(\??|\\([1-9][0-9]*)|\\./;
	/**
	* @param {(string | RegExp)[]} regexps
	* @param {{joinWith: string}} opts
	* @returns {string}
	*/
	function _rewriteBackreferences(regexps, { joinWith }) {
		let numCaptures = 0;
		return regexps.map((regex) => {
			numCaptures += 1;
			const offset = numCaptures;
			let re = source(regex);
			let out = "";
			while (re.length > 0) {
				const match = BACKREF_RE.exec(re);
				if (!match) {
					out += re;
					break;
				}
				out += re.substring(0, match.index);
				re = re.substring(match.index + match[0].length);
				if (match[0][0] === "\\" && match[1]) out += "\\" + String(Number(match[1]) + offset);
				else {
					out += match[0];
					if (match[0] === "(") numCaptures++;
				}
			}
			return out;
		}).map((re) => `(${re})`).join(joinWith);
	}
	/** @typedef {import('highlight.js').Mode} Mode */
	/** @typedef {import('highlight.js').ModeCallback} ModeCallback */
	var MATCH_NOTHING_RE = /\b\B/;
	var IDENT_RE = "[a-zA-Z]\\w*";
	var UNDERSCORE_IDENT_RE = "[a-zA-Z_]\\w*";
	var NUMBER_RE = "\\b\\d+(\\.\\d+)?";
	var C_NUMBER_RE = "(-?)(\\b0[xX][a-fA-F0-9]+|(\\b\\d+(\\.\\d*)?|\\.\\d+)([eE][-+]?\\d+)?)";
	var BINARY_NUMBER_RE = "\\b(0b[01]+)";
	var RE_STARTERS_RE = "!|!=|!==|%|%=|&|&&|&=|\\*|\\*=|\\+|\\+=|,|-|-=|/=|/|:|;|<<|<<=|<=|<|===|==|=|>>>=|>>=|>=|>>>|>>|>|\\?|\\[|\\{|\\(|\\^|\\^=|\\||\\|=|\\|\\||~";
	/**
	* @param { Partial<Mode> & {binary?: string | RegExp} } opts
	*/
	var SHEBANG = (opts = {}) => {
		const beginShebang = /^#![ ]*\//;
		if (opts.binary) opts.begin = concat(beginShebang, /.*\b/, opts.binary, /\b.*/);
		return inherit$1({
			scope: "meta",
			begin: beginShebang,
			end: /$/,
			relevance: 0,
			/** @type {ModeCallback} */
			"on:begin": (m, resp) => {
				if (m.index !== 0) resp.ignoreMatch();
			}
		}, opts);
	};
	var BACKSLASH_ESCAPE = {
		begin: "\\\\[\\s\\S]",
		relevance: 0
	};
	var APOS_STRING_MODE = {
		scope: "string",
		begin: "'",
		end: "'",
		illegal: "\\n",
		contains: [BACKSLASH_ESCAPE]
	};
	var QUOTE_STRING_MODE = {
		scope: "string",
		begin: "\"",
		end: "\"",
		illegal: "\\n",
		contains: [BACKSLASH_ESCAPE]
	};
	var PHRASAL_WORDS_MODE = { begin: /\b(a|an|the|are|I'm|isn't|don't|doesn't|won't|but|just|should|pretty|simply|enough|gonna|going|wtf|so|such|will|you|your|they|like|more)\b/ };
	/**
	* Creates a comment mode
	*
	* @param {string | RegExp} begin
	* @param {string | RegExp} end
	* @param {Mode | {}} [modeOptions]
	* @returns {Partial<Mode>}
	*/
	var COMMENT = function(begin, end, modeOptions = {}) {
		const mode = inherit$1({
			scope: "comment",
			begin,
			end,
			contains: []
		}, modeOptions);
		mode.contains.push({
			scope: "doctag",
			begin: "[ ]*(?=(TODO|FIXME|NOTE|BUG|OPTIMIZE|HACK|XXX):)",
			end: /(TODO|FIXME|NOTE|BUG|OPTIMIZE|HACK|XXX):/,
			excludeBegin: true,
			relevance: 0
		});
		const ENGLISH_WORD = either("I", "a", "is", "so", "us", "to", "at", "if", "in", "it", "on", /[A-Za-z]+['](d|ve|re|ll|t|s|n)/, /[A-Za-z]+[-][a-z]+/, /[A-Za-z][a-z]{2,}/);
		mode.contains.push({ begin: concat(/[ ]+/, "(", ENGLISH_WORD, /[.]?[:]?([.][ ]|[ ])/, "){3}") });
		return mode;
	};
	var C_LINE_COMMENT_MODE = COMMENT("//", "$");
	var C_BLOCK_COMMENT_MODE = COMMENT("/\\*", "\\*/");
	var HASH_COMMENT_MODE = COMMENT("#", "$");
	var NUMBER_MODE = {
		scope: "number",
		begin: NUMBER_RE,
		relevance: 0
	};
	var C_NUMBER_MODE = {
		scope: "number",
		begin: C_NUMBER_RE,
		relevance: 0
	};
	var BINARY_NUMBER_MODE = {
		scope: "number",
		begin: BINARY_NUMBER_RE,
		relevance: 0
	};
	var REGEXP_MODE = {
		scope: "regexp",
		begin: /\/(?=[^/\n]*\/)/,
		end: /\/[gimuy]*/,
		contains: [BACKSLASH_ESCAPE, {
			begin: /\[/,
			end: /\]/,
			relevance: 0,
			contains: [BACKSLASH_ESCAPE]
		}]
	};
	var TITLE_MODE = {
		scope: "title",
		begin: IDENT_RE,
		relevance: 0
	};
	var UNDERSCORE_TITLE_MODE = {
		scope: "title",
		begin: UNDERSCORE_IDENT_RE,
		relevance: 0
	};
	var METHOD_GUARD = {
		begin: "\\.\\s*[a-zA-Z_]\\w*",
		relevance: 0
	};
	/**
	* Adds end same as begin mechanics to a mode
	*
	* Your mode must include at least a single () match group as that first match
	* group is what is used for comparison
	* @param {Partial<Mode>} mode
	*/
	var END_SAME_AS_BEGIN = function(mode) {
		return Object.assign(mode, {
			/** @type {ModeCallback} */
			"on:begin": (m, resp) => {
				resp.data._beginMatch = m[1];
			},
			/** @type {ModeCallback} */
			"on:end": (m, resp) => {
				if (resp.data._beginMatch !== m[1]) resp.ignoreMatch();
			}
		});
	};
	var MODES = /*#__PURE__*/ Object.freeze({
		__proto__: null,
		APOS_STRING_MODE,
		BACKSLASH_ESCAPE,
		BINARY_NUMBER_MODE,
		BINARY_NUMBER_RE,
		COMMENT,
		C_BLOCK_COMMENT_MODE,
		C_LINE_COMMENT_MODE,
		C_NUMBER_MODE,
		C_NUMBER_RE,
		END_SAME_AS_BEGIN,
		HASH_COMMENT_MODE,
		IDENT_RE,
		MATCH_NOTHING_RE,
		METHOD_GUARD,
		NUMBER_MODE,
		NUMBER_RE,
		PHRASAL_WORDS_MODE,
		QUOTE_STRING_MODE,
		REGEXP_MODE,
		RE_STARTERS_RE,
		SHEBANG,
		TITLE_MODE,
		UNDERSCORE_IDENT_RE,
		UNDERSCORE_TITLE_MODE
	});
	/**
	@typedef {import('highlight.js').CallbackResponse} CallbackResponse
	@typedef {import('highlight.js').CompilerExt} CompilerExt
	*/
	/**
	* Skip a match if it has a preceding dot
	*
	* This is used for `beginKeywords` to prevent matching expressions such as
	* `bob.keyword.do()`. The mode compiler automatically wires this up as a
	* special _internal_ 'on:begin' callback for modes with `beginKeywords`
	* @param {RegExpMatchArray} match
	* @param {CallbackResponse} response
	*/
	function skipIfHasPrecedingDot(match, response) {
		if (match.input[match.index - 1] === ".") response.ignoreMatch();
	}
	/**
	*
	* @type {CompilerExt}
	*/
	function scopeClassName(mode, _parent) {
		if (mode.className !== void 0) {
			mode.scope = mode.className;
			delete mode.className;
		}
	}
	/**
	* `beginKeywords` syntactic sugar
	* @type {CompilerExt}
	*/
	function beginKeywords(mode, parent) {
		if (!parent) return;
		if (!mode.beginKeywords) return;
		mode.begin = "\\b(" + mode.beginKeywords.split(" ").join("|") + ")(?!\\.)(?=\\b|\\s)";
		mode.__beforeBegin = skipIfHasPrecedingDot;
		mode.keywords = mode.keywords || mode.beginKeywords;
		delete mode.beginKeywords;
		if (mode.relevance === void 0) mode.relevance = 0;
	}
	/**
	* Allow `illegal` to contain an array of illegal values
	* @type {CompilerExt}
	*/
	function compileIllegal(mode, _parent) {
		if (!Array.isArray(mode.illegal)) return;
		mode.illegal = either(...mode.illegal);
	}
	/**
	* `match` to match a single expression for readability
	* @type {CompilerExt}
	*/
	function compileMatch(mode, _parent) {
		if (!mode.match) return;
		if (mode.begin || mode.end) throw new Error("begin & end are not supported with match");
		mode.begin = mode.match;
		delete mode.match;
	}
	/**
	* provides the default 1 relevance to all modes
	* @type {CompilerExt}
	*/
	function compileRelevance(mode, _parent) {
		if (mode.relevance === void 0) mode.relevance = 1;
	}
	var beforeMatchExt = (mode, parent) => {
		if (!mode.beforeMatch) return;
		if (mode.starts) throw new Error("beforeMatch cannot be used with starts");
		const originalMode = Object.assign({}, mode);
		Object.keys(mode).forEach((key) => {
			delete mode[key];
		});
		mode.keywords = originalMode.keywords;
		mode.begin = concat(originalMode.beforeMatch, lookahead(originalMode.begin));
		mode.starts = {
			relevance: 0,
			contains: [Object.assign(originalMode, { endsParent: true })]
		};
		mode.relevance = 0;
		delete originalMode.beforeMatch;
	};
	var COMMON_KEYWORDS = [
		"of",
		"and",
		"for",
		"in",
		"not",
		"or",
		"if",
		"then",
		"parent",
		"list",
		"value"
	];
	var DEFAULT_KEYWORD_SCOPE = "keyword";
	/**
	* Given raw keywords from a language definition, compile them.
	*
	* @param {string | Record<string,string|string[]> | Array<string>} rawKeywords
	* @param {boolean} caseInsensitive
	*/
	function compileKeywords(rawKeywords, caseInsensitive, scopeName = DEFAULT_KEYWORD_SCOPE) {
		/** @type {import("highlight.js/private").KeywordDict} */
		const compiledKeywords = Object.create(null);
		if (typeof rawKeywords === "string") compileList(scopeName, rawKeywords.split(" "));
		else if (Array.isArray(rawKeywords)) compileList(scopeName, rawKeywords);
		else Object.keys(rawKeywords).forEach(function(scopeName) {
			Object.assign(compiledKeywords, compileKeywords(rawKeywords[scopeName], caseInsensitive, scopeName));
		});
		return compiledKeywords;
		/**
		* Compiles an individual list of keywords
		*
		* Ex: "for if when while|5"
		*
		* @param {string} scopeName
		* @param {Array<string>} keywordList
		*/
		function compileList(scopeName, keywordList) {
			if (caseInsensitive) keywordList = keywordList.map((x) => x.toLowerCase());
			keywordList.forEach(function(keyword) {
				const pair = keyword.split("|");
				compiledKeywords[pair[0]] = [scopeName, scoreForKeyword(pair[0], pair[1])];
			});
		}
	}
	/**
	* Returns the proper score for a given keyword
	*
	* Also takes into account comment keywords, which will be scored 0 UNLESS
	* another score has been manually assigned.
	* @param {string} keyword
	* @param {string} [providedScore]
	*/
	function scoreForKeyword(keyword, providedScore) {
		if (providedScore) return Number(providedScore);
		return commonKeyword(keyword) ? 0 : 1;
	}
	/**
	* Determines if a given keyword is common or not
	*
	* @param {string} keyword */
	function commonKeyword(keyword) {
		return COMMON_KEYWORDS.includes(keyword.toLowerCase());
	}
	/**
	* @type {Record<string, boolean>}
	*/
	var seenDeprecations = {};
	/**
	* @param {string} message
	*/
	var error = (message) => {
		console.error(message);
	};
	/**
	* @param {string} message
	* @param {any} args
	*/
	var warn = (message, ...args) => {
		console.log(`WARN: ${message}`, ...args);
	};
	/**
	* @param {string} version
	* @param {string} message
	*/
	var deprecated = (version, message) => {
		if (seenDeprecations[`${version}/${message}`]) return;
		console.log(`Deprecated as of ${version}. ${message}`);
		seenDeprecations[`${version}/${message}`] = true;
	};
	/**
	@typedef {import('highlight.js').CompiledMode} CompiledMode
	*/
	var MultiClassError = /* @__PURE__ */ new Error();
	/**
	* Renumbers labeled scope names to account for additional inner match
	* groups that otherwise would break everything.
	*
	* Lets say we 3 match scopes:
	*
	*   { 1 => ..., 2 => ..., 3 => ... }
	*
	* So what we need is a clean match like this:
	*
	*   (a)(b)(c) => [ "a", "b", "c" ]
	*
	* But this falls apart with inner match groups:
	*
	* (a)(((b)))(c) => ["a", "b", "b", "b", "c" ]
	*
	* Our scopes are now "out of alignment" and we're repeating `b` 3 times.
	* What needs to happen is the numbers are remapped:
	*
	*   { 1 => ..., 2 => ..., 5 => ... }
	*
	* We also need to know that the ONLY groups that should be output
	* are 1, 2, and 5.  This function handles this behavior.
	*
	* @param {CompiledMode} mode
	* @param {Array<RegExp | string>} regexes
	* @param {{key: "beginScope"|"endScope"}} opts
	*/
	function remapScopeNames(mode, regexes, { key }) {
		let offset = 0;
		const scopeNames = mode[key];
		/** @type Record<number,boolean> */
		const emit = {};
		/** @type Record<number,string> */
		const positions = {};
		for (let i = 1; i <= regexes.length; i++) {
			positions[i + offset] = scopeNames[i];
			emit[i + offset] = true;
			offset += countMatchGroups(regexes[i - 1]);
		}
		mode[key] = positions;
		mode[key]._emit = emit;
		mode[key]._multi = true;
	}
	/**
	* @param {CompiledMode} mode
	*/
	function beginMultiClass(mode) {
		if (!Array.isArray(mode.begin)) return;
		if (mode.skip || mode.excludeBegin || mode.returnBegin) {
			error("skip, excludeBegin, returnBegin not compatible with beginScope: {}");
			throw MultiClassError;
		}
		if (typeof mode.beginScope !== "object" || mode.beginScope === null) {
			error("beginScope must be object");
			throw MultiClassError;
		}
		remapScopeNames(mode, mode.begin, { key: "beginScope" });
		mode.begin = _rewriteBackreferences(mode.begin, { joinWith: "" });
	}
	/**
	* @param {CompiledMode} mode
	*/
	function endMultiClass(mode) {
		if (!Array.isArray(mode.end)) return;
		if (mode.skip || mode.excludeEnd || mode.returnEnd) {
			error("skip, excludeEnd, returnEnd not compatible with endScope: {}");
			throw MultiClassError;
		}
		if (typeof mode.endScope !== "object" || mode.endScope === null) {
			error("endScope must be object");
			throw MultiClassError;
		}
		remapScopeNames(mode, mode.end, { key: "endScope" });
		mode.end = _rewriteBackreferences(mode.end, { joinWith: "" });
	}
	/**
	* this exists only to allow `scope: {}` to be used beside `match:`
	* Otherwise `beginScope` would necessary and that would look weird

	{
	match: [ /def/, /\w+/ ]
	scope: { 1: "keyword" , 2: "title" }
	}

	* @param {CompiledMode} mode
	*/
	function scopeSugar(mode) {
		if (mode.scope && typeof mode.scope === "object" && mode.scope !== null) {
			mode.beginScope = mode.scope;
			delete mode.scope;
		}
	}
	/**
	* @param {CompiledMode} mode
	*/
	function MultiClass(mode) {
		scopeSugar(mode);
		if (typeof mode.beginScope === "string") mode.beginScope = { _wrap: mode.beginScope };
		if (typeof mode.endScope === "string") mode.endScope = { _wrap: mode.endScope };
		beginMultiClass(mode);
		endMultiClass(mode);
	}
	/**
	@typedef {import('highlight.js').Mode} Mode
	@typedef {import('highlight.js').CompiledMode} CompiledMode
	@typedef {import('highlight.js').Language} Language
	@typedef {import('highlight.js').HLJSPlugin} HLJSPlugin
	@typedef {import('highlight.js').CompiledLanguage} CompiledLanguage
	*/
	/**
	* Compiles a language definition result
	*
	* Given the raw result of a language definition (Language), compiles this so
	* that it is ready for highlighting code.
	* @param {Language} language
	* @returns {CompiledLanguage}
	*/
	function compileLanguage(language) {
		/**
		* Builds a regex with the case sensitivity of the current language
		*
		* @param {RegExp | string} value
		* @param {boolean} [global]
		*/
		function langRe(value, global) {
			return new RegExp(source(value), "m" + (language.case_insensitive ? "i" : "") + (language.unicodeRegex ? "u" : "") + (global ? "g" : ""));
		}
		/**
		Stores multiple regular expressions and allows you to quickly search for
		them all in a string simultaneously - returning the first match.  It does
		this by creating a huge (a|b|c) regex - each individual item wrapped with ()
		and joined by `|` - using match groups to track position.  When a match is
		found checking which position in the array has content allows us to figure
		out which of the original regexes / match groups triggered the match.

		The match object itself (the result of `Regex.exec`) is returned but also
		enhanced by merging in any meta-data that was registered with the regex.
		This is how we keep track of which mode matched, and what type of rule
		(`illegal`, `begin`, end, etc).
		*/
		class MultiRegex {
			constructor() {
				this.matchIndexes = {};
				this.regexes = [];
				this.matchAt = 1;
				this.position = 0;
			}
			addRule(re, opts) {
				opts.position = this.position++;
				this.matchIndexes[this.matchAt] = opts;
				this.regexes.push([opts, re]);
				this.matchAt += countMatchGroups(re) + 1;
			}
			compile() {
				if (this.regexes.length === 0) this.exec = () => null;
				const terminators = this.regexes.map((el) => el[1]);
				this.matcherRe = langRe(_rewriteBackreferences(terminators, { joinWith: "|" }), true);
				this.lastIndex = 0;
			}
			/** @param {string} s */
			exec(s) {
				this.matcherRe.lastIndex = this.lastIndex;
				const match = this.matcherRe.exec(s);
				if (!match) return null;
				const i = match.findIndex((el, i) => i > 0 && el !== void 0);
				const matchData = this.matchIndexes[i];
				match.splice(0, i);
				return Object.assign(match, matchData);
			}
		}
		class ResumableMultiRegex {
			constructor() {
				this.rules = [];
				this.multiRegexes = [];
				this.count = 0;
				this.lastIndex = 0;
				this.regexIndex = 0;
			}
			getMatcher(index) {
				if (this.multiRegexes[index]) return this.multiRegexes[index];
				const matcher = new MultiRegex();
				this.rules.slice(index).forEach(([re, opts]) => matcher.addRule(re, opts));
				matcher.compile();
				this.multiRegexes[index] = matcher;
				return matcher;
			}
			resumingScanAtSamePosition() {
				return this.regexIndex !== 0;
			}
			considerAll() {
				this.regexIndex = 0;
			}
			addRule(re, opts) {
				this.rules.push([re, opts]);
				if (opts.type === "begin") this.count++;
			}
			/** @param {string} s */
			exec(s) {
				const m = this.getMatcher(this.regexIndex);
				m.lastIndex = this.lastIndex;
				let result = m.exec(s);
				if (this.resumingScanAtSamePosition()) {
					if (result && result.index === this.lastIndex);
					else {
						const m2 = this.getMatcher(0);
						m2.lastIndex = this.lastIndex + 1;
						result = m2.exec(s);
					}
				}
				if (result) {
					this.regexIndex += result.position + 1;
					if (this.regexIndex === this.count) this.considerAll();
				}
				return result;
			}
		}
		/**
		* Given a mode, builds a huge ResumableMultiRegex that can be used to walk
		* the content and find matches.
		*
		* @param {CompiledMode} mode
		* @returns {ResumableMultiRegex}
		*/
		function buildModeRegex(mode) {
			const mm = new ResumableMultiRegex();
			mode.contains.forEach((term) => mm.addRule(term.begin, {
				rule: term,
				type: "begin"
			}));
			if (mode.terminatorEnd) mm.addRule(mode.terminatorEnd, { type: "end" });
			if (mode.illegal) mm.addRule(mode.illegal, { type: "illegal" });
			return mm;
		}
		/** skip vs abort vs ignore
		*
		* @skip   - The mode is still entered and exited normally (and contains rules apply),
		*           but all content is held and added to the parent buffer rather than being
		*           output when the mode ends.  Mostly used with `sublanguage` to build up
		*           a single large buffer than can be parsed by sublanguage.
		*
		*             - The mode begin ands ends normally.
		*             - Content matched is added to the parent mode buffer.
		*             - The parser cursor is moved forward normally.
		*
		* @abort  - A hack placeholder until we have ignore.  Aborts the mode (as if it
		*           never matched) but DOES NOT continue to match subsequent `contains`
		*           modes.  Abort is bad/suboptimal because it can result in modes
		*           farther down not getting applied because an earlier rule eats the
		*           content but then aborts.
		*
		*             - The mode does not begin.
		*             - Content matched by `begin` is added to the mode buffer.
		*             - The parser cursor is moved forward accordingly.
		*
		* @ignore - Ignores the mode (as if it never matched) and continues to match any
		*           subsequent `contains` modes.  Ignore isn't technically possible with
		*           the current parser implementation.
		*
		*             - The mode does not begin.
		*             - Content matched by `begin` is ignored.
		*             - The parser cursor is not moved forward.
		*/
		/**
		* Compiles an individual mode
		*
		* This can raise an error if the mode contains certain detectable known logic
		* issues.
		* @param {Mode} mode
		* @param {CompiledMode | null} [parent]
		* @returns {CompiledMode | never}
		*/
		function compileMode(mode, parent) {
			const cmode = mode;
			if (mode.isCompiled) return cmode;
			[
				scopeClassName,
				compileMatch,
				MultiClass,
				beforeMatchExt
			].forEach((ext) => ext(mode, parent));
			language.compilerExtensions.forEach((ext) => ext(mode, parent));
			mode.__beforeBegin = null;
			[
				beginKeywords,
				compileIllegal,
				compileRelevance
			].forEach((ext) => ext(mode, parent));
			mode.isCompiled = true;
			let keywordPattern = null;
			if (typeof mode.keywords === "object" && mode.keywords.$pattern) {
				mode.keywords = Object.assign({}, mode.keywords);
				keywordPattern = mode.keywords.$pattern;
				delete mode.keywords.$pattern;
			}
			keywordPattern = keywordPattern || /\w+/;
			if (mode.keywords) mode.keywords = compileKeywords(mode.keywords, language.case_insensitive);
			cmode.keywordPatternRe = langRe(keywordPattern, true);
			if (parent) {
				if (!mode.begin) mode.begin = /\B|\b/;
				cmode.beginRe = langRe(cmode.begin);
				if (!mode.end && !mode.endsWithParent) mode.end = /\B|\b/;
				if (mode.end) cmode.endRe = langRe(cmode.end);
				cmode.terminatorEnd = source(cmode.end) || "";
				if (mode.endsWithParent && parent.terminatorEnd) cmode.terminatorEnd += (mode.end ? "|" : "") + parent.terminatorEnd;
			}
			if (mode.illegal) cmode.illegalRe = langRe(mode.illegal);
			if (!mode.contains) mode.contains = [];
			mode.contains = [].concat(...mode.contains.map(function(c) {
				return expandOrCloneMode(c === "self" ? mode : c);
			}));
			mode.contains.forEach(function(c) {
				compileMode(c, cmode);
			});
			if (mode.starts) compileMode(mode.starts, parent);
			cmode.matcher = buildModeRegex(cmode);
			return cmode;
		}
		if (!language.compilerExtensions) language.compilerExtensions = [];
		if (language.contains && language.contains.includes("self")) throw new Error("ERR: contains `self` is not supported at the top-level of a language.  See documentation.");
		language.classNameAliases = inherit$1(language.classNameAliases || {});
		return compileMode(language);
	}
	/**
	* Determines if a mode has a dependency on it's parent or not
	*
	* If a mode does have a parent dependency then often we need to clone it if
	* it's used in multiple places so that each copy points to the correct parent,
	* where-as modes without a parent can often safely be re-used at the bottom of
	* a mode chain.
	*
	* @param {Mode | null} mode
	* @returns {boolean} - is there a dependency on the parent?
	* */
	function dependencyOnParent(mode) {
		if (!mode) return false;
		return mode.endsWithParent || dependencyOnParent(mode.starts);
	}
	/**
	* Expands a mode or clones it if necessary
	*
	* This is necessary for modes with parental dependenceis (see notes on
	* `dependencyOnParent`) and for nodes that have `variants` - which must then be
	* exploded into their own individual modes at compile time.
	*
	* @param {Mode} mode
	* @returns {Mode | Mode[]}
	* */
	function expandOrCloneMode(mode) {
		if (mode.variants && !mode.cachedVariants) mode.cachedVariants = mode.variants.map(function(variant) {
			return inherit$1(mode, { variants: null }, variant);
		});
		if (mode.cachedVariants) return mode.cachedVariants;
		if (dependencyOnParent(mode)) return inherit$1(mode, { starts: mode.starts ? inherit$1(mode.starts) : null });
		if (Object.isFrozen(mode)) return inherit$1(mode);
		return mode;
	}
	var version = "11.11.2";
	var HTMLInjectionError = class extends Error {
		constructor(reason, html) {
			super(reason);
			this.name = "HTMLInjectionError";
			this.html = html;
		}
	};
	/**
	@typedef {import('highlight.js').Mode} Mode
	@typedef {import('highlight.js').CompiledMode} CompiledMode
	@typedef {import('highlight.js').CompiledScope} CompiledScope
	@typedef {import('highlight.js').Language} Language
	@typedef {import('highlight.js').HLJSApi} HLJSApi
	@typedef {import('highlight.js').HLJSPlugin} HLJSPlugin
	@typedef {import('highlight.js').PluginEvent} PluginEvent
	@typedef {import('highlight.js').HLJSOptions} HLJSOptions
	@typedef {import('highlight.js').LanguageFn} LanguageFn
	@typedef {import('highlight.js').HighlightedHTMLElement} HighlightedHTMLElement
	@typedef {import('highlight.js').BeforeHighlightContext} BeforeHighlightContext
	@typedef {import('highlight.js/private').MatchType} MatchType
	@typedef {import('highlight.js/private').KeywordData} KeywordData
	@typedef {import('highlight.js/private').EnhancedMatch} EnhancedMatch
	@typedef {import('highlight.js/private').AnnotatedError} AnnotatedError
	@typedef {import('highlight.js').AutoHighlightResult} AutoHighlightResult
	@typedef {import('highlight.js').HighlightOptions} HighlightOptions
	@typedef {import('highlight.js').HighlightResult} HighlightResult
	*/
	var escape = escapeHTML;
	var inherit = inherit$1;
	var NO_MATCH = Symbol("nomatch");
	var MAX_KEYWORD_HITS = 7;
	/**
	* @param {any} hljs - object that is extended (legacy)
	* @returns {HLJSApi}
	*/
	var HLJS = function(hljs) {
		/** @type {Record<string, Language>} */
		const languages = Object.create(null);
		/** @type {Record<string, string>} */
		const aliases = Object.create(null);
		/** @type {HLJSPlugin[]} */
		const plugins = [];
		let SAFE_MODE = true;
		const LANGUAGE_NOT_FOUND = "Could not find the language '{}', did you forget to load/include a language module?";
		/** @type {Language} */
		const PLAINTEXT_LANGUAGE = {
			disableAutodetect: true,
			name: "Plain text",
			contains: []
		};
		/** @type HLJSOptions */
		let options = {
			ignoreUnescapedHTML: false,
			throwUnescapedHTML: false,
			noHighlightRe: /^(no-?highlight)$/i,
			languageDetectRe: /\blang(?:uage)?-([\w-]+)\b/i,
			classPrefix: "hljs-",
			cssSelector: "pre code",
			languages: null,
			__emitter: TokenTreeEmitter
		};
		/**
		* Tests a language name to see if highlighting should be skipped
		* @param {string} languageName
		*/
		function shouldNotHighlight(languageName) {
			return options.noHighlightRe.test(languageName);
		}
		/**
		* @param {HighlightedHTMLElement} block - the HTML element to determine language for
		*/
		function blockLanguage(block) {
			let classes = block.className + " ";
			classes += block.parentNode ? block.parentNode.className : "";
			const match = options.languageDetectRe.exec(classes);
			if (match) {
				const language = getLanguage(match[1]);
				if (!language) {
					warn(LANGUAGE_NOT_FOUND.replace("{}", match[1]));
					warn("Falling back to no-highlight mode for this block.", block);
				}
				return language ? match[1] : "no-highlight";
			}
			return classes.split(/\s+/).find((_class) => shouldNotHighlight(_class) || getLanguage(_class));
		}
		/**
		* Core highlighting function.
		*
		* OLD API
		* highlight(lang, code, ignoreIllegals, continuation)
		*
		* NEW API
		* highlight(code, {lang, ignoreIllegals})
		*
		* @param {string} codeOrLanguageName - the language to use for highlighting
		* @param {string | HighlightOptions} optionsOrCode - the code to highlight
		* @param {boolean} [ignoreIllegals] - whether to ignore illegal matches, default is to bail
		*
		* @returns {HighlightResult} Result - an object that represents the result
		* @property {string} language - the language name
		* @property {number} relevance - the relevance score
		* @property {string} value - the highlighted HTML code
		* @property {string} code - the original raw code
		* @property {CompiledMode} top - top of the current mode stack
		* @property {boolean} illegal - indicates whether any illegal matches were found
		*/
		function highlight(codeOrLanguageName, optionsOrCode, ignoreIllegals) {
			let code = "";
			let languageName = "";
			if (typeof optionsOrCode === "object") {
				code = codeOrLanguageName;
				ignoreIllegals = optionsOrCode.ignoreIllegals;
				languageName = optionsOrCode.language;
			} else {
				deprecated("10.7.0", "highlight(lang, code, ...args) has been deprecated.");
				deprecated("10.7.0", "Please use highlight(code, options) instead.\nhttps://github.com/highlightjs/highlight.js/issues/2277");
				languageName = codeOrLanguageName;
				code = optionsOrCode;
			}
			if (ignoreIllegals === void 0) ignoreIllegals = true;
			/** @type {BeforeHighlightContext} */
			const context = {
				code,
				language: languageName
			};
			fire("before:highlight", context);
			const result = context.result ? context.result : _highlight(context.language, context.code, ignoreIllegals);
			result.code = context.code;
			fire("after:highlight", result);
			return result;
		}
		/**
		* private highlight that's used internally and does not fire callbacks
		*
		* @param {string} languageName - the language to use for highlighting
		* @param {string} codeToHighlight - the code to highlight
		* @param {boolean?} [ignoreIllegals] - whether to ignore illegal matches, default is to bail
		* @param {CompiledMode?} [continuation] - current continuation mode, if any
		* @returns {HighlightResult} - result of the highlight operation
		*/
		function _highlight(languageName, codeToHighlight, ignoreIllegals, continuation) {
			const keywordHits = Object.create(null);
			/**
			* Return keyword data if a match is a keyword
			* @param {CompiledMode} mode - current mode
			* @param {string} matchText - the textual match
			* @returns {KeywordData | false}
			*/
			function keywordData(mode, matchText) {
				return mode.keywords[matchText];
			}
			function processKeywords() {
				if (!top.keywords) {
					emitter.addText(modeBuffer);
					return;
				}
				let lastIndex = 0;
				top.keywordPatternRe.lastIndex = 0;
				let match = top.keywordPatternRe.exec(modeBuffer);
				let buf = "";
				while (match) {
					buf += modeBuffer.substring(lastIndex, match.index);
					const word = language.case_insensitive ? match[0].toLowerCase() : match[0];
					const data = keywordData(top, word);
					if (data) {
						const [kind, keywordRelevance] = data;
						emitter.addText(buf);
						buf = "";
						keywordHits[word] = (keywordHits[word] || 0) + 1;
						if (keywordHits[word] <= MAX_KEYWORD_HITS) relevance += keywordRelevance;
						if (kind.startsWith("_")) buf += match[0];
						else {
							const cssClass = language.classNameAliases[kind] || kind;
							emitKeyword(match[0], cssClass);
						}
					} else buf += match[0];
					lastIndex = top.keywordPatternRe.lastIndex;
					match = top.keywordPatternRe.exec(modeBuffer);
				}
				buf += modeBuffer.substring(lastIndex);
				emitter.addText(buf);
			}
			function processSubLanguage() {
				if (modeBuffer === "") return;
				/** @type HighlightResult */
				let result = null;
				if (typeof top.subLanguage === "string") {
					if (!languages[top.subLanguage]) {
						emitter.addText(modeBuffer);
						return;
					}
					result = _highlight(top.subLanguage, modeBuffer, true, continuations[top.subLanguage]);
					continuations[top.subLanguage] = result._top;
				} else result = highlightAuto(modeBuffer, top.subLanguage.length ? top.subLanguage : null);
				if (top.relevance > 0) relevance += result.relevance;
				emitter.__addSublanguage(result._emitter, result.language);
			}
			function processBuffer() {
				if (top.subLanguage != null) processSubLanguage();
				else processKeywords();
				modeBuffer = "";
			}
			/**
			* @param {string} text
			* @param {string} scope
			*/
			function emitKeyword(keyword, scope) {
				if (keyword === "") return;
				emitter.startScope(scope);
				emitter.addText(keyword);
				emitter.endScope();
			}
			/**
			* @param {CompiledScope} scope
			* @param {RegExpMatchArray} match
			*/
			function emitMultiClass(scope, match) {
				let i = 1;
				const max = match.length - 1;
				while (i <= max) {
					if (!scope._emit[i]) {
						i++;
						continue;
					}
					const klass = language.classNameAliases[scope[i]] || scope[i];
					const text = match[i];
					if (klass) emitKeyword(text, klass);
					else {
						modeBuffer = text;
						processKeywords();
						modeBuffer = "";
					}
					i++;
				}
			}
			/**
			* @param {CompiledMode} mode - new mode to start
			* @param {RegExpMatchArray} match
			*/
			function startNewMode(mode, match) {
				if (mode.scope && typeof mode.scope === "string") emitter.openNode(language.classNameAliases[mode.scope] || mode.scope);
				if (mode.beginScope) {
					if (mode.beginScope._wrap) {
						emitKeyword(modeBuffer, language.classNameAliases[mode.beginScope._wrap] || mode.beginScope._wrap);
						modeBuffer = "";
					} else if (mode.beginScope._multi) {
						emitMultiClass(mode.beginScope, match);
						modeBuffer = "";
					}
				}
				top = Object.create(mode, { parent: { value: top } });
				return top;
			}
			/**
			* @param {CompiledMode } mode - the mode to potentially end
			* @param {RegExpMatchArray} match - the latest match
			* @param {string} matchPlusRemainder - match plus remainder of content
			* @returns {CompiledMode | void} - the next mode, or if void continue on in current mode
			*/
			function endOfMode(mode, match, matchPlusRemainder) {
				let matched = startsWith(mode.endRe, matchPlusRemainder);
				if (matched) {
					if (mode["on:end"]) {
						const resp = new Response(mode);
						mode["on:end"](match, resp);
						if (resp.isMatchIgnored) matched = false;
					}
					if (matched) {
						while (mode.endsParent && mode.parent) mode = mode.parent;
						return mode;
					}
				}
				if (mode.endsWithParent) return endOfMode(mode.parent, match, matchPlusRemainder);
			}
			/**
			* Handle matching but then ignoring a sequence of text
			*
			* @param {string} lexeme - string containing full match text
			*/
			function doIgnore(lexeme) {
				if (top.matcher.regexIndex === 0) {
					modeBuffer += lexeme[0];
					return 1;
				} else {
					resumeScanAtSamePosition = true;
					return 0;
				}
			}
			/**
			* Handle the start of a new potential mode match
			*
			* @param {EnhancedMatch} match - the current match
			* @returns {number} how far to advance the parse cursor
			*/
			function doBeginMatch(match) {
				const lexeme = match[0];
				const newMode = match.rule;
				const resp = new Response(newMode);
				const beforeCallbacks = [newMode.__beforeBegin, newMode["on:begin"]];
				for (const cb of beforeCallbacks) {
					if (!cb) continue;
					cb(match, resp);
					if (resp.isMatchIgnored) return doIgnore(lexeme);
				}
				if (newMode.skip) modeBuffer += lexeme;
				else {
					if (newMode.excludeBegin) modeBuffer += lexeme;
					processBuffer();
					if (!newMode.returnBegin && !newMode.excludeBegin) modeBuffer = lexeme;
				}
				startNewMode(newMode, match);
				return newMode.returnBegin ? 0 : lexeme.length;
			}
			/**
			* Handle the potential end of mode
			*
			* @param {RegExpMatchArray} match - the current match
			*/
			function doEndMatch(match) {
				const lexeme = match[0];
				const matchPlusRemainder = codeToHighlight.substring(match.index);
				const endMode = endOfMode(top, match, matchPlusRemainder);
				if (!endMode) return NO_MATCH;
				const origin = top;
				if (top.endScope && top.endScope._wrap) {
					processBuffer();
					emitKeyword(lexeme, top.endScope._wrap);
				} else if (top.endScope && top.endScope._multi) {
					processBuffer();
					emitMultiClass(top.endScope, match);
				} else if (origin.skip) modeBuffer += lexeme;
				else {
					if (!(origin.returnEnd || origin.excludeEnd)) modeBuffer += lexeme;
					processBuffer();
					if (origin.excludeEnd) modeBuffer = lexeme;
				}
				do {
					if (top.scope) emitter.closeNode();
					if (!top.skip && !top.subLanguage) relevance += top.relevance;
					top = top.parent;
				} while (top !== endMode.parent);
				if (endMode.starts) startNewMode(endMode.starts, match);
				return origin.returnEnd ? 0 : lexeme.length;
			}
			function processContinuations() {
				const list = [];
				for (let current = top; current !== language; current = current.parent) if (current.scope) list.unshift(current.scope);
				list.forEach((item) => emitter.openNode(item));
			}
			/** @type {{type?: MatchType, index?: number, rule?: Mode}}} */
			let lastMatch = {};
			/**
			*  Process an individual match
			*
			* @param {string} textBeforeMatch - text preceding the match (since the last match)
			* @param {EnhancedMatch} [match] - the match itself
			*/
			function processLexeme(textBeforeMatch, match) {
				const lexeme = match && match[0];
				modeBuffer += textBeforeMatch;
				if (lexeme == null) {
					processBuffer();
					return 0;
				}
				if (lastMatch.type === "begin" && match.type === "end" && lastMatch.index === match.index && lexeme === "") {
					modeBuffer += codeToHighlight.slice(match.index, match.index + 1);
					if (!SAFE_MODE) {
						/** @type {AnnotatedError} */
						const err = /* @__PURE__ */ new Error(`0 width match regex (${languageName})`);
						err.languageName = languageName;
						err.badRule = lastMatch.rule;
						throw err;
					}
					return 1;
				}
				lastMatch = match;
				if (match.type === "begin") return doBeginMatch(match);
				else if (match.type === "illegal" && !ignoreIllegals) {
					/** @type {AnnotatedError} */
					const err = /* @__PURE__ */ new Error("Illegal lexeme \"" + lexeme + "\" for mode \"" + (top.scope || "<unnamed>") + "\"");
					err.mode = top;
					throw err;
				} else if (match.type === "end") {
					const processed = doEndMatch(match);
					if (processed !== NO_MATCH) return processed;
				}
				if (match.type === "illegal" && lexeme === "") {
					if (match.index === codeToHighlight.length);
					else modeBuffer += "\n";
					return 1;
				}
				if (iterations > 1e5 && iterations > match.index * 3) throw /* @__PURE__ */ new Error("potential infinite loop, way more iterations than matches");
				modeBuffer += lexeme;
				return lexeme.length;
			}
			const language = getLanguage(languageName);
			if (!language) {
				error(LANGUAGE_NOT_FOUND.replace("{}", languageName));
				throw new Error("Unknown language: \"" + languageName + "\"");
			}
			const md = compileLanguage(language);
			let result = "";
			/** @type {CompiledMode} */
			let top = continuation || md;
			/** @type Record<string,CompiledMode> */
			const continuations = {};
			const emitter = new options.__emitter(options);
			processContinuations();
			let modeBuffer = "";
			let relevance = 0;
			let index = 0;
			let iterations = 0;
			let resumeScanAtSamePosition = false;
			try {
				if (!language.__emitTokens) {
					top.matcher.considerAll();
					for (;;) {
						iterations++;
						if (resumeScanAtSamePosition) resumeScanAtSamePosition = false;
						else top.matcher.considerAll();
						top.matcher.lastIndex = index;
						const match = top.matcher.exec(codeToHighlight);
						if (!match) break;
						const processedCount = processLexeme(codeToHighlight.substring(index, match.index), match);
						index = match.index + processedCount;
					}
					processLexeme(codeToHighlight.substring(index));
				} else language.__emitTokens(codeToHighlight, emitter);
				emitter.finalize();
				result = emitter.toHTML();
				return {
					language: languageName,
					value: result,
					relevance,
					illegal: false,
					_emitter: emitter,
					_top: top
				};
			} catch (err) {
				if (err.message && err.message.includes("Illegal")) return {
					language: languageName,
					value: escape(codeToHighlight),
					illegal: true,
					relevance: 0,
					_illegalBy: {
						message: err.message,
						index,
						context: codeToHighlight.slice(index - 100, index + 100),
						mode: err.mode,
						resultSoFar: result
					},
					_emitter: emitter
				};
				else if (SAFE_MODE) return {
					language: languageName,
					value: escape(codeToHighlight),
					illegal: false,
					relevance: 0,
					errorRaised: err,
					_emitter: emitter,
					_top: top
				};
				else throw err;
			}
		}
		/**
		* returns a valid highlight result, without actually doing any actual work,
		* auto highlight starts with this and it's possible for small snippets that
		* auto-detection may not find a better match
		* @param {string} code
		* @returns {HighlightResult}
		*/
		function justTextHighlightResult(code) {
			const result = {
				value: escape(code),
				illegal: false,
				relevance: 0,
				_top: PLAINTEXT_LANGUAGE,
				_emitter: new options.__emitter(options)
			};
			result._emitter.addText(code);
			return result;
		}
		/**
		Highlighting with language detection. Accepts a string with the code to
		highlight. Returns an object with the following properties:

		- language (detected language)
		- relevance (int)
		- value (an HTML string with highlighting markup)
		- secondBest (object with the same structure for second-best heuristically
		detected language, may be absent)

		@param {string} code
		@param {Array<string>} [languageSubset]
		@returns {AutoHighlightResult}
		*/
		function highlightAuto(code, languageSubset) {
			languageSubset = languageSubset || options.languages || Object.keys(languages);
			const plaintext = justTextHighlightResult(code);
			const results = languageSubset.filter(getLanguage).filter(autoDetection).map((name) => _highlight(name, code, false));
			results.unshift(plaintext);
			const [best, secondBest] = results.sort((a, b) => {
				if (a.relevance !== b.relevance) return b.relevance - a.relevance;
				if (a.language && b.language) {
					if (getLanguage(a.language).supersetOf === b.language) return 1;
					else if (getLanguage(b.language).supersetOf === a.language) return -1;
				}
				return 0;
			});
			/** @type {AutoHighlightResult} */
			const result = best;
			result.secondBest = secondBest;
			return result;
		}
		/**
		* Builds new class name for block given the language name
		*
		* @param {HTMLElement} element
		* @param {string} [currentLang]
		* @param {string} [resultLang]
		*/
		function updateClassName(element, currentLang, resultLang) {
			const language = currentLang && aliases[currentLang] || resultLang;
			element.classList.add("hljs");
			element.classList.add(`language-${language}`);
		}
		/**
		* Applies highlighting to a DOM node containing code.
		*
		* @param {HighlightedHTMLElement} element - the HTML element to highlight
		*/
		function highlightElement(element) {
			/** @type HTMLElement */
			let node = null;
			const language = blockLanguage(element);
			if (shouldNotHighlight(language)) return;
			fire("before:highlightElement", {
				el: element,
				language
			});
			if (element.dataset.highlighted) {
				console.log("Element previously highlighted. To highlight again, first unset `dataset.highlighted`.", element);
				return;
			}
			if (element.children.length > 0) {
				if (!options.ignoreUnescapedHTML) {
					console.warn("One of your code blocks includes unescaped HTML. This is a potentially serious security risk.");
					console.warn("https://github.com/highlightjs/highlight.js/wiki/security");
					console.warn("The element with unescaped HTML:");
					console.warn(element);
				}
				if (options.throwUnescapedHTML) throw new HTMLInjectionError("One of your code blocks includes unescaped HTML.", element.innerHTML);
			}
			node = element;
			const text = node.textContent;
			const result = language ? highlight(text, {
				language,
				ignoreIllegals: true
			}) : highlightAuto(text);
			element.innerHTML = result.value;
			element.dataset.highlighted = "yes";
			updateClassName(element, language, result.language);
			element.result = {
				language: result.language,
				re: result.relevance,
				relevance: result.relevance
			};
			if (result.secondBest) element.secondBest = {
				language: result.secondBest.language,
				relevance: result.secondBest.relevance
			};
			fire("after:highlightElement", {
				el: element,
				result,
				text
			});
		}
		/**
		* Updates highlight.js global options with the passed options
		*
		* @param {Partial<HLJSOptions>} userOptions
		*/
		function configure(userOptions) {
			options = inherit(options, userOptions);
		}
		const initHighlighting = () => {
			highlightAll();
			deprecated("10.6.0", "initHighlighting() deprecated.  Use highlightAll() now.");
		};
		function initHighlightingOnLoad() {
			highlightAll();
			deprecated("10.6.0", "initHighlightingOnLoad() deprecated.  Use highlightAll() now.");
		}
		let wantsHighlight = false;
		/**
		* auto-highlights all pre>code elements on the page
		*/
		function highlightAll() {
			function boot() {
				highlightAll();
			}
			if (document.readyState === "loading") {
				if (!wantsHighlight) window.addEventListener("DOMContentLoaded", boot, false);
				wantsHighlight = true;
				return;
			}
			document.querySelectorAll(options.cssSelector).forEach(highlightElement);
		}
		/**
		* Register a language grammar module
		*
		* @param {string} languageName
		* @param {LanguageFn} languageDefinition
		*/
		function registerLanguage(languageName, languageDefinition) {
			let lang = null;
			try {
				lang = languageDefinition(hljs);
			} catch (error$1) {
				error("Language definition for '{}' could not be registered.".replace("{}", languageName));
				if (!SAFE_MODE) throw error$1;
				else error(error$1);
				lang = PLAINTEXT_LANGUAGE;
			}
			if (!lang.name) lang.name = languageName;
			languages[languageName] = lang;
			lang.rawDefinition = languageDefinition.bind(null, hljs);
			if (lang.aliases) registerAliases(lang.aliases, { languageName });
		}
		/**
		* Remove a language grammar module
		*
		* @param {string} languageName
		*/
		function unregisterLanguage(languageName) {
			delete languages[languageName];
			for (const alias of Object.keys(aliases)) if (aliases[alias] === languageName) delete aliases[alias];
		}
		/**
		* @returns {string[]} List of language internal names
		*/
		function listLanguages() {
			return Object.keys(languages);
		}
		/**
		* @param {string} name - name of the language to retrieve
		* @returns {Language | undefined}
		*/
		function getLanguage(name) {
			name = (name || "").toLowerCase();
			return languages[name] || languages[aliases[name]];
		}
		/**
		*
		* @param {string|string[]} aliasList - single alias or list of aliases
		* @param {{languageName: string}} opts
		*/
		function registerAliases(aliasList, { languageName }) {
			if (typeof aliasList === "string") aliasList = [aliasList];
			aliasList.forEach((alias) => {
				aliases[alias.toLowerCase()] = languageName;
			});
		}
		/**
		* Determines if a given language has auto-detection enabled
		* @param {string} name - name of the language
		*/
		function autoDetection(name) {
			const lang = getLanguage(name);
			return lang && !lang.disableAutodetect;
		}
		/**
		* Upgrades the old highlightBlock plugins to the new
		* highlightElement API
		* @param {HLJSPlugin} plugin
		*/
		function upgradePluginAPI(plugin) {
			if (plugin["before:highlightBlock"] && !plugin["before:highlightElement"]) plugin["before:highlightElement"] = (data) => {
				plugin["before:highlightBlock"](Object.assign({ block: data.el }, data));
			};
			if (plugin["after:highlightBlock"] && !plugin["after:highlightElement"]) plugin["after:highlightElement"] = (data) => {
				plugin["after:highlightBlock"](Object.assign({ block: data.el }, data));
			};
		}
		/**
		* @param {HLJSPlugin} plugin
		*/
		function addPlugin(plugin) {
			upgradePluginAPI(plugin);
			plugins.push(plugin);
		}
		/**
		* @param {HLJSPlugin} plugin
		*/
		function removePlugin(plugin) {
			const index = plugins.indexOf(plugin);
			if (index !== -1) plugins.splice(index, 1);
		}
		/**
		*
		* @param {PluginEvent} event
		* @param {any} args
		*/
		function fire(event, args) {
			const cb = event;
			plugins.forEach(function(plugin) {
				if (plugin[cb]) plugin[cb](args);
			});
		}
		/**
		* DEPRECATED
		* @param {HighlightedHTMLElement} el
		*/
		function deprecateHighlightBlock(el) {
			deprecated("10.7.0", "highlightBlock will be removed entirely in v12.0");
			deprecated("10.7.0", "Please use highlightElement now.");
			return highlightElement(el);
		}
		Object.assign(hljs, {
			highlight,
			highlightAuto,
			highlightAll,
			highlightElement,
			highlightBlock: deprecateHighlightBlock,
			configure,
			initHighlighting,
			initHighlightingOnLoad,
			registerLanguage,
			unregisterLanguage,
			listLanguages,
			getLanguage,
			registerAliases,
			autoDetection,
			inherit,
			addPlugin,
			removePlugin
		});
		hljs.debugMode = function() {
			SAFE_MODE = false;
		};
		hljs.safeMode = function() {
			SAFE_MODE = true;
		};
		hljs.versionString = version;
		hljs.regex = {
			concat,
			lookahead,
			either,
			optional,
			anyNumberOfTimes
		};
		for (const key in MODES) if (typeof MODES[key] === "object") deepFreeze(MODES[key]);
		Object.assign(hljs, MODES);
		return hljs;
	};
	var highlight = HLJS({});
	highlight.newInstance = () => HLJS({});
	module.exports = highlight;
	highlight.HighlightJS = highlight;
	highlight.default = highlight;
})))())).default;
//#endregion
//#region node_modules/lowlight/lib/index.js
/**
* @import {ElementContent, Element, RootData, Root} from 'hast'
* @import {Emitter, HLJSOptions as HljsOptions, HighlightResult, LanguageFn} from 'highlight.js'
*/
/**
* @typedef {Object} ExtraOptions
*   Extra fields.
* @property {ReadonlyArray<string> | null | undefined} [subset]
*   List of allowed languages (default: all registered languages).
*
* @typedef Options
*   Configuration for `highlight`.
* @property {string | null | undefined} [prefix='hljs-']
*   Class prefix (default: `'hljs-'`).
*
* @typedef {Options & ExtraOptions} AutoOptions
*   Configuration for `highlightAuto`.
*/
/** @type {AutoOptions} */
var emptyOptions = {};
var defaultPrefix = "hljs-";
/**
* Create a `lowlight` instance.
*
* @param {Readonly<Record<string, LanguageFn>> | null | undefined} [grammars]
*   Grammars to add (optional).
* @returns
*   Lowlight.
*/
function createLowlight(grammars) {
	const high = core_default.newInstance();
	if (grammars) register(grammars);
	return {
		highlight,
		highlightAuto,
		listLanguages,
		register,
		registerAlias,
		registered
	};
	/**
	* Highlight `value` (code) as `language` (name).
	*
	* @example
	*   ```js
	*   import {common, createLowlight} from 'lowlight'
	*
	*   const lowlight = createLowlight(common)
	*
	*   console.log(lowlight.highlight('css', 'em { color: red }'))
	*   ```
	*
	*   Yields:
	*
	*   ```js
	*   {type: 'root', children: [Array], data: {language: 'css', relevance: 3}}
	*   ```
	*
	* @param {string} language
	*   Programming language name.
	* @param {string} value
	*   Code to highlight.
	* @param {Readonly<Options> | null | undefined} [options={}]
	*   Configuration (optional).
	* @returns {Root}
	*   Tree; with the following `data` fields: `language` (`string`), detected
	*   programming language name; `relevance` (`number`), how sure lowlight is
	*   that the given code is in the language.
	*/
	function highlight(language, value, options) {
		const settings = options || emptyOptions;
		const prefix = typeof settings.prefix === "string" ? settings.prefix : defaultPrefix;
		if (!high.getLanguage(language)) throw new Error("Unknown language: `" + language + "` is not registered");
		high.configure({
			__emitter: HastEmitter,
			classPrefix: prefix
		});
		const result = high.highlight(value, {
			ignoreIllegals: true,
			language
		});
		/* c8 ignore next 5 */
		if (result.errorRaised) throw new Error("Could not highlight with `Highlight.js`", { cause: result.errorRaised });
		const root = result._emitter.root;
		const data = root.data;
		data.language = result.language;
		data.relevance = result.relevance;
		return root;
	}
	/**
	* Highlight `value` (code) and guess its programming language.
	*
	* @example
	*   ```js
	*   import {common, createLowlight} from 'lowlight'
	*
	*   const lowlight = createLowlight(common)
	*
	*   console.log(lowlight.highlightAuto('"hello, " + name + "!"'))
	*   ```
	*
	*   Yields:
	*
	*   ```js
	*   {type: 'root', children: [Array], data: {language: 'arduino', relevance: 2}}
	*   ```
	*
	* @param {string} value
	*   Code to highlight.
	* @param {Readonly<AutoOptions> | null | undefined} [options={}]
	*   Configuration (optional).
	* @returns {Root}
	*   Tree; with the following `data` fields: `language` (`string`), detected
	*   programming language name; `relevance` (`number`), how sure lowlight is
	*   that the given code is in the language.
	*/
	function highlightAuto(value, options) {
		const subset = (options || emptyOptions).subset || listLanguages();
		let index = -1;
		let relevance = 0;
		/** @type {Root | undefined} */
		let result;
		while (++index < subset.length) {
			const name = subset[index];
			if (!high.getLanguage(name)) continue;
			const current = highlight(name, value, options);
			if (current.data && current.data.relevance !== void 0 && current.data.relevance > relevance) {
				relevance = current.data.relevance;
				result = current;
			}
		}
		return result || {
			type: "root",
			children: [],
			data: {
				language: void 0,
				relevance
			}
		};
	}
	/**
	* List registered languages.
	*
	* @example
	*   ```js
	*   import {createLowlight} from 'lowlight'
	*   import markdown from 'highlight.js/lib/languages/markdown'
	*
	*   const lowlight = createLowlight()
	*
	*   console.log(lowlight.listLanguages()) // => []
	*
	*   lowlight.register({markdown})
	*
	*   console.log(lowlight.listLanguages()) // => ['markdown']
	*   ```
	*
	* @returns {Array<string>}
	*   Names of registered language.
	*/
	function listLanguages() {
		return high.listLanguages();
	}
	/**
	* Register languages.
	*
	* @example
	*   ```js
	*   import {createLowlight} from 'lowlight'
	*   import xml from 'highlight.js/lib/languages/xml'
	*
	*   const lowlight = createLowlight()
	*
	*   lowlight.register({xml})
	*
	*   // Note: `html` is an alias for `xml`.
	*   console.log(lowlight.highlight('html', '<em>Emphasis</em>'))
	*   ```
	*
	*   Yields:
	*
	*   ```js
	*   {type: 'root', children: [Array], data: {language: 'html', relevance: 2}}
	*   ```
	*
	* @overload
	* @param {Readonly<Record<string, LanguageFn>>} grammars
	* @returns {undefined}
	*
	* @overload
	* @param {string} name
	* @param {LanguageFn} grammar
	* @returns {undefined}
	*
	* @param {Readonly<Record<string, LanguageFn>> | string} grammarsOrName
	*   Grammars or programming language name.
	* @param {LanguageFn | undefined} [grammar]
	*   Grammar, if with name.
	* @returns {undefined}
	*   Nothing.
	*/
	function register(grammarsOrName, grammar) {
		if (typeof grammarsOrName === "string") high.registerLanguage(grammarsOrName, grammar);
		else {
			/** @type {string} */
			let name;
			for (name in grammarsOrName) if (Object.hasOwn(grammarsOrName, name)) high.registerLanguage(name, grammarsOrName[name]);
		}
	}
	/**
	* Register aliases.
	*
	* @example
	*   ```js
	*   import {createLowlight} from 'lowlight'
	*   import markdown from 'highlight.js/lib/languages/markdown'
	*
	*   const lowlight = createLowlight()
	*
	*   lowlight.register({markdown})
	*
	*   // lowlight.highlight('mdown', '<em>Emphasis</em>')
	*   // ^ would throw: Error: Unknown language: `mdown` is not registered
	*
	*   lowlight.registerAlias({markdown: ['mdown', 'mkdn', 'mdwn', 'ron']})
	*   lowlight.highlight('mdown', '<em>Emphasis</em>')
	*   // ^ Works!
	*   ```
	*
	* @overload
	* @param {Readonly<Record<string, ReadonlyArray<string> | string>>} aliases
	* @returns {undefined}
	*
	* @overload
	* @param {string} language
	* @param {ReadonlyArray<string> | string} alias
	* @returns {undefined}
	*
	* @param {Readonly<Record<string, ReadonlyArray<string> | string>> | string} aliasesOrName
	*   Map of programming language names to one or more aliases, or programming
	*   language name.
	* @param {ReadonlyArray<string> | string | undefined} [alias]
	*   One or more aliases for the programming language, if with `name`.
	* @returns {undefined}
	*   Nothing.
	*/
	function registerAlias(aliasesOrName, alias) {
		if (typeof aliasesOrName === "string") high.registerAliases(typeof alias === "string" ? alias : [...alias], { languageName: aliasesOrName });
		else {
			/** @type {string} */
			let key;
			for (key in aliasesOrName) if (Object.hasOwn(aliasesOrName, key)) {
				const aliases = aliasesOrName[key];
				high.registerAliases(typeof aliases === "string" ? aliases : [...aliases], { languageName: key });
			}
		}
	}
	/**
	* Check whether an alias or name is registered.
	*
	* @example
	*   ```js
	*   import {createLowlight} from 'lowlight'
	*   import javascript from 'highlight.js/lib/languages/javascript'
	*
	*   const lowlight = createLowlight({javascript})
	*
	*   console.log(lowlight.registered('funkyscript')) // => `false`
	*
	*   lowlight.registerAlias({javascript: 'funkyscript'})
	*   console.log(lowlight.registered('funkyscript')) // => `true`
	*   ```
	*
	* @param {string} aliasOrName
	*   Name of a language or alias for one.
	* @returns {boolean}
	*   Whether `aliasOrName` is registered.
	*/
	function registered(aliasOrName) {
		return Boolean(high.getLanguage(aliasOrName));
	}
}
/** @type {Emitter} */
var HastEmitter = class {
	/**
	* @param {Readonly<HljsOptions>} options
	*   Configuration.
	* @returns
	*   Instance.
	*/
	constructor(options) {
		/** @type {HljsOptions} */
		this.options = options;
		/** @type {Root} */
		this.root = {
			type: "root",
			children: [],
			data: {
				language: void 0,
				relevance: 0
			}
		};
		/** @type {[Root, ...Array<Element>]} */
		this.stack = [this.root];
	}
	/**
	* @param {string} value
	*   Text to add.
	* @returns {undefined}
	*   Nothing.
	*
	*/
	addText(value) {
		if (value === "") return;
		const current = this.stack[this.stack.length - 1];
		const tail = current.children[current.children.length - 1];
		if (tail && tail.type === "text") tail.value += value;
		else current.children.push({
			type: "text",
			value
		});
	}
	/**
	*
	* @param {unknown} rawName
	*   Name to add.
	* @returns {undefined}
	*   Nothing.
	*/
	startScope(rawName) {
		this.openNode(String(rawName));
	}
	/**
	* @returns {undefined}
	*   Nothing.
	*/
	endScope() {
		this.closeNode();
	}
	/**
	* @param {HastEmitter} other
	*   Other emitter.
	* @param {string} name
	*   Name of the sublanguage.
	* @returns {undefined}
	*   Nothing.
	*/
	__addSublanguage(other, name) {
		const current = this.stack[this.stack.length - 1];
		const results = other.root.children;
		if (name) current.children.push({
			type: "element",
			tagName: "span",
			properties: { className: [name] },
			children: results
		});
		else current.children.push(...results);
	}
	/**
	* @param {string} name
	*   Name to add.
	* @returns {undefined}
	*   Nothing.
	*/
	openNode(name) {
		const self = this;
		const className = name.split(".").map(function(d, i) {
			return i ? d + "_".repeat(i) : self.options.classPrefix + d;
		});
		const current = this.stack[this.stack.length - 1];
		/** @type {Element} */
		const child = {
			type: "element",
			tagName: "span",
			properties: { className },
			children: []
		};
		current.children.push(child);
		this.stack.push(child);
	}
	/**
	* @returns {undefined}
	*   Nothing.
	*/
	closeNode() {
		this.stack.pop();
	}
	/**
	* @returns {undefined}
	*   Nothing.
	*/
	finalize() {}
	/**
	* @returns {string}
	*   Nothing.
	*/
	toHTML() {
		return "";
	}
};
//#endregion
//#region node_modules/marked/lib/marked.esm.js
/**
* marked v18.0.14 - a markdown parser
* Copyright (c) 2018-2026, MarkedJS. (MIT License)
* Copyright (c) 2011-2018, Christopher Jeffrey. (MIT License)
* https://github.com/markedjs/marked
*/
/**
* DO NOT EDIT THIS FILE
* The code in this file is generated from files in ./src/
*/
function I() {
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
var y = I();
function W(l) {
	y = l;
}
var A = { exec: () => null };
function C(l) {
	let e = [];
	return (t) => {
		let n = Math.max(0, Math.min(3, t - 1)), s = e[n];
		return s || (s = l(n), e[n] = s), s;
	};
}
function h(l, e = "") {
	let t = typeof l == "string" ? l : l.source, n = {
		replace: (s, r) => {
			let o = typeof r == "string" ? r : r.source;
			return o = o.replace(x.caret, "$1"), t = t.replace(s, o), n;
		},
		getRegex: () => new RegExp(t, e)
	};
	return n;
}
var _e = ((l = "") => {
	try {
		return !!new RegExp("(?<=1)(?<!1)" + l);
	} catch {
		return !1;
	}
})();
var x = {
	codeRemoveIndent: /^(?: {0,3}\t| {1,4})/gm,
	outputLinkReplace: /\\([\[\]])/g,
	indentCodeCompensation: /^(\s+)(?:```)/,
	beginningSpace: /^\s+/,
	endingHash: /#$/,
	startingSpaceChar: /^ /,
	endingSpaceChar: / $/,
	endingSpaceTabChar: /[ \t]$/,
	nonSpaceChar: /[^ ]/,
	newLineCharGlobal: /\n/g,
	tabCharGlobal: /\t/g,
	leadingSpaceTab: /^[ \t]+/,
	multipleSpaceGlobal: /\s+/g,
	blankLine: /^[ \t]*$/,
	doubleBlankLine: /\n[ \t]*\n[ \t]*$/,
	blockquoteStart: /^ {0,3}>/,
	blockquoteSetextReplace: /\n {0,3}((?:=+|-+) *)(?=\n|$)/g,
	blockquoteSetextReplace2: /^ {0,3}>[ \t]?/gm,
	listReplaceNesting: /^ {1,4}(?=( {4})*[^ ])/g,
	listIsTask: /^\[[ xX]\] +\S/,
	listReplaceTask: /^\[[ xX]\] +/,
	listTaskCheckbox: /\[[ xX]\]/,
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
	numericCharacterReference: /&#(?:(\d{1,7})|[Xx]([A-Fa-f0-9]{1,6}));/g,
	escapeTest: /[&<>"']/,
	escapeReplace: /[&<>"']/g,
	escapeTestNoEncode: /[<>"']|&(?!(#\d{1,7}|#[Xx][a-fA-F0-9]{1,6}|\w+);)/,
	escapeReplaceNoEncode: /[<>"']|&(?!(#\d{1,7}|#[Xx][a-fA-F0-9]{1,6}|\w+);)/g,
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
	nextBulletRegex: C((l) => new RegExp(`^ {0,${l}}(?:[*+-]|\\d{1,9}[.)])((?:[ 	][^\\n]*)?(?:\\n|$))`)),
	hrRegex: C((l) => new RegExp(`^ {0,${l}}((?:-[ 	]*){3,}|(?:_[ 	]*){3,}|(?:\\*[ 	]*){3,})(?:\\n+|$)`)),
	fencesBeginRegex: C((l) => new RegExp(`^ {0,${l}}(?:\`\`\`|~~~)`)),
	headingBeginRegex: C((l) => new RegExp(`^ {0,${l}}#`)),
	htmlBeginRegex: C((l) => new RegExp(`^ {0,${l}}(?:</?(?:${N})(?: +|$|/?>)|<(?:script|pre|style|textarea|!--))`, "i")),
	blockquoteBeginRegex: C((l) => new RegExp(`^ {0,${l}}>`))
};
var $e = /^(?:[ \t]*(?:\n|$))+/;
var Le = /^((?: {4}| {0,3}\t)[^\n]+(?:\n(?:[ \t]*(?:\n|$))*)?)+/;
var ze = /^ {0,3}(`{3,}(?=[^`\n]*(?:\n|$))|~{3,})([^\n]*)(?:\n|$)(?:|([\s\S]*?)(?:\n|$))(?: {0,3}\1[~`]* *(?=\n|$)|$)/;
var G = /^ {0,3}((?:-[\t ]*){3,}|(?:_[ \t]*){3,}|(?:\*[ \t]*){3,})(?:\n+|$)/;
var Ae = /^ {0,3}(#{1,6})(?=\s|$)(.*)(?:\n+|$)/;
var J = / {0,3}(?:[*+-]|\d{1,9}[.)])/;
var ce = /^(?!bull |blockCode|fences|blockquote|heading|html|table)((?:.|\n(?!\s*?\n|bull |fences|blockquote|heading|hr|html|table))+?)\n {0,3}(=+|-+) *(?:\n+|$)/;
var he = h(ce).replace(/bull/g, J).replace(/blockCode/g, /(?: {4}| {0,3}\t)/).replace(/fences/g, / {0,3}(?:`{3,}|~{3,})/).replace(/blockquote/g, / {0,3}>/).replace(/heading/g, / {0,3}#{1,6}(?:\s|$)/).replace(/hr/g, / {0,3}(?:(?:-[\t ]*){3,}|(?:_[ \t]*){3,}|(?:\*[ \t]*){3,})(?:\n+|$)/).replace(/html/g, / {0,3}<[^\n>]+>\n/).replace(/\|table/g, "").getRegex();
var Ee = h(ce).replace(/bull/g, J).replace(/blockCode/g, /(?: {4}| {0,3}\t)/).replace(/fences/g, / {0,3}(?:`{3,}|~{3,})/).replace(/blockquote/g, / {0,3}>/).replace(/heading/g, / {0,3}#{1,6}(?:\s|$)/).replace(/hr/g, / {0,3}(?:(?:-[\t ]*){3,}|(?:_[ \t]*){3,}|(?:\*[ \t]*){3,})(?:\n+|$)/).replace(/html/g, / {0,3}<[^\n>]+>\n/).replace(/table/g, / {0,3}\|?(?:[:\- ]*\|)+[\:\- ]*\n/).getRegex();
var V = /^([^\n]+(?:\n(?!hr|heading|lheading|blockquote|fences|list|html|table|[ \t]+\n)[^\n]+)*)/;
var Me = /^[^\n]+/;
var Y = /(?!\s*\])(?:\\[\s\S]|[^\[\]\\])+/;
var Ie = h(/^ {0,3}\[(label)\]: *(?:\n[ \t]*)?([^<\s][^\s]*|<.*?>)(?:(?: +(?:\n[ \t]*)?| *\n[ \t]*)(title))? *(?:\n+|$)/).replace("label", Y).replace("title", /(?:"(?:\\"?|[^"\\])*"|'[^'\n]*(?:\n[^'\n]+)*\n?'|\([^()]*\))/).getRegex();
var Ce = h(/^(bull)([ \t][^\n]*?)?(?:\n|$)/).replace(/bull/g, J).getRegex();
var N = "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|meta|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul";
var ee = /<!--(?:-?>|[\s\S]*?(?:-->|$))/;
var Be = h("^ {0,3}(?:<(script|pre|style|textarea)[\\s>][\\s\\S]*?(?:</\\1>[^\\n]*\\n*|$)|comment[^\\n]*(\\n+|$)|<\\?[\\s\\S]*?(?:\\?>[^\\n]*\\n*|$)|<![A-Z][\\s\\S]*?(?:>[^\\n]*\\n*|$)|<!\\[CDATA\\[[\\s\\S]*?(?:\\]\\]>[^\\n]*\\n*|$)|</?(tag)(?: +|\\n|/?>)[\\s\\S]*?(?:(?:\\n[ 	]*)+\\n|$)|<(?!script|pre|style|textarea)([a-z][a-z0-9-]*)(?:attribute)*? */?>(?=[ \\t]*(?:\\n|$))[\\s\\S]*?(?:(?:\\n[ 	]*)+\\n|$)|</(?!script|pre|style|textarea)[a-z][a-z0-9-]*\\s*>(?=[ \\t]*(?:\\n|$))[\\s\\S]*?(?:(?:\\n[ 	]*)+\\n|$))", "i").replace("comment", ee).replace("tag", N).replace("attribute", / +[a-zA-Z:_][\w.:-]*(?: *= *"[^"\n]*"| *= *'[^'\n]*'| *= *[^\s"'=<>`]+)?/).getRegex();
var de = (l) => h(V).replace("hr", G).replace("heading", " {0,3}#{1,6}(?:\\s|$)").replace("|lheading", "").replace("|table", "").replace("blockquote", " {0,3}>").replace("fences", " {0,3}(?:`{3,}(?=[^`\\n]*(?:\\n|$))|~~~)[^\\n]*(?:\\n|$)").replace("list", l).replace("html", "</?(?:tag)(?: +|\\n|/?>)|<(?:script|pre|style|textarea|!--)").replace("tag", N).getRegex();
var De = de(/ {0,3}(?:[*+-]|1[.)])[ \t]+[^ \t\n]/);
var qe = de(/ {0,3}(?:[*+-]|\d{1,9}[.)])(?:[ \t]|\n|$)/);
var te = {
	blockquote: h(/^( {0,3}> ?(paragraph|[^\n]*)(?:\n|$))+/).replace("paragraph", qe).getRegex(),
	code: Le,
	def: Ie,
	fences: ze,
	heading: Ae,
	hr: G,
	html: Be,
	lheading: he,
	list: Ce,
	newline: $e,
	paragraph: De,
	table: A,
	text: Me
};
var le = h("^ *([^\\n ].*)\\n {0,3}((?:\\| *)?:?-+:? *(?:\\| *:?-+:? *)*(?:\\| *)?)(?:\\n((?:(?! *\\n|hr|heading|blockquote|code|fences|list|html).*(?:\\n|$))*)\\n*|$)").replace("hr", G).replace("heading", " {0,3}#{1,6}(?:\\s|$)").replace("blockquote", " {0,3}>").replace("code", "(?: {4}| {0,3}	)[^\\n]").replace("fences", " {0,3}(?:`{3,}(?=[^`\\n]*(?:\\n|$))|~~~)[^\\n]*(?:\\n|$)").replace("list", " {0,3}(?:[*+-]|1[.)])[ \\t]").replace("html", "</?(?:tag)(?: +|\\n|/?>)|<(?:script|pre|style|textarea|!--)").replace("tag", N).getRegex();
var Ze = {
	...te,
	lheading: Ee,
	table: le,
	paragraph: h(V).replace("hr", G).replace("heading", " {0,3}#{1,6}(?:\\s|$)").replace("|lheading", "").replace("table", le).replace("blockquote", " {0,3}>").replace("fences", " {0,3}(?:`{3,}(?=[^`\\n]*(?:\\n|$))|~~~)[^\\n]*(?:\\n|$)").replace("list", " {0,3}(?:[*+-]|1[.)])[ \\t]+[^ \\t\\n]").replace("html", "</?(?:tag)(?: +|\\n|/?>)|<(?:script|pre|style|textarea|!--)").replace("tag", N).getRegex()
};
var He = {
	...te,
	html: h(`^ *(?:comment *(?:\\n|\\s*$)|<(tag)[\\s\\S]+?</\\1> *(?:\\n{2,}|\\s*$)|<tag(?:"[^"]*"|'[^']*'|\\s[^'"/>\\s]*)*?/?> *(?:\\n{2,}|\\s*$))`).replace("comment", ee).replace(/tag/g, "(?!(?:a|em|strong|small|s|cite|q|dfn|abbr|data|time|code|var|samp|kbd|sub|sup|i|b|u|mark|ruby|rt|rp|bdi|bdo|span|br|wbr|ins|del|img)\\b)\\w+(?!:|[^\\w\\s@]*@)\\b").getRegex(),
	def: /^ *\[([^\]]+)\]: *<?([^\s>]+)>?(?: +(["(][^\n]+[")]))? *(?:\n+|$)/,
	heading: /^(#{1,6})(.*)(?:\n+|$)/,
	fences: A,
	lheading: /^(.+?)\n {0,3}(=+|-+) *(?:\n+|$)/,
	paragraph: h(V).replace("hr", G).replace("heading", ` *#{1,6} *[^
]`).replace("lheading", he).replace("|table", "").replace("blockquote", " {0,3}>").replace("|fences", "").replace("|list", "").replace("|html", "").replace("|tag", "").getRegex()
};
var Ge = /^\\([!"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])/;
var Ne = /^(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)/;
var ke = /^( {2,}|\\)\n(?!\s*$)[ \t]*/;
var Qe = /^(`+|[^`])(?:(?= {2,}\n)|[\s\S]*?(?:(?=[\\<!\[`*_]|\b_|$)|[^ ](?= {2,}\n)))/;
var $ = /[\p{P}\p{S}]/u;
var B = /[\s\p{P}\p{S}]/u;
var Q = /[^\s\p{P}\p{S}]/u;
var je = h(/^((?![*_])punctSpace)/, "u").replace(/punctSpace/g, B).getRegex();
var Fe = /[\p{Pi}\p{Ps}"']/u;
var ge = /(?!~)[\p{P}\p{S}]/u;
var Ue = /(?!~)[\s\p{P}\p{S}]/u;
var Ke = /(?:[^\s\p{P}\p{S}]|~)/u;
var We = h(/link|precode-code|html/, "g").replace("link", /\[(?:[^\[\]`]|(?<a>`+)[^`]+\k<a>(?!`))*?\]\((?:\\[\s\S]|[^\\\(\)]|\((?:\\[\s\S]|[^\\\(\)])*\))*\)/).replace("precode-", _e ? "(?<!`)()" : "(^^|[^`])").replace("code", /(?<b>`+)[^`]+\k<b>(?!`)/).replace("html", /<(?! )[^<>]*?>/).getRegex();
var fe = /^(?:\*+(?:((?!\*)punct)|([^\s*]))?)|^_+(?:((?!_)punct)|([^\s_]))?/;
var Xe = h(fe, "u").replace(/punct/g, $).getRegex();
var Je = h(fe, "u").replace(/punct/g, ge).getRegex();
var Ye = h(/^(?:\*+(?:((?!\*)(?!openQuote)punct)|([^\s*]))?)|^_+(?:((?!_)(?!openQuote)punct)|([^\s_]))?/, "u").replace(/openQuote/g, Fe).replace(/punct/g, $).getRegex();
var me = "^[^_*]*?__[^_*]*?\\*[^_*]*?(?=__)|[^*]+(?=[^*])|(?!\\*)punct(\\*+)(?=[\\s]|$)|notPunctSpace(\\*+)(?!\\*)(?=punctSpace|$)|(?!\\*)punctSpace(\\*+)(?=notPunctSpace)|[\\s](\\*+)(?!\\*)(?=punct)|(?!\\*)punct(\\*+)(?!\\*)(?=punct)|notPunctSpace(\\*+)(?=notPunctSpace)";
var et = h(me, "gu").replace(/notPunctSpace/g, Q).replace(/punctSpace/g, B).replace(/punct/g, $).getRegex();
var tt = h(me, "gu").replace(/notPunctSpace/g, Ke).replace(/punctSpace/g, Ue).replace(/punct/g, ge).getRegex();
var rt = h("^[^_*]*?__[^_*]*?\\*[^_*]*?(?=__)|[^*]+(?=[^*])|(?!\\*)punct(\\*+)(?=[\\s]|$)|notPunctSpace(\\*+)(?!\\*)(?=punctSpace|$)|(?!\\*)[\\s](\\*+)(?=notPunctSpace)|[\\s](\\*+)(?!\\*)(?=punct)|(?!\\*)punct(\\*+)(?!\\*)(?=punct)|(?:(?!\\*)punct|notPunctSpace)(\\*+)(?!\\*)(?=notPunctSpace)", "gu").replace(/notPunctSpace/g, Q).replace(/punctSpace/g, B).replace(/punct/g, $).getRegex();
var st = h("^[^_*]*?\\*\\*[^_*]*?_[^_*]*?(?=\\*\\*)|[^_]+(?=[^_])|(?!_)punct(_+)(?=[\\s]|$)|notPunctSpace(_+)(?!_)(?=punctSpace|$)|(?!_)punctSpace(_+)(?=notPunctSpace)|[\\s](_+)(?!_)(?=punct)|(?!_)punct(_+)(?!_)(?=punct)", "gu").replace(/notPunctSpace/g, Q).replace(/punctSpace/g, B).replace(/punct/g, $).getRegex();
var ot = h("^[^_*]*?\\*\\*[^_*]*?_[^_*]*?(?=\\*\\*)|[^_]+(?=[^_])|(?!_)punct(_+)(?=[\\s]|$)|notPunctSpace(_+)(?!_)(?=punctSpace|$)|(?!_)[\\s](_+)(?=notPunctSpace)|[\\s](_+)(?!_)(?=punct)|(?!_)punct(_+)(?!_)(?=punct)|(?:(?!_)punct|notPunctSpace)(_+)(?!_)(?=notPunctSpace)", "gu").replace(/notPunctSpace/g, Q).replace(/punctSpace/g, B).replace(/punct/g, $).getRegex();
var at = h(/^~~?(?:((?!~)punct)|[^\s~])/, "u").replace(/punct/g, $).getRegex();
var ut = h("^[^~]+(?=[^~])|(?!~)punct(~~?)(?=[\\s]|$)|notPunctSpace(~~?)(?!~)(?=punctSpace|$)|(?!~)punctSpace(~~?)(?=notPunctSpace)|[\\s](~~?)(?!~)(?=punct)|(?!~)punct(~~?)(?!~)(?=punct)|notPunctSpace(~~?)(?=notPunctSpace)", "gu").replace(/notPunctSpace/g, Q).replace(/punctSpace/g, B).replace(/punct/g, $).getRegex();
var pt = h(/\\(punct)/, "gu").replace(/punct/g, $).getRegex();
var ct = h(/^<(scheme:[^\s\x00-\x1f<>]*|email)>/).replace("scheme", /[a-zA-Z][a-zA-Z0-9+.-]{1,31}/).replace("email", /[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+(@)[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+(?![-_])/).getRegex();
var ht = h(ee).replace("(?:-->|$)", "-->").getRegex();
var dt = h("^comment|^</[a-zA-Z][a-zA-Z0-9-]*\\s*>|^<[a-zA-Z][a-zA-Z0-9-]*(?:attribute)*?\\s*/?>|^<\\?[\\s\\S]*?\\?>|^<![a-zA-Z]+\\s[\\s\\S]*?>|^<!\\[CDATA\\[[\\s\\S]*?\\]\\]>").replace("comment", ht).replace("attribute", /\s+[a-zA-Z:_][\w.:-]*(?:\s*=\s*"[^"]*"|\s*=\s*'[^']*'|\s*=\s*[^\s"'=<>`]+)?/).getRegex();
var xe = /\[(?:\\[\s\S]|[^\[\]\\])*\]/;
var U = h(/(?:\[(?:brackets|\\[\s\S]|[^\[\]\\])*\]|\\[\s\S]|`+(?!`)[^`]*?`+(?!`)|``+(?=\])|[^\[\]\\`])*?/).replace("brackets", xe).getRegex();
var kt = h(/^!?\[(label)\]\(\s*(href)(?:(?:[ \t]+(?:\n[ \t]*)?|\n[ \t]*)(title))?\s*\)/).replace("label", U).replace("href", /<(?:\\.|[^\n<>\\])+>|[^ \t\n\x00-\x1f]+|(?=\))/).replace("title", /"(?:\\"?|[^"\\])*"|'(?:\\'?|[^'\\])*'|\((?:\\\)?|[^)\\])*\)/).getRegex();
var gt = h(/^!?\[(label)\]\[(ref)\]/).replace("label", U).replace("ref", Y).getRegex();
var ft = h(/^!?\[(ref)\](?:\[\])?/).replace("ref", Y).getRegex();
var ue = /(?!\s*\])(?:\\[\s\S]|[^\[\]\\]){1,999}/;
var mt = h(/(?:[^\[\]\\`]*(?:\[(?:brackets|\\[\s\S]|[^\[\]\\])*\]|\\[\s\S]|`+(?!`)[^`]*?`+(?!`)|``+(?=\]))){0,999}?[^\[\]\\`]*?/).replace("brackets", xe).getRegex();
var xt = h("reflink|nolink(?!\\()", "g").replace("reflink", h(/^!?\[(label)\]\[(ref)\]/).replace("label", mt).replace("ref", ue).getRegex()).replace("nolink", h(/^!?\[(ref)\](?:\[\])?/).replace("ref", ue).getRegex()).getRegex();
var pe = /[hH][tT][tT][pP][sS]?|[fF][tT][pP]/;
var Rt = h(/(?:mailto:email|xmpp:email(?:\/[A-Za-z0-9@.]+)?)/).replace(/email/g, /[A-Za-z0-9._+-]+@[a-zA-Z0-9-_]+(?:\.[a-zA-Z0-9-_]*[a-zA-Z0-9])+(?![\w-])/).getRegex();
var ne = {
	_backpedal: A,
	anyPunctuation: pt,
	autolink: ct,
	blockSkip: We,
	br: ke,
	code: Ne,
	del: A,
	delLDelim: A,
	delRDelim: A,
	emStrongLDelim: Xe,
	emStrongRDelimAst: et,
	emStrongRDelimUnd: st,
	escape: Ge,
	link: kt,
	nolink: ft,
	punctuation: je,
	reflink: gt,
	reflinkSearch: xt,
	tag: dt,
	text: Qe,
	url: A
};
var Tt = {
	...ne,
	emStrongLDelim: Ye,
	emStrongRDelimAst: rt,
	emStrongRDelimUnd: ot,
	link: h(/^!?\[(label)\]\((.*?)\)/).replace("label", U).getRegex(),
	reflink: h(/^!?\[(label)\]\s*\[([^\]]*)\]/).replace("label", U).getRegex()
};
var X = {
	...ne,
	emStrongRDelimAst: tt,
	emStrongLDelim: Je,
	delLDelim: at,
	delRDelim: ut,
	url: h(/^emailProtocol|^((?:protocol):\/\/|www\.)(?:[a-zA-Z0-9\-]+\.?)+[^\s<]*|^email/).replace("emailProtocol", Rt).replace("protocol", pe).replace("email", /[A-Za-z0-9._+-]+(@)[a-zA-Z0-9-_]+(?:\.[a-zA-Z0-9-_]*[a-zA-Z0-9])+(?![\w-])/).getRegex(),
	_backpedal: /(?:[^?!.,:;*_'"~()&]+|\([^)]*\)|&(?![a-zA-Z0-9]+;$)|[?!.,:;*_'"~)]+(?!$))+/,
	del: /^(~~?)(?=[^\s~])((?:\\[\s\S]|[^\\])*?(?:\\[\s\S]|[^\s~\\]))\1(?=[^~]|$)/,
	text: h(/^(?:[^a-zA-Z0-9](?=emailProtocol)|(`+|~+|[^`~])(?:(?=[`~])|(?= {2,}\n)|(?=[a-zA-Z0-9.!#$%&'*+\/=?_`{\|}~-]+@)|[\s\S]*?(?:(?=[\\<!\[`*~_]|\b_|protocol:\/\/|www\.|$)|[^ ](?= {2,}\n)|[^a-zA-Z0-9](?=emailProtocol)|[^a-zA-Z0-9.!#$%&'*+\/=?_`{\|}~-](?=[a-zA-Z0-9.!#$%&'*+\/=?_`{\|}~-]+@))))/).replace("protocol", pe).replace(/emailProtocol/g, /(?:mailto|xmpp):/).getRegex()
};
var Ot = {
	...X,
	br: h(ke).replace("{2,}", "*").getRegex(),
	text: h(X.text).replace("\\b_", "\\b_| {2,}\\n").replace(/\{2,\}/g, "*").getRegex()
};
var j = {
	normal: te,
	gfm: Ze,
	pedantic: He
};
var D = {
	normal: ne,
	gfm: X,
	breaks: Ot,
	pedantic: Tt
};
var wt = {
	"&": "&amp;",
	"<": "&lt;",
	">": "&gt;",
	"\"": "&quot;",
	"'": "&#39;"
};
var be = (l) => wt[l];
function O(l, e) {
	if (e) {
		if (x.escapeTest.test(l)) return l.replace(x.escapeReplace, be);
	} else if (x.escapeTestNoEncode.test(l)) return l.replace(x.escapeReplaceNoEncode, be);
	return l;
}
function Re(l) {
	return l.replace(x.numericCharacterReference, (e, t, n) => {
		let s = t === void 0 ? Number.parseInt(n, 16) : Number.parseInt(t, 10);
		return s === 0 || s > 1114111 || s >= 55296 && s <= 57343 ? "�" : String.fromCodePoint(s);
	});
}
function re(l) {
	try {
		l = encodeURI(l).replace(x.percentDecode, "%");
	} catch {
		return null;
	}
	return l;
}
function se(l, e) {
	let n = l.replace(x.findPipe, (r, o, i) => {
		let u = !1, a = o;
		for (; --a >= 0 && i[a] === "\\";) u = !u;
		return u ? "|" : " |";
	}).split(x.splitPipe), s = 0;
	if (n[0].trim() || n.shift(), n.length > 0 && !n.at(-1)?.trim() && n.pop(), e) if (n.length > e) n.splice(e);
	else for (; n.length < e;) n.push("");
	for (; s < n.length; s++) n[s] = n[s].trim().replace(x.slashPipe, "|");
	return n;
}
function L(l, e, t) {
	let n = l.length;
	if (n === 0) return "";
	let s = 0;
	for (; s < n;) {
		let r = l.charAt(n - s - 1);
		if (r === e && !t) s++;
		else if (r !== e && t) s++;
		else break;
	}
	return l.slice(0, n - s);
}
function ie(l) {
	let e = l.split(`
`), t = e.length - 1;
	for (; t >= 0 && x.blankLine.test(e[t]);) t--;
	return e.length - t <= 2 ? l : e.slice(0, t + 1).join(`
`);
}
function q(l) {
	return l.trim().toLowerCase().toUpperCase().toLowerCase();
}
function Te(l, e) {
	if (l.indexOf(e[1]) === -1) return -1;
	let t = 0;
	for (let n = 0; n < l.length; n++) if (l[n] === "\\") n++;
	else if (l[n] === e[0]) t++;
	else if (l[n] === e[1] && (t--, t < 0)) return n;
	return t > 0 ? -2 : -1;
}
function oe(l, e = 0) {
	let t = e, n = "";
	for (let s of l) if (s === "	") {
		let r = 4 - t % 4;
		n += " ".repeat(r), t += r;
	} else n += s, t++;
	return n;
}
function Oe(l, e, t, n, s) {
	let r = e.href, o = e.title || null, i = l[1].replace(s.other.outputLinkReplace, "$1"), u = l[0].charAt(0) === "!";
	n.state.inLink = !0;
	let a = n.state.linkEmitted, p = n.state.inRawBlock;
	n.state.linkEmitted = !1;
	let c = n.inlineTokens(i), d = n.state.linkEmitted;
	if (n.state.linkEmitted = a, n.state.inLink = !1, !u) {
		if (d) {
			n.state.inRawBlock = p;
			return;
		}
		n.state.linkEmitted = !0;
	}
	return {
		type: u ? "image" : "link",
		raw: t,
		href: r,
		title: o,
		text: i,
		tokens: c
	};
}
function yt(l, e, t) {
	let n = l.match(t.other.indentCodeCompensation);
	if (n === null) return e;
	let s = n[1];
	return e.split(`
`).map((r) => {
		let o = r.match(t.other.beginningSpace);
		if (o === null) return r;
		let [i] = o;
		return r.slice(Math.min(i.length, s.length));
	}).join(`
`);
}
function we(l, e, t, n) {
	if (!e.includes("<")) return !1;
	for (let s = 0; s < e.length; s++) {
		if (e[s] === "\\") {
			s++;
			continue;
		}
		if (e[s] === "`") {
			let i = n.inline.code.exec(e.slice(s));
			if (i) {
				s += i[0].length - 1;
				continue;
			}
		}
		if (e[s] !== "<") continue;
		let r = l.slice(t + s), o = n.inline.tag.exec(r) || n.inline.autolink.exec(r);
		if (o) {
			if (o[0].length > e.length - s) return !0;
			s += o[0].length - 1;
		}
	}
	return !1;
}
var P = class {
	options;
	rules;
	lexer;
	constructor(e) {
		this.options = e || y;
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
			let n = this.options.pedantic ? t[0] : ie(t[0]);
			return {
				type: "code",
				raw: n,
				codeBlockStyle: "indented",
				text: n.replace(this.rules.other.codeRemoveIndent, "")
			};
		}
	}
	fences(e) {
		let t = this.rules.block.fences.exec(e);
		if (t) {
			let n = t[0], s = yt(n, t[3] || "", this.rules);
			return {
				type: "code",
				raw: n,
				lang: t[2] ? t[2].trim().replace(this.rules.inline.anyPunctuation, "$1") : t[2],
				text: s
			};
		}
	}
	heading(e) {
		let t = this.rules.block.heading.exec(e);
		if (t) {
			let n = t[2].trim();
			if (this.rules.other.endingHash.test(n)) {
				let s = L(n, "#");
				(this.options.pedantic || !s || this.rules.other.endingSpaceTabChar.test(s)) && (n = s.trim());
			}
			return {
				type: "heading",
				raw: L(t[0], `
`),
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
			raw: L(t[0], `
`)
		};
	}
	blockquote(e) {
		let t = this.rules.block.blockquote.exec(e);
		if (t) {
			let n = L(t[0], `
`).split(`
`), s = "", r = "", o = [];
			for (; n.length > 0;) {
				let i = !1, u = [], a = 0;
				for (; a < n.length; a++) if (this.rules.other.blockquoteStart.test(n[a])) u.push(n[a]), i = !0;
				else if (!i) u.push(n[a]);
				else break;
				n = n.slice(a);
				let p = u.join(`
`), c = p.replace(this.rules.other.blockquoteSetextReplace, `
    $1`).replace(this.rules.other.blockquoteSetextReplace2, "");
				s = s ? `${s}
${p}` : p, r = r ? `${r}
${c}` : c;
				let d = this.lexer.state.top;
				if (this.lexer.state.top = !0, this.lexer.blockTokens(c, o, !0), this.lexer.state.top = d, n.length === 0) break;
				let m = o.at(-1);
				if (m?.type === "code") break;
				if (m?.type === "blockquote") {
					let b = m, g = n.join(`
`), w = b.raw + `
` + g.replace(this.rules.other.blockquoteSetextReplace2, ""), f = this.blockquote(w);
					o[o.length - 1] = f;
					let M = w.substring(f.raw.length).replace(/^\n/, ""), v = M ? M.split(`
`).length : 0, Z = v ? n.slice(0, -v) : n;
					Z.length > 0 && (s = `${s}
${Z.join(`
`)}`), r = r.substring(0, r.length - b.text.length) + f.text;
					break;
				} else if (m?.type === "list") {
					let b = m, g = b.raw + `
` + n.join(`
`), w = this.list(g);
					o[o.length - 1] = w, s = s.substring(0, s.length - m.raw.length) + w.raw, r = r.substring(0, r.length - b.raw.length) + w.raw, n = g.substring(o.at(-1).raw.length).split(`
`);
					continue;
				}
			}
			return {
				type: "blockquote",
				raw: s,
				tokens: o,
				text: r
			};
		}
	}
	list(e) {
		let t = this.rules.block.list.exec(e);
		if (t) {
			let n = t[1].trim(), s = n.length > 1, r = {
				type: "list",
				raw: "",
				ordered: s,
				start: s ? +n.slice(0, -1) : "",
				loose: !1,
				items: []
			};
			n = s ? `\\d{1,9}\\${n.slice(-1)}` : `\\${n}`, this.options.pedantic && (n = s ? n : "[*+-]");
			let o = this.rules.other.listItemRegex(n), i = !1;
			for (; e;) {
				let a = !1, p = "", c = "";
				if (!(t = o.exec(e)) || this.rules.block.hr.test(e)) break;
				p = t[0], e = e.substring(p.length);
				let d = t[2].split(`
`, 1)[0], m = t[1].length, b = this.options.pedantic ? oe(d, m) : d.replace(this.rules.other.leadingSpaceTab, (M) => oe(M, m)), g = e.split(`
`, 1)[0], w = !b.trim(), f = 0;
				if (this.options.pedantic ? (f = 2, c = b.trimStart()) : w ? f = m + 1 : (f = b.search(this.rules.other.nonSpaceChar), f = f > 4 ? 1 : f, c = b.slice(f), f += m), w && this.rules.other.blankLine.test(g) && (p += g + `
`, e = e.substring(g.length + 1), a = !0), !a) {
					let M = this.rules.other.nextBulletRegex(f), v = this.rules.other.hrRegex(f), Z = this.rules.other.fencesBeginRegex(f), ae = this.rules.other.headingBeginRegex(f), ye = this.rules.other.htmlBeginRegex(f), Pe = this.rules.other.blockquoteBeginRegex(f);
					for (; e;) {
						let K = e.split(`
`, 1)[0], H;
						if (g = K, this.options.pedantic ? (g = g.replace(this.rules.other.listReplaceNesting, "  "), H = g) : H = g.replace(this.rules.other.leadingSpaceTab, (Se) => Se.replace(this.rules.other.tabCharGlobal, "    ")), Z.test(g) || ae.test(g) || ye.test(g) || Pe.test(g) || M.test(g) || v.test(g)) break;
						if (H.search(this.rules.other.nonSpaceChar) >= f || !g.trim()) c += `
` + H.slice(f);
						else {
							if (w || b.replace(this.rules.other.tabCharGlobal, "    ").search(this.rules.other.nonSpaceChar) >= 4 || Z.test(b) || ae.test(b) || v.test(b)) break;
							c += `
` + g;
						}
						w = !g.trim(), p += K + `
`, e = e.substring(K.length + 1), b = H.slice(f);
					}
				}
				r.loose || (i ? r.loose = !0 : this.rules.other.doubleBlankLine.test(p) && (i = !0)), r.items.push({
					type: "list_item",
					raw: p,
					task: !!this.options.gfm && this.rules.other.listIsTask.test(c),
					loose: !1,
					text: c,
					tokens: []
				}), r.raw += p;
			}
			let u = r.items.at(-1);
			if (u) u.raw = u.raw.trimEnd(), u.text = u.text.trimEnd();
			else return;
			r.raw = r.raw.trimEnd();
			for (let a of r.items) if (this.lexer.state.top = !1, a.tokens = this.lexer.blockTokens(a.text, []), !r.loose) {
				let p = a.tokens.filter((d) => d.type === "space");
				r.loose = p.length > 0 && p.some((d) => this.rules.other.anyLine.test(d.raw));
			}
			for (let a of r.items) {
				let p = a.tokens[0];
				if (a.task && (p?.type === "text" || p?.type === "paragraph")) {
					a.text = a.text.replace(this.rules.other.listReplaceTask, ""), p.raw = p.raw.replace(this.rules.other.listReplaceTask, ""), p.text = p.text.replace(this.rules.other.listReplaceTask, "");
					for (let d = this.lexer.inlineQueue.length - 1; d >= 0; d--) if (this.rules.other.listIsTask.test(this.lexer.inlineQueue[d].src)) {
						this.lexer.inlineQueue[d].src = this.lexer.inlineQueue[d].src.replace(this.rules.other.listReplaceTask, "");
						break;
					}
					let c = this.rules.other.listTaskCheckbox.exec(a.raw);
					if (c) {
						let d = {
							type: "checkbox",
							raw: c[0] + " ",
							checked: c[0] !== "[ ]"
						};
						a.checked = d.checked, r.loose ? a.tokens[0] && ["paragraph", "text"].includes(a.tokens[0].type) && "tokens" in a.tokens[0] && a.tokens[0].tokens ? (a.tokens[0].raw = d.raw + a.tokens[0].raw, a.tokens[0].text = d.raw + a.tokens[0].text, a.tokens[0].tokens.unshift(d)) : a.tokens.unshift({
							type: "paragraph",
							raw: d.raw,
							text: d.raw,
							tokens: [d]
						}) : a.tokens.unshift(d);
					}
				} else a.task && (a.task = !1);
			}
			if (r.loose) for (let a of r.items) {
				a.loose = !0;
				for (let p of a.tokens) p.type === "text" && (p.type = "paragraph");
			}
			return r;
		}
	}
	html(e) {
		let t = this.rules.block.html.exec(e);
		if (t) {
			let n = ie(t[0]);
			return {
				type: "html",
				block: !0,
				raw: n,
				pre: t[1] === "pre" || t[1] === "script" || t[1] === "style",
				text: n
			};
		}
	}
	def(e) {
		let t = this.rules.block.def.exec(e);
		if (t) {
			let n = q(t[1]).replace(this.rules.other.multipleSpaceGlobal, " "), s = t[2] ? t[2].replace(this.rules.other.hrefBrackets, "$1").replace(this.rules.inline.anyPunctuation, "$1") : "", r = t[3] ? t[3].substring(1, t[3].length - 1).replace(this.rules.inline.anyPunctuation, "$1") : t[3];
			return {
				type: "def",
				tag: n,
				raw: L(t[0], `
`),
				href: s,
				title: r
			};
		}
	}
	table(e) {
		let t = this.rules.block.table.exec(e);
		if (!t || !this.rules.other.tableDelimiter.test(t[2])) return;
		let n = se(t[1]), s = t[2].replace(this.rules.other.tableAlignChars, "").split("|"), r = t[3]?.trim() ? t[3].replace(this.rules.other.tableRowBlankLine, "").split(`
`) : [], o = {
			type: "table",
			raw: L(t[0], `
`),
			header: [],
			align: [],
			rows: []
		};
		if (n.length === s.length) {
			for (let i of s) this.rules.other.tableAlignRight.test(i) ? o.align.push("right") : this.rules.other.tableAlignCenter.test(i) ? o.align.push("center") : this.rules.other.tableAlignLeft.test(i) ? o.align.push("left") : o.align.push(null);
			for (let i = 0; i < n.length; i++) o.header.push({
				text: n[i],
				tokens: this.lexer.inline(n[i]),
				header: !0,
				align: o.align[i]
			});
			for (let i of r) o.rows.push(se(i, o.header.length).map((u, a) => ({
				text: u,
				tokens: this.lexer.inline(u),
				header: !1,
				align: o.align[a]
			})));
			return o;
		}
	}
	lheading(e) {
		let t = this.rules.block.lheading.exec(e);
		if (t) {
			let n = t[1].trim();
			return {
				type: "heading",
				raw: L(t[0], `
`),
				depth: t[2].charAt(0) === "=" ? 1 : 2,
				text: n,
				tokens: this.lexer.inline(n)
			};
		}
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
			let n = t[0].charAt(0) === "!" ? 2 : 1;
			if (!this.options.pedantic && we(e, t[1], n, this.rules)) return;
			let s = t[2].trim();
			if (!this.options.pedantic && this.rules.other.startAngleBracket.test(s)) {
				if (!this.rules.other.endAngleBracket.test(s)) return;
				let i = L(s.slice(0, -1), "\\");
				if ((s.length - i.length) % 2 === 0) return;
			} else {
				let i = Te(t[2], "()");
				if (i === -2) return;
				if (i > -1) {
					let a = (t[0].indexOf("!") === 0 ? 5 : 4) + t[1].length + i;
					t[2] = t[2].substring(0, i), t[0] = t[0].substring(0, a).trim(), t[3] = "";
				}
			}
			let r = t[2], o = "";
			if (this.options.pedantic) {
				let i = this.rules.other.pedanticHrefTitle.exec(r);
				i && (r = i[1], o = i[3]);
			} else o = t[3] ? t[3].slice(1, -1) : "";
			return r = r.trim(), this.rules.other.startAngleBracket.test(r) && (this.options.pedantic && !this.rules.other.endAngleBracket.test(s) ? r = r.slice(1) : r = r.slice(1, -1)), Oe(t, {
				href: r && r.replace(this.rules.inline.anyPunctuation, "$1"),
				title: o && o.replace(this.rules.inline.anyPunctuation, "$1")
			}, t[0], this.lexer, this.rules);
		}
	}
	reflink(e, t) {
		let n;
		if ((n = this.rules.inline.reflink.exec(e)) || (n = this.rules.inline.nolink.exec(e))) {
			let s = n[0].charAt(0) === "!" ? 2 : 1;
			if (!this.options.pedantic && we(e, n[1], s, this.rules)) return;
			let o = t[q((n[2] || n[1]).replace(this.rules.other.multipleSpaceGlobal, " "))];
			if (!o) {
				let i = n[0].charAt(0);
				return {
					type: "text",
					raw: i,
					text: i
				};
			}
			return Oe(n, o, n[0], this.lexer, this.rules);
		}
	}
	emStrong(e, t, n = "") {
		let s = this.rules.inline.emStrongLDelim.exec(e);
		if (!s || !s[1] && !s[2] && !s[3] && !s[4] || s[4] && n.match(this.rules.other.unicodeAlphaNumeric)) return;
		if (!(s[1] || s[3] || "") || !n || this.rules.inline.punctuation.exec(n)) {
			let o = [...s[0]].length - 1, i, u, a = o, p = 0, c = s[0][0], d = n === c, m = c === "*" ? this.rules.inline.emStrongRDelimAst : this.rules.inline.emStrongRDelimUnd;
			for (m.lastIndex = 0, t = t.slice(-1 * e.length + o); (s = m.exec(t)) !== null;) {
				if (i = s[1] || s[2] || s[3] || s[4] || s[5] || s[6], !i) continue;
				if (u = [...i].length, s[3] || s[4]) {
					a += u;
					continue;
				} else if (s[5] || s[6]) {
					if (o % 3 && !((o + u) % 3)) {
						p += u;
						continue;
					}
					if (d) break;
				}
				if (a -= u, a > 0) continue;
				u = Math.min(u, u + a + p);
				let b = [...s[0]][0].length, g = e.slice(0, o + s.index + b + u);
				if (Math.min(o, u) % 2) {
					let f = g.slice(1, -1);
					return {
						type: "em",
						raw: g,
						text: f,
						tokens: this.lexer.inlineTokens(f)
					};
				}
				let w = g.slice(2, -2);
				return {
					type: "strong",
					raw: g,
					text: w,
					tokens: this.lexer.inlineTokens(w)
				};
			}
		}
	}
	codespan(e) {
		let t = this.rules.inline.code.exec(e);
		if (t) {
			let n = t[2].replace(this.rules.other.newLineCharGlobal, " "), s = this.rules.other.nonSpaceChar.test(n), r = this.rules.other.startingSpaceChar.test(n) && this.rules.other.endingSpaceChar.test(n);
			return s && r && (n = n.substring(1, n.length - 1)), {
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
	del(e, t, n = "") {
		let s = this.rules.inline.delLDelim.exec(e);
		if (!s) return;
		if (!(s[1] || "") || !n || this.rules.inline.punctuation.exec(n)) {
			let o = [...s[0]].length - 1, i, u, a = o, p = this.rules.inline.delRDelim;
			for (p.lastIndex = 0, t = t.slice(-1 * e.length + o); (s = p.exec(t)) !== null;) {
				if (i = s[1] || s[2] || s[3] || s[4] || s[5] || s[6], !i || (u = [...i].length, u !== o)) continue;
				if (s[3] || s[4]) {
					a += u;
					continue;
				}
				if (a -= u, a > 0) continue;
				u = Math.min(u, u + a);
				let c = [...s[0]][0].length, d = e.slice(0, o + s.index + c + u), m = d.slice(o, -o);
				return {
					type: "del",
					raw: d,
					text: m,
					tokens: this.lexer.inlineTokens(m)
				};
			}
		}
	}
	autolink(e) {
		let t = this.rules.inline.autolink.exec(e);
		if (t) {
			let n, s;
			return t[2] === "@" ? (n = t[1], s = "mailto:" + n) : (n = t[1], s = n), {
				type: "link",
				raw: t[0],
				text: n,
				href: s,
				autolink: !0,
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
			let n, s;
			if (t[2] === "@") n = t[0], s = "mailto:" + n;
			else {
				let r;
				do
					r = t[0], t[0] = this.rules.inline._backpedal.exec(t[0])?.[0] ?? "";
				while (r !== t[0]);
				n = t[0], t[1] === "www." ? s = "http://" + t[0] : s = t[0];
			}
			return {
				type: "link",
				raw: t[0],
				text: n,
				href: s,
				autolink: !0,
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
				text: n ? t[0] : Re(t[0]),
				escaped: n
			};
		}
	}
};
var R = class l {
	tokens;
	options;
	state;
	inlineQueue;
	tokenizer;
	constructor(e) {
		this.tokens = [], this.tokens.links = Object.create(null), this.options = e || y, this.options.tokenizer = this.options.tokenizer || new P(), this.tokenizer = this.options.tokenizer, this.tokenizer.options = this.options, this.tokenizer.lexer = this, this.inlineQueue = [], this.state = {
			inLink: !1,
			inRawBlock: !1,
			linkEmitted: !1,
			top: !0
		};
		let t = {
			other: x,
			block: j.normal,
			inline: D.normal
		};
		this.options.pedantic ? (t.block = j.pedantic, t.inline = D.pedantic) : this.options.gfm && (t.block = j.gfm, this.options.breaks ? t.inline = D.breaks : t.inline = D.gfm), this.tokenizer.rules = t;
	}
	static get rules() {
		return {
			block: j,
			inline: D
		};
	}
	static lex(e, t) {
		return new l(t).lex(e);
	}
	static lexInline(e, t) {
		return new l(t).inlineTokens(e);
	}
	lex(e) {
		e = e.replace(x.carriageReturn, `
`), this.blockTokens(e, this.tokens);
		for (let t = 0; t < this.inlineQueue.length; t++) {
			let n = this.inlineQueue[t];
			this.inlineTokens(n.src, n.tokens);
		}
		return this.inlineQueue = [], this.tokens;
	}
	blockTokens(e, t = [], n = !1) {
		this.tokenizer.lexer = this, this.options.pedantic && (e = e.replace(x.tabCharGlobal, "    ").replace(x.spaceLine, ""));
		let s = 1 / 0;
		for (; e;) {
			if (e.length < s) s = e.length;
			else {
				this.infiniteLoopError(e.charCodeAt(0));
				break;
			}
			let r;
			if (this.options.extensions?.block?.some((i) => (r = i.call({ lexer: this }, e, t)) ? (e = e.substring(r.raw.length), t.push(r), !0) : !1)) continue;
			if (r = this.tokenizer.space(e)) {
				e = e.substring(r.raw.length);
				let i = t.at(-1);
				r.raw.length === 1 && i !== void 0 ? i.raw += `
` : t.push(r);
				continue;
			}
			if (r = this.tokenizer.code(e)) {
				e = e.substring(r.raw.length);
				let i = t.at(-1);
				i?.type === "paragraph" || i?.type === "text" ? (i.raw += (i.raw.endsWith(`
`) ? "" : `
`) + r.raw, i.text += `
` + r.text, this.inlineQueue.at(-1).src = i.text) : t.push(r);
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
				let i = t.at(-1);
				i?.type === "paragraph" || i?.type === "text" ? (i.raw += (i.raw.endsWith(`
`) ? "" : `
`) + r.raw, i.text += `
` + r.raw, this.inlineQueue.at(-1).src = i.text) : this.tokens.links[r.tag] || (this.tokens.links[r.tag] = {
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
			let o = e;
			if (this.options.extensions?.startBlock) {
				let i = 1 / 0, u = e.slice(1), a;
				this.options.extensions.startBlock.forEach((p) => {
					a = p.call({ lexer: this }, u), typeof a == "number" && a >= 0 && (i = Math.min(i, a));
				}), i < 1 / 0 && i >= 0 && (o = e.substring(0, i + 1));
			}
			if (this.state.top && (r = this.tokenizer.paragraph(o))) {
				let i = t.at(-1);
				n && i?.type === "paragraph" ? (i.raw += (i.raw.endsWith(`
`) ? "" : `
`) + r.raw, i.text += `
` + r.text, this.inlineQueue.pop(), this.inlineQueue.at(-1).src = i.text) : t.push(r), n = o.length !== e.length, e = e.substring(r.raw.length);
				continue;
			}
			if (r = this.tokenizer.text(e)) {
				e = e.substring(r.raw.length);
				let i = t.at(-1);
				i?.type === "text" ? (i.raw += (i.raw.endsWith(`
`) ? "" : `
`) + r.raw, i.text += `
` + r.text, this.inlineQueue.pop(), this.inlineQueue.at(-1).src = i.text) : t.push(r);
				continue;
			}
			if (e) {
				this.infiniteLoopError(e.charCodeAt(0));
				break;
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
	linkInText(e) {
		if (!e.includes("[")) return !1;
		let t = this.tokenizer.rules.inline.link;
		for (let n of e.matchAll(this.tokenizer.rules.inline.blockSkip)) if (t.test(n[0]) && e.charAt(n.index - 1) !== "!") return !0;
		for (let n of e.matchAll(this.tokenizer.rules.inline.reflinkSearch)) {
			let s = n[0], r = s.lastIndexOf("[");
			if (!(s.charAt(0) === "!" || !Object.hasOwn(this.tokens.links, q(s.slice(r + 1, -1)))) && !(r > 1 && this.linkInText(s.slice(1, r - 1)))) return !0;
		}
		return !1;
	}
	inlineTokens(e, t = []) {
		this.tokenizer.lexer = this;
		let n = e;
		if (this.tokens.links && e.includes("[")) {
			let i = this.tokenizer.rules.inline.reflinkSearch, u = (a) => {
				let p = a.lastIndexOf("[");
				if (!Object.hasOwn(this.tokens.links, q(a.slice(p + 1, -1)))) return a;
				if (p > 1 && a.charAt(0) !== "!") {
					let c = a.slice(1, p - 1);
					if (this.linkInText(c)) return "[" + c.replace(i, u) + "][" + "a".repeat(a.length - p - 2) + "]";
				}
				return "[" + "a".repeat(a.length - 2) + "]";
			};
			n = n.replace(i, u);
		}
		n = n.replace(this.tokenizer.rules.inline.anyPunctuation, (i) => "+".repeat(i.length)), n = n.replace(this.tokenizer.rules.inline.blockSkip, (i, u, a) => {
			let p = a ? a.length : 0;
			return i.slice(0, p) + "[" + "a".repeat(i.length - p - 2) + "]";
		}), n = this.options.hooks?.emStrongMask?.call({ lexer: this }, n) ?? n;
		let s = !1, r = "", o = 1 / 0;
		for (; e;) {
			if (e.length < o) o = e.length;
			else {
				this.infiniteLoopError(e.charCodeAt(0));
				break;
			}
			s || (r = ""), s = !1;
			let i;
			if (this.options.extensions?.inline?.some((a) => (i = a.call({ lexer: this }, e, t)) ? (e = e.substring(i.raw.length), t.push(i), !0) : !1)) continue;
			if (i = this.tokenizer.escape(e)) {
				e = e.substring(i.raw.length), t.push(i);
				continue;
			}
			if (i = this.tokenizer.tag(e)) {
				e = e.substring(i.raw.length), t.push(i);
				continue;
			}
			if (i = this.tokenizer.link(e)) {
				e = e.substring(i.raw.length), t.push(i);
				continue;
			}
			if (i = this.tokenizer.reflink(e, this.tokens.links)) {
				e = e.substring(i.raw.length);
				let a = t.at(-1);
				i.type === "text" && a?.type === "text" ? (a.raw += i.raw, a.text += i.text) : t.push(i);
				continue;
			}
			if (i = this.tokenizer.emStrong(e, n, r)) {
				e = e.substring(i.raw.length), t.push(i);
				continue;
			}
			if (i = this.tokenizer.codespan(e)) {
				e = e.substring(i.raw.length), t.push(i);
				continue;
			}
			if (i = this.tokenizer.br(e)) {
				e = e.substring(i.raw.length), t.push(i);
				continue;
			}
			if (i = this.tokenizer.del(e, n, r)) {
				e = e.substring(i.raw.length), t.push(i);
				continue;
			}
			if (i = this.tokenizer.autolink(e)) {
				e = e.substring(i.raw.length), t.push(i);
				continue;
			}
			if (!this.state.inLink && (i = this.tokenizer.url(e))) {
				e = e.substring(i.raw.length), t.push(i);
				continue;
			}
			let u = e;
			if (this.options.extensions?.startInline) {
				let a = 1 / 0, p = e.slice(1), c;
				this.options.extensions.startInline.forEach((d) => {
					c = d.call({ lexer: this }, p), typeof c == "number" && c >= 0 && (a = Math.min(a, c));
				}), a < 1 / 0 && a >= 0 && (u = e.substring(0, a + 1));
			}
			if (i = this.tokenizer.inlineText(u)) {
				e = e.substring(i.raw.length), i.raw.slice(-1) !== "_" && (r = i.raw.slice(-1)), s = !0;
				let a = t.at(-1);
				a?.type === "text" ? (a.raw += i.raw, a.text += i.text) : t.push(i);
				continue;
			}
			if (e) {
				this.infiniteLoopError(e.charCodeAt(0));
				break;
			}
		}
		return t;
	}
	infiniteLoopError(e) {
		let t = "Infinite loop on byte: " + e;
		if (this.options.silent) console.error(t);
		else throw new Error(t);
	}
};
var S = class {
	options;
	parser;
	constructor(e) {
		this.options = e || y;
	}
	space(e) {
		return "";
	}
	code({ text: e, lang: t, escaped: n }) {
		let s = (t || "").match(x.notSpaceStart)?.[0], r = e ? e.replace(x.endingNewline, "") + `
` : "";
		return s ? "<pre><code class=\"language-" + O(s) + "\">" + (n ? r : O(r, !0)) + `</code></pre>
` : "<pre><code>" + (n ? r : O(r, !0)) + `</code></pre>
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
		let t = e.ordered, n = e.start, s = "";
		for (let i = 0; i < e.items.length; i++) {
			let u = e.items[i];
			s += this.listitem(u);
		}
		let r = t ? "ol" : "ul", o = t && n !== 1 ? " start=\"" + n + "\"" : "";
		return "<" + r + o + `>
` + s + "</" + r + `>
`;
	}
	listitem(e) {
		return `<li>${this.parser.parse(e.tokens)}</li>
`;
	}
	checkbox({ checked: e }) {
		return "<input " + (e ? "checked=\"\" " : "") + "disabled=\"\" type=\"checkbox\"> ";
	}
	paragraph({ tokens: e }) {
		return `<p>${this.parser.parseInline(e)}</p>
`;
	}
	table(e) {
		let t = "", n = "";
		for (let r = 0; r < e.header.length; r++) n += this.tablecell(e.header[r]);
		t += this.tablerow({ text: n });
		let s = "";
		for (let r = 0; r < e.rows.length; r++) {
			let o = e.rows[r];
			n = "";
			for (let i = 0; i < o.length; i++) n += this.tablecell(o[i]);
			s += this.tablerow({ text: n });
		}
		return s && (s = `<tbody>${s}</tbody>`), `<table>
<thead>
` + t + `</thead>
` + s + `</table>
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
		return `<code>${O(e, !0)}</code>`;
	}
	br(e) {
		return "<br>";
	}
	del({ tokens: e }) {
		return `<del>${this.parser.parseInline(e)}</del>`;
	}
	link({ href: e, title: t, text: n, tokens: s, autolink: r }) {
		let o = r ? O(n, !0) : this.parser.parseInline(s), i = re(e);
		if (i === null) return o;
		e = O(i, r);
		let u = "<a href=\"" + e + "\"";
		return t && (u += " title=\"" + O(t) + "\""), u += ">" + o + "</a>", u;
	}
	image({ href: e, title: t, text: n, tokens: s }) {
		s && (n = this.parser.parseInline(s, this.parser.textRenderer));
		let r = re(e);
		if (r === null) return O(n);
		e = r;
		let o = `<img src="${O(e)}" alt="${O(n)}"`;
		return t && (o += ` title="${O(t)}"`), o += ">", o;
	}
	text(e) {
		return "tokens" in e && e.tokens ? this.parser.parseInline(e.tokens) : "escaped" in e && e.escaped ? e.text : O(e.text);
	}
};
var z = class {
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
	checkbox({ raw: e }) {
		return e;
	}
};
var T = class l {
	options;
	renderer;
	textRenderer;
	constructor(e) {
		this.options = e || y, this.options.renderer = this.options.renderer || new S(), this.renderer = this.options.renderer, this.renderer.options = this.options, this.renderer.parser = this, this.textRenderer = new z();
	}
	static parse(e, t) {
		return new l(t).parse(e);
	}
	static parseInline(e, t) {
		return new l(t).parseInline(e);
	}
	parse(e) {
		this.renderer.parser = this;
		let t = "";
		for (let n = 0; n < e.length; n++) {
			let s = e[n];
			if (this.options.extensions?.renderers?.[s.type]) {
				let o = s, i = this.options.extensions.renderers[o.type].call({ parser: this }, o);
				if (i !== !1 || ![
					"space",
					"hr",
					"heading",
					"code",
					"table",
					"blockquote",
					"list",
					"checkbox",
					"html",
					"def",
					"paragraph",
					"text"
				].includes(o.type)) {
					t += i || "";
					continue;
				}
			}
			let r = s;
			switch (r.type) {
				case "space":
					t += this.renderer.space(r);
					break;
				case "hr":
					t += this.renderer.hr(r);
					break;
				case "heading":
					t += this.renderer.heading(r);
					break;
				case "code":
					t += this.renderer.code(r);
					break;
				case "table":
					t += this.renderer.table(r);
					break;
				case "blockquote":
					t += this.renderer.blockquote(r);
					break;
				case "list":
					t += this.renderer.list(r);
					break;
				case "checkbox":
					t += this.renderer.checkbox(r);
					break;
				case "html":
					t += this.renderer.html(r);
					break;
				case "def":
					t += this.renderer.def(r);
					break;
				case "paragraph":
					t += this.renderer.paragraph(r);
					break;
				case "text":
					t += this.renderer.text(r);
					break;
				default: {
					let o = "Token with \"" + r.type + "\" type was not found.";
					if (this.options.silent) return console.error(o), "";
					throw new Error(o);
				}
			}
		}
		return t;
	}
	parseInline(e, t = this.renderer) {
		this.renderer.parser = this;
		let n = "";
		for (let s = 0; s < e.length; s++) {
			let r = e[s];
			if (this.options.extensions?.renderers?.[r.type]) {
				let i = this.options.extensions.renderers[r.type].call({ parser: this }, r);
				if (i !== !1 || ![
					"escape",
					"html",
					"link",
					"image",
					"checkbox",
					"strong",
					"em",
					"codespan",
					"br",
					"del",
					"text"
				].includes(r.type)) {
					n += i || "";
					continue;
				}
			}
			let o = r;
			switch (o.type) {
				case "escape":
					n += t.text(o);
					break;
				case "html":
					n += t.html(o);
					break;
				case "link":
					n += t.link(o);
					break;
				case "image":
					n += t.image(o);
					break;
				case "checkbox":
					n += t.checkbox(o);
					break;
				case "strong":
					n += t.strong(o);
					break;
				case "em":
					n += t.em(o);
					break;
				case "codespan":
					n += t.codespan(o);
					break;
				case "br":
					n += t.br(o);
					break;
				case "del":
					n += t.del(o);
					break;
				case "text":
					n += t.text(o);
					break;
				default: {
					let i = "Token with \"" + o.type + "\" type was not found.";
					if (this.options.silent) return console.error(i), "";
					throw new Error(i);
				}
			}
		}
		return n;
	}
};
var _ = class {
	options;
	block;
	constructor(e) {
		this.options = e || y;
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
	provideLexer(e = this.block) {
		return e ? R.lex : R.lexInline;
	}
	provideParser(e = this.block) {
		return e ? T.parse : T.parseInline;
	}
};
var F = class {
	defaults = I();
	options = this.setOptions;
	parse = this.parseMarkdown(!0);
	parseInline = this.parseMarkdown(!1);
	Parser = T;
	Renderer = S;
	TextRenderer = z;
	Lexer = R;
	Tokenizer = P;
	Hooks = _;
	constructor(...e) {
		this.use(...e);
	}
	walkTokens(e, t) {
		let n = [];
		for (let s of e) switch (n = n.concat(t.call(this, s)), s.type) {
			case "table": {
				let r = s;
				for (let o of r.header) n = n.concat(this.walkTokens(o.tokens, t));
				for (let o of r.rows) for (let i of o) n = n.concat(this.walkTokens(i.tokens, t));
				break;
			}
			case "list": {
				let r = s;
				n = n.concat(this.walkTokens(r.items, t));
				break;
			}
			default: {
				let r = s;
				this.defaults.extensions?.childTokens?.[r.type] ? this.defaults.extensions.childTokens[r.type].forEach((o) => {
					let i = r[o].flat(1 / 0);
					n = n.concat(this.walkTokens(i, t));
				}) : r.tokens && (n = n.concat(this.walkTokens(r.tokens, t)));
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
			let s = { ...n };
			if (s.async = this.defaults.async || s.async || !1, n.extensions && (n.extensions.forEach((r) => {
				if (!r.name) throw new Error("extension name required");
				if ("renderer" in r) {
					let o = t.renderers[r.name];
					o ? t.renderers[r.name] = function(...i) {
						let u = r.renderer.apply(this, i);
						return u === !1 && (u = o.apply(this, i)), u;
					} : t.renderers[r.name] = r.renderer;
				}
				if ("tokenizer" in r) {
					if (!r.level || r.level !== "block" && r.level !== "inline") throw new Error("extension level must be 'block' or 'inline'");
					let o = t[r.level];
					o ? o.unshift(r.tokenizer) : t[r.level] = [r.tokenizer], r.start && (r.level === "block" ? t.startBlock ? t.startBlock.push(r.start) : t.startBlock = [r.start] : r.level === "inline" && (t.startInline ? t.startInline.push(r.start) : t.startInline = [r.start]));
				}
				"childTokens" in r && r.childTokens && (t.childTokens[r.name] = r.childTokens);
			}), s.extensions = t), n.renderer) {
				let r = this.defaults.renderer || new S(this.defaults);
				for (let o in n.renderer) {
					if (!(o in r)) throw new Error(`renderer '${o}' does not exist`);
					if (["options", "parser"].includes(o)) continue;
					let i = o, u = n.renderer[i], a = r[i];
					r[i] = (...p) => {
						let c = u.apply(r, p);
						return c === !1 && (c = a.apply(r, p)), c || "";
					};
				}
				s.renderer = r;
			}
			if (n.tokenizer) {
				let r = this.defaults.tokenizer || new P(this.defaults);
				for (let o in n.tokenizer) {
					if (!(o in r)) throw new Error(`tokenizer '${o}' does not exist`);
					if ([
						"options",
						"rules",
						"lexer"
					].includes(o)) continue;
					let i = o, u = n.tokenizer[i], a = r[i];
					r[i] = (...p) => {
						let c = u.apply(r, p);
						return c === !1 && (c = a.apply(r, p)), c;
					};
				}
				s.tokenizer = r;
			}
			if (n.hooks) {
				let r = this.defaults.hooks || new _();
				for (let o in n.hooks) {
					if (!(o in r)) throw new Error(`hook '${o}' does not exist`);
					if (["options", "block"].includes(o)) continue;
					let i = o, u = n.hooks[i], a = r[i];
					_.passThroughHooks.has(o) ? r[i] = (p) => {
						if (this.defaults.async && _.passThroughHooksRespectAsync.has(o)) return (async () => {
							let d = await u.call(r, p);
							return a.call(r, d);
						})();
						let c = u.call(r, p);
						return a.call(r, c);
					} : r[i] = (...p) => {
						if (this.defaults.async) return (async () => {
							let d = await u.apply(r, p);
							return d === !1 && (d = await a.apply(r, p)), d;
						})();
						let c = u.apply(r, p);
						return c === !1 && (c = a.apply(r, p)), c;
					};
				}
				s.hooks = r;
			}
			if (n.walkTokens) {
				let r = this.defaults.walkTokens, o = n.walkTokens;
				s.walkTokens = function(i) {
					let u = [];
					return u.push(o.call(this, i)), r && (u = u.concat(r.call(this, i))), u;
				};
			}
			this.defaults = {
				...this.defaults,
				...s
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
		return R.lex(e, t ?? this.defaults);
	}
	parser(e, t) {
		return T.parse(e, t ?? this.defaults);
	}
	parseMarkdown(e) {
		return (n, s) => {
			let r = { ...s }, o = {
				...this.defaults,
				...r
			}, i = this.onError(!!o.silent, !!o.async);
			if (this.defaults.async === !0 && r.async === !1) return i(/* @__PURE__ */ new Error("marked(): The async option was set to true by an extension. Remove async: false from the parse options object to return a Promise."));
			if (typeof n > "u" || n === null) return i(/* @__PURE__ */ new Error("marked(): input parameter is undefined or null"));
			if (typeof n != "string") return i(/* @__PURE__ */ new Error("marked(): input parameter is of type " + Object.prototype.toString.call(n) + ", string expected"));
			if (o.hooks && (o.hooks.options = o, o.hooks.block = e), o.async) return (async () => {
				let u = o.hooks ? await o.hooks.preprocess(n) : n, p = await (o.hooks ? await o.hooks.provideLexer(e) : e ? R.lex : R.lexInline)(u, o), c = o.hooks ? await o.hooks.processAllTokens(p) : p;
				o.walkTokens && await Promise.all(this.walkTokens(c, o.walkTokens));
				let m = await (o.hooks ? await o.hooks.provideParser(e) : e ? T.parse : T.parseInline)(c, o);
				return o.hooks ? await o.hooks.postprocess(m) : m;
			})().catch(i);
			try {
				o.hooks && (n = o.hooks.preprocess(n));
				let a = (o.hooks ? o.hooks.provideLexer(e) : e ? R.lex : R.lexInline)(n, o);
				o.hooks && (a = o.hooks.processAllTokens(a)), o.walkTokens && this.walkTokens(a, o.walkTokens);
				let c = (o.hooks ? o.hooks.provideParser(e) : e ? T.parse : T.parseInline)(a, o);
				return o.hooks && (c = o.hooks.postprocess(c)), c;
			} catch (u) {
				return i(u);
			}
		};
	}
	onError(e, t) {
		return (n) => {
			if (n.message += `
Please report this to https://github.com/markedjs/marked.`, e) {
				let s = "<p>An error occurred:</p><pre>" + O(n.message + "", !0) + "</pre>";
				return t ? Promise.resolve(s) : s;
			}
			if (t) return Promise.reject(n);
			throw n;
		};
	}
};
var E = new F();
function k(l, e) {
	return E.parse(l, e);
}
k.options = k.setOptions = function(l) {
	return E.setOptions(l), k.defaults = E.defaults, W(k.defaults), k;
};
k.getDefaults = I;
k.defaults = y;
function Pt(...l) {
	return E.use(...l), k.defaults = E.defaults, W(k.defaults), k;
}
k.use = Pt;
k.walkTokens = function(l, e) {
	return E.walkTokens(l, e);
};
k.parseInline = E.parseInline;
k.Parser = T;
k.parser = T.parse;
k.Renderer = S;
k.TextRenderer = z;
k.Lexer = R;
k.lexer = R.lex;
k.Tokenizer = P;
k.Hooks = _;
k.parse = k;
k.options;
k.setOptions;
k.walkTokens;
k.parseInline;
T.parse;
R.lex;
//#endregion
//#region src/ui/markdown.ts
init_clientLogic();
var lowlight = createLowlight();
lowlight.register({
	bash,
	cpp,
	dart,
	javascript: javascript$1,
	json,
	markdown,
	python,
	sql,
	typescript,
	xml,
	yaml
});
lowlight.registerAlias({
	bash: [
		"sh",
		"shell",
		"zsh"
	],
	cpp: [
		"c",
		"cxx",
		"h",
		"hpp"
	],
	javascript: [
		"js",
		"jsx",
		"mjs",
		"cjs"
	],
	markdown: ["md"],
	python: ["py"],
	typescript: ["ts", "tsx"],
	xml: ["html", "svg"],
	yaml: ["yml"]
});
var MARKDOWN_CACHE_MAX_ENTRIES = 192;
var MARKDOWN_CACHE_MAX_SOURCE_CHARS = 1e6;
var markdownCache = /* @__PURE__ */ new Map();
var markdownCacheSourceChars = 0;
var HIGHLIGHT_CACHE_MAX_ENTRIES = 128;
var HIGHLIGHT_CACHE_MAX_CODE_CHARS = 512e3;
var highlightCache = /* @__PURE__ */ new Map();
var highlightCacheCodeChars = 0;
function promoteCacheEntry(cache, key, value) {
	cache.delete(key);
	cache.set(key, value);
}
function evictCacheEntries(cache, maxEntries, currentChars, incomingChars, maxChars) {
	let chars = currentChars;
	while (cache.size && (cache.size >= maxEntries || chars + incomingChars > maxChars)) {
		const oldestKey = cache.keys().next().value;
		if (oldestKey === void 0) break;
		const oldest = cache.get(oldestKey);
		cache.delete(oldestKey);
		chars -= oldest?.sourceChars ?? oldest?.codeChars ?? 0;
	}
	return chars;
}
function escapeMarkdownLabel(value) {
	return value.replaceAll("\\", "\\\\").replaceAll("[", "\\[").replaceAll("]", "\\]");
}
function richMarkersToMarkdown(value) {
	return replaceChatGptRichMarkers(value, (label, url) => {
		const safeUrl = url.replaceAll(">", "%3E");
		return `[${escapeMarkdownLabel(label)}](<${safeUrl}>)`;
	});
}
function incompleteFenceStart(source) {
	const pattern = /^ {0,3}```[^\n]*(?:\n|$)/gm;
	let openAt = -1;
	let match;
	while ((match = pattern.exec(source)) !== null) openAt = openAt < 0 ? match.index : -1;
	return openAt;
}
function lexMarkdown(source, renderIncompleteFence) {
	const openFenceAt = incompleteFenceStart(source);
	if (openFenceAt >= 0) {
		if (renderIncompleteFence) source += "\n```";
		else {
			const prefix = k.lexer(source.slice(0, openFenceAt), {
				async: false,
				breaks: false,
				gfm: true
			});
			const remainder = source.slice(openFenceAt);
			return [...prefix, {
				type: "paragraph",
				raw: remainder,
				text: remainder,
				tokens: [{
					type: "text",
					raw: remainder,
					text: remainder
				}]
			}];
		}
	}
	return k.lexer(source, {
		async: false,
		breaks: false,
		gfm: true
	});
}
function parseMarkdown(raw, { renderIncompleteFence = false } = {}) {
	const source = richMarkersToMarkdown(raw);
	if (renderIncompleteFence || source.length > MARKDOWN_CACHE_MAX_SOURCE_CHARS) return lexMarkdown(source, renderIncompleteFence);
	const cached = markdownCache.get(source);
	if (cached) {
		promoteCacheEntry(markdownCache, source, cached);
		return cached.document;
	}
	const document = lexMarkdown(source, false);
	markdownCacheSourceChars = evictCacheEntries(markdownCache, MARKDOWN_CACHE_MAX_ENTRIES, markdownCacheSourceChars, source.length, MARKDOWN_CACHE_MAX_SOURCE_CHARS);
	markdownCache.set(source, {
		document,
		sourceChars: source.length
	});
	markdownCacheSourceChars += source.length;
	return document;
}
function normalizedLanguage(value) {
	const raw = String(value || "").trim().toLowerCase().split(/\s+/)[0];
	return {
		c: "c",
		cjs: "javascript",
		cxx: "cpp",
		h: "c",
		hpp: "cpp",
		html: "xml",
		js: "javascript",
		jsx: "javascript",
		md: "markdown",
		mjs: "javascript",
		py: "python",
		sh: "bash",
		shell: "bash",
		svg: "xml",
		ts: "typescript",
		tsx: "typescript",
		xml: "xml",
		yml: "yaml",
		zsh: "bash"
	}[raw] || raw || "plaintext";
}
function highlightedCode(code, language) {
	if (!code) return [];
	const normalized = normalizedLanguage(language);
	if (!lowlight.registered(normalized)) return [{
		type: "text",
		value: code
	}];
	const key = `${normalized}\u0000${code}`;
	const cached = highlightCache.get(key);
	if (cached) {
		promoteCacheEntry(highlightCache, key, cached);
		return cached.nodes;
	}
	let nodes;
	try {
		nodes = lowlight.highlight(normalized, code).children;
	} catch {
		nodes = [{
			type: "text",
			value: code
		}];
	}
	if (code.length <= HIGHLIGHT_CACHE_MAX_CODE_CHARS) {
		highlightCacheCodeChars = evictCacheEntries(highlightCache, HIGHLIGHT_CACHE_MAX_ENTRIES, highlightCacheCodeChars, code.length, HIGHLIGHT_CACHE_MAX_CODE_CHARS);
		highlightCache.set(key, {
			nodes,
			codeChars: code.length
		});
		highlightCacheCodeChars += code.length;
	}
	return nodes;
}
function codePresentation(token) {
	const rawLanguage = String(token.lang || "").trim();
	const language = normalizedLanguage(rawLanguage);
	const toolMatch = rawLanguage.match(/^(?:tool|tool-call|function|function-call)(?::\s*(.+))?$/i);
	const inlineToolMatch = token.text.match(/^\s*(?:tool|function|to)\s*[:=]\s*([\w.-]+)/i);
	const toolish = Boolean(toolMatch || inlineToolMatch);
	const rawToolName = toolMatch?.[1]?.trim() || inlineToolMatch?.[1] || "";
	const toolName = toolCallDisplayName(rawToolName);
	const trimmedCode = token.text.trim();
	const genericToolInvocation = toolish && toolCallIsInvocationPlaceholder(trimmedCode);
	const hasUsefulToolDetail = !toolish || toolCallHasUsefulDetail(trimmedCode);
	if (toolish && !toolName && !hasUsefulToolDetail && !genericToolInvocation) return null;
	const pythonCode = toolish ? pythonToolCallCode(rawToolName, trimmedCode) : "";
	const code = pythonCode || (toolish && (!hasUsefulToolDetail || genericToolInvocation) ? "" : token.text);
	const highlightLanguage = pythonCode ? "python" : toolish ? trimmedCode.startsWith("{") || trimmedCode.startsWith("[") ? "json" : "plaintext" : language;
	const label = pythonCode ? "python" : toolish ? "tool call" : rawLanguage || "code";
	if (!toolish) return {
		code,
		language: highlightLanguage,
		label,
		highlight: true,
		highlighted: highlightedCode(code, highlightLanguage),
		tool: null
	};
	const summary = toolCallSummary(trimmedCode);
	const timestamp = toolCallTimestampMillis(trimmedCode);
	const parts = toolName.split(/\s*·\s*/).filter(Boolean);
	const action = parts.length > 1 ? parts[parts.length - 1] : toolName;
	const connector = parts.length > 1 ? parts.slice(0, -1).join(" · ") : "";
	return {
		code,
		language: highlightLanguage,
		label,
		highlight: Boolean(pythonCode),
		highlighted: pythonCode ? highlightedCode(code, highlightLanguage) : [{
			type: "text",
			value: code
		}],
		tool: {
			name: toolName,
			summary,
			action,
			connector,
			time: timestamp === null ? null : {
				text: formatClockTime12Hour(timestamp, true),
				iso: new Date(timestamp).toISOString()
			},
			hasMeta: Boolean(summary && action)
		}
	};
}
function safeLinkHref(value) {
	const href = String(value || "").trim();
	return /^https?:\/\//i.test(href) ? href : "";
}
//#endregion
//#region src/ui/MarkdownContent.svelte
init_client();
init_index_client$1();
init_browserAttachments_svelte();
var root$5 = /* @__PURE__ */ from_html(`<span><!></span>`);
var root_1$4 = /* @__PURE__ */ from_html(`<strong><!></strong>`);
var root_2$4 = /* @__PURE__ */ from_html(`<em><!></em>`);
var root_3$4 = /* @__PURE__ */ from_html(`<del><!></del>`);
var root_4$4 = /* @__PURE__ */ from_html(`<code class="inline-code"> </code>`);
var root_5$3 = /* @__PURE__ */ from_html(`<br/>`);
var root_6$3 = /* @__PURE__ */ from_html(`<a target="_blank" rel="noreferrer noopener"><!></a>`);
var root_7$3 = /* @__PURE__ */ from_html(`<p><!></p>`);
var root_8$2 = /* @__PURE__ */ from_html(`<h1><!></h1>`);
var root_9$2 = /* @__PURE__ */ from_html(`<h2><!></h2>`);
var root_10$2 = /* @__PURE__ */ from_html(`<h3><!></h3>`);
var root_11 = /* @__PURE__ */ from_html(`<h4><!></h4>`);
var root_12 = /* @__PURE__ */ from_html(`<h5><!></h5>`);
var root_13 = /* @__PURE__ */ from_html(`<h6><!></h6>`);
var root_14 = /* @__PURE__ */ from_html(`<hr/>`);
var root_15 = /* @__PURE__ */ from_html(`<blockquote><!></blockquote>`);
var root_16 = /* @__PURE__ */ from_html(`<input type="checkbox" disabled=""/>`);
var root_17 = /* @__PURE__ */ from_html(`<li><!> <!></li>`);
var root_18 = /* @__PURE__ */ from_html(`<ol></ol>`);
var root_19 = /* @__PURE__ */ from_html(`<ul></ul>`);
var root_20 = /* @__PURE__ */ from_html(`<th><!></th>`);
var root_21 = /* @__PURE__ */ from_html(`<td><!></td>`);
var root_22 = /* @__PURE__ */ from_html(`<tr></tr>`);
var root_23 = /* @__PURE__ */ from_html(`<div><table><thead><tr></tr></thead><tbody></tbody></table></div>`);
var root_24 = /* @__PURE__ */ from_html(`<span class="tool-expanded-separator">|</span> <span class="tool-expanded-connector"> </span>`, 1);
var root_25 = /* @__PURE__ */ from_html(`<span class="tool-inline-meta"><span class="tool-expanded-separator">|</span> <span class="tool-expanded-action"> </span> <!></span>`);
var root_26 = /* @__PURE__ */ from_html(`<span class="tool-summary"> </span> <!>`, 1);
var root_27 = /* @__PURE__ */ from_html(`<span> </span>`);
var root_28 = /* @__PURE__ */ from_html(`<time class="tool-time"> </time>`);
var root_29 = /* @__PURE__ */ from_html(`<div class="tool-expanded-meta"><span class="tool-expanded-action"> </span> <!></div>`);
var root_30 = /* @__PURE__ */ from_html(`<pre><code><!></code></pre>`);
var root_31 = /* @__PURE__ */ from_html(`<details><summary class="code-header"><!> <!></summary> <!> <!></details>`);
var root_32 = /* @__PURE__ */ from_html(`<button type="button" class="copy-code"> </button>`);
var root_33 = /* @__PURE__ */ from_html(`<div class="code-block"><div class="code-header"><span class="code-language"> </span> <!></div> <!></div>`);
var root_34 = /* @__PURE__ */ from_html(`<p> </p>`);
function MarkdownContent($$anchor, $$props) {
	push($$props, true);
	const highlightNodes = ($$anchor, nodes = noop) => {
		var fragment = comment();
		each(first_child(fragment), 17, nodes, index, ($$anchor, node) => {
			var fragment_1 = comment();
			var node_2 = first_child(fragment_1);
			var consequent = ($$anchor) => {
				var text$2 = text();
				template_effect(() => set_text(text$2, get(node).value));
				append($$anchor, text$2);
			};
			var consequent_1 = ($$anchor) => {
				var span = root$5();
				var node_3 = child(span);
				highlightNodes(node_3, () => get(node).children);
				reset(span);
				template_effect(($0) => set_class(span, 1, $0), [() => clsx(elementClasses(get(node)))]);
				append($$anchor, span);
			};
			if_block(node_2, ($$render) => {
				if (get(node).type === "text") $$render(consequent);
				else if (get(node).type === "element") $$render(consequent_1, 1);
			});
			append($$anchor, fragment_1);
		});
		append($$anchor, fragment);
	};
	const inline = ($$anchor, items = noop) => {
		var fragment_3 = comment();
		each(first_child(fragment_3), 19, items, (token, index) => tokenKey(token, index), ($$anchor, token) => {
			var fragment_4 = comment();
			var node_5 = first_child(fragment_4);
			var consequent_3 = ($$anchor) => {
				var fragment_5 = comment();
				var node_6 = first_child(fragment_5);
				var consequent_2 = ($$anchor) => {
					{
						let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
						inline($$anchor, () => get($0));
					}
				};
				var d = /* @__PURE__ */ user_derived(() => childTokens(get(token))?.length);
				var alternate = ($$anchor) => {
					var text_1 = text();
					template_effect(() => set_text(text_1, get(token).text));
					append($$anchor, text_1);
				};
				if_block(node_6, ($$render) => {
					if (get(d)) $$render(consequent_2);
					else $$render(alternate, -1);
				});
				append($$anchor, fragment_5);
			};
			var consequent_4 = ($$anchor) => {
				var text_2 = text();
				template_effect(() => set_text(text_2, get(token).text));
				append($$anchor, text_2);
			};
			var consequent_5 = ($$anchor) => {
				var strong = root_1$4();
				var node_7 = child(strong);
				{
					let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
					inline(node_7, () => get($0));
				}
				reset(strong);
				append($$anchor, strong);
			};
			var consequent_6 = ($$anchor) => {
				var em = root_2$4();
				var node_8 = child(em);
				{
					let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
					inline(node_8, () => get($0));
				}
				reset(em);
				append($$anchor, em);
			};
			var consequent_7 = ($$anchor) => {
				var del = root_3$4();
				var node_9 = child(del);
				{
					let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
					inline(node_9, () => get($0));
				}
				reset(del);
				append($$anchor, del);
			};
			var consequent_8 = ($$anchor) => {
				var code_1 = root_4$4();
				var text_3 = only_child(code_1, true);
				template_effect(() => set_text(text_3, get(token).text));
				append($$anchor, code_1);
			};
			var consequent_9 = ($$anchor) => {
				append($$anchor, root_5$3());
			};
			var consequent_11 = ($$anchor) => {
				var fragment_9 = comment();
				var node_10 = first_child(fragment_9);
				var consequent_10 = ($$anchor) => {
					var a = root_6$3();
					var node_11 = child(a);
					{
						let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
						inline(node_11, () => get($0));
					}
					reset(a);
					template_effect(($0) => set_attribute(a, "href", $0), [() => safeLinkHref(get(token).href)]);
					append($$anchor, a);
				};
				var d_1 = /* @__PURE__ */ user_derived(() => safeLinkHref(get(token).href));
				var alternate_1 = ($$anchor) => {
					{
						let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
						inline($$anchor, () => get($0));
					}
				};
				if_block(node_10, ($$render) => {
					if (get(d_1)) $$render(consequent_10);
					else $$render(alternate_1, -1);
				});
				append($$anchor, fragment_9);
			};
			var consequent_12 = ($$anchor) => {
				var text_4 = text();
				template_effect(() => set_text(text_4, get(token).text));
				append($$anchor, text_4);
			};
			var consequent_13 = ($$anchor) => {
				var text_5 = text();
				template_effect(() => set_text(text_5, get(token).text));
				append($$anchor, text_5);
			};
			if_block(node_5, ($$render) => {
				if (get(token).type === "text") $$render(consequent_3);
				else if (get(token).type === "escape") $$render(consequent_4, 1);
				else if (get(token).type === "strong") $$render(consequent_5, 2);
				else if (get(token).type === "em") $$render(consequent_6, 3);
				else if (get(token).type === "del") $$render(consequent_7, 4);
				else if (get(token).type === "codespan") $$render(consequent_8, 5);
				else if (get(token).type === "br") $$render(consequent_9, 6);
				else if (get(token).type === "link") $$render(consequent_11, 7);
				else if (get(token).type === "image") $$render(consequent_12, 8);
				else if (get(token).type === "html") $$render(consequent_13, 9);
			});
			append($$anchor, fragment_4);
		});
		append($$anchor, fragment_3);
	};
	const blocks = ($$anchor, items = noop) => {
		var fragment_13 = comment();
		each(first_child(fragment_13), 19, items, (token, index) => tokenKey(token, index), ($$anchor, token, index$1) => {
			var fragment_14 = comment();
			var node_13 = first_child(fragment_14);
			var consequent_14 = ($$anchor) => {
				var p = root_7$3();
				var node_14 = child(p);
				{
					let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
					inline(node_14, () => get($0));
				}
				reset(p);
				append($$anchor, p);
			};
			var consequent_20 = ($$anchor) => {
				var fragment_15 = comment();
				var node_15 = first_child(fragment_15);
				var consequent_15 = ($$anchor) => {
					var h1 = root_8$2();
					var node_16 = child(h1);
					{
						let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
						inline(node_16, () => get($0));
					}
					reset(h1);
					append($$anchor, h1);
				};
				var consequent_16 = ($$anchor) => {
					var h2 = root_9$2();
					var node_17 = child(h2);
					{
						let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
						inline(node_17, () => get($0));
					}
					reset(h2);
					append($$anchor, h2);
				};
				var consequent_17 = ($$anchor) => {
					var h3 = root_10$2();
					var node_18 = child(h3);
					{
						let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
						inline(node_18, () => get($0));
					}
					reset(h3);
					append($$anchor, h3);
				};
				var consequent_18 = ($$anchor) => {
					var h4 = root_11();
					var node_19 = child(h4);
					{
						let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
						inline(node_19, () => get($0));
					}
					reset(h4);
					append($$anchor, h4);
				};
				var consequent_19 = ($$anchor) => {
					var h5 = root_12();
					var node_20 = child(h5);
					{
						let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
						inline(node_20, () => get($0));
					}
					reset(h5);
					append($$anchor, h5);
				};
				var alternate_2 = ($$anchor) => {
					var h6 = root_13();
					var node_21 = child(h6);
					{
						let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
						inline(node_21, () => get($0));
					}
					reset(h6);
					append($$anchor, h6);
				};
				if_block(node_15, ($$render) => {
					if (get(token).depth === 1) $$render(consequent_15);
					else if (get(token).depth === 2) $$render(consequent_16, 1);
					else if (get(token).depth === 3) $$render(consequent_17, 2);
					else if (get(token).depth === 4) $$render(consequent_18, 3);
					else if (get(token).depth === 5) $$render(consequent_19, 4);
					else $$render(alternate_2, -1);
				});
				append($$anchor, fragment_15);
			};
			var consequent_21 = ($$anchor) => {
				append($$anchor, root_14());
			};
			var consequent_22 = ($$anchor) => {
				var blockquote = root_15();
				var node_22 = child(blockquote);
				{
					let $0 = /* @__PURE__ */ user_derived(() => childTokens(get(token)));
					blocks(node_22, () => get($0));
				}
				reset(blockquote);
				append($$anchor, blockquote);
			};
			var consequent_26 = ($$anchor) => {
				var fragment_16 = comment();
				var node_23 = first_child(fragment_16);
				var consequent_24 = ($$anchor) => {
					var ol = root_18();
					each(ol, 23, () => get(token).items, (item, itemIndex) => item.raw + ":" + itemIndex, ($$anchor, item) => {
						var li = root_17();
						var node_24 = child(li);
						var consequent_23 = ($$anchor) => {
							var input = root_16();
							remove_input_defaults(input);
							template_effect(($0) => set_checked(input, $0), [() => Boolean(get(item).checked)]);
							append($$anchor, input);
						};
						if_block(node_24, ($$render) => {
							if (get(item).task) $$render(consequent_23);
						});
						var node_25 = sibling(node_24, 2);
						blocks(node_25, () => get(item).tokens);
						reset(li);
						template_effect(() => set_class(li, 1, clsx({ "task-item": get(item).task })));
						append($$anchor, li);
					});
					reset(ol);
					template_effect(() => set_attribute(ol, "start", typeof get(token).start === "number" ? get(token).start : void 0));
					append($$anchor, ol);
				};
				var alternate_3 = ($$anchor) => {
					var ul = root_19();
					each(ul, 23, () => get(token).items, (item, itemIndex) => item.raw + ":" + itemIndex, ($$anchor, item) => {
						var li_1 = root_17();
						var node_26 = child(li_1);
						var consequent_25 = ($$anchor) => {
							var input_1 = root_16();
							remove_input_defaults(input_1);
							template_effect(($0) => set_checked(input_1, $0), [() => Boolean(get(item).checked)]);
							append($$anchor, input_1);
						};
						if_block(node_26, ($$render) => {
							if (get(item).task) $$render(consequent_25);
						});
						var node_27 = sibling(node_26, 2);
						blocks(node_27, () => get(item).tokens);
						reset(li_1);
						template_effect(() => set_class(li_1, 1, clsx({ "task-item": get(item).task })));
						append($$anchor, li_1);
					});
					reset(ul);
					append($$anchor, ul);
				};
				if_block(node_23, ($$render) => {
					if (get(token).ordered) $$render(consequent_24);
					else $$render(alternate_3, -1);
				});
				append($$anchor, fragment_16);
			};
			var consequent_27 = ($$anchor) => {
				var div = root_23();
				var table = child(div);
				var thead = child(table);
				var tr = child(thead);
				each(tr, 21, () => get(token).header, index, ($$anchor, cell) => {
					var th = root_20();
					let styles;
					var node_28 = child(th);
					inline(node_28, () => get(cell).tokens);
					reset(th);
					template_effect(() => styles = set_style(th, "", styles, { "text-align": get(cell).align ?? void 0 }));
					append($$anchor, th);
				});
				reset(tr);
				reset(thead);
				var tbody = sibling(thead);
				each(tbody, 21, () => get(token).rows, index, ($$anchor, row) => {
					var tr_1 = root_22();
					each(tr_1, 21, () => get(row), index, ($$anchor, cell) => {
						var td = root_21();
						let styles_1;
						var node_29 = child(td);
						inline(node_29, () => get(cell).tokens);
						reset(td);
						template_effect(() => styles_1 = set_style(td, "", styles_1, { "text-align": get(cell).align ?? void 0 }));
						append($$anchor, td);
					});
					reset(tr_1);
					append($$anchor, tr_1);
				});
				reset(tbody);
				reset(table);
				reset(div);
				template_effect(() => set_class(div, 1, clsx(["table-scroll", { "table-scroll-wide": get(token).header.length >= 3 }])));
				append($$anchor, div);
			};
			var consequent_39 = ($$anchor) => {
				const presentation = codePresentation(get(token));
				const key = tokenKey(get(token), get(index$1));
				var fragment_17 = comment();
				var node_30 = first_child(fragment_17);
				var consequent_38 = ($$anchor) => {
					var fragment_18 = comment();
					var node_31 = first_child(fragment_18);
					var consequent_35 = ($$anchor) => {
						var details = root_31();
						var summary = child(details);
						var node_32 = child(summary);
						var consequent_30 = ($$anchor) => {
							var fragment_19 = root_26();
							var span_1 = first_child(fragment_19);
							var text_6 = only_child(span_1, true);
							var node_33 = sibling(span_1, 2);
							var consequent_29 = ($$anchor) => {
								var span_2 = root_25();
								var span_3 = sibling(child(span_2), 2);
								var text_7 = only_child(span_3, true);
								var node_34 = sibling(span_3, 2);
								var consequent_28 = ($$anchor) => {
									var fragment_20 = root_24();
									var text_8 = only_child(sibling(first_child(fragment_20), 2), true);
									template_effect(() => set_text(text_8, presentation.tool.connector));
									append($$anchor, fragment_20);
								};
								if_block(node_34, ($$render) => {
									if (presentation.tool.connector) $$render(consequent_28);
								});
								reset(span_2);
								template_effect(() => set_text(text_7, presentation.tool.action));
								append($$anchor, span_2);
							};
							if_block(node_33, ($$render) => {
								if (presentation.tool.action) $$render(consequent_29);
							});
							template_effect(() => set_text(text_6, presentation.tool.summary));
							append($$anchor, fragment_19);
						};
						var alternate_4 = ($$anchor) => {
							var span_5 = root_27();
							var text_9 = only_child(span_5, true);
							template_effect(() => {
								set_class(span_5, 1, clsx(presentation.tool.name ? "tool-primary-name" : "code-language"));
								set_text(text_9, presentation.tool.name || presentation.label);
							});
							append($$anchor, span_5);
						};
						if_block(node_32, ($$render) => {
							if (presentation.tool.summary) $$render(consequent_30);
							else $$render(alternate_4, -1);
						});
						var node_35 = sibling(node_32, 2);
						var consequent_31 = ($$anchor) => {
							var time = root_28();
							var text_10 = only_child(time, true);
							template_effect(() => {
								set_attribute(time, "datetime", presentation.tool.time.iso);
								set_text(text_10, presentation.tool.time.text);
							});
							append($$anchor, time);
						};
						if_block(node_35, ($$render) => {
							if (presentation.tool.time) $$render(consequent_31);
						});
						reset(summary);
						var node_36 = sibling(summary, 2);
						var consequent_33 = ($$anchor) => {
							var div_1 = root_29();
							var span_6 = child(div_1);
							var text_11 = only_child(span_6, true);
							var node_37 = sibling(span_6, 2);
							var consequent_32 = ($$anchor) => {
								var fragment_21 = root_24();
								var text_12 = only_child(sibling(first_child(fragment_21), 2), true);
								template_effect(() => set_text(text_12, presentation.tool.connector));
								append($$anchor, fragment_21);
							};
							if_block(node_37, ($$render) => {
								if (presentation.tool.connector) $$render(consequent_32);
							});
							reset(div_1);
							template_effect(() => set_text(text_11, presentation.tool.action));
							append($$anchor, div_1);
						};
						if_block(node_36, ($$render) => {
							if (presentation.tool.hasMeta) $$render(consequent_33);
						});
						var node_38 = sibling(node_36, 2);
						var consequent_34 = ($$anchor) => {
							var pre = root_30();
							var code_2 = child(pre);
							var node_39 = child(code_2);
							{
								let $0 = /* @__PURE__ */ user_derived(() => presentation.highlight ? presentation.highlighted : highlightedCode(presentation.code, presentation.language));
								highlightNodes(node_39, () => get($0));
							}
							reset(code_2);
							reset(pre);
							template_effect(() => set_class(code_2, 1, "language-" + presentation.language));
							append($$anchor, pre);
						};
						var d_2 = /* @__PURE__ */ user_derived(() => presentation.code && get(expandedTools).has(key));
						if_block(node_38, ($$render) => {
							if (get(d_2)) $$render(consequent_34);
						});
						reset(details);
						template_effect(($0) => set_class(details, 1, $0), [() => clsx([
							"code-block",
							"tool-call-block",
							{
								"tool-has-summary": Boolean(presentation.tool.summary),
								"tool-has-meta": presentation.tool.hasMeta
							}
						])]);
						event("toggle", details, (event) => setToolOpen(key, event.currentTarget.open));
						append($$anchor, details);
					};
					var alternate_5 = ($$anchor) => {
						var div_2 = root_33();
						var div_3 = child(div_2);
						var span_8 = child(div_3);
						var text_13 = only_child(span_8, true);
						var node_40 = sibling(span_8, 2);
						var consequent_36 = ($$anchor) => {
							var button = root_32();
							var text_14 = only_child(button, true);
							template_effect(() => set_text(text_14, get(copiedKey) === key ? "copied" : "copy"));
							delegated("click", button, () => void copyCode(key, presentation.code));
							append($$anchor, button);
						};
						if_block(node_40, ($$render) => {
							if (presentation.code) $$render(consequent_36);
						});
						reset(div_3);
						var node_41 = sibling(div_3, 2);
						var consequent_37 = ($$anchor) => {
							var pre_1 = root_30();
							var code_3 = child(pre_1);
							var node_42 = child(code_3);
							highlightNodes(node_42, () => presentation.highlighted);
							reset(code_3);
							reset(pre_1);
							template_effect(() => set_class(code_3, 1, "language-" + presentation.language));
							append($$anchor, pre_1);
						};
						if_block(node_41, ($$render) => {
							if (presentation.code) $$render(consequent_37);
						});
						reset(div_2);
						template_effect(() => set_text(text_13, presentation.label));
						append($$anchor, div_2);
					};
					if_block(node_31, ($$render) => {
						if (presentation.tool) $$render(consequent_35);
						else $$render(alternate_5, -1);
					});
					append($$anchor, fragment_18);
				};
				if_block(node_30, ($$render) => {
					if (presentation) $$render(consequent_38);
				});
				append($$anchor, fragment_17);
			};
			var consequent_40 = ($$anchor) => {
				var p_1 = root_34();
				var text_15 = only_child(p_1, true);
				template_effect(() => set_text(text_15, get(token).text));
				append($$anchor, p_1);
			};
			var consequent_41 = ($$anchor) => {
				var p_2 = root_7$3();
				var node_43 = child(p_2);
				inline(node_43, () => [get(token)]);
				reset(p_2);
				append($$anchor, p_2);
			};
			if_block(node_13, ($$render) => {
				if (get(token).type === "paragraph") $$render(consequent_14);
				else if (get(token).type === "heading") $$render(consequent_20, 1);
				else if (get(token).type === "hr") $$render(consequent_21, 2);
				else if (get(token).type === "blockquote") $$render(consequent_22, 3);
				else if (get(token).type === "list") $$render(consequent_26, 4);
				else if (get(token).type === "table") $$render(consequent_27, 5);
				else if (get(token).type === "code") $$render(consequent_39, 6);
				else if (get(token).type === "html") $$render(consequent_40, 7);
				else if (get(token).type === "text") $$render(consequent_41, 8);
			});
			append($$anchor, fragment_14);
		});
		append($$anchor, fragment_13);
	};
	let streaming = prop($$props, "streaming", 3, false);
	let copiedKey = /* @__PURE__ */ state$1("");
	let expandedTools = /* @__PURE__ */ state$1(/* @__PURE__ */ new Set());
	const tokens = /* @__PURE__ */ user_derived(() => parseMarkdown($$props.source, { renderIncompleteFence: streaming() }));
	function tokenKey(token, index) {
		return token.type + ":" + index + ":" + token.raw.slice(0, 80);
	}
	function childTokens(token) {
		return "tokens" in token && Array.isArray(token.tokens) ? token.tokens : [];
	}
	function elementClasses(node) {
		const value = node.properties.className;
		return Array.isArray(value) ? value.map(String) : typeof value === "string" ? value : "";
	}
	async function setToolOpen(key, open) {
		const restoreViewport = preserveConversationViewportPosition();
		const next = new Set(get(expandedTools));
		if (open) next.add(key);
		else next.delete(key);
		set(expandedTools, next);
		await tick();
		restoreViewport();
	}
	async function copyCode(key, code) {
		set(copiedKey, await copyText(code) ? key : "", true);
		if (get(copiedKey)) setTimeout(() => {
			if (get(copiedKey) === key) set(copiedKey, "");
		}, 1e3);
	}
	blocks($$anchor, () => get(tokens));
	pop();
}
delegate(["click"]);
//#endregion
//#region src/ui/conversationState.svelte.ts
var ConversationState, conversationState;
var init_conversationState_svelte = __esmMin((() => {
	init_client();
	ConversationState = class {
		#messages = /* @__PURE__ */ state$1([]);
		get messages() {
			return get(this.#messages);
		}
		set messages(value) {
			set(this.#messages, value);
		}
		#allowStreaming = /* @__PURE__ */ state$1(false);
		get allowStreaming() {
			return get(this.#allowStreaming);
		}
		set allowStreaming(value) {
			set(this.#allowStreaming, value, true);
		}
		#loading = /* @__PURE__ */ state$1(false);
		get loading() {
			return get(this.#loading);
		}
		set loading(value) {
			set(this.#loading, value, true);
		}
		#deletingKeys = /* @__PURE__ */ state$1(/* @__PURE__ */ new Set());
		get deletingKeys() {
			return get(this.#deletingKeys);
		}
		set deletingKeys(value) {
			set(this.#deletingKeys, value);
		}
		onRetry = () => {};
		onBump = () => {};
		onDelete = () => {};
		onEdit = () => {};
	};
	conversationState = new ConversationState();
}));
//#endregion
//#region src/ui/conversationLogic.ts
function imageAttachments(message) {
	return (Array.isArray(message?.attachments) ? message.attachments : []).filter((attachment) => attachment && typeof attachment === "object" && String(attachment.type || "").startsWith("image/") && (Boolean(attachment.id) || String(attachment.src || "").startsWith("data:image/")));
}
function pendingImageAttachments(serializedAttachments) {
	return serializedAttachments.filter((attachment) => attachment.type.startsWith("image/")).map((attachment) => ({
		name: attachment.name,
		type: attachment.type,
		src: "data:" + attachment.type + ";base64," + attachment.data
	}));
}
function shouldHandlePendingLongPress(pointerType, coarsePointer) {
	return pointerType !== "mouse" || coarsePointer;
}
function pendingLongPressMoved(startX, startY, currentX, currentY, tolerance = 8) {
	return Math.max(Math.abs(currentX - startX), Math.abs(currentY - startY)) > tolerance;
}
function messageDisplayContent(message) {
	const fallback = String(message?.content || "");
	if (message?.role !== "assistant" || message?.parts_renderable !== true) return fallback;
	if (!Array.isArray(message.parts)) return fallback;
	const ordered = message.parts.map((part, index) => ({
		content: String(part?.content || "").trim(),
		index,
		ordinal: Number.isFinite(Number(part?.ordinal)) ? Number(part.ordinal) : index
	})).filter((part) => Boolean(part.content)).sort((left, right) => left.ordinal - right.ordinal || left.index - right.index);
	if (!ordered.length) return fallback;
	return ordered.map((part) => part.content).join("\n\n").trim() || fallback;
}
var init_conversationLogic = __esmMin((() => {}));
//#endregion
//#region src/ui/ConversationMessages.svelte
init_client();
init_index_client();
init_appViewState_svelte();
init_browserAttachments_svelte();
init_clientLogic();
init_conversationState_svelte();
init_conversationLogic();
var root$4 = /* @__PURE__ */ from_html(`<div class="conversation-loading" data-message-key="__loading__" aria-live="polite" aria-label="Loading conversation"><div class="conversation-loading-row conversation-loading-user"></div> <div class="conversation-loading-row conversation-loading-assistant"></div> <div class="conversation-loading-row conversation-loading-assistant short"></div></div>`);
var root_1$3 = /* @__PURE__ */ from_html(`<div class="message-label"><span class="assistant-avatar"> </span> </div>`);
var root_2$3 = /* @__PURE__ */ from_html(`<div class="message-attachments"><img class="message-image-preview" loading="lazy" decoding="async"/></div>`);
var root_3$3 = /* @__PURE__ */ from_html(`<button type="button" class="retry-send-button">Retry</button>`);
var root_4$3 = /* @__PURE__ */ from_html(`<button type="button" class="pending-message-button bump-pending-button" aria-label="Send queued message next" title="Send queued message next"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 19V5m-6 6 6-6 6 6"></path></svg></button>`);
var root_5$2 = /* @__PURE__ */ from_html(`<div class="pending-message-controls" aria-label="Queued message actions"><button type="button" class="pending-message-button edit-pending-button" aria-label="Edit queued message" title="Edit queued message"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m4 20 4.2-1 10.9-10.9a2.1 2.1 0 0 0-3-3L5.2 16 4 20Zm10.6-13.4 3 3"></path></svg></button> <!> <button type="button" class="pending-message-button delete-pending-button" aria-label="Delete queued message" title="Delete queued message"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5"></path></svg></button></div>`);
var root_6$2 = /* @__PURE__ */ from_html(`<div class="streaming-indicator"><span class="streaming-dots"><i></i><i></i><i></i></span> </div>`);
var root_7$2 = /* @__PURE__ */ from_html(`<span class="message-age"> </span>`);
var root_8$1 = /* @__PURE__ */ from_html(`<section role="presentation"><div class="message-inner"><!> <!> <div class="message-content"><!></div> <!> <!> <!> <time class="message-timestamp"><span class="message-clock"> </span> <!></time></div></section>`);
var root_9$1 = /* @__PURE__ */ from_html(`<button type="button" class="pending-message-action">Send next</button>`);
var root_10$1 = /* @__PURE__ */ from_html(`<div role="presentation"><!> <!></div> <dialog class="pending-message-actions" aria-labelledby="pendingMessageActionsTitle"><div class="pending-message-actions-shell"><div id="pendingMessageActionsTitle" class="pending-message-actions-title">Pending message</div> <!> <button type="button" class="pending-message-action">Edit message</button> <button type="button" class="pending-message-action danger">Delete message</button> <button type="button" class="pending-message-action cancel">Cancel</button></div></dialog>`, 1);
function ConversationMessages($$anchor, $$props) {
	push($$props, true);
	const coarsePointer = new MediaQuery("(pointer: coarse)");
	let actionsKey = /* @__PURE__ */ state$1("");
	let actionsCanBump = /* @__PURE__ */ state$1(false);
	let actionsOpen = /* @__PURE__ */ state$1(false);
	let pendingLongPressTimer;
	let pendingLongPressPointerId = null;
	let pendingLongPressStartX = 0;
	let pendingLongPressStartY = 0;
	function timestamp(message, _clockTick) {
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
	function key(message, index) {
		return String(message.message_key || `${message.role || "message"}:${index}`);
	}
	function streaming(message) {
		return Boolean(message.pending_activity) || conversationState.allowStreaming && message.status === "streaming";
	}
	function images(message) {
		return Array.isArray(message.attachments) ? message.attachments.filter((item) => item && String(item.type || "").startsWith("image/")) : [];
	}
	function imageSrc(item) {
		return String(item.src || "").startsWith("data:image/") ? item.src : item.id ? `api/attachment-previews/${encodeURIComponent(item.id)}` : "";
	}
	function clearPendingLongPress() {
		if (pendingLongPressTimer !== void 0) {
			clearTimeout(pendingLongPressTimer);
			pendingLongPressTimer = void 0;
		}
		pendingLongPressPointerId = null;
	}
	function startPendingLongPress(event, message) {
		if (!message.pending_delete_key || !shouldHandlePendingLongPress(event.pointerType, coarsePointer.current)) return;
		clearPendingLongPress();
		pendingLongPressPointerId = event.pointerId;
		pendingLongPressStartX = event.clientX;
		pendingLongPressStartY = event.clientY;
		pendingLongPressTimer = setTimeout(() => {
			pendingLongPressTimer = void 0;
			pendingLongPressPointerId = null;
			openActions(message);
		}, 480);
	}
	function movePendingLongPress(event) {
		if (event.pointerId !== pendingLongPressPointerId) return;
		if (pendingLongPressMoved(pendingLongPressStartX, pendingLongPressStartY, event.clientX, event.clientY)) clearPendingLongPress();
	}
	function endPendingLongPress(event) {
		if (event.pointerId === pendingLongPressPointerId) clearPendingLongPress();
	}
	function openActions(message) {
		if (!message.pending_delete_key) return;
		clearPendingLongPress();
		set(actionsKey, String(message.pending_delete_key), true);
		set(actionsCanBump, Boolean(message.pending_bump_key), true);
		set(actionsOpen, true);
	}
	function closeActions() {
		set(actionsOpen, false);
	}
	function bumpPending() {
		closeActions();
		conversationState.onBump(get(actionsKey));
	}
	function editPending() {
		closeActions();
		conversationState.onEdit(get(actionsKey));
	}
	function deletePending() {
		closeActions();
		conversationState.onDelete(get(actionsKey));
	}
	var fragment = root_10$1();
	event("keydown", $window, (event) => {
		if (event.key === "Escape" && get(actionsOpen)) closeActions();
	});
	var div = first_child(fragment);
	var node = child(div);
	var consequent = ($$anchor) => {
		append($$anchor, root$4());
	};
	if_block(node, ($$render) => {
		if (conversationState.loading) $$render(consequent);
	});
	each(sibling(node, 2), 19, () => conversationState.messages, (message, index) => key(message, index), ($$anchor, message, index) => {
		const value = timestamp(get(message), appViewState.clockTick);
		const deleting = conversationState.deletingKeys.has(String(get(message).pending_delete_key || ""));
		const role = get(message).role === "user" ? "user" : "assistant";
		var section = root_8$1();
		var div_2 = child(section);
		var node_2 = child(div_2);
		var consequent_1 = ($$anchor) => {
			var div_3 = root_1$3();
			var span = child(div_3);
			var text = only_child(span, true);
			var text_1 = sibling(span);
			reset(div_3);
			template_effect(() => {
				set_text(text, get(message).send_error ? "!" : "P");
				set_text(text_1, ` ${get(message).send_error ? "Send error" : "Prompta run"}`);
			});
			append($$anchor, div_3);
		};
		if_block(node_2, ($$render) => {
			if (role === "assistant") $$render(consequent_1);
		});
		var node_3 = sibling(node_2, 2);
		var consequent_2 = ($$anchor) => {
			var fragment_1 = comment();
			each(first_child(fragment_1), 17, () => images(get(message)), (image) => image.id || image.src || image.name, ($$anchor, image) => {
				var div_4 = root_2$3();
				var img = only_child(div_4);
				template_effect(($0) => {
					set_attribute(img, "src", $0);
					set_attribute(img, "alt", get(image).name || "Attached image");
				}, [() => imageSrc(get(image))]);
				append($$anchor, div_4);
			});
			append($$anchor, fragment_1);
		};
		if_block(node_3, ($$render) => {
			if (!get(message).pending_activity) $$render(consequent_2);
		});
		var div_5 = sibling(node_3, 2);
		var node_5 = child(div_5);
		var consequent_3 = ($$anchor) => {
			{
				let $0 = /* @__PURE__ */ user_derived(() => messageDisplayContent(get(message)));
				let $1 = /* @__PURE__ */ user_derived(() => streaming(get(message)));
				MarkdownContent($$anchor, {
					get source() {
						return get($0);
					},
					get streaming() {
						return get($1);
					}
				});
			}
		};
		if_block(node_5, ($$render) => {
			if (!get(message).pending_activity) $$render(consequent_3);
		});
		reset(div_5);
		var node_6 = sibling(div_5, 2);
		var consequent_4 = ($$anchor) => {
			var button = root_3$3();
			delegated("click", button, () => conversationState.onRetry(String(get(message).retry_scope), String(get(message).retry_key)));
			append($$anchor, button);
		};
		if_block(node_6, ($$render) => {
			if (get(message).send_error && get(message).retry_scope && get(message).retry_key) $$render(consequent_4);
		});
		var node_7 = sibling(node_6, 2);
		var consequent_6 = ($$anchor) => {
			var div_6 = root_5$2();
			var button_1 = child(div_6);
			var node_8 = sibling(button_1, 2);
			var consequent_5 = ($$anchor) => {
				var button_2 = root_4$3();
				template_effect(() => button_2.disabled = deleting);
				delegated("click", button_2, () => conversationState.onBump(String(get(message).pending_bump_key)));
				append($$anchor, button_2);
			};
			if_block(node_8, ($$render) => {
				if (get(message).pending_bump_key) $$render(consequent_5);
			});
			var button_3 = sibling(node_8, 2);
			reset(div_6);
			template_effect(() => {
				button_1.disabled = deleting;
				button_3.disabled = deleting;
				set_attribute(button_3, "aria-busy", deleting ? "true" : void 0);
			});
			delegated("click", button_1, () => conversationState.onEdit(String(get(message).pending_delete_key)));
			delegated("click", button_3, () => conversationState.onDelete(String(get(message).pending_delete_key)));
			append($$anchor, div_6);
		};
		if_block(node_7, ($$render) => {
			if (get(message).pending_delete_key) $$render(consequent_6);
		});
		var node_9 = sibling(node_7, 2);
		var consequent_7 = ($$anchor) => {
			var div_7 = root_6$2();
			var text_2 = sibling(child(div_7));
			reset(div_7);
			template_effect(() => set_text(text_2, ` ${(get(message).pending_activity_label || "writing") ?? ""}`));
			append($$anchor, div_7);
		};
		var d = /* @__PURE__ */ user_derived(() => streaming(get(message)));
		if_block(node_9, ($$render) => {
			if (get(d)) $$render(consequent_7);
		});
		var time = sibling(node_9, 2);
		var span_1 = child(time);
		var text_3 = only_child(span_1, true);
		var node_10 = sibling(span_1, 2);
		var consequent_8 = ($$anchor) => {
			var span_2 = root_7$2();
			var text_4 = only_child(span_2);
			template_effect(() => set_text(text_4, `· ${value.age ?? ""}`));
			append($$anchor, span_2);
		};
		if_block(node_10, ($$render) => {
			if (value.age) $$render(consequent_8);
		});
		reset(time);
		reset(div_2);
		reset(section);
		template_effect(($0, $1) => {
			set_class(section, 1, $0);
			set_attribute(section, "data-message-key", $1);
			set_attribute(time, "datetime", value.iso);
			set_attribute(time, "data-message-at", value.millis ?? void 0);
			set_text(text_3, value.text);
		}, [() => clsx([
			"message",
			role,
			{
				"send-error": Boolean(get(message).send_error),
				"pending-activity": Boolean(get(message).pending_activity),
				"pending-message-action-target": Boolean(get(message).pending_delete_key),
				"pending-message-bumpable": Boolean(get(message).pending_bump_key),
				"pending-message-deleting": deleting
			}
		]), () => key(get(message), get(index))]);
		delegated("pointerdown", section, (event) => startPendingLongPress(event, get(message)));
		delegated("pointermove", section, movePendingLongPress);
		delegated("pointerup", section, endPendingLongPress);
		event("pointercancel", section, endPendingLongPress);
		delegated("contextmenu", section, (event) => {
			if (get(message).pending_delete_key && coarsePointer.current) {
				event.preventDefault();
				openActions(get(message));
			}
		});
		append($$anchor, section);
	});
	reset(div);
	var dialog = sibling(div, 2);
	var div_8 = child(dialog);
	var node_11 = sibling(child(div_8), 2);
	var consequent_9 = ($$anchor) => {
		var button_4 = root_9$1();
		delegated("click", button_4, bumpPending);
		append($$anchor, button_4);
	};
	if_block(node_11, ($$render) => {
		if (get(actionsCanBump)) $$render(consequent_9);
	});
	var button_5 = sibling(node_11, 2);
	var button_6 = sibling(button_5, 2);
	var button_7 = sibling(button_6, 2);
	reset(div_8);
	reset(dialog);
	attach(dialog, () => dialogVisibility(() => get(actionsOpen), () => true, closeActions));
	delegated("click", dialog, (event) => {
		if (event.target === event.currentTarget) closeActions();
	});
	delegated("click", button_5, editPending);
	delegated("click", button_6, deletePending);
	delegated("click", button_7, closeActions);
	append($$anchor, fragment);
	pop();
}
delegate([
	"pointerdown",
	"pointermove",
	"pointerup",
	"contextmenu",
	"click"
]);
function jobPromptIsExpandable(promptValue) {
	const prompt = typeof promptValue === "string" ? promptValue.trim() : "";
	return prompt.length > 220 || prompt.includes("\n");
}
function paginateJobs(jobs, requestedPage, pageSize = 10) {
	const normalizedPageSize = Math.max(1, Math.floor(pageSize));
	const pageCount = Math.max(1, Math.ceil(jobs.length / normalizedPageSize));
	const page = Math.min(pageCount, Math.max(1, Math.floor(requestedPage)));
	const start = (page - 1) * normalizedPageSize;
	return {
		items: jobs.slice(start, start + normalizedPageSize),
		page,
		pageCount
	};
}
//#endregion
//#region src/ui/JobsDialog.svelte
init_client();
init_index_client();
init_browserAttachments_svelte();
init_clientLogic();
init_uiControllers();
var root$3 = /* @__PURE__ */ from_html(`<div class="jobs-empty">No scheduled jobs.</div>`);
var root_1$2 = /* @__PURE__ */ from_html(`· rev <span> </span>`, 1);
var root_2$2 = /* @__PURE__ */ from_html(`<details class="job-prompt-details"><summary class="job-prompt-summary"><span class="job-prompt-preview" aria-hidden="true"> </span> <span class="job-prompt-toggle-label"><span class="job-prompt-show">Show full prompt</span> <span class="job-prompt-hide">Hide prompt</span></span></summary> <div class="job-row-prompt job-row-prompt-full"> </div></details>`);
var root_3$2 = /* @__PURE__ */ from_html(`<div class="job-row-prompt"> </div>`);
var root_4$2 = /* @__PURE__ */ from_html(`<button type="button" class="job-action">Edit</button>`);
var root_5$1 = /* @__PURE__ */ from_html(`<article class="job-row"><div class="job-row-top"><div><div class="job-row-name"> </div> <div class="job-row-meta"> <!></div></div> <span class="job-status"> </span></div> <!> <div class="job-row-actions"><!> <button type="button" class="job-action"> </button> <button type="button" class="job-action">Remove</button></div></article>`);
var root_6$1 = /* @__PURE__ */ from_html(`<nav class="jobs-pagination" aria-label="Scheduled jobs pages"><button type="button" class="jobs-secondary-button">Previous</button> <span class="jobs-pagination-status" aria-live="polite"> </span> <button type="button" class="jobs-secondary-button">Next</button></nav>`);
var root_7$1 = /* @__PURE__ */ from_html(`<label><span>Every (minutes)</span> <input type="number" min="0.1" step="0.1"/></label>`);
var root_8 = /* @__PURE__ */ from_html(`<label><span>At</span> <input type="time"/></label>`);
var root_9 = /* @__PURE__ */ from_html(`<label class="jobs-check"><input type="checkbox"/> <span>Exact interval</span></label>`);
var root_10 = /* @__PURE__ */ from_html(`<dialog class="jobs-dialog" id="jobsDialog" aria-labelledby="jobsDialogTitle"><div class="jobs-dialog-shell"><header class="jobs-dialog-header"><div class="chat-heading"><div class="heading-title" id="jobsDialogTitle">Scheduled jobs</div> <div class="heading-meta">Create and manage scheduled prompts.</div></div> <button type="button" class="jobs-icon-button" aria-label="Close scheduled jobs">×</button></header> <div class="jobs-dialog-status" role="status"> </div> <div class="jobs-list"><!> <!></div> <!> <form class="jobs-form"><h3> </h3> <label><span>Name</span> <input autocomplete="off" required=""/></label> <label><span>Prompt</span> <textarea rows="3" required=""></textarea></label> <div class="jobs-form-grid"><label><span>Schedule</span> <select><option>Interval</option><option>Daily</option></select></label> <!></div> <!> <div class="jobs-form-actions"><button type="button" class="jobs-secondary-button">Reset</button> <button type="submit" class="jobs-primary-button">Save job</button></div></form> <div class="jobs-dialog-footer"><button type="button" class="jobs-danger-button">Clear all jobs</button></div></div></dialog>`);
function JobsDialog($$anchor, $$props) {
	push($$props, true);
	const mobile = new MediaQuery("(max-width: 600px)");
	let dialogOpen = /* @__PURE__ */ state$1(false);
	let presentation = /* @__PURE__ */ state$1("modal");
	let jobs = /* @__PURE__ */ state$1([]);
	let page = /* @__PURE__ */ state$1(1);
	let status = /* @__PURE__ */ state$1("");
	let saving = /* @__PURE__ */ state$1(false);
	let editing = /* @__PURE__ */ state$1("");
	let name = /* @__PURE__ */ state$1("");
	let prompt = /* @__PURE__ */ state$1("");
	let schedule = /* @__PURE__ */ state$1("interval");
	let interval = /* @__PURE__ */ state$1("40");
	let dailyAt = /* @__PURE__ */ state$1("09:00");
	let exact = /* @__PURE__ */ state$1(false);
	const pagination = /* @__PURE__ */ user_derived(() => paginateJobs(get(jobs), get(page)));
	function reset$1() {
		set(editing, "");
		set(name, "");
		set(prompt, "");
		set(schedule, "interval");
		set(interval, "40");
		set(dailyAt, "09:00");
		set(exact, false);
	}
	function scheduleText(job) {
		if (job.run_at_epoch) {
			const date = /* @__PURE__ */ new Date(job.run_at_epoch * 1e3);
			return `once · ${date.toLocaleDateString([], {
				year: "numeric",
				month: "short",
				day: "numeric"
			})} ${formatClockTime12Hour(date)}`;
		}
		if (job.daily_at) return `daily · ${formatDailyTime12Hour(job.daily_at)}`;
		const minutes = Number(job.interval_minutes);
		return `every ${minutes >= 60 && minutes % 60 === 0 ? `${minutes / 60} hour${minutes === 60 ? "" : "s"}` : `${minutes} minute${minutes === 1 ? "" : "s"}`}${job.exact_interval ? " · exact" : ""}`;
	}
	async function load() {
		set(status, "Loading jobs…");
		try {
			const response = await fetch("api/jobs", { cache: "no-store" });
			if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
			const result = await response.json();
			set(jobs, Array.isArray(result.jobs) ? result.jobs : []);
			set(page, 1);
			set(status, `${get(jobs).length} configured job${get(jobs).length === 1 ? "" : "s"}.`);
		} catch (error) {
			set(status, `Could not load jobs: ${String(error).replace(/^Error:\s*/, "")}`);
		}
	}
	async function command(payload, success) {
		set(status, "Running Prompta CLI command…");
		set(saving, true);
		try {
			const result = await postJsonRequest("api/jobs", payload);
			set(jobs, Array.isArray(result.jobs) ? result.jobs : []);
			set(page, paginateJobs(get(jobs), get(page)).page, true);
			const invoked = Array.isArray(result.command) ? result.command.join(" ") : "";
			set(status, invoked ? `${success} · ${invoked}` : success, true);
			return true;
		} catch (error) {
			set(status, `Jobs command failed: ${String(error).replace(/^Error:\s*/, "")}`);
			return false;
		} finally {
			set(saving, false);
		}
	}
	async function submit() {
		const daily = get(schedule) === "daily";
		if (await command({
			action: "add",
			name: get(name).trim(),
			prompt: get(prompt).trim(),
			daily_at: daily ? get(dailyAt) : "",
			interval_minutes: daily ? null : Number(get(interval)),
			exact_interval: !daily && get(exact)
		}, `Saved ${get(name).trim()}`)) reset$1();
	}
	function edit(job) {
		set(editing, job.name, true);
		set(name, job.name, true);
		set(prompt, job.prompt || "", true);
		set(schedule, job.daily_at ? "daily" : "interval", true);
		set(dailyAt, job.daily_at || "09:00", true);
		set(interval, String(job.interval_minutes || 40), true);
		set(exact, Boolean(job.exact_interval), true);
	}
	async function show() {
		reset$1();
		set(presentation, mobile.current ? "stack" : "modal", true);
		set(dialogOpen, true);
		await load();
	}
	function close() {
		set(dialogOpen, false);
	}
	registerJobsDialog({
		open: show,
		close
	});
	var $$exports = {
		show,
		close
	};
	var dialog = root_10();
	var div = child(dialog);
	var header = child(div);
	var button = sibling(child(header), 2);
	reset(header);
	var div_1 = sibling(header, 2);
	var text = only_child(div_1, true);
	var div_2 = sibling(div_1, 2);
	var node = child(div_2);
	var consequent = ($$anchor) => {
		append($$anchor, root$3());
	};
	if_block(node, ($$render) => {
		if (!get(jobs).length) $$render(consequent);
	});
	each(sibling(node, 2), 17, () => get(pagination).items, (job) => job.name, ($$anchor, job) => {
		var article = root_5$1();
		var div_4 = child(article);
		var div_5 = child(div_4);
		var div_6 = child(div_5);
		var text_1 = only_child(div_6, true);
		var div_7 = sibling(div_6, 2);
		var text_2 = child(div_7);
		var node_2 = sibling(text_2);
		var consequent_1 = ($$anchor) => {
			var fragment = root_1$2();
			var span = sibling(first_child(fragment));
			var text_3 = only_child(span, true);
			template_effect(($0) => {
				set_attribute(span, "title", get(job).source_revision);
				set_text(text_3, $0);
			}, [() => get(job).source_revision.slice(0, 8)]);
			append($$anchor, fragment);
		};
		if_block(node_2, ($$render) => {
			if (get(job).source_revision) $$render(consequent_1);
		});
		reset(div_7);
		reset(div_5);
		var text_4 = only_child(sibling(div_5, 2), true);
		reset(div_4);
		var node_3 = sibling(div_4, 2);
		var consequent_2 = ($$anchor) => {
			var details = root_2$2();
			var summary = child(details);
			var text_5 = only_child(child(summary), true);
			next(2);
			reset(summary);
			var text_6 = only_child(sibling(summary, 2), true);
			reset(details);
			template_effect(() => {
				set_text(text_5, get(job).prompt || "");
				set_text(text_6, get(job).prompt || "");
			});
			append($$anchor, details);
		};
		var d = /* @__PURE__ */ user_derived(() => jobPromptIsExpandable(get(job).prompt));
		var alternate = ($$anchor) => {
			var div_9 = root_3$2();
			var text_7 = only_child(div_9, true);
			template_effect(() => set_text(text_7, get(job).prompt || ""));
			append($$anchor, div_9);
		};
		if_block(node_3, ($$render) => {
			if (get(d)) $$render(consequent_2);
			else $$render(alternate, -1);
		});
		var div_10 = sibling(node_3, 2);
		var node_4 = child(div_10);
		var consequent_3 = ($$anchor) => {
			var button_1 = root_4$2();
			delegated("click", button_1, () => edit(get(job)));
			append($$anchor, button_1);
		};
		if_block(node_4, ($$render) => {
			if (!get(job).run_at_epoch) $$render(consequent_3);
		});
		var button_2 = sibling(node_4, 2);
		var text_8 = only_child(button_2, true);
		var button_3 = sibling(button_2, 2);
		reset(div_10);
		reset(article);
		template_effect(($0) => {
			set_text(text_1, get(job).name);
			set_text(text_2, `${$0 ?? ""} `);
			set_text(text_4, get(job).status || (get(job).paused ? "paused" : "pending"));
			set_text(text_8, get(job).paused ? "Resume" : "Pause");
		}, [() => scheduleText(get(job))]);
		delegated("click", button_2, () => void command({
			action: get(job).paused ? "resume" : "pause",
			name: get(job).name
		}, `${get(job).paused ? "Resumed" : "Paused"} ${get(job).name}`));
		delegated("click", button_3, () => void command({
			action: "remove",
			name: get(job).name
		}, `Removed ${get(job).name}`));
		append($$anchor, article);
	});
	reset(div_2);
	var node_5 = sibling(div_2, 2);
	var consequent_4 = ($$anchor) => {
		var nav = root_6$1();
		var button_4 = child(nav);
		var span_3 = sibling(button_4, 2);
		var text_9 = only_child(span_3);
		var button_5 = sibling(span_3, 2);
		reset(nav);
		template_effect(() => {
			button_4.disabled = get(pagination).page === 1;
			set_text(text_9, `Page ${get(pagination).page ?? ""} of ${get(pagination).pageCount ?? ""}`);
			button_5.disabled = get(pagination).page === get(pagination).pageCount;
		});
		delegated("click", button_4, () => set(page, get(pagination).page - 1));
		delegated("click", button_5, () => set(page, get(pagination).page + 1));
		append($$anchor, nav);
	};
	if_block(node_5, ($$render) => {
		if (get(pagination).pageCount > 1) $$render(consequent_4);
	});
	var form = sibling(node_5, 2);
	var h3 = child(form);
	var text_10 = only_child(h3, true);
	var label = sibling(h3, 2);
	var input = sibling(child(label), 2);
	remove_input_defaults(input);
	reset(label);
	var label_1 = sibling(label, 2);
	var textarea = sibling(child(label_1), 2);
	remove_textarea_child(textarea);
	reset(label_1);
	var div_11 = sibling(label_1, 2);
	var label_2 = child(div_11);
	var select = sibling(child(label_2), 2);
	var option = child(select);
	option.value = option.__value = "interval";
	var option_1 = sibling(option);
	option_1.value = option_1.__value = "daily";
	reset(select);
	init_select(select);
	reset(label_2);
	var node_6 = sibling(label_2, 2);
	var consequent_5 = ($$anchor) => {
		var label_3 = root_7$1();
		var input_1 = sibling(child(label_3), 2);
		remove_input_defaults(input_1);
		reset(label_3);
		bind_value(input_1, () => get(interval), ($$value) => set(interval, $$value));
		append($$anchor, label_3);
	};
	var alternate_1 = ($$anchor) => {
		var label_4 = root_8();
		var input_2 = sibling(child(label_4), 2);
		remove_input_defaults(input_2);
		reset(label_4);
		bind_value(input_2, () => get(dailyAt), ($$value) => set(dailyAt, $$value));
		append($$anchor, label_4);
	};
	if_block(node_6, ($$render) => {
		if (get(schedule) === "interval") $$render(consequent_5);
		else $$render(alternate_1, -1);
	});
	reset(div_11);
	var node_7 = sibling(div_11, 2);
	var consequent_6 = ($$anchor) => {
		var label_5 = root_9();
		var input_3 = child(label_5);
		remove_input_defaults(input_3);
		next(2);
		reset(label_5);
		bind_checked(input_3, () => get(exact), ($$value) => set(exact, $$value));
		append($$anchor, label_5);
	};
	if_block(node_7, ($$render) => {
		if (get(schedule) === "interval") $$render(consequent_6);
	});
	var div_12 = sibling(node_7, 2);
	var button_6 = child(div_12);
	var button_7 = sibling(button_6, 2);
	reset(div_12);
	reset(form);
	var button_8 = only_child(sibling(form, 2));
	reset(div);
	reset(dialog);
	attach(dialog, () => dialogVisibility(() => get(dialogOpen), () => get(presentation) === "modal", close));
	template_effect(($0) => {
		set_attribute(dialog, "data-presentation", get(presentation));
		set_text(text, get(status));
		set_text(text_10, get(editing) ? `Edit ${get(editing)}` : "Add job");
		input.readOnly = $0;
		button_7.disabled = get(saving);
		button_8.disabled = !get(jobs).length || get(saving);
	}, [() => Boolean(get(editing))]);
	delegated("click", dialog, (event) => {
		if (event.target === event.currentTarget && get(presentation) !== "stack") close();
	});
	delegated("click", button, close);
	event("submit", form, (event) => {
		event.preventDefault();
		submit();
	});
	bind_value(input, () => get(name), ($$value) => set(name, $$value));
	bind_value(textarea, () => get(prompt), ($$value) => set(prompt, $$value));
	bind_select_value(select, () => get(schedule), ($$value) => set(schedule, $$value));
	delegated("click", button_6, reset$1);
	delegated("click", button_8, () => {
		if (confirm(`Clear all ${get(jobs).length} scheduled jobs?`)) command({ action: "clear" }, "Cleared all scheduled jobs");
	});
	append($$anchor, dialog);
	return pop($$exports);
}
delegate(["click"]);
//#endregion
//#region src/ui/LogsPanel.svelte
init_client();
init_appViewState_svelte();
init_browserAttachments_svelte();
init_uiControllers();
var root$2 = /* @__PURE__ */ from_html(`<section class="logs-viewport" id="logsViewport"><div class="logs-shell"><div class="logs-header"><div><strong> </strong><span> </span></div> <span class="logs-live"><i></i> live</span></div> <pre class="log-output"> </pre></div></section>`);
function LogsPanel($$anchor, $$props) {
	push($$props, true);
	const visible = /* @__PURE__ */ user_derived(() => appViewState.mode === "logs");
	let serverTitle = /* @__PURE__ */ state$1("Prompta · prompta.service");
	let meta = /* @__PURE__ */ state$1("Waiting for synced journal");
	let output = /* @__PURE__ */ state$1("Loading logs…");
	let fingerprint = /* @__PURE__ */ state$1("");
	let timer;
	function relativeTime(epochSeconds) {
		const value = Number(epochSeconds || 0);
		if (!value) return "";
		const delta = Math.abs(Date.now() - value * 1e3);
		if (delta < 45e3) return "now";
		if (delta < 36e5) return `${Math.max(1, Math.round(delta / 6e4))}m`;
		if (delta < 864e5) return `${Math.round(delta / 36e5)}h`;
		return `${Math.round(delta / 864e5)}d`;
	}
	function render(payload) {
		const lines = Array.isArray(payload.lines) ? payload.lines.map(String) : [];
		const next = JSON.stringify([payload.updated_at, lines]);
		if (next !== get(fingerprint)) {
			set(fingerprint, next, true);
			set(output, lines.length ? lines.join("\n") : "No Prompta service logs are available yet.", true);
		}
		set(meta, payload.exists ? payload.source === "journal" ? `${lines.length} lines · live journal` : `${lines.length} lines · synced ${relativeTime(payload.updated_at)}` : "Waiting for Prompta service logs", true);
	}
	async function load() {
		try {
			const response = await fetch("api/logs?limit=800", { cache: "no-store" });
			if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
			render(await response.json());
		} catch (error) {
			set(meta, "Logs unavailable");
			console.error(error);
		}
	}
	function setServerTitle(display) {
		set(serverTitle, `${display || ""} · prompta.service`);
	}
	registerLogsPanel({
		load,
		setServerTitle
	});
	user_effect(() => {
		if (!get(visible)) return;
		load();
		timer = setInterval(() => void load(), 2e3);
		return () => {
			if (timer) clearInterval(timer);
			timer = void 0;
		};
	});
	var $$exports = {
		load,
		setServerTitle
	};
	var section = root$2();
	var div = child(section);
	var div_1 = child(div);
	var div_2 = child(div_1);
	var strong = child(div_2);
	var text = only_child(strong, true);
	var text_1 = only_child(sibling(strong), true);
	reset(div_2);
	next(2);
	reset(div_1);
	var text_2 = only_child(sibling(div_1, 2), true);
	reset(div);
	reset(section);
	attach(section, () => stickToBottom(() => get(fingerprint)));
	template_effect(() => {
		set_attribute(section, "hidden", !get(visible));
		set_text(text, get(serverTitle));
		set_text(text_1, get(meta));
		set_text(text_2, get(output));
	});
	append($$anchor, section);
	return pop($$exports);
}
//#endregion
//#region src/ui/sidebarState.svelte.ts
function configureSidebar(onMotionEnd) {
	motionEnd = onMotionEnd;
}
function openSidebar() {
	sidebarState.moving = !sidebarState.open;
	sidebarState.open = true;
}
function closeSidebar(_restoreFocus = false) {
	sidebarState.moving = sidebarState.open;
	sidebarState.open = false;
}
function finishSidebarMotion() {
	if (!sidebarState.moving) return;
	sidebarState.moving = false;
	motionEnd();
}
var motionEnd, sidebarState, sidebarListState, sidebarListActions;
var init_sidebarState_svelte = __esmMin((() => {
	init_client();
	motionEnd = () => {};
	sidebarState = proxy({
		open: false,
		moving: false
	});
	sidebarListState = proxy({
		model: {
			emptyState: "none",
			hasMore: false,
			loadingMore: false,
			groups: []
		},
		selectedConversationId: ""
	});
	sidebarListActions = proxy({
		onSelect: () => {},
		onPin: () => {},
		onPrefetch: () => {},
		onLoadMore: () => {}
	});
}));
//#endregion
//#region src/ui/SidebarList.svelte
init_client();
init_index_client();
init_appViewState_svelte();
init_browserAttachments_svelte();
init_clientLogic();
init_conversationLogic();
init_sidebarState_svelte();
var root$1 = /* @__PURE__ */ from_html(`No cached conversations yet.<br/>Prompta runs will appear here live.`, 1);
var root_1$1 = /* @__PURE__ */ from_html(`<div class="list-empty"><!></div>`);
var root_2$1 = /* @__PURE__ */ from_html(`<span></span>`);
var root_3$1 = /* @__PURE__ */ from_html(`<span class="chat-broken-badge" title="No ChatGPT response for at least 40 minutes">Broken</span>`);
var root_4$1 = /* @__PURE__ */ from_html(`<div><button type="button" class="chat-item-select"><div class="chat-item-top"><!> <span class="chat-title"> </span> <!></div> <div class="chat-preview"> </div> <div class="chat-meta"><span class="chat-job"> </span> <span class="chat-time"> </span></div></button> <button type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6l-.8 5 3.3 3.3v1.4H13v7.8l-1 1-1-1v-7.8H6.5v-1.4L9.8 8 9 3z"></path></svg></button></div>`);
var root_5 = /* @__PURE__ */ from_html(`<section class="chat-group"><div class="chat-group-label"> </div> <!></section>`);
var root_6 = /* @__PURE__ */ from_html(`<button type="button" class="sidebar-load-more"> </button>`);
var root_7 = /* @__PURE__ */ from_html(`<!> <!> <dialog class="pending-message-actions" aria-labelledby="sidebarChatActionsTitle"><div class="pending-message-actions-shell"><div id="sidebarChatActionsTitle" class="pending-message-actions-title">Chat actions</div> <button type="button" class="pending-message-action"> </button> <button type="button" class="pending-message-action cancel">Cancel</button></div></dialog>`, 1);
function SidebarList($$anchor, $$props) {
	push($$props, true);
	const coarsePointer = new MediaQuery("(pointer: coarse)");
	let actionsChatId = /* @__PURE__ */ state$1("");
	let actionsChatPinned = /* @__PURE__ */ state$1(false);
	let actionsOpen = /* @__PURE__ */ state$1(false);
	let longPressTimer;
	let longPressPointerId = null;
	let longPressStartX = 0;
	let longPressStartY = 0;
	let suppressSelectChatId = "";
	function clearLongPress() {
		if (longPressTimer !== void 0) {
			clearTimeout(longPressTimer);
			longPressTimer = void 0;
		}
		longPressPointerId = null;
	}
	function openActions(chatId, pinned) {
		clearLongPress();
		set(actionsChatId, chatId, true);
		set(actionsChatPinned, pinned, true);
		set(actionsOpen, true);
	}
	function closeActions() {
		set(actionsOpen, false);
		suppressSelectChatId = "";
	}
	function startLongPress(event, chatId, pinned) {
		sidebarListActions.onPrefetch(chatId);
		if (!coarsePointer.current || event.pointerType === "mouse") return;
		clearLongPress();
		suppressSelectChatId = "";
		longPressPointerId = event.pointerId;
		longPressStartX = event.clientX;
		longPressStartY = event.clientY;
		longPressTimer = setTimeout(() => {
			longPressTimer = void 0;
			longPressPointerId = null;
			suppressSelectChatId = chatId;
			openActions(chatId, pinned);
		}, 480);
	}
	function moveLongPress(event) {
		if (event.pointerId !== longPressPointerId) return;
		if (pendingLongPressMoved(longPressStartX, longPressStartY, event.clientX, event.clientY)) clearLongPress();
	}
	function endLongPress(event, chatId, optimisticNew) {
		if (event.pointerId !== longPressPointerId) return;
		clearLongPress();
		suppressSelectChatId = chatId;
		sidebarListActions.onSelect(chatId, optimisticNew);
	}
	function cancelLongPress(event) {
		if (event.pointerId === longPressPointerId) clearLongPress();
	}
	function selectChat(chatId, optimisticNew) {
		if (suppressSelectChatId === chatId) {
			suppressSelectChatId = "";
			return;
		}
		sidebarListActions.onSelect(chatId, optimisticNew);
	}
	function togglePinFromActions() {
		const chatId = get(actionsChatId);
		closeActions();
		if (chatId) sidebarListActions.onPin(chatId);
	}
	var fragment = root_7();
	event("keydown", $window, (event) => {
		if (event.key === "Escape" && get(actionsOpen)) closeActions();
	});
	var node = first_child(fragment);
	var consequent_2 = ($$anchor) => {
		var div = root_1$1();
		var node_1 = child(div);
		var consequent = ($$anchor) => {
			append($$anchor, text("No cached chats match your search."));
		};
		var consequent_1 = ($$anchor) => {
			append($$anchor, text("No conversations match these filters."));
		};
		var alternate = ($$anchor) => {
			var fragment_1 = root$1();
			next(2);
			append($$anchor, fragment_1);
		};
		if_block(node_1, ($$render) => {
			if (sidebarListState.model.emptyState === "search") $$render(consequent);
			else if (sidebarListState.model.emptyState === "filter") $$render(consequent_1, 1);
			else $$render(alternate, -1);
		});
		reset(div);
		append($$anchor, div);
	};
	var alternate_1 = ($$anchor) => {
		var fragment_2 = comment();
		each(first_child(fragment_2), 17, () => sidebarListState.model.groups, (group) => group.label, ($$anchor, group) => {
			var section = root_5();
			var div_1 = child(section);
			var text_2 = only_child(div_1, true);
			each(sibling(div_1, 2), 17, () => get(group).chats, (chat) => chat.id, ($$anchor, chat) => {
				var div_2 = root_4$1();
				var button = child(div_2);
				var div_3 = child(button);
				var node_4 = child(div_3);
				var consequent_3 = ($$anchor) => {
					var span = root_2$1();
					template_effect(() => {
						set_class(span, 1, clsx(["item-status-dot", get(chat).statusClass]));
						set_attribute(span, "title", get(chat).statusLabel || void 0);
						set_attribute(span, "aria-label", get(chat).statusLabel || void 0);
					});
					append($$anchor, span);
				};
				if_block(node_4, ($$render) => {
					if (get(chat).statusClass) $$render(consequent_3);
				});
				var span_1 = sibling(node_4, 2);
				var text_3 = only_child(span_1, true);
				var node_5 = sibling(span_1, 2);
				var consequent_4 = ($$anchor) => {
					append($$anchor, root_3$1());
				};
				if_block(node_5, ($$render) => {
					if (get(chat).broken) $$render(consequent_4);
				});
				reset(div_3);
				var div_4 = sibling(div_3, 2);
				var text_4 = only_child(div_4, true);
				var div_5 = sibling(div_4, 2);
				var span_3 = child(div_5);
				var text_5 = only_child(span_3, true);
				var span_4 = sibling(span_3, 2);
				var text_6 = only_child(span_4, true);
				reset(div_5);
				reset(button);
				var button_1 = sibling(button, 2);
				reset(div_2);
				template_effect(($0) => {
					set_class(div_2, 1, clsx(["chat-item", {
						selected: get(chat).id === sidebarListState.selectedConversationId,
						unread: get(chat).unread
					}]));
					set_attribute(div_2, "data-dom-key", "chat:" + get(chat).id);
					set_attribute(button, "data-chat-id", get(chat).id);
					set_attribute(button, "data-optimistic-new", get(chat).optimisticNew ? "true" : "false");
					set_attribute(button, "aria-current", get(chat).id === sidebarListState.selectedConversationId ? "true" : void 0);
					set_text(text_3, get(chat).title);
					set_text(text_4, get(chat).preview);
					set_text(text_5, get(chat).jobLabel);
					set_attribute(span_4, "data-activity-at", get(chat).activityAt);
					set_text(text_6, $0);
					set_class(button_1, 1, clsx(["chat-row-pin", { active: get(chat).pinned }]));
					set_attribute(button_1, "data-pin-chat-id", get(chat).id);
					set_attribute(button_1, "aria-label", get(chat).pinned ? "Unpin chat" : "Pin chat");
					set_attribute(button_1, "title", get(chat).pinned ? "Unpin chat" : "Pin chat");
					set_attribute(button_1, "aria-pressed", get(chat).pinned);
				}, [() => formatRelativeTime(get(chat).activityAt, appViewState.clockTick)]);
				delegated("pointerdown", button, (event) => startLongPress(event, get(chat).id, get(chat).pinned));
				delegated("pointermove", button, moveLongPress);
				delegated("pointerup", button, (event) => endLongPress(event, get(chat).id, get(chat).optimisticNew));
				event("pointercancel", button, cancelLongPress);
				delegated("contextmenu", button, (event) => {
					if (!coarsePointer.current) return;
					event.preventDefault();
					suppressSelectChatId = get(chat).id;
					openActions(get(chat).id, get(chat).pinned);
				});
				delegated("click", button, () => selectChat(get(chat).id, get(chat).optimisticNew));
				delegated("click", button_1, () => sidebarListActions.onPin(get(chat).id));
				append($$anchor, div_2);
			});
			reset(section);
			template_effect(() => {
				set_attribute(section, "data-dom-key", "group:" + get(group).label);
				set_text(text_2, get(group).label);
			});
			append($$anchor, section);
		});
		append($$anchor, fragment_2);
	};
	if_block(node, ($$render) => {
		if (sidebarListState.model.groups.length === 0) $$render(consequent_2);
		else $$render(alternate_1, -1);
	});
	var node_6 = sibling(node, 2);
	var consequent_5 = ($$anchor) => {
		var button_2 = root_6();
		var text_7 = only_child(button_2, true);
		template_effect(() => {
			button_2.disabled = sidebarListState.model.loadingMore;
			set_attribute(button_2, "aria-busy", sidebarListState.model.loadingMore);
			set_text(text_7, sidebarListState.model.loadingMore ? "Loading older chats…" : "Load older chats");
		});
		delegated("click", button_2, () => sidebarListActions.onLoadMore());
		append($$anchor, button_2);
	};
	if_block(node_6, ($$render) => {
		if (sidebarListState.model.hasMore) $$render(consequent_5);
	});
	var dialog = sibling(node_6, 2);
	var div_6 = child(dialog);
	var button_3 = sibling(child(div_6), 2);
	var text_8 = only_child(button_3, true);
	var button_4 = sibling(button_3, 2);
	reset(div_6);
	reset(dialog);
	attach(dialog, () => dialogVisibility(() => get(actionsOpen), () => true, closeActions));
	template_effect(() => set_text(text_8, get(actionsChatPinned) ? "Unpin chat" : "Pin chat"));
	delegated("click", dialog, (event) => {
		if (event.target === event.currentTarget) closeActions();
	});
	delegated("click", button_3, togglePinFromActions);
	delegated("click", button_4, closeActions);
	append($$anchor, fragment);
	pop();
}
delegate([
	"pointerdown",
	"pointermove",
	"pointerup",
	"contextmenu",
	"click"
]);
//#endregion
//#region src/ui/sidebarGesture.ts
function sidebarDragDirection(deltaX, deltaY) {
	if (Math.max(Math.abs(deltaX), Math.abs(deltaY)) <= 8) return "pending";
	return Math.abs(deltaX) > Math.abs(deltaY) * 1.15 ? "horizontal" : "vertical";
}
function sidebarDragPosition(wasOpen, width, startClientX, clientX) {
	const startX = wasOpen ? 0 : -width;
	const x = Math.max(-width, Math.min(0, startX + clientX - startClientX));
	const progress = width > 0 ? 1 + x / width : 0;
	return {
		x,
		progress: Math.max(0, Math.min(1, progress))
	};
}
function sidebarDragShouldOpen(velocityX, progress) {
	if (velocityX > .35) return true;
	if (velocityX < -.35) return false;
	return progress >= .5;
}
//#endregion
//#region src/ui/App.svelte
init_client();
init_index_client();
init_appActions_svelte();
init_appViewState_svelte();
init_browserAttachments_svelte();
init_uiControllers();
init_sidebarState_svelte();
var root = /* @__PURE__ */ from_html(`<meta name="apple-mobile-web-app-title"/>`);
var root_1 = /* @__PURE__ */ from_html(`<button type="button" class="search-clear" aria-label="Clear search" title="Clear search"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"></path></svg></button>`);
var root_2 = /* @__PURE__ */ from_html(`<kbd>/</kbd>`);
var root_3 = /* @__PURE__ */ from_html(`<button type="button"> </button>`);
var root_4 = /* @__PURE__ */ from_html(`<div class="app-shell"><aside id="sidebar"><div class="sidebar-top"><div class="brand-row"><button class="icon-button mobile-only" id="closeSidebar" aria-label="Close sidebar" aria-controls="sidebar"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6"></path></svg></button> <div class="brand-mark" aria-hidden="true">P</div> <div class="brand-copy"><strong>Prompta</strong> <span id="serverLabel"> </span></div> <div id="globalLiveOrb"></div></div> <label class="search-box"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg> <input id="searchInput" type="search" placeholder="Search cached chats" aria-label="Search cached chats" aria-keyshortcuts="/" autocomplete="off"/> <!></label></div> <div class="sidebar-scroll"><div class="sidebar-toolbar"><button type="button" class="sidebar-action sidebar-jobs-action" id="jobsSidebarButton"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3v3M17 3v3M4.5 8.5h15M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"></path><path d="M8 12h3M8 16h3M14 12h2M14 16h2"></path></svg> <span>Jobs</span></button> <div class="sidebar-toolbar-right"><button type="button" class="sidebar-mark-all-read" aria-label="Mark all chats as read" title="Mark all chats as read">Read all</button> <div class="sidebar-filters" aria-label="Conversation filters"></div></div></div> <nav class="chat-list" id="chatList" aria-label="Cached conversations"><!></nav></div> <div class="sidebar-footer"><div class="cache-summary"><span class="summary-dot"></span> <span id="cacheSummary"> </span></div> <button type="button" class="read-only-pill" id="headLabel" aria-haspopup="dialog" aria-controls="changelogDialog"> </button></div></aside> <div id="sidebarScrim" role="button" tabindex="-1" aria-label="Close sidebar"></div> <main class="main-panel"><header class="topbar"><button class="icon-button mobile-only" id="openSidebar" aria-label="Open sidebar" aria-controls="sidebar"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"></path></svg></button> <div class="chat-heading" id="chatHeading"><div class="heading-title"> </div> <div class="heading-meta"> </div></div> <div class="topbar-actions" aria-label="Prompta actions"><button id="unattendedModeButton"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z"></path></svg></button> <button id="pinChatButton"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6ZM12 14v7"></path></svg></button> <button class="icon-button" id="shareChatButton" aria-label="Copy chat link" title="Share chat"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15V3M7 8l5-5 5 5M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"></path></svg></button> <span id="syncLabel" role="img"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 6c0-1.1 3.1-2 7-2s7 .9 7 2-3.1 2-7 2-7-.9-7-2Zm0 0v6c0 1.1 3.1 2 7 2s7-.9 7-2V6M5 12v6c0 1.1 3.1 2 7 2s7-.9 7-2v-6"></path></svg></span></div></header> <section id="conversationViewport"><div class="empty-state" id="emptyState"><div class="empty-logo">P</div> <h1>Your Prompta chats, locally.</h1> <p>Active runs and completed history stream from Prompta's SQLite cache.</p> <div class="empty-features"><span>Reply from here</span> <span>Live SSE updates</span> <span>SQLite source of truth</span></div></div> <article class="conversation" id="conversation"><!></article></section> <!> <!></main></div> <div class="action-toast" role="status" aria-live="polite" aria-atomic="true"> </div> <button type="button" class="version-update-notice" id="versionUpdateNotice" aria-live="polite"> </button> <!> <!>`, 1);
function App($$anchor, $$props) {
	push($$props, true);
	const serverDisplay = /* @__PURE__ */ user_derived(() => appViewState.serverDisplay || $$props.serverName);
	const serverLabel = /* @__PURE__ */ user_derived(() => appViewState.serverLabel === "Server · local" ? "Server · " + $$props.serverName : appViewState.serverLabel);
	const sidebarFilterOptions = [
		{
			key: "unread",
			label: "Unread"
		},
		{
			key: "active",
			label: "Active"
		},
		{
			key: "broken",
			label: "Broken"
		}
	];
	const mobileSidebarMedia = new MediaQuery("(max-width: 780px)");
	let sidebarWidth = /* @__PURE__ */ state$1(0);
	let sidebarDragCleanupTimer;
	const sidebarDrag = proxy({
		pointerId: null,
		startX: 0,
		startY: 0,
		lastX: 0,
		lastAt: 0,
		velocityX: 0,
		width: 0,
		wasOpen: false,
		active: false,
		settling: false,
		x: 0,
		progress: 0,
		duration: 0
	});
	function mobileSidebarEnabled() {
		return mobileSidebarMedia.current;
	}
	function syncConversationPinned(pinned) {
		appViewState.conversationPinnedToBottom = pinned;
	}
	function clearSidebarDrag() {
		if (sidebarDragCleanupTimer !== void 0) {
			clearTimeout(sidebarDragCleanupTimer);
			sidebarDragCleanupTimer = void 0;
		}
		sidebarDrag.pointerId = null;
		sidebarDrag.active = false;
		sidebarDrag.settling = false;
		sidebarDrag.width = 0;
		sidebarDrag.velocityX = 0;
		sidebarDrag.duration = 0;
	}
	function completeSidebarDrag() {
		const wasMoving = sidebarState.moving;
		clearSidebarDrag();
		if (wasMoving) finishSidebarMotion();
	}
	function settleSidebarDrag(opened) {
		const targetX = opened ? 0 : -sidebarDrag.width;
		const remaining = Math.abs(targetX - sidebarDrag.x);
		const speed = Math.max(.6, Math.abs(sidebarDrag.velocityX));
		const duration = Math.max(90, Math.min(180, Math.round(remaining / speed)));
		sidebarState.open = opened;
		sidebarState.moving = true;
		sidebarDrag.settling = true;
		sidebarDrag.duration = duration;
		sidebarDrag.x = targetX;
		sidebarDrag.progress = opened ? 1 : 0;
		sidebarDragCleanupTimer = setTimeout(completeSidebarDrag, duration + 40);
	}
	function handleSidebarPointerDown(event) {
		if (event.pointerType === "mouse" || sidebarDrag.pointerId !== null || sidebarDrag.active || !mobileSidebarEnabled() || get(sidebarWidth) <= 0) return;
		const width = get(sidebarWidth);
		const wasOpen = sidebarState.open;
		sidebarDrag.pointerId = event.pointerId;
		sidebarDrag.startX = event.clientX;
		sidebarDrag.startY = event.clientY;
		sidebarDrag.lastX = event.clientX;
		sidebarDrag.lastAt = performance.now();
		sidebarDrag.velocityX = 0;
		sidebarDrag.width = width;
		sidebarDrag.wasOpen = wasOpen;
		sidebarDrag.x = wasOpen ? 0 : -width;
		sidebarDrag.progress = wasOpen ? 1 : 0;
	}
	function handleSidebarPointerMove(event) {
		if (event.pointerId !== sidebarDrag.pointerId) return;
		const deltaX = event.clientX - sidebarDrag.startX;
		const deltaY = event.clientY - sidebarDrag.startY;
		if (!sidebarDrag.active) {
			const direction = sidebarDragDirection(deltaX, deltaY);
			if (direction === "pending") return;
			if (direction === "vertical") {
				clearSidebarDrag();
				return;
			}
			if (!sidebarDrag.wasOpen && deltaX <= 0) return;
			sidebarDrag.active = true;
			sidebarState.moving = true;
		}
		event.preventDefault();
		const now = performance.now();
		const elapsed = Math.max(1, now - sidebarDrag.lastAt);
		const { x, progress } = sidebarDragPosition(sidebarDrag.wasOpen, sidebarDrag.width, sidebarDrag.startX, event.clientX);
		sidebarDrag.velocityX = (event.clientX - sidebarDrag.lastX) / elapsed;
		sidebarDrag.lastX = event.clientX;
		sidebarDrag.lastAt = now;
		sidebarDrag.x = x;
		sidebarDrag.progress = progress;
	}
	function handleSidebarPointerUp(event) {
		if (event.pointerId !== sidebarDrag.pointerId) return;
		if (!sidebarDrag.active) {
			clearSidebarDrag();
			return;
		}
		const { x, progress } = sidebarDragPosition(sidebarDrag.wasOpen, sidebarDrag.width, sidebarDrag.startX, event.clientX);
		const now = performance.now();
		const elapsed = Math.max(1, now - sidebarDrag.lastAt);
		const finalVelocity = (event.clientX - sidebarDrag.lastX) / elapsed;
		sidebarDrag.x = x;
		sidebarDrag.progress = progress;
		if (Math.abs(finalVelocity) > Math.abs(sidebarDrag.velocityX)) sidebarDrag.velocityX = finalVelocity;
		settleSidebarDrag(sidebarDragShouldOpen(sidebarDrag.velocityX, progress));
	}
	function handleSidebarPointerCancel(event) {
		if (event.pointerId !== sidebarDrag.pointerId) return;
		if (sidebarDrag.active) settleSidebarDrag(sidebarDrag.wasOpen);
		else clearSidebarDrag();
	}
	function handleSidebarTransitionEnd(event) {
		if (event.propertyName !== "transform") return;
		if (sidebarDrag.settling) completeSidebarDrag();
		else finishSidebarMotion();
	}
	function handleGlobalKeydown(event) {
		const target = event.target;
		const typing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || Boolean(target?.isContentEditable);
		if (event.key === "/" && !typing) {
			event.preventDefault();
			openSidebar();
			requestSearchFocus();
			return;
		}
		if (event.key !== "Escape") return;
		if (target instanceof HTMLInputElement && target.id === "searchInput" && appViewState.searchValue) {
			event.preventDefault();
			appViewState.searchValue = "";
			appActions.onSearch("");
			return;
		}
		getAttachmentPicker().closeMenu();
		getJobsDialog().close();
		getChangelogDialog().close();
		requestSearchBlur();
		closeSidebar(true);
	}
	var fragment = root_4();
	head("1ocnzw1", ($$anchor) => {
		var meta = root();
		template_effect(() => set_attribute(meta, "content", "Prompta " + get(serverDisplay)));
		deferred_template_effect(() => {
			$document.title = `Prompta · ${get(serverDisplay) ?? ""}`;
		});
		append($$anchor, meta);
	});
	event("keydown", $window, handleGlobalKeydown);
	event("hashchange", $window, function(...$$args) {
		appActions.onHashChange?.apply(this, $$args);
	});
	event("pagehide", $window, function(...$$args) {
		appActions.onPageHide?.apply(this, $$args);
	});
	event("pageshow", $window, function(...$$args) {
		appActions.onPageShow?.apply(this, $$args);
	});
	event("pointerdown", $window, handleSidebarPointerDown, true);
	event("pointermove", $window, handleSidebarPointerMove, true);
	event("pointerup", $window, handleSidebarPointerUp, true);
	event("pointercancel", $window, handleSidebarPointerCancel, true);
	var div = first_child(fragment);
	var aside = child(div);
	let styles;
	var div_1 = child(aside);
	var div_2 = child(div_1);
	var button = child(div_2);
	var div_3 = sibling(button, 4);
	var text = only_child(sibling(child(div_3), 2), true);
	reset(div_3);
	var div_4 = sibling(div_3, 2);
	reset(div_2);
	var label = sibling(div_2, 2);
	var input = sibling(child(label), 2);
	remove_input_defaults(input);
	attach(input, () => focusOnRequest(() => appViewState.searchFocusRequest));
	attach(input, () => blurOnRequest(() => appViewState.searchBlurRequest));
	var node = sibling(input, 2);
	var consequent = ($$anchor) => {
		var button_1 = root_1();
		delegated("click", button_1, () => {
			appViewState.searchValue = "";
			appActions.onSearch("");
		});
		append($$anchor, button_1);
	};
	var alternate = ($$anchor) => {
		append($$anchor, root_2());
	};
	if_block(node, ($$render) => {
		if (appViewState.searchValue) $$render(consequent);
		else $$render(alternate, -1);
	});
	reset(label);
	reset(div_1);
	var div_5 = sibling(div_1, 2);
	var div_6 = child(div_5);
	var button_2 = child(div_6);
	var div_7 = sibling(button_2, 2);
	var button_3 = child(div_7);
	var div_8 = sibling(button_3, 2);
	each(div_8, 21, () => sidebarFilterOptions, (filter) => filter.key, ($$anchor, filter) => {
		var button_4 = root_3();
		var text_1 = only_child(button_4, true);
		template_effect(() => {
			set_class(button_4, 1, clsx(["sidebar-filter-chip", { active: appViewState.sidebarFilters[get(filter).key] }]));
			set_attribute(button_4, "aria-pressed", appViewState.sidebarFilters[get(filter).key]);
			set_text(text_1, get(filter).label);
		});
		delegated("click", button_4, () => appActions.onSidebarFilter(get(filter).key));
		append($$anchor, button_4);
	});
	reset(div_8);
	reset(div_7);
	reset(div_6);
	var nav = sibling(div_6, 2);
	SidebarList(child(nav), {});
	reset(nav);
	reset(div_5);
	attach(div_5, () => scrollToTopOnRequest(() => appViewState.sidebarTopRequest));
	var div_9 = sibling(div_5, 2);
	var div_10 = child(div_9);
	var text_2 = only_child(sibling(child(div_10), 2), true);
	reset(div_10);
	var button_5 = sibling(div_10, 2);
	var text_3 = only_child(button_5, true);
	reset(div_9);
	reset(aside);
	attach(aside, () => reportElementWidth((width) => set(sidebarWidth, width, true)));
	var div_11 = sibling(aside, 2);
	let styles_1;
	var main = sibling(div_11, 2);
	var header = child(main);
	var button_6 = child(header);
	var div_12 = sibling(button_6, 2);
	var div_13 = child(div_12);
	var text_4 = only_child(div_13, true);
	var text_5 = only_child(sibling(div_13, 2), true);
	reset(div_12);
	var div_15 = sibling(div_12, 2);
	var button_7 = child(div_15);
	var button_8 = sibling(button_7, 2);
	var button_9 = sibling(button_8, 2);
	var span_2 = sibling(button_9, 2);
	reset(div_15);
	reset(header);
	var section = sibling(header, 2);
	var div_16 = child(section);
	var article = sibling(div_16, 2);
	ConversationMessages(child(article), {});
	reset(article);
	reset(section);
	attach(section, () => conversationViewport(syncConversationPinned));
	var node_3 = sibling(section, 2);
	LogsPanel(node_3, {});
	var node_4 = sibling(node_3, 2);
	var consequent_1 = ($$anchor) => {
		Composer($$anchor, {});
	};
	if_block(node_4, ($$render) => {
		if (appViewState.mode === "chats") $$render(consequent_1);
	});
	reset(main);
	reset(div);
	attach(div, fitVisualViewport);
	var div_17 = sibling(div, 2);
	var text_6 = only_child(div_17, true);
	var button_10 = sibling(div_17, 2);
	var text_7 = only_child(button_10, true);
	var node_5 = sibling(button_10, 2);
	JobsDialog(node_5, {});
	ChangelogDialog(sibling(node_5, 2), {});
	template_effect(($0) => {
		set_class(aside, 1, clsx(["sidebar", { "is-open": sidebarState.open }]));
		styles = set_style(aside, "", styles, {
			transform: sidebarDrag.active ? "translate3d(" + sidebarDrag.x + "px, 0, 0)" : void 0,
			transition: sidebarDrag.active ? sidebarDrag.settling ? "transform " + sidebarDrag.duration + "ms cubic-bezier(0.2, 0, 0, 1)" : "none" : void 0
		});
		set_text(text, get(serverLabel));
		set_class(div_4, 1, clsx(["live-orb", { live: appViewState.live }]));
		set_attribute(div_4, "title", appViewState.liveTitle);
		set_text(text_2, appViewState.cacheSummary);
		set_attribute(button_5, "title", appViewState.headTitle);
		set_text(text_3, appViewState.headLabel);
		set_class(div_11, 1, clsx(["sidebar-scrim", { "is-open": sidebarState.open }]));
		styles_1 = set_style(div_11, "", styles_1, {
			opacity: $0,
			transition: sidebarDrag.active ? sidebarDrag.settling ? "opacity " + sidebarDrag.duration + "ms linear" : "none" : void 0,
			"pointer-events": sidebarDrag.active ? "none" : void 0
		});
		set_attribute(button_6, "aria-expanded", sidebarState.open);
		set_text(text_4, appViewState.headingTitle);
		set_text(text_5, appViewState.headingMeta);
		set_class(button_7, 1, clsx(["icon-button", { active: appViewState.unattended }]));
		set_attribute(button_7, "aria-label", appViewState.unattended ? "Disable unattended mode" : "Enable unattended mode");
		set_attribute(button_7, "title", appViewState.unattended ? "Unattended · no ChatGPT polling · " + appViewState.unattendedSendGapSeconds + "s send gap" : "Unattended mode · disable ChatGPT polling and increase send allowance");
		set_attribute(button_7, "aria-pressed", appViewState.unattended);
		button_7.disabled = appViewState.unattendedUpdating;
		set_class(button_8, 1, clsx(["icon-button", { active: appViewState.pinActive }]));
		set_attribute(button_8, "aria-label", appViewState.pinLabel);
		set_attribute(button_8, "title", appViewState.pinLabel);
		set_attribute(button_8, "aria-pressed", appViewState.pinActive);
		button_8.disabled = appViewState.pinDisabled;
		button_9.disabled = appViewState.shareDisabled;
		set_class(span_2, 1, clsx([
			"status-icon",
			"sync",
			appViewState.syncStatus
		]));
		set_attribute(span_2, "aria-label", appViewState.syncLabel);
		set_attribute(span_2, "title", appViewState.syncLabel);
		set_class(section, 1, clsx(["conversation-viewport", { "chat-switching": appViewState.chatSwitching }]));
		set_attribute(section, "aria-busy", appViewState.chatSwitching ? "true" : void 0);
		set_attribute(section, "hidden", appViewState.mode === "logs");
		set_attribute(div_16, "hidden", !appViewState.emptyVisible);
		set_attribute(article, "hidden", !appViewState.conversationVisible);
		set_attribute(div_17, "hidden", !appViewState.actionToast);
		set_text(text_6, appViewState.actionToast);
		set_attribute(button_10, "aria-label", appViewState.updateApplying ? "Updating Prompta" : "New Prompta version available. Tap to update");
		set_attribute(button_10, "hidden", !appViewState.updateAvailable);
		button_10.disabled = appViewState.updateApplying;
		set_text(text_7, appViewState.updateApplying ? "Updating…" : "Update available");
	}, [() => sidebarDrag.active ? String(sidebarDrag.progress) : void 0]);
	event("transitionend", aside, handleSidebarTransitionEnd);
	delegated("click", button, () => closeSidebar());
	delegated("input", input, () => appActions.onSearch(appViewState.searchValue));
	bind_value(input, () => appViewState.searchValue, ($$value) => appViewState.searchValue = $$value);
	delegated("click", button_2, () => void getJobsDialog().open());
	delegated("click", button_3, function(...$$args) {
		appActions.onMarkAllRead?.apply(this, $$args);
	});
	delegated("click", button_5, () => void getChangelogDialog().open());
	delegated("click", div_11, () => closeSidebar());
	delegated("keydown", div_11, (event) => {
		if (event.key === "Enter" || event.key === " ") closeSidebar();
	});
	delegated("click", button_6, function(...$$args) {
		openSidebar?.apply(this, $$args);
	});
	delegated("click", button_7, function(...$$args) {
		appActions.onUnattendedMode?.apply(this, $$args);
	});
	delegated("click", button_8, function(...$$args) {
		appActions.onPin?.apply(this, $$args);
	});
	delegated("click", button_9, function(...$$args) {
		appActions.onShare?.apply(this, $$args);
	});
	delegated("click", button_10, function(...$$args) {
		appActions.onApplyUpdate?.apply(this, $$args);
	});
	append($$anchor, fragment);
	pop();
}
delegate([
	"click",
	"input",
	"keydown"
]);
//#endregion
//#region src/ui/recentChatCache.ts
var DATABASE_NAME$1, DATABASE_VERSION$1, STORE_NAME$1, ACCESSED_AT_INDEX_NAME, SUMMARY_STORE_NAME, SUMMARY_LIMIT, RecentChatCache;
var init_recentChatCache = __esmMin((() => {
	DATABASE_NAME$1 = "prompta-recent-chats";
	DATABASE_VERSION$1 = 3;
	STORE_NAME$1 = "chats";
	ACCESSED_AT_INDEX_NAME = "scope-accessed-at";
	SUMMARY_STORE_NAME = "summaries";
	SUMMARY_LIMIT = 200;
	RecentChatCache = class {
		scope;
		limit;
		memory = /* @__PURE__ */ new Map();
		databasePromise = null;
		persistedSummaryFingerprint = "";
		activeSummaryFingerprint = "";
		pendingSummaryWrite = null;
		summaryWriteRunning = false;
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
				const request = database.transaction(STORE_NAME$1, "readonly").objectStore(STORE_NAME$1).get(this.key(conversationId));
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
			const fingerprint = JSON.stringify(summaries);
			if (fingerprint === this.persistedSummaryFingerprint || fingerprint === this.activeSummaryFingerprint || fingerprint === this.pendingSummaryWrite?.fingerprint) return false;
			this.pendingSummaryWrite = {
				fingerprint,
				summaries
			};
			this.drainSummaryWrites();
			return true;
		}
		async warmSummaries() {
			const database = await this.database();
			if (!database) return [];
			const chats = (await new Promise((resolve) => {
				const request = database.transaction(SUMMARY_STORE_NAME, "readonly").objectStore(SUMMARY_STORE_NAME).openCursor(this.scopeKeyRange());
				const scopedRecords = [];
				request.onsuccess = () => {
					const cursor = request.result;
					if (!cursor) {
						resolve(scopedRecords);
						return;
					}
					const record = cursor.value;
					if (record.chat) scopedRecords.push(record);
					cursor.continue();
				};
				request.onerror = () => resolve(scopedRecords);
			})).sort((left, right) => left.position - right.position).slice(0, SUMMARY_LIMIT).map((record) => record.chat);
			this.persistedSummaryFingerprint = JSON.stringify(chats);
			return chats;
		}
		async warm() {
			const database = await this.database();
			if (!database) return [];
			const chats = await new Promise((resolve) => {
				const store = database.transaction(STORE_NAME$1, "readonly").objectStore(STORE_NAME$1);
				const range = IDBKeyRange.bound([this.scope, 0], [this.scope, Number.MAX_SAFE_INTEGER]);
				const request = store.index(ACCESSED_AT_INDEX_NAME).openCursor(range, "prev");
				const scopedChats = [];
				request.onsuccess = () => {
					const cursor = request.result;
					if (!cursor || scopedChats.length >= this.limit) {
						resolve(scopedChats);
						return;
					}
					const record = cursor.value;
					if (record.chat) scopedChats.push(record.chat);
					if (scopedChats.length >= this.limit) {
						resolve(scopedChats);
						return;
					}
					cursor.continue();
				};
				request.onerror = () => resolve(scopedChats);
			});
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
				const transaction = database.transaction([STORE_NAME$1, SUMMARY_STORE_NAME], "readwrite");
				transaction.objectStore(STORE_NAME$1).delete(this.key(conversationId));
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
		scopeKeyRange() {
			const prefix = this.scope + ":";
			return IDBKeyRange.bound(prefix, prefix + "￿");
		}
		async persist(chat) {
			const conversationId = String(chat?.id || "");
			if (!conversationId) return;
			const database = await this.database();
			if (!database) return;
			await new Promise((resolve) => {
				const transaction = database.transaction(STORE_NAME$1, "readwrite");
				const store = transaction.objectStore(STORE_NAME$1);
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
		async drainSummaryWrites() {
			if (this.summaryWriteRunning) return;
			this.summaryWriteRunning = true;
			try {
				while (this.pendingSummaryWrite) {
					const pending = this.pendingSummaryWrite;
					this.pendingSummaryWrite = null;
					if (pending.fingerprint === this.persistedSummaryFingerprint) continue;
					this.activeSummaryFingerprint = pending.fingerprint;
					await this.persistSummaries(pending.summaries);
					this.persistedSummaryFingerprint = pending.fingerprint;
					this.activeSummaryFingerprint = "";
				}
			} finally {
				this.activeSummaryFingerprint = "";
				this.summaryWriteRunning = false;
				if (this.pendingSummaryWrite) this.drainSummaryWrites();
			}
		}
		async persistSummaries(chats) {
			const database = await this.database();
			if (!database) return;
			const retainedIds = new Set(chats.map((chat) => String(chat.id)));
			await new Promise((resolve) => {
				const transaction = database.transaction(SUMMARY_STORE_NAME, "readwrite");
				const store = transaction.objectStore(SUMMARY_STORE_NAME);
				const cursorRequest = store.openCursor(this.scopeKeyRange());
				cursorRequest.onsuccess = () => {
					const cursor = cursorRequest.result;
					if (cursor) {
						const record = cursor.value;
						if (!retainedIds.has(String(record.conversationId || ""))) cursor.delete();
						cursor.continue();
						return;
					}
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
					request = indexedDB.open(DATABASE_NAME$1, DATABASE_VERSION$1);
				} catch {
					resolve(null);
					return;
				}
				request.onupgradeneeded = (event) => {
					const database = request.result;
					const transaction = request.transaction;
					const chatStore = database.objectStoreNames.contains(STORE_NAME$1) ? transaction?.objectStore(STORE_NAME$1) : database.createObjectStore(STORE_NAME$1, { keyPath: "key" });
					if (chatStore && !chatStore.indexNames.contains(ACCESSED_AT_INDEX_NAME)) chatStore.createIndex(ACCESSED_AT_INDEX_NAME, ["scope", "accessedAt"]);
					if (chatStore && event.oldVersion > 0 && event.oldVersion < DATABASE_VERSION$1) chatStore.clear();
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
//#region src/ui/offlineOutbox.ts
function createOfflinePostRecord(scope, input, createdAt = Date.now()) {
	const clientId = input.clientId.trim();
	if (!clientId) throw new Error("Offline outbox requires a client id");
	return {
		id: `${scope}:${clientId}`,
		scope,
		operation: input.operation,
		targetChatId: input.targetChatId?.trim() || null,
		message: input.message,
		attachments: (input.attachments || []).map((attachment) => ({ ...attachment })),
		clientId,
		createdAt: input.createdAt ?? createdAt,
		retryState: "pending",
		retryCount: 0,
		lastAttemptAt: null,
		lastError: input.lastError || ""
	};
}
var DATABASE_NAME, DATABASE_VERSION, STORE_NAME, CREATED_AT_INDEX_NAME, IndexedDbOfflineOutboxWriter, OfflineOutbox;
var init_offlineOutbox = __esmMin((() => {
	DATABASE_NAME = "prompta-offline-outbox";
	DATABASE_VERSION = 1;
	STORE_NAME = "posts";
	CREATED_AT_INDEX_NAME = "scope-created-at";
	IndexedDbOfflineOutboxWriter = class {
		databasePromise = null;
		async put(record) {
			const database = await this.database();
			if (!database) throw new Error("IndexedDB is unavailable");
			await new Promise((resolve, reject) => {
				const transaction = database.transaction(STORE_NAME, "readwrite");
				transaction.objectStore(STORE_NAME).put(record);
				transaction.oncomplete = () => resolve();
				transaction.onerror = () => reject(transaction.error || /* @__PURE__ */ new Error("Offline outbox write failed"));
				transaction.onabort = () => reject(transaction.error || /* @__PURE__ */ new Error("Offline outbox write aborted"));
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
				request.onupgradeneeded = () => {
					const database = request.result;
					const store = database.objectStoreNames.contains(STORE_NAME) ? request.transaction?.objectStore(STORE_NAME) : database.createObjectStore(STORE_NAME, { keyPath: "id" });
					if (store && !store.indexNames.contains(CREATED_AT_INDEX_NAME)) store.createIndex(CREATED_AT_INDEX_NAME, ["scope", "createdAt"]);
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
	OfflineOutbox = class {
		scope;
		writer;
		constructor(scope, writer = new IndexedDbOfflineOutboxWriter()) {
			this.scope = scope;
			this.writer = writer;
		}
		async enqueue(input) {
			const record = createOfflinePostRecord(this.scope, input);
			await this.writer.put(record);
			return record;
		}
	};
}));
//#endregion
//#region src/ui/browserState.svelte.ts
var finePointer;
var init_browserState_svelte = __esmMin((() => {
	init_client();
	init_index_client();
	finePointer = new MediaQuery("(pointer: fine)");
}));
//#endregion
//#region src/ui/conversationRenderer.ts
function createConversationRenderer({ onRetry, onBump, onDelete, onEdit }) {
	conversationState.onRetry = onRetry;
	conversationState.onBump = onBump;
	conversationState.onDelete = onDelete;
	conversationState.onEdit = onEdit;
	function messageNodeFingerprint(message, allowStreaming) {
		return JSON.stringify([
			message.role,
			message.status,
			messageDisplayContent(message),
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
			message.pending_bump_key,
			message.pending_delete_key,
			message.created_at,
			message.updated_at,
			message.display_at,
			allowStreaming
		]);
	}
	return {
		renderMessageNodes: async (messages, allowStreaming) => {
			conversationState.loading = false;
			conversationState.messages = messages;
			conversationState.allowStreaming = allowStreaming;
		},
		renderLoadingState: () => {
			if (!conversationState.messages.length) conversationState.loading = true;
		},
		setPendingDeleteBusy: (deleteKey, busy) => {
			const deletingKeys = new Set(conversationState.deletingKeys);
			if (busy) deletingKeys.add(deleteKey);
			else deletingKeys.delete(deleteKey);
			conversationState.deletingKeys = deletingKeys;
		},
		messageNodeFingerprint,
		captureConversationViewport,
		restoreConversationViewport
	};
}
var init_conversationRenderer = __esmMin((() => {
	init_browserAttachments_svelte();
	init_conversationState_svelte();
	init_conversationLogic();
}));
//#endregion
//#region src/ui/deploymentMonitor.ts
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
//#region src/ui/liveUpdates.ts
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
	function handlePageHide() {
		paused = true;
		stop();
	}
	function handlePageShow() {
		onPageShow();
		if (!paused) return;
		paused = false;
		loadServerIdentity();
		loadChats();
		start();
	}
	return {
		start,
		stop,
		handlePageHide,
		handlePageShow
	};
}
var init_liveUpdates = __esmMin((() => {}));
//#endregion
//#region src/ui/completionNotifications.ts
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
		const title = chatTitle(chat);
		const options = {
			body: "Finished · " + display,
			tag: "prompta-finished-" + chat.id,
			icon: "./icon.svg",
			badge: "./icon.svg",
			data: { url: "./#/" + encodeURIComponent(chat.id) }
		};
		if ("serviceWorker" in navigator) try {
			let registration = typeof navigator.serviceWorker.getRegistration === "function" ? await navigator.serviceWorker.getRegistration() : null;
			if (!registration) registration = await Promise.race([navigator.serviceWorker.ready, new Promise((resolve) => setTimeout(() => resolve(null), 1500))]);
			if (registration) {
				await registration.showNotification(title, options);
				return true;
			}
		} catch (error) {
			console.warn("Could not show Prompta service worker notification", error);
		}
		try {
			new Notification(title, options);
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
//#region src/ui/clientStorage.ts
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
//#region src/ui/app.ts
var app_exports = /* @__PURE__ */ __exportAll({});
function chatPrefetchRevision(chat) {
	return JSON.stringify([chat.status || "", chat.updated_at ?? ""]);
}
function rememberPrefetchedRevision(conversationId, revision) {
	prefetchedChatRevisions.delete(conversationId);
	prefetchedChatRevisions.set(conversationId, revision);
	while (prefetchedChatRevisions.size > 50) {
		const oldest = prefetchedChatRevisions.keys().next().value;
		if (!oldest) break;
		prefetchedChatRevisions.delete(oldest);
	}
}
function fetchChatDetail(conversationId) {
	const existing = chatDetailRequests.get(conversationId);
	if (existing) return existing;
	const request = fetchJson(`api/chats/${encodeURIComponent(conversationId)}`, 3e4).then((chat) => {
		if (!chat || String(chat.id || "") !== conversationId) return null;
		recentChatCache.remember(chat);
		return chat;
	}).finally(() => {
		chatDetailRequests.delete(conversationId);
	});
	chatDetailRequests.set(conversationId, request);
	return request;
}
function runQueuedChatPrefetch() {
	if (chatPrefetchRunning) return;
	const pending = queuedPrefetches.shift();
	if (!pending) return;
	const { conversationId, revision } = pending;
	queuedPrefetchSet.delete(conversationId);
	chatPrefetchRunning = true;
	fetchChatDetail(conversationId).then((chat) => {
		if (chat) rememberPrefetchedRevision(conversationId, revision);
	}).catch((error) => {
		console.warn("Could not prefetch Prompta chat", conversationId, error);
	}).finally(() => {
		chatPrefetchRunning = false;
		if (!queuedPrefetches.length) return;
		(typeof requestIdleCallback === "function" ? (callback) => requestIdleCallback(callback, { timeout: 500 }) : (callback) => setTimeout(callback, 40))(runQueuedChatPrefetch);
	});
}
function queueChatPrefetch(chats) {
	for (const chat of chats.slice(0, 8)) {
		const id = String(chat?.id || "");
		const revision = chatPrefetchRevision(chat);
		if (!id || chat.status === "active" || chat._optimisticNew || chat._pending_send || recentChatCache.getMemory(id) || prefetchedChatRevisions.get(id) === revision || queuedPrefetchSet.has(id) || chatDetailRequests.has(id)) continue;
		queuedPrefetchSet.add(id);
		queuedPrefetches.push({
			conversationId: id,
			revision
		});
	}
	runQueuedChatPrefetch();
}
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
function markChatRead(chatId) {
	const chat = state.chats.find((candidate) => candidate.id === chatId);
	if (!chat?.unread) return;
	chat.unread = false;
	state.sidebarFingerprint = "";
	for (const group of sidebarListState.model.groups) {
		const row = group.chats.find((candidate) => candidate.id === chatId);
		if (row) {
			row.unread = false;
			break;
		}
	}
	postJsonRequest(`api/chats/${encodeURIComponent(chatId)}/read`, {}, 2, 5e3).catch((error) => {
		console.warn("Could not persist Prompta read state", error);
	});
}
async function markAllChatsRead() {
	const unreadIds = new Set(state.chats.filter((chat) => Boolean(chat.unread)).map((chat) => chat.id));
	for (const chat of state.chats) if (unreadIds.has(chat.id)) chat.unread = false;
	state.sidebarFingerprint = "";
	renderSidebar(true);
	try {
		await postJsonRequest("api/chats/read-all", {}, 2, 5e3);
	} catch (error) {
		for (const chat of state.chats) if (unreadIds.has(chat.id)) chat.unread = true;
		state.sidebarFingerprint = "";
		renderSidebar(true);
		console.warn("Could not mark all Prompta chats read", error);
	}
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
	setStoredComposerDraft(target, appViewState.composerValue);
}
function clearComposerDraft(target = composerDraftTarget()) {
	if (!target) return;
	if (state.composerDrafts.delete(target)) saveComposerDrafts(state.composerDrafts);
}
function syncComposerDraftTarget() {
	const nextTarget = composerDraftTarget();
	if (nextTarget === state.composerDraftTarget) return;
	if (state.composerDraftTarget && !state.sending) setStoredComposerDraft(state.composerDraftTarget, appViewState.composerValue);
	state.composerDraftTarget = nextTarget;
	const draft = nextTarget ? state.composerDrafts.get(nextTarget) || "" : "";
	if (appViewState.composerValue !== draft) appViewState.composerValue = draft;
	syncSendButton();
}
function setComposerStatus(value) {
	appViewState.composerStatus = String(value ?? "");
}
function showActionToast(value) {
	const message = String(value ?? "");
	if (actionToastTimer !== null) {
		clearTimeout(actionToastTimer);
		actionToastTimer = null;
	}
	appViewState.actionToast = message;
	if (!message) return;
	actionToastTimer = setTimeout(() => {
		appViewState.actionToast = "";
		actionToastTimer = null;
	}, 2200);
}
function setCacheSummary(value) {
	appViewState.cacheSummary = String(value ?? "");
}
function showConversation(visible) {
	appViewState.emptyVisible = !visible;
	appViewState.conversationVisible = visible;
}
function setConversationHeading(title, meta) {
	appViewState.headingTitle = String(title ?? "");
	appViewState.headingMeta = String(meta ?? "");
}
function syncSendButton() {
	const waitingNew = state.composingNew && state.pendingNewSend && ![
		"failed",
		"dead_lettered",
		"succeeded"
	].includes(state.pendingNewSend.status);
	const hasTarget = state.composingNew || Boolean(state.selectedId);
	const hasContent = composerHasContent(appViewState.composerValue, attachmentPicker.count());
	const canCompose = state.mode === "chats" && !appViewState.composerDisabled && hasTarget;
	const stopMode = canCompose && shouldShowStopAction(state.selectedChat?.status, state.composingNew, hasContent);
	const probingActivity = Boolean(state.selectedId && state.activityProbes.has(state.selectedId));
	appViewState.composerAction = stopMode ? "stop" : "send";
	appViewState.composerActionDisabled = !canCompose || state.sending || state.stopping || probingActivity || !stopMode && (Boolean(waitingNew) || !hasContent);
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
	appViewState.serverDisplay = display;
	appViewState.serverLabel = knownOnline === false ? "Server · " + display + " · offline" : "Server · " + display;
	appViewState.serverOnline = knownOnline;
	appViewState.live = knownOnline === true;
	appViewState.liveTitle = knownOnline === false ? display + " is offline" : knownOnline === true ? display + " is online" : display + " status unknown";
	logsPanel.setServerTitle(display);
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
	return sidebarChatLastUserAt(chat);
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
function setStatusIcon(status, label) {
	appViewState.syncStatus = iconStatusClasses.has(status) ? status : "neutral";
	appViewState.syncLabel = String(label || "");
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
			status: pendingConversationStatus(chat.status, latest.status),
			preview: latest.message,
			updated_at: Math.max(Number(chat.updated_at || 0), Number(latest.updatedAt || 0)),
			last_user_at: Math.max(Number(chat.last_user_at || chat.created_at || 0), Number(latest.createdAt || 0)),
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
		status: pendingConversationStatus("", pending.status),
		title: truncate(pending.message, 72) || "New chat",
		preview: pending.message,
		message_count: 1,
		job_name: "new chat",
		created_at: pending.createdAt,
		updated_at: pending.updatedAt,
		last_user_at: pending.createdAt,
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
	requestSidebarTop();
}
function syncSidebarSelection() {
	const pendingNewDisplayId = state.composingNew ? pendingConversationDisplayId(state.pendingNewSend) : "";
	sidebarListState.selectedConversationId = sidebarSelectedConversationId(state.selectedId, state.composingNew, pendingNewDisplayId);
}
function renderSidebar(force = false) {
	syncSidebarSelection();
	if (sidebar.isMoving()) {
		sidebarRenderDeferred = true;
		return;
	}
	const filtersActive = Object.values(appViewState.sidebarFilters).some(Boolean);
	const chats = sidebarChats().filter((chat) => sidebarChatMatchesFilters(chat, appViewState.sidebarFilters));
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
		state.pinnedIds.has(chat.id),
		Boolean(chat.unread)
	])) + JSON.stringify(appViewState.sidebarFilters) + String(state.chatListHasMore) + String(state.chatListLoadingMore) + (/* @__PURE__ */ new Date()).toDateString();
	if (!force && fingerprint === state.sidebarFingerprint) return;
	state.sidebarFingerprint = fingerprint;
	state.sidebarRenderedDate = (/* @__PURE__ */ new Date()).toDateString();
	if (!chats.length) {
		sidebarListState.model = {
			emptyState: filtersActive ? "filter" : state.search ? "search" : "empty",
			hasMore: state.chatListHasMore,
			loadingMore: state.chatListLoadingMore,
			groups: []
		};
		return;
	}
	sidebarListState.model = {
		emptyState: "none",
		hasMore: state.chatListHasMore,
		loadingMore: state.chatListLoadingMore,
		groups: groupChats(chats).map(([label, groupedChats]) => ({
			label,
			chats: groupedChats.map((chat) => {
				const broken = chatIsBroken(chat);
				let statusClass = null;
				if (broken) statusClass = "broken";
				else if (chat.status !== "interrupted") statusClass = chat.status === "active" || chat.status === "complete" ? chat.status : "neutral";
				const activityAt = chatActivityAt(chat);
				return {
					id: chat.id,
					optimisticNew: Boolean(chat._optimisticNew),
					statusClass,
					broken,
					statusLabel: broken ? "No ChatGPT response for at least 40 minutes" : String(chat.status || ""),
					title: String(chatTitle(chat)),
					preview: truncate(sidebarChatPreviewText(chat.preview, chat.prompt) || "Waiting for messages…"),
					jobLabel: String(chat.job_name || String(chat.message_count || 0) + " messages"),
					activityAt,
					pinned: state.pinnedIds.has(chat.id),
					unread: Boolean(chat.unread)
				};
			})
		}))
	};
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
		return Boolean(pendingSendActivity(item.status, Boolean(item.sendId), item.retryAfterSeconds, item.retryAt, void 0, item.queuePosition, item.queueEtaAt));
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
			pending_bump_key: Number(item.queuePosition || 0) > 1 ? item.clientId || item.sendId || "" : "",
			pending_delete_key: item.clientId || item.sendId || ""
		});
		const activity = pendingSendActivity(item.status, Boolean(item.sendId), item.retryAfterSeconds, item.retryAt, void 0, item.queuePosition, item.queueEtaAt);
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
	appViewState.pinDisabled = !available;
	appViewState.pinActive = pinned;
	appViewState.pinLabel = pinned ? "Unpin chat" : "Pin chat";
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
	setStatusIcon(broken ? "broken" : chat.status === "active" ? "active" : chat.status === "interrupted" ? "interrupted" : "cached", broken ? "No ChatGPT response for at least 40 minutes" : chat.status === "active" ? "Syncing from SQLite" : chat.status === "interrupted" ? "Last run was interrupted" : "Cached in SQLite");
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
	appViewState.chatSwitching = true;
}
function cancelChatSwitch() {
	state.chatSwitchToken += 1;
	appViewState.chatSwitching = false;
}
function finishChatSwitch(conversationId) {
	if (!appViewState.chatSwitching) return;
	const token = state.chatSwitchToken;
	requestAnimationFrame(() => {
		if (token !== state.chatSwitchToken || state.selectedId !== conversationId) return;
		appViewState.chatSwitching = false;
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
	appViewState.emptyVisible = false;
	appViewState.conversationVisible = true;
	appViewState.composerDisabled = false;
	state.composingNew = false;
	syncSidebarSelection();
	syncComposerDraftTarget();
	syncSendButton();
	appViewState.shareDisabled = false;
	updatePinButton();
	syncSendButton();
	const pendingActivity = [...state.pendingReplies.get(chat.id) || []].reverse().map((item) => pendingSendActivity(item.status, Boolean(item.sendId), item.retryAfterSeconds, item.retryAt, void 0, item.queuePosition, item.queueEtaAt)).find(Boolean);
	if (pendingActivity) appViewState.composerStatus = pendingActivity.statusText;
	else if (!state.sending) appViewState.composerStatus = chat.status === "active" ? "Uses the existing live ChatGPT tab." : chat.status === "interrupted" ? "The last run was interrupted. Sending will reopen this chat." : "Sending will reopen this chat once if its retained tab has expired.";
}
function showMode(mode) {
	state.mode = mode === "logs" ? "logs" : "chats";
	appViewState.mode = state.mode === "logs" ? "logs" : "chats";
	if (state.mode === "logs") {
		cancelChatSwitch();
		state.selectedMetaFingerprint = "";
		const display = displayServerName(state.serverName || location.hostname);
		setConversationHeading(display + " Prompta logs", "journalctl · prompta.service · " + display);
		setStatusIcon("journal", display + " journal");
		appViewState.composerDisabled = true;
		appViewState.shareDisabled = true;
		appViewState.composerStatus = "Switch back to chats to send a message.";
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
	syncSidebarSelection();
	appViewState.emptyVisible = true;
	appViewState.conversationVisible = false;
	conversationRenderer.renderMessageNodes([], false);
	setConversationHeading("Prompta", "Local conversation history");
	setStatusIcon("local", "Local cache");
	appViewState.composerDisabled = true;
	appViewState.shareDisabled = true;
	updatePinButton();
	appViewState.composerPlaceholder = "Message Prompta…";
	appViewState.composerStatus = "";
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
	appViewState.mode = "chats";
	syncSidebarSelection();
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
		pending?.queueEtaAt || 0,
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
				pending_bump_key: Number(pending.queuePosition || 0) > 1 ? pending.clientId || pending.sendId || "" : "",
				pending_delete_key: pending.clientId || pending.sendId || ""
			}];
			const activity = pendingSendActivity(pending.status, Boolean(pending.sendId), pending.retryAfterSeconds, pending.retryAt, void 0, pending.queuePosition, pending.queueEtaAt);
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
			showConversation(true);
			conversationRenderer.renderMessageNodes(messages, true);
			conversationRenderer.restoreConversationViewport(viewportSnapshot, enteringNewChat);
		} else {
			showConversation(false);
			conversationRenderer.renderMessageNodes([], false);
		}
		setConversationHeading("New chat", pending ? "Queued through the live Prompta session" : "Starts a fresh ChatGPT conversation");
		setStatusIcon(pending ? "queued" : "new", pending ? "Send queued" : "Fresh conversation");
		appViewState.composerDisabled = false;
		syncSendButton();
		appViewState.shareDisabled = true;
		updatePinButton();
		appViewState.composerPlaceholder = "Start a new chat…";
		const activity = pending ? pendingSendActivity(pending.status, Boolean(pending.sendId), pending.retryAfterSeconds, pending.retryAt, void 0, pending.queuePosition, pending.queueEtaAt) : null;
		setComposerStatus(pending ? ["failed", "dead_lettered"].includes(pending.status) ? pending.status === "dead_lettered" ? "Send exhausted its retry budget. Retry to enqueue it again." : "Send failed. The error is shown in the chat." : activity?.statusText || "Sent. Waiting for the cached response…" : "");
	}
	updateComposerActionButton();
	if (enteringNewChat) {
		appViewState.mode = "chats";
		history.replaceState(null, "", `${location.pathname}${location.search}`);
		renderSidebar();
		scrollSidebarToNewest();
		sidebar.close();
		if (!waiting && finePointer.current) requestComposerFocus();
	}
}
async function fetchJson(url, timeoutMs = 1e4, controller = new AbortController()) {
	const timeout = setTimeout(() => controller.abort(), timeoutMs);
	try {
		const response = await fetch(url, {
			cache: "no-store",
			signal: controller.signal
		});
		if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
		return await response.json();
	} finally {
		clearTimeout(timeout);
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
		timeout = setTimeout(() => resolve(null), 500);
	})]);
	if (timeout !== void 0) clearTimeout(timeout);
	if (!cached) return false;
	const [cachedChats, cachedSummaries] = cached;
	const sidebarSnapshot = cachedSummaries.length ? cachedSummaries : cachedChats;
	if (!sidebarSnapshot.length || state.search) return false;
	const unique = /* @__PURE__ */ new Map();
	for (const chat of sidebarSnapshot) if (chat?.id && !unique.has(chat.id)) unique.set(chat.id, chat);
	state.chats = sortSidebarChats(Array.from(unique.values()), state.pinnedIds);
	state.chatOrderScope = "";
	const activeCount = state.chats.filter((chat) => chat.status === "active").length;
	setCacheSummary(sidebarChatCountSummary(state.chats.length, activeCount, state.search));
	const initialId = conversationIdFromHash(location.hash) || state.chats[0]?.id || "";
	if (initialId) {
		state.selectedId = initialId;
		const chat = recentChatCache.getMemory(initialId);
		if (chat) {
			state.selectedUpdatedAt = chat.updated_at;
			renderConversation(chat);
		} else {
			conversationRenderer.renderLoadingState();
			showConversation(true);
		}
	}
	renderSidebar();
	return true;
}
async function loadServerIdentity() {
	try {
		const payload = await fetchJson("api/health");
		setServerStatus(payload.server, payload.online);
		appViewState.unattended = payload.unattended === true;
		appViewState.unattendedSendGapSeconds = Number(payload.send_gap_seconds || 60);
		const head = String(payload.head || "").trim().toLowerCase();
		deploymentMonitor.observeHead(head);
		appViewState.headLabel = head ? head : "unknown";
		appViewState.headTitle = head ? "UI commit " + head : "UI commit unavailable";
	} catch (error) {
		setServerStatus(state.serverName || location.hostname, false);
		console.warn("Could not load Prompta server identity", error);
	}
}
async function toggleUnattendedMode() {
	if (appViewState.unattendedUpdating) return;
	const next = !appViewState.unattended;
	appViewState.unattendedUpdating = true;
	try {
		const payload = await postJsonRequest("api/mode", { unattended: next }, 1, 1e4);
		appViewState.unattended = payload.unattended === true;
		appViewState.unattendedSendGapSeconds = Number(payload.send_gap_seconds || 60);
		showActionToast(appViewState.unattended ? "Unattended mode · no chat polling · " + appViewState.unattendedSendGapSeconds + "s send gap" : "Unattended mode off · normal chat polling restored");
	} catch (error) {
		showActionToast("Could not change unattended mode: " + String(error).replace(/^Error:\s*/, ""));
	} finally {
		appViewState.unattendedUpdating = false;
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
				queueEtaAt: Number(job.queue_eta_at || 0),
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
async function loadOlderChats() {
	if (state.chatListLoadingMore || !state.chatListHasMore || state.chatListLimit >= 500) return;
	state.chatListLoadingMore = true;
	state.chatListLimit = Math.min(500, state.chatListLimit + CHAT_LIST_PAGE_SIZE);
	state.sidebarFingerprint = "";
	renderSidebar(true);
	try {
		await loadChats();
	} finally {
		state.chatListLoadingMore = false;
		state.sidebarFingerprint = "";
		renderSidebar(true);
	}
}
async function loadChats(forceSelectedRefresh = false) {
	const requestId = ++state.chatsRequestId;
	chatsRequestController?.abort();
	const requestController = new AbortController();
	chatsRequestController = requestController;
	try {
		const payload = await fetchJson(chatListRequestUrl(state.search, state.pinnedIds, state.chatListLimit), 1e4, requestController);
		if (requestId !== state.chatsRequestId) return;
		const chats = payload.chats || [];
		state.chatListHasMore = Boolean(payload.has_more);
		promoteServerPendingPins(chats);
		reconcileOptimisticNew(chats);
		const orderedChats = sortSidebarChats(chats, state.pinnedIds);
		if (!state.search) {
			recentChatCache.rememberSummaries(orderedChats);
			queueChatPrefetch(orderedChats);
		}
		completionNotifications.trackCompletions(chats);
		state.chats = orderedChats;
		state.chatOrderScope = state.search;
		const activeCount = state.chats.filter((chat) => chat.status === "active").length;
		setCacheSummary(sidebarChatCountSummary(state.chats.length, activeCount, state.search));
		const hashId = conversationIdFromHash(location.hash);
		if (!state.selectedId && hashId) state.selectedId = hashId;
		state.selectedId = selectedConversationAfterChatRefresh(state.selectedId, state.composingNew, state.chats);
		renderSidebar();
		if (state.mode === "chats") {
			if (state.selectedId) {
				if (shouldRefreshSelectedChat(state.chats.find((chat) => chat.id === state.selectedId), state.selectedUpdatedAt, state.selectedFingerprint, forceSelectedRefresh)) await loadSelectedChat();
			} else if (!state.composingNew) clearConversation();
		}
	} catch (error) {
		if (requestId !== state.chatsRequestId) return;
		appViewState.live = false;
		setCacheSummary("Cache unavailable");
		console.error(error);
	} finally {
		if (chatsRequestController === requestController) chatsRequestController = null;
	}
}
async function probeHistoricalActivity(conversationId) {
	if (appViewState.unattended || !conversationId || !shouldProbeHistoricalActivity(state.selectedChat?.status)) return;
	const now = Date.now();
	const lastProbeAt = Number(state.activityProbeAt.get(conversationId) || 0);
	if (state.activityProbes.has(conversationId) || now - lastProbeAt < HISTORICAL_ACTIVITY_PROBE_TTL_MS) return;
	state.activityProbeAt.set(conversationId, now);
	state.activityProbes.add(conversationId);
	if (state.selectedId === conversationId) {
		setComposerStatus("Checking whether ChatGPT is still running…");
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
		if (state.selectedId === conversationId) setComposerStatus("Could not verify whether this interrupted chat is still running.");
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
		showConversation(true);
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
		const chat = await fetchChatDetail(selectedId);
		if (!chat || requestId !== state.selectedRequestId || selectedId !== state.selectedId || chat.id !== state.selectedId) return;
		if (state.pendingNewId === chat.id && !state.pendingNewSend) state.pendingNewId = null;
		state.selectedUpdatedAt = chat.updated_at;
		recentChatCache.remember(chat);
		renderConversation(chat);
		markChatRead(chat.id);
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
	if (isUnresolvedPendingNewConversation(state.pendingNewSend, id)) {
		rememberConversationViewport(state.selectedId);
		state.pendingNewId = state.pendingNewSend?.conversationId || null;
		renderNewChat();
		return;
	}
	markChatRead(id);
	if (id === state.selectedId) {
		if (!state.selectedChat || state.selectedChat.id !== id) await loadSelectedChat();
		return;
	}
	rememberConversationViewport(state.selectedId);
	beginChatSwitch();
	const pendingNew = state.pendingNewSend?.conversationId === id ? state.pendingNewSend : null;
	state.composingNew = false;
	state.pendingNewId = pendingNew ? id : null;
	appViewState.composerPlaceholder = "Message Prompta…";
	state.selectedId = id;
	state.selectedUpdatedAt = null;
	state.selectedFingerprint = "";
	state.selectedMetaFingerprint = "";
	state.selectedChat = null;
	history.replaceState(null, "", `#/${encodeURIComponent(id)}`);
	syncSidebarSelection();
	await loadSelectedChat();
}
async function runScheduleSlashCommand(command, originalMessage) {
	state.sending = true;
	appViewState.composerDisabled = true;
	attachmentPicker.setDisabled(true);
	clearComposerDraft();
	appViewState.composerValue = "";
	updateComposerActionButton();
	setComposerStatus("Saving schedule…");
	try {
		const result = await postJsonRequest("api/schedule", {
			interval_minutes: command.intervalMinutes,
			prompt: command.prompt
		});
		const server = displayServerName(result.server || state.serverName || location.hostname);
		const interval = formatScheduleInterval(Number(result.interval_minutes));
		setComposerStatus((result.created === false ? "Already scheduled" : "Scheduled") + " on " + server + ": every " + interval + " · " + command.prompt);
	} catch (error) {
		appViewState.composerValue = originalMessage;
		persistComposerDraft();
		setComposerStatus("Schedule failed: " + String(error).replace(/^Error:\s*/, ""));
		console.error(error);
	} finally {
		state.sending = false;
		appViewState.composerDisabled = false;
		attachmentPicker.setDisabled(false);
		syncSendButton();
		if (finePointer.current) requestComposerFocus();
	}
}
async function runAtSlashCommand(command, originalMessage) {
	state.sending = true;
	appViewState.composerDisabled = true;
	attachmentPicker.setDisabled(true);
	clearComposerDraft();
	appViewState.composerValue = "";
	updateComposerActionButton();
	setComposerStatus("Saving one-time schedule…");
	try {
		setComposerStatus("Scheduled on " + displayServerName((await postJsonRequest("api/schedule-at", {
			run_at_epoch: command.runAtEpoch,
			prompt: command.prompt
		})).server || state.serverName || location.hostname) + ": " + command.runAtLabel + " · " + command.prompt);
	} catch (error) {
		appViewState.composerValue = originalMessage;
		persistComposerDraft();
		setComposerStatus("Schedule failed: " + String(error).replace(/^Error:\s*/, ""));
		console.error(error);
	} finally {
		state.sending = false;
		appViewState.composerDisabled = false;
		attachmentPicker.setDisabled(false);
		syncSendButton();
		if (finePointer.current) requestComposerFocus();
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
		item.queuePosition || 0,
		item.queueEtaAt || 0
	]);
	Object.assign(item, updates);
	const changed = JSON.stringify([
		item.status || "",
		item.error || "",
		item.retryAfterSeconds || 0,
		item.retryAt || 0,
		item.retryAttempt || 0,
		item.queuePosition || 0,
		item.queueEtaAt || 0
	]) !== previous;
	if (changed) item.updatedAt = Date.now() / 1e3;
	return changed;
}
function setPendingDeleteBusy(deleteKey, busy) {
	conversationRenderer.setPendingDeleteBusy(deleteKey, busy);
}
async function bumpPendingSend(bumpKey) {
	let pending = null;
	const conversationId = state.selectedId || "";
	if (state.pendingNewSend && (state.pendingNewSend.clientId === bumpKey || state.pendingNewSend.sendId === bumpKey)) pending = state.pendingNewSend;
	else if (conversationId) pending = (state.pendingReplies.get(conversationId) || []).find((item) => item.clientId === bumpKey || item.sendId === bumpKey) || null;
	if (!pending) return;
	const sendId = String(pending.sendId || "");
	if (!sendId) {
		setComposerStatus("Message is still entering the queue. Try sending it next again.");
		return;
	}
	try {
		const job = await postJsonRequest("api/sends/" + encodeURIComponent(sendId) + "/bump", {});
		pending.queuePosition = Number(job.queue_position || 1);
		pending.queueEtaAt = Number(job.queue_eta_at || 0);
		pending.updatedAt = Date.now() / 1e3;
		if (state.pendingNewSend === pending && state.composingNew) renderNewChat();
		else if (state.selectedChat?.id === conversationId) {
			state.selectedFingerprint = "";
			renderConversation(state.selectedChat);
		}
		setComposerStatus("Queued message moved to the front.");
	} catch (error) {
		console.warn("Could not bump pending Prompta send", error);
		setComposerStatus("Could not move the pending message to the front.");
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
	const canDiscardLocally = !sendId && ["failed", "dead_lettered"].includes(String(pending.status || ""));
	if (!sendId && !canDiscardLocally) {
		setComposerStatus("Message is still entering the queue. Try deleting again.");
		return;
	}
	if (sendId) {
		setPendingDeleteBusy(deleteKey, true);
		try {
			await deleteRequest("api/sends/" + encodeURIComponent(sendId));
		} catch (error) {
			setPendingDeleteBusy(deleteKey, false);
			console.warn("Could not delete pending Prompta send", error);
			setComposerStatus("Could not delete the pending message.");
			return;
		}
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
		setComposerStatus("Message is still entering the queue. Try editing again.");
		return;
	}
	try {
		await deleteRequest("api/sends/" + encodeURIComponent(sendId));
	} catch (error) {
		console.warn("Could not cancel pending Prompta send for editing", error);
		setComposerStatus("Could not edit the pending message.");
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
	appViewState.composerValue = pending.message || "";
	persistComposerDraft();
	syncSendButton();
	renderSidebar();
	if ((pending.attachmentNames || []).length) setComposerStatus("Editing pending message. Reattach the files before sending.");
	else setComposerStatus("Editing pending message.");
	requestComposerFocus(true);
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
				setComposerStatus("Send status unavailable. Prompta may still be running it; reconnecting…");
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
			const nextQueueEtaAt = Number(job.queue_eta_at || 0);
			if (nextConversationId) promotePendingConversationPin(pendingNewSend, nextConversationId);
			const changed = pendingNewSend.status !== status || pendingNewSend.error !== nextError || pendingNewSend.conversationId !== nextConversationId || pendingNewSend.retryAfterSeconds !== nextRetryAfterSeconds || pendingNewSend.retryAt !== nextRetryAt || pendingNewSend.retryAttempt !== nextRetryAttempt || pendingNewSend.queuePosition !== nextQueuePosition || pendingNewSend.queueEtaAt !== nextQueueEtaAt;
			Object.assign(pendingNewSend, {
				status,
				error: nextError,
				conversationId: nextConversationId,
				retryAfterSeconds: nextRetryAfterSeconds,
				retryAt: nextRetryAt,
				retryAttempt: nextRetryAttempt,
				queuePosition: nextQueuePosition,
				queueEtaAt: nextQueueEtaAt
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
				appViewState.composerPlaceholder = "Message Prompta…";
				setComposerStatus("Sent. Waiting for the cached response…");
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
			queuePosition: Number(job.queue_position || 0),
			queueEtaAt: Number(job.queue_eta_at || 0)
		})) renderSidebar();
		if (state.selectedId === conversationId) await loadSelectedChat();
		if (status === "succeeded") {
			setComposerStatus(appViewState.unattended ? "Sent. Unattended mode is not polling ChatGPT for the response." : "Sent. Waiting for the cached response…");
			await loadChats();
			return;
		}
		if (["failed", "dead_lettered"].includes(status)) {
			setComposerStatus(status === "dead_lettered" ? "Send exhausted its retry budget. Retry to enqueue it again." : "Send failed. The error is shown in the chat.");
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
	appViewState.composerValue = pending.message || "";
	syncSendButton();
	if ((pending.attachmentNames || []).length) {
		setComposerStatus("Reattach the files, then send again.");
		requestComposerFocus();
		return;
	}
	await sendSelectedMessage();
}
async function stopSelectedChat() {
	const conversationId = state.selectedId;
	if (!conversationId || state.mode !== "chats" || state.stopping) return;
	state.stopping = true;
	syncSendButton();
	setComposerStatus("Stopping response…");
	try {
		await postJsonRequest("api/chats/" + encodeURIComponent(conversationId) + "/stop", {});
		setComposerStatus("Stopped.");
		state.selectedFingerprint = "";
		state.selectedUpdatedAt = null;
		await loadSelectedChat();
		await loadChats();
	} catch (error) {
		setComposerStatus("Stop failed: " + String(error).replace(/^Error:\s*/, ""));
		console.error(error);
	} finally {
		state.stopping = false;
		syncSendButton();
	}
}
async function sendSelectedMessage() {
	const message = appViewState.composerValue.trim();
	const creatingNew = state.composingNew;
	const conversationId = state.selectedId;
	const attachments = attachmentPicker.snapshot();
	if (!message || state.mode !== "chats" || state.sending) return;
	if (message.toLowerCase() === "/logs") {
		clearComposerDraft();
		appViewState.composerValue = "";
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
			setComposerStatus("Scheduled prompts do not include attachments.");
			return;
		}
		if ("error" in scheduleCommand) {
			setComposerStatus(scheduleCommand.error);
			return;
		}
		await runScheduleSlashCommand(scheduleCommand, message);
		return;
	}
	const atCommand = parseAtSlashCommand(message);
	if (atCommand) {
		if (attachments.length) {
			setComposerStatus("Scheduled prompts do not include attachments.");
			return;
		}
		if ("error" in atCommand) {
			setComposerStatus(atCommand.error);
			return;
		}
		await runAtSlashCommand(atCommand, message);
		return;
	}
	if (!creatingNew && isUnresolvedPendingNewConversation(state.pendingNewSend, conversationId)) {
		state.pendingNewId = state.pendingNewSend?.conversationId || null;
		renderNewChat();
		setComposerStatus("Wait for the pending chat to start before sending another message.");
		return;
	}
	if (!creatingNew && !conversationId) return;
	let serializedAttachments = [];
	if (attachments.length) {
		state.sending = true;
		appViewState.composerDisabled = true;
		appViewState.composerActionDisabled = true;
		attachmentPicker.setDisabled(true);
		setComposerStatus("Preparing attachments…");
		try {
			serializedAttachments = await attachmentPicker.serialize();
		} catch (error) {
			state.sending = false;
			appViewState.composerDisabled = false;
			attachmentPicker.setDisabled(false);
			syncSendButton();
			setComposerStatus("Attachment failed: " + String(error).replace(/^Error:\s*/, ""));
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
	appViewState.composerActionDisabled = true;
	clearComposerDraft();
	appViewState.composerValue = "";
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
		const coalescedReply = !creatingNew ? (state.pendingReplies.get(conversationId || "") || []).find((item) => item !== pending && item.sendId === result.send_id) : null;
		if (coalescedReply) {
			const coalescedUiReply = coalescedReply;
			coalescedReply.message = [coalescedReply.message, pending.message].filter(Boolean).join("\n");
			coalescedUiReply.attachmentNames = [...coalescedUiReply.attachmentNames || [], ...pending.attachmentNames || []];
			coalescedReply.attachments = [...coalescedReply.attachments || [], ...pending.attachments || []];
			coalescedReply.status = result.status || "queued";
			coalescedReply.queuePosition = Number(result.queue_position || 0);
			coalescedReply.updatedAt = Date.now() / 1e3;
			state.pendingReplies.set(conversationId || "", (state.pendingReplies.get(conversationId || "") || []).filter((item) => item !== pending));
			if (attachments.length) attachmentPicker.clear();
			state.selectedFingerprint = "";
			if (state.selectedChat?.id === conversationId) renderConversation(state.selectedChat);
			renderSidebar();
			return;
		}
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
		const errorMessage = error instanceof Error ? error.message : String(error);
		let savedOffline = false;
		if (isPostJsonTransportError(error)) try {
			await offlineOutbox.enqueue({
				operation: creatingNew ? "new_chat" : "reply",
				targetChatId: creatingNew ? null : conversationId || null,
				message,
				attachments: serializedAttachments,
				clientId: String(pending.clientId || ""),
				createdAt: now * 1e3,
				lastError: errorMessage
			});
			savedOffline = true;
			if (attachments.length) attachmentPicker.clear();
		} catch (outboxError) {
			console.error("Could not persist failed post to the offline outbox", outboxError);
		}
		pending.status = "failed";
		pending.error = savedOffline ? "Saved offline for retry." : errorMessage;
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
			appViewState.composerDisabled = false;
			syncSendButton();
			if (finePointer.current) requestComposerFocus();
		} else if (creatingNew && state.pendingNewSend?.status === "failed" && state.mode === "chats") {
			appViewState.composerDisabled = false;
			syncSendButton();
			if (finePointer.current) requestComposerFocus();
		}
		updateComposerActionButton();
	}
}
async function copySelectedChatUrl() {
	if (!state.selectedId) return;
	const url = new URL(location.href);
	url.hash = "/" + encodeURIComponent(state.selectedId);
	const message = await copyText(url.toString()) ? "Chat link copied." : "Could not copy the chat link.";
	setComposerStatus(message);
	showActionToast(message);
}
function refreshDisplayedTimes() {
	appViewState.clockTick = Math.floor(Date.now() / 6e4) * 6e4;
	if (state.composingNew && (["rate_limited", "retrying"].includes(state.pendingNewSend?.status || "") || state.pendingNewSend?.status === "queued" && Number(state.pendingNewSend?.queueEtaAt || 0) > 0)) {
		state.newChatFingerprint = "";
		renderNewChat();
	} else if (state.selectedId && (state.pendingReplies.get(state.selectedId) || []).some((item) => ["rate_limited", "retrying"].includes(item.status || "") || item.status === "queued" && Number(item.queueEtaAt || 0) > 0)) {
		state.selectedFingerprint = "";
		loadSelectedChat();
	}
	const sidebarRows = sidebarListState.model.groups.flatMap((group) => group.chats);
	if ((/* @__PURE__ */ new Date()).toDateString() !== state.sidebarRenderedDate || sidebarHealthNeedsRefresh(sidebarRows, sidebarChats(), appViewState.sidebarFilters.broken, appViewState.clockTick / 1e3)) renderSidebar(true);
	if (state.mode === "chats" && state.selectedChat && state.selectedChat.id === state.selectedId && !state.composingNew) {
		state.selectedMetaFingerprint = "";
		renderConversationMeta(state.selectedChat, state.selectedVisibleMessageCount);
	}
}
async function startApp() {
	deploymentMonitor.registerServiceWorker();
	loadServerIdentity();
	await hydratePinnedIds();
	await hydratePendingSends();
	if (!await hydrateRecentChatCache()) {
		conversationRenderer.renderLoadingState();
		showConversation(true);
	}
	appViewState.bootComplete = true;
	await loadChats(true);
	liveUpdates.start();
}
var clientScope, recentChatCache, offlineOutbox, INITIAL_CHAT_LIST_LIMIT, CHAT_LIST_PAGE_SIZE, clientSessionId, actionToastTimer, chatDetailRequests, queuedPrefetches, queuedPrefetchSet, prefetchedChatRevisions, chatPrefetchRunning, state, sidebarRenderDeferred, sidebar, jobsDialog, conversationRenderer, attachmentPicker, logsPanel, deploymentMonitor, completionNotifications, liveUpdates, iconStatusClasses, chatsRequestController, HISTORICAL_ACTIVITY_PROBE_TTL_MS, searchTimer;
var init_app = __esmMin((() => {
	init_clientLogic();
	init_recentChatCache();
	init_offlineOutbox();
	init_appViewState_svelte();
	init_clipboard();
	init_browserState_svelte();
	init_appActions_svelte();
	init_sidebarState_svelte();
	init_conversationRenderer();
	init_conversationLogic();
	init_uiControllers();
	init_deploymentMonitor();
	init_liveUpdates();
	init_completionNotifications();
	init_clientStorage();
	clientScope = location.pathname.replace(/\/$/, "") || "/";
	recentChatCache = new RecentChatCache(clientScope, 20);
	offlineOutbox = new OfflineOutbox(clientScope);
	INITIAL_CHAT_LIST_LIMIT = 50;
	CHAT_LIST_PAGE_SIZE = 50;
	clientSessionId = loadClientSessionId();
	actionToastTimer = null;
	chatDetailRequests = /* @__PURE__ */ new Map();
	queuedPrefetches = [];
	queuedPrefetchSet = /* @__PURE__ */ new Set();
	prefetchedChatRevisions = /* @__PURE__ */ new Map();
	chatPrefetchRunning = false;
	state = {
		chats: [],
		selectedId: null,
		selectedUpdatedAt: null,
		selectedFingerprint: "",
		search: "",
		sidebarFingerprint: "",
		sidebarRenderedDate: "",
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
		chatListLimit: INITIAL_CHAT_LIST_LIMIT,
		chatListHasMore: false,
		chatListLoadingMore: false,
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
	sidebarRenderDeferred = false;
	configureSidebar(() => {
		if (!sidebarRenderDeferred) return;
		sidebarRenderDeferred = false;
		renderSidebar();
	});
	sidebar = {
		close: closeSidebar,
		open: openSidebar,
		isMoving: () => sidebarState.moving
	};
	sidebarListActions.onSelect = (chatId, optimisticNew) => {
		if (optimisticNew && state.pendingNewSend) {
			renderNewChat();
			sidebar.close();
			return;
		}
		selectChat(chatId);
	};
	sidebarListActions.onPin = (chatId) => {
		setChatPinned(chatId, !state.pinnedIds.has(chatId));
		renderSidebar(true);
		updatePinButton();
	};
	sidebarListActions.onPrefetch = (chatId) => {
		if (recentChatCache.getMemory(chatId)) return;
		fetchChatDetail(chatId).catch(() => {});
	};
	sidebarListActions.onLoadMore = () => {
		loadOlderChats();
	};
	jobsDialog = getJobsDialog();
	conversationRenderer = createConversationRenderer({
		onRetry: retryFailedSend,
		onBump: bumpPendingSend,
		onDelete: deletePendingSend,
		onEdit: editPendingSend
	});
	attachmentPicker = getAttachmentPicker();
	attachmentPicker.configure({
		onChange: syncSendButton,
		setStatus: (message) => {
			appViewState.composerStatus = message;
		}
	});
	logsPanel = getLogsPanel();
	deploymentMonitor = createDeploymentMonitor({ onUpdateAvailable: () => {
		appViewState.updateAvailable = true;
	} });
	appActions.onApplyUpdate = () => {
		appViewState.updateApplying = true;
		deploymentMonitor.applyUpdate();
	};
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
		onStreamError: () => {
			appViewState.live = false;
		},
		onPageShow: () => deploymentMonitor.handleVisibilityChange()
	});
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
	appActions.onSearch = (value) => {
		appViewState.searchValue = value;
		clearTimeout(searchTimer);
		searchTimer = setTimeout(() => {
			state.search = value.trim();
			state.chatListLimit = INITIAL_CHAT_LIST_LIMIT;
			state.chatListHasMore = false;
			state.sidebarFingerprint = "";
			loadChats();
		}, 140);
	};
	appActions.onSidebarFilter = (filter) => {
		appViewState.sidebarFilters[filter] = !appViewState.sidebarFilters[filter];
		state.sidebarFingerprint = "";
		renderSidebar(true);
	};
	appActions.onMarkAllRead = () => {
		markAllChatsRead();
	};
	appActions.onNewChat = () => {
		state.pendingNewSend = null;
		state.newChatFingerprint = "";
		renderNewChat();
	};
	appActions.onPin = toggleSelectedPin;
	appActions.onShare = () => void copySelectedChatUrl();
	appActions.onUnattendedMode = () => void toggleUnattendedMode();
	appActions.onSubmit = () => {
		if (appViewState.composerAction === "stop") stopSelectedChat();
		else sendSelectedMessage();
	};
	appActions.onComposerInput = (value) => {
		appViewState.composerValue = value;
		persistComposerDraft();
		syncSendButton();
	};
	appActions.onHashChange = () => {
		const id = conversationIdFromHash(location.hash);
		if (id && id !== state.selectedId) selectChat(id);
	};
	appActions.onPageHide = () => liveUpdates.handlePageHide();
	appActions.onPageShow = () => liveUpdates.handlePageShow();
	startApp();
}));
//#endregion
//#region src/ui/main.ts
init_index_client$1();
var target = document.querySelector("#app");
if (!target) throw new Error("Missing #app mount target");
mount(App, {
	target,
	props: { serverName: target.dataset.serverName?.trim() || "local" }
});
await Promise.resolve().then(() => (init_app(), app_exports));
//#endregion
