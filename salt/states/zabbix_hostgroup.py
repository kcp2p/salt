"""
Management of Zabbix host groups.

:codeauthor: Jiri Kotlin <jiri.kotlin@ultimum.io>


"""


def __virtual__():
    """
    Only make these states available if Zabbix module is available.
    """
    if "zabbix.hostgroup_create" in __salt__:
        return True
    return (False, "zabbix module could not be loaded")


def present(name, **kwargs):
    """
    Ensures that the host group exists, eventually creates new host group.

    .. versionadded:: 2016.3.0

    :param name: name of the host group
    :param _connection_user: Optional - zabbix user (can also be set in opts or pillar, see module's docstring)
    :param _connection_password: Optional - zabbix password (can also be set in opts or pillar, see module's docstring)
    :param _connection_url: Optional - url of zabbix frontend (can also be set in opts, pillar, see module's docstring)

    .. code-block:: yaml

        create_testing_host_group:
            zabbix_hostgroup.present:
                - name: 'My hostgroup name'


    """
    connection_args = {}
    if "_connection_user" in kwargs:
        connection_args["_connection_user"] = kwargs["_connection_user"]
    if "_connection_password" in kwargs:
        connection_args["_connection_password"] = kwargs["_connection_password"]
    if "_connection_url" in kwargs:
        connection_args["_connection_url"] = kwargs["_connection_url"]
    ret = {"name": name, "changes": {}, "result": False, "comment": ""}

    # Comment and change messages
    comment_hostgroup_created = f"Host group {name} created."
    comment_hostgroup_notcreated = f"Unable to create host group: {name}. "
    comment_hostgroup_exists = f"Host group {name} already exists."
    changes_hostgroup_created = {
        name: {
            "old": f"Host group {name} does not exist.",
            "new": f"Host group {name} created.",
        }
    }

    hostgroup_exists = __salt__["zabbix.hostgroup_exists"](name, **connection_args)

    # Dry run, test=true mode
    if __opts__["test"]:
        if hostgroup_exists:
            ret["result"] = True
            ret["comment"] = comment_hostgroup_exists
        else:
            ret["result"] = None
            ret["comment"] = comment_hostgroup_created
            ret["changes"] = changes_hostgroup_created
        return ret

    if hostgroup_exists:
        ret["result"] = True
        ret["comment"] = comment_hostgroup_exists
    else:
        hostgroup_create = __salt__["zabbix.hostgroup_create"](name, **connection_args)

        if "error" not in hostgroup_create:
            ret["result"] = True
            ret["comment"] = comment_hostgroup_created
            ret["changes"] = changes_hostgroup_created
        else:
            ret["result"] = False
            ret["comment"] = comment_hostgroup_notcreated + str(
                hostgroup_create["error"]
            )

    return ret


def absent(name, **kwargs):
    """
    Ensures that the host group does not exist, eventually delete host group.

    .. versionadded:: 2016.3.0

    :param name: name of the host group
    :param _connection_user: Optional - zabbix user (can also be set in opts or pillar, see module's docstring)
    :param _connection_password: Optional - zabbix password (can also be set in opts or pillar, see module's docstring)
    :param _connection_url: Optional - url of zabbix frontend (can also be set in opts, pillar, see module's docstring)

    .. code-block:: yaml

        delete_testing_host_group:
            zabbix_hostgroup.absent:
                - name: 'My hostgroup name'

    """

    ret = {"name": name, "changes": {}, "result": False, "comment": ""}

    # Comment and change messages
    comment_hostgroup_deleted = f"Host group {name} deleted."
    comment_hostgroup_notdeleted = f"Unable to delete host group: {name}. "
    comment_hostgroup_notexists = f"Host group {name} does not exist."
    changes_hostgroup_deleted = {
        name: {
            "old": f"Host group {name} exists.",
            "new": f"Host group {name} deleted.",
        }
    }

    connection_args = {}
    if "_connection_user" in kwargs:
        connection_args["_connection_user"] = kwargs["_connection_user"]
    if "_connection_password" in kwargs:
        connection_args["_connection_password"] = kwargs["_connection_password"]
    if "_connection_url" in kwargs:
        connection_args["_connection_url"] = kwargs["_connection_url"]

    hostgroup_exists = __salt__["zabbix.hostgroup_exists"](name, **connection_args)

    # Dry run, test=true mode
    if __opts__["test"]:
        if not hostgroup_exists:
            ret["result"] = True
            ret["comment"] = comment_hostgroup_notexists
        else:
            ret["result"] = None
            ret["comment"] = comment_hostgroup_deleted
            ret["changes"] = changes_hostgroup_deleted
        return ret

    hostgroup_get = __salt__["zabbix.hostgroup_get"](name, **connection_args)

    if not hostgroup_get:
        ret["result"] = True
        ret["comment"] = comment_hostgroup_notexists
    else:
        try:
            groupid = hostgroup_get[0]["groupid"]
            hostgroup_delete = __salt__["zabbix.hostgroup_delete"](
                groupid, **connection_args
            )
        except KeyError:
            hostgroup_delete = False

        if hostgroup_delete and "error" not in hostgroup_delete:
            ret["result"] = True
            ret["comment"] = comment_hostgroup_deleted
            ret["changes"] = changes_hostgroup_deleted
        else:
            ret["result"] = False
            ret["comment"] = comment_hostgroup_notdeleted + str(
                hostgroup_delete["error"]
            )

    return ret
