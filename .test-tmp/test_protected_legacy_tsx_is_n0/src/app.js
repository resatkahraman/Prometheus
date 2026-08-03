import { percentageOf } from "./calculator.js";

const output = document.querySelector("#result");
if (output) {
  output.value = String(percentageOf(200, 15));
}
