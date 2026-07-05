# VLTIMA Kernel

The VLTIMA kernel is the universal civilizational substrate underneath the
organs. The existing five institutional primitives stay intact; this document
names the lower layer they project from and the value layer they must eventually
support.

The executable registry is [`kernel.yaml`](kernel.yaml). `scripts/validate-vltima-kernel.py`
loads that registry, verifies the canonical primitive set, and checks every organ
projection against it. `scripts/validate-vltima-kernel.py --json-output` emits the
derived machine-readable substrate: primitive graph nodes and source edges,
layers, projection groups, and each organ's kernel mapping from `organ-ladder.json`.

## Lower Layer

| Primitive | Meaning |
|---|---|
| **Object** | Anything the institution can point at: artifact, account, document, work, rule, claim, file, or product. |
| **Subject** | A bearer of interest, consent, harm, benefit, identity, or standing. |
| **Agent** | A system or person capable of producing an event under a known authority boundary. |
| **Actor** | An agent acting in a role at a specific moment. |
| **System** | The bounded machine, office, institution, or process that receives events and maintains records. |
| **Event** | A dated assertion that something happened, was proposed, was decided, or changed state. |
| **Record** | A durable event or projection that can be re-read, audited, and cited. |
| **Covenant** | A binding rule or promise that governs future events and record interpretation. |

## Institutional Projection

Every organ projects the lower layer into the five existing primitives:

| Institutional primitive | Universal source |
|---|---|
| **Member** | Subject or object with recognized standing inside the system. |
| **Mandate** | Covenant-backed purpose, claim, role, matter, goal, or obligation. |
| **Standing** | Current record-derived posture: who may act, what is true enough to rely on, and what remains blocked. |
| **Standard** | The covenant, law, rubric, benchmark, or test that decides whether standing can change. |
| **Governance** | The rule-bound authority map for actors, agents, records, and external acts. |

## Value Projection

Money is not separate from the kernel. It is a value-bearing projection:

| Value primitive | Meaning |
|---|---|
| **Exchange** | A recordable transfer of value or promise of value. |
| **Entitlement** | Standing granted by a valid record, such as a MONETA license. |
| **Obligation** | A covenant-backed duty to pay, deliver, maintain, review, or refrain. |

## Operating Law

Events become records. Records establish standing. Standing authorizes action.
Action produces value. Value funds the institution.

TABVLARIVS is the record proof: ticket event -> board projection -> sealed
record -> task standing. MONETA is the value proof: buyer -> payment/order event
-> license record -> entitlement standing. The organs are institutional proofs:
member -> mandate -> standing -> standard -> governance.
