"""
A REST API for Salt
===================

.. py:currentmodule:: salt.netapi.rest_cherrypy.app

.. note::

    This module is Experimental on Windows platforms and supports limited
    configurations:

    - doesn't support PAM authentication (i.e. external_auth: auto)
    - doesn't support SSL (i.e. disable_ssl: True)

:depends:
    - CherryPy Python module.

      Note: there is a `known SSL traceback for CherryPy versions 3.2.5 through
      3.7.x <https://github.com/cherrypy/cherrypy/issues/1298>`_. Please use
      version 3.2.3 or the latest 10.x version instead.
:optdepends:    - ws4py Python module for websockets support.
:client_libraries:
    - Java: https://github.com/SUSE/salt-netapi-client
    - Python: https://github.com/saltstack/pepper
:setup:
    All steps below are performed on the machine running the Salt Master
    daemon. Configuration goes into the Master configuration file.

    1.  Install ``salt-api``. (This step varies between OS and Linux distros.
        Some package systems have a split package, others include salt-api in
        the main Salt package. Ensure the ``salt-api --version`` output matches
        the ``salt --version`` output.)
    2.  Install CherryPy. (Read the version caveat in the section above.)
    3.  Optional: generate self-signed SSL certificates.

        Using a secure HTTPS connection is strongly recommended since Salt
        eauth authentication credentials will be sent over the wire.

        1.  Install the PyOpenSSL package.
        2.  Generate a self-signed certificate using the
            :py:func:`~salt.modules.tls.create_self_signed_cert` execution
            function.

            .. code-block:: bash

                salt-call --local tls.create_self_signed_cert

    4.  Edit the master config to create at least one external auth user or
        group following the :ref:`full external auth instructions <acl-eauth>`.
    5.  Edit the master config with the following production-ready example to
        enable the ``rest_cherrypy`` module. (Adjust cert paths as needed, or
        disable SSL (not recommended!).)

        .. code-block:: yaml

            rest_cherrypy:
              port: 8000
              ssl_crt: /etc/pki/tls/certs/localhost.crt
              ssl_key: /etc/pki/tls/certs/localhost.key

    6.  Restart the ``salt-master`` daemon.
    7.  Start the ``salt-api`` daemon.

:configuration:
    All available configuration options are detailed below. These settings
    configure the CherryPy HTTP server and do not apply when using an external
    server such as Apache or Nginx.

    port
        **Required**

        The port for the webserver to listen on.
    host : ``0.0.0.0``
        The socket interface for the HTTP server to listen on.
    debug : ``False``
        Starts the web server in development mode. It will reload itself when
        the underlying code is changed and will output more debugging info.
    log_access_file
        Path to a file to write HTTP access logs.

        .. versionadded:: 2016.11.0

    log_error_file
        Path to a file to write HTTP error logs.

        .. versionadded:: 2016.11.0

    ssl_crt
        The path to a SSL certificate. (See below)
    ssl_key
        The path to the private key for your SSL certificate. (See below)
    ssl_chain
        (Optional when using PyOpenSSL) the certificate chain to pass to
        ``Context.load_verify_locations``.
    disable_ssl
        A flag to disable SSL. Warning: your Salt authentication credentials
        will be sent in the clear!
    webhook_disable_auth : False
        The :py:class:`Webhook` URL requires authentication by default but
        external services cannot always be configured to send authentication.
        See the Webhook documentation for suggestions on securing this
        interface.
    webhook_url : /hook
        Configure the URL endpoint for the :py:class:`Webhook` entry point.
    thread_pool : ``100``
        The number of worker threads to start up in the pool.
    socket_queue_size : ``30``
        Specify the maximum number of HTTP connections to queue.
    expire_responses : True
        Whether to check for and kill HTTP responses that have exceeded the
        default timeout.

        .. deprecated:: 2016.11.9,2017.7.3,2018.3.0

            The "expire_responses" configuration setting, which corresponds
            to the ``timeout_monitor`` setting in CherryPy, is no longer
            supported in CherryPy versions >= 12.0.0.

    max_request_body_size : ``1048576``
        Maximum size for the HTTP request body.
    collect_stats : False
        Collect and report statistics about the CherryPy server

        Reports are available via the :py:class:`Stats` URL.
    stats_disable_auth : False
        Do not require authentication to access the ``/stats`` endpoint.

        .. versionadded:: 2018.3.0
    static
        A filesystem path to static HTML/JavaScript/CSS/image assets.
    static_path : ``/static``
        The URL prefix to use when serving static assets out of the directory
        specified in the ``static`` setting.
    enable_sessions : ``True``
        Enable or disable all endpoints that rely on session cookies. This can
        be useful to enforce only header-based authentication.

        .. versionadded:: 2017.7.0

    app : ``index.html``
        A filesystem path to an HTML file that will be served as a static file.
        This is useful for bootstrapping a single-page JavaScript app.

        Warning! If you set this option to a custom web application, anything
        that uses cookie-based authentication is vulnerable to XSRF attacks.
        Send the custom ``X-Auth-Token`` header instead and consider disabling
        the ``enable_sessions`` setting.

        .. versionchanged:: 2017.7.0

            Add a proof-of-concept JavaScript single-page app.

    app_path : ``/app``
        The URL prefix to use for serving the HTML file specified in the ``app``
        setting. This should be a simple name containing no slashes.

        Any path information after the specified path is ignored; this is
        useful for apps that utilize the HTML5 history API.
    root_prefix : ``/``
        A URL path to the main entry point for the application. This is useful
        for serving multiple applications from the same URL.

.. _rest_cherrypy-auth:

Authentication
--------------

Authentication is performed by passing a session token with each request.
Tokens are generated via the :py:class:`Login` URL.

The token may be sent in one of two ways: as a custom header or as a session
cookie. The latter is far more convenient for clients that support cookies.

* Include a custom header named :mailheader:`X-Auth-Token`.

  For example, using curl:

  .. code-block:: bash

      curl -sSk https://localhost:8000/login \\
          -H 'Accept: application/x-yaml' \\
          -d username=saltdev \\
          -d password=saltdev \\
          -d eauth=pam

  Copy the ``token`` value from the output and include it in subsequent requests:

  .. code-block:: bash

      curl -sSk https://localhost:8000 \\
          -H 'Accept: application/x-yaml' \\
          -H 'X-Auth-Token: 697adbdc8fe971d09ae4c2a3add7248859c87079'\\
          -d client=local \\
          -d tgt='*' \\
          -d fun=test.ping

* Sent via a cookie. This option is a convenience for HTTP clients that
  automatically handle cookie support (such as browsers).

  For example, using curl:

  .. code-block:: bash

      # Write the cookie file:
      curl -sSk https://localhost:8000/login \\
            -c ~/cookies.txt \\
            -H 'Accept: application/x-yaml' \\
            -d username=saltdev \\
            -d password=saltdev \\
            -d eauth=auto

      # Read the cookie file:
      curl -sSk https://localhost:8000 \\
            -b ~/cookies.txt \\
            -H 'Accept: application/x-yaml' \\
            -d client=local \\
            -d tgt='*' \\
            -d fun=test.ping

  Another example using the :program:`requests` library in Python:

  .. code-block:: python

      >>> import requests
      >>> session = requests.Session()
      >>> session.post('http://localhost:8000/login', json={
          'username': 'saltdev',
          'password': 'saltdev',
          'eauth': 'auto',
      })
      <Response [200]>
      >>> resp = session.post('http://localhost:8000', json=[{
          'client': 'local',
          'tgt': '*',
          'fun': 'test.arg',
          'arg': ['foo', 'bar'],
          'kwarg': {'baz': 'Baz!'},
      }])
      >>> resp.json()
      {u'return': [{
          ...snip...
      }]}

.. seealso:: You can bypass the session handling via the :py:class:`Run` URL.

Usage
-----

This interface directly exposes Salt's :ref:`Python API <python-api>`.
Everything possible at the CLI is possible through the Python API. Commands are
executed on the Salt Master.

The root URL (``/``) is RPC-like in that it accepts instructions in the request
body for what Salt functions to execute, and the response contains the result
of those function calls.

For example:

.. code-block:: text

    % curl -sSi https://localhost:8000 \
        -H 'Content-type: application/json' \
        -d '[{
            "client": "local",
            "tgt": "*",
            "fun": "test.ping"
        }]'
    HTTP/1.1 200 OK
    Content-Type: application/json
    [...snip...]

    {"return": [{"jerry": true}]}

The request body must be an array of commands. Use this workflow to build a
command:

1.  Choose a client interface.
2.  Choose a function.
3.  Fill out the remaining parameters needed for the chosen client.

The ``client`` field is a reference to the main Python classes used in Salt's
Python API. Read the full :ref:`Client APIs <client-apis>` documentation, but
in short:

* "local" uses :py:class:`LocalClient <salt.client.LocalClient>` which sends
  commands to Minions. Equivalent to the ``salt`` CLI command.
* "runner" uses :py:class:`RunnerClient <salt.runner.RunnerClient>` which
  invokes runner modules on the Master. Equivalent to the ``salt-run`` CLI
  command.
* "wheel" uses :py:class:`WheelClient <salt.wheel.WheelClient>` which invokes
  wheel modules on the Master. Wheel modules do not have a direct CLI
  equivalent but they typically manage Master-side resources such as state
  files, pillar files, the Salt config files, and the :py:mod:`key wheel module
  <salt.wheel.key>` exposes similar functionality as the ``salt-key`` CLI
  command.

Most clients have variants like synchronous or asynchronous execution as well as
others like batch execution. See the :ref:`full list of client interfaces
<client-interfaces>`.

Each client requires different arguments and sometimes has different syntax.
For example, ``LocalClient`` requires the ``tgt`` argument because it forwards
the command to Minions and the other client interfaces do not. ``LocalClient``
also takes ``arg`` (array) and ``kwarg`` (dictionary) arguments because these
values are sent to the Minions and used to execute the requested function
there. ``RunnerClient`` and ``WheelClient`` are executed directly on the Master
and thus do not need or accept those arguments.

Read the method signatures in the client documentation linked above, but
hopefully an example will help illustrate the concept. This example causes Salt
to execute two functions -- the :py:func:`test.arg execution function
<salt.modules.test.arg>` using ``LocalClient`` and the :py:func:`test.arg
runner function <salt.runners.test.arg>` using ``RunnerClient``; note the
different structure for each command. The results for both are combined and
returned as one response.

.. code-block:: text

    % curl -b ~/cookies.txt -sSi localhost:8000 \
        -H 'Content-type: application/json' \
        -d '
    [
        {
            "client": "local",
            "tgt": "*",
            "fun": "test.arg",
            "arg": ["positional arg one", "positional arg two"],
            "kwarg": {
                "keyword arg one": "Hello from a minion",
                "keyword arg two": "Hello again from a minion"
            }
        },
        {
            "client": "runner",
            "fun": "test.arg",
            "keyword arg one": "Hello from a master",
            "keyword arg two": "Runners do not support positional args"
        }
    ]
    '
    HTTP/1.1 200 OK
    [...snip...]
    {
      "return": [
        {
          "jerry": {
            "args": [
              "positional arg one",
              "positional arg two"
            ],
            "kwargs": {
              "keyword arg one": "Hello from a minion",
              "keyword arg two": "Hello again from a minion",
              [...snip...]
            }
          },
          [...snip; other minion returns here...]
        },
        {
          "args": [],
          "kwargs": {
            "keyword arg two": "Runners do not support positional args",
            "keyword arg one": "Hello from a master"
          }
        }
      ]
    }

One more example, this time with more commonly used functions:

.. code-block:: text

    curl -b /tmp/cookies.txt -sSi localhost:8000 \
        -H 'Content-type: application/json' \
        -d '
    [
        {
            "client": "local",
            "tgt": "*",
            "fun": "state.sls",
            "kwarg": {
                "mods": "apache",
                "pillar": {
                    "lookup": {
                        "wwwdir": "/srv/httpd/htdocs"
                    }
                }
            }
        },
        {
            "client": "runner",
            "fun": "cloud.create",
            "provider": "my-ec2-provider",
            "instances": "my-centos-6",
            "image": "ami-1624987f",
            "delvol_on_destroy", true
        }
    ]
    '
    HTTP/1.1 200 OK
    [...snip...]
    {
      "return": [
        {
          "jerry": {
            "pkg_|-install_apache_|-httpd_|-installed": {
                [...snip full state return here...]
            }
          }
          [...snip other minion returns here...]
        },
        {
            [...snip full salt-cloud output here...]
        }
      ]
    }

Content negotiation
-------------------

This REST interface is flexible in what data formats it will accept as well
as what formats it will return (e.g., JSON, YAML, urlencoded).

* Specify the format of data in the request body by including the
  :mailheader:`Content-Type` header.
* Specify the desired data format for the response body with the
  :mailheader:`Accept` header.

We recommend the JSON format for most HTTP requests. urlencoded data is simple
and cannot express complex data structures -- and that is often required for
some Salt commands, such as starting a state run that uses Pillar data. Salt's
CLI tool can reformat strings passed in at the CLI into complex data
structures, and that behavior also works via salt-api, but that can be brittle
and since salt-api can accept JSON it is best just to send JSON.

Here is an example of sending urlencoded data:

.. code-block:: bash

    curl -sSik https://localhost:8000 \\
        -b ~/cookies.txt \\
        -d client=runner \\
        -d fun='jobs.lookup_jid' \\
        -d jid='20150129182456704682'

.. admonition:: urlencoded data caveats

    * Only a single command may be sent per HTTP request.
    * Repeating the ``arg`` parameter multiple times will cause those
      parameters to be combined into a single list.

      Note, some popular frameworks and languages (notably jQuery, PHP, and
      Ruby on Rails) will automatically append empty brackets onto repeated
      query string parameters. E.g., ``?foo[]=fooone&foo[]=footwo``. This is
      **not** supported; send ``?foo=fooone&foo=footwo`` instead, or send JSON
      or YAML.

    A note about ``curl``

    The ``-d`` flag to curl does *not* automatically urlencode data which can
    affect passwords and other data that contains characters that must be
    encoded. Use the ``--data-urlencode`` flag instead. E.g.:

    .. code-block:: bash

        curl -ksi http://localhost:8000/login \\
        -H "Accept: application/json" \\
        -d username='myapiuser' \\
        --data-urlencode password='1234+' \\
        -d eauth='pam'

Performance Expectations and Recommended Usage
==============================================

This module provides a thin wrapper around :ref:`Salt's Python API
<python-api>`. Executing a Salt command via rest_cherrypy is directly analogous
to executing a Salt command via Salt's CLI (which also uses the Python API) --
they share the same semantics, performance characteristics, and 98% of the same
code. As a rule-of-thumb: if you wouldn't do it at the CLI don't do it via this
API.

Long-Running HTTP Connections
-----------------------------

The CherryPy server is a production-ready, threading HTTP server written in
Python. Because it makes use of a thread pool to process HTTP requests it is
not ideally suited to maintaining large numbers of concurrent, synchronous
connections. On moderate hardware with default settings it should top-out at
around 30 to 50 concurrent connections.

That number of long-running, synchronous Salt processes is also not ideal. Like
at the CLI, each Salt command run will start a process that instantiates its
own ``LocalClient``, which instantiates its own listener to the Salt event bus,
and sends out its own periodic ``saltutil.find_job`` queries to determine if a
Minion is still running the command. Not exactly a lightweight operation.

Timeouts
--------

In addition to the above resource overhead for long-running connections, there
are the usual HTTP timeout semantics for the CherryPy server, any HTTP client
being used, as well as any hardware in between such as proxies, gateways, or
load balancers. rest_cherrypy can be configured not to time-out long responses
via the ``expire_responses`` setting, and both :py:class:`LocalClient
<salt.client.LocalClient>` and :py:class:`RunnerClient
<salt.runner.RunnerClient>` have their own timeout parameters that may be
passed as top-level keywords:

.. code-block:: bash

    curl -b /tmp/cookies.txt -sSi localhost:8000 \
        -H 'Content-type: application/json' \
        -d '
    [
        {
            "client": "local",
            "tgt": "*",
            "fun": "test.sleep",
            "kwarg": {"length": 30},
            "timeout": 60
        },
        {
            "client": "runner",
            "fun": "test.sleep",
            "kwarg": {"s_time": 30},
            "timeout": 60
        }
    ]
    '

Best Practices
--------------

Given the performance overhead and HTTP timeouts for long-running operations
described above, the most effective and most scalable way to use both Salt and
salt-api is to run commands asynchronously using the ``local_async``,
``runner_async``, and ``wheel_async`` clients.

Running asynchronous jobs results in being able to process 3x more commands per second
for ``LocalClient`` and 17x more commands per second for ``RunnerClient``, in
addition to much less network traffic and memory requirements. Job returns can
be fetched from Salt's job cache via the ``/jobs/<jid>`` endpoint, or they can
be collected into a data store using Salt's :ref:`Returner system <returners>`.

The ``/events`` endpoint is specifically designed to handle long-running HTTP
connections and it exposes Salt's event bus which includes job returns.
Watching this endpoint first, then executing asynchronous Salt commands second,
is the most lightweight and scalable way to use ``rest_cherrypy`` while still
receiving job returns in real-time. But this requires clients that can properly
handle the inherent asynchronicity of that workflow.

Performance Tuning
------------------

The ``thread_pool`` and ``socket_queue_size`` settings can be used to increase
the capacity of rest_cherrypy to handle incoming requests. Keep an eye on RAM
usage as well as available file handles while testing changes to these
settings. As salt-api is a thin wrapper around Salt's Python API, also keep an
eye on the performance of Salt when testing.

Future Plans
------------

Now that Salt uses the Tornado concurrency library internally, we plan to
improve performance in the API by taking advantage of existing processes and
event listeners and to use lightweight coroutines to facilitate more
simultaneous HTTP connections and better support for synchronous operations.
That effort can be tracked in `issue 26505`__, but until that issue is closed
rest_cherrypy will remain the officially recommended REST API.

.. __: https://github.com/saltstack/salt/issues/26505

.. |req_token| replace:: a session token from :py:class:`~Login`.
.. |req_accept| replace:: the desired response format.
.. |req_ct| replace:: the format of the request body.

.. |res_ct| replace:: the format of the response body; depends on the
    :mailheader:`Accept` request header.

.. |200| replace:: success
.. |400| replace:: bad or malformed request
.. |401| replace:: authentication required
.. |406| replace:: requested Content-Type not available

"""

import functools
import io
import itertools
import logging
import os
import signal
import tarfile
import time
from collections.abc import Iterator, Mapping
from multiprocessing import Pipe, Process
from urllib.parse import parse_qsl

import cherrypy  # pylint: disable=import-error,3rd-party-module-not-gated

import salt
import salt.auth
import salt.exceptions
import salt.netapi
import salt.utils.args
import salt.utils.event
import salt.utils.json
import salt.utils.stringutils
import salt.utils.versions
import salt.utils.yaml

logger = logging.getLogger(__name__)


try:
    from cherrypy.lib import (  # pylint: disable=import-error,3rd-party-module-not-gated
        cpstats,
    )
except AttributeError:
    cpstats = None
    logger.warning(
        "Import of cherrypy.cpstats failed. Possible upstream bug: "
        "https://github.com/cherrypy/cherrypy/issues/1444"
    )
except ImportError:
    cpstats = None
    logger.warning("Import of cherrypy.cpstats failed.")

try:
    # Imports related to websocket
    from . import event_processor
    from .tools import websockets

    HAS_WEBSOCKETS = True
except ImportError:
    websockets = type("websockets", (object,), {"SynchronizingWebsocket": None})

    HAS_WEBSOCKETS = False


def html_override_tool():
    """
    Bypass the normal handler and serve HTML for all URLs

    The ``app_path`` setting must be non-empty and the request must ask for
    ``text/html`` in the ``Accept`` header.
    """
    apiopts = cherrypy.config["apiopts"]
    request = cherrypy.request

    url_blacklist = (
        apiopts.get("app_path", "/app"),
        apiopts.get("static_path", "/static"),
    )

    if "app" not in cherrypy.config["apiopts"]:
        return

    if request.path_info.startswith(url_blacklist):
        return

    if request.headers.get("Accept") == "*/*":
        return

    try:
        wants_html = cherrypy.lib.cptools.accept("text/html")
    except cherrypy.HTTPError:
        return
    else:
        if wants_html != "text/html":
            return

    raise cherrypy.InternalRedirect(apiopts.get("app_path", "/app"))


def salt_token_tool():
    """
    If the custom authentication header is supplied, put it in the cookie dict
    so the rest of the session-based auth works as intended
    """
    x_auth = cherrypy.request.headers.get("X-Auth-Token", None)

    # X-Auth-Token header trumps session cookie
    if x_auth:
        cherrypy.request.cookie["session_id"] = x_auth


def salt_api_acl_tool(username, request):
    """
    .. versionadded:: 2016.3.0

    Verifies user requests against the API whitelist. (User/IP pair)
    in order to provide whitelisting for the API similar to the
    master, but over the API.

    .. code-block:: yaml

        rest_cherrypy:
            api_acl:
                users:
                    '*':
                        - 1.1.1.1
                        - 1.1.1.2
                    foo:
                        - 8.8.4.4
                    bar:
                        - '*'

    :param username: Username to check against the API.
    :type username: str
    :param request: Cherrypy request to check against the API.
    :type request: cherrypy.request
    """
    failure_str = "[api_acl] Authentication failed for user %s from IP %s"
    success_str = "[api_acl] Authentication successful for user %s from IP %s"
    pass_str = "[api_acl] Authentication not checked for user %s from IP %s"

    acl = None
    # Salt Configuration
    salt_config = cherrypy.config.get("saltopts", None)
    if salt_config:
        # Cherrypy Config.
        cherrypy_conf = salt_config.get("rest_cherrypy", None)
        if cherrypy_conf:
            # ACL Config.
            acl = cherrypy_conf.get("api_acl", None)

    ip = request.remote.ip
    if acl:
        users = acl.get("users", {})
        if users:
            if username in users:
                if ip in users[username] or "*" in users[username]:
                    logger.info(success_str, username, ip)
                    return True
                else:
                    logger.info(failure_str, username, ip)
                    return False
            elif username not in users and "*" in users:
                if ip in users["*"] or "*" in users["*"]:
                    logger.info(success_str, username, ip)
                    return True
                else:
                    logger.info(failure_str, username, ip)
                    return False
            else:
                logger.info(failure_str, username, ip)
                return False
    else:
        logger.info(pass_str, username, ip)
        return True


def salt_ip_verify_tool():
    """
    If there is a list of restricted IPs, verify current
    client is coming from one of those IPs.
    """
    # This is overly cumbersome and crude,
    # But, it's also safe... ish...
    salt_config = cherrypy.config.get("saltopts", None)
    if salt_config:
        cherrypy_conf = salt_config.get("rest_cherrypy", None)
        if cherrypy_conf:
            auth_ip_list = cherrypy_conf.get("authorized_ips", None)
            if auth_ip_list:
                logger.debug("Found IP list: %s", auth_ip_list)
                rem_ip = cherrypy.request.headers.get("Remote-Addr", None)
                logger.debug("Request from IP: %s", rem_ip)
                if rem_ip not in auth_ip_list:
                    logger.error("Blocked IP: %s", rem_ip)
                    raise cherrypy.HTTPError(403, "Bad IP")


def salt_auth_tool():
    """
    Redirect all unauthenticated requests to the login page
    """
    # Redirect to the login page if the session hasn't been authed
    if "token" not in cherrypy.session:
        raise cherrypy.HTTPError(401)

    # Session is authenticated; inform caches
    cherrypy.response.headers["Cache-Control"] = "private"


def cors_tool():
    """
    Handle both simple and complex CORS requests

    Add CORS headers to each response. If the request is a CORS preflight
    request swap out the default handler with a simple, single-purpose handler
    that verifies the request and provides a valid CORS response.
    """
    req_head = cherrypy.request.headers
    resp_head = cherrypy.response.headers

    # Always set response headers necessary for 'simple' CORS.
    resp_head["Access-Control-Allow-Origin"] = req_head.get("Origin", "*")
    resp_head["Access-Control-Expose-Headers"] = "GET, POST"
    resp_head["Access-Control-Allow-Credentials"] = "true"

    # Non-simple CORS preflight request; short-circuit the normal handler.
    if cherrypy.request.method == "OPTIONS":
        ac_method = req_head.get("Access-Control-Request-Method", None)

        allowed_methods = ["GET", "POST"]
        allowed_headers = [
            "Content-Type",
            "X-Auth-Token",
            "X-Requested-With",
        ]

        if ac_method and ac_method in allowed_methods:
            resp_head["Access-Control-Allow-Methods"] = ", ".join(allowed_methods)
            resp_head["Access-Control-Allow-Headers"] = ", ".join(allowed_headers)

            resp_head["Connection"] = "keep-alive"
            resp_head["Access-Control-Max-Age"] = "1400"

        # Note: CherryPy on Py3 uses binary objects for the response
        # Python 2.6 also supports the byte prefix, so no need for conditionals
        cherrypy.response.body = b""
        cherrypy.response.status = 200
        # CORS requests should short-circuit the other tools.
        cherrypy.serving.request.handler = None

        # Needed to avoid the auth_tool check.
        if cherrypy.request.config.get("tools.sessions.on", False):
            cherrypy.session["token"] = True
        return True


# Be conservative in what you send
# Maps Content-Type to serialization functions; this is a tuple of tuples to
# preserve order of preference.
ct_out_map = (
    ("application/json", salt.utils.json.dumps),
    (
        "application/x-yaml",
        functools.partial(salt.utils.yaml.safe_dump, default_flow_style=False),
    ),
)


def hypermedia_handler(*args, **kwargs):
    """
    Determine the best output format based on the Accept header, execute the
    regular handler, and transform the output to the request content type (even
    if it's an error).

    :param args: Pass args through to the main handler
    :param kwargs: Pass kwargs through to the main handler
    """
    # Execute the real handler. Handle or pass-through any errors we know how
    # to handle (auth & HTTP errors). Reformat any errors we don't know how to
    # handle as a data structure.
    try:
        cherrypy.response.processors = dict(ct_out_map)
        ret = cherrypy.serving.request._hypermedia_inner_handler(*args, **kwargs)
    except (
        salt.exceptions.AuthenticationError,
        salt.exceptions.AuthorizationError,
        salt.exceptions.EauthAuthenticationError,
        salt.exceptions.TokenAuthenticationError,
    ) as e:
        logger.error(e.message)
        raise cherrypy.HTTPError(401, e.message)
    except salt.exceptions.SaltInvocationError as e:
        logger.error(e.message)
        raise cherrypy.HTTPError(400, e.message)
    except (
        salt.exceptions.SaltDaemonNotRunning,
        salt.exceptions.SaltReqTimeoutError,
    ) as exc:
        raise cherrypy.HTTPError(503, exc.strerror)
    except salt.exceptions.SaltClientTimeout:
        raise cherrypy.HTTPError(504)
    except cherrypy.CherryPyException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        # The TimeoutError exception class was removed in CherryPy in 12.0.0, but
        # Still check existence of TimeoutError and handle in CherryPy < 12.
        # The check was moved down from the SaltClientTimeout error line because
        # A one-line if statement throws a BaseException inheritance TypeError.
        if hasattr(cherrypy, "TimeoutError") and isinstance(exc, cherrypy.TimeoutError):
            raise cherrypy.HTTPError(504)

        import traceback

        logger.debug(
            "Error while processing request for: %s",
            cherrypy.request.path_info,
            exc_info=True,
        )

        cherrypy.response.status = 500

        ret = {
            "status": cherrypy.response.status,
            "return": (
                f"{traceback.format_exc()}"
                if cherrypy.config["debug"]
                else "An unexpected error occurred"
            ),
        }

    # Raises 406 if requested content-type is not supported
    best = cherrypy.lib.cptools.accept([i for (i, _) in ct_out_map])

    # Transform the output from the handler into the requested output format
    cherrypy.response.headers["Content-Type"] = best
    out = cherrypy.response.processors[best]
    try:
        response = out(ret)
        return salt.utils.stringutils.to_bytes(response)
    except Exception:  # pylint: disable=broad-except
        msg = "Could not serialize the return data from Salt."
        logger.debug(msg, exc_info=True)
        raise cherrypy.HTTPError(500, msg)


def hypermedia_out():
    """
    Determine the best handler for the requested content type

    Wrap the normal handler and transform the output from that handler into the
    requested content type
    """
    request = cherrypy.serving.request
    request._hypermedia_inner_handler = request.handler

    # If handler has been explicitly set to None, don't override.
    if request.handler is not None:
        request.handler = hypermedia_handler


def process_request_body(fn):
    """
    A decorator to skip a processor function if process_request_body is False
    """

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):  # pylint: disable=C0111
        if cherrypy.request.process_request_body is not False:
            fn(*args, **kwargs)

    return wrapped


def urlencoded_processor(entity):
    """
    Accept x-www-form-urlencoded data and reformat it into a Low State
    data structure.

    Since we can't easily represent complicated data structures with
    key-value pairs, any more complicated requirements (e.g. compound
    commands) must instead be delivered via JSON or YAML.

    For example::

    .. code-block:: bash

        curl -si localhost:8000 -d client=local -d tgt='*' \\
                -d fun='test.kwarg' -d arg='one=1' -d arg='two=2'

    :param entity: raw POST data
    """
    # cherrypy._cpreqbody.process_urlencoded doesn't preserve the raw
    # "body", so we have to handle parsing the tokens using parse_qsl
    urlencoded = entity.read()
    try:
        urlencoded = urlencoded.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        pass
    cherrypy.serving.request.raw_body = urlencoded
    unserialized_data = {}
    for key, val in parse_qsl(urlencoded):
        unserialized_data.setdefault(key, []).append(val)
    for key, val in unserialized_data.items():
        if len(val) == 1:
            unserialized_data[key] = val[0]
        if len(val) == 0:
            unserialized_data[key] = ""

    # Parse `arg` and `kwarg` just like we do it on the CLI
    if "kwarg" in unserialized_data:
        unserialized_data["kwarg"] = salt.utils.args.yamlify_arg(
            unserialized_data["kwarg"]
        )
    if "arg" in unserialized_data:
        if isinstance(unserialized_data["arg"], list):
            for idx, value in enumerate(unserialized_data["arg"]):
                unserialized_data["arg"][idx] = salt.utils.args.yamlify_arg(value)
        else:
            unserialized_data["arg"] = [
                salt.utils.args.yamlify_arg(unserialized_data["arg"])
            ]
    cherrypy.serving.request.unserialized_data = unserialized_data


@process_request_body
def json_processor(entity):
    """
    Unserialize raw POST data in JSON format to a Python data structure.

    :param entity: raw POST data
    """
    # https://github.com/cherrypy/cherrypy/pull/1572
    contents = io.BytesIO()
    body = entity.fp.read(fp_out=contents)
    contents.seek(0)
    body = salt.utils.stringutils.to_unicode(contents.read())
    del contents
    try:
        cherrypy.serving.request.unserialized_data = salt.utils.json.loads(body)
    except ValueError:
        raise cherrypy.HTTPError(400, "Invalid JSON document")

    cherrypy.serving.request.raw_body = body


@process_request_body
def yaml_processor(entity):
    """
    Unserialize raw POST data in YAML format to a Python data structure.

    :param entity: raw POST data
    """
    # https://github.com/cherrypy/cherrypy/pull/1572
    contents = io.BytesIO()
    body = entity.fp.read(fp_out=contents)
    contents.seek(0)
    body = salt.utils.stringutils.to_unicode(contents.read())
    try:
        cherrypy.serving.request.unserialized_data = salt.utils.yaml.safe_load(body)
    except ValueError:
        raise cherrypy.HTTPError(400, "Invalid YAML document")

    cherrypy.serving.request.raw_body = body


@process_request_body
def text_processor(entity):
    """
    Attempt to unserialize plain text as JSON

    Some large services still send JSON with a text/plain Content-Type. Those
    services are bad and should feel bad.

    :param entity: raw POST data
    """
    # https://github.com/cherrypy/cherrypy/pull/1572
    contents = io.BytesIO()
    body = entity.fp.read(fp_out=contents)
    contents.seek(0)
    body = salt.utils.stringutils.to_unicode(contents.read())
    try:
        cherrypy.serving.request.unserialized_data = salt.utils.json.loads(body)
    except ValueError:
        cherrypy.serving.request.unserialized_data = body

    cherrypy.serving.request.raw_body = body


def hypermedia_in():
    """
    Unserialize POST/PUT data of a specified Content-Type.

    The following custom processors all are intended to format Low State data
    and will place that data structure into the request object.

    :raises HTTPError: if the request contains a Content-Type that we do not
        have a processor for
    """
    # Be liberal in what you accept
    ct_in_map = {
        "application/x-www-form-urlencoded": urlencoded_processor,
        "application/json": json_processor,
        "application/x-yaml": yaml_processor,
        "text/yaml": yaml_processor,
        "text/plain": text_processor,
    }

    # Do not process the body for POST requests that have specified no content
    # or have not specified Content-Length
    if (
        cherrypy.request.method.upper() == "POST"
        and cherrypy.request.headers.get("Content-Length", "0") == "0"
    ):
        cherrypy.request.process_request_body = False
        cherrypy.request.unserialized_data = None

    cherrypy.request.body.processors.clear()
    cherrypy.request.body.default_proc = cherrypy.HTTPError(
        406, "Content type not supported"
    )
    cherrypy.request.body.processors = ct_in_map


def lowdata_fmt():
    """
    Validate and format lowdata from incoming unserialized request data

    This tool requires that the hypermedia_in tool has already been run.
    """

    if cherrypy.request.method.upper() != "POST":
        return

    data = cherrypy.request.unserialized_data

    # if the data was sent as urlencoded, we need to make it a list.
    # this is a very forgiving implementation as different clients set different
    # headers for form encoded data (including charset or something similar)
    if data and isinstance(data, Mapping):
        # Make the 'arg' param a list if not already
        if "arg" in data and not isinstance(
            data["arg"], list
        ):  # pylint: disable=unsupported-membership-test
            data["arg"] = [data["arg"]]

        # Finally, make a Low State and put it in request
        cherrypy.request.lowstate = [data]
    else:
        cherrypy.serving.request.lowstate = data


tools_config = {
    "on_start_resource": [
        ("html_override", html_override_tool),
        ("salt_token", salt_token_tool),
    ],
    "before_request_body": [
        ("cors_tool", cors_tool),
        ("salt_auth", salt_auth_tool),
        ("hypermedia_in", hypermedia_in),
    ],
    "before_handler": [
        ("lowdata_fmt", lowdata_fmt),
        ("hypermedia_out", hypermedia_out),
        ("salt_ip_verify", salt_ip_verify_tool),
    ],
}

for hook, tool_list in tools_config.items():
    for idx, tool_config in enumerate(tool_list):
        tool_name, tool_fn = tool_config
        setattr(
            cherrypy.tools, tool_name, cherrypy.Tool(hook, tool_fn, priority=50 + idx)
        )


###############################################################################


class LowDataAdapter:
    """
    The primary entry point to Salt's REST API

    """

    exposed = True

    _cp_config = {
        "tools.salt_token.on": True,
        "tools.sessions.on": True,
        "tools.sessions.timeout": 60 * 10,  # 10 hours
        # 'tools.autovary.on': True,
        "tools.hypermedia_out.on": True,
        "tools.hypermedia_in.on": True,
        "tools.lowdata_fmt.on": True,
        "tools.salt_ip_verify.on": True,
    }

    def __init__(self):
        self.opts = cherrypy.config["saltopts"]
        self.apiopts = cherrypy.config["apiopts"]
        self.api = salt.netapi.NetapiClient(self.opts)

    def exec_lowstate(self, client=None, token=None):
        """
        Pull a Low State data structure from request and execute the low-data
        chunks through Salt. The low-data chunks will be updated to include the
        authorization token for the current session.
        """
        lowstate = cherrypy.request.lowstate

        # Release the session lock before executing any potentially
        # long-running Salt commands. This allows different threads to execute
        # Salt commands concurrently without blocking.
        if cherrypy.request.config.get("tools.sessions.on", False):
            cherrypy.session.release_lock()

        # if the lowstate loaded isn't a list, lets notify the client
        if not isinstance(lowstate, list):
            raise cherrypy.HTTPError(400, "Lowstates must be a list")

        # Make any requested additions or modifications to each lowstate, then
        # execute each one and yield the result.
        for chunk in lowstate:
            if token:
                chunk["token"] = token

            if "token" in chunk:
                # Make sure that auth token is hex
                try:
                    int(chunk["token"], 16)
                except (TypeError, ValueError):
                    raise cherrypy.HTTPError(401, "Invalid token")

            if "token" in chunk:
                # Make sure that auth token is hex
                try:
                    int(chunk["token"], 16)
                except (TypeError, ValueError):
                    raise cherrypy.HTTPError(401, "Invalid token")

            if client:
                chunk["client"] = client

            # Make any 'arg' params a list if not already.
            # This is largely to fix a deficiency in the urlencoded format.
            if "arg" in chunk and not isinstance(chunk["arg"], list):
                chunk["arg"] = [chunk["arg"]]

            ret = self.api.run(chunk)

            # Sometimes Salt gives us a return and sometimes an iterator
            if isinstance(ret, Iterator):
                yield from ret
            else:
                yield ret

    @cherrypy.config(**{"tools.sessions.on": False})
    def GET(self):
        """
        An explanation of the API with links of where to go next

        .. http:get:: /

            :reqheader Accept: |req_accept|

            :status 200: |200|
            :status 401: |401|
            :status 406: |406|

        **Example request:**

        .. code-block:: bash

            curl -i localhost:8000

        .. code-block:: text

            GET / HTTP/1.1
            Host: localhost:8000
            Accept: application/json

        **Example response:**

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Type: application/json
        """
        return {
            "return": "Welcome",
            "clients": salt.netapi.CLIENTS,
        }

    @cherrypy.tools.salt_token()
    @cherrypy.tools.salt_auth()
    def POST(self, **kwargs):
        """
        Send one or more Salt commands in the request body

        .. http:post:: /

            :reqheader X-Auth-Token: |req_token|
            :reqheader Accept: |req_accept|
            :reqheader Content-Type: |req_ct|

            :resheader Content-Type: |res_ct|

            :status 200: |200|
            :status 400: |400|
            :status 401: |401|
            :status 406: |406|

            :term:`lowstate` data describing Salt commands must be sent in the
            request body.

        **Example request:**

        .. code-block:: bash

            curl -sSik https://localhost:8000 \\
                -b ~/cookies.txt \\
                -H "Accept: application/x-yaml" \\
                -H "Content-type: application/json" \\
                -d '[{"client": "local", "tgt": "*", "fun": "test.ping"}]'

        .. code-block:: text

            POST / HTTP/1.1
            Host: localhost:8000
            Accept: application/x-yaml
            X-Auth-Token: d40d1e1e
            Content-Type: application/json

            [{"client": "local", "tgt": "*", "fun": "test.ping"}]

        **Example response:**

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Length: 200
            Allow: GET, HEAD, POST
            Content-Type: application/x-yaml

            return:
            - ms-0: true
              ms-1: true
              ms-2: true
              ms-3: true
              ms-4: true
        """
        return {"return": list(self.exec_lowstate(token=cherrypy.session.get("token")))}


class Minions(LowDataAdapter):
    """
    Convenience URLs for working with minions
    """

    _cp_config = dict(LowDataAdapter._cp_config, **{"tools.salt_auth.on": True})

    def GET(self, mid=None):  # pylint: disable=arguments-differ
        """
        A convenience URL for getting lists of minions or getting minion
        details

        .. http:get:: /minions/(mid)

            :reqheader X-Auth-Token: |req_token|
            :reqheader Accept: |req_accept|

            :status 200: |200|
            :status 401: |401|
            :status 406: |406|

        **Example request:**

        .. code-block:: bash

            curl -i localhost:8000/minions/ms-3

        .. code-block:: text

            GET /minions/ms-3 HTTP/1.1
            Host: localhost:8000
            Accept: application/x-yaml

        **Example response:**

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Length: 129005
            Content-Type: application/x-yaml

            return:
            - ms-3:
                grains.items:
                    ...
        """
        cherrypy.request.lowstate = [
            {"client": "local", "tgt": mid or "*", "fun": "grains.items"}
        ]
        return {
            "return": list(self.exec_lowstate(token=cherrypy.session.get("token"))),
        }

    def POST(self, **kwargs):
        """
        Start an execution command and immediately return the job id

        .. http:post:: /minions

            :reqheader X-Auth-Token: |req_token|
            :reqheader Accept: |req_accept|
            :reqheader Content-Type: |req_ct|

            :resheader Content-Type: |res_ct|

            :status 200: |200|
            :status 400: |400|
            :status 401: |401|
            :status 406: |406|

            Lowstate data describing Salt commands must be sent in the request
            body. The ``client`` option will be set to
            :py:meth:`~salt.client.LocalClient.local_async`.

        **Example request:**

        .. code-block:: bash

            curl -sSi localhost:8000/minions \\
                -b ~/cookies.txt \\
                -H "Accept: application/x-yaml" \\
                -d '[{"tgt": "*", "fun": "status.diskusage"}]'

        .. code-block:: text

            POST /minions HTTP/1.1
            Host: localhost:8000
            Accept: application/x-yaml
            Content-Type: application/x-www-form-urlencoded

            tgt=*&fun=status.diskusage

        **Example response:**

        .. code-block:: text

            HTTP/1.1 202 Accepted
            Content-Length: 86
            Content-Type: application/x-yaml

            return:
            - jid: '20130603122505459265'
              minions: [ms-4, ms-3, ms-2, ms-1, ms-0]
            _links:
              jobs:
                - href: /jobs/20130603122505459265
        """
        job_data = list(
            self.exec_lowstate(
                client="local_async", token=cherrypy.session.get("token")
            )
        )

        cherrypy.response.status = 202
        return {
            "return": job_data,
            "_links": {
                "jobs": [{"href": "/jobs/{}".format(i["jid"])} for i in job_data if i],
            },
        }


class Jobs(LowDataAdapter):
    _cp_config = dict(LowDataAdapter._cp_config, **{"tools.salt_auth.on": True})

    def GET(self, jid=None, timeout=""):  # pylint: disable=arguments-differ
        """
        A convenience URL for getting lists of previously run jobs or getting
        the return from a single job

        .. http:get:: /jobs/(jid)

            List jobs or show a single job from the job cache.

            :reqheader X-Auth-Token: |req_token|
            :reqheader Accept: |req_accept|

            :status 200: |200|
            :status 401: |401|
            :status 406: |406|

        **Example request:**

        .. code-block:: bash

            curl -i localhost:8000/jobs

        .. code-block:: text

            GET /jobs HTTP/1.1
            Host: localhost:8000
            Accept: application/x-yaml

        **Example response:**

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Length: 165
            Content-Type: application/x-yaml

            return:
            - '20121130104633606931':
                Arguments:
                - '3'
                Function: test.fib
                Start Time: 2012, Nov 30 10:46:33.606931
                Target: jerry
                Target-type: glob

        **Example request:**

        .. code-block:: bash

            curl -i localhost:8000/jobs/20121130104633606931

        .. code-block:: text

            GET /jobs/20121130104633606931 HTTP/1.1
            Host: localhost:8000
            Accept: application/x-yaml

        **Example response:**

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Length: 73
            Content-Type: application/x-yaml

            info:
            - Arguments:
                - '3'
                Function: test.fib
                Minions:
                - jerry
                Start Time: 2012, Nov 30 10:46:33.606931
                Target: '*'
                Target-type: glob
                User: saltdev
                jid: '20121130104633606931'
            return:
            - jerry:
                - - 0
                - 1
                - 1
                - 2
                - 6.9141387939453125e-06
        """
        lowstate = {"client": "runner"}
        if jid:
            lowstate.update({"fun": "jobs.list_job", "jid": jid})
        else:
            lowstate.update({"fun": "jobs.list_jobs"})

        cherrypy.request.lowstate = [lowstate]
        job_ret_info = list(self.exec_lowstate(token=cherrypy.session.get("token")))

        ret = {}
        if jid:
            ret["info"] = [job_ret_info[0]]
            minion_ret = {}
            returns = job_ret_info[0].get("Result")
            for minion in returns:
                if "return" in returns[minion]:
                    minion_ret[minion] = returns[minion].get("return")
                else:
                    minion_ret[minion] = returns[minion].get("return")
            ret["return"] = [minion_ret]
        else:
            ret["return"] = [job_ret_info[0]]

        return ret


class Keys(LowDataAdapter):
    """
    Convenience URLs for working with minion keys

    .. versionadded:: 2014.7.0

    These URLs wrap the functionality provided by the :py:mod:`key wheel
    module <salt.wheel.key>` functions.
    """

    def GET(self, mid=None):  # pylint: disable=arguments-differ
        """
        Show the list of minion keys or detail on a specific key

        .. versionadded:: 2014.7.0

        .. http:get:: /keys/(mid)

            List all keys or show a specific key

            :reqheader X-Auth-Token: |req_token|
            :reqheader Accept: |req_accept|

            :status 200: |200|
            :status 401: |401|
            :status 406: |406|

        **Example request:**

        .. code-block:: bash

            curl -i localhost:8000/keys

        .. code-block:: text

            GET /keys HTTP/1.1
            Host: localhost:8000
            Accept: application/x-yaml

        **Example response:**

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Length: 165
            Content-Type: application/x-yaml

            return:
              local:
              - master.pem
              - master.pub
              minions:
              - jerry
              minions_pre: []
              minions_rejected: []

        **Example request:**

        .. code-block:: bash

            curl -i localhost:8000/keys/jerry

        .. code-block:: text

            GET /keys/jerry HTTP/1.1
            Host: localhost:8000
            Accept: application/x-yaml

        **Example response:**

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Length: 73
            Content-Type: application/x-yaml

            return:
              minions:
                jerry: 51:93:b3:d0:9f:3a:6d:e5:28:67:c2:4b:27:d6:cd:2b
        """
        if mid:
            lowstate = [{"client": "wheel", "fun": "key.finger", "match": mid}]
        else:
            lowstate = [{"client": "wheel", "fun": "key.list_all"}]

        cherrypy.request.lowstate = lowstate
        result = self.exec_lowstate(token=cherrypy.session.get("token"))

        return {"return": next(result, {}).get("data", {}).get("return", {})}

    @cherrypy.config(**{"tools.hypermedia_out.on": False, "tools.sessions.on": False})
    def POST(self, **kwargs):
        r"""
        Easily generate keys for a minion and auto-accept the new key

        Accepts all the same parameters as the :py:func:`key.gen_accept
        <salt.wheel.key.gen_accept>`.

        .. note:: A note about ``curl``
           Avoid using the ``-i`` flag or HTTP headers will be written and
           produce an invalid tar file.

        Example partial kickstart script to bootstrap a new minion:

        .. code-block:: text

            %post
            mkdir -p /etc/salt/pki/minion
            curl -sSk https://localhost:8000/keys \
                    -d mid=jerry \
                    -d username=kickstart \
                    -d password=kickstart \
                    -d eauth=pam \
                | tar -C /etc/salt/pki/minion -xf -

            mkdir -p /etc/salt/minion.d
            printf 'master: 10.0.0.5\nid: jerry' > /etc/salt/minion.d/id.conf
            %end

        .. http:post:: /keys

            Generate a public and private key and return both as a tarball

            Authentication credentials must be passed in the request.

            :status 200: |200|
            :status 401: |401|
            :status 406: |406|

        **Example request:**

        .. code-block:: bash

            curl -sSk https://localhost:8000/keys \
                    -d mid=jerry \
                    -d username=kickstart \
                    -d password=kickstart \
                    -d eauth=pam \
                    -o jerry-salt-keys.tar

        .. code-block:: text

            POST /keys HTTP/1.1
            Host: localhost:8000

        **Example response:**

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Length: 10240
            Content-Disposition: attachment; filename="saltkeys-jerry.tar"
            Content-Type: application/x-tar

            jerry.pub0000644000000000000000000000070300000000000010730 0ustar  00000000000000
        """
        lowstate = cherrypy.request.lowstate
        lowstate[0].update({"client": "wheel", "fun": "key.gen_accept"})

        if "mid" in lowstate[0]:
            lowstate[0]["id_"] = lowstate[0].pop("mid")

        result = self.exec_lowstate()
        ret = next(result, {}).get("data", {}).get("return", {})

        pub_key = ret.get("pub", "")
        pub_key_file = tarfile.TarInfo("minion.pub")
        pub_key_file.size = len(pub_key)

        priv_key = ret.get("priv", "")
        priv_key_file = tarfile.TarInfo("minion.pem")
        priv_key_file.size = len(priv_key)

        fileobj = io.BytesIO()
        tarball = tarfile.open(fileobj=fileobj, mode="w")

        pub_key = pub_key.encode(__salt_system_encoding__)
        priv_key = priv_key.encode(__salt_system_encoding__)

        tarball.addfile(pub_key_file, io.BytesIO(pub_key))
        tarball.addfile(priv_key_file, io.BytesIO(priv_key))
        tarball.close()

        headers = cherrypy.response.headers
        headers["Content-Disposition"] = (
            'attachment; filename="saltkeys-{}.tar"'.format(lowstate[0]["id_"])
        )
        headers["Content-Type"] = "application/x-tar"
        headers["Content-Length"] = len(fileobj.getvalue())
        headers["Cache-Control"] = "no-cache"

        fileobj.seek(0)
        return fileobj


class Login(LowDataAdapter):
    """
    Log in to receive a session token

    :ref:`Authentication information <rest_cherrypy-auth>`.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.auth = salt.auth.Resolver(self.opts)

    def GET(self):
        """
        Present the login interface

        .. http:get:: /login

            An explanation of how to log in.

            :status 200: |200|
            :status 401: |401|
            :status 406: |406|

        **Example request:**

        .. code-block:: bash

            curl -i localhost:8000/login

        .. code-block:: text

            GET /login HTTP/1.1
            Host: localhost:8000
            Accept: text/html

        **Example response:**

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Type: text/html
        """
        cherrypy.response.headers["WWW-Authenticate"] = "Session"

        return {
            "status": cherrypy.response.status,
            "return": "Please log in",
        }

    def POST(self, **kwargs):
        """
        :ref:`Authenticate  <rest_cherrypy-auth>` against Salt's eauth system

        .. http:post:: /login

            :reqheader X-Auth-Token: |req_token|
            :reqheader Accept: |req_accept|
            :reqheader Content-Type: |req_ct|

            :form eauth: the eauth backend configured for the user
            :form username: username
            :form password: password

            :status 200: |200|
            :status 401: |401|
            :status 406: |406|

        **Example request:**

        .. code-block:: bash

            curl -si localhost:8000/login \\
                -c ~/cookies.txt \\
                -H "Accept: application/json" \\
                -H "Content-type: application/json" \\
                -d '{
                    "username": "saltuser",
                    "password": "saltuser",
                    "eauth": "auto"
                }'

        .. code-block:: text

            POST / HTTP/1.1
            Host: localhost:8000
            Content-Length: 42
            Content-Type: application/json
            Accept: application/json

            {"username": "saltuser", "password": "saltuser", "eauth": "auto"}


        **Example response:**

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Type: application/json
            Content-Length: 206
            X-Auth-Token: 6d1b722e
            Set-Cookie: session_id=6d1b722e; expires=Sat, 17 Nov 2012 03:23:52 GMT; Path=/

            {"return": {
                "token": "6d1b722e",
                "start": 1363805943.776223,
                "expire": 1363849143.776224,
                "user": "saltuser",
                "eauth": "pam",
                "perms": [
                    "grains.*",
                    "status.*",
                    "sys.*",
                    "test.*"
                ]
            }}
        """
        if not self.api._is_master_running():
            raise salt.exceptions.SaltDaemonNotRunning("Salt Master is not available.")

        # the urlencoded_processor will wrap this in a list
        if isinstance(cherrypy.serving.request.lowstate, list):
            creds = cherrypy.serving.request.lowstate[0]
        else:
            creds = cherrypy.serving.request.lowstate

        username = creds.get("username", None)
        # Validate against the whitelist.
        if not salt_api_acl_tool(username, cherrypy.request):
            raise cherrypy.HTTPError(401)

        # Mint token.
        token = self.auth.mk_token(creds)
        if "token" not in token:
            raise cherrypy.HTTPError(
                401, "Could not authenticate using provided credentials"
            )

        cherrypy.response.headers["X-Auth-Token"] = cherrypy.session.id
        cherrypy.session["token"] = token["token"]
        cherrypy.session["timeout"] = (token["expire"] - token["start"]) / 60

        # Grab eauth config for the current backend for the current user
        try:
            eauth = self.opts.get("external_auth", {}).get(token["eauth"], {})

            if token["eauth"] == "django" and "^model" in eauth:
                perms = token["auth_list"]
            elif token["eauth"] == "rest" and "auth_list" in token:
                perms = token["auth_list"]
            else:
                perms = salt.netapi.sum_permissions(token, eauth)
                perms = salt.netapi.sorted_permissions(perms)

            if not perms:
                logger.debug("Eauth permission list not found.")
        except Exception:  # pylint: disable=broad-except
            logger.debug(
                "Configuration for external_auth malformed for eauth %r, and user %r.",
                token.get("eauth"),
                token.get("name"),
                exc_info=True,
            )
            perms = None

        return {
            "return": [
                {
                    "token": cherrypy.session.id,
                    "expire": token["expire"],
                    "start": token["start"],
                    "user": token["name"],
                    "eauth": token["eauth"],
                    "perms": perms or {},
                }
            ]
        }


class Logout(LowDataAdapter):
    """
    Class to remove or invalidate sessions
    """

    _cp_config = dict(
        LowDataAdapter._cp_config,
        **{"tools.salt_auth.on": True, "tools.lowdata_fmt.on": False},
    )

    def POST(self):  # pylint: disable=arguments-differ
        """
        Destroy the currently active session and expire the session cookie
        """
        cherrypy.lib.sessions.expire()  # set client-side to expire
        cherrypy.session.regenerate()  # replace server-side with new

        return {"return": "Your token has been cleared"}


class Token(LowDataAdapter):
    """
    Generate a Salt token from eauth credentials

    Wraps functionality in the :py:mod:`auth Runner <salt.runners.auth>`.

    .. versionadded:: 2017.7.0
    """

    @cherrypy.config(**{"tools.sessions.on": False})
    def POST(self, **kwargs):
        r"""
        .. http:post:: /token

            Generate a Salt eauth token

            :status 200: |200|
            :status 400: |400|
            :status 401: |401|

        **Example request:**

        .. code-block:: bash

            curl -sSk https://localhost:8000/token \
                -H 'Content-type: application/json' \
                -d '{
                    "username": "saltdev",
                    "password": "saltdev",
                    "eauth": "auto"
                }'

        **Example response:**

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Type: application/json

            [{
                "start": 1494987445.528182,
                "token": "e72ca1655d05...",
                "expire": 1495030645.528183,
                "name": "saltdev",
                "eauth": "auto"
            }]
        """
        for creds in cherrypy.request.lowstate:
            try:
                creds.update(
                    {
                        "client": "runner",
                        "fun": "auth.mk_token",
                        "kwarg": {
                            "username": creds["username"],
                            "password": creds["password"],
                            "eauth": creds["eauth"],
                        },
                    }
                )
            except KeyError:
                raise cherrypy.HTTPError(
                    400, 'Require "username", "password", and "eauth" params'
                )

        return list(self.exec_lowstate())


class Run(LowDataAdapter):
    """
    Run commands bypassing the :ref:`normal session handling
    <rest_cherrypy-auth>`.

    salt-api does not enforce authorization, Salt's eauth system does that.
    Local/Runner/WheelClient all accept ``username``/``password``/``eauth``
    **or** ``token`` kwargs that are then checked by the eauth system. The
    session mechanism in ``rest_cherrypy`` simply pairs a session with a Salt
    eauth token and then passes the ``token`` kwarg in automatically.

    If you already have a Salt eauth token, perhaps generated by the
    :py:func:`mk_token <salt.runners.auth.mk_token>` function in the Auth
    Runner module, then there is no reason to use sessions.

    This endpoint accepts either a ``username``, ``password``, ``eauth`` trio,
    **or** a ``token`` kwarg and does not make use of sessions at all.
    """

    _cp_config = dict(LowDataAdapter._cp_config, **{"tools.sessions.on": False})

    def POST(self, **kwargs):
        """
        Run commands bypassing the :ref:`normal session handling
        <rest_cherrypy-auth>`.  Otherwise, this URL is identical to the
        :py:meth:`root URL (/) <LowDataAdapter.POST>`.

        .. http:post:: /run

            An array of lowstate data describing Salt commands must be sent in
            the request body.

            :status 200: |200|
            :status 400: |400|
            :status 401: |401|
            :status 406: |406|

        **Example request:**

        .. code-block:: bash

            curl -sS localhost:8000/run \\
                -H 'Accept: application/x-yaml' \\
                -H 'Content-type: application/json' \\
                -d '[{
                    "client": "local",
                    "tgt": "*",
                    "fun": "test.ping",
                    "username": "saltdev",
                    "password": "saltdev",
                    "eauth": "auto"
                }]'

        **Or** using a Salt Eauth token:

        .. code-block:: bash

            curl -sS localhost:8000/run \\
                -H 'Accept: application/x-yaml' \\
                -H 'Content-type: application/json' \\
                -d '[{
                    "client": "local",
                    "tgt": "*",
                    "fun": "test.ping",
                    "token": "<salt eauth token here>"
                }]'

        .. code-block:: text

            POST /run HTTP/1.1
            Host: localhost:8000
            Accept: application/x-yaml
            Content-Length: 75
            Content-Type: application/json

            [{"client": "local", "tgt": "*", "fun": "test.ping", "username": "saltdev", "password": "saltdev", "eauth": "auto"}]

        **Example response:**

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Length: 73
            Content-Type: application/x-yaml

            return:
            - ms-0: true
              ms-1: true
              ms-2: true
              ms-3: true
              ms-4: true

        The /run endpoint can also be used to issue commands using the salt-ssh
        subsystem.  When using salt-ssh, eauth credentials must also be
        supplied, and are subject to :ref:`eauth access-control lists <acl>`.

        All SSH client requests are synchronous.

        **Example SSH client request:**

        .. code-block:: bash

            curl -sS localhost:8000/run \\
                -H 'Accept: application/x-yaml' \\
                -d client='ssh' \\
                -d tgt='*' \\
                -d username='saltdev' \\
                -d password='saltdev' \\
                -d eauth='auto' \\
                -d fun='test.ping'

        .. code-block:: text

            POST /run HTTP/1.1
            Host: localhost:8000
            Accept: application/x-yaml
            Content-Length: 75
            Content-Type: application/x-www-form-urlencoded

        **Example SSH response:**

        .. code-block:: text

                return:
                - silver:
                    _stamp: '2020-09-08T23:04:28.912609'
                    fun: test.ping
                    fun_args: []
                    id: silver
                    jid: '20200908230427905565'
                    retcode: 0
                    return: true
        """
        return {
            "return": list(self.exec_lowstate()),
        }


class Events:
    """
    Expose the Salt event bus

    The event bus on the Salt master exposes a large variety of things, notably
    when executions are started on the master and also when minions ultimately
    return their results. This URL provides a real-time window into a running
    Salt infrastructure.

    .. seealso:: :ref:`events`

    """

    exposed = True

    _cp_config = dict(
        LowDataAdapter._cp_config,
        **{
            "response.stream": True,
            "tools.encode.encoding": "utf-8",
            # Auth handled manually below
            "tools.salt_auth.on": False,
            "tools.hypermedia_in.on": False,
            "tools.hypermedia_out.on": False,
        },
    )

    def __init__(self):
        self.opts = cherrypy.config["saltopts"]
        self.resolver = salt.auth.Resolver(self.opts)

    def _is_valid_token(self, auth_token):
        """
        Check if this is a valid salt-api token or valid Salt token

        salt-api tokens are regular session tokens that tie back to a real Salt
        token. Salt tokens are tokens generated by Salt's eauth system.

        :return bool: True if valid, False if not valid.
        """
        # Make sure that auth token is hex. If it's None, or something other
        # than hex, this will raise a ValueError.
        try:
            int(auth_token, 16)
        except (TypeError, ValueError):
            return False

        # First check if the given token is in our session table; if so it's a
        # salt-api token and we need to get the Salt token from there.
        orig_session, _ = cherrypy.session.cache.get(auth_token, ({}, None))
        # If it's not in the session table, assume it's a regular Salt token.
        salt_token = orig_session.get("token", auth_token)

        # The eauth system does not currently support perms for the event
        # stream, so we're just checking if the token exists not if the token
        # allows access.
        if salt_token:
            # We want to at least make sure that the token isn't expired yet.
            resolved_tkn = self.resolver.get_token(salt_token)
            if resolved_tkn and resolved_tkn.get("expire", 0) > time.time():
                return True

        return False

    def GET(self, token=None, salt_token=None):
        r"""
        An HTTP stream of the Salt master event bus

        This stream is formatted per the Server Sent Events (SSE) spec. Each
        event is formatted as JSON.

        .. http:get:: /events

            :status 200: |200|
            :status 401: |401|
            :status 406: |406|
            :query token: **optional** parameter containing the token
                ordinarily supplied via the X-Auth-Token header in order to
                allow cross-domain requests in browsers that do not include
                CORS support in the EventSource API. E.g.,
                ``curl -NsS localhost:8000/events?token=308650d``
            :query salt_token: **optional** parameter containing a raw Salt
                *eauth token* (not to be confused with the token returned from
                the /login URL). E.g.,
                ``curl -NsS localhost:8000/events?salt_token=30742765``

        **Example request:**

        .. code-block:: bash

            curl -NsS localhost:8000/events

        .. code-block:: text

            GET /events HTTP/1.1
            Host: localhost:8000

        **Example response:**

        Note, the ``tag`` field is not part of the spec. SSE compliant clients
        should ignore unknown fields. This addition allows non-compliant
        clients to only watch for certain tags without having to deserialze the
        JSON object each time.

        .. code-block:: text

            HTTP/1.1 200 OK
            Connection: keep-alive
            Cache-Control: no-cache
            Content-Type: text/event-stream;charset=utf-8

            retry: 400

            tag: salt/job/20130802115730568475/new
            data: {'tag': 'salt/job/20130802115730568475/new', 'data': {'minions': ['ms-4', 'ms-3', 'ms-2', 'ms-1', 'ms-0']}}

            tag: salt/job/20130802115730568475/ret/jerry
            data: {'tag': 'salt/job/20130802115730568475/ret/jerry', 'data': {'jid': '20130802115730568475', 'return': True, 'retcode': 0, 'success': True, 'cmd': '_return', 'fun': 'test.ping', 'id': 'ms-1'}}

        The event stream can be easily consumed via JavaScript:

        .. code-block:: javascript

            var source = new EventSource('/events');
            source.onopen = function() { console.info('Listening ...') };
            source.onerror = function(err) { console.error(err) };
            source.onmessage = function(message) {
                var saltEvent = JSON.parse(message.data);
                console.log(saltEvent.tag, saltEvent.data);
            };

        Note, the SSE stream is fast and completely asynchronous and Salt is
        very fast. If a job is created using a regular POST request, it is
        possible that the job return will be available on the SSE stream before
        the response for the POST request arrives. It is important to take that
        asynchronicity into account when designing an application. Below are
        some general guidelines.

        * Subscribe to the SSE stream _before_ creating any events.
        * Process SSE events directly as they arrive and don't wait for any
          other process to "complete" first (like an ajax request).
        * Keep a buffer of events if the event stream must be used for
          synchronous lookups.
        * Be cautious in writing Salt's event stream directly to the DOM. It is
          very busy and can quickly overwhelm the memory allocated to a
          browser tab.

        A full, working proof-of-concept JavaScript application is available
        :blob:`adjacent to this file <salt/netapi/rest_cherrypy/index.html>`.
        It can be viewed by pointing a browser at the ``/app`` endpoint in a
        running ``rest_cherrypy`` instance.

        Or using CORS:

        .. code-block:: javascript

            var source = new EventSource('/events?token=ecd589e4e01912cf3c4035afad73426dbb8dba75', {withCredentials: true});

        It is also possible to consume the stream via the shell.

        Records are separated by blank lines; the ``data:`` and ``tag:``
        prefixes will need to be removed manually before attempting to
        unserialize the JSON.

        curl's ``-N`` flag turns off input buffering which is required to
        process the stream incrementally.

        Here is a basic example of printing each event as it comes in:

        .. code-block:: bash

            curl -NsS localhost:8000/events |\
                    while IFS= read -r line ; do
                        echo $line
                    done

        Here is an example of using awk to filter events based on tag:

        .. code-block:: bash

            curl -NsS localhost:8000/events |\
                    awk '
                        BEGIN { RS=""; FS="\\n" }
                        $1 ~ /^tag: salt\/job\/[0-9]+\/new$/ { print $0 }
                    '
            tag: salt/job/20140112010149808995/new
            data: {"tag": "salt/job/20140112010149808995/new", "data": {"tgt_type": "glob", "jid": "20140112010149808995", "tgt": "jerry", "_stamp": "2014-01-12_01:01:49.809617", "user": "shouse", "arg": [], "fun": "test.ping", "minions": ["jerry"]}}
            tag: 20140112010149808995
            data: {"tag": "20140112010149808995", "data": {"fun_args": [], "jid": "20140112010149808995", "return": true, "retcode": 0, "success": true, "cmd": "_return", "_stamp": "2014-01-12_01:01:49.819316", "fun": "test.ping", "id": "jerry"}}
        """
        cookies = cherrypy.request.cookie
        auth_token = (
            token
            or salt_token
            or (cookies["session_id"].value if "session_id" in cookies else None)
        )

        if not self._is_valid_token(auth_token):
            raise cherrypy.HTTPError(401)

        # Release the session lock before starting the long-running response
        cherrypy.session.release_lock()

        cherrypy.response.headers["Content-Type"] = "text/event-stream"
        cherrypy.response.headers["Cache-Control"] = "no-cache"
        cherrypy.response.headers["Connection"] = "keep-alive"

        def listen():
            """
            An iterator to yield Salt events
            """
            with salt.utils.event.get_event(
                "master",
                sock_dir=self.opts["sock_dir"],
                opts=self.opts,
                listen=True,
            ) as event:
                stream = event.iter_events(full=True, auto_reconnect=True)

                yield "retry: 400\n"

                while True:
                    # make sure the token is still valid
                    if not self._is_valid_token(auth_token):
                        logger.debug("Token is no longer valid")
                        break

                    data = next(stream)
                    yield "tag: {}\n".format(data.get("tag", ""))
                    yield f"data: {salt.utils.json.dumps(data)}\n\n"

        return listen()


class WebsocketEndpoint:
    """
    Open a WebSocket connection to Salt's event bus

    The event bus on the Salt master exposes a large variety of things, notably
    when executions are started on the master and also when minions ultimately
    return their results. This URL provides a real-time window into a running
    Salt infrastructure. Uses websocket as the transport mechanism.

    .. seealso:: :ref:`events`
    """

    exposed = True

    _cp_config = dict(
        LowDataAdapter._cp_config,
        **{
            "response.stream": True,
            "tools.encode.encoding": "utf-8",
            # Auth handled manually below
            "tools.salt_auth.on": False,
            "tools.hypermedia_in.on": False,
            "tools.hypermedia_out.on": False,
            "tools.websocket.on": True,
            "tools.websocket.handler_cls": websockets.SynchronizingWebsocket,
        },
    )

    def __init__(self):
        self.opts = cherrypy.config["saltopts"]
        self.auth = salt.auth.LoadAuth(self.opts)

    def GET(self, token=None, **kwargs):
        """
        Return a websocket connection of Salt's event stream

        .. http:get:: /ws/(token)

        :query format_events: The event stream will undergo server-side
            formatting if the ``format_events`` URL parameter is included
            in the request. This can be useful to avoid formatting on the
            client-side:

            .. code-block:: bash

                curl -NsS <...snip...> localhost:8000/ws?format_events

        :reqheader X-Auth-Token: an authentication token from
            :py:class:`~Login`.

        :status 101: switching to the websockets protocol
        :status 401: |401|
        :status 406: |406|

        **Example request:** ::

            curl -NsSk \\
                -H 'X-Auth-Token: ffedf49d' \\
                -H 'Host: localhost:8000' \\
                -H 'Connection: Upgrade' \\
                -H 'Upgrade: websocket' \\
                -H 'Origin: https://localhost:8000' \\
                -H 'Sec-WebSocket-Version: 13' \\
                -H 'Sec-WebSocket-Key: '"$(echo -n $RANDOM | base64)" \\
                localhost:8000/ws

        .. code-block:: text

            GET /ws HTTP/1.1
            Connection: Upgrade
            Upgrade: websocket
            Host: localhost:8000
            Origin: https://localhost:8000
            Sec-WebSocket-Version: 13
            Sec-WebSocket-Key: s65VsgHigh7v/Jcf4nXHnA==
            X-Auth-Token: ffedf49d

        **Example response**:

        .. code-block:: text

            HTTP/1.1 101 Switching Protocols
            Upgrade: websocket
            Connection: Upgrade
            Sec-WebSocket-Accept: mWZjBV9FCglzn1rIKJAxrTFlnJE=
            Sec-WebSocket-Version: 13

        An authentication token **may optionally** be passed as part of the URL
        for browsers that cannot be configured to send the authentication
        header or cookie:

        .. code-block:: bash

            curl -NsS <...snip...> localhost:8000/ws/ffedf49d

        The event stream can be easily consumed via JavaScript:

        .. code-block:: javascript

            // Note, you must be authenticated!
            var source = new Websocket('ws://localhost:8000/ws/d0ce6c1a');
            source.onerror = function(e) { console.debug('error!', e); };
            source.onmessage = function(e) { console.debug(e.data); };

            source.send('websocket client ready')

            source.close();

        Or via Python, using the Python module `websocket-client
        <https://pypi.python.org/pypi/websocket-client/>`_ for example.

        .. code-block:: python

            # Note, you must be authenticated!

            from websocket import create_connection

            ws = create_connection('ws://localhost:8000/ws/d0ce6c1a')
            ws.send('websocket client ready')

            # Look at https://pypi.python.org/pypi/websocket-client/ for more
            # examples.
            while listening_to_events:
                print ws.recv()

            ws.close()

        Above examples show how to establish a websocket connection to Salt and
        activating real time updates from Salt's event stream by signaling
        ``websocket client ready``.
        """
        # Pulling the session token from an URL param is a workaround for
        # browsers not supporting CORS in the EventSource API.
        if token:
            orig_session, _ = cherrypy.session.cache.get(token, ({}, None))
            salt_token = orig_session.get("token")
        else:
            salt_token = cherrypy.session.get("token")

        # Manually verify the token
        if not salt_token or not self.auth.get_tok(salt_token):
            raise cherrypy.HTTPError(401)

        # Release the session lock before starting the long-running response
        cherrypy.session.release_lock()

        # A handler is the server side end of the websocket connection. Each
        # request spawns a new instance of this handler
        handler = cherrypy.request.ws_handler

        def event_stream(handler, pipe):
            """
            An iterator to return Salt events (and optionally format them)
            """
            # blocks until send is called on the parent end of this pipe.
            pipe.recv()

            with salt.utils.event.get_event(
                "master",
                sock_dir=self.opts["sock_dir"],
                opts=self.opts,
                listen=True,
            ) as event:
                stream = event.iter_events(full=True, auto_reconnect=True)
                SaltInfo = event_processor.SaltInfo(handler)

                def signal_handler(signal, frame):
                    os._exit(0)

                signal.signal(signal.SIGTERM, signal_handler)

                while True:
                    data = next(stream)
                    if data:
                        try:  # work around try to decode catch unicode errors
                            if "format_events" in kwargs:
                                SaltInfo.process(data, salt_token, self.opts)
                            else:
                                handler.send(
                                    f"data: {salt.utils.json.dumps(data)}\n\n",
                                    False,
                                )
                        except UnicodeDecodeError:
                            logger.error(
                                "Error: Salt event has non UTF-8 data:\n%s", data
                            )

        parent_pipe, child_pipe = Pipe()
        handler.pipe = parent_pipe
        handler.opts = self.opts
        # Process to handle asynchronous push to a client.
        # Each GET request causes a process to be kicked off.
        proc = Process(target=event_stream, args=(handler, child_pipe))
        proc.start()


class Webhook:
    """
    A generic web hook entry point that fires an event on Salt's event bus

    External services can POST data to this URL to trigger an event in Salt.
    For example, Amazon SNS, Jenkins-CI or Travis-CI, or GitHub web hooks.

    .. note:: Be mindful of security

        Salt's Reactor can run any code. A Reactor SLS that responds to a hook
        event is responsible for validating that the event came from a trusted
        source and contains valid data.

        **This is a generic interface and securing it is up to you!**

        This URL requires authentication however not all external services can
        be configured to authenticate. For this reason authentication can be
        selectively disabled for this URL. Follow best practices -- always use
        SSL, pass a secret key, configure the firewall to only allow traffic
        from a known source, etc.

    The event data is taken from the request body. The
    :mailheader:`Content-Type` header is respected for the payload.

    The event tag is prefixed with ``salt/netapi/hook`` and the URL path is
    appended to the end. For example, a ``POST`` request sent to
    ``/hook/mycompany/myapp/mydata`` will produce a Salt event with the tag
    ``salt/netapi/hook/mycompany/myapp/mydata``.

    The following is an example ``.travis.yml`` file to send notifications to
    Salt of successful test runs:

    .. code-block:: yaml

        language: python
        script: python -m unittest tests
        after_success:
            - |
                curl -sSk https://saltapi-url.example.com:8000/hook/travis/build/success \
                        -d branch="${TRAVIS_BRANCH}" \
                        -d commit="${TRAVIS_COMMIT}"

    .. seealso:: :ref:`events`, :ref:`reactor <reactor>`
    """

    exposed = True
    tag_base = ["salt", "netapi", "hook"]

    _cp_config = dict(
        LowDataAdapter._cp_config,
        **{
            # Don't do any lowdata processing on the POST data
            "tools.lowdata_fmt.on": True,
            # Auth can be overridden in __init__().
            "tools.salt_auth.on": True,
        },
    )

    def __init__(self):
        self.opts = cherrypy.config["saltopts"]
        self.event = salt.utils.event.get_event(
            "master",
            sock_dir=self.opts["sock_dir"],
            opts=self.opts,
            listen=False,
        )

        if cherrypy.config["apiopts"].get("webhook_disable_auth"):
            self._cp_config["tools.salt_auth.on"] = False

    def POST(self, *args, **kwargs):
        """
        Fire an event in Salt with a custom event tag and data

        .. http:post:: /hook

            :status 200: |200|
            :status 401: |401|
            :status 406: |406|
            :status 413: request body is too large

        **Example request:**

        .. code-block:: bash

            curl -sS localhost:8000/hook \\
                -H 'Content-type: application/json' \\
                -d '{"foo": "Foo!", "bar": "Bar!"}'

        .. code-block:: text

            POST /hook HTTP/1.1
            Host: localhost:8000
            Content-Length: 16
            Content-Type: application/json

            {"foo": "Foo!", "bar": "Bar!"}

        **Example response**:

        .. code-block:: text

            HTTP/1.1 200 OK
            Content-Length: 14
            Content-Type: application/json

            {"success": true}

        As a practical example, an internal continuous-integration build
        server could send an HTTP POST request to the URL
        ``https://localhost:8000/hook/mycompany/build/success`` which contains
        the result of a build and the SHA of the version that was built as
        JSON. That would then produce the following event in Salt that could be
        used to kick off a deployment via Salt's Reactor::

            Event fired at Fri Feb 14 17:40:11 2014
            *************************
            Tag: salt/netapi/hook/mycompany/build/success
            Data:
            {'_stamp': '2014-02-14_17:40:11.440996',
                'headers': {
                    'X-My-Secret-Key': 'F0fAgoQjIT@W',
                    'Content-Length': '37',
                    'Content-Type': 'application/json',
                    'Host': 'localhost:8000',
                    'Remote-Addr': '127.0.0.1'},
                'post': {'revision': 'aa22a3c4b2e7', 'result': True}}

        Salt's Reactor could listen for the event:

        .. code-block:: yaml

            reactor:
              - 'salt/netapi/hook/mycompany/build/*':
                - /srv/reactor/react_ci_builds.sls

        And finally deploy the new build:

        .. code-block:: jinja

            {% set secret_key = data.get('headers', {}).get('X-My-Secret-Key') %}
            {% set build = data.get('post', {}) %}

            {% if secret_key == 'F0fAgoQjIT@W' and build.result == True %}
            deploy_my_app:
              cmd.state.sls:
                - tgt: 'application*'
                - arg:
                  - myapp.deploy
                - kwarg:
                    pillar:
                      revision: {{ revision }}
            {% endif %}
        """
        tag = "/".join(itertools.chain(self.tag_base, args))
        data = cherrypy.serving.request.unserialized_data
        if not data:
            data = {}
        raw_body = getattr(cherrypy.serving.request, "raw_body", "")
        headers = dict(cherrypy.request.headers)

        ret = self.event.fire_event(
            {"body": raw_body, "post": data, "headers": headers}, tag
        )
        return {"success": ret}


class Stats:
    """
    Expose statistics on the running CherryPy server
    """

    exposed = True

    _cp_config = dict(LowDataAdapter._cp_config, **{"tools.salt_auth.on": True})

    def __init__(self):
        if cherrypy.config["apiopts"].get("stats_disable_auth"):
            self._cp_config["tools.salt_auth.on"] = False

    def GET(self):
        """
        Return a dump of statistics collected from the CherryPy server

        .. http:get:: /stats

            :reqheader X-Auth-Token: |req_token|
            :reqheader Accept: |req_accept|

            :resheader Content-Type: |res_ct|

            :status 200: |200|
            :status 401: |401|
            :status 406: |406|
        """
        if hasattr(logging, "statistics"):
            return cpstats.extrapolate_statistics(logging.statistics)

        return {}


class App:
    """
    Class to serve HTML5 apps
    """

    exposed = True

    def GET(self, *args):
        """
        Serve a single static file ignoring the remaining path

        This is useful in combination with a browser-based app using the HTML5
        history API.

        .. http:get:: /app

            :reqheader X-Auth-Token: |req_token|

            :status 200: |200|
            :status 401: |401|
        """
        apiopts = cherrypy.config["apiopts"]

        default_index = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "index.html")
        )

        return cherrypy.lib.static.serve_file(apiopts.get("app", default_index))


class API:
    """
    Collect configuration and URL map for building the CherryPy app
    """

    url_map = {
        "index": LowDataAdapter,
        "login": Login,
        "logout": Logout,
        "token": Token,
        "minions": Minions,
        "run": Run,
        "jobs": Jobs,
        "keys": Keys,
        "events": Events,
        "stats": Stats,
    }

    def _setattr_url_map(self):
        """
        Set an attribute on the local instance for each key/val in url_map

        CherryPy uses class attributes to resolve URLs.
        """
        if self.apiopts.get("enable_sessions", True) is False:
            url_blacklist = ["login", "logout", "minions", "jobs"]
        else:
            url_blacklist = []

        urls = (
            (url, cls) for url, cls in self.url_map.items() if url not in url_blacklist
        )

        for url, cls in urls:
            setattr(self, url, cls())

    def _update_url_map(self):
        """
        Assemble any dynamic or configurable URLs
        """
        if HAS_WEBSOCKETS:
            self.url_map.update({"ws": WebsocketEndpoint})

        # Allow the Webhook URL to be overridden from the conf.
        self.url_map.update(
            {self.apiopts.get("webhook_url", "hook").lstrip("/"): Webhook}
        )

        # Enable the single-page JS app URL.
        self.url_map.update({self.apiopts.get("app_path", "app").lstrip("/"): App})

    def __init__(self):
        self.opts = cherrypy.config["saltopts"]
        self.apiopts = cherrypy.config["apiopts"]

        self._update_url_map()
        self._setattr_url_map()

    def get_conf(self):
        """
        Combine the CherryPy configuration with the rest_cherrypy config values
        pulled from the master config and return the CherryPy configuration
        """
        conf = {
            "global": {
                "server.socket_host": self.apiopts.get("host", "0.0.0.0"),
                "server.socket_port": self.apiopts.get("port", 8000),
                "server.thread_pool": self.apiopts.get("thread_pool", 100),
                "server.socket_queue_size": self.apiopts.get("queue_size", 30),
                "max_request_body_size": self.apiopts.get(
                    "max_request_body_size", 1048576
                ),
                "debug": self.apiopts.get("debug", False),
                "log.access_file": self.apiopts.get("log_access_file", ""),
                "log.error_file": self.apiopts.get("log_error_file", ""),
            },
            "/": {
                "request.dispatch": cherrypy.dispatch.MethodDispatcher(),
                "tools.trailing_slash.on": True,
                "tools.gzip.on": True,
                "tools.html_override.on": True,
                "tools.cors_tool.on": True,
            },
        }

        if salt.utils.versions.version_cmp(cherrypy.__version__, "12.0.0") < 0:
            # CherryPy >= 12.0 no longer supports "timeout_monitor", only set
            # this config option when using an older version of CherryPy.
            # See Issue #44601 for more information.
            conf["global"]["engine.timeout_monitor.on"] = self.apiopts.get(
                "expire_responses", True
            )

        if cpstats and self.apiopts.get("collect_stats", False):
            conf["/"]["tools.cpstats.on"] = True

        if "favicon" in self.apiopts:
            conf["/favicon.ico"] = {
                "tools.staticfile.on": True,
                "tools.staticfile.filename": self.apiopts["favicon"],
            }

        if self.apiopts.get("debug", False) is False:
            conf["global"]["environment"] = "production"

        # Serve static media if the directory has been set in the configuration
        if "static" in self.apiopts:
            conf[self.apiopts.get("static_path", "/static")] = {
                "tools.staticdir.on": True,
                "tools.staticdir.dir": self.apiopts["static"],
            }

        # Add to global config
        cherrypy.config.update(conf["global"])

        return conf


def get_app(opts):
    """
    Returns a WSGI app and a configuration dictionary
    """
    apiopts = opts.get(__name__.rsplit(".", 2)[-2], {})  # rest_cherrypy opts

    # Add Salt and salt-api config options to the main CherryPy config dict
    cherrypy.config["saltopts"] = opts
    cherrypy.config["apiopts"] = apiopts

    root = API()  # cherrypy app
    cpyopts = root.get_conf()  # cherrypy app opts

    return root, apiopts, cpyopts
