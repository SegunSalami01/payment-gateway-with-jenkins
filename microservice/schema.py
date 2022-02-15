from enum import Enum
from fastapi import Query
from typing import Optional
from pydantic import BaseModel


class GatewayType(Enum):
    Payload = 1
    CardConnect = 2


class GatewayCredentials(Enum):
    Payload = ['apiKey', 'processingId']
    # Note: merchantId is NOT the same as merchantAccountId.
    # It is a CardConnect specific keyword
    CardConnect = ['username', 'password', 'merchantId']


class Payment(BaseModel):
    gatewayTypeId: int
    gatewayTypeName: str
    merchantAccountId: int
    credentials: dict
    account: str = Query(None, regex='[0-9]{13,16}')
    expDate: str = Query(None, regex='[0-9]{4}')
    amount: float
    userId: int
    cvv2: str = Query(None, regex='[0-9]{3,4}')
    currencyType: int
    name: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    comment: Optional[str] = None
    userName: Optional[str] = None


class Refund(BaseModel):
    gatewayTypeId: int
    gatewayTypeName: str
    merchantAccountId: int
    credentials: dict
    paymentTransactionId: str
    userId: int
    comment: Optional[str] = None
    amount: Optional[float] = None
    maskedCardNumber: Optional[str] = None
    currencyType: Optional[int] = None


class CurrencyCode(Enum):
    USD = 840
    CAD = 124
    GBP = 826
    EUR = 978


class GatewayResponses(Enum):
    Approved = 200
    BadRequest = 400
    Unauthorized = 401
    Forbidden = 403
    NotFound = 404
    Conflict = 409
    InvalidAttributes = 422
    TooManyRequests = 429
    InternalServerError = 500
    ServiceUnavailable = 503
