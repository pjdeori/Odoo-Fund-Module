# ledger event constants

EVENT_INCOMING = 'incoming'
EVENT_INCOMING_REVERSAL = 'incoming_reversal'

EVENT_HOLD = 'hold'
EVENT_RELEASE = 'release'

EVENT_ASSIGN = 'assign'

EVENT_REQUISITION_HOLD = 'requisition_hold'
EVENT_REQUISITION_RELEASE = 'requisition_release'

EVENT_TRANSFER_HOLD = 'transfer_hold'
EVENT_TRANSFER_RELEASE = 'transfer_release'

EVENT_TRANSFER_IN = 'transfer_in'
EVENT_TRANSFER_OUT = 'transfer_out'

EVENT_SPENT = 'spent'
EVENT_SPEND_REVERSAL = 'spend_reversal'


# ledger event selection values

LEDGER_EVENT_TYPES = [
    (EVENT_INCOMING, 'Incoming'),
    (EVENT_INCOMING_REVERSAL, 'Incoming Reversal'),

    (EVENT_HOLD, 'Hold'),
    (EVENT_RELEASE, 'Release'),

    (EVENT_ASSIGN, 'Assign'),

    (EVENT_REQUISITION_HOLD, 'Requisition Hold'),
    (EVENT_REQUISITION_RELEASE, 'Requisition Release'),

    (EVENT_TRANSFER_HOLD, 'Transfer Hold'),
    (EVENT_TRANSFER_RELEASE, 'Transfer Release'),

    (EVENT_TRANSFER_IN, 'Transfer In'),
    (EVENT_TRANSFER_OUT, 'Transfer Out'),

    (EVENT_SPENT, 'Spent'),
    (EVENT_SPEND_REVERSAL, 'Spend Reversal'),
]