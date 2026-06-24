from odoo import models, fields, api
from odoo.exceptions import ValidationError

from .ledger_event_types import (
    EVENT_HOLD,
    EVENT_RELEASE,
    EVENT_ASSIGN,
)


# request to allocate money from a fund account
# into a project or expense head
class FundAllocationRequest(models.Model):
    _name = 'fund.allocation_request'
    _description = 'Allocation Request'

    # request number must be globally unique
    _sql_constraints = [
        (
            'allocation_request_number_unique',
            'unique(request_number)',
            'Request number must be unique.'
        ),
        (
            'allocation_request_amount_positive',
            'CHECK(amount > 0)',
            'Amount must be greater than zero.'
        )
    ]

    # business identifier
    request_number = fields.Char(
        required=True,
        copy=False
    )

    # amount requested
    amount = fields.Float(
        required=True
    )

    # business justification
    purpose = fields.Text()

    # request metadata
    request_date = fields.Date(
        default=fields.Date.today
    )

    requested_by = fields.Many2one(
        'res.users',
        default=lambda self: self.env.user
    )

    # supporting documents
    attachment = fields.Binary()

    # source account
    fund_account_id = fields.Many2one(
        'fund.account',
        required=True
    )

    # destination bucket
    fund_bucket_id = fields.Many2one(
        'fund.bucket',
        required=True
    )

    # workflow state
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('gm_approval', 'GM Approval'),
        ('md_approval', 'MD Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], default='draft')

    # approval history
    approval_history_ids = fields.One2many(
        'fund.approval_history',
        'source_id',
        domain=[('source_model', '=', 'fund.allocation_request')]
    )

    # company ownership
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company
    )

    # idempotency flags
    hold_posted = fields.Boolean(default=False)
    release_posted = fields.Boolean(default=False)
    assignment_posted = fields.Boolean(default=False)

    # BUSINESS RULES -----------------------------------------------------

    # amount must be positive
    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError("Amount must be greater than zero.")

    # fund account and bucket must belong to same company
    @api.constrains('company_id', 'fund_account_id', 'fund_bucket_id')
    def _check_company_consistency(self):
        for rec in self:
            if (
                rec.fund_account_id
                and rec.fund_account_id.company_id != rec.company_id
            ):
                raise ValidationError("Fund account must belong to the same company.")
            if (
                rec.fund_bucket_id
                and rec.fund_bucket_id.company_id != rec.company_id
            ):
                raise ValidationError("Fund bucket must belong to the same company.")

    # APPROVAL HISTORY ---------------------------------------------------

    # create permanent approval trail

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
            'fund_account_id': self.fund_account_id.id,
            'fund_bucket_id': self.fund_bucket_id.id,
            'source_model': self._name,
            'source_id': self.id,
            'company_id': self.company_id.id,
        })

    # ACTIONS ------------------------------------------------------------

    # submit allocation request
    # deducts amount from available unassigned balance and places on hold
    # only draft records can be submitted
    def action_submit(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'draft':
                raise ValidationError("Only draft requests can be submitted.")
            if rec.amount > rec.fund_account_id.available_unassigned_balance:
                raise ValidationError("Insufficient available balance.")
            if rec.hold_posted:
                raise ValidationError("Hold already created.")
            self.env['fund.ledger'].sudo().create({
                'date': fields.Date.today(),
                'amount': rec.amount,
                'event_type': EVENT_HOLD,
                'fund_account_id': rec.fund_account_id.id,
                'source_model': self._name,
                'source_id': rec.id,
                'company_id': rec.company_id.id,
            })
            rec.hold_posted = True
            rec.state = 'submitted'
            rec._create_audit('submit', prev)

    # GM approval
    # records gm approval and moves to md queue
    # validates user has gm_approver group and is not the requester
    def action_gm_approve(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'submitted':
                raise ValidationError("Only submitted requests can move to GM approval.")
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

    # MD approval
    # final approval — releases hold and assigns money to bucket
    # validates user has md_approver group and is not the requester
    def action_md_approve(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'gm_approval':
                raise ValidationError("Record is not awaiting MD approval.")
            if not self.env.user.has_group('fund_management.group_md_approver'):
                raise ValidationError(
                    "You do not have MD approver permissions."
                )
            if rec.requested_by == self.env.user:
                raise ValidationError("You cannot approve your own request.")
            if rec.assignment_posted:
                raise ValidationError("Allocation already approved.")
            if not rec.release_posted:
                self.env['fund.ledger'].sudo().create({
                    'date': fields.Date.today(),
                    'amount': rec.amount,
                    'event_type': EVENT_RELEASE,
                    'fund_account_id': rec.fund_account_id.id,
                    'source_model': self._name,
                    'source_id': rec.id,
                    'company_id': rec.company_id.id,
                })
                rec.release_posted = True
            self.env['fund.ledger'].sudo().create({
                'date': fields.Date.today(),
                'amount': rec.amount,
                'event_type': EVENT_ASSIGN,
                'fund_account_id': rec.fund_account_id.id,
                'fund_bucket_id': rec.fund_bucket_id.id,
                'source_model': self._name,
                'source_id': rec.id,
                'company_id': rec.company_id.id,
            })
            rec.assignment_posted = True
            rec._create_approval_history(
                approval_level='md',
                result='approved'
            )
            rec.state = 'approved'
            rec._create_audit('md_approve', prev)

    # reject allocation request
    # releases held money back to available unassigned balance
    # records rejection in approval and audit history
    def action_reject(self):
        for rec in self:
            prev = rec.state
            if rec.state not in ('gm_approval', 'md_approval'):
                raise ValidationError("Only pending requests can be rejected.")
            if rec.hold_posted and not rec.release_posted:
                self.env['fund.ledger'].sudo().create({
                    'date': fields.Date.today(),
                    'amount': rec.amount,
                    'event_type': EVENT_RELEASE,
                    'fund_account_id': rec.fund_account_id.id,
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

    # cancel allocation request
    # releases held money if not yet released
    # approved requests cannot be cancelled — reversal required
    def action_cancel(self):
        for rec in self:
            prev = rec.state
            if rec.state == 'approved':
                raise ValidationError("Approved allocations cannot be cancelled.")
            if rec.state in ('cancelled', 'rejected'):
                raise ValidationError("Request is already closed.")
            if rec.hold_posted and not rec.release_posted:
                self.env['fund.ledger'].sudo().create({
                    'date': fields.Date.today(),
                    'amount': rec.amount,
                    'event_type': EVENT_RELEASE,
                    'fund_account_id': rec.fund_account_id.id,
                    'source_model': self._name,
                    'source_id': rec.id,
                    'company_id': rec.company_id.id,
                })
                rec.release_posted = True
            rec.state = 'cancelled'
            rec._create_audit('cancel', prev)

    # DATA PROTECTION ----------------------------------------------------

    # only draft requests may be deleted
    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError("Only draft allocation requests can be deleted.")
        return super().unlink()
