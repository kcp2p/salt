import hashlib
import logging
import os
import shutil
import signal
import tempfile
import textwrap
import time
import uuid

import psutil  # pylint: disable=3rd-party-module-not-gated
import pytest
from pytestshellutils.utils import ports
from saltfactories.utils.tempfiles import temp_file

import salt.utils.files
import salt.utils.path
import salt.utils.platform
import salt.utils.stringutils
from tests.support.case import ModuleCase
from tests.support.helpers import with_tempfile
from tests.support.runtests import RUNTIME_VARS

log = logging.getLogger(__name__)


@pytest.mark.windows_whitelisted
class CPModuleTest(ModuleCase):
    """
    Validate the cp module
    """

    def run_function(self, *args, **kwargs):  # pylint: disable=arguments-differ
        """
        Ensure that results are decoded

        TODO: maybe move this behavior to ModuleCase itself?
        """
        return salt.utils.data.decode(super().run_function(*args, **kwargs))

    @with_tempfile()
    @pytest.mark.slow_test
    def test_get_file(self, tgt):
        """
        cp.get_file
        """
        self.run_function("cp.get_file", ["salt://grail/scene33", tgt])
        with salt.utils.files.fopen(tgt, "r") as scene:
            data = salt.utils.stringutils.to_unicode(scene.read())
        self.assertIn("KNIGHT:  They're nervous, sire.", data)
        self.assertNotIn("bacon", data)

    @pytest.mark.slow_test
    def test_get_file_to_dir(self):
        """
        cp.get_file
        """
        tgt = os.path.join(RUNTIME_VARS.TMP, "")
        self.run_function("cp.get_file", ["salt://grail/scene33", tgt])
        with salt.utils.files.fopen(tgt + "scene33", "r") as scene:
            data = salt.utils.stringutils.to_unicode(scene.read())
        self.assertIn("KNIGHT:  They're nervous, sire.", data)
        self.assertNotIn("bacon", data)

    @with_tempfile()
    @pytest.mark.skip_on_windows(reason="This test hangs on Windows on Py3")
    def test_get_file_templated_paths(self, tgt):
        """
        cp.get_file
        """
        self.run_function(
            "cp.get_file",
            [
                "salt://{{grains.test_grain}}",
                tgt.replace("cheese", "{{grains.test_grain}}"),
            ],
            template="jinja",
        )
        with salt.utils.files.fopen(tgt, "r") as cheese:
            data = salt.utils.stringutils.to_unicode(cheese.read())
        self.assertIn("Gromit", data)
        self.assertNotIn("bacon", data)

    @with_tempfile()
    @pytest.mark.slow_test
    def test_get_file_gzipped(self, tgt):
        """
        cp.get_file
        """
        src = os.path.join(RUNTIME_VARS.FILES, "file", "base", "file.big")
        with salt.utils.files.fopen(src, "rb") as fp_:
            hash_str = hashlib.sha256(fp_.read()).hexdigest()

        self.run_function("cp.get_file", ["salt://file.big", tgt], gzip=5)
        with salt.utils.files.fopen(tgt, "rb") as scene:
            data = scene.read()
        self.assertEqual(hash_str, hashlib.sha256(data).hexdigest())
        data = salt.utils.stringutils.to_unicode(data)
        self.assertIn("KNIGHT:  They're nervous, sire.", data)
        self.assertNotIn("bacon", data)

    @pytest.mark.slow_test
    def test_get_file_makedirs(self):
        """
        cp.get_file
        """
        tgt = os.path.join(RUNTIME_VARS.TMP, "make", "dirs", "scene33")
        self.run_function("cp.get_file", ["salt://grail/scene33", tgt], makedirs=True)
        self.addCleanup(
            shutil.rmtree, os.path.join(RUNTIME_VARS.TMP, "make"), ignore_errors=True
        )
        with salt.utils.files.fopen(tgt, "r") as scene:
            data = salt.utils.stringutils.to_unicode(scene.read())
        self.assertIn("KNIGHT:  They're nervous, sire.", data)
        self.assertNotIn("bacon", data)

    @with_tempfile()
    @pytest.mark.slow_test
    def test_get_template(self, tgt):
        """
        cp.get_template
        """
        self.run_function(
            "cp.get_template", ["salt://grail/scene33", tgt], spam="bacon"
        )
        with salt.utils.files.fopen(tgt, "r") as scene:
            data = salt.utils.stringutils.to_unicode(scene.read())
        self.assertIn("bacon", data)
        self.assertNotIn("spam", data)

    @pytest.mark.slow_test
    def test_get_dir(self):
        """
        cp.get_dir
        """
        tgt = os.path.join(RUNTIME_VARS.TMP, "many")
        self.run_function("cp.get_dir", ["salt://grail", tgt])
        self.assertIn("grail", os.listdir(tgt))
        self.assertIn("36", os.listdir(os.path.join(tgt, "grail")))
        self.assertIn("empty", os.listdir(os.path.join(tgt, "grail")))
        self.assertIn("scene", os.listdir(os.path.join(tgt, "grail", "36")))

    @pytest.mark.slow_test
    def test_get_dir_templated_paths(self):
        """
        cp.get_dir
        """
        tgt = os.path.join(RUNTIME_VARS.TMP, "many")
        self.run_function(
            "cp.get_dir",
            ["salt://{{grains.script}}", tgt.replace("many", "{{grains.alot}}")],
        )
        self.assertIn("grail", os.listdir(tgt))
        self.assertIn("36", os.listdir(os.path.join(tgt, "grail")))
        self.assertIn("empty", os.listdir(os.path.join(tgt, "grail")))
        self.assertIn("scene", os.listdir(os.path.join(tgt, "grail", "36")))

    # cp.get_url tests

    @with_tempfile()
    @pytest.mark.slow_test
    def test_get_url(self, tgt):
        """
        cp.get_url with salt:// source given
        """
        self.run_function("cp.get_url", ["salt://grail/scene33", tgt])
        with salt.utils.files.fopen(tgt, "r") as scene:
            data = salt.utils.stringutils.to_unicode(scene.read())
        self.assertIn("KNIGHT:  They're nervous, sire.", data)
        self.assertNotIn("bacon", data)

    @pytest.mark.slow_test
    def test_get_url_makedirs(self):
        """
        cp.get_url
        """
        tgt = os.path.join(RUNTIME_VARS.TMP, "make", "dirs", "scene33")
        self.run_function("cp.get_url", ["salt://grail/scene33", tgt], makedirs=True)
        self.addCleanup(
            shutil.rmtree, os.path.join(RUNTIME_VARS.TMP, "make"), ignore_errors=True
        )
        with salt.utils.files.fopen(tgt, "r") as scene:
            data = salt.utils.stringutils.to_unicode(scene.read())
        self.assertIn("KNIGHT:  They're nervous, sire.", data)
        self.assertNotIn("bacon", data)

    @pytest.mark.slow_test
    def test_get_url_dest_empty(self):
        """
        cp.get_url with salt:// source given and destination omitted.
        """
        ret = self.run_function("cp.get_url", ["salt://grail/scene33"])
        with salt.utils.files.fopen(ret, "r") as scene:
            data = salt.utils.stringutils.to_unicode(scene.read())
        self.assertIn("KNIGHT:  They're nervous, sire.", data)
        self.assertNotIn("bacon", data)

    @pytest.mark.slow_test
    def test_get_url_no_dest(self):
        """
        cp.get_url with salt:// source given and destination set as None
        """
        tgt = None
        ret = self.run_function("cp.get_url", ["salt://grail/scene33", tgt])
        self.assertIn("KNIGHT:  They're nervous, sire.", ret)

    @pytest.mark.slow_test
    def test_get_url_nonexistent_source(self):
        """
        cp.get_url with nonexistent salt:// source given
        """
        tgt = None
        ret = self.run_function("cp.get_url", ["salt://grail/nonexistent_scene", tgt])
        self.assertEqual(ret, False)

    @pytest.mark.slow_test
    def test_get_url_to_dir(self):
        """
        cp.get_url with salt:// source
        """
        tgt = os.path.join(RUNTIME_VARS.TMP, "")
        self.run_function("cp.get_url", ["salt://grail/scene33", tgt])
        with salt.utils.files.fopen(tgt + "scene33", "r") as scene:
            data = salt.utils.stringutils.to_unicode(scene.read())
        self.assertIn("KNIGHT:  They're nervous, sire.", data)
        self.assertNotIn("bacon", data)

    @with_tempfile()
    @pytest.mark.slow_test
    def test_get_url_https(self, tgt):
        """
        cp.get_url with https:// source given
        """
        self.run_function(
            "cp.get_url",
            ["https://packages.broadcom.com/artifactory/saltproject-generic/", tgt],
        )
        with salt.utils.files.fopen(tgt, "r") as instructions:
            data = salt.utils.stringutils.to_unicode(instructions.read())
        self.assertIn("Index of saltproject", data)
        self.assertIn("onedir", data)
        self.assertIn("Artifactory Online Server", data)
        self.assertNotIn("AYBABTU", data)

    @pytest.mark.slow_test
    def test_get_url_https_dest_empty(self):
        """
        cp.get_url with https:// source given and destination omitted.
        """
        ret = self.run_function(
            "cp.get_url",
            ["https://packages.broadcom.com/artifactory/saltproject-generic/"],
        )

        with salt.utils.files.fopen(ret, "r") as instructions:
            data = salt.utils.stringutils.to_unicode(instructions.read())
        self.assertIn("Index of saltproject", data)
        self.assertIn("onedir", data)
        self.assertIn("Artifactory Online Server", data)
        self.assertNotIn("AYBABTU", data)

    @pytest.mark.slow_test
    def test_get_url_https_no_dest(self):
        """
        cp.get_url with https:// source given and destination set as None
        """
        timeout = 500
        start = time.time()
        sleep = 5
        tgt = None
        while time.time() - start <= timeout:
            ret = self.run_function(
                "cp.get_url",
                ["https://packages.broadcom.com/artifactory/saltproject-generic/", tgt],
            )
            if ret.find("HTTP 599") == -1:
                break
            time.sleep(sleep)
        if ret.find("HTTP 599") != -1:
            raise Exception(
                "https://packages.broadcom.com/artifactory/saltproject-generic/ returned 599 error"
            )
        self.assertIn("Index of saltproject", ret)
        self.assertIn("onedir", ret)
        self.assertIn("Artifactory Online Server", ret)
        self.assertNotIn("AYBABTU", ret)

    @pytest.mark.slow_test
    def test_get_url_file(self):
        """
        cp.get_url with file:// source given
        """
        tgt = ""
        src = os.path.join("file://", RUNTIME_VARS.FILES, "file", "base", "file.big")
        ret = self.run_function("cp.get_url", [src, tgt])
        with salt.utils.files.fopen(ret, "r") as scene:
            data = salt.utils.stringutils.to_unicode(scene.read())
        self.assertIn("KNIGHT:  They're nervous, sire.", data)
        self.assertNotIn("bacon", data)

    @pytest.mark.slow_test
    def test_get_url_file_no_dest(self):
        """
        cp.get_url with file:// source given and destination set as None
        """
        tgt = None
        src = os.path.join("file://", RUNTIME_VARS.FILES, "file", "base", "file.big")
        ret = self.run_function("cp.get_url", [src, tgt])
        self.assertIn("KNIGHT:  They're nervous, sire.", ret)
        self.assertNotIn("bacon", ret)

    @with_tempfile()
    @pytest.mark.slow_test
    def test_get_url_ftp(self, tgt):
        """
        cp.get_url with https:// source given
        """
        self.run_function(
            "cp.get_url",
            [
                "ftp://ftp.freebsd.org/pub/FreeBSD/releases/amd64/README.TXT",
                tgt,
            ],
        )
        with salt.utils.files.fopen(tgt, "r") as instructions:
            data = salt.utils.stringutils.to_unicode(instructions.read())
        self.assertIn("The official FreeBSD", data)

    # cp.get_file_str tests

    @pytest.mark.slow_test
    def test_get_file_str_salt(self):
        """
        cp.get_file_str with salt:// source given
        """
        src = "salt://grail/scene33"
        ret = self.run_function("cp.get_file_str", [src])
        self.assertIn("KNIGHT:  They're nervous, sire.", ret)

    @pytest.mark.slow_test
    def test_get_file_str_nonexistent_source(self):
        """
        cp.get_file_str with nonexistent salt:// source given
        """
        src = "salt://grail/nonexistent_scene"
        ret = self.run_function("cp.get_file_str", [src])
        self.assertEqual(ret, False)

    @pytest.mark.slow_test
    def test_get_file_str_https(self):
        """
        cp.get_file_str with https:// source given
        """
        src = "https://packages.broadcom.com/artifactory/saltproject-generic/"
        ret = self.run_function("cp.get_file_str", [src])
        self.assertIn("Index of saltproject", ret)
        self.assertIn("onedir", ret)
        self.assertIn("Artifactory Online Server", ret)
        self.assertNotIn("AYBABTU", ret)

    @pytest.mark.slow_test
    def test_get_file_str_local(self):
        """
        cp.get_file_str with file:// source given
        """
        src = os.path.join("file://", RUNTIME_VARS.FILES, "file", "base", "file.big")
        ret = self.run_function("cp.get_file_str", [src])
        self.assertIn("KNIGHT:  They're nervous, sire.", ret)
        self.assertNotIn("bacon", ret)

    # caching tests

    @pytest.mark.slow_test
    def test_cache_file(self):
        """
        cp.cache_file
        """
        ret = self.run_function("cp.cache_file", ["salt://grail/scene33"])
        with salt.utils.files.fopen(ret, "r") as scene:
            data = salt.utils.stringutils.to_unicode(scene.read())
        self.assertIn("KNIGHT:  They're nervous, sire.", data)
        self.assertNotIn("bacon", data)

    @pytest.mark.slow_test
    def test_cache_files(self):
        """
        cp.cache_files
        """
        ret = self.run_function(
            "cp.cache_files", [["salt://grail/scene33", "salt://grail/36/scene"]]
        )
        for path in ret:
            with salt.utils.files.fopen(path, "r") as scene:
                data = salt.utils.stringutils.to_unicode(scene.read())
            self.assertIn("ARTHUR:", data)
            self.assertNotIn("bacon", data)

    @with_tempfile()
    @pytest.mark.slow_test
    def test_cache_master(self, tgt):
        """
        cp.cache_master
        """
        ret = self.run_function(
            "cp.cache_master",
            [tgt],
        )
        for path in ret:
            self.assertTrue(os.path.exists(path))

    @pytest.mark.slow_test
    def test_cache_local_file(self):
        """
        cp.cache_local_file
        """
        src = os.path.join(RUNTIME_VARS.TMP, "random")
        with salt.utils.files.fopen(src, "w+") as fn_:
            fn_.write(salt.utils.stringutils.to_str("foo"))
        ret = self.run_function("cp.cache_local_file", [src])
        with salt.utils.files.fopen(ret, "r") as cp_:
            self.assertEqual(salt.utils.stringutils.to_unicode(cp_.read()), "foo")

    @pytest.mark.skip_if_binaries_missing("nginx")
    @pytest.mark.slow_test
    @pytest.mark.skip_if_not_root
    def test_cache_remote_file(self):
        """
        cp.cache_file
        """
        nginx_port = ports.get_unused_localhost_port()
        url_prefix = f"http://localhost:{nginx_port}/"
        temp_dir = tempfile.mkdtemp(dir=RUNTIME_VARS.TMP)
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        nginx_root_dir = os.path.join(temp_dir, "root")
        nginx_conf_dir = os.path.join(temp_dir, "conf")
        nginx_conf = os.path.join(nginx_conf_dir, "nginx.conf")
        nginx_pidfile = os.path.join(nginx_conf_dir, "nginx.pid")
        file_contents = "Hello world!"

        for dirname in (nginx_root_dir, nginx_conf_dir):
            os.makedirs(dirname)

        # Write the temp file
        with salt.utils.files.fopen(
            os.path.join(nginx_root_dir, "actual_file"), "w"
        ) as fp_:
            fp_.write(salt.utils.stringutils.to_str(file_contents))

        # Write the nginx config
        with salt.utils.files.fopen(nginx_conf, "w") as fp_:
            fp_.write(
                textwrap.dedent(
                    salt.utils.stringutils.to_str(
                        f"""\
                user root;
                worker_processes 1;
                error_log {nginx_conf_dir}/server_error.log;
                pid {nginx_pidfile};

                events {{
                    worker_connections 1024;
                }}

                http {{
                    include       /etc/nginx/mime.types;
                    default_type  application/octet-stream;

                    access_log {nginx_conf_dir}/access.log;
                    error_log {nginx_conf_dir}/error.log;

                    server {{
                        listen {nginx_port} default_server;
                        server_name cachefile.local;
                        root {nginx_root_dir};

                        location ~ ^/301$ {{
                            return 301 /actual_file;
                        }}

                        location ~ ^/302$ {{
                            return 302 /actual_file;
                        }}
                    }}
                }}"""
                    )
                )
            )

        self.run_function("cmd.run", [["nginx", "-c", nginx_conf]], python_shell=False)
        with salt.utils.files.fopen(nginx_pidfile) as fp_:
            nginx_pid = int(fp_.read().strip())
            nginx_proc = psutil.Process(pid=nginx_pid)
            self.addCleanup(nginx_proc.send_signal, signal.SIGQUIT)

        for code in ("", "301", "302"):
            url = url_prefix + (code or "actual_file")
            log.debug("attempting to cache %s", url)
            ret = self.run_function("cp.cache_file", [url])
            self.assertTrue(ret)
            with salt.utils.files.fopen(ret) as fp_:
                cached_contents = salt.utils.stringutils.to_unicode(fp_.read())
                self.assertEqual(cached_contents, file_contents)

    @pytest.mark.slow_test
    def test_list_states(self):
        """
        cp.list_states
        """
        top_sls = """
        base:
          '*':
            - core
            """

        core_state = """
        {}/testfile:
          file:
            - managed
            - source: salt://testfile
            - makedirs: true
            """.format(
            RUNTIME_VARS.TMP
        )

        with temp_file(
            "top.sls", top_sls, RUNTIME_VARS.TMP_BASEENV_STATE_TREE
        ), temp_file("core.sls", core_state, RUNTIME_VARS.TMP_BASEENV_STATE_TREE):
            ret = self.run_function(
                "cp.list_states",
            )
            self.assertIn("core", ret)
            self.assertIn("top", ret)

    @pytest.mark.slow_test
    def test_list_minion(self):
        """
        cp.list_minion
        """
        self.run_function("cp.cache_file", ["salt://grail/scene33"])
        ret = self.run_function("cp.list_minion")
        found = False
        search = "grail/scene33"
        if salt.utils.platform.is_windows():
            search = r"grail\scene33"
        for path in ret:
            if search in path:
                found = True
                break
        self.assertTrue(found)

    @pytest.mark.slow_test
    def test_is_cached(self):
        """
        cp.is_cached
        """
        self.run_function("cp.cache_file", ["salt://grail/scene33"])
        ret1 = self.run_function("cp.is_cached", ["salt://grail/scene33"])
        self.assertTrue(ret1)
        ret2 = self.run_function("cp.is_cached", ["salt://fasldkgj/poicxzbn"])
        self.assertFalse(ret2)

    @pytest.mark.slow_test
    def test_hash_file(self):
        """
        cp.hash_file
        """
        sha256_hash = self.run_function("cp.hash_file", ["salt://grail/scene33"])
        path = self.run_function("cp.cache_file", ["salt://grail/scene33"])
        with salt.utils.files.fopen(path, "rb") as fn_:
            data = fn_.read()
            self.assertEqual(sha256_hash["hsum"], hashlib.sha256(data).hexdigest())

    @with_tempfile()
    @pytest.mark.slow_test
    def test_get_file_from_env_predefined(self, tgt):
        """
        cp.get_file
        """
        tgt = os.path.join(RUNTIME_VARS.TMP, "cheese")
        try:
            self.run_function("cp.get_file", ["salt://cheese", tgt])
            with salt.utils.files.fopen(tgt, "r") as cheese:
                data = salt.utils.stringutils.to_unicode(cheese.read())
            self.assertIn("Gromit", data)
            self.assertNotIn("Comte", data)
        finally:
            os.unlink(tgt)

    @with_tempfile()
    @pytest.mark.slow_test
    def test_get_file_from_env_in_url(self, tgt):
        tgt = os.path.join(RUNTIME_VARS.TMP, "cheese")
        try:
            self.run_function("cp.get_file", ["salt://cheese?saltenv=prod", tgt])
            with salt.utils.files.fopen(tgt, "r") as cheese:
                data = salt.utils.stringutils.to_unicode(cheese.read())
            self.assertIn("Gromit", data)
            self.assertIn("Comte", data)
        finally:
            os.unlink(tgt)

    @pytest.mark.slow_test
    def test_push(self):
        log_to_xfer = os.path.join(RUNTIME_VARS.TMP, uuid.uuid4().hex)
        open(  # pylint: disable=resource-leakage
            log_to_xfer, "w", encoding="utf-8"
        ).close()
        try:
            self.run_function("cp.push", [log_to_xfer])
            tgt_cache_file = os.path.join(
                RUNTIME_VARS.RUNTIME_CONFIGS["master"]["cachedir"],
                "minions",
                "minion",
                "files",
                os.path.splitdrive(os.path.normpath(log_to_xfer.lstrip(os.sep)))[1],
            )
            self.assertTrue(
                os.path.isfile(tgt_cache_file), "File was not cached on the master"
            )
        finally:
            os.unlink(tgt_cache_file)

    @pytest.mark.slow_test
    def test_envs(self):
        self.assertEqual(sorted(self.run_function("cp.envs")), sorted(["base", "prod"]))
