from odoo import models, fields, api
from odoo.exceptions import ValidationError

from .ledger_event_types import (
    EVENT_REQUISITION_HOLD,
    EVENT_REQUISITION_RELEASE,
)


# request to reserve funds from a bucket
# approved requisitions later become spendable through bills/payments
class FundRequisition(models.Model):
    _name = 'fund.requisition'
    _description = 'Fund Requisition'

    _sql_constraints = [
        (
            'requisition_number_unique',
            'unique(request_number)',
            'Request number must be unique.'
        ),
        (
            'requisition_amount_positive',
            'CHECK(amount > 0)',
            'Amount must be greater than zero.'
        )
    ]

    request_number = fields.Char(
        required=True,
        copy=False
    )

    fund_bucket_id = fields.Many2one(
        'fund.bucket',
        required=True
    )

    amount = fields.Float(
        required=True
    )

    purpose = fields.Text()

    request_date = fields.Date(
        default=fields.Date.today
    )

    # date by which funds are required
    required_date = fields.Date()

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
        ('closed', 'Closed'),
    ], default='draft')

    approval_history_ids = fields.One2many(
        'fund.approval_history',
        'source_id',
        domain=[('source_model', '=', 'fund.requisition')]
    )

    bill_ids = fields.One2many(
        'fund.bill',
        'requisition_id'
    )

    remaining_billable_amount = fields.Float(
        compute='_compute_remaining_billable',
        store=False
    )

    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company
    )

    hold_posted = fields.Boolean(
        default=False
    )

    release_posted = fields.Boolean(
        default=False
    )

    # COMPUTED FIELDS ----------------------------------------------------

    @api.depends('amount', 'bill_ids.state', 'bill_ids.amount')
    def _compute_remaining_billable(self):
        for rec in self:
            billed = sum(
                rec.bill_ids.filtered(
                    lambda b: b.state == 'posted'
                ).mapped('amount')
            )
            rec.remaining_billable_amount = rec.amount - billed

    # BUSINESS RULES -----------------------------------------------------

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(
                    "Amount must be greater than zero."
                )

    @api.constrains('company_id', 'fund_bucket_id')
    def _check_company_consistency(self):
        for rec in self:
            if (
                rec.fund_bucket_id
                and rec.fund_bucket_id.company_id != rec.company_id
            ):
                raise ValidationError(
                    "Fund bucket must belong to the same company."
                )

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
            'fund_bucket_id': self.fund_bucket_id.id,
            'source_model': self._name,
            'source_id': self.id,
            'company_id': self.company_id.id,
        })

    # ACTIONS ------------------------------------------------------------

    # submit requisition
    # reserves money from bucket by creating hold
    def action_submit(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'draft':
                raise ValidationError(
                    "Only draft requisitions can be submitted."
                )
            if rec.amount > rec.fund_bucket_id.available_fund:
                raise ValidationError(
                    "Insufficient available bucket balance."
                )
            if rec.hold_posted:
                raise ValidationError(
                    "Hold already created."
                )
            self.env['fund.ledger'].sudo().create({
                'date': fields.Date.today(),
                'amount': rec.amount,
                'event_type': EVENT_REQUISITION_HOLD,
                'fund_bucket_id': rec.fund_bucket_id.id,
                'source_model': self._name,
                'source_id': rec.id,
                'company_id': rec.company_id.id,
            })
            rec.hold_posted = True
            rec.state = 'submitted'
            rec._create_audit('submit', prev)

    # move submitted request into gm queue
    def action_gm_review(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'submitted':
                raise ValidationError(
                    "Only submitted requisitions can move to GM approval."
                )
            rec.state = 'gm_approval'
            rec._create_audit('gm_review', prev)

    # gm approval
    # validates user has gm_approver group and is not the requester
    def action_gm_approve(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'gm_approval':
                raise ValidationError(
                    "Record is not awaiting GM approval."
                )
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
            rec.state = 'md_approval'
            rec._create_audit('gm_approve', prev)

    # md approval
    # validates user has md_approver group and is not the requester
    def action_md_approve(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'md_approval':
                raise ValidationError(
                    "Record is not awaiting MD approval."
                )
            if not self.env.user.has_group('fund_management.group_md_approver'):
                raise ValidationError(
                    "You do not have MD approver permissions."
                )
            if rec.requested_by == self.env.user:
                raise ValidationError("You cannot approve your own request.")
            rec._create_approval_history(
                approval_level='md',
                result='approved'
            )
            rec.state = 'approved'
            rec._create_audit('md_approve', prev)

    # reject requisition
    # releases held money
    def action_reject(self):
        for rec in self:
            prev = rec.state
            if rec.state not in ('gm_approval', 'md_approval'):
                raise ValidationError(
                    "Only pending requisitions can be rejected."
                )
            if not rec.release_posted:
                self.env['fund.ledger'].sudo().create({
                    'date': fields.Date.today(),
                    'amount': rec.amount,
                    'event_type': EVENT_REQUISITION_RELEASE,
                    'fund_bucket_id': rec.fund_bucket_id.id,
                    'source_model': self._name,
                    'source_id': rec.id,
                    'company_id': rec.company_id.id,
                })
                rec.release_posted = True
            rec._create_approval_history(
                approval_level='gm'
                if rec.state == 'gm_approval'
                else 'md',
                result='rejected'
            )
            rec.state = 'rejected'
            rec._create_audit('reject', prev)

    # cancel requisition
    # releases held money if required
    def action_cancel(self):
        for rec in self:
            prev = rec.state
            if rec.state == 'approved':
                raise ValidationError(
                    "Approved requisitions cannot be cancelled."
                )
            if rec.state in ('rejected', 'cancelled', 'closed'):
                raise ValidationError(
                    "Requisition is already closed."
                )
            if rec.hold_posted and not rec.release_posted:
                self.env['fund.ledger'].sudo().create({
                    'date': fields.Date.today(),
                    'amount': rec.amount,
                    'event_type': EVENT_REQUISITION_RELEASE,
                    'fund_bucket_id': rec.fund_bucket_id.id,
                    'source_model': self._name,
                    'source_id': rec.id,
                    'company_id': rec.company_id.id,
                })
                rec.release_posted = True
            rec.state = 'cancelled'
            rec._create_audit('cancel', prev)

    # close completed requisition
    # used after all spending is completed or unused amount released
    def action_close(self):
        for rec in self:
            prev = rec.state
            if rec.state != 'approved':
                raise ValidationError(
                    "Only approved requisitions can be closed."
                )
            rec.state = 'closed'
            rec._create_audit('close', prev)

    # HELPERS ------------------------------------------------------------

    def get_approval_history(self):
        self.ensure_one()
        return self.env['fund.approval_history'].search([
            ('source_model', '=', self._name),
            ('source_id', '=', self.id),
        ])

    # DATA PROTECTION ----------------------------------------------------

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError(
                    "Only draft requisitions can be deleted."
                )
        return super().unlink()
