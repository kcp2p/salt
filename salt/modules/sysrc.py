"""
sysrc module for FreeBSD
"""

import salt.utils.path
from salt.exceptions import CommandExecutionError

__virtualname__ = "sysrc"

__func_alias__ = {"set_": "set"}


def __virtual__():
    """
    Only runs if sysrc exists
    """
    if salt.utils.path.which("sysrc") is not None:
        return True
    return (
        False,
        "The sysrc execution module failed to load: the sysrc binary is not in the"
        " path.",
    )


def get(**kwargs):
    """
    Return system rc configuration variables

    CLI Example:

     .. code-block:: bash

         salt '*' sysrc.get includeDefaults=True
    """

    cmd = "sysrc -v"

    if "file" in kwargs:
        cmd += " -f " + kwargs["file"]

    if "jail" in kwargs:
        cmd += " -j " + kwargs["jail"]

    if "name" in kwargs:
        cmd += " " + kwargs["name"]
    elif kwargs.get("includeDefaults", False):
        cmd += " -A"
    else:
        cmd += " -a"

    sysrcs = __salt__["cmd.run"](cmd)
    if "sysrc: unknown variable" in sysrcs:
        # raise CommandExecutionError(sysrcs)
        return None

    ret = {}
    for sysrc in sysrcs.split("\n"):
        line_components = sysrc.split(": ")
        rcfile = line_components[0]
        if len(line_components) > 2:
            var = line_components[1]
            val = line_components[2]
        else:
            var = line_components[1].rstrip(":")
            val = ""
        if rcfile not in ret:
            ret[rcfile] = {}
        ret[rcfile][var] = val
    return ret


def set_(name, value, **kwargs):
    """
    Set system rc configuration variables

    CLI Example:

     .. code-block:: bash

         salt '*' sysrc.set name=sshd_flags value="-p 2222"
    """

    cmd = "sysrc -v"

    if "file" in kwargs:
        cmd += " -f " + kwargs["file"]

    if "jail" in kwargs:
        cmd += " -j " + kwargs["jail"]

    # This is here because the YAML parser likes to convert the string literals
    # YES, NO, Yes, No, True, False, etc. to boolean types.  However, in this case,
    # we will check to see if that happened and replace it with "YES" or "NO" because
    # those items are accepted in sysrc.
    if isinstance(value, bool):
        if value:
            value = "YES"
        else:
            value = "NO"

    # This is here for the same reason, except for numbers
    if isinstance(value, int):
        value = str(value)

    cmd += " " + name + '="' + value + '"'

    r = __salt__["cmd.run_all"](cmd)

    if r["retcode"] != 0:
        raise CommandExecutionError("sysrc failed: {}".format(r["stderr"]))

    ret = {}
    for sysrc in r["stdout"].split("\n"):
        rcfile = sysrc.split(": ")[0]
        var = sysrc.split(": ")[1]
        oldval = sysrc.split(": ")[2].strip().split("->")[0]
        newval = sysrc.split(": ")[2].strip().split("->")[1]
        if rcfile not in ret:
            ret[rcfile] = {}
        ret[rcfile][var] = newval
    return ret


def remove(name, **kwargs):
    """
    Remove system rc configuration variables

    CLI Example:

     .. code-block:: bash

         salt '*' sysrc.remove name=sshd_enable
    """

    cmd = "sysrc -v"

    if "file" in kwargs:
        cmd += " -f " + kwargs["file"]

    if "jail" in kwargs:
        cmd += " -j " + kwargs["jail"]

    cmd += " -x " + name

    sysrcs = __salt__["cmd.run"](cmd)
    if "sysrc: unknown variable" in sysrcs:
        raise CommandExecutionError(sysrcs)
    else:
        return name + " removed"
