#!/usr/bin/python

#
# Copyright (c) 2014, 2015, Oracle and/or its affiliates. All rights reserved.
#

# The sample code provided here is for training purposes only to help you to
# get familiar with the Oracle ZFS Storage Appliance RESTful API.
# As such the use of this code is unsupported and is for non-commercial or
# non-production use only.
# No effort has been made to include exception handling and error checking
# functionality as is required in a production environment.

"""
Example Code of a REST API client library for the ZFSSA
Version 1.1
"""

import base64
import json
import httplib
import threading
import ssl
import urllib2
import Queue


class Status:
    """Result HTTP Status"""
    def __init__(self):
        pass

    # Successful Status Values
    OK = 200            #: Request return OK
    CREATED = 201       #: New resource created successfully
    ACCEPTED = 202      #: Command accepted
    NO_CONTENT = 204    #: Command returned OK but no data returned

    # Client Side Errors
    BAD_REQUEST = 400   #: Bad Request.  Usually invalid properties
    UNAUTHORIZED = 401  #: User is not authorized
    FORBIDDEN = 403     #: The request is forbidden
    NOT_FOUND = 404     #: The requested resource was not found
    NOT_ALLOWED = 405   #: The request is not allowed
    TIMEOUT = 408       #: Request timed out
    CONFLICT = 409      #: Invalid request.  Resource may already exist

    # Server Side Errors
    INTERNAL_SERVER_ERROR = 500     #: General REST API Error
    SERVICE_UNAVAILABLE = 503       #: Service is unavailable or busy
    GATEWAY_TIMEOUT = 504           #: REST API is not responding


class RestRequest(object):
    """Class that encapsulates a REST request"""
    def __init__(self, method, path, data=None):
        self.path = self.api_path(path)
        self.method = method
        self.data = data

    @staticmethod
    def api_path(path):
        """Adds /api to path if needed"""
        if not path.startswith("/"):
            path = "/" + path
        if not path.startswith("/api"):
            path = "/api" + path
        return path


class RestResult(object):
    """Result from a REST API client operation"""
    def __init__(self, response, error_status=0):
        """Initialize a RestResult containing the response from a REST call"""
        self.response = response
        self.error_status = error_status
        self._body = None
        self._data = None

    def __str__(self):
        if self.error_status:
            return str(self.response)

        data = self.getdata()
        if isinstance(data, (str, tuple)):
            return data
        return json.dumps(data, indent=4, default=str)

    @property
    def body(self):
        """Get the entire returned text body.  Will not return until all
        data has been read from the server."""
        if self._body:
            return self._body

        self._body = ""
        data = self.response.read()
        while data:
            self._body += data
            data = self.response.read()
        return self._body

    @property
    def status(self):
        """Get the HTTP status result, or -1 if call failed"""
        if self.error_status:
            return self.error_status
        else:
            return self.response.getcode()

    @property
    def data(self):
        """Parsed REST result data"""
        if self._data is None:
            self._data = self.getdata()
        return self._data

    def readline(self):
        """Reads a single line of data from the server.  Useful for
        commands that return streamed data.

        :returns: A line of text read from the REST API server
        """
        if self.error_status:
            return None
        self.response.fp._rbufsize = 0
        return self.response.readline()

    def getdata(self, name=None):
        """Get the returned data parsed into a python object.  Right now
        only supports JSON encoded data.

        :param name: Optional key name used to return sub-data
        :return: Data is parsed as the returned data type into a python
        object.  If the data type isn't supported than the string value of
        the data is returned.
        """
        if self.error_status:
            return None
        data = self.body
        if data:
            content_type = self.getheader("Content-Type")
            if content_type.startswith("application/json"):
                    data = json.loads(data)
        if name:
            data = data.get(name)
        return data

    def getheader(self, name):
        """Get an HTTP header with the given name from the results

        :param name: HTTP header name
        :return: The header value or None if no value is found
        """
        if self.error_status:
            return None
        info = self.response.info()
        return info.getheader(name)

    def debug(self):
        """Get debug text containing HTTP status and headers"""
        if self.error_status:
            return repr(self.response) + "\n"

        msg = httplib.responses.get(self.status, "Unknown")
        hdr = "HTTP/1.1 %d %s\n" % (self.status, msg)
        return hdr + str(self.response.info())


class RestException(Exception):
    """An Exception that wraps a RestResult"""
    def __init__(self, message, result=None):
        Exception.__init__(
            self, message + '\n' + str(result) if result else message)
        self.result = result


class RestRunner(object):
    """REST request runner for a background client call.  Clients can obtain
    the result when it is ready by calling result()
    """
    def __init__(self, client, request, **kwargs):
        self._result = None                   # REST result from request
        self._called = threading.Condition()  # Result available condition
        self.client = client                  # Client used to run request
        self.request = request                # REST Request
        self.verbose = kwargs.get("verbose")
        self.handle_result = False

    def __str__(self):
        url = self.client.url(self.request.path)
        out = "%s %s %s\n" % (self.request.method, url, self.request.data)
        if self.isdone():
            if self.verbose:
                out += self._result.debug()
                out += "\n"
            out += str(self._result)
            out += "\n"
        else:
            out += "waiting"
        return out

    def run(self):
        """Thread run routine.  Should only be called by thread"""
        try:
            result = self.client.execute(self.request)
        except Exception as err:
            result = RestResult(err, -1)
        with self._called:
            self._result = result
            self._called.notify_all()

    def isdone(self):
        """Determine if the REST call has returned data.

        :return: True if server has returned data, otherwise False
        """
        with self._called:
            return self._result is not None

    def result(self, timeout=0):
        """Get the REST call result object once the call is finished.

        :param timeout: The number of seconds to wait for the response to
                        finish
        :returns: RestResult or None if not finished.
        """
        with self._called:
            if self._result:
                return self._result
            else:
                self._called.wait(timeout)
                return self._result

    def cancel(self):
        if self.isdone():
            result = self.result()
            if result:
                result.fp.close()


class RestClient(object):
    """A REST Client API class to access the ZFSSA REST API"""
    REST_URL = "https://%s:%d%s"
    ACCESS_URL = "https://%s:%d/api/access/v1"
    METHODS = ('GET', 'PUT', 'POST', 'DELETE')

    def __init__(self, host, user=None, password=None, session=None, port=215):
        """Create a client that will communicate with the specified ZFSSA
        host.  If user and password are not supplied then the client must
        login before making calls.

        :param host: Appliance host name
        :param port: Management port
        :param user: Management user name
        :param password: Management user password.
        :param session: Create a client using an existing session
        """
        self.host = host
        self.port = port
        self._auth = []

        # ZFSSA uses self-signed SSL certificates so versions of Python that
        # verify SSL certificates by default need to be disabled for the
        # request.
        if hasattr(ssl, '_create_unverified_context'):
            self.opener = urllib2.build_opener(urllib2.HTTPSHandler(
                context=ssl._create_unverified_context()))
        else:
            self.opener = urllib2.build_opener(urllib2.HTTPHandler())
        self.services = None
        if session:
            self._auth.extend(("X-Auth-Session", session))
        elif user and password:
            auth = "%s:%s" % (user, password)
            basic = "Basic %s" % base64.encodestring(auth).replace('\n', '')
            self._auth.extend(("Authorization", basic))
        self.opener.addheaders = [self._auth,
                                  ('Content-Type', 'application/json'),
                                  ('Accept', 'application/json')]

    def login(self, user, password):
        """
        Create a login session for a client.  The client will keep track of
        the login session information so additional calls can be made without
        having to supply credentials.

        :param user: The login user name
        :param password: The ZFSSA user password
        :return: The REST result of the login call
        """
        if self.services:
            self.logout()

        auth = "%s:%s" % (user, password)
        basic = "Basic %s" % base64.encodestring(auth).replace('\n', '')
        del self._auth[:]
        self._auth.extend(("Authorization", basic))
        url = self.ACCESS_URL % (self.host, self.port)
        request = urllib2.Request(url, '')
        request.get_method = lambda: 'POST'

        try:
            result = RestResult(self.opener.open(request))
            if result.status == Status.CREATED:
                del self._auth[:]
                self._auth.append("X-Auth-Session")
                self._auth.append(result.getheader("X-Auth-Session"))
                data = result.getdata()
                self.services = data.get('services')
        except urllib2.HTTPError as e:
            result = RestResult(e)
        return result

    def logout(self):
        """Logout of the appliance and clear session data"""
        request = urllib2.Request(self.ACCESS_URL % (self.host, self.port))
        request.get_method = lambda: "DELETE"
        result = self.call(request)
        self.opener.addheaders = None
        self.services = None
        return result

    def service_url(self, module, version=None):
        url = None
        for service in self.services:
            if module == service['name']:
                if version and service['version'] != version:
                    continue
                url = service['uri']
                break
        return url

    def url(self, path, service=None, version=None):
        """
        Get the URL of a resource path for the client.

        :param path: Resource path
        :key service: The name of the REST API service
        :key version: The version of the service
        :return:
        """
        if service:
            url = self.service_url(service, version) + path
        else:
            url = self.REST_URL % (self.host, self.port, path)
        return url

    def call(self, request, background=False, status=None):
        """
        Make a REST API call using the specified urllib2 request

        :param request: A urllib2 request object
        :param background: Run call in background flag
        :param status: Expected status
        :return: RestResult
        """
        if background:
            runner = RestRunner(self, request)
            thread = threading.Thread(target=runner)
            thread.start()
            return runner

        try:
            response = self.opener.open(request)
            result = RestResult(response)
        except urllib2.HTTPError as e:
            result = RestResult(e)
        if status and result.status != status:
            message = "Error: %s %s returned status %d, expected %d" % (
                      request.get_method(), request.get_full_url(),
                      result.status, status)
            raise RestException(message, result)
        return result

    def request(self, method, path, data, headers=None,
                service=None, version=None):
        """
        Build a urllib2 REST request.

        :param method: The request method: GET, PUT, POST, or DELETE
        :param path: The request path
        :param data: Optional HTTP body data
        :param headers: Optional HTTP headers dictionary
        :param service: REST API service name
        :param version: REST API version such as "v1.0"
        :return: urllib2 request object
        """
        if not headers:
            headers = {"Content-Type": "application/json"}
        url = self.url(path, service, version)
        if data and not isinstance(data, (str, unicode)):
            data = json.dumps(data)
        request = urllib2.Request(url, data, headers)
        request.get_method = lambda: method.upper()
        return request

    def execute(self, request, **kwargs):
        """Make an HTTP REST request

        :param request: RestRequest object containing the path command and data.
        :param kwargs: Any of the optional parameters used in request or call.
        """
        method = getattr(self, request.method.lower())
        return method(request.path, request.data, **kwargs)

    def __getattr__(self, name):
        method = name.upper()
        if not method in self.METHODS:
            raise Exception("Invalid HTTP request '%s', should be one of %s" %
                            (method, ' '.join(self.METHODS)))
        client = self

        def request_call(path, data=None, headers=None,
                         background=False, status=None, service=None,
                         version=None):
            request = client.request(method, path, data, headers, service,
                                     version)
            return client.call(request, background, status)
        return request_call


class _RestWorker(threading.Thread):
    """A worker thread that runs REST API requests from a queue"""
    def __init__(self, work_queue):
        threading.Thread.__init__(self)
        self._work_queue = work_queue   # Queue containing requests
        self._lock = threading.Lock()   # Lock to protect properties below
        self._request = None            # Current REST request being processed
        self._running = True            # Worker will run while True
        self.setDaemon(True)
        self.start()                    # Start this thread

    def run(self):
        """Run REST API commands from a queue."""
        with self._lock:
            running = self._running

        while running:
            request = self._work_queue.get()
            with self._lock:
                running = self._running
                if running:
                    self._request = request

            if running:
                try:
                    self._request.run()
                except Exception as err:
                    self._request.error = err

            with self._lock:
                self._request = None
                running = self._running

    def shutdown(self):
        """Allows RestThreadPool to shutdown this thread."""
        with self._lock:
            self._running = False
            if self._request:
                self._request.cancel()
            self._request = None


class RestThreadPool(object):
    """A pool of threads that will run REST API client requests."""
    def __init__(self, max_threads=8):
        """Creates a REST API thread pool with the specified max threads"""
        self._work_queue = Queue.Queue()
        self._workers = list()
        self._lock = threading.Lock()   # Lock to protect _workers
        self.max_threads = max_threads

    def add_runner(self, *runners):
        """Adds a REST API runner to the thread pool queue to be processed"""
        for runner in runners:
            self._work_queue.put(runner)
            with self._lock:
                num_threads = len(self._workers)
                if self.max_threads <= 0 or self.max_threads > num_threads:
                    if self._work_queue.qsize() > num_threads:
                        self._workers.append(_RestWorker(self._work_queue))

    def stop(self):
        """Stops all worker threads when thread pool is stopped"""
        with self._lock:
            for worker in self._workers:
                worker.shutdown()


class RestMultiRequest(object):
    """Handles processing for a group of REST API requests"""
    def __init__(self, runs=None, pool=None):
        """Create a group request with a list of RestRunner objects and a
        RestPool used to run the requests"""
        if not runs:
            runs = list()
        self.runs = runs
        if not pool:
            pool = RestThreadPool()
        self.pool = pool

    def run(self):
        self.pool.add_runner(*self.runs)

    def wait(self):
        """Wait for all request runners to finish"""
        done = False
        while not done:
            done = True
            for r in self.runs:
                if not r.handle_result:
                    if r.isdone():
                        self.handle_result(r)
                        r.handle_result = True
                    else:
                        done = False

    def add_request(self, client, request):
        self.runs.append(RestRunner(client, request))

    def handle_result(self, runner):
        """Default result handler called when a single REST request completes"""
        pass
