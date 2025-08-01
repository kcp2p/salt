"""
This package contains the loader modules for the salt streams system
"""

import copy
import logging
import re
import sys

import salt.utils.event
import salt.utils.minion

log = logging.getLogger(__name__)


class Beacon:
    """
    This class is used to evaluate and execute on the beacon system
    """

    def __init__(self, opts, functions):
        import salt.loader

        self.opts = opts
        self.functions = functions
        self.beacons = salt.loader.beacons(opts, functions)
        self.interval_map = dict()

    def process(self, config, grains):
        """
        Process the configured beacons

        The config must be a list and looks like this in yaml

        .. code_block:: yaml
            beacons:
              inotify:
                - files:
                    - /etc/fstab: {}
                    - /var/cache/foo: {}
        """
        ret = []
        b_config = copy.deepcopy(config)
        if "enabled" in b_config and not b_config["enabled"]:
            return
        for mod in config:
            if mod == "enabled":
                continue

            # Convert beacons that are lists to a dict to make processing easier
            current_beacon_config = None
            if isinstance(config[mod], list):
                current_beacon_config = {}
                list(map(current_beacon_config.update, config[mod]))
            elif isinstance(config[mod], dict):
                current_beacon_config = config[mod]

            if "enabled" in current_beacon_config:
                if not current_beacon_config["enabled"]:
                    log.trace("Beacon %s disabled", mod)
                    continue
                else:
                    # remove 'enabled' item before processing the beacon
                    if isinstance(config[mod], dict):
                        del config[mod]["enabled"]
                    else:
                        self._remove_list_item(config[mod], "enabled")

            log.trace("Beacon processing: %s", mod)
            beacon_name = None
            if self._determine_beacon_config(current_beacon_config, "beacon_module"):
                beacon_name = current_beacon_config["beacon_module"]
            else:
                beacon_name = mod

            # Run the validate function if it's available,
            # otherwise there is a warning about it being missing
            validate_str = f"{beacon_name}.validate"
            if validate_str in self.beacons:
                valid, vcomment = self.beacons[validate_str](b_config[mod])

                if not valid:
                    log.error(
                        "Beacon %s configuration invalid, not running.\n%s",
                        mod,
                        vcomment,
                    )
                    continue
            else:
                log.warning(
                    "No validate function found for %s, running basic beacon validation.",
                    mod,
                )
                if not isinstance(b_config[mod], list):
                    log.error("Configuration for beacon must be a list.")
                    continue

            b_config[mod].append({"_beacon_name": mod})
            fun_str = f"{beacon_name}.beacon"
            if fun_str in self.beacons:
                runonce = self._determine_beacon_config(
                    current_beacon_config, "run_once"
                )
                interval = self._determine_beacon_config(
                    current_beacon_config, "interval"
                )
                if interval:
                    b_config = self._trim_config(b_config, mod, "interval")
                    if not self._process_interval(mod, interval):
                        log.trace("Skipping beacon %s. Interval not reached.", mod)
                        continue
                if self._determine_beacon_config(
                    current_beacon_config, "disable_during_state_run"
                ):
                    log.trace(
                        "Evaluting if beacon %s should be skipped due to a state run.",
                        mod,
                    )
                    b_config = self._trim_config(
                        b_config, mod, "disable_during_state_run"
                    )
                    is_running = False
                    running_jobs = salt.utils.minion.running(self.opts)
                    for job in running_jobs:
                        if re.match("state.*", job["fun"]):
                            is_running = True
                    if is_running:
                        close_str = f"{beacon_name}.close"
                        if close_str in self.beacons:
                            log.info("Closing beacon %s. State run in progress.", mod)
                            self.beacons[close_str](b_config[mod])
                        else:
                            log.info("Skipping beacon %s. State run in progress.", mod)
                        continue
                # Update __grains__ on the beacon
                self.beacons[fun_str].__globals__["__grains__"] = grains

                # Fire the beacon!
                error = None
                try:
                    raw = self.beacons[fun_str](b_config[mod])
                except:  # pylint: disable=bare-except
                    error = f"{sys.exc_info()[1]}"
                    log.error("Unable to start %s beacon, %s", mod, error)
                    # send beacon error event
                    tag = "salt/beacon/{}/{}/".format(self.opts["id"], mod)
                    ret.append(
                        {
                            "tag": tag,
                            "error": error,
                            "data": {},
                            "beacon_name": beacon_name,
                        }
                    )
                if not error:
                    for data in raw:
                        tag = "salt/beacon/{}/{}/".format(self.opts["id"], mod)
                        if "tag" in data:
                            tag += data.pop("tag")
                        if "id" not in data:
                            data["id"] = self.opts["id"]
                        ret.append(
                            {"tag": tag, "data": data, "beacon_name": beacon_name}
                        )
                    if runonce:
                        self.disable_beacon(mod)
            else:
                log.warning("Unable to process beacon %s", mod)
        return ret

    def _trim_config(self, b_config, mod, key):
        """
        Take a beacon configuration and strip out the interval bits
        """
        if isinstance(b_config[mod], list):
            self._remove_list_item(b_config[mod], key)
        elif isinstance(b_config[mod], dict):
            b_config[mod].pop(key)
        return b_config

    def _determine_beacon_config(self, current_beacon_config, key):
        """
        Process a beacon configuration to determine its interval
        """

        interval = False
        if isinstance(current_beacon_config, dict):
            interval = current_beacon_config.get(key, False)

        return interval

    def _process_interval(self, mod, interval):
        """
        Process beacons with intervals
        Return True if a beacon should be run on this loop
        """
        log.trace("Processing interval %s for beacon mod %s", interval, mod)
        loop_interval = self.opts["loop_interval"]
        if mod in self.interval_map:
            log.trace("Processing interval in map")
            counter = self.interval_map[mod]
            log.trace("Interval counter: %s", counter)
            if counter * loop_interval >= interval:
                self.interval_map[mod] = 1
                return True
            else:
                self.interval_map[mod] += 1
        else:
            log.trace("Interval process inserting mod: %s", mod)
            self.interval_map[mod] = 1
        return False

    def _get_index(self, beacon_config, label):
        """
        Return the index of a labeled config item in the beacon config, -1 if the index is not found
        """

        indexes = [index for index, item in enumerate(beacon_config) if label in item]
        if not indexes:
            return -1
        else:
            return indexes[0]

    def _remove_list_item(self, beacon_config, label):
        """
        Remove an item from a beacon config list
        """

        index = self._get_index(beacon_config, label)
        del beacon_config[index]

    def _update_enabled(self, name, enabled_value):
        """
        Update whether an individual beacon is enabled
        """

        if isinstance(self.opts["beacons"][name], dict):
            # Backwards compatibility
            self.opts["beacons"][name]["enabled"] = enabled_value
        else:
            enabled_index = self._get_index(self.opts["beacons"][name], "enabled")
            if enabled_index >= 0:
                self.opts["beacons"][name][enabled_index]["enabled"] = enabled_value
            else:
                self.opts["beacons"][name].append({"enabled": enabled_value})

    def _get_beacons(self, include_opts=True, include_pillar=True):
        """
        Return the beacons data structure
        """
        beacons = {}
        if include_pillar:
            pillar_beacons = self.opts.get("pillar", {}).get("beacons", {})
            if not isinstance(pillar_beacons, dict):
                raise ValueError("Beacons must be of type dict.")
            beacons.update(pillar_beacons)
        if include_opts:
            opts_beacons = self.opts.get("beacons", {})
            if not isinstance(opts_beacons, dict):
                raise ValueError("Beacons must be of type dict.")
            beacons.update(opts_beacons)
        return beacons

    def list_beacons(self, include_pillar=True, include_opts=True):
        """
        List the beacon items

        include_pillar: Whether to include beacons that are
                        configured in pillar, default is True.

        include_opts:   Whether to include beacons that are
                        configured in opts, default is True.
        """
        beacons = self._get_beacons(
            include_pillar=include_pillar, include_opts=include_opts
        )

        # Fire the complete event back along with the list of beacons
        with salt.utils.event.get_event("minion", opts=self.opts) as evt:
            evt.fire_event(
                {"complete": True, "beacons": beacons},
                tag="/salt/minion/minion_beacons_list_complete",
            )

        return True

    def list_available_beacons(self):
        """
        List the available beacons
        """
        _beacons = [
            "{}".format(_beacon.replace(".beacon", ""))
            for _beacon in self.beacons
            if ".beacon" in _beacon
        ]

        # Fire the complete event back along with the list of beacons
        with salt.utils.event.get_event("minion", opts=self.opts) as evt:
            evt.fire_event(
                {"complete": True, "beacons": _beacons},
                tag="/salt/minion/minion_beacons_list_available_complete",
            )

        return True

    def validate_beacon(self, name, beacon_data):
        """
        Return available beacon functions
        """
        beacon_name = next(item.get("beacon_module", name) for item in beacon_data)

        validate_str = f"{beacon_name}.validate"
        # Run the validate function if it's available,
        # otherwise there is a warning about it being missing
        if validate_str in self.beacons:
            if "enabled" in beacon_data:
                del beacon_data["enabled"]
            valid, vcomment = self.beacons[validate_str](beacon_data)
        else:
            vcomment = (
                "Beacon {} does not have a validate"
                " function, skipping validation.".format(beacon_name)
            )
            valid = True

        # Fire the complete event back along with the list of beacons
        with salt.utils.event.get_event("minion", opts=self.opts) as evt:
            evt.fire_event(
                {"complete": True, "vcomment": vcomment, "valid": valid},
                tag="/salt/minion/minion_beacon_validation_complete",
            )

        return True

    def add_beacon(self, name, beacon_data):
        """
        Add a beacon item
        """

        data = {}
        data[name] = beacon_data

        if name in self._get_beacons(include_opts=False):
            comment = (
                "Cannot update beacon item {}, "
                "because it is configured in pillar.".format(name)
            )
            complete = False
        else:
            if name in self.opts["beacons"]:
                comment = f"Updating settings for beacon item: {name}"
            else:
                comment = f"Added new beacon item: {name}"
            complete = True
            self.opts["beacons"].update(data)

        # Fire the complete event back along with updated list of beacons
        with salt.utils.event.get_event("minion", opts=self.opts) as evt:
            evt.fire_event(
                {
                    "complete": complete,
                    "comment": comment,
                    "beacons": self.opts["beacons"],
                },
                tag="/salt/minion/minion_beacon_add_complete",
            )

        return True

    def modify_beacon(self, name, beacon_data):
        """
        Modify a beacon item
        """

        data = {}
        data[name] = beacon_data

        if name in self._get_beacons(include_opts=False):
            comment = f"Cannot modify beacon item {name}, it is configured in pillar."
            complete = False
        else:
            comment = f"Updating settings for beacon item: {name}"
            complete = True
            self.opts["beacons"].update(data)

        # Fire the complete event back along with updated list of beacons
        with salt.utils.event.get_event("minion", opts=self.opts) as evt:
            evt.fire_event(
                {
                    "complete": complete,
                    "comment": comment,
                    "beacons": self.opts["beacons"],
                },
                tag="/salt/minion/minion_beacon_modify_complete",
            )
        return True

    def delete_beacon(self, name):
        """
        Delete a beacon item
        """

        if name in self._get_beacons(include_opts=False):
            comment = f"Cannot delete beacon item {name}, it is configured in pillar."
            complete = False
        else:
            if name in self.opts["beacons"]:
                del self.opts["beacons"][name]
                comment = f"Deleting beacon item: {name}"
            else:
                comment = f"Beacon item {name} not found."
            complete = True

        # Fire the complete event back along with updated list of beacons
        with salt.utils.event.get_event("minion", opts=self.opts) as evt:
            evt.fire_event(
                {
                    "complete": complete,
                    "comment": comment,
                    "beacons": self.opts["beacons"],
                },
                tag="/salt/minion/minion_beacon_delete_complete",
            )

        return True

    def enable_beacons(self):
        """
        Enable beacons
        """

        self.opts["beacons"]["enabled"] = True

        # Fire the complete event back along with updated list of beacons
        with salt.utils.event.get_event("minion", opts=self.opts) as evt:
            evt.fire_event(
                {"complete": True, "beacons": self.opts["beacons"]},
                tag="/salt/minion/minion_beacons_enabled_complete",
            )

        return True

    def disable_beacons(self):
        """
        Enable beacons
        """

        self.opts["beacons"]["enabled"] = False

        # Fire the complete event back along with updated list of beacons
        with salt.utils.event.get_event("minion", opts=self.opts) as evt:
            evt.fire_event(
                {"complete": True, "beacons": self.opts["beacons"]},
                tag="/salt/minion/minion_beacons_disabled_complete",
            )

        return True

    def enable_beacon(self, name):
        """
        Enable a beacon
        """

        if name in self._get_beacons(include_opts=False):
            comment = f"Cannot enable beacon item {name}, it is configured in pillar."
            complete = False
        else:
            self._update_enabled(name, True)
            comment = f"Enabling beacon item {name}"
            complete = True

        # Fire the complete event back along with updated list of beacons
        with salt.utils.event.get_event("minion", opts=self.opts) as evt:
            evt.fire_event(
                {
                    "complete": complete,
                    "comment": comment,
                    "beacons": self.opts["beacons"],
                },
                tag="/salt/minion/minion_beacon_enabled_complete",
            )

        return True

    def disable_beacon(self, name):
        """
        Disable a beacon
        """

        if name in self._get_beacons(include_opts=False):
            comment = (
                "Cannot disable beacon item {}, it is configured in pillar.".format(
                    name
                )
            )
            complete = False
        else:
            self._update_enabled(name, False)
            comment = f"Disabling beacon item {name}"
            complete = True

        # Fire the complete event back along with updated list of beacons
        with salt.utils.event.get_event("minion", opts=self.opts) as evt:
            evt.fire_event(
                {
                    "complete": complete,
                    "comment": comment,
                    "beacons": self.opts["beacons"],
                },
                tag="/salt/minion/minion_beacon_disabled_complete",
            )

        return True

    def reset(self):
        """
        Reset the beacons to defaults
        """
        self.opts["beacons"] = {}
        with salt.utils.event.get_event("minion", opts=self.opts) as evt:
            evt.fire_event(
                {
                    "complete": True,
                    "comment": "Beacons have been reset",
                    "beacons": self.opts["beacons"],
                },
                tag="/salt/minion/minion_beacon_reset_complete",
            )
        return True
