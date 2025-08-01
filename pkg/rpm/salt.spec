%global __brp_check_rpaths %{nil}

%bcond_with tests
%bcond_with docs

# Disable build-id symlinks
%define _build_id_links none
%undefine _missing_build_ids_terminate_build
%define __brp_mangle_shebangs /usr/bin/true
%define __brp_python_hardlink /usr/bin/true

# Disable private libraries from showing in provides
%global __to_exclude .*\\.so.*
%global __provides_exclude_from ^.*$
%global __requires_exclude_from ^.*$
%define _source_payload w2.gzdio
%define _binary_payload w2.gzdio
%global _SALT_GROUP salt
%global _SALT_USER salt
%global _SALT_NAME Salt
%global _SALT_HOME /opt/saltstack/salt

# salt-master current user and group
%global _MS_CUR_USER %{_SALT_USER}
%global _MS_CUR_GROUP %{_SALT_GROUP}

# salt-minion current user and group
%global _MN_CUR_USER %{_SALT_USER}
%global _MN_CUR_GROUP %{_SALT_GROUP}

# Disable debugsource template
%define _debugsource_template %{nil}

# Needed for packages built from source.
%define _unpackaged_files_terminate_build 0

# Disable python bytecompile for MANY reasons
%global __os_install_post %(echo '%{__os_install_post}' | sed -e 's!/usr/lib[^[:space:]]*/brp-python-bytecompile[[:space:]].*$!!g')

%define fish_dir %{_datadir}/fish/vendor_functions.d

Name:    salt
Version: 3006.14
Release: 0
Summary: A parallel remote execution system
Group:   System Environment/Daemons
License: ASL 2.0
URL:     https://saltproject.io/

Provides:  salt = %{version}
Obsoletes: salt3 < 3006

BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)

%ifarch %{ix86} x86_64
Requires: dmidecode
%endif

Requires: pciutils
Requires: which
Requires: openssl
Requires: /usr/sbin/usermod
Requires: /usr/sbin/groupadd
Requires: /usr/sbin/useradd

BuildRequires: python3
BuildRequires: python3-pip
BuildRequires: openssl
BuildRequires: git

# rhel is not defined on all rpm based distros.
%if %{?rhel:1}%{!?rhel:0}
%if %{rhel} >= 9
BuildRequires: libxcrypt-compat
%endif
%endif

# Build debuginfo package
%debug_package
%_no_recompute_build_ids 1

%description
Salt is a distributed remote execution system used to execute commands and
query data. It was developed in order to bring the best solutions found in
the world of remote execution together and make them better, faster and more
malleable. Salt accomplishes this via its ability to handle larger loads of
information, and not just dozens, but hundreds or even thousands of individual
servers, handle them quickly and through a simple and manageable interface.


%package    master
Summary:    Management component for salt, a parallel remote execution system
Group:      System Environment/Daemons
Requires:   %{name} = %{version}-%{release}
Provides:   salt-master = %{version}
Obsoletes:  salt3-master < 3006

%description master
The Salt master is the central server to which all minions connect.


%package    minion
Summary:    Client component for Salt, a parallel remote execution system
Group:      System Environment/Daemons
Requires:   %{name} = %{version}-%{release}
Provides:   salt-minion = %{version}
Obsoletes:  salt3-minion < 3006

%description minion
The Salt minion is the agent component of Salt. It listens for instructions
from the master, runs jobs, and returns results back to the master.


%package    syndic
Summary:    Master-of-master component for Salt, a parallel remote execution system
Group:      System Environment/Daemons
Requires:   %{name}-master = %{version}-%{release}
Provides:   salt-syndic = %{version}
Obsoletes:  salt3-syndic < 3006

%description syndic
The Salt syndic is a master daemon which can receive instruction from a
higher-level master, allowing for tiered organization of your Salt
infrastructure.


%package    api
Summary:    REST API for Salt, a parallel remote execution system
Group:      Applications/System
Requires:   %{name}-master = %{version}-%{release}
Provides:   salt-api = %{version}
Obsoletes:  salt3-api < 3006

%description api
salt-api provides a REST interface to the Salt master.


%package    cloud
Summary:    Cloud provisioner for Salt, a parallel remote execution system
Group:      Applications/System
Requires:   %{name}-master = %{version}-%{release}
Provides:   salt-cloud = %{version}
Obsoletes:  salt3-cloud < 3006

%description cloud
The salt-cloud tool provisions new cloud VMs, installs salt-minion on them, and
adds them to the master's collection of controllable minions.


%package    ssh
Summary:    Agentless SSH-based version of Salt, a parallel remote execution system
Group:      Applications/System
Requires:   %{name} = %{version}-%{release}
Provides:   salt-ssh = %{version}
Obsoletes:  salt3-ssh < 3006

%description ssh
The salt-ssh tool can run remote execution functions and states without the use
of an agent (salt-minion) service.


%build
unset CC
unset CXX
unset CPPFLAGS
unset CXXFLAGS
unset CFLAGS
unset LDFLAGS
rm -rf $RPM_BUILD_DIR
mkdir -p $RPM_BUILD_DIR/build
cd $RPM_BUILD_DIR

%if "%{getenv:SALT_ONEDIR_ARCHIVE}" == ""
  export PIP_CONSTRAINT=%{_salt_src}/requirements/constraints.txt
  export FETCH_RELENV_VERSION=${SALT_RELENV_VERSION}
  python3 -m venv --clear --copies build/venv
  build/venv/bin/python3 -m pip install relenv==${SALT_RELENV_VERSION}
  export FETCH_RELENV_VERSION=${SALT_RELENV_VERSION}
  export PY=$(build/venv/bin/python3 -c 'import sys; sys.stdout.write("{}.{}".format(*sys.version_info)); sys.stdout.flush()')
  build/venv/bin/python3 -m pip install -r %{_salt_src}/requirements/static/ci/py${PY}/tools.txt
  build/venv/bin/relenv fetch --python=${SALT_PYTHON_VERSION}
  build/venv/bin/pip install ppbt
  pushd %{_salt_src}
	$RPM_BUILD_DIR/build/venv/bin/tools pkg build onedir-dependencies --arch ${SALT_PACKAGE_ARCH} --relenv-version=${SALT_RELENV_VERSION} --python-version ${SALT_PYTHON_VERSION} --package-name $RPM_BUILD_DIR/build/salt --platform linux

  # Fix any hardcoded paths to the relenv python binary on any of the scripts installed in
  # the <onedir>/bin directory
  find $RPM_BUILD_DIR/build/salt/bin/ -type f -exec sed -i 's:#!/\(.*\)salt/bin/python3:#!/bin/sh\n"exec" "$(dirname $(readlink -f $0))/python3" "$0" "$@":g' {} \;

  $RPM_BUILD_DIR/build/venv/bin/tools pkg build salt-onedir . --package-name $RPM_BUILD_DIR/build/salt --platform linux
  $RPM_BUILD_DIR/build/venv/bin/tools pkg pre-archive-cleanup --pkg $RPM_BUILD_DIR/build/salt
  popd
  build/venv/bin/python3 -m pip uninstall -y ppbt

  # Generate master config
  sed 's/#user: root/user: salt/g' %{_salt_src}/conf/master > $RPM_BUILD_DIR/build/master

%else
  # The relenv onedir is being provided, all setup up until Salt is installed
  # is expected to be done
  cd build
  tar xf ${SALT_ONEDIR_ARCHIVE}

  # Fix any hardcoded paths to the relenv python binary on any of the scripts installed in the <onedir>/bin directory
  find salt/bin/ -type f -exec sed -i 's:#!/\(.*\)salt/bin/python3:#!/bin/sh\n"exec" "$$(dirname $$(readlink -f $$0))/python3" "$$0" "$$@":g' {} \;

  # Generate master config
  sed 's/#user: root/user: salt/g' %{_salt_src}/conf/master > $RPM_BUILD_DIR/build/master

  cd $RPM_BUILD_DIR
%endif


%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/opt/saltstack
cp -R $RPM_BUILD_DIR/build/salt %{buildroot}/opt/saltstack/

# Add some directories
install -d -m 0755 %{buildroot}%{_var}/log/salt
install -d -m 0755 %{buildroot}%{_var}/run/salt
install -d -m 0755 %{buildroot}%{_var}/run/salt/master
install -d -m 0755 %{buildroot}%{_var}/cache/salt
install -Dd -m 0750 %{buildroot}%{_var}/cache/salt/master
install -Dd -m 0750 %{buildroot}%{_var}/cache/salt/minion
install -Dd -m 0750 %{buildroot}%{_var}/cache/salt/master/jobs
install -Dd -m 0750 %{buildroot}%{_var}/cache/salt/master/proc
install -Dd -m 0750 %{buildroot}%{_var}/cache/salt/master/queues
install -Dd -m 0750 %{buildroot}%{_var}/cache/salt/master/roots
install -Dd -m 0750 %{buildroot}%{_var}/cache/salt/master/syndics
install -Dd -m 0750 %{buildroot}%{_var}/cache/salt/master/tokens
install -d -m 0755 %{buildroot}%{_sysconfdir}/salt
install -d -m 0755 %{buildroot}%{_sysconfdir}/salt/master.d
install -d -m 0755 %{buildroot}%{_sysconfdir}/salt/minion.d
install -d -m 0755 %{buildroot}%{_sysconfdir}/salt/pki
install -d -m 0700 %{buildroot}%{_sysconfdir}/salt/pki/master
install -Dd -m 0750 %{buildroot}%{_sysconfdir}/salt/pki/master/minions
install -Dd -m 0750 %{buildroot}%{_sysconfdir}/salt/pki/master/minions_autosign
install -Dd -m 0750 %{buildroot}%{_sysconfdir}/salt/pki/master/minions_denied
install -Dd -m 0750 %{buildroot}%{_sysconfdir}/salt/pki/master/minions_pre
install -Dd -m 0750 %{buildroot}%{_sysconfdir}/salt/pki/master/minions_rejected
install -d -m 0700 %{buildroot}%{_sysconfdir}/salt/pki/minion
install -d -m 0700 %{buildroot}%{_sysconfdir}/salt/cloud.conf.d
install -d -m 0700 %{buildroot}%{_sysconfdir}/salt/cloud.deploy.d
install -d -m 0700 %{buildroot}%{_sysconfdir}/salt/cloud.maps.d
install -d -m 0700 %{buildroot}%{_sysconfdir}/salt/cloud.profiles.d
install -d -m 0700 %{buildroot}%{_sysconfdir}/salt/cloud.providers.d
install -d -m 0755 %{buildroot}%{_sysconfdir}/salt/proxy.d
install -d -m 0755 %{buildroot}%{_bindir}

install -m 0755 %{buildroot}/opt/saltstack/salt/salt %{buildroot}%{_bindir}/salt
install -m 0755 %{buildroot}/opt/saltstack/salt/salt-call %{buildroot}%{_bindir}/salt-call
install -m 0755 %{buildroot}/opt/saltstack/salt/salt-master %{buildroot}%{_bindir}/salt-master
install -m 0755 %{buildroot}/opt/saltstack/salt/salt-minion %{buildroot}%{_bindir}/salt-minion
install -m 0755 %{buildroot}/opt/saltstack/salt/salt-api %{buildroot}%{_bindir}/salt-api
install -m 0755 %{buildroot}/opt/saltstack/salt/salt-cp %{buildroot}%{_bindir}/salt-cp
install -m 0755 %{buildroot}/opt/saltstack/salt/salt-key %{buildroot}%{_bindir}/salt-key
install -m 0755 %{buildroot}/opt/saltstack/salt/salt-run %{buildroot}%{_bindir}/salt-run
install -m 0755 %{buildroot}/opt/saltstack/salt/salt-cloud %{buildroot}%{_bindir}/salt-cloud
install -m 0755 %{buildroot}/opt/saltstack/salt/salt-ssh %{buildroot}%{_bindir}/salt-ssh
install -m 0755 %{buildroot}/opt/saltstack/salt/salt-syndic %{buildroot}%{_bindir}/salt-syndic
install -m 0755 %{buildroot}/opt/saltstack/salt/salt-proxy %{buildroot}%{_bindir}/salt-proxy
install -m 0755 %{buildroot}/opt/saltstack/salt/spm %{buildroot}%{_bindir}/spm
install -m 0755 %{buildroot}/opt/saltstack/salt/salt-pip %{buildroot}%{_bindir}/salt-pip

# Add the config files
install -p -m 0640 %{_salt_src}/conf/minion %{buildroot}%{_sysconfdir}/salt/minion
install -p -m 0640 $RPM_BUILD_DIR/build/master %{buildroot}%{_sysconfdir}/salt/master
install -p -m 0640 %{_salt_src}/conf/cloud %{buildroot}%{_sysconfdir}/salt/cloud
install -p -m 0640 %{_salt_src}/conf/roster %{buildroot}%{_sysconfdir}/salt/roster
install -p -m 0640 %{_salt_src}/conf/proxy %{buildroot}%{_sysconfdir}/salt/proxy

# Add the unit files
mkdir -p %{buildroot}%{_unitdir}
install -p -m 0644 %{_salt_src}/pkg/common/salt-master.service %{buildroot}%{_unitdir}/
install -p -m 0644 %{_salt_src}/pkg/common/salt-minion.service %{buildroot}%{_unitdir}/
install -p -m 0644 %{_salt_src}/pkg/common/salt-api.service %{buildroot}%{_unitdir}/
install -p -m 0644 %{_salt_src}/pkg/common/salt-syndic.service %{buildroot}%{_unitdir}/
install -p -m 0644 %{_salt_src}/pkg/common/salt-proxy@.service %{buildroot}%{_unitdir}/

# Logrotate
#install -p %{SOURCE10} .
mkdir -p %{buildroot}%{_sysconfdir}/logrotate.d/
install -p -m 0644 %{_salt_src}/pkg/common/logrotate/salt-common %{buildroot}%{_sysconfdir}/logrotate.d/salt

# Bash completion
mkdir -p %{buildroot}%{_sysconfdir}/bash_completion.d/
install -p -m 0644 %{_salt_src}/pkg/rpm/salt.bash %{buildroot}%{_sysconfdir}/bash_completion.d/salt.bash

# Fish completion (TBD remove -v)
mkdir -p %{buildroot}%{fish_dir}
install -p -m 0644 %{_salt_src}/pkg/common/fish-completions/*.fish  %{buildroot}%{fish_dir}/

# Man files
mkdir -p %{buildroot}%{_mandir}/man1
mkdir -p %{buildroot}%{_mandir}/man7
install -p -m 0644 %{_salt_src}/doc/man/spm.1 %{buildroot}%{_mandir}/man1/spm.1
install -p -m 0644 %{_salt_src}/doc/man/spm.1 %{buildroot}%{_mandir}/man1/spm.1
install -p -m 0644 %{_salt_src}/doc/man/salt.1 %{buildroot}%{_mandir}/man1/salt.1
install -p -m 0644 %{_salt_src}/doc/man/salt.7 %{buildroot}%{_mandir}/man7/salt.7
install -p -m 0644 %{_salt_src}/doc/man/salt-cp.1 %{buildroot}%{_mandir}/man1/salt-cp.1
install -p -m 0644 %{_salt_src}/doc/man/salt-key.1 %{buildroot}%{_mandir}/man1/salt-key.1
install -p -m 0644 %{_salt_src}/doc/man/salt-master.1 %{buildroot}%{_mandir}/man1/salt-master.1
install -p -m 0644 %{_salt_src}/doc/man/salt-run.1 %{buildroot}%{_mandir}/man1/salt-run.1
install -p -m 0644 %{_salt_src}/doc/man/salt-call.1 %{buildroot}%{_mandir}/man1/salt-call.1
install -p -m 0644 %{_salt_src}/doc/man/salt-minion.1 %{buildroot}%{_mandir}/man1/salt-minion.1
install -p -m 0644 %{_salt_src}/doc/man/salt-proxy.1 %{buildroot}%{_mandir}/man1/salt-proxy.1
install -p -m 0644 %{_salt_src}/doc/man/salt-syndic.1 %{buildroot}%{_mandir}/man1/salt-syndic.1
install -p -m 0644 %{_salt_src}/doc/man/salt-api.1 %{buildroot}%{_mandir}/man1/salt-api.1
install -p -m 0644 %{_salt_src}/doc/man/salt-cloud.1 %{buildroot}%{_mandir}/man1/salt-cloud.1
install -p -m 0644 %{_salt_src}/doc/man/salt-ssh.1 %{buildroot}%{_mandir}/man1/salt-ssh.1


%clean
rm -rf %{buildroot}


%files
%defattr(-,root,root,-)
%{_sysconfdir}/logrotate.d/salt
%{_sysconfdir}/bash_completion.d/salt.bash
%config(noreplace) %{fish_dir}/salt*.fish
%dir %{_var}/cache/salt
%dir %{_var}/run/salt
%dir %{_var}/log/salt
%doc %{_mandir}/man1/spm.1*
%{_bindir}/spm
%{_bindir}/salt-pip
/opt/saltstack/salt
%dir %{_sysconfdir}/salt
%dir %{_sysconfdir}/salt/pki


%files master
%defattr(-,root,root)
%doc %{_mandir}/man7/salt.7*
%doc %{_mandir}/man1/salt.1*
%doc %{_mandir}/man1/salt-cp.1*
%doc %{_mandir}/man1/salt-key.1*
%doc %{_mandir}/man1/salt-master.1*
%doc %{_mandir}/man1/salt-run.1*
%{_bindir}/salt
%{_bindir}/salt-cp
%{_bindir}/salt-key
%{_bindir}/salt-master
%{_bindir}/salt-run
%{_unitdir}/salt-master.service
%config(noreplace) %{_sysconfdir}/salt/master
%dir %{_sysconfdir}/salt/master.d
%config(noreplace) %{_sysconfdir}/salt/pki/master
%dir %attr(0750, salt, salt) %{_sysconfdir}/salt/pki/master/
%dir %attr(0750, salt, salt) %{_sysconfdir}/salt/pki/master/minions/
%dir %attr(0750, salt, salt) %{_sysconfdir}/salt/pki/master/minions_autosign/
%dir %attr(0750, salt, salt) %{_sysconfdir}/salt/pki/master/minions_denied/
%dir %attr(0750, salt, salt) %{_sysconfdir}/salt/pki/master/minions_pre/
%dir %attr(0750, salt, salt) %{_sysconfdir}/salt/pki/master/minions_rejected/
%dir %attr(0750, salt, salt) %{_var}/run/salt/master/
%dir %attr(0750, salt, salt) %{_var}/cache/salt/master/
%dir %attr(0750, salt, salt) %{_var}/cache/salt/master/jobs/
%dir %attr(0750, salt, salt) %{_var}/cache/salt/master/proc/
%dir %attr(0750, salt, salt) %{_var}/cache/salt/master/queues/
%dir %attr(0750, salt, salt) %{_var}/cache/salt/master/roots/
%dir %attr(0750, salt, salt) %{_var}/cache/salt/master/syndics/
%dir %attr(0750, salt, salt) %{_var}/cache/salt/master/tokens/


%files minion
%defattr(-,root,root)
%doc %{_mandir}/man1/salt-call.1*
%doc %{_mandir}/man1/salt-minion.1*
%doc %{_mandir}/man1/salt-proxy.1*
%{_bindir}/salt-minion
%{_bindir}/salt-call
%{_bindir}/salt-proxy
%{_unitdir}/salt-minion.service
%{_unitdir}/salt-proxy@.service
%config(noreplace) %{_sysconfdir}/salt/minion
%config(noreplace) %{_sysconfdir}/salt/proxy
%config(noreplace) %{_sysconfdir}/salt/pki/minion
%dir %{_sysconfdir}/salt/minion.d
%dir %attr(0750, root, root) %{_var}/cache/salt/minion/


%files syndic
%doc %{_mandir}/man1/salt-syndic.1*
%{_bindir}/salt-syndic
%{_unitdir}/salt-syndic.service


%files api
%defattr(-,root,root)
%doc %{_mandir}/man1/salt-api.1*
%{_bindir}/salt-api
%{_unitdir}/salt-api.service


%files cloud
%doc %{_mandir}/man1/salt-cloud.1*
%{_bindir}/salt-cloud
%{_sysconfdir}/salt/cloud.conf.d
%{_sysconfdir}/salt/cloud.deploy.d
%{_sysconfdir}/salt/cloud.maps.d
%{_sysconfdir}/salt/cloud.profiles.d
%{_sysconfdir}/salt/cloud.providers.d
%config(noreplace) %{_sysconfdir}/salt/cloud


%files ssh
%doc %{_mandir}/man1/salt-ssh.1*
%{_bindir}/salt-ssh
%config(noreplace) %{_sysconfdir}/salt/roster


%pre
# create user to avoid running server as root
# 1. create group if not existing
if ! getent group %{_SALT_GROUP}; then
   groupadd --system %{_SALT_GROUP} 2>/dev/null ||true
fi
# 2. create homedir if not existing
test -d %{_SALT_HOME} || mkdir -p %{_SALT_HOME}
# 3. create user if not existing
#         -g %{_SALT_GROUP} \
if ! getent passwd | grep -q "^%{_SALT_USER}:"; then
  useradd --system \
          --no-create-home \
          -s /sbin/nologin \
          -g %{_SALT_GROUP} \
          %{_SALT_USER} 2>/dev/null || true
fi
# 4. adjust passwd entry
usermod -c "%{_SALT_NAME}" \
        -d %{_SALT_HOME}   \
        -g %{_SALT_GROUP}  \
         %{_SALT_USER}

%pre master
if [ $1 -gt 1 ] ; then
    # Reset permissions to match previous installs - performing upgrade
    _MS_LCUR_USER=$(ls -dl /run/salt/master | cut -d ' ' -f 3)
    _MS_LCUR_GROUP=$(ls -dl /run/salt/master | cut -d ' ' -f 4)
    %global _MS_CUR_USER  %{_MS_LCUR_USER}
    %global _MS_CUR_GROUP %{_MS_LCUR_GROUP}
fi

%pre syndic
if [ $1 -gt 1 ] ; then
    # Reset permissions to match previous installs - performing upgrade
    _MS_LCUR_USER=$(ls -dl /run/salt/master | cut -d ' ' -f 3)
    _MS_LCUR_GROUP=$(ls -dl /run/salt/master | cut -d ' ' -f 4)
    %global _MS_CUR_USER  %{_MS_LCUR_USER}
    %global _MS_CUR_GROUP %{_MS_LCUR_GROUP}
fi

%pre minion
if [ $1 -gt 1 ] ; then
    # Reset permissions to match previous installs - performing upgrade
    _MN_LCUR_USER=$(ls -dl /run/salt/minion | cut -d ' ' -f 3)
    _MN_LCUR_GROUP=$(ls -dl /run/salt/minion | cut -d ' ' -f 4)
    %global _MN_CUR_USER  %{_MN_LCUR_USER}
    %global _MN_CUR_GROUP %{_MN_LCUR_GROUP}
fi


%pre cloud
if [ $1 -gt 1 ] ; then
    # Reset permissions to match previous installs - performing upgrade
    _MS_LCUR_USER=$(ls -dl /etc/salt/cloud.deploy.d | cut -d ' ' -f 3)
    _MS_LCUR_GROUP=$(ls -dl /etc/salt/cloud.deploy.d | cut -d ' ' -f 4)
    %global _MS_CUR_USER  %{_MS_LCUR_USER}
    %global _MS_CUR_GROUP %{_MS_LCUR_GROUP}
fi

# assumes systemd for RHEL 7 & 8 & 9
# foregoing %systemd_* scriptlets due to RHEL 7/8 vs. RHEL 9 incompatibilities
## - Using hardcoded scriptlet definitions from RHEL 7/8 that are forward-compatible
%preun master
# RHEL 9 is giving warning msg if syndic is not installed, supress it
# %%systemd_preun salt-syndic.service > /dev/null 2>&1
if [ $1 -eq 0 ] ; then
  # Package removal, not upgrade
  /bin/systemctl --no-reload disable salt-syndic.service > /dev/null 2>&1 || :
  /bin/systemctl stop salt-syndic.service > /dev/null 2>&1 || :
fi

%preun syndic
# %%systemd_preun salt-syndic.service
if [ $1 -eq 0 ] ; then
  # Package removal, not upgrade
  /bin/systemctl --no-reload disable salt-syndic.service > /dev/null 2>&1 || :
  /bin/systemctl stop salt-syndic.service > /dev/null 2>&1 || :
fi

%preun minion
# %%systemd_preun salt-minion.service
if [ $1 -eq 0 ] ; then
  # Package removal, not upgrade
  /bin/systemctl --no-reload disable salt-minion.service > /dev/null 2>&1 || :
  /bin/systemctl stop salt-minion.service > /dev/null 2>&1 || :
fi

%preun api
# %%systemd_preun salt-api.service
if [ $1 -eq 0 ] ; then
  # Package removal, not upgrade
  /bin/systemctl --no-reload disable salt-api.service > /dev/null 2>&1 || :
  /bin/systemctl stop salt-api.service > /dev/null 2>&1 || :
fi


%post
ln -s -f /opt/saltstack/salt/spm %{_bindir}/spm
ln -s -f /opt/saltstack/salt/salt-pip %{_bindir}/salt-pip
/opt/saltstack/salt/bin/python3 -m compileall -qq /opt/saltstack/salt/lib


%post cloud
ln -s -f /opt/saltstack/salt/salt-cloud %{_bindir}/salt-cloud


%post master
ln -s -f /opt/saltstack/salt/salt %{_bindir}/salt
ln -s -f /opt/saltstack/salt/salt-cp %{_bindir}/salt-cp
ln -s -f /opt/saltstack/salt/salt-key %{_bindir}/salt-key
ln -s -f /opt/saltstack/salt/salt-master %{_bindir}/salt-master
ln -s -f /opt/saltstack/salt/salt-run %{_bindir}/salt-run
if [ $1 -lt 2 ]; then
  # install
  # ensure hmac are up to date, master or minion, rest install one or the other
  # key used is from openssl/crypto/fips/fips_standalone_hmac.c openssl 1.1.1k
  if [ $(cat /etc/os-release | grep VERSION_ID | cut -d '=' -f 2 | sed  's/\"//g' | cut -d '.' -f 1) = "8" ]; then
    if [ -e /opt/saltstack/salt/lib/libssl.so.1.1 ]; then
      /bin/openssl sha256 -r -hmac orboDeJITITejsirpADONivirpUkvarP /opt/saltstack/salt/lib/libssl.so.1.1 | cut -d ' ' -f 1 > /opt/saltstack/salt/lib/.libssl.so.1.1.hmac || :
    fi
    if [ -e /opt/saltstack/salt/lib/libcrypto.so.1.1 ]; then
      /bin/openssl sha256 -r -hmac orboDeJITITejsirpADONivirpUkvarP /opt/saltstack/salt/lib/libcrypto.so.1.1 | cut -d ' ' -f 1 > /opt/saltstack/salt/lib/.libcrypto.so.1.1.hmac || :
    fi
  fi
fi
# %%systemd_post salt-master.service
if [ $1 -gt 1 ] ; then
  # Upgrade
  /bin/systemctl try-restart salt-master.service >/dev/null 2>&1 || :
else
  # Initial installation
  /bin/systemctl preset salt-master.service >/dev/null 2>&1 || :
fi

%post syndic
ln -s -f /opt/saltstack/salt/salt-syndic %{_bindir}/salt-syndic
# %%systemd_post salt-syndic.service
if [ $1 -gt 1 ] ; then
  # Upgrade
  /bin/systemctl try-restart salt-syndic.service >/dev/null 2>&1 || :
else
  # Initial installation
  /bin/systemctl preset salt-syndic.service >/dev/null 2>&1 || :
fi

%post minion
ln -s -f /opt/saltstack/salt/salt-minion %{_bindir}/salt-minion
ln -s -f /opt/saltstack/salt/salt-call %{_bindir}/salt-call
ln -s -f /opt/saltstack/salt/salt-proxy %{_bindir}/salt-proxy
if [ $1 -lt 2 ]; then
  # install
  # ensure hmac are up to date, master or minion, rest install one or the other
  # key used is from openssl/crypto/fips/fips_standalone_hmac.c openssl 1.1.1k
  if [ $(cat /etc/os-release | grep VERSION_ID | cut -d '=' -f 2 | sed  's/\"//g' | cut -d '.' -f 1) = "8" ]; then
    if [ -e /opt/saltstack/salt/lib/libssl.so.1.1 ]; then
      /bin/openssl sha256 -r -hmac orboDeJITITejsirpADONivirpUkvarP /opt/saltstack/salt/lib/libssl.so.1.1 | cut -d ' ' -f 1 > /opt/saltstack/salt/lib/.libssl.so.1.1.hmac || :
    fi
    if [ -e /opt/saltstack/salt/lib/libcrypto.so.1.1 ]; then
      /bin/openssl sha256 -r -hmac orboDeJITITejsirpADONivirpUkvarP /opt/saltstack/salt/lib/libcrypto.so.1.1 | cut -d ' ' -f 1 > /opt/saltstack/salt/lib/.libcrypto.so.1.1.hmac || :
    fi
  fi
fi
# %%systemd_post salt-minion.service
if [ $1 -gt 1 ] ; then
  # Upgrade
  /bin/systemctl try-restart salt-minion.service >/dev/null 2>&1 || :
else
  # Initial installation
  /bin/systemctl preset salt-minion.service >/dev/null 2>&1 || :
fi

%post ssh
ln -s -f /opt/saltstack/salt/salt-ssh %{_bindir}/salt-ssh

%post api
ln -s -f /opt/saltstack/salt/salt-api %{_bindir}/salt-api
# %%systemd_post salt-api.service
if [ $1 -gt 1 ] ; then
  # Upgrade
  /bin/systemctl try-restart salt-api.service >/dev/null 2>&1 || :
else
  # Initial installation
  /bin/systemctl preset salt-api.service >/dev/null 2>&1 || :
fi


%posttrans cloud
PY_VER=$(/opt/saltstack/salt/bin/python3 -c "import sys; sys.stdout.write('{}.{}'.format(*sys.version_info)); sys.stdout.flush();")
if [ ! -e "/var/log/salt/cloud" ]; then
  touch /var/log/salt/cloud
  chmod 640 /var/log/salt/cloud
fi
if [ $1 -gt 1 ] ; then
    # Reset permissions to match previous installs - performing upgrade
    chown -R %{_MS_CUR_USER}:%{_MS_CUR_GROUP} /etc/salt/cloud.deploy.d /var/log/salt/cloud /opt/saltstack/salt/lib/python${PY_VER}/site-packages/salt/cloud/deploy
else
    chown -R %{_SALT_USER}:%{_SALT_GROUP} /etc/salt/cloud.deploy.d /var/log/salt/cloud /opt/saltstack/salt/lib/python${PY_VER}/site-packages/salt/cloud/deploy
fi


%posttrans master
if [ ! -e "/var/log/salt/master" ]; then
  touch /var/log/salt/master
  chmod 640 /var/log/salt/master
fi
if [ ! -e "/var/log/salt/key" ]; then
  touch /var/log/salt/key
  chmod 640 /var/log/salt/key
fi
if [ $1 -gt 1 ] ; then
    # Reset permissions to match previous installs - performing upgrade
    chown -R %{_MS_CUR_USER}:%{_MS_CUR_GROUP} /etc/salt/pki/master /etc/salt/master.d /var/log/salt/master /var/log/salt/key /var/cache/salt/master /var/run/salt/master
else
    chown -R %{_SALT_USER}:%{_SALT_GROUP} /etc/salt/pki/master /etc/salt/master.d /var/log/salt/master /var/log/salt/key /var/cache/salt/master /var/run/salt/master
fi


%posttrans syndic
if [ ! -e "/var/log/salt/syndic" ]; then
  touch /var/log/salt/syndic
  chmod 640 /var/log/salt/syndic
fi
if [ $1 -gt 1 ] ; then
    # Reset permissions to match previous installs - performing upgrade
    chown -R %{_MS_CUR_USER}:%{_MS_CUR_GROUP} /var/log/salt/syndic
else
    chown -R %{_SALT_USER}:%{_SALT_GROUP} /var/log/salt/syndic
fi


%posttrans api
if [ ! -e "/var/log/salt/api" ]; then
  touch /var/log/salt/api
  chmod 640 /var/log/salt/api
fi
if [ $1 -gt 1 ] ; then
    # Reset permissions to match previous installs - performing upgrade
    chown -R %{_MS_CUR_USER}:%{_MS_CUR_GROUP} /var/log/salt/api
else
    chown -R %{_SALT_USER}:%{_SALT_GROUP} /var/log/salt/api
fi

%posttrans minion
if [ ! -e "/var/log/salt/minion" ]; then
  touch /var/log/salt/minion
  chmod 640 /var/log/salt/minion
fi
if [ ! -e "/var/log/salt/key" ]; then
  touch /var/log/salt/key
  chmod 640 /var/log/salt/key
fi
if [ $1 -gt 1 ] ; then
    # Reset permissions to match previous installs - performing upgrade
    chown -R %{_MN_CUR_USER}:%{_MN_CUR_GROUP} /etc/salt/pki/minion /etc/salt/minion.d /var/log/salt/minion /var/cache/salt/minion /var/run/salt/minion
fi


%preun
if [ $1 -eq 0 ]; then
  # Uninstall
  find /opt/saltstack/salt -type f -name \*\.pyc -print0 | xargs --null --no-run-if-empty rm
  find /opt/saltstack/salt -type d -name __pycache__ -empty -print0 | xargs --null --no-run-if-empty rmdir
fi

%postun master
# %%systemd_postun_with_restart salt-master.service
/bin/systemctl daemon-reload >/dev/null 2>&1 || :
if [ $1 -ge 1 ] ; then
  # Package upgrade, not uninstall
  /bin/systemctl try-restart salt-master.service >/dev/null 2>&1 || :
fi
if [ $1 -eq 0 ]; then
  if [ $(cat /etc/os-release | grep VERSION_ID | cut -d '=' -f 2 | sed  's/\"//g' | cut -d '.' -f 1) = "8" ]; then
    if [ -z "$(rpm -qi salt-minion | grep Name | grep salt-minion)" ]; then
      # uninstall and no minion running
      if [ -e  /opt/saltstack/salt/lib/.libssl.so.1.1.hmac ]; then
        /bin/rm -f /opt/saltstack/salt/lib/.libssl.so.1.1.hmac || :
      fi
      if [ -e /opt/saltstack/salt/lib/.libcrypto.so.1.1.hmac ]; then
        /bin/rm -f /opt/saltstack/salt/lib/.libcrypto.so.1.1.hmac || :
      fi
    fi
  fi
fi

%postun syndic
# %%systemd_postun_with_restart salt-syndic.service
/bin/systemctl daemon-reload >/dev/null 2>&1 || :
if [ $1 -ge 1 ] ; then
  # Package upgrade, not uninstall
  /bin/systemctl try-restart salt-syndic.service >/dev/null 2>&1 || :
fi

%postun minion
# %%systemd_postun_with_restart salt-minion.service
/bin/systemctl daemon-reload >/dev/null 2>&1 || :
if [ $1 -ge 1 ] ; then
  # Package upgrade, not uninstall
  /bin/systemctl try-restart salt-minion.service >/dev/null 2>&1 || :
fi
if [ $1 -eq 0 ]; then
  if [ $(cat /etc/os-release | grep VERSION_ID | cut -d '=' -f 2 | sed  's/\"//g' | cut -d '.' -f 1) = "8" ]; then
    if [ -z "$(rpm -qi salt-master | grep Name | grep salt-master)" ]; then
      # uninstall and no master running
      if [ -e /opt/saltstack/salt/lib/.libssl.so.1.1.hmac ]; then
        /bin/rm -f /opt/saltstack/salt/lib/.libssl.so.1.1.hmac || :
      fi
      if [ -e /opt/saltstack/salt/lib/.libcrypto.so.1.1.hmac ]; then
        /bin/rm -f /opt/saltstack/salt/lib/.libcrypto.so.1.1.hmac || :
      fi
    fi
  fi
fi

%postun api
# %%systemd_postun_with_restart salt-api.service
/bin/systemctl daemon-reload >/dev/null 2>&1 || :
if [ $1 -ge 1 ] ; then
  # Package upgrade, not uninstall
  /bin/systemctl try-restart salt-api.service >/dev/null 2>&1 || :
fi

%changelog
* Thu Jul 10 2025 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.14

# Fixed

- Onedir packages include relenv 0.19.4.
  - Update sqlite to 3500200
  - Update libffi to 3.5.1
  - Update python 3.13 to 3.13.5
  - Load default openssl modules when no system openssl binary exists [#68014](https://github.com/saltstack/salt/issues/68014)
- pkgrepo.managed not applying changes / account for 'name' attr being part of the state [#68107](https://github.com/saltstack/salt/issues/68107)
- Fix `test mode` causing unintended execution when non-boolean values are passed. [#68121](https://github.com/saltstack/salt/issues/68121)


* Thu Jun 26 2025 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.13

# Fixed

- Return target path for symlinks and junctions on Windows [#54484](https://github.com/saltstack/salt/issues/54484)
- Fixed `Pillar payload signature failed to validate` error on master failover [#62318](https://github.com/saltstack/salt/issues/62318)
- Fixes an issue running powershell commands that begin with parenthesis or
  other commands that do not require an ampersand [#67190](https://github.com/saltstack/salt/issues/67190)
- Make x509 module compatible with M2Crypto 0.44.0. [#67782](https://github.com/saltstack/salt/issues/67782)
- Fix syndic event forwarding [#67936](https://github.com/saltstack/salt/issues/67936)
- Fix cp.push module function and its integration test [#67941](https://github.com/saltstack/salt/issues/67941)
- logging regression: fix loglines/findCaller introspection [#68057](https://github.com/saltstack/salt/issues/68057)
- Handle git@github.com:saltstack/salt style remotes in remote url validation [#68069](https://github.com/saltstack/salt/issues/68069)
- Fix GitFS file_find for file in sub-directories [#68072](https://github.com/saltstack/salt/issues/68072)
- Fix install in Ubuntu 24.04 noble Docker by using groupadd rather than addgroup. [#68073](https://github.com/saltstack/salt/issues/68073)
- Token validation removes token from request handler payload [#68076](https://github.com/saltstack/salt/issues/68076)
- Fix minion connectivity issues by ensuring auth notices refreshed session token [#68079](https://github.com/saltstack/salt/issues/68079)
- Fix file_recv path verification to allow subdirs used by cp.push [#68087](https://github.com/saltstack/salt/issues/68087)
- Fixes an issue on Windows where cmd.run wasn't handling commands sent as a
  list [#68095](https://github.com/saltstack/salt/issues/68095)
- Disconnect ipc clients that stop consuming [#68114](https://github.com/saltstack/salt/issues/68114)


* Thu Jun 12 2025 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.12

# Fixed

- CVE-2024-38822
  Multiple methods in the salt master skip minion token validation. Therefore a misbehaving minion can impersonate another minion.

  CVSS 2.7 V:N/AC:L/PR:H/UI:N/S:U/C:N/I:L/A:N

  CVE-2024-38823
  Salt's request server is vulnerable to replay attacks when not using a TLS encrypted transport.

  CVSS Score 2.7 AV:N/AC:L/PR:H/UI:N/S:U/C:N/I:L/A:N

  CVE-2024-38824
  Directory traversal vulnerability in recv_file method allows arbitrary files to be written to the master cache directory.

  CVSS Score 9.6 AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:N

  CVE-2024-38825
  The salt.auth.pki module does not properly authenticate callers. The "password" field contains a public certificate which is validated against a CA certificate by the module. This is not pki authentication, as the caller does not need access to the corresponding private key for the authentication attempt to be accepted.

  CVSS Score 6.4 AV:N/AC:L/PR:L/UI:N/S:C/C:L/I:L/A:N

  CVE-2025-22236
  Minion event bus authorization bypass. An attacker with access to a minion key can craft a message which may be able to execute a job on other minions (>= 3007.0).

  CVSS 8.1 AV:L/AC:L/PR:H/UI:N/S:C/C:H/I:H/A:L

  CVE-2025-22237
  An attacker with access to a minion key can exploit the 'on demand' pillar functionality with a specially crafted git url which could cause and arbitrary command to be run on the master with the same privileges as the master process.

  CVSS 6.7 AV:L/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H

  CVE-2025-22238
  Directory traversal attack in minion file cache creation. The master's default cache is vulnerable to a directory traversal attack. Which could be leveraged to write or overwrite 'cache' files outside of the cache directory.

  CVSS 4.2 AV:L/AC:L/PR:H/UI:R/S:U/C:N/I:H/A:N

  CVE-2025-22239
  Arbitrary event injection on Salt Master. The master's "_minion_event" method can be used by and authorized minion to send arbitrary events onto the master's event bus.

  CVSS 8.1 AV:L/AC:L/PR:H/UI:N/S:C/C:H/I:H/A:L

  CVE-2025-22240
  Arbitrary directory creation or file deletion. In the find_file method of the GitFS class, a path is created using os.path.join using unvalidated input from the “tgt_env” variable. This can be exploited by an attacker to delete any file on the Master's process has permissions to

  CVSS 6.3 AV:L/AC:H/PR:H/UI:R/S:U/C:H/I:H/A:H

  CVE-2025-22241
  File contents overwrite the VirtKey class is called when “on-demand pillar” data is requested and uses un-validated input to create paths to the “pki directory”. The functionality is used to auto-accept Minion authentication keys based on a pre-placed “authorization file” at a specific location and is present in the default configuration.

  CVSS 5.6 AV:L/AC:H/PR:H/UI:R/S:U/C:H/I:H/A:N

  CVE-2025-22242
  Worker process denial of service through file read operation. .A vulnerability exists in the Master's “pub_ret” method which is exposed to all minions. The un-sanitized input value “jid” is used to construct a path which is then opened for reading. An attacker could exploit this vulnerabilities by attempting to read from a filename that will not return any data, e.g. by targeting a pipe node on the proc file system.

  CVSS 5.6 AV:L/AC:H/PR:H/UI:R/S:U/C:H/I:N/A:H

  This release also includes sqlite 3.50.1 to address CVE-2025-29087 [#68033](https://github.com/saltstack/salt/issues/68033)


* Mon Jun 02 2025 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.11

# Fixed

- Fixes an issue with cmd.run where the command is a built-in command and must be
  run with cmd. [#54821](https://github.com/saltstack/salt/issues/54821)
- Show a better error when running cmd.* commands using runas and the
  runas user does not exist [#56680](https://github.com/saltstack/salt/issues/56680)
- Make sure the comment field is populated when test=True for the reg state [#65514](https://github.com/saltstack/salt/issues/65514)
- Fixed result detection of module.run from returned dict [#65842](https://github.com/saltstack/salt/issues/65842)
- Fix an issue with the osrelease_info grain that was displaying empty strings [#66936](https://github.com/saltstack/salt/issues/66936)
- support retry: True as per docs [#67049](https://github.com/saltstack/salt/issues/67049)
- Fixed if arguments are passed to the key delete all, -D, it will throw an error [#67903](https://github.com/saltstack/salt/issues/67903)
- Set virtual grain for docker using systemd and virt-what [#67905](https://github.com/saltstack/salt/issues/67905)
- Remove broken salt-common bash-completion links in root filesystem [#67915](https://github.com/saltstack/salt/issues/67915)
- Fix refresh of osrelease and related grains on Python 3.10+ [#67932](https://github.com/saltstack/salt/issues/67932)
- Re-add -oProxyCommand to ssh gateway arguments when ssh_gateway is present. [#67934](https://github.com/saltstack/salt/issues/67934)
- Repair Git state comment formatting [#67944](https://github.com/saltstack/salt/issues/67944)
- Use a Jscript Custom Action to stop the salt-minion service on Windows instead
  of a VBscript Custom Action due to future deprecation and security issues [#67982](https://github.com/saltstack/salt/issues/67982)


* Wed Mar 19 2025 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.10

# Removed

- Remove psutil_compat.py file, which should have been removed when RHEL 6 EOL [#66467](https://github.com/saltstack/salt/issues/66467)
- Removed dependency on bsdmainutils package for Debian and Ubuntu [#67184](https://github.com/saltstack/salt/issues/67184)

# Deprecated

- Drop Arch Linux support [#66886](https://github.com/saltstack/salt/issues/66886)
- Removed support for end of life Python 3.7 and 3.8 from pre-commit and requirements [#67729](https://github.com/saltstack/salt/issues/67729)

# Fixed

- Commands on Windows are now prefixed with ``cmd /c`` so that compound
  commands (commands separated by ``&&``) run properly when using ``runas`` [#44736](https://github.com/saltstack/salt/issues/44736)
- Issue 58969: Fixes an issue with `saltclass.expand_classes_in_order`
  function where it was losing nested classes states during class
  expansion. The logic now use `salt.utils.odict.OrderedDict` to keep
  the inclusion ordering. [#58969](https://github.com/saltstack/salt/issues/58969)
- Fix issue with RunAs on Windows so that usernames of all numeric characters
  are handled as strings [#59344](https://github.com/saltstack/salt/issues/59344)
- Fixed an issue on Windows where checking success_retcodes when using the
  runas parameter would fail. Now success_retcodes are checked correctly [#59977](https://github.com/saltstack/salt/issues/59977)
- Fix an issue with cmd.script in Windows so that the exit code from a script will
  be passed through to the retcode of the state [#60884](https://github.com/saltstack/salt/issues/60884)
- Fixed an issue uninstalling packages on Windows using pkg.removed where there
  are multiple versions of the same software installed [#61001](https://github.com/saltstack/salt/issues/61001)
- Ensure file clients for runner, wheel, local and caller are available from the client_cache if called upon. [#61416](https://github.com/saltstack/salt/issues/61416)
- Convert stdin string to bytes regardless of stdin_raw_newlines [#62501](https://github.com/saltstack/salt/issues/62501)
- Issue 63933: Fixes an issue with `saltclass.expanded_dict_from_minion`
  function where it was passing a reference to minion `dict` which was
  overridden by nested classes during class expansion. Copy the node
  definition with `copy.deepcopy` instead of passing a reference. [#63933](https://github.com/saltstack/salt/issues/63933)
- Fixed an intermittent issue with file.recurse where the state would
  report failure even on success. Makes sure symlinks are created
  after the target file is created [#64630](https://github.com/saltstack/salt/issues/64630)
- The 'profile' outputter does not crash with incorrectly formatted data [#65104](https://github.com/saltstack/salt/issues/65104)
- Updating version comparison for rpm and removed obsolete comparison methods for rpms [#65443](https://github.com/saltstack/salt/issues/65443)
- Fix batch mode hang indefinitely in some scenarios [#66249](https://github.com/saltstack/salt/issues/66249)
- Applying `selinux.fcontext_policy_present` to a shorter path than an existing entry now works [#66252](https://github.com/saltstack/salt/issues/66252)
- Correct bash-completion for Debian / Ubuntu [#66560](https://github.com/saltstack/salt/issues/66560)
- Fix minion config option startup_states [#66592](https://github.com/saltstack/salt/issues/66592)
- Fixed an issue with cmd.run with requirements when the shell is not the
  default [#66596](https://github.com/saltstack/salt/issues/66596)
- Fixes an issue when getting account names using the get_name function in the
  win_dacl.py salt util. Capability SIDs return ``None``. SIDs for deleted
  accounts return the SID. SIDs for domain accounts where the system is not
  connected to the domain return the SID. [#66637](https://github.com/saltstack/salt/issues/66637)
- Fixed an issue where ``status.master`` wasn't detecting a connection to the
  specified master properly [#66716](https://github.com/saltstack/salt/issues/66716)
- Fixed ``win_wua.available`` when some of the update objects are empty CDispatch
  objects. The ``available`` function no longer crashes [#66718](https://github.com/saltstack/salt/issues/66718)
- Clean up multiprocessing file handles on minion [#66726](https://github.com/saltstack/salt/issues/66726)
- Fixed nacl.keygen for not yet existing sk_file or pk_file [#66772](https://github.com/saltstack/salt/issues/66772)
- fix yaml output [#66783](https://github.com/saltstack/salt/issues/66783)
- Fixed an issue where enabling `grain_opts` in the minion config would cause
  some core grains to be overwritten. [#66784](https://github.com/saltstack/salt/issues/66784)
- Fix an issue where files created using `salt.utils.atomicile.atomic_open()`
  were created with restrictive permissions instead of respecting the umask. [#66786](https://github.com/saltstack/salt/issues/66786)
- Fix bad async_method name on AsyncPubClient class [#66789](https://github.com/saltstack/salt/issues/66789)
- Ensure Manjaro ARM reports the correct os_family of Arch. [#66796](https://github.com/saltstack/salt/issues/66796)
- Removed ``salt.utils.data.decode`` usage from the fileserver. This function was
  necessary to support Python 2. This speeds up loading the list cache by 80-90x. [#66835](https://github.com/saltstack/salt/issues/66835)
- Issue 66837: Fixes an issue with the `network.local_port_tcp` function
  where it was not parsing the IPv4 mapped IPv6 address correctly. The
  ``::ffff:`` is now removed and only the IP address is returned. [#66837](https://github.com/saltstack/salt/issues/66837)
- Better handling output of `systemctl --version` with salt.grains.core._systemd [#66856](https://github.com/saltstack/salt/issues/66856)
- Upgrade relenv to 0.17.3. This release includes python 3.10.15, openssl 3.2.3,
  and fixes for pip 24.2. [#66858](https://github.com/saltstack/salt/issues/66858)
- Remove caching of 'systemctl status' in systemd_service to fix automatic daemon-reload for repeated invocations. [#66864](https://github.com/saltstack/salt/issues/66864)
- Added cryptogrpahy back to base.txt requirements as a dependency [#66883](https://github.com/saltstack/salt/issues/66883)
- Remove "perms" from `linux_acl.list_absent()` documentation [#66891](https://github.com/saltstack/salt/issues/66891)
- Ensure minion start event coroutines are run [#66932](https://github.com/saltstack/salt/issues/66932)
- Allow for secure-boot efivars directory having SecureBoot-xxx files, not directories with a data file [#66955](https://github.com/saltstack/salt/issues/66955)
- Removed the usage of wmic to get the disk and iscsi grains for Windows. The wmic
  binary is being deprecated. [#66959](https://github.com/saltstack/salt/issues/66959)
- Fixes an issue with the LGPO module when trying to parse ADMX/ADML files
  that have a space in the XMLNS url in the policyDefinitionsResources header. [#66992](https://github.com/saltstack/salt/issues/66992)
- Ensured global dunders like __env__ are defined in state module that are run in parallel on spawning platforms [#66996](https://github.com/saltstack/salt/issues/66996)
- Filtered unpicklable objects from the context dict when invoking states in parallel on spawning platforms to avoid a crash [#66999](https://github.com/saltstack/salt/issues/66999)
- Update for deprecation of hex in pygit2 1.15.0 and above [#67017](https://github.com/saltstack/salt/issues/67017)
- Fixed blob path for salt.ufw in the firewall tutorial documentation [#67019](https://github.com/saltstack/salt/issues/67019)
- Update locations for bootstrap scripts, to new infrastructure, GitHub releases for bootstrap [#67020](https://github.com/saltstack/salt/issues/67020)
- Constrained the localfs module to operations inside the specified cachedir [#67031](https://github.com/saltstack/salt/issues/67031)
- Added support for dnf5 (backport from 3007) and update to its new command syntax changes since 2023 [#67057](https://github.com/saltstack/salt/issues/67057)
- Recognise newer AMD GPU devices [#67058](https://github.com/saltstack/salt/issues/67058)
- Fix yumpkg module for Python<3.8 [#67091](https://github.com/saltstack/salt/issues/67091)
- Fixed an issue with making changes to the Windows Firewall when the
  AllowInboundRules setting is set to True [#67122](https://github.com/saltstack/salt/issues/67122)
- Added support and tests for dnf5 to services_need_restart for yum packages [#67177](https://github.com/saltstack/salt/issues/67177)
- Use os.walk to traverse git branches, and no longer replace slash '/' in git branch names [#67722](https://github.com/saltstack/salt/issues/67722)
- Set correct virtual grain in systemd based Podman containers [#67733](https://github.com/saltstack/salt/issues/67733)
- Corrected option --upgrades for dnf[5] for function list_upgrades [#67743](https://github.com/saltstack/salt/issues/67743)
- Fix salt-ssh for hosts that use password as the SSH password [#67754](https://github.com/saltstack/salt/issues/67754)
- Corrected dnf5 option --downloadonly for dnf5 install [#67769](https://github.com/saltstack/salt/issues/67769)
- Upgrade relenv to 0.18.1. Which includes python 3.10.16 and openssl 3.2.4.
  Openssl 3.2.4 fixes CVE-2024-12797 and CVE-2024-13176 [#67792](https://github.com/saltstack/salt/issues/67792)
- Update jinja2 to 3.1.5, advisories GHSA-q2x7-8rv6-6q7h and GHSA-gmj6-6f8f-6699
  Update urllib3 to 1.26.18 advisories GHSA-34jh-p97f-mpxf [#67794](https://github.com/saltstack/salt/issues/67794)
- Ensure salt-cloud has salt-master dependency on Debian and Ubuntu [#67810](https://github.com/saltstack/salt/issues/67810)
- Fix traceback from _send_req_sync method on minion by raising proper timeout error. [#67891](https://github.com/saltstack/salt/issues/67891)

# Added

- Issue #33669: Fixes an issue with the ``ini_managed`` execution module
  where it would always wrap the separator with spaces. Adds a new parameter
  named ``no_spaces`` that will not warp the separator with spaces. [#33669](https://github.com/saltstack/salt/issues/33669)
- Enhance json.find_json to return json even when it contains text on the same line of the last closing parenthesis [#67023](https://github.com/saltstack/salt/issues/67023)


* Mon Jul 29 2024 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.9

# Deprecated

- Drop CentOS 7 support [#66623](https://github.com/saltstack/salt/issues/66623)
- No longer build RPM packages with CentOS Stream 9 [#66624](https://github.com/saltstack/salt/issues/66624)

# Fixed

- Made slsutil.renderer work with salt-ssh [#50196](https://github.com/saltstack/salt/issues/50196)
- Fixed defaults.merge is not available when using salt-ssh [#51605](https://github.com/saltstack/salt/issues/51605)
- Fixed config.get does not support merge option with salt-ssh [#56441](https://github.com/saltstack/salt/issues/56441)
- Update to include croniter in pkg requirements [#57649](https://github.com/saltstack/salt/issues/57649)
- Fixed state.test does not work with salt-ssh [#61100](https://github.com/saltstack/salt/issues/61100)
- Made slsutil.findup work with salt-ssh [#61143](https://github.com/saltstack/salt/issues/61143)
- Fixes multiple issues with the cmd module on Windows. Scripts are called using
  the ``-File`` parameter to the ``powershell.exe`` binary. ``CLIXML`` data in
  stderr is now removed (only applies to encoded commands). Commands can now be
  sent to ``cmd.powershell`` as a list. Makes sure JSON data returned is valid.
  Strips whitespace from the return when using ``runas``. [#61166](https://github.com/saltstack/salt/issues/61166)
- Fixed the win_lgpo_netsh salt util to handle non-English systems. This was a
  rewrite to use PowerShell instead of netsh to make the changes on the system [#61534](https://github.com/saltstack/salt/issues/61534)
- file.replace and file.search work properly with /proc files [#63102](https://github.com/saltstack/salt/issues/63102)
- Fix utf8 handling in 'pass' renderer [#64300](https://github.com/saltstack/salt/issues/64300)
- Fixed incorrect version argument will be ignored for multiple package targets warning when using pkgs argument to yumpkg module. [#64563](https://github.com/saltstack/salt/issues/64563)
- salt-cloud honors root_dir config setting for log_file location and fixes for root_dir locations on windows. [#64728](https://github.com/saltstack/salt/issues/64728)
- Fixed slsutil.update with salt-ssh during template rendering [#65067](https://github.com/saltstack/salt/issues/65067)
- Fix config.items when called on minion [#65251](https://github.com/saltstack/salt/issues/65251)
- Ensure on rpm and deb systems, that user and group for existing Salt, is maintained on upgrade [#65264](https://github.com/saltstack/salt/issues/65264)
- Fix typo in nftables module to ensure unique nft family values [#65295](https://github.com/saltstack/salt/issues/65295)
- pkg.installed state aggregate does not honors requires requisite [#65304](https://github.com/saltstack/salt/issues/65304)
- Added SSH wrapper for logmod [#65630](https://github.com/saltstack/salt/issues/65630)
- Fix for GitFS failure to unlock lock file, and resource cleanup for process SIGTERM [#65816](https://github.com/saltstack/salt/issues/65816)
- Corrected x509_v2 CRL creation `last_update` and `next_update` values when system timezone is not UTC [#65837](https://github.com/saltstack/salt/issues/65837)
- Make sure the root minion process handles SIGUSR1 and emits a traceback like it's child processes [#66095](https://github.com/saltstack/salt/issues/66095)
- Replaced pyvenv with builtin venv for virtualenv_mod [#66132](https://github.com/saltstack/salt/issues/66132)
- Made `file.managed` skip download of a remote source if the managed file already exists with the correct hash [#66342](https://github.com/saltstack/salt/issues/66342)
- Fix win_task ExecutionTimeLimit and result/error code interpretation [#66347](https://github.com/saltstack/salt/issues/66347), [#66441](https://github.com/saltstack/salt/issues/66441)
- Fixed nftables.build_rule breaks ipv6 rules by using the wrong syntax for source and destination addresses [#66382](https://github.com/saltstack/salt/issues/66382)
- Fixed x509_v2 certificate.managed crash for locally signed certificates if the signing policy defines signing_private_key [#66414](https://github.com/saltstack/salt/issues/66414)
- Fixed parallel state execution with Salt-SSH [#66514](https://github.com/saltstack/salt/issues/66514)
- Fix support for FIPS approved encryption and signing algorithms. [#66579](https://github.com/saltstack/salt/issues/66579)
- Fix relative file_roots paths [#66588](https://github.com/saltstack/salt/issues/66588)
- Fixed an issue with cmd.run with requirements when the shell is not the
  default [#66596](https://github.com/saltstack/salt/issues/66596)
- Fix RPM package provides [#66604](https://github.com/saltstack/salt/issues/66604)
- Upgrade relAenv to 0.16.1. This release fixes several package installs for salt-pip [#66632](https://github.com/saltstack/salt/issues/66632)
- Upgrade relenv to 0.17.0 (https://github.com/saltstack/relenv/blob/v0.17.0/CHANGELOG.md) [#66663](https://github.com/saltstack/salt/issues/66663)
- Upgrade dependencies due to security issues:
  - pymysql>=1.1.1
  - requests>=2.32.0
  - docker>=7.1.0 [#66666](https://github.com/saltstack/salt/issues/66666)
- Corrected missed line in branch 3006.x when backporting from PR 61620 and 65044 [#66683](https://github.com/saltstack/salt/issues/66683)
- Remove debug output from shell scripts for packaging [#66747](https://github.com/saltstack/salt/issues/66747)

# Added

- Add Ubuntu 24.04 support [#66180](https://github.com/saltstack/salt/issues/66180)
- Add Fedora 40 support, replacing Fedora 39 [#66300](https://github.com/saltstack/salt/issues/66300)
- Build RPM packages with Rocky Linux 9 (instead of CentOS Stream 9) [#66624](https://github.com/saltstack/salt/issues/66624)

# Security

- Bump to ``jinja2==3.1.4`` due to https://github.com/advisories/GHSA-h75v-3vvj-5mfj [#66488](https://github.com/saltstack/salt/issues/66488)
- CVE-2024-37088 salt-call will fail with exit code 1 if bad pillar data is
  encountered. [#66702](https://github.com/saltstack/salt/issues/66702)


* Mon Apr 29 2024 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.8

# Removed

- Removed deprecated code scheduled to be removed on 2024-01-01:

  * ``TemporaryLoggingHandler`` and ``QueueHandler`` in ``salt/_logging/handlers.py``
  * All of the ``salt/log`` package.
  * The ``salt/modules/cassandra_mod.py`` module.
  * The ``salt/returners/cassandra_return.py`` returner.
  * The ``salt/returners/django_return.py`` returner. [#66147](https://github.com/saltstack/salt/issues/66147)

# Deprecated

- Drop Fedora 37 and Fedora 38 support [#65860](https://github.com/saltstack/salt/issues/65860)
- Drop CentOS Stream 8 and 9 from CI/CD [#66104](https://github.com/saltstack/salt/issues/66104)
- Drop Photon OS 3 support [#66105](https://github.com/saltstack/salt/issues/66105)
- The ``salt.utils.psutil_compat`` module has been deprecated and will be removed in Salt 3008. Please use the ``psutil`` module directly. [#66139](https://github.com/saltstack/salt/issues/66139)

# Fixed

- ``user.add`` on Windows now allows you to add user names that contain all
  numeric characters [#53363](https://github.com/saltstack/salt/issues/53363)
- Fix an issue with the win_system module detecting established connections on
  non-Windows systems. Uses psutils instead of parsing the return of netstat [#60508](https://github.com/saltstack/salt/issues/60508)
- pkg.refresh_db on Windows now honors saltenv [#61807](https://github.com/saltstack/salt/issues/61807)
- Fixed an issue with adding new machine policies and applying those same
  policies in the same state by adding a ``refresh_cache`` option to the
  ``lgpo.set`` state. [#62734](https://github.com/saltstack/salt/issues/62734)
- file.managed correctly handles file path with '#' [#63060](https://github.com/saltstack/salt/issues/63060)
- Fix master ip detection when DNS records change [#63654](https://github.com/saltstack/salt/issues/63654)
- Fix user and group management on Windows to handle the Everyone group [#63667](https://github.com/saltstack/salt/issues/63667)
- Fixes an issue in pkg.refresh_db on Windows where new package definition
  files were not being picked up on the first run [#63848](https://github.com/saltstack/salt/issues/63848)
- Display a proper error when pki commands fail in the win_pki module [#64933](https://github.com/saltstack/salt/issues/64933)
- Prevent full system upgrade on single package install for Arch Linux [#65200](https://github.com/saltstack/salt/issues/65200)
- When using s3fs, if files are deleted from the bucket, they were not deleted in
  the master or minion local cache, which could lead to unexpected file copies or
  even state applications. This change makes the local cache consistent with the
  remote bucket by deleting files locally that are deleted from the bucket.

  **NOTE** this could lead to **breakage** on your affected systems if it was
  inadvertently depending on previously deleted files. [#65611](https://github.com/saltstack/salt/issues/65611)
- Fixed an issue with file.directory state where paths would be modified in test
  mode if backupname is used. [#66049](https://github.com/saltstack/salt/issues/66049)
- Execution modules have access to regular fileclient durring pillar rendering. [#66124](https://github.com/saltstack/salt/issues/66124)
- Fixed a issue with server channel where a minion's public key
  would be rejected if it contained a final newline character. [#66126](https://github.com/saltstack/salt/issues/66126)
- Fix content type backwards compatablity with http proxy post requests in the http utils module. [#66127](https://github.com/saltstack/salt/issues/66127)
- Fix systemctl with "try-restart" instead of "retry-restart" within the RPM spec, properly restarting upgraded services [#66143](https://github.com/saltstack/salt/issues/66143)
- Auto discovery of ssh, scp and ssh-keygen binaries. [#66205](https://github.com/saltstack/salt/issues/66205)
- Add leading slash to salt helper file paths as per dh_links requirement [#66280](https://github.com/saltstack/salt/issues/66280)
- Fixed x509.certificate_managed - ca_server did not return a certificate [#66284](https://github.com/saltstack/salt/issues/66284)
- removed log line that did nothing. [#66289](https://github.com/saltstack/salt/issues/66289)
- Chocolatey: Make sure the return dictionary from ``chocolatey.version``
  contains lowercase keys [#66290](https://github.com/saltstack/salt/issues/66290)
- fix cacheing inline pillar, by not rendering inline pillar during cache save function. [#66292](https://github.com/saltstack/salt/issues/66292)
- The file module correctly perserves file permissions on link target. [#66400](https://github.com/saltstack/salt/issues/66400)
- Upgrade relenv to 0.16.0 and python to 3.10.14 [#66402](https://github.com/saltstack/salt/issues/66402)
- backport the fix from #66164 to fix #65703. use OrderedDict to fix bad indexing. [#66705](https://github.com/saltstack/salt/issues/66705)

# Added

- Add Fedora 39 support [#65859](https://github.com/saltstack/salt/issues/65859)

# Security

- Upgrade to `cryptography==42.0.5` due to a few security issues:

  * https://github.com/advisories/GHSA-9v9h-cgj8-h64p
  * https://github.com/advisories/GHSA-3ww4-gg4f-jr7f
  * https://github.com/advisories/GHSA-6vqw-3v5j-54x4 [#66141](https://github.com/saltstack/salt/issues/66141)
- Bump to `idna==3.7` due to https://github.com/advisories/GHSA-jjg7-2v4v-x38h [#66377](https://github.com/saltstack/salt/issues/66377)
- Bump to `aiohttp==3.9.4` due to https://github.com/advisories/GHSA-7gpw-8wmc-pm8g [#66411](https://github.com/saltstack/salt/issues/66411)


* Tue Feb 20 2024 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.7

# Deprecated

- Deprecate and stop using ``salt.features`` [#65951](https://github.com/saltstack/salt/issues/65951)

# Changed

- Change module search path priority, so Salt extensions can be overridden by syncable modules and module_dirs. You can switch back to the old logic by setting features.enable_deprecated_module_search_path_priority to true, but it will be removed in Salt 3008. [#65938](https://github.com/saltstack/salt/issues/65938)

# Fixed

- Fix issue with ownership on upgrade of master and minion files
- Fix an issue with mac_shadow that was causing a command execution error when
  retrieving values that were not yet set. For example, retrieving last login
  before the user had logged in. [#34658](https://github.com/saltstack/salt/issues/34658)
- Fixed an issue when keys didn't match because of line endings [#52289](https://github.com/saltstack/salt/issues/52289)
- Corrected encoding of credentials for use with Artifactory [#63063](https://github.com/saltstack/salt/issues/63063)
- Use `send_multipart` instead of `send` when sending multipart message. [#65018](https://github.com/saltstack/salt/issues/65018)
- Fix an issue where the minion would crash on Windows if some of the grains
  failed to resolve [#65154](https://github.com/saltstack/salt/issues/65154)
- Fix issue with openscap when the error was outside the expected scope. It now
  returns failed with the error code and the error [#65193](https://github.com/saltstack/salt/issues/65193)
- Upgrade relenv to 0.15.0 to fix namespaced packages installed by salt-pip [#65433](https://github.com/saltstack/salt/issues/65433)
- Fix regression of fileclient re-use when rendering sls pillars and states [#65450](https://github.com/saltstack/salt/issues/65450)
- Fixes the s3fs backend computing the local cache's files with the wrong hash type [#65589](https://github.com/saltstack/salt/issues/65589)
- Fixed Salt-SSH pillar rendering and state rendering with nested SSH calls when called via saltutil.cmd or in an orchestration [#65670](https://github.com/saltstack/salt/issues/65670)
- Fix boto execution module loading [#65691](https://github.com/saltstack/salt/issues/65691)
- Removed PR 65185 changes since incomplete solution [#65692](https://github.com/saltstack/salt/issues/65692)
- catch only ret/ events not all returning events. [#65727](https://github.com/saltstack/salt/issues/65727)
- Fix nonsensical time in fileclient timeout error. [#65752](https://github.com/saltstack/salt/issues/65752)
- Fixes an issue when reading/modifying ini files that contain unicode characters [#65777](https://github.com/saltstack/salt/issues/65777)
- added https proxy to the list of proxies so that requests knows what to do with https based proxies [#65824](https://github.com/saltstack/salt/issues/65824)
- Ensure minion channels are closed on any master connection error. [#65932](https://github.com/saltstack/salt/issues/65932)
- Fixed issue where Salt can't find libcrypto when pip installed from a cloned repo [#65954](https://github.com/saltstack/salt/issues/65954)
- Fix RPM package systemd scriptlets to make RPM packages more universal [#65987](https://github.com/saltstack/salt/issues/65987)
- Fixed an issue where fileclient requests during Pillar rendering cause
  fileserver backends to be needlessly refreshed. [#65990](https://github.com/saltstack/salt/issues/65990)
- Fix exceptions being set on futures that are already done in ZeroMQ transport [#66006](https://github.com/saltstack/salt/issues/66006)
- Use hmac compare_digest method in hashutil module to mitigate potential timing attacks [#66041](https://github.com/saltstack/salt/issues/66041)
- Fix request channel default timeout regression. In 3006.5 it was changed from
  60 to 30 and is now set back to 60 by default. [#66061](https://github.com/saltstack/salt/issues/66061)
- Upgrade relenv to 0.15.1 to fix debugpy support. [#66094](https://github.com/saltstack/salt/issues/66094)

# Security

- Bump to ``cryptography==42.0.0`` due to https://github.com/advisories/GHSA-3ww4-gg4f-jr7f

  In the process, we were also required to update to ``pyOpenSSL==24.0.0`` [#66004](https://github.com/saltstack/salt/issues/66004)
- Bump to `cryptography==42.0.3` due to https://github.com/advisories/GHSA-3ww4-gg4f-jr7f [#66090](https://github.com/saltstack/salt/issues/66090)


* Fri Jan 26 2024 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.6

# Changed

- Salt no longer time bombs user installations on code using `salt.utils.versions.warn_until_date` [#665924](https://github.com/saltstack/salt/issues/665924)

# Fixed

- Fix un-closed transport in tornado netapi [#65759](https://github.com/saltstack/salt/issues/65759)

# Security

- CVE-2024-22231 Prevent directory traversal when creating syndic cache directory on the master
  CVE-2024-22232 Prevent directory traversal attacks in the master's serve_file method.
  These vulerablities were discovered and reported by:
  Yudi Zhao(Huawei Nebula Security Lab),Chenwei Jiang(Huawei Nebula Security Lab) [#565](https://github.com/saltstack/salt/issues/565)
- Update some requirements which had some security issues:

  * Bump to `pycryptodome==3.19.1` and `pycryptodomex==3.19.1` due to https://github.com/advisories/GHSA-j225-cvw7-qrx7
  * Bump to `gitpython==3.1.41` due to https://github.com/advisories/GHSA-2mqj-m65w-jghx
  * Bump to `jinja2==3.1.3` due to https://github.com/advisories/GHSA-h5c8-rqwp-cp95 [#65830](https://github.com/saltstack/salt/issues/65830)


* Tue Dec 12 2023 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.5

# Removed

- Tech Debt - support for pysss removed due to functionality addition in Python 3.3 [#65029](https://github.com/saltstack/salt/issues/65029)

# Fixed

- Improved error message when state arguments are accidentally passed as a string [#38098](https://github.com/saltstack/salt/issues/38098)
- Allow `pip.install` to create a log file that is passed in if the parent directory is writeable [#44722](https://github.com/saltstack/salt/issues/44722)
- Fixed merging of complex pillar overrides with salt-ssh states [#59802](https://github.com/saltstack/salt/issues/59802)
- Fixed gpg pillar rendering with salt-ssh [#60002](https://github.com/saltstack/salt/issues/60002)
- Made salt-ssh states not re-render pillars unnecessarily [#62230](https://github.com/saltstack/salt/issues/62230)
- Made Salt maintain options in Debian package repo definitions [#64130](https://github.com/saltstack/salt/issues/64130)
- Migrated all [`invoke`](https://www.pyinvoke.org/) tasks to [`python-tools-scripts`](https://github.com/s0undt3ch/python-tools-scripts).

  * `tasks/docs.py` -> `tools/precommit/docs.py`
  * `tasks/docstrings.py` -> `tools/precommit/docstrings.py`
  * `tasks/loader.py` -> `tools/precommit/loader.py`
  * `tasks/filemap.py` -> `tools/precommit/filemap.py` [#64374](https://github.com/saltstack/salt/issues/64374)
- Fix salt user login shell path in Debian packages [#64377](https://github.com/saltstack/salt/issues/64377)
- Fill out lsb_distrib_xxxx (best estimate) grains if problems with retrieving lsb_release data [#64473](https://github.com/saltstack/salt/issues/64473)
- Fixed an issue in the ``file.directory`` state where the ``children_only`` keyword
  argument was not being respected. [#64497](https://github.com/saltstack/salt/issues/64497)
- Move salt.ufw to correct location /etc/ufw/applications.d/ [#64572](https://github.com/saltstack/salt/issues/64572)
- Fixed salt-ssh stacktrace when retcode is not an integer [#64575](https://github.com/saltstack/salt/issues/64575)
- Fixed SSH shell seldomly fails to report any exit code [#64588](https://github.com/saltstack/salt/issues/64588)
- Fixed some issues in x509_v2 execution module private key functions [#64597](https://github.com/saltstack/salt/issues/64597)
- Fixed grp.getgrall() in utils/user.py causing performance issues [#64888](https://github.com/saltstack/salt/issues/64888)
- Fix user.list_groups omits remote groups via sssd, etc. [#64953](https://github.com/saltstack/salt/issues/64953)
- Ensure sync from _grains occurs before attempting pillar compilation in case custom grain used in pillar file [#65027](https://github.com/saltstack/salt/issues/65027)
- Moved gitfs locks to salt working dir to avoid lock wipes [#65086](https://github.com/saltstack/salt/issues/65086)
- Only attempt to create a keys directory when `--gen-keys` is passed to the `salt-key` CLI [#65093](https://github.com/saltstack/salt/issues/65093)
- Fix nonce verification, request server replies do not stomp on eachother. [#65114](https://github.com/saltstack/salt/issues/65114)
- speed up yumpkg list_pkgs by not requiring digest or signature verification on lookup. [#65152](https://github.com/saltstack/salt/issues/65152)
- Fix pkg.latest failing on windows for winrepo packages where the package is already up to date [#65165](https://github.com/saltstack/salt/issues/65165)
- Ensure __kwarg__ is preserved when checking for kwargs.  This change affects proxy minions when used with Deltaproxy, which had kwargs popped when targeting multiple minions id. [#65179](https://github.com/saltstack/salt/issues/65179)
- Fixes traceback when state id is an int in a reactor SLS file. [#65210](https://github.com/saltstack/salt/issues/65210)
- Install logrotate config as /etc/logrotate.d/salt-common for Debian packages
  Remove broken /etc/logrotate.d/salt directory from 3006.3 if it exists. [#65231](https://github.com/saltstack/salt/issues/65231)
- Use ``sha256`` as the default ``hash_type``. It has been the default since Salt v2016.9 [#65287](https://github.com/saltstack/salt/issues/65287)
- Preserve ownership on log rotation [#65288](https://github.com/saltstack/salt/issues/65288)
- Ensure that the correct value of jid_inclue is passed if the argument is included in the passed keyword arguments. [#65302](https://github.com/saltstack/salt/issues/65302)
- Uprade relenv to 0.14.2
   - Update openssl to address CVE-2023-5363.
   - Fix bug in openssl setup when openssl binary can't be found.
   - Add M1 mac support. [#65316](https://github.com/saltstack/salt/issues/65316)
- Fix regex for filespec adding/deleting fcontext policy in selinux [#65340](https://github.com/saltstack/salt/issues/65340)
- Ensure CLI options take priority over Saltfile options [#65358](https://github.com/saltstack/salt/issues/65358)
- Test mode for state function `saltmod.wheel` no longer set's `result` to `(None,)` [#65372](https://github.com/saltstack/salt/issues/65372)
- Client only process events which tag conforms to an event return. [#65400](https://github.com/saltstack/salt/issues/65400)
- Fixes an issue setting user or machine policy on Windows when the Group Policy
  directory is missing [#65411](https://github.com/saltstack/salt/issues/65411)
- Fix regression in file module which was not re-using a file client. [#65450](https://github.com/saltstack/salt/issues/65450)
- pip.installed state will now properly fail when a specified user does not exists [#65458](https://github.com/saltstack/salt/issues/65458)
- Publish channel connect callback method properly closes it's request channel. [#65464](https://github.com/saltstack/salt/issues/65464)
- Ensured the pillar in SSH wrapper modules is the same as the one used in template rendering when overrides are passed [#65483](https://github.com/saltstack/salt/issues/65483)
- Fix file.comment ignore_missing not working with multiline char [#65501](https://github.com/saltstack/salt/issues/65501)
- Warn when an un-closed transport client is being garbage collected. [#65554](https://github.com/saltstack/salt/issues/65554)
- Only generate the HMAC's for ``libssl.so.1.1`` and ``libcrypto.so.1.1`` if those files exist. [#65581](https://github.com/saltstack/salt/issues/65581)
- Fixed an issue where Salt Cloud would fail if it could not delete lingering
  PAexec binaries [#65584](https://github.com/saltstack/salt/issues/65584)

# Added

- Added Salt support for Debian 12 [#64223](https://github.com/saltstack/salt/issues/64223)
- Added Salt support for Amazon Linux 2023 [#64455](https://github.com/saltstack/salt/issues/64455)

# Security

- Bump to `cryptography==41.0.4` due to https://github.com/advisories/GHSA-v8gr-m533-ghj9 [#65268](https://github.com/saltstack/salt/issues/65268)
- Bump to `cryptography==41.0.7` due to https://github.com/advisories/GHSA-jfhm-5ghh-2f97 [#65643](https://github.com/saltstack/salt/issues/65643)


* Mon Oct 16 2023 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.4

# Security

- Fix CVE-2023-34049 by ensuring we do not use a predictable name for the script and correctly check returncode of scp command.
  This only impacts salt-ssh users using the pre-flight option. [#cve-2023-34049](https://github.com/saltstack/salt/issues/cve-2023-34049)
- Update to `gitpython>=3.1.35` due to https://github.com/advisories/GHSA-wfm5-v35h-vwf4 and https://github.com/advisories/GHSA-cwvm-v4w8-q58c [#65163](https://github.com/saltstack/salt/issues/65163)
- Bump to `cryptography==41.0.4` due to https://github.com/advisories/GHSA-v8gr-m533-ghj9 [#65268](https://github.com/saltstack/salt/issues/65268)
- Upgrade relenv to 0.13.12 to address CVE-2023-4807 [#65316](https://github.com/saltstack/salt/issues/65316)
- Bump to `urllib3==1.26.17` or `urllib3==2.0.6` due to https://github.com/advisories/GHSA-v845-jxx5-vc9f [#65334](https://github.com/saltstack/salt/issues/65334)
- Bump to `gitpython==3.1.37` due to https://github.com/advisories/GHSA-cwvm-v4w8-q58c [#65383](https://github.com/saltstack/salt/issues/65383)


* Wed Sep 06 2023 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.3

# Removed

- Fedora 36 support was removed because it reached EOL [#64315](https://github.com/saltstack/salt/issues/64315)
- Handle deprecation warnings:

  * Switch to `FullArgSpec` since Py 3.11 no longer has `ArgSpec`, deprecated since Py 3.0
  * Stop using the deprecated `cgi` module
  * Stop using the deprecated `pipes` module
  * Stop using the deprecated `imp` module [#64553](https://github.com/saltstack/salt/issues/64553)

# Changed

- Replace libnacl with PyNaCl [#64372](https://github.com/saltstack/salt/issues/64372)
- Don't hardcode the python version on the Salt Package tests and on the `pkg/debian/salt-cloud.postinst` file [#64553](https://github.com/saltstack/salt/issues/64553)
- Some more deprecated code fixes:

  * Stop using the deprecated `locale.getdefaultlocale()` function
  * Stop accessing deprecated attributes
  * `pathlib.Path.__enter__()` usage is deprecated and not required, a no-op [#64565](https://github.com/saltstack/salt/issues/64565)
- Bump to `pyyaml==6.0.1` due to https://github.com/yaml/pyyaml/issues/601 and address lint issues [#64657](https://github.com/saltstack/salt/issues/64657)

# Fixed

- Fix for assume role when used salt-cloud to create aws ec2. [#52501](https://github.com/saltstack/salt/issues/52501)
- fixes aptpkg module by checking for blank comps. [#58667](https://github.com/saltstack/salt/issues/58667)
- `wheel.file_roots.find` is now able to find files in subdirectories of the roots. [#59800](https://github.com/saltstack/salt/issues/59800)
- pkg.latest no longer fails when multiple versions are reported to be installed (e.g. updating the kernel) [#60931](https://github.com/saltstack/salt/issues/60931)
- Do not update the credentials dictionary in `utils/aws.py` while iterating over it, and use the correct delete functionality [#61049](https://github.com/saltstack/salt/issues/61049)
- fixed runner not having a proper exit code when runner modules throw an exception. [#61173](https://github.com/saltstack/salt/issues/61173)
- `pip.list_all_versions` now works with `index_url` and `extra_index_url` [#61610](https://github.com/saltstack/salt/issues/61610)
- speed up file.recurse by using prefix with cp.list_master_dir and remove an un-needed loop. [#61998](https://github.com/saltstack/salt/issues/61998)
- Preserve test=True condition while running sub states. [#62590](https://github.com/saltstack/salt/issues/62590)
- Job returns are only sent to originating master [#62834](https://github.com/saltstack/salt/issues/62834)
- Fixes an issue with failing subsequent state runs with the lgpo state module.
  The ``lgpo.get_polcy`` function now returns all boolean settings. [#63296](https://github.com/saltstack/salt/issues/63296)
- Fix SELinux get policy with trailing whitespace [#63336](https://github.com/saltstack/salt/issues/63336)
- Fixes an issue with boolean settings not being reported after being set. The
  ``lgpo.get_polcy`` function now returns all boolean settings. [#63473](https://github.com/saltstack/salt/issues/63473)
- Ensure body is returned when salt.utils.http returns something other than 200 with tornado backend. [#63557](https://github.com/saltstack/salt/issues/63557)
- Allow long running pillar and file client requests to finish using request_channel_timeout and request_channel_tries minion config. [#63824](https://github.com/saltstack/salt/issues/63824)
- Fix state_queue type checking to allow int values [#64122](https://github.com/saltstack/salt/issues/64122)
- Call global logger when catching pip.list exceptions in states.pip.installed
  Rename global logger `log` to `logger` inside pip_state [#64169](https://github.com/saltstack/salt/issues/64169)
- Fixes permissions created by the Debian and RPM packages for the salt user.

  The salt user created by the Debian and RPM packages to run the salt-master process, was previously given ownership of various directories in a way which compromised the benefits of running the salt-master process as a non-root user.

  This fix sets the salt user to only have write access to those files and
  directories required for the salt-master process to run. [#64193](https://github.com/saltstack/salt/issues/64193)
- Fix user.present state when groups is unset to ensure the groups are unchanged, as documented. [#64211](https://github.com/saltstack/salt/issues/64211)
- Fixes issue with MasterMinion class loading configuration from `/etc/salt/minion.d/*.conf.

  The MasterMinion class (used for running orchestraions on master and other functionality) was incorrectly loading configuration from `/etc/salt/minion.d/*.conf`, when it should only load configuration from `/etc/salt/master` and `/etc/salt/master.d/*.conf`. [#64219](https://github.com/saltstack/salt/issues/64219)
- Fixed issue in mac_user.enable_auto_login that caused the user's keychain to be reset at each boot [#64226](https://github.com/saltstack/salt/issues/64226)
- Fixed KeyError in logs when running a state that fails. [#64231](https://github.com/saltstack/salt/issues/64231)
- Fixed x509_v2 `create_private_key`/`create_crl` unknown kwargs: __pub_fun... [#64232](https://github.com/saltstack/salt/issues/64232)
- remove the hard coded python version in error. [#64237](https://github.com/saltstack/salt/issues/64237)
- `salt-pip` now properly errors out when being called from a non `onedir` environment. [#64249](https://github.com/saltstack/salt/issues/64249)
- Ensure we return an error when adding the key fails in the pkgrepo state for debian hosts. [#64253](https://github.com/saltstack/salt/issues/64253)
- Fixed file client private attribute reference on `SaltMakoTemplateLookup` [#64280](https://github.com/saltstack/salt/issues/64280)
- Fix pkgrepo.absent failures on apt-based systems when repo either a) contains a
  trailing slash, or b) there is an arch mismatch. [#64286](https://github.com/saltstack/salt/issues/64286)
- Fix detection of Salt codename by "salt_version" execution module [#64306](https://github.com/saltstack/salt/issues/64306)
- Ensure selinux values are handled lowercase [#64318](https://github.com/saltstack/salt/issues/64318)
- Remove the `clr.AddReference`, it is causing an `Illegal characters in path` exception [#64339](https://github.com/saltstack/salt/issues/64339)
- Update `pkg.group_installed` state to support repo options [#64348](https://github.com/saltstack/salt/issues/64348)
- Fix salt user login shell path in Debian packages [#64377](https://github.com/saltstack/salt/issues/64377)
- Allow for multiple user's keys presented when authenticating, for example: root, salt, etc. [#64398](https://github.com/saltstack/salt/issues/64398)
- Fixed an issue with ``lgpo_reg`` where existing entries for the same key in
  ``Registry.pol`` were being overwritten in subsequent runs if the value name in
  the subesequent run was contained in the existing value name. For example, a
  key named ``SetUpdateNotificationLevel`` would be overwritten by a subsequent
  run attempting to set ``UpdateNotificationLevel`` [#64401](https://github.com/saltstack/salt/issues/64401)
- Add search for %ProgramData%\Chocolatey\choco.exe to determine if Chocolatey is installed or not [#64427](https://github.com/saltstack/salt/issues/64427)
- Fix regression for user.present on handling groups with dupe GIDs [#64430](https://github.com/saltstack/salt/issues/64430)
- Fix inconsistent use of args in ssh_auth.managed [#64442](https://github.com/saltstack/salt/issues/64442)
- Ensure we raise an error when the name argument is invalid in pkgrepo.managed state for systems using apt. [#64451](https://github.com/saltstack/salt/issues/64451)
- Fix file.symlink will not replace/update existing symlink [#64477](https://github.com/saltstack/salt/issues/64477)
- Fixed salt-ssh state.* commands returning retcode 0 when state/pillar rendering fails [#64514](https://github.com/saltstack/salt/issues/64514)
- Fix pkg.install when using a port in the url. [#64516](https://github.com/saltstack/salt/issues/64516)
- `win_pkg` Fixes an issue runing `pkg.install` with `version=latest` where the
  new installer would not be cached if there was already an installer present
  with the same name. [#64519](https://github.com/saltstack/salt/issues/64519)
- Added a `test:full` label in the salt repository, which, when selected, will force a full test run. [#64539](https://github.com/saltstack/salt/issues/64539)
- Syndic's async_req_channel uses the asynchornous version of request channel [#64552](https://github.com/saltstack/salt/issues/64552)
- Ensure runners properly save information to job cache. [#64570](https://github.com/saltstack/salt/issues/64570)
- Added salt.ufw to salt-master install on Debian and Ubuntu [#64572](https://github.com/saltstack/salt/issues/64572)
- Added support for Chocolatey 2.0.0+ while maintaining support for older versions [#64622](https://github.com/saltstack/salt/issues/64622)
- Updated semanage fcontext to use --modify if context already exists when adding context [#64625](https://github.com/saltstack/salt/issues/64625)
- Preserve request client socket between requests. [#64627](https://github.com/saltstack/salt/issues/64627)
- Show user friendly message when pillars timeout [#64651](https://github.com/saltstack/salt/issues/64651)
- File client timeouts durring jobs show user friendly errors instead of tracbacks [#64653](https://github.com/saltstack/salt/issues/64653)
- SaltClientError does not log a traceback on minions, we expect these to happen so a user friendly log is shown. [#64729](https://github.com/saltstack/salt/issues/64729)
- Look in location salt is running from, this accounts for running from an unpacked onedir file that has not been installed. [#64877](https://github.com/saltstack/salt/issues/64877)
- Preserve credentials on spawning platforms, minions no longer re-authenticate
  with every job when using `multiprocessing=True`. [#64914](https://github.com/saltstack/salt/issues/64914)
- Fixed uninstaller to not remove the `salt` directory by default. This allows
  the `extras-3.##` folder to persist so salt-pip dependencies are not wiped out
  during an upgrade. [#64957](https://github.com/saltstack/salt/issues/64957)
- fix msteams by adding the missing header that Microsoft is now enforcing. [#64973](https://github.com/saltstack/salt/issues/64973)
- Fix __env__ and improve cache cleaning see more info at pull #65017. [#65002](https://github.com/saltstack/salt/issues/65002)
- Better error message on inconsistent decoded payload [#65020](https://github.com/saltstack/salt/issues/65020)
- Handle permissions access error when calling `lsb_release` with the salt user [#65024](https://github.com/saltstack/salt/issues/65024)
- Allow schedule state module to update schedule when the minion is offline. [#65033](https://github.com/saltstack/salt/issues/65033)
- Fixed creation of wildcard DNS in SAN in `x509_v2` [#65072](https://github.com/saltstack/salt/issues/65072)
- The macOS installer no longer removes the extras directory [#65073](https://github.com/saltstack/salt/issues/65073)

# Added

- Added a script to automate setting up a 2nd minion in a user context on Windows [#64439](https://github.com/saltstack/salt/issues/64439)
- Several fixes to the CI workflow:

  * Don't override the `on` Jinja block on the `ci.yaml` template. This enables reacting to labels getting added/removed
    to/from pull requests.
  * Switch to using `tools` and re-use the event payload available instead of querying the GH API again to get the pull
    request labels
  * Concentrate test selection by labels to a single place
  * Enable code coverage on pull-requests by setting the `test:coverage` label [#64547](https://github.com/saltstack/salt/issues/64547)

# Security

- Upgrade to `cryptography==41.0.3`(and therefor `pyopenssl==23.2.0` due to https://github.com/advisories/GHSA-jm77-qphf-c4w8)

  This only really impacts pip installs of Salt and the windows onedir since the linux and macos onedir build every package dependency from source, not from pre-existing wheels.

  Also resolves the following cryptography advisories:

  Due to:
    * https://github.com/advisories/GHSA-5cpq-8wj7-hf2v
    * https://github.com/advisories/GHSA-x4qr-2fvf-3mr5
    * https://github.com/advisories/GHSA-w7pp-m8wf-vj6r [#64595](https://github.com/saltstack/salt/issues/64595)
- Bump to `aiohttp==3.8.5` due to https://github.com/advisories/GHSA-45c4-8wx5-qw6w [#64687](https://github.com/saltstack/salt/issues/64687)
- Bump to `certifi==2023.07.22` due to https://github.com/advisories/GHSA-xqr8-7jwr-rhp7 [#64718](https://github.com/saltstack/salt/issues/64718)
- Upgrade `relenv` to `0.13.2` and Python to `3.10.12`

  Addresses multiple CVEs in Python's dependencies: https://docs.python.org/release/3.10.12/whatsnew/changelog.html#python-3-10-12 [#64719](https://github.com/saltstack/salt/issues/64719)
- Update to `gitpython>=3.1.32` due to https://github.com/advisories/GHSA-pr76-5cm5-w9cj [#64988](https://github.com/saltstack/salt/issues/64988)


* Wed Aug 09 2023 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.2

# Fixed

- In scenarios where PythonNet fails to load, Salt will now fall back to WMI for
  gathering grains information [#64897](https://github.com/saltstack/salt/issues/64897)

# Security

- fix CVE-2023-20897 by catching exception instead of letting exception disrupt connection [#cve-2023-20897](https://github.com/saltstack/salt/issues/cve-2023-20897)
- Fixed gitfs cachedir_basename to avoid hash collisions. Added MP Lock to gitfs. These changes should stop race conditions. [#cve-2023-20898](https://github.com/saltstack/salt/issues/cve-2023-20898)
- Upgrade to `requests==2.31.0`

  Due to:
    * https://github.com/advisories/GHSA-j8r2-6x86-q33q [#64336](https://github.com/saltstack/salt/issues/64336)
- Upgrade to `cryptography==41.0.3`(and therefor `pyopenssl==23.2.0` due to https://github.com/advisories/GHSA-jm77-qphf-c4w8)

  This only really impacts pip installs of Salt and the windows onedir since the linux and macos onedir build every package dependency from source, not from pre-existing wheels.

  Also resolves the following cryptography advisories:

  Due to:
    * https://github.com/advisories/GHSA-5cpq-8wj7-hf2v
    * https://github.com/advisories/GHSA-x4qr-2fvf-3mr5
    * https://github.com/advisories/GHSA-w7pp-m8wf-vj6r

  There is no security upgrade available for Py3.5 [#64595](https://github.com/saltstack/salt/issues/64595)
- Bump to `certifi==2023.07.22` due to https://github.com/advisories/GHSA-xqr8-7jwr-rhp7 [#64718](https://github.com/saltstack/salt/issues/64718)
- Upgrade `relenv` to `0.13.2` and Python to `3.10.12`

  Addresses multiple CVEs in Python's dependencies: https://docs.python.org/release/3.10.12/whatsnew/changelog.html#python-3-10-12 [#64719](https://github.com/saltstack/salt/issues/64719)


* Fri May 05 2023 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.1

# Fixed

- Check that the return data from the cloud create function is a dictionary before attempting to pull values out. [#61236](https://github.com/saltstack/salt/issues/61236)
- Ensure NamedLoaderContext's have their value() used if passing to other modules [#62477](https://github.com/saltstack/salt/issues/62477)
- add documentation note about reactor state ids. [#63589](https://github.com/saltstack/salt/issues/63589)
- Added support for ``test=True`` to the ``file.cached`` state module [#63785](https://github.com/saltstack/salt/issues/63785)
- Updated `source_hash` documentation and added a log warning when `source_hash` is used with a source other than `http`, `https` and `ftp`. [#63810](https://github.com/saltstack/salt/issues/63810)
- Fixed clear pillar cache on every highstate and added clean_pillar_cache=False to saltutil functions. [#64081](https://github.com/saltstack/salt/issues/64081)
- Fix dmsetup device names with hyphen being picked up. [#64082](https://github.com/saltstack/salt/issues/64082)
- Update all the scheduler functions to include a fire_event argument which will determine whether to fire the completion event onto the event bus.
  This event is only used when these functions are called via the schedule execution modules.
  Update all the calls to the schedule related functions in the deltaproxy proxy minion to include fire_event=False, as the event bus is not available when these functions are called. [#64102](https://github.com/saltstack/salt/issues/64102), [#64103](https://github.com/saltstack/salt/issues/64103)
- Default to a 0 timeout if none is given for the terraform roster to avoid `-o ConnectTimeout=None` when using `salt-ssh` [#64109](https://github.com/saltstack/salt/issues/64109)
- Disable class level caching of the file client on `SaltCacheLoader` and properly use context managers to take care of initialization and termination of the file client. [#64111](https://github.com/saltstack/salt/issues/64111)
- Fixed several file client uses which were not properly terminating it by switching to using it as a context manager
  whenever possible or making sure `.destroy()` was called when using a context manager was not possible. [#64113](https://github.com/saltstack/salt/issues/64113)
- Fix running setup.py when passing in --salt-config-dir and --salt-cache-dir arguments. [#64114](https://github.com/saltstack/salt/issues/64114)
- Moved /etc/salt/proxy and /lib/systemd/system/salt-proxy@.service to the salt-minion DEB package [#64117](https://github.com/saltstack/salt/issues/64117)
- Stop passing `**kwargs` and be explicit about the keyword arguments to pass, namely, to `cp.cache_file` call in `salt.states.pkg` [#64118](https://github.com/saltstack/salt/issues/64118)
- lgpo_reg.set_value now returns ``True`` on success instead of ``None`` [#64126](https://github.com/saltstack/salt/issues/64126)
- Make salt user's home /opt/saltstack/salt [#64141](https://github.com/saltstack/salt/issues/64141)
- Fix cmd.run doesn't output changes in test mode [#64150](https://github.com/saltstack/salt/issues/64150)
- Move salt user and group creation to common package [#64158](https://github.com/saltstack/salt/issues/64158)
- Fixed issue in salt-cloud so that multiple masters specified in the cloud
  are written to the minion config properly [#64170](https://github.com/saltstack/salt/issues/64170)
- Make sure the `salt-ssh` CLI calls it's `fsclient.destroy()` method when done. [#64184](https://github.com/saltstack/salt/issues/64184)
- Stop using the deprecated `salt.transport.client` imports. [#64186](https://github.com/saltstack/salt/issues/64186)
- Add a `.pth` to the Salt onedir env to ensure packages in extras are importable. Bump relenv to 0.12.3. [#64192](https://github.com/saltstack/salt/issues/64192)
- Fix ``lgpo_reg`` state to work with User policy [#64200](https://github.com/saltstack/salt/issues/64200)
- Cloud deployment directories are owned by salt user and group [#64204](https://github.com/saltstack/salt/issues/64204)
- ``lgpo_reg`` state now enforces and reports changes to the registry [#64222](https://github.com/saltstack/salt/issues/64222)


* Tue Apr 18 2023 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.0

# Removed

- Remove and deprecate the __orchestration__ key from salt.runner and salt.wheel return data. To get it back, set features.enable_deprecated_orchestration_flag master configuration option to True. The flag will be completely removed in Salt 3008 Argon. [#59917](https://github.com/saltstack/salt/issues/59917)
- Removed distutils and replaced with setuptools, given distutils is deprecated and removed in Python 3.12 [#60476](https://github.com/saltstack/salt/issues/60476)
- Removed ``runtests`` targets from ``noxfile.py`` [#62239](https://github.com/saltstack/salt/issues/62239)
- Removed the PyObjC dependency.

  This addresses problems with building a one dir build for macOS.
  It became problematic because depending on the macOS version, it pulls different dependencies, and we would either have to build a macos onedir for each macOS supported release, or ship a crippled onedir(because it would be tied to the macOS version where the onedir was built).
  Since it's currently not being used, it's removed. [#62432](https://github.com/saltstack/salt/issues/62432)
- Removed `SixRedirectImporter` from Salt. Salt hasn't shipped `six` since Salt 3004. [#63874](https://github.com/saltstack/salt/issues/63874)

# Deprecated

- renamed `keep_jobs`, specifying job cache TTL in hours, to `keep_jobs_seconds`, specifying TTL in seconds.
  `keep_jobs` will be removed in the Argon release [#55295](https://github.com/saltstack/salt/issues/55295)
- Removing all references to napalm-base which is no longer supported. [#61542](https://github.com/saltstack/salt/issues/61542)
- The 'ip_bracket' function has been moved from salt/utils/zeromq.py in salt/utils/network.py [#62009](https://github.com/saltstack/salt/issues/62009)
- The `expand_repo_def` function in `salt.modules.aptpkg` is now deprecated. It's only used in `salt.states.pkgrepo` and it has no use of being exposed to the CLI. [#62485](https://github.com/saltstack/salt/issues/62485)
- Deprecated defunct Django returner [#62644](https://github.com/saltstack/salt/issues/62644)
- Deprecate core ESXi and associated states and modules, vcenter and vsphere support in favor of Salt VMware Extensions [#62754](https://github.com/saltstack/salt/issues/62754)
- Removing manufacture grain which has been deprecated. [#62914](https://github.com/saltstack/salt/issues/62914)
- Removing deprecated utils/boto3_elasticsearch.py [#62915](https://github.com/saltstack/salt/issues/62915)
- Removing support for the now deprecated _ext_nodes from salt/master.py. [#62917](https://github.com/saltstack/salt/issues/62917)
- Deprecating the Salt Slack engine in favor of the Salt Slack Bolt Engine. [#63095](https://github.com/saltstack/salt/issues/63095)
- `salt.utils.version.StrictVersion` is now deprecated and it's use should be replaced with `salt.utils.version.Version`. [#63383](https://github.com/saltstack/salt/issues/63383)

# Changed

- More intelligent diffing in changes of file.serialize state. [#48609](https://github.com/saltstack/salt/issues/48609)
- Move deprecation of the neutron module to Argon. Please migrate to the neutronng module instead. [#49430](https://github.com/saltstack/salt/issues/49430)
- ``umask`` is now a global state argument, instead of only applying to ``cmd``
  states. [#57803](https://github.com/saltstack/salt/issues/57803)
- Update pillar.obfuscate to accept kwargs in addition to args.  This is useful when passing in keyword arguments like saltenv that are then passed along to pillar.items. [#58971](https://github.com/saltstack/salt/issues/58971)
- Improve support for listing macOS brew casks [#59439](https://github.com/saltstack/salt/issues/59439)
- Add missing MariaDB Grants to mysql module.
  MariaDB has added some grants in 10.4.x and 10.5.x that are not present here, which results in an error when creating.
  Also improved exception handling in `grant_add` which did not log the original error message and replaced it with a generic error. [#61409](https://github.com/saltstack/salt/issues/61409)
- Use VENV_PIP_TARGET environment variable as a default target for pip if present. [#62089](https://github.com/saltstack/salt/issues/62089)
- Disabled FQDNs grains on macOS by default [#62168](https://github.com/saltstack/salt/issues/62168)
- Replaced pyroute2.IPDB with pyroute2.NDB, as the former is deprecated [#62218](https://github.com/saltstack/salt/issues/62218)
- Enhance capture of error messages for Zypper calls in zypperpkg module. [#62346](https://github.com/saltstack/salt/issues/62346)
- Removed GPG_1_3_1 check [#62895](https://github.com/saltstack/salt/issues/62895)
- Requisite state chunks now all consistently contain `__id__`, `__sls__` and `name`. [#63012](https://github.com/saltstack/salt/issues/63012)
- netapi_enable_clients option to allow enabling/disabling of clients in salt-api.
  By default all clients will now be disabled. Users of salt-api will need
  to update their master config to enable the clients that they use. Not adding
  the netapi_enable_clients option with required clients to the master config will
  disable salt-api. [#63050](https://github.com/saltstack/salt/issues/63050)
- Stop relying on `salt/_version.py` to write Salt's version. Instead use `salt/_version.txt` which only contains the version string. [#63383](https://github.com/saltstack/salt/issues/63383)
- Set enable_fqdns_grains to be False by default. [#63595](https://github.com/saltstack/salt/issues/63595)
- Changelog snippet files must now have a `.md` file extension to be more explicit on what type of rendering is done when they are included in the main `CHANGELOG.md` file. [#63710](https://github.com/saltstack/salt/issues/63710)
- Upgraded to `relenv==0.9.0` [#63883](https://github.com/saltstack/salt/issues/63883)

# Fixed

- Add kwargs to handle extra parameters for http.query [#36138](https://github.com/saltstack/salt/issues/36138)
- Fix mounted bind mounts getting active mount options added [#39292](https://github.com/saltstack/salt/issues/39292)
- Fix `sysctl.present` converts spaces to tabs. [#40054](https://github.com/saltstack/salt/issues/40054)
- Fixes state pkg.purged to purge removed packages on Debian family systems [#42306](https://github.com/saltstack/salt/issues/42306)
- Fix fun_args missing from syndic returns [#45823](https://github.com/saltstack/salt/issues/45823)
- Fix mount.mounted with 'mount: False' reports unmounted file system as unchanged when running with test=True [#47201](https://github.com/saltstack/salt/issues/47201)
- Issue #49310: Allow users to touch a file with Unix date of birth [#49310](https://github.com/saltstack/salt/issues/49310)
- Do not raise an exception in pkg.info_installed on nonzero return code [#51620](https://github.com/saltstack/salt/issues/51620)
- Passes the value of the force parameter from file.copy to its call to file.remove so that files with the read-only attribute are handled. [#51739](https://github.com/saltstack/salt/issues/51739)
- Fixed x509.certificate_managed creates new certificate every run in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#52167](https://github.com/saltstack/salt/issues/52167)
- Don't check for cached pillar errors on state.apply [#52354](https://github.com/saltstack/salt/issues/52354), [#57180](https://github.com/saltstack/salt/issues/57180), [#59339](https://github.com/saltstack/salt/issues/59339)
- Swapping out args and kwargs for arg and kwarg respectively in the Slack engine when the command passed is a runner. [#52400](https://github.com/saltstack/salt/issues/52400)
- Ensure when we're adding chunks to the rules when running aggregation with the iptables state module we use a copy of the chunk otherwise we end up with a recursive mess. [#53353](https://github.com/saltstack/salt/issues/53353)
- When user_create or user_remove fail, return False instead of returning the error. [#53377](https://github.com/saltstack/salt/issues/53377)
- Include sync_roster when sync_all is called. [#53914](https://github.com/saltstack/salt/issues/53914)
- Avoid warning noise in lograte.get [#53988](https://github.com/saltstack/salt/issues/53988)
- Fixed listing revoked keys with gpg.list_keys [#54347](https://github.com/saltstack/salt/issues/54347)
- Fix mount.mounted does not handle blanks properly [#54508](https://github.com/saltstack/salt/issues/54508)
- Fixed grain num_cpus get wrong CPUs count in case of inconsistent CPU numbering. [#54682](https://github.com/saltstack/salt/issues/54682)
- Fix spelling error for python_shell argument in dpkg_lower module [#54907](https://github.com/saltstack/salt/issues/54907)
- Cleaned up bytes response data before sending to non-bytes compatible returners (postgres, mysql) [#55226](https://github.com/saltstack/salt/issues/55226)
- Fixed malformed state return when testing file.managed with unavailable source file [#55269](https://github.com/saltstack/salt/issues/55269)
- Included stdout in error message for Zypper calls in zypperpkg module. [#56016](https://github.com/saltstack/salt/issues/56016)
- Fixed pillar.filter_by with salt-ssh [#56093](https://github.com/saltstack/salt/issues/56093)
- Fix boto_route53 issue with (multiple) VPCs. [#57139](https://github.com/saltstack/salt/issues/57139)
- Remove log from mine runner which was not used. [#57463](https://github.com/saltstack/salt/issues/57463)
- Fixed x509.read_certificate error when reading a Microsoft CA issued certificate in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#57535](https://github.com/saltstack/salt/issues/57535)
- Updating Slack engine to use slack_bolt library. [#57842](https://github.com/saltstack/salt/issues/57842)
- Fixed warning about replace=True with x509.certificate_managed in the new cryptography x509 module. [#58165](https://github.com/saltstack/salt/issues/58165)
- Fix salt.modules.pip:is_installed doesn't handle locally installed packages [#58202](https://github.com/saltstack/salt/issues/58202)
- Add missing MariaDB Grants to mysql module. MariaDB has added some grants in 10.4.x and 10.5.x that are not present here, which results in an error when creating. [#58297](https://github.com/saltstack/salt/issues/58297)
- linux_shadow: Fix cases where malformed shadow entries cause `user.present`
  states to fail. [#58423](https://github.com/saltstack/salt/issues/58423)
- Fixed salt.utils.compat.cmp to work with dictionaries [#58729](https://github.com/saltstack/salt/issues/58729)
- Fixed formatting for terse output mode [#58953](https://github.com/saltstack/salt/issues/58953)
- Fixed RecursiveDictDiffer with added nested dicts [#59017](https://github.com/saltstack/salt/issues/59017)
- Fixed x509.certificate_managed has DoS effect on master in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#59169](https://github.com/saltstack/salt/issues/59169)
- Fixed saltnado websockets disconnecting immediately [#59183](https://github.com/saltstack/salt/issues/59183)
- Fixed x509.certificate_managed rolls certificates every now and then in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#59315](https://github.com/saltstack/salt/issues/59315)
- Fix postgres_privileges.present not idempotent for functions [#59585](https://github.com/saltstack/salt/issues/59585)
- Fixed influxdb_continuous_query.present state to provide the client args to the underlying module on create. [#59766](https://github.com/saltstack/salt/issues/59766)
- Warn when using insecure (http:// based) key_urls for apt-based systems in pkgrepo.managed, and add a kwarg that determines the validity of such a url. [#59786](https://github.com/saltstack/salt/issues/59786)
- add load balancing policy default option and ensure the module can be executed with arguments from CLI [#59909](https://github.com/saltstack/salt/issues/59909)
- Fix salt-ssh when using imports with extra-filerefs. [#60003](https://github.com/saltstack/salt/issues/60003)
- Fixed cache directory corruption startup error [#60170](https://github.com/saltstack/salt/issues/60170)
- Update docs remove dry_run in docstring of file.blockreplace state. [#60227](https://github.com/saltstack/salt/issues/60227)
- Adds Parrot to OS_Family_Map in grains. [#60249](https://github.com/saltstack/salt/issues/60249)
- Fixed stdout and stderr being empty sometimes when use_vt=True for the cmd.run[*] functions [#60365](https://github.com/saltstack/salt/issues/60365)
- Use return code in iptables --check to verify rule exists. [#60467](https://github.com/saltstack/salt/issues/60467)
- Fix regression pip.installed does not pass env_vars when calling pip.list [#60557](https://github.com/saltstack/salt/issues/60557)
- Fix xfs module when additional output included in mkfs.xfs command. [#60853](https://github.com/saltstack/salt/issues/60853)
- Fixed parsing new format of terraform states in roster.terraform [#60915](https://github.com/saltstack/salt/issues/60915)
- Fixed recognizing installed ARMv7 rpm packages in compatible architectures. [#60994](https://github.com/saltstack/salt/issues/60994)
- Fixing changes dict in pkg state to be consistent when installing and test=True. [#60995](https://github.com/saltstack/salt/issues/60995)
- Fix cron.present duplicating entries when changing timespec to special. [#60997](https://github.com/saltstack/salt/issues/60997)
- Made salt-ssh respect --wipe again [#61083](https://github.com/saltstack/salt/issues/61083)
- state.orchestrate_single only passes a pillar if it is set to the state
  function. This allows it to be used with state functions that don't accept a
  pillar keyword argument. [#61092](https://github.com/saltstack/salt/issues/61092)
- Fix ipset state when the comment kwarg is set. [#61122](https://github.com/saltstack/salt/issues/61122)
- Fix issue with archive.unzip where the password was not being encoded for the extract function [#61422](https://github.com/saltstack/salt/issues/61422)
- Some Linux distributions (like AlmaLinux, Astra Linux, Debian, Mendel, Linux
  Mint, Pop!_OS, Rocky Linux) report different `oscodename`, `osfullname`,
  `osfinger` grains if lsb-release is installed or not. They have been changed to
  only derive these OS grains from `/etc/os-release`. [#61618](https://github.com/saltstack/salt/issues/61618)
- Pop!_OS uses the full version (YY.MM) in the osfinger grain now, not just the year. This allows differentiating for example between 20.04 and 20.10. [#61619](https://github.com/saltstack/salt/issues/61619)
- Fix ssh config roster to correctly parse the ssh config files that contain spaces. [#61650](https://github.com/saltstack/salt/issues/61650)
- Fix SoftLayer configuration not raising an exception when a domain is missing [#61727](https://github.com/saltstack/salt/issues/61727)
- Allow the minion to start or salt-call to run even if the user doesn't have permissions to read the root_dir value from the registry [#61789](https://github.com/saltstack/salt/issues/61789)
- Need to move the creation of the proxy object for the ProxyMinion further down in the initialization for sub proxies to ensure that all modules, especially any custom proxy modules, are available before attempting to run the init function. [#61805](https://github.com/saltstack/salt/issues/61805)
- Fixed malformed state return when merge-serializing to an improperly formatted file [#61814](https://github.com/saltstack/salt/issues/61814)
- Made cmdmod._run[_all]_quiet work during minion startup on MacOS with runas specified (which fixed mac_service) [#61816](https://github.com/saltstack/salt/issues/61816)
- When deleting the vault cache, also delete from the session cache [#61821](https://github.com/saltstack/salt/issues/61821)
- Ignore errors on reading license info with dpkg_lowpkg to prevent tracebacks on getting package information. [#61827](https://github.com/saltstack/salt/issues/61827)
- win_lgpo: Display conflicting policy names when more than one policy is found [#61859](https://github.com/saltstack/salt/issues/61859)
- win_lgpo: Fixed intermittent KeyError when getting policy setting using lgpo.get_policy [#61860](https://github.com/saltstack/salt/issues/61860)
- Fixed listing minions on OpenBSD [#61966](https://github.com/saltstack/salt/issues/61966)
- Make Salt to return an error on "pkg" modules and states when targeting duplicated package names [#62019](https://github.com/saltstack/salt/issues/62019)
- Fix return of REST-returned permissions when auth_list is set [#62022](https://github.com/saltstack/salt/issues/62022)
- Normalize package names once on using pkg.installed/removed with yum to make it possible to install packages with the name containing a part similar to a name of architecture. [#62029](https://github.com/saltstack/salt/issues/62029)
- Fix inconsitency regarding name and pkgs parameters between zypperpkg.upgrade() and yumpkg.upgrade() [#62030](https://github.com/saltstack/salt/issues/62030)
- Fix attr=all handling in pkg.list_pkgs() (yum/zypper). [#62032](https://github.com/saltstack/salt/issues/62032)
- Fixed the humanname being ignored in pkgrepo.managed on openSUSE Leap [#62053](https://github.com/saltstack/salt/issues/62053)
- Fixed issue with some LGPO policies having whitespace at the beginning or end of the element alias [#62058](https://github.com/saltstack/salt/issues/62058)
- Fix ordering of args to libcloud_storage.download_object module [#62074](https://github.com/saltstack/salt/issues/62074)
- Ignore extend declarations in sls files that are excluded. [#62082](https://github.com/saltstack/salt/issues/62082)
- Remove leftover usage of impacket [#62101](https://github.com/saltstack/salt/issues/62101)
- Pass executable path from _get_path_exec() is used when calling the program.
  The $HOME env is no longer modified globally.
  Only trailing newlines are stripped from the fetched secret.
  Pass process arguments are handled in a secure way. [#62120](https://github.com/saltstack/salt/issues/62120)
- Ignore some command return codes in openbsdrcctl_service to prevent spurious errors [#62131](https://github.com/saltstack/salt/issues/62131)
- Fixed extra period in filename output in tls module. Instead of "server.crt." it will now be "server.crt". [#62139](https://github.com/saltstack/salt/issues/62139)
- Make sure lingering PAexec-*.exe files in the Windows directory are cleaned up [#62152](https://github.com/saltstack/salt/issues/62152)
- Restored Salt's DeprecationWarnings [#62185](https://github.com/saltstack/salt/issues/62185)
- Fixed issue with forward slashes on Windows with file.recurse and clean=True [#62197](https://github.com/saltstack/salt/issues/62197)
- Recognize OSMC as Debian-based [#62198](https://github.com/saltstack/salt/issues/62198)
- Fixed Zypper module failing on RPM lock file being temporarily unavailable. [#62204](https://github.com/saltstack/salt/issues/62204)
- Improved error handling and diagnostics in the proxmox salt-cloud driver [#62211](https://github.com/saltstack/salt/issues/62211)
- Added EndeavourOS to the Arch os_family. [#62220](https://github.com/saltstack/salt/issues/62220)
- Fix salt-ssh not detecting `platform-python` as a valid interpreter on EL8 [#62235](https://github.com/saltstack/salt/issues/62235)
- Fix pkg.version_cmp on openEuler and a few other os flavors. [#62248](https://github.com/saltstack/salt/issues/62248)
- Fix localhost detection in glusterfs.peers [#62273](https://github.com/saltstack/salt/issues/62273)
- Fix Salt Package Manager (SPM) exception when calling spm create_repo . [#62281](https://github.com/saltstack/salt/issues/62281)
- Fix matcher slowness due to loader invocation [#62283](https://github.com/saltstack/salt/issues/62283)
- Fixes the Puppet module for non-aio Puppet packages for example running the Puppet module on FreeBSD. [#62323](https://github.com/saltstack/salt/issues/62323)
- Issue 62334: Displays a debug log message instead of an error log message when the publisher fails to connect [#62334](https://github.com/saltstack/salt/issues/62334)
- Fix pyobjects renderer access to opts and sls [#62336](https://github.com/saltstack/salt/issues/62336)
- Fix use of random shuffle and sample functions as Jinja filters [#62372](https://github.com/saltstack/salt/issues/62372)
- Fix groups with duplicate GIDs are not returned by get_group_list [#62377](https://github.com/saltstack/salt/issues/62377)
- Fix the "zpool.present" state when enabling zpool features that are already active. [#62390](https://github.com/saltstack/salt/issues/62390)
- Fix ability to execute remote file client methods in saltcheck [#62398](https://github.com/saltstack/salt/issues/62398)
- Update all platforms to use pycparser 2.21 or greater for Py 3.9 or higher, fixes fips fault with openssl v3.x [#62400](https://github.com/saltstack/salt/issues/62400)
- Due to changes in the Netmiko library for the exception paths, need to check the version of Netmiko python library and then import the exceptions from different locations depending on the result. [#62405](https://github.com/saltstack/salt/issues/62405)
- When using preq on a state, then prereq state will first be run with test=True to determine if there are changes.  When there are changes, the state with the prereq option will be run prior to the prereq state.  If this state fails then the prereq state will not run and the state output uses the test=True run.  However, the proposed changes are included for the prereq state are included from the test=True run.  We should pull those out as there weren't actually changes since the prereq state did not run. [#62408](https://github.com/saltstack/salt/issues/62408)
- Added directory mode for file.copy with makedirs [#62426](https://github.com/saltstack/salt/issues/62426)
- Provide better error handling in the various napalm proxy minion functions when the device is not accessible. [#62435](https://github.com/saltstack/salt/issues/62435)
- When handling aggregation, change the order to ensure that the requisites are aggregated first and then the state functions are aggregated.  Caching whether aggregate functions are available for particular states so we don't need to attempt to load them everytime. [#62439](https://github.com/saltstack/salt/issues/62439)
- The patch allows to boostrap kubernetes clusters in the version above 1.13 via salt module [#62451](https://github.com/saltstack/salt/issues/62451)
- sysctl.persist now updates the in-memory value on FreeBSD even if the on-disk value was already correct. [#62461](https://github.com/saltstack/salt/issues/62461)
- Fixed parsing CDROM apt sources [#62474](https://github.com/saltstack/salt/issues/62474)
- Update sanitizing masking for Salt SSH to include additional password like strings. [#62483](https://github.com/saltstack/salt/issues/62483)
- Fix user/group checking on file state functions in the test mode. [#62499](https://github.com/saltstack/salt/issues/62499)
- Fix user.present to allow removing groups using optional_groups parameter and enforcing idempotent group membership. [#62502](https://github.com/saltstack/salt/issues/62502)
- Fix possible tracebacks if there is a package with '------' or '======' in the description is installed on the Debian based minion. [#62519](https://github.com/saltstack/salt/issues/62519)
- Fixed the omitted "pool" parameter when cloning a VM with the proxmox salt-cloud driver [#62521](https://github.com/saltstack/salt/issues/62521)
- Fix rendering of pyobjects states in saltcheck [#62523](https://github.com/saltstack/salt/issues/62523)
- Fixes pillar where a corrupted CacheDisk file forces the pillar to be rebuilt [#62527](https://github.com/saltstack/salt/issues/62527)
- Use str() method instead of repo_line for when python3-apt is installed or not in aptpkg.py. [#62546](https://github.com/saltstack/salt/issues/62546)
- Remove the connection_timeout from netmiko_connection_args before netmiko_connection_args is added to __context__["netmiko_device"]["args"] which is passed along to the Netmiko library. [#62547](https://github.com/saltstack/salt/issues/62547)
- Fix order specific mount.mounted options for persist [#62556](https://github.com/saltstack/salt/issues/62556)
- Fixed salt-cloud cloning a proxmox VM with a specified new vmid. [#62558](https://github.com/saltstack/salt/issues/62558)
- Fix runas with cmd module when using the onedir bundled packages [#62565](https://github.com/saltstack/salt/issues/62565)
- Update setproctitle version for all platforms [#62576](https://github.com/saltstack/salt/issues/62576)
- Fixed missing parameters when cloning a VM with the proxmox salt-cloud driver [#62580](https://github.com/saltstack/salt/issues/62580)
- Handle PermissionError when importing crypt when FIPS is enabled. [#62587](https://github.com/saltstack/salt/issues/62587)
- Correctly reraise exceptions in states.http [#62595](https://github.com/saltstack/salt/issues/62595)
- Fixed syndic eauth. Now jobs will be published when a valid eauth user is targeting allowed minions/functions. [#62618](https://github.com/saltstack/salt/issues/62618)
- updated rest_cherry/app to properly detect arg sent as a string as curl will do when only one arg is supplied. [#62624](https://github.com/saltstack/salt/issues/62624)
- Prevent possible tracebacks in core grains module by ignoring non utf8 characters in /proc/1/environ, /proc/1/cmdline, /proc/cmdline [#62633](https://github.com/saltstack/salt/issues/62633)
- Fixed vault ext pillar return data for KV v2 [#62651](https://github.com/saltstack/salt/issues/62651)
- Fix saltcheck _get_top_states doesn't pass saltenv to state.show_top [#62654](https://github.com/saltstack/salt/issues/62654)
- Fix groupadd.* functions hard code relative command name [#62657](https://github.com/saltstack/salt/issues/62657)
- Fixed pdbedit.create trying to use a bytes-like hash as string. [#62670](https://github.com/saltstack/salt/issues/62670)
- Fix depenency on legacy boto module in boto3 modules [#62672](https://github.com/saltstack/salt/issues/62672)
- Modified "_get_flags" function so that it returns regex flags instead of integers [#62676](https://github.com/saltstack/salt/issues/62676)
- Change startup ReqServer log messages from error to info level. [#62728](https://github.com/saltstack/salt/issues/62728)
- Fix kmod.* functions hard code relative command name [#62772](https://github.com/saltstack/salt/issues/62772)
- Remove mako as a dependency in Windows and macOS. [#62785](https://github.com/saltstack/salt/issues/62785)
- Fix mac_brew_pkg to work with null taps [#62793](https://github.com/saltstack/salt/issues/62793)
- Fixing a bug when listing the running schedule if "schedule.enable" and/or "schedule.disable" has been run, where the "enabled" items is being treated as a schedule item. [#62795](https://github.com/saltstack/salt/issues/62795)
- Prevent annoying RuntimeWarning message about line buffering (buffering=1) not being supported in binary mode [#62817](https://github.com/saltstack/salt/issues/62817)
- Include UID and GID checks in modules.file.check_perms as well as comparing
  ownership by username and group name. [#62818](https://github.com/saltstack/salt/issues/62818)
- Fix presence events on TCP transport by removing a client's presence when minion disconnects from publish channel correctly [#62826](https://github.com/saltstack/salt/issues/62826)
- Remove Azure deprecation messages from functions that always run w/ salt-cloud [#62845](https://github.com/saltstack/salt/issues/62845)
- Use select instead of iterating over entrypoints as a dictionary for importlib_metadata>=5.0.0 [#62854](https://github.com/saltstack/salt/issues/62854)
- Fixed master job scheduler using when [#62858](https://github.com/saltstack/salt/issues/62858)
- LGPO: Added support for missing domain controller policies: VulnerableChannelAllowList and LdapEnforceChannelBinding [#62873](https://github.com/saltstack/salt/issues/62873)
- Fix unnecessarily complex gce metadata grains code to use googles metadata service more effectively. [#62878](https://github.com/saltstack/salt/issues/62878)
- Fixed dockermod version_info function for docker-py 6.0.0+ [#62882](https://github.com/saltstack/salt/issues/62882)
- Moving setting the LOAD_BALANCING_POLICY_MAP dictionary into the try except block that determines if the cassandra_cql module should be made available. [#62886](https://github.com/saltstack/salt/issues/62886)
- Updating various MongoDB module functions to work with latest version of pymongo. [#62900](https://github.com/saltstack/salt/issues/62900)
- Restored channel for Syndic minions to send job returns to the Salt master. [#62933](https://github.com/saltstack/salt/issues/62933)
- removed _resolve_deps as it required a library that is not generally avalible. and switched to apt-get for everything as that can auto resolve dependencies. [#62934](https://github.com/saltstack/salt/issues/62934)
- Updated pyzmq to version 22.0.3 on Windows builds because the old version was causing salt-minion/salt-call to hang [#62937](https://github.com/saltstack/salt/issues/62937)
- Allow root user to modify crontab lines for non-root users (except AIX and Solaris). Align crontab line changes with the file ones and also with listing crontab. [#62940](https://github.com/saltstack/salt/issues/62940)
- Fix systemd_service.* functions hard code relative command name [#62942](https://github.com/saltstack/salt/issues/62942)
- Fix file.symlink backupname operation can copy remote contents to local disk [#62953](https://github.com/saltstack/salt/issues/62953)
- Issue #62968: Fix issue where cloud deployments were putting the keys in the wrong location on Windows hosts [#62968](https://github.com/saltstack/salt/issues/62968)
- Fixed gpg_passphrase issue with gpg decrypt/encrypt functions [#62977](https://github.com/saltstack/salt/issues/62977)
- Fix file.tidied FileNotFoundError [#62986](https://github.com/saltstack/salt/issues/62986)
- Fixed bug where module.wait states were detected as running legacy module.run syntax [#62988](https://github.com/saltstack/salt/issues/62988)
- Fixed issue with win_wua module where it wouldn't load if the CryptSvc was set to Manual start [#62993](https://github.com/saltstack/salt/issues/62993)
- The `__opts__` dunder dictionary is now added to the loader's `pack` if not
  already present, which makes it accessible via the
  `salt.loader.context.NamedLoaderContext` class. [#63013](https://github.com/saltstack/salt/issues/63013)
- Issue #63024: Fix issue where grains and config data were being place in the wrong location on Windows hosts [#63024](https://github.com/saltstack/salt/issues/63024)
- Fix btrfs.subvolume_snapshot command failing [#63025](https://github.com/saltstack/salt/issues/63025)
- Fix file.retention_schedule always reports changes [#63033](https://github.com/saltstack/salt/issues/63033)
- Fix mongo authentication for mongo ext_pillar and mongo returner

  This fix also include the ability to use the mongo connection string for mongo ext_pillar [#63058](https://github.com/saltstack/salt/issues/63058)
- Fixed x509.create_csr creates invalid CSR by default in the new cryptography x509 module. [#63103](https://github.com/saltstack/salt/issues/63103)
- TCP transport documentation now contains proper master/minion-side filtering information [#63120](https://github.com/saltstack/salt/issues/63120)
- Fixed gpg.verify does not respect gnupghome [#63145](https://github.com/saltstack/salt/issues/63145)
- User responsible for the runner is now correctly reported in the events on the event bus for the runner. [#63148](https://github.com/saltstack/salt/issues/63148)
- Made pillar cache pass extra minion data as well [#63208](https://github.com/saltstack/salt/issues/63208)
- Fix serious performance issues with the file.tidied module [#63231](https://github.com/saltstack/salt/issues/63231)
- Fix rpm_lowpkg version comparison logic when using rpm-vercmp and only one version has a release number. [#63317](https://github.com/saltstack/salt/issues/63317)
- Import StrictVersion and LooseVersion from setuptools.distutils.verison or setuptools._distutils.version, if first not available [#63350](https://github.com/saltstack/salt/issues/63350)
- ``service.status`` on Windows does no longer throws a CommandExecutionError if
  the service is not found on the system. It now returns "Not Found" instead. [#63577](https://github.com/saltstack/salt/issues/63577)
- When the shell is passed as powershell or pwsh, only wrapper the shell in quotes if cmd.run is running on Windows.  When quoted on Linux hosts, this results in an error when the keyword arguments are appended. [#63590](https://github.com/saltstack/salt/issues/63590)
- LGPO: Added support for "Relax minimum password length limits" [#63596](https://github.com/saltstack/salt/issues/63596)
- Fixed the ability to set a scheduled task to auto delete if not scheduled to run again (``delete_after``) [#63650](https://github.com/saltstack/salt/issues/63650)
- When a job is disabled only increase it's _next_fire_time value if the job would have run at the current time, eg. the current _next_fire_time == now. [#63699](https://github.com/saltstack/salt/issues/63699)
- have salt.template.compile_template_str cleanup its temp files. [#63724](https://github.com/saltstack/salt/issues/63724)
- Check file is not empty before attempting to read pillar disk cache file [#63729](https://github.com/saltstack/salt/issues/63729)
- Fixed an issue with generating fingerprints for public keys with different line endings [#63742](https://github.com/saltstack/salt/issues/63742)
- Add `fileserver_interval` and `maintenance_interval` master configuration options. These options control how often to restart the FileServerUpdate and Maintenance processes. Some file server and pillar configurations are known to cause memory leaks over time. A notable example of this are configurations that use pygit2. Salt can not guarantee dependency libraries like pygit2 won't leak memory. Restarting any long running processes that use pygit2 guarantees we can keep the master's memory usage in check. [#63747](https://github.com/saltstack/salt/issues/63747)
- mac_xattr.list and mac_xattr.read will replace undecode-able bytes to avoid raising CommandExecutionError. [#63779](https://github.com/saltstack/salt/issues/63779) [#63779](https://github.com/saltstack/salt/issues/63779)
- Change default GPG keyserver from pgp.mit.edu to keys.openpgp.org. [#63806](https://github.com/saltstack/salt/issues/63806)
- fix cherrypy 400 error output to be less generic. [#63835](https://github.com/saltstack/salt/issues/63835)
- Ensure kwargs is passed along to _call_apt when passed into install function. [#63847](https://github.com/saltstack/salt/issues/63847)
- remove eval and update logging to be more informative on bad config [#63879](https://github.com/saltstack/salt/issues/63879)
- add linux_distribution to util to stop dep warning [#63904](https://github.com/saltstack/salt/issues/63904)
- Fix valuerror when trying to close fileclient. Remove usage of __del__ and close the filclient properly. [#63920](https://github.com/saltstack/salt/issues/63920)
- Handle the situation when a sub proxy minion does not init properly, eg. an exception happens, and the sub proxy object is not available. [#63923](https://github.com/saltstack/salt/issues/63923)
- Clarifying documentation for extension_modules configuration option. [#63929](https://github.com/saltstack/salt/issues/63929)
- Windows pkg module now properly handles versions containing strings [#63935](https://github.com/saltstack/salt/issues/63935)
- Handle the scenario when the check_cmd requisite is used with a state function when the state has a local check_cmd function but that function isn't used by that function. [#63948](https://github.com/saltstack/salt/issues/63948)
- Issue #63981: Allow users to pass verify_ssl to pkg.install/pkg.installed on Windows [#63981](https://github.com/saltstack/salt/issues/63981)
- Hardened permissions on workers.ipc and master_event_pub.ipc. [#64063](https://github.com/saltstack/salt/issues/64063)

# Added

- Introduce a `LIB_STATE_DIR` syspaths variable which defaults to `CONFIG_DIR`,
  but can be individually customized during installation by specifying
  `--salt-lib-state-dir` during installation. Change the default `pki_dir` to
  `<LIB_STATE_DIR>/pki/master` (for the master) and `<LIB_STATE_DIR>/pki/minion`
  (for the minion). [#3396](https://github.com/saltstack/salt/issues/3396)
- Allow users to enable 'queue=True' for all state runs via config file [#31468](https://github.com/saltstack/salt/issues/31468)
- Added pillar templating to vault policies [#43287](https://github.com/saltstack/salt/issues/43287)
- Add support for NVMeF as a transport protocol for hosts in a Pure Storage FlashArray [#51088](https://github.com/saltstack/salt/issues/51088)
- A new salt-ssh roster that generates a roster by parses a known_hosts file. [#54679](https://github.com/saltstack/salt/issues/54679)
- Added Windows Event Viewer support [#54713](https://github.com/saltstack/salt/issues/54713)
- Added the win_lgpo_reg state and execution modules which will allow registry based group policy to be set directly in the Registry.pol file [#56013](https://github.com/saltstack/salt/issues/56013)
- Added resource tagging functions to boto_dynamodb execution module [#57500](https://github.com/saltstack/salt/issues/57500)
- Added `openvswitch_db` state module and functions `bridge_to_parent`,
  `bridge_to_vlan`, `db_get`, and `db_set` to the `openvswitch` execution module.
  Also added optional `parent` and `vlan` parameters to the
  `openvswitch_bridge.present` state module function and the
  `openvswitch.bridge_create` execution module function. [#58986](https://github.com/saltstack/salt/issues/58986)
- State module to manage SysFS attributes [#60154](https://github.com/saltstack/salt/issues/60154)
- Added ability for `salt.wait_for_event` to handle `event_id`s that have a list value. [#60430](https://github.com/saltstack/salt/issues/60430)
- Added suport for Linux ppc64le core grains (cpu_model, virtual, productname, manufacturer, serialnumber) and arm core grains (serialnumber, productname) [#60518](https://github.com/saltstack/salt/issues/60518)
- Added autostart option to virt.defined and virt.running states, along with virt.update execution modules. [#60700](https://github.com/saltstack/salt/issues/60700)
- Added .0 back to our versioning scheme for future versions (e.g. 3006.0) [#60722](https://github.com/saltstack/salt/issues/60722)
- Initial work to allow parallel startup of proxy minions when used as sub proxies with Deltaproxy. [#61153](https://github.com/saltstack/salt/issues/61153)
- Added node label support for GCE [#61245](https://github.com/saltstack/salt/issues/61245)
- Support the --priority flag when adding sources to Chocolatey. [#61319](https://github.com/saltstack/salt/issues/61319)
- Add namespace option to ext_pillar.http_json [#61335](https://github.com/saltstack/salt/issues/61335)
- Added a filter function to ps module to get a list of processes on a minion according to their state. [#61420](https://github.com/saltstack/salt/issues/61420)
- Add postgres.timeout option to postgres module for limiting postgres query times [#61433](https://github.com/saltstack/salt/issues/61433)
- Added new optional vault option, ``config_location``. This can be either ``master`` or ``local`` and defines where vault will look for connection details, either requesting them from the master or using the local config. [#61857](https://github.com/saltstack/salt/issues/61857)
- Add ipwrap() jinja filter to wrap IPv6 addresses with brackets. [#61931](https://github.com/saltstack/salt/issues/61931)
- 'tcp' transport is now available in ipv6-only network [#62009](https://github.com/saltstack/salt/issues/62009)
- Add `diff_attr` parameter to pkg.upgrade() (zypper/yum). [#62031](https://github.com/saltstack/salt/issues/62031)
- Config option pass_variable_prefix allows to distinguish variables that contain paths to pass secrets.
  Config option pass_strict_fetch allows to error out when a secret cannot be fetched from pass.
  Config option pass_dir allows setting the PASSWORD_STORE_DIR env for pass.
  Config option pass_gnupghome allows setting the $GNUPGHOME env for pass. [#62120](https://github.com/saltstack/salt/issues/62120)
- Add file.pruned state and expanded file.rmdir exec module functionality [#62178](https://github.com/saltstack/salt/issues/62178)
- Added "dig.PTR" function to resolve PTR records for IPs, as well as tests and documentation [#62275](https://github.com/saltstack/salt/issues/62275)
- Added the ability to remove a KB using the DISM state/execution modules [#62366](https://github.com/saltstack/salt/issues/62366)
- Add "<tiamat> python" subcommand to allow execution or arbitrary scripts via bundled Python runtime [#62381](https://github.com/saltstack/salt/issues/62381)
- Add ability to provide conditions which convert normal state actions to no-op when true [#62446](https://github.com/saltstack/salt/issues/62446)
- Added debug log messages displaying the command being run when installing packages on Windows [#62480](https://github.com/saltstack/salt/issues/62480)
- Add biosvendor grain [#62496](https://github.com/saltstack/salt/issues/62496)
- Add ifelse Jinja function as found in CFEngine [#62508](https://github.com/saltstack/salt/issues/62508)
- Implementation of Amazon EC2 instance detection and setting `virtual_subtype` grain accordingly including the product if possible to identify. [#62539](https://github.com/saltstack/salt/issues/62539)
- Adds __env__substitution to ext_pillar.stack; followup of #61531, improved exception handling for stacked template (jinja) template rendering and yaml parsing in ext_pillar.stack [#62578](https://github.com/saltstack/salt/issues/62578)
- Increase file.tidied flexibility with regard to age and size [#62678](https://github.com/saltstack/salt/issues/62678)
- Added "connected_devices" feature to netbox pillar module. It contains extra information about devices connected to the minion [#62761](https://github.com/saltstack/salt/issues/62761)
- Add atomic file operation for symlink changes [#62768](https://github.com/saltstack/salt/issues/62768)
- Add password/account locking/unlocking in user.present state on supported operating systems [#62856](https://github.com/saltstack/salt/issues/62856)
- Added onchange configuration for script engine [#62867](https://github.com/saltstack/salt/issues/62867)
- Added output and bare functionality to export_key gpg module function [#62978](https://github.com/saltstack/salt/issues/62978)
- Add keyvalue serializer for environment files [#62983](https://github.com/saltstack/salt/issues/62983)
- Add ability to ignore symlinks in file.tidied [#63042](https://github.com/saltstack/salt/issues/63042)
- salt-cloud support IMDSv2 tokens when using 'use-instance-role-credentials' [#63067](https://github.com/saltstack/salt/issues/63067)
- Fix running fast tests twice and add git labels to suite. [#63081](https://github.com/saltstack/salt/issues/63081)
- Add ability for file.symlink to not set ownership on existing links [#63093](https://github.com/saltstack/salt/issues/63093)
- Restore the previous slack engine and deprecate it, rename replace the slack engine to slack_bolt until deprecation [#63095](https://github.com/saltstack/salt/issues/63095)
- Add functions that will return the underlying block device, mount point, and filesystem type for a given path [#63098](https://github.com/saltstack/salt/issues/63098)
- Add ethtool execution and state module functions for pause [#63128](https://github.com/saltstack/salt/issues/63128)
- Add boardname grain [#63131](https://github.com/saltstack/salt/issues/63131)
- Added management of ECDSA/EdDSA private keys with x509 modules in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#63248](https://github.com/saltstack/salt/issues/63248)
- Added x509 modules support for different output formats in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#63249](https://github.com/saltstack/salt/issues/63249)
- Added deprecation_warning test state for ensuring that deprecation warnings are correctly emitted. [#63315](https://github.com/saltstack/salt/issues/63315)
- Adds a state_events option to state.highstate, state.apply, state.sls, state.sls_id.
  This allows users to enable state_events on a per use basis rather than having to
  enable them globally for all state runs. [#63316](https://github.com/saltstack/salt/issues/63316)
- Allow max queue size setting for state runs to prevent performance problems from queue growth [#63356](https://github.com/saltstack/salt/issues/63356)
- Add support of exposing meta_server_grains for Azure VMs [#63606](https://github.com/saltstack/salt/issues/63606)
- Include the version of `relenv` in the versions report. [#63827](https://github.com/saltstack/salt/issues/63827)
- Added debug log messages displaying the command being run when removing packages on Windows [#63866](https://github.com/saltstack/salt/issues/63866)
- Adding the ability to exclude arguments from a state that end up passed to cmd.retcode when requisites such as onlyif or unless are used. [#63956](https://github.com/saltstack/salt/issues/63956)
- Add --next-release argument to salt/version.py, which prints the next upcoming release. [#64023](https://github.com/saltstack/salt/issues/64023)

# Security

- Upgrade Requirements Due to Security Issues.

  * Upgrade to `cryptography>=39.0.1` due to:
    * https://github.com/advisories/GHSA-x4qr-2fvf-3mr5
    * https://github.com/advisories/GHSA-w7pp-m8wf-vj6r
  * Upgrade to `pyopenssl==23.0.0` due to the cryptography upgrade.
  * Update to `markdown-it-py==2.2.0` due to:
    * https://github.com/advisories/GHSA-jrwr-5x3p-hvc3
    * https://github.com/advisories/GHSA-vrjv-mxr7-vjf8 [#63882](https://github.com/saltstack/salt/issues/63882)


* Wed Mar 29 2023 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.0~rc3

# Removed

- Remove and deprecate the __orchestration__ key from salt.runner and salt.wheel return data. To get it back, set features.enable_deprecated_orchestration_flag master configuration option to True. The flag will be completely removed in Salt 3008 Argon. [#59917](https://github.com/saltstack/salt/issues/59917)
- Removed distutils and replaced with setuptools, given distutils is deprecated and removed in Python 3.12 [#60476](https://github.com/saltstack/salt/issues/60476)
- Removed ``runtests`` targets from ``noxfile.py`` [#62239](https://github.com/saltstack/salt/issues/62239)
- Removed the PyObjC dependency.

  This addresses problems with building a one dir build for macOS.
  It became problematic because depending on the macOS version, it pulls different dependencies, and we would either have to build a macos onedir for each macOS supported release, or ship a crippled onedir(because it would be tied to the macOS version where the onedir was built).
  Since it's currently not being used, it's removed. [#62432](https://github.com/saltstack/salt/issues/62432)
- Removed `SixRedirectImporter` from Salt. Salt hasn't shipped `six` since Salt 3004. [#63874](https://github.com/saltstack/salt/issues/63874)

# Deprecated

- renamed `keep_jobs`, specifying job cache TTL in hours, to `keep_jobs_seconds`, specifying TTL in seconds.
  `keep_jobs` will be removed in the Argon release [#55295](https://github.com/saltstack/salt/issues/55295)
- Removing all references to napalm-base which is no longer supported. [#61542](https://github.com/saltstack/salt/issues/61542)
- The 'ip_bracket' function has been moved from salt/utils/zeromq.py in salt/utils/network.py [#62009](https://github.com/saltstack/salt/issues/62009)
- The `expand_repo_def` function in `salt.modules.aptpkg` is now deprecated. It's only used in `salt.states.pkgrepo` and it has no use of being exposed to the CLI. [#62485](https://github.com/saltstack/salt/issues/62485)
- Deprecated defunct Django returner [#62644](https://github.com/saltstack/salt/issues/62644)
- Deprecate core ESXi and associated states and modules, vcenter and vsphere support in favor of Salt VMware Extensions [#62754](https://github.com/saltstack/salt/issues/62754)
- Removing manufacture grain which has been deprecated. [#62914](https://github.com/saltstack/salt/issues/62914)
- Removing deprecated utils/boto3_elasticsearch.py [#62915](https://github.com/saltstack/salt/issues/62915)
- Removing support for the now deprecated _ext_nodes from salt/master.py. [#62917](https://github.com/saltstack/salt/issues/62917)
- Deprecating the Salt Slack engine in favor of the Salt Slack Bolt Engine. [#63095](https://github.com/saltstack/salt/issues/63095)
- `salt.utils.version.StrictVersion` is now deprecated and it's use should be replaced with `salt.utils.version.Version`. [#63383](https://github.com/saltstack/salt/issues/63383)

# Changed

- More intelligent diffing in changes of file.serialize state. [#48609](https://github.com/saltstack/salt/issues/48609)
- Move deprecation of the neutron module to Argon. Please migrate to the neutronng module instead. [#49430](https://github.com/saltstack/salt/issues/49430)
- ``umask`` is now a global state argument, instead of only applying to ``cmd``
  states. [#57803](https://github.com/saltstack/salt/issues/57803)
- Update pillar.obfuscate to accept kwargs in addition to args.  This is useful when passing in keyword arguments like saltenv that are then passed along to pillar.items. [#58971](https://github.com/saltstack/salt/issues/58971)
- Improve support for listing macOS brew casks [#59439](https://github.com/saltstack/salt/issues/59439)
- Add missing MariaDB Grants to mysql module.
  MariaDB has added some grants in 10.4.x and 10.5.x that are not present here, which results in an error when creating.
  Also improved exception handling in `grant_add` which did not log the original error message and replaced it with a generic error. [#61409](https://github.com/saltstack/salt/issues/61409)
- Use VENV_PIP_TARGET environment variable as a default target for pip if present. [#62089](https://github.com/saltstack/salt/issues/62089)
- Disabled FQDNs grains on macOS by default [#62168](https://github.com/saltstack/salt/issues/62168)
- Replaced pyroute2.IPDB with pyroute2.NDB, as the former is deprecated [#62218](https://github.com/saltstack/salt/issues/62218)
- Enhance capture of error messages for Zypper calls in zypperpkg module. [#62346](https://github.com/saltstack/salt/issues/62346)
- Removed GPG_1_3_1 check [#62895](https://github.com/saltstack/salt/issues/62895)
- Requisite state chunks now all consistently contain `__id__`, `__sls__` and `name`. [#63012](https://github.com/saltstack/salt/issues/63012)
- netapi_enable_clients option to allow enabling/disabling of clients in salt-api.
  By default all clients will now be disabled. Users of salt-api will need
  to update their master config to enable the clients that they use. Not adding
  the netapi_enable_clients option with required clients to the master config will
  disable salt-api. [#63050](https://github.com/saltstack/salt/issues/63050)
- Stop relying on `salt/_version.py` to write Salt's version. Instead use `salt/_version.txt` which only contains the version string. [#63383](https://github.com/saltstack/salt/issues/63383)
- Set enable_fqdns_grains to be False by default. [#63595](https://github.com/saltstack/salt/issues/63595)
- Changelog snippet files must now have a `.md` file extension to be more explicit on what type of rendering is done when they are included in the main `CHANGELOG.md` file. [#63710](https://github.com/saltstack/salt/issues/63710)
- Upgraded to `relenv==0.9.0` [#63883](https://github.com/saltstack/salt/issues/63883)

# Fixed

- Add kwargs to handle extra parameters for http.query [#36138](https://github.com/saltstack/salt/issues/36138)
- Fix mounted bind mounts getting active mount options added [#39292](https://github.com/saltstack/salt/issues/39292)
- Fix `sysctl.present` converts spaces to tabs. [#40054](https://github.com/saltstack/salt/issues/40054)
- Fixes state pkg.purged to purge removed packages on Debian family systems [#42306](https://github.com/saltstack/salt/issues/42306)
- Fix fun_args missing from syndic returns [#45823](https://github.com/saltstack/salt/issues/45823)
- Fix mount.mounted with 'mount: False' reports unmounted file system as unchanged when running with test=True [#47201](https://github.com/saltstack/salt/issues/47201)
- Issue #49310: Allow users to touch a file with Unix date of birth [#49310](https://github.com/saltstack/salt/issues/49310)
- Do not raise an exception in pkg.info_installed on nonzero return code [#51620](https://github.com/saltstack/salt/issues/51620)
- Passes the value of the force parameter from file.copy to its call to file.remove so that files with the read-only attribute are handled. [#51739](https://github.com/saltstack/salt/issues/51739)
- Fixed x509.certificate_managed creates new certificate every run in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#52167](https://github.com/saltstack/salt/issues/52167)
- Don't check for cached pillar errors on state.apply [#52354](https://github.com/saltstack/salt/issues/52354), [#57180](https://github.com/saltstack/salt/issues/57180), [#59339](https://github.com/saltstack/salt/issues/59339)
- Swapping out args and kwargs for arg and kwarg respectively in the Slack engine when the command passed is a runner. [#52400](https://github.com/saltstack/salt/issues/52400)
- Ensure when we're adding chunks to the rules when running aggregation with the iptables state module we use a copy of the chunk otherwise we end up with a recursive mess. [#53353](https://github.com/saltstack/salt/issues/53353)
- When user_create or user_remove fail, return False instead of returning the error. [#53377](https://github.com/saltstack/salt/issues/53377)
- Include sync_roster when sync_all is called. [#53914](https://github.com/saltstack/salt/issues/53914)
- Avoid warning noise in lograte.get [#53988](https://github.com/saltstack/salt/issues/53988)
- Fixed listing revoked keys with gpg.list_keys [#54347](https://github.com/saltstack/salt/issues/54347)
- Fix mount.mounted does not handle blanks properly [#54508](https://github.com/saltstack/salt/issues/54508)
- Fixed grain num_cpus get wrong CPUs count in case of inconsistent CPU numbering. [#54682](https://github.com/saltstack/salt/issues/54682)
- Fix spelling error for python_shell argument in dpkg_lower module [#54907](https://github.com/saltstack/salt/issues/54907)
- Cleaned up bytes response data before sending to non-bytes compatible returners (postgres, mysql) [#55226](https://github.com/saltstack/salt/issues/55226)
- Fixed malformed state return when testing file.managed with unavailable source file [#55269](https://github.com/saltstack/salt/issues/55269)
- Included stdout in error message for Zypper calls in zypperpkg module. [#56016](https://github.com/saltstack/salt/issues/56016)
- Fixed pillar.filter_by with salt-ssh [#56093](https://github.com/saltstack/salt/issues/56093)
- Fix boto_route53 issue with (multiple) VPCs. [#57139](https://github.com/saltstack/salt/issues/57139)
- Remove log from mine runner which was not used. [#57463](https://github.com/saltstack/salt/issues/57463)
- Fixed x509.read_certificate error when reading a Microsoft CA issued certificate in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#57535](https://github.com/saltstack/salt/issues/57535)
- Updating Slack engine to use slack_bolt library. [#57842](https://github.com/saltstack/salt/issues/57842)
- Fixed warning about replace=True with x509.certificate_managed in the new cryptography x509 module. [#58165](https://github.com/saltstack/salt/issues/58165)
- Fix salt.modules.pip:is_installed doesn't handle locally installed packages [#58202](https://github.com/saltstack/salt/issues/58202)
- Add missing MariaDB Grants to mysql module. MariaDB has added some grants in 10.4.x and 10.5.x that are not present here, which results in an error when creating. [#58297](https://github.com/saltstack/salt/issues/58297)
- linux_shadow: Fix cases where malformed shadow entries cause `user.present`
  states to fail. [#58423](https://github.com/saltstack/salt/issues/58423)
- Fixed salt.utils.compat.cmp to work with dictionaries [#58729](https://github.com/saltstack/salt/issues/58729)
- Fixed formatting for terse output mode [#58953](https://github.com/saltstack/salt/issues/58953)
- Fixed RecursiveDictDiffer with added nested dicts [#59017](https://github.com/saltstack/salt/issues/59017)
- Fixed x509.certificate_managed has DoS effect on master in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#59169](https://github.com/saltstack/salt/issues/59169)
- Fixed saltnado websockets disconnecting immediately [#59183](https://github.com/saltstack/salt/issues/59183)
- Fixed x509.certificate_managed rolls certificates every now and then in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#59315](https://github.com/saltstack/salt/issues/59315)
- Fix postgres_privileges.present not idempotent for functions [#59585](https://github.com/saltstack/salt/issues/59585)
- Fixed influxdb_continuous_query.present state to provide the client args to the underlying module on create. [#59766](https://github.com/saltstack/salt/issues/59766)
- Warn when using insecure (http:// based) key_urls for apt-based systems in pkgrepo.managed, and add a kwarg that determines the validity of such a url. [#59786](https://github.com/saltstack/salt/issues/59786)
- add load balancing policy default option and ensure the module can be executed with arguments from CLI [#59909](https://github.com/saltstack/salt/issues/59909)
- Fix salt-ssh when using imports with extra-filerefs. [#60003](https://github.com/saltstack/salt/issues/60003)
- Fixed cache directory corruption startup error [#60170](https://github.com/saltstack/salt/issues/60170)
- Update docs remove dry_run in docstring of file.blockreplace state. [#60227](https://github.com/saltstack/salt/issues/60227)
- Adds Parrot to OS_Family_Map in grains. [#60249](https://github.com/saltstack/salt/issues/60249)
- Fixed stdout and stderr being empty sometimes when use_vt=True for the cmd.run[*] functions [#60365](https://github.com/saltstack/salt/issues/60365)
- Use return code in iptables --check to verify rule exists. [#60467](https://github.com/saltstack/salt/issues/60467)
- Fix regression pip.installed does not pass env_vars when calling pip.list [#60557](https://github.com/saltstack/salt/issues/60557)
- Fix xfs module when additional output included in mkfs.xfs command. [#60853](https://github.com/saltstack/salt/issues/60853)
- Fixed parsing new format of terraform states in roster.terraform [#60915](https://github.com/saltstack/salt/issues/60915)
- Fixed recognizing installed ARMv7 rpm packages in compatible architectures. [#60994](https://github.com/saltstack/salt/issues/60994)
- Fixing changes dict in pkg state to be consistent when installing and test=True. [#60995](https://github.com/saltstack/salt/issues/60995)
- Fix cron.present duplicating entries when changing timespec to special. [#60997](https://github.com/saltstack/salt/issues/60997)
- Made salt-ssh respect --wipe again [#61083](https://github.com/saltstack/salt/issues/61083)
- state.orchestrate_single only passes a pillar if it is set to the state
  function. This allows it to be used with state functions that don't accept a
  pillar keyword argument. [#61092](https://github.com/saltstack/salt/issues/61092)
- Fix ipset state when the comment kwarg is set. [#61122](https://github.com/saltstack/salt/issues/61122)
- Fix issue with archive.unzip where the password was not being encoded for the extract function [#61422](https://github.com/saltstack/salt/issues/61422)
- Some Linux distributions (like AlmaLinux, Astra Linux, Debian, Mendel, Linux
  Mint, Pop!_OS, Rocky Linux) report different `oscodename`, `osfullname`,
  `osfinger` grains if lsb-release is installed or not. They have been changed to
  only derive these OS grains from `/etc/os-release`. [#61618](https://github.com/saltstack/salt/issues/61618)
- Pop!_OS uses the full version (YY.MM) in the osfinger grain now, not just the year. This allows differentiating for example between 20.04 and 20.10. [#61619](https://github.com/saltstack/salt/issues/61619)
- Fix ssh config roster to correctly parse the ssh config files that contain spaces. [#61650](https://github.com/saltstack/salt/issues/61650)
- Fix SoftLayer configuration not raising an exception when a domain is missing [#61727](https://github.com/saltstack/salt/issues/61727)
- Allow the minion to start or salt-call to run even if the user doesn't have permissions to read the root_dir value from the registry [#61789](https://github.com/saltstack/salt/issues/61789)
- Need to move the creation of the proxy object for the ProxyMinion further down in the initialization for sub proxies to ensure that all modules, especially any custom proxy modules, are available before attempting to run the init function. [#61805](https://github.com/saltstack/salt/issues/61805)
- Fixed malformed state return when merge-serializing to an improperly formatted file [#61814](https://github.com/saltstack/salt/issues/61814)
- Made cmdmod._run[_all]_quiet work during minion startup on MacOS with runas specified (which fixed mac_service) [#61816](https://github.com/saltstack/salt/issues/61816)
- When deleting the vault cache, also delete from the session cache [#61821](https://github.com/saltstack/salt/issues/61821)
- Ignore errors on reading license info with dpkg_lowpkg to prevent tracebacks on getting package information. [#61827](https://github.com/saltstack/salt/issues/61827)
- win_lgpo: Display conflicting policy names when more than one policy is found [#61859](https://github.com/saltstack/salt/issues/61859)
- win_lgpo: Fixed intermittent KeyError when getting policy setting using lgpo.get_policy [#61860](https://github.com/saltstack/salt/issues/61860)
- Fixed listing minions on OpenBSD [#61966](https://github.com/saltstack/salt/issues/61966)
- Make Salt to return an error on "pkg" modules and states when targeting duplicated package names [#62019](https://github.com/saltstack/salt/issues/62019)
- Fix return of REST-returned permissions when auth_list is set [#62022](https://github.com/saltstack/salt/issues/62022)
- Normalize package names once on using pkg.installed/removed with yum to make it possible to install packages with the name containing a part similar to a name of architecture. [#62029](https://github.com/saltstack/salt/issues/62029)
- Fix inconsitency regarding name and pkgs parameters between zypperpkg.upgrade() and yumpkg.upgrade() [#62030](https://github.com/saltstack/salt/issues/62030)
- Fix attr=all handling in pkg.list_pkgs() (yum/zypper). [#62032](https://github.com/saltstack/salt/issues/62032)
- Fixed the humanname being ignored in pkgrepo.managed on openSUSE Leap [#62053](https://github.com/saltstack/salt/issues/62053)
- Fixed issue with some LGPO policies having whitespace at the beginning or end of the element alias [#62058](https://github.com/saltstack/salt/issues/62058)
- Fix ordering of args to libcloud_storage.download_object module [#62074](https://github.com/saltstack/salt/issues/62074)
- Ignore extend declarations in sls files that are excluded. [#62082](https://github.com/saltstack/salt/issues/62082)
- Remove leftover usage of impacket [#62101](https://github.com/saltstack/salt/issues/62101)
- Pass executable path from _get_path_exec() is used when calling the program.
  The $HOME env is no longer modified globally.
  Only trailing newlines are stripped from the fetched secret.
  Pass process arguments are handled in a secure way. [#62120](https://github.com/saltstack/salt/issues/62120)
- Ignore some command return codes in openbsdrcctl_service to prevent spurious errors [#62131](https://github.com/saltstack/salt/issues/62131)
- Fixed extra period in filename output in tls module. Instead of "server.crt." it will now be "server.crt". [#62139](https://github.com/saltstack/salt/issues/62139)
- Make sure lingering PAexec-*.exe files in the Windows directory are cleaned up [#62152](https://github.com/saltstack/salt/issues/62152)
- Restored Salt's DeprecationWarnings [#62185](https://github.com/saltstack/salt/issues/62185)
- Fixed issue with forward slashes on Windows with file.recurse and clean=True [#62197](https://github.com/saltstack/salt/issues/62197)
- Recognize OSMC as Debian-based [#62198](https://github.com/saltstack/salt/issues/62198)
- Fixed Zypper module failing on RPM lock file being temporarily unavailable. [#62204](https://github.com/saltstack/salt/issues/62204)
- Improved error handling and diagnostics in the proxmox salt-cloud driver [#62211](https://github.com/saltstack/salt/issues/62211)
- Added EndeavourOS to the Arch os_family. [#62220](https://github.com/saltstack/salt/issues/62220)
- Fix salt-ssh not detecting `platform-python` as a valid interpreter on EL8 [#62235](https://github.com/saltstack/salt/issues/62235)
- Fix pkg.version_cmp on openEuler and a few other os flavors. [#62248](https://github.com/saltstack/salt/issues/62248)
- Fix localhost detection in glusterfs.peers [#62273](https://github.com/saltstack/salt/issues/62273)
- Fix Salt Package Manager (SPM) exception when calling spm create_repo . [#62281](https://github.com/saltstack/salt/issues/62281)
- Fix matcher slowness due to loader invocation [#62283](https://github.com/saltstack/salt/issues/62283)
- Fixes the Puppet module for non-aio Puppet packages for example running the Puppet module on FreeBSD. [#62323](https://github.com/saltstack/salt/issues/62323)
- Issue 62334: Displays a debug log message instead of an error log message when the publisher fails to connect [#62334](https://github.com/saltstack/salt/issues/62334)
- Fix pyobjects renderer access to opts and sls [#62336](https://github.com/saltstack/salt/issues/62336)
- Fix use of random shuffle and sample functions as Jinja filters [#62372](https://github.com/saltstack/salt/issues/62372)
- Fix groups with duplicate GIDs are not returned by get_group_list [#62377](https://github.com/saltstack/salt/issues/62377)
- Fix the "zpool.present" state when enabling zpool features that are already active. [#62390](https://github.com/saltstack/salt/issues/62390)
- Fix ability to execute remote file client methods in saltcheck [#62398](https://github.com/saltstack/salt/issues/62398)
- Update all platforms to use pycparser 2.21 or greater for Py 3.9 or higher, fixes fips fault with openssl v3.x [#62400](https://github.com/saltstack/salt/issues/62400)
- Due to changes in the Netmiko library for the exception paths, need to check the version of Netmiko python library and then import the exceptions from different locations depending on the result. [#62405](https://github.com/saltstack/salt/issues/62405)
- When using preq on a state, then prereq state will first be run with test=True to determine if there are changes.  When there are changes, the state with the prereq option will be run prior to the prereq state.  If this state fails then the prereq state will not run and the state output uses the test=True run.  However, the proposed changes are included for the prereq state are included from the test=True run.  We should pull those out as there weren't actually changes since the prereq state did not run. [#62408](https://github.com/saltstack/salt/issues/62408)
- Added directory mode for file.copy with makedirs [#62426](https://github.com/saltstack/salt/issues/62426)
- Provide better error handling in the various napalm proxy minion functions when the device is not accessible. [#62435](https://github.com/saltstack/salt/issues/62435)
- When handling aggregation, change the order to ensure that the requisites are aggregated first and then the state functions are aggregated.  Caching whether aggregate functions are available for particular states so we don't need to attempt to load them everytime. [#62439](https://github.com/saltstack/salt/issues/62439)
- The patch allows to boostrap kubernetes clusters in the version above 1.13 via salt module [#62451](https://github.com/saltstack/salt/issues/62451)
- sysctl.persist now updates the in-memory value on FreeBSD even if the on-disk value was already correct. [#62461](https://github.com/saltstack/salt/issues/62461)
- Fixed parsing CDROM apt sources [#62474](https://github.com/saltstack/salt/issues/62474)
- Update sanitizing masking for Salt SSH to include additional password like strings. [#62483](https://github.com/saltstack/salt/issues/62483)
- Fix user/group checking on file state functions in the test mode. [#62499](https://github.com/saltstack/salt/issues/62499)
- Fix user.present to allow removing groups using optional_groups parameter and enforcing idempotent group membership. [#62502](https://github.com/saltstack/salt/issues/62502)
- Fix possible tracebacks if there is a package with '------' or '======' in the description is installed on the Debian based minion. [#62519](https://github.com/saltstack/salt/issues/62519)
- Fixed the omitted "pool" parameter when cloning a VM with the proxmox salt-cloud driver [#62521](https://github.com/saltstack/salt/issues/62521)
- Fix rendering of pyobjects states in saltcheck [#62523](https://github.com/saltstack/salt/issues/62523)
- Fixes pillar where a corrupted CacheDisk file forces the pillar to be rebuilt [#62527](https://github.com/saltstack/salt/issues/62527)
- Use str() method instead of repo_line for when python3-apt is installed or not in aptpkg.py. [#62546](https://github.com/saltstack/salt/issues/62546)
- Remove the connection_timeout from netmiko_connection_args before netmiko_connection_args is added to __context__["netmiko_device"]["args"] which is passed along to the Netmiko library. [#62547](https://github.com/saltstack/salt/issues/62547)
- Fix order specific mount.mounted options for persist [#62556](https://github.com/saltstack/salt/issues/62556)
- Fixed salt-cloud cloning a proxmox VM with a specified new vmid. [#62558](https://github.com/saltstack/salt/issues/62558)
- Fix runas with cmd module when using the onedir bundled packages [#62565](https://github.com/saltstack/salt/issues/62565)
- Update setproctitle version for all platforms [#62576](https://github.com/saltstack/salt/issues/62576)
- Fixed missing parameters when cloning a VM with the proxmox salt-cloud driver [#62580](https://github.com/saltstack/salt/issues/62580)
- Handle PermissionError when importing crypt when FIPS is enabled. [#62587](https://github.com/saltstack/salt/issues/62587)
- Correctly reraise exceptions in states.http [#62595](https://github.com/saltstack/salt/issues/62595)
- Fixed syndic eauth. Now jobs will be published when a valid eauth user is targeting allowed minions/functions. [#62618](https://github.com/saltstack/salt/issues/62618)
- updated rest_cherry/app to properly detect arg sent as a string as curl will do when only one arg is supplied. [#62624](https://github.com/saltstack/salt/issues/62624)
- Prevent possible tracebacks in core grains module by ignoring non utf8 characters in /proc/1/environ, /proc/1/cmdline, /proc/cmdline [#62633](https://github.com/saltstack/salt/issues/62633)
- Fixed vault ext pillar return data for KV v2 [#62651](https://github.com/saltstack/salt/issues/62651)
- Fix saltcheck _get_top_states doesn't pass saltenv to state.show_top [#62654](https://github.com/saltstack/salt/issues/62654)
- Fix groupadd.* functions hard code relative command name [#62657](https://github.com/saltstack/salt/issues/62657)
- Fixed pdbedit.create trying to use a bytes-like hash as string. [#62670](https://github.com/saltstack/salt/issues/62670)
- Fix depenency on legacy boto module in boto3 modules [#62672](https://github.com/saltstack/salt/issues/62672)
- Modified "_get_flags" function so that it returns regex flags instead of integers [#62676](https://github.com/saltstack/salt/issues/62676)
- Change startup ReqServer log messages from error to info level. [#62728](https://github.com/saltstack/salt/issues/62728)
- Fix kmod.* functions hard code relative command name [#62772](https://github.com/saltstack/salt/issues/62772)
- Fix mac_brew_pkg to work with null taps [#62793](https://github.com/saltstack/salt/issues/62793)
- Fixing a bug when listing the running schedule if "schedule.enable" and/or "schedule.disable" has been run, where the "enabled" items is being treated as a schedule item. [#62795](https://github.com/saltstack/salt/issues/62795)
- Prevent annoying RuntimeWarning message about line buffering (buffering=1) not being supported in binary mode [#62817](https://github.com/saltstack/salt/issues/62817)
- Include UID and GID checks in modules.file.check_perms as well as comparing
  ownership by username and group name. [#62818](https://github.com/saltstack/salt/issues/62818)
- Fix presence events on TCP transport by removing a client's presence when minion disconnects from publish channel correctly [#62826](https://github.com/saltstack/salt/issues/62826)
- Remove Azure deprecation messages from functions that always run w/ salt-cloud [#62845](https://github.com/saltstack/salt/issues/62845)
- Use select instead of iterating over entrypoints as a dictionary for importlib_metadata>=5.0.0 [#62854](https://github.com/saltstack/salt/issues/62854)
- Fixed master job scheduler using when [#62858](https://github.com/saltstack/salt/issues/62858)
- LGPO: Added support for missing domain controller policies: VulnerableChannelAllowList and LdapEnforceChannelBinding [#62873](https://github.com/saltstack/salt/issues/62873)
- Fix unnecessarily complex gce metadata grains code to use googles metadata service more effectively. [#62878](https://github.com/saltstack/salt/issues/62878)
- Fixed dockermod version_info function for docker-py 6.0.0+ [#62882](https://github.com/saltstack/salt/issues/62882)
- Moving setting the LOAD_BALANCING_POLICY_MAP dictionary into the try except block that determines if the cassandra_cql module should be made available. [#62886](https://github.com/saltstack/salt/issues/62886)
- Updating various MongoDB module functions to work with latest version of pymongo. [#62900](https://github.com/saltstack/salt/issues/62900)
- Restored channel for Syndic minions to send job returns to the Salt master. [#62933](https://github.com/saltstack/salt/issues/62933)
- removed _resolve_deps as it required a library that is not generally avalible. and switched to apt-get for everything as that can auto resolve dependencies. [#62934](https://github.com/saltstack/salt/issues/62934)
- Updated pyzmq to version 22.0.3 on Windows builds because the old version was causing salt-minion/salt-call to hang [#62937](https://github.com/saltstack/salt/issues/62937)
- Allow root user to modify crontab lines for non-root users (except AIX and Solaris). Align crontab line changes with the file ones and also with listing crontab. [#62940](https://github.com/saltstack/salt/issues/62940)
- Fix systemd_service.* functions hard code relative command name [#62942](https://github.com/saltstack/salt/issues/62942)
- Fix file.symlink backupname operation can copy remote contents to local disk [#62953](https://github.com/saltstack/salt/issues/62953)
- Issue #62968: Fix issue where cloud deployments were putting the keys in the wrong location on Windows hosts [#62968](https://github.com/saltstack/salt/issues/62968)
- Fixed gpg_passphrase issue with gpg decrypt/encrypt functions [#62977](https://github.com/saltstack/salt/issues/62977)
- Fix file.tidied FileNotFoundError [#62986](https://github.com/saltstack/salt/issues/62986)
- Fixed bug where module.wait states were detected as running legacy module.run syntax [#62988](https://github.com/saltstack/salt/issues/62988)
- Fixed issue with win_wua module where it wouldn't load if the CryptSvc was set to Manual start [#62993](https://github.com/saltstack/salt/issues/62993)
- The `__opts__` dunder dictionary is now added to the loader's `pack` if not
  already present, which makes it accessible via the
  `salt.loader.context.NamedLoaderContext` class. [#63013](https://github.com/saltstack/salt/issues/63013)
- Issue #63024: Fix issue where grains and config data were being place in the wrong location on Windows hosts [#63024](https://github.com/saltstack/salt/issues/63024)
- Fix btrfs.subvolume_snapshot command failing [#63025](https://github.com/saltstack/salt/issues/63025)
- Fix file.retention_schedule always reports changes [#63033](https://github.com/saltstack/salt/issues/63033)
- Fix mongo authentication for mongo ext_pillar and mongo returner

  This fix also include the ability to use the mongo connection string for mongo ext_pillar [#63058](https://github.com/saltstack/salt/issues/63058)
- Fixed x509.create_csr creates invalid CSR by default in the new cryptography x509 module. [#63103](https://github.com/saltstack/salt/issues/63103)
- TCP transport documentation now contains proper master/minion-side filtering information [#63120](https://github.com/saltstack/salt/issues/63120)
- Fixed gpg.verify does not respect gnupghome [#63145](https://github.com/saltstack/salt/issues/63145)
- Made pillar cache pass extra minion data as well [#63208](https://github.com/saltstack/salt/issues/63208)
- Fix serious performance issues with the file.tidied module [#63231](https://github.com/saltstack/salt/issues/63231)
- Fix rpm_lowpkg version comparison logic when using rpm-vercmp and only one version has a release number. [#63317](https://github.com/saltstack/salt/issues/63317)
- Import StrictVersion and LooseVersion from setuptools.distutils.verison or setuptools._distutils.version, if first not available [#63350](https://github.com/saltstack/salt/issues/63350)
- When the shell is passed as powershell or pwsh, only wrapper the shell in quotes if cmd.run is running on Windows.  When quoted on Linux hosts, this results in an error when the keyword arguments are appended. [#63590](https://github.com/saltstack/salt/issues/63590)
- LGPO: Added support for "Relax minimum password length limits" [#63596](https://github.com/saltstack/salt/issues/63596)
- Fixed the ability to set a scheduled task to auto delete if not scheduled to run again (``delete_after``) [#63650](https://github.com/saltstack/salt/issues/63650)
- When a job is disabled only increase it's _next_fire_time value if the job would have run at the current time, eg. the current _next_fire_time == now. [#63699](https://github.com/saltstack/salt/issues/63699)
- have salt.template.compile_template_str cleanup its temp files. [#63724](https://github.com/saltstack/salt/issues/63724)
- Check file is not empty before attempting to read pillar disk cache file [#63729](https://github.com/saltstack/salt/issues/63729)
- Fixed an issue with generating fingerprints for public keys with different line endings [#63742](https://github.com/saltstack/salt/issues/63742)
- Change default GPG keyserver from pgp.mit.edu to keys.openpgp.org. [#63806](https://github.com/saltstack/salt/issues/63806)
- fix cherrypy 400 error output to be less generic. [#63835](https://github.com/saltstack/salt/issues/63835)
- Ensure kwargs is passed along to _call_apt when passed into install function. [#63847](https://github.com/saltstack/salt/issues/63847)
- remove eval and update logging to be more informative on bad config [#63879](https://github.com/saltstack/salt/issues/63879)
- add linux_distribution to util to stop dep warning [#63904](https://github.com/saltstack/salt/issues/63904)
- Handle the situation when a sub proxy minion does not init properly, eg. an exception happens, and the sub proxy object is not available. [#63923](https://github.com/saltstack/salt/issues/63923)
- Clarifying documentation for extension_modules configuration option. [#63929](https://github.com/saltstack/salt/issues/63929)
- Windows pkg module now properly handles versions containing strings [#63935](https://github.com/saltstack/salt/issues/63935)
- Handle the scenario when the check_cmd requisite is used with a state function when the state has a local check_cmd function but that function isn't used by that function. [#63948](https://github.com/saltstack/salt/issues/63948)
- Issue #63981: Allow users to pass verify_ssl to pkg.install/pkg.installed on Windows [#63981](https://github.com/saltstack/salt/issues/63981)

# Added

- Introduce a `LIB_STATE_DIR` syspaths variable which defaults to `CONFIG_DIR`,
  but can be individually customized during installation by specifying
  `--salt-lib-state-dir` during installation. Change the default `pki_dir` to
  `<LIB_STATE_DIR>/pki/master` (for the master) and `<LIB_STATE_DIR>/pki/minion`
  (for the minion). [#3396](https://github.com/saltstack/salt/issues/3396)
- Allow users to enable 'queue=True' for all state runs via config file [#31468](https://github.com/saltstack/salt/issues/31468)
- Added pillar templating to vault policies [#43287](https://github.com/saltstack/salt/issues/43287)
- Add support for NVMeF as a transport protocol for hosts in a Pure Storage FlashArray [#51088](https://github.com/saltstack/salt/issues/51088)
- A new salt-ssh roster that generates a roster by parses a known_hosts file. [#54679](https://github.com/saltstack/salt/issues/54679)
- Added Windows Event Viewer support [#54713](https://github.com/saltstack/salt/issues/54713)
- Added the win_lgpo_reg state and execution modules which will allow registry based group policy to be set directly in the Registry.pol file [#56013](https://github.com/saltstack/salt/issues/56013)
- Added resource tagging functions to boto_dynamodb execution module [#57500](https://github.com/saltstack/salt/issues/57500)
- Added `openvswitch_db` state module and functions `bridge_to_parent`,
  `bridge_to_vlan`, `db_get`, and `db_set` to the `openvswitch` execution module.
  Also added optional `parent` and `vlan` parameters to the
  `openvswitch_bridge.present` state module function and the
  `openvswitch.bridge_create` execution module function. [#58986](https://github.com/saltstack/salt/issues/58986)
- State module to manage SysFS attributes [#60154](https://github.com/saltstack/salt/issues/60154)
- Added ability for `salt.wait_for_event` to handle `event_id`s that have a list value. [#60430](https://github.com/saltstack/salt/issues/60430)
- Added suport for Linux ppc64le core grains (cpu_model, virtual, productname, manufacturer, serialnumber) and arm core grains (serialnumber, productname) [#60518](https://github.com/saltstack/salt/issues/60518)
- Added autostart option to virt.defined and virt.running states, along with virt.update execution modules. [#60700](https://github.com/saltstack/salt/issues/60700)
- Added .0 back to our versioning scheme for future versions (e.g. 3006.0) [#60722](https://github.com/saltstack/salt/issues/60722)
- Initial work to allow parallel startup of proxy minions when used as sub proxies with Deltaproxy. [#61153](https://github.com/saltstack/salt/issues/61153)
- Added node label support for GCE [#61245](https://github.com/saltstack/salt/issues/61245)
- Support the --priority flag when adding sources to Chocolatey. [#61319](https://github.com/saltstack/salt/issues/61319)
- Add namespace option to ext_pillar.http_json [#61335](https://github.com/saltstack/salt/issues/61335)
- Added a filter function to ps module to get a list of processes on a minion according to their state. [#61420](https://github.com/saltstack/salt/issues/61420)
- Add postgres.timeout option to postgres module for limiting postgres query times [#61433](https://github.com/saltstack/salt/issues/61433)
- Added new optional vault option, ``config_location``. This can be either ``master`` or ``local`` and defines where vault will look for connection details, either requesting them from the master or using the local config. [#61857](https://github.com/saltstack/salt/issues/61857)
- Add ipwrap() jinja filter to wrap IPv6 addresses with brackets. [#61931](https://github.com/saltstack/salt/issues/61931)
- 'tcp' transport is now available in ipv6-only network [#62009](https://github.com/saltstack/salt/issues/62009)
- Add `diff_attr` parameter to pkg.upgrade() (zypper/yum). [#62031](https://github.com/saltstack/salt/issues/62031)
- Config option pass_variable_prefix allows to distinguish variables that contain paths to pass secrets.
  Config option pass_strict_fetch allows to error out when a secret cannot be fetched from pass.
  Config option pass_dir allows setting the PASSWORD_STORE_DIR env for pass.
  Config option pass_gnupghome allows setting the $GNUPGHOME env for pass. [#62120](https://github.com/saltstack/salt/issues/62120)
- Add file.pruned state and expanded file.rmdir exec module functionality [#62178](https://github.com/saltstack/salt/issues/62178)
- Added "dig.PTR" function to resolve PTR records for IPs, as well as tests and documentation [#62275](https://github.com/saltstack/salt/issues/62275)
- Added the ability to remove a KB using the DISM state/execution modules [#62366](https://github.com/saltstack/salt/issues/62366)
- Add "<tiamat> python" subcommand to allow execution or arbitrary scripts via bundled Python runtime [#62381](https://github.com/saltstack/salt/issues/62381)
- Add ability to provide conditions which convert normal state actions to no-op when true [#62446](https://github.com/saltstack/salt/issues/62446)
- Added debug log messages displaying the command being run when installing packages on Windows [#62480](https://github.com/saltstack/salt/issues/62480)
- Add biosvendor grain [#62496](https://github.com/saltstack/salt/issues/62496)
- Add ifelse Jinja function as found in CFEngine [#62508](https://github.com/saltstack/salt/issues/62508)
- Implementation of Amazon EC2 instance detection and setting `virtual_subtype` grain accordingly including the product if possible to identify. [#62539](https://github.com/saltstack/salt/issues/62539)
- Adds __env__substitution to ext_pillar.stack; followup of #61531, improved exception handling for stacked template (jinja) template rendering and yaml parsing in ext_pillar.stack [#62578](https://github.com/saltstack/salt/issues/62578)
- Increase file.tidied flexibility with regard to age and size [#62678](https://github.com/saltstack/salt/issues/62678)
- Added "connected_devices" feature to netbox pillar module. It contains extra information about devices connected to the minion [#62761](https://github.com/saltstack/salt/issues/62761)
- Add atomic file operation for symlink changes [#62768](https://github.com/saltstack/salt/issues/62768)
- Add password/account locking/unlocking in user.present state on supported operating systems [#62856](https://github.com/saltstack/salt/issues/62856)
- Added onchange configuration for script engine [#62867](https://github.com/saltstack/salt/issues/62867)
- Added output and bare functionality to export_key gpg module function [#62978](https://github.com/saltstack/salt/issues/62978)
- Add keyvalue serializer for environment files [#62983](https://github.com/saltstack/salt/issues/62983)
- Add ability to ignore symlinks in file.tidied [#63042](https://github.com/saltstack/salt/issues/63042)
- salt-cloud support IMDSv2 tokens when using 'use-instance-role-credentials' [#63067](https://github.com/saltstack/salt/issues/63067)
- Add ability for file.symlink to not set ownership on existing links [#63093](https://github.com/saltstack/salt/issues/63093)
- Restore the previous slack engine and deprecate it, rename replace the slack engine to slack_bolt until deprecation [#63095](https://github.com/saltstack/salt/issues/63095)
- Add functions that will return the underlying block device, mount point, and filesystem type for a given path [#63098](https://github.com/saltstack/salt/issues/63098)
- Add ethtool execution and state module functions for pause [#63128](https://github.com/saltstack/salt/issues/63128)
- Add boardname grain [#63131](https://github.com/saltstack/salt/issues/63131)
- Added management of ECDSA/EdDSA private keys with x509 modules in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#63248](https://github.com/saltstack/salt/issues/63248)
- Added x509 modules support for different output formats in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#63249](https://github.com/saltstack/salt/issues/63249)
- Added deprecation_warning test state for ensuring that deprecation warnings are correctly emitted. [#63315](https://github.com/saltstack/salt/issues/63315)
- Adds a state_events option to state.highstate, state.apply, state.sls, state.sls_id.
  This allows users to enable state_events on a per use basis rather than having to
  enable them globally for all state runs. [#63316](https://github.com/saltstack/salt/issues/63316)
- Allow max queue size setting for state runs to prevent performance problems from queue growth [#63356](https://github.com/saltstack/salt/issues/63356)
- Add support of exposing meta_server_grains for Azure VMs [#63606](https://github.com/saltstack/salt/issues/63606)
- Include the version of `relenv` in the versions report. [#63827](https://github.com/saltstack/salt/issues/63827)
- Added debug log messages displaying the command being run when removing packages on Windows [#63866](https://github.com/saltstack/salt/issues/63866)

# Security

- Upgrade Requirements Due to Security Issues.

  * Upgrade to `cryptography>=39.0.1` due to:
    * https://github.com/advisories/GHSA-x4qr-2fvf-3mr5
    * https://github.com/advisories/GHSA-w7pp-m8wf-vj6r
  * Upgrade to `pyopenssl==23.0.0` due to the cryptography upgrade.
  * Update to `markdown-it-py==2.2.0` due to:
    * https://github.com/advisories/GHSA-jrwr-5x3p-hvc3
    * https://github.com/advisories/GHSA-vrjv-mxr7-vjf8 [#63882](https://github.com/saltstack/salt/issues/63882)


* Sun Mar 19 2023 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.0~rc2

# Removed

- Remove and deprecate the __orchestration__ key from salt.runner and salt.wheel return data. To get it back, set features.enable_deprecated_orchestration_flag master configuration option to True. The flag will be completely removed in Salt 3008 Argon. [#59917](https://github.com/saltstack/salt/issues/59917)
- Removed distutils and replaced with setuptools, given distutils is deprecated and removed in Python 3.12 [#60476](https://github.com/saltstack/salt/issues/60476)
- Removed ``runtests`` targets from ``noxfile.py`` [#62239](https://github.com/saltstack/salt/issues/62239)
- Removed the PyObjC dependency.

  This addresses problems with building a one dir build for macOS.
  It became problematic because depending on the macOS version, it pulls different dependencies, and we would either have to build a macos onedir for each macOS supported release, or ship a crippled onedir(because it would be tied to the macOS version where the onedir was built).
  Since it's currently not being used, it's removed. [#62432](https://github.com/saltstack/salt/issues/62432)
- Removed `SixRedirectImporter` from Salt. Salt hasn't shipped `six` since Salt 3004. [#63874](https://github.com/saltstack/salt/issues/63874)

# Deprecated

- renamed `keep_jobs`, specifying job cache TTL in hours, to `keep_jobs_seconds`, specifying TTL in seconds.
  `keep_jobs` will be removed in the Argon release [#55295](https://github.com/saltstack/salt/issues/55295)
- Removing all references to napalm-base which is no longer supported. [#61542](https://github.com/saltstack/salt/issues/61542)
- The 'ip_bracket' function has been moved from salt/utils/zeromq.py in salt/utils/network.py [#62009](https://github.com/saltstack/salt/issues/62009)
- The `expand_repo_def` function in `salt.modules.aptpkg` is now deprecated. It's only used in `salt.states.pkgrepo` and it has no use of being exposed to the CLI. [#62485](https://github.com/saltstack/salt/issues/62485)
- Deprecated defunct Django returner [#62644](https://github.com/saltstack/salt/issues/62644)
- Deprecate core ESXi and associated states and modules, vcenter and vsphere support in favor of Salt VMware Extensions [#62754](https://github.com/saltstack/salt/issues/62754)
- Removing manufacture grain which has been deprecated. [#62914](https://github.com/saltstack/salt/issues/62914)
- Removing deprecated utils/boto3_elasticsearch.py [#62915](https://github.com/saltstack/salt/issues/62915)
- Removing support for the now deprecated _ext_nodes from salt/master.py. [#62917](https://github.com/saltstack/salt/issues/62917)
- Deprecating the Salt Slack engine in favor of the Salt Slack Bolt Engine. [#63095](https://github.com/saltstack/salt/issues/63095)
- `salt.utils.version.StrictVersion` is now deprecated and it's use should be replaced with `salt.utils.version.Version`. [#63383](https://github.com/saltstack/salt/issues/63383)

# Changed

- More intelligent diffing in changes of file.serialize state. [#48609](https://github.com/saltstack/salt/issues/48609)
- Move deprecation of the neutron module to Argon. Please migrate to the neutronng module instead. [#49430](https://github.com/saltstack/salt/issues/49430)
- ``umask`` is now a global state argument, instead of only applying to ``cmd``
  states. [#57803](https://github.com/saltstack/salt/issues/57803)
- Update pillar.obfuscate to accept kwargs in addition to args.  This is useful when passing in keyword arguments like saltenv that are then passed along to pillar.items. [#58971](https://github.com/saltstack/salt/issues/58971)
- Improve support for listing macOS brew casks [#59439](https://github.com/saltstack/salt/issues/59439)
- Add missing MariaDB Grants to mysql module.
  MariaDB has added some grants in 10.4.x and 10.5.x that are not present here, which results in an error when creating.
  Also improved exception handling in `grant_add` which did not log the original error message and replaced it with a generic error. [#61409](https://github.com/saltstack/salt/issues/61409)
- Use VENV_PIP_TARGET environment variable as a default target for pip if present. [#62089](https://github.com/saltstack/salt/issues/62089)
- Disabled FQDNs grains on macOS by default [#62168](https://github.com/saltstack/salt/issues/62168)
- Replaced pyroute2.IPDB with pyroute2.NDB, as the former is deprecated [#62218](https://github.com/saltstack/salt/issues/62218)
- Enhance capture of error messages for Zypper calls in zypperpkg module. [#62346](https://github.com/saltstack/salt/issues/62346)
- Removed GPG_1_3_1 check [#62895](https://github.com/saltstack/salt/issues/62895)
- Requisite state chunks now all consistently contain `__id__`, `__sls__` and `name`. [#63012](https://github.com/saltstack/salt/issues/63012)
- netapi_enable_clients option to allow enabling/disabling of clients in salt-api.
  By default all clients will now be disabled. Users of salt-api will need
  to update their master config to enable the clients that they use. Not adding
  the netapi_enable_clients option with required clients to the master config will
  disable salt-api. [#63050](https://github.com/saltstack/salt/issues/63050)
- Stop relying on `salt/_version.py` to write Salt's version. Instead use `salt/_version.txt` which only contains the version string. [#63383](https://github.com/saltstack/salt/issues/63383)
- Set enable_fqdns_grains to be False by default. [#63595](https://github.com/saltstack/salt/issues/63595)
- Changelog snippet files must now have a `.md` file extension to be more explicit on what type of rendering is done when they are included in the main `CHANGELOG.md` file. [#63710](https://github.com/saltstack/salt/issues/63710)

# Fixed

- Add kwargs to handle extra parameters for http.query [#36138](https://github.com/saltstack/salt/issues/36138)
- Fix mounted bind mounts getting active mount options added [#39292](https://github.com/saltstack/salt/issues/39292)
- Fix `sysctl.present` converts spaces to tabs. [#40054](https://github.com/saltstack/salt/issues/40054)
- Fixes state pkg.purged to purge removed packages on Debian family systems [#42306](https://github.com/saltstack/salt/issues/42306)
- Fix fun_args missing from syndic returns [#45823](https://github.com/saltstack/salt/issues/45823)
- Fix mount.mounted with 'mount: False' reports unmounted file system as unchanged when running with test=True [#47201](https://github.com/saltstack/salt/issues/47201)
- Issue #49310: Allow users to touch a file with Unix date of birth [#49310](https://github.com/saltstack/salt/issues/49310)
- Do not raise an exception in pkg.info_installed on nonzero return code [#51620](https://github.com/saltstack/salt/issues/51620)
- Passes the value of the force parameter from file.copy to its call to file.remove so that files with the read-only attribute are handled. [#51739](https://github.com/saltstack/salt/issues/51739)
- Fixed x509.certificate_managed creates new certificate every run in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#52167](https://github.com/saltstack/salt/issues/52167)
- Don't check for cached pillar errors on state.apply [#52354](https://github.com/saltstack/salt/issues/52354), [#57180](https://github.com/saltstack/salt/issues/57180), [#59339](https://github.com/saltstack/salt/issues/59339)
- Swapping out args and kwargs for arg and kwarg respectively in the Slack engine when the command passed is a runner. [#52400](https://github.com/saltstack/salt/issues/52400)
- Ensure when we're adding chunks to the rules when running aggregation with the iptables state module we use a copy of the chunk otherwise we end up with a recursive mess. [#53353](https://github.com/saltstack/salt/issues/53353)
- When user_create or user_remove fail, return False instead of returning the error. [#53377](https://github.com/saltstack/salt/issues/53377)
- Include sync_roster when sync_all is called. [#53914](https://github.com/saltstack/salt/issues/53914)
- Avoid warning noise in lograte.get [#53988](https://github.com/saltstack/salt/issues/53988)
- Fixed listing revoked keys with gpg.list_keys [#54347](https://github.com/saltstack/salt/issues/54347)
- Fix mount.mounted does not handle blanks properly [#54508](https://github.com/saltstack/salt/issues/54508)
- Fixed grain num_cpus get wrong CPUs count in case of inconsistent CPU numbering. [#54682](https://github.com/saltstack/salt/issues/54682)
- Fix spelling error for python_shell argument in dpkg_lower module [#54907](https://github.com/saltstack/salt/issues/54907)
- Cleaned up bytes response data before sending to non-bytes compatible returners (postgres, mysql) [#55226](https://github.com/saltstack/salt/issues/55226)
- Fixed malformed state return when testing file.managed with unavailable source file [#55269](https://github.com/saltstack/salt/issues/55269)
- Included stdout in error message for Zypper calls in zypperpkg module. [#56016](https://github.com/saltstack/salt/issues/56016)
- Fixed pillar.filter_by with salt-ssh [#56093](https://github.com/saltstack/salt/issues/56093)
- Fix boto_route53 issue with (multiple) VPCs. [#57139](https://github.com/saltstack/salt/issues/57139)
- Remove log from mine runner which was not used. [#57463](https://github.com/saltstack/salt/issues/57463)
- Fixed x509.read_certificate error when reading a Microsoft CA issued certificate in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#57535](https://github.com/saltstack/salt/issues/57535)
- Updating Slack engine to use slack_bolt library. [#57842](https://github.com/saltstack/salt/issues/57842)
- Fixed warning about replace=True with x509.certificate_managed in the new cryptography x509 module. [#58165](https://github.com/saltstack/salt/issues/58165)
- Fix salt.modules.pip:is_installed doesn't handle locally installed packages [#58202](https://github.com/saltstack/salt/issues/58202)
- Add missing MariaDB Grants to mysql module. MariaDB has added some grants in 10.4.x and 10.5.x that are not present here, which results in an error when creating. [#58297](https://github.com/saltstack/salt/issues/58297)
- linux_shadow: Fix cases where malformed shadow entries cause `user.present`
  states to fail. [#58423](https://github.com/saltstack/salt/issues/58423)
- Fixed salt.utils.compat.cmp to work with dictionaries [#58729](https://github.com/saltstack/salt/issues/58729)
- Fixed formatting for terse output mode [#58953](https://github.com/saltstack/salt/issues/58953)
- Fixed RecursiveDictDiffer with added nested dicts [#59017](https://github.com/saltstack/salt/issues/59017)
- Fixed x509.certificate_managed has DoS effect on master in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#59169](https://github.com/saltstack/salt/issues/59169)
- Fixed saltnado websockets disconnecting immediately [#59183](https://github.com/saltstack/salt/issues/59183)
- Fixed x509.certificate_managed rolls certificates every now and then in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#59315](https://github.com/saltstack/salt/issues/59315)
- Fix postgres_privileges.present not idempotent for functions [#59585](https://github.com/saltstack/salt/issues/59585)
- Fixed influxdb_continuous_query.present state to provide the client args to the underlying module on create. [#59766](https://github.com/saltstack/salt/issues/59766)
- Warn when using insecure (http:// based) key_urls for apt-based systems in pkgrepo.managed, and add a kwarg that determines the validity of such a url. [#59786](https://github.com/saltstack/salt/issues/59786)
- add load balancing policy default option and ensure the module can be executed with arguments from CLI [#59909](https://github.com/saltstack/salt/issues/59909)
- Fix salt-ssh when using imports with extra-filerefs. [#60003](https://github.com/saltstack/salt/issues/60003)
- Fixed cache directory corruption startup error [#60170](https://github.com/saltstack/salt/issues/60170)
- Update docs remove dry_run in docstring of file.blockreplace state. [#60227](https://github.com/saltstack/salt/issues/60227)
- Adds Parrot to OS_Family_Map in grains. [#60249](https://github.com/saltstack/salt/issues/60249)
- Fixed stdout and stderr being empty sometimes when use_vt=True for the cmd.run[*] functions [#60365](https://github.com/saltstack/salt/issues/60365)
- Use return code in iptables --check to verify rule exists. [#60467](https://github.com/saltstack/salt/issues/60467)
- Fix regression pip.installed does not pass env_vars when calling pip.list [#60557](https://github.com/saltstack/salt/issues/60557)
- Fix xfs module when additional output included in mkfs.xfs command. [#60853](https://github.com/saltstack/salt/issues/60853)
- Fixed parsing new format of terraform states in roster.terraform [#60915](https://github.com/saltstack/salt/issues/60915)
- Fixed recognizing installed ARMv7 rpm packages in compatible architectures. [#60994](https://github.com/saltstack/salt/issues/60994)
- Fixing changes dict in pkg state to be consistent when installing and test=True. [#60995](https://github.com/saltstack/salt/issues/60995)
- Fix cron.present duplicating entries when changing timespec to special. [#60997](https://github.com/saltstack/salt/issues/60997)
- Made salt-ssh respect --wipe again [#61083](https://github.com/saltstack/salt/issues/61083)
- state.orchestrate_single only passes a pillar if it is set to the state
  function. This allows it to be used with state functions that don't accept a
  pillar keyword argument. [#61092](https://github.com/saltstack/salt/issues/61092)
- Fix ipset state when the comment kwarg is set. [#61122](https://github.com/saltstack/salt/issues/61122)
- Fix issue with archive.unzip where the password was not being encoded for the extract function [#61422](https://github.com/saltstack/salt/issues/61422)
- Some Linux distributions (like AlmaLinux, Astra Linux, Debian, Mendel, Linux
  Mint, Pop!_OS, Rocky Linux) report different `oscodename`, `osfullname`,
  `osfinger` grains if lsb-release is installed or not. They have been changed to
  only derive these OS grains from `/etc/os-release`. [#61618](https://github.com/saltstack/salt/issues/61618)
- Pop!_OS uses the full version (YY.MM) in the osfinger grain now, not just the year. This allows differentiating for example between 20.04 and 20.10. [#61619](https://github.com/saltstack/salt/issues/61619)
- Fix ssh config roster to correctly parse the ssh config files that contain spaces. [#61650](https://github.com/saltstack/salt/issues/61650)
- Fix SoftLayer configuration not raising an exception when a domain is missing [#61727](https://github.com/saltstack/salt/issues/61727)
- Allow the minion to start or salt-call to run even if the user doesn't have permissions to read the root_dir value from the registry [#61789](https://github.com/saltstack/salt/issues/61789)
- Need to move the creation of the proxy object for the ProxyMinion further down in the initialization for sub proxies to ensure that all modules, especially any custom proxy modules, are available before attempting to run the init function. [#61805](https://github.com/saltstack/salt/issues/61805)
- Fixed malformed state return when merge-serializing to an improperly formatted file [#61814](https://github.com/saltstack/salt/issues/61814)
- Made cmdmod._run[_all]_quiet work during minion startup on MacOS with runas specified (which fixed mac_service) [#61816](https://github.com/saltstack/salt/issues/61816)
- When deleting the vault cache, also delete from the session cache [#61821](https://github.com/saltstack/salt/issues/61821)
- Ignore errors on reading license info with dpkg_lowpkg to prevent tracebacks on getting package information. [#61827](https://github.com/saltstack/salt/issues/61827)
- win_lgpo: Display conflicting policy names when more than one policy is found [#61859](https://github.com/saltstack/salt/issues/61859)
- win_lgpo: Fixed intermittent KeyError when getting policy setting using lgpo.get_policy [#61860](https://github.com/saltstack/salt/issues/61860)
- Fixed listing minions on OpenBSD [#61966](https://github.com/saltstack/salt/issues/61966)
- Make Salt to return an error on "pkg" modules and states when targeting duplicated package names [#62019](https://github.com/saltstack/salt/issues/62019)
- Fix return of REST-returned permissions when auth_list is set [#62022](https://github.com/saltstack/salt/issues/62022)
- Normalize package names once on using pkg.installed/removed with yum to make it possible to install packages with the name containing a part similar to a name of architecture. [#62029](https://github.com/saltstack/salt/issues/62029)
- Fix inconsitency regarding name and pkgs parameters between zypperpkg.upgrade() and yumpkg.upgrade() [#62030](https://github.com/saltstack/salt/issues/62030)
- Fix attr=all handling in pkg.list_pkgs() (yum/zypper). [#62032](https://github.com/saltstack/salt/issues/62032)
- Fixed the humanname being ignored in pkgrepo.managed on openSUSE Leap [#62053](https://github.com/saltstack/salt/issues/62053)
- Fixed issue with some LGPO policies having whitespace at the beginning or end of the element alias [#62058](https://github.com/saltstack/salt/issues/62058)
- Fix ordering of args to libcloud_storage.download_object module [#62074](https://github.com/saltstack/salt/issues/62074)
- Ignore extend declarations in sls files that are excluded. [#62082](https://github.com/saltstack/salt/issues/62082)
- Remove leftover usage of impacket [#62101](https://github.com/saltstack/salt/issues/62101)
- Pass executable path from _get_path_exec() is used when calling the program.
  The $HOME env is no longer modified globally.
  Only trailing newlines are stripped from the fetched secret.
  Pass process arguments are handled in a secure way. [#62120](https://github.com/saltstack/salt/issues/62120)
- Ignore some command return codes in openbsdrcctl_service to prevent spurious errors [#62131](https://github.com/saltstack/salt/issues/62131)
- Fixed extra period in filename output in tls module. Instead of "server.crt." it will now be "server.crt". [#62139](https://github.com/saltstack/salt/issues/62139)
- Make sure lingering PAexec-*.exe files in the Windows directory are cleaned up [#62152](https://github.com/saltstack/salt/issues/62152)
- Restored Salt's DeprecationWarnings [#62185](https://github.com/saltstack/salt/issues/62185)
- Fixed issue with forward slashes on Windows with file.recurse and clean=True [#62197](https://github.com/saltstack/salt/issues/62197)
- Recognize OSMC as Debian-based [#62198](https://github.com/saltstack/salt/issues/62198)
- Fixed Zypper module failing on RPM lock file being temporarily unavailable. [#62204](https://github.com/saltstack/salt/issues/62204)
- Improved error handling and diagnostics in the proxmox salt-cloud driver [#62211](https://github.com/saltstack/salt/issues/62211)
- Added EndeavourOS to the Arch os_family. [#62220](https://github.com/saltstack/salt/issues/62220)
- Fix salt-ssh not detecting `platform-python` as a valid interpreter on EL8 [#62235](https://github.com/saltstack/salt/issues/62235)
- Fix pkg.version_cmp on openEuler and a few other os flavors. [#62248](https://github.com/saltstack/salt/issues/62248)
- Fix localhost detection in glusterfs.peers [#62273](https://github.com/saltstack/salt/issues/62273)
- Fix Salt Package Manager (SPM) exception when calling spm create_repo . [#62281](https://github.com/saltstack/salt/issues/62281)
- Fix matcher slowness due to loader invocation [#62283](https://github.com/saltstack/salt/issues/62283)
- Fixes the Puppet module for non-aio Puppet packages for example running the Puppet module on FreeBSD. [#62323](https://github.com/saltstack/salt/issues/62323)
- Issue 62334: Displays a debug log message instead of an error log message when the publisher fails to connect [#62334](https://github.com/saltstack/salt/issues/62334)
- Fix pyobjects renderer access to opts and sls [#62336](https://github.com/saltstack/salt/issues/62336)
- Fix use of random shuffle and sample functions as Jinja filters [#62372](https://github.com/saltstack/salt/issues/62372)
- Fix groups with duplicate GIDs are not returned by get_group_list [#62377](https://github.com/saltstack/salt/issues/62377)
- Fix the "zpool.present" state when enabling zpool features that are already active. [#62390](https://github.com/saltstack/salt/issues/62390)
- Fix ability to execute remote file client methods in saltcheck [#62398](https://github.com/saltstack/salt/issues/62398)
- Update all platforms to use pycparser 2.21 or greater for Py 3.9 or higher, fixes fips fault with openssl v3.x [#62400](https://github.com/saltstack/salt/issues/62400)
- Due to changes in the Netmiko library for the exception paths, need to check the version of Netmiko python library and then import the exceptions from different locations depending on the result. [#62405](https://github.com/saltstack/salt/issues/62405)
- When using preq on a state, then prereq state will first be run with test=True to determine if there are changes.  When there are changes, the state with the prereq option will be run prior to the prereq state.  If this state fails then the prereq state will not run and the state output uses the test=True run.  However, the proposed changes are included for the prereq state are included from the test=True run.  We should pull those out as there weren't actually changes since the prereq state did not run. [#62408](https://github.com/saltstack/salt/issues/62408)
- Added directory mode for file.copy with makedirs [#62426](https://github.com/saltstack/salt/issues/62426)
- Provide better error handling in the various napalm proxy minion functions when the device is not accessible. [#62435](https://github.com/saltstack/salt/issues/62435)
- When handling aggregation, change the order to ensure that the requisites are aggregated first and then the state functions are aggregated.  Caching whether aggregate functions are available for particular states so we don't need to attempt to load them everytime. [#62439](https://github.com/saltstack/salt/issues/62439)
- The patch allows to boostrap kubernetes clusters in the version above 1.13 via salt module [#62451](https://github.com/saltstack/salt/issues/62451)
- sysctl.persist now updates the in-memory value on FreeBSD even if the on-disk value was already correct. [#62461](https://github.com/saltstack/salt/issues/62461)
- Fixed parsing CDROM apt sources [#62474](https://github.com/saltstack/salt/issues/62474)
- Update sanitizing masking for Salt SSH to include additional password like strings. [#62483](https://github.com/saltstack/salt/issues/62483)
- Fix user/group checking on file state functions in the test mode. [#62499](https://github.com/saltstack/salt/issues/62499)
- Fix user.present to allow removing groups using optional_groups parameter and enforcing idempotent group membership. [#62502](https://github.com/saltstack/salt/issues/62502)
- Fix possible tracebacks if there is a package with '------' or '======' in the description is installed on the Debian based minion. [#62519](https://github.com/saltstack/salt/issues/62519)
- Fixed the omitted "pool" parameter when cloning a VM with the proxmox salt-cloud driver [#62521](https://github.com/saltstack/salt/issues/62521)
- Fix rendering of pyobjects states in saltcheck [#62523](https://github.com/saltstack/salt/issues/62523)
- Fixes pillar where a corrupted CacheDisk file forces the pillar to be rebuilt [#62527](https://github.com/saltstack/salt/issues/62527)
- Use str() method instead of repo_line for when python3-apt is installed or not in aptpkg.py. [#62546](https://github.com/saltstack/salt/issues/62546)
- Remove the connection_timeout from netmiko_connection_args before netmiko_connection_args is added to __context__["netmiko_device"]["args"] which is passed along to the Netmiko library. [#62547](https://github.com/saltstack/salt/issues/62547)
- Fix order specific mount.mounted options for persist [#62556](https://github.com/saltstack/salt/issues/62556)
- Fixed salt-cloud cloning a proxmox VM with a specified new vmid. [#62558](https://github.com/saltstack/salt/issues/62558)
- Fix runas with cmd module when using the onedir bundled packages [#62565](https://github.com/saltstack/salt/issues/62565)
- Update setproctitle version for all platforms [#62576](https://github.com/saltstack/salt/issues/62576)
- Fixed missing parameters when cloning a VM with the proxmox salt-cloud driver [#62580](https://github.com/saltstack/salt/issues/62580)
- Handle PermissionError when importing crypt when FIPS is enabled. [#62587](https://github.com/saltstack/salt/issues/62587)
- Correctly reraise exceptions in states.http [#62595](https://github.com/saltstack/salt/issues/62595)
- Fixed syndic eauth. Now jobs will be published when a valid eauth user is targeting allowed minions/functions. [#62618](https://github.com/saltstack/salt/issues/62618)
- updated rest_cherry/app to properly detect arg sent as a string as curl will do when only one arg is supplied. [#62624](https://github.com/saltstack/salt/issues/62624)
- Prevent possible tracebacks in core grains module by ignoring non utf8 characters in /proc/1/environ, /proc/1/cmdline, /proc/cmdline [#62633](https://github.com/saltstack/salt/issues/62633)
- Fixed vault ext pillar return data for KV v2 [#62651](https://github.com/saltstack/salt/issues/62651)
- Fix saltcheck _get_top_states doesn't pass saltenv to state.show_top [#62654](https://github.com/saltstack/salt/issues/62654)
- Fix groupadd.* functions hard code relative command name [#62657](https://github.com/saltstack/salt/issues/62657)
- Fixed pdbedit.create trying to use a bytes-like hash as string. [#62670](https://github.com/saltstack/salt/issues/62670)
- Fix depenency on legacy boto module in boto3 modules [#62672](https://github.com/saltstack/salt/issues/62672)
- Modified "_get_flags" function so that it returns regex flags instead of integers [#62676](https://github.com/saltstack/salt/issues/62676)
- Change startup ReqServer log messages from error to info level. [#62728](https://github.com/saltstack/salt/issues/62728)
- Fix kmod.* functions hard code relative command name [#62772](https://github.com/saltstack/salt/issues/62772)
- Fix mac_brew_pkg to work with null taps [#62793](https://github.com/saltstack/salt/issues/62793)
- Fixing a bug when listing the running schedule if "schedule.enable" and/or "schedule.disable" has been run, where the "enabled" items is being treated as a schedule item. [#62795](https://github.com/saltstack/salt/issues/62795)
- Prevent annoying RuntimeWarning message about line buffering (buffering=1) not being supported in binary mode [#62817](https://github.com/saltstack/salt/issues/62817)
- Include UID and GID checks in modules.file.check_perms as well as comparing
  ownership by username and group name. [#62818](https://github.com/saltstack/salt/issues/62818)
- Fix presence events on TCP transport by removing a client's presence when minion disconnects from publish channel correctly [#62826](https://github.com/saltstack/salt/issues/62826)
- Remove Azure deprecation messages from functions that always run w/ salt-cloud [#62845](https://github.com/saltstack/salt/issues/62845)
- Use select instead of iterating over entrypoints as a dictionary for importlib_metadata>=5.0.0 [#62854](https://github.com/saltstack/salt/issues/62854)
- Fixed master job scheduler using when [#62858](https://github.com/saltstack/salt/issues/62858)
- LGPO: Added support for missing domain controller policies: VulnerableChannelAllowList and LdapEnforceChannelBinding [#62873](https://github.com/saltstack/salt/issues/62873)
- Fix unnecessarily complex gce metadata grains code to use googles metadata service more effectively. [#62878](https://github.com/saltstack/salt/issues/62878)
- Fixed dockermod version_info function for docker-py 6.0.0+ [#62882](https://github.com/saltstack/salt/issues/62882)
- Moving setting the LOAD_BALANCING_POLICY_MAP dictionary into the try except block that determines if the cassandra_cql module should be made available. [#62886](https://github.com/saltstack/salt/issues/62886)
- Updating various MongoDB module functions to work with latest version of pymongo. [#62900](https://github.com/saltstack/salt/issues/62900)
- Restored channel for Syndic minions to send job returns to the Salt master. [#62933](https://github.com/saltstack/salt/issues/62933)
- removed _resolve_deps as it required a library that is not generally avalible. and switched to apt-get for everything as that can auto resolve dependencies. [#62934](https://github.com/saltstack/salt/issues/62934)
- Updated pyzmq to version 22.0.3 on Windows builds because the old version was causing salt-minion/salt-call to hang [#62937](https://github.com/saltstack/salt/issues/62937)
- Allow root user to modify crontab lines for non-root users (except AIX and Solaris). Align crontab line changes with the file ones and also with listing crontab. [#62940](https://github.com/saltstack/salt/issues/62940)
- Fix systemd_service.* functions hard code relative command name [#62942](https://github.com/saltstack/salt/issues/62942)
- Fix file.symlink backupname operation can copy remote contents to local disk [#62953](https://github.com/saltstack/salt/issues/62953)
- Issue #62968: Fix issue where cloud deployments were putting the keys in the wrong location on Windows hosts [#62968](https://github.com/saltstack/salt/issues/62968)
- Fixed gpg_passphrase issue with gpg decrypt/encrypt functions [#62977](https://github.com/saltstack/salt/issues/62977)
- Fix file.tidied FileNotFoundError [#62986](https://github.com/saltstack/salt/issues/62986)
- Fixed bug where module.wait states were detected as running legacy module.run syntax [#62988](https://github.com/saltstack/salt/issues/62988)
- Fixed issue with win_wua module where it wouldn't load if the CryptSvc was set to Manual start [#62993](https://github.com/saltstack/salt/issues/62993)
- The `__opts__` dunder dictionary is now added to the loader's `pack` if not
  already present, which makes it accessible via the
  `salt.loader.context.NamedLoaderContext` class. [#63013](https://github.com/saltstack/salt/issues/63013)
- Issue #63024: Fix issue where grains and config data were being place in the wrong location on Windows hosts [#63024](https://github.com/saltstack/salt/issues/63024)
- Fix btrfs.subvolume_snapshot command failing [#63025](https://github.com/saltstack/salt/issues/63025)
- Fix file.retention_schedule always reports changes [#63033](https://github.com/saltstack/salt/issues/63033)
- Fix mongo authentication for mongo ext_pillar and mongo returner

  This fix also include the ability to use the mongo connection string for mongo ext_pillar [#63058](https://github.com/saltstack/salt/issues/63058)
- Fixed x509.create_csr creates invalid CSR by default in the new cryptography x509 module. [#63103](https://github.com/saltstack/salt/issues/63103)
- TCP transport documentation now contains proper master/minion-side filtering information [#63120](https://github.com/saltstack/salt/issues/63120)
- Fixed gpg.verify does not respect gnupghome [#63145](https://github.com/saltstack/salt/issues/63145)
- Made pillar cache pass extra minion data as well [#63208](https://github.com/saltstack/salt/issues/63208)
- Fix serious performance issues with the file.tidied module [#63231](https://github.com/saltstack/salt/issues/63231)
- Fix rpm_lowpkg version comparison logic when using rpm-vercmp and only one version has a release number. [#63317](https://github.com/saltstack/salt/issues/63317)
- Import StrictVersion and LooseVersion from setuptools.distutils.verison or setuptools._distutils.version, if first not available [#63350](https://github.com/saltstack/salt/issues/63350)
- When the shell is passed as powershell or pwsh, only wrapper the shell in quotes if cmd.run is running on Windows.  When quoted on Linux hosts, this results in an error when the keyword arguments are appended. [#63590](https://github.com/saltstack/salt/issues/63590)
- LGPO: Added support for "Relax minimum password length limits" [#63596](https://github.com/saltstack/salt/issues/63596)
- When a job is disabled only increase it's _next_fire_time value if the job would have run at the current time, eg. the current _next_fire_time == now. [#63699](https://github.com/saltstack/salt/issues/63699)
- Check file is not empty before attempting to read pillar disk cache file [#63729](https://github.com/saltstack/salt/issues/63729)
- fix cherrypy 400 error output to be less generic. [#63835](https://github.com/saltstack/salt/issues/63835)
- remove eval and update logging to be more informative on bad config [#63879](https://github.com/saltstack/salt/issues/63879)

# Added

- Introduce a `LIB_STATE_DIR` syspaths variable which defaults to `CONFIG_DIR`,
  but can be individually customized during installation by specifying
  `--salt-lib-state-dir` during installation. Change the default `pki_dir` to
  `<LIB_STATE_DIR>/pki/master` (for the master) and `<LIB_STATE_DIR>/pki/minion`
  (for the minion). [#3396](https://github.com/saltstack/salt/issues/3396)
- Allow users to enable 'queue=True' for all state runs via config file [#31468](https://github.com/saltstack/salt/issues/31468)
- Added pillar templating to vault policies [#43287](https://github.com/saltstack/salt/issues/43287)
- Add support for NVMeF as a transport protocol for hosts in a Pure Storage FlashArray [#51088](https://github.com/saltstack/salt/issues/51088)
- A new salt-ssh roster that generates a roster by parses a known_hosts file. [#54679](https://github.com/saltstack/salt/issues/54679)
- Added Windows Event Viewer support [#54713](https://github.com/saltstack/salt/issues/54713)
- Added the win_lgpo_reg state and execution modules which will allow registry based group policy to be set directly in the Registry.pol file [#56013](https://github.com/saltstack/salt/issues/56013)
- Added resource tagging functions to boto_dynamodb execution module [#57500](https://github.com/saltstack/salt/issues/57500)
- Added `openvswitch_db` state module and functions `bridge_to_parent`,
  `bridge_to_vlan`, `db_get`, and `db_set` to the `openvswitch` execution module.
  Also added optional `parent` and `vlan` parameters to the
  `openvswitch_bridge.present` state module function and the
  `openvswitch.bridge_create` execution module function. [#58986](https://github.com/saltstack/salt/issues/58986)
- State module to manage SysFS attributes [#60154](https://github.com/saltstack/salt/issues/60154)
- Added ability for `salt.wait_for_event` to handle `event_id`s that have a list value. [#60430](https://github.com/saltstack/salt/issues/60430)
- Added suport for Linux ppc64le core grains (cpu_model, virtual, productname, manufacturer, serialnumber) and arm core grains (serialnumber, productname) [#60518](https://github.com/saltstack/salt/issues/60518)
- Added autostart option to virt.defined and virt.running states, along with virt.update execution modules. [#60700](https://github.com/saltstack/salt/issues/60700)
- Added .0 back to our versioning scheme for future versions (e.g. 3006.0) [#60722](https://github.com/saltstack/salt/issues/60722)
- Initial work to allow parallel startup of proxy minions when used as sub proxies with Deltaproxy. [#61153](https://github.com/saltstack/salt/issues/61153)
- Added node label support for GCE [#61245](https://github.com/saltstack/salt/issues/61245)
- Support the --priority flag when adding sources to Chocolatey. [#61319](https://github.com/saltstack/salt/issues/61319)
- Add namespace option to ext_pillar.http_json [#61335](https://github.com/saltstack/salt/issues/61335)
- Added a filter function to ps module to get a list of processes on a minion according to their state. [#61420](https://github.com/saltstack/salt/issues/61420)
- Add postgres.timeout option to postgres module for limiting postgres query times [#61433](https://github.com/saltstack/salt/issues/61433)
- Added new optional vault option, ``config_location``. This can be either ``master`` or ``local`` and defines where vault will look for connection details, either requesting them from the master or using the local config. [#61857](https://github.com/saltstack/salt/issues/61857)
- Add ipwrap() jinja filter to wrap IPv6 addresses with brackets. [#61931](https://github.com/saltstack/salt/issues/61931)
- 'tcp' transport is now available in ipv6-only network [#62009](https://github.com/saltstack/salt/issues/62009)
- Add `diff_attr` parameter to pkg.upgrade() (zypper/yum). [#62031](https://github.com/saltstack/salt/issues/62031)
- Config option pass_variable_prefix allows to distinguish variables that contain paths to pass secrets.
  Config option pass_strict_fetch allows to error out when a secret cannot be fetched from pass.
  Config option pass_dir allows setting the PASSWORD_STORE_DIR env for pass.
  Config option pass_gnupghome allows setting the $GNUPGHOME env for pass. [#62120](https://github.com/saltstack/salt/issues/62120)
- Add file.pruned state and expanded file.rmdir exec module functionality [#62178](https://github.com/saltstack/salt/issues/62178)
- Added "dig.PTR" function to resolve PTR records for IPs, as well as tests and documentation [#62275](https://github.com/saltstack/salt/issues/62275)
- Added the ability to remove a KB using the DISM state/execution modules [#62366](https://github.com/saltstack/salt/issues/62366)
- Add "<tiamat> python" subcommand to allow execution or arbitrary scripts via bundled Python runtime [#62381](https://github.com/saltstack/salt/issues/62381)
- Add ability to provide conditions which convert normal state actions to no-op when true [#62446](https://github.com/saltstack/salt/issues/62446)
- Added debug log messages displaying the command being run when installing packages on Windows [#62480](https://github.com/saltstack/salt/issues/62480)
- Add biosvendor grain [#62496](https://github.com/saltstack/salt/issues/62496)
- Add ifelse Jinja function as found in CFEngine [#62508](https://github.com/saltstack/salt/issues/62508)
- Implementation of Amazon EC2 instance detection and setting `virtual_subtype` grain accordingly including the product if possible to identify. [#62539](https://github.com/saltstack/salt/issues/62539)
- Adds __env__substitution to ext_pillar.stack; followup of #61531, improved exception handling for stacked template (jinja) template rendering and yaml parsing in ext_pillar.stack [#62578](https://github.com/saltstack/salt/issues/62578)
- Increase file.tidied flexibility with regard to age and size [#62678](https://github.com/saltstack/salt/issues/62678)
- Added "connected_devices" feature to netbox pillar module. It contains extra information about devices connected to the minion [#62761](https://github.com/saltstack/salt/issues/62761)
- Add atomic file operation for symlink changes [#62768](https://github.com/saltstack/salt/issues/62768)
- Add password/account locking/unlocking in user.present state on supported operating systems [#62856](https://github.com/saltstack/salt/issues/62856)
- Added onchange configuration for script engine [#62867](https://github.com/saltstack/salt/issues/62867)
- Added output and bare functionality to export_key gpg module function [#62978](https://github.com/saltstack/salt/issues/62978)
- Add keyvalue serializer for environment files [#62983](https://github.com/saltstack/salt/issues/62983)
- Add ability to ignore symlinks in file.tidied [#63042](https://github.com/saltstack/salt/issues/63042)
- salt-cloud support IMDSv2 tokens when using 'use-instance-role-credentials' [#63067](https://github.com/saltstack/salt/issues/63067)
- Add ability for file.symlink to not set ownership on existing links [#63093](https://github.com/saltstack/salt/issues/63093)
- Restore the previous slack engine and deprecate it, rename replace the slack engine to slack_bolt until deprecation [#63095](https://github.com/saltstack/salt/issues/63095)
- Add functions that will return the underlying block device, mount point, and filesystem type for a given path [#63098](https://github.com/saltstack/salt/issues/63098)
- Add ethtool execution and state module functions for pause [#63128](https://github.com/saltstack/salt/issues/63128)
- Add boardname grain [#63131](https://github.com/saltstack/salt/issues/63131)
- Added management of ECDSA/EdDSA private keys with x509 modules in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#63248](https://github.com/saltstack/salt/issues/63248)
- Added x509 modules support for different output formats in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#63249](https://github.com/saltstack/salt/issues/63249)
- Added deprecation_warning test state for ensuring that deprecation warnings are correctly emitted. [#63315](https://github.com/saltstack/salt/issues/63315)
- Adds a state_events option to state.highstate, state.apply, state.sls, state.sls_id.
  This allows users to enable state_events on a per use basis rather than having to
  enable them globally for all state runs. [#63316](https://github.com/saltstack/salt/issues/63316)
- Allow max queue size setting for state runs to prevent performance problems from queue growth [#63356](https://github.com/saltstack/salt/issues/63356)
- Add support of exposing meta_server_grains for Azure VMs [#63606](https://github.com/saltstack/salt/issues/63606)
- Include the version of `relenv` in the versions report. [#63827](https://github.com/saltstack/salt/issues/63827)
- Added debug log messages displaying the command being run when removing packages on Windows [#63866](https://github.com/saltstack/salt/issues/63866)


* Wed Mar 01 2023 Salt Project Packaging <saltproject-packaging@vmware.com> - 3006.0~rc1

# Removed

- Remove and deprecate the __orchestration__ key from salt.runner and salt.wheel return data. To get it back, set features.enable_deprecated_orchestration_flag master configuration option to True. The flag will be completely removed in Salt 3008 Argon. [#59917](https://github.com/saltstack/salt/issues/59917)
- Removed distutils and replaced with setuptools, given distutils is deprecated and removed in Python 3.12 [#60476](https://github.com/saltstack/salt/issues/60476)
- Removed ``runtests`` targets from ``noxfile.py`` [#62239](https://github.com/saltstack/salt/issues/62239)
- Removed the PyObjC dependency.

  This addresses problems with building a one dir build for macOS.
  It became problematic because depending on the macOS version, it pulls different dependencies, and we would either have to build a macos onedir for each macOS supported release, or ship a crippled onedir(because it would be tied to the macOS version where the onedir was built).
  Since it's currently not being used, it's removed. [#62432](https://github.com/saltstack/salt/issues/62432)

# Deprecated

- renamed `keep_jobs`, specifying job cache TTL in hours, to `keep_jobs_seconds`, specifying TTL in seconds.
  `keep_jobs` will be removed in the Argon release [#55295](https://github.com/saltstack/salt/issues/55295)
- Removing all references to napalm-base which is no longer supported. [#61542](https://github.com/saltstack/salt/issues/61542)
- The 'ip_bracket' function has been moved from salt/utils/zeromq.py in salt/utils/network.py [#62009](https://github.com/saltstack/salt/issues/62009)
- The `expand_repo_def` function in `salt.modules.aptpkg` is now deprecated. It's only used in `salt.states.pkgrepo` and it has no use of being exposed to the CLI. [#62485](https://github.com/saltstack/salt/issues/62485)
- Deprecated defunct Django returner [#62644](https://github.com/saltstack/salt/issues/62644)
- Deprecate core ESXi and associated states and modules, vcenter and vsphere support in favor of Salt VMware Extensions [#62754](https://github.com/saltstack/salt/issues/62754)
- Removing manufacture grain which has been deprecated. [#62914](https://github.com/saltstack/salt/issues/62914)
- Removing deprecated utils/boto3_elasticsearch.py [#62915](https://github.com/saltstack/salt/issues/62915)
- Removing support for the now deprecated _ext_nodes from salt/master.py. [#62917](https://github.com/saltstack/salt/issues/62917)
- Deprecating the Salt Slack engine in favor of the Salt Slack Bolt Engine. [#63095](https://github.com/saltstack/salt/issues/63095)
- `salt.utils.version.StrictVersion` is now deprecated and it's use should be replaced with `salt.utils.version.Version`. [#63383](https://github.com/saltstack/salt/issues/63383)

# Changed

- More intelligent diffing in changes of file.serialize state. [#48609](https://github.com/saltstack/salt/issues/48609)
- Move deprecation of the neutron module to Argon. Please migrate to the neutronng module instead. [#49430](https://github.com/saltstack/salt/issues/49430)
- ``umask`` is now a global state argument, instead of only applying to ``cmd``
  states. [#57803](https://github.com/saltstack/salt/issues/57803)
- Update pillar.obfuscate to accept kwargs in addition to args.  This is useful when passing in keyword arguments like saltenv that are then passed along to pillar.items. [#58971](https://github.com/saltstack/salt/issues/58971)
- Improve support for listing macOS brew casks [#59439](https://github.com/saltstack/salt/issues/59439)
- Add missing MariaDB Grants to mysql module.
  MariaDB has added some grants in 10.4.x and 10.5.x that are not present here, which results in an error when creating.
  Also improved exception handling in `grant_add` which did not log the original error message and replaced it with a generic error. [#61409](https://github.com/saltstack/salt/issues/61409)
- Use VENV_PIP_TARGET environment variable as a default target for pip if present. [#62089](https://github.com/saltstack/salt/issues/62089)
- Disabled FQDNs grains on macOS by default [#62168](https://github.com/saltstack/salt/issues/62168)
- Replaced pyroute2.IPDB with pyroute2.NDB, as the former is deprecated [#62218](https://github.com/saltstack/salt/issues/62218)
- Enhance capture of error messages for Zypper calls in zypperpkg module. [#62346](https://github.com/saltstack/salt/issues/62346)
- Removed GPG_1_3_1 check [#62895](https://github.com/saltstack/salt/issues/62895)
- Requisite state chunks now all consistently contain `__id__`, `__sls__` and `name`. [#63012](https://github.com/saltstack/salt/issues/63012)
- netapi_enable_clients option to allow enabling/disabling of clients in salt-api.
  By default all clients will now be disabled. Users of salt-api will need
  to update their master config to enable the clients that they use. Not adding
  the netapi_enable_clients option with required clients to the master config will
  disable salt-api. [#63050](https://github.com/saltstack/salt/issues/63050)
- Stop relying on `salt/_version.py` to write Salt's version. Instead use `salt/_version.txt` which only contains the version string. [#63383](https://github.com/saltstack/salt/issues/63383)
- Set enable_fqdns_grains to be False by default. [#63595](https://github.com/saltstack/salt/issues/63595)
- Changelog snippet files must now have a `.md` file extension to be more explicit on what type of rendering is done when they are included in the main `CHANGELOG.md` file. [#63710](https://github.com/saltstack/salt/issues/63710)

# Fixed

- Add kwargs to handle extra parameters for http.query [#36138](https://github.com/saltstack/salt/issues/36138)
- Fix mounted bind mounts getting active mount options added [#39292](https://github.com/saltstack/salt/issues/39292)
- Fix `sysctl.present` converts spaces to tabs. [#40054](https://github.com/saltstack/salt/issues/40054)
- Fixes state pkg.purged to purge removed packages on Debian family systems [#42306](https://github.com/saltstack/salt/issues/42306)
- Fix fun_args missing from syndic returns [#45823](https://github.com/saltstack/salt/issues/45823)
- Fix mount.mounted with 'mount: False' reports unmounted file system as unchanged when running with test=True [#47201](https://github.com/saltstack/salt/issues/47201)
- Issue #49310: Allow users to touch a file with Unix date of birth [#49310](https://github.com/saltstack/salt/issues/49310)
- Do not raise an exception in pkg.info_installed on nonzero return code [#51620](https://github.com/saltstack/salt/issues/51620)
- Passes the value of the force parameter from file.copy to its call to file.remove so that files with the read-only attribute are handled. [#51739](https://github.com/saltstack/salt/issues/51739)
- Fixed x509.certificate_managed creates new certificate every run in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#52167](https://github.com/saltstack/salt/issues/52167)
- Don't check for cached pillar errors on state.apply [#52354](https://github.com/saltstack/salt/issues/52354), [#57180](https://github.com/saltstack/salt/issues/57180), [#59339](https://github.com/saltstack/salt/issues/59339)
- Swapping out args and kwargs for arg and kwarg respectively in the Slack engine when the command passed is a runner. [#52400](https://github.com/saltstack/salt/issues/52400)
- Ensure when we're adding chunks to the rules when running aggregation with the iptables state module we use a copy of the chunk otherwise we end up with a recursive mess. [#53353](https://github.com/saltstack/salt/issues/53353)
- When user_create or user_remove fail, return False instead of returning the error. [#53377](https://github.com/saltstack/salt/issues/53377)
- Include sync_roster when sync_all is called. [#53914](https://github.com/saltstack/salt/issues/53914)
- Avoid warning noise in lograte.get [#53988](https://github.com/saltstack/salt/issues/53988)
- Fixed listing revoked keys with gpg.list_keys [#54347](https://github.com/saltstack/salt/issues/54347)
- Fix mount.mounted does not handle blanks properly [#54508](https://github.com/saltstack/salt/issues/54508)
- Fixed grain num_cpus get wrong CPUs count in case of inconsistent CPU numbering. [#54682](https://github.com/saltstack/salt/issues/54682)
- Fix spelling error for python_shell argument in dpkg_lower module [#54907](https://github.com/saltstack/salt/issues/54907)
- Cleaned up bytes response data before sending to non-bytes compatible returners (postgres, mysql) [#55226](https://github.com/saltstack/salt/issues/55226)
- Fixed malformed state return when testing file.managed with unavailable source file [#55269](https://github.com/saltstack/salt/issues/55269)
- Included stdout in error message for Zypper calls in zypperpkg module. [#56016](https://github.com/saltstack/salt/issues/56016)
- Fixed pillar.filter_by with salt-ssh [#56093](https://github.com/saltstack/salt/issues/56093)
- Fix boto_route53 issue with (multiple) VPCs. [#57139](https://github.com/saltstack/salt/issues/57139)
- Remove log from mine runner which was not used. [#57463](https://github.com/saltstack/salt/issues/57463)
- Fixed x509.read_certificate error when reading a Microsoft CA issued certificate in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#57535](https://github.com/saltstack/salt/issues/57535)
- Updating Slack engine to use slack_bolt library. [#57842](https://github.com/saltstack/salt/issues/57842)
- Fixed warning about replace=True with x509.certificate_managed in the new cryptography x509 module. [#58165](https://github.com/saltstack/salt/issues/58165)
- Fix salt.modules.pip:is_installed doesn't handle locally installed packages [#58202](https://github.com/saltstack/salt/issues/58202)
- Add missing MariaDB Grants to mysql module. MariaDB has added some grants in 10.4.x and 10.5.x that are not present here, which results in an error when creating. [#58297](https://github.com/saltstack/salt/issues/58297)
- linux_shadow: Fix cases where malformed shadow entries cause `user.present`
  states to fail. [#58423](https://github.com/saltstack/salt/issues/58423)
- Fixed salt.utils.compat.cmp to work with dictionaries [#58729](https://github.com/saltstack/salt/issues/58729)
- Fixed formatting for terse output mode [#58953](https://github.com/saltstack/salt/issues/58953)
- Fixed RecursiveDictDiffer with added nested dicts [#59017](https://github.com/saltstack/salt/issues/59017)
- Fixed x509.certificate_managed has DoS effect on master in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#59169](https://github.com/saltstack/salt/issues/59169)
- Fixed saltnado websockets disconnecting immediately [#59183](https://github.com/saltstack/salt/issues/59183)
- Fixed x509.certificate_managed rolls certificates every now and then in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#59315](https://github.com/saltstack/salt/issues/59315)
- Fix postgres_privileges.present not idempotent for functions [#59585](https://github.com/saltstack/salt/issues/59585)
- Fixed influxdb_continuous_query.present state to provide the client args to the underlying module on create. [#59766](https://github.com/saltstack/salt/issues/59766)
- Warn when using insecure (http:// based) key_urls for apt-based systems in pkgrepo.managed, and add a kwarg that determines the validity of such a url. [#59786](https://github.com/saltstack/salt/issues/59786)
- add load balancing policy default option and ensure the module can be executed with arguments from CLI [#59909](https://github.com/saltstack/salt/issues/59909)
- Fix salt-ssh when using imports with extra-filerefs. [#60003](https://github.com/saltstack/salt/issues/60003)
- Fixed cache directory corruption startup error [#60170](https://github.com/saltstack/salt/issues/60170)
- Update docs remove dry_run in docstring of file.blockreplace state. [#60227](https://github.com/saltstack/salt/issues/60227)
- Adds Parrot to OS_Family_Map in grains. [#60249](https://github.com/saltstack/salt/issues/60249)
- Fixed stdout and stderr being empty sometimes when use_vt=True for the cmd.run[*] functions [#60365](https://github.com/saltstack/salt/issues/60365)
- Use return code in iptables --check to verify rule exists. [#60467](https://github.com/saltstack/salt/issues/60467)
- Fix regression pip.installed does not pass env_vars when calling pip.list [#60557](https://github.com/saltstack/salt/issues/60557)
- Fix xfs module when additional output included in mkfs.xfs command. [#60853](https://github.com/saltstack/salt/issues/60853)
- Fixed parsing new format of terraform states in roster.terraform [#60915](https://github.com/saltstack/salt/issues/60915)
- Fixed recognizing installed ARMv7 rpm packages in compatible architectures. [#60994](https://github.com/saltstack/salt/issues/60994)
- Fixing changes dict in pkg state to be consistent when installing and test=True. [#60995](https://github.com/saltstack/salt/issues/60995)
- Fix cron.present duplicating entries when changing timespec to special. [#60997](https://github.com/saltstack/salt/issues/60997)
- Made salt-ssh respect --wipe again [#61083](https://github.com/saltstack/salt/issues/61083)
- state.orchestrate_single only passes a pillar if it is set to the state
  function. This allows it to be used with state functions that don't accept a
  pillar keyword argument. [#61092](https://github.com/saltstack/salt/issues/61092)
- Fix ipset state when the comment kwarg is set. [#61122](https://github.com/saltstack/salt/issues/61122)
- Fix issue with archive.unzip where the password was not being encoded for the extract function [#61422](https://github.com/saltstack/salt/issues/61422)
- Some Linux distributions (like AlmaLinux, Astra Linux, Debian, Mendel, Linux
  Mint, Pop!_OS, Rocky Linux) report different `oscodename`, `osfullname`,
  `osfinger` grains if lsb-release is installed or not. They have been changed to
  only derive these OS grains from `/etc/os-release`. [#61618](https://github.com/saltstack/salt/issues/61618)
- Pop!_OS uses the full version (YY.MM) in the osfinger grain now, not just the year. This allows differentiating for example between 20.04 and 20.10. [#61619](https://github.com/saltstack/salt/issues/61619)
- Fix ssh config roster to correctly parse the ssh config files that contain spaces. [#61650](https://github.com/saltstack/salt/issues/61650)
- Fix SoftLayer configuration not raising an exception when a domain is missing [#61727](https://github.com/saltstack/salt/issues/61727)
- Allow the minion to start or salt-call to run even if the user doesn't have permissions to read the root_dir value from the registry [#61789](https://github.com/saltstack/salt/issues/61789)
- Need to move the creation of the proxy object for the ProxyMinion further down in the initialization for sub proxies to ensure that all modules, especially any custom proxy modules, are available before attempting to run the init function. [#61805](https://github.com/saltstack/salt/issues/61805)
- Fixed malformed state return when merge-serializing to an improperly formatted file [#61814](https://github.com/saltstack/salt/issues/61814)
- Made cmdmod._run[_all]_quiet work during minion startup on MacOS with runas specified (which fixed mac_service) [#61816](https://github.com/saltstack/salt/issues/61816)
- When deleting the vault cache, also delete from the session cache [#61821](https://github.com/saltstack/salt/issues/61821)
- Ignore errors on reading license info with dpkg_lowpkg to prevent tracebacks on getting package information. [#61827](https://github.com/saltstack/salt/issues/61827)
- win_lgpo: Display conflicting policy names when more than one policy is found [#61859](https://github.com/saltstack/salt/issues/61859)
- win_lgpo: Fixed intermittent KeyError when getting policy setting using lgpo.get_policy [#61860](https://github.com/saltstack/salt/issues/61860)
- Fixed listing minions on OpenBSD [#61966](https://github.com/saltstack/salt/issues/61966)
- Make Salt to return an error on "pkg" modules and states when targeting duplicated package names [#62019](https://github.com/saltstack/salt/issues/62019)
- Fix return of REST-returned permissions when auth_list is set [#62022](https://github.com/saltstack/salt/issues/62022)
- Normalize package names once on using pkg.installed/removed with yum to make it possible to install packages with the name containing a part similar to a name of architecture. [#62029](https://github.com/saltstack/salt/issues/62029)
- Fix inconsitency regarding name and pkgs parameters between zypperpkg.upgrade() and yumpkg.upgrade() [#62030](https://github.com/saltstack/salt/issues/62030)
- Fix attr=all handling in pkg.list_pkgs() (yum/zypper). [#62032](https://github.com/saltstack/salt/issues/62032)
- Fixed the humanname being ignored in pkgrepo.managed on openSUSE Leap [#62053](https://github.com/saltstack/salt/issues/62053)
- Fixed issue with some LGPO policies having whitespace at the beginning or end of the element alias [#62058](https://github.com/saltstack/salt/issues/62058)
- Fix ordering of args to libcloud_storage.download_object module [#62074](https://github.com/saltstack/salt/issues/62074)
- Ignore extend declarations in sls files that are excluded. [#62082](https://github.com/saltstack/salt/issues/62082)
- Remove leftover usage of impacket [#62101](https://github.com/saltstack/salt/issues/62101)
- Pass executable path from _get_path_exec() is used when calling the program.
  The $HOME env is no longer modified globally.
  Only trailing newlines are stripped from the fetched secret.
  Pass process arguments are handled in a secure way. [#62120](https://github.com/saltstack/salt/issues/62120)
- Ignore some command return codes in openbsdrcctl_service to prevent spurious errors [#62131](https://github.com/saltstack/salt/issues/62131)
- Fixed extra period in filename output in tls module. Instead of "server.crt." it will now be "server.crt". [#62139](https://github.com/saltstack/salt/issues/62139)
- Make sure lingering PAexec-*.exe files in the Windows directory are cleaned up [#62152](https://github.com/saltstack/salt/issues/62152)
- Restored Salt's DeprecationWarnings [#62185](https://github.com/saltstack/salt/issues/62185)
- Fixed issue with forward slashes on Windows with file.recurse and clean=True [#62197](https://github.com/saltstack/salt/issues/62197)
- Recognize OSMC as Debian-based [#62198](https://github.com/saltstack/salt/issues/62198)
- Fixed Zypper module failing on RPM lock file being temporarily unavailable. [#62204](https://github.com/saltstack/salt/issues/62204)
- Improved error handling and diagnostics in the proxmox salt-cloud driver [#62211](https://github.com/saltstack/salt/issues/62211)
- Added EndeavourOS to the Arch os_family. [#62220](https://github.com/saltstack/salt/issues/62220)
- Fix salt-ssh not detecting `platform-python` as a valid interpreter on EL8 [#62235](https://github.com/saltstack/salt/issues/62235)
- Fix pkg.version_cmp on openEuler and a few other os flavors. [#62248](https://github.com/saltstack/salt/issues/62248)
- Fix localhost detection in glusterfs.peers [#62273](https://github.com/saltstack/salt/issues/62273)
- Fix Salt Package Manager (SPM) exception when calling spm create_repo . [#62281](https://github.com/saltstack/salt/issues/62281)
- Fix matcher slowness due to loader invocation [#62283](https://github.com/saltstack/salt/issues/62283)
- Fixes the Puppet module for non-aio Puppet packages for example running the Puppet module on FreeBSD. [#62323](https://github.com/saltstack/salt/issues/62323)
- Issue 62334: Displays a debug log message instead of an error log message when the publisher fails to connect [#62334](https://github.com/saltstack/salt/issues/62334)
- Fix pyobjects renderer access to opts and sls [#62336](https://github.com/saltstack/salt/issues/62336)
- Fix use of random shuffle and sample functions as Jinja filters [#62372](https://github.com/saltstack/salt/issues/62372)
- Fix groups with duplicate GIDs are not returned by get_group_list [#62377](https://github.com/saltstack/salt/issues/62377)
- Fix the "zpool.present" state when enabling zpool features that are already active. [#62390](https://github.com/saltstack/salt/issues/62390)
- Fix ability to execute remote file client methods in saltcheck [#62398](https://github.com/saltstack/salt/issues/62398)
- Update all platforms to use pycparser 2.21 or greater for Py 3.9 or higher, fixes fips fault with openssl v3.x [#62400](https://github.com/saltstack/salt/issues/62400)
- Due to changes in the Netmiko library for the exception paths, need to check the version of Netmiko python library and then import the exceptions from different locations depending on the result. [#62405](https://github.com/saltstack/salt/issues/62405)
- When using preq on a state, then prereq state will first be run with test=True to determine if there are changes.  When there are changes, the state with the prereq option will be run prior to the prereq state.  If this state fails then the prereq state will not run and the state output uses the test=True run.  However, the proposed changes are included for the prereq state are included from the test=True run.  We should pull those out as there weren't actually changes since the prereq state did not run. [#62408](https://github.com/saltstack/salt/issues/62408)
- Added directory mode for file.copy with makedirs [#62426](https://github.com/saltstack/salt/issues/62426)
- Provide better error handling in the various napalm proxy minion functions when the device is not accessible. [#62435](https://github.com/saltstack/salt/issues/62435)
- When handling aggregation, change the order to ensure that the requisites are aggregated first and then the state functions are aggregated.  Caching whether aggregate functions are available for particular states so we don't need to attempt to load them everytime. [#62439](https://github.com/saltstack/salt/issues/62439)
- The patch allows to boostrap kubernetes clusters in the version above 1.13 via salt module [#62451](https://github.com/saltstack/salt/issues/62451)
- sysctl.persist now updates the in-memory value on FreeBSD even if the on-disk value was already correct. [#62461](https://github.com/saltstack/salt/issues/62461)
- Fixed parsing CDROM apt sources [#62474](https://github.com/saltstack/salt/issues/62474)
- Update sanitizing masking for Salt SSH to include additional password like strings. [#62483](https://github.com/saltstack/salt/issues/62483)
- Fix user/group checking on file state functions in the test mode. [#62499](https://github.com/saltstack/salt/issues/62499)
- Fix user.present to allow removing groups using optional_groups parameter and enforcing idempotent group membership. [#62502](https://github.com/saltstack/salt/issues/62502)
- Fix possible tracebacks if there is a package with '------' or '======' in the description is installed on the Debian based minion. [#62519](https://github.com/saltstack/salt/issues/62519)
- Fixed the omitted "pool" parameter when cloning a VM with the proxmox salt-cloud driver [#62521](https://github.com/saltstack/salt/issues/62521)
- Fix rendering of pyobjects states in saltcheck [#62523](https://github.com/saltstack/salt/issues/62523)
- Fixes pillar where a corrupted CacheDisk file forces the pillar to be rebuilt [#62527](https://github.com/saltstack/salt/issues/62527)
- Use str() method instead of repo_line for when python3-apt is installed or not in aptpkg.py. [#62546](https://github.com/saltstack/salt/issues/62546)
- Remove the connection_timeout from netmiko_connection_args before netmiko_connection_args is added to __context__["netmiko_device"]["args"] which is passed along to the Netmiko library. [#62547](https://github.com/saltstack/salt/issues/62547)
- Fix order specific mount.mounted options for persist [#62556](https://github.com/saltstack/salt/issues/62556)
- Fixed salt-cloud cloning a proxmox VM with a specified new vmid. [#62558](https://github.com/saltstack/salt/issues/62558)
- Fix runas with cmd module when using the onedir bundled packages [#62565](https://github.com/saltstack/salt/issues/62565)
- Update setproctitle version for all platforms [#62576](https://github.com/saltstack/salt/issues/62576)
- Fixed missing parameters when cloning a VM with the proxmox salt-cloud driver [#62580](https://github.com/saltstack/salt/issues/62580)
- Handle PermissionError when importing crypt when FIPS is enabled. [#62587](https://github.com/saltstack/salt/issues/62587)
- Correctly reraise exceptions in states.http [#62595](https://github.com/saltstack/salt/issues/62595)
- Fixed syndic eauth. Now jobs will be published when a valid eauth user is targeting allowed minions/functions. [#62618](https://github.com/saltstack/salt/issues/62618)
- updated rest_cherry/app to properly detect arg sent as a string as curl will do when only one arg is supplied. [#62624](https://github.com/saltstack/salt/issues/62624)
- Prevent possible tracebacks in core grains module by ignoring non utf8 characters in /proc/1/environ, /proc/1/cmdline, /proc/cmdline [#62633](https://github.com/saltstack/salt/issues/62633)
- Fixed vault ext pillar return data for KV v2 [#62651](https://github.com/saltstack/salt/issues/62651)
- Fix saltcheck _get_top_states doesn't pass saltenv to state.show_top [#62654](https://github.com/saltstack/salt/issues/62654)
- Fix groupadd.* functions hard code relative command name [#62657](https://github.com/saltstack/salt/issues/62657)
- Fixed pdbedit.create trying to use a bytes-like hash as string. [#62670](https://github.com/saltstack/salt/issues/62670)
- Fix depenency on legacy boto module in boto3 modules [#62672](https://github.com/saltstack/salt/issues/62672)
- Modified "_get_flags" function so that it returns regex flags instead of integers [#62676](https://github.com/saltstack/salt/issues/62676)
- Change startup ReqServer log messages from error to info level. [#62728](https://github.com/saltstack/salt/issues/62728)
- Fix kmod.* functions hard code relative command name [#62772](https://github.com/saltstack/salt/issues/62772)
- Fix mac_brew_pkg to work with null taps [#62793](https://github.com/saltstack/salt/issues/62793)
- Fixing a bug when listing the running schedule if "schedule.enable" and/or "schedule.disable" has been run, where the "enabled" items is being treated as a schedule item. [#62795](https://github.com/saltstack/salt/issues/62795)
- Prevent annoying RuntimeWarning message about line buffering (buffering=1) not being supported in binary mode [#62817](https://github.com/saltstack/salt/issues/62817)
- Include UID and GID checks in modules.file.check_perms as well as comparing
  ownership by username and group name. [#62818](https://github.com/saltstack/salt/issues/62818)
- Fix presence events on TCP transport by removing a client's presence when minion disconnects from publish channel correctly [#62826](https://github.com/saltstack/salt/issues/62826)
- Remove Azure deprecation messages from functions that always run w/ salt-cloud [#62845](https://github.com/saltstack/salt/issues/62845)
- Use select instead of iterating over entrypoints as a dictionary for importlib_metadata>=5.0.0 [#62854](https://github.com/saltstack/salt/issues/62854)
- Fixed master job scheduler using when [#62858](https://github.com/saltstack/salt/issues/62858)
- LGPO: Added support for missing domain controller policies: VulnerableChannelAllowList and LdapEnforceChannelBinding [#62873](https://github.com/saltstack/salt/issues/62873)
- Fix unnecessarily complex gce metadata grains code to use googles metadata service more effectively. [#62878](https://github.com/saltstack/salt/issues/62878)
- Fixed dockermod version_info function for docker-py 6.0.0+ [#62882](https://github.com/saltstack/salt/issues/62882)
- Moving setting the LOAD_BALANCING_POLICY_MAP dictionary into the try except block that determines if the cassandra_cql module should be made available. [#62886](https://github.com/saltstack/salt/issues/62886)
- Updating various MongoDB module functions to work with latest version of pymongo. [#62900](https://github.com/saltstack/salt/issues/62900)
- Restored channel for Syndic minions to send job returns to the Salt master. [#62933](https://github.com/saltstack/salt/issues/62933)
- removed _resolve_deps as it required a library that is not generally avalible. and switched to apt-get for everything as that can auto resolve dependencies. [#62934](https://github.com/saltstack/salt/issues/62934)
- Updated pyzmq to version 22.0.3 on Windows builds because the old version was causing salt-minion/salt-call to hang [#62937](https://github.com/saltstack/salt/issues/62937)
- Allow root user to modify crontab lines for non-root users (except AIX and Solaris). Align crontab line changes with the file ones and also with listing crontab. [#62940](https://github.com/saltstack/salt/issues/62940)
- Fix systemd_service.* functions hard code relative command name [#62942](https://github.com/saltstack/salt/issues/62942)
- Fix file.symlink backupname operation can copy remote contents to local disk [#62953](https://github.com/saltstack/salt/issues/62953)
- Issue #62968: Fix issue where cloud deployments were putting the keys in the wrong location on Windows hosts [#62968](https://github.com/saltstack/salt/issues/62968)
- Fixed gpg_passphrase issue with gpg decrypt/encrypt functions [#62977](https://github.com/saltstack/salt/issues/62977)
- Fix file.tidied FileNotFoundError [#62986](https://github.com/saltstack/salt/issues/62986)
- Fixed bug where module.wait states were detected as running legacy module.run syntax [#62988](https://github.com/saltstack/salt/issues/62988)
- Fixed issue with win_wua module where it wouldn't load if the CryptSvc was set to Manual start [#62993](https://github.com/saltstack/salt/issues/62993)
- The `__opts__` dunder dictionary is now added to the loader's `pack` if not
  already present, which makes it accessible via the
  `salt.loader.context.NamedLoaderContext` class. [#63013](https://github.com/saltstack/salt/issues/63013)
- Issue #63024: Fix issue where grains and config data were being place in the wrong location on Windows hosts [#63024](https://github.com/saltstack/salt/issues/63024)
- Fix btrfs.subvolume_snapshot command failing [#63025](https://github.com/saltstack/salt/issues/63025)
- Fix file.retention_schedule always reports changes [#63033](https://github.com/saltstack/salt/issues/63033)
- Fix mongo authentication for mongo ext_pillar and mongo returner

  This fix also include the ability to use the mongo connection string for mongo ext_pillar [#63058](https://github.com/saltstack/salt/issues/63058)
- Fixed x509.create_csr creates invalid CSR by default in the new cryptography x509 module. [#63103](https://github.com/saltstack/salt/issues/63103)
- TCP transport documentation now contains proper master/minion-side filtering information [#63120](https://github.com/saltstack/salt/issues/63120)
- Fixed gpg.verify does not respect gnupghome [#63145](https://github.com/saltstack/salt/issues/63145)
- Made pillar cache pass extra minion data as well [#63208](https://github.com/saltstack/salt/issues/63208)
- Fix serious performance issues with the file.tidied module [#63231](https://github.com/saltstack/salt/issues/63231)
- Import StrictVersion and LooseVersion from setuptools.distutils.verison or setuptools._distutils.version, if first not available [#63350](https://github.com/saltstack/salt/issues/63350)
- When the shell is passed as powershell or pwsh, only wrapper the shell in quotes if cmd.run is running on Windows.  When quoted on Linux hosts, this results in an error when the keyword arguments are appended. [#63590](https://github.com/saltstack/salt/issues/63590)
- LGPO: Added support for "Relax minimum password length limits" [#63596](https://github.com/saltstack/salt/issues/63596)
- Check file is not empty before attempting to read pillar disk cache file [#63729](https://github.com/saltstack/salt/issues/63729)

# Added

- Introduce a `LIB_STATE_DIR` syspaths variable which defaults to `CONFIG_DIR`,
  but can be individually customized during installation by specifying
  `--salt-lib-state-dir` during installation. Change the default `pki_dir` to
  `<LIB_STATE_DIR>/pki/master` (for the master) and `<LIB_STATE_DIR>/pki/minion`
  (for the minion). [#3396](https://github.com/saltstack/salt/issues/3396)
- Allow users to enable 'queue=True' for all state runs via config file [#31468](https://github.com/saltstack/salt/issues/31468)
- Added pillar templating to vault policies [#43287](https://github.com/saltstack/salt/issues/43287)
- Add support for NVMeF as a transport protocol for hosts in a Pure Storage FlashArray [#51088](https://github.com/saltstack/salt/issues/51088)
- A new salt-ssh roster that generates a roster by parses a known_hosts file. [#54679](https://github.com/saltstack/salt/issues/54679)
- Added Windows Event Viewer support [#54713](https://github.com/saltstack/salt/issues/54713)
- Added the win_lgpo_reg state and execution modules which will allow registry based group policy to be set directly in the Registry.pol file [#56013](https://github.com/saltstack/salt/issues/56013)
- Added resource tagging functions to boto_dynamodb execution module [#57500](https://github.com/saltstack/salt/issues/57500)
- Added `openvswitch_db` state module and functions `bridge_to_parent`,
  `bridge_to_vlan`, `db_get`, and `db_set` to the `openvswitch` execution module.
  Also added optional `parent` and `vlan` parameters to the
  `openvswitch_bridge.present` state module function and the
  `openvswitch.bridge_create` execution module function. [#58986](https://github.com/saltstack/salt/issues/58986)
- State module to manage SysFS attributes [#60154](https://github.com/saltstack/salt/issues/60154)
- Added ability for `salt.wait_for_event` to handle `event_id`s that have a list value. [#60430](https://github.com/saltstack/salt/issues/60430)
- Added suport for Linux ppc64le core grains (cpu_model, virtual, productname, manufacturer, serialnumber) and arm core grains (serialnumber, productname) [#60518](https://github.com/saltstack/salt/issues/60518)
- Added autostart option to virt.defined and virt.running states, along with virt.update execution modules. [#60700](https://github.com/saltstack/salt/issues/60700)
- Added .0 back to our versioning scheme for future versions (e.g. 3006.0) [#60722](https://github.com/saltstack/salt/issues/60722)
- Initial work to allow parallel startup of proxy minions when used as sub proxies with Deltaproxy. [#61153](https://github.com/saltstack/salt/issues/61153)
- Added node label support for GCE [#61245](https://github.com/saltstack/salt/issues/61245)
- Support the --priority flag when adding sources to Chocolatey. [#61319](https://github.com/saltstack/salt/issues/61319)
- Add namespace option to ext_pillar.http_json [#61335](https://github.com/saltstack/salt/issues/61335)
- Added a filter function to ps module to get a list of processes on a minion according to their state. [#61420](https://github.com/saltstack/salt/issues/61420)
- Add postgres.timeout option to postgres module for limiting postgres query times [#61433](https://github.com/saltstack/salt/issues/61433)
- Added new optional vault option, ``config_location``. This can be either ``master`` or ``local`` and defines where vault will look for connection details, either requesting them from the master or using the local config. [#61857](https://github.com/saltstack/salt/issues/61857)
- Add ipwrap() jinja filter to wrap IPv6 addresses with brackets. [#61931](https://github.com/saltstack/salt/issues/61931)
- 'tcp' transport is now available in ipv6-only network [#62009](https://github.com/saltstack/salt/issues/62009)
- Add `diff_attr` parameter to pkg.upgrade() (zypper/yum). [#62031](https://github.com/saltstack/salt/issues/62031)
- Config option pass_variable_prefix allows to distinguish variables that contain paths to pass secrets.
  Config option pass_strict_fetch allows to error out when a secret cannot be fetched from pass.
  Config option pass_dir allows setting the PASSWORD_STORE_DIR env for pass.
  Config option pass_gnupghome allows setting the $GNUPGHOME env for pass. [#62120](https://github.com/saltstack/salt/issues/62120)
- Add file.pruned state and expanded file.rmdir exec module functionality [#62178](https://github.com/saltstack/salt/issues/62178)
- Added "dig.PTR" function to resolve PTR records for IPs, as well as tests and documentation [#62275](https://github.com/saltstack/salt/issues/62275)
- Added the ability to remove a KB using the DISM state/execution modules [#62366](https://github.com/saltstack/salt/issues/62366)
- Add "<tiamat> python" subcommand to allow execution or arbitrary scripts via bundled Python runtime [#62381](https://github.com/saltstack/salt/issues/62381)
- Add ability to provide conditions which convert normal state actions to no-op when true [#62446](https://github.com/saltstack/salt/issues/62446)
- Added debug log messages displaying the command being run when installing packages on Windows [#62480](https://github.com/saltstack/salt/issues/62480)
- Add biosvendor grain [#62496](https://github.com/saltstack/salt/issues/62496)
- Add ifelse Jinja function as found in CFEngine [#62508](https://github.com/saltstack/salt/issues/62508)
- Implementation of Amazon EC2 instance detection and setting `virtual_subtype` grain accordingly including the product if possible to identify. [#62539](https://github.com/saltstack/salt/issues/62539)
- Adds __env__substitution to ext_pillar.stack; followup of #61531, improved exception handling for stacked template (jinja) template rendering and yaml parsing in ext_pillar.stack [#62578](https://github.com/saltstack/salt/issues/62578)
- Increase file.tidied flexibility with regard to age and size [#62678](https://github.com/saltstack/salt/issues/62678)
- Added "connected_devices" feature to netbox pillar module. It contains extra information about devices connected to the minion [#62761](https://github.com/saltstack/salt/issues/62761)
- Add atomic file operation for symlink changes [#62768](https://github.com/saltstack/salt/issues/62768)
- Add password/account locking/unlocking in user.present state on supported operating systems [#62856](https://github.com/saltstack/salt/issues/62856)
- Added onchange configuration for script engine [#62867](https://github.com/saltstack/salt/issues/62867)
- Added output and bare functionality to export_key gpg module function [#62978](https://github.com/saltstack/salt/issues/62978)
- Add keyvalue serializer for environment files [#62983](https://github.com/saltstack/salt/issues/62983)
- Add ability to ignore symlinks in file.tidied [#63042](https://github.com/saltstack/salt/issues/63042)
- salt-cloud support IMDSv2 tokens when using 'use-instance-role-credentials' [#63067](https://github.com/saltstack/salt/issues/63067)
- Add ability for file.symlink to not set ownership on existing links [#63093](https://github.com/saltstack/salt/issues/63093)
- Restore the previous slack engine and deprecate it, rename replace the slack engine to slack_bolt until deprecation [#63095](https://github.com/saltstack/salt/issues/63095)
- Add functions that will return the underlying block device, mount point, and filesystem type for a given path [#63098](https://github.com/saltstack/salt/issues/63098)
- Add ethtool execution and state module functions for pause [#63128](https://github.com/saltstack/salt/issues/63128)
- Add boardname grain [#63131](https://github.com/saltstack/salt/issues/63131)
- Added management of ECDSA/EdDSA private keys with x509 modules in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#63248](https://github.com/saltstack/salt/issues/63248)
- Added x509 modules support for different output formats in the new cryptography x509 module. Please migrate to the new cryptography x509 module for this improvement. [#63249](https://github.com/saltstack/salt/issues/63249)
- Added deprecation_warning test state for ensuring that deprecation warnings are correctly emitted. [#63315](https://github.com/saltstack/salt/issues/63315)
- Adds a state_events option to state.highstate, state.apply, state.sls, state.sls_id.
  This allows users to enable state_events on a per use basis rather than having to
  enable them globally for all state runs. [#63316](https://github.com/saltstack/salt/issues/63316)
- Allow max queue size setting for state runs to prevent performance problems from queue growth [#63356](https://github.com/saltstack/salt/issues/63356)
- Add support of exposing meta_server_grains for Azure VMs [#63606](https://github.com/saltstack/salt/issues/63606)


* Tue Nov 01 2022 SaltStack Packaging Team <packaging@saltstack.com> - 3005-2
- Generate HMAC files post-install in case FIPS mode used only if libraries exist

* Tue Sep 27 2022 SaltStack Packaging Team <packaging@saltstack.com> - 3005-1
- Generate HMAC files post-install in case FIPS mode used
- Added MAN pages

* Fri Apr 10 2020 SaltStack Packaging Team <packaging@frogunder.com> - 3001
- Update to use pop-build

* Mon Feb 03 2020 SaltStack Packaging Team <packaging@frogunder.com> - 3000-1
- Update to feature release 3000-1  for Python 3

## - Removed Torando since salt.ext.tornado, add dependencies for Tornado

* Wed Jan 22 2020 SaltStack Packaging Team <packaging@garethgreenaway.com> - 3000.0.0rc2-1
- Update to Neon Release Candidate 2 for Python 3
- Updated spec file to not use py3_build  due to '-s' preventing pip installs
- Updated patch file to support Tornado4

* Wed Jan 08 2020 SaltStack Packaging Team <packaging@frogunder.com> - 2019.2.3-1
- Update to feature release 2019.2.3-1  for Python 3

* Tue Oct 15 2019 SaltStack Packaging Team <packaging@frogunder.com> - 2019.2.2-1
- Update to feature release 2019.2.2-1  for Python 3

* Thu Sep 12 2019 SaltStack Packaging Team <packaging@frogunder.com> - 2019.2.1-1
- Update to feature release 2019.2.1-1  for Python 3

* Tue Sep 10 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2019.2.0-10
- Support for point release, added distro as a requirement

* Tue Jul 02 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2019.2.0-9
- Support for point release, only rpmsign and tornado4 patches

* Thu Jun 06 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2019.2.0-8
- Support for Redhat 7 need for PyYAML and tornado 4 patch since Tornado < v5.x

* Thu May 23 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2019.2.0-7
- Patching in support for gpg-agent and passphrase preset

* Wed May 22 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2019.2.0-6
- Patching in fix for rpmsign

* Thu May 16 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2019.2.0-5
- Patching in fix for gpg str/bytes to to_unicode/to_bytes

* Tue May 14 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2019.2.0-4
- Patching in support for Tornado 4

* Mon May 13 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2019.2.0-3
- Added support for Redhat 8, and removed support for Python 2 packages

* Mon Apr 08 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2019.2.0-2
- Update to support Python 3.6

* Mon Apr 08 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2018.3.4-2
- Update to allow for Python 3.6

* Sat Feb 16 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2019.2.0-1
- Update to feature release 2019.2.0-1  for Python 3

* Sat Feb 16 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2018.3.4-1
- Update to feature release 2018.3.4-1  for Python 3

* Wed Jan 09 2019 SaltStack Packaging Team <packaging@saltstack.com> - 2019.2.0-0
- Update to feature release branch 2019.2.0-0 for Python 2
- Revised acceptable versions of cherrypy, futures

* Tue Oct 09 2018 SaltStack Packaging Team <packaging@saltstack.com> - 2018.3.3-1
- Update to feature release 2018.3.3-1  for Python 3
- Revised versions of cherrypy acceptable

* Mon Jun 11 2018 SaltStack Packaging Team <packaging@saltstack.com> - 2018.3.1-1
- Update to feature release 2018.3.1-1  for Python 3
- Revised minimum msgpack version >= 0.4

* Mon Apr 02 2018 SaltStack Packaging Team <packaging@saltstack.com> - 2018.3.0-1
- Development build for Python 3 support

* Tue Jan 30 2018 SaltStack Packaging Team <packaging@Ch3LL.com> - 2017.7.3-1
- Update to feature release 2017.7.3-1

* Mon Sep 18 2017 SaltStack Packaging Team <packaging@saltstack.com> - 2017.7.2-1
- Update to feature release 2017.7.2

* Tue Aug 15 2017 SaltStack Packaging Team <packaging@saltstack.com> - 2017.7.1-1
- Update to feature release 2017.7.1
- Altered dependency for dnf-utils instead of yum-utils if Fedora 26 or greater

* Wed Jul 12 2017 SaltStack Packaging Team <packaging@saltstack.com> - 2017.7.0-1
- Update to feature release 2017.7.0
- Added python-psutil as a requirement, disabled auto enable for Redhat 6

* Thu Jun 22 2017 SaltStack Packaging Team <packaging@saltstack.com> - 2016.11.6-1
- Update to feature release 2016.11.6

* Thu Apr 27 2017 SaltStack Packaging Team <packaging@saltstack.com> - 2016.11.5-1
- Update to feature release 2016.11.5
- Altered to use pycryptodomex if 64 bit and Redhat 6 and greater otherwise pycrypto
- Addition of salt-proxy@.service

* Wed Apr 19 2017 SaltStack Packaging Team <packaging@saltstack.com> - 2016.11.4-1
- Update to feature release 2016.11.4 and use of pycryptodomex

* Mon Mar 20 2017 SaltStack Packaging Team <packaging@saltstack.com> - 2016.11.3-2
- Updated to allow for pre and post processing for salt-syndic and salt-api

* Wed Feb 22 2017 SaltStack Packaging Team <packaging@saltstack.com> - 2016.11.3-1
- Update to feature release 2016.11.3

* Tue Jan 17 2017 SaltStack Packaging Team <packaging@saltstack.com> - 2016.11.2-1
- Update to feature release 2016.11.2

* Tue Dec 13 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.11.1-1
- Update to feature release 2016.11.1

* Wed Nov 30 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.11.0-2
- Adjust for single spec for Redhat family and fish-completions

* Tue Nov 22 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.11.0-1
- Update to feature release 2016.11.0

* Wed Nov  2 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.11.0-0.rc2
- Update to feature release 2016.11.0 Release Candidate 2

* Wed Oct 26 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.11.0-0.rc1
- Update to feature release 2016.11.0 Release Candidate 1

* Fri Oct 14 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.3.3-4
- Ported to build on Amazon Linux 2016.09 natively

* Mon Sep 12 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.3.3-3
- Adjust spec file for Fedora 24 support

* Tue Aug 30 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.3.3-2
- Fix systemd update of existing installation

* Fri Aug 26 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.3.3-1
- Update to feature release 2016.3.3

* Fri Jul 29 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.3.2-1
- Update to feature release 2016.3.2

* Fri Jun 10 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.3.1-1
- Update to feature release 2016.3.1

* Mon May 23 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.3.0-1
- Update to feature release 2016.3.0

* Wed Apr  6 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2016.3.0-rc2
- Update to bugfix release 2016.3.0 Release Candidate 2

* Fri Mar 25 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.8-2
- Patched fixes 32129, 32023, 32117

* Wed Mar 16 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.8-1
- Update to bugfix release 2015.8.8

* Tue Feb 16 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.7-1
- Update to bugfix release 2015.8.7

* Mon Jan 25 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.4-1
- Update to bugfix release 2015.8.4

* Thu Jan 14 2016 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.3-3
- Add systemd environment files

* Mon Dec  7 2015 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.3-2
- Additional salt configuration directories on install

* Tue Dec  1 2015 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.3-1
- Update to bugfix release 2015.8.3

* Fri Nov 13 2015 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.2-1
- Update to bugfix release 2015.8.2

* Fri Oct 30 2015 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.1-2
- Update for pre-install direcories

* Wed Oct  7 2015 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.1-1
- Update to feature release 2015.8.1

* Wed Sep 30 2015 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.0-3
- Update include python-uinttest2

* Wed Sep  9 2015 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.0-2
- Update include testing

* Fri Sep  4 2015 SaltStack Packaging Team <packaging@saltstack.com> - 2015.8.0-1
- Update to feature release 2015.8.0

* Fri Jul 10 2015 Erik Johnson <erik@saltstack.com> - 2015.5.3-4
- Patch tests

* Fri Jul 10 2015 Erik Johnson <erik@saltstack.com> - 2015.5.3-3
- Patch init grain

* Fri Jul 10 2015 Erik Johnson <erik@saltstack.com> - 2015.5.3-2
- Update to bugfix release 2015.5.3, add bash completion

* Thu Jun  4 2015 Erik Johnson <erik@saltstack.com> - 2015.5.2-3
- Mark salt-ssh roster as a config file to prevent replacement

* Thu Jun  4 2015 Erik Johnson <erik@saltstack.com> - 2015.5.2-2
- Update skipped tests

* Thu Jun  4 2015 Erik Johnson <erik@saltstack.com> - 2015.5.2-1
- Update to bugfix release 2015.5.2

* Mon Jun  1 2015 Erik Johnson <erik@saltstack.com> - 2015.5.1-2
- Add missing dependency on which (RH #1226636)

* Wed May 27 2015 Erik Johnson <erik@saltstack.com> - 2015.5.1-1
- Update to bugfix release 2015.5.1

* Mon May 11 2015 Erik Johnson <erik@saltstack.com> - 2015.5.0-1
- Update to feature release 2015.5.0

* Fri Apr 17 2015 Erik Johnson <erik@saltstack.com> - 2014.7.5-1
- Update to bugfix release 2014.7.5

* Tue Apr  7 2015 Erik Johnson <erik@saltstack.com> - 2014.7.4-4
- Fix RH bug #1210316 and Salt bug #22003

* Tue Apr  7 2015 Erik Johnson <erik@saltstack.com> - 2014.7.4-2
- Update to bugfix release 2014.7.4

* Tue Feb 17 2015 Erik Johnson <erik@saltstack.com> - 2014.7.2-1
- Update to bugfix release 2014.7.2

* Mon Jan 19 2015 Erik Johnson <erik@saltstack.com> - 2014.7.1-1
- Update to bugfix release 2014.7.1

* Fri Nov  7 2014 Erik Johnson <erik@saltstack.com> - 2014.7.0-3
- Make salt-api its own package

* Thu Nov  6 2014 Erik Johnson <erik@saltstack.com> - 2014.7.0-2
- Fix changelog

* Thu Nov  6 2014 Erik Johnson <erik@saltstack.com> - 2014.7.0-1
- Update to feature release 2014.7.0

* Fri Oct 17 2014 Erik Johnson <erik@saltstack.com> - 2014.1.13-1
- Update to bugfix release 2014.1.13

* Mon Sep 29 2014 Erik Johnson <erik@saltstack.com> - 2014.1.11-1
- Update to bugfix release 2014.1.11

* Sun Aug 10 2014 Erik Johnson <erik@saltstack.com> - 2014.1.10-4
- Fix incorrect conditional

* Tue Aug  5 2014 Erik Johnson <erik@saltstack.com> - 2014.1.10-2
- Deploy cachedir with package

* Mon Aug  4 2014 Erik Johnson <erik@saltstack.com> - 2014.1.10-1
- Update to bugfix release 2014.1.10

* Thu Jul 10 2014 Erik Johnson <erik@saltstack.com> - 2014.1.7-3
- Add logrotate script

* Thu Jul 10 2014 Erik Johnson <erik@saltstack.com> - 2014.1.7-1
- Update to bugfix release 2014.1.7

* Wed Jun 11 2014 Erik Johnson <erik@saltstack.com> - 2014.1.5-1
- Update to bugfix release 2014.1.5

* Tue May  6 2014 Erik Johnson <erik@saltstack.com> - 2014.1.4-1
- Update to bugfix release 2014.1.4

* Thu Feb 20 2014 Erik Johnson <erik@saltstack.com> - 2014.1.0-1
- Update to feature release 2014.1.0

* Mon Jan 27 2014 Erik Johnson <erik@saltstack.com> - 0.17.5-1
- Update to bugfix release 0.17.5

* Thu Dec 19 2013 Erik Johnson <erik@saltstack.com> - 0.17.4-1
- Update to bugfix release 0.17.4

* Tue Nov 19 2013 Erik Johnson <erik@saltstack.com> - 0.17.2-2
- Patched to fix pkgrepo.managed regression

* Mon Nov 18 2013 Erik Johnson <erik@saltstack.com> - 0.17.2-1
- Update to bugfix release 0.17.2

* Thu Oct 17 2013 Erik Johnson <erik@saltstack.com> - 0.17.1-1
- Update to bugfix release 0.17.1

* Thu Sep 26 2013 Erik Johnson <erik@saltstack.com> - 0.17.0-1
- Update to feature release 0.17.0

* Wed Sep 11 2013 David Anderson <dave@dubkat.com>
- Change sourcing order of init functions and salt default file

* Sat Sep 07 2013 Erik Johnson <erik@saltstack.com> - 0.16.4-1
- Update to patch release 0.16.4

* Sun Aug 25 2013 Florian La Roche <Florian.LaRoche@gmx.net>
- fixed preun/postun scripts for salt-minion

* Thu Aug 15 2013 Andrew Niemantsverdriet <andrewniemants@gmail.com> - 0.16.3-1
- Update to patch release 0.16.3

* Thu Aug 8 2013 Clint Savage <herlo1@gmail.com> - 0.16.2-1
- Update to patch release 0.16.2

* Sun Aug 04 2013 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.16.0-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_20_Mass_Rebuild

* Tue Jul 9 2013 Clint Savage <herlo1@gmail.com> - 0.16.0-1
- Update to feature release 0.16.0

* Sat Jun 1 2013 Clint Savage <herlo1@gmail.com> - 0.15.3-1
- Update to patch release 0.15.3
- Removed OrderedDict patch

* Fri May 31 2013 Clint Savage <herlo1@gmail.com> - 0.15.2-1
- Update to patch release 0.15.2
- Patch OrderedDict for failed tests (SaltStack#4912)

* Wed May 8 2013 Clint Savage <herlo1@gmail.com> - 0.15.1-1
- Update to patch release 0.15.1

* Sat May 4 2013 Clint Savage <herlo1@gmail.com> - 0.15.0-1
- Update to upstream feature release 0.15.0

* Fri Apr 19 2013 Clint Savage <herlo1@gmail.com> - 0.14.1-1
- Update to upstream patch release 0.14.1

* Sat Mar 23 2013 Clint Savage <herlo1@gmail.com> - 0.14.0-1
- Update to upstream feature release 0.14.0

* Fri Mar 22 2013 Clint Savage <herlo1@gmail.com> - 0.13.3-1
- Update to upstream patch release 0.13.3

* Wed Mar 13 2013 Clint Savage <herlo1@gmail.com> - 0.13.2-1
- Update to upstream patch release 0.13.2

* Fri Feb 15 2013 Clint Savage <herlo1@gmail.com> - 0.13.1-1
- Update to upstream patch release 0.13.1
- Add unittest support

* Sat Feb 02 2013 Clint Savage <herlo1@gmail.com> - 0.12.1-1
- Remove patches and update to upstream patch release 0.12.1

* Thu Jan 17 2013 Wendall Cada <wendallc@83864.com> - 0.12.0-2
- Added unittest support

* Wed Jan 16 2013 Clint Savage <herlo1@gmail.com> - 0.12.0-1
- Upstream release 0.12.0

* Fri Dec 14 2012 Clint Savage <herlo1@gmail.com> - 0.11.1-1
- Upstream patch release 0.11.1
- Fixes security vulnerability (https://github.com/saltstack/salt/issues/2916)

* Fri Dec 14 2012 Clint Savage <herlo1@gmail.com> - 0.11.0-1
- Moved to upstream release 0.11.0

* Wed Dec 05 2012 Mike Chesnut <mchesnut@gmail.com> - 0.10.5-2
- moved to upstream release 0.10.5
- removing references to minion.template and master.template, as those files
  have been removed from the repo

* Sun Nov 18 2012 Clint Savage <herlo1@gmail.com> - 0.10.5-1
- Moved to upstream release 0.10.5
- Added pciutils as Requires

* Wed Oct 24 2012 Clint Savage <herlo1@gmail.com> - 0.10.4-1
- Moved to upstream release 0.10.4
- Patched jcollie/systemd-service-status (SALT@GH#2335) (RHBZ#869669)

* Tue Oct 2 2012 Clint Savage <herlo1@gmail.com> - 0.10.3-1
- Moved to upstream release 0.10.3
- Added systemd scriplets (RHBZ#850408)

* Thu Aug 2 2012 Clint Savage <herlo1@gmail.com> - 0.10.2-2
- Fix upstream bug #1730 per RHBZ#845295

* Tue Jul 31 2012 Clint Savage <herlo1@gmail.com> - 0.10.2-1
- Moved to upstream release 0.10.2
- Removed PyXML as a dependency

* Sat Jun 16 2012 Clint Savage <herlo1@gmail.com> - 0.10.1-1
- Moved to upstream release 0.10.1

* Sat Apr 28 2012 Clint Savage <herlo1@gmail.com> - 0.9.9.1-1
- Moved to upstream release 0.9.9.1

* Tue Apr 17 2012 Peter Robinson <pbrobinson@fedoraproject.org> - 0.9.8-2
- dmidecode is x86 only

* Wed Mar 21 2012 Clint Savage <herlo1@gmail.com> - 0.9.8-1
- Moved to upstream release 0.9.8

* Thu Mar 8 2012 Clint Savage <herlo1@gmail.com> - 0.9.7-2
- Added dmidecode as a Requires

* Thu Feb 16 2012 Clint Savage <herlo1@gmail.com> - 0.9.7-1
- Moved to upstream release 0.9.7

* Tue Jan 24 2012 Clint Savage <herlo1@gmail.com> - 0.9.6-2
- Added README.fedora and removed deps for optional modules

* Sat Jan 21 2012 Clint Savage <herlo1@gmail.com> - 0.9.6-1
- New upstream release

* Sun Jan 8 2012 Clint Savage <herlo1@gmail.com> - 0.9.4-6
- Missed some critical elements for SysV and rpmlint cleanup

* Sun Jan 8 2012 Clint Savage <herlo1@gmail.com> - 0.9.4-5
- SysV clean up in post

* Sat Jan 7 2012 Clint Savage <herlo1@gmail.com> - 0.9.4-4
- Cleaning up perms, group and descriptions, adding post scripts for systemd

* Thu Jan 5 2012 Clint Savage <herlo1@gmail.com> - 0.9.4-3
- Updating for systemd on Fedora 15+

* Thu Dec 1 2011 Clint Savage <herlo1@gmail.com> - 0.9.4-2
- Removing requirement for Cython. Optional only for salt-minion

* Wed Nov 30 2011 Clint Savage <herlo1@gmail.com> - 0.9.4-1
- New upstream release with new features and bugfixes

* Thu Nov 17 2011 Clint Savage <herlo1@gmail.com> - 0.9.3-1
- New upstream release with new features and bugfixes

* Sat Sep 17 2011 Clint Savage <herlo1@gmail.com> - 0.9.2-1
- Bugfix release from upstream to fix python2.6 issues

* Fri Sep 09 2011 Clint Savage <herlo1@gmail.com> - 0.9.1-1
- Initial packages
