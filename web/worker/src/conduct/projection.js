import YAML from "yaml";

const GITHUB_API = "https://api.github.com";
const inlineBoards = new WeakMap();
const VALID_STATUSES = new Set([
  "open",
  "dispatched",
  "in_progress",
  "done",
  "failed",
  "failed_blocked",
  "needs_human",
  "archived",
]);
const PATCHABLE_TASK_FIELDS = new Set([
  "title",
  "description",
  "repo",
  "type",
  "target_agent",
  "workstream",
  "priority",
  "budget_cost",
  "status",
  "labels",
  "urls",
  "context",
  "predicate",
  "receipt_target",
  "execution_requirements",
  "workstream_contract",
  "claude_tier",
  "depends_on",
]);
const CANONICAL_TRANSITIONS = new Map([
  ["open", new Set(["open", "dispatched"])],
  ["dispatched", new Set(["open", "dispatched", "in_progress"])],
  ["in_progress", new Set(["in_progress", "done", "failed", "failed_blocked", "needs_human"])],
  ["failed", new Set(["failed", "open"])],
  ["failed_blocked", new Set(["failed_blocked", "open"])],
  ["needs_human", new Set(["needs_human", "open"])],
  ["done", new Set(["done", "archived"])],
  ["archived", new Set(["archived"])],
]);

export class ConductProjectionError extends Error {
  constructor(message, status = 503) {
    super(message);
    this.name = "ConductProjectionError";
    this.status = status;
  }
}

function clone(value) {
  return structuredClone(value);
}

function decodeBase64(value) {
  const binary = atob(String(value || "").replace(/\n/g, ""));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return new TextDecoder().decode(bytes);
}

function encodeBase64(value) {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  const size = 0x8000;
  for (let index = 0; index < bytes.length; index += size) {
    binary += String.fromCharCode(...bytes.subarray(index, index + size));
  }
  return btoa(binary);
}

function inlineBoardSource(env) {
  if (env.LIMEN_INLINE_TASKS_YAML) return String(env.LIMEN_INLINE_TASKS_YAML);
  if (env.LIMEN_INLINE_TASKS_YAML_B64) return decodeBase64(env.LIMEN_INLINE_TASKS_YAML_B64);
  return "";
}

function eventAlreadyApplied(board, eventId) {
  return (board.tasks || []).some((task) =>
    (task.dispatch_log || []).some((entry) => entry?.conduct_event_id === eventId));
}

function conductLog(event, log, fallbackStatus, fallbackOutput) {
  return {
    timestamp: event.timestamp,
    agent: String(event.agent),
    session_id: String(event.session_id),
    status: String(fallbackStatus),
    output: String(log?.output ?? fallbackOutput ?? ""),
    conduct_event_id: event.event_id,
    conduct_run_id: event.run_id,
    conduct_lease_id: event.lease_id,
    conduct_generation: event.generation,
  };
}

function validateTaskShape(task, taskId) {
  if (!task || typeof task !== "object" || Array.isArray(task)) {
    throw new ConductProjectionError(`task ${taskId} projection must be an object`, 422);
  }
  if (task.id !== taskId) {
    throw new ConductProjectionError(`task projection id ${task.id} does not match ${taskId}`, 422);
  }
  if (!task.title || typeof task.title !== "string") {
    throw new ConductProjectionError(`task ${taskId} requires a title`, 422);
  }
  if (!task.status || typeof task.status !== "string") {
    throw new ConductProjectionError(`task ${taskId} requires a status`, 422);
  }
  if (!VALID_STATUSES.has(task.status)) {
    throw new ConductProjectionError(`task ${taskId} has unsupported status ${task.status}`, 422);
  }
}

function resetBudgetWindow(budget, event) {
  budget.track ||= { date: "", spent: 0, per_agent: {} };
  const currentDate = String(event.timestamp).slice(0, 10);
  if (budget.track.date === currentDate) return;
  budget.track.date = currentDate;
  budget.track.spent = 0;
  budget.track.per_agent = Object.fromEntries(
    Object.keys(budget.per_agent || {}).map((agent) => [agent, 0]),
  );
}

function canonicalClaimAgent(task, patch) {
  const agent = String(patch.target_agent || task.target_agent || "");
  if (!agent || agent === "any") {
    throw new ConductProjectionError(`task ${task.id} claim requires one concrete target_agent`, 422);
  }
  if (task.target_agent && task.target_agent !== "any" && task.target_agent !== agent) {
    throw new ConductProjectionError(
      `task ${task.id} targets ${task.target_agent}, not claim agent ${agent}`,
      409,
    );
  }
  return agent;
}

function applyCanonicalBudgetDebit(board, task, event, patch) {
  const amount = Number(task.budget_cost || 0);
  if (!Number.isFinite(amount) || !Number.isInteger(amount) || amount < 0) {
    throw new ConductProjectionError(`task ${task.id} has invalid canonical budget_cost`, 422);
  }
  const agent = canonicalClaimAgent(task, patch);
  const budget = board.portal?.budget;
  if (!budget || !amount) return;
  resetBudgetWindow(budget, event);
  budget.track.per_agent ||= {};
  const priorTotal = Number(budget.track.spent || 0);
  const priorAgent = Number(budget.track.per_agent[agent] || 0);
  const dailyLimit = Number(budget.daily ?? Number.POSITIVE_INFINITY);
  const agentLimit = Number(budget.per_agent?.[agent] ?? dailyLimit);
  if (priorTotal + amount > dailyLimit || priorAgent + amount > agentLimit) {
    throw new ConductProjectionError(`task ${task.id} exceeds live ${agent} compatibility budget`, 409);
  }
  budget.track.spent = priorTotal + amount;
  budget.track.per_agent[agent] = priorAgent + amount;
}

function applyCanonicalBudgetRefund(board, task, event) {
  const amount = Number(task.budget_cost || 0);
  const agent = String(task.target_agent || "");
  if (!Number.isFinite(amount) || !Number.isInteger(amount) || amount < 0 || !agent || agent === "any") {
    throw new ConductProjectionError(`task ${task.id} cannot derive a canonical budget refund`, 422);
  }
  const budget = board.portal?.budget;
  if (!budget || !amount) return;
  resetBudgetWindow(budget, event);
  budget.track.per_agent ||= {};
  budget.track.spent = Math.max(0, Number(budget.track.spent || 0) - amount);
  budget.track.per_agent[agent] = Math.max(
    0,
    Number(budget.track.per_agent[agent] || 0) - amount,
  );
}

function canonicalRevision(task) {
  const value = String(
    task.updated
    || task.dispatch_log?.at(-1)?.timestamp
    || task.created
    || task.status,
  );
  return /^\d{4}-\d{2}-\d{2}T/.test(value) && Number.isFinite(Date.parse(value))
    ? new Date(value).toISOString()
    : value;
}

function validatePatch(patch, taskId) {
  if (!patch || typeof patch !== "object" || Array.isArray(patch)) {
    throw new ConductProjectionError(`task ${taskId} compatibility patch must be an object`, 422);
  }
  const forbidden = Object.keys(patch).filter((field) => !PATCHABLE_TASK_FIELDS.has(field));
  if (forbidden.length) {
    throw new ConductProjectionError(
      `task ${taskId} compatibility patch contains server-owned or unsupported fields: ${forbidden.sort().join(", ")}`,
      422,
    );
  }
  if ("status" in patch && !VALID_STATUSES.has(patch.status)) {
    throw new ConductProjectionError(`task ${taskId} has unsupported status ${patch.status}`, 422);
  }
  if ("budget_cost" in patch
      && (!Number.isInteger(patch.budget_cost) || patch.budget_cost < 1 || patch.budget_cost > 1000)) {
    throw new ConductProjectionError(`task ${taskId} has invalid budget_cost`, 422);
  }
}

function validateTransition(taskId, fromStatus, toStatus, kind) {
  if (kind === "task.claim" && (fromStatus !== "open" || toStatus !== "dispatched")) {
    throw new ConductProjectionError(`task ${taskId} claim requires open -> dispatched`, 409);
  }
  if (!CANONICAL_TRANSITIONS.get(fromStatus)?.has(toStatus)) {
    throw new ConductProjectionError(
      `task ${taskId} cannot transition from ${fromStatus} to ${toStatus}`,
      409,
    );
  }
}

export function applyTaskPacketProjectionEvent(input, event) {
  const board = clone(input);
  const intent = event.intent || {};
  const kind = String(intent.kind || "");
  const taskId = String(intent.task_id || event.task_id || "");
  if (!taskId) throw new ConductProjectionError("compatibility event requires task_id", 422);
  const existing = (board.tasks || []).find((candidate) => candidate.id === taskId);
  if (existing && eventAlreadyApplied(board, event.event_id)) {
    return { board, task: clone(existing), duplicate: true, changed: false };
  }

  if (kind === "task.upsert") {
    if (intent.expected_absent && existing) {
      throw new ConductProjectionError(`task ${taskId} already exists`, 409);
    }
    const supplied = clone(intent.task || {});
    validateTaskShape(supplied, taskId);
    const task = existing || {
      ...supplied,
      dispatch_log: [],
    };
    if (existing) {
      if (supplied.status !== existing.status) {
        throw new ConductProjectionError(
          `task ${taskId} upsert cannot change lifecycle status; submit task.status`,
          409,
        );
      }
      const history = existing.dispatch_log || [];
      const created = existing.created;
      const patch = Object.fromEntries(
        Object.entries(supplied).filter(([field]) => PATCHABLE_TASK_FIELDS.has(field)),
      );
      validatePatch(patch, taskId);
      Object.assign(task, patch);
      task.dispatch_log = history;
      if (created !== undefined) task.created = created;
    }
    board.tasks ||= [];
    if (!existing) board.tasks.push(task);
    task.updated = event.timestamp;
    task.dispatch_log ||= [];
    task.dispatch_log.push(conductLog(
      event,
      intent.log,
      task.status,
      `Created by ${event.agent} through the conduct keeper`,
    ));
    return { board, task: clone(task), duplicate: false, changed: true };
  }

  if (!["task.status", "task.claim", "task.mutate"].includes(kind)) {
    throw new ConductProjectionError(`unsupported task compatibility intent: ${kind}`, 422);
  }
  if (!existing) throw new ConductProjectionError(`task ${taskId} not found in canonical board`, 409);
  if (intent.expected_revision !== undefined
      && String(intent.expected_revision) !== canonicalRevision(existing)) {
    throw new ConductProjectionError(`task ${taskId} exact revision moved`, 409);
  }
  const expected = intent.expected_status;
  const expectedStatuses = Array.isArray(expected) ? expected : [expected];
  if (!expectedStatuses.includes(existing.status)) {
    throw new ConductProjectionError(
      `task ${taskId} is ${existing.status}; compatibility event requires ${expectedStatuses.join(" or ")}`,
      409,
    );
  }
  const patch = intent.patch || {};
  validatePatch(patch, taskId);
  if (kind === "task.status" && !Object.prototype.hasOwnProperty.call(patch, "status")) {
    throw new ConductProjectionError(`task ${taskId} status intent requires a status patch`, 422);
  }
  const nextStatus = patch.status ?? existing.status;
  validateTransition(taskId, existing.status, nextStatus, kind);
  if (kind === "task.claim") applyCanonicalBudgetDebit(board, existing, event, patch);
  if (kind === "task.status" && existing.status === "dispatched" && nextStatus === "open") {
    applyCanonicalBudgetRefund(board, existing, event);
  }
  Object.assign(existing, clone(patch));
  existing.updated = event.timestamp;
  existing.dispatch_log ||= [];
  existing.dispatch_log.push(conductLog(
    event,
    intent.log,
    existing.status,
    `${kind} applied through the conduct keeper`,
  ));
  validateTaskShape(existing, taskId);
  return { board, task: clone(existing), duplicate: false, changed: true };
}

function ensureBudget(board, task, event) {
  const budget = board.portal?.budget;
  if (!budget || event.budget_action === "none") return;
  resetBudgetWindow(budget, event);
  budget.track.per_agent ||= {};
  const cost = Number(task.budget_cost ?? event.budget_cost ?? 1);
  if (!Number.isFinite(cost) || cost < 0) {
    throw new ConductProjectionError(`task ${task.id} has invalid budget_cost`, 409);
  }
  const priorTotal = Number(budget.track.spent || 0);
  const priorAgent = Number(budget.track.per_agent[event.agent] || 0);
  if (event.budget_action === "debit") {
    const dailyLimit = Number(budget.daily ?? Number.POSITIVE_INFINITY);
    const agentLimit = Number(budget.per_agent?.[event.agent] ?? dailyLimit);
    if (priorTotal + cost > dailyLimit || priorAgent + cost > agentLimit) {
      throw new ConductProjectionError(`task ${task.id} exceeds live ${event.agent} conduct budget`, 409);
    }
    budget.track.spent = priorTotal + cost;
    budget.track.per_agent[event.agent] = priorAgent + cost;
  } else if (event.budget_action === "refund") {
    budget.track.spent = Math.max(0, priorTotal - cost);
    budget.track.per_agent[event.agent] = Math.max(0, priorAgent - cost);
  }
}

export function applyTaskCompatibilityEvent(input, event) {
  if (event.schema_version === "limen.task_packet_projection_event.v1") {
    return applyTaskPacketProjectionEvent(input, event);
  }
  const board = clone(input);
  if (eventAlreadyApplied(board, event.event_id)) {
    return { board, task: clone((board.tasks || []).find((task) => task.id === event.task_id)), duplicate: true, changed: false };
  }
  const task = (board.tasks || []).find((candidate) => candidate.id === event.task_id);
  if (!task) throw new ConductProjectionError(`task ${event.task_id} not found in canonical board`, 409);
  if (!event.from_statuses.includes(task.status)) {
    throw new ConductProjectionError(
      `task ${event.task_id} is ${task.status}; conduct event ${event.kind} requires ${event.from_statuses.join(" or ")}`,
      409,
    );
  }
  ensureBudget(board, task, event);
  task.status = event.status;
  task.updated = event.timestamp;
  task.dispatch_log ||= [];
  task.dispatch_log.push({
    timestamp: event.timestamp,
    agent: event.agent,
    session_id: event.session_id,
    status: event.status,
    output: event.output,
    conduct_event_id: event.event_id,
    conduct_run_id: event.run_id,
    conduct_lease_id: event.lease_id,
    conduct_generation: event.generation,
  });
  return { board, task: clone(task), duplicate: false, changed: true };
}

function githubContentsUrl(env) {
  const repo = String(env.LIMEN_GITHUB_REPO || "");
  const path = encodeURIComponent(env.LIMEN_GITHUB_PATH || "tasks.yaml").replaceAll("%2F", "/");
  return `${GITHUB_API}/repos/${repo}/contents/${path}`;
}

function githubHeaders(env, withBody = false) {
  return {
    authorization: `Bearer ${env.LIMEN_GITHUB_TOKEN}`,
    accept: "application/vnd.github+json",
    "user-agent": "limen-conduct-keeper",
    "x-github-api-version": "2022-11-28",
    ...(withBody ? { "content-type": "application/json" } : {}),
  };
}

async function githubGet(env, fetchImpl) {
  const branch = env.LIMEN_GITHUB_BRANCH || "main";
  const response = await fetchImpl(`${githubContentsUrl(env)}?ref=${encodeURIComponent(branch)}`, {
    method: "GET",
    headers: githubHeaders(env),
  });
  const text = await response.text();
  if (!response.ok) {
    throw new ConductProjectionError(`GitHub projection read failed (${response.status}): ${text.slice(0, 300)}`);
  }
  const raw = text ? JSON.parse(text) : {};
  return {
    board: YAML.parse(decodeBase64(raw.content || "")) || { portal: {}, tasks: [] },
    sha: raw.sha,
  };
}

async function githubPut(env, fetchImpl, board, sha, event) {
  const branch = env.LIMEN_GITHUB_BRANCH || "main";
  const response = await fetchImpl(githubContentsUrl(env), {
    method: "PUT",
    headers: githubHeaders(env, true),
    body: JSON.stringify({
      message: `limen conduct: ${event.kind} ${event.task_id}`,
      content: encodeBase64(YAML.stringify(board)),
      branch,
      sha,
    }),
  });
  const text = await response.text();
  return { ok: response.ok, status: response.status, text };
}

export async function commitTaskCompatibilityEvent(env, event, { fetchImpl = fetch, maxAttempts = 4 } = {}) {
  if (!event) return { status: "not_applicable" };
  const inline = inlineBoardSource(env);
  if (inline) {
    const current = inlineBoards.get(env) || inline;
    const parsed = YAML.parse(current) || { portal: {}, tasks: [] };
    const applied = applyTaskCompatibilityEvent(parsed, event);
    inlineBoards.set(env, YAML.stringify(applied.board));
    return {
      status: applied.duplicate ? "duplicate" : "committed",
      mode: "inline",
      task: applied.task,
      event_id: event.event_id,
    };
  }
  if (!env.LIMEN_GITHUB_REPO || !env.LIMEN_GITHUB_TOKEN) {
    throw new ConductProjectionError(
      "task-backed conduct transitions require LIMEN_GITHUB_REPO and LIMEN_GITHUB_TOKEN",
    );
  }
  let lastConflict = "";
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const document = await githubGet(env, fetchImpl);
    const applied = applyTaskCompatibilityEvent(document.board, event);
    if (applied.duplicate) {
      return {
        status: "duplicate",
        mode: "github",
        sha: document.sha,
        task: applied.task,
        event_id: event.event_id,
      };
    }
    const written = await githubPut(env, fetchImpl, applied.board, document.sha, event);
    if (written.ok) {
      return {
        status: "committed",
        mode: "github",
        task: applied.task,
        event_id: event.event_id,
      };
    }
    if (written.status === 409 || (written.status === 422 && /sha|does not match|conflict/i.test(written.text))) {
      lastConflict = written.text.slice(0, 300);
      continue;
    }
    throw new ConductProjectionError(
      `GitHub projection write failed (${written.status}): ${written.text.slice(0, 300)}`,
    );
  }
  throw new ConductProjectionError(
    `GitHub projection CAS did not converge after ${maxAttempts} attempts: ${lastConflict}`,
    409,
  );
}

export function readInlineProjection(env) {
  const text = inlineBoards.get(env) || inlineBoardSource(env);
  return YAML.parse(text) || { portal: {}, tasks: [] };
}

export const readInlineProjectionForTest = readInlineProjection;
