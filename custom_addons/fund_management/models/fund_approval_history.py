from odoo import models, fields, api
from odoo.exceptions import ValidationError


# permanent record of approval decisions
# linked generically to any source document via source_model / source_id
class FundApprovalHistory(models.Model):
    _name = 'fund.approval_history'
    _description = 'Approval History'
    _order = 'date desc, id desc'

    # user who made the decision
    approver_id = fields.Many2one(
        'res.users',
        required=True,
        default=lambda self: self.env.user
    )

    # when the decision was made
    date = fields.Datetime(
        default=fields.Datetime.now
    )

    # which level acted
    approval_level = fields.Selection([
        ('gm', 'General Manager'),
        ('md', 'Managing Director'),
    ], required=True)

    # decision outcome
    result = fields.Selection([
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], required=True)

    # optional justification
    comment = fields.Text()

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

    # approval records are immutable
    def write(self, vals):
        raise ValidationError(
            "Approval history records cannot be modified."
        )

    # approval records are permanent
    def unlink(self):
        raise ValidationError(
            "Approval history records cannot be deleted."
        )
