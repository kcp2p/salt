"""
Encapsulate the different transports available to Salt.

This includes server side transport, for the ReqServer and the Publisher
"""

import binascii
import hashlib
import logging
import os
import pathlib
import shutil
import time

import salt.crypt
import salt.ext.tornado.gen
import salt.master
import salt.payload
import salt.transport.frame
import salt.utils.channel
import salt.utils.event
import salt.utils.files
import salt.utils.minions
import salt.utils.platform
import salt.utils.stringutils
import salt.utils.verify
from salt.exceptions import SaltDeserializationError, UnsupportedAlgorithm
from salt.utils.cache import CacheCli

log = logging.getLogger(__name__)


class ReqServerChannel:
    """
    ReqServerChannel handles request/reply messages from ReqChannels.
    """

    @classmethod
    def factory(cls, opts, **kwargs):
        if "master_uri" not in opts and "master_uri" in kwargs:
            opts["master_uri"] = kwargs["master_uri"]
        transport = salt.transport.request_server(opts, **kwargs)
        return cls(opts, transport)

    @classmethod
    def compare_keys(cls, key1, key2):
        """
        Normalize and compare two keys

        Returns:
            bool: ``True`` if the keys match, otherwise ``False``
        """
        return salt.crypt.clean_key(key1) == salt.crypt.clean_key(key2)

    def __init__(self, opts, transport):
        self.opts = opts
        self.transport = transport
        # The event and master_key attributes will be populated after fork.
        self.event = None
        self.master_key = None
        (pathlib.Path(self.opts["cachedir"]) / "sessions").mkdir(exist_ok=True)
        self.sessions = {}

    def session_key(self, minion):
        """
        Returns a session key for the given minion id.
        """
        now = time.time()
        if minion in self.sessions:
            if now - self.sessions[minion][0] < self.opts["publish_session"]:
                return self.sessions[minion][1]

        path = pathlib.Path(self.opts["cachedir"]) / "sessions" / minion
        try:
            if now - path.stat().st_mtime > self.opts["publish_session"]:
                salt.crypt.Crypticle.write_key(path)
        except FileNotFoundError:
            salt.crypt.Crypticle.write_key(path)

        self.sessions[minion] = (
            path.stat().st_mtime,
            salt.crypt.Crypticle.read_key(path),
        )
        return self.sessions[minion][1]

    def pre_fork(self, process_manager):
        """
        Do anything necessary pre-fork. Since this is on the master side this will
        primarily be bind and listen (or the equivalent for your network library)
        """
        if hasattr(self.transport, "pre_fork"):
            self.transport.pre_fork(process_manager)

    def post_fork(self, payload_handler, io_loop):
        """
        Do anything you need post-fork. This should handle all incoming payloads
        and call payload_handler. You will also be passed io_loop, for all of your
        asynchronous needs
        """
        import salt.master

        if self.opts["pub_server_niceness"] and not salt.utils.platform.is_windows():
            log.info(
                "setting Publish daemon niceness to %i",
                self.opts["pub_server_niceness"],
            )
            os.nice(self.opts["pub_server_niceness"])
        self.io_loop = io_loop
        self.crypticle = salt.crypt.Crypticle(
            self.opts, salt.master.SMaster.secrets["aes"]["secret"].value
        )
        # other things needed for _auth
        # Create the event manager
        self.event = salt.utils.event.get_master_event(
            self.opts, self.opts["sock_dir"], listen=False, io_loop=io_loop
        )
        self.auto_key = salt.daemons.masterapi.AutoKey(self.opts)
        # only create a con_cache-client if the con_cache is active
        if self.opts["con_cache"]:
            self.cache_cli = CacheCli(self.opts)
        else:
            self.cache_cli = False
            # Make an minion checker object
            self.ckminions = salt.utils.minions.CkMinions(self.opts)
        self.master_key = salt.crypt.MasterKeys(self.opts)
        self.payload_handler = payload_handler
        if hasattr(self.transport, "post_fork"):
            self.transport.post_fork(self.handle_message, io_loop)

    @salt.ext.tornado.gen.coroutine
    def handle_message(self, payload):
        if (
            not isinstance(payload, dict)
            or "enc" not in payload
            or "load" not in payload
        ):
            log.warn("bad load received on socket")
            raise salt.ext.tornado.gen.Return("bad load")
        version = payload.get("version", 0)
        try:
            payload = self._decode_payload(payload, version)
        except Exception as exc:  # pylint: disable=broad-except
            exc_type = type(exc).__name__
            if exc_type == "AuthenticationError":
                log.debug(
                    "Minion failed to auth to master. Since the payload is "
                    "encrypted, it is not known which minion failed to "
                    "authenticate. It is likely that this is a transient "
                    "failure due to the master rotating its public key."
                )
            else:
                log.error("Bad load from minion: %s: %s", exc_type, exc)
            raise salt.ext.tornado.gen.Return("bad load")

        # TODO helper functions to normalize payload?
        if not isinstance(payload, dict) or not isinstance(payload.get("load"), dict):
            log.error(
                "payload and load must be a dict. Payload was: %s and load was %s",
                payload,
                payload.get("load"),
            )
            raise salt.ext.tornado.gen.Return("payload and load must be a dict")

        try:
            id_ = payload["load"].get("id", "")
            if "\0" in id_:
                log.error("Payload contains an id with a null byte: %s", payload)
                raise salt.ext.tornado.gen.Return("bad load: id contains a null byte")
        except TypeError:
            log.error("Payload contains non-string id: %s", payload)
            raise salt.ext.tornado.gen.Return(f"bad load: id {id_} is not a string")

        sign_messages = False
        if version > 1:
            sign_messages = True

        # intercept the "_auth" commands, since the main daemon shouldn't know
        # anything about our key auth
        if payload["enc"] == "clear" and payload.get("load", {}).get("cmd") == "_auth":
            raise salt.ext.tornado.gen.Return(
                self._auth(payload["load"], sign_messages, version)
            )

        if payload["enc"] == "aes":
            nonce = None
            if version > 1:
                nonce = payload["load"].pop("nonce", None)

            # Check validity of message ttl and id's match
            if version > 2:
                if self.opts["request_server_ttl"] > 0:
                    ttl = time.time() - payload["load"]["ts"]
                    if ttl > self.opts["request_server_ttl"]:
                        log.warning(
                            "Received request from %s with expired ttl: %d > %d",
                            payload["load"]["id"],
                            ttl,
                            self.opts["request_server_ttl"],
                        )
                        raise salt.ext.tornado.gen.Return("bad load")

                if payload["id"] != payload["load"]["id"]:
                    log.warning(
                        "Request id mismatch. Found '%s' but expected '%s'",
                        payload["load"]["id"],
                        payload["id"],
                    )
                    raise salt.ext.tornado.gen.Return("bad load")
                if not salt.utils.verify.valid_id(self.opts, payload["load"]["id"]):
                    log.warning(
                        "Request contains invalid minion id '%s'", payload["load"]["id"]
                    )
                    raise salt.ext.tornado.gen.Return("bad load")
                if not self.validate_token(payload, required=True):
                    raise salt.ext.tornado.gen.Return("bad load")
            # The token won't always be present in the payload for v2 and
            # below, but if it is we always wanto validate it.
            elif not self.validate_token(payload, required=False):
                raise salt.ext.tornado.gen.Return("bad load")

        # TODO: test
        try:
            # Take the payload_handler function that was registered when we created the channel
            # and call it, returning control to the caller until it completes
            ret, req_opts = yield self.payload_handler(payload)
        except Exception as e:  # pylint: disable=broad-except
            # always attempt to return an error to the minion
            log.error("Some exception handling a payload from minion", exc_info=True)
            raise salt.ext.tornado.gen.Return("Some exception handling minion payload")

        req_fun = req_opts.get("fun", "send")
        if req_fun == "send_clear":
            raise salt.ext.tornado.gen.Return(ret)
        elif req_fun == "send":
            if version > 2:
                raise salt.ext.tornado.gen.Return(
                    salt.crypt.Crypticle(self.opts, self.session_key(id_)).dumps(
                        ret, nonce
                    )
                )
            else:
                raise salt.ext.tornado.gen.Return(self.crypticle.dumps(ret, nonce))
        elif req_fun == "send_private":
            raise salt.ext.tornado.gen.Return(
                self._encrypt_private(
                    ret,
                    req_opts["key"],
                    req_opts["tgt"],
                    nonce,
                    sign_messages,
                    payload.get("enc_algo", salt.crypt.OAEP_SHA1),
                    payload.get("sig_algo", salt.crypt.PKCS1v15_SHA1),
                ),
            )
        log.error("Unknown req_fun %s", req_fun)
        # always attempt to return an error to the minion
        raise salt.ext.tornado.gen.Return("Server-side exception handling payload")

    def _encrypt_private(
        self,
        ret,
        dictkey,
        target,
        nonce=None,
        sign_messages=True,
        encryption_algorithm=salt.crypt.OAEP_SHA1,
        signing_algorithm=salt.crypt.PKCS1v15_SHA1,
    ):
        """
        The server equivalent of ReqChannel.crypted_transfer_decode_dictentry
        """
        # encrypt with a specific AES key
        pubfn = os.path.join(self.opts["pki_dir"], "minions", target)
        key = salt.crypt.Crypticle.generate_key_string()
        pcrypt = salt.crypt.Crypticle(self.opts, key)
        try:
            pub = salt.crypt.PublicKey(pubfn)
        except (ValueError, IndexError, TypeError):
            log.error("Bad load from minion")
            return {"error": "bad load"}
        except OSError:
            log.error("AES key not found")
            return {"error": "AES key not found"}
        pret = {}
        pret["key"] = pub.encrypt(
            salt.utils.stringutils.to_bytes(key), encryption_algorithm
        )
        if ret is False:
            ret = {}
        if sign_messages:
            if nonce is None:
                return {"error": "Nonce not included in request"}
            tosign = salt.payload.dumps(
                {"key": pret["key"], "pillar": ret, "nonce": nonce}
            )
            master_pem_path = os.path.join(self.opts["pki_dir"], "master.pem")
            signed_msg = {
                "data": tosign,
                "sig": salt.crypt.PrivateKey(master_pem_path).sign(
                    tosign, algorithm=signing_algorithm
                ),
            }
            pret[dictkey] = pcrypt.dumps(signed_msg)
        else:
            pret[dictkey] = pcrypt.dumps(ret)
        return pret

    def _clear_signed(self, load, algorithm):
        try:
            master_pem_path = os.path.join(self.opts["pki_dir"], "master.pem")
            tosign = salt.payload.dumps(load)
            return {
                "enc": "clear",
                "load": tosign,
                "sig": salt.crypt.PrivateKey(master_pem_path).sign(
                    tosign, algorithm=algorithm
                ),
            }
        except UnsupportedAlgorithm:
            log.info(
                "Minion tried to authenticate with unsupported signing algorithm: %s",
                algorithm,
            )
            return {"enc": "clear", "load": {"ret": "bad sig algo"}}

    def _update_aes(self):
        """
        Check to see if a fresh AES key is available and update the components
        of the worker
        """
        import salt.master

        if (
            salt.master.SMaster.secrets["aes"]["secret"].value
            != self.crypticle.key_string
        ):
            self.crypticle = salt.crypt.Crypticle(
                self.opts, salt.master.SMaster.secrets["aes"]["secret"].value
            )
            return True
        return False

    def _decode_payload(self, payload, version):
        # we need to decrypt it
        if payload["enc"] == "aes":
            if version > 2:
                if salt.utils.verify.valid_id(self.opts, payload["id"]):
                    payload["load"] = salt.crypt.Crypticle(
                        self.opts,
                        self.session_key(payload["id"]),
                    ).loads(payload["load"])
                else:
                    raise SaltDeserializationError("Encountered invalid id")
            else:
                try:
                    payload["load"] = self.crypticle.loads(payload["load"])
                except salt.crypt.AuthenticationError:
                    if not self._update_aes():
                        raise
                    payload["load"] = self.crypticle.loads(payload["load"])
        return payload

    def validate_token(self, payload, required=True):
        """
        Validate the token (tok) and minion id (id) in the payload. If the
        payload and token exist they will be validated even if required is
        False.

        When required is False and either the tok or id is not found in the
        load, this check will pass.

        This method has a side effect of removing the 'tok' key from the load
        so that it is not passed along to request handlers.
        """
        tok = payload["load"].pop("tok", None)
        id_ = payload["load"].get("id", None)
        if tok is not None and id_ is not None:
            if "cluster_id" in self.opts and self.opts["cluster_id"]:
                pki_dir = self.opts["cluster_pki_dir"]
            else:
                pki_dir = self.opts.get("pki_dir", "")
            try:
                pub_path = salt.utils.verify.clean_join(pki_dir, "minions", id_)
            except salt.exceptions.SaltValidationError:
                log.warning("Invalid minion id: %s", id_)
                return False
            try:
                pub = salt.crypt.PublicKey(pub_path)
            except OSError:
                log.warning(
                    "Salt minion claiming to be %s attempted to communicate with "
                    "master, but key could not be read and verification was denied.",
                    id_,
                )
                return False
            try:
                if pub.decrypt(tok) != b"salt":
                    log.error("Minion token did not validate: %s", id_)
                    return False
            except ValueError as err:
                log.error("Unable to decrypt token: %s", err)
                return False
        elif required:
            return False
        return True

    def _auth(self, load, sign_messages=False, version=0):
        """
        Authenticate the client, use the sent public key to encrypt the AES key
        which was generated at start up.

        This method fires an event over the master event manager. The event is
        tagged "auth" and returns a dict with information about the auth
        event

            - Verify that the key we are receiving matches the stored key
            - Store the key if it is not there
            - Make an RSA key with the pub key
            - Encrypt the AES key as an encrypted salt.payload
            - Package the return and return it
        """
        import salt.master

        enc_algo = load.get("enc_algo", salt.crypt.OAEP_SHA1)
        sig_algo = load.get("sig_algo", salt.crypt.PKCS1v15_SHA1)

        if not salt.utils.verify.valid_id(self.opts, load["id"]):
            log.info("Authentication request from invalid id %s", load["id"])
            if sign_messages:
                return self._clear_signed(
                    {"ret": False, "nonce": load["nonce"]}, sig_algo
                )
            else:
                return {"enc": "clear", "load": {"ret": False}}
        log.info("Authentication request from %s", load["id"])

        # 0 is default which should be 'unlimited'
        if self.opts["max_minions"] > 0:
            # use the ConCache if enabled, else use the minion utils
            if self.cache_cli:
                minions = self.cache_cli.get_cached()
            else:
                minions = self.ckminions.connected_ids()
                if len(minions) > 1000:
                    log.info(
                        "With large numbers of minions it is advised "
                        "to enable the ConCache with 'con_cache: True' "
                        "in the masters configuration file."
                    )

            if not len(minions) <= self.opts["max_minions"]:
                # we reject new minions, minions that are already
                # connected must be allowed for the mine, highstate, etc.
                if load["id"] not in minions:
                    log.info(
                        "Too many minions connected (max_minions=%s). "
                        "Rejecting connection from id %s",
                        self.opts["max_minions"],
                        load["id"],
                    )
                    eload = {
                        "result": False,
                        "act": "full",
                        "id": load["id"],
                        "pub": load["pub"],
                    }

                    if self.opts.get("auth_events") is True:
                        self.event.fire_event(
                            eload, salt.utils.event.tagify(prefix="auth")
                        )
                    if sign_messages:
                        return self._clear_signed(
                            {"ret": "full", "nonce": load["nonce"]}, sig_algo
                        )
                    else:
                        return {"enc": "clear", "load": {"ret": "full"}}

        # Check if key is configured to be auto-rejected/signed
        auto_reject = self.auto_key.check_autoreject(load["id"])
        auto_sign = self.auto_key.check_autosign(
            load["id"], load.get("autosign_grains", None)
        )

        pubfn = os.path.join(self.opts["pki_dir"], "minions", load["id"])
        pubfn_pend = os.path.join(self.opts["pki_dir"], "minions_pre", load["id"])
        pubfn_rejected = os.path.join(
            self.opts["pki_dir"], "minions_rejected", load["id"]
        )
        pubfn_denied = os.path.join(self.opts["pki_dir"], "minions_denied", load["id"])
        if self.opts["open_mode"]:
            # open mode is turned on, nuts to checks and overwrite whatever
            # is there
            pass
        elif os.path.isfile(pubfn_rejected):
            # The key has been rejected, don't place it in pending
            log.info(
                "Public key rejected for %s. Key is present in rejection key dir.",
                load["id"],
            )
            eload = {"result": False, "id": load["id"], "pub": load["pub"]}
            if self.opts.get("auth_events") is True:
                self.event.fire_event(eload, salt.utils.event.tagify(prefix="auth"))
            if sign_messages:
                return self._clear_signed(
                    {"ret": False, "nonce": load["nonce"]}, sig_algo
                )
            else:
                return {"enc": "clear", "load": {"ret": False}}
        elif os.path.isfile(pubfn):
            # The key has been accepted, check it
            with salt.utils.files.fopen(pubfn, "r") as pubfn_handle:
                if not self.compare_keys(pubfn_handle.read(), load["pub"]):
                    log.error(
                        "Authentication attempt from %s failed, the public "
                        "keys did not match. This may be an attempt to compromise "
                        "the Salt cluster.",
                        load["id"],
                    )
                    # put denied minion key into minions_denied
                    with salt.utils.files.fopen(pubfn_denied, "w+") as fp_:
                        fp_.write(load["pub"])
                    eload = {
                        "result": False,
                        "id": load["id"],
                        "act": "denied",
                        "pub": load["pub"],
                    }
                    if self.opts.get("auth_events") is True:
                        self.event.fire_event(
                            eload, salt.utils.event.tagify(prefix="auth")
                        )
                    if sign_messages:
                        return self._clear_signed(
                            {"ret": False, "nonce": load["nonce"]}, sig_algo
                        )
                    else:
                        return {"enc": "clear", "load": {"ret": False}}

        elif not os.path.isfile(pubfn_pend):
            # The key has not been accepted, this is a new minion
            if os.path.isdir(pubfn_pend):
                # The key path is a directory, error out
                log.info("New public key %s is a directory", load["id"])
                eload = {"result": False, "id": load["id"], "pub": load["pub"]}
                if self.opts.get("auth_events") is True:
                    self.event.fire_event(eload, salt.utils.event.tagify(prefix="auth"))
                if sign_messages:
                    return self._clear_signed(
                        {"ret": False, "nonce": load["nonce"]}, sig_algo
                    )
                else:
                    return {"enc": "clear", "load": {"ret": False}}

            if auto_reject:
                key_path = pubfn_rejected
                log.info(
                    "New public key for %s rejected via autoreject_file", load["id"]
                )
                key_act = "reject"
                key_result = False
            elif not auto_sign:
                key_path = pubfn_pend
                log.info("New public key for %s placed in pending", load["id"])
                key_act = "pend"
                key_result = True
            else:
                # The key is being automatically accepted, don't do anything
                # here and let the auto accept logic below handle it.
                key_path = None

            if key_path is not None:
                # Write the key to the appropriate location
                with salt.utils.files.fopen(key_path, "w+") as fp_:
                    fp_.write(load["pub"])
                eload = {
                    "result": key_result,
                    "act": key_act,
                    "id": load["id"],
                    "pub": load["pub"],
                }
                if self.opts.get("auth_events") is True:
                    self.event.fire_event(eload, salt.utils.event.tagify(prefix="auth"))
                if sign_messages:
                    return self._clear_signed(
                        {"ret": key_result, "nonce": load["nonce"]},
                        sig_algo,
                    )
                else:
                    return {"enc": "clear", "load": {"ret": key_result}}

        elif os.path.isfile(pubfn_pend):
            # This key is in the pending dir and is awaiting acceptance
            if auto_reject:
                # We don't care if the keys match, this minion is being
                # auto-rejected. Move the key file from the pending dir to the
                # rejected dir.
                try:
                    shutil.move(pubfn_pend, pubfn_rejected)
                except OSError:
                    pass
                log.info(
                    "Pending public key for %s rejected via autoreject_file",
                    load["id"],
                )
                eload = {
                    "result": False,
                    "act": "reject",
                    "id": load["id"],
                    "pub": load["pub"],
                }
                if self.opts.get("auth_events") is True:
                    self.event.fire_event(eload, salt.utils.event.tagify(prefix="auth"))
                if sign_messages:
                    return self._clear_signed(
                        {"ret": False, "nonce": load["nonce"]}, sig_algo
                    )
                else:
                    return {"enc": "clear", "load": {"ret": False}}

            elif not auto_sign:
                # This key is in the pending dir and is not being auto-signed.
                # Check if the keys are the same and error out if this is the
                # case. Otherwise log the fact that the minion is still
                # pending.
                with salt.utils.files.fopen(pubfn_pend, "r") as pubfn_handle:
                    if not self.compare_keys(pubfn_handle.read(), load["pub"]):
                        log.error(
                            "Authentication attempt from %s failed, the public "
                            "key in pending did not match. This may be an "
                            "attempt to compromise the Salt cluster.",
                            load["id"],
                        )
                        # put denied minion key into minions_denied
                        with salt.utils.files.fopen(pubfn_denied, "w+") as fp_:
                            fp_.write(load["pub"])
                        eload = {
                            "result": False,
                            "id": load["id"],
                            "act": "denied",
                            "pub": load["pub"],
                        }
                        if self.opts.get("auth_events") is True:
                            self.event.fire_event(
                                eload, salt.utils.event.tagify(prefix="auth")
                            )
                        if sign_messages:
                            return self._clear_signed(
                                {"ret": False, "nonce": load["nonce"]}, sig_algo
                            )
                        else:
                            return {"enc": "clear", "load": {"ret": False}}
                    else:
                        log.info(
                            "Authentication failed from host %s, the key is in "
                            "pending and needs to be accepted with salt-key "
                            "-a %s",
                            load["id"],
                            load["id"],
                        )
                        eload = {
                            "result": True,
                            "act": "pend",
                            "id": load["id"],
                            "pub": load["pub"],
                        }
                        if self.opts.get("auth_events") is True:
                            self.event.fire_event(
                                eload, salt.utils.event.tagify(prefix="auth")
                            )
                        if sign_messages:
                            return self._clear_signed(
                                {"ret": True, "nonce": load["nonce"]}, sig_algo
                            )
                        else:
                            return {"enc": "clear", "load": {"ret": True}}
            else:
                # This key is in pending and has been configured to be
                # auto-signed. Check to see if it is the same key, and if
                # so, pass on doing anything here, and let it get automatically
                # accepted below.
                with salt.utils.files.fopen(pubfn_pend, "r") as pubfn_handle:
                    if not self.compare_keys(pubfn_handle.read(), load["pub"]):
                        log.error(
                            "Authentication attempt from %s failed, the public "
                            "keys in pending did not match. This may be an "
                            "attempt to compromise the Salt cluster.",
                            load["id"],
                        )
                        # put denied minion key into minions_denied
                        with salt.utils.files.fopen(pubfn_denied, "w+") as fp_:
                            fp_.write(load["pub"])
                        eload = {"result": False, "id": load["id"], "pub": load["pub"]}
                        if self.opts.get("auth_events") is True:
                            self.event.fire_event(
                                eload, salt.utils.event.tagify(prefix="auth")
                            )
                        if sign_messages:
                            return self._clear_signed(
                                {"ret": False, "nonce": load["nonce"]}, sig_algo
                            )
                        else:
                            return {"enc": "clear", "load": {"ret": False}}
                    else:
                        os.remove(pubfn_pend)

        else:
            # Something happened that I have not accounted for, FAIL!
            log.warning("Unaccounted for authentication failure")
            eload = {"result": False, "id": load["id"], "pub": load["pub"]}
            if self.opts.get("auth_events") is True:
                self.event.fire_event(eload, salt.utils.event.tagify(prefix="auth"))
            if sign_messages:
                return self._clear_signed(
                    {"ret": False, "nonce": load["nonce"]}, sig_algo
                )
            else:
                return {"enc": "clear", "load": {"ret": False}}

        log.info("Authentication accepted from %s", load["id"])
        # only write to disk if you are adding the file, and in open mode,
        # which implies we accept any key from a minion.
        if not os.path.isfile(pubfn) and not self.opts["open_mode"]:
            with salt.utils.files.fopen(pubfn, "w+") as fp_:
                fp_.write(load["pub"])
        elif self.opts["open_mode"]:
            disk_key = ""
            if os.path.isfile(pubfn):
                with salt.utils.files.fopen(pubfn, "r") as fp_:
                    disk_key = fp_.read()
            if load["pub"] and load["pub"] != disk_key:
                log.debug("Host key change detected in open mode.")
                with salt.utils.files.fopen(pubfn, "w+") as fp_:
                    fp_.write(load["pub"])
            elif not load["pub"]:
                log.error("Public key is empty: %s", load["id"])
                if sign_messages:
                    return self._clear_signed(
                        {"ret": False, "nonce": load["nonce"]}, sig_algo
                    )
                else:
                    return {"enc": "clear", "load": {"ret": False}}

        pub = None

        # the con_cache is enabled, send the minion id to the cache
        if self.cache_cli:
            self.cache_cli.put_cache([load["id"]])

        # The key payload may sometimes be corrupt when using auto-accept
        # and an empty request comes in
        try:
            pub = salt.crypt.PublicKey(pubfn)
        except salt.crypt.InvalidKeyError as err:
            log.error('Corrupt public key "%s": %s', pubfn, err)
            if sign_messages:
                return self._clear_signed(
                    {"ret": False, "nonce": load["nonce"]}, sig_algo
                )
            else:
                return {"enc": "clear", "load": {"ret": False}}

        ret = {
            "enc": "pub",
            "pub_key": self.master_key.get_pub_str(),
            "publish_port": self.opts["publish_port"],
        }

        # sign the master's pubkey (if enabled) before it is
        # sent to the minion that was just authenticated
        if self.opts["master_sign_pubkey"]:
            # append the pre-computed signature to the auth-reply
            if self.master_key.pubkey_signature():
                log.debug("Adding pubkey signature to auth-reply")
                log.debug(self.master_key.pubkey_signature())
                ret.update({"pub_sig": self.master_key.pubkey_signature()})
            else:
                # the master has its own signing-keypair, compute the master.pub's
                # signature and append that to the auth-reply

                # get the key_pass for the signing key
                key_pass = salt.utils.sdb.sdb_get(
                    self.opts["signing_key_pass"], self.opts
                )
                log.debug("Signing master public key before sending")
                pub_sign = salt.crypt.sign_message(
                    self.master_key.get_sign_paths()[1],
                    ret["pub_key"],
                    key_pass,
                    algorithm=sig_algo,
                )
                ret.update({"pub_sig": binascii.b2a_base64(pub_sign)})

        if self.opts["auth_mode"] >= 2:
            if "token" in load:
                try:
                    mtoken = self.master_key.key.decrypt(load["token"], enc_algo)
                    aes = "{}_|-{}".format(
                        salt.master.SMaster.secrets["aes"]["secret"].value, mtoken
                    )
                except UnsupportedAlgorithm as exc:
                    log.info(
                        "Minion %s tried to authenticate with unsupported encryption algorithm: %s",
                        load["id"],
                        enc_algo,
                    )
                    return {"enc": "clear", "load": {"ret": "bad enc algo"}}
                except Exception as exc:  # pylint: disable=broad-except
                    log.warning("Token failed to decrypt %s", exc)
                    # Token failed to decrypt, send back the salty bacon to
                    # support older minions
            else:
                aes = salt.master.SMaster.secrets["aes"]["secret"].value

            ret["aes"] = pub.encrypt(aes, enc_algo)
            ret["session"] = pub.encrypt(self.session_key(load["id"]), enc_algo)
        else:
            if "token" in load:
                try:
                    mtoken = self.master_key.key.decrypt(load["token"], enc_algo)
                    ret["token"] = pub.encrypt(mtoken, enc_algo)
                except UnsupportedAlgorithm as exc:
                    log.info(
                        "Minion %s tried to authenticate with unsupported encryption algorithm: %s",
                        load["id"],
                        enc_algo,
                    )
                    return {"enc": "clear", "load": {"ret": "bad enc algo"}}
                except Exception as exc:  # pylint: disable=broad-except
                    # Token failed to decrypt, send back the salty bacon to
                    # support older minions
                    log.warning("Token failed to decrypt: %r", exc)

            aes = salt.master.SMaster.secrets["aes"]["secret"].value
            ret["aes"] = pub.encrypt(aes, enc_algo)
            ret["session"] = pub.encrypt(self.session_key(load["id"]), enc_algo)

        if version < 3:
            log.warning(
                "Minion using legacy request server protocol, please upgrade %s",
                load["id"],
            )

        # Be aggressive about the signature
        digest = salt.utils.stringutils.to_bytes(hashlib.sha256(aes).hexdigest())
        ret["sig"] = salt.crypt.private_encrypt(self.master_key.key, digest)
        eload = {"result": True, "act": "accept", "id": load["id"], "pub": load["pub"]}
        if self.opts.get("auth_events") is True:
            self.event.fire_event(eload, salt.utils.event.tagify(prefix="auth"))
        if sign_messages:
            ret["nonce"] = load["nonce"]
            return self._clear_signed(ret, sig_algo)
        return ret

    def close(self):
        self.transport.close()
        if self.event is not None:
            self.event.destroy()


class PubServerChannel:
    """
    Factory class to create subscription channels to the master's Publisher
    """

    @classmethod
    def factory(cls, opts, **kwargs):
        if "master_uri" not in opts and "master_uri" in kwargs:
            opts["master_uri"] = kwargs["master_uri"]
        presence_events = False
        if opts.get("presence_events", False):
            tcp_only = True
            for transport, _ in salt.utils.channel.iter_transport_opts(opts):
                if transport != "tcp":
                    tcp_only = False
            if tcp_only:
                # Only when the transport is TCP only, the presence events will
                # be handled here. Otherwise, it will be handled in the
                # 'Maintenance' process.
                presence_events = True
        transport = salt.transport.publish_server(opts, **kwargs)
        return cls(opts, transport, presence_events=presence_events)

    def __init__(self, opts, transport, presence_events=False):
        self.opts = opts
        self.ckminions = salt.utils.minions.CkMinions(self.opts)
        self.transport = transport
        self.aes_funcs = salt.master.AESFuncs(self.opts)
        self.present = {}
        self.presence_events = presence_events
        self.event = salt.utils.event.get_event("master", opts=self.opts, listen=False)

    def __getstate__(self):
        return {
            "opts": self.opts,
            "transport": self.transport,
            "presence_events": self.presence_events,
        }

    def __setstate__(self, state):
        self.opts = state["opts"]
        self.state = state["presence_events"]
        self.transport = state["transport"]
        self.event = salt.utils.event.get_event("master", opts=self.opts, listen=False)
        self.ckminions = salt.utils.minions.CkMinions(self.opts)
        self.present = {}

    def close(self):
        self.transport.close()
        if self.event is not None:
            self.event.destroy()
            self.event = None
        if self.aes_funcs is not None:
            self.aes_funcs.destroy()
            self.aes_funcs = None

    def pre_fork(self, process_manager, kwargs=None):
        """
        Do anything necessary pre-fork. Since this is on the master side this will
        primarily be used to create IPC channels and create our daemon process to
        do the actual publishing

        :param func process_manager: A ProcessManager, from salt.utils.process.ProcessManager
        """
        if hasattr(self.transport, "publish_daemon"):
            process_manager.add_process(self._publish_daemon, kwargs=kwargs)

    def _publish_daemon(self, **kwargs):
        if self.opts["pub_server_niceness"] and not salt.utils.platform.is_windows():
            log.info(
                "setting Publish daemon niceness to %i",
                self.opts["pub_server_niceness"],
            )
            os.nice(self.opts["pub_server_niceness"])
        secrets = kwargs.get("secrets", None)
        if secrets is not None:
            salt.master.SMaster.secrets = secrets
        self.master_key = salt.crypt.MasterKeys(self.opts)
        self.transport.publish_daemon(
            self.publish_payload, self.presence_callback, self.remove_presence_callback
        )

    def presence_callback(self, subscriber, msg):
        if msg["enc"] != "aes":
            # We only accept 'aes' encoded messages for 'id'
            return
        crypticle = salt.crypt.Crypticle(
            self.opts, salt.master.SMaster.secrets["aes"]["secret"].value
        )
        load = crypticle.loads(msg["load"])
        load = salt.transport.frame.decode_embedded_strs(load)
        if not self.aes_funcs.verify_minion(load["id"], load["tok"]):
            return
        subscriber.id_ = load["id"]
        self._add_client_present(subscriber)

    def remove_presence_callback(self, subscriber):
        self._remove_client_present(subscriber)

    def _add_client_present(self, client):
        id_ = client.id_
        if id_ in self.present:
            clients = self.present[id_]
            clients.add(client)
        else:
            self.present[id_] = {client}
            if self.presence_events:
                data = {"new": [id_], "lost": []}
                self.event.fire_event(
                    data, salt.utils.event.tagify("change", "presence")
                )
                data = {"present": list(self.present.keys())}
                self.event.fire_event(
                    data, salt.utils.event.tagify("present", "presence")
                )

    def _remove_client_present(self, client):
        id_ = client.id_
        if id_ is None or id_ not in self.present:
            # This is possible if _remove_client_present() is invoked
            # before the minion's id is validated.
            return

        clients = self.present[id_]
        if client not in clients:
            # Since _remove_client_present() is potentially called from
            # _stream_read() and/or publish_payload(), it is possible for
            # it to be called twice, in which case we will get here.
            # This is not an abnormal case, so no logging is required.
            return

        clients.remove(client)
        if len(clients) == 0:
            del self.present[id_]
            if self.presence_events:
                data = {"new": [], "lost": [id_]}
                self.event.fire_event(
                    data, salt.utils.event.tagify("change", "presence")
                )
                data = {"present": list(self.present.keys())}
                self.event.fire_event(
                    data, salt.utils.event.tagify("present", "presence")
                )

    @salt.ext.tornado.gen.coroutine
    def publish_payload(self, load, *args):
        unpacked_package = self.wrap_payload(load)
        try:
            payload = salt.payload.loads(unpacked_package["payload"])
        except KeyError:
            log.error("Invalid package %r", unpacked_package)
            raise
        if "topic_lst" in unpacked_package:
            topic_list = unpacked_package["topic_lst"]
            ret = yield self.transport.publish_payload(payload, topic_list)
        else:
            ret = yield self.transport.publish_payload(payload)
        raise salt.ext.tornado.gen.Return(ret)

    def wrap_payload(self, load):
        payload = {"enc": "aes"}
        load["serial"] = salt.master.SMaster.get_serial()
        crypticle = salt.crypt.Crypticle(
            self.opts, salt.master.SMaster.secrets["aes"]["secret"].value
        )
        payload["load"] = crypticle.dumps(load)
        if self.opts["sign_pub_messages"]:
            master_pem_path = os.path.join(self.opts["pki_dir"], "master.pem")
            log.debug("Signing data packet")
            payload["sig_algo"] = self.opts["publish_signing_algorithm"]
            payload["sig"] = salt.crypt.PrivateKey(
                self.master_key.rsa_path,
            ).sign(payload["load"], self.opts["publish_signing_algorithm"])

        int_payload = {"payload": salt.payload.dumps(payload)}

        # If topics are upported, target matching has to happen master side
        match_targets = ["pcre", "glob", "list"]
        if self.transport.topic_support and load["tgt_type"] in match_targets:
            # add some targeting stuff for lists only (for now)
            if load["tgt_type"] == "list":
                int_payload["topic_lst"] = load["tgt"]
            if isinstance(load["tgt"], str):
                # Fetch a list of minions that match
                _res = self.ckminions.check_minions(
                    load["tgt"], tgt_type=load["tgt_type"]
                )
                match_ids = _res["minions"]
                log.debug("Publish Side Match: %s", match_ids)
                # Send list of miions thru so zmq can target them
                int_payload["topic_lst"] = match_ids
            else:
                int_payload["topic_lst"] = load["tgt"]

        return int_payload

    def publish(self, load):
        """
        Publish "load" to minions
        """
        log.debug(
            "Sending payload to publish daemon. jid=%s load=%s",
            load.get("jid", None),
            repr(load)[:40],
        )
        self.transport.publish(load)
