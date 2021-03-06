"""
Nmeta policy.py Tests
"""
import pytest

#*** Use copy to create copies not linked to originals (with copy.deepcopy):
import copy

from voluptuous import Invalid, MultipleInvalid

import sys
#*** Handle tests being in different directory branch to app code:
sys.path.insert(0, '../nmeta')

import logging

#*** nmeta imports:
import policy as policy_module
import config
import flows as flows_module
import identities

#*** nmeta test packet imports:
import packets_ipv4_http as pkts

#*** For timestamps:
import datetime

#*** Instantiate config class:
config = config.Config()

#*** Test DPIDs and in ports:
DPID1 = 1
DPID2 = 2
INPORT1 = 1
INPORT2 = 2

#*** Test condition instances (sets of classifiers):
condition_any_opf = {'match_type': 'any', 'classifiers_list':
                             [{'tcp_src': 6633}, {'tcp_dst': 6633}]}
condition_all_opf = {'match_type': 'all', 'classifiers_list':
                             [{'tcp_src': 6633}, {'tcp_dst': 6633}]}
condition_none_opf = {'match_type': 'none', 'classifiers_list':
                             [{'tcp_src': 6633}, {'tcp_dst': 6633}]}
condition_any_http = {'match_type': 'any', 'classifiers_list':
                             [{'tcp_src': 80}, {'tcp_dst': 80}]}
condition_all_http = {'match_type': 'all', 'classifiers_list':
                             [{'tcp_src': 80}, {'tcp_dst': 80}]}
condition_all_http2 = {'match_type': 'all', 'classifiers_list':
                             [{'tcp_src': 43297}, {'tcp_dst': 80}]}
condition_any_mac = {'match_type': 'any', 'classifiers_list':
                             [{'eth_src': '08:00:27:2a:d6:dd'},
                              {'eth_dst': '08:00:27:c8:db:91'}]}
condition_all_mac = {'match_type': 'all', 'classifiers_list':
                             [{'eth_src': '08:00:27:2a:d6:dd'},
                              {'eth_dst': '08:00:27:c8:db:91'}]}
condition_any_mac2 = {'match_type': 'any', 'classifiers_list':
                             [{'eth_src': '00:00:00:01:02:03'},
                              {'eth_dst': '08:00:27:01:02:03'}]}
condition_any_ip = {'match_type': 'any', 'classifiers_list':
                             [{'ip_dst': '192.168.57.12'},
                              {'ip_src': '192.168.56.32'}]}
condition_any_ssh = {'match_type': 'any', 'classifiers_list':
                             [{'tcp_src': 22}, {'tcp_dst': 22}]}

condition_bad_no_list = {'match_type': 'any'}

rule_1 = {
            'comment': 'HTTP traffic',
            'conditions_list':
                [
                    {
                    'match_type': 'any',
                    'classifiers_list':
                        [{'tcp_src': 80},
                         {'tcp_dst': 80}]
                },
                    {
                    'match_type': 'any',
                    'classifiers_list':
                        [{'ip_src': '10.1.0.1'},
                         {'ip_dst': '10.1.0.1'}]
                }
            ],
            'match_type': 'all',
            'actions':
                {
                'qos_treatment': 'QoS_treatment=high_priority',
                'set_desc': 'description="High Priority HTTP Traffic"'
            }
        }

logger = logging.getLogger(__name__)

def test_check_policy():
    """
    Test that packet match against policy works correctly
    """
    #*** Instantiate tc, flows and identities classes, specifying
    #*** a particular main_policy file to use:
    policy = policy_module.Policy(config,
                            pol_dir_default="config/tests/regression",
                            pol_dir_user="config/tests/foo",
                            pol_filename="main_policy_regression_static.yaml")
    flow = flows_module.Flow(config)
    ident = identities.Identities(config, policy)

    #*** Note: cannot query a classification until a packet has been
    #*** ingested - will throw error

    #*** Ingest a packet:
    #*** Test Flow 1 Packet 1 (Client TCP SYN):
    # 10.1.0.1 10.1.0.2 TCP 74 43297 > http [SYN]
    flow.ingest_packet(DPID1, INPORT1, pkts.RAW[0], datetime.datetime.now())
    #*** Check policy:
    policy.check_policy(flow, ident)
    #*** Should not match any rules in that policy:
    logger.debug("flow.classification.classified=%s", flow.classification.classified)
    assert flow.classification.classified == 1
    assert flow.classification.classification_tag == ""
    assert flow.classification.actions == {}

    #*** Re-instantiate policy with different policy that should classify:
    policy = policy_module.Policy(config,
                        pol_dir_default="config/tests/regression",
                        pol_dir_user="config/tests/foo",
                        pol_filename="main_policy_regression_static_3.yaml")

    #*** Re-ingest packet:
    #*** Test Flow 1 Packet 1 (Client TCP SYN):
    # 10.1.0.1 10.1.0.2 TCP 74 43297 > http [SYN]
    flow.ingest_packet(DPID1, INPORT1, pkts.RAW[0], datetime.datetime.now())
    #*** Check policy:
    policy.check_policy(flow, ident)
    #*** Should match policy:
    assert flow.classification.classified == 1
    assert flow.classification.classification_tag == "Constrained Bandwidth Traffic"
    logger.debug("flow.classification.actions=%s", flow.classification.actions)
    assert flow.classification.actions == {'set_desc': 'Constrained Bandwidth Traffic',
                                           'qos_treatment': 'constrained_bw'}

def test_check_tc_rule():
    #*** Instantiate classes:
    policy = policy_module.Policy(config,
                            pol_dir_default="config/tests/regression",
                            pol_dir_user="config/tests/foo",
                            pol_filename="main_policy_regression_static.yaml")
    flow = flows_module.Flow(config)
    ident = identities.Identities(config, policy)

    #*** Test Flow 1 Packet 1 (Client TCP SYN):
    # 10.1.0.1 10.1.0.2 TCP 74 43297 > http [SYN]
    flow.ingest_packet(DPID1, INPORT1, pkts.RAW[0], datetime.datetime.now())
    #*** Set policy.pkt as work around for not calling parent method that sets it:
    policy.pkt = flow.packet

    #*** main_policy_regression_static.yaml shouldn't match HTTP (rule 0):
    tc_rules = policy_module.TCRules(policy)
    tc_rule = policy_module.TCRule(tc_rules, policy, 0)
    tc_rule_result = tc_rule.check_tc_rule(flow, ident)
    assert tc_rule_result.match == False
    assert tc_rule_result.continue_to_inspect == False
    assert tc_rule_result.classification_tag == ""
    assert tc_rule_result.actions == {}


    #*** main_policy_regression_static_3.yaml should match HTTP (rule 0):
    policy = policy_module.Policy(config,
                            pol_dir_default="config/tests/regression",
                            pol_dir_user="config/tests/foo",
                            pol_filename="main_policy_regression_static_3.yaml")
    ident = identities.Identities(config, policy)
    tc_rules = policy_module.TCRules(policy)
    tc_rule = policy_module.TCRule(tc_rules, policy, 0)
    tc_rule_result = tc_rule.check_tc_rule(flow, ident)
    assert tc_rule_result.match == True
    assert tc_rule_result.continue_to_inspect == False
    assert tc_rule_result.classification_tag == "Constrained Bandwidth Traffic"
    assert tc_rule_result.actions == {'qos_treatment': 'constrained_bw',
                                   'set_desc': 'Constrained Bandwidth Traffic'}

    # TBD - more

def test_check_tc_condition():
    """
    Check TC packet match against a TC condition (set of classifiers and
    match type)
    """
    #*** Instantiate classes:
    policy = policy_module.Policy(config)
    flow = flows_module.Flow(config)
    ident = identities.Identities(config, policy)

    #*** Test Flow 1 Packet 1 (Client TCP SYN):
    # 10.1.0.1 10.1.0.2 TCP 74 43297 > http [SYN]
    flow.ingest_packet(DPID1, INPORT1, pkts.RAW[0], datetime.datetime.now())
    #*** Set policy.pkt as work around for not calling parent method
    #***  that sets it:
    policy.pkt = flow.packet

    #*** HTTP is not OpenFlow so shouldn't match!
    logger.debug("condition_any_opf should not match")
    tc_rules = policy_module.TCRules(policy)
    tc_condition = policy_module.TCCondition(tc_rules, policy, condition_any_opf)
    condition_result = tc_condition.check_tc_condition(flow, ident)
    assert condition_result.match == False
    assert condition_result.continue_to_inspect == False
    assert condition_result.classification_tag == ""
    assert condition_result.actions == {}

    #*** HTTP is not OpenFlow so should match none rule!
    logger.debug("condition_any_opf should not match")
    tc_rules = policy_module.TCRules(policy)
    tc_condition = policy_module.TCCondition(tc_rules, policy, condition_none_opf)
    condition_result = tc_condition.check_tc_condition(flow, ident)
    assert condition_result.match == True
    assert condition_result.continue_to_inspect == False
    assert condition_result.classification_tag == ""
    assert condition_result.actions == {}

    #*** HTTP is HTTP so should match:
    logger.debug("condition_any_http should match")
    tc_condition = policy_module.TCCondition(tc_rules, policy, condition_any_http)
    condition_result = tc_condition.check_tc_condition(flow, ident)
    assert condition_result.match == True
    assert condition_result.continue_to_inspect == False
    assert condition_result.classification_tag == ""
    assert condition_result.actions == {}

    #*** Source AND Dest aren't both HTTP so should not match:
    logger.debug("condition_all_http should not match")
    tc_condition = policy_module.TCCondition(tc_rules, policy, condition_all_http)
    condition_result = tc_condition.check_tc_condition(flow, ident)
    assert condition_result.match == False
    assert condition_result.continue_to_inspect == False
    assert condition_result.classification_tag == ""
    assert condition_result.actions == {}

    #*** This should match (HTTP src and dst ports correct):
    logger.debug("condition_all_http2 should match")
    tc_condition = policy_module.TCCondition(tc_rules, policy, condition_all_http2)
    condition_result = tc_condition.check_tc_condition(flow, ident)
    assert condition_result.match == True
    assert condition_result.continue_to_inspect == False
    assert condition_result.classification_tag == ""
    assert condition_result.actions == {}

    #*** MAC should match:
    tc_condition = policy_module.TCCondition(tc_rules, policy, condition_any_mac)
    condition_result = tc_condition.check_tc_condition(flow, ident)
    assert condition_result.match == True
    assert condition_result.continue_to_inspect == False
    assert condition_result.classification_tag == ""
    assert condition_result.actions == {}

    tc_condition = policy_module.TCCondition(tc_rules, policy, condition_all_mac)
    condition_result = tc_condition.check_tc_condition(flow, ident)
    assert condition_result.match == True
    assert condition_result.continue_to_inspect == False
    assert condition_result.classification_tag == ""
    assert condition_result.actions == {}

    #*** Different MAC shouldn't match:
    tc_condition = policy_module.TCCondition(tc_rules, policy, condition_any_mac2)
    condition_result = tc_condition.check_tc_condition(flow, ident)
    assert condition_result.match == False
    assert condition_result.continue_to_inspect == False
    assert condition_result.classification_tag == ""
    assert condition_result.actions == {}

def test_custom_classifiers():
    """
    Check deduplicated list of custom classifiers works
    """
    #*** Instantiate policy, specifying
    #*** a particular main_policy file to use that has no custom classifiers:
    policy = policy_module.Policy(config,
                            pol_dir_default="config/tests/regression",
                            pol_dir_user="config/tests/regression",
                            pol_filename="main_policy_regression_static.yaml")
    assert policy.tc_rules.custom_classifiers == []

    #*** Instantiate policy, specifying
    #*** a custom statistical main_policy file to use that has a
    #*** custom classifier:
    policy = policy_module.Policy(config,
                        pol_dir_default="config/tests/regression",
                        pol_dir_user="config/tests/foo",
                        pol_filename="main_policy_regression_statistical.yaml")
    assert policy.tc_rules.custom_classifiers == ['statistical_qos_bandwidth_1']

def test_qos():
    """
    Test the assignment of QoS queues based on a qos_treatment action
    """
    #*** Instantiate policy, specifying
    #*** a particular main_policy file to use that has no custom classifiers:
    policy = policy_module.Policy(config,
                            pol_dir_default="config/tests/regression",
                            pol_dir_user="config/tests/foo",
                            pol_filename="main_policy_regression_static.yaml")
    assert policy.qos('default_priority') == 0
    assert policy.qos('constrained_bw') == 1
    assert policy.qos('high_priority') == 2
    assert policy.qos('low_priority') == 3
    assert policy.qos('foo') == 0

def test_portsets_get_port_set():
    """
    Test that get_port_set returns correct port_set name
    """
    #*** Instantiate Policy class instance:
    policy = policy_module.Policy(config,
                            pol_dir_default="config/tests/regression",
                            pol_dir_user="config/tests/regression",
                            pol_filename="main_policy_regression_static.yaml")

    #*** Positive matches:
    assert policy.port_sets.get_port_set(255, 5, 0) == "port_set_location_internal"
    assert policy.port_sets.get_port_set(1, 6, 0) == "port_set_location_external"

    #*** Shouldn't match:
    assert policy.port_sets.get_port_set(1234, 5, 0) == ""

def test_portset_is_member():
    """
    Test that the PortSet class method is_member works correctly
    """
    #*** Instantiate Policy class instance:
    policy = policy_module.Policy(config,
                            pol_dir_default="config/tests/regression",
                            pol_dir_user="config/tests/regression",
                            pol_filename="main_policy_regression_static.yaml")

    #*** Members:
    assert policy.port_sets.port_sets_list[0].is_member(255, 5, 0) == 1
    assert policy.port_sets.port_sets_list[0].is_member(1, 2, 0) == 1
    #*** Not members:
    assert policy.port_sets.port_sets_list[0].is_member(255, 4, 0) == 0
    assert policy.port_sets.port_sets_list[0].is_member(256, 5, 0) == 0
    assert policy.port_sets.port_sets_list[0].is_member(255, 5, 1) == 0

def test_validate():
    """
    Test the validate function of policy.py module against various
    good and bad policy scenarios to ensure correct results produced
    """
    #*** Instantiate Policy class instance:
    policy = policy_module.Policy(config,
                            pol_dir_default="config/tests/regression",
                            pol_dir_user="config/tests/regression",
                            pol_filename="main_policy_regression_static.yaml")

    #=================== Top level:

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)

    #*** Check the correctness of the top level of main policy:
    assert policy_module.validate(logger, main_policy, policy_module.TOP_LEVEL_SCHEMA, 'top') == 1

    #*** Knock out a required key from top level of main policy and check that it raises exception:
    del main_policy['tc_rules']
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate(logger, main_policy, policy_module.TOP_LEVEL_SCHEMA, 'top')

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)

    #*** Add an invalid key to top level of main policy and check that it raises exception:
    main_policy['foo'] = 1
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate(logger, main_policy, policy_module.TOP_LEVEL_SCHEMA, 'top')

    #=================== TC Rules branch

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)
    tc_rule_policy = main_policy['tc_rules']['tc_ruleset_1'][0]
    assert policy_module.validate(logger, tc_rule_policy, policy_module.TC_RULE_SCHEMA, 'tc_rule') == 1

    #*** Knock comment out of rule, should still validate as comment is optional:
    del tc_rule_policy['comment']
    assert policy_module.validate(logger, tc_rule_policy, policy_module.TC_RULE_SCHEMA, 'tc_rule') == 1

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)
    tc_rule_policy = main_policy['tc_rules']['tc_ruleset_1'][0]
    assert policy_module.validate(logger, tc_rule_policy, policy_module.TC_RULE_SCHEMA, 'tc_rule') == 1

    #*** Knock match_type out of rule, should fail:
    del tc_rule_policy['match_type']
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate(logger, tc_rule_policy, policy_module.TC_RULE_SCHEMA, 'tc_rule')

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)
    tc_rule_policy = main_policy['tc_rules']['tc_ruleset_1'][0]
    assert policy_module.validate(logger, tc_rule_policy, policy_module.TC_RULE_SCHEMA, 'tc_rule') == 1

    #*** Change match_type to something that isn't supported, should fail:
    tc_rule_policy['match_type'] = 'foo'
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate(logger, tc_rule_policy, policy_module.TC_RULE_SCHEMA, 'tc_rule')

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)
    tc_rule_policy = main_policy['tc_rules']['tc_ruleset_1'][0]
    assert policy_module.validate(logger, tc_rule_policy, policy_module.TC_RULE_SCHEMA, 'tc_rule') == 1

    #*** Knock conditions_list out of rule, should fail:
    del tc_rule_policy['conditions_list']
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate(logger, tc_rule_policy, policy_module.TC_RULE_SCHEMA, 'tc_rule')

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)
    tc_rule_policy = main_policy['tc_rules']['tc_ruleset_1'][0]
    assert policy_module.validate(logger, tc_rule_policy, policy_module.TC_RULE_SCHEMA, 'tc_rule') == 1

    #*** Knock actions out of rule, should fail:
    del tc_rule_policy['actions']
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate(logger, tc_rule_policy, policy_module.TC_RULE_SCHEMA, 'tc_rule')

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)
    tc_rule_actions = main_policy['tc_rules']['tc_ruleset_1'][0]['actions']
    assert policy_module.validate(logger, tc_rule_actions, policy_module.TC_ACTIONS_SCHEMA, 'tc_rule_actions') == 1

    #*** Add invalid action:
    tc_rule_actions['foo'] = 'bar'
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate(logger, tc_rule_actions, policy_module.TC_ACTIONS_SCHEMA, 'tc_rule_actions')

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)
    tc_rule_actions = main_policy['tc_rules']['tc_ruleset_1'][0]['actions']
    assert policy_module.validate(logger, tc_rule_actions, policy_module.TC_ACTIONS_SCHEMA, 'tc_rule_actions') == 1

    #*** Add a valid action key with valid value:
    tc_rule_actions['drop'] = 'at_controller_and_switch'
    assert policy_module.validate(logger, tc_rule_actions, policy_module.TC_ACTIONS_SCHEMA, 'tc_rule_actions') == 1

    #*** Add a valid action key with invalid value:
    tc_rule_actions['drop'] = 'controller'
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate(logger, tc_rule_actions, policy_module.TC_ACTIONS_SCHEMA, 'tc_rule_actions')

    #*** Bad classifier:
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate(logger, condition_bad_no_list, policy_module.TC_CONDITION_SCHEMA, 'tc_condition_bad_no_list')

    #=================== QoS treatment branch

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)
    qos_treatment = main_policy['qos_treatment']
    assert policy_module.validate(logger, qos_treatment, policy_module.QOS_TREATMENT_SCHEMA, 'qos_treatment') == 1

    #*** Add a valid key with invalid value:
    qos_treatment['BadQueue'] = 'foo'
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate(logger, qos_treatment, policy_module.QOS_TREATMENT_SCHEMA, 'qos_treatment')

    #=================== Port Sets branch

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)
    port_sets_policy = main_policy['port_sets']

    #*** Check the correctness of the locations branch of main policy:
    assert policy_module.validate(logger, port_sets_policy, policy_module.PORT_SETS_SCHEMA, 'port_sets') == 1


    #=================== Locations branch

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)
    locations_policy = main_policy['locations']

    #*** Check the correctness of the locations branch of main policy:
    assert policy_module.validate(logger, locations_policy, policy_module.LOCATIONS_SCHEMA, 'locations') == 1

    #*** Knock out a required key from locations branch of main policy and check that it raises exception:
    del locations_policy['default_match']
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate(logger, locations_policy, policy_module.LOCATIONS_SCHEMA, 'locations')

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)
    locations_policy = main_policy['locations']

    #*** Add an invalid key to locations branch of main policy and check that it raises exception:
    locations_policy['foo'] = 1
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate(logger, locations_policy, policy_module.LOCATIONS_SCHEMA, 'locations')

def test_validate_port_set_list():
    """
    Test the validate_port_set_list function of policy.py module against
    various good and bad policy scenarios to ensure correct results produced
    """
    #*** Instantiate Policy class instance:
    policy = policy_module.Policy(config)

    #*** Get a copy of the main policy YAML:
    main_policy = copy.deepcopy(policy.main_policy)

    port_set_list = main_policy['locations']['locations_list'][0]['port_set_list']
    assert policy_module.validate_port_set_list(logger, port_set_list, policy) == 1

    #*** Add a bad port_set:
    bad_port_set = {'port_set': 'foobar'}
    port_set_list.append(bad_port_set)
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate_port_set_list(logger, port_set_list, policy)

def test_validate_location():
    """
    Test validation that a location string appears as a location in policy
    """
    policy = policy_module.Policy(config,
                            pol_dir_default="config/tests/regression",
                            pol_dir_user="config/tests/foo",
                            pol_filename="main_policy_regression_static.yaml")
    #*** Good location strings:
    assert policy_module.validate_location(logger, 'internal', policy) == True
    assert policy_module.validate_location(logger, 'external', policy) == True

    #*** Invalid location strings:
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate_location(logger, 'foo', policy)
    with pytest.raises(SystemExit) as exit_info:
        policy_module.validate_location(logger, '', policy)

def test_validate_ports():
    """
    Test the validate_ports function of policy.py module against various
    good and bad ports specifications

    Example:
    1-3,5,66
    """
    ports_good1 = "1-3,5,66"
    ports_good2 = "99"
    ports_good3 = "1-3,5,66-99"
    ports_good4 = "1-3, 5, 66-99"

    #*** Non-integer values:
    ports_bad1 = "1-3,foo,66"
    ports_bad2 = "1-b,5,66"
    #*** Invalid range:
    ports_bad3 = "1-3,5,66-65"

    assert policy_module.validate_ports(ports_good1) == ports_good1

    assert policy_module.validate_ports(ports_good2) == ports_good2

    assert policy_module.validate_ports(ports_good3) == ports_good3

    assert policy_module.validate_ports(ports_good4) == ports_good4

    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_ports(ports_bad1)

    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_ports(ports_bad2)

    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_ports(ports_bad3)

def test_validate_time_of_day():
    """
    Test the validate_time_of_day function of policy.py module against various
    good and bad time ranges
    """
    #*** Valid time ranges:
    assert policy_module.validate_time_of_day('05:00-14:00') == '05:00-14:00'
    assert policy_module.validate_time_of_day('21:00-06:00') == '21:00-06:00'

    #*** Invalid time ranges:
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_time_of_day('abc-efg')
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_time_of_day('01:00-24:03')

def test_validate_macaddress():
    """
    Test the validate_macaddress function of policy.py module against various
    good and bad MAC addresses
    """
    #*** Valid MAC Addresses:
    assert policy_module.validate_macaddress('fe80:dead:beef') == 'fe80:dead:beef'
    assert policy_module.validate_macaddress('fe80deadbeef') == 'fe80deadbeef'
    assert policy_module.validate_macaddress('fe:80:de:ad:be:ef') == 'fe:80:de:ad:be:ef'

    #*** Invalid MAC Addresses:
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_macaddress('192.168.3.4')
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_macaddress('foo 123')

def test_validate_ipaddress():
    """
    Test the validate_ipaddress function of policy.py module against various
    good and bad IP addresses
    """
    #*** Valid IP Addresses:
    assert policy_module.validate_ip_space('192.168.3.4') == '192.168.3.4'
    assert policy_module.validate_ip_space('192.168.3.0/24') == '192.168.3.0/24'
    assert policy_module.validate_ip_space('192.168.3.25-192.168.4.58') == '192.168.3.25-192.168.4.58'
    assert policy_module.validate_ip_space('fe80::dead:beef') == 'fe80::dead:beef'
    assert policy_module.validate_ip_space('10.1.2.2-10.1.2.3') == '10.1.2.2-10.1.2.3'
    assert policy_module.validate_ip_space('fe80::dead:beef-fe80::dead:beff') == 'fe80::dead:beef-fe80::dead:beff'

    #*** Invalid IP Addresses:
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_ip_space('192.168.322.0/24')
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_ip_space('foo')
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_ip_space('192.168.4.25-192.168.3.58')
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_ip_space('192.168.3.25-43')
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_ip_space('10.1.2.3-fe80::dead:beef')
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_ip_space('10.1.2.3-10.1.2.5-10.1.2.8')

def test_validate_ethertype():
    """
    Test the validate_ethertype function of policy.py module against various
    good and bad ethertypes
    """
    #*** Valid EtherTypes:
    assert policy_module.validate_ethertype('0x0800') == '0x0800'
    assert policy_module.validate_ethertype('0x08001') == '0x08001'
    assert policy_module.validate_ethertype('35020') == '35020'

    assert policy_module.validate_ethertype(0x0800) == 0x0800
    assert policy_module.validate_ethertype(0x08001) == 0x08001
    assert policy_module.validate_ethertype(35020) == 35020

    #*** Invalid EtherTypes:
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_ethertype('foo')
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_ethertype('0x18001')
    with pytest.raises(Invalid) as exit_info:
        policy_module.validate_ethertype('350201')

def test_transform_ports():
    """
    Test the transform_ports function of policy.py module against various
    ports specifications

    Example:
    Ports specification "1-3,5,66" should become list [1,2,3,5,66]
    """
    ports1 = "1-3,5,66"
    ports_list1 = [1,2,3,5,66]

    ports2 = "10-15, 19-26"
    ports_list2 = [10,11,12,13,14,15,19,20,21,22,23,24,25,26]

    assert policy_module.transform_ports(ports1) == ports_list1

    assert policy_module.transform_ports(ports2) == ports_list2

def test_location_check():
    """
    Test the check method of the Location class

    Check a dpid/port to see if it is part of this location
    and if so return the string name of the location otherwise
    return empty string
    """
    #*** Instantiate Policy class instance:
    policy = policy_module.Policy(config,
                            pol_dir_default="config/tests/regression",
                            pol_dir_user="config/tests/foo",
                            pol_filename="main_policy_regression_static.yaml")

    #*** Test against 'internal' location:
    assert policy.locations.locations_list[0].check(1, 1) == 'internal'
    assert policy.locations.locations_list[0].check(1, 6) == ''
    assert policy.locations.locations_list[0].check(56, 1) == ''
    assert policy.locations.locations_list[0].check(255, 3) == 'internal'

    #*** Test against 'external' location:
    assert policy.locations.locations_list[1].check(1, 6) == 'external'
    assert policy.locations.locations_list[1].check(1, 1) == ''

def test_locations_get_location():
    """
    Test the get_location method of the Locations class
    """
    #*** Instantiate Policy class instance:
    policy = policy_module.Policy(config,
                            pol_dir_default="config/tests/regression",
                            pol_dir_user="config/tests/foo",
                            pol_filename="main_policy_regression_static.yaml")

    #*** Test against 'internal' location:
    assert policy.locations.get_location(1, 1) == 'internal'
    assert policy.locations.get_location(255, 3) == 'internal'
    assert policy.locations.get_location(1, 66) == 'internal'

    #*** Test against 'external' location:
    assert policy.locations.get_location(1, 6) == 'external'
    assert policy.locations.get_location(255, 4) == 'external'

    #*** Test against no match to default 'unknown' location:
    assert policy.locations.get_location(1, 7) == 'unknown'
    assert policy.locations.get_location(1234, 5) == 'unknown'
