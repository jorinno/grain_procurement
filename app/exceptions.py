"""
Custom exceptions for the Grain Procurement Management System.

Each exception corresponds to one or more exception conditions listed in
section 10 of the Grain Purchase and Payment Workflow document.
"""


class GrainProcurementError(Exception):
    """Base class for all domain-level errors in this system."""


class AuthenticationError(GrainProcurementError):
    """Raised when a user is not authenticated or credentials are invalid."""


class AuthorizationError(GrainProcurementError):
    """Raised when a user attempts an action outside their role's permissions."""


class InvalidCategoryError(GrainProcurementError):
    """Raised when a grain category does not exist or is inactive."""


class InvalidWeightError(GrainProcurementError):
    """Raised when the entered weight is zero, negative, or non-numerical."""


class NoActivePriceError(GrainProcurementError):
    """Raised when no active price exists for the selected grain category."""


class NoActiveCommissionRateError(GrainProcurementError):
    """Raised when no active commission rate exists for the selected category."""


class MissingSupplierInfoError(GrainProcurementError):
    """Raised when required supplier details are missing before saving a purchase."""


class InvalidMobileMoneyNumberError(GrainProcurementError):
    """Raised when the supplier's mobile-money number fails validation."""


class PurchaseAlreadyConfirmedError(GrainProcurementError):
    """Raised when attempting to confirm a purchase that is already saved/confirmed."""


class DuplicatePaymentReferenceError(GrainProcurementError):
    """Raised when a payment transaction reference has already been used."""


class DuplicatePaymentConfirmationError(GrainProcurementError):
    """Raised when the same payment (supplier or agent) is confirmed twice."""


class PurchaseNotFoundError(GrainProcurementError):
    """Raised when a referenced purchase does not exist."""
