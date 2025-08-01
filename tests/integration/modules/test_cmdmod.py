import os
import random
import sys
import tempfile
from contextlib import contextmanager

import pytest

import salt.utils.path
import salt.utils.platform
import salt.utils.user
from tests.support.case import ModuleCase
from tests.support.helpers import SKIP_INITIAL_PHOTONOS_FAILURES, dedent
from tests.support.runtests import RUNTIME_VARS

AVAILABLE_PYTHON_EXECUTABLE = salt.utils.path.which_bin(
    ["python", "python2", "python2.6", "python2.7"]
)


@pytest.mark.windows_whitelisted
class CMDModuleTest(ModuleCase):
    """
    Validate the cmd module
    """

    def setUp(self):
        self.runas_usr = "nobody"
        if salt.utils.platform.is_darwin():
            self.runas_usr = "macsalttest"

    @contextmanager
    def _ensure_user_exists(self, name):
        if name in self.run_function("user.info", [name]).values():
            # User already exists; don't touch
            yield
        else:
            # Need to create user for test
            self.run_function("user.add", [name])
            try:
                yield
            finally:
                self.run_function("user.delete", [name], remove=True)

    @pytest.mark.slow_test
    @pytest.mark.skip_on_windows
    def test_run(self):
        """
        cmd.run
        """
        shell = os.environ.get("SHELL")
        if shell is None:
            # Failed to get the SHELL var, don't run
            self.skipTest("Unable to get the SHELL environment variable")

        self.assertTrue(self.run_function("cmd.run", ["echo $SHELL"]))
        self.assertEqual(
            self.run_function(
                "cmd.run", ["echo $SHELL", f"shell={shell}"], python_shell=True
            ).rstrip(),
            shell,
        )
        self.assertEqual(
            self.run_function("cmd.run", ["ls / | grep etc"], python_shell=True), "etc"
        )
        self.assertEqual(
            self.run_function(
                "cmd.run",
                ['echo {{grains.id}} | awk "{print $1}"'],
                template="jinja",
                python_shell=True,
            ),
            "minion",
        )
        self.assertEqual(
            self.run_function(
                "cmd.run", ["grep f"], stdin="one\ntwo\nthree\nfour\nfive\n"
            ),
            "four\nfive",
        )
        self.assertEqual(
            self.run_function(
                "cmd.run", ["cat"], stdin="one\\ntwo", stdin_raw_newlines=False
            ),
            "one\ntwo",
        )
        self.assertEqual(
            self.run_function(
                "cmd.run", ["cat"], stdin="one\\ntwo", stdin_raw_newlines=True
            ),
            "one\\ntwo",
        )
        self.assertEqual(
            self.run_function(
                "cmd.run", ['echo "a=b" | sed -e s/=/:/g'], python_shell=True
            ),
            "a:b",
        )

    @pytest.mark.slow_test
    def test_stdout(self):
        """
        cmd.run_stdout
        """
        self.assertEqual(
            self.run_function("cmd.run_stdout", ['echo "cheese"']).rstrip(),
            "cheese" if not salt.utils.platform.is_windows() else '"cheese"',
        )

    @pytest.mark.slow_test
    def test_stderr(self):
        """
        cmd.run_stderr
        """
        if sys.platform.startswith(("freebsd", "openbsd")):
            shell = "/bin/sh"
        else:
            shell = "/bin/bash"

        self.assertEqual(
            self.run_function(
                "cmd.run_stderr",
                ['echo "cheese" 1>&2', f"shell={shell}"],
                python_shell=True,
            ).rstrip(),
            "cheese" if not salt.utils.platform.is_windows() else '"cheese"',
        )

    @pytest.mark.slow_test
    def test_run_all(self):
        """
        cmd.run_all
        """
        if sys.platform.startswith(("freebsd", "openbsd")):
            shell = "/bin/sh"
        else:
            shell = "/bin/bash"

        ret = self.run_function(
            "cmd.run_all",
            ['echo "cheese" 1>&2', f"shell={shell}"],
            python_shell=True,
        )
        self.assertTrue("pid" in ret)
        self.assertTrue("retcode" in ret)
        self.assertTrue("stdout" in ret)
        self.assertTrue("stderr" in ret)
        self.assertTrue(isinstance(ret.get("pid"), int))
        self.assertTrue(isinstance(ret.get("retcode"), int))
        self.assertTrue(isinstance(ret.get("stdout"), str))
        self.assertTrue(isinstance(ret.get("stderr"), str))
        self.assertEqual(
            ret.get("stderr").rstrip(),
            "cheese" if not salt.utils.platform.is_windows() else '"cheese"',
        )

    @pytest.mark.slow_test
    def test_retcode(self):
        """
        cmd.retcode
        """
        self.assertEqual(
            self.run_function("cmd.retcode", ["exit 0"], python_shell=True), 0
        )
        self.assertEqual(
            self.run_function("cmd.retcode", ["exit 1"], python_shell=True), 1
        )

    @pytest.mark.slow_test
    def test_run_all_with_success_retcodes(self):
        """
        cmd.run with success_retcodes
        """
        ret = self.run_function(
            "cmd.run_all", ["exit 42"], success_retcodes=[42], python_shell=True
        )

        self.assertTrue("retcode" in ret)
        self.assertEqual(ret.get("retcode"), 0)

    @pytest.mark.slow_test
    def test_retcode_with_success_retcodes(self):
        """
        cmd.run with success_retcodes
        """
        ret = self.run_function(
            "cmd.retcode", ["exit 42"], success_retcodes=[42], python_shell=True
        )

        self.assertEqual(ret, 0)

    @pytest.mark.slow_test
    def test_run_all_with_success_stderr(self):
        """
        cmd.run with success_retcodes
        """
        random_file = "{}{}{}".format(
            RUNTIME_VARS.TMP_ROOT_DIR, os.path.sep, random.random()
        )

        if salt.utils.platform.is_windows():
            func = "type"
            expected_stderr = "cannot find the file specified"
        else:
            func = "cat"
            expected_stderr = "No such file or directory"
        ret = self.run_function(
            "cmd.run_all",
            [f"{func} {random_file}"],
            success_stderr=[expected_stderr],
            python_shell=True,
        )

        self.assertTrue("retcode" in ret)
        self.assertEqual(ret.get("retcode"), 0)

    @pytest.mark.slow_test
    def test_blacklist_glob(self):
        """
        cmd_blacklist_glob
        """
        self.assertEqual(
            self.run_function("cmd.run", ["bad_command --foo"]).rstrip(),
            'ERROR: The shell command "bad_command --foo" is not permitted',
        )

    @pytest.mark.slow_test
    @pytest.mark.skip_on_windows
    def test_script(self):
        """
        cmd.script
        """
        args = "saltines crackers biscuits=yes"
        script = "salt://script.py"
        ret = self.run_function("cmd.script", [script, args], saltenv="base")
        self.assertEqual(ret["stdout"], args)

    @pytest.mark.slow_test
    @pytest.mark.skip_on_windows
    def test_script_query_string(self):
        """
        cmd.script
        """
        args = "saltines crackers biscuits=yes"
        script = "salt://script.py?saltenv=base"
        ret = self.run_function("cmd.script", [script, args], saltenv="base")
        self.assertEqual(ret["stdout"], args)

    @pytest.mark.slow_test
    @pytest.mark.skip_on_windows
    def test_script_retcode(self):
        """
        cmd.script_retcode
        """
        script = "salt://script.py"
        ret = self.run_function("cmd.script_retcode", [script], saltenv="base")
        self.assertEqual(ret, 0)

    @pytest.mark.slow_test
    @pytest.mark.skip_on_windows
    def test_script_cwd(self):
        """
        cmd.script with cwd
        """
        tmp_cwd = tempfile.mkdtemp(dir=RUNTIME_VARS.TMP)
        args = "saltines crackers biscuits=yes"
        script = "salt://script.py"
        ret = self.run_function(
            "cmd.script", [script, args], cwd=tmp_cwd, saltenv="base"
        )
        self.assertEqual(ret["stdout"], args)

    @pytest.mark.slow_test
    @pytest.mark.skip_on_windows
    def test_script_cwd_with_space(self):
        """
        cmd.script with cwd
        """
        tmp_cwd = "{}{}test 2".format(
            tempfile.mkdtemp(dir=RUNTIME_VARS.TMP), os.path.sep
        )
        os.mkdir(tmp_cwd)

        args = "saltines crackers biscuits=yes"
        script = "salt://script.py"
        ret = self.run_function(
            "cmd.script", [script, args], cwd=tmp_cwd, saltenv="base"
        )
        self.assertEqual(ret["stdout"], args)

    @pytest.mark.destructive_test
    def test_tty(self):
        """
        cmd.tty
        """
        for tty in ("tty0", "pts3"):
            if os.path.exists(os.path.join("/dev", tty)):
                ret = self.run_function("cmd.tty", [tty, "apply salt liberally"])
                self.assertTrue("Success" in ret)

    @pytest.mark.skip_on_windows
    @pytest.mark.skip_if_binaries_missing("which")
    def test_which(self):
        """
        cmd.which
        """
        cmd_which = self.run_function("cmd.which", ["cat"])
        self.assertIsInstance(cmd_which, str)
        cmd_run = self.run_function("cmd.run", ["which cat"])
        self.assertIsInstance(cmd_run, str)
        self.assertEqual(cmd_which.rstrip(), cmd_run.rstrip())

    @pytest.mark.skip_on_windows
    @pytest.mark.skip_if_binaries_missing("which")
    def test_which_bin(self):
        """
        cmd.which_bin
        """
        cmds = ["pip3", "pip2", "pip", "pip-python"]
        ret = self.run_function("cmd.which_bin", [cmds])
        self.assertTrue(os.path.split(ret)[1] in cmds)

    @pytest.mark.slow_test
    def test_has_exec(self):
        """
        cmd.has_exec
        """
        self.assertTrue(
            self.run_function("cmd.has_exec", [AVAILABLE_PYTHON_EXECUTABLE])
        )
        self.assertFalse(
            self.run_function("cmd.has_exec", ["alllfsdfnwieulrrh9123857ygf"])
        )

    @pytest.mark.slow_test
    def test_exec_code(self):
        """
        cmd.exec_code
        """
        code = dedent(
            """
                   import sys
                   sys.stdout.write('cheese')
               """
        )
        self.assertEqual(
            self.run_function(
                "cmd.exec_code", [AVAILABLE_PYTHON_EXECUTABLE, code]
            ).rstrip(),
            "cheese",
        )

    @pytest.mark.slow_test
    def test_exec_code_with_single_arg(self):
        """
        cmd.exec_code
        """
        code = dedent(
            """
                   import sys
                   sys.stdout.write(sys.argv[1])
               """
        )
        arg = "cheese"
        self.assertEqual(
            self.run_function(
                "cmd.exec_code", [AVAILABLE_PYTHON_EXECUTABLE, code], args=arg
            ).rstrip(),
            arg,
        )

    @pytest.mark.slow_test
    def test_exec_code_with_multiple_args(self):
        """
        cmd.exec_code
        """
        code = dedent(
            """
                   import sys
                   sys.stdout.write(sys.argv[1])
               """
        )
        arg = "cheese"
        self.assertEqual(
            self.run_function(
                "cmd.exec_code", [AVAILABLE_PYTHON_EXECUTABLE, code], args=[arg, "test"]
            ).rstrip(),
            arg,
        )

    @pytest.mark.slow_test
    def test_quotes(self):
        """
        cmd.run with quoted command
        """
        if salt.utils.platform.is_windows():
            cmd = """echo SELECT * FROM foo WHERE bar="baz" """
        else:
            cmd = """echo 'SELECT * FROM foo WHERE bar="baz"' """
        expected_result = 'SELECT * FROM foo WHERE bar="baz"'
        result = self.run_function("cmd.run_stdout", [cmd]).strip()
        self.assertEqual(result, expected_result)

    @pytest.mark.skip_if_not_root
    @pytest.mark.skip_on_windows(reason="Skip on Windows, requires password")
    def test_quotes_runas(self):
        """
        cmd.run with quoted command
        """
        cmd = """echo 'SELECT * FROM foo WHERE bar="baz"' """
        expected_result = 'SELECT * FROM foo WHERE bar="baz"'
        result = self.run_function(
            "cmd.run_all", [cmd], runas=RUNTIME_VARS.RUNNING_TESTS_USER
        )
        errmsg = f"The command returned: {result}"
        self.assertEqual(result["retcode"], 0, errmsg)
        self.assertEqual(result["stdout"], expected_result, errmsg)

    @pytest.mark.destructive_test
    @pytest.mark.skip_if_not_root
    @pytest.mark.skip_on_windows(reason="Skip on Windows, uses unix commands")
    @pytest.mark.slow_test
    def test_avoid_injecting_shell_code_as_root(self):
        """
        cmd.run should execute the whole command as the "runas" user, not
        running substitutions as root.
        """
        cmd = "echo $(id -u)"

        root_id = self.run_function("cmd.run_stdout", [cmd])
        runas_root_id = self.run_function(
            "cmd.run_stdout", [cmd], runas=RUNTIME_VARS.RUNNING_TESTS_USER
        )
        with self._ensure_user_exists(self.runas_usr):
            user_id = self.run_function("cmd.run_stdout", [cmd], runas=self.runas_usr)

        self.assertNotEqual(user_id, root_id)
        self.assertNotEqual(user_id, runas_root_id)
        self.assertEqual(root_id, runas_root_id)

    @pytest.mark.destructive_test
    @pytest.mark.skip_if_not_root
    @pytest.mark.skip_on_windows(reason="Skip on Windows, uses unix commands")
    @pytest.mark.slow_test
    def test_cwd_runas(self):
        """
        cmd.run should be able to change working directory correctly, whether
        or not runas is in use.
        """
        cmd = "pwd"
        tmp_cwd = tempfile.mkdtemp(dir=RUNTIME_VARS.TMP)
        os.chmod(tmp_cwd, 0o711)

        cwd_normal = self.run_function("cmd.run_stdout", [cmd], cwd=tmp_cwd).rstrip(
            "\n"
        )
        self.assertEqual(tmp_cwd, cwd_normal)

        with self._ensure_user_exists(self.runas_usr):
            cwd_runas = self.run_function(
                "cmd.run_stdout", [cmd], cwd=tmp_cwd, runas=self.runas_usr
            ).rstrip("\n")
        self.assertEqual(tmp_cwd, cwd_runas)

    @pytest.mark.destructive_test
    @pytest.mark.skip_if_not_root
    @pytest.mark.skip_unless_on_darwin(reason="Applicable to MacOS only")
    @pytest.mark.slow_test
    def test_runas_env(self):
        """
        cmd.run should be able to change working directory correctly, whether
        or not runas is in use.
        """
        with self._ensure_user_exists(self.runas_usr):
            user_path = self.run_function(
                "cmd.run_stdout", ['printf %s "$PATH"'], runas=self.runas_usr
            )
        # XXX: Not sure of a better way. Environment starts out with
        # /bin:/usr/bin and should be populated by path helper and the bash
        # profile.
        self.assertNotEqual("/bin:/usr/bin", user_path)

    @pytest.mark.destructive_test
    @pytest.mark.skip_if_not_root
    @pytest.mark.skip_unless_on_darwin(reason="Applicable to MacOS only")
    @pytest.mark.slow_test
    def test_runas_complex_command_bad_cwd(self):
        """
        cmd.run should not accidentally run parts of a complex command when
        given a cwd which cannot be used by the user the command is run as.

        Due to the need to use `su -l` to login to another user on MacOS, we
        cannot cd into directories that the target user themselves does not
        have execute permission for. To an extent, this test is testing that
        buggy behaviour, but its purpose is to ensure that the greater bug of
        running commands after failing to cd does not occur.
        """
        tmp_cwd = tempfile.mkdtemp(dir=RUNTIME_VARS.TMP)
        os.chmod(tmp_cwd, 0o700)

        with self._ensure_user_exists(self.runas_usr):
            cmd_result = self.run_function(
                "cmd.run_all",
                ['pwd; pwd; : $(echo "You have failed the test" >&2)'],
                cwd=tmp_cwd,
                runas=self.runas_usr,
            )

        self.assertEqual("", cmd_result["stdout"])
        self.assertNotIn("You have failed the test", cmd_result["stderr"])
        self.assertNotEqual(0, cmd_result["retcode"])

    @SKIP_INITIAL_PHOTONOS_FAILURES
    @pytest.mark.skip_on_windows
    @pytest.mark.skip_if_not_root
    @pytest.mark.destructive_test
    @pytest.mark.slow_test
    def test_runas(self):
        """
        Ensure that the env is the runas user's
        """
        with self._ensure_user_exists(self.runas_usr):
            out = self.run_function(
                "cmd.run", ["env"], runas=self.runas_usr, cwd="/tmp"
            ).splitlines()
        self.assertIn(f"USER={self.runas_usr}", out)

    @pytest.mark.skip_if_binaries_missing("sleep", reason="sleep cmd not installed")
    def test_timeout(self):
        """
        cmd.run trigger timeout
        """
        out = self.run_function(
            "cmd.run", ["sleep 2 && echo hello"], f_timeout=1, python_shell=True
        )
        self.assertTrue("Timed out" in out)

    @pytest.mark.skip_if_binaries_missing("sleep", reason="sleep cmd not installed")
    def test_timeout_success(self):
        """
        cmd.run sufficient timeout to succeed
        """
        out = self.run_function(
            "cmd.run", ["sleep 1 && echo hello"], f_timeout=2, python_shell=True
        )
        self.assertEqual(out, "hello")

    @pytest.mark.slow_test
    def test_hide_output(self):
        """
        Test the hide_output argument
        """
        ls_command = (
            ["ls", "/"] if not salt.utils.platform.is_windows() else ["dir", "c:\\"]
        )

        error_command = ["thiscommanddoesnotexist"]

        # cmd.run
        out = self.run_function("cmd.run", ls_command, hide_output=True)
        self.assertEqual(out, "")

        # cmd.shell
        out = self.run_function("cmd.shell", ls_command, hide_output=True)
        self.assertEqual(out, "")

        # cmd.run_stdout
        out = self.run_function("cmd.run_stdout", ls_command, hide_output=True)
        self.assertEqual(out, "")

        # cmd.run_stderr
        out = self.run_function("cmd.shell", error_command, hide_output=True)
        self.assertEqual(out, "")

        # cmd.run_all (command should have produced stdout)
        out = self.run_function("cmd.run_all", ls_command, hide_output=True)
        self.assertEqual(out["stdout"], "")
        self.assertEqual(out["stderr"], "")

        # cmd.run_all (command should have produced stderr)
        out = self.run_function("cmd.run_all", error_command, hide_output=True)
        self.assertEqual(out["stdout"], "")
        self.assertEqual(out["stderr"], "")

    @pytest.mark.slow_test
    def test_cmd_run_whoami(self):
        """
        test return of whoami
        """
        if not salt.utils.platform.is_windows():
            user = RUNTIME_VARS.RUNTIME_CONFIGS["master"]["user"]
        else:
            user = salt.utils.user.get_specific_user()
        if user.startswith("sudo_"):
            user = user.replace("sudo_", "")
        cmd = self.run_function("cmd.run", ["whoami"])
        try:
            self.assertEqual(user.lower(), cmd.lower())
        except AssertionError as exc:
            if not salt.utils.platform.is_windows():
                raise exc from None
            if "\\" in user:
                user = user.split("\\")[-1]
            self.assertEqual(user.lower(), cmd.lower())

    @pytest.mark.skip_unless_on_windows(reason="Minion is not Windows")
    @pytest.mark.slow_test
    def test_windows_env_handling(self):
        """
        Ensure that nt.environ is used properly with cmd.run*
        """
        out = self.run_function(
            "cmd.run", ["set"], env={"abc": "123", "ABC": "456"}
        ).splitlines()
        self.assertIn("abc=123", out)
        self.assertIn("ABC=456", out)
