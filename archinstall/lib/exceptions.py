"""
Adding custom exceptions, making the code more readable.
"""


class RequirementError(BaseException):
    pass


class DiskError(BaseException):
    pass


class ProfileError(BaseException):
    pass


class SysCallError(BaseException):
    pass
