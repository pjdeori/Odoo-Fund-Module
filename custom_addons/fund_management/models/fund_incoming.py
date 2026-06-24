from odoo import models, fields, api
from odoo.exceptions import ValidationError

from .ledger_event_types import (
    EVENT_INCOMING,
    EVENT_INCOMING_REVERSAL,
)


# document representing incoming money into a fund account
# actual financial truth is stored in fund.ledger
class FundIncoming(models.Model):
    _name = 'fund.incoming'
    _description = 'Fund Incoming'

    _sql_constraints = [
        (
            'incoming_reference_unique',
            'unique(transaction_reference, fund_account_id)',
            'Duplicate transaction reference for this fund account.'
        ),
        (
            'incoming_amount_positive',
            'CHECK(amount > 0)',
            'Amount must be greater than zero.'
        )
    ]

    date = fields.Date(
        required=True
    )

    source = fields.Char()

    fund_account_id = fields.Many2one(
        'fund.account',
        required=True
    )

    amount = fields.Float(
        required=True
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ], default='draft')

    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company
    )

    transaction_reference = fields.Char(
        required=True
    )

    description = fields.Text()

    attachment = fields.Binary()

    ledger_posted = fields.Boolean(
        default=False
    )

    reversal_posted = fields.Boolean(
        default=False
    )

    # AUDIT HISTORY ------------------------------------------------------

    # create immutable audit trail entry for every workflow transition
    def _create_audit(self, action, prev_state, comment=None):
        self.env['fund.audit_history'].sudo().create({
            'actor_id': self.env.user.id,
            'action': action,
            'previous_state': prev_state,
            'new_state': self.state,
            'comment': comment,
            'amount': self.amount,
            'fund_account_id': self.fund_account_id.id,
            'source_model': self._name,
            'source_id': self.id,
            'company_id': self.company_id.id,
        })

    # BUSINESS RULES -----------------------------------------------------

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(
                    "Amount must be greater than zero."
                )

    @api.constrains('company_id', 'fund_account_id')
    def _check_account_company(self):
        for rec in self:
            if (
                rec.fund_account_id
                and rec.company_id
                and rec.fund_account_id.company_id != rec.company_id
            ):
                raise ValidationError(
                    "Fund account must belong to the same company."
                )

    # WORKFLOW ACTIONS ---------------------------------------------------

    # confirm incoming funds
    # creates the financial ledger entry
    def action_confirm(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'draft':
                raise ValidationError(
                    "Only draft records can be confirmed."
                )
            if rec.ledger_posted:
                raise ValidationError(
                    "Incoming fund already confirmed."
                )
            self.env['fund.ledger'].sudo().create({
                'date': rec.date,
                'amount': rec.amount,
                'event_type': EVENT_INCOMING,
                'fund_account_id': rec.fund_account_id.id,
                'source_model': self._name,
                'source_id': rec.id,
                'reference': rec.transaction_reference,
                'external_reference': rec.transaction_reference,
                'company_id': rec.company_id.id,
            })
            rec.ledger_posted = True
            rec.state = 'confirmed'
            rec._create_audit('confirm', prev)

    # cancel incoming funds
    # financial history is preserved through reversal
    def action_cancel(self):
        for rec in self:
            prev = rec.state
            if rec.state == 'cancelled':
                raise ValidationError(
                    "Record is already cancelled."
                )
            if rec.state == 'draft':
                rec.state = 'cancelled'
                rec._create_audit('cancel', prev)
                continue
            if rec.reversal_posted:
                raise ValidationError(
                    "Reversal already posted."
                )
            self.env['fund.ledger'].sudo().create({
                'date': fields.Date.today(),
                'amount': -rec.amount,
                'event_type': EVENT_INCOMING_REVERSAL,
                'fund_account_id': rec.fund_account_id.id,
                'source_model': self._name,
                'source_id': rec.id,
                'reference': f"REV-{rec.transaction_reference}",
                'external_reference': f"REV-{rec.transaction_reference}",
                'company_id': rec.company_id.id,
            })
            rec.reversal_posted = True
            rec.state = 'cancelled'
            rec._create_audit('cancel', prev)

    # DATA PROTECTION ----------------------------------------------------

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError(
                    "Only draft records can be deleted."
                )
        return super().unlink()
