import { test } from "node:test";
import assert from "node:assert/strict";
import { accessAllows, alignedEnabled, drawOrder, stateKey, unionBbox } from "../js/policy.js";
import { RENDERERS, drawableChannels, paletteFor, breaksFit, breaksProblem } from "../js/map/renderers.js";
import { PALETTES } from "../js/map/colors.js";

const layer = (channels, extra = {}) => ({ channels, ...extra });

test("access is decided by access state and tier, never by the renderer", () => {
  for (const renderer of Object.keys(RENDERERS)) {
    assert.equal(accessAllows({ renderer, access: "restricted", layer: layer({}) }, "public"), false, renderer);
    assert.equal(accessAllows({ renderer, access: "open", layer: layer({}, { accessTier: "private" }) }, "public"), false, renderer);
    assert.equal(accessAllows({ renderer, access: "open", layer: layer({}, { accessTier: "private" }) }, "private"), true, renderer);
    assert.equal(accessAllows({ renderer, access: "open", layer: layer({}, { accessTier: "public" }) }, "private"), true, renderer);
  }
});

test("panel state is keyed by source and panel: two dashboards with the same panel ids do not share it", () => {
  assert.notEqual(stateKey("hamburg", "panel-risk"), stateKey("bremen", "panel-risk"));
  assert.equal(stateKey("hamburg", "panel-risk"), stateKey("hamburg", "panel-risk"));
});

test("a classifying renderer draws only declared breaks in its shape, on every path", () => {
  const withBreaks = layer({ x: { column: "a", breaks: [1, 2, 3] }, y: { column: "b", breaks: [1, 2, 3] } });
  const noBreaks = layer({ x: { column: "a", breaks: [] }, y: { column: "b", breaks: [1, 2, 3] } });
  const noColumn = layer({ x: { column: null, breaks: [1, 2, 3] }, y: { column: "b", breaks: [1, 2, 3] } });
  assert.equal(drawableChannels("bivariate-map", withBreaks), true);
  assert.equal(drawableChannels("bivariate-map", noBreaks), false);
  assert.equal(drawableChannels("bivariate-map", noColumn), false);
  assert.equal(drawableChannels("single-variable-map", layer({ value: { column: "v", breaks: [] } })), false);
  assert.equal(drawableChannels("outline", layer({})), true);
  assert.equal(drawableChannels("claims-list", layer({})), false);
});

test("a composed colorScheme changes the palette when the renderer knows it, else the default is used", () => {
  assert.equal(paletteFor("bivariate-map", layer({}, { style: { colorScheme: "yellow-purple" } })), PALETTES["yellow-purple"]);
  assert.equal(paletteFor("bivariate-map", layer({}, { style: { colorScheme: "rainbow" } })), PALETTES["yellow-purple"]);
  assert.equal(paletteFor("single-variable-map", layer({}, { style: { colorScheme: null } })), PALETTES.greys);
  assert.equal(paletteFor("bivariate-background", layer({}, { style: { colorScheme: "greys" } })), PALETTES.greys);
});

test("stacking: exclusive-group panels below, then position, then key", () => {
  const order = drawOrder([
    { key: "c", position: 1, exclusiveGroup: null }, { key: "a", position: 3, exclusiveGroup: "background" },
    { key: "b", position: 2, exclusiveGroup: "background" }, { key: "d", position: 1, exclusiveGroup: null },
  ]).map((p) => p.key);
  assert.deepEqual(order, ["b", "a", "c", "d"]);
});

test("the footprint of several cities is the union of their declared boxes; undeclared boxes are skipped", () => {
  assert.deepEqual(unionBbox([[9.7, 53.4, 10.3, 53.7], [8.5, 53.0, 9.0, 53.2]]), [8.5, 53.0, 10.3, 53.7]);
  assert.deepEqual(unionBbox([null, [8.5, 53.0, 9.0, 53.2], [1, 2]]), [8.5, 53.0, 9.0, 53.2]);
  assert.equal(unionBbox([]), null);
});

test("several cities on one map share the lead city's enabled flags per renderer", () => {
  const lead = [{ key: "riskMap", renderer: "bivariate-map" }, { key: "sv", renderer: "single-variable-map" }, { key: "drivers", renderer: "bivariate-background" }];
  const other = [{ key: "panel-risk", renderer: "bivariate-map" }, { key: "panel-sv", renderer: "single-variable-map" }, { key: "panel-drivers", renderer: "bivariate-background" }];
  const enabled = { [stateKey("hamburg", "riskMap")]: true, [stateKey("hamburg", "sv")]: false, [stateKey("hamburg", "drivers")]: true,
    [stateKey("bremen", "panel-risk")]: true, [stateKey("bremen", "panel-sv")]: true, [stateKey("bremen", "panel-drivers")]: false };
  const out = alignedEnabled(enabled, "hamburg", lead, "bremen", other);
  assert.equal(out[stateKey("bremen", "panel-sv")], false);
  assert.equal(out[stateKey("bremen", "panel-drivers")], true);
  assert.equal(out[stateKey("hamburg", "sv")], false, "the lead is unchanged");
});

test("breaks must fit the renderer: classes - 1 finite increasing numbers, else the layer is not drawn and says why", () => {
  assert.equal(breaksFit([1, 2, 3], 4), true);
  assert.equal(breaksFit([1, 2], 4), false, "too few");
  assert.equal(breaksFit([1, 2, 3, 4], 4), false, "too many");
  assert.equal(breaksFit([1, 3, 2], 4), false, "not increasing");
  assert.equal(breaksFit([1, null, 3], 4), false, "a null break");
  assert.equal(breaksFit([1, 2], 3), true);
  const four = { x: { column: "a", breaks: [1, 2, 3] }, y: { column: "b", breaks: [1, 2, 3] } };
  assert.equal(drawableChannels("bivariate-map", layer(four)), true);
  assert.equal(drawableChannels("bivariate-map", layer({ ...four, y: { column: "b", breaks: [1, 2] } })), false);
  assert.equal(drawableChannels("bivariate-background", layer({ x: { column: "a", breaks: [1, 2] }, y: { column: "b", breaks: [1, 2] } })), true);
  assert.equal(drawableChannels("single-variable-map", layer({ value: { column: "a", breaks: [1, 2] } })), false, "4 classes need 3 breaks");
  assert.match(breaksProblem("bivariate-map", layer({ ...four, y: { column: "b", breaks: [1, 2] } })), /declares 2 breaks; this renderer draws 4 classes/);
  assert.match(breaksProblem("single-variable-map", layer({ value: { column: "a", breaks: [] } })), /no declared class breaks/);
  assert.equal(breaksProblem("outline", layer({})), null);
});
