from odoo import models, fields, api
from odoo.exceptions import ValidationError

from .ledger_event_types import (
    EVENT_ASSIGN,
    EVENT_REQUISITION_HOLD,
    EVENT_REQUISITION_RELEASE,
    EVENT_TRANSFER_HOLD,
    EVENT_TRANSFER_RELEASE,
    EVENT_TRANSFER_IN,
    EVENT_TRANSFER_OUT,
    EVENT_SPENT,
    EVENT_SPEND_REVERSAL,
)


# project or expense head
# receives allocated funds from fund accounts
class FundBucket(models.Model):
    _name = 'fund.bucket'
    _description = 'Fund Bucket'

    _sql_constraints = [
        (
            'bucket_name_company_unique',
            'unique(name, company_id)',
            'Bucket name must be unique per company.'
        )
    ]

    # bucket name
    # example:
    # Project A
    # Marketing
    # Office Rent
    name = fields.Char(
        required=True
    )

    # bucket type
    type = fields.Selection([
        ('project', 'Project'),
        ('expense_head', 'Expense Head'),
    ], required=True)

    # company ownership
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company
    )

    # ledger entries affecting this bucket
    # many ledger rows may affect one bucket
    ledger_line_ids = fields.One2many(
        'fund.ledger',
        'fund_bucket_id'
    )

    # DERIVED BALANCES --------------------------------------------------

    # total money allocated into this bucket
    total_allocated_fund = fields.Float(
        compute='_compute_balances',
        store=False
    )

    # money reserved by approved requisitions
    requisition_hold = fields.Float(
        compute='_compute_balances',
        store=False
    )

    # money reserved by transfer requests
    transfer_hold = fields.Float(
        compute='_compute_balances',
        store=False
    )

    # money spent through bills
    total_spent_amount = fields.Float(
        compute='_compute_balances',
        store=False
    )

    # money received from transfers
    incoming_transfers = fields.Float(
        compute='_compute_balances',
        store=False
    )

    # money sent through transfers
    outgoing_transfers = fields.Float(
        compute='_compute_balances',
        store=False
    )

    # approved but not yet spent
    approved_unspent_amount = fields.Float(
        compute='_compute_balances',
        store=False
    )

    # immediately available balance
    available_fund = fields.Float(
        compute='_compute_balances',
        store=False
    )

    # COMPUTATIONS ------------------------------------------------------

    @api.depends(
        'ledger_line_ids.amount',
        'ledger_line_ids.event_type'
    )
    def _compute_balances(self):
        for rec in self:

            allocated = 0.0
            requisition_hold = 0.0
            transfer_hold = 0.0
            spent = 0.0
            transfer_in = 0.0
            transfer_out = 0.0

            # read all ledger entries affecting this bucket
            for line in rec.ledger_line_ids:

                # funds allocated into bucket
                if line.event_type == EVENT_ASSIGN:
                    allocated += line.amount

                # requisition reserve
                elif line.event_type == EVENT_REQUISITION_HOLD:
                    requisition_hold += line.amount

                # requisition released
                elif line.event_type == EVENT_REQUISITION_RELEASE:
                    requisition_hold -= line.amount

                # transfer reserve
                elif line.event_type == EVENT_TRANSFER_HOLD:
                    transfer_hold += line.amount

                # transfer reserve released
                elif line.event_type == EVENT_TRANSFER_RELEASE:
                    transfer_hold -= line.amount

                # incoming transfer
                elif line.event_type == EVENT_TRANSFER_IN:
                    transfer_in += line.amount

                # outgoing transfer
                elif line.event_type == EVENT_TRANSFER_OUT:
                    transfer_out += abs(line.amount)

                # bill payment / spending
                elif line.event_type == EVENT_SPENT:
                    spent += line.amount

                # spending reversal
                elif line.event_type == EVENT_SPEND_REVERSAL:
                    spent -= abs(line.amount)

            rec.total_allocated_fund = allocated

            rec.requisition_hold = requisition_hold

            rec.transfer_hold = transfer_hold

            rec.total_spent_amount = spent

            rec.incoming_transfers = transfer_in

            rec.outgoing_transfers = transfer_out

            # funds approved for this bucket
            # regardless of temporary holds
            rec.approved_unspent_amount = (
                allocated
                + transfer_in
                - transfer_out
                - spent
            )

            # immediately usable funds
            rec.available_fund = (
                allocated
                + transfer_in
                - transfer_out
                - requisition_hold
                - transfer_hold
                - spent
            )

    # BUSINESS RULES ----------------------------------------------------

    # bucket name cannot be blank
    @api.constrains('name')
    def _check_name_not_blank(self):
        for rec in self:

            if not rec.name or not rec.name.strip():
                raise ValidationError(
                    "Bucket name cannot be blank."
                )

    # DATA PROTECTION ---------------------------------------------------

    # buckets with financial history cannot be deleted
    def unlink(self):
        for rec in self:

            if rec.ledger_line_ids:
                raise ValidationError(
                    "Buckets with ledger history cannot be deleted."
                )

        return super().unlink()