from odoo import models, fields, api
from odoo.exceptions import ValidationError


# immutable record of document lifecycle actions
# captures who did what, when, and the state transition
# distinct from fund.ledger which tracks financial movements
class FundAuditHistory(models.Model):
    _name = 'fund.audit_history'
    _description = 'Audit History'
    _order = 'date_time desc, id desc'

    # user who performed the action
    actor_id = fields.Many2one(
        'res.users',
        required=True,
        default=lambda self: self.env.user
    )

    # type of action performed
    action = fields.Selection([
        ('submit', 'Submitted'),
        ('gm_approve', 'GM Approved'),
        ('md_approve', 'MD Approved'),
        ('reject', 'Rejected'),
        ('cancel', 'Cancelled'),
        ('close', 'Closed'),
        ('confirm', 'Confirmed'),
        ('post', 'Posted'),
        ('reverse', 'Reversed'),
    ], required=True)

    # state transition
    previous_state = fields.Char()

    new_state = fields.Char()

    # when the action occurred
    date_time = fields.Datetime(
        default=fields.Datetime.now
    )

    # optional notes
    comment = fields.Text()

    # financial context (if applicable)
    amount = fields.Float()

    # related financial entities
    fund_account_id = fields.Many2one(
        'fund.account'
    )

    fund_bucket_id = fields.Many2one(
        'fund.bucket'
    )

    # generic link back to the source document
    source_model = fields.Char(
        required=True
    )

    source_id = fields.Integer(
        required=True
    )

    # multi-company safety
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company
    )

    # DATA PROTECTION ----------------------------------------------------

    # audit records are immutable
    def write(self, vals):
        raise ValidationError(
            "Audit history records cannot be modified."
        )

    # audit records are permanent
    def unlink(self):
        raise ValidationError(
            "Audit history records cannot be deleted."
        )
