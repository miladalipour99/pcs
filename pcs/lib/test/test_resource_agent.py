from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

from lxml import etree
from functools import partial

from pcs.test.tools.assertions import (
    ExtendedAssertionsMixin,
    assert_raise_library_error,
    assert_report_item_list_equal,
    assert_xml_equal,
    start_tag_error_text,
)
from pcs.test.tools.misc import create_patcher
from pcs.test.tools.pcs_unittest import TestCase, mock
from pcs.test.tools.xml import XmlManipulation

from pcs.common import report_codes
from pcs.lib import resource_agent as lib_ra
from pcs.lib.errors import ReportItemSeverity as severity, LibraryError
from pcs.lib.external import CommandRunner

patch_agent = create_patcher("pcs.lib.resource_agent")
patch_agent_object = partial(mock.patch.object, lib_ra.Agent)


class GetDefaultInterval(TestCase):
    def test_return_0s_on_name_different_from_monitor(self):
        self.assertEqual("0s", lib_ra.get_default_interval("start"))
    def test_return_60s_on_monitor(self):
        self.assertEqual("60s", lib_ra.get_default_interval("monitor"))


@patch_agent("get_default_interval", mock.Mock(return_value="10s"))
class CompleteAllIntervals(TestCase):
    def test_add_intervals_everywhere_is_missing(self):
        self.assertEqual(
            [
                {"name": "monitor", "interval": "20s"},
                {"name": "start", "interval": "10s"},
            ],
            lib_ra.complete_all_intervals([
                {"name": "monitor", "interval": "20s"},
                {"name": "start"},
            ])
        )

class GetResourceAgentNameFromString(TestCase):
    def test_returns_resource_agent_name_when_is_valid(self):
        self.assertEqual(
            lib_ra.ResourceAgentName("ocf", "heartbeat", "Dummy"),
            lib_ra.get_resource_agent_name_from_string("ocf:heartbeat:Dummy")
        )

    def test_refuses_string_if_is_not_valid(self):
        self.assertRaises(
            lib_ra.InvalidResourceAgentName,
            lambda: lib_ra.get_resource_agent_name_from_string(
                "invalid:resource:agent:string"
            )
        )

    def test_refuses_with_unknown_standard(self):
        self.assertRaises(
            lib_ra.InvalidResourceAgentName,
            lambda: lib_ra.get_resource_agent_name_from_string("unknown:Dummy")
        )

    def test_refuses_ocf_agent_name_without_provider(self):
        self.assertRaises(
            lib_ra.InvalidResourceAgentName,
            lambda: lib_ra.get_resource_agent_name_from_string("ocf:Dummy")
        )

    def test_refuses_non_ocf_agent_name_with_provider(self):
        self.assertRaises(
            lib_ra.InvalidResourceAgentName,
            lambda:
            lib_ra.get_resource_agent_name_from_string("lsb:provider:Dummy")
        )

    def test_returns_resource_agent_containing_sytemd_instance(self):
        self.assertEqual(
            lib_ra.ResourceAgentName("systemd", None, "lvm2-pvscan@252:2"),
            lib_ra.get_resource_agent_name_from_string(
                "systemd:lvm2-pvscan@252:2"
            )
        )

    def test_returns_resource_agent_containing_service_instance(self):
        self.assertEqual(
            lib_ra.ResourceAgentName("service", None, "lvm2-pvscan@252:2"),
            lib_ra.get_resource_agent_name_from_string(
                "service:lvm2-pvscan@252:2"
            )
        )

    def test_returns_resource_agent_containing_systemd_instance_short(self):
        self.assertEqual(
            lib_ra.ResourceAgentName("service", None, "getty@tty1"),
            lib_ra.get_resource_agent_name_from_string("service:getty@tty1")
        )

    def test_refuses_systemd_agent_name_with_provider(self):
        self.assertRaises(
            lib_ra.InvalidResourceAgentName,
            lambda: lib_ra.get_resource_agent_name_from_string(
                "sytemd:lvm2-pvscan252:@2"
            )
        )


class ListResourceAgentsStandardsTest(TestCase):
    def test_success_and_filter_stonith_out(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        agents = [
            "ocf",
            "lsb",
            "service",
            "systemd",
            "nagios",
            "stonith",
        ]
        # retval is number of providers found
        mock_runner.run.return_value = (
            "\n".join(agents) + "\n",
            "",
            len(agents)
        )

        self.assertEqual(
            lib_ra.list_resource_agents_standards(mock_runner),
            [
                "lsb",
                "nagios",
                "ocf",
                "service",
                "systemd",
            ]
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-standards"
        ])

    def test_success_filter_whitespace(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        agents = [
            "",
            "ocf",
            "  lsb",
            "service  ",
            "systemd",
            "  nagios  ",
            "",
            "stonith",
            "",
        ]
        # retval is number of providers found
        mock_runner.run.return_value = (
            "\n".join(agents) + "\n",
            "",
            len(agents)
        )

        self.assertEqual(
            lib_ra.list_resource_agents_standards(mock_runner),
            [
                "lsb",
                "nagios",
                "ocf",
                "service",
                "systemd",
            ]
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-standards"
        ])

    def test_empty(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.return_value = ("", "", 0)

        self.assertEqual(
            lib_ra.list_resource_agents_standards(mock_runner),
            []
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-standards"
        ])

    def test_error(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.return_value = ("lsb", "error", 1)

        self.assertEqual(
            lib_ra.list_resource_agents_standards(mock_runner),
            ["lsb"]
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-standards"
        ])


class ListResourceAgentsOcfProvidersTest(TestCase):
    def test_success(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        providers = [
            "heartbeat",
            "openstack",
            "pacemaker",
            "booth",
        ]
        # retval is number of providers found
        mock_runner.run.return_value = (
            "\n".join(providers) + "\n",
            "",
            len(providers)
        )

        self.assertEqual(
            lib_ra.list_resource_agents_ocf_providers(mock_runner),
            [
                "booth",
                "heartbeat",
                "openstack",
                "pacemaker",
            ]
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-ocf-providers"
        ])

    def test_success_filter_whitespace(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        providers = [
            "",
            "heartbeat",
            " openstack",
            "pacemaker ",
            " booth ",
        ]
        # retval is number of providers found
        mock_runner.run.return_value = (
            "\n".join(providers) + "\n",
            "",
            len(providers)
        )

        self.assertEqual(
            lib_ra.list_resource_agents_ocf_providers(mock_runner),
            [
                "booth",
                "heartbeat",
                "openstack",
                "pacemaker",
            ]
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-ocf-providers"
        ])

    def test_empty(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.return_value = ("", "", 0)

        self.assertEqual(
            lib_ra.list_resource_agents_ocf_providers(mock_runner),
            []
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-ocf-providers"
        ])

    def test_error(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.return_value = ("booth", "error", 1)

        self.assertEqual(
            lib_ra.list_resource_agents_ocf_providers(mock_runner),
            ["booth"]
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-ocf-providers"
        ])


class ListResourceAgentsStandardsAndProvidersTest(TestCase):
    def test_success(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.side_effect = [
            (
                "\n".join([
                    "ocf",
                    "lsb",
                    "service",
                    "systemd",
                    "nagios",
                    "stonith",
                    "",
                ]),
                "",
                0
            ),
            (
                "\n".join([
                    "heartbeat",
                    "openstack",
                    "pacemaker",
                    "booth",
                    "",
                ]),
                "",
                0
            ),
        ]

        self.assertEqual(
            lib_ra.list_resource_agents_standards_and_providers(mock_runner),
            [
                "lsb",
                "nagios",
                "ocf:booth",
                "ocf:heartbeat",
                "ocf:openstack",
                "ocf:pacemaker",
                "service",
                "systemd",
            ]
        )

        self.assertEqual(2, len(mock_runner.run.mock_calls))
        mock_runner.run.assert_has_calls([
            mock.call(["/usr/sbin/crm_resource", "--list-standards"]),
            mock.call(["/usr/sbin/crm_resource", "--list-ocf-providers"]),
        ])


class ListResourceAgentsTest(TestCase):
    def test_success_standard(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.return_value = (
            "\n".join([
                "docker",
                "Dummy",
                "dhcpd",
                "Dummy",
                "ethmonitor",
                "",
            ]),
            "",
            0
        )

        self.assertEqual(
            lib_ra.list_resource_agents(mock_runner, "ocf"),
            [
                "dhcpd",
                "docker",
                "Dummy",
                "Dummy",
                "ethmonitor",
            ]
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-agents", "ocf"
        ])

    def test_success_standard_provider(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.return_value = (
            "\n".join([
                "ping",
                "SystemHealth",
                "SysInfo",
                "HealthCPU",
                "Dummy",
                "",
            ]),
            "",
            0
        )

        self.assertEqual(
            lib_ra.list_resource_agents(mock_runner, "ocf:pacemaker"),
            [
                "Dummy",
                "HealthCPU",
                "ping",
                "SysInfo",
                "SystemHealth",
            ]
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-agents", "ocf:pacemaker"
        ])

    def test_bad_standard(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.return_value = (
            "",
            "No agents found for standard=nonsense, provider=*",
            1
        )

        self.assertEqual(
            lib_ra.list_resource_agents(mock_runner, "nonsense"),
            []
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-agents", "nonsense"
        ])


class ListStonithAgentsTest(TestCase):
    def test_success(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.return_value = (
            "\n".join([
                "fence_xvm",
                "fence_wti",
                "fence_vmware_soap",
                "fence_virt",
                "fence_scsi",
                "",
            ]),
            "",
            0
        )

        self.assertEqual(
            lib_ra.list_stonith_agents(mock_runner),
            [
                "fence_scsi",
                "fence_virt",
                "fence_vmware_soap",
                "fence_wti",
                "fence_xvm",
            ]
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-agents", "stonith"
        ])

    def test_no_agents(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.return_value = (
            "",
            "No agents found for standard=stonith provider=*",
            1
        )

        self.assertEqual(
            lib_ra.list_stonith_agents(mock_runner),
            []
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-agents", "stonith"
        ])

    def test_filter_hidden_agents(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.return_value = (
            "\n".join([
                "fence_na",
                "fence_wti",
                "fence_scsi",
                "fence_vmware_helper",
                "fence_nss_wrapper",
                "fence_node",
                "fence_vmware_soap",
                "fence_virt",
                "fence_pcmk",
                "fence_sanlockd",
                "fence_xvm",
                "fence_ack_manual",
                "fence_legacy",
                "fence_check",
                "fence_tool",
                "fence_kdump_send",
                "fence_virtd",
                "",
            ]),
            "",
            0
        )

        self.assertEqual(
            lib_ra.list_stonith_agents(mock_runner),
            [
                "fence_scsi",
                "fence_virt",
                "fence_vmware_soap",
                "fence_wti",
                "fence_xvm",
            ]
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_resource", "--list-agents", "stonith"
        ])


class GuessResourceAgentFullNameTest(TestCase):
    def setUp(self):
        self.mock_runner_side_effect = [
            # list standards
            ("ocf\n", "", 0),
            # list providers
            ("heartbeat\npacemaker\n", "", 0),
            # list agents for standard-provider pairs
            ("Delay\nDummy\n", "", 0),
            ("Dummy\nStateful\n", "", 0),
        ]

    def test_one_agent_list(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.side_effect = (
            self.mock_runner_side_effect
            +
            [
                ("<resource-agent />", "", 0)
            ]
        )

        self.assertEqual(
            [
                agent.get_name() for agent in
                lib_ra.guess_resource_agent_full_name(mock_runner, "delay")
            ],
            ["ocf:heartbeat:Delay"]
        )

    def test_one_agent_exception(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.side_effect = (
            self.mock_runner_side_effect
            +
            [
                ("<resource-agent />", "", 0),
            ]
        )

        self.assertEqual(
            lib_ra.guess_exactly_one_resource_agent_full_name(
                mock_runner,
                "delay"
            ).get_name(),
            "ocf:heartbeat:Delay"
        )

    def test_two_agents_list(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.side_effect = (
            self.mock_runner_side_effect
            +
            [
                ("<resource-agent />", "", 0),
                ("<resource-agent />", "", 0),
            ]
        )

        self.assertEqual(
            [
                agent.get_name() for agent in
                lib_ra.guess_resource_agent_full_name(mock_runner, "dummy")
            ],
            ["ocf:heartbeat:Dummy", "ocf:pacemaker:Dummy"]
        )

    def test_two_agents_one_valid_list(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.side_effect = (
            self.mock_runner_side_effect
            +
            [
                ("<resource-agent />", "", 0),
                ("invalid metadata", "", 0),
            ]
        )

        self.assertEqual(
            [
                agent.get_name() for agent in
                lib_ra.guess_resource_agent_full_name(mock_runner, "dummy")
            ],
            ["ocf:heartbeat:Dummy"]
        )

    def test_two_agents_exception(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.side_effect = (
            self.mock_runner_side_effect
            +
            [
                ("<resource-agent />", "", 0),
                ("<resource-agent />", "", 0),
            ]
        )

        assert_raise_library_error(
            lambda: lib_ra.guess_exactly_one_resource_agent_full_name(
                mock_runner,
                "dummy"
            ),
            (
                severity.ERROR,
                report_codes.AGENT_NAME_GUESS_FOUND_MORE_THAN_ONE,
                {
                    "agent": "dummy",
                    "possible_agents": [
                        "ocf:heartbeat:Dummy",
                        "ocf:pacemaker:Dummy"
                    ],
                }
            ),
        )

    def test_no_agents_list(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.side_effect = self.mock_runner_side_effect

        self.assertEqual(
            lib_ra.guess_resource_agent_full_name(mock_runner, "missing"),
            []
        )

    def test_no_agents_exception(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.side_effect = self.mock_runner_side_effect

        assert_raise_library_error(
            lambda: lib_ra.guess_exactly_one_resource_agent_full_name(
                mock_runner,
                "missing"
            ),
            (
                severity.ERROR,
                report_codes.AGENT_NAME_GUESS_FOUND_NONE,
                {
                    "agent": "missing",
                }
            ),
        )

    def test_no_valids_agent_list(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        mock_runner.run.side_effect = (
            self.mock_runner_side_effect
            +
            [
                ("invalid metadata", "", 0),
            ]
        )

        self.assertEqual(
            lib_ra.guess_resource_agent_full_name(mock_runner, "Delay"),
            []
        )


@patch_agent_object("_get_metadata")
class AgentMetadataGetShortdescTest(TestCase):
    def setUp(self):
        self.agent = lib_ra.Agent(
            mock.MagicMock(spec_set=CommandRunner)
        )

    def test_no_desc(self, mock_metadata):
        xml = '<resource-agent />'
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_shortdesc(),
            ""
        )

    def test_shortdesc_attribute(self, mock_metadata):
        xml = '<resource-agent shortdesc="short description" />'
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_shortdesc(),
            "short description"
        )

    def test_shortdesc_element(self, mock_metadata):
        xml = """
            <resource-agent>
                <shortdesc>  short \n description  </shortdesc>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_shortdesc(),
            "short \n description"
        )


@patch_agent_object("_get_metadata")
class AgentMetadataGetLongdescTest(TestCase):
    def setUp(self):
        self.agent = lib_ra.Agent(
            mock.MagicMock(spec_set=CommandRunner)
        )

    def test_no_desc(self, mock_metadata):
        xml = '<resource-agent />'
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_longdesc(),
            ""
        )

    def test_longesc_element(self, mock_metadata):
        xml = """
            <resource-agent>
                <longdesc>  long \n description  </longdesc>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_longdesc(),
            "long \n description"
        )


@patch_agent_object("_get_metadata")
class AgentMetadataGetParametersTest(TestCase):
    def setUp(self):
        self.agent = lib_ra.Agent(
            mock.MagicMock(spec_set=CommandRunner)
        )

    def test_no_parameters(self, mock_metadata):
        xml = """
            <resource-agent>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_parameters(),
            []
        )

    def test_empty_parameters(self, mock_metadata):
        xml = """
            <resource-agent>
                <parameters />
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_parameters(),
            []
        )

    def test_empty_parameter(self, mock_metadata):
        xml = """
            <resource-agent>
                <parameters>
                    <parameter />
                </parameters>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_parameters(),
            [
                {
                    "name": "",
                    "longdesc": "",
                    "shortdesc": "",
                    "type": "string",
                    "required": False,
                    "default": None,
                    "advanced": False,
                    "deprecated": False,
                    "obsoletes": None,
                }
            ]
        )

    def test_all_data_and_minimal_data(self, mock_metadata):
        xml = """
            <resource-agent>
                <parameters>
                    <parameter name="test_param" required="1">
                        <longdesc>
                            Long description
                        </longdesc>
                        <shortdesc>short description</shortdesc>
                        <content type="test_type" default="default_value" />
                    </parameter>
                    <parameter name="another parameter"/>
                </parameters>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_parameters(),
            [
                {
                    "name": "test_param",
                    "longdesc": "Long description",
                    "shortdesc": "short description",
                    "type": "test_type",
                    "required": True,
                    "default": "default_value",
                    "advanced": False,
                    "deprecated": False,
                    "obsoletes": None,
                },
                {
                    "name": "another parameter",
                    "longdesc": "",
                    "shortdesc": "",
                    "type": "string",
                    "required": False,
                    "default": None,
                    "advanced": False,
                    "deprecated": False,
                    "obsoletes": None,
                }
            ]
        )

    def test_remove_obsoletes_keep_deprecated(self, mock_metadata):
        xml = """
            <resource-agent>
                <parameters>
                    <parameter name="obsoletes" obsoletes="deprecated"/>
                    <parameter name="deprecated" deprecated="1"/>
                </parameters>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_parameters(),
            [
                {
                    "name": "deprecated",
                    "longdesc": "",
                    "shortdesc": "",
                    "type": "string",
                    "required": False,
                    "default": None,
                    "advanced": False,
                    "deprecated": True,
                    "obsoletes": None,
                },
            ]
        )

@patch_agent_object("_get_metadata")
class AgentMetadataGetActionsTest(TestCase):
    def setUp(self):
        self.agent = lib_ra.Agent(
            mock.MagicMock(spec_set=CommandRunner)
        )

    def test_no_actions(self, mock_metadata):
        xml = """
            <resource-agent>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_actions(),
            []
        )

    def test_empty_actions(self, mock_metadata):
        xml = """
            <resource-agent>
                <actions />
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_actions(),
            []
        )

    def test_empty_action(self, mock_metadata):
        xml = """
            <resource-agent>
                <actions>
                    <action />
                </actions>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_actions(),
            [{}]
        )

    def test_more_actions(self, mock_metadata):
        xml = """
            <resource-agent>
                <actions>
                    <action name="on" automatic="0"/>
                    <action name="off" />
                    <action name="reboot" />
                    <action name="status" />
                </actions>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_actions(),
            [
                {
                    "name": "on",
                    "automatic": "0"
                },
                {"name": "off"},
                {"name": "reboot"},
                {"name": "status"}
            ]
        )

    def test_remove_depth_with_0(self, mock_metadata):
        xml = """
            <resource-agent>
                <actions>
                    <action name="monitor" timeout="20" depth="0"/>
                </actions>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_actions(),
            [
                {
                    "name": "monitor",
                    "timeout": "20"
                },
            ]
        )

    def test_transfor_depth_to_OCF_CHECK_LEVEL(self, mock_metadata):
        xml = """
            <resource-agent>
                <actions>
                    <action name="monitor" timeout="20" depth="1"/>
                </actions>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_actions(),
            [
                {
                    "name": "monitor",
                    "timeout": "20",
                    "OCF_CHECK_LEVEL": "1",
                },
            ]
        )


@patch_agent_object("DEFAULT_CIB_ACTION_NAMES", ["monitor", "start"])
@patch_agent_object("get_actions")
class AgentMetadataGetCibDefaultActions(TestCase):
    def setUp(self):
        self.agent = lib_ra.Agent(
            mock.MagicMock(spec_set=CommandRunner)
        )

    def test_select_only_actions_for_cib(self, get_actions):
        get_actions.return_value = [
            {"name": "metadata"},
            {"name": "start", "interval": "40s"},
            {"name": "monitor", "interval": "10s", "timeout": "30s"},
        ]
        self.assertEqual(
            [
                {"name": "start", "interval": "40s"},
                {"name": "monitor", "interval": "10s", "timeout": "30s"}
            ],
            self.agent.get_cib_default_actions()
        )

    def test_complete_monitor(self, get_actions):
        get_actions.return_value = [{"name": "metadata"}]
        self.assertEqual(
            [{"name": "monitor", "interval": "60s"}],
            self.agent.get_cib_default_actions()
        )

    def test_complete_intervals(self, get_actions):
        get_actions.return_value = [
            {"name": "metadata"},
            {"name": "monitor", "timeout": "30s"},
        ]
        self.assertEqual(
            [{"name": "monitor", "interval": "60s", "timeout": "30s"}],
            self.agent.get_cib_default_actions()
        )

    def test_select_only_necessary_actions_for_cib(self, get_actions):
        get_actions.return_value = [
            {"name": "metadata"},
            {"name": "start", "interval": "40s"},
            {"name": "monitor", "interval": "10s", "timeout": "30s"},
        ]
        self.assertEqual(
            [
                {"name": "monitor", "interval": "10s", "timeout": "30s"}
            ],
            self.agent.get_cib_default_actions(necessary_only=True)
        )


@patch_agent_object("_get_metadata")
@patch_agent_object("get_name", lambda self: "agent-name")
class AgentMetadataGetInfoTest(TestCase):
    def setUp(self):
        self.agent = lib_ra.Agent(
            mock.MagicMock(spec_set=CommandRunner)
        )
        self.metadata = etree.XML("""
            <resource-agent>
                <shortdesc>short description</shortdesc>
                <longdesc>long description</longdesc>
                <parameters>
                    <parameter name="test_param" required="1">
                        <longdesc>
                            Long description
                        </longdesc>
                        <shortdesc>short description</shortdesc>
                        <content type="test_type" default="default_value" />
                    </parameter>
                    <parameter name="another parameter"/>
                </parameters>
                <actions>
                    <action name="on" automatic="0"/>
                    <action name="off" />
                </actions>
            </resource-agent>
        """)

    def test_name_info(self, mock_metadata):
        mock_metadata.return_value = self.metadata
        self.assertEqual(
            self.agent.get_name_info(),
            {
                "name": "agent-name",
                "shortdesc": "",
                "longdesc": "",
                "parameters": [],
                "actions": [],
            }
        )

    def test_description_info(self, mock_metadata):
        mock_metadata.return_value = self.metadata
        self.assertEqual(
            self.agent.get_description_info(),
            {
                "name": "agent-name",
                "shortdesc": "short description",
                "longdesc": "long description",
                "parameters": [],
                "actions": [],
            }
        )

    def test_full_info(self, mock_metadata):
        mock_metadata.return_value = self.metadata
        self.assertEqual(
            self.agent.get_full_info(),
            {
                "name": "agent-name",
                "shortdesc": "short description",
                "longdesc": "long description",
                "parameters": [
                    {
                        "name": "test_param",
                        "longdesc": "Long description",
                        "shortdesc": "short description",
                        "type": "test_type",
                        "required": True,
                        "default": "default_value",
                        "advanced": False,
                        "deprecated": False,
                        "obsoletes": None,
                    },
                    {
                        "name": "another parameter",
                        "longdesc": "",
                        "shortdesc": "",
                        "type": "string",
                        "required": False,
                        "default": None,
                        "advanced": False,
                        "deprecated": False,
                        "obsoletes": None,
                    }
                ],
                "actions": [
                    {
                        "name": "on",
                        "automatic": "0"
                    },
                    {"name": "off"},
                ],
                "default_actions": [{"name": "monitor", "interval": "60s"}],
            }
        )


@patch_agent_object("_get_metadata")
class AgentMetadataValidateParametersValuesTest(TestCase):
    def setUp(self):
        self.agent = lib_ra.Agent(
            mock.MagicMock(spec_set=CommandRunner)
        )
        self.metadata = etree.XML("""
            <resource-agent>
                <parameters>
                    <parameter name="test_param" required="0">
                        <longdesc>Long description</longdesc>
                        <shortdesc>short description</shortdesc>
                        <content type="string" default="default_value" />
                    </parameter>
                    <parameter name="required_param" required="1">
                        <content type="boolean" />
                    </parameter>
                    <parameter name="another_required_param" required="1">
                        <content type="string" />
                    </parameter>
                </parameters>
            </resource-agent>
        """)

    def test_all_required(self, mock_metadata):
        mock_metadata.return_value = self.metadata
        self.assertEqual(
            self.agent.validate_parameters_values({
                "another_required_param": "value1",
                "required_param": "value2",
            }),
            ([], [])
        )

    def test_all_required_and_optional(self, mock_metadata):
        mock_metadata.return_value = self.metadata
        self.assertEqual(
            self.agent.validate_parameters_values({
                "another_required_param": "value1",
                "required_param": "value2",
                "test_param": "value3",
            }),
            ([], [])
        )

    def test_all_required_and_invalid(self, mock_metadata):
        mock_metadata.return_value = self.metadata
        self.assertEqual(
            self.agent.validate_parameters_values({
                "another_required_param": "value1",
                "required_param": "value2",
                "invalid_param": "value3",
            }),
            (["invalid_param"], [])
        )

    def test_missing_required(self, mock_metadata):
        mock_metadata.return_value = self.metadata
        self.assertEqual(
            self.agent.validate_parameters_values({
            }),
            ([], ["required_param", "another_required_param"])
        )

    def test_missing_required_and_invalid(self, mock_metadata):
        mock_metadata.return_value = self.metadata
        self.assertEqual(
            self.agent.validate_parameters_values({
                "another_required_param": "value1",
                "invalid_param": "value3",
            }),
            (["invalid_param"], ["required_param"])
        )

    def test_ignore_obsoletes_use_deprecated(self, mock_metadata):
        xml = """
            <resource-agent>
                <parameters>
                    <parameter name="obsoletes" obsoletes="deprecated"
                        required="1"
                    />
                    <parameter name="deprecated" deprecated="1" required="1"/>
                </parameters>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.validate_parameters_values({
            }),
            ([], ["deprecated"])
        )

    def test_dont_allow_obsoletes_use_deprecated(self, mock_metadata):
        xml = """
            <resource-agent>
                <parameters>
                    <parameter name="obsoletes" obsoletes="deprecated"
                        required="1"
                    />
                    <parameter name="deprecated" deprecated="1" required="1"/>
                </parameters>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.validate_parameters_values({
                "obsoletes": "value",
            }),
            (["obsoletes"], ["deprecated"])
        )


class AgentMetadataValidateParameters(TestCase):
    def setUp(self):
        self.agent = lib_ra.Agent(mock.MagicMock(spec_set=CommandRunner))
        self.metadata = etree.XML("""
            <resource-agent>
                <parameters>
                    <parameter name="test_param" required="0">
                        <longdesc>Long description</longdesc>
                        <shortdesc>short description</shortdesc>
                        <content type="string" default="default_value" />
                    </parameter>
                    <parameter name="required_param" required="1">
                        <content type="boolean" />
                    </parameter>
                    <parameter name="another_required_param" required="1">
                        <content type="string" />
                    </parameter>
                </parameters>
            </resource-agent>
        """)
        patcher = patch_agent_object("_get_metadata")
        self.addCleanup(patcher.stop)
        self.get_metadata = patcher.start()
        self.get_metadata.return_value = self.metadata

    def test_returns_empty_report_when_all_required_there(self):
        self.assertEqual(
            [],
            self.agent.validate_parameters({
                "another_required_param": "value1",
                "required_param": "value2",
            }),
        )

    def test_returns_empty_report_when_all_required_and_optional_there(self):
        self.assertEqual(
            [],
            self.agent.validate_parameters({
                "another_required_param": "value1",
                "required_param": "value2",
                "test_param": "value3",
            })
        )

    def test_report_invalid_option(self):
        assert_report_item_list_equal(
            self.agent.validate_parameters({
                "another_required_param": "value1",
                "required_param": "value2",
                "invalid_param": "value3",
            }),
            [
                (
                    severity.ERROR,
                    report_codes.INVALID_OPTION,
                    {
                        "option_names": ["invalid_param"],
                        "option_type": "resource agent parameter",
                        "allowed": [
                            "another_required_param",
                            "required_param",
                            "test_param",
                        ]
                    },
                    report_codes.FORCE_OPTIONS
                ),
            ],
        )

    def test_report_missing_option(self):
        assert_report_item_list_equal(
            self.agent.validate_parameters({}),
            [
                (
                    severity.ERROR,
                    report_codes.REQUIRED_OPTION_IS_MISSING,
                    {
                        "option_names": [
                            "required_param",
                            "another_required_param",
                        ],
                        "option_type": "resource agent parameter",
                    },
                    report_codes.FORCE_OPTIONS
                ),
            ],
        )

    def test_warn_missing_required(self):
        assert_report_item_list_equal(
            self.agent.validate_parameters({}, allow_invalid=True),
            [
                (
                    severity.WARNING,
                    report_codes.REQUIRED_OPTION_IS_MISSING,
                    {
                        "option_names": [
                            "required_param",
                            "another_required_param",
                        ],
                        "option_type": "resource agent parameter",
                    },
                ),
            ]
        )

    def test_ignore_obsoletes_use_deprecated(self):
        xml = """
            <resource-agent>
                <parameters>
                    <parameter name="obsoletes" obsoletes="deprecated"
                        required="1"
                    />
                    <parameter name="deprecated" deprecated="1" required="1"/>
                </parameters>
            </resource-agent>
        """
        self.get_metadata.return_value = etree.XML(xml)
        assert_report_item_list_equal(
            self.agent.validate_parameters({}),
            [
                (
                    severity.ERROR,
                    report_codes.REQUIRED_OPTION_IS_MISSING,
                    {
                        "option_names": [
                            "deprecated",
                        ],
                        "option_type": "resource agent parameter",
                    },
                    report_codes.FORCE_OPTIONS
                ),
            ]
        )

    def test_dont_allow_obsoletes_use_deprecated(self):
        xml = """
            <resource-agent>
                <parameters>
                    <parameter name="obsoletes" obsoletes="deprecated"
                        required="1"
                    />
                    <parameter name="deprecated" deprecated="1" required="1"/>
                </parameters>
            </resource-agent>
        """
        self.get_metadata.return_value = etree.XML(xml)
        assert_report_item_list_equal(
            self.agent.validate_parameters({"obsoletes": "value"}),
            [
                (
                    severity.ERROR,
                    report_codes.REQUIRED_OPTION_IS_MISSING,
                    {
                        "option_names": [
                            "deprecated",
                        ],
                        "option_type": "resource agent parameter",
                    },
                    report_codes.FORCE_OPTIONS
                ),
                (
                    severity.ERROR,
                    report_codes.INVALID_OPTION,
                    {
                        "option_names": ["obsoletes"],
                        "option_type": "resource agent parameter",
                        "allowed": [
                            "deprecated",
                        ]
                    },
                    report_codes.FORCE_OPTIONS
                ),
            ]
        )


class StonithdMetadataGetMetadataTest(TestCase, ExtendedAssertionsMixin):
    def setUp(self):
        self.mock_runner = mock.MagicMock(spec_set=CommandRunner)
        self.agent = lib_ra.StonithdMetadata(self.mock_runner)

    def test_success(self):
        metadata = """
            <resource-agent>
                <shortdesc>stonithd test metadata</shortdesc>
            </resource-agent>
        """
        self.mock_runner.run.return_value = (metadata, "", 0)

        assert_xml_equal(
            str(XmlManipulation(self.agent._get_metadata())),
            metadata
        )

        self.mock_runner.run.assert_called_once_with(
            ["/usr/libexec/pacemaker/stonithd", "metadata"]
        )

    def test_failed_to_get_xml(self):
        self.mock_runner.run.return_value = ("", "some error", 1)

        self.assert_raises(
            lib_ra.UnableToGetAgentMetadata,
            self.agent._get_metadata,
            {
                "agent": "stonithd",
                "message": "some error",
            }
        )

        self.mock_runner.run.assert_called_once_with(
            ["/usr/libexec/pacemaker/stonithd", "metadata"]
        )

    def test_invalid_xml(self):
        self.mock_runner.run.return_value = ("some garbage", "", 0)

        self.assert_raises(
            lib_ra.UnableToGetAgentMetadata,
            self.agent._get_metadata,
            {
                "agent": "stonithd",
                "message": start_tag_error_text(),
            }
        )

        self.mock_runner.run.assert_called_once_with(
            ["/usr/libexec/pacemaker/stonithd", "metadata"]
        )


@patch_agent_object("_get_metadata")
class StonithdMetadataGetParametersTest(TestCase):
    def setUp(self):
        self.agent = lib_ra.StonithdMetadata(
            mock.MagicMock(spec_set=CommandRunner)
        )

    def test_success(self, mock_metadata):
        xml = """
            <resource-agent>
                <parameters>
                    <parameter name="test_param" required="0">
                        <longdesc>
                             Long description
                        </longdesc>
                        <shortdesc>
                             Advanced use only: short description
                        </shortdesc>
                        <content type="test_type" default="default_value" />
                    </parameter>
                    <parameter name="another parameter"/>
                </parameters>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertEqual(
            self.agent.get_parameters(),
            [
                {
                    "name": "test_param",
                    "longdesc":
                        "Advanced use only: short description\nLong "
                        "description",
                    "shortdesc": "Advanced use only: short description",
                    "type": "test_type",
                    "required": False,
                    "default": "default_value",
                    "advanced": True,
                    "deprecated": False,
                    "obsoletes": None,
                },
                {
                    "name": "another parameter",
                    "longdesc": "",
                    "shortdesc": "",
                    "type": "string",
                    "required": False,
                    "default": None,
                    "advanced": False,
                    "deprecated": False,
                    "obsoletes": None,
                }
            ]
        )


class CrmAgentDescendant(lib_ra.CrmAgent):
    def _prepare_name_parts(self, name):
        return lib_ra.ResourceAgentName("STANDARD", None, name)

    def get_name(self):
        return self.get_type()


class CrmAgentMetadataGetMetadataTest(TestCase, ExtendedAssertionsMixin):
    def setUp(self):
        self.mock_runner = mock.MagicMock(spec_set=CommandRunner)
        self.agent = CrmAgentDescendant(self.mock_runner, "TYPE")

    def test_success(self):
        metadata = """
            <resource-agent>
                <shortdesc>crm agent test metadata</shortdesc>
            </resource-agent>
        """
        self.mock_runner.run.return_value = (metadata, "", 0)

        assert_xml_equal(
            str(XmlManipulation(self.agent._get_metadata())),
            metadata
        )

        self.mock_runner.run.assert_called_once_with(
            [
                "/usr/sbin/crm_resource",
                "--show-metadata",
                self.agent._get_full_name()
            ],
             env_extend={
                 "PATH": "/usr/sbin/:/bin/:/usr/bin/",
             }
        )

    def test_failed_to_get_xml(self):
        self.mock_runner.run.return_value = ("", "some error", 1)

        self.assert_raises(
            lib_ra.UnableToGetAgentMetadata,
            self.agent._get_metadata,
            {
                "agent": self.agent.get_name(),
                "message": "some error",
            }
        )

        self.mock_runner.run.assert_called_once_with(
            [
                "/usr/sbin/crm_resource",
                "--show-metadata",
                self.agent._get_full_name()
            ],
             env_extend={
                 "PATH": "/usr/sbin/:/bin/:/usr/bin/",
             }
        )

    def test_invalid_xml(self):
        self.mock_runner.run.return_value = ("some garbage", "", 0)

        self.assert_raises(
            lib_ra.UnableToGetAgentMetadata,
            self.agent._get_metadata,
            {
                "agent": self.agent.get_name(),
                "message": start_tag_error_text(),
            }
        )

        self.mock_runner.run.assert_called_once_with(
            [
                "/usr/sbin/crm_resource",
                "--show-metadata",
                self.agent._get_full_name()
            ],
             env_extend={
                 "PATH": "/usr/sbin/:/bin/:/usr/bin/",
             }
        )


class CrmAgentMetadataIsValidAgentTest(TestCase):
    def setUp(self):
        self.mock_runner = mock.MagicMock(spec_set=CommandRunner)
        self.agent = CrmAgentDescendant(self.mock_runner, "TYPE")

    def test_success(self):
        metadata = """
            <resource-agent>
                <shortdesc>crm agent test metadata</shortdesc>
            </resource-agent>
        """
        self.mock_runner.run.return_value = (metadata, "", 0)

        self.assertTrue(self.agent.is_valid_metadata())

    def test_fail(self):
        self.mock_runner.run.return_value = ("", "", 1)

        self.assertFalse(self.agent.is_valid_metadata())


class StonithAgentMetadataGetNameTest(TestCase, ExtendedAssertionsMixin):
    def test_success(self):
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        agent_name = "fence_dummy"
        agent = lib_ra.StonithAgent(mock_runner, agent_name)

        self.assertEqual(agent.get_name(), agent_name)


class StonithAgentMetadataGetMetadataTest(TestCase, ExtendedAssertionsMixin):
    # Only test that correct name is going to crm_resource. Everything else is
    # covered by the parent class and therefore tested in its test.
    def setUp(self):
        self.mock_runner = mock.MagicMock(spec_set=CommandRunner)
        self.agent_name = "fence_dummy"
        self.agent = lib_ra.StonithAgent(
            self.mock_runner,
            self.agent_name
        )

    def tearDown(self):
        lib_ra.StonithAgent._stonithd_metadata = None

    def test_success(self):
        metadata = """
            <resource-agent>
                <shortdesc>crm agent test metadata</shortdesc>
            </resource-agent>
        """
        self.mock_runner.run.return_value = (metadata, "", 0)

        assert_xml_equal(
            str(XmlManipulation(self.agent._get_metadata())),
            metadata
        )

        self.mock_runner.run.assert_called_once_with(
            [
                "/usr/sbin/crm_resource",
                "--show-metadata",
                "stonith:{0}".format(self.agent_name)
            ],
             env_extend={
                 "PATH": "/usr/sbin/:/bin/:/usr/bin/",
             }
        )


class StonithAgentMetadataGetParametersTest(TestCase):
    def setUp(self):
        self.mock_runner = mock.MagicMock(spec_set=CommandRunner)
        self.agent_name = "fence_dummy"
        self.agent = lib_ra.StonithAgent(
            self.mock_runner,
            self.agent_name
        )

    def tearDown(self):
        lib_ra.StonithAgent._stonithd_metadata = None

    def test_success(self):
        metadata = """
            <resource-agent>
                <shortdesc>crm agent test metadata</shortdesc>
                <parameters>
                    <parameter name="debug"/>
                    <parameter name="valid_param"/>
                    <parameter name="verbose"/>
                    <parameter name="help"/>
                    <parameter name="action" required="1">
                        <shortdesc>Fencing Action</shortdesc>
                    </parameter>
                    <parameter name="another_param"/>
                    <parameter name="version"/>
                </parameters>
            </resource-agent>
        """
        stonithd_metadata = """
            <resource-agent>
                <parameters>
                    <parameter name="stonithd_param"/>
                </parameters>
            </resource-agent>
        """
        self.mock_runner.run.side_effect = [
            (metadata, "", 0),
            (stonithd_metadata, "", 0),
        ]

        self.assertEqual(
            self.agent.get_parameters(),
            [
                {
                    "name": "valid_param",
                    "longdesc": "",
                    "shortdesc": "",
                    "type": "string",
                    "required": False,
                    "default": None,
                    "advanced": False,
                    "deprecated": False,
                    "obsoletes": None,
                },
                {
                    "name": "action",
                    "longdesc": "",
                    "shortdesc":
                        "Fencing Action\nWARNING: specifying 'action' is"
                        " deprecated and not necessary with current Pacemaker"
                        " versions."
                    ,
                    "type": "string",
                    "required": False,
                    "default": None,
                    "advanced": False,
                    "deprecated": False,
                    "obsoletes": None,
                },
                {
                    "name": "another_param",
                    "longdesc": "",
                    "shortdesc": "",
                    "type": "string",
                    "required": False,
                    "default": None,
                    "advanced": False,
                    "deprecated": False,
                    "obsoletes": None,
                },
                {
                    "name": "stonithd_param",
                    "longdesc": "",
                    "shortdesc": "",
                    "type": "string",
                    "required": False,
                    "default": None,
                    "advanced": False,
                    "deprecated": False,
                    "obsoletes": None,
                },
            ]
        )

        self.assertEqual(2, len(self.mock_runner.run.mock_calls))
        self.mock_runner.run.assert_has_calls([
            mock.call(
                [
                    "/usr/sbin/crm_resource",
                    "--show-metadata",
                    "stonith:{0}".format(self.agent_name)
                ],
                 env_extend={
                     "PATH": "/usr/sbin/:/bin/:/usr/bin/",
                 }
            ),
            mock.call(
                ["/usr/libexec/pacemaker/stonithd", "metadata"]
            ),
        ])


@patch_agent_object("_get_metadata")
class StonithAgentMetadataGetProvidesUnfencingTest(TestCase):
    def setUp(self):
        self.agent = lib_ra.StonithAgent(
            mock.MagicMock(spec_set=CommandRunner),
            "fence_dummy"
        )

    def tearDown(self):
        lib_ra.StonithAgent._stonithd_metadata = None

    def test_true(self, mock_metadata):
        xml = """
            <resource-agent>
                <actions>
                    <action name="off" />
                    <action name="on" on_target="1" automatic="1"/>
                    <action name="reboot" />
                    <action name="status" />
                </actions>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertTrue(self.agent.get_provides_unfencing())

    def test_no_action_on(self, mock_metadata):
        xml = """
            <resource-agent>
                <actions>
                    <action name="off" />
                    <action name="reboot" />
                    <action name="status" />
                </actions>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertFalse(self.agent.get_provides_unfencing())

    def test_no_tagret(self, mock_metadata):
        xml = """
            <resource-agent>
                <actions>
                    <action name="off" />
                    <action name="on" automatic="1"/>
                    <action name="reboot" />
                    <action name="status" />
                </actions>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertFalse(self.agent.get_provides_unfencing())

    def test_no_automatic(self, mock_metadata):
        xml = """
            <resource-agent>
                <actions>
                    <action name="off" />
                    <action name="on" on_target="1" />
                    <action name="reboot" />
                    <action name="status" />
                </actions>
            </resource-agent>
        """
        mock_metadata.return_value = etree.XML(xml)
        self.assertFalse(self.agent.get_provides_unfencing())


class ResourceAgentTest(TestCase):
    def test_raises_on_invalid_name(self):
        self.assertRaises(
            lib_ra.InvalidResourceAgentName,
            lambda: lib_ra.ResourceAgent(mock.MagicMock(), "invalid_name")
        )

    def test_does_not_raise_on_valid_name(self):
        lib_ra.ResourceAgent(mock.MagicMock(), "ocf:heardbeat:name")


@patch_agent_object("_get_metadata")
class ResourceAgentGetParameters(TestCase):
    def fixture_metadata(self, params):
        return etree.XML("""
            <resource-agent>
                <parameters>{0}</parameters>
            </resource-agent>
        """.format(['<parameter name="{0}" />'.format(name) for name in params])
        )

    def assert_param_names(self, expected_names, actual_params):
        self.assertEqual(
            expected_names,
            [param["name"] for param in actual_params]
        )

    def test_add_trace_parameters_to_ocf(self, mock_metadata):
        mock_metadata.return_value = self.fixture_metadata(["test_param"])
        agent = lib_ra.ResourceAgent(
            mock.MagicMock(spec_set=CommandRunner),
            "ocf:pacemaker:test"
        )
        self.assert_param_names(
            ["test_param", "trace_ra", "trace_file"],
            agent.get_parameters()
        )

    def test_do_not_add_trace_parameters_if_present(self, mock_metadata):
        mock_metadata.return_value = self.fixture_metadata([
            "trace_ra", "test_param", "trace_file"
        ])
        agent = lib_ra.ResourceAgent(
            mock.MagicMock(spec_set=CommandRunner),
            "ocf:pacemaker:test"
        )
        self.assert_param_names(
            ["trace_ra", "test_param", "trace_file"],
            agent.get_parameters()
        )

    def test_do_not_add_trace_parameters_to_others(self, mock_metadata):
        mock_metadata.return_value = self.fixture_metadata(["test_param"])
        agent = lib_ra.ResourceAgent(
            mock.MagicMock(spec_set=CommandRunner),
            "service:test"
        )
        self.assert_param_names(
            ["test_param"],
            agent.get_parameters()
        )


class FindResourceAgentByNameTest(TestCase):
    def setUp(self):
        self.report_processor = mock.MagicMock()
        self.runner = mock.MagicMock()
        self.run = partial(
            lib_ra.find_valid_resource_agent_by_name,
            self.report_processor,
            self.runner,
        )

    @patch_agent("reports.agent_name_guessed")
    @patch_agent("guess_exactly_one_resource_agent_full_name")
    def test_returns_guessed_agent(self, mock_guess, mock_report):
        #setup
        name = "Delay"
        guessed_name =  "ocf:heartbeat:Delay"
        report = "AGENT_NAME_GUESSED"

        agent = mock.MagicMock(get_name=mock.Mock(return_value=guessed_name))
        mock_guess.return_value = agent
        mock_report.return_value = report

        #test
        self.assertEqual(agent, self.run(name))
        mock_guess.assert_called_once_with(self.runner, name)
        self.report_processor.process.assert_called_once_with(report)
        mock_report.assert_called_once_with(name, guessed_name)

    @patch_agent("ResourceAgent")
    def test_returns_real_agent_when_is_there(self, ResourceAgent):
        #setup
        name = "ocf:heartbeat:Delay"

        agent = mock.MagicMock()
        agent.validate_metadata = mock.Mock(return_value=agent)
        ResourceAgent.return_value = agent

        #test
        self.assertEqual(agent, self.run(name))
        ResourceAgent.assert_called_once_with(self.runner, name)

    @patch_agent("resource_agent_error_to_report_item")
    @patch_agent("AbsentResourceAgent")
    @patch_agent("ResourceAgent")
    def test_returns_absent_agent_on_metadata_load_fail(
        self, ResourceAgent, AbsentResourceAgent, error_to_report_item
    ):
        #setup
        name = "ocf:heartbeat:Some"
        report = "UNABLE_TO_GET_AGENT_METADATA"
        e = lib_ra.UnableToGetAgentMetadata(name, "metadata missing")
        agent = 'absent agent'

        ResourceAgent.side_effect = e
        error_to_report_item.return_value = report
        AbsentResourceAgent.return_value = agent

        #test
        self.assertEqual(agent, self.run(name, allowed_absent=True))
        ResourceAgent.assert_called_once_with(self.runner, name)
        AbsentResourceAgent.assert_called_once_with(self.runner, name)
        error_to_report_item.assert_called_once_with(
            e, severity=severity.WARNING
        )
        self.report_processor.process.assert_called_once_with(report)

    @patch_agent("resource_agent_error_to_report_item")
    @patch_agent("ResourceAgent")
    def test_raises_on_metatdata_load_fail_disallowed_absent(
        self, ResourceAgent, error_to_report_item
    ):
        name = "ocf:heartbeat:Some"
        report = "UNABLE_TO_GET_AGENT_METADATA"
        e = lib_ra.UnableToGetAgentMetadata(name, "metadata missing")

        ResourceAgent.side_effect = e
        error_to_report_item.return_value = report

        with self.assertRaises(LibraryError) as context_manager:
            self.run(name)

        self.assertEqual(report, context_manager.exception.args[0])
        ResourceAgent.assert_called_once_with(self.runner, name)
        error_to_report_item.assert_called_once_with(e, forceable=True)

    @patch_agent("resource_agent_error_to_report_item")
    @patch_agent("ResourceAgent")
    def test_raises_on_invalid_name(self, ResourceAgent, error_to_report_item):
        name = "ocf:heartbeat:Something:else"
        report = "INVALID_RESOURCE_AGENT_NAME"
        e = lib_ra.InvalidResourceAgentName(name, "invalid agent name")

        ResourceAgent.side_effect = e
        error_to_report_item.return_value = report

        with self.assertRaises(LibraryError) as context_manager:
            self.run(name)

        self.assertEqual(report, context_manager.exception.args[0])
        ResourceAgent.assert_called_once_with(self.runner, name)
        error_to_report_item.assert_called_once_with(e)


class FindStonithAgentByName(TestCase):
    # It is quite similar to find_valid_stonith_agent_by_name, so only minimum
    # tests here:
    # - test success
    # - test with ":" in agent name - there was a bug
    def setUp(self):
        self.report_processor = mock.MagicMock()
        self.runner = mock.MagicMock()
        self.run = partial(
            lib_ra.find_valid_stonith_agent_by_name,
            self.report_processor,
            self.runner,
        )

    @patch_agent("StonithAgent")
    def test_returns_real_agent_when_is_there(self, StonithAgent):
        #setup
        name = "fence_xvm"

        agent = mock.MagicMock()
        agent.validate_metadata = mock.Mock(return_value=agent)
        StonithAgent.return_value = agent

        #test
        self.assertEqual(agent, self.run(name))
        StonithAgent.assert_called_once_with(self.runner, name)

    @patch_agent("resource_agent_error_to_report_item")
    @patch_agent("StonithAgent")
    def test_raises_on_invalid_name(self, StonithAgent, error_to_report_item):
        name = "fence_xvm:invalid"
        report = "INVALID_STONITH_AGENT_NAME"
        e = lib_ra.InvalidStonithAgentName(name, "invalid agent name")

        StonithAgent.side_effect = e
        error_to_report_item.return_value = report

        with self.assertRaises(LibraryError) as context_manager:
            self.run(name)

        self.assertEqual(report, context_manager.exception.args[0])
        StonithAgent.assert_called_once_with(self.runner, name)
        error_to_report_item.assert_called_once_with(e)


class AbsentResourceAgentTest(TestCase):
    @mock.patch.object(lib_ra.CrmAgent, "_load_metadata")
    def test_behaves_like_a_proper_agent(self, load_metadata):
        name =  "ocf:heartbeat:Absent"
        runner = mock.MagicMock(spec_set=CommandRunner)
        load_metadata.return_value = "<resource-agent/>"

        agent = lib_ra.ResourceAgent(runner, name)
        absent = lib_ra.AbsentResourceAgent(runner, name)

        #metadata are valid
        absent.validate_metadata()
        self.assertTrue(absent.is_valid_metadata())

        self.assertEqual(agent.get_name(), absent.get_name())
        self.assertEqual(
            agent.get_description_info(), absent.get_description_info()
        )
        self.assertEqual(agent.get_full_info(), absent.get_full_info())
        self.assertEqual(agent.get_shortdesc(), absent.get_shortdesc())
        self.assertEqual(agent.get_longdesc(), absent.get_longdesc())
        self.assertEqual(agent.get_parameters(), absent.get_parameters())
        self.assertEqual(agent.get_actions(), absent.get_actions())
        self.assertEqual(([], []), absent.validate_parameters_values({
            "whatever": "anything"
        }))
