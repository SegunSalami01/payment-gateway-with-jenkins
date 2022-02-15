#!/usr/bin/env python3
# vim: set fileencoding=UTF-8 :
# Copyright © 2021 BlueVolt, LLC
# All Rights Reserved
# 0.0.1 LJR 3/19/21 - Initial implementation
###############################################################################################################
# Payment Gateway API endpoints                                                                               #
#   Microservice package requirements/core installation and execution steps:                                  #
#     python3 -m venv venv                                                                                    #
#     source venv/bin/activate                                                                                #
#     pip3 install fastapi                                                                                    #
#     pip3 install uvicorn[standard]                                                                          #
#     sample startup command:  uvicorn main:app --reload --loop asyncio --port 8082 --host 0.0.0.0 \          #
#                            --proxy-headers --forwarded-allow-ips='*'                                        #
#                                                                                                             #
#   Brief overview:                                                                                           #
#     The payment gateway microservice has been implemented initially as an 'extension to' our legacy         #
#     payment processing system.  What this means is that all core data related to transaction, payment       #
#     gateway type definition, and credentials presently lives in the legacy database.  For time to market    #
#     reasons, this microservice has not including a shift of all of the legacy payment processing and        #
#     payment gateways.  What WAS achieved was to structure things in the legacy platform such that no net    #
#     new legacy database tables need to be created any more (previously, each new payment gateway type       #
#     required an additional table in the legacy database), and all new payment gateway logic and payment/    #
#     refund processing take place here in the microservice.                                                  #
#                                                                                                             #
#     Further, within this code itself, each payment processor class is implemented with a consistent set of  #
#     methods, thus enabling the various endpoints handling payment, refund, etc. requests to instantiate     #
#     the appropriate processor (based on the payment gateway type specified in the incoming request) and     #
#     then be blissfully unaware of which processor it is calling - the method names are identical across     #
#     each and every payment gateway class.                                                                   #
#                                                                                                             #
#     As with all of our microservices, logging is routed to a common location outside of the legacy          #
#     database.                                                                                               #
###############################################################################################################
from enum import Enum
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import json
import os
from pydantic import BaseModel, BaseSettings
import socket
from typing import Optional
import time
# local imports
from gateways.payload import PayloadProcessor
from gateways.cardconnect import CardConnectProcessor
from schema import GatewayCredentials, GatewayType, Payment, Refund
#-----------------------
# Begin Declarations   |
#-----------------------
# CONSTANTS
REQUIRED_BLUEVOLT_HEADER_KEYS = {'transactionId', 'universityId', 'userId'}
CARDCONNECT_HOSTNAME = os.getenv('CARDCONNECT_HOSTNAME') if 'CARDCONNECT_HOSTNAME' in os.environ else ''
#-----------------------
# End Declarations     |
#-----------------------
#-----------------------
# Begin Subroutines    |
#-----------------------


def validate_bvmeta_header(header_contents):
    if header_contents is None:
        contents_as_json = {}
    else:
        try:
            contents_as_json = json.loads(header_contents)
            if not set(contents_as_json) >= REQUIRED_BLUEVOLT_HEADER_KEYS:
                contents_as_json = {}
        except ValueError or TypeError:
            contents_as_json = {}
    return contents_as_json


def send_log_message(tx_metadata, request_data, uri, req_type, level='INFO', response_code=200):
    # construct logging message per BlueVolt logging specification and submit message to logstash
    message = {'service': 'payment_gateway', 'level': level,
               'data': {'requestUri': uri, 'requestType': req_type}}
    for item in tx_metadata:
        message[item] = tx_metadata[item]
    for key in request_data:
        message['data'][key] = request_data[key]
    message['data']['http_response_code'] = response_code
    # send message to logging service
    logstash_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    retry_count = 0
    connected = False
    # sockets connections are a bit interesting.  Sometimes connection attempts fail.  This code makes several
    # attempts to connect and, if it never succeeds it simply skips logging this particular message.  There is
    # really no other alternative.
    while not connected and retry_count < 10:
        try:
            logstash_client.connect(("logger.bluevolt.local", 5959))
            connected = True
        except socket.error:
            time.sleep(0.05)
        retry_count += 1
    if connected:
        logstash_client.send(json.dumps(message).encode())
        logstash_client.shutdown(socket.SHUT_RDWR)
        logstash_client.close()
#-----------------------
# End Subroutines      |
#-----------------------
#-----------------------
#  Main Program        |
#-----------------------

   
# initialize our fastapi app
app = FastAPI()
# configure Cross-Origin Resource Sharing configuration
# TODO : Have to enter all the allowed origins
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/paymentGateway/processPayment", status_code=200)
###########################################################################################################
# This is the endpoint that receives and processes payments.  The expected request body fields along with #
# basic field validation are set up in the Payment class in schema.py.  FastAPI performs all specified    #
# checks and validations on the content body as the first step in routing a request.  If anything is      #
# amiss or missing in the request body, FastAPI returns directly with a 422 (unprocessable entity)        #
# response.  The flow here is roughly to first validate that the BVMeta header is present and of the      #
# expected format, then grab a copy of the incoming request body for logging purposes, removing it of any #
# sensitive information, then initialization our response body, and attempting to process payment.        #
#                                                                                                         #
# Probably the most interesting/tricky aspect of this code is that it will instantiate the appropriate    #
# payment gateway class (as determined by the incoming request) as the payment_processor and call a       #
# standard method which must be present in each payment gateway class -- process_payment.  All payment    #
# gateway classes reside in the gateways folder.                                                          #
#                                                                                                         #
# Various error codes and messages can be returned.   Wherever possible, these codes and messages are     #
# those returned by the payment processor itself.  One exception to this is that any payment gateway      #
# http response code of 5xx is converted to a 400 since that could create confusion at the front end.     #
# In general, 5xx errors indicate some sort of web server error and that the back end function called     #
# is not functioning.  Clearly, passing back a 5xx error from our payment gateway processor would be      #
# very misleading to anyone/anything attempting to monitor our microservice.  The only 5xx errors that    #
# ought to be return would be those generated directly by our microservice.                               #
###########################################################################################################
async def submit_sale(payment: Payment, request: Request, bvmeta: str = Header(None)):
    # validate ourBVMeta header contents
    bv_header = validate_bvmeta_header(bvmeta)
    # initialize logging copy of transaction payload
    request_body_as_json = payment.dict()
    # remove payment gateway credentials from logging data
    del(request_body_as_json['credentials'])
    # remove cvv2 from logging data
    del(request_body_as_json['cvv2'])
    # mask card number to only log last 4 digits in logging data
    request_body_as_json['maskedCardNumber'] = ''.join('x' for c in request_body_as_json['account'][0:-4]) + \
                                               ''.join(c for c in request_body_as_json['account'][-4:])
    # remove original card number from logging data
    del(request_body_as_json['account'])
    payment_result = {'success': None,
                      'paymentTransactionId': None,
                      'statusCode': None,
                      'gatewayHttpStatusCode': None,
                      'responseMessage': None,
                      'responseDetail': None,
                      'merchantAccountId': payment.merchantAccountId,
                      'gatewayResponseData': None}
    response_detail = None
    if not bv_header:
        response_status = 400
        response_detail = 'Incomplete request'
        request_body_as_json['status'] = response_detail
        log_level = 'ERROR'
    else:
        # check if the gateway type passed in is supported by our microservice (it should be)
        if payment.gatewayTypeId in [item.value for item in GatewayType]:
            # the payment gateway type is a match for one of our processors
            try:
                required_credentials_present_in_request = False
                if GatewayType(payment.gatewayTypeId).name == 'Payload':
                    if set(payment.credentials) >= set(GatewayCredentials.Payload.value):
                        # we have the necessary credential key/value pairs in our incoming payload for Payload.co
                        required_credentials_present_in_request = True
                        payment_processor = PayloadProcessor(payment.credentials)
                elif GatewayType(payment.gatewayTypeId).name == 'CardConnect':
                    if set(payment.credentials) >= set(GatewayCredentials.CardConnect.value):
                        required_credentials_present_in_request = True
                        payment_processor = CardConnectProcessor(payment.credentials, CARDCONNECT_HOSTNAME)
                if required_credentials_present_in_request:
                    payment_result = payment_processor.process_payment(payment)
                    response_status = payment_result.get('gatewayHttpStatusCode', 200)
                    if response_status >= 500:
                        response_status = 400
                    if response_status != 200:
                        # An error was thrown by our payment gateway payment method
                        response_detail = 'Error encountered during payment attempt to ' + \
                                          GatewayType(payment.gatewayTypeId).name + ' payment processing endpoint'
                        request_body_as_json['status'] = response_detail
                        log_level = 'ERROR'
                    else:
                        # The payment result was successful
                        response_detail = 'Transaction approved'
                        log_level = 'AUDIT'
                else:
                    # we did not receive necessary credential key/value pairs for the specified payment gateway type
                    response_status = 400
                    response_detail = 'Required credentials for ' + GatewayType(payment.gatewayTypeId).name + \
                                      ' are not present'
                    request_body_as_json['status'] = response_detail
                    log_level = 'ERROR'
            except:
                # We should never hit this case, but it is here just to be safe
                response_status = 421
                response_detail = 'Unexpected error encountered processing ' + \
                                  GatewayType(payment.gatewayTypeId).name + ' payment request'
                request_body_as_json['status'] = response_detail
                log_level = 'ERROR'
        else:
            # the payment gateway type is not a match for any of our processors
            response_status = 400
            response_detail = 'Unknown payment gateway type'
            request_body_as_json['status'] = response_detail
            log_level = 'ERROR'
    # gateway response data is intended to be added to the message that gets logged and is not required for the
    # response. if gatewayResponseData is in the gateway response object, then we will init the variable and remove
    # it from the response object
    gateway_response_data = None
    if 'gatewayResponseData' in payment_result:
        gateway_response_data = payment_result['gatewayResponseData']
        del payment_result['gatewayResponseData']
    payment_result['responseDetail'] = payment_result['responseMessage'] \
        if type(payment_result['responseMessage']) is str else response_detail
    log_data = {'requestData': request_body_as_json,
                'responseDetail': payment_result,
                'gatewayResponseData': gateway_response_data}
    send_log_message(bv_header, log_data, request.url.path, 'POST', log_level, response_status)
    if response_status != 200:
        raise HTTPException(status_code=response_status, detail=payment_result)
    return {'detail': payment_result}


@app.patch("/paymentGateway/processRefund")
###########################################################################################################
# This is the endpoint that receives and processes refunds.  The expected request body fields along with  #
# basic field validation are set up in the Payment class in schema.py.  FastAPI performs all specified    #
# checks and validations on the content body as the first step in routing a request.  If anything is      #
# amiss or missing in the request body, FastAPI returns directly with a 422 (unprocessable entity)        #
# response.  The flow here is roughly to first validate that the BVMeta header is present and of the      #
# expected format, then grab a copy of the incoming request body for logging purposes, removing it of any #
# sensitive information, then initialization our response body, and attempting to process payment.        #
#                                                                                                         #
# As with the process payment endpoint, this logic will instantiate the appropriate payment gateway class #
# as the refund_processor and call a standard method which must be present in each payment gateway class  #
# -- process_refund.  All payment gateway classes reside in the gateways folder.                          #
#                                                                                                         #
# Various error codes and messages can be returned.   Wherever possible, these codes and messages are     #
# those returned by the payment processor itself.  One exception to this is that any payment gateway      #
# http response code of 5xx is converted to a 400 since that could create confusion at the front end.     #
# In general, 5xx errors indicate some sort of web server error and that the back end function called     #
# is not functioning.  Clearly, passing back a 5xx error from our payment gateway processor would be      #
# very misleading to anyone/anything attempting to monitor our microservice.  The only 5xx errors that    #
# ought to be return would be those generated directly by our microservice.                               #
###########################################################################################################
async def submit_credit(refund: Refund, request: Request, bvmeta: str = Header(None)):
    # validate our BVMeta header contents
    bv_header = validate_bvmeta_header(bvmeta)
    # initialize logging copy of transaction payload
    request_body_as_json = refund.dict()
    # remove payment gateway credentials
    del(request_body_as_json['credentials'])
    refund_result = {'success': None,
                     'refundTransactionId': None,
                     'statusCode': None,
                     'gatewayHttpStatusCode': None,
                     'responseMessage': None,
                     'responseDetail': None,
                     'merchantAccountId': refund.merchantAccountId,
                     'gatewayResponseData': None}
    response_detail = None
    if not bv_header:
        response_status = 400
        response_detail = 'Incomplete request'
        request_body_as_json['status'] = response_detail
        log_level = 'ERROR'
    else:
        # check if the gateway type passed in is supported by our microservice (it should be)
        if refund.gatewayTypeId in [item.value for item in GatewayType]:
            # the payment gateway type is a match for one of our processors
            try:
                required_credentials_present_in_request = False
                gateway_type = GatewayType(refund.gatewayTypeId).name
                if gateway_type == 'Payload':
                    if set(refund.credentials) >= set(GatewayCredentials.Payload.value):
                        # we have the necessary credential key/value pairs in our incoming payload for Payload.co
                        required_credentials_present_in_request = True
                        refund_processor = PayloadProcessor(refund.credentials)
                elif gateway_type == 'CardConnect':
                    if set(refund.credentials) >= set(GatewayCredentials.CardConnect.value):
                        required_credentials_present_in_request = True
                        refund_processor = CardConnectProcessor(refund.credentials, CARDCONNECT_HOSTNAME)
                if required_credentials_present_in_request:
                    refund_result = refund_processor.process_refund(refund)
                    response_status = refund_result.get('gatewayHttpStatusCode', 200)
                    if response_status >= 500:
                        response_status = 400
                    if response_status != 200:
                        # An error was thrown by our payment gateway refund method
                        if gateway_type == 'Payload' and response_status == 404:
                            # a very special case for Payload - a 404/NotFound error means that the payment transaction
                            # id did not exist
                            response_detail = 'The provided payment transaction id does not exist'
                        else:
                            response_detail = 'Error encountered during refund request to ' + \
                                              gateway_type + ' refund processing endpoint'
                        request_body_as_json['status'] = response_detail
                        log_level = 'ERROR'
                    else:
                        # The payment result was successful
                        response_detail = 'Refund successfully processed'
                        log_level = 'AUDIT'
                    #print('this one\'s a keeper')
                else:
                    # we did not receive necessary credential key/value pairs for the specified payment gateway type
                    response_status = 400
                    response_detail = 'Required credentials for ' + GatewayType(refund.gatewayTypeId).name + \
                                      ' are not present'
                    request_body_as_json['status'] = response_detail
                    log_level = 'ERROR'
            except:
                # We should never hit this case, but it is here just to be safe
                response_status = 421
                response_detail = 'Unexpected error encountered processing ' + \
                                  GatewayType(refund.gatewayTypeId).name + ' refund request'
                request_body_as_json['status'] = response_detail
                log_level = 'ERROR'
        else:
            # the payment gateway type is not a match for any of our processors
            response_status = 400
            response_detail = 'Unknown payment gateway type'
            request_body_as_json['status'] = response_detail
            log_level = 'ERROR'
    # gateway response data is intended to be added to the message that gets logged and is not required for the
    # response. if gatewayResponseData is in the gateway response object, then we will init the variable and remove
    # it from the response object
    gateway_response_data = None
    if 'gatewayResponseData' in refund_result:
        gateway_response_data = refund_result['gatewayResponseData']
        del refund_result['gatewayResponseData']
    refund_result['responseDetail'] = refund_result['responseMessage'] \
        if type(refund_result['responseMessage']) is str else response_detail
    log_data = {'requestData': request_body_as_json,
                'responseDetail': refund_result,
                'gatewayResponseData': gateway_response_data}
    send_log_message(bv_header, log_data, request.url.path, 'POST', log_level, response_status)
    if response_status != 200:
        raise HTTPException(status_code=response_status, detail=refund_result)
    return {'detail': refund_result}


@app.get("/paymentGateway/test", status_code=200)
async def return_hello(request: Request):
    # a test endpoint that can be used internally for health check purposes.  Note that this endpoint is NOT
    # exposed externally.
    return 'Test endpoint successfully reached.  Client IP: ' + request.client.host
