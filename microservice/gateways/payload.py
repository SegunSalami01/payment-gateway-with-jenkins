########################################################################################################################
# Payload Payment Gatway class                                                                                         #
# python3 -m venv venv                                                                                                 #
# source venv/bin/activate                                                                                             #
# pip3 install payload-api                                                                                             #
#                                                                                                                      #
# card_expired        The card has expired.                                                      4111 1111 1111 9900   #
# duplicate_attempt   This transaction appears be a duplicate attempt and has been prevented.    4111 1111 1111 9901   #
# exceeded_limit      The amount of the transaction exceeds the allowed limit for this account.  4111 1111 1111 9902   #
# general_decline     The card has been declined, contact card issuer for more information.      4111 1111 1111 9903   #
# insufficient_bal    The card does not have a sufficient balance to complete the payment.       4111 1111 1111 9904   #
# invalid_card_code   The security code is invalid, please check the number.                     4111 1111 1111 9905   #
# invalid_card_number The card number is invalid, please check the number.                       4111 1111 1111 9906   #
# invalid_zip         The ZIP Code does not match the card.                                      4111 1111 1111 9907   #
# suspicious_activity This transaction has been identified as suspicious.                        4111 1111 1111 9908   #
# too_many_attempts   Too many payment attempts have been made, please try again later.          4111 1111 1111 9909   #
########################################################################################################################
from enum import Enum
import payload as pl
from payload.exceptions import (
    TransactionDeclined,
    InvalidAttributes,
    Unauthorized,
    NotFound,
    InternalServerError,
    Forbidden,
    ServiceUnavailable,
    BadRequest,
    TooManyRequests,
)
from schema import Payment, Refund, GatewayResponses


class PayloadProcessor:
    def __init__(self, credentials):
        self.api_key = credentials['apiKey']
        self.processing_id = credentials['processingId']

    def process_payment(self, payment: Payment):
        # This function to create and process the payment to payload_co
        payment_transaction_id = None
        payload_processing_status = None
        http_status_code = 200
        payment_success = False
        message = None
        try:
            pl.api_key = self.api_key
            expiration_date = payment.expDate[0:2] + '/' + payment.expDate[2:]
            payment_response = pl.Payment.create(
                amount=payment.amount,
                payment_method=pl.Card(
                    account_holder=payment.name,
                    card_number=payment.account,
                    expiry=expiration_date,
                    card_code=payment.cvv2,
                ),
                processing_id=self.processing_id,
                description=payment.comment[:128]
            )
            payment_success = True
            payload_processing_status = payment_response.status_code
            message = payment_response.status_message
            payment_transaction_id = payment_response.id
        except ValueError as error:
            http_status_code = 400
            message = str(error)
        except TransactionDeclined as error:
            payload_processing_status = error.transaction.status_code
            http_status_code = error.http_code
            message = error.transaction.status_message
        except (
                InvalidAttributes,
                InternalServerError,
                Unauthorized,
                NotFound,
                TooManyRequests,
                ServiceUnavailable,
                BadRequest,
                Forbidden,
               ) as error:
            # status_code is not provided in this case, payload_processing_status will be left as None
            error_type = type(error).__name__
            if error_type in GatewayResponses.__members__:
                http_status_code = GatewayResponses[error_type].value
                try:
                    error_response = getattr(error, 'response')
                    # This feels very hacky, but per ticket https://dev.azure.com/bluevolt/BVLMS/_workitems/edit/11508/,
                    # we must pass back a text string for 'invalid card', and this gets generated in a very specific
                    # way by payload payment processing.  So, we are going to check for the existing of this very
                    # specific bit of metadata in the response and send it back as the error message used by the front
                    # end.   If for any reason something different is returned, we handle that in the more 'generic'
                    # fashion so as not to generate a 5xx error.
                    if 'details' in error_response and 'payment_method' in error_response['details'] \
                            and 'card' in error_response['details']['payment_method'] \
                            and 'card_number' in error_response['details']['payment_method']['card']:
                        message = error_response['details']['payment_method']['card']['card_number']
                    else:
                        message = error.response
                except:
                    message = error.__dict__
            else:
                message = 'Unrecognized Payload error response'
                http_status_code = 400
        except:
            message = 'Unknown Payload response type'
            http_status_code = 422
        finally:
            processing_result = {'success': payment_success,
                                 'paymentTransactionId': payment_transaction_id,
                                 'statusCode': payload_processing_status,
                                 'gatewayHttpStatusCode': http_status_code,
                                 'responseMessage': message,
                                 'merchantAccountId': payment.merchantAccountId,
                                 'gatewayResponseData': None}
        return processing_result

    def process_refund(self, refund: Refund):
        # This function is to check whether payment has to be void or refund
        refund_transaction_id = None
        payload_processing_status = None
        http_status_code = 200
        refund_success = False
        message = None
        already_voided_message = None
        try:
            pl.api_key = self.api_key
            # We need to attempt to retrieve attempt to retrieve a payment object matching the passed in transaction id
            # If there is no matching transaction id, we will hit our exception processing logic
            payment_object = pl.Payment.get(refund.paymentTransactionId)
            if payment_object.status == 'voided':
                already_voided_message = \
                    'Payment transaction has already been voided.  No further action has been taken.'
            else:
                if payment_object.funding_status == "pending":
                    # the payment has not settled yet.  We will void the payment request
                    refund_object = pl.Transaction.get(refund.paymentTransactionId)
                    refund_object.update(status="voided", description=refund.comment[:128])
                elif payment_object.funding_status == "batched":
                    # the payment is settled.  We will generate a refund transaction
                    refund_object = \
                        pl.Refund.create(amount=payment_object.amount,
                                         ledger=[{"assoc_transaction_id": refund.paymentTransactionId}],
                                         description=refund.comment[:128])
                else:
                    raise ValueError(f"Unknown funding status '{payment_object.funding_status}' encountered during refund "
                                     f"process.  Payment was not refunded.")
            refund_success = True
            if already_voided_message:
                payload_processing_status = payment_object.status
                message = already_voided_message
            else:
                payload_processing_status = refund_object.status
                message = refund_object.status_message
                refund_transaction_id = refund_object.id
        except ValueError as error:
            http_status_code = 400
            message = str(error)
        except (
                InvalidAttributes,
                InternalServerError,
                Unauthorized,
                NotFound,
                TooManyRequests,
                ServiceUnavailable,
                BadRequest,
                Forbidden,
        ) as error:
            # status_code is not provided in this case, payload_processing_status will be left as None
            error_type = type(error).__name__
            if error_type in GatewayResponses.__members__:
                http_status_code = GatewayResponses[error_type].value
                try:
                    message = error.response
                except:
                    message = error.__dict__
            else:
                message = 'Unrecognized Payload error response'
                http_status_code = 400
        except:
            message = 'Unknown Payload response type'
            http_status_code = 422
        finally:
            refund_result = {'success': refund_success,
                             'refundTransactionId': refund_transaction_id,
                             'statusCode': payload_processing_status,
                             'gatewayHttpStatusCode': http_status_code,
                             'responseMessage': message,
                             'merchantAccountId': refund.merchantAccountId,
                             'gatewayResponseData': None}
        return refund_result
