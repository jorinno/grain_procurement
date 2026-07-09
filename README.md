# Grain Procurement Management System — Version 1 (Manual Payment Workflow)

A working implementation of the Grain Purchase and Payment Workflow: a
purchase agent records a grain purchase, the system calculates the
supplier payout and agent commission from admin-configured rates, and a
procurement manager confirms both payments manually via Mobile Money
before the purchase is marked complete.

## Requirements

- Python 3.10+ (uses the `str | None` type-hint syntax)
- No external dependencies — uses the standard library only (`sqlite3`)

## Setup

```bash
python seed.py
```

This creates `grain_procurement.db` and three starter accounts:

| Role    | Username | Password    |
|---------|----------|-------------|
| Admin   | admin    | admin123    |
| Manager | manager  | manager123  |
| Agent   | agent    | agent123    |

Starter config: maize @ 1200/kg (commission 100/kg), beans @ 2800/kg
(commission 150/kg).

## Running

Two front ends are included, both built on the same service layer in `app/`.

### Web front end (recommended)

```bash
pip install flask
python webapp.py
```

Open `http://127.0.0.1:5000` and log in as any of the three roles. Each
role is routed to its own dashboard (`/agent`, `/manager`, `/admin`) and
is blocked from the others.

### CLI

```bash
python main.py
```

Log in as any of the three roles to reach that role's menu:

- **Agent** — start a new purchase (enter category + weight, review the
  read-only calculation, enter and verify supplier Mobile Money details,
  confirm and submit).
- **Manager** — view pending purchases, record payment confirmations
  (supplier payout and agent commission are confirmed separately, each
  with its own transaction reference).
- **Admin** — add grain categories, set prices, set commission rates,
  activate/deactivate categories.

## Verifying it works

```bash
python test_workflow.py
```

Runs an end-to-end smoke test: submits a purchase, confirms both
payments, checks the status transitions (`PAYMENT_PENDING` →
`PARTIALLY_PAID` → `COMPLETED`), and exercises the key business rules
(invalid weight, unknown/inactive category, duplicate payment
confirmation, duplicate transaction reference, invalid Mobile Money
number, and price/rate snapshotting on historical purchases).

## Project structure

```
app/
  database.py            SQLite schema + connection helper
  auth.py                Login, password hashing, role checks
  exceptions.py          Domain exceptions (map to SOP section 10)
  audit.py               Audit log recording
  admin_service.py       Admin Configuration Workflow (SOP section 5)
  notification_service.py  Agent/manager notifications (SOP step 10)
  purchase_service.py    Core purchase + payment workflow (SOP steps 4-14)
web/
  templates/             Jinja templates (login, agent, manager, admin)
  static/style.css        Design system (see "Web design" below)
seed.py                  Bootstraps starter users and config
main.py                  CLI entry point (role-based menus)
webapp.py                Flask web front end (same service layer as the CLI)
test_workflow.py         End-to-end smoke test
```

## Web design

The web front end is styled as a weighbridge ticket / procurement ledger
rather than a generic admin-dashboard template:

- Purchases render as **ticket stubs** with a dashed perforation line and
  a rotated rubber-stamp status badge (`PENDING` / `PARTIALLY PAID` /
  `COMPLETED`), echoing a physical grain receipt or MoMo confirmation slip.
- A mono face carries the data that matters operationally (weights,
  prices, purchase references, transaction references); a plain sans face
  carries labels and body copy.
- A warm charcoal background with a grain-gold accent, muted olive-green
  for paid/success states, and rust for errors — colors pulled from the
  subject (grain, soil, ink stamps) rather than a default palette.
- No JavaScript framework: server-rendered Jinja templates and plain
  HTML forms, matching the CLI's own step-by-step flow (calculate →
  review → enter supplier details → confirm).

## What's implemented vs. what's still Version 1-limited

**Implemented, matching the spec:**
- Role-based authentication (agent / manager / admin)
- Category, weight, price, and commission-rate validation
- Supplier-payout and agent-commission calculation from active config
- Read-only calculated values; editable supplier fields until confirmed
- Purchase saving with a generated purchase reference
- Agent + manager notifications on save
- Manual payment confirmation per payment type, with duplicate-reference
  and duplicate-confirmation protection
- Status lifecycle: `PAYMENT_PENDING` → `PARTIALLY_PAID` → `COMPLETED`
- Admin price/commission-rate updates that don't retroactively change
  historical purchases (each purchase stores its own snapshot)
- Audit log of key actions

**Deliberately out of scope for Version 1** (per the spec itself):
- No live Mobile Money API integration — transfers are manual, the app
  only records transaction references (planned for Version 2)
- No web front end — this is a CLI exercising the same service layer a
  web app would call
- `system-scope.md` and `business-rules.md` were uploaded empty, so any
  requirements only defined in those files (and not restated in the
  main workflow doc) may not be covered here
