"""
States for managing Hashicorp Vault.
Currently handles policies. Configuration instructions are documented in the execution module docs.

:maintainer:    SaltStack
:maturity:      new
:platform:      all

.. versionadded:: 2017.7.0

"""

import difflib
import logging

log = logging.getLogger(__name__)


def policy_present(name, rules):
    """
    Ensure a Vault policy with the given name and rules is present.

    name
        The name of the policy

    rules
        Rules formatted as in-line HCL


    .. code-block:: yaml

        demo-policy:
          vault.policy_present:
            - name: foo/bar
            - rules: |
                path "secret/top-secret/*" {
                  policy = "deny"
                }
                path "secret/not-very-secret/*" {
                  policy = "write"
                }

    """
    url = f"v1/sys/policy/{name}"
    response = __utils__["vault.make_request"]("GET", url)
    try:
        if response.status_code == 200:
            return _handle_existing_policy(name, rules, response.json()["rules"])
        elif response.status_code == 404:
            return _create_new_policy(name, rules)
        else:
            response.raise_for_status()
    except Exception as e:  # pylint: disable=broad-except
        return {
            "name": name,
            "changes": {},
            "result": False,
            "comment": f"Failed to get policy: {e}",
        }


def _create_new_policy(name, rules):
    if __opts__["test"]:
        return {
            "name": name,
            "changes": {name: {"old": "", "new": rules}},
            "result": None,
            "comment": "Policy would be created",
        }

    payload = {"rules": rules}
    url = f"v1/sys/policy/{name}"
    response = __utils__["vault.make_request"]("PUT", url, json=payload)
    if response.status_code not in [200, 204]:
        return {
            "name": name,
            "changes": {},
            "result": False,
            "comment": f"Failed to create policy: {response.reason}",
        }

    return {
        "name": name,
        "result": True,
        "changes": {name: {"old": None, "new": rules}},
        "comment": "Policy was created",
    }


def _handle_existing_policy(name, new_rules, existing_rules):
    ret = {"name": name}
    if new_rules == existing_rules:
        ret["result"] = True
        ret["changes"] = {}
        ret["comment"] = "Policy exists, and has the correct content"
        return ret

    change = "".join(
        difflib.unified_diff(
            existing_rules.splitlines(True), new_rules.splitlines(True)
        )
    )
    if __opts__["test"]:
        ret["result"] = None
        ret["changes"] = {name: {"change": change}}
        ret["comment"] = "Policy would be changed"
        return ret

    payload = {"rules": new_rules}

    url = f"v1/sys/policy/{name}"
    response = __utils__["vault.make_request"]("PUT", url, json=payload)
    if response.status_code not in [200, 204]:
        return {
            "name": name,
            "changes": {},
            "result": False,
            "comment": f"Failed to change policy: {response.reason}",
        }

    ret["result"] = True
    ret["changes"] = {name: {"change": change}}
    ret["comment"] = "Policy was updated"

    return ret
