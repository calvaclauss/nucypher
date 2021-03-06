import json
import os
from base64 import b64encode
from unittest import mock

from twisted.logger import Logger

from nucypher.characters.control.emitters import JSONRPCStdoutEmitter
from nucypher.characters.lawful import Ursula
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import BobConfiguration
from nucypher.cli.actions import SUCCESSFUL_DESTRUCTION


@mock.patch('nucypher.config.characters.BobConfiguration.default_filepath', return_value='/non/existent/file')
def test_missing_configuration_file(default_filepath_mock, click_runner):
    cmd_args = ('bob', 'run')
    result = click_runner.invoke(nucypher_cli, cmd_args, catch_exceptions=False)
    assert result.exit_code != 0
    assert default_filepath_mock.called
    assert "run: 'nucypher bob init'" in result.output


def test_bob_public_keys(click_runner):
    derive_key_args = ('bob', 'public-keys',
                       '--dev')

    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)

    assert result.exit_code == 0
    assert "bob_encrypting_key" in result.output
    assert "bob_verifying_key" in result.output
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import SigningPower
from nucypher.utilities.logging import GlobalLoggerSettings
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD, TEMPORARY_DOMAIN
from nucypher.utilities.sandbox.constants import MOCK_IP_ADDRESS, MOCK_CUSTOM_INSTALLATION_PATH

log = Logger()


def test_initialize_bob_with_custom_configuration_root(custom_filepath, click_runner):
    # Use a custom local filepath for configuration
    init_args = ('bob', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--config-root', custom_filepath)

    user_input = '{password}\n{password}'.format(password=INSECURE_DEVELOPMENT_PASSWORD, ip=MOCK_IP_ADDRESS)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0, result.exception

    # CLI Output
    assert MOCK_CUSTOM_INSTALLATION_PATH in result.output, "Configuration not in system temporary directory"
    assert "nucypher bob run" in result.output, 'Help message is missing suggested command'
    assert 'IPv4' not in result.output

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'keyring')), 'Keyring does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'known_nodes')), 'known_nodes directory does not exist'

    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    # Auth
    assert 'Enter NuCypher keyring password' in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_bob_control_starts_with_preexisting_configuration(click_runner, custom_filepath):
    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())

    init_args = ('bob', 'run',
                 '--dry-run',
                 '--config-file', custom_config_filepath)

    user_input = '{password}\n{password}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input)
    assert result.exit_code == 0, result.exception
    assert "Bob Verifying Key" in result.output
    assert "Bob Encrypting Key" in result.output


def test_bob_view_with_preexisting_configuration(click_runner, custom_filepath):
    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())

    view_args = ('bob', 'config',
                 '--config-file', custom_config_filepath)

    user_input = '{password}\n{password}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli, view_args, input=user_input)

    assert result.exit_code == 0, result.exception
    assert "checksum_address" in result.output
    assert "domains" in result.output
    assert TEMPORARY_DOMAIN in result.output
    assert custom_filepath in result.output


def test_bob_public_keys(click_runner):
    derive_key_args = ('bob', 'public-keys', '--dev')

    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)

    assert result.exit_code == 0
    assert "bob_encrypting_key" in result.output
    assert "bob_verifying_key" in result.output


# Should be the last test since it deletes the configuration file
def test_bob_destroy(click_runner, custom_filepath):
    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())
    destroy_args = ('bob', 'destroy',
                    '--config-file', custom_config_filepath,
                    '--force')

    result = click_runner.invoke(nucypher_cli, destroy_args, catch_exceptions=False)
    assert result.exit_code == 0, result.exception
    assert SUCCESSFUL_DESTRUCTION in result.output
    assert not os.path.exists(custom_config_filepath), "Bob config file was deleted"


def test_bob_retrieves_twice_via_cli(click_runner,
                                     capsule_side_channel,
                                     enacted_federated_policy,
                                     federated_ursulas,
                                     custom_filepath_2,
                                     federated_alice
                                     ):
    teacher = list(federated_ursulas)[0]

    first_message = capsule_side_channel.reset(plaintext_passthrough=True)
    three_message_kits = [capsule_side_channel(), capsule_side_channel(), capsule_side_channel()]

    bob_config_root = custom_filepath_2
    bob_configuration_file_location = os.path.join(bob_config_root, BobConfiguration.generate_filename())
    label = enacted_federated_policy.label

    # I already have a Bob.

    # Need to init so that the config file is made, even though we won't use this Bob.
    bob_init_args = ('bob', 'init',
                     '--network', TEMPORARY_DOMAIN,
                     '--config-root', bob_config_root,
                     '--federated-only')

    envvars = {'NUCYPHER_KEYRING_PASSWORD': INSECURE_DEVELOPMENT_PASSWORD}

    log.info("Init'ing a normal Bob; we'll substitute the Policy Bob in shortly.")
    bob_init_response = click_runner.invoke(nucypher_cli, bob_init_args, catch_exceptions=False, env=envvars)

    message_kit_bytes = bytes(three_message_kits[0])
    message_kit_b64_bytes = b64encode(message_kit_bytes)
    UmbralMessageKit.from_bytes(message_kit_bytes)

    retrieve_args = ('bob', 'retrieve',
                     '--mock-networking',
                     '--json-ipc',
                     '--teacher', teacher.seed_node_metadata(as_teacher_uri=True),
                     '--config-file', bob_configuration_file_location,
                     '--message-kit', message_kit_b64_bytes,
                     '--label', label,
                     '--policy-encrypting-key', federated_alice.get_policy_encrypting_key_from_label(label).hex(),
                     '--alice-verifying-key', federated_alice.public_keys(SigningPower).hex()
                     )

    from nucypher.cli import actions

    def substitute_bob(*args, **kwargs):
        log.info("Substituting the Policy's Bob in CLI runtime.")
        this_fuckin_guy = enacted_federated_policy.bob
        somebody_else = Ursula.from_teacher_uri(teacher_uri=kwargs['teacher_uri'],
                                                min_stake=0,
                                                federated_only=True,
                                                network_middleware=this_fuckin_guy.network_middleware)
        this_fuckin_guy.remember_node(somebody_else)
        this_fuckin_guy.controller.emitter = JSONRPCStdoutEmitter()
        return this_fuckin_guy


    _old_make_character_function = actions.make_cli_character
    try:

        log.info("Patching make_cli_character with substitute_bob")
        actions.make_cli_character = substitute_bob

        # Once...
        with GlobalLoggerSettings.pause_all_logging_while():
            retrieve_response = click_runner.invoke(nucypher_cli, retrieve_args, catch_exceptions=False, env=envvars)

        log.info(f"First retrieval response: {retrieve_response.output}")
        assert retrieve_response.exit_code == 0

        retrieve_response = json.loads(retrieve_response.output)
        for cleartext in retrieve_response['result']['cleartexts']:
            assert cleartext.encode() == capsule_side_channel.plaintexts[1]

        # and again!
        with GlobalLoggerSettings.pause_all_logging_while():
            retrieve_response = click_runner.invoke(nucypher_cli, retrieve_args, catch_exceptions=False, env=envvars)

        log.info(f"Second retrieval response: {retrieve_response.output}")
        assert retrieve_response.exit_code == 0

        retrieve_response = json.loads(retrieve_response.output)
        for cleartext in retrieve_response['result']['cleartexts']:
            assert cleartext.encode() == capsule_side_channel.plaintexts[1]
    finally:
        log.info("un-patching make_cli_character")
        actions.make_cli_character = _old_make_character_function
