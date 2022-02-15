########################################################################################################################
# CardConnect Payment Gateway class
# Documentation: https://developer.cardpointe.com/cardconnect-api#overview  (12/21/21)                                 #
# python3 -m venv venv                                                                                                 #
# source venv/bin/activate                                                                                             #
# pip3 install requests                                                                                                #
# pip3 install json                                                                                                    #
#                                                                                                                      #
# Testing Data:                                                                                                        #
# Payment Authorization Test Cards                                                                                     #
# respstat      account number          resptext                       notes                                           #
# A             4788250000121443        Approval                                                                       #
# B             4999006200620062        Timed out                      Visa                                            #
# B             5111006200620062        Timed out                      Mastercard                                      #
# B             6465006200620062        Timed out                      Discover                                        #
# C             4387751111111020        Refer to issuer                                                                #
# C             4387751111111038        Do not honor                                                                   #
# C             5442981111111049        Wrong expiration                                                               #
# C             5442981111111056        Insufficient funds                                                             #
#                                                                                                                      #
# Test Credentials                                                                                                     #
# username = testing                                                                                                   #
# password = testing123                                                                                                #
# merchantId = 496160873888                                                                                            #
########################################################################################################################
import requests
from requests.auth import HTTPBasicAuth
import json

from schema import Payment, Refund, CurrencyCode, GatewayResponses

CARDCONNECT_UAT_TEST_HOSTNAME = 'fts-uat.cardconnect.com'
CARDCONNECT_PROD_HOSTNAME = 'fts.cardconnect.com'


class CardConnectResponseStatusType:
    Approved = 'A'
    Retry = 'B'
    Declined = 'C'


class CardConnectVoidableStatusType:
    Voidable = 'Y'
    NotVoidable = 'N'


class CardConnectRefundableStatusType:
    Refundable = 'Y'
    NotRefundable = 'N'


class CardConnectVoidRespAuthCodeType:
    Successful = 'REVERS'
    Unsuccessful = 'NULL'


class CardConnectProcessor:
    def __init__(self, credentials, cardconnect_hostname):
        self.usr = credentials['username']
        self.pwd = credentials['password']
        self.merchantId = credentials['merchantId']
        # if cardconnect_hostname exists use that domain else default to prod
        cc_hostname = cardconnect_hostname if cardconnect_hostname else CARDCONNECT_PROD_HOSTNAME
        self.authEndPoint = 'https://' + cc_hostname + '/cardconnect/rest/auth'
        self.inquireEndpointBaseUrl = 'https://' + cc_hostname + '/cardconnect/rest/inquire'
        self.voidEndpoint = 'https://' + cc_hostname + '/cardconnect/rest/void'
        self.refundEndpoint = 'https://' + cc_hostname + '/cardconnect/rest/refund'

    def process_payment(self, payment: Payment):
        # This function is to create and process the payment to CardConnect
        # Part 1 - perform an 'all in one' POST request to the auth endpoint by adding the
        # key/value pair of "capture": "y".  This also returns retref and other data, and the
        # transaction gets processed directly without requiring a second call
        payment_transaction_id = None
        http_status_code = GatewayResponses.Approved.value
        payment_success = False
        message = None
        gateway_response_data = []
        response = None
        try:
            auth_url = self.authEndPoint
            # the following dataset will be sent to the auth endpoint.(*) denotes that the param is required.
            # below are param notes from the CardConnect API docs.
            # - merchid(*):CardPointe merchant ID, required for all requests.
            # - account(*): Can be: CardSecure Token, Clear text card number, or a Bank Account Number. We currently
            #               only support clear text card numbers.
            # - expiry(*): Card expiration in one of the following formats:
            #           - MMYY      **** this is what we are using ****
            #           - YYYYM (for single-digit months)
            #           - YYYYMM
            #           - YYYYMMDD
            #           Not required for eCheck (ACH) or digital wallet (for example, Apple Pay or Google Pay) payments.
            #           Note: payment.expDate will always be in MMYY format.
            # - amount(*): Amount with decimal or without decimal in currency minor units ( for example, USD Pennies or
            #               EUR Cents). The value can be a positive or negative amount or 0, and is used to identify
            #               the type of authorization, as follows:
            #                   Positive - Authorization request.
            #                   Zero - Account Verification request, if AVS and CVV verification is enabled for your
            #                          merchant account. Account Verification is not supported for eCheck (ACH)
            #                          authorizations.
            #                   Negative - Refund without reference (Forced Credit). Merchants must be configured to
            #                              process forced credit transactions. To refund an existing authorization,
            #                              use Refund.
            # - capture: Optional, specify Y to capture the transaction for settlement if approved.
            #            Defaults to N if not provided.
            # - cvv2: The 3 or 4-digit cardholder verification value (CVV2/CVC/CID) value present on the card.
            #         Note: It is strongly recommended that your application prompts for CVV for card-not-present
            #         transactions for fraud prevention and to avoid declines on the CardPointe Gateway if the CVV
            #         verification option is enabled for your merchant account.
            # - name: Account holder's name, optional for credit cards and electronic checks (ACH).
            # - ecomind: An e-commerce transaction origin indicator, for card-not-present transactions only.
            #           Options are:
            #               - T - telephone or mail payment
            #               - R - recurring billing
            #               - E - e-commerce web or mobile application      **** this is what we are using ****
            #           Note: You should include the appropriate ecomind value for all card-not-present transactions,
            #           to ensure that the transaction processes at the appropriate interchange level. Do not include
            #           ecomind for card-present transactions, in which the payment card data is obtained using a
            #           POS device.
            # NOTE: this endpoint does not support the ability to add a comment or text string to a transaction, so we
            #       cannot utilize payment.comment for this gateway type.
            data = {
                "merchid": self.merchantId,
                "account": payment.account,
                "expiry": payment.expDate,
                "amount": payment.amount,
                "capture": "Y",
                "cvv2": payment.cvv2,
                "currency": CurrencyCode(payment.currencyType).name,
                "name": payment.name,
                "ecomind": "E"
            }
            # check if zip exists as an included field in payment object, if yes then make sure it is not empty
            # further checks to zip format are not made as it can change based on country and if the zip is incorrect
            # CardConnect will throw back the number which the code below will report.
            if payment.zip and payment.zip != '':
                data['postal'] = payment.zip
            # perform the same check for name since it is an optional parameter
            if payment.name and payment.name != '':
                data['name'] = payment.name
            # 'userfields' allows users to pass optional custom fields in a transaction. The CardConnect account
            # has a custom user field called Description and passing the following populates that custom field
            # for transactions.
            description = payment.comment if payment.comment else ''
            data['userfields'] = [{'Description': description}]
            response = requests.post(
                auth_url,
                json=data,
                auth=HTTPBasicAuth(self.usr, self.pwd)
            )
            response_status_code = response.status_code
            if response_status_code == GatewayResponses.Approved.value:
                response_as_json = json.loads(response.text)
                gateway_response_data.append(response_as_json)
                # first check authorization status, respstat. The possible values for this are:
                #   A - Approved
                #   B - Retry
                #   C - Declined
                # we are treating A as approvals, B and C as declines.
                if response_as_json.get('respstat', None) and \
                        response_as_json['respstat'] == CardConnectResponseStatusType.Approved:
                    # payment authorization success
                    # http_status_code is initialized to GatewayResponses.Approved.value
                    # and we dont have to set it here.
                    payment_success = True
                    message = 'Success.'
                else:
                    # payment authorization failure
                    # handle retry or Decline ( B or C )
                    payment_success = False
                    http_status_code = GatewayResponses.BadRequest.value
                    if response_as_json.get('respstat', None) and \
                            response_as_json['respstat'] == CardConnectResponseStatusType.Retry:
                        message = 'Please retry the request.'
                    else:
                        message = 'Authorization failed.'
                    if response_as_json.get('resptext', None):
                        message += f' {response_as_json["resptext"]}.'
                if response_as_json.get('retref', None):
                    payment_transaction_id = response_as_json['retref']
            elif response_status_code == GatewayResponses.Unauthorized.value:
                # authentication error handling
                gateway_response_data = append_json_or_string_to_array(response.text, gateway_response_data)
                payment_success = False
                http_status_code = response_status_code
                message = 'There was an authorization error with your request.'
            else:
                # network error handling
                gateway_response_data = append_json_or_string_to_array(response.text, gateway_response_data)
                payment_success = False
                http_status_code = response_status_code
                message = 'There was a network error with your request.'
        except Exception as e:
            # handle error
            exception_message = "process_payment exception: " + str(e)
            print(exception_message)
            gateway_response_data.append(exception_message)
            if response and response.text:
                gateway_response_data = append_json_or_string_to_array(response.text, gateway_response_data)
            http_status_code = GatewayResponses.InternalServerError.value
            message = 'There was an internal service error with your request.'
        finally:
            # payload_processing_status is set to http status code to reflect final result of the settlement.
            # In the future this may be expanded to be more functional.
            payload_processing_status = http_status_code
            processing_result = {'success': payment_success,
                                 'paymentTransactionId': payment_transaction_id,
                                 'statusCode': payload_processing_status,
                                 'gatewayHttpStatusCode': http_status_code,
                                 'responseMessage': message,
                                 'merchantAccountId': payment.merchantAccountId,
                                 'gatewayResponseData': gateway_response_data}
        return processing_result

    def process_refund(self, refund: Refund):
        # This function is to refund a payment and must check
        # whether that means the payment has to be voided or refunded
        # must void if payment transaction has not been sent to capture endpoint i.e. it has not been settled
        # refund if the payment transaction has been settled. This is determined by using the inquire endpoint
        # which returns a 'voidable' yes/no response
        refund_transaction_id = None
        http_status_code = GatewayResponses.Approved.value
        refund_success = False
        message = None
        gateway_response_data = []
        payment_status_response = None
        # grab payment attempt
        inquire_url = self.inquireEndpointBaseUrl + f'/{refund.paymentTransactionId}/{self.merchantId}'
        try:
            payment_status_response = requests.get(
                inquire_url,
                auth=HTTPBasicAuth(self.usr, self.pwd)
            )
            payment_status_response_code = payment_status_response.status_code
            if payment_status_response_code == GatewayResponses.Approved.value:
                # call successfully made, parse response into json
                payment_status_response_json = json.loads(payment_status_response.text)
                gateway_response_data.append(payment_status_response_json)
                # check status of payment attempt
                if payment_status_response_json.get('respstat', None) and \
                        payment_status_response_json['respstat'] == CardConnectResponseStatusType.Approved:
                    # payment exists and is authorized, now check if payment is voidable
                    if payment_status_response_json.get('voidable', None) and \
                            payment_status_response_json['voidable'] == CardConnectVoidableStatusType.Voidable:
                        # set up API call to void payment attempt
                        void_url = self.voidEndpoint
                        # no payment amount specified in data object so the default is
                        # to always void the full amount of the transaction
                        data = {
                            'retref': refund.paymentTransactionId,
                            'merchid': self.merchantId
                        }
                        void_resp = None
                        # make void call
                        try:
                            void_resp = requests.post(
                                void_url,
                                json=data,
                                auth=HTTPBasicAuth(self.usr, self.pwd)
                            )
                            void_resp_status_code = void_resp.status_code
                            if void_resp_status_code == GatewayResponses.Approved.value:
                                void_resp_json = json.loads(void_resp.text)
                                gateway_response_data.append(void_resp_json)
                                # check void status:
                                # first look at authentication through 'respstat' returning A, B, or C responses for
                                # Approved, Retry, or Declined respectively
                                # authcode field only appears if respstat is equal to Approved and
                                # is set one of two yes/no values:
                                # REVERS - indicates a successful void
                                # NULL - indicates an unsuccessful void
                                if void_resp_json.get('respstat', None) and \
                                        void_resp_json['respstat'] == CardConnectResponseStatusType.Approved and \
                                        void_resp_json.get('authcode', None) and \
                                        void_resp_json['authcode'] == CardConnectVoidRespAuthCodeType.Successful:
                                    # void successful
                                    refund_success = True
                                    message = 'Successfully voided transaction.'
                                elif void_resp_json.get('respstat', None) and \
                                        void_resp_json['respstat'] == CardConnectResponseStatusType.Approved and \
                                        void_resp_json.get('authcode', None) and \
                                        void_resp_json['authcode'] == CardConnectVoidRespAuthCodeType.Unsuccessful:
                                    # void unsuccessful
                                    message = 'Void transaction was unsuccessful.'
                                    error_resp_txt = void_resp_json['resptext']
                                    message += f' {error_resp_txt}'
                                    http_status_code = GatewayResponses.BadRequest.value
                                else:
                                    # check if 'authcode' field is missing but respstat was still approved
                                    if not void_resp_json.get('authcode', None) and \
                                            void_resp_json.get('respstat', None) and \
                                            void_resp_json['respstat'] == CardConnectResponseStatusType.Approved:
                                        # without any additional information from the void endpoint
                                        # we must assume void transaction was successful
                                        refund_success = True
                                        message = 'success'
                                    else:
                                        # void was declined respstat is either Retry or Decline
                                        if void_resp_json.get('respstat', None) and \
                                                void_resp_json['respstat'] == CardConnectResponseStatusType.Retry:
                                            message = 'Unable to complete void transaction.'
                                        else:
                                            'Void transaction was declined.'
                                        error_resp_txt = void_resp_json['resptext']
                                        message += f' {error_resp_txt}'
                                        http_status_code = GatewayResponses.Conflict.value
                                refund_transaction_id = void_resp_json['retref']
                            elif void_resp_status_code == GatewayResponses.Unauthorized.value:
                                # handle unauthorized void response
                                gateway_response_data = append_json_or_string_to_array(void_resp.text,
                                                                                       gateway_response_data)
                                http_status_code = void_resp_status_code
                                message = 'There was an authorization error while processing a void request.'
                            else:
                                # error returned from void endpoint
                                gateway_response_data = append_json_or_string_to_array(void_resp.text,
                                                                                       gateway_response_data)
                                http_status_code = void_resp_status_code
                                refund_transaction_id = refund.paymentTransactionId
                                message = 'Unable to complete void transaction.'
                        except Exception as e:
                            # handle error making void call
                            print(e)
                            exception_message = "process_refund void exception: " + str(e)
                            print(exception_message)
                            gateway_response_data.append(exception_message)
                            if void_resp and void_resp.text:
                                gateway_response_data = append_json_or_string_to_array(void_resp.text,
                                                                                       gateway_response_data)
                            message = 'An unknown error occurred while processing void transaction.'
                            http_status_code = GatewayResponses.InternalServerError.value
                            refund_transaction_id = refund.paymentTransactionId
                    elif payment_status_response_json.get('refundable', None) and \
                            payment_status_response_json['refundable'] == CardConnectRefundableStatusType.Refundable:
                        # refund payment
                        refund_url = self.refundEndpoint
                        # no payment amount specified in data object so the default is
                        # to always void the full amount of the transaction
                        data = {
                            'retref': refund.paymentTransactionId,
                            'merchid': self.merchantId,
                            'amount': refund.amount
                        }
                        refund_response = None
                        # make refund call
                        try:
                            refund_response = requests.post(
                                refund_url,
                                json=data,
                                auth=HTTPBasicAuth(self.usr, self.pwd)
                            )
                            refund_response_status_code = refund_response.status_code
                            if refund_response_status_code == GatewayResponses.Approved.value:
                                # parse response as json
                                refund_resp_json = json.loads(refund_response.text)
                                gateway_response_data.append(refund_resp_json)
                                # check success of refund
                                #   A - Approved
                                #   B - Retry
                                #   C - Declined
                                # we are treating A as approvals, B and C as declines.
                                if refund_resp_json.get('respstat', None) and \
                                        refund_resp_json['respstat'] == CardConnectResponseStatusType.Approved:
                                    # handle successful refund
                                    refund_success = True
                                    message = 'Successful refund transaction.'
                                else:
                                    # handle Retry retry response and Decline response statuses as a failed refund
                                    http_status_code = GatewayResponses.BadRequest.value
                                    if refund_resp_json.get('respstat', None) and \
                                            refund_resp_json['respstat'] == CardConnectResponseStatusType.Retry:
                                        message = 'Please retry the request.'
                                    else:
                                        message = 'Refund failed.'
                                    error_resp_txt = refund_resp_json['resptext']
                                    message += f' {error_resp_txt}'
                                if refund_resp_json.get('retref', None):
                                    refund_transaction_id = refund_resp_json['retref']
                            elif refund_response_status_code == GatewayResponses.Unauthorized.value:
                                # handle unauthorized refund response
                                gateway_response_data = append_json_or_string_to_array(refund_response.text,
                                                                                       gateway_response_data)
                                http_status_code = refund_response_status_code
                                message = 'There was an authorization error while processing the refund request.'
                            else:
                                # handle error returned from refund endpoint
                                gateway_response_data = append_json_or_string_to_array(refund_response.text,
                                                                                       gateway_response_data)
                                http_status_code = refund_response_status_code
                                refund_transaction_id = refund.paymentTransactionId
                                message = 'Unable to complete refund transaction'
                        except Exception as e:
                            # handle internal error processing refund call
                            exception_message = "process_refund refund exception: " + str(e)
                            print(exception_message)
                            gateway_response_data.append(exception_message)
                            if refund_response and refund_response.text:
                                gateway_response_data = append_json_or_string_to_array(refund_response.text,
                                                                                       gateway_response_data)
                            message = 'An unknown error occurred while processing refund transaction.'
                            http_status_code = GatewayResponses.InternalServerError.value
                            refund_transaction_id = refund.paymentTransactionId
                    else:
                        # transaction is not voidable and not refundable, so we cannot complete the refund request
                        message = 'The refund cannot be processed at this time.'
                        http_status_code = GatewayResponses.Conflict.value
                        refund_transaction_id = refund.paymentTransactionId
                else:
                    # payment may not exist and auth is declined. Treat both Retry and Decline response statuses
                    # as decline
                    message = 'The payment requested was not authorized or does not exist.'
                    http_status_code = GatewayResponses.Conflict.value
                    refund_transaction_id = refund.paymentTransactionId
            elif payment_status_response_code == GatewayResponses.Unauthorized.value:
                # handle unauthorized payment status response
                gateway_response_data = append_json_or_string_to_array(payment_status_response.text,
                                                                       gateway_response_data)
                http_status_code = payment_status_response_code
                message = 'There was an authorization error while accessing your previous payment status.'
            else:
                # unable to retrieve payment status
                gateway_response_data = append_json_or_string_to_array(payment_status_response.text,
                                                                       gateway_response_data)
                message = 'Unable to complete request for payment status. Please contact BlueVolt support.'
                http_status_code = payment_status_response_code
                refund_transaction_id = refund.paymentTransactionId
        except Exception as e:
            # handle error while making call to inquire endpoint
            exception_message = "process_refund inquiry exception: " + str(e)
            print(exception_message)
            gateway_response_data.append(exception_message)
            if payment_status_response and payment_status_response.text:
                gateway_response_data = append_json_or_string_to_array(payment_status_response.text,
                                                                       gateway_response_data)
            message = 'An unknown error occurred while retrieving your payment status. The refund was unsuccessful.'
            http_status_code = GatewayResponses.InternalServerError.value
            refund_transaction_id = refund.paymentTransactionId
        finally:
            # payload_processing_status is set to http status code
            # to reflect final result of the settlement.
            # In the future this may be expanded to be more functional.
            payload_processing_status = http_status_code
            refund_result = {'success': refund_success,
                             'refundTransactionId': refund_transaction_id,
                             'statusCode': payload_processing_status,
                             'gatewayHttpStatusCode': http_status_code,
                             'responseMessage': message,
                             'merchantAccountId': refund.merchantAccountId,
                             'gatewayResponseData': gateway_response_data}
        return refund_result


def append_json_or_string_to_array(json_or_string, array):
    try:
        string_converted_to_json = json.loads(json_or_string)
        array.append(string_converted_to_json)
    except json.JSONDecodeError as json_err:
        # unable to json load the string, so just append string.
        array.append("error decoding string into json: " + str(json_err))
        array.append(json_or_string)
    except Exception as err:
        # unknown exception, append json_or_string and exception str to array.
        array.append("error converting string into json: " + str(err))
        array.append(json_or_string)
    return array
