import test from "node:test";
import assert from "node:assert/strict";
import { percentageOf } from "../src/calculator.js";

test("calculates a percentage of a value", () => {
  assert.equal(percentageOf(200, 15), 30);
  assert.equal(percentageOf(50, 10), 5);
});

test("supports zero, negative values and decimal percentages", () => {
  assert.equal(percentageOf(500, 0), 0);
  assert.equal(percentageOf(-80, 25), -20);
  assert.equal(percentageOf(40, 12.5), 5);
});

test("rejects non-finite inputs", () => {
  assert.throws(() => percentageOf(Number.NaN, 10), TypeError);
  assert.throws(() => percentageOf(10, Number.POSITIVE_INFINITY), TypeError);
});
