# Agent Team — README Index
**Last Updated:** 2026-04-21
**Purpose:** One file per agent. Each agent owns their file and can add to it freely. This is the living record of who does what, what decisions have been made, and what is still open.

---

## Template

Every agent file uses this structure. Add sections as needed; do not remove them.

```
# [Name] — [Domain]

**One-liner:** What I do in one sentence.
**Ouch-list items I own:** [list of risk IDs]
**Signing status:** has key pair | planned | not yet

---

## Responsibilities
## Design Decisions  (date | decision | reasoning)
## Open Questions
## Interfaces        (sends | receives | signs | requires signatures from)
## Notes to Other Agents
```

---

## Engineering Design Team

| Agent | Domain | File |
|-------|--------|------|
| Cilia | Civil / Structural | [cilia.md](cilia.md) |
| Matilda | Mechanical + Fleet Calibration | [matilda.md](matilda.md) |
| Sparki | Energy | [sparki.md](sparki.md) |
| Athena | Security | [athena.md](athena.md) |
| Willi | Pedestrian / Walking Access | [willi.md](willi.md) |
| Kinder | Special Users | [kinder.md](kinder.md) |

## Control System Agents

| Agent | Role | File |
|-------|------|------|
| Nora | Vehicle — autonomous pod | [nora.md](nora.md) |
| Natalie | Router — trip scheduling | [natalie.md](natalie.md) |
| Noelle | Load Balancer — ezones, prepositioning | [noelle.md](noelle.md) |

## Ecosystem Agents

| Agent | Role | File | WC Connection |
|-------|------|------|---------------|
| Alice | WebClerk specialist — data quality, billing, patterns | [alice.md](alice.md) | 24 |
| Allie | Bill's personal AI — cross-domain, sovereignty review | [allie.md](allie.md) | 22 |
| Athena | Adversarial reviewer — security, privacy, action gate | [athena.md](athena.md) | 23 |

---

## Editing Rights

**Any agent may edit any file in `/agents/` at any time for anything that affects their domain.**

This is not limited to your own file. If Cilia sees a structural consequence in Matilda's domain, she writes it in matilda.md. If Nora discovers a routing edge case, she writes it in natalie.md. Cross-domain notes belong in the file of the agent who needs to act on them, not only in the file of the agent who noticed them.

The only constraint is honesty: write what you know, date design decisions, mark open questions as open.

**Athena maintains integrity.** Every file in `/agents/` is hashed and backed up by Athena's verification system (`athena/verify_agents.sh`). Changes are logged. If a file is hijacked or corrupted, Athena can restore from a signed backup. Write freely — Athena has the merge.

---

## Cross-Cutting Rules

1. **Payload is always readable.** Sign for authenticity; never encrypt to obscure. Debugging must remain possible without Athena's tooling.
2. **Any agent can sign and require signatures without asking permission.** That is what sovereignty means at the message layer.
3. **Add to ouch-list freely.** Flag cross-domain risks in the other agent's section — that is the protocol, not overstepping.
4. **Open questions belong here, not in your head.** If you do not know, write it down.
5. **Edit `/agents/` freely.** Athena has the merge and the backup. You cannot break it permanently.
6. **Machine-readable protocol:** `agent-protocol.md` has precise call syntax, credential IDs, and behavioral contracts for Allie, Alice, and Athena.
