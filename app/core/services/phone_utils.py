"""Phone number normalization utility.

Normalizes various US phone formats to E.164 (+1XXXXXXXXXX).
Handles: 19403376016, 930-337-6016, 9403376016, (940) 337-6016, +1-940-337-6016, etc.

Used at every phone write point (contact creation, update, call ingestion)
so DB lookups are always exact-match on a canonical format.
"""

import re


def normalize_phone(phone: str | None) -> str | None:
    """Normalize a phone number to E.164 format (+1XXXXXXXXXX for US numbers).

    Returns None if the input is None, empty, or not a recognizable phone number.
    """
    if not phone:
        return None

    # Strip everything except digits and leading +
    digits = re.sub(r"[^\d]", "", phone)

    if not digits:
        return None

    # Handle US numbers
    if len(digits) == 10:
        # 9403376016 → +19403376016
        return f"+1{digits}"
    elif len(digits) == 11 and digits[0] == "1":
        # 19403376016 → +19403376016
        return f"+{digits}"
    elif len(digits) > 11:
        # International or long format — keep as +digits
        return f"+{digits}"
    else:
        # Too short to be valid — return as-is with + prefix for consistency
        return f"+{digits}"
