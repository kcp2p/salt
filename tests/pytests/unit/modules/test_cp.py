"""
    :codeauthor: jmoney <justin@saltstack.com>
"""

import pytest

import salt.channel.client
import salt.modules.cp as cp
import salt.utils.files
import salt.utils.platform
import salt.utils.templates as templates
from salt.exceptions import CommandExecutionError
from tests.support.mock import MagicMock, Mock, mock_open, patch


@pytest.fixture()
def configure_loader_modules():
    return {cp: {"__opts__": {"saltenv": None}}}


def test__render_filenames_undefined_template():
    """
    Test if _render_filenames fails upon getting a template not in
    TEMPLATE_REGISTRY.
    """
    path = "/srv/salt/saltines"
    dest = "/srv/salt/cheese"
    saltenv = "base"
    template = "biscuits"
    ret = (path, dest)
    pytest.raises(
        CommandExecutionError, cp._render_filenames, path, dest, saltenv, template
    )


def test__render_filenames_render_failed():
    """
    Test if _render_filenames fails when template rendering fails.
    """
    path = "salt://saltines"
    dest = "/srv/salt/cheese"
    saltenv = "base"
    template = "jinja"
    file_data = "Remember to keep your files well salted."

    def mock_jinja(*args, **kwargs):
        return {"result": False, "data": file_data}

    with patch.dict(templates.TEMPLATE_REGISTRY, {"jinja": mock_jinja}):
        with patch("salt.utils.files.fopen", mock_open(read_data=file_data)):
            pytest.raises(
                CommandExecutionError,
                cp._render_filenames,
                path,
                dest,
                saltenv,
                template,
            )


def test__render_filenames_success():
    """
    Test if _render_filenames succeeds.
    """
    path = "salt://saltines"
    dest = "/srv/salt/cheese"
    saltenv = "base"
    template = "jinja"
    file_data = "/srv/salt/biscuits"

    def mock_jinja(*args, **kwargs):
        return {"result": True, "data": file_data}

    ret = (file_data, file_data)  # salt.utils.files.fopen can only be mocked once
    with patch.dict(templates.TEMPLATE_REGISTRY, {"jinja": mock_jinja}):
        with patch("salt.utils.files.fopen", mock_open(read_data=file_data)):
            assert cp._render_filenames(path, dest, saltenv, template) == ret
            # saltenv=None should default to "base" when not set in config
            assert (
                cp._render_filenames(path, dest, saltenv=None, template=template) == ret
            )


def test_get_file_not_found():
    """
    Test if get_file can't find the file.
    """
    with patch("salt.modules.cp.hash_file", MagicMock(return_value=False)):
        path = "salt://saltines"
        dest = "/srv/salt/cheese"
        ret = ""
        assert cp.get_file(path, dest) == ret


def test_get_file_str_success():
    """
    Test if get_file_str succeeds.
    """
    path = "salt://saltines"
    dest = "/srv/salt/cheese/saltines"
    file_data = "Remember to keep your files well salted."
    saltenv = "base"
    ret = file_data
    with patch("salt.utils.files.fopen", mock_open(read_data=file_data)):
        with patch("salt.modules.cp.cache_file", MagicMock(return_value=dest)):
            assert cp.get_file_str(path, dest) == ret


def test_push_non_absolute_path():
    """
    Test if push fails on a non absolute path.
    """
    path = "../saltines"
    ret = False

    assert cp.push(path) == ret


def test_push_dir_non_absolute_path():
    """
    Test if push_dir fails on a non absolute path.
    """
    path = "../saltines"
    ret = False

    assert cp.push_dir(path) == ret


def test_push():
    """
    Test if push works with good posix path.
    """
    filename = "/saltines/test.file"
    if salt.utils.platform.is_windows():
        filename = "C:\\saltines\\test.file"
    with patch(
        "salt.modules.cp.os.path",
        MagicMock(isfile=Mock(return_value=True), wraps=cp.os.path),
    ), patch(
        "salt.modules.cp.os.path",
        MagicMock(getsize=MagicMock(return_value=10), wraps=cp.os.path),
    ), patch.multiple(
        "salt.modules.cp",
        _auth=MagicMock(**{"return_value.gen_token.return_value": "token"}),
        __opts__=salt.loader.dunder.__opts__.with_default(
            {"id": "abc", "file_buffer_size": 10}
        ),
    ), patch(
        "salt.utils.files.fopen", mock_open(read_data=b"content")
    ) as m_open, patch(
        "salt.channel.client.ReqChannel.factory", MagicMock()
    ) as req_channel_factory_mock:
        response = cp.push(filename)
        assert response, response
        num_opens = len(m_open.filehandles[filename])
        assert num_opens == 1, num_opens
        fh_ = m_open.filehandles[filename][0]
        assert fh_.read.call_count == 2, fh_.read.call_count

        req_channel_factory_mock().__enter__().send.assert_called_once_with(  # pylint: disable=unnecessary-dunder-call
            dict(
                loc=fh_.tell(),  # pylint: disable=resource-leakage
                cmd="_file_recv",
                path=["saltines", "test.file"],
                size=10,
                data=b"",  # data is empty here because load['data'] is overwritten
                id="abc",
            )
        )
