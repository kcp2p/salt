"""
Install features/packages for Windows using DISM, which is useful for minions
not running server versions of Windows. Some functions are only available on
Windows 10.

"""

import logging
import os
import re

import salt.utils.platform
import salt.utils.versions
from salt.exceptions import CommandExecutionError

log = logging.getLogger(__name__)
__virtualname__ = "dism"

# We always want to use the version of dism that matches the architecture of the
# host machine. On 32bit boxes that will always be System32. On 64bit boxes that
# are running 64bit salt that will always be System32. On 64bit boxes that are
# running 32bit salt the 64bit dism will be found in SysNative
# Sysnative is a virtual folder, a special alias, that can be used to access the
# 64-bit System32 folder from a 32-bit application
try:
    # This does not apply to Non-Windows platforms
    if not salt.utils.platform.is_windows():
        raise OSError

    if os.path.exists(os.path.join(os.environ.get("SystemRoot"), "SysNative")):
        bin_path = os.path.join(os.environ.get("SystemRoot"), "SysNative")
    else:
        bin_path = os.path.join(os.environ.get("SystemRoot"), "System32")
    bin_dism = os.path.join(bin_path, "dism.exe")

except OSError:
    log.trace("win_dism: Non-Windows system")
    bin_dism = "dism.exe"


def __virtual__():
    """
    Only work on Windows
    """
    if not salt.utils.platform.is_windows():
        return False, "Only available on Windows systems"

    return __virtualname__


def _get_components(type_regex, plural_type, install_value, image=None):
    cmd = [
        bin_dism,
        "/English",
        f"/Image:{image}" if image else "/Online",
        f"/Get-{plural_type}",
    ]
    out = __salt__["cmd.run"](cmd)
    pattern = rf"{type_regex} : (.*)\r\n.*State : {install_value}\r\n"
    capabilities = re.findall(pattern, out, re.MULTILINE)
    capabilities.sort()
    return capabilities


def add_capability(
    capability, source=None, limit_access=False, image=None, restart=False
):
    """
    Install a capability

    Args:
        capability (str): The capability to install
        source (Optional[str]): The optional source of the capability. Default
            is set by group policy and can be Windows Update.
        limit_access (Optional[bool]): Prevent DISM from contacting Windows
            Update for the source package
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.
        restart (Optional[bool]): Reboot the machine if required by the install

    Raises:
        NotImplementedError: For all versions of Windows that are not Windows 10
        and later. Server editions of Windows use ServerManager instead.

    Returns:
        dict: A dictionary containing the results of the command

    CLI Example:

    .. code-block:: bash

        salt '*' dism.add_capability Tools.Graphics.DirectX~~~~0.0.1.0
    """
    if salt.utils.versions.version_cmp(__grains__["osversion"], "10") == -1:
        raise NotImplementedError(
            "`install_capability` is not available on this version of Windows: "
            "{}".format(__grains__["osversion"])
        )

    cmd = [
        bin_dism,
        "/Quiet",
        f"/Image:{image}" if image else "/Online",
        "/Add-Capability",
        f"/CapabilityName:{capability}",
    ]

    if source:
        cmd.append(f"/Source:{source}")
    if limit_access:
        cmd.append("/LimitAccess")
    if not restart:
        cmd.append("/NoRestart")

    return __salt__["cmd.run_all"](cmd)


def remove_capability(capability, image=None, restart=False):
    """
    Uninstall a capability

    Args:
        capability(str): The capability to be removed
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.
        restart (Optional[bool]): Reboot the machine if required by the install

    Raises:
        NotImplementedError: For all versions of Windows that are not Windows 10
        and later. Server editions of Windows use ServerManager instead.

    Returns:
        dict: A dictionary containing the results of the command

    CLI Example:

    .. code-block:: bash

        salt '*' dism.remove_capability Tools.Graphics.DirectX~~~~0.0.1.0
    """
    if salt.utils.versions.version_cmp(__grains__["osversion"], "10") == -1:
        raise NotImplementedError(
            "`uninstall_capability` is not available on this version of "
            "Windows: {}".format(__grains__["osversion"])
        )

    cmd = [
        bin_dism,
        "/Quiet",
        f"/Image:{image}" if image else "/Online",
        "/Remove-Capability",
        f"/CapabilityName:{capability}",
    ]

    if not restart:
        cmd.append("/NoRestart")

    return __salt__["cmd.run_all"](cmd)


def get_capabilities(image=None):
    """
    List all capabilities on the system

    Args:
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.

    Raises:
        NotImplementedError: For all versions of Windows that are not Windows 10
        and later. Server editions of Windows use ServerManager instead.

    Returns:
        list: A list of capabilities

    CLI Example:

    .. code-block:: bash

        salt '*' dism.get_capabilities
    """
    if salt.utils.versions.version_cmp(__grains__["osversion"], "10") == -1:
        raise NotImplementedError(
            "`installed_capabilities` is not available on this version of "
            "Windows: {}".format(__grains__["osversion"])
        )

    cmd = [
        bin_dism,
        "/English",
        f"/Image:{image}" if image else "/Online",
        "/Get-Capabilities",
    ]
    out = __salt__["cmd.run"](cmd)

    pattern = r"Capability Identity : (.*)\r\n"
    capabilities = re.findall(pattern, out, re.MULTILINE)
    capabilities.sort()

    return capabilities


def installed_capabilities(image=None):
    """
    List the capabilities installed on the system

    Args:
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.

    Raises:
        NotImplementedError: For all versions of Windows that are not Windows 10
        and later. Server editions of Windows use ServerManager instead.

    Returns:
        list: A list of installed capabilities

    CLI Example:

    .. code-block:: bash

        salt '*' dism.installed_capabilities
    """
    if salt.utils.versions.version_cmp(__grains__["osversion"], "10") == -1:
        raise NotImplementedError(
            "`installed_capabilities` is not available on this version of "
            "Windows: {}".format(__grains__["osversion"])
        )
    return _get_components("Capability Identity", "Capabilities", "Installed")


def available_capabilities(image=None):
    """
    List the capabilities available on the system

    Args:
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.

    Raises:
        NotImplementedError: For all versions of Windows that are not Windows 10
        and later. Server editions of Windows use ServerManager instead.

    Returns:
        list: A list of available capabilities

    CLI Example:

    .. code-block:: bash

        salt '*' dism.installed_capabilities
    """
    if salt.utils.versions.version_cmp(__grains__["osversion"], "10") == -1:
        raise NotImplementedError(
            "`installed_capabilities` is not available on this version of "
            "Windows: {}".format(__grains__["osversion"])
        )
    return _get_components("Capability Identity", "Capabilities", "Not Present")


def add_feature(
    feature,
    package=None,
    source=None,
    limit_access=False,
    enable_parent=False,
    image=None,
    restart=False,
):
    """
    Install a feature using DISM

    Args:
        feature (str): The feature to install
        package (Optional[str]): The parent package for the feature. You do not
            have to specify the package if it is the Windows Foundation Package.
            Otherwise, use package to specify the parent package of the feature
        source (Optional[str]): The optional source of the capability. Default
            is set by group policy and can be Windows Update
        limit_access (Optional[bool]): Prevent DISM from contacting Windows
            Update for the source package
        enable_parent (Optional[bool]): True will enable all parent features of
            the specified feature
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.
        restart (Optional[bool]): Reboot the machine if required by the install

    Returns:
        dict: A dictionary containing the results of the command

    CLI Example:

    .. code-block:: bash

        salt '*' dism.add_feature NetFx3
    """
    cmd = [
        bin_dism,
        "/Quiet",
        f"/Image:{image}" if image else "/Online",
        "/Enable-Feature",
        f"/FeatureName:{feature}",
    ]
    if package:
        cmd.append(f"/PackageName:{package}")
    if source:
        cmd.append(f"/Source:{source}")
    if limit_access:
        cmd.append("/LimitAccess")
    if enable_parent:
        cmd.append("/All")
    if not restart:
        cmd.append("/NoRestart")

    return __salt__["cmd.run_all"](cmd)


def remove_feature(feature, remove_payload=False, image=None, restart=False):
    """
    Disables the feature.

    Args:
        feature (str): The feature to uninstall
        remove_payload (Optional[bool]): Remove the feature's payload. Must
            supply source when enabling in the future.
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.
        restart (Optional[bool]): Reboot the machine if required by the install

    Returns:
        dict: A dictionary containing the results of the command

    CLI Example:

    .. code-block:: bash

        salt '*' dism.remove_feature NetFx3
    """
    cmd = [
        bin_dism,
        "/Quiet",
        f"/Image:{image}" if image else "/Online",
        "/Disable-Feature",
        f"/FeatureName:{feature}",
    ]

    if remove_payload:
        cmd.append("/Remove")
    if not restart:
        cmd.append("/NoRestart")

    return __salt__["cmd.run_all"](cmd)


def get_features(package=None, image=None):
    """
    List features on the system or in a package

    Args:
        package (Optional[str]): The full path to the package. Can be either a
            .cab file or a folder. Should point to the original source of the
            package, not to where the file is installed. You cannot use this
            command to get package information for .msu files

            This can also be the name of a package as listed in
            ``dism.installed_packages``
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.

    Returns:
        list: A list of features

    CLI Example:

        .. code-block:: bash

            # Return all features on the system
            salt '*' dism.get_features

            # Return all features in package.cab
            salt '*' dism.get_features C:\\packages\\package.cab

            # Return all features in the calc package
            salt '*' dism.get_features Microsoft.Windows.Calc.Demo~6595b6144ccf1df~x86~en~1.0.0.0
    """
    cmd = [
        bin_dism,
        "/English",
        f"/Image:{image}" if image else "/Online",
        "/Get-Features",
    ]

    if package:
        if "~" in package:
            cmd.append(f"/PackageName:{package}")
        else:
            cmd.append(f"/PackagePath:{package}")

    out = __salt__["cmd.run"](cmd)

    pattern = r"Feature Name : (.*)\r\n"
    features = re.findall(pattern, out, re.MULTILINE)
    features.sort()

    return features


def installed_features(image=None):
    """
    List the features installed on the system

    Args:
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.

    Returns:
        list: A list of installed features

    CLI Example:

    .. code-block:: bash

        salt '*' dism.installed_features
    """
    return _get_components("Feature Name", "Features", "Enabled")


def available_features(image=None):
    """
    List the features available on the system

    Args:
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.

    Returns:
        list: A list of available features

    CLI Example:

    .. code-block:: bash

        salt '*' dism.available_features
    """
    return _get_components("Feature Name", "Features", "Disabled")


def add_package(
    package, ignore_check=False, prevent_pending=False, image=None, restart=False
):
    """
    Install a package using DISM

    Args:
        package (str):
            The package to install. Can be a .cab file, a .msu file, or a folder

            .. note::
                An `.msu` package is supported only when the target image is
                offline, either mounted or applied.

        ignore_check (Optional[bool]):
            Skip installation of the package if the applicability checks fail

        prevent_pending (Optional[bool]):
            Skip the installation of the package if there are pending online
            actions

        image (Optional[str]):
            The path to the root directory of an offline Windows image. If
            ``None`` is passed, the running operating system is targeted.
            Default is None.

        restart (Optional[bool]):
            Reboot the machine if required by the install

    Returns:
        dict: A dictionary containing the results of the command

    CLI Example:

    .. code-block:: bash

        salt '*' dism.add_package C:\\Packages\\package.cab
    """
    cmd = [
        bin_dism,
        "/Quiet",
        f"/Image:{image}" if image else "/Online",
        "/Add-Package",
        f"/PackagePath:{package}",
    ]

    if ignore_check:
        cmd.append("/IgnoreCheck")
    if prevent_pending:
        cmd.append("/PreventPending")
    if not restart:
        cmd.append("/NoRestart")

    return __salt__["cmd.run_all"](cmd)


def remove_package(package, image=None, restart=False):
    """
    Uninstall a package

    Args:
        package (str): The full path to the package. Can be either a .cab file
            or a folder. Should point to the original source of the package, not
            to where the file is installed. This can also be the name of a
            package as listed in ``dism.installed_packages``
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.
        restart (Optional[bool]): Reboot the machine if required by the
            uninstall

    Returns:
        dict: A dictionary containing the results of the command

    CLI Example:

    .. code-block:: bash

        # Remove the Calc Package
        salt '*' dism.remove_package Microsoft.Windows.Calc.Demo~6595b6144ccf1df~x86~en~1.0.0.0

        # Remove the package.cab (does not remove C:\\packages\\package.cab)
        salt '*' dism.remove_package C:\\packages\\package.cab
    """
    cmd = [
        bin_dism,
        "/Quiet",
        f"/Image:{image}" if image else "/Online",
        "/Remove-Package",
    ]

    if not restart:
        cmd.append("/NoRestart")

    if "~" in package:
        cmd.append(f"/PackageName:{package}")
    else:
        cmd.append(f"/PackagePath:{package}")

    return __salt__["cmd.run_all"](cmd)


def get_kb_package_name(kb, image=None):
    """
    Get the actual package name on the system based on the KB name

    .. versionadded:: 3006.0

    Args:
        kb (str): The name of the KB to remove. Can also be just the KB number
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.

    Returns:
        str: The name of the package found on the system
        None: If the package is not installed on the system

    CLI Example:

    .. code-block:: bash

        # Get the package name for KB1231231
        salt '*' dism.get_kb_package_name KB1231231

        # Get the package name for KB1231231 using just the number
        salt '*' dism.get_kb_package_name 1231231
    """
    packages = installed_packages(image=image)
    search = kb.upper() if kb.lower().startswith("kb") else f"KB{kb}"
    for package in packages:
        if f"_{search}~" in package:
            return package
    return None


def remove_kb(kb, image=None, restart=False):
    """
    Remove a package by passing a KB number. This searches the installed
    packages to get the full package name of the KB. It then calls the
    ``dism.remove_package`` function to remove the package.

    .. versionadded:: 3006.0

    Args:
        kb (str): The name of the KB to remove. Can also be just the KB number
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.
        restart (Optional[bool]): Reboot the machine if required by the
            uninstall

    Returns:
        dict: A dictionary containing the results of the command

    CLI Example:

    .. code-block:: bash

        # Remove the KB5007575 just passing the number
        salt '*' dism.remove_kb 5007575

        # Remove the KB5007575 just passing the full name
        salt '*' dism.remove_kb KB5007575
    """
    pkg_name = get_kb_package_name(kb=kb, image=image)
    if pkg_name is None:
        msg = f"{kb} not installed"
        raise CommandExecutionError(msg)
    log.debug("Found: %s", pkg_name)
    return remove_package(package=pkg_name, image=image, restart=restart)


def installed_packages(image=None):
    """
    List the packages installed on the system

    Args:
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.

    Returns:
        list: A list of installed packages

    CLI Example:

    .. code-block:: bash

        salt '*' dism.installed_packages
    """
    return _get_components(
        type_regex="Package Identity",
        plural_type="Packages",
        install_value="Installed",
        image=image,
    )


def package_info(package, image=None):
    """
    Display information about a package

    Args:
        package (str): The full path to the package. Can be either a .cab file
            or a folder. Should point to the original source of the package, not
            to where the file is installed. You cannot use this command to get
            package information for .msu files
        image (Optional[str]): The path to the root directory of an offline
            Windows image. If `None` is passed, the running operating system is
            targeted. Default is None.

    Returns:
        dict: A dictionary containing the results of the command

    CLI Example:

    .. code-block:: bash

        salt '*' dism. package_info C:\\packages\\package.cab
    """
    cmd = [
        bin_dism,
        "/English",
        f"/Image:{image}" if image else "/Online",
        "/Get-PackageInfo",
    ]

    if "~" in package:
        cmd.append(f"/PackageName:{package}")
    else:
        cmd.append(f"/PackagePath:{package}")

    out = __salt__["cmd.run_all"](cmd)

    if out["retcode"] == 0:
        ret = dict()
        for line in str(out["stdout"]).splitlines():
            if " : " in line:
                info = line.split(" : ")
                if len(info) < 2:
                    continue
                ret[info[0]] = info[1]
    else:
        ret = out

    return ret
