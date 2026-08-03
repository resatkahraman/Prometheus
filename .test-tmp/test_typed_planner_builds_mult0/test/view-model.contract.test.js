import test from "node:test";
import assert from "node:assert/strict";
import { buildOrderSummary } from "../src/view-model.js";

test("builds a deterministic Turkish order summary", () => {
  const summary = buildOrderSummary(
    [
      { price: 50, quantity: 2 },
      { price: 20, quantity: 1 },
    ],
    25,
  );
  assert.deepEqual(summary, {
    itemCount: 3,
    total: 90,
    label: "3 ürün • 90,00 TRY",
  });
});

test("uses singular wording for one item", () => {
  assert.equal(
    buildOrderSummary([{ price: 7.5, quantity: 1 }]).label,
    "1 ürün • 7,50 TRY",
  );
});
