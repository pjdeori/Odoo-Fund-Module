from odoo import models, fields, api
from odoo.exceptions import ValidationError

from .ledger_event_types import LEDGER_EVENT_TYPES


# stores immutable money movements that become the source of truth for balances
class FundLedger(models.Model):
    _name = 'fund.ledger'
    _description = 'Fund Ledger'
    _order = 'date desc, id desc'

    # prevents duplicate financial event posting
    _sql_constraints = [
        (
            'fund_ledger_source_event_unique',
            'unique(source_model, source_id, event_type)',
            'This financial event has already been posted.'
        ),
        (
            'fund_ledger_amount_not_zero',
            'CHECK(amount <> 0)',
            'Ledger amount cannot be zero.'
        )
    ]

    # date when the financial event happened
    date = fields.Date(
        required=True
    )

    # type of financial event
    # drives all balance calculations
    event_type = fields.Selection(
        LEDGER_EVENT_TYPES,
        required=True
    )

    # amount involved in the movement
    # positive and negative values are allowed
    # meaning depends on event type
    amount = fields.Float(
        required=True
    )

    # user who created the ledger entry
    created_by_id = fields.Many2one(
        'res.users',
        default=lambda self: self.env.user,
        readonly=True
    )

    # account involved in the movement
    fund_account_id = fields.Many2one(
        'fund.account'
    )

    # bucket involved in the movement
    fund_bucket_id = fields.Many2one(
        'fund.bucket'
    )

    # originating business document
    # examples:
    # fund.incoming
    # fund.allocation_request
    # fund.requisition
    source_model = fields.Char(
        required=True
    )

    # originating record id
    source_id = fields.Integer(
        required=True
    )

    # internal reference
    reference = fields.Char()

    # external reference
    # bank transaction id, cheque number, etc.
    external_reference = fields.Char(
        index=True
    )

    # company ownership
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company
    )

    # BUSINESS RULES -----------------------------------------------------

    # ledger amount cannot be zero
    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:

            if rec.amount == 0:
                raise ValidationError(
                    "Ledger amount cannot be zero."
                )

    # source reference must be complete
    @api.constrains(
        'source_model',
        'source_id'
    )
    def _check_source_reference(self):
        for rec in self:

            if not rec.source_model:
                raise ValidationError(
                    "Source model is required."
                )

            if not rec.source_id:
                raise ValidationError(
                    "Source id is required."
                )

    # DATA PROTECTION ----------------------------------------------------

    # ledger entries are immutable
    # corrections must happen through reversal entries
    def write(self, vals):
        raise ValidationError(
            "Ledger entries cannot be modified."
        )

    # ledger entries are permanent
    def unlink(self):
        raise ValidationError(
            "Ledger entries cannot be deleted."
        )