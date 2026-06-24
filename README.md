# NN Fund Management

An Odoo 18 custom module for managing incoming funds, allocations, requisitions, bills, transfers, and multi-level approval workflow.

**Developer:** Trainee Software Developer — NN Services & Engineering Ltd.
**Module Name:** `nn_fund_management`

---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Testing](#testing)
- [Architecture](#architecture)
- [Specification](#specification)
  - [1. Fund Accounts & Incoming Funds](#1-fund-accounts-and-incoming-funds)
  - [2. Fund Allocation](#2-fund-allocation)
  - [3. Approval Process](#3-approval-process)
  - [4. Project & Expense Balances](#4-project-and-expense-balances)
  - [5. Fund Requisition](#5-fund-requisition)
  - [6. Bill Control](#6-bill-control)
  - [7. Fund Transfer](#7-fund-transfer)
  - [8. Security & Access Control](#8-security-and-access-control)
  - [9. Audit History](#9-audit-history)
  - [10. Bonus Features](#10-bonus-features)
- [Implementation Details](#implementation-details)
  - [Security](#security)
  - [File Responsibilities](#file-responsibilities)
  - [AI Usage Transparency](#ai-usage-transparency)
  - [Known Limitations](#known-limitations)
  - [Assumptions](#assumptions)
  - [Odoo 18 Findings (Resolved)](#odoo-18-findings-resolved)

---

## Requirements

| Requirement | Detail |
|-------------|--------|
| Odoo Version | Odoo 18 Community Edition |
| Python Version | 3.12 |
| Dependencies | `base`, `mail` (no external packages) |
| Database | PostgreSQL 18 |

## Installation

1. Shallow clone Odoo 18 into `resources/`
   ```bash
   git clone -b 18.0 --depth 1 https://github.com/odoo/odoo.git resources/odoo18
   ```

2. Move only essential files to project root
   ```bash
   mv resources/odoo18/odoo .
   mv resources/odoo18/odoo-bin .
   mv resources/odoo18/requirements.txt .
   mv resources/odoo18/addons .
   ```

3. Create Python virtual env
   ```bash
   python -3.12 -m venv venv
   ```

4. Activate venv
   ```bash
   source venv/Scripts/activate
   ```

5. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

6. Create PostgreSQL user
   ```bash
   psql -U postgres -c "CREATE USER odoo WITH PASSWORD 'odoo';"
   psql -U postgres -c "ALTER USER odoo CREATEDB;"
   ```

7. Create odoo.conf
   ```bash
   cat > odoo.conf <<'EOF'
   [options]
   db_host = localhost
   db_port = 5432
   db_user = odoo
   db_password = odoo
   addons_path = addons, custom_addons
   http_port = 8069
   dev_mode = all
   log_level = debug
   EOF
   ```

8. Run Odoo
   ```bash
   python odoo-bin --config=odoo.conf
   ```

## Configuration

1. **Create fund accounts** — Requests > Finance > Fund Accounts
2. **Create buckets** (projects / expense heads) — Requests > Finance > Buckets
3. **Assign security groups** to users:
   - **Fund User** — create and view own requests
   - **Finance User** — confirm incoming funds, manage bills
   - **GM Approver** — first-level approval
   - **MD Approver** — second-level approval
   - **Fund Administrator** — full access, cancel approved transactions

## Testing

1. Activate developer mode.
2. Record an incoming fund and confirm it.
3. Create a draft allocation request, submit, approve via GM then MD.
4. Verify balances update at each step.
5. Repeat for requisitions, transfers, and bills.

---

## Architecture

### Models (11)

| Model | Purpose |
|-------|---------|
| `fund_account` | Bank/cash accounts with computed available, held, assigned, received balances |
| `fund_bucket` | Projects or expense heads with allocated, available, hold, spent balances |
| `fund_incoming` | Incoming fund records; confirmed amounts flow to account unassigned balance |
| `fund_ledger` | Immutable single source of truth for all money movements |
| `ledger_event_types` | Constants defining every financial event type |
| `fund_allocation_request` | Assign funds from account to a bucket (4-step approval) |
| `fund_requisition` | Reserve spendable funds from a bucket (4-step approval, links to bills) |
| `fund_transfer_request` | Move funds between buckets (4-step approval) |
| `fund_bill` | Spend against an approved requisition (enforces remaining-amount cap) |
| `fund_approval_history` | Immutable record of every GM and MD approval/rejection |
| `fund_audit_history` | Immutable log of document lifecycle actions |

### Key Design Decisions

- **Double-spending prevention** — holds are created on submit (not at approval), blocking the same funds from being used concurrently by another request
- **`sudo()` for ledger/approval/audit creation** — keeps ACLs clean without granting create access on audit-only models
- **No `write()` overrides** — state transitions happen only through action methods, each validating the current state
- **Server-side group checks** — all approve/reject methods verify group membership via `has_group()` and prevent self-approval
- **Computed balance fields** — all balance fields are `compute` methods, never stored or editable
- **Generic approval history** — `approval_history` uses `source_model`/`source_id` rather than per-model relation fields

### File Structure

```
nn_fund_management/
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── fund_account.py
│   ├── fund_bucket.py
│   ├── fund_incoming.py
│   ├── fund_allocation_request.py
│   ├── fund_requisition.py
│   ├── fund_transfer_request.py
│   ├── fund_bill.py
│   ├── fund_ledger.py
│   ├── fund_approval_history.py
│   ├── fund_audit_history.py
│   └── ledger_event_types.py
├── views/
│   ├── fund_account_views.xml
│   ├── fund_bucket_views.xml
│   ├── fund_incoming_views.xml
│   ├── fund_allocation_request_views.xml
│   ├── fund_requisition_views.xml
│   ├── fund_transfer_request_views.xml
│   ├── fund_bill_views.xml
│   ├── fund_ledger_views.xml
│   ├── fund_approval_history_views.xml
│   ├── fund_audit_history_views.xml
│   └── fund_menus.xml
├── security/
│   ├── fund_management_groups.xml
│   ├── ir.model.access.csv
│   └── fund_management_record_rules.xml
└── data/
    └── fund_sequence_data.xml
```

---

## Specification

### 1. Fund Accounts and Incoming Funds

Fund accounts represent bank, cash, or other financial accounts. Each account displays:

- Total received
- Available unassigned balance
- Amount on hold
- Total assigned amount

Incoming funds are recorded with fund account, date, amount, transaction reference, sender, description, and attachment. On confirmation the amount is added to the account's unassigned balance. The same transaction reference cannot be used twice within the same fund account.

### 2. Fund Allocation

Funds may be assigned to a project or an expense head (not both). An allocation request contains request number, fund account, project or expense head, amount, purpose, request date, requested by, attachment, status, and approval history.

**Workflow:** Draft -> Submitted -> GM Approval -> MD Approval -> Approved / Rejected / Cancelled

**Rules:**
- On submit: amount deducted from available unassigned balance and placed on hold
- On approval: hold released, amount becomes available under the selected project/expense head
- On rejection/cancellation: amount returns to unassigned balance
- Request is blocked if amount exceeds available unassigned balance

### 3. Approval Process

Two approval levels: General Manager then Managing Director.

- GM approval must complete before MD approval
- MD cannot approve before GM
- Only the current approver can approve or reject
- Users cannot approve their own requests
- Approvers are configurable via security groups (not hardcoded)
- Every decision records approver, date, level, comment, and result
- Repeated actions do not create duplicate fund movements

Applies to: allocation requests, fund requisitions, fund transfers.

### 4. Project and Expense Balances

Each bucket displays:

- Total allocated fund
- Available fund
- Requisition hold
- Transfer hold
- Approved but unspent amount
- Total spent amount
- Incoming transfers
- Outgoing transfers

All balance fields are computed automatically. Manual editing is blocked. Negative balances are not allowed.

### 5. Fund Requisition

Users request funds from a project or expense head. Contains requisition number, project/expense head, amount, purpose, request date, required date, requested by, attachment, status, approval history, and remaining billable amount.

**Workflow:** Draft -> Submitted -> GM Approval -> MD Approval -> Approved / Rejected / Cancelled / Closed

**Rules:**
- On submit: checks available balance, places amount on hold
- On approval: amount reserved for bills against the requisition
- On rejection/cancellation: amount returns to available balance
- Closed when fully billed or unused amount is released

### 6. Bill Control

Bills are linked to approved fund requisitions.

- Only approved requisitions can be used
- Bill must use the same project/expense head as the requisition
- Cannot exceed the remaining billable amount
- Multiple partial bills allowed
- Total billed cannot exceed approved amount
- Cross-project/expense-head bills are blocked
- On post: amount marked as spent, remaining billable decreases
- On cancellation: amount returns to remaining billable (no new funds created)

### 7. Fund Transfer

Transfers between: project to project, project to expense head, expense head to project, expense head to expense head.

**Workflow:** Draft -> Submitted -> GM Approval -> MD Approval -> Approved / Rejected / Cancelled

**Rules:**
- On submit: amount deducted from source available balance, placed on transfer hold
- On approval: amount added to destination balance
- On rejection/cancellation: amount returns to source balance
- Amount cannot exceed source available balance
- Source and destination cannot be the same

### 8. Security and Access Control

Security groups: Fund User, Finance User, GM Approver, MD Approver, Fund Administrator.

- Fund users create and view allowed requests
- Only assigned approvers can approve or reject
- Only authorized finance users can confirm incoming funds
- Only authorized users can cancel approved transactions
- Multi-company records isolated
- Security checked server-side (ACLs, record rules, explicit `has_group()` checks)

### 9. Audit History

Every financial action preserves:

- Record creator
- Person who submitted the request
- Approver or rejecter
- Previous and new status
- Date and time
- Comments
- Amount
- Related fund account
- Related project or expense head
- Reference document

Confirmed financial records cannot be deleted without proper cancellation or reversal.

### 10. Bonus Features

**Configurable Approval Rules** — rules based on request type, amount range, company, project/category, approval sequence, user/group.

**Bank Email Integration** — prototype that reads bank notification emails and creates incoming fund records. Deduplicates by email message ID and transaction reference.

**Dashboard and Notifications** — overview of totals, balances, pending approvals, project/expense-head balances, recent movements, and Odoo activities for workflow events.

---

## Implementation Details

### Security

#### Model Access (ir.model.access.csv)

| Group | fund.account | fund.bucket | allocation_request | requisition | transfer_request | incoming | bill | ledger | approval_history | audit_history |
|-------|-------------|------------|-------------------|-------------|-----------------|----------|------|--------|-----------------|---------------|
| Fund User | R | R | CRU | CRU | CRU | — | — | R+C | R | R |
| Finance User | R | R | — | — | — | CRU | CRU | R+C | R | R |
| GM Approver | R | R | RU | RU | RU | R | — | R+C | R+C | R |
| MD Approver | R | R | RU | RU | RU | R | — | R+C | R+C | R |
| Administrator | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD |

**Legend:** C=Create, R=Read, U=Update, D=Delete. Groups without explicit access are denied. System models (ledger, approval_history, audit_history) are created by workflow actions, not directly via UI.

#### Group Actions by Model

- **Fund User** — allocation_request, requisition, transfer_request (CRU). account, bucket (R).
- **Finance User** — incoming, bill (CRU). account, bucket (R).
- **GM Approver** — allocation_request, requisition, transfer_request (RU). account, bucket, incoming (R).
- **MD Approver** — allocation_request, requisition, transfer_request (RU). account, bucket, incoming (R).
- **Administrator** — Full CRUD on all models.

### File Responsibilities

| File | Responsibility |
|------|---------------|
| **ledger_event_types.py** | Constants defining every financial event type used by the ledger |
| **fund_account.py** | Financial accounts with computed available, held, assigned, and received balances |
| **fund_ledger.py** | Immutable single source of truth for all money movements; drives balance calculations |
| **fund_incoming.py** | Records incoming funds into a fund account, with confirmation and cancellation flows |
| **fund_bucket.py** | Projects or expense heads with computed allocated, held, available, and spent balances |
| **fund_allocation_request.py** | Requests to assign money from a fund account into a project or expense head |
| **fund_approval_history.py** | Immutable record of every GM and MD approval or rejection decision |
| **fund_requisition.py** | Requests to reserve spendable funds from a project or expense head bucket |
| **fund_transfer_request.py** | Transfers money between two buckets (project to project, project to expense head, etc.) |
| **fund_bill.py** | Spends against an approved requisition, deducted from the bucket's available balance |
| **fund_audit_history.py** | Immutable log of document lifecycle actions (submit, approve, reject, cancel, etc.) |

### AI Usage Transparency

AI tools (OpenCode) were used to:

- Scaffold model and view files from the requirements document
- Generate security group definitions and ACL entries
- Refactor `write()` overrides into action methods
- Draft documentation

All development was done via Git Bash terminal — helper scripts are in `scripts/`.

All generated code was reviewed and modified by the candidate. Known AI-generated errors that were corrected:

| Error | Fix |
|-------|-----|
| `states` attribute in views (removed in Odoo 18) | Replaced with `invisible` domain expressions |
| `write()` overrides blocking workflow state transitions | Removed entirely from all models |
| `<tree>` tag usage (renamed to `<list>` in Odoo 18) | Corrected globally across all view files |
| `view_mode="tree,form"` (renamed to `list,form`) | Corrected in manifest and menu actions |

### Known Limitations

- Approval levels are hardcoded to GM -> MD (not configurable via UI without bonus feature)
- No Odoo Invoicing/Accounting integration — bills are a custom model
- No real-time notifications or Odoo activities
- All balances are computed per-record; performance may degrade with very large datasets
- Single-currency (BDT) — no multi-currency support
- Bank email integration is a prototype only (bonus feature)
- No dashboard view — access via standard list/form menus

### Assumptions

- Transfers are bucket-to-bucket (project/expense head), not account-to-account
- The approval order (GM before MD) is enforced programmatically
- Holds are created on submit (not during approval) to prevent double-spending during pending period
- Confirmed financial records should be reversed/cancelled, not deleted
- `sudo()` is used for ledger, approval_history, and audit_history creation to keep ACLs simple

### Odoo 18 Findings (Resolved)

**1. `<menuitem>` without `action` does not clear the DB value during upgrade**
Root menus keep their `action` reference even after the XML attribute is removed. If the referenced model is inaccessible to certain users, Odoo prunes the entire menu branch.

*Resolution:* Explicitly clear with `<record>`:
```xml
<record id="menu_fund_management" model="ir.ui.menu">
    <field name="action" eval="False"/>
</record>
```

**2. `<menuitem>` without `groups` does not clear DB restrictions**
Group restrictions persist across upgrades even after removing the `groups` attribute from the XML.

*Resolution:* Clear with `[(5,)]`:
```xml
<record id="menu_fund_management" model="ir.ui.menu">
    <field name="groups_id" eval="[(5,)]"/>
</record>
```

**3. `<menuitem>` `groups` attribute requires full module prefix**
Unlike `ref()` in eval contexts, the `groups` attribute on `<menuitem>` does not resolve unprefixed XML IDs.
```xml
<!-- Works in ref() but NOT in menuitem groups -->
<menuitem id="..." groups="group_finance_user"/>

<!-- Must use full prefix -->
<menuitem id="..." groups="fund_management.group_finance_user"/>
```
Odoo core follows this pattern: `sales_team.group_sale_salesman`, not `group_sale_salesman`.
