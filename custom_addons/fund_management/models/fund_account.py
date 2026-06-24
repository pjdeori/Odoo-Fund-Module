from odoo import models, fields, api
from odoo.exceptions import ValidationError

from .ledger_event_types import (
    EVENT_INCOMING,
    EVENT_INCOMING_REVERSAL,
    EVENT_HOLD,
    EVENT_RELEASE,
    EVENT_ASSIGN,
)


# represents a financial account (bank, cash, etc.)
# IMPORTANT: this model does NOT store money directly
# it computes balances from fund.ledger
class FundAccount(models.Model):
    _name = 'fund.account'
    _description = 'Fund Account'

    # prevent duplicate accounts within same company
    _sql_constraints = [
        (
            'fund_account_company_unique',
            'unique(name, company_id)',
            'Fund account name must be unique per company.'
        )
    ]

    # name of the account (bank, cash, etc.)
    name = fields.Char(
        required=True
    )

    # company ownership (multi-company safety)
    # many rows can point to same row
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company
    )

    # currency (needed for monetary correctness in multi currency accounts)
    # many rows can point to same row
    currency_id = fields.Many2one(
        'res.currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )

    # link to all ledger entries (financial truth source)
    # many fund.ledger rows point to one fund.account row
    # not stored in fund.account table
    ledger_line_ids = fields.One2many(
        'fund.ledger',      # find from ledger rows
        'fund_account_id'   # all rows that have this id
    )

    # DERIVED BALANCES (READ ONLY) ---------------------------------------

    # total money ever received into this account
    total_received = fields.Float(
        compute="_compute_balances",
        store=False
    )

    # money not yet assigned/allocated and not held
    available_unassigned_balance = fields.Float(
        compute="_compute_balances",
        store=False
    )

    # money currently locked in processes
    # allocation / transfer / requisition
    amount_currently_on_hold = fields.Float(
        compute="_compute_balances",
        store=False
    )

    # total money already assigned to buckets
    # project / expense head
    total_assigned_amount = fields.Float(
        compute="_compute_balances",
        store=False
    )

    @api.depends(
        'ledger_line_ids.amount',
        'ledger_line_ids.event_type'
    )
    def _compute_balances(self):
        for rec in self:

            total_received = 0.0
            held_total = 0.0
            assigned_total = 0.0

            # read all ledger entries for this account
            for line in rec.ledger_line_ids:

                # incoming funds increase available money
                if line.event_type == EVENT_INCOMING:
                    total_received += line.amount

                # reversal removes previously received money
                elif line.event_type == EVENT_INCOMING_REVERSAL:
                    total_received += line.amount

                # money temporarily reserved
                elif line.event_type == EVENT_HOLD:
                    held_total += line.amount

                # held money released back
                elif line.event_type == EVENT_RELEASE:
                    held_total -= line.amount

                # money permanently assigned to bucket
                elif line.event_type == EVENT_ASSIGN:
                    assigned_total += line.amount

            rec.total_received = total_received

            rec.total_assigned_amount = assigned_total

            rec.amount_currently_on_hold = held_total

            rec.available_unassigned_balance = (
                total_received
                - held_total
                - assigned_total
            )

    # BUSINESS RULES -----------------------------------------------------

    # account name cannot be empty
    @api.constrains('name')
    def _check_name(self):
        for rec in self:

            if not rec.name or not rec.name.strip():
                raise ValidationError(
                    "Account name is required."
                )

    # DATA PROTECTION ----------------------------------------------------

    # accounts with ledger activity cannot be deleted
    def unlink(self):
        for rec in self:

            if rec.ledger_line_ids:
                raise ValidationError(
                    "Accounts with ledger history cannot be deleted."
                )

        return super().unlink()