"""Canonical content types shared with the frontend through the catalog API."""
CONTENT_TYPES = {'notice': '通知', 'activity': '活动', 'competition': '竞赛', 'lecture': '讲座',
                 'employment': '就业', 'postgraduate': '考研', 'scholarship': '奖助', 'academic': '教务'}
ALIASES = {'volunteer': 'activity', 'club': 'activity', 'teaching': 'academic', 'graduate': 'postgraduate',
           **{label: code for code, label in CONTENT_TYPES.items()}}


def normalize_type(value):
    value = ALIASES.get(value, value)
    return value if value in CONTENT_TYPES else 'notice'
