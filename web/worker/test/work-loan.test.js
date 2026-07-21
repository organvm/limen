import assert from "node:assert/strict";
import test from "node:test";

import {
  packetWorkLoanMissingFields,
  taskWorkLoanMissingFields,
  workLoanDenial,
} from "../src/conduct/work-loan.js";

test("task work-loan denials use stable field order", () => {
  const missing = taskWorkLoanMissingFields({
    id: "RAW",
    title: "Human asks for valuable urgent work",
    repo: "organvm/limen",
    budget_cost: 0,
    status: "open",
    predicate: "should pass",
    receipt_target: "receipt.txt",
  });

  assert.deepEqual(missing, [
    "source_origin",
    "horizon",
    "value_case",
    "budget_cost",
    "predicate",
    "receipt_target",
  ]);
  assert.equal(
    workLoanDenial(missing),
    "task-not-underwritten:source_origin,horizon,value_case,budget_cost,predicate,receipt_target",
  );
});

test("packet work loans bind their positive cost to the spend envelope", () => {
  const packet = {
    predicate: "pytest -q",
    receipt_target: "github:organvm/limen:pull-request:WL-1",
    spend: { limit: 2 },
    work_loan: {
      source_origin: "human_prompt",
      horizon: "present",
      value_case: "Deliver one bounded outcome",
      budget_cost: 3,
      owner_surface: "organvm/limen",
    },
  };

  assert.deepEqual(packetWorkLoanMissingFields(packet), ["budget_cost"]);
  packet.work_loan.budget_cost = 2;
  assert.deepEqual(packetWorkLoanMissingFields(packet), []);

  packet.work_loan.source_origin = "urgent";
  packet.work_loan.horizon = "soon";
  assert.deepEqual(packetWorkLoanMissingFields(packet), ["source_origin", "horizon"]);
});

test("due_at is required only for declared external deadlines", () => {
  const task = {
    repo: "organvm/limen",
    budget_cost: 1,
    origin: "obligation",
    horizon: "present",
    value_case: "Meet the real deadline",
    predicate: "pytest -q",
    receipt_target: "git:organvm/limen:logs/deadline.json",
  };

  assert.deepEqual(taskWorkLoanMissingFields(task), []);
  assert.deepEqual(taskWorkLoanMissingFields({ ...task, external_deadline: true }), ["due_at"]);
  assert.deepEqual(
    taskWorkLoanMissingFields({ ...task, external_deadline: true, due_at: "2026-08-01" }),
    [],
  );
});
