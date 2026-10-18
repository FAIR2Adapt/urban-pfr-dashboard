import { test } from "node:test";
import assert from "node:assert/strict";
import { axisTitle, axisUnit, classRanges, formatBreak, formatValue, statusText } from "../js/map/classes.js";

test("breaks are shown as the data states them, short", () => {
  assert.equal(formatBreak(0.63046683), "0.63");
  assert.equal(formatBreak(2.11474288), "2.11");
  assert.equal(formatBreak(0.00010378), "0.000104");
  assert.equal(formatBreak(0.00028887), "0.000289");
  assert.equal(formatBreak(1.508e-5), "1.5e-5");
  assert.equal(formatBreak(12.5), "12.5");
  assert.equal(formatBreak(0), "0");
  assert.equal(formatBreak("x"), "x");
});

test("n breaks give n+1 labelled classes, class 0 below the first break", () => {
  assert.deepEqual(classRanges([0.1, 0.2, 0.3]), ["≤ 0.1", "0.1 – 0.2", "0.2 – 0.3", "> 0.3"]);
  assert.deepEqual(classRanges([0.5]), ["≤ 0.5", "> 0.5"]);
  assert.deepEqual(classRanges([0.12341, 0.12349, 0.5]), ["≤ 0.12341", "0.12341 – 0.12349", "0.12349 – 0.5", "> 0.5"], "neighbours that round alike get more digits");
  assert.deepEqual(classRanges([]), []);
  assert.deepEqual(classRanges(null), []);
});

test("the threshold status reads as stated, nothing assumed when absent", () => {
  assert.equal(statusText("provisional_pending_scientific_validation"), "provisional, pending scientific validation");
  assert.equal(statusText("validated_2026-09"), "validated 2026-09");
  assert.equal(statusText(""), "");
  assert.equal(statusText(undefined), "");
});

test("an axis is titled by the object's description of the bound column, then the key, then the column", () => {
  const layer = { variables: { risk_wellbeing: "PFRWB_smoothed", svi: "SVI" },
    variableInfo: { PFRWB_smoothed: { key: "risk_wellbeing", description: "pluvial flood risk, well-being (smoothed index)", unit: "index 0-1" } } };
  assert.equal(axisTitle({ column: "PFRWB_smoothed" }, layer), "pluvial flood risk, well-being (smoothed index)");
  assert.equal(axisUnit({ column: "PFRWB_smoothed" }, layer), "index 0-1");
  assert.equal(axisTitle({ column: "SVI" }, layer), "svi");
  assert.equal(axisTitle({ column: "Other" }, layer), "Other");
  assert.equal(axisTitle({ column: null }, layer), "");
  assert.equal(axisUnit({ column: "SVI" }, layer), "");
});

test("a popup value keeps an integer whole and a fraction short", () => {
  assert.equal(formatValue(775695977), "775695977");
  assert.equal(formatValue("12"), "12");
  assert.equal(formatValue(0.36410912), "0.364109");
  assert.equal(formatValue("0.1243240"), "0.124324");
  assert.equal(formatValue("n/a"), "n/a");
  assert.equal(formatValue(null), "");
});
