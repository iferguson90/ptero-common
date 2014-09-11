from flask import request, Response
from collections import defaultdict
import jot
import re
from jot.exceptions import InvalidSerialization
import logging

LOG = logging.getLogger(__name__)

class MissingAuthHeadersError(Exception): pass
class MalformedAccessTokenError(Exception): pass

class ProtectedEndpoint(object):
    def __init__(self, realm=None, scopes=[], claims=[], audiences=[]):
        self.realm = realm
        self.scopes = scopes
        self.claims = claims
        self.audiences = audiences
        self.exception_map = construct_exception_map(realm, scopes,
                claims, audiences)

    def __call__(self, target):
        self.target = target
        return self._execute_target

    def _execute_target(self, *args, **kwargs):
        try:
            id_token = self._extract_id_token()
        except Exception as e:
            if (e.__class__ in self.exception_map):
                return self.exception_map[e.__class__]
            else:
                LOG.exception("Unexpected exception occured while processing request url=(%s) headers=(%s)",
                        request.url, request.headers)
        return self.target(*args, id_token=id_token, **kwargs)

    def _extract_id_token(self):
        ensure_headers_are_present(request)
        access_token = parse_authorization_text(request.headers['Authorization'])
        jwe_or_jws = jot.deserialize(request.headers['Identity'])
        return None

protected_endpoint = ProtectedEndpoint

def construct_exception_map(realm, scopes, claims, audiences):
    result = defaultdict(lambda :Response(status=400,
                headers={'WWW-Authenticate': authenticate_value_text(realm, scopes),
                         'Identify': identify_value_text(claims, audiences)}))

    result[MissingAuthHeadersError] = Response(status=401,
                headers={'WWW-Authenticate': authenticate_value_text(realm, scopes),
                         'Identify': identify_value_text(claims, audiences)})

    result[MalformedAccessTokenError] = Response(status=400,
                headers={'WWW-Authenticate':
                        '%s, error="invalid_request", error_description="The Bearer token is malformed"' %
                        (authenticate_value_text(realm, scopes)),
                        'Identify': identify_value_text(claims, audiences)})
    result[InvalidSerialization] = Response(status=400,
                headers={'WWW-Authenticate': authenticate_value_text(realm, scopes),
                        'Identify': '%s, error="invalid_request", error_description="The ID token is malformed"'
                        % identify_value_text(claims, audiences)})
    return result



def ensure_headers_are_present(request):
    if ('Authorization' not in request.headers or
            'Identity' not in request.headers):
        raise MissingAuthHeadersError

def authenticate_value_text(realm, scopes):
    return 'Bearer realm="%s", scope="%s"' % (realm, ' '.join(scopes))

def identify_value_text(claims, audiences):
    return 'ID Token claims="%s", aud="%s"' % (', '.join(claims),
            ', '.join(audiences))

def parse_authorization_text(text):
    match_object = re.search('Bearer (.*)', text)
    if match_object is None:
        raise MalformedAccessTokenError
    else:
        return match_object.groups()[0]
