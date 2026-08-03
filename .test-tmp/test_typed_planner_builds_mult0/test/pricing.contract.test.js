import test from "node:test";
import assert from "node:assert/strict";
import { calculateOrderTotal } from "../src/pricing.js";

test("calculates quantities and percentage discount", () => {
  const items = [
    { price: 50, quantity: 2 },
    { price: 20, quantity: 1 },
  ];
  assert.equal(calculateOrderTotal(items, 25), 90);
});

test("does not mutate input items", () => {
  const items = [{ price: 12.5, quantity: 2 }];
  const snapshot = structuredClone(items);
  assert.equal(calculateOrderTotal(items), 25);
  assert.equal(
    calculateOrderTotal([{ price: 7.5, quantity: 1 }]),
    7.5,
  );
  assert.deepEqual(items, snapshot);
});

test("rejects invalid collections, items and discounts", () => {
  assert.throws(() => calculateOrderTotal(null), TypeError);
  assert.throws(
    () => calculateOrderTotal([{ price: -1, quantity: 1 }]),
    TypeError,
  );
  assert.throws(
    () => calculateOrderTotal([{ price: 1, quantity: 0 }]),
    TypeError,
  );
  assert.throws(() => calculateOrderTotal([], 101), RangeError);
});
