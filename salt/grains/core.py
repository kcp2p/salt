"""
The static grains, these are the core, or built in grains.

When grains are loaded they are not loaded in the same way that modules are
loaded, grain functions are detected and executed, the functions MUST
return a dict which will be applied to the main grains dict. This module
will always be executed first, so that any grains loaded here in the core
module can be overwritten just by returning dict keys with the same value
as those returned here
"""

import datetime
import hashlib
import locale
import logging
import os
import platform
import re
import socket
import subprocess
import sys
import time
import uuid
from errno import EACCES, EPERM

import salt.exceptions

# Solve the Chicken and egg problem where grains need to run before any
# of the modules are loaded and are generally available for any usage.
import salt.modules.cmdmod
import salt.modules.network
import salt.modules.smbios
import salt.utils.args
import salt.utils.dns
import salt.utils.files
import salt.utils.network
import salt.utils.path
import salt.utils.pkg.rpm
import salt.utils.platform
import salt.utils.stringutils
from salt.utils.network import _clear_interfaces, _get_interfaces
from salt.utils.platform import get_machine_identifier as _get_machine_identifier
from salt.utils.platform import linux_distribution as _linux_distribution

try:
    # pylint: disable=no-name-in-module
    from platform import freedesktop_os_release as _freedesktop_os_release

except ImportError:  # Define freedesktop_os_release for Python < 3.10

    def _parse_os_release(*os_release_files):
        """
        Parse os-release and return a parameter dictionary

        This function will behave identical to
        platform.freedesktop_os_release() from Python >= 3.10, if
        called with ("/etc/os-release", "/usr/lib/os-release").

        See http://www.freedesktop.org/software/systemd/man/os-release.html
        for specification of the file format.
        """
        # These fields are mandatory fields with well-known defaults
        # in practice all Linux distributions override NAME, ID, and PRETTY_NAME.
        ret = {"NAME": "Linux", "ID": "linux", "PRETTY_NAME": "Linux"}

        errno = None
        for filename in os_release_files:
            try:
                with salt.utils.files.fopen(filename) as ifile:
                    regex = re.compile("^([\\w]+)=(?:'|\")?(.*?)(?:'|\")?$")
                    for line in ifile:
                        match = regex.match(line.strip())
                        if match:
                            # Shell special characters ("$", quotes, backslash,
                            # backtick) are escaped with backslashes
                            ret[match.group(1)] = re.sub(
                                r'\\([$"\'\\`])', r"\1", match.group(2)
                            )
                break
            except OSError as error:
                errno = error.errno
        else:
            raise OSError(
                errno, "Unable to read files {}".format(", ".join(os_release_files))
            )

        return ret

    def _freedesktop_os_release():
        return _parse_os_release("/etc/os-release", "/usr/lib/os-release")


def __init__(opts):
    _clear_interfaces()


try:
    import dateutil.tz  # pylint: disable=import-error

    _DATEUTIL_TZ = True
except ImportError:
    _DATEUTIL_TZ = False

log = logging.getLogger(__name__)

HAS_WMI = False
if salt.utils.platform.is_windows():
    import salt.utils.win_osinfo

    # attempt to import the python wmi module
    # the Windows minion uses WMI for some of its grains
    try:
        import win32api
        import wmi  # pylint: disable=import-error

        import salt.utils.win_reg
        import salt.utils.winapi

        HAS_WMI = True
    except ImportError:
        log.exception(
            "Unable to import Python wmi module, some core grains will be missing"
        )


__proxyenabled__ = ["*"]
__FQDN__ = None

__salt__ = {
    "cmd.run": salt.modules.cmdmod._run_quiet,
    "cmd.retcode": salt.modules.cmdmod._retcode_quiet,
    "cmd.run_all": salt.modules.cmdmod._run_all_quiet,
    "smbios.records": salt.modules.smbios.records,
    "smbios.get": salt.modules.smbios.get,
    "network.fqdns": salt.modules.network.fqdns,
}

HAS_UNAME = hasattr(os, "uname")


# Possible value for h_errno defined in netdb.h
HOST_NOT_FOUND = 1
NO_DATA = 4


def _parse_junos_showver(txt):
    showver = {}
    for l in txt.splitlines():
        decoded_line = l.decode("utf-8")
        if decoded_line.startswith("Model"):
            showver["model"] = decoded_line.split(" ")[1]
        if decoded_line.startswith("Junos"):
            showver["osrelease"] = decoded_line.split(" ")[1]
            showver["osmajorrelease"] = decoded_line.split(".")[0]
            showver["osrelease_info"] = decoded_line.split(".")
        if decoded_line.startswith("JUNOS OS Kernel"):
            showver["kernelversion"] = decoded_line
            relno = re.search(r"\[(.*)\]", decoded_line)
            if relno:
                showver["kernelrelease"] = relno.group(1)
    return showver


def _windows_cpudata():
    """
    Return some CPU information on Windows minions
    """
    # Provides:
    #   num_cpus
    #   cpu_model
    grains = {}
    if "NUMBER_OF_PROCESSORS" in os.environ:
        # Cast to int so that the logic isn't broken when used as a
        # conditional in templating. Also follows _linux_cpudata()
        try:
            grains["num_cpus"] = int(os.environ["NUMBER_OF_PROCESSORS"])
        except ValueError:
            grains["num_cpus"] = 1
    grains["cpu_model"] = salt.utils.win_reg.read_value(
        hive="HKEY_LOCAL_MACHINE",
        key="HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0",
        vname="ProcessorNameString",
    ).get("vdata")
    return grains


def _linux_cpudata():
    """
    Return some CPU information for Linux minions
    """
    # Provides:
    #   num_cpus
    #   cpu_model
    #   cpu_flags
    grains = {}
    cpuinfo = "/proc/cpuinfo"
    # Parse over the cpuinfo file
    if os.path.isfile(cpuinfo):
        with salt.utils.files.fopen(cpuinfo, "r") as _fp:
            grains["num_cpus"] = 0
            for line in _fp:
                comps = line.split(":")
                if not len(comps) > 1:
                    continue
                key = comps[0].strip()
                val = comps[1].strip()
                if key == "processor":
                    grains["num_cpus"] += 1
                # head -2 /proc/cpuinfo
                # vendor_id       : IBM/S390
                # # processors    : 2
                elif key == "# processors":
                    grains["num_cpus"] = int(val)
                elif key == "vendor_id":
                    grains["cpu_model"] = val
                elif key == "model name":
                    grains["cpu_model"] = val
                elif key == "flags":
                    grains["cpu_flags"] = val.split()
                elif key == "Features":
                    grains["cpu_flags"] = val.split()
                # ARM support - /proc/cpuinfo
                #
                # Processor       : ARMv6-compatible processor rev 7 (v6l)
                # BogoMIPS        : 697.95
                # Features        : swp half thumb fastmult vfp edsp java tls
                # CPU implementer : 0x41
                # CPU architecture: 7
                # CPU variant     : 0x0
                # CPU part        : 0xb76
                # CPU revision    : 7
                #
                # Hardware        : BCM2708
                # Revision        : 0002
                # Serial          : 00000000
                elif key == "Processor":
                    grains["cpu_model"] = val.split("-")[0]
                    grains["num_cpus"] = 1
                # PPC64LE support - /proc/cpuinfo
                #
                # processor	: 0
                # cpu		: POWER9 (architected), altivec supported
                # clock		: 2750.000000MHz
                # revision	: 2.2 (pvr 004e 0202)
                elif key == "cpu":
                    grains["cpu_model"] = val

    if "num_cpus" not in grains:
        grains["num_cpus"] = 0
    if "cpu_model" not in grains:
        grains["cpu_model"] = "Unknown"
    if "cpu_flags" not in grains:
        grains["cpu_flags"] = []
    return grains


def _linux_gpu_data():
    """
    num_gpus: int
    gpus:
      - vendor: nvidia|amd|ati|...
        model: string
    """
    if __opts__.get("enable_lspci", True) is False:
        return {}

    if __opts__.get("enable_gpu_grains", True) is False:
        return {}

    lspci = salt.utils.path.which("lspci")
    if not lspci:
        log.debug(
            "The `lspci` binary is not available on the system. GPU grains "
            "will not be available."
        )
        return {}

    # dominant gpu vendors to search for (MUST be lowercase for matching below)
    known_vendors = [
        "nvidia",
        "amd",
        "ati",
        "intel",
        "cirrus logic",
        "vmware",
        "matrox",
        "aspeed",
    ]
    gpu_classes = (
        "3d controller",
        "display controller",
        "processing accelerators",
        "vga compatible controller",
    )

    devs = []
    try:
        lspci_out = __salt__["cmd.run"](f"{lspci} -vmm")

        cur_dev = {}
        error = False
        # Add a blank element to the lspci_out.splitlines() list,
        # otherwise the last device is not evaluated as a cur_dev and ignored.
        lspci_list = lspci_out.splitlines()
        lspci_list.append("")
        for line in lspci_list:
            # check for record-separating empty lines
            if line == "":
                if cur_dev.get("Class", "").lower() in gpu_classes:
                    devs.append(cur_dev)
                cur_dev = {}
                continue
            if re.match(r"^\w+:\s+.*", line):
                key, val = line.split(":", 1)
                cur_dev[key.strip()] = val.strip()
            else:
                error = True
                log.debug("Unexpected lspci output: '%s'", line)

        if error:
            log.warning(
                "Error loading grains, unexpected linux_gpu_data output, "
                "check that you have a valid shell configured and "
                "permissions to run lspci command"
            )
    except OSError:
        pass

    gpus = []
    for gpu in devs:
        vendor_strings = re.split("[^A-Za-z0-9]", gpu["Vendor"].lower())
        # default vendor to 'unknown', overwrite if we match a known one
        vendor = "unknown"
        for name in known_vendors:
            # search for an 'expected' vendor name in the list of strings
            if name in vendor_strings:
                vendor = name
                break
        gpus.append({"vendor": vendor, "model": gpu["Device"]})

    grains = {}
    grains["num_gpus"] = len(gpus)
    grains["gpus"] = gpus
    return grains


def _netbsd_gpu_data():
    """
    num_gpus: int
    gpus:
      - vendor: nvidia|amd|ati|...
        model: string
    """
    known_vendors = [
        "nvidia",
        "amd",
        "ati",
        "intel",
        "cirrus logic",
        "vmware",
        "matrox",
        "aspeed",
    ]

    gpus = []
    try:
        pcictl_out = __salt__["cmd.run"]("pcictl pci0 list")

        for line in pcictl_out.splitlines():
            for vendor in known_vendors:
                vendor_match = re.match(
                    rf"[0-9:]+ ({vendor}) (.+) \(VGA .+\)", line, re.IGNORECASE
                )
                if vendor_match:
                    gpus.append(
                        {
                            "vendor": vendor_match.group(1),
                            "model": vendor_match.group(2),
                        }
                    )
    except OSError:
        pass

    grains = {}
    grains["num_gpus"] = len(gpus)
    grains["gpus"] = gpus
    return grains


def _osx_gpudata():
    """
    num_gpus: int
    gpus:
      - vendor: nvidia|amd|ati|...
        model: string
    """

    gpus = []
    try:
        pcictl_out = __salt__["cmd.run"]("system_profiler SPDisplaysDataType")

        for line in pcictl_out.splitlines():
            fieldname, _, fieldval = line.partition(": ")
            if fieldname.strip() == "Chipset Model":
                vendor, _, model = fieldval.partition(" ")
                vendor = vendor.lower()
                gpus.append({"vendor": vendor, "model": model})

    except OSError:
        pass

    grains = {}
    grains["num_gpus"] = len(gpus)
    grains["gpus"] = gpus
    return grains


def _bsd_cpudata(osdata):
    """
    Return CPU information for BSD-like systems
    """
    # Provides:
    #   cpuarch
    #   num_cpus
    #   cpu_model
    #   cpu_flags
    sysctl = salt.utils.path.which("sysctl")
    arch = salt.utils.path.which("arch")
    cmds = {}

    if sysctl:
        cmds.update(
            {
                "num_cpus": f"{sysctl} -n hw.ncpu",
                "cpuarch": f"{sysctl} -n hw.machine",
                "cpu_model": f"{sysctl} -n hw.model",
            }
        )

    if arch and osdata["kernel"] == "OpenBSD":
        cmds["cpuarch"] = f"{arch} -s"

    if osdata["kernel"] == "Darwin":
        cmds["cpu_model"] = f"{sysctl} -n machdep.cpu.brand_string"
        cmds["cpu_flags"] = f"{sysctl} -n machdep.cpu.features"

    grains = {k: __salt__["cmd.run"](v) for k, v in cmds.items()}

    if "cpu_flags" in grains and isinstance(grains["cpu_flags"], str):
        grains["cpu_flags"] = grains["cpu_flags"].split(" ")

    if osdata["kernel"] == "NetBSD":
        grains["cpu_flags"] = []
        for line in __salt__["cmd.run"]("cpuctl identify 0").splitlines():
            cpu_match = re.match(r"cpu[0-9]:\ features[0-9]?\ .+<(.+)>", line)
            if cpu_match:
                flag = cpu_match.group(1).split(",")
                grains["cpu_flags"].extend(flag)

    if osdata["kernel"] == "FreeBSD" and os.path.isfile("/var/run/dmesg.boot"):
        grains["cpu_flags"] = []
        # TODO: at least it needs to be tested for BSD other then FreeBSD
        with salt.utils.files.fopen("/var/run/dmesg.boot", "r") as _fp:
            cpu_here = False
            for line in _fp:
                if line.startswith("CPU: "):
                    cpu_here = True  # starts CPU descr
                    continue
                if cpu_here:
                    if not line.startswith(" "):
                        break  # game over
                    if "Features" in line:
                        start = line.find("<")
                        end = line.find(">")
                        if start > 0 and end > 0:
                            flag = line[start + 1 : end].split(",")
                            grains["cpu_flags"].extend(flag)
    try:
        grains["num_cpus"] = int(grains["num_cpus"])
    except ValueError:
        grains["num_cpus"] = 1

    return grains


def _sunos_cpudata():  # pragma: no cover
    """
    Return the CPU information for Solaris-like systems
    """
    # Provides:
    #   cpuarch
    #   num_cpus
    #   cpu_model
    #   cpu_flags
    grains = {}
    grains["cpu_flags"] = []

    grains["cpuarch"] = __salt__["cmd.run"]("isainfo -k")
    psrinfo = "/usr/sbin/psrinfo 2>/dev/null"
    grains["num_cpus"] = len(
        __salt__["cmd.run"](psrinfo, python_shell=True).splitlines()
    )
    kstat_info = "kstat -p cpu_info:*:*:brand"
    for line in __salt__["cmd.run"](kstat_info).splitlines():
        match = re.match(r"(\w+:\d+:\w+\d+:\w+)\s+(.+)", line)
        if match:
            grains["cpu_model"] = match.group(2)
    isainfo = "isainfo -n -v"
    for line in __salt__["cmd.run"](isainfo).splitlines():
        match = re.match(r"^\s+(.+)", line)
        if match:
            cpu_flags = match.group(1).split()
            grains["cpu_flags"].extend(cpu_flags)

    return grains


def _aix_cpudata():  # pragma: no cover
    """
    Return CPU information for AIX systems
    """
    # Provides:
    #   cpuarch
    #   num_cpus
    #   cpu_model
    #   cpu_flags
    grains = {}
    cmd = salt.utils.path.which("prtconf")
    if cmd:
        data = __salt__["cmd.run"](f"{cmd}") + os.linesep
        for dest, regstring in (
            ("cpuarch", r"(?im)^\s*Processor\s+Type:\s+(\S+)"),
            ("cpu_flags", r"(?im)^\s*Processor\s+Version:\s+(\S+)"),
            ("cpu_model", r"(?im)^\s*Processor\s+Implementation\s+Mode:\s+(.*)"),
            ("num_cpus", r"(?im)^\s*Number\s+Of\s+Processors:\s+(\S+)"),
        ):
            for regex in [re.compile(r) for r in [regstring]]:
                res = regex.search(data)
                if res and len(res.groups()) >= 1:
                    grains[dest] = res.group(1).strip().replace("'", "")
    else:
        log.error("The 'prtconf' binary was not found in $PATH.")
    return grains


def _linux_memdata():
    """
    Return the memory information for Linux-like systems
    """
    grains = {"mem_total": 0, "swap_total": 0}

    meminfo = "/proc/meminfo"
    if os.path.isfile(meminfo):
        with salt.utils.files.fopen(meminfo, "r") as ifile:
            for line in ifile:
                comps = line.rstrip("\n").split(":")
                if not len(comps) > 1:
                    continue
                if comps[0].strip() == "MemTotal":
                    # Use floor division to force output to be an integer
                    grains["mem_total"] = int(comps[1].split()[0]) // 1024
                if comps[0].strip() == "SwapTotal":
                    # Use floor division to force output to be an integer
                    grains["swap_total"] = int(comps[1].split()[0]) // 1024
    return grains


def _osx_memdata():
    """
    Return the memory information for BSD-like systems
    """
    grains = {"mem_total": 0, "swap_total": 0}

    sysctl = salt.utils.path.which("sysctl")
    if sysctl:
        mem = __salt__["cmd.run"](f"{sysctl} -n hw.memsize")
        swap_total = (
            __salt__["cmd.run"](f"{sysctl} -n vm.swapusage")
            .split()[2]
            .replace(",", ".")
        )
        if swap_total.endswith("K"):
            _power = 2**10
        elif swap_total.endswith("M"):
            _power = 2**20
        elif swap_total.endswith("G"):
            _power = 2**30
        swap_total = float(swap_total[:-1]) * _power

        grains["mem_total"] = int(mem) // 1024 // 1024
        grains["swap_total"] = int(swap_total) // 1024 // 1024
    return grains


def _bsd_memdata(osdata):
    """
    Return the memory information for BSD-like systems
    """
    grains = {"mem_total": 0, "swap_total": 0}

    sysctl = salt.utils.path.which("sysctl")
    if sysctl:
        mem = __salt__["cmd.run"](f"{sysctl} -n hw.physmem")
        if osdata["kernel"] == "NetBSD" and mem.startswith("-"):
            mem = __salt__["cmd.run"](f"{sysctl} -n hw.physmem64")
        grains["mem_total"] = int(mem) // 1024 // 1024

        if osdata["kernel"] in ["OpenBSD", "NetBSD"]:
            swapctl = salt.utils.path.which("swapctl")
            swap_data = __salt__["cmd.run"](f"{swapctl} -sk")
            if swap_data == "no swap devices configured":
                swap_total = 0
            else:
                swap_total = swap_data.split(" ")[1]
        else:
            swap_total = __salt__["cmd.run"](f"{sysctl} -n vm.swap_total")
        grains["swap_total"] = int(swap_total) // 1024 // 1024
    return grains


def _sunos_memdata():  # pragma: no cover
    """
    Return the memory information for SunOS-like systems
    """
    grains = {"mem_total": 0, "swap_total": 0}

    prtconf = "/usr/sbin/prtconf 2>/dev/null"
    for line in __salt__["cmd.run"](prtconf, python_shell=True).splitlines():
        comps = line.split(" ")
        if comps[0].strip() == "Memory" and comps[1].strip() == "size:":
            grains["mem_total"] = int(comps[2].strip())

    swap_cmd = salt.utils.path.which("swap")
    swap_data = __salt__["cmd.run"](f"{swap_cmd} -s").split()
    try:
        swap_avail = int(swap_data[-2][:-1])
        swap_used = int(swap_data[-4][:-1])
        swap_total = (swap_avail + swap_used) // 1024
    except ValueError:
        swap_total = None
    grains["swap_total"] = swap_total
    return grains


def _aix_memdata():  # pragma: no cover
    """
    Return the memory information for AIX systems
    """
    grains = {"mem_total": 0, "swap_total": 0}
    prtconf = salt.utils.path.which("prtconf")
    if prtconf:
        for line in __salt__["cmd.run"](prtconf, python_shell=True).splitlines():
            comps = [x for x in line.strip().split(" ") if x]
            if len(comps) > 2 and "Memory" in comps[0] and "Size" in comps[1]:
                grains["mem_total"] = int(comps[2])
                break
    else:
        log.error("The 'prtconf' binary was not found in $PATH.")

    swap_cmd = salt.utils.path.which("swap")
    if swap_cmd:
        swap_data = __salt__["cmd.run"](f"{swap_cmd} -s").split()
        try:
            swap_total = (int(swap_data[-2]) + int(swap_data[-6])) * 4
        except ValueError:
            swap_total = None
        grains["swap_total"] = swap_total
    else:
        log.error("The 'swap' binary was not found in $PATH.")
    return grains


def _windows_memdata():
    """
    Return the memory information for Windows systems
    """
    grains = {"mem_total": 0}
    # get the Total Physical memory as reported by msinfo32
    tot_bytes = win32api.GlobalMemoryStatusEx()["TotalPhys"]
    # return memory info in gigabytes
    grains["mem_total"] = int(tot_bytes / (1024**2))
    return grains


def _memdata(osdata):
    """
    Gather information about the system memory
    """
    # Provides:
    #   mem_total
    #   swap_total, for supported systems.
    grains = {"mem_total": 0}
    if osdata["kernel"] == "Linux":
        grains.update(_linux_memdata())
    elif osdata["kernel"] in ("FreeBSD", "OpenBSD", "NetBSD"):
        grains.update(_bsd_memdata(osdata))
    elif osdata["kernel"] == "Darwin":
        grains.update(_osx_memdata())
    elif osdata["kernel"] == "SunOS":  # pragma: no cover
        grains.update(_sunos_memdata())  # pragma: no cover
    elif osdata["kernel"] == "AIX":  # pragma: no cover
        grains.update(_aix_memdata())  # pragma: no cover
    elif osdata["kernel"] == "Windows" and HAS_WMI:
        grains.update(_windows_memdata())
    return grains


def _aix_get_machine_id():  # pragma: no cover
    """
    Parse the output of lsattr -El sys0 for os_uuid
    """
    grains = {}
    cmd = salt.utils.path.which("lsattr")
    if cmd:
        data = __salt__["cmd.run"](f"{cmd} -El sys0") + os.linesep
        uuid_regexes = [re.compile(r"(?im)^\s*os_uuid\s+(\S+)\s+(.*)")]
        for regex in uuid_regexes:
            res = regex.search(data)
            if res and len(res.groups()) >= 1:
                grains["machine_id"] = res.group(1).strip()
                break
    else:
        log.error("The 'lsattr' binary was not found in $PATH.")
    return grains


def _windows_virtual(osdata):
    """
    Returns what type of virtual hardware is under the hood, kvm or physical
    """
    # Provides:
    #   virtual
    #   virtual_subtype
    grains = dict()
    if osdata["kernel"] != "Windows":
        return grains

    # Set the default virtual environment to physical, meaning not a VM
    grains["virtual"] = "physical"

    # It is possible that the 'manufacturer' and/or 'productname' grains exist
    # but have a value of None
    manufacturer = osdata.get("manufacturer", "")
    if manufacturer is None:
        manufacturer = ""
    product_name = osdata.get("productname", "")
    if product_name is None:
        product_name = ""
    bios_string = osdata.get("biosstring", "")
    if bios_string is None:
        bios_string = ""

    if "QEMU" in manufacturer:
        # FIXME: Make this detect between kvm or qemu
        grains["virtual"] = "kvm"
    elif "VRTUAL" in bios_string:  # (not a typo)
        grains["virtual"] = "HyperV"
    elif "A M I" in bios_string:
        grains["virtual"] = "VirtualPC"
    elif "Xen" in bios_string:
        grains["virtual"] = "Xen"
        if "HVM domU" in product_name:
            grains["virtual_subtype"] = "HVM domU"
    elif "AMAZON" in bios_string:
        grains["virtual"] = "EC2"
    elif "Bochs" in manufacturer:
        grains["virtual"] = "kvm"
    # Product Name: (oVirt) www.ovirt.org
    # Red Hat Community virtualization Project based on kvm
    elif "oVirt" in product_name:
        grains["virtual"] = "kvm"
        grains["virtual_subtype"] = "oVirt"
    # Red Hat Enterprise Virtualization
    elif "RHEV Hypervisor" in product_name:
        grains["virtual"] = "kvm"
        grains["virtual_subtype"] = "rhev"
    # Product Name: VirtualBox
    elif "VirtualBox" in product_name:
        grains["virtual"] = "VirtualBox"
    # Product Name: VMware Virtual Platform
    elif "VMware" in product_name:
        grains["virtual"] = "VMware"
    # Manufacturer: Microsoft Corporation
    # Product Name: Virtual Machine
    elif "Microsoft" in manufacturer and "Virtual Machine" in product_name:
        grains["virtual"] = "VirtualPC"
    elif "OpenStack" in product_name:
        grains["virtual"] = "OpenStack"
    # Manufacturer: Parallels Software International Inc.
    elif "Parallels" in manufacturer:
        grains["virtual"] = "Parallels"
    # Apache CloudStack
    elif "CloudStack KVM Hypervisor" in product_name:
        grains["virtual"] = "kvm"
        grains["virtual_subtype"] = "cloudstack"
    return grains


def _virtual(osdata):
    """
    Returns what type of virtual hardware is under the hood, kvm or physical
    """
    # This is going to be a monster, if you are running a vm you can test this
    # grain with please submit patches!
    # Provides:
    #   virtual
    #   virtual_subtype

    grains = {"virtual": osdata.get("virtual", "physical")}

    # Skip the below loop on platforms which have none of the desired cmds
    # This is a temporary measure until we can write proper virtual hardware
    # detection.
    skip_cmds = ("AIX",)

    # list of commands to be executed to determine the 'virtual' grain
    _cmds = ["systemd-detect-virt", "virt-what", "dmidecode"]
    # test first for virt-what, which covers most of the desired functionality
    # on most platforms
    if not salt.utils.platform.is_windows() and osdata["kernel"] not in skip_cmds:
        if salt.utils.path.which("virt-what"):
            _cmds = ["virt-what"]

    # Check if enable_lspci is True or False
    if __opts__.get("enable_lspci", True) is True:
        # /proc/bus/pci does not exists, lspci will fail
        if os.path.exists("/proc/bus/pci"):
            _cmds += ["lspci"]

    # Add additional last resort commands
    if osdata["kernel"] in skip_cmds:
        _cmds = ()

    # Quick backout for BrandZ (Solaris LX Branded zones)
    # Don't waste time trying other commands to detect the virtual grain
    if (
        HAS_UNAME
        and osdata["kernel"] == "Linux"
        and "BrandZ virtual linux" in os.uname()
    ):
        grains["virtual"] = "zone"
        return grains

    failed_commands = set()
    for command in _cmds:
        args = []
        if osdata["kernel"] == "Darwin":
            command = "system_profiler"
            args = ["SPDisplaysDataType"]
        elif osdata["kernel"] == "SunOS":
            virtinfo = salt.utils.path.which("virtinfo")
            if virtinfo:
                try:
                    ret = __salt__["cmd.run_all"](virtinfo)
                except salt.exceptions.CommandExecutionError:
                    failed_commands.add(virtinfo)
                else:
                    if ret["stdout"].endswith("not supported"):
                        command = "prtdiag"
                    else:
                        command = "virtinfo"
                        args.append("-c current list -H -o name")
            else:
                command = "prtdiag"

        cmd = salt.utils.path.which(command)

        if not cmd:
            continue

        cmd = "{} {}".format(cmd, " ".join(args))

        try:
            ret = __salt__["cmd.run_all"](cmd)

            if ret["retcode"] > 0:
                # systemd-detect-virt always returns > 0 on non-virtualized
                # systems
                # prtdiag only works in the global zone, skip if it fails
                if (
                    salt.utils.platform.is_windows()
                    or "systemd-detect-virt" in cmd
                    or "prtdiag" in cmd
                ):
                    continue
                failed_commands.add(command)
                continue
        except salt.exceptions.CommandExecutionError:
            if salt.utils.platform.is_windows():
                continue
            failed_commands.add(command)
            continue

        output = ret["stdout"]
        if command == "system_profiler":
            macoutput = output.lower()
            if "0x1ab8" in macoutput:
                grains["virtual"] = "Parallels"
            if "parallels" in macoutput:
                grains["virtual"] = "Parallels"
            if "vmware" in macoutput:
                grains["virtual"] = "VMware"
            if "0x15ad" in macoutput:
                grains["virtual"] = "VMware"
            if "virtualbox" in macoutput:
                grains["virtual"] = "VirtualBox"
            # Break out of the loop so the next log message is not issued
            break
        elif command == "systemd-detect-virt":
            if output in (
                "qemu",
                "kvm",
                "oracle",
                "xen",
                "bochs",
                "chroot",
                "uml",
                "systemd-nspawn",
            ):
                grains["virtual"] = output
                break
            elif "vmware" in output:
                grains["virtual"] = "VMware"
                break
            elif "microsoft" in output:
                grains["virtual"] = "VirtualPC"
                break
            elif "lxc" in output:
                grains["virtual"] = "container"
                grains["virtual_subtype"] = "LXC"
                break
            elif "podman" in output:
                grains["virtual"] = "container"
                grains["virtual_subtype"] = "Podman"
                break
            elif "docker" in output:
                grains["virtual"] = "container"
                grains["virtual_subtype"] = "Docker"
                break
            elif "amazon" in output:
                grains["virtual"] = "Nitro"
                grains["virtual_subtype"] = "Amazon EC2"
                break
        elif command == "virt-what":
            for line in output.splitlines():
                if line in ("kvm", "qemu", "uml", "xen"):
                    grains["virtual"] = line
                    break
                elif "lxc" in line:
                    grains["virtual"] = "container"
                    grains["virtual_subtype"] = "LXC"
                    break
                elif "docker" in line:
                    grains["virtual"] = "container"
                    grains["virtual_subtype"] = "Docker"
                    break
                elif "vmware" in line:
                    grains["virtual"] = "VMware"
                    break
                elif "parallels" in line:
                    grains["virtual"] = "Parallels"
                    break
                elif "hyperv" in line:
                    grains["virtual"] = "HyperV"
                    break
                elif line == "ibm_power-kvm":
                    grains["virtual"] = "kvm"
                    break
                elif line == "ibm_power-lpar_shared":
                    grains["virtual"] = "LPAR"
                    grains["virtual_subtype"] = "shared"
                    break
                elif line == "ibm_power-lpar_dedicated":
                    grains["virtual"] = "LPAR"
                    grains["virtual_subtype"] = "dedicated"
                    break
            break
        elif command == "dmidecode":
            # Product Name: VirtualBox
            if "Vendor: QEMU" in output:
                # FIXME: Make this detect between kvm or qemu
                grains["virtual"] = "kvm"
            if "Manufacturer: QEMU" in output:
                grains["virtual"] = "kvm"
            if "Vendor: Bochs" in output:
                grains["virtual"] = "kvm"
            if "Manufacturer: Bochs" in output:
                grains["virtual"] = "kvm"
            if "BHYVE" in output:
                grains["virtual"] = "bhyve"
            # Product Name: (oVirt) www.ovirt.org
            # Red Hat Community virtualization Project based on kvm
            elif "Manufacturer: oVirt" in output:
                grains["virtual"] = "kvm"
                grains["virtual_subtype"] = "ovirt"
            # Red Hat Enterprise Virtualization
            elif "Product Name: RHEV Hypervisor" in output:
                grains["virtual"] = "kvm"
                grains["virtual_subtype"] = "rhev"
            elif "VirtualBox" in output:
                grains["virtual"] = "VirtualBox"
            # Product Name: VMware Virtual Platform
            elif "VMware" in output:
                grains["virtual"] = "VMware"
            # Manufacturer: Microsoft Corporation
            # Product Name: Virtual Machine
            elif ": Microsoft" in output and "Virtual Machine" in output:
                grains["virtual"] = "VirtualPC"
            # Manufacturer: Parallels Software International Inc.
            elif "Parallels Software" in output:
                grains["virtual"] = "Parallels"
            elif "Manufacturer: Google" in output:
                grains["virtual"] = "kvm"
            # Proxmox KVM
            elif "Vendor: SeaBIOS" in output:
                grains["virtual"] = "kvm"
            # Break out of the loop, lspci parsing is not necessary
            break
        elif command == "lspci":
            # dmidecode not available or the user does not have the necessary
            # permissions
            model = output.lower()
            if "vmware" in model:
                grains["virtual"] = "VMware"
            # 00:04.0 System peripheral: InnoTek Systemberatung GmbH
            #         VirtualBox Guest Service
            elif "virtualbox" in model:
                grains["virtual"] = "VirtualBox"
            elif "qemu" in model:
                grains["virtual"] = "kvm"
            elif "virtio" in model:
                grains["virtual"] = "kvm"
            # Break out of the loop so the next log message is not issued
            break
        elif command == "prtdiag":
            model = output.lower().split("\n")[0]
            if "vmware" in model:
                grains["virtual"] = "VMware"
            elif "virtualbox" in model:
                grains["virtual"] = "VirtualBox"
            elif "qemu" in model:
                grains["virtual"] = "kvm"
            elif "joyent smartdc hvm" in model:
                grains["virtual"] = "kvm"
            break
        elif command == "virtinfo":
            if output == "logical-domain":
                grains["virtual"] = "LDOM"
                roles = []
                for role in ("control", "io", "root", "service"):
                    subtype_cmd = "{} -c current get -H -o value {}-role".format(
                        command, role
                    )
                    ret = __salt__["cmd.run"](f"{subtype_cmd}")
                    if ret == "true":
                        roles.append(role)
                if roles:
                    grains["virtual_subtype"] = roles
            elif output == "non-global-zone":
                grains["virtual"] = "zone"
                grains["virtual_subtype"] = "non-global"
            elif output == "kernel-zone":
                grains["virtual"] = "zone"
                grains["virtual_subtype"] = "kernel"
            elif output == "vmware":
                grains["virtual"] = "VMware"
            break

    choices = ("Linux", "HP-UX")
    isdir = os.path.isdir
    sysctl = salt.utils.path.which("sysctl")
    if osdata["kernel"] in choices:
        if os.path.isdir("/proc"):
            try:
                self_root = os.stat("/")
                init_root = os.stat("/proc/1/root/.")
                if self_root != init_root:
                    grains["virtual_subtype"] = "chroot"
            except OSError:
                pass
        if isdir("/proc/vz"):
            if os.path.isfile("/proc/vz/version"):
                grains["virtual"] = "openvzhn"
            elif os.path.isfile("/proc/vz/veinfo"):
                grains["virtual"] = "openvzve"
                # a posteriori, it's expected for these to have failed:
                failed_commands.discard("lspci")
                failed_commands.discard("dmidecode")
        # Provide additional detection for OpenVZ
        if os.path.isfile("/proc/self/status"):
            with salt.utils.files.fopen("/proc/self/status") as status_file:
                vz_re = re.compile(r"^envID:\s+(\d+)$")
                for line in status_file:
                    vz_match = vz_re.match(line.rstrip("\n"))
                    if vz_match and int(vz_match.groups()[0]) != 0:
                        grains["virtual"] = "openvzve"
                    elif vz_match and int(vz_match.groups()[0]) == 0:
                        grains["virtual"] = "openvzhn"
        if isdir("/proc/sys/xen") or isdir("/sys/bus/xen") or isdir("/proc/xen"):
            if os.path.isfile("/proc/xen/xsd_kva"):
                # Tested on CentOS 5.3 / 2.6.18-194.26.1.el5xen
                # Tested on CentOS 5.4 / 2.6.18-164.15.1.el5xen
                grains["virtual_subtype"] = "Xen Dom0"
            else:
                if osdata.get("productname", "") == "HVM domU":
                    # Requires dmidecode!
                    grains["virtual_subtype"] = "Xen HVM DomU"
                elif os.path.isfile("/proc/xen/capabilities") and os.access(
                    "/proc/xen/capabilities", os.R_OK
                ):
                    with salt.utils.files.fopen("/proc/xen/capabilities") as fhr:
                        if "control_d" not in fhr.read():
                            # Tested on CentOS 5.5 / 2.6.18-194.3.1.el5xen
                            grains["virtual_subtype"] = "Xen PV DomU"
                        else:
                            # Shouldn't get to this, but just in case
                            grains["virtual_subtype"] = "Xen Dom0"
                # Tested on Fedora 10 / 2.6.27.30-170.2.82 with xen
                # Tested on Fedora 15 / 2.6.41.4-1 without running xen
                elif isdir("/sys/bus/xen"):
                    if os.path.isdir("/sys/bus/xen/drivers/xenconsole"):
                        # An actual DomU will have the xenconsole driver
                        grains["virtual_subtype"] = "Xen PV DomU"
                    elif "xen:" in __salt__["cmd.run"]("dmesg").lower():
                        # Fallback to parsing dmesg, might not be successful
                        grains["virtual_subtype"] = "Xen PV DomU"
            # If a Dom0 or DomU was detected, obviously this is xen
            if "dom" in grains.get("virtual_subtype", "").lower():
                grains["virtual"] = "xen"
        if os.path.isfile("/proc/cpuinfo"):
            with salt.utils.files.fopen("/proc/cpuinfo", "r") as fhr:
                if "QEMU Virtual CPU" in fhr.read():
                    grains["virtual"] = "kvm"
        if os.path.isfile("/sys/devices/virtual/dmi/id/product_name"):
            try:
                with salt.utils.files.fopen(
                    "/sys/devices/virtual/dmi/id/product_name", "rb"
                ) as fhr:
                    output = salt.utils.stringutils.to_unicode(
                        fhr.read(), errors="replace"
                    )
                    if "VirtualBox" in output:
                        grains["virtual"] = "VirtualBox"
                    elif "RHEV Hypervisor" in output:
                        grains["virtual"] = "kvm"
                        grains["virtual_subtype"] = "rhev"
                    elif "oVirt Node" in output:
                        grains["virtual"] = "kvm"
                        grains["virtual_subtype"] = "ovirt"
                    elif "Google" in output:
                        grains["virtual"] = "gce"
                    elif "BHYVE" in output:
                        grains["virtual"] = "bhyve"
            except UnicodeDecodeError:
                # Some firmwares provide non-valid 'product_name'
                # files, ignore them
                log.debug(
                    "The content in /sys/devices/virtual/dmi/id/product_name is not"
                    " valid"
                )
            except OSError:
                pass
        # Check container type after hypervisors, to avoid variable overwrite on containers running in virtual environment.
        if os.path.isfile("/proc/1/cgroup"):
            try:
                with salt.utils.files.fopen("/proc/1/cgroup", "r") as fhr:
                    fhr_contents = fhr.read()
                if ":/lxc/" in fhr_contents:
                    grains["virtual"] = "container"
                    grains["virtual_subtype"] = "LXC"
                elif ":/kubepods/" in fhr_contents:
                    grains["virtual_subtype"] = "kubernetes"
                elif ":/libpod_parent/" in fhr_contents:
                    grains["virtual_subtype"] = "libpod"
                else:
                    if any(
                        x in fhr_contents
                        for x in (":/system.slice/docker", ":/docker/", ":/docker-ce/")
                    ):
                        grains["virtual"] = "container"
                        grains["virtual_subtype"] = "Docker"
            except OSError:
                pass
        # Newer versions of LXC didn't have "lxc" in /proc/1/cgroup. Check environ
        if ("virtual_subtype" not in grains) or (grains["virtual_subtype"] != "LXC"):
            if os.path.isfile("/proc/1/environ"):
                try:
                    with salt.utils.files.fopen(
                        "/proc/1/environ", "r", errors="ignore"
                    ) as fhr:
                        fhr_contents = fhr.read()
                    if "container=lxc" in fhr_contents:
                        grains["virtual"] = "container"
                        grains["virtual_subtype"] = "LXC"
                except OSError:
                    pass
    elif osdata["kernel"] == "FreeBSD":
        kenv = salt.utils.path.which("kenv")
        if kenv:
            product = __salt__["cmd.run"](f"{kenv} smbios.system.product")
            maker = __salt__["cmd.run"](f"{kenv} smbios.system.maker")
            if product.startswith("VMware"):
                grains["virtual"] = "VMware"
            if product.startswith("VirtualBox"):
                grains["virtual"] = "VirtualBox"
            if maker.startswith("Xen"):
                grains["virtual_subtype"] = f"{maker} {product}"
                grains["virtual"] = "xen"
            if maker.startswith("Microsoft") and product.startswith("Virtual"):
                grains["virtual"] = "VirtualPC"
            if maker.startswith("OpenStack"):
                grains["virtual"] = "OpenStack"
            if maker.startswith("Bochs"):
                grains["virtual"] = "kvm"
            if maker.startswith("Amazon EC2"):
                grains["virtual"] = "Nitro"
        if sysctl:
            hv_vendor = __salt__["cmd.run"](f"{sysctl} -n hw.hv_vendor")
            model = __salt__["cmd.run"](f"{sysctl} -n hw.model")
            jail = __salt__["cmd.run"](f"{sysctl} -n security.jail.jailed")
            if "bhyve" in hv_vendor:
                grains["virtual"] = "bhyve"
            elif "QEMU Virtual CPU" in model:
                grains["virtual"] = "kvm"
            if jail == "1":
                grains["virtual_subtype"] = "jail"
    elif osdata["kernel"] == "OpenBSD":
        if "manufacturer" in osdata:
            if osdata["manufacturer"] in ["QEMU", "Red Hat", "Joyent"]:
                grains["virtual"] = "kvm"
            if osdata["manufacturer"] == "OpenBSD":
                grains["virtual"] = "vmm"
    elif osdata["kernel"] == "NetBSD":
        if sysctl:
            if "QEMU Virtual CPU" in __salt__["cmd.run"](
                f"{sysctl} -n machdep.cpu_brand"
            ):
                grains["virtual"] = "kvm"
            elif "invalid" not in __salt__["cmd.run"](
                f"{sysctl} -n machdep.xen.suspend"
            ):
                grains["virtual"] = "Xen PV DomU"
            elif "VMware" in __salt__["cmd.run"](
                f"{sysctl} -n machdep.dmi.system-vendor"
            ):
                grains["virtual"] = "VMware"
            # NetBSD has Xen dom0 support
            elif __salt__["cmd.run"](f"{sysctl} -n machdep.idle-mechanism") == "xen":
                if os.path.isfile("/var/run/xenconsoled.pid"):
                    grains["virtual_subtype"] = "Xen Dom0"
    elif osdata["kernel"] == "SunOS":
        # we did not get any data from virtinfo or prtdiag
        # check the zonename here as fallback
        zonename = salt.utils.path.which("zonename")
        if zonename:
            zone = __salt__["cmd.run"](f"{zonename}")
            if zone != "global":
                grains["virtual"] = "zone"

        # last ditch efford to check the brand identifier
        elif os.path.isdir("/.SUNWnative"):
            grains["virtual"] = "zone"

    # If we have a virtual_subtype, we're virtual, but maybe we couldn't
    # figure out what specific virtual type we were?
    if grains.get("virtual_subtype") and grains["virtual"] == "physical":
        grains["virtual"] = "virtual"

    # Try to detect if the instance is running on Amazon EC2
    if grains["virtual"] in ("qemu", "kvm", "xen", "amazon"):
        dmidecode = salt.utils.path.which("dmidecode")
        if dmidecode:
            ret = __salt__["cmd.run_all"](
                [dmidecode, "-t", "system"], ignore_retcode=True
            )
            output = ret["stdout"]
            if "Manufacturer: Amazon EC2" in output:
                if grains["virtual"] != "xen":
                    grains["virtual"] = "Nitro"
                grains["virtual_subtype"] = "Amazon EC2"
                product = re.match(
                    r".*Product Name: ([^\r\n]*).*", output, flags=re.DOTALL
                )
                if product:
                    grains["virtual_subtype"] = f"Amazon EC2 ({product[1]})"
            elif re.match(r".*Version: [^\r\n]+\.amazon.*", output, flags=re.DOTALL):
                grains["virtual_subtype"] = "Amazon EC2"

    for command in failed_commands:
        log.info(
            "Although '%s' was found in path, the current user "
            "cannot execute it. Grains output might not be "
            "accurate.",
            command,
            once=True,
        )
    return grains


def _virtual_hv(osdata):
    """
    Returns detailed hypervisor information from sysfs
    Currently this seems to be used only by Xen
    """
    grains = {}

    # Bail early if we're not running on Xen
    try:
        if "xen" not in osdata["virtual"]:
            return grains
    except KeyError:
        return grains

    # Try to get the exact hypervisor version from sysfs
    try:
        version = {}
        for fn in ("major", "minor", "extra"):
            with salt.utils.files.fopen(f"/sys/hypervisor/version/{fn}", "r") as fhr:
                version[fn] = salt.utils.stringutils.to_unicode(fhr.read().strip())
        grains["virtual_hv_version"] = "{}.{}{}".format(
            version["major"], version["minor"], version["extra"]
        )
        grains["virtual_hv_version_info"] = [
            version["major"],
            version["minor"],
            version["extra"],
        ]
    except (OSError, KeyError):
        pass

    # Try to read and decode the supported feature set of the hypervisor
    # Based on https://github.com/brendangregg/Misc/blob/master/xen/xen-features.py
    # Table data from include/xen/interface/features.h
    xen_feature_table = {
        0: "writable_page_tables",
        1: "writable_descriptor_tables",
        2: "auto_translated_physmap",
        3: "supervisor_mode_kernel",
        4: "pae_pgdir_above_4gb",
        5: "mmu_pt_update_preserve_ad",
        7: "gnttab_map_avail_bits",
        8: "hvm_callback_vector",
        9: "hvm_safe_pvclock",
        10: "hvm_pirqs",
        11: "dom0",
        12: "grant_map_identity",
        13: "memory_op_vnode_supported",
        14: "ARM_SMCCC_supported",
    }
    try:
        with salt.utils.files.fopen("/sys/hypervisor/properties/features", "r") as fhr:
            features = salt.utils.stringutils.to_unicode(fhr.read().strip())
        enabled_features = []
        for bit, feat in xen_feature_table.items():
            if int(features, 16) & (1 << bit):
                enabled_features.append(feat)
        grains["virtual_hv_features"] = features
        grains["virtual_hv_features_list"] = enabled_features
    except (OSError, KeyError):
        pass

    return grains


def _ps(osdata):
    """
    Return the ps grain
    """
    grains = {}
    bsd_choices = ("FreeBSD", "NetBSD", "OpenBSD", "MacOS")
    if osdata["os"] in bsd_choices:
        grains["ps"] = "ps auxwww"
    elif osdata["os_family"] == "Solaris":
        grains["ps"] = "/usr/ucb/ps auxwww"
    elif osdata["os"] == "Windows":
        grains["ps"] = "tasklist.exe"
    elif osdata.get("virtual", "") == "openvzhn":
        grains["ps"] = (
            'ps -fH -p $(grep -l "^envID:[[:space:]]*0\\$" '
            '/proc/[0-9]*/status | sed -e "s=/proc/\\([0-9]*\\)/.*=\\1=")  '
            "| awk '{ $7=\"\"; print }'"
        )
    elif osdata["os_family"] == "AIX":
        grains["ps"] = "/usr/bin/ps auxww"
    elif osdata["os_family"] == "NILinuxRT":
        grains["ps"] = "ps -o user,pid,ppid,tty,time,comm"
    else:
        grains["ps"] = "ps -efHww"
    return grains


def _clean_value(key, val):
    """
    Clean out well-known bogus values.
    If it isn't clean (for example has value 'None'), return None.
    Otherwise, return the original value.

    NOTE: This logic also exists in the smbios module. This function is
          for use when not using smbios to retrieve the value.
    """
    if val is None or not val or re.match("none", val, flags=re.IGNORECASE):
        return None
    elif "uuid" in key:
        # Try each version (1-5) of RFC4122 to check if it's actually a UUID
        for uuidver in range(1, 5):
            try:
                uuid.UUID(val, version=uuidver)
                return val
            except ValueError:
                continue
        log.trace("HW %s value %s is an invalid UUID", key, val.replace("\n", " "))
        return None
    elif re.search("serial|part|version", key):
        # 'To be filled by O.E.M.
        # 'Not applicable' etc.
        # 'Not specified' etc.
        # 0000000, 1234567 etc.
        # begone!
        if (
            re.match(r"^[0]+$", val)
            or re.match(r"[0]?1234567[8]?[9]?[0]?", val)
            or re.search(
                r"sernum|part[_-]?number|specified|filled|applicable",
                val,
                flags=re.IGNORECASE,
            )
        ):
            return None
    elif re.search("asset|manufacturer", key):
        # AssetTag0. Manufacturer04. Begone.
        if re.search(
            r"manufacturer|to be filled|available|asset|^no(ne|t)",
            val,
            flags=re.IGNORECASE,
        ):
            return None
    else:
        # map unspecified, undefined, unknown & whatever to None
        if re.search(r"to be filled", val, flags=re.IGNORECASE) or re.search(
            r"un(known|specified)|no(t|ne)?"
            r" (asset|provided|defined|available|present|specified)",
            val,
            flags=re.IGNORECASE,
        ):
            return None
    return val


def _windows_os_release_grain(caption, product_type):
    """
    helper function for getting the osrelease grain
    :return:
    """
    # This creates the osrelease grain based on the Windows Operating
    # System Product Name. As long as Microsoft maintains a similar format
    # this should be future proof
    version = "Unknown"
    release = ""
    if "Server" in caption:
        # Edge case here to handle MS Product that doesn't contain a year
        if re.match(
            r"^Microsoft[^\d]+(Server|Datacenter|Standard|Essentials)$", caption
        ):
            version = "2019"
        else:
            for item in caption.split(" "):
                # If it's all digits, then it's version
                if re.match(r"\d+", item):
                    version = item
                # If it starts with R and then numbers, it's the release
                # ie: R2
                if re.match(r"^R\d+$", item):
                    release = item
        os_release = f"{version}Server{release}"
    else:
        for item in caption.split(" "):
            # If it's a number, decimal number, Thin or Vista, then it's the
            # version
            if re.match(r"^(\d+(\.\d+)?)|Thin|Vista|XP$", item):
                version = item
        os_release = version

    # If the version is still Unknown, revert back to the old way of getting
    # the os_release
    # https://github.com/saltstack/salt/issues/52339
    if os_release in ["Unknown"]:
        os_release = platform.release()
        server = {
            "Vista": "2008Server",
            "7": "2008ServerR2",
            "8": "2012Server",
            "8.1": "2012ServerR2",
            "10": "2016Server",
        }

        # Starting with Python 2.7.12 and 3.5.2 the `platform.uname()`
        # function started reporting the Desktop version instead of the
        # Server version on # Server versions of Windows, so we need to look
        # those up. So, if you find a Server Platform that's a key in the
        # server dictionary, then lookup the actual Server Release.
        # (Product Type 1 is Desktop, Everything else is Server)
        if product_type > 1 and os_release in server:
            os_release = server[os_release]

    return os_release


def _windows_platform_data():
    """
    Use the platform module for as much as we can.
    """
    # Provides:
    #    kernelrelease
    #    kernelversion
    #    osversion
    #    osrelease
    #    osservicepack
    #    osmanufacturer
    #    manufacturer
    #    productname
    #    biosversion
    #    serialnumber
    #    osfullname
    #    timezone
    #    uuid
    #    windowsdomain
    #    windowsdomaintype
    #    motherboard.productname
    #    motherboard.serialnumber
    #    virtual

    if not HAS_WMI:
        return {}

    grains = {}
    with salt.utils.winapi.Com():
        wmi_c = wmi.WMI()
        try:
            # http://msdn.microsoft.com/en-us/library/windows/desktop/aa394102%28v=vs.85%29.aspx
            systeminfo = wmi_c.Win32_ComputerSystem()[0]
            grains.update(
                {
                    "manufacturer": _clean_value(
                        "manufacturer", systeminfo.Manufacturer
                    ),
                    "productname": _clean_value("productname", systeminfo.Model),
                }
            )
        except IndexError:
            grains.update({"manufacturer": None, "productname": None})
            log.warning("Computer System info not available on this system")

        try:
            # https://msdn.microsoft.com/en-us/library/aa394239(v=vs.85).aspx
            osinfo = wmi_c.Win32_OperatingSystem()[0]
            os_release = _windows_os_release_grain(
                caption=osinfo.Caption, product_type=osinfo.ProductType
            )
            grains.update(
                {
                    "kernelrelease": _clean_value("kernelrelease", osinfo.Version),
                    "osfullname": _clean_value("osfullname", osinfo.Caption),
                    "osmanufacturer": _clean_value(
                        "osmanufacturer", osinfo.Manufacturer
                    ),
                    "osrelease": _clean_value("osrelease", os_release),
                    "osversion": _clean_value("osversion", osinfo.Version),
                }
            )
        except IndexError:
            grains.update(
                {
                    "kernelrelease": None,
                    "osfullname": None,
                    "osmanufacturer": None,
                    "osrelease": None,
                    "osversion": None,
                }
            )
            log.warning("Operating System info not available on this system")

        try:
            # http://msdn.microsoft.com/en-us/library/windows/desktop/aa394077(v=vs.85).aspx
            biosinfo = wmi_c.Win32_BIOS()[0]
            grains.update(
                {
                    # bios name had a bunch of whitespace appended to it in my testing
                    # 'PhoenixBIOS 4.0 Release 6.0     '
                    "biosversion": _clean_value("biosversion", biosinfo.Name.strip()),
                    "biosstring": _clean_value("string", biosinfo.Version),
                    "serialnumber": _clean_value("serialnumber", biosinfo.SerialNumber),
                }
            )
        except IndexError:
            grains.update(
                {"biosstring": None, "biosversion": None, "serialnumber": None}
            )
            log.warning("BIOS info not available on this system")

        try:
            # http://msdn.microsoft.com/en-us/library/windows/desktop/aa394498(v=vs.85).aspx
            timeinfo = wmi_c.Win32_TimeZone()[0]
            grains.update(
                {
                    "timezone": _clean_value("timezone", timeinfo.Description),
                }
            )
        except IndexError:
            grains.update({"timezone": None})
            log.warning("TimeZone info not available on this system")

        try:
            # https://docs.microsoft.com/en-us/windows/win32/cimwin32prov/win32-computersystemproduct
            csproductinfo = wmi_c.Win32_ComputerSystemProduct()[0]
            grains.update(
                {
                    "uuid": _clean_value("uuid", csproductinfo.UUID.lower()),
                }
            )
        except IndexError:
            grains.update({"uuid": None})
            log.warning("Computer System Product info not available on this system")

        # http://msdn.microsoft.com/en-us/library/windows/desktop/aa394072(v=vs.85).aspx
        try:
            motherboardinfo = wmi_c.Win32_BaseBoard()[0]
            grains.update(
                {
                    "motherboard": {
                        "productname": _clean_value(
                            "motherboard.productname", motherboardinfo.Product
                        ),
                        "serialnumber": _clean_value(
                            "motherboard.serialnumber", motherboardinfo.SerialNumber
                        ),
                    },
                }
            )
        except IndexError:
            grains.update(
                {
                    "motherboard": {"productname": None, "serialnumber": None},
                }
            )
            log.debug("Motherboard info not available on this system")

        grains.update(
            {
                "kernelversion": _clean_value("kernelversion", platform.version()),
            }
        )
        net_info = salt.utils.win_osinfo.get_join_info()
        grains.update(
            {
                "windowsdomain": _clean_value("windowsdomain", net_info["Domain"]),
                "windowsdomaintype": _clean_value(
                    "windowsdomaintype", net_info["DomainType"]
                ),
            }
        )

        info = salt.utils.win_osinfo.get_os_version_info()
        if info["ServicePackMajor"] > 0:
            service_pack = "".join(["SP", str(info["ServicePackMajor"])])
            grains.update(
                {
                    "osservicepack": _clean_value("osservicepack", service_pack),
                }
            )
        else:
            grains.update({"osservicepack": None})

    return grains


def _osx_platform_data():
    """
    Additional data for macOS systems
    Returns: A dictionary containing values for the following:
        - model_name
        - boot_rom_version
        - smc_version
        - system_serialnumber
    """
    cmd = "system_profiler SPHardwareDataType"
    hardware = __salt__["cmd.run"](cmd)

    grains = {}
    for line in hardware.splitlines():
        field_name, _, field_val = line.partition(": ")
        if field_name.strip() == "Model Name":
            key = "model_name"
            grains[key] = _clean_value(key, field_val)
        if field_name.strip() == "Boot ROM Version":
            key = "boot_rom_version"
            grains[key] = _clean_value(key, field_val)
        if field_name.strip() == "SMC Version (system)":
            key = "smc_version"
            grains[key] = _clean_value(key, field_val)
        if field_name.strip() == "Serial Number (system)":
            key = "system_serialnumber"
            grains[key] = _clean_value(key, field_val)

    return grains


def _linux_devicetree_platform_data():
    """
    Additional data for Linux Devicetree subsystem - https://www.kernel.org/doc/html/latest/devicetree/usage-model.html
    Returns: A dictionary containing values for the following:
        - manufacturer
        - produtname
        - serialnumber
    """

    def _read_dt_string(path):
        try:
            # /proc/device-tree should be used instead of /sys/firmware/devicetree/base
            # see https://github.com/torvalds/linux/blob/v5.13/Documentation/ABI/testing/sysfs-firmware-ofw#L14
            loc = f"/proc/device-tree/{path}"
            if os.path.isfile(loc):
                with salt.utils.files.fopen(loc, mode="r") as f:
                    return f.read().rstrip("\x00")  # all strings are null-terminated
        except Exception:  # pylint: disable=broad-except
            return None

        return None

    grains = {}

    model = _read_dt_string("model")
    if model:
        # Devicetree spec v0.3, section 2.3.2
        tmp = model.split(",", 1)
        if len(tmp) == 2:
            # format "manufacturer,model"
            grains["manufacturer"] = tmp[0]
            grains["productname"] = tmp[1]
        else:
            grains["productname"] = tmp[0]

    # not in specs, but observed on "Linux on Power" systems
    systemid = _read_dt_string("system-id")
    if systemid:
        grains["serialnumber"] = systemid

    # not in spec, but populated for ARM Linux - https://github.com/torvalds/linux/blob/master/arch/arm/kernel/setup.c#L961
    # as this is "more correct" naming, this should have priority over system-id
    serial = _read_dt_string("serial-number")
    if serial:
        grains["serialnumber"] = serial

    return grains


def id_():
    """
    Return the id
    """
    return {"id": __opts__.get("id", "")}


# Pattern for os-release PRETTY_NAME containing "name version (codename)"
_PRETTY_NAME_RE = re.compile(r"[^\d]+ (?P<version>\d[\d.+\-a-z]*) \((?P<codename>.+)\)")
# Pattern for os-release VERSION containing "version (codename)"
_VERSION_RE = re.compile(r"\d[\d.+\-a-z]* \((?P<codename>.+)\)")

_REPLACE_LINUX_RE = re.compile(r"\W(?:gnu/)?linux", re.IGNORECASE)

# This maps (at most) the first ten characters (no spaces, lowercased) of
# 'osfullname' to the 'os' grain that Salt traditionally uses, and is used by
# the os_data() function to create the "os" grain.
#
# If your system is not detecting the "os" grain properly, it likely needs an
# entry in this dictionary.
_OS_NAME_MAP = {
    "redhatente": "RedHat",
    "gentoobase": "Gentoo",
    "archarm": "Arch ARM",
    "arch": "Arch",
    "debian": "Debian",
    "Junos": "Junos",
    "raspbian": "Raspbian",
    "fedoraremi": "Fedora",
    "chapeau": "Chapeau",
    "korora": "Korora",
    "amazonami": "Amazon",
    "alt": "ALT",
    "enterprise": "OEL",
    "oracleserv": "OEL",
    "cloudserve": "CloudLinux",
    "cloudlinux": "CloudLinux",
    "almalinux": "AlmaLinux",
    "pidora": "Fedora",
    "scientific": "ScientificLinux",
    "synology": "Synology",
    "nilrt": "NILinuxRT",
    "poky": "Poky",
    "manjaro": "Manjaro",
    "manjarolin": "Manjaro",
    "univention": "Univention",
    "antergos": "Antergos",
    "sles": "SUSE",
    "void": "Void",
    "slesexpand": "RES",
    "linuxmint": "Mint",
    "neon": "KDE neon",
    "pop": "Pop",
    "rocky": "Rocky",
    "alibabaclo": "Alinux",
    "mendel": "Mendel",
}

# This dictionary maps the pair of os-release ID and NAME to the 'os' grain
# that Salt traditionally uses, and is used by the os_data() function to
# create the "os" grain.
#
# Add entries to this dictionary to retain historic values of the "os" grain.
_ID_AND_NAME_TO_OS_NAME_MAP = {
    ("astra", "Astra Linux (Orel)"): "AstraLinuxCE",
    ("astra", "Astra Linux (Smolensk)"): "AstraLinuxSE",
    ("pop", "Pop!_OS"): "Pop",
}


def _derive_os_grain(osfullname, os_id=None):
    """
    Derive the 'os' grain from the 'osfullname' grain

    For deriving the 'os' grain from the os-release data,
    pass NAME as 'osfullname' and ID as 'os_id'.

    The 'os' grain that Salt traditionally uses is a shortened
    version of the 'osfullname' grain.
    """
    if (os_id, osfullname) in _ID_AND_NAME_TO_OS_NAME_MAP:
        return _ID_AND_NAME_TO_OS_NAME_MAP[(os_id, osfullname)]

    distroname = _REPLACE_LINUX_RE.sub("", osfullname).strip()
    # return the first ten characters with no spaces, lowercased
    shortname = distroname.replace(" ", "").lower()[:10]
    # this maps the long names from the /etc/DISTRO-release files to the
    # traditional short names that Salt has used.
    return _OS_NAME_MAP.get(shortname, distroname)


# Map the 'os' grain to the 'os_family' grain
# These should always be capitalized entries as the lookup comes
# post-_OS_NAME_MAP. If your system is having trouble with detection, please
# make sure that the 'os' grain is capitalized and working correctly first.
_OS_FAMILY_MAP = {
    "Ubuntu": "Debian",
    "Fedora": "RedHat",
    "Chapeau": "RedHat",
    "Korora": "RedHat",
    "FedBerry": "RedHat",
    "CentOS": "RedHat",
    "CentOS Stream": "RedHat",
    "GoOSe": "RedHat",
    "Scientific": "RedHat",
    "Amazon": "RedHat",
    "CloudLinux": "RedHat",
    "AlmaLinux": "RedHat",
    "OVS": "RedHat",
    "OEL": "RedHat",
    "XCP": "RedHat",
    "XCP-ng": "RedHat",
    "XenServer": "RedHat",
    "RES": "RedHat",
    "Sangoma": "RedHat",
    "VMware Photon OS": "RedHat",
    "Mandrake": "Mandriva",
    "Mint": "Debian",
    "VMwareESX": "VMware",
    "Bluewhite64": "Bluewhite",
    "Slamd64": "Slackware",
    "SLES": "Suse",
    "SUSE Enterprise Server": "Suse",
    "SUSE  Enterprise Server": "Suse",
    "SLED": "Suse",
    "openSUSE": "Suse",
    "SUSE": "Suse",
    "openSUSE Leap": "Suse",
    "openSUSE Tumbleweed": "Suse",
    "SLES_SAP": "Suse",
    "Arch ARM": "Arch",
    "Manjaro": "Arch",
    "Manjaro ARM": "Arch",
    "Antergos": "Arch",
    "EndeavourOS": "Arch",
    "ALT": "RedHat",
    "Trisquel": "Debian",
    "GCEL": "Debian",
    "Linaro": "Debian",
    "elementary OS": "Debian",
    "elementary": "Debian",
    "Univention": "Debian",
    "ScientificLinux": "RedHat",
    "Raspbian": "Debian",
    "Devuan": "Debian",
    "antiX": "Debian",
    "Kali": "Debian",
    "Parrot OS": "Debian",
    "neon": "Debian",
    "Cumulus": "Debian",
    "Deepin": "Debian",
    "NILinuxRT": "NILinuxRT",
    "KDE neon": "Debian",
    "Void": "Void",
    "IDMS": "Debian",
    "Funtoo": "Gentoo",
    "TurnKey": "Debian",
    "Pop": "Debian",
    "Rocky": "RedHat",
    "AstraLinuxCE": "Debian",
    "AstraLinuxSE": "Debian",
    "Alinux": "RedHat",
    "Mendel": "Debian",
    "OSMC": "Debian",
}


# Map the 'family_id' (from os-release) to the 'os_family' grain. If your
# system is having trouble with detection, please make sure that the
# 'family_id' is determined correctly first (in case multiple ID_LIKE entries
# are specified).
_OS_FAMILY_ID_MAP = {
    # Red Hat Enterprise Linux (RHEL) is based on Fedora
    # and Fedora is the successor of Red Hat Linux (RHL).
    "fedora": "RedHat"
}


def _prettify_os_family(family_id):
    if family_id in _OS_FAMILY_ID_MAP:
        return _OS_FAMILY_ID_MAP[family_id]
    # Fall back to use the os_id with an capital starting letter.
    return family_id.capitalize()


# Matches any possible format:
#     DISTRIB_ID="Ubuntu"
#     DISTRIB_ID='Mageia'
#     DISTRIB_ID=Fedora
#     DISTRIB_RELEASE='10.10'
#     DISTRIB_CODENAME='squeeze'
#     DISTRIB_DESCRIPTION='Ubuntu 10.10'
_LSB_REGEX = re.compile(
    "^(DISTRIB_(?:ID|RELEASE|CODENAME|DESCRIPTION))=(?:'|\")?"
    "([\\w\\s\\.\\-_]+)(?:'|\")?"
)


def _linux_bin_exists(binary):
    """
    Does a binary exist in linux (depends on which, type, or whereis)
    """
    for search_cmd in ("which", "type -ap"):
        try:
            return __salt__["cmd.retcode"](f"{search_cmd} {binary}") == 0
        except salt.exceptions.CommandExecutionError:
            pass

    try:
        return (
            len(__salt__["cmd.run_all"](f"whereis -b {binary}")["stdout"].split()) > 1
        )
    except salt.exceptions.CommandExecutionError:
        return False


def _parse_lsb_release():
    ret = {}
    try:
        log.trace("Attempting to parse /etc/lsb-release")
        with salt.utils.files.fopen("/etc/lsb-release") as ifile:
            for line in ifile:
                try:
                    key, value = _LSB_REGEX.match(line.rstrip("\n")).groups()[:2]
                except AttributeError:
                    pass
                else:
                    # Adds lsb_distrib_{id,release,codename,description}
                    ret[f"lsb_{key.lower()}"] = value.rstrip()
    except OSError as exc:
        log.trace("Failed to parse /etc/lsb-release: %s", exc)
    return ret


def _parse_cpe_name(cpe):
    """
    Parse CPE_NAME data from the os-release

    Info: https://csrc.nist.gov/projects/security-content-automation-protocol/scap-specifications/cpe

    Note: cpe:2.3:part:vendor:product:version:update:edition:lang:sw_edition:target_sw:target_hw:other
          however some OS's do not have the full 13 elements, for example:
                CPE_NAME="cpe:2.3:o:amazon:amazon_linux:2"

    :param cpe:
    :return:
    """
    part = {
        "o": "operating system",
        "h": "hardware",
        "a": "application",
    }
    ret = {}
    cpe = (cpe or "").split(":")
    if len(cpe) > 4 and cpe[0] == "cpe":
        if cpe[1].startswith("/"):  # WFN to URI
            ret["vendor"], ret["product"], ret["version"] = cpe[2:5]
            ret["phase"] = cpe[5] if len(cpe) > 5 else None
            ret["part"] = part.get(cpe[1][1:])
        elif len(cpe) == 6 and cpe[1] == "2.3":  # WFN to a string
            ret["vendor"], ret["product"], ret["version"] = (
                x if x != "*" else None for x in cpe[3:6]
            )
            ret["phase"] = None
            ret["part"] = part.get(cpe[2])
        elif len(cpe) > 7 and len(cpe) <= 13 and cpe[1] == "2.3":  # WFN to a string
            ret["vendor"], ret["product"], ret["version"], ret["phase"] = (
                x if x != "*" else None for x in cpe[3:7]
            )
            ret["part"] = part.get(cpe[2])

    return ret


def _linux_init_system():
    """
    Determine init system on Linux systems
    """
    init_system = "unknown"
    try:
        os.stat("/run/systemd/system")
        init_system = "systemd"
    except OSError:
        try:
            with salt.utils.files.fopen("/proc/1/cmdline", "r", errors="ignore") as fhr:
                init_cmdline = fhr.read().replace("\x00", " ").split()
        except OSError:
            pass
        else:
            try:
                init_bin = salt.utils.path.which(init_cmdline[0])
            except IndexError:
                # Emtpy init_cmdline
                init_bin = None
                log.warning("Unable to fetch data from /proc/1/cmdline")
            if init_bin is not None and init_bin.endswith("bin/init"):
                supported_inits = (b"upstart", b"sysvinit", b"systemd")
                edge_len = max(len(x) for x in supported_inits) - 1
                try:
                    buf_size = __opts__["file_buffer_size"]
                except KeyError:
                    # Default to the value of file_buffer_size for the minion
                    buf_size = 262144
                try:
                    with salt.utils.files.fopen(init_bin, "rb") as fp_:
                        edge = b""
                        buf = fp_.read(buf_size).lower()
                        while buf:
                            buf = edge + buf
                            for item in supported_inits:
                                if item in buf:
                                    item = item.decode("utf-8")
                                    init_system = item
                                    buf = b""
                                    break
                            edge = buf[-edge_len:]
                            buf = fp_.read(buf_size).lower()
                except OSError as exc:
                    log.error("Unable to read from init_bin (%s): %s", init_bin, exc)
            elif salt.utils.path.which("supervisord") in init_cmdline:
                init_system = "supervisord"
            elif salt.utils.path.which("dumb-init") in init_cmdline:
                # https://github.com/Yelp/dumb-init
                init_system = "dumb-init"
            elif salt.utils.path.which("tini") in init_cmdline:
                # https://github.com/krallin/tini
                init_system = "tini"
            elif init_cmdline == ["runit"]:
                init_system = "runit"
            elif "/sbin/my_init" in init_cmdline:
                # Phusion Base docker container use runit for srv mgmt, but
                # my_init as pid1
                init_system = "runit"
            else:
                log.debug(
                    "Could not determine init system from command line: (%s)",
                    " ".join(init_cmdline),
                )
    return init_system


def _linux_lsb_distrib_data():
    """
    Determine lsb_distrib_* grains if LSB data is available.

    Returns a (lsb_grain, has_error) pair. The lsb_grain
    dictionary is expected to have following keys on success:
     * lsb_distrib_codename
     * lsb_distrib_description
     * lsb_distrib_id
     * lsb_distrib_release
    """
    grains = {}
    has_error = False
    # Add lsb grains on any distro with lsb-release. Note that this import
    # can fail on systems with lsb-release installed if the system package
    # does not install the python package for the python interpreter used by
    # Salt (i.e. python2 or python3)
    try:
        log.trace("Getting lsb_release distro information")
        import lsb_release  # pylint: disable=import-error

        release = lsb_release.get_distro_information()
        for key, value in release.items():
            key = key.lower()
            lsb_param = "lsb_{}{}".format(
                "" if key.startswith("distrib_") else "distrib_", key
            )
            grains[lsb_param] = value
    # Catch a NameError to workaround possible breakage in lsb_release
    # See https://github.com/saltstack/salt/issues/37867
    except (ImportError, NameError):
        has_error = True
        # if the python library isn't available, try to parse
        # /etc/lsb-release using regex
        log.trace("lsb_release python bindings not available")
        grains.update(_parse_lsb_release())
    return grains, has_error


def _family_id(os_id, id_like):
    """
    Return the family ID which is the oldest distribution ancestor.
    """
    if not id_like:
        # If ID_LIKE is not specified, the distribution has no derivative.
        return os_id

    ids_like = [os_id] + id_like.split()

    # Linux Mint 20.3 does not declare to be a derivative of Debian.
    if "debian" in ids_like or "ubuntu" in ids_like:
        return "debian"

    # The IDs are ordered from closest to farthest.
    return ids_like[-1]


def _os_release_quirks_for_oscodename(os_release):
    """
    Apply quirks for 'oscodename' grain for faulty os-release files

    Some distributions do not (fully) follow the os-release
    specification. This function bundles all required quirks
    for the 'oscodename' grain. To be on the safe side, only
    apply the quirks for allow-listed distributions. Better
    not set the codename instead of setting it wrong.
    """
    if os_release["ID"] in ("astra",):
        # Astra Linux has no version codename, but Salt used
        # to report the variant ID as oscodename.
        return os_release.get("VARIANT_ID")
    if os_release["ID"] in ("almalinux", "rocky"):
        # VERSION_CODENAME is not set, but the codename is
        # mentioned in PRETTY_NAME and VERSION.
        match = _VERSION_RE.match(os_release.get("VERSION", ""))
        if match:
            return match.group("codename")
    return None


def _os_release_quirks_for_osrelease(os_release):
    """
    Apply quirks for 'osrelease' grain for faulty os-release files

    Some distributions do not (fully) follow the os-release
    specification. This function bundles all required quirks
    for the 'osrelease' grain. To be on the safe side, only
    apply the quirks for allow-listed distributions. Better
    not set the release instead of setting it wrong.
    """
    if os_release["ID"] in ("mendel",):
        # Mendel sets VERSION_CODENAME but not VERSION_ID.
        # Only PRETTY_NAME mentions the version number.
        # for example: Mendel GNU/Linux 5 (Eagle)
        test_strg = os_release["PRETTY_NAME"].split()
        if len(test_strg) >= 3:
            return test_strg[2]

    return None


def _os_release_to_grains(os_release):
    """
    Transform the given os-release data to grains.

    The os-release file is a freedesktop.org standard:
    https://www.freedesktop.org/software/systemd/man/os-release.html

    The keys NAME, ID, and PRETTY_NAME are expected to exist. All
    other keys are optional.
    """
    family_id = _family_id(os_release["ID"], os_release.get("ID_LIKE"))
    grains = {
        "os": _derive_os_grain(os_release["NAME"], os_release["ID"]),
        "os_family": _prettify_os_family(family_id),
        "oscodename": os_release.get("VERSION_CODENAME")
        or _os_release_quirks_for_oscodename(os_release),
        "osfullname": os_release["NAME"].strip(),
        "osrelease": os_release.get("VERSION_ID")
        or _os_release_quirks_for_osrelease(os_release),
    }

    # oscodename and osrelease could be empty or None. Remove those.
    return {key: value for key, value in grains.items() if key}


def _linux_distribution_data():
    """
    Determine distribution information like OS name and version.

    Return a grain dictionary with following keys:
     * os
     * os_family
     * oscodename
     * osfullname
     * osrelease

    This function might also return lsb_distrib_* grains
    from _linux_lsb_distrib_data().

    Most Linux distributions should ship a os-release file
    and this file should be the sole source for deriving the
    OS grains. To not cause regressions, only switch the
    distribution that has been tested.
    """
    grains, lsb_has_error = _linux_lsb_distrib_data()

    log.trace("Getting OS name, release, and codename from freedesktop_os_release")
    try:
        # If using platform.freedesktop_os_release we must invalidate
        # the internal platform os_release cache to allow grains to be
        # actually recalculated during grains_refresh
        if hasattr(platform, "_os_release_cache"):
            platform._os_release_cache = None
        os_release = _freedesktop_os_release()
        grains.update(_os_release_to_grains(os_release))

        # To prevent regressions, only let distributions solely
        # use os-release after testing.
        if os_release["ID"] in (
            "almalinux",
            "astra",
            "debian",
            "linuxmint",
            "mendel",
            "pop",
            "rocky",
            "ubuntu",
        ):
            if lsb_has_error is False:
                # Solely use os-release data. See description of the function.
                return grains

    except OSError:
        os_release = {}

    # Warning: The remaining code is legacy code. Please solely rely
    # on os-release data. See description of the function.
    if "osrelease" in grains:
        # Let the legacy code define osrelease to avoid discrepancies.
        del grains["osrelease"]
    return _legacy_linux_distribution_data(grains, os_release, lsb_has_error)


def _legacy_linux_distribution_data(grains, os_release, lsb_has_error):
    """
    Legacy heuristics to determine distribution information.

    Most Linux distributions should ship a os-release file
    and this file should be the sole source for deriving the
    OS grains. See _linux_distribution_data.
    """
    if lsb_has_error:
        if grains.get("lsb_distrib_description", "").lower().startswith("antergos"):
            # Antergos incorrectly configures their /etc/lsb-release,
            # setting the DISTRIB_ID to "Arch". This causes the "os" grain
            # to be incorrectly set to "Arch".
            grains["osfullname"] = "Antergos Linux"
        elif "lsb_distrib_id" not in grains:
            log.trace("Failed to get lsb_distrib_id, trying to parse os-release")
            if os_release:
                if "NAME" in os_release:
                    grains["lsb_distrib_id"] = os_release["NAME"].strip()
                if "VERSION_ID" in os_release:
                    grains["lsb_distrib_release"] = os_release["VERSION_ID"]
                if "VERSION_CODENAME" in os_release:
                    grains["lsb_distrib_codename"] = os_release["VERSION_CODENAME"]
                elif "PRETTY_NAME" in os_release:
                    grains["lsb_distrib_codename"] = os_release["PRETTY_NAME"]
                if "CPE_NAME" in os_release:
                    cpe = _parse_cpe_name(os_release["CPE_NAME"])
                    if not cpe:
                        log.error("Broken CPE_NAME format in /etc/os-release!")
                    elif cpe.get("vendor", "").lower() in ["suse", "opensuse"]:
                        grains["os"] = "SUSE"
                        # openSUSE `osfullname` grain normalization
                        if os_release.get("NAME") == "openSUSE Leap":
                            grains["osfullname"] = "Leap"
                        elif os_release.get("VERSION") == "Tumbleweed":
                            grains["osfullname"] = os_release["VERSION"]
                        # Override VERSION_ID, if CPE_NAME around
                        if (
                            cpe.get("version") and cpe.get("vendor") == "opensuse"
                        ):  # Keep VERSION_ID for SLES
                            grains["lsb_distrib_release"] = cpe["version"]
                if "ID" in os_release and os_release["ID"].strip() == "mendel":
                    test_strg = os_release["PRETTY_NAME"].split()
                    if len(test_strg) >= 3:
                        grains["lsb_distrib_release"] = test_strg[2]

            elif os.path.isfile("/etc/SuSE-release"):
                log.trace("Parsing distrib info from /etc/SuSE-release")
                grains["lsb_distrib_id"] = "SUSE"
                version = ""
                patch = ""
                with salt.utils.files.fopen("/etc/SuSE-release") as fhr:
                    for line in fhr:
                        if "enterprise" in line.lower():
                            grains["lsb_distrib_id"] = "SLES"
                            grains["lsb_distrib_codename"] = re.sub(
                                r"\(.+\)", "", line
                            ).strip()
                        elif "version" in line.lower():
                            version = re.sub(r"[^0-9]", "", line)
                        elif "patchlevel" in line.lower():
                            patch = re.sub(r"[^0-9]", "", line)
                grains["lsb_distrib_release"] = version
                if patch:
                    grains["lsb_distrib_release"] += "." + patch
                    patchstr = "SP" + patch
                    if (
                        grains["lsb_distrib_codename"]
                        and patchstr not in grains["lsb_distrib_codename"]
                    ):
                        grains["lsb_distrib_codename"] += " " + patchstr
                if not grains.get("lsb_distrib_codename"):
                    grains["lsb_distrib_codename"] = "n.a"
            elif os.path.isfile("/etc/altlinux-release"):
                log.trace("Parsing distrib info from /etc/altlinux-release")
                # ALT Linux
                grains["lsb_distrib_id"] = "altlinux"
                with salt.utils.files.fopen("/etc/altlinux-release") as ifile:
                    # This file is symlinked to from:
                    #     /etc/fedora-release
                    #     /etc/redhat-release
                    #     /etc/system-release
                    for line in ifile:
                        # ALT Linux Sisyphus (unstable)
                        comps = line.split()
                        if comps[0] == "ALT":
                            grains["lsb_distrib_release"] = comps[2]
                            grains["lsb_distrib_codename"] = (
                                comps[3].replace("(", "").replace(")", "")
                            )
            elif os.path.isfile("/etc/centos-release"):
                log.trace("Parsing distrib info from /etc/centos-release")
                # CentOS Linux
                grains["lsb_distrib_id"] = "CentOS"
                with salt.utils.files.fopen("/etc/centos-release") as ifile:
                    for line in ifile:
                        # Need to pull out the version and codename
                        # in the case of custom content in /etc/centos-release
                        find_release = re.compile(r"\d+\.\d+")
                        find_codename = re.compile(r"(?<=\()(.*?)(?=\))")
                        release = find_release.search(line)
                        codename = find_codename.search(line)
                        if release is not None:
                            grains["lsb_distrib_release"] = release.group()
                        if codename is not None:
                            grains["lsb_distrib_codename"] = codename.group()
            elif os.path.isfile("/etc.defaults/VERSION") and os.path.isfile(
                "/etc.defaults/synoinfo.conf"
            ):
                grains["osfullname"] = "Synology"
                log.trace("Parsing Synology distrib info from /etc/.defaults/VERSION")
                with salt.utils.files.fopen("/etc.defaults/VERSION", "r") as fp_:
                    synoinfo = {}
                    for line in fp_:
                        try:
                            key, val = line.rstrip("\n").split("=")
                        except ValueError:
                            continue
                        if key in ("majorversion", "minorversion", "buildnumber"):
                            synoinfo[key] = val.strip('"')
                    if len(synoinfo) != 3:
                        log.warning(
                            "Unable to determine Synology version info. "
                            "Please report this, as it is likely a bug."
                        )
                    else:
                        grains["osrelease"] = (
                            "{majorversion}.{minorversion}-{buildnumber}".format(
                                **synoinfo
                            )
                        )

    log.trace(
        "Getting OS name, release, and codename from distro id, version, codename"
    )
    (osname, osrelease, oscodename) = (
        x.strip('"').strip("'") for x in _linux_distribution()
    )
    # Try to assign these three names based on the lsb info, they tend to
    # be more accurate than what python gets from /etc/DISTRO-release.
    # It's worth noting that Ubuntu has patched their Python distribution
    # so that linux_distribution() does the /etc/lsb-release parsing, but
    # we do it anyway here for the sake for full portability.
    if "osfullname" not in grains:
        # If NI Linux RT distribution, set the grains['osfullname'] to 'nilrt'
        if grains.get("lsb_distrib_id", "").lower().startswith("nilrt"):
            grains["osfullname"] = "nilrt"
        else:
            grains["osfullname"] = grains.get("lsb_distrib_id", osname).strip()
    if "osrelease" not in grains:
        # NOTE: This is a workaround for CentOS 7 os-release bug
        # https://bugs.centos.org/view.php?id=8359
        # /etc/os-release contains no minor distro release number so we fall back to parse
        # /etc/centos-release file instead.
        # Commit introducing this comment should be reverted after the upstream bug is released.
        # This also affects Centos 8
        if any(
            os in grains.get("lsb_distrib_codename", "")
            for os in ["CentOS Linux 7", "CentOS Linux 8"]
        ):
            grains.pop("lsb_distrib_release", None)
        grains["osrelease"] = grains.get("lsb_distrib_release", osrelease).strip()

    # allow for codename being within brackets on certain OS
    if grains.get("lsb_distrib_codename", "") and (
        any(os in grains.get("os", "") for os in ["Rocky", "AlmaLinux", "AstraLinuxSE"])
    ):
        test_strg = grains["lsb_distrib_codename"].split("(", maxsplit=1)
        if len(test_strg) >= 2:
            test_strg_2 = test_strg[1].split(")", maxsplit=1)
            if grains["os"] == "AstraLinuxSE":
                # AstraLinuxSE has version aka 'Smolensk 1.6'
                grains["lsb_distrib_codename"] = test_strg_2[0].split()[0].lower()
            else:
                grains["lsb_distrib_codename"] = test_strg_2[0]

    grains["oscodename"] = grains.get("lsb_distrib_codename", "").strip() or oscodename
    if "Red Hat" in grains["oscodename"]:
        grains["oscodename"] = oscodename
    if "os" not in grains:
        grains["os"] = _derive_os_grain(grains["osfullname"])
    # this assigns family names based on the os name
    # family defaults to the os name if not found
    grains["os_family"] = _OS_FAMILY_MAP.get(grains["os"], grains["os"])
    return grains


def _osarch(os_family, cpuarch):
    """
    Return the osarch grain

    This grain will be used for platform-specific considerations such
    as package management. Fall back to the given CPU architecture.
    """
    if os_family == "Debian":
        return __salt__["cmd.run"]("dpkg --print-architecture").strip()
    if os_family in ["RedHat", "Suse"]:
        return salt.utils.pkg.rpm.get_osarch()
    if os_family in ("NILinuxRT", "Poky"):
        archinfo = {}
        for line in __salt__["cmd.run"]("opkg print-architecture").splitlines():
            if line.startswith("arch"):
                _, arch, priority = line.split()
                archinfo[arch.strip()] = int(priority.strip())

        # Return osarch in priority order (higher to lower)
        return sorted(archinfo, key=archinfo.get, reverse=True)

    return cpuarch


def _osrelease_data(os, osfullname, osrelease):
    """
    Derive osrelease_info, osmajorrelease, and osfinger.

    Derive osrelease_info, osmajorrelease from given
    osrelease grain. Derive osfinger from os/osfullname and
    osrelease.
    """
    grains = {}
    osrelease_info = osrelease.split(".")
    for idx, value in enumerate(osrelease_info):
        if not value.isdigit():
            continue
        osrelease_info[idx] = int(value)
    grains["osrelease_info"] = tuple(osrelease_info)
    try:
        grains["osmajorrelease"] = int(grains["osrelease_info"][0])
    except (IndexError, TypeError, ValueError):
        log.debug(
            "Unable to derive osmajorrelease from osrelease_info '%s'. "
            "The osmajorrelease grain will not be set.",
            grains["osrelease_info"],
        )

    if os in ("Debian", "FreeBSD", "OpenBSD", "NetBSD", "Mac", "Raspbian"):
        os_name = os
    else:
        os_name = osfullname
    grains["osfinger"] = "{}-{}".format(
        os_name,
        osrelease if os in ("Ubuntu", "Pop") else grains["osrelease_info"][0],
    )

    return grains


def _selinux():
    """
    Return the selinux grain
    """
    selinux = {"enabled": (__salt__["cmd.retcode"]("selinuxenabled") == 0)}
    if _linux_bin_exists("getenforce"):
        selinux["enforced"] = __salt__["cmd.run"]("getenforce").strip()
    return selinux


def _systemd():
    """
    Return the systemd grain
    """
    systemd_version = "UNDEFINED"
    systemd_features = ""
    try:
        systemd_output = __salt__["cmd.run_all"]("systemctl --version")
    except Exception:  # pylint: disable=broad-except
        log.error("Exception while executing `systemctl --version`", exc_info=True)
        return {
            "version": systemd_version,
            "features": systemd_features,
        }
    if systemd_output.get("retcode") == 0:
        systemd_info = systemd_output.get("stdout", "").splitlines()
        try:
            if systemd_info[0].startswith("systemd "):
                systemd_version = systemd_info[0].split()[1]
                systemd_features = systemd_info[1]
        except IndexError:
            pass
    if systemd_version == "UNDEFINED" or systemd_features == "":
        log.error(
            "Unexpected output returned by `systemctl --version`: %s", systemd_output
        )
    return {
        "version": systemd_version,
        "features": systemd_features,
    }


def _smartos_os_data():
    grains = {}
    # See https://github.com/joyent/smartos-live/issues/224
    if HAS_UNAME:
        uname_v = os.uname()[3]  # format: joyent_20161101T004406Z
    else:
        uname_v = os.name
    uname_v = uname_v[uname_v.index("_") + 1 :]
    grains["os"] = grains["osfullname"] = "SmartOS"
    # store a parsed version of YYYY.MM.DD as osrelease
    grains["osrelease"] = ".".join(
        [
            uname_v.split("T")[0][0:4],
            uname_v.split("T")[0][4:6],
            uname_v.split("T")[0][6:8],
        ]
    )
    # store a untouched copy of the timestamp in osrelease_stamp
    grains["osrelease_stamp"] = uname_v
    return grains


def _sunos_release():  # pragma: no cover
    grains = {}
    with salt.utils.files.fopen("/etc/release", "r") as fp_:
        rel_data = fp_.read()
    try:
        release_re = re.compile(
            r"((?:Open|Oracle )?Solaris|OpenIndiana|OmniOS) (Development)?"
            r"\s*(\d+\.?\d*|v\d+)\s?[A-Z]*\s?(r\d+|\d+\/\d+|oi_\S+|snv_\S+)?"
        )
        (
            osname,
            development,
            osmajorrelease,
            osminorrelease,
        ) = release_re.search(rel_data).groups()
    except AttributeError:
        # Set a blank osrelease grain and fallback to 'Solaris'
        # as the 'os' grain.
        grains["os"] = grains["osfullname"] = "Solaris"
        grains["osrelease"] = ""
    else:
        if development is not None:
            osname = " ".join((osname, development))
        if HAS_UNAME:
            uname_v = os.uname()[3]
        else:
            uname_v = os.name
        grains["os"] = grains["osfullname"] = osname
        if osname in ["Oracle Solaris"] and uname_v.startswith(osmajorrelease):
            # Oracla Solars 11 and up have minor version in uname
            grains["osrelease"] = uname_v
        elif osname in ["OmniOS"]:
            # OmniOS
            osrelease = []
            osrelease.append(osmajorrelease[1:])
            osrelease.append(osminorrelease[1:])
            grains["osrelease"] = ".".join(osrelease)
            grains["osrelease_stamp"] = uname_v
        else:
            # Sun Solaris 10 and earlier/comparable
            osrelease = []
            osrelease.append(osmajorrelease)
            if osminorrelease:
                osrelease.append(osminorrelease)
            grains["osrelease"] = ".".join(osrelease)
            grains["osrelease_stamp"] = uname_v
    return grains


def os_data():
    """
    Return grains pertaining to the operating system
    """
    grains = {
        "num_gpus": 0,
        "gpus": [],
    }

    # Windows Server 2008 64-bit
    # ('Windows', 'MINIONNAME', '2008ServerR2', '6.1.7601', 'AMD64',
    #  'Intel64 Fam ily 6 Model 23 Stepping 6, GenuineIntel')
    # Ubuntu 10.04
    # ('Linux', 'MINIONNAME', '2.6.32-38-server',
    # '#83-Ubuntu SMP Wed Jan 4 11:26:59 UTC 2012', 'x86_64', '')

    # pylint: disable=unpacking-non-sequence
    (
        grains["kernel"],
        grains["nodename"],
        grains["kernelrelease"],
        grains["kernelversion"],
        grains["cpuarch"],
        _,
    ) = platform.uname()
    # pylint: enable=unpacking-non-sequence

    if salt.utils.platform.is_junos():
        grains["kernel"] = "Junos"
        grains["osfullname"] = "Junos"
        grains["os"] = "Junos"
        grains["os_family"] = "FreeBSD"
        showver = _parse_junos_showver(
            subprocess.run(
                ["/usr/sbin/cli", "show", "version"], stdout=subprocess.PIPE, check=True
            ).stdout
        )
        grains.update(showver)
    elif salt.utils.platform.is_proxy():
        grains["kernel"] = "proxy"
        grains["kernelrelease"] = "proxy"
        grains["kernelversion"] = "proxy"
        grains["osrelease"] = "proxy"
        grains["os"] = "proxy"
        grains["os_family"] = "proxy"
        grains["osfullname"] = "proxy"
    elif salt.utils.platform.is_windows():
        grains["os"] = "Windows"
        grains["os_family"] = "Windows"
        grains.update(_memdata(grains))
        grains.update(_windows_platform_data())
        grains.update(_windows_cpudata())
        grains.update(_windows_virtual(grains))
        grains.update(_ps(grains))

        if "Server" in grains["osrelease"]:
            osrelease_info = grains["osrelease"].split("Server", 1)
            osrelease_info[1] = osrelease_info[1].lstrip("R")
        else:
            osrelease_info = grains["osrelease"].split(".")
        osrelease_info = [s for s in osrelease_info if s]

        for idx, value in enumerate(osrelease_info):
            if not value.isdigit():
                continue
            osrelease_info[idx] = int(value)
        grains["osrelease_info"] = tuple(osrelease_info)

        grains["osfinger"] = "{os}-{ver}".format(
            os=grains["os"], ver=grains["osrelease"]
        )

        grains["init"] = "Windows"

        return grains
    elif salt.utils.platform.is_linux():
        # Add SELinux grain, if you have it
        if _linux_bin_exists("selinuxenabled"):
            log.trace("Adding selinux grains")
            grains["selinux"] = _selinux()

        # Add systemd grain, if you have it
        if _linux_bin_exists("systemctl") and _linux_bin_exists("localectl"):
            log.trace("Adding systemd grains")
            grains["systemd"] = _systemd()

        # Add init grain
        log.trace("Adding init grain")
        grains["init"] = _linux_init_system()

        grains.update(_linux_distribution_data())
        grains.update(_linux_cpudata())
        grains.update(_linux_gpu_data())

        # only if devicetree is mounted
        if os.path.isdir("/proc/device-tree"):
            grains.update(_linux_devicetree_platform_data())
    elif grains["kernel"] == "SunOS":
        grains["os_family"] = "Solaris"
        if salt.utils.platform.is_smartos():
            grains.update(_smartos_os_data())
        elif os.path.isfile("/etc/release"):
            grains.update(_sunos_release())
        else:
            grains["os"] = "Unknown {}".format(grains["kernel"])
        grains.update(_sunos_cpudata())
    elif grains["kernel"] == "VMkernel":
        grains["os"] = "ESXi"
        grains["os_family"] = "VMware"
    elif grains["kernel"] == "Darwin":
        osrelease = __salt__["cmd.run"]("sw_vers -productVersion")
        osname = __salt__["cmd.run"]("sw_vers -productName")
        osbuild = __salt__["cmd.run"]("sw_vers -buildVersion")
        grains["os"] = "MacOS"
        grains["os_family"] = "MacOS"
        grains["osfullname"] = f"{osname} {osrelease}"
        grains["osrelease"] = osrelease
        grains["osbuild"] = osbuild
        grains["init"] = "launchd"
        grains.update(_bsd_cpudata(grains))
        grains.update(_osx_gpudata())
        grains.update(_osx_platform_data())
    elif grains["kernel"] == "AIX":
        osrelease = __salt__["cmd.run"]("oslevel")
        osrelease_techlevel = __salt__["cmd.run"]("oslevel -r")
        osname = __salt__["cmd.run"]("uname")
        grains["os"] = "AIX"
        grains["os_family"] = "AIX"
        grains["osfullname"] = osname
        grains["osrelease"] = osrelease
        grains["osrelease_techlevel"] = osrelease_techlevel
        grains.update(_aix_cpudata())
    elif grains["kernel"] == "FreeBSD":
        grains["os_family"] = grains["osfullname"] = grains["os"] = grains["kernel"]
        try:
            grains["osrelease"] = __salt__["cmd.run"]("freebsd-version -u").split("-")[
                0
            ]
        except salt.exceptions.CommandExecutionError:
            # freebsd-version was introduced in 10.0.
            # derive osrelease from kernelversion prior to that
            grains["osrelease"] = grains["kernelrelease"].split("-")[0]
        grains.update(_bsd_cpudata(grains))
    elif grains["kernel"] in ("OpenBSD", "NetBSD"):
        grains["os_family"] = grains["os"] = grains["kernel"]
        grains.update(_bsd_cpudata(grains))
        grains["osrelease"] = grains["kernelrelease"].split("-")[0]
        if grains["kernel"] == "NetBSD":
            grains.update(_netbsd_gpu_data())
    else:
        grains["os"] = grains["kernel"]
        grains["os_family"] = "Unknown"

    grains["osarch"] = _osarch(grains.get("os_family"), grains.get("cpuarch"))

    grains.update(_memdata(grains))

    # Get the hardware and bios data
    grains.update(_hw_data(grains))

    # Load the virtual machine info
    grains.update(_virtual(grains))
    grains.update(_virtual_hv(grains))
    grains.update(_ps(grains))

    if grains.get("osrelease", ""):
        grains.update(
            _osrelease_data(grains["os"], grains["osfullname"], grains["osrelease"])
        )

    return grains


def locale_info():
    """
    Provides
        defaultlanguage
        defaultencoding
    """
    grains = {}
    grains["locale_info"] = {}

    if salt.utils.platform.is_proxy():
        return grains

    try:
        (
            grains["locale_info"]["defaultlanguage"],
            grains["locale_info"]["defaultencoding"],
        ) = locale.getlocale()
    except Exception:  # pylint: disable=broad-except
        grains["locale_info"]["defaultlanguage"] = "unknown"
        grains["locale_info"]["defaultencoding"] = "unknown"
    grains["locale_info"]["detectedencoding"] = __salt_system_encoding__

    grains["locale_info"]["timezone"] = "unknown"
    if _DATEUTIL_TZ:
        try:
            grains["locale_info"]["timezone"] = datetime.datetime.now(
                dateutil.tz.tzlocal()
            ).tzname()
        except UnicodeDecodeError:
            # Because the method 'tzname' is not a part of salt the decoding error cant be fixed.
            # The error is in datetime in the python2 lib
            if salt.utils.platform.is_windows():
                grains["locale_info"]["timezone"] = time.tzname[0].decode("mbcs")

    return grains


def hostname():
    """
    Return fqdn, hostname, domainname

    .. note::
        On Windows the ``domain`` grain may refer to the dns entry for the host
        instead of the Windows domain to which the host is joined. It may also
        be empty if not a part of any domain. Refer to the ``windowsdomain``
        grain instead
    """
    # This is going to need some work
    # Provides:
    #   fqdn
    #   host
    #   localhost
    #   domain
    global __FQDN__
    grains = {}

    if salt.utils.platform.is_proxy():
        return grains

    grains["localhost"] = socket.gethostname()
    if __FQDN__ is None:
        __FQDN__ = salt.utils.network.get_fqhostname()

    # On some distros (notably FreeBSD) if there is no hostname set
    # salt.utils.network.get_fqhostname() will return None.
    # In this case we punt and log a message at error level, but force the
    # hostname and domain to be localhost.localdomain
    # Otherwise we would stacktrace below
    if __FQDN__ is None:  # still!
        log.error(
            "Having trouble getting a hostname.  Does this machine have its hostname"
            " and domain set properly?"
        )
        __FQDN__ = "localhost.localdomain"

    grains["fqdn"] = __FQDN__
    (grains["host"], grains["domain"]) = grains["fqdn"].partition(".")[::2]
    return grains


def append_domain():
    """
    Return append_domain if set
    """

    grain = {}

    if salt.utils.platform.is_proxy():
        return grain

    if "append_domain" in __opts__:
        grain["append_domain"] = __opts__["append_domain"]
    return grain


def fqdns():
    """
    Return all known FQDNs for the system by enumerating all interfaces and
    then trying to reverse resolve them (excluding 'lo' interface).
    To disable the fqdns grain, set enable_fqdns_grains: False in the minion configuration file.
    """
    # Provides:
    # fqdns
    opt = {"fqdns": []}
    if __opts__.get(
        "enable_fqdns_grains",
        (
            False
            if salt.utils.platform.is_windows()
            or salt.utils.platform.is_proxy()
            or salt.utils.platform.is_sunos()
            or salt.utils.platform.is_aix()
            or salt.utils.platform.is_junos()
            or salt.utils.platform.is_darwin()
            else True
        ),
    ):
        opt = __salt__["network.fqdns"]()
    return opt


def ip_fqdn():
    """
    Return ip address and FQDN grains
    """
    if salt.utils.platform.is_proxy():
        return {}

    ret = {}
    ret["ipv4"] = salt.utils.network.ip_addrs(include_loopback=True)
    ret["ipv6"] = salt.utils.network.ip_addrs6(include_loopback=True)

    _fqdn = hostname()["fqdn"]
    for socket_type, ipv_num in ((socket.AF_INET, "4"), (socket.AF_INET6, "6")):
        key = "fqdn_ip" + ipv_num
        if not ret["ipv" + ipv_num]:
            ret[key] = []
        else:
            start_time = datetime.datetime.utcnow()
            try:
                info = socket.getaddrinfo(_fqdn, None, socket_type)
                ret[key] = list({item[4][0] for item in info})
            except (OSError, UnicodeError):
                timediff = datetime.datetime.utcnow() - start_time
                if timediff.seconds > 5 and __opts__["__role"] == "master":
                    log.warning(
                        'Unable to find IPv%s record for "%s" causing a %s '
                        "second timeout when rendering grains. Set the dns or "
                        "/etc/hosts for IPv%s to clear this.",
                        ipv_num,
                        _fqdn,
                        timediff,
                        ipv_num,
                    )
                ret[key] = []

    return ret


def ip_interfaces():
    """
    Provide a dict of the connected interfaces and their ip addresses
    The addresses will be passed as a list for each interface
    """
    # Provides:
    #   ip_interfaces

    if salt.utils.platform.is_proxy():
        return {}

    ret = {}
    ifaces = _get_interfaces()
    for face in ifaces:
        iface_ips = []
        for inet in ifaces[face].get("inet", []):
            if "address" in inet:
                iface_ips.append(inet["address"])
        for inet in ifaces[face].get("inet6", []):
            if "address" in inet:
                iface_ips.append(inet["address"])
        for secondary in ifaces[face].get("secondary", []):
            if "address" in secondary:
                iface_ips.append(secondary["address"])
        ret[face] = iface_ips
    return {"ip_interfaces": ret}


def ip4_interfaces():
    """
    Provide a dict of the connected interfaces and their ip4 addresses
    The addresses will be passed as a list for each interface
    """
    # Provides:
    #   ip_interfaces

    if salt.utils.platform.is_proxy():
        return {}

    ret = {}
    ifaces = _get_interfaces()
    for face in ifaces:
        iface_ips = []
        for inet in ifaces[face].get("inet", []):
            if "address" in inet:
                iface_ips.append(inet["address"])
        for secondary in ifaces[face].get("secondary", []):
            if "address" in secondary and secondary.get("type") == "inet":
                iface_ips.append(secondary["address"])
        ret[face] = iface_ips
    return {"ip4_interfaces": ret}


def ip6_interfaces():
    """
    Provide a dict of the connected interfaces and their ip6 addresses
    The addresses will be passed as a list for each interface
    """
    # Provides:
    #   ip_interfaces

    if salt.utils.platform.is_proxy():
        return {}

    ret = {}
    ifaces = _get_interfaces()
    for face in ifaces:
        iface_ips = []
        for inet in ifaces[face].get("inet6", []):
            if "address" in inet:
                iface_ips.append(inet["address"])
        for secondary in ifaces[face].get("secondary", []):
            if "address" in secondary and secondary.get("type") == "inet6":
                iface_ips.append(secondary["address"])
        ret[face] = iface_ips
    return {"ip6_interfaces": ret}


def hwaddr_interfaces():
    """
    Provide a dict of the connected interfaces and their
    hw addresses (Mac Address)
    """
    # Provides:
    #   hwaddr_interfaces
    ret = {}
    ifaces = _get_interfaces()
    for face in ifaces:
        if "hwaddr" in ifaces[face]:
            ret[face] = ifaces[face]["hwaddr"]
    return {"hwaddr_interfaces": ret}


def dns():
    """
    Parse the resolver configuration file

     .. versionadded:: 2016.3.0
    """
    # Provides:
    #   dns
    if salt.utils.platform.is_windows() or "proxyminion" in __opts__:
        return {}

    if os.path.exists("/run/systemd/resolve/resolv.conf"):
        resolv = salt.utils.dns.parse_resolv("/run/systemd/resolve/resolv.conf")
    else:
        resolv = salt.utils.dns.parse_resolv()

    for key in ("nameservers", "ip4_nameservers", "ip6_nameservers", "sortlist"):
        if key in resolv:
            resolv[key] = [str(i) for i in resolv[key]]

    return {"dns": resolv} if resolv else {}


def get_machine_id():
    """
    Provide the machine-id for machine/virtualization combination
    """
    # Provides:
    #   machine-id
    if platform.system() == "AIX":
        return _aix_get_machine_id()

    return _get_machine_identifier()


def cwd():
    """
    Current working directory
    """
    return {"cwd": os.getcwd()}


def path():
    """
    Return the path
    """
    # Provides:
    #   path
    #   systempath
    _path = salt.utils.stringutils.to_unicode(os.environ.get("PATH", "").strip())
    return {
        "path": _path,
        "systempath": _path.split(os.path.pathsep),
    }


def pythonversion():
    """
    Return the Python version
    """
    # Provides:
    #   pythonversion
    return {"pythonversion": list(sys.version_info)}


def pythonpath():
    """
    Return the Python path
    """
    # Provides:
    #   pythonpath
    return {"pythonpath": sys.path}


def pythonexecutable():
    """
    Return the python executable in use
    """
    # Provides:
    #   pythonexecutable
    return {"pythonexecutable": sys.executable}


def saltpath():
    """
    Return the path of the salt module
    """
    # Provides:
    #   saltpath
    salt_path = os.path.abspath(os.path.join(__file__, os.path.pardir))
    return {"saltpath": os.path.dirname(salt_path)}


def saltversion():
    """
    Return the version of salt
    """
    # Provides:
    #   saltversion
    from salt.version import __version__

    return {"saltversion": __version__}


def zmqversion():
    """
    Return the zeromq version
    """
    # Provides:
    #   zmqversion
    try:
        import zmq

        return {"zmqversion": zmq.zmq_version()}  # pylint: disable=no-member
    except ImportError:
        return {}


def saltversioninfo():
    """
    Return the version_info of salt

     .. versionadded:: 0.17.0
    """
    # Provides:
    #   saltversioninfo
    from salt.version import __version_info__

    return {"saltversioninfo": list(__version_info__)}


def _hw_data(osdata):
    """
    Get system specific hardware data from dmidecode

    Provides
        biosversion
        biosvendor
        boardname
        productname
        manufacturer
        serialnumber
        biosreleasedate
        uuid

    .. versionadded:: 0.9.5
    """

    if salt.utils.platform.is_proxy():
        return {}

    grains = {}
    if osdata["kernel"] == "Linux" and os.path.exists("/sys/class/dmi/id"):
        # On many Linux distributions basic firmware information is available via sysfs
        # requires CONFIG_DMIID to be enabled in the Linux kernel configuration
        sysfs_firmware_info = {
            "biosversion": "bios_version",
            "biosvendor": "bios_vendor",
            "boardname": "board_name",
            "productname": "product_name",
            "manufacturer": "sys_vendor",
            "biosreleasedate": "bios_date",
            "uuid": "product_uuid",
            "serialnumber": "product_serial",
        }
        for key, fw_file in sysfs_firmware_info.items():
            contents_file = os.path.join("/sys/class/dmi/id", fw_file)
            if os.path.exists(contents_file):
                try:
                    with salt.utils.files.fopen(contents_file, "rb") as ifile:
                        grains[key] = salt.utils.stringutils.to_unicode(
                            ifile.read().strip(), errors="replace"
                        )
                        if key == "uuid":
                            grains["uuid"] = grains["uuid"].lower()
                except UnicodeDecodeError:
                    # Some firmwares provide non-valid 'product_name'
                    # files, ignore them
                    log.debug(
                        "The content in /sys/devices/virtual/dmi/id/product_name is not"
                        " valid"
                    )
                except OSError as err:
                    # PermissionError is new to Python 3, but corresponds to the EACESS and
                    # EPERM error numbers. Use those instead here for PY2 compatibility.
                    if err.errno == EACCES or err.errno == EPERM:
                        # Skip the grain if non-root user has no access to the file.
                        pass
    elif salt.utils.path.which_bin(["dmidecode", "smbios"]) is not None and not (
        salt.utils.platform.is_smartos()
        or (  # SunOS on SPARC - 'smbios: failed to load SMBIOS: System does not export an SMBIOS table'
            osdata["kernel"] == "SunOS" and osdata["cpuarch"].startswith("sparc")
        )
    ):
        # On SmartOS (possibly SunOS also) smbios only works in the global zone
        # smbios is also not compatible with linux's smbios (smbios -s = print summarized)
        grains = {
            "biosversion": __salt__["smbios.get"]("bios-version"),
            "biosvendor": __salt__["smbios.get"]("bios-vendor"),
            "productname": __salt__["smbios.get"]("system-product-name"),
            "manufacturer": __salt__["smbios.get"]("system-manufacturer"),
            "biosreleasedate": __salt__["smbios.get"]("bios-release-date"),
            "uuid": __salt__["smbios.get"]("system-uuid"),
        }
        grains = {key: val for key, val in grains.items() if val is not None}
        uuid = __salt__["smbios.get"]("system-uuid")
        if uuid is not None:
            grains["uuid"] = uuid.lower()
        for serial in (
            "system-serial-number",
            "chassis-serial-number",
            "baseboard-serial-number",
        ):
            serial = __salt__["smbios.get"](serial)
            if serial is not None:
                grains["serialnumber"] = serial
                break
    elif salt.utils.path.which_bin(["fw_printenv"]) is not None:
        # ARM Linux devices expose UBOOT env variables via fw_printenv
        hwdata = {
            "manufacturer": "manufacturer",
            "serialnumber": "serial#",
            "productname": "DeviceDesc",
        }
        for grain_name, cmd_key in hwdata.items():
            result = __salt__["cmd.run_all"](f"fw_printenv {cmd_key}")
            if result["retcode"] == 0:
                uboot_keyval = result["stdout"].split("=")
                grains[grain_name] = _clean_value(grain_name, uboot_keyval[1])
    elif osdata["kernel"] == "FreeBSD":
        # On FreeBSD /bin/kenv (already in base system)
        # can be used instead of dmidecode
        kenv = salt.utils.path.which("kenv")
        if kenv:
            # In theory, it will be easier to add new fields to this later
            fbsd_hwdata = {
                "biosversion": "smbios.bios.version",
                "biosvendor": "smbios.bios.vendor",
                "manufacturer": "smbios.system.maker",
                "serialnumber": "smbios.system.serial",
                "productname": "smbios.system.product",
                "biosreleasedate": "smbios.bios.reldate",
                "uuid": "smbios.system.uuid",
            }
            for key, val in fbsd_hwdata.items():
                value = __salt__["cmd.run"](f"{kenv} {val}")
                grains[key] = _clean_value(key, value)
    elif osdata["kernel"] == "OpenBSD":
        sysctl = salt.utils.path.which("sysctl")
        hwdata = {
            "biosversion": "hw.version",
            "manufacturer": "hw.vendor",
            "productname": "hw.product",
            "serialnumber": "hw.serialno",
            "uuid": "hw.uuid",
        }
        for key, oid in hwdata.items():
            value = __salt__["cmd.run"](f"{sysctl} -n {oid}")
            if not value.endswith(" value is not available"):
                grains[key] = _clean_value(key, value)
    elif osdata["kernel"] == "NetBSD":
        sysctl = salt.utils.path.which("sysctl")
        nbsd_hwdata = {
            "biosversion": "machdep.dmi.board-version",
            "biosvendor": "machdep.dmi.bios-vendor",
            "manufacturer": "machdep.dmi.system-vendor",
            "serialnumber": "machdep.dmi.system-serial",
            "productname": "machdep.dmi.system-product",
            "biosreleasedate": "machdep.dmi.bios-date",
            "uuid": "machdep.dmi.system-uuid",
        }
        for key, oid in nbsd_hwdata.items():
            result = __salt__["cmd.run_all"](f"{sysctl} -n {oid}")
            if result["retcode"] == 0:
                grains[key] = _clean_value(key, result["stdout"])
    elif osdata["kernel"] == "Darwin":
        grains["manufacturer"] = "Apple Inc."
        sysctl = salt.utils.path.which("sysctl")
        hwdata = {"productname": "hw.model"}
        for key, oid in hwdata.items():
            value = __salt__["cmd.run"](f"{sysctl} -b {oid}")
            if not value.endswith(" is invalid"):
                grains[key] = _clean_value(key, value)
    elif osdata["kernel"] == "SunOS" and osdata["cpuarch"].startswith("sparc"):
        # Depending on the hardware model, commands can report different bits
        # of information.  With that said, consolidate the output from various
        # commands and attempt various lookups.
        data = ""
        for cmd, args in (
            ("/usr/sbin/prtdiag", "-v"),
            ("/usr/sbin/prtconf", "-vp"),
            ("/usr/sbin/virtinfo", "-a"),
        ):
            if salt.utils.path.which(cmd):  # Also verifies that cmd is executable
                data += __salt__["cmd.run"](f"{cmd} {args}")
                data += "\n"

        sn_regexes = [
            re.compile(r)
            for r in [
                r"(?im)^\s*Chassis\s+Serial\s+Number\n-+\n(\S+)",  # prtdiag
                r"(?im)^\s*chassis-sn:\s*(\S+)",  # prtconf
                r"(?im)^\s*Chassis\s+Serial#:\s*(\S+)",  # virtinfo
            ]
        ]

        obp_regexes = [
            re.compile(r)
            for r in [
                r"(?im)^\s*System\s+PROM\s+revisions.*\nVersion\n-+\nOBP\s+(\S+)\s+(\S+)",  # prtdiag
                r"(?im)^\s*version:\s*\'OBP\s+(\S+)\s+(\S+)",  # prtconf
            ]
        ]

        fw_regexes = [
            re.compile(r)
            for r in [r"(?im)^\s*Sun\s+System\s+Firmware\s+(\S+)\s+(\S+)"]  # prtdiag
        ]

        uuid_regexes = [
            re.compile(r) for r in [r"(?im)^\s*Domain\s+UUID:\s*(\S+)"]  # virtinfo
        ]

        manufacturer_regexes = [
            re.compile(r)
            for r in [r"(?im)^\s*System\s+Configuration:\s*(.*)(?=sun)"]  # prtdiag
        ]

        product_regexes = [
            re.compile(r)
            for r in [
                r"(?im)^\s*System\s+Configuration:\s*.*?sun\d\S+[^\S\r\n]*(.*)",  # prtdiag
                r"(?im)^[^\S\r\n]*banner-name:[^\S\r\n]*(.*)",  # prtconf
                r"(?im)^[^\S\r\n]*product-name:[^\S\r\n]*(.*)",  # prtconf
            ]
        ]

        sn_regexes = [
            re.compile(r)
            for r in [
                r"(?im)Chassis\s+Serial\s+Number\n-+\n(\S+)",  # prtdiag
                r"(?i)Chassis\s+Serial#:\s*(\S+)",  # virtinfo
                r"(?i)chassis-sn:\s*(\S+)",  # prtconf
            ]
        ]

        obp_regexes = [
            re.compile(r)
            for r in [
                r"(?im)System\s+PROM\s+revisions.*\nVersion\n-+\nOBP\s+(\S+)\s+(\S+)",  # prtdiag
                r"(?im)version:\s*\'OBP\s+(\S+)\s+(\S+)",  # prtconf
            ]
        ]

        fw_regexes = [
            re.compile(r)
            for r in [r"(?i)Sun\s+System\s+Firmware\s+(\S+)\s+(\S+)"]  # prtdiag
        ]

        uuid_regexes = [
            re.compile(r) for r in [r"(?i)Domain\s+UUID:\s+(\S+)"]  # virtinfo
        ]

        for regex in sn_regexes:
            res = regex.search(data)
            if res and len(res.groups()) >= 1:
                grains["serialnumber"] = res.group(1).strip().replace("'", "")
                break

        for regex in obp_regexes:
            res = regex.search(data)
            if res and len(res.groups()) >= 1:
                obp_rev, obp_date = res.groups()[
                    0:2
                ]  # Limit the number in case we found the data in multiple places
                grains["biosversion"] = obp_rev.strip().replace("'", "")
                grains["biosreleasedate"] = obp_date.strip().replace("'", "")

        for regex in fw_regexes:
            res = regex.search(data)
            if res and len(res.groups()) >= 1:
                fw_rev, fw_date = res.groups()[0:2]
                grains["systemfirmware"] = fw_rev.strip().replace("'", "")
                grains["systemfirmwaredate"] = fw_date.strip().replace("'", "")
                break

        for regex in uuid_regexes:
            res = regex.search(data)
            if res and len(res.groups()) >= 1:
                grains["uuid"] = res.group(1).strip().replace("'", "")
                break

        for regex in manufacturer_regexes:
            res = regex.search(data)
            if res and len(res.groups()) >= 1:
                grains["manufacturer"] = res.group(1).strip().replace("'", "")
                break

        for regex in product_regexes:
            res = regex.search(data)
            if res and len(res.groups()) >= 1:
                t_productname = res.group(1).strip().replace("'", "")
                if t_productname:
                    grains["product"] = t_productname
                    grains["productname"] = t_productname
                    break
    elif osdata["kernel"] == "AIX":
        cmd = salt.utils.path.which("prtconf")
        if cmd:
            data = __salt__["cmd.run"](f"{cmd}") + os.linesep
            for dest, regstring in (
                ("serialnumber", r"(?im)^\s*Machine\s+Serial\s+Number:\s+(\S+)"),
                ("systemfirmware", r"(?im)^\s*Firmware\s+Version:\s+(.*)"),
            ):
                for regex in [re.compile(r) for r in [regstring]]:
                    res = regex.search(data)
                    if res and len(res.groups()) >= 1:
                        grains[dest] = res.group(1).strip().replace("'", "")

            product_regexes = [re.compile(r"(?im)^\s*System\s+Model:\s+(\S+)")]
            for regex in product_regexes:
                res = regex.search(data)
                if res and len(res.groups()) >= 1:
                    grains["manufacturer"], grains["productname"] = (
                        res.group(1).strip().replace("'", "").split(",")
                    )
                    break
        else:
            log.error("The 'prtconf' binary was not found in $PATH.")

    return grains


def get_server_id():
    """
    Provides an integer based on the FQDN of a machine.
    Useful as server-id in MySQL replication or anywhere else you'll need an ID
    like this.
    """
    # Provides:
    #   server_id

    if salt.utils.platform.is_proxy():
        return {}
    id_ = __opts__.get("id", "")
    hash_ = int(hashlib.sha256(id_.encode()).hexdigest(), 16)
    return {"server_id": abs(hash_ % (2**31))}


def get_master():
    """
    Provides the minion with the name of its master.
    This is useful in states to target other services running on the master.
    """
    # Provides:
    #   master
    return {"master": __opts__.get("master", "")}


def default_gateway():
    """
    Populates grains which describe whether a server has a default gateway
    configured or not. Uses `ip -4 route show` and `ip -6 route show` and greps
    for a `default` at the beginning of any line. Assuming the standard
    `default via <ip>` format for default gateways, it will also parse out the
    ip address of the default gateway, and put it in ip4_gw or ip6_gw.

    If the `ip` command is unavailable, no grains will be populated.

    Currently does not support multiple default gateways. The grains will be
    set to the first default gateway found.

    List of grains:

        ip4_gw: True  # ip/True/False if default ipv4 gateway
        ip6_gw: True  # ip/True/False if default ipv6 gateway
        ip_gw: True   # True if either of the above is True, False otherwise
    """
    grains = {}
    ip_bin = salt.utils.path.which("ip")
    if not ip_bin:
        return {}
    grains["ip_gw"] = False
    grains["ip4_gw"] = False
    grains["ip6_gw"] = False
    for ip_version in ("4", "6"):
        try:
            out = __salt__["cmd.run"]([ip_bin, "-" + ip_version, "route", "show"])
            for line in out.splitlines():
                if line.startswith("default"):
                    grains["ip_gw"] = True
                    grains[f"ip{ip_version}_gw"] = True
                    try:
                        via, gw_ip = line.split()[1:3]
                    except ValueError:
                        pass
                    else:
                        if via == "via":
                            grains[f"ip{ip_version}_gw"] = gw_ip
                    break
        except Exception:  # pylint: disable=broad-except
            continue
    return grains


def kernelparams():
    """
    Return the kernel boot parameters
    """
    if salt.utils.platform.is_windows():
        # TODO: add grains using `bcdedit /enum {current}`
        return {}
    else:
        try:
            with salt.utils.files.fopen(
                "/proc/cmdline", "r", errors="surrogateescape"
            ) as fhr:
                cmdline = fhr.read()
                grains = {"kernelparams": []}
                for data in [
                    item.split("=") for item in salt.utils.args.shlex_split(cmdline)
                ]:
                    value = None
                    if len(data) == 2:
                        value = data[1].strip('"')

                    grains["kernelparams"] += [(data[0], value)]
        except FileNotFoundError:
            grains = {}
        except OSError as exc:
            grains = {}
            log.debug("Failed to read /proc/cmdline: %s", exc)

        return grains
