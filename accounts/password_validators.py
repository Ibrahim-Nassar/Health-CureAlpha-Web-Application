import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class PasswordComplexityValidator:
    """
    Require at least:
    - one letter (a-z or A-Z)
    - one number (0-9)
    - one special character (anything not a letter or number)
    """

    def validate(self, password, user=None):
        if password is None:
            return

        has_letter = re.search(r"[A-Za-z]", password) is not None
        has_digit = re.search(r"\d", password) is not None
        has_special = re.search(r"[^A-Za-z0-9]", password) is not None

        if not (has_letter and has_digit and has_special):
            raise ValidationError(
                _(
                    "Your password must contain at least 1 letter, 1 number, and 1 special character."
                ),
                code="password_no_complexity",
            )

    def get_help_text(self):
        return _(
            "Your password must contain at least 1 letter, 1 number, and 1 special character."
        )


