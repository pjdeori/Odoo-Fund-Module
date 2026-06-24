from odoo import models, fields, api
from odoo.exceptions import ValidationError

from .ledger_event_types import (
    EVENT_TRANSFER_HOLD,
    EVENT_TRANSFER_RELEASE,
    EVENT_TRANSFER_OUT,
    EVENT_TRANSFER_IN,
)


# transfer money between two fund buckets
# always preserves full audit trail via ledger (never edits balances directly)
class FundTransferRequest(models.Model):
    _name = 'fund.transfer_request'
    _description = 'Fund Transfer Request'

    _sql_constraints = [
        (
            'transfer_request_number_unique',
            'unique(request_number)',
            'Transfer request number must be unique.'
        ),
        (
            'transfer_amount_positive',
            'CHECK(amount > 0)',
            'Transfer amount must be greater than zero.'
        )
    ]

    request_number = fields.Char(required=True, copy=False)

    source_fund_bucket_id = fields.Many2one(
        'fund.bucket',
        required=True
    )

    destination_fund_bucket_id = fields.Many2one(
        'fund.bucket',
        required=True
    )

    amount = fields.Float(required=True)

    purpose = fields.Text()

    request_date = fields.Date(default=fields.Date.today)

    requested_by = fields.Many2one(
        'res.users',
        default=lambda self: self.env.user
    )

    attachment = fields.Binary()

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('gm_approval', 'GM Approval'),
        ('md_approval', 'MD Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], default='draft')

    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company
    )

    approval_history_ids = fields.One2many(
        'fund.approval_history',
        'source_id',
        domain=[('source_model', '=', 'fund.transfer_request')]
    )

    hold_posted = fields.Boolean(default=False)
    release_posted = fields.Boolean(default=False)
    transfer_posted = fields.Boolean(default=False)

    # BUSINESS RULES -----------------------------------------------------

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError("Amount must be greater than zero.")

    @api.constrains('source_fund_bucket_id', 'destination_fund_bucket_id')
    def _check_buckets(self):
        for rec in self:
            if rec.source_fund_bucket_id == rec.destination_fund_bucket_id:
                raise ValidationError("Source and destination buckets cannot be the same.")
            if rec.source_fund_bucket_id.company_id != rec.company_id:
                raise ValidationError("Source bucket must belong to same company.")
            if rec.destination_fund_bucket_id.company_id != rec.company_id:
                raise ValidationError("Destination bucket must belong to same company.")

    # APPROVAL HISTORY ---------------------------------------------------

    # create permanent approval trail
    def _create_approval_history(self, approval_level, result, comment=None):
        self.env['fund.approval_history'].sudo().create({
            'approver_id': self.env.user.id,
            'approval_level': approval_level,
            'result': result,
            'comment': comment,
            'source_model': self._name,
            'source_id': self.id,
            'company_id': self.company_id.id,
        })

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
            'fund_bucket_id': self.source_fund_bucket_id.id,
            'source_model': self._name,
            'source_id': self.id,
            'company_id': self.company_id.id,
        })

    # WORKFLOW -----------------------------------------------------------

    # submit transfer request
    # reserves amount from source bucket
    def action_submit(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'draft':
                raise ValidationError("Only draft transfers can be submitted.")
            if rec.amount > rec.source_fund_bucket_id.available_fund:
                raise ValidationError("Insufficient balance in source bucket.")
            if rec.hold_posted:
                raise ValidationError("Hold already created.")
            self.env['fund.ledger'].sudo().create({
                'date': fields.Date.today(),
                'amount': rec.amount,
                'event_type': EVENT_TRANSFER_HOLD,
                'fund_bucket_id': rec.source_fund_bucket_id.id,
                'source_model': self._name,
                'source_id': rec.id,
                'company_id': rec.company_id.id,
            })
            rec.hold_posted = True
            rec.state = 'submitted'
            rec._create_audit('submit', prev)

    # gm approval
    # validates user has gm_approver group
    def action_gm_approve(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'submitted':
                raise ValidationError("Only submitted transfers allowed.")
            if not self.env.user.has_group('fund_management.group_gm_approver'):
                raise ValidationError(
                    "You do not have GM approver permissions."
                )
            if rec.requested_by == self.env.user:
                raise ValidationError("You cannot approve your own request.")
            rec._create_approval_history(
                approval_level='gm',
                result='approved'
            )
            rec.state = 'gm_approval'
            rec._create_audit('gm_approve', prev)

    # md approval
    # releases hold, records out from source and in to destination
    # validates user has md_approver group
    def action_md_approve(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'gm_approval':
                raise ValidationError("Not ready for MD approval.")
            if not self.env.user.has_group('fund_management.group_md_approver'):
                raise ValidationError(
                    "You do not have MD approver permissions."
                )
            if rec.requested_by == self.env.user:
                raise ValidationError("You cannot approve your own request.")
            if rec.transfer_posted:
                raise ValidationError("Transfer already processed.")
            if not rec.release_posted:
                self.env['fund.ledger'].sudo().create({
                    'date': fields.Date.today(),
                    'amount': rec.amount,
                    'event_type': EVENT_TRANSFER_RELEASE,
                    'fund_bucket_id': rec.source_fund_bucket_id.id,
                    'source_model': self._name,
                    'source_id': rec.id,
                    'company_id': rec.company_id.id,
                })
                rec.release_posted = True
            self.env['fund.ledger'].sudo().create({
                'date': fields.Date.today(),
                'amount': rec.amount,
                'event_type': EVENT_TRANSFER_OUT,
                'fund_bucket_id': rec.source_fund_bucket_id.id,
                'source_model': self._name,
                'source_id': rec.id,
                'company_id': rec.company_id.id,
            })
            self.env['fund.ledger'].sudo().create({
                'date': fields.Date.today(),
                'amount': rec.amount,
                'event_type': EVENT_TRANSFER_IN,
                'fund_bucket_id': rec.destination_fund_bucket_id.id,
                'source_model': self._name,
                'source_id': rec.id,
                'company_id': rec.company_id.id,
            })
            rec.transfer_posted = True
            rec._create_approval_history(
                approval_level='md',
                result='approved'
            )
            rec.state = 'approved'
            rec._create_audit('md_approve', prev)

    # reject transfer
    # releases held money back to source bucket
    def action_reject(self):
        for rec in self:
            prev = rec.state
            if rec.state not in ('submitted', 'gm_approval', 'md_approval'):
                raise ValidationError("Cannot reject in current state.")
            if rec.hold_posted and not rec.release_posted:
                self.env['fund.ledger'].sudo().create({
                    'date': fields.Date.today(),
                    'amount': rec.amount,
                    'event_type': EVENT_TRANSFER_RELEASE,
                    'fund_bucket_id': rec.source_fund_bucket_id.id,
                    'source_model': self._name,
                    'source_id': rec.id,
                    'company_id': rec.company_id.id,
                })
                rec.release_posted = True
            rec._create_approval_history(
                approval_level='gm' if rec.state == 'gm_approval' else 'md',
                result='rejected'
            )
            rec.state = 'rejected'
            rec._create_audit('reject', prev)

    # cancel transfer
    # releases held money if not yet released
    def action_cancel(self):
        for rec in self:
            prev = rec.state
            if rec.state == 'approved':
                raise ValidationError("Approved transfers cannot be cancelled.")
            if rec.state in ('cancelled', 'rejected'):
                raise ValidationError("Transfer is already closed.")
            if rec.hold_posted and not rec.release_posted:
                self.env['fund.ledger'].sudo().create({
                    'date': fields.Date.today(),
                    'amount': rec.amount,
                    'event_type': EVENT_TRANSFER_RELEASE,
                    'fund_bucket_id': rec.source_fund_bucket_id.id,
                    'source_model': self._name,
                    'source_id': rec.id,
                    'company_id': rec.company_id.id,
                })
                rec.release_posted = True
            rec.state = 'cancelled'
            rec._create_audit('cancel', prev)

    # PROTECTION ---------------------------------------------------------

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError("Only draft transfers can be deleted.")
        return super().unlink()
