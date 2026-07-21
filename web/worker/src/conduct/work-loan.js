const FIELD_ORDER = [
  "source_origin",
  "horizon",
  "value_case",
  "budget_cost",
  "owner_surface",
  "predicate",
  "receipt_target",
  "due_at",
];
const EXECUTABLES = new Set([
  "[", "bash", "bundle", "cargo", "curl", "gh", "git", "go", "just", "limen", "make", "node", "nox", "npm",
  "pnpm", "py.test", "pytest", "python", "python3", "ruby", "sh", "test", "tox", "uv", "yarn", "zsh",
]);
const ORIGINS = new Map([
  ["ask", "human_prompt"], ["human", "human_prompt"], ["human_ask", "human_prompt"],
  ["prompt", "human_prompt"], ["human_prompt", "human_prompt"],
  ["due", "obligation"], ["external", "obligation"], ["obligation", "obligation"],
  ["agent", "agent_recommendation"], ["agent_recommendation", "agent_recommendation"],
  ["recommendation", "agent_recommendation"], ["system", "system_debt"], ["debt", "system_debt"],
  ["system_debt", "system_debt"],
]);
const HORIZONS = new Map([
  ["past", "past"], ["recovery", "past"], ["present", "present"], ["now", "present"],
  ["current", "present"], ["next", "future"], ["future", "future"], ["later", "future"],
]);

function slug(value) {
  return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function fieldOrLabel(task, fields, prefixes) {
  for (const field of fields) {
    if (task?.[field] != null && String(task[field]).trim()) return String(task[field]).trim();
  }
  for (const label of task?.labels || []) {
    const normalized = String(label).trim().toLowerCase();
    for (const prefix of prefixes) {
      const marker = `${prefix}:`;
      if (normalized.startsWith(marker) && normalized.slice(marker.length).trim()) {
        return normalized.slice(marker.length).trim();
      }
    }
  }
  return null;
}

export function executablePredicate(value) {
  if (typeof value !== "string" || !value.trim() || /[\r\n\0]/.test(value)) return false;
  const tokens = value.trim().split(/\s+/);
  let index = 0;
  while (index < tokens.length && (
    ["command", "env", "sudo"].includes(tokens[index])
    || (/^[A-Za-z_][A-Za-z0-9_]*=/.test(tokens[index]) && !tokens[index].startsWith("/"))
    || tokens[index].startsWith("-")
  )) index += 1;
  if (index >= tokens.length) return false;
  const first = tokens[index].replace(/^['"]|['"]$/g, "");
  return EXECUTABLES.has(first) || first.includes("/") || first.endsWith(".py") || first.endsWith(".sh");
}

export function durableReceiptTarget(value) {
  if (typeof value !== "string" || !value.trim() || /[\s\0]/.test(value)) return false;
  if (/^github:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+:(pull-request|issue):[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(value)) {
    return true;
  }
  if (/^git:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+:(?!\/)(?!.*\/\.\.?(?:\/|$))(?!.*\/\.git(?:\/|$))[^\s#]+(?:#[^\s]+)?$/.test(value)) {
    return true;
  }
  return /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/(?:issues|pull|actions\/(?:runs|workflows)|commit|blob|tree)\/[A-Za-z0-9][^\s?#]*$/.test(value);
}

function ordered(fields) {
  return FIELD_ORDER.filter((field) => fields.has(field));
}

export function packetWorkLoanMissingFields(packet) {
  const loan = packet.work_loan;
  const missing = new Set();
  if (!loan) {
    for (const field of ["source_origin", "horizon", "value_case", "budget_cost", "owner_surface"]) missing.add(field);
  } else {
    for (const field of ["source_origin", "horizon", "value_case", "owner_surface"]) {
      if (typeof loan[field] !== "string" || !loan[field].trim()) missing.add(field);
    }
    if (!Number.isInteger(loan.budget_cost) || loan.budget_cost <= 0 || loan.budget_cost !== packet.spend.limit) {
      missing.add("budget_cost");
    }
    if (loan.external_deadline && !loan.due_at) missing.add("due_at");
  }
  if (!executablePredicate(packet.predicate)) missing.add("predicate");
  if (!durableReceiptTarget(packet.receipt_target)) missing.add("receipt_target");
  return ordered(missing);
}

export function taskWorkLoanMissingFields(task) {
  const missing = new Set();
  const origin = ORIGINS.get(slug(fieldOrLabel(
    task,
    ["source_origin", "intent_origin", "work_origin", "origin"],
    ["origin", "intent-origin", "work-origin"],
  )));
  const horizon = HORIZONS.get(slug(fieldOrLabel(
    task,
    ["time_horizon", "horizon"],
    ["horizon", "time-horizon"],
  )));
  const valueCase = fieldOrLabel(task, ["value_case", "expected_value", "work_credit"], ["value", "value-case", "work-credit"]);
  const owner = fieldOrLabel(task, ["owner_surface", "work_owner"], ["owner-surface", "work-owner"])
    || String(task?.repo || "").trim();
  if (!origin) missing.add("source_origin");
  if (!horizon) missing.add("horizon");
  if (!valueCase) missing.add("value_case");
  if (!Number.isInteger(task?.budget_cost) || task.budget_cost <= 0) missing.add("budget_cost");
  if (!owner) missing.add("owner_surface");
  if (!executablePredicate(task?.predicate)) missing.add("predicate");
  if (!durableReceiptTarget(task?.receipt_target)) missing.add("receipt_target");
  const external = task?.external_deadline === true
    || ["1", "true", "yes"].includes(String(task?.external_deadline || "").trim().toLowerCase());
  const dueAt = fieldOrLabel(task, ["due_at", "due_on", "due_date", "deadline"], ["due", "due-at", "due-on", "deadline"]);
  if (external && !dueAt) missing.add("due_at");
  return ordered(missing);
}

export function workLoanDenial(fields) {
  return `task-not-underwritten:${fields.join(",")}`;
}
