# Financial Office — Standing Census

> Generated: 2026-07-03T23:58:44Z
> This is the reliability preflight: what the office can be trusted for today, and which fields still require the principal's hand.

## Reliance Posture

| Can rely on today | Not yet reliable for |
|---|---|
| entity/account inventory | net worth or solvency amount |
| payrail route map and no-money-movement boundary | runway duration or weekly surplus/deficit |
| first-dollar path selection from revenue-ladder.json | sovereign intake being live |
| ranked financial obligation visibility |  |

## Census Counts

| Measure | Count |
|---|---:|
| Accounts registered | 13 |
| Known balances | 0 |
| Missing balances | 13 |
| Liability accounts registered | 2 |
| Known liability balances | 0 |
| Financial obligations | 4 |
| Quantified obligations | 0 |
| Unknown obligation amounts | 4 |

## Checks

| Check | Status | Gate |
|---|---|---|
| Entity registry has personal, commercial, mission, and product containers | pass | repo |
| At least one cash/checking balance is known | needs_principal | principal balance entry |
| Credit/loan liabilities are present in the registry | pass | repo |
| Credit/loan balances are known | needs_principal | principal balance entry |
| Financial-material obligations are visible | pass | mail organ or registry fallback |
| Financial obligations have usable dollar amounts | needs_principal | principal amount entry |
| A first-dollar product path is selected | pass | revenue-ladder.json |
| MONETA rail exists in this checkout | pass | repo |
| MONETA has a deploy-time self-custodied receive address | needs_principal | MINT_BTC_ADDRESS outside git |

## Next Principal Inputs

- **enter_cash_balance** — `anthony-personal:ach-checking balance + as_of` in organs/financial/entities.yaml. Unlocks real net worth and runway start point.
- **enter_liability_balances** — `santander-card-0186 and student-loan-nelnet balance + as_of` in organs/financial/entities.yaml. Turns fraud-hold and default risk into real liability posture.
- **quantify_obligations** — `amount/frequency for highest-priority obligations` in organs/financial/entities.yaml or obligations-ledger.json. Makes cashflow/runway usable instead of structural only.
- **configure_moneta_address** — `MINT_BTC_ADDRESS` in deploy secret, not git. Opens the sovereign first-dollar rail without giving the organ spending authority.

## Rail Boundary

- MONETA present: yes; receive address configured in this process: no.
- The receive address is a deploy secret/human lever, not repo content.
- Aerarium stages accounting and decisions; it never moves money.
