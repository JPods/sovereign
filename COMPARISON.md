# How Sovereign Differs

*April 2026*

There are many AI agent frameworks. None of them are built on the premise that the user is sovereign. Most are built on the premise that more automation is better.

This document is an honest accounting of what exists and what is different here.

---

## The Landscape

### LangChain / LangGraph

**What it does:** Orchestrates chains and graphs of LLM calls. Rich ecosystem, widely used.

**What it lacks:**
- No adversarial reviewer in the pipeline. The system assembles and executes; nothing challenges it.
- No consent gate. Actions execute when the graph reaches them.
- No sovereignty declaration. There is no file that defines what the agent is permitted to do.
- Logging is for debugging, not audit. You can see what happened; you cannot approve or reject it before it runs.

**When to use it:** When you're building agent pipelines for production services and trust the pipeline.

---

### AutoGen (Microsoft)

**What it does:** Multi-agent conversation framework. Agents talk to each other to complete tasks.

**What it lacks:**
- Agents can override each other but there is no external reviewer whose job is to find what's wrong.
- Human-in-the-loop is a configuration option, not a structural guarantee.
- No standing approvals model. No noise budget. No concept that the oversight agent itself can be miscalibrated.
- No sovereignty declaration binding what agents may do.

**When to use it:** When you want agents to collaborate on well-defined tasks in a controlled environment.

---

### CrewAI

**What it does:** Role-based multi-agent framework. Assigns agents to roles (researcher, writer, etc.).

**What it lacks:**
- Roles are for capability, not for adversarial review. No agent's job is to find what's wrong with other agents' proposals.
- No consent gate between proposal and execution.
- No persistent sovereignty declaration.

**When to use it:** Task decomposition across specialized LLM roles.

---

### Open WebUI

**What it does:** Self-hosted ChatGPT-style interface with model switching, RAG, and some agent support.

**What it lacks:**
- No agent-to-agent coordination with adversarial review.
- No action queue. No consent gate.
- Conversation history ≠ audit log. You can read what happened; you did not approve it.

**When to use it:** Local LLM interface for conversations and document Q&A.

---

### Guardrails AI

**What it does:** Validates LLM outputs against schemas and rules.

**What it lacks:**
- Defaults to allow. A guardrail that trips routes to a fallback or retry — it does not queue the action for human review.
- No adversarial agent. Rules are static; Guardrails does not reason about novel risk.
- No standing approvals, noise budget, or sovereignty declaration.

**When to use it:** Output validation for structured LLM responses in production pipelines.

---

### Activity Monitors (various)

File watchers, app trackers, time-tracking tools. They record what happened.

**What they lack:** No agent layer. No proposal → review → consent → execute cycle. Recording ≠ oversight.

---

## What Sovereign Does Differently

### 1. Adversarial review is a first-class agent

In every other framework, review is optional middleware or a configuration flag. In Sovereign, Athena's job is to find what's wrong. She is not a filter that defaults to yes. She has three specialized LLMs — fast classifier, deep security reviewer, threat modeler — and a structured output format that forces her to name what she checked, not just whether she approved.

A security system that defaults to allow is not security. It is the appearance of security.

### 2. The consent gate has teeth

Action items with status `pending-audit` do not execute. Period. They sit in the queue. The audit console applies pressure back — harvest.md escalates overdue items. The system is designed to make skipping your review uncomfortable, not easy.

Most frameworks treat human-in-the-loop as an option. Sovereign treats it as the mechanism by which the user stays sovereign.

### 3. The sovereignty declaration

`profile.json` is not a settings file. It is a declaration: here is what agents are permitted to do, with scope and expiry. Standing approvals are explicit grants, not defaults. Everything outside the declaration requires consent.

This is the difference between a tool that works for you and a tool that works.

### 4. Standing approvals + noise budget

The standing approvals model solves the real problem with human oversight: it is exhausting if the system escalates everything. Routine actions — log writes, harvest generation — are pre-authorized. Non-routine actions go to the queue.

The noise budget solves the other real problem: an oversight agent that escalates everything is not useful. If Athena exceeds five escalations per week, harvest.md flags a calibration failure. Athena is accountable to her own escalation rate.

### 5. Local-first, no cloud dependency

All three Athena models run locally via Ollama. Nothing about your activity log, action queue, or sovereignty declaration leaves your machine unless you explicitly enable external probes. External probes (OpenAI, Anthropic) are opt-in, triggered only on BLOCK or model disagreement, and use environment-variable keys only.

---

## What Sovereign Is Not

- Not a general-purpose agent orchestration framework. Use LangChain for that.
- Not a production pipeline tool. Use Guardrails for output validation in services.
- Not a replacement for good judgment. Sovereign makes your judgment the bottleneck, not an afterthought.

---

## The Core Claim

Every other framework assumes the automation is correct and asks you to trust it.

Sovereign assumes the automation needs to earn that trust, one approved action at a time.

That is not a feature. It is a different premise.
