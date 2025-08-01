"""
Grains for iSCSI Qualified Names (IQN).

.. versionadded:: 2018.3.0

To enable these grains set `iscsi_grains: True` in the minion config.

.. code-block:: yaml

    iscsi_grains: True
"""

import errno
import logging

import salt.modules.cmdmod
import salt.utils.files
import salt.utils.path
import salt.utils.platform

__virtualname__ = "iscsi"

# Get logging started
log = logging.getLogger(__name__)


def __virtual__():
    if __opts__.get("iscsi_grains", False) is False:
        return False
    else:
        return __virtualname__


def iscsi_iqn():
    """
    Return iSCSI IQN
    """
    grains = {}
    grains["iscsi_iqn"] = False
    if salt.utils.platform.is_linux():
        grains["iscsi_iqn"] = _linux_iqn()
    elif salt.utils.platform.is_windows():
        grains["iscsi_iqn"] = _windows_iqn()
    elif salt.utils.platform.is_aix():
        grains["iscsi_iqn"] = _aix_iqn()
    return grains


def _linux_iqn():
    """
    Return iSCSI IQN from a Linux host.
    """
    ret = []

    initiator = "/etc/iscsi/initiatorname.iscsi"
    try:
        with salt.utils.files.fopen(initiator, "r") as _iscsi:
            for line in _iscsi:
                line = line.strip()
                if line.startswith("InitiatorName="):
                    ret.append(line.split("=", 1)[1])
    except OSError as ex:
        if ex.errno != errno.ENOENT:
            log.debug("Error while accessing '%s': %s", initiator, ex)

    return ret


def _aix_iqn():
    """
    Return iSCSI IQN from an AIX host.
    """
    ret = []

    aix_cmd = "lsattr -E -l iscsi0 | grep initiator_name"

    aix_ret = salt.modules.cmdmod.run(aix_cmd)
    if aix_ret[0].isalpha():
        try:
            ret.append(aix_ret.split()[1].rstrip())
        except IndexError:
            pass
    return ret


def _windows_iqn():
    """
    Return iSCSI nodes from a Windows host.
    """
    cmd = "Get-InitiatorPort | Select NodeAddress"
    ret = []

    nodes = salt.modules.cmdmod.powershell(cmd)

    if not nodes:
        log.trace("No iSCSI nodes found")
        return ret

    # A single node will return a dictionary with a single entry
    # {"NodeAddress": "iqn.1991-05.com.microsoft:johnj99-pc2.contoso.com"}
    # Multiple nodes will return a list of single entry dicts
    # We need a list of dict
    if isinstance(nodes, dict):
        nodes = [nodes]

    for node in nodes:
        ret.append(node["NodeAddress"])

    return ret
