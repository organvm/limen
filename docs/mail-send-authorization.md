# Mail-send authorization boundary

`scripts/mail-send` is a narrow shim, not the mail authority. It executes only the
Domus-installed UMA delegate at:

```text
/Library/Application Support/org.organvm.domus/limen/uma/bin/mail-send
```

The delegate and every path component must be owner-owned, non-symlinked, and
non-writable by the ordinary executor. `LIMEN_UMA_ROOT`, `UMA_ROOT`, `PATH`, and
`PYTHONPATH` cannot select executable mail code.

Preview is the default. It passes `--dry-run` under a fixed owner HOME, TMPDIR,
and working directory with a minimal environment, no `PYTHONPATH`, and
`PYTHONSAFEPATH=1`. It never resolves or passes a credential file. Apply requires
the complete UMA attempt/receipt/signature shape. Only then may the shim pass the
fixed root-owned mode-0400/0600 credential file and fixed owner-only attempt
registry. Caller-selected credential, authorization-key, and attempt-store flags
are refused.

The delegate and its owner home/tmp/run/credential/attempt-store paths are currently
unprovisioned by Limen. Until Domus installs an accepted exact-head UMA build and
those paths, every invocation fails closed before SMTP access.

Domus provisions the fixed `uma/` subtree with root-owned, non-symlinked,
non-group/world-writable ancestors and these exact leaves:

- executable `bin/mail-send`;
- mode `0400` or `0600` single-link `credentials/mail.env`;
- owner-only directories `state/mail-attempts`, `home`, `tmp`, and `run`.

The wrapper injects `--attempt-store` with that fixed registry only on apply.
The installed UMA delegate owns signed-receipt validation and atomic `O_EXCL`
attempt consumption. A checkout or caller-selected registry cannot prove replay
protection.
