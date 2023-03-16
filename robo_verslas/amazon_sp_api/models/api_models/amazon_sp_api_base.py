# -*- coding: utf-8 -*-
from odoo import models, api, tools, exceptions, _
from dateutil.relativedelta import relativedelta
from ... import amazon_sp_api_tools as at
from collections import OrderedDict
from datetime import datetime
import requests
import hashlib
import logging
import urllib
import boto3
import json
import time
import hmac


_logger = logging.getLogger(__name__)


class AmazonSPAPIBase(models.AbstractModel):
    _name = 'amazon.sp.api.base'
    _description = _(
        'Model that contains core methods that are used to connect and interact with Amazon SP-API'
    )

    # API core block --------------------------------------------------------------------------------------------------

    @api.model
    def call_api_base(self, action, extra_data=None, manual_action=False, refresh_token=True, throttle_count=0):
        """
        Main method used to prepare data/structures for Amazon SP-API call.
        :param action: API action name (str)
        :param extra_data: Dict of API call that including endpoints and various parameters (dict)
        :param manual_action: Indicates whether current action is executed by cron or by user (bool)
        :param refresh_token: Indicates whether current call should try to refresh the token (bool)
        :param throttle_count: Indicates the count of repeated calls that was caused by throttling (bool)
        :return: True/False (based on success of the call), response_data (dict)
        """

        # Refresh the token before any call if the region is specified
        # in extra data and if refresh flag is set to true
        request_region = extra_data.get('region') if extra_data else None
        if request_region and refresh_token:
            self.api_refresh_access_token(request_region)

        # Get the required data and call the endpoint
        api_data = self.get_api_call_data(action, extra_data=extra_data)
        response = self.call_api_endpoint(api_data)

        # Sanitize the response, parse the data and status code
        response_data, status_code = self.sanitize_api_response(response, manual_action)
        # If parsed status code is throttled endpoint code, repeat the request and increase the count
        if status_code == at.THROTTLED_ENDPOINT_CODE:
            if throttle_count > at.THROTTLE_REPEAT_COUNT:
                raise exceptions.ValidationError(_('Amazon SP-API Request throttled after 15 tries'))
            # Wait before next try, increased exponentially
            time.sleep(5 * throttle_count)
            return self.call_api_base(action, extra_data, manual_action, refresh_token, throttle_count)

        # Check whether call was successful
        successful_call = status_code == 200
        return successful_call, response_data

    @api.model
    def call_api_continuation_key_wrapper(self, call_data, data_type, base_request_query=None):
        """
        Intermediate wrapper method that is used when calling API endpoint
        that returns results with continuation key (throttling limiting)
        :param call_data: Data that is being passed in the API call (dict)
        :param data_type: Type of the data that is being requested (str)
        :param base_request_query: Base request query dict, next token is passed here.
        Can be either passed as (dict) if call has arguments, or not used (None)
        :return: Fetched data and flag that indicates whether whole period
        was fetched successfully (dict)
        """

        base_request_query = {} if base_request_query is None else base_request_query
        # Prepare empty list to store fetched payloads
        # Period fetched flag indicates that multi-call (continuation token) request completed
        # successfully - all desired period was fetched (no partial failures)
        fetched_data = []
        period_fetched = True

        # Init next token and start time of the bulk
        start_time = time.time()
        next_token = None
        while True:
            request_query = base_request_query
            # Update the query with request continuation key if it's present
            if next_token:
                request_query = base_request_query.copy()
                request_query['NextToken'] = next_token
            # Always re-order request query
            ordered_query = OrderedDict(sorted(request_query.items()))
            call_data['extra_data'].update({'request_query': ordered_query})
            # Call the endpoint
            successful_call, response_data = self.call_api_base(**call_data)
            if successful_call:
                # Update total data list and check for continuation key
                payload = response_data['payload']
                if isinstance(payload, dict):
                    # Nice consistency Amazon.. Try to get next token from both of the structures
                    next_token = payload.get('NextToken') or response_data.get('pagination', {}).get('nextToken')
                fetched_data.append(payload)
                # If there's no continuation key, all of the period data has been fetched
                if not next_token:
                    break
            else:
                error = '[{}] / {}'.format(response_data['status_code'], response_data['system_notification'])
                message = _('Amazon SP-API: Data [{}] fetching error: {}').format(data_type, error)
                # If we encounter external failure, we silently stop for current account
                if response_data.get('external_failure'):
                    period_fetched = False
                    _logger.info(message)
                    break
                raise exceptions.ValidationError(message)
            # Check the elapsed time and break the loop if its more than MAX_DATA_FETCHING_TTL
            elapsed_time = time.time() - start_time
            if elapsed_time > at.MAX_DATA_FETCHING_TTL:
                _logger.info('Amazon SP-API: Not waiting for data [{}] after {} seconds....'.format(
                    data_type, at.MAX_DATA_FETCHING_TTL)
                )
                period_fetched = False
                break

        return {
            'fetched_data': fetched_data,
            'period_fetched': period_fetched,
        }

    @api.model
    def call_api_endpoint(self, api_data):
        """
        API core method that aggregates the data and calls specific Amazon SP-API endpoint.
        Most of the calls require authentication and are supplemented by generating signed headers.
        :param api_data: Various API data - Endpoints, queries, etc (dict)
        :return: response of specific API endpoint (requests object)
        """

        request_method = api_data['main_data']['method']
        request_url = api_data['main_data']['absolute_url']
        request_region = api_data['content_data']['region']
        # Check if current call is a call to restricted resource
        restricted_resource_data = api_data['main_data'].get('restricted_resource')
        if restricted_resource_data:
            # Update restricted data token
            self.api_get_restricted_data_token(restricted_resource_data, request_region)

        # Optionally passed fields
        requires_authentication = api_data['main_data'].get('requires_authentication')
        canonical_url = api_data['main_data'].get('canonical_url', '/')
        request_payload = api_data['content_data'].get('request_payload')
        content_type = api_data['main_data'].get('content_type')
        request_query = api_data['content_data'].get('request_query')

        # Check if there's any payload passed and encode it
        if request_payload:
            request_payload = json.dumps(request_payload).encode('utf-8')

        # Check if there's any query string data and build the string
        query_string = str()
        if request_query:
            query_string = urllib.urlencode(request_query, doseq=True)

        # Pass endpoint region as host
        base_headers = {'host': request_region.region_endpoint}
        # If call requires authentication, build authentication headers
        if requires_authentication:
            # Get the configuration record
            configuration = self.get_configuration()
            # Assume AWS role
            tmp_role_data = self.api_assume_aws_role(configuration, request_region)
            base_headers.update({
                'x-amz-security-token': tmp_role_data['session_token'],
                'x-amz-access-token': request_region.access_token,
            })
            # Get utc time and store it as date/datetime strings
            request_dt = datetime.utcnow()
            request_date_str = request_dt.strftime(at.AMAZON_DATE_FORMAT)
            request_dt_str = request_dt.strftime(at.AMAZON_DATETIME_FORMAT)
            # Update the headers with the request date and content type if it's passed
            base_headers.update({'x-amz-date': request_dt_str, })
            if content_type:
                base_headers.update({'content-type': content_type, })

            # Check if there's any JSON payload and build the hash code, on no payload empty string is used
            payload_hash = hashlib.sha256(request_payload or str()).hexdigest()

            # Build ordered headers, sequence is important for the request string
            ordered_headers = OrderedDict(sorted(base_headers.items()))
            # Build canonical headers string based on the header dict
            canonical_headers = str().join(
                '%s:%s\n' % (k.lower().strip(), v.strip()) for k, v in ordered_headers.items()
            )
            # Build signed headers list based on base header mandatory values
            signed_headers = ';'.join(
                '%s' % k.lower().strip() for k, v in ordered_headers.items() if k in at.SIGNED_HEADER_VALUES
            )

            # Build canonical request string and it's hash
            canonical_request = '{}\n{}\n{}\n{}\n{}\n{}'.format(
                request_method, canonical_url, query_string,
                canonical_headers, signed_headers, payload_hash,
            )
            canonical_request_hash = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()

            # Build credential scope and string to sign
            credential_scope = '{}/{}/{}/{}'.format(
                request_date_str, request_region.code, 'execute-api', 'aws4_request'
            )
            string_to_sign = '{}\n{}\n{}\n{}'.format(
                at.AMAZON_HASH_ALGORITHM, request_dt_str, credential_scope, canonical_request_hash,
            )
            # Produce the signature of the request and build authorization headers
            signature = self.sign_api_request({
                'request_date': request_date_str,
                'string_to_sign': string_to_sign,
                'region': request_region,
                'temporal_secret_key': tmp_role_data['secret_key'],
            })
            auth_header = '{} Credential={}/{}, SignedHeaders={}, Signature={}'.format(
                at.AMAZON_HASH_ALGORITHM, tmp_role_data['access_key'], credential_scope, signed_headers, signature,
            )
            # Append all of the needed request data to the headers
            base_headers.update({
                'Authorization': auth_header,
            })

        try:
            # Only GETs and POSTs are supported  at the moment
            if request_method == 'GET':
                response = requests.get(request_url, headers=base_headers, params=query_string)
            else:
                response = requests.post(request_url, headers=base_headers, data=request_payload)
        except Exception as e:
            _logger.info('Amazon SP-API REQUEST ERROR: {}'.format(e.args[0]))
            raise exceptions.ValidationError(
                _('Could not reach Amazon SP-API server. Please contact administrators')
            )
        return response

    @api.model
    def get_api_static_action_data(self):
        """
        Returns static data dict for API token endpoints.
        Method is overridden in each of the specific API
        models by adding endpoints specific to that API.
        :return: endpoint action data (dict)
        """
        action_mapping = {
            'post_token_exchange': {
                'absolute_url': 'api.amazon.com/auth/o2/token',
                'method': 'POST',
            },
            'post_restricted_token': {
                'canonical_url': '/tokens/2021-03-01/restrictedDataToken',
                'requires_authentication': True,
                'content_type': 'application/json',
                'method': 'POST',
            },
        }
        return action_mapping

    @api.model
    def get_api_call_data(self, action, extra_data=None):
        """
        Prepare specific Amazon SP-API endpoint data based on passed action value
        :param action: API action that is mapped to specific endpoint (str)
        :param extra_data: extra parameters that are passed to the endpoint (dict/None)
        :return: prepared data (dict)
        """

        extra_data = {} if extra_data is None else extra_data
        # Gets method, endpoint, and other info based on the action
        action_data = self.get_api_static_action_data()
        call_data = action_data.get(action)
        # If not method or endpoint exists, raise an exception
        if not call_data:
            raise exceptions.ValidationError(_('Incorrect endpoint is passed!'))

        # Format the absolute URL (either absolute or canonical must be specified
        absolute_url = call_data.get('absolute_url')
        if not absolute_url:
            canonical_url = call_data.get('canonical_url')
            base_url = extra_data.get('base_url')
            if not canonical_url or not base_url:
                raise exceptions.ValidationError(_('Incorrect endpoint is passed!'))
            # If canonical URL is passed format it with extra  data
            canonical_url = canonical_url.format(**extra_data)
            call_data['canonical_url'] = canonical_url
            # Format the absolute URL
            absolute_url = '{}{}'.format(base_url, canonical_url)
        # Populate absolute URL with the object data
        absolute_url = 'https://{}'.format(absolute_url.format(**extra_data))
        # Reassign formatted absolute URL to the data
        call_data['absolute_url'] = absolute_url
        return {
            'main_data': call_data,
            'content_data': extra_data,
        }

    @api.model
    def sanitize_api_response(self, response, manual_action):
        """
        Sanitize the response of specific Amazon SP-API endpoint
        :param response: response (object)
        :param manual_action: Indicates whether action is done by a job, or manually (bool)
        :return: response content (dict), status code (int)
        """
        # Parse the JSON and get status code
        try:
            response_content = response.json()
            status_code = response.status_code
        except (ValueError, AttributeError):
            response_content = {}
            status_code = 500
        # Prepare error description strings
        error_str = description = str()
        # If status code is not 200, raise an error (or send a bug)
        if status_code != 200:
            # Get the errors block
            errors_block = response_content.get('errors', {})
            # Get both of the error descriptions
            if isinstance(errors_block, list):
                errors_block = errors_block[0]
            description = errors_block.get('message')
            ext_e_code = errors_block.get('code')
            # Fetch description from mapping based on status code if it does not exist
            if not description:
                description = at.GENERAL_API_RESPONSE_MAPPING.get(status_code, _('Unexpected error'))
            # Compose an error message
            error_str = _('Amazon SP-API error: {}\nDescription: {}\nStatus code - [{}]').format(
                ext_e_code, description, status_code)
            _logger.info(error_str)

            # Set some extra flags based on the received data
            if status_code == at.EXTERNAL_FAILURE_CODE:
                response_content['external_failure'] = True

            # Raise the error if it's automatic action, non external failure and not throttled request
            if not manual_action and not response_content.get('external_failure') \
                    and status_code != at.THROTTLED_ENDPOINT_CODE:
                raise exceptions.ValidationError(error_str)
        # Always attach detailed admin error to the response
        response_content.update({
            'system_notification': error_str,
            'status_description': description,
            'status_code': status_code,
        })
        return response_content, status_code

    @api.model
    def sign_api_request(self, signing_data):
        """
        Signs API request data with the derived signature key.
        :param signing_data: data that is needed to compose a signature (dict)
        :return: signature (str)
        """

        def sign(key, message):
            """Signs the message with passed key using H-MAC and SHA256"""
            return hmac.new(key, message.encode('utf-8'), digestmod=hashlib.sha256).digest()

        # Get the needed data to compose a signature
        request_date = signing_data['request_date']
        string_to_sign = signing_data['string_to_sign']
        region = signing_data['region']
        temporal_secret_key = signing_data['temporal_secret_key']

        encoded_secret_key = 'AWS4{}'.format(temporal_secret_key.encode('utf-8'))
        # Make the first H-MAC digest by using application's secret key and date of the request
        k_date = sign(encoded_secret_key, request_date)
        # Make the second digest using region identifier
        r_region = sign(k_date, region.code)
        # Get the service digest (static value IAM)
        k_service = sign(r_region, 'execute-api')
        # Get the final signing key
        signing_key = sign(k_service, 'aws4_request')

        # Sign the final string with the derived key and get the HEX digest of the signature
        signature = hmac.new(
            signing_key, msg=string_to_sign.encode('utf-8'), digestmod=hashlib.sha256,
        ).hexdigest()
        return signature

    @api.model
    def api_assume_aws_role(self, configuration, request_region):
        """
        Assumes AWS STS role for current request region.
        Assuming the role grants temporal elevated rights
        and returns keys that can be used to invoke those rights.
        :param configuration: SP-API configuration (record)
        :param request_region: Amazon SP-API region (record)
        :return: Temporal role keys (dict)
        """
        # Assume AWS role
        aws_sts_client = boto3.client(
            'sts', aws_access_key_id=configuration.access_key_id,
            aws_secret_access_key=configuration.secret_key,
            region_name=request_region.code,
        )
        sts_session = 'STS_ROLE_{}'.format(datetime.utcnow().strftime('%s'))
        sts_response = aws_sts_client.assume_role(
            RoleArn=configuration.application_arn,
            RoleSessionName=sts_session,
        )

        # Get the credentials and return them
        temporal_secret_key = sts_response['Credentials']['SecretAccessKey']
        temporal_access_key = sts_response['Credentials']['AccessKeyId']
        temporal_session_token = sts_response['Credentials']['SessionToken']

        return {
            'secret_key': temporal_secret_key,
            'access_key': temporal_access_key,
            'session_token': temporal_session_token,
        }

    # API Token Methods -----------------------------------------------------------------------------------------------

    @api.model
    def parse_api_state_vector(self, state_vector, session_code):
        """
        Check whether passed Amazon state vector corresponds to any region
        and if it does, initiate the session to exchange session code for a token.
        Method is called from internal.
        :param state_vector: Amazon vector (string)
        :param session_code: Amazon session code (string)
        :return: True if exchange was successful otherwise False
        """
        successful_call = False
        # State vector is already validated before it reaches this method
        # thus we can split without any try/except blocks
        region_id = state_vector.split('__')[2]
        # Search for the mapper with the database name
        amazon_region = self.env['amazon.sp.region'].search(
            [('last_state_vector', '=', state_vector), ('id', '=', region_id)]
        )
        if amazon_region and session_code:
            successful_call = self.api_get_access_token(
                region=amazon_region, authorization_code=session_code,
            )
        return successful_call

    @api.model
    def api_get_access_token(self, region, authorization_code):
        """
        Used to exchange authentication code for the token.
        Two tokens, access and refresh are returned.
        :param region: Amazon SP region object that is being authorized (record)
        :param authorization_code: Code received in oAuth  (str)
        :return: True if exchange call was successful, else False
        """

        # Get the configuration and check it's status
        # artificially by ignoring the API state
        configuration = self.get_configuration(check_status=False)
        if not configuration.check_configuration(ignore_api_state=True):
            return

        # Prepare the data, use ordered dict
        request_payload = OrderedDict([
            ('grant_type', 'authorization_code'),
            ('code', authorization_code),
            ('redirect_uri', configuration.get_redirect_url()),
            ('client_id', configuration.lwa_client_id),
            ('client_secret', configuration.lwa_client_secret),
        ])
        # Call the endpoint to exchange the tokens
        successful_call, response_data = self.call_api_base(
            action='post_token_exchange',
            manual_action=True,
            extra_data={
                'request_payload': request_payload,
                'region': region,
            }, refresh_token=False,
        )
        if successful_call:
            # Try to get the expires in
            expires_in = response_data.get('expires_in')
            if not expires_in:
                expires_in = response_data.get('expiresIn', 3600)
            # Write token values to the region and activate it's api state
            region.write({
                'access_token': response_data.get('access_token', str()),
                'refresh_token': response_data.get('refresh_token', str()),
                'api_state': 'working',
                'access_token_expiry_date': datetime.utcnow() + relativedelta(seconds=expires_in),
            })
        else:
            # If it fails, post two messages for admin and user
            message_base = _('Failed to authenticate the session: {}')
            region.message_post(
                body=message_base.format(response_data['system_notification']))
            region.write({
                'api_state': 'failed',
                'last_api_error_message': message_base.format(response_data['status_description']),
            })
        return successful_call

    @api.model
    def api_refresh_access_token(self, region):
        """
        Used to refresh current access token for a new one.
        Token is valid  for one hour after refreshing
        :param region: Amazon SP region object that is being refreshed (record)
        :return: None
        """

        # Get the configuration and check it's status
        configuration = self.get_configuration()
        if not configuration:
            return
        # Check if both access token and refresh token are set
        if not region.access_token or not region.refresh_token:
            raise exceptions.ValidationError(_('There is no access token to refresh!'))

        # If current token is still valid - return
        if region.check_token_ttl():
            return

        # Prepare the data, use ordered dict
        request_payload = OrderedDict([
            ('grant_type', 'refresh_token'),
            ('refresh_token', region.refresh_token),
            ('client_id', configuration.lwa_client_id),
            ('client_secret', configuration.lwa_client_secret),
        ])
        # Call the endpoint to exchange the tokens
        successful_call, response_data = self.call_api_base(
            action='post_token_exchange',
            manual_action=True,
            extra_data={'region': region, 'request_payload': request_payload, },
            refresh_token=False,
        )
        if successful_call:
            # Calculate token expiry date
            expiry_date = (
                    datetime.utcnow() + relativedelta(seconds=response_data['expires_in'])
            ).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            # Write token values to the region and activate it's api state
            region.write({
                'access_token': response_data['access_token'],
                'refresh_token': response_data['refresh_token'],
                'access_token_expiry_date': expiry_date,
            })
        else:
            # If it fails, post two messages for admin and user
            message_base = _('Failed to refresh the token: {}')
            region.message_post(
                body=message_base.format(response_data['system_notification']))
            region.write({
                'api_state': 'failed',
                'last_api_error_message': message_base.format(response_data['status_description']),
            })

    @api.model
    def api_get_restricted_data_token(self, restricted_data, region):
        """
        Call API endpoint to exchange regular access token to
        restricted data token. Write the token to corresponding region
        :param restricted_data: data that is being accessed (dict)
        :param region: Related Amazon region (record)
        :return: True if operation was successful else False (bool)
        """
        # Get configuration and the application key
        configuration = self.get_configuration()
        if not configuration:
            return

        # Prepare request payload
        request_payload = {
            'targetApplication': configuration.application_key,
            'restrictedResources': [restricted_data],
        }
        # Call the endpoint for the restricted data token
        successful_call, response_data = self.call_api_base(
            action='post_restricted_token',
            extra_data={
                'request_payload': request_payload,
                'base_url': region.region_endpoint,
                'region': region,
            }, manual_action=True, refresh_token=False,
        )
        if successful_call:
            # Write the restricted data token
            region.write({
                'restricted_data_token': response_data['restrictedDataToken'],
            })
        return successful_call

    # Other Methods ---------------------------------------------------------------------------------------------------

    @api.model
    def convert_date_iso_format(self, date_string):
        """Convert passed date string to iso-format date string"""
        try:
            converted_date = datetime.strptime(date_string, tools.DEFAULT_SERVER_DATE_FORMAT)
        except ValueError:
            converted_date = datetime.strptime(date_string, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        return converted_date.isoformat()

    @api.model
    def get_configuration(self, raise_exception=True, check_status=True):
        """
        Returns related configuration record if it's state is configured
        :param raise_exception: Indicates whether it should fail silently
        :param check_status: Indicates whether the status of configuration should be
        checked, if marked configuration is returned only if it's fully functional
        :return: Amazon configuration (record)
        """
        AmazonSPConfiguration = self.env['amazon.sp.configuration'].sudo()
        # Search for the configuration record
        configuration = AmazonSPConfiguration.search([])
        if not configuration and raise_exception:
            raise exceptions.ValidationError(_('Amazon configuration record was not found!'))
        # Return the empty set if configuration is not working
        if check_status and not configuration.check_configuration():
            return AmazonSPConfiguration
        return configuration
