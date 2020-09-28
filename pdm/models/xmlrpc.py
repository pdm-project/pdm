import urllib.parse as urllib_parse
import xmlrpc.client as xmlrpc_client


class PyPIXmlrpcTransport(xmlrpc_client.Transport):
    """Provide a `xmlrpclib.Transport` implementation via a `PipSession`
    object.
    """

    def __init__(self, index_url, session, use_datetime=False):
        xmlrpc_client.Transport.__init__(self, use_datetime)
        index_parts = urllib_parse.urlparse(index_url)
        self._scheme = index_parts.scheme
        self._session = session

    def request(self, host, handler, request_body, verbose=False):
        parts = (self._scheme, host, handler, None, None, None)
        url = urllib_parse.urlunparse(parts)
        headers = {"Content-Type": "text/xml"}
        response = self._session.post(
            url, data=request_body, headers=headers, stream=True
        )
        response.raise_for_status()
        self.verbose = verbose
        return self.parse_response(response.raw)
