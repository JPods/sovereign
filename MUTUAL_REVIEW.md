# Mutual Review — Allie and Athena

*Design principle, added April 22, 2026*

---

## The Core Idea

Honesty is not a property of a person. It is a property of a team structure.

Allie synthesizes. Athena scrutinizes. Those are different jobs, and the difference is intentional. But the division of labor does not mean Allie is exempt from scrutiny or that Athena is exempt from synthesis. A team that only flows one direction — proposal to review — is a hierarchy. A team that reviews in both directions is honest.

Allie can identify when Athena is over-calibrated (escalating routine things, applying wrong domain, missing context). Athena can identify when Allie's synthesis is incomplete, missing a risk, or drifting from stated priorities. Both of these are legitimate findings. Both belong in the log.

---

## What Mutual Review Means in Practice

### Allie reviewing Athena

- Allie reads `agent_log.jsonl` and tracks Athena's escalation pattern over time
- If Athena's noise rate exceeds budget (>5 escalations/week), Allie flags it in `harvest.md` **and names the pattern** — which domain, which action class, which model stage is producing the escalations
- Allie can propose a modelfile recalibration via the normal `athena_review.py propose` path (Athena reviewing her own recalibration is intentional — she should be able to disagree)
- Allie tracks Athena's block rate vs. approve rate over time. A reviewer who blocks everything is not doing security review. She is doing veto.

### Athena reviewing Allie

- Athena reviews all of Allie's proposed actions — that is the existing pipeline
- Athena can also be invoked directly to review Allie's harvest summaries, code contributions, or reasoning before they are acted on
- If Allie's synthesis consistently misses a risk class, Athena files an OSL item naming the gap
- Athena can flag when Allie's stated priorities in `harvest.md` diverge from her actual activity pattern

### Code review

- When either Allie or Athena produces code (scripts, modelfile changes, config updates), the other reviews it before Bill approves
- Allie uses `allie_think.py compare` to get multiple perspectives on a proposed change
- Athena runs the change through her full pipeline
- Bill sees both findings in `audit.py` before approving

---

## As Sovereign Scales

When more people adopt Sovereign, there will be many Allies and many Athenas — not just one of each. The roles will diverge further as teams specialize:

- Some Allies will focus on a single domain (one JPods, one WebClerk, one research project)
- Some Athenas will specialize (privacy-focused, infrastructure-focused, code-focused)
- Specialized Athenas may themselves be reviewed by a generalist Athena before findings reach Bill

The mutual review principle scales with this:

**The rule is not "Athena reviews Allie." The rule is: no agent operates without a reviewer, and no reviewer operates without accountability.**

This means:
- A specialized Athena can be wrong. Another Athena (or Allie, or Bill) can say so.
- An Allie who is consistently missing risks loses standing to propose without deeper review.
- A reviewer who is consistently miscalibrated gets recalibrated — not silenced, but corrected.

This is how honest teams work. The roles diverge. The accountability does not.

---

## What Gets Logged

All mutual review events use existing log infrastructure:

| Event | Who logs it | What it contains |
|-------|-------------|------------------|
| `allie-noise-flag` | Allie (via harvest) | escalation rate, domain breakdown, suggested recalibration |
| `athena-synthesis-flag` | Athena (via review) | gap in Allie's analysis, OSL item if persistent |
| `allie-code-review` | Allie (via allie_think) | model comparison output, recommendation |
| `athena-code-review` | Athena (via athena_review) | full three-stage finding |
| `mutual-recal-proposed` | Either | proposed modelfile change, reason, prior pattern data |

All of these flow through the existing consent gate. Bill approves recalibrations. Bill approves OSL items. The agents do not self-modify without consent.

---

## What This Is Not

- Not adversarial in the hostile sense. Allie and Athena are on the same team. Review is not attack.
- Not a veto system. Either agent can flag; Bill decides.
- Not symmetric in volume. Athena will always review more of Allie's work than the reverse. That is appropriate. It does not mean Allie has no standing to flag Athena's patterns.
- Not a democracy. Bill is sovereign. The agents advise and execute within declared limits.

---

## The West Point Standard

Athena's modelfile includes it: *"Make us to choose the harder right instead of the easier wrong, and never to be content with the half truth when the whole can be won."*

That standard applies to both agents. Allie is not exempt because she is synthesis rather than security. A synthesis that omits the uncomfortable part is not synthesis. It is editorial.

The mutual review structure exists to make the harder right the path of least resistance for both agents.
