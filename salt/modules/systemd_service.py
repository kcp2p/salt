"""
Provides the service module for systemd

.. versionadded:: 0.10.0

.. important::
    If you feel that Salt should be using this module to manage services on a
    minion, and it is using a different module (or gives an error similar to
    *'service.start' is not available*), see :ref:`here
    <module-provider-override>`.

.. important::
    This is an implementation of virtual 'service' module. As such, you must
    call it under the name 'service' and NOT 'systemd'. You can see that also
    in the examples below.
"""

import errno
import fnmatch
import glob
import logging
import os
import re
import shlex

import salt.utils.files
import salt.utils.itertools
import salt.utils.path
import salt.utils.stringutils
import salt.utils.systemd
from salt.exceptions import CommandExecutionError

log = logging.getLogger(__name__)

__func_alias__ = {
    "reload_": "reload",
    "unmask_": "unmask",
}

SYSTEM_CONFIG_PATHS = ("/lib/systemd/system", "/usr/lib/systemd/system")
LOCAL_CONFIG_PATH = "/etc/systemd/system"
INITSCRIPT_PATH = "/etc/init.d"
VALID_UNIT_TYPES = (
    "service",
    "socket",
    "device",
    "mount",
    "automount",
    "swap",
    "target",
    "path",
    "timer",
)

# Define the module's virtual name
__virtualname__ = "service"


def __virtual__():
    """
    Only work on systems that have been booted with systemd
    """
    is_linux = __grains__.get("kernel") == "Linux"
    is_booted = salt.utils.systemd.booted(__context__)
    is_offline = salt.utils.systemd.offline(__context__)
    if is_linux and (is_booted or is_offline):
        return __virtualname__
    return (
        False,
        "The systemd execution module failed to load: only available on Linux "
        "systems which have been booted with systemd.",
    )


def _root(path, root):
    """
    Relocate an absolute path to a new root directory.
    """
    if root:
        return os.path.join(root, os.path.relpath(path, os.path.sep))
    else:
        return path


def _canonical_unit_name(name):
    """
    Build a canonical unit name treating unit names without one
    of the valid suffixes as a service.
    """
    if not isinstance(name, str):
        name = str(name)
    if any(name.endswith(suffix) for suffix in VALID_UNIT_TYPES):
        return name
    return "%s.service" % name


def _check_available(name):
    """
    Returns boolean telling whether or not the named service is available
    """
    if offline():
        raise CommandExecutionError(
            "Cannot run in offline mode. Failed to get information on unit '%s'" % name
        )

    _status = _systemctl_status(name)
    sd_version = salt.utils.systemd.version(__context__)
    if sd_version is not None and sd_version >= 231:
        # systemd 231 changed the output of "systemctl status" for unknown
        # services, and also made it return an exit status of 4. If we are on
        # a new enough version, check the retcode, otherwise fall back to
        # parsing the "systemctl status" output.
        # See: https://github.com/systemd/systemd/pull/3385
        # Also: https://github.com/systemd/systemd/commit/3dced37
        return 0 <= _status["retcode"] < 4

    out = _status["stdout"].lower()
    if "could not be found" in out:
        # Catch cases where the systemd version is < 231 but the return code
        # and output changes have been backported (e.g. RHEL 7.3).
        return False

    for line in salt.utils.itertools.split(out, "\n"):
        match = re.match(r"\s+loaded:\s+(\S+)", line)
        if match:
            ret = match.group(1) != "not-found"
            break
    else:
        raise CommandExecutionError("Failed to get information on unit '%s'" % name)
    return ret


def _check_for_unit_changes(name):
    """
    Check for modified/updated unit files, and run a daemon-reload if any are
    found.
    """
    if _untracked_custom_unit_found(name) or _unit_file_changed(name):
        systemctl_reload()


def _check_unmask(name, unmask, unmask_runtime, root=None):
    """
    Common code for conditionally removing masks before making changes to a
    service's state.
    """
    if unmask:
        unmask_(name, runtime=False, root=root)
    if unmask_runtime:
        unmask_(name, runtime=True, root=root)


def _default_runlevel():
    """
    Try to figure out the default runlevel.  It is kept in
    /etc/init/rc-sysinit.conf, but can be overridden with entries
    in /etc/inittab, or via the kernel command-line at boot
    """
    # Try to get the "main" default.  If this fails, throw up our
    # hands and just guess "2", because things are horribly broken
    try:
        with salt.utils.files.fopen("/etc/init/rc-sysinit.conf") as fp_:
            for line in fp_:
                line = salt.utils.stringutils.to_unicode(line)
                if line.startswith("env DEFAULT_RUNLEVEL"):
                    runlevel = line.split("=")[-1].strip()
    except Exception:  # pylint: disable=broad-except
        return "2"

    # Look for an optional "legacy" override in /etc/inittab
    try:
        with salt.utils.files.fopen("/etc/inittab") as fp_:
            for line in fp_:
                line = salt.utils.stringutils.to_unicode(line)
                if not line.startswith("#") and "initdefault" in line:
                    runlevel = line.split(":")[1]
    except Exception:  # pylint: disable=broad-except
        pass

    # The default runlevel can also be set via the kernel command-line.
    try:
        valid_strings = {"0", "1", "2", "3", "4", "5", "6", "s", "S", "-s", "single"}
        with salt.utils.files.fopen("/proc/cmdline") as fp_:
            for line in fp_:
                line = salt.utils.stringutils.to_unicode(line)
                for arg in line.strip().split():
                    if arg in valid_strings:
                        runlevel = arg
                        break
    except Exception:  # pylint: disable=broad-except
        pass

    return runlevel


def _get_systemd_services(root):
    """
    Use os.listdir() to get all the unit files
    """
    ret = set()
    for path in SYSTEM_CONFIG_PATHS + (LOCAL_CONFIG_PATH,):
        # Make sure user has access to the path, and if the path is a
        # link it's likely that another entry in SYSTEM_CONFIG_PATHS
        # or LOCAL_CONFIG_PATH points to it, so we can ignore it.
        path = _root(path, root)
        if os.access(path, os.R_OK) and not os.path.islink(path):
            for fullname in os.listdir(path):
                try:
                    unit_name, unit_type = fullname.rsplit(".", 1)
                except ValueError:
                    continue
                if unit_type in VALID_UNIT_TYPES:
                    ret.add(unit_name if unit_type == "service" else fullname)
    return ret


def _get_sysv_services(root, systemd_services=None):
    """
    Use os.listdir() and os.access() to get all the initscripts
    """
    initscript_path = _root(INITSCRIPT_PATH, root)
    try:
        sysv_services = os.listdir(initscript_path)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            pass
        elif exc.errno == errno.EACCES:
            log.error(
                "Unable to check sysvinit scripts, permission denied to %s",
                initscript_path,
            )
        else:
            log.error(
                "Error %d encountered trying to check sysvinit scripts: %s",
                exc.errno,
                exc.strerror,
            )
        return []

    if systemd_services is None:
        systemd_services = _get_systemd_services(root)

    ret = []
    for sysv_service in sysv_services:
        if os.access(os.path.join(initscript_path, sysv_service), os.X_OK):
            if sysv_service in systemd_services:
                log.debug(
                    "sysvinit script '%s' found, but systemd unit "
                    "'%s.service' already exists",
                    sysv_service,
                    sysv_service,
                )
                continue
            ret.append(sysv_service)
    return ret


def _get_service_exec():
    """
    Returns the path to the sysv service manager (either update-rc.d or
    chkconfig)
    """
    contextkey = "systemd._get_service_exec"
    if contextkey not in __context__:
        executables = ("update-rc.d", "chkconfig")
        for executable in executables:
            service_exec = salt.utils.path.which(executable)
            if service_exec is not None:
                break
        else:
            raise CommandExecutionError(
                "Unable to find sysv service manager (tried {})".format(
                    ", ".join(executables)
                )
            )
        __context__[contextkey] = service_exec
    return __context__[contextkey]


def _runlevel():
    """
    Return the current runlevel
    """
    contextkey = "systemd._runlevel"
    if contextkey in __context__:
        return __context__[contextkey]
    out = __salt__["cmd.run"](
        salt.utils.path.which("runlevel"), python_shell=False, ignore_retcode=True
    )
    try:
        ret = out.split()[1]
    except IndexError:
        # The runlevel is unknown, return the default
        ret = _default_runlevel()
    __context__[contextkey] = ret
    return ret


def _strip_scope(msg):
    """
    Strip unnecessary message about running the command with --scope from
    stderr so that we can raise an exception with the remaining stderr text.
    """
    ret = []
    for line in msg.splitlines():
        if not line.endswith(".scope"):
            ret.append(line)
    return "\n".join(ret).strip()


def _systemctl_cmd(action, name=None, systemd_scope=False, no_block=False, root=None):
    """
    Build a systemctl command line. Treat unit names without one
    of the valid suffixes as a service.
    """
    ret = []
    if (
        systemd_scope
        and salt.utils.systemd.has_scope(__context__)
        and __salt__["config.get"]("systemd.scope", True)
    ):
        ret.extend([salt.utils.path.which("systemd-run"), "--scope"])
    ret.append(salt.utils.path.which("systemctl"))
    if no_block:
        ret.append("--no-block")
    if root:
        ret.extend(["--root", root])
    if isinstance(action, str):
        action = shlex.split(action)
    ret.extend(action)
    if name is not None:
        ret.append(_canonical_unit_name(name))
    if "status" in ret:
        ret.extend(["-n", "0"])
    return ret


def _systemctl_status(name):
    """
    Helper function to run 'systemctl status'.
    """
    return __salt__["cmd.run_all"](
        _systemctl_cmd("status", name),
        python_shell=False,
        redirect_stderr=True,
        ignore_retcode=True,
    )


def _sysv_enabled(name, root):
    """
    A System-V style service is assumed disabled if the "startup" symlink
    (starts with "S") to its script is found in /etc/init.d in the current
    runlevel.
    """
    # Find exact match (disambiguate matches like "S01anacron" for cron)
    rc = _root(f"/etc/rc{_runlevel()}.d/S*{name}", root)
    for match in glob.glob(rc):
        if re.match(r"S\d{,2}%s" % name, os.path.basename(match)):
            return True
    return False


def _untracked_custom_unit_found(name, root=None):
    """
    If the passed service name is not available, but a unit file exist in
    /etc/systemd/system, return True. Otherwise, return False.
    """
    system = _root("/etc/systemd/system", root)
    unit_path = os.path.join(system, _canonical_unit_name(name))
    return os.access(unit_path, os.R_OK) and not _check_available(name)


def _unit_file_changed(name):
    """
    Returns True if systemctl reports that the unit file has changed, otherwise
    returns False.
    """
    status = _systemctl_status(name)["stdout"].lower()
    return "'systemctl daemon-reload'" in status


def systemctl_reload():
    """
    .. versionadded:: 0.15.0

    Reloads systemctl, an action needed whenever unit files are updated.

    CLI Example:

    .. code-block:: bash

        salt '*' service.systemctl_reload
    """
    out = __salt__["cmd.run_all"](
        _systemctl_cmd("--system daemon-reload"),
        python_shell=False,
        redirect_stderr=True,
    )
    if out["retcode"] != 0:
        raise CommandExecutionError(
            "Problem performing systemctl daemon-reload: %s" % out["stdout"]
        )
    return True


def get_running():
    """
    Return a list of all running services, so far as systemd is concerned

    CLI Example:

    .. code-block:: bash

        salt '*' service.get_running
    """
    ret = set()
    # Get running systemd units
    out = __salt__["cmd.run"](
        _systemctl_cmd("--full --no-legend --no-pager"),
        python_shell=False,
        ignore_retcode=True,
    )
    for line in salt.utils.itertools.split(out, "\n"):
        try:
            comps = line.strip().split()
            fullname = comps[0]
            if len(comps) > 3:
                active_state = comps[3]
        except ValueError as exc:
            log.error(exc)
            continue
        else:
            if active_state != "running":
                continue
        try:
            unit_name, unit_type = fullname.rsplit(".", 1)
        except ValueError:
            continue
        if unit_type in VALID_UNIT_TYPES:
            ret.add(unit_name if unit_type == "service" else fullname)

    return sorted(ret)


def get_enabled(root=None):
    """
    Return a list of all enabled services

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Example:

    .. code-block:: bash

        salt '*' service.get_enabled
    """
    ret = set()
    # Get enabled systemd units. Can't use --state=enabled here because it's
    # not present until systemd 216.
    out = __salt__["cmd.run"](
        _systemctl_cmd("--full --no-legend --no-pager list-unit-files", root=root),
        python_shell=False,
        ignore_retcode=True,
    )
    for line in salt.utils.itertools.split(out, "\n"):
        try:
            fullname, unit_state = line.strip().split()[:2]
        except ValueError:
            continue
        else:
            # Arch Linux adds a third column, which we want to ignore
            if unit_state.split()[0] != "enabled":
                continue
        try:
            unit_name, unit_type = fullname.rsplit(".", 1)
        except ValueError:
            continue
        if unit_type in VALID_UNIT_TYPES:
            ret.add(unit_name if unit_type == "service" else fullname)

    # Add in any sysvinit services that are enabled
    ret.update({x for x in _get_sysv_services(root) if _sysv_enabled(x, root)})
    return sorted(ret)


def get_disabled(root=None):
    """
    Return a list of all disabled services

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Example:

    .. code-block:: bash

        salt '*' service.get_disabled
    """
    ret = set()
    # Get disabled systemd units. Can't use --state=disabled here because it's
    # not present until systemd 216.
    out = __salt__["cmd.run"](
        _systemctl_cmd("--full --no-legend --no-pager list-unit-files", root=root),
        python_shell=False,
        ignore_retcode=True,
    )
    for line in salt.utils.itertools.split(out, "\n"):
        try:
            fullname, unit_state = line.strip().split()[:2]
        except ValueError:
            continue
        else:
            # Arch Linux adds a third column, which we want to ignore
            if unit_state.split()[0] != "disabled":
                continue
        try:
            unit_name, unit_type = fullname.rsplit(".", 1)
        except ValueError:
            continue
        if unit_type in VALID_UNIT_TYPES:
            ret.add(unit_name if unit_type == "service" else fullname)

    # Add in any sysvinit services that are disabled
    ret.update({x for x in _get_sysv_services(root) if not _sysv_enabled(x, root)})
    return sorted(ret)


def get_static(root=None):
    """
    .. versionadded:: 2015.8.5

    Return a list of all static services

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Example:

    .. code-block:: bash

        salt '*' service.get_static
    """
    ret = set()
    # Get static systemd units. Can't use --state=static here because it's
    # not present until systemd 216.
    out = __salt__["cmd.run"](
        _systemctl_cmd("--full --no-legend --no-pager list-unit-files", root=root),
        python_shell=False,
        ignore_retcode=True,
    )
    for line in salt.utils.itertools.split(out, "\n"):
        try:
            fullname, unit_state = line.strip().split()[:2]
        except ValueError:
            continue
        else:
            if unit_state != "static":
                continue
        try:
            unit_name, unit_type = fullname.rsplit(".", 1)
        except ValueError:
            continue
        if unit_type in VALID_UNIT_TYPES:
            ret.add(unit_name if unit_type == "service" else fullname)

    # sysvinit services cannot be static
    return sorted(ret)


def get_all(root=None):
    """
    Return a list of all available services

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Example:

    .. code-block:: bash

        salt '*' service.get_all
    """
    ret = _get_systemd_services(root)
    ret.update(set(_get_sysv_services(root, systemd_services=ret)))
    return sorted(ret)


def available(name):
    """
    .. versionadded:: 0.10.4

    Check that the given service is available taking into account template
    units.

    CLI Example:

    .. code-block:: bash

        salt '*' service.available sshd
    """
    _check_for_unit_changes(name)
    return _check_available(name)


def missing(name):
    """
    .. versionadded:: 2014.1.0

    The inverse of :py:func:`service.available
    <salt.modules.systemd.available>`. Returns ``True`` if the specified
    service is not available, otherwise returns ``False``.

    CLI Example:

    .. code-block:: bash

        salt '*' service.missing sshd
    """
    return not available(name)


def unmask_(name, runtime=False, root=None):
    """
    .. versionadded:: 2015.5.0
    .. versionchanged:: 2015.8.12,2016.3.3,2016.11.0
        On minions running systemd>=205, `systemd-run(1)`_ is now used to
        isolate commands run by this function from the ``salt-minion`` daemon's
        control group. This is done to avoid a race condition in cases where
        the ``salt-minion`` service is restarted while a service is being
        modified. If desired, usage of `systemd-run(1)`_ can be suppressed by
        setting a :mod:`config option <salt.modules.config.get>` called
        ``systemd.scope``, with a value of ``False`` (no quotes).

    .. _`systemd-run(1)`: https://www.freedesktop.org/software/systemd/man/systemd-run.html

    Unmask the specified service with systemd

    runtime : False
        Set to ``True`` to unmask this service only until the next reboot

        .. versionadded:: 2017.7.0
            In previous versions, this function would remove whichever mask was
            identified by running ``systemctl is-enabled`` on the service.
            However, since it is possible to both have both indefinite and
            runtime masks on a service simultaneously, this function now
            removes a runtime mask only when this argument is set to ``True``,
            and otherwise removes an indefinite mask.

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Example:

    .. code-block:: bash

        salt '*' service.unmask foo
        salt '*' service.unmask foo runtime=True
    """
    _check_for_unit_changes(name)
    if not masked(name, runtime, root=root):
        log.debug("Service '%s' is not %smasked", name, "runtime-" if runtime else "")
        return True

    cmd = "unmask --runtime" if runtime else "unmask"
    out = __salt__["cmd.run_all"](
        _systemctl_cmd(cmd, name, systemd_scope=True, root=root),
        python_shell=False,
        redirect_stderr=True,
    )

    if out["retcode"] != 0:
        raise CommandExecutionError("Failed to unmask service '%s'" % name)

    return True


def mask(name, runtime=False, root=None):
    """
    .. versionadded:: 2015.5.0
    .. versionchanged:: 2015.8.12,2016.3.3,2016.11.0
        On minions running systemd>=205, `systemd-run(1)`_ is now used to
        isolate commands run by this function from the ``salt-minion`` daemon's
        control group. This is done to avoid a race condition in cases where
        the ``salt-minion`` service is restarted while a service is being
        modified. If desired, usage of `systemd-run(1)`_ can be suppressed by
        setting a :mod:`config option <salt.modules.config.get>` called
        ``systemd.scope``, with a value of ``False`` (no quotes).

    .. _`systemd-run(1)`: https://www.freedesktop.org/software/systemd/man/systemd-run.html

    Mask the specified service with systemd

    runtime : False
        Set to ``True`` to mask this service only until the next reboot

        .. versionadded:: 2015.8.5

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Example:

    .. code-block:: bash

        salt '*' service.mask foo
        salt '*' service.mask foo runtime=True
    """
    _check_for_unit_changes(name)

    cmd = "mask --runtime" if runtime else "mask"
    out = __salt__["cmd.run_all"](
        _systemctl_cmd(cmd, name, systemd_scope=True, root=root),
        python_shell=False,
        redirect_stderr=True,
    )

    if out["retcode"] != 0:
        raise CommandExecutionError(
            "Failed to mask service '%s'" % name, info=out["stdout"]
        )

    return True


def masked(name, runtime=False, root=None):
    """
    .. versionadded:: 2015.8.0
    .. versionchanged:: 2015.8.5
        The return data for this function has changed. If the service is
        masked, the return value will now be the output of the ``systemctl
        is-enabled`` command (so that a persistent mask can be distinguished
        from a runtime mask). If the service is not masked, then ``False`` will
        be returned.
    .. versionchanged:: 2017.7.0
        This function now returns a boolean telling the user whether a mask
        specified by the new ``runtime`` argument is set. If ``runtime`` is
        ``False``, this function will return ``True`` if an indefinite mask is
        set for the named service (otherwise ``False`` will be returned). If
        ``runtime`` is ``False``, this function will return ``True`` if a
        runtime mask is set, otherwise ``False``.

    Check whether or not a service is masked

    runtime : False
        Set to ``True`` to check for a runtime mask

        .. versionadded:: 2017.7.0
            In previous versions, this function would simply return the output
            of ``systemctl is-enabled`` when the service was found to be
            masked. However, since it is possible to both have both indefinite
            and runtime masks on a service simultaneously, this function now
            only checks for runtime masks if this argument is set to ``True``.
            Otherwise, it will check for an indefinite mask.

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Examples:

    .. code-block:: bash

        salt '*' service.masked foo
        salt '*' service.masked foo runtime=True
    """
    _check_for_unit_changes(name)
    root_dir = _root("/run" if runtime else "/etc", root)
    link_path = os.path.join(root_dir, "systemd", "system", _canonical_unit_name(name))
    try:
        return os.readlink(link_path) == "/dev/null"
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            log.trace(
                "Path %s does not exist. This is normal if service '%s' is "
                "not masked or does not exist.",
                link_path,
                name,
            )
        elif exc.errno == errno.EINVAL:
            log.error(
                "Failed to check mask status for service %s. Path %s is a "
                "file, not a symlink. This could be caused by changes in "
                "systemd and is probably a bug in Salt. Please report this "
                "to the developers.",
                name,
                link_path,
            )
        return False


def start(name, no_block=False, unmask=False, unmask_runtime=False):
    """
    .. versionchanged:: 2015.8.12,2016.3.3,2016.11.0
        On minions running systemd>=205, `systemd-run(1)`_ is now used to
        isolate commands run by this function from the ``salt-minion`` daemon's
        control group. This is done to avoid a race condition in cases where
        the ``salt-minion`` service is restarted while a service is being
        modified. If desired, usage of `systemd-run(1)`_ can be suppressed by
        setting a :mod:`config option <salt.modules.config.get>` called
        ``systemd.scope``, with a value of ``False`` (no quotes).

    .. _`systemd-run(1)`: https://www.freedesktop.org/software/systemd/man/systemd-run.html

    Start the specified service with systemd

    no_block : False
        Set to ``True`` to start the service using ``--no-block``.

        .. versionadded:: 2017.7.0

    unmask : False
        Set to ``True`` to remove an indefinite mask before attempting to start
        the service.

        .. versionadded:: 2017.7.0
            In previous releases, Salt would simply unmask a service before
            starting. This behavior is no longer the default.

    unmask_runtime : False
        Set to ``True`` to remove a runtime mask before attempting to start the
        service.

        .. versionadded:: 2017.7.0
            In previous releases, Salt would simply unmask a service before
            starting. This behavior is no longer the default.

    CLI Example:

    .. code-block:: bash

        salt '*' service.start <service name>
    """
    _check_for_unit_changes(name)
    _check_unmask(name, unmask, unmask_runtime)
    ret = __salt__["cmd.run_all"](
        _systemctl_cmd("start", name, systemd_scope=True, no_block=no_block),
        python_shell=False,
    )

    if ret["retcode"] != 0:
        # Instead of returning a bool, raise an exception so that we can
        # include the error message in the return data. This helps give more
        # information to the user in instances where the service is masked.
        raise CommandExecutionError(_strip_scope(ret["stderr"]))
    return True


def stop(name, no_block=False):
    """
    .. versionchanged:: 2015.8.12,2016.3.3,2016.11.0
        On minions running systemd>=205, `systemd-run(1)`_ is now used to
        isolate commands run by this function from the ``salt-minion`` daemon's
        control group. This is done to avoid a race condition in cases where
        the ``salt-minion`` service is restarted while a service is being
        modified. If desired, usage of `systemd-run(1)`_ can be suppressed by
        setting a :mod:`config option <salt.modules.config.get>` called
        ``systemd.scope``, with a value of ``False`` (no quotes).

    .. _`systemd-run(1)`: https://www.freedesktop.org/software/systemd/man/systemd-run.html

    Stop the specified service with systemd

    no_block : False
        Set to ``True`` to start the service using ``--no-block``.

        .. versionadded:: 2017.7.0

    CLI Example:

    .. code-block:: bash

        salt '*' service.stop <service name>
    """
    _check_for_unit_changes(name)
    # Using cmd.run_all instead of cmd.retcode here to make unit tests easier
    return (
        __salt__["cmd.run_all"](
            _systemctl_cmd("stop", name, systemd_scope=True, no_block=no_block),
            python_shell=False,
        )["retcode"]
        == 0
    )


def restart(name, no_block=False, unmask=False, unmask_runtime=False):
    """
    .. versionchanged:: 2015.8.12,2016.3.3,2016.11.0
        On minions running systemd>=205, `systemd-run(1)`_ is now used to
        isolate commands run by this function from the ``salt-minion`` daemon's
        control group. This is done to avoid a race condition in cases where
        the ``salt-minion`` service is restarted while a service is being
        modified. If desired, usage of `systemd-run(1)`_ can be suppressed by
        setting a :mod:`config option <salt.modules.config.get>` called
        ``systemd.scope``, with a value of ``False`` (no quotes).

    .. _`systemd-run(1)`: https://www.freedesktop.org/software/systemd/man/systemd-run.html

    Restart the specified service with systemd

    no_block : False
        Set to ``True`` to start the service using ``--no-block``.

        .. versionadded:: 2017.7.0

    unmask : False
        Set to ``True`` to remove an indefinite mask before attempting to
        restart the service.

        .. versionadded:: 2017.7.0
            In previous releases, Salt would simply unmask a service before
            restarting. This behavior is no longer the default.

    unmask_runtime : False
        Set to ``True`` to remove a runtime mask before attempting to restart
        the service.

        .. versionadded:: 2017.7.0
            In previous releases, Salt would simply unmask a service before
            restarting. This behavior is no longer the default.

    CLI Example:

    .. code-block:: bash

        salt '*' service.restart <service name>
    """
    _check_for_unit_changes(name)
    _check_unmask(name, unmask, unmask_runtime)
    ret = __salt__["cmd.run_all"](
        _systemctl_cmd("restart", name, systemd_scope=True, no_block=no_block),
        python_shell=False,
    )

    if ret["retcode"] != 0:
        # Instead of returning a bool, raise an exception so that we can
        # include the error message in the return data. This helps give more
        # information to the user in instances where the service is masked.
        raise CommandExecutionError(_strip_scope(ret["stderr"]))
    return True


def reload_(name, no_block=False, unmask=False, unmask_runtime=False):
    """
    .. versionchanged:: 2015.8.12,2016.3.3,2016.11.0
        On minions running systemd>=205, `systemd-run(1)`_ is now used to
        isolate commands run by this function from the ``salt-minion`` daemon's
        control group. This is done to avoid a race condition in cases where
        the ``salt-minion`` service is restarted while a service is being
        modified. If desired, usage of `systemd-run(1)`_ can be suppressed by
        setting a :mod:`config option <salt.modules.config.get>` called
        ``systemd.scope``, with a value of ``False`` (no quotes).

    .. _`systemd-run(1)`: https://www.freedesktop.org/software/systemd/man/systemd-run.html

    Reload the specified service with systemd

    no_block : False
        Set to ``True`` to reload the service using ``--no-block``.

        .. versionadded:: 2017.7.0

    unmask : False
        Set to ``True`` to remove an indefinite mask before attempting to
        reload the service.

        .. versionadded:: 2017.7.0
            In previous releases, Salt would simply unmask a service before
            reloading. This behavior is no longer the default.

    unmask_runtime : False
        Set to ``True`` to remove a runtime mask before attempting to reload
        the service.

        .. versionadded:: 2017.7.0
            In previous releases, Salt would simply unmask a service before
            reloading. This behavior is no longer the default.

    CLI Example:

    .. code-block:: bash

        salt '*' service.reload <service name>
    """
    _check_for_unit_changes(name)
    _check_unmask(name, unmask, unmask_runtime)
    ret = __salt__["cmd.run_all"](
        _systemctl_cmd("reload", name, systemd_scope=True, no_block=no_block),
        python_shell=False,
    )

    if ret["retcode"] != 0:
        # Instead of returning a bool, raise an exception so that we can
        # include the error message in the return data. This helps give more
        # information to the user in instances where the service is masked.
        raise CommandExecutionError(_strip_scope(ret["stderr"]))
    return True


def force_reload(name, no_block=True, unmask=False, unmask_runtime=False):
    """
    .. versionchanged:: 2015.8.12,2016.3.3,2016.11.0
        On minions running systemd>=205, `systemd-run(1)`_ is now used to
        isolate commands run by this function from the ``salt-minion`` daemon's
        control group. This is done to avoid a race condition in cases where
        the ``salt-minion`` service is restarted while a service is being
        modified. If desired, usage of `systemd-run(1)`_ can be suppressed by
        setting a :mod:`config option <salt.modules.config.get>` called
        ``systemd.scope``, with a value of ``False`` (no quotes).

    .. _`systemd-run(1)`: https://www.freedesktop.org/software/systemd/man/systemd-run.html

    .. versionadded:: 0.12.0

    Force-reload the specified service with systemd

    no_block : False
        Set to ``True`` to start the service using ``--no-block``.

        .. versionadded:: 2017.7.0

    unmask : False
        Set to ``True`` to remove an indefinite mask before attempting to
        force-reload the service.

        .. versionadded:: 2017.7.0
            In previous releases, Salt would simply unmask a service before
            force-reloading. This behavior is no longer the default.

    unmask_runtime : False
        Set to ``True`` to remove a runtime mask before attempting to
        force-reload the service.

        .. versionadded:: 2017.7.0
            In previous releases, Salt would simply unmask a service before
            force-reloading. This behavior is no longer the default.

    CLI Example:

    .. code-block:: bash

        salt '*' service.force_reload <service name>
    """
    _check_for_unit_changes(name)
    _check_unmask(name, unmask, unmask_runtime)
    ret = __salt__["cmd.run_all"](
        _systemctl_cmd("force-reload", name, systemd_scope=True, no_block=no_block),
        python_shell=False,
    )

    if ret["retcode"] != 0:
        # Instead of returning a bool, raise an exception so that we can
        # include the error message in the return data. This helps give more
        # information to the user in instances where the service is masked.
        raise CommandExecutionError(_strip_scope(ret["stderr"]))
    return True


# The unused sig argument is required to maintain consistency with the API
# established by Salt's service management states.
def status(name, sig=None):  # pylint: disable=unused-argument
    """
    Return the status for a service via systemd.
    If the name contains globbing, a dict mapping service name to True/False
    values is returned.

    .. versionchanged:: 2018.3.0
        The service name can now be a glob (e.g. ``salt*``)

    Args:
        name (str): The name of the service to check
        sig (str): Not implemented

    Returns:
        bool: True if running, False otherwise
        dict: Maps service name to True if running, False otherwise

    CLI Example:

    .. code-block:: bash

        salt '*' service.status <service name> [service signature]
    """
    contains_globbing = bool(re.search(r"\*|\?|\[.+\]", name))
    if contains_globbing:
        services = fnmatch.filter(get_all(), name)
    else:
        services = [name]
    results = {}
    for service in services:
        _check_for_unit_changes(service)
        results[service] = (
            __salt__["cmd.retcode"](
                _systemctl_cmd("is-active", service),
                python_shell=False,
                ignore_retcode=True,
            )
            == 0
        )
    if contains_globbing:
        return results
    return results[name]


# **kwargs is required to maintain consistency with the API established by
# Salt's service management states.
def enable(
    name, no_block=False, unmask=False, unmask_runtime=False, root=None, **kwargs
):  # pylint: disable=unused-argument
    """
    .. versionchanged:: 2015.8.12,2016.3.3,2016.11.0
        On minions running systemd>=205, `systemd-run(1)`_ is now used to
        isolate commands run by this function from the ``salt-minion`` daemon's
        control group. This is done to avoid a race condition in cases where
        the ``salt-minion`` service is restarted while a service is being
        modified. If desired, usage of `systemd-run(1)`_ can be suppressed by
        setting a :mod:`config option <salt.modules.config.get>` called
        ``systemd.scope``, with a value of ``False`` (no quotes).

    .. _`systemd-run(1)`: https://www.freedesktop.org/software/systemd/man/systemd-run.html

    Enable the named service to start when the system boots

    no_block : False
        Set to ``True`` to start the service using ``--no-block``.

        .. versionadded:: 2017.7.0

    unmask : False
        Set to ``True`` to remove an indefinite mask before attempting to
        enable the service.

        .. versionadded:: 2017.7.0
            In previous releases, Salt would simply unmask a service before
            enabling. This behavior is no longer the default.

    unmask_runtime : False
        Set to ``True`` to remove a runtime mask before attempting to enable
        the service.

        .. versionadded:: 2017.7.0
            In previous releases, Salt would simply unmask a service before
            enabling. This behavior is no longer the default.

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Example:

    .. code-block:: bash

        salt '*' service.enable <service name>
    """
    _check_for_unit_changes(name)
    _check_unmask(name, unmask, unmask_runtime, root)
    if name in _get_sysv_services(root):
        cmd = []
        if salt.utils.systemd.has_scope(__context__) and __salt__["config.get"](
            "systemd.scope", True
        ):
            cmd.extend(["systemd-run", "--scope"])
        service_exec = _get_service_exec()
        if service_exec.endswith("/update-rc.d"):
            cmd.extend([service_exec, "-f", name, "defaults", "99"])
        elif service_exec.endswith("/chkconfig"):
            cmd.extend([service_exec, name, "on"])
        return (
            __salt__["cmd.retcode"](cmd, python_shell=False, ignore_retcode=True) == 0
        )
    ret = __salt__["cmd.run_all"](
        _systemctl_cmd(
            "enable", name, systemd_scope=True, no_block=no_block, root=root
        ),
        python_shell=False,
        ignore_retcode=True,
    )

    if ret["retcode"] != 0:
        # Instead of returning a bool, raise an exception so that we can
        # include the error message in the return data. This helps give more
        # information to the user in instances where the service is masked.
        raise CommandExecutionError(_strip_scope(ret["stderr"]))
    return True


# The unused kwargs argument is required to maintain consistency with the API
# established by Salt's service management states.
def disable(
    name, no_block=False, root=None, **kwargs
):  # pylint: disable=unused-argument
    """
    .. versionchanged:: 2015.8.12,2016.3.3,2016.11.0
        On minions running systemd>=205, `systemd-run(1)`_ is now used to
        isolate commands run by this function from the ``salt-minion`` daemon's
        control group. This is done to avoid a race condition in cases where
        the ``salt-minion`` service is restarted while a service is being
        modified. If desired, usage of `systemd-run(1)`_ can be suppressed by
        setting a :mod:`config option <salt.modules.config.get>` called
        ``systemd.scope``, with a value of ``False`` (no quotes).

    .. _`systemd-run(1)`: https://www.freedesktop.org/software/systemd/man/systemd-run.html

    Disable the named service to not start when the system boots

    no_block : False
        Set to ``True`` to start the service using ``--no-block``.

        .. versionadded:: 2017.7.0

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Example:

    .. code-block:: bash

        salt '*' service.disable <service name>
    """
    _check_for_unit_changes(name)
    if name in _get_sysv_services(root):
        cmd = []
        if salt.utils.systemd.has_scope(__context__) and __salt__["config.get"](
            "systemd.scope", True
        ):
            cmd.extend(["systemd-run", "--scope"])
        service_exec = _get_service_exec()
        if service_exec.endswith("/update-rc.d"):
            cmd.extend([service_exec, "-f", name, "remove"])
        elif service_exec.endswith("/chkconfig"):
            cmd.extend([service_exec, name, "off"])
        return (
            __salt__["cmd.retcode"](cmd, python_shell=False, ignore_retcode=True) == 0
        )
    # Using cmd.run_all instead of cmd.retcode here to make unit tests easier
    return (
        __salt__["cmd.run_all"](
            _systemctl_cmd(
                "disable", name, systemd_scope=True, no_block=no_block, root=root
            ),
            python_shell=False,
            ignore_retcode=True,
        )["retcode"]
        == 0
    )


# The unused kwargs argument is required to maintain consistency with the API
# established by Salt's service management states.
def enabled(name, root=None, **kwargs):  # pylint: disable=unused-argument
    """
    Return if the named service is enabled to start on boot

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Example:

    .. code-block:: bash

        salt '*' service.enabled <service name>
    """
    # Try 'systemctl is-enabled' first, then look for a symlink created by
    # systemctl (older systemd releases did not support using is-enabled to
    # check templated services), and lastly check for a sysvinit service.
    if (
        __salt__["cmd.retcode"](
            _systemctl_cmd("is-enabled", name, root=root),
            python_shell=False,
            ignore_retcode=True,
        )
        == 0
    ):
        return True
    elif "@" in name:
        # On older systemd releases, templated services could not be checked
        # with ``systemctl is-enabled``. As a fallback, look for the symlinks
        # created by systemctl when enabling templated services.
        local_config_path = _root(LOCAL_CONFIG_PATH, "/")
        cmd = [
            "find",
            local_config_path,
            "-name",
            name,
            "-type",
            "l",
            "-print",
            "-quit",
        ]
        # If the find command returns any matches, there will be output and the
        # string will be non-empty.
        if bool(__salt__["cmd.run"](cmd, python_shell=False)):
            return True
    elif name in _get_sysv_services(root):
        return _sysv_enabled(name, root)

    return False


def disabled(name, root=None):
    """
    Return if the named service is disabled from starting on boot

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Example:

    .. code-block:: bash

        salt '*' service.disabled <service name>
    """
    return not enabled(name, root=root)


def show(name, root=None):
    """
    .. versionadded:: 2014.7.0

    Show properties of one or more units/jobs or the manager

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Example:

    .. code-block:: bash

        salt '*' service.show <service name>
    """
    ret = {}
    out = __salt__["cmd.run"](
        _systemctl_cmd("show", name, root=root), python_shell=False
    )
    for line in salt.utils.itertools.split(out, "\n"):
        comps = line.split("=")
        name = comps[0]
        value = "=".join(comps[1:])
        if value.startswith("{"):
            value = value.replace("{", "").replace("}", "")
            ret[name] = {}
            for item in value.split(" ; "):
                comps = item.split("=")
                ret[name][comps[0].strip()] = comps[1].strip()
        elif name in ("Before", "After", "Wants"):
            ret[name] = value.split()
        else:
            ret[name] = value

    return ret


def execs(root=None):
    """
    .. versionadded:: 2014.7.0

    Return a list of all files specified as ``ExecStart`` for all services.

    root
        Enable/disable/mask unit files in the specified root directory

    CLI Example:

    .. code-block:: bash

        salt '*' service.execs
    """
    ret = {}
    for service in get_all(root=root):
        data = show(service, root=root)
        if "ExecStart" not in data:
            continue
        ret[service] = data["ExecStart"]["path"]
    return ret


def firstboot(
    locale=None,
    locale_message=None,
    keymap=None,
    timezone=None,
    hostname=None,
    machine_id=None,
    root=None,
):
    """
    .. versionadded:: 3001

    Call systemd-firstboot to configure basic settings of the system

    locale
        Set primary locale (LANG=)

    locale_message
        Set message locale (LC_MESSAGES=)

    keymap
        Set keymap

    timezone
        Set timezone

    hostname
        Set host name

    machine_id
        Set machine ID

    root
        Operate on an alternative filesystem root

    CLI Example:

    .. code-block:: bash

        salt '*' service.firstboot keymap=jp locale=en_US.UTF-8

    """
    cmd = [salt.utils.path.which("systemd-firstboot")]
    parameters = [
        ("locale", locale),
        ("locale-message", locale_message),
        ("keymap", keymap),
        ("timezone", timezone),
        ("hostname", hostname),
        ("machine-ID", machine_id),
        ("root", root),
    ]
    for parameter, value in parameters:
        if value:
            cmd.extend([f"--{parameter}", str(value)])

    out = __salt__["cmd.run_all"](cmd)

    if out["retcode"] != 0:
        raise CommandExecutionError("systemd-firstboot error: {}".format(out["stderr"]))

    return True


def offline():
    """
    .. versionadded:: 3004

    Check if systemd is working in offline mode, where is not possible
    to talk with PID 1.

    CLI Example:

    .. code-block:: bash

        salt '*' service.offline

    """

    return salt.utils.systemd.offline(__context__)
