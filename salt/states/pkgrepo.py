"""
Management of APT/DNF/YUM/Zypper package repos
==============================================

States for managing software package repositories on Linux distros. Supported
package managers are APT, DNF, YUM and Zypper. Here is some example SLS:

.. code-block:: yaml

    base:
      pkgrepo.managed:
        - humanname: CentOS-$releasever - Base
        - mirrorlist: http://mirrorlist.centos.org/?release=$releasever&arch=$basearch&repo=os
        - comments:
            - 'http://mirror.centos.org/centos/$releasever/os/$basearch/'
        - gpgcheck: 1
        - gpgkey: file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-6

.. code-block:: yaml

    base:
      pkgrepo.managed:
        - humanname: Logstash PPA
        - name: deb http://ppa.launchpad.net/wolfnet/logstash/ubuntu precise main
        - dist: precise
        - file: /etc/apt/sources.list.d/logstash.list
        - keyid: 28B04E4A
        - keyserver: keyserver.ubuntu.com
        - require_in:
          - pkg: logstash

      pkg.latest:
        - name: logstash
        - refresh: True

.. code-block:: yaml

    base:
      pkgrepo.managed:
        - humanname: deb-multimedia
        - name: deb http://www.deb-multimedia.org stable main
        - file: /etc/apt/sources.list.d/deb-multimedia.list
        - key_url: salt://deb-multimedia/files/marillat.pub

.. code-block:: yaml

    base:
      pkgrepo.managed:
        - humanname: Google Chrome
        - name: deb http://dl.google.com/linux/chrome/deb/ stable main
        - dist: stable
        - file: /etc/apt/sources.list.d/chrome-browser.list
        - require_in:
          - pkg: google-chrome-stable
        - gpgcheck: 1
        - key_url: https://dl-ssl.google.com/linux/linux_signing_key.pub

.. code-block:: yaml

    base:
      pkgrepo.managed:
        - ppa: wolfnet/logstash
      pkg.latest:
        - name: logstash
        - refresh: True

.. note::

    On Ubuntu systems, the ``python-software-properties`` package should be
    installed for better support of PPA repositories. To check if this package
    is installed, run ``dpkg -l python-software-properties``.

    On Ubuntu & Debian systems, the ``python-apt`` package is required to be
    installed. To check if this package is installed, run ``dpkg -l python-apt``.
    ``python-apt`` will need to be manually installed if it is not present.

.. code-block:: yaml

    hello-copr:
        pkgrepo.managed:
            - copr: mymindstorm/hello
        pkg.installed:
            - name: hello


apt-key deprecated
------------------
``apt-key`` is deprecated and will be last available in Debian 11 and
Ubuntu 22.04. The recommended way to manage repo keys going forward
is to download the keys into /etc/apt/keyrings and use ``signed-by``
in your repo file pointing to the key. This module was updated
in version 3005 to implement the recommended approach. You need to add
``- aptkey: False`` to your state and set ``signed-by`` in your repo
name, to use this recommended approach.  If the cli command ``apt-key``
is not available it will automatically set ``aptkey`` to False.


Using ``aptkey: False`` with ``key_url`` example:

.. code-block:: yaml

    deb [signed-by=/etc/apt/keyrings/salt-archive-keyring.gpg arch=amd64] https://packages.broadcom.com/artifactory/saltproject-deb/ bionic main:
      pkgrepo.managed:
        - file: /etc/apt/sources.list.d/salt.list
        - key_url: https://packages.broadcom.com/artifactory/api/security/keypair/SaltProjectKey/public
        - aptkey: False

Using ``aptkey: False`` with ``keyserver`` and ``keyid``:

.. code-block:: yaml

    deb [signed-by=/etc/apt/keyrings/salt-archive-keyring.gpg arch=amd64] https://packages.broadcom.com/artifactory/saltproject-deb/ bionic main:
      pkgrepo.managed:
        - file: /etc/apt/sources.list.d/salt.list
        - keyserver: keyserver.ubuntu.com
        - keyid: 0E08A149DE57BFBE
        - aptkey: False
"""

import sys

import salt.utils.data
import salt.utils.files
import salt.utils.pkg.deb
import salt.utils.pkg.rpm
import salt.utils.versions
from salt.exceptions import CommandExecutionError, SaltInvocationError
from salt.state import STATE_INTERNAL_KEYWORDS as _STATE_INTERNAL_KEYWORDS


def __virtual__():
    """
    Only load if modifying repos is available for this package type
    """
    return "pkg.mod_repo" in __salt__


def managed(name, ppa=None, copr=None, aptkey=True, **kwargs):
    """
    This state manages software package repositories. Currently, :mod:`yum
    <salt.modules.yumpkg>`, :mod:`apt <salt.modules.aptpkg>`, and :mod:`zypper
    <salt.modules.zypperpkg>` repositories are supported.

    **YUM/DNF/ZYPPER-BASED SYSTEMS**

    .. note::
        One of ``baseurl`` or ``mirrorlist`` below is required. Additionally,
        note that this state is not presently capable of managing more than one
        repo in a single repo file, so each instance of this state will manage
        a single repo file containing the configuration for a single repo.

    name
        This value will be used in two ways: Firstly, it will be the repo ID,
        as seen in the entry in square brackets (e.g. ``[foo]``) for a given
        repo. Secondly, it will be the name of the file as stored in
        /etc/yum.repos.d (e.g. ``/etc/yum.repos.d/foo.conf``).

    enabled : True
        Whether the repo is enabled or not. Can be specified as ``True``/``False`` or
        ``1``/``0``.

    disabled : False
        Included to reduce confusion due to APT's use of the ``disabled``
        argument. If this is passed for a YUM/DNF/Zypper-based distro, then the
        reverse will be passed as ``enabled``. For example passing
        ``disabled=True`` will assume ``enabled=False``.

    copr
        Fedora and RedHat based distributions only. Use community packages
        outside of the main package repository.

        .. versionadded:: 3002

    humanname
        This is used as the ``name`` value in the repo file in
        ``/etc/yum.repos.d/`` (or ``/etc/zypp/repos.d`` for SUSE distros).

    baseurl
        The URL to a yum repository

    mirrorlist
        A URL which points to a file containing a collection of baseurls

    comments
        Sometimes you want to supply additional information, but not as
        enabled configuration. Anything supplied for this list will be saved
        in the repo configuration with a comment marker (#) in front.

    gpgautoimport
        Only valid for Zypper package manager. If set to ``True``, automatically
        trust and import the new repository signing key. The key should be
        specified with ``gpgkey`` parameter. See details below.

    Additional configuration values seen in YUM/DNF/Zypper repo files, such as
    ``gpgkey`` or ``gpgcheck``, will be used directly as key-value pairs.
    For example:

    .. code-block:: yaml

        foo:
          pkgrepo.managed:
            - humanname: Personal repo for foo
            - baseurl: https://mydomain.tld/repo/foo/$releasever/$basearch
            - gpgkey: file:///etc/pki/rpm-gpg/foo-signing-key
            - gpgcheck: 1


    **APT-BASED SYSTEMS**

    ppa
        On Ubuntu, you can take advantage of Personal Package Archives on
        Launchpad simply by specifying the user and archive name. The keyid
        will be queried from launchpad and everything else is set
        automatically. You can override any of the below settings by simply
        setting them as you would normally. For example:

        .. code-block:: yaml

            logstash-ppa:
              pkgrepo.managed:
                - ppa: wolfnet/logstash

    ppa_auth
        For Ubuntu PPAs there can be private PPAs that require authentication
        to access. For these PPAs the username/password can be passed as an
        HTTP Basic style username/password combination.

        .. code-block:: yaml

            logstash-ppa:
              pkgrepo.managed:
                - ppa: wolfnet/logstash
                - ppa_auth: username:password

    name
        On apt-based systems this must be the complete entry as it would be
        seen in the ``sources.list`` file. This can have a limited subset of
        components (e.g. ``main``) which can be added/modified with the
        ``comps`` option.

        .. code-block:: yaml

            precise-repo:
              pkgrepo.managed:
                - name: deb http://us.archive.ubuntu.com/ubuntu precise main

        .. note::

            The above example is intended as a more readable way of configuring
            the SLS, it is equivalent to the following:

            .. code-block:: yaml

                'deb http://us.archive.ubuntu.com/ubuntu precise main':
                  pkgrepo.managed

    disabled : False
        Toggles whether or not the repo is used for resolving dependencies
        and/or installing packages.

    enabled : True
        Included to reduce confusion due to YUM/DNF/Zypper's use of the
        ``enabled`` argument. If this is passed for an APT-based distro, then
        the reverse will be passed as ``disabled``. For example, passing
        ``enabled=False`` will assume ``disabled=False``.

    architectures
        On apt-based systems, ``architectures`` can restrict the available
        architectures that the repository provides (e.g. only ``amd64``).
        ``architectures`` should be a comma-separated list.

    comps
        On apt-based systems, comps dictate the types of packages to be
        installed from the repository (e.g. ``main``, ``nonfree``, ...).  For
        purposes of this, ``comps`` should be a comma-separated list.

    file
        The filename for the ``*.list`` that the repository is configured in.
        It is important to include the full-path AND make sure it is in
        a directory that APT will look in when handling packages

    dist
        This dictates the release of the distro the packages should be built
        for.  (e.g. ``unstable``). This option is rarely needed.

    keyid
        The KeyID or a list of KeyIDs of the GPG key to install.
        This option also requires the ``keyserver`` option to be set.

    keyserver
        This is the name of the keyserver to retrieve GPG keys from. The
        ``keyid`` option must also be set for this option to work.

    key_url
        URL to retrieve a GPG key from. Allows the usage of
        ``https://`` as well as ``salt://``.  If ``allow_insecure_key`` is True,
        this also allows ``http://``.

        .. note::

            Use either ``keyid``/``keyserver`` or ``key_url``, but not both.

    key_text
        The string representation of the GPG key to install.

        .. versionadded:: 2018.3.0

        .. note::

            Use either ``keyid``/``keyserver``, ``key_url``, or ``key_text`` but
            not more than one method.

    consolidate : False
        If set to ``True``, this will consolidate all sources definitions to the
        ``sources.list`` file, cleanup the now unused files, consolidate components
        (e.g. ``main``) for the same URI, type, and architecture to a single line,
        and finally remove comments from the ``sources.list`` file.  The consolidation
        will run every time the state is processed. The option only needs to be
        set on one repo managed by Salt to take effect.

    clean_file : False
        If set to ``True``, empty the file before configuring the defined repository

        .. note::
            Use with care. This can be dangerous if multiple sources are
            configured in the same file.

        .. versionadded:: 2015.8.0

    refresh : True
        If set to ``False`` this will skip refreshing the apt package database
        on Debian based systems.

    refresh_db : True
        .. deprecated:: 2018.3.0
            Use ``refresh`` instead.

    require_in
        Set this to a list of :mod:`pkg.installed <salt.states.pkg.installed>` or
        :mod:`pkg.latest <salt.states.pkg.latest>` to trigger the
        running of ``apt-get update`` prior to attempting to install these
        packages. Setting a require in the pkg state will not work for this.

    aptkey:
        Use the binary apt-key. If the command ``apt-key`` is not found
        in the path, aptkey will be False, regardless of what is passed into
        this argument.


    allow_insecure_key : True
        Whether to allow an insecure (e.g. http vs. https) key_url.

        .. versionadded:: 3006.0
    """
    if not salt.utils.path.which("apt-key"):
        aptkey = False

    ret = {"name": name, "changes": {}, "result": None, "comment": ""}

    if "pkg.get_repo" not in __salt__:
        ret["result"] = False
        ret["comment"] = "Repo management not implemented on this platform"
        return ret

    if "key_url" in kwargs and ("keyid" in kwargs or "keyserver" in kwargs):
        ret["result"] = False
        ret["comment"] = (
            'You may not use both "keyid"/"keyserver" and "key_url" argument.'
        )

    if "key_text" in kwargs and ("keyid" in kwargs or "keyserver" in kwargs):
        ret["result"] = False
        ret["comment"] = (
            'You may not use both "keyid"/"keyserver" and "key_text" argument.'
        )
    if "key_text" in kwargs and ("key_url" in kwargs):
        ret["result"] = False
        ret["comment"] = 'You may not use both "key_url" and "key_text" argument.'

    if "repo" in kwargs:
        ret["result"] = False
        ret["comment"] = (
            "'repo' is not a supported argument for this "
            "state. The 'name' argument is probably what was "
            "intended."
        )
        return ret

    enabled = kwargs.pop("enabled", None)
    disabled = kwargs.pop("disabled", None)

    if enabled is not None and disabled is not None:
        ret["result"] = False
        ret["comment"] = "Only one of enabled/disabled is allowed"
        return ret
    elif enabled is None and disabled is None:
        # If neither argument was passed we assume the repo will be enabled
        enabled = True

    # To be changed in version 3008: default to False and still log a warning
    allow_insecure_key = kwargs.pop("allow_insecure_key", True)
    key_is_insecure = kwargs.get("key_url", "").strip().startswith("http:")
    if key_is_insecure:
        if allow_insecure_key:
            salt.utils.versions.warn_until(
                3008,
                "allow_insecure_key will default to False starting in salt 3008.",
            )
        else:
            ret["result"] = False
            ret["comment"] = (
                "Cannot have 'key_url' using http with 'allow_insecure_key' set to True"
            )
            return ret

    kwargs["name"] = repo = name

    if __grains__["os"] in ("Ubuntu", "Mint"):
        if ppa is not None:
            # overload the name/repo value for PPAs cleanly
            # this allows us to have one code-path for PPAs
            try:
                repo = ":".join(("ppa", ppa))
            except TypeError:
                repo = ":".join(("ppa", str(ppa)))

        kwargs["disabled"] = (
            not salt.utils.data.is_true(enabled)
            if enabled is not None
            else salt.utils.data.is_true(disabled)
        )

    elif __grains__["os_family"] in ("RedHat", "Suse"):
        if __grains__["os_family"] in "RedHat":
            if copr is not None:
                repo = ":".join(("copr", copr))
                kwargs["name"] = name

        if "humanname" in kwargs:
            kwargs["name"] = kwargs.pop("humanname")

        kwargs["enabled"] = (
            not salt.utils.data.is_true(disabled)
            if disabled is not None
            else salt.utils.data.is_true(enabled)
        )

    elif __grains__["os_family"] in ("NILinuxRT", "Poky"):
        # opkg is the pkg virtual
        kwargs["enabled"] = (
            not salt.utils.data.is_true(disabled)
            if disabled is not None
            else salt.utils.data.is_true(enabled)
        )

    for kwarg in _STATE_INTERNAL_KEYWORDS:
        kwargs.pop(kwarg, None)

    try:
        pre = __salt__["pkg.get_repo"](repo=repo, **kwargs)
    except CommandExecutionError as exc:
        ret["result"] = False
        ret["comment"] = f"Failed to examine repo '{name}': {exc}"
        return ret

    # This is because of how apt-sources works. This pushes distro logic
    # out of the state itself and into a module that it makes more sense
    # to use. Most package providers will simply return the data provided
    # it doesn't require any "specialized" data massaging.
    if __grains__.get("os_family") == "Debian":
        from salt.modules.aptpkg import _expand_repo_def

        os_name = __grains__["os"]
        os_codename = __grains__["oscodename"]

        sanitizedkwargs = _expand_repo_def(
            os_name=os_name, os_codename=os_codename, repo=repo, **kwargs
        )
    else:
        sanitizedkwargs = kwargs

    if pre:
        # 22412: Remove file attribute in case same repo is set up multiple times but with different files
        pre.pop("file", None)
        sanitizedkwargs.pop("file", None)
        for kwarg in sanitizedkwargs:
            if kwarg not in pre:
                if kwarg == "enabled":
                    # On a RedHat-based OS, 'enabled' is assumed to be true if
                    # not explicitly set, so we don't need to update the repo
                    # if it's desired to be enabled and the 'enabled' key is
                    # missing from the repo definition
                    if __grains__["os_family"] == "RedHat":
                        if not salt.utils.data.is_true(sanitizedkwargs[kwarg]):
                            break
                    else:
                        break
                else:
                    break
            elif kwarg in ("comps", "key_url"):
                if sorted(sanitizedkwargs[kwarg]) != sorted(pre[kwarg]):
                    break
            elif kwarg == "line" and __grains__["os_family"] == "Debian":
                if not sanitizedkwargs["disabled"]:
                    # split the line and sort everything after the URL
                    sanitizedsplit = sanitizedkwargs[kwarg].split()
                    sanitizedsplit[3:] = sorted(sanitizedsplit[3:])
                    reposplit, _, pre_comments = (
                        x.strip() for x in pre[kwarg].partition("#")
                    )
                    reposplit = reposplit.split()
                    reposplit[3:] = sorted(reposplit[3:])
                    if sanitizedsplit != reposplit:
                        break
                    if "comments" in kwargs:
                        post_comments = salt.utils.pkg.deb.combine_comments(
                            kwargs["comments"]
                        )
                        if pre_comments != post_comments:
                            break
            elif kwarg == "comments" and __grains__["os_family"] == "RedHat":
                precomments = salt.utils.pkg.rpm.combine_comments(pre[kwarg])
                kwargcomments = salt.utils.pkg.rpm.combine_comments(
                    sanitizedkwargs[kwarg]
                )
                if precomments != kwargcomments:
                    break
            elif kwarg == "architectures" and sanitizedkwargs[kwarg]:
                if set(sanitizedkwargs[kwarg]) != set(pre[kwarg]):
                    break
            else:
                if __grains__["os_family"] in ("RedHat", "Suse") and any(
                    isinstance(x, bool) for x in (sanitizedkwargs[kwarg], pre[kwarg])
                ):
                    # This check disambiguates 1/0 from True/False
                    if salt.utils.data.is_true(
                        sanitizedkwargs[kwarg]
                    ) != salt.utils.data.is_true(pre[kwarg]):
                        break
                else:
                    if str(sanitizedkwargs[kwarg]) != str(pre[kwarg]):
                        break
        else:
            ret["result"] = True
            ret["comment"] = f"Package repo '{name}' already configured"
            return ret

    if __opts__["test"]:
        ret["comment"] = (
            "Package repo '{}' would be configured. This may cause pkg "
            "states to behave differently than stated if this action is "
            "repeated without test=True, due to the differences in the "
            "configured repositories.".format(name)
        )
        if pre:
            for kwarg in sanitizedkwargs:
                if sanitizedkwargs.get(kwarg) != pre.get(kwarg):
                    ret["changes"][kwarg] = {
                        "new": sanitizedkwargs.get(kwarg),
                        "old": pre.get(kwarg),
                    }
        else:
            ret["changes"]["repo"] = name
        return ret

    # empty file before configure
    if kwargs.get("clean_file", False):
        with salt.utils.files.fopen(kwargs["file"], "w"):
            pass

    try:
        if __grains__["os_family"] == "Debian":
            __salt__["pkg.mod_repo"](repo, saltenv=__env__, aptkey=aptkey, **kwargs)
        else:
            __salt__["pkg.mod_repo"](repo, **kwargs)
    except Exception as exc:  # pylint: disable=broad-except
        # This is another way to pass information back from the mod_repo
        # function.
        ret["result"] = False
        ret["comment"] = f"Failed to configure repo '{name}': {exc}"
        return ret

    try:
        post = __salt__["pkg.get_repo"](repo=repo, **kwargs)
        if pre:
            for kwarg in sanitizedkwargs:
                if post.get(kwarg) != pre.get(kwarg):
                    ret["changes"][kwarg] = {
                        "new": post.get(kwarg),
                        "old": pre.get(kwarg),
                    }
        else:
            ret["changes"] = {"repo": repo}

        ret["result"] = True
        ret["comment"] = f"Configured package repo '{name}'"
    except Exception as exc:  # pylint: disable=broad-except
        ret["result"] = False
        ret["comment"] = f"Failed to confirm config of repo '{name}': {exc}"

    # Clear cache of available packages, if present, since changes to the
    # repositories may change the packages that are available.
    if ret["changes"]:
        sys.modules[__salt__["test.ping"].__module__].__context__.pop(
            "pkg._avail", None
        )

    return ret


def absent(name, **kwargs):
    """
    This function deletes the specified repo on the system, if it exists. It
    is essentially a wrapper around :mod:`pkg.del_repo <salt.modules.pkg.del_repo>`.

    name
        The name of the package repo, as it would be referred to when running
        the regular package manager commands.

    .. note::
        On apt-based systems this must be the complete source entry. For
        example, if you include ``[arch=amd64]``, and a repo matching the
        specified URI, dist, etc. exists _without_ an architecture, then no
        changes will be made and the state will report a ``True`` result.

    **FEDORA/REDHAT-SPECIFIC OPTIONS**

    copr
        Use community packages outside of the main package repository.

        .. versionadded:: 3002

        .. code-block:: yaml

            hello-copr:
                pkgrepo.absent:
                  - copr: mymindstorm/hello

    **UBUNTU-SPECIFIC OPTIONS**

    ppa
        On Ubuntu, you can take advantage of Personal Package Archives on
        Launchpad simply by specifying the user and archive name.

        .. code-block:: yaml

            logstash-ppa:
              pkgrepo.absent:
                - ppa: wolfnet/logstash

    ppa_auth
        For Ubuntu PPAs there can be private PPAs that require authentication
        to access. For these PPAs the username/password can be specified.  This
        is required for matching if the name format uses the ``ppa:`` specifier
        and is private (requires username/password to access, which is encoded
        in the URI).

        .. code-block:: yaml

            logstash-ppa:
              pkgrepo.absent:
                - ppa: wolfnet/logstash
                - ppa_auth: username:password

    keyid
        If passed, then the GPG key corresponding to the passed KeyID will also
        be removed.

    keyid_ppa : False
        If set to ``True``, the GPG key's ID will be looked up from
        ppa.launchpad.net and removed, and the ``keyid`` argument will be
        ignored.

        .. note::
            This option will be disregarded unless the ``ppa`` argument is
            present.
    """
    ret = {"name": name, "changes": {}, "result": None, "comment": ""}

    if "ppa" in kwargs and __grains__["os"] in ("Ubuntu", "Mint"):
        name = kwargs.pop("ppa")
        if not name.startswith("ppa:"):
            name = "ppa:" + name

    if "copr" in kwargs and __grains__["os_family"] in "RedHat":
        name = kwargs.pop("copr")
        if not name.startswith("copr:"):
            name = "copr:" + name

    remove_key = any(kwargs.get(x) is not None for x in ("keyid", "keyid_ppa"))
    if remove_key and "pkg.del_repo_key" not in __salt__:
        ret["result"] = False
        ret["comment"] = "Repo key management is not implemented for this platform"
        return ret

    if __grains__["os_family"] == "Debian":
        stripname = salt.utils.pkg.deb.strip_uri(name)
    else:
        stripname = name

    try:
        repo = __salt__["pkg.get_repo"](stripname, **kwargs)
    except CommandExecutionError as exc:
        ret["result"] = False
        ret["comment"] = f"Failed to configure repo '{name}': {exc}"
        return ret

    if repo and (
        __grains__["os_family"].lower() == "debian"
        or __opts__.get("providers", {}).get("pkg") == "aptpkg"
    ):
        # On Debian/Ubuntu, pkg.get_repo will return a match for the repo
        # even if the architectures do not match. However, changing get_repo
        # breaks idempotency for pkgrepo.managed states. So, compare the
        # architectures of the matched repo to the architectures specified in
        # the repo string passed to this state. If the architectures do not
        # match, then invalidate the match by setting repo to an empty dict.
        from salt.modules.aptpkg import _split_repo_str

        if set(_split_repo_str(stripname)["architectures"]) != set(
            repo["architectures"]
        ):
            repo = {}

    if not repo:
        ret["comment"] = f"Package repo {name} is absent"
        ret["result"] = True
        return ret

    if __opts__["test"]:
        ret["comment"] = (
            "Package repo '{}' will be removed. This may "
            "cause pkg states to behave differently than stated "
            "if this action is repeated without test=True, due "
            "to the differences in the configured repositories.".format(name)
        )
        return ret

    try:
        __salt__["pkg.del_repo"](repo=stripname, **kwargs)
    except (CommandExecutionError, SaltInvocationError) as exc:
        ret["result"] = False
        ret["comment"] = exc.strerror
        return ret

    repos = __salt__["pkg.list_repos"]()
    if stripname not in repos:
        ret["changes"]["repo"] = name
        ret["comment"] = f"Removed repo {name}"

        if not remove_key:
            ret["result"] = True
        else:
            try:
                removed_keyid = __salt__["pkg.del_repo_key"](stripname, **kwargs)
            except (CommandExecutionError, SaltInvocationError) as exc:
                ret["result"] = False
                ret["comment"] += f", but failed to remove key: {exc}"
            else:
                ret["result"] = True
                ret["changes"]["keyid"] = removed_keyid
                ret["comment"] += f", and keyid {removed_keyid}"
    else:
        ret["result"] = False
        ret["comment"] = f"Failed to remove repo {name}"

    return ret
