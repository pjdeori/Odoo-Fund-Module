from odoo import models, fields, api
from odoo.exceptions import ValidationError

from .ledger_event_types import (
    EVENT_SPENT,
    EVENT_SPEND_REVERSAL,
)


# documents spending against an approved requisition
# linked to a specific fund bucket through the requisition
class FundBill(models.Model):
    _name = 'fund.bill'
    _description = 'Bill'

    _sql_constraints = [
        (
            'bill_number_unique',
            'unique(bill_number)',
            'Bill number must be unique.'
        ),
        (
            'bill_amount_positive',
            'CHECK(amount > 0)',
            'Bill amount must be greater than zero.'
        )
    ]

    bill_number = fields.Char(
        required=True,
        copy=False
    )

    requisition_id = fields.Many2one(
        'fund.requisition',
        required=True
    )

    amount = fields.Float(
        required=True
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled'),
    ], default='draft')

    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company
    )

    attachment = fields.Binary()

    ledger_posted = fields.Boolean(
        default=False
    )

    reversal_posted = fields.Boolean(
        default=False
    )

    fund_bucket_id = fields.Many2one(
        'fund.bucket',
        related='requisition_id.fund_bucket_id',
        store=False
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
            'fund_bucket_id': self.requisition_id.fund_bucket_id.id,
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
                    "Bill amount must be greater than zero."
                )

    @api.constrains('requisition_id', 'amount')
    def _check_requisition(self):
        for rec in self:
            if rec.requisition_id.state != 'approved':
                raise ValidationError(
                    "Only approved requisitions can be billed."
                )
            if rec.amount > rec.requisition_id.remaining_billable_amount:
                raise ValidationError(
                    "Bill amount exceeds the requisition's remaining billable amount."
                )

    @api.constrains('company_id', 'requisition_id')
    def _check_company_consistency(self):
        for rec in self:
            if (
                rec.requisition_id
                and rec.requisition_id.company_id != rec.company_id
            ):
                raise ValidationError(
                    "Requisition must belong to the same company."
                )

    # WORKFLOW ACTIONS ---------------------------------------------------

    # post bill
    # marks amount as spent on the bucket
    def action_post(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'draft':
                raise ValidationError(
                    "Only draft bills can be posted."
                )
            if rec.ledger_posted:
                raise ValidationError(
                    "Bill already posted to ledger."
                )
            if rec.amount > rec.requisition_id.remaining_billable_amount:
                raise ValidationError(
                    "Bill amount exceeds remaining billable amount."
                )
            self.env['fund.ledger'].sudo().create({
                'date': fields.Date.today(),
                'amount': rec.amount,
                'event_type': EVENT_SPENT,
                'fund_bucket_id': rec.requisition_id.fund_bucket_id.id,
                'source_model': self._name,
                'source_id': rec.id,
                'company_id': rec.company_id.id,
            })
            rec.ledger_posted = True
            rec.state = 'posted'
            rec._create_audit('post', prev)

    # cancel / reverse bill
    def action_cancel(self):
        for rec in self:
            prev = rec.state
            if rec.state == 'cancelled':
                raise ValidationError(
                    "Bill is already cancelled."
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
                'amount': rec.amount,
                'event_type': EVENT_SPEND_REVERSAL,
                'fund_bucket_id': rec.requisition_id.fund_bucket_id.id,
                'source_model': self._name,
                'source_id': rec.id,
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
                    "Only draft bills can be deleted."
                )
        return super().unlink()
