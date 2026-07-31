# Relay

The literal-substrate implementation is closed into three exact owner heads:

- Limen PR #1705 — `f77931aa67af8febb98e8a0a43030d3a9836f0a2`
- PORTVS PR #6 — `bffd599f0ab114917bade162f609772a345f696e`
- Domus PR #361 — `c31d1e97e5053ee5330715f78484c1498ff6ed33`

All 33 current review findings were independently verified, replied to, and
resolved; seven additional outdated Limen threads were also resolved so no
review debt remains. Exact-head remote checks are terminal green on all three
owners.

Producer proof:

- Limen: 34 substrate tests plus 52 focused owner tests passed; mypy, Ruff,
  path-contract, Python CI, and 25/25 cheap scoped gates passed. Three
  unrelated xdist/host-pressure nodes passed sequentially on the unchanged
  tree.
- PORTVS: 41 tests passed; dependency lock, Ruff, formatting, `py_compile`,
  and Bash checks passed. Repeated plan and verify receipts are byte-identical.
- Domus: 106 template checks, 22 Node tests, 334 BATS tests, and 418 Python
  tests passed. Repeated no-apply Home receipts are byte-identical.
- Two protected Claude sessions and 466 diagram artifacts remain privately
  receipted and reconstructible.

The physical migration is not claimed complete. Its red state is owned by the
three PR receipts, Limen's migration registry, and this successor: PORTVS
records 11 blockers and 63 strict violations; Domus records 16 planned actions,
2 protected blockers, and 19 violations; Limen records 77 violations and zero
unmeasured state. No repository or private payload was moved, and no Home route
was applied.

Human gate: Anthony reviews and merges the three owner PRs. The branches are
clean, pushed, reviewed, and mergeable; this closeout does not merge them.

Launch the next lane with:

```bash
bash /Users/4jp/Workspace/limen/.worktrees/omega-substrate-convergence-next/.limen-workstream/kickstart.sh
```

`producer-closeout.json` and `verify-producer-closeout.py` are the executable
producer fixed-point receipt.
