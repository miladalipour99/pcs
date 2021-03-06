import os.path
from unittest import mock, TestCase
from lxml import etree

from pcs_test.tools.assertions import (
    assert_raise_library_error,
    assert_xml_equal,
    start_tag_error_text,
)
from pcs_test.tools import fixture
from pcs_test.tools.command_env import get_env_tools
from pcs_test.tools.misc import get_test_resource as rc
from pcs_test.tools.xml import etree_to_str, XmlManipulation

from pcs import settings
from pcs.common import report_codes
from pcs.common.reports import ReportItemSeverity as Severity
from pcs.common.tools import Version
import pcs.lib.pacemaker.live as lib
from pcs.lib.external import CommandRunner

# pylint: disable=no-self-use

def get_runner(stdout="", stderr="", returncode=0, env_vars=None):
    runner = mock.MagicMock(spec_set=CommandRunner)
    runner.run.return_value = (stdout, stderr, returncode)
    runner.env_vars = env_vars if env_vars else {}
    return runner


class LibraryPacemakerTest(TestCase):
    @staticmethod
    def path(name):
        return os.path.join(settings.pacemaker_binaries, name)

    def crm_mon_cmd(self):
        return [self.path("crm_mon"), "--one-shot", "--as-xml", "--inactive"]


class GetClusterStatusXmlTest(LibraryPacemakerTest):
    def test_success(self):
        expected_stdout = "<xml />"
        expected_stderr = ""
        expected_retval = 0
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        real_xml = lib.get_cluster_status_xml(mock_runner)

        mock_runner.run.assert_called_once_with(self.crm_mon_cmd())
        self.assertEqual(expected_stdout, real_xml)

    def test_error(self):
        expected_stdout = "some info"
        expected_stderr = "some error"
        expected_retval = 1
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        assert_raise_library_error(
            lambda: lib.get_cluster_status_xml(mock_runner),
            (
                Severity.ERROR,
                report_codes.CRM_MON_ERROR,
                {
                    "reason": expected_stderr + "\n" + expected_stdout,
                }
            )
        )

        mock_runner.run.assert_called_once_with(self.crm_mon_cmd())

class GetClusterStatusText(TestCase):
    def setUp(self):
        self.mock_fencehistory_supported = mock.patch(
            "pcs.lib.pacemaker.live.is_fence_history_supported_status",
            return_value=True
        )
        self.mock_fencehistory_supported.start()
        self.expected_stdout = "cluster status"
        self.expected_stderr = ""
        self.expected_retval = 0

    def tearDown(self):
        self.mock_fencehistory_supported.stop()

    def get_runner(self, stdout=None, stderr=None, retval=None):
        return get_runner(
            self.expected_stdout if stdout is None else stdout,
            self.expected_stderr if stderr is None else stderr,
            self.expected_retval if retval is None else retval,
        )

    def test_success_minimal(self):
        mock_runner = self.get_runner()
        real_status, warnings = lib.get_cluster_status_text(
            mock_runner, False, False
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_mon", "--one-shot", "--inactive"
        ])
        self.assertEqual(self.expected_stdout, real_status)
        self.assertEqual(warnings, [])

    def test_success_verbose(self):
        mock_runner = self.get_runner()
        real_status, warnings = lib.get_cluster_status_text(
            mock_runner, False, True
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_mon", "--one-shot", "--inactive", "--show-detail",
            "--show-node-attributes", "--failcounts", "--fence-history=3",
        ])
        self.assertEqual(self.expected_stdout, real_status)
        self.assertEqual(warnings, [])

    def test_success_no_fence_history(self):
        self.mock_fencehistory_supported.stop()
        self.mock_fencehistory_supported = mock.patch(
            "pcs.lib.pacemaker.live.is_fence_history_supported_status",
            return_value=False
        )
        self.mock_fencehistory_supported.start()

        mock_runner = self.get_runner()
        real_status, warnings = lib.get_cluster_status_text(
            mock_runner, False, True
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_mon", "--one-shot", "--inactive", "--show-detail",
            "--show-node-attributes", "--failcounts",
        ])
        self.assertEqual(self.expected_stdout, real_status)
        self.assertEqual(warnings, [])

    def test_success_hide_inactive(self):
        mock_runner = self.get_runner()
        real_status, warnings = lib.get_cluster_status_text(
            mock_runner, True, False
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_mon", "--one-shot"
        ])
        self.assertEqual(self.expected_stdout, real_status)
        self.assertEqual(warnings, [])

    def test_success_hide_inactive_verbose(self):
        mock_runner = self.get_runner()
        real_status, warnings = lib.get_cluster_status_text(
            mock_runner, True, True
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_mon", "--one-shot", "--show-detail",
            "--show-node-attributes", "--failcounts", "--fence-history=3",
        ])
        self.assertEqual(self.expected_stdout, real_status)
        self.assertEqual(warnings, [])

    def test_error(self):
        mock_runner = self.get_runner("stdout", "stderr", 1)
        assert_raise_library_error(
            lambda: lib.get_cluster_status_text(mock_runner, False, False),
            (
                fixture.error(
                    report_codes.CRM_MON_ERROR,
                    reason="stderr\nstdout"
                )
            )
        )
        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_mon", "--one-shot", "--inactive"
        ])

    def test_warnings(self):
        mock_runner = self.get_runner(
            stderr="msgA\nDEBUG: msgB\nmsgC\nDEBUG: msgd\n"
        )
        real_status, warnings = lib.get_cluster_status_text(
            mock_runner, False, False
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_mon", "--one-shot", "--inactive"
        ])
        self.assertEqual(self.expected_stdout, real_status)
        self.assertEqual(warnings, ["msgA", "msgC"])

    def test_warnings_verbose(self):
        mock_runner = self.get_runner(
            stderr="msgA\nDEBUG: msgB\nmsgC\nDEBUG: msgd\n"
        )
        real_status, warnings = lib.get_cluster_status_text(
            mock_runner, False, True
        )

        mock_runner.run.assert_called_once_with([
            "/usr/sbin/crm_mon", "--one-shot", "--inactive", "--show-detail",
            "--show-node-attributes", "--failcounts", "--fence-history=3",
        ])
        self.assertEqual(self.expected_stdout, real_status)
        self.assertEqual(
            warnings,
            ["msgA", "DEBUG: msgB", "msgC", "DEBUG: msgd"]
        )

class GetCibXmlTest(LibraryPacemakerTest):
    def test_success(self):
        expected_stdout = "<xml />"
        expected_stderr = ""
        expected_retval = 0
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        real_xml = lib.get_cib_xml(mock_runner)

        mock_runner.run.assert_called_once_with(
            [self.path("cibadmin"), "--local", "--query"]
        )
        self.assertEqual(expected_stdout, real_xml)

    def test_error(self):
        expected_stdout = "some info"
        expected_stderr = "some error"
        expected_retval = 1
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        assert_raise_library_error(
            lambda: lib.get_cib_xml(mock_runner),
            (
                Severity.ERROR,
                report_codes.CIB_LOAD_ERROR,
                {
                    "reason": expected_stderr + "\n" + expected_stdout,
                }
            )
        )

        mock_runner.run.assert_called_once_with(
            [self.path("cibadmin"), "--local", "--query"]
        )

    def test_success_scope(self):
        expected_stdout = "<xml />"
        expected_stderr = ""
        expected_retval = 0
        scope = "test_scope"
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        real_xml = lib.get_cib_xml(mock_runner, scope)

        mock_runner.run.assert_called_once_with(
            [
                self.path("cibadmin"),
                "--local", "--query", "--scope={0}".format(scope)
            ]
        )
        self.assertEqual(expected_stdout, real_xml)

    def test_scope_error(self):
        expected_stdout = "some info"
        # yes, the numbers do not match, tested and verified with
        # pacemaker-2.0.0-1.fc29.1.x86_64
        expected_stderr = (
            "Call cib_query failed (-6): No such device or address"
        )
        expected_retval = 105
        scope = "test_scope"
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        assert_raise_library_error(
            lambda: lib.get_cib_xml(mock_runner, scope=scope),
            (
                Severity.ERROR,
                report_codes.CIB_LOAD_ERROR_SCOPE_MISSING,
                {
                    "scope": scope,
                    "reason": expected_stderr + "\n" + expected_stdout,
                }
            )
        )

        mock_runner.run.assert_called_once_with(
            [
                self.path("cibadmin"),
                "--local", "--query", "--scope={0}".format(scope)
            ]
        )

class GetCibTest(LibraryPacemakerTest):
    def test_success(self):
        xml = "<xml />"
        assert_xml_equal(xml, str(XmlManipulation((lib.get_cib(xml)))))

    def test_invalid_xml(self):
        xml = "<invalid><xml />"
        assert_raise_library_error(
            lambda: lib.get_cib(xml),
            (
                Severity.ERROR,
                report_codes.CIB_LOAD_ERROR_BAD_FORMAT,
                {
                }
            )
        )

class Verify(LibraryPacemakerTest):
    def test_run_on_live_cib(self):
        runner = get_runner()
        self.assertEqual(
            lib.verify(runner),
            ("", "", 0, False)
        )
        runner.run.assert_called_once_with(
            [self.path("crm_verify"), "--live-check"],
        )

    def test_run_on_mocked_cib(self):
        fake_tmp_file = "/fake/tmp/file"
        runner = get_runner(env_vars={"CIB_file": fake_tmp_file})

        self.assertEqual(lib.verify(runner), ("", "", 0, False))
        runner.run.assert_called_once_with(
            [self.path("crm_verify"), "--xml-file", fake_tmp_file],
        )

    def test_run_verbose(self):
        runner = get_runner()
        self.assertEqual(
            lib.verify(runner, verbose=True),
            ("", "", 0, False)
        )
        runner.run.assert_called_once_with(
            [self.path("crm_verify"), "-V", "-V", "--live-check"],
        )

    def test_run_verbose_on_mocked_cib(self):
        fake_tmp_file = "/fake/tmp/file"
        runner = get_runner(env_vars={"CIB_file": fake_tmp_file})

        self.assertEqual(
            lib.verify(runner, verbose=True),
            ("", "", 0, False)
        )
        runner.run.assert_called_once_with(
            [self.path("crm_verify"), "-V", "-V", "--xml-file", fake_tmp_file],
        )

    @staticmethod
    def get_in_out_filtered_stderr():
        in_stderr = (
            (
                "Errors found during check: config not valid\n",
                "  -V may provide more details\n",
            ),
            (
                "Warnings found during check: config may not be valid\n",
                "  Use -V -V for more detail\n",
            ),
            (
                "some output\n",
                "another output\n",
                "-V -V -V more details...\n",
            ),
            (
                "some output\n",
                "before-V -V -V in the middle more detailafter\n",
                "another output\n",
            ),
        )
        out_stderr = []
        for input_lines in in_stderr:
            out_stderr.append([
                line for line in input_lines if "-V" not in line
            ])
        return zip(in_stderr, out_stderr)

    @staticmethod
    def get_in_out_unfiltered_data():
        in_out_data = (
            (
                "no verbose option in stderr\n",
            ),
            (
                "some output\n",
                "Options '-V -V' do not match\n",
                "because line missing 'more details'\n",
            ),
        )
        return zip(in_out_data, in_out_data)

    def subtest_filter_stderr_and_can_be_more_verbose(
        self, in_out_tuple_list, can_be_more_verbose, verbose=False,
    ):
        fake_tmp_file = "/fake/tmp/file"
        runner = get_runner(env_vars={"CIB_file": fake_tmp_file})
        for in_stderr, out_stderr in in_out_tuple_list:
            with self.subTest(in_stderr=in_stderr, out_stderr=out_stderr):
                runner = get_runner(
                    stderr="".join(in_stderr),
                    returncode=78,
                    env_vars={"CIB_file": fake_tmp_file},
                )
                self.assertEqual(
                    lib.verify(runner, verbose=verbose),
                    ("", "".join(out_stderr), 78, can_be_more_verbose),
                )
                args = [self.path("crm_verify")]
                if verbose:
                    args.extend(["-V", "-V"])
                args.extend(["--xml-file", fake_tmp_file])
                runner.run.assert_called_once_with(args)

    def test_error_can_be_more_verbose(self):
        self.subtest_filter_stderr_and_can_be_more_verbose(
            self.get_in_out_filtered_stderr(),
            True,
        )

    def test_error_cannot_be_more_verbose(self):
        self.subtest_filter_stderr_and_can_be_more_verbose(
            self.get_in_out_unfiltered_data(),
            False,
        )

    def test_error_cannot_be_more_verbose_in_verbose_mode(self):
        self.subtest_filter_stderr_and_can_be_more_verbose(
            (
                list(self.get_in_out_filtered_stderr())
                +
                list(self.get_in_out_unfiltered_data())
            ),
            False,
            verbose=True,
        )


class ReplaceCibConfigurationTest(LibraryPacemakerTest):
    def test_success(self):
        xml = "<xml/>"
        expected_stdout = "expected output"
        expected_stderr = ""
        expected_retval = 0
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        lib.replace_cib_configuration(
            mock_runner,
            XmlManipulation.from_str(xml).tree
        )

        mock_runner.run.assert_called_once_with(
            [
                self.path("cibadmin"), "--replace", "--verbose", "--xml-pipe",
                "--scope", "configuration"
            ],
            stdin_string=xml
        )

    def test_error(self):
        xml = "<xml/>"
        expected_stdout = "expected output"
        expected_stderr = "expected stderr"
        expected_retval = 1
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        assert_raise_library_error(
            lambda: lib.replace_cib_configuration(
                    mock_runner,
                    XmlManipulation.from_str(xml).tree
                )
            ,
            (
                Severity.ERROR,
                report_codes.CIB_PUSH_ERROR,
                {
                    "reason": expected_stderr,
                    "pushed_cib": expected_stdout,
                }
            )
        )

        mock_runner.run.assert_called_once_with(
            [
                self.path("cibadmin"), "--replace", "--verbose", "--xml-pipe",
                "--scope", "configuration"
            ],
            stdin_string=xml
        )

class UpgradeCibTest(TestCase):
    # pylint: disable=protected-access
    def test_success(self):
        mock_runner = get_runner("", "", 0)
        lib._upgrade_cib(mock_runner)
        mock_runner.run.assert_called_once_with(
            ["/usr/sbin/cibadmin", "--upgrade", "--force"]
        )

    def test_error(self):
        expected_stdout = "some info"
        expected_stderr = "some error"
        expected_retval = 1
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )
        assert_raise_library_error(
            lambda: lib._upgrade_cib(mock_runner),
            (
                Severity.ERROR,
                report_codes.CIB_UPGRADE_FAILED,
                {
                    "reason": expected_stderr + "\n" + expected_stdout,
                }
            )
        )
        mock_runner.run.assert_called_once_with(
            ["/usr/sbin/cibadmin", "--upgrade", "--force"]
        )

@mock.patch("pcs.lib.pacemaker.live.get_cib_xml")
@mock.patch("pcs.lib.pacemaker.live._upgrade_cib")
class EnsureCibVersionTest(TestCase):
    def setUp(self):
        self.mock_runner = mock.MagicMock(spec_set=CommandRunner)
        self.cib = etree.XML('<cib validate-with="pacemaker-2.3.4"/>')

    def test_same_version(self, mock_upgrade, mock_get_cib):
        self.assertTrue(
            lib.ensure_cib_version(
                self.mock_runner, self.cib, Version(2, 3, 4)
            ) is None
        )
        mock_upgrade.assert_not_called()
        mock_get_cib.assert_not_called()

    def test_higher_version(self, mock_upgrade, mock_get_cib):
        self.assertTrue(
            lib.ensure_cib_version(
                self.mock_runner, self.cib, Version(2, 3, 3)
            ) is None
        )
        mock_upgrade.assert_not_called()
        mock_get_cib.assert_not_called()

    def test_upgraded_same_version(self, mock_upgrade, mock_get_cib):
        upgraded_cib = '<cib validate-with="pacemaker-2.3.5"/>'
        mock_get_cib.return_value = upgraded_cib
        assert_xml_equal(
            upgraded_cib,
            etree.tostring(
                lib.ensure_cib_version(
                    self.mock_runner, self.cib, Version(2, 3, 5)
                )
            ).decode()
        )
        mock_upgrade.assert_called_once_with(self.mock_runner)
        mock_get_cib.assert_called_once_with(self.mock_runner)

    def test_upgraded_higher_version(self, mock_upgrade, mock_get_cib):
        upgraded_cib = '<cib validate-with="pacemaker-2.3.6"/>'
        mock_get_cib.return_value = upgraded_cib
        assert_xml_equal(
            upgraded_cib,
            etree.tostring(
                lib.ensure_cib_version(
                    self.mock_runner, self.cib, Version(2, 3, 5)
                )
            ).decode()
        )
        mock_upgrade.assert_called_once_with(self.mock_runner)
        mock_get_cib.assert_called_once_with(self.mock_runner)

    def test_upgraded_lower_version(self, mock_upgrade, mock_get_cib):
        mock_get_cib.return_value = etree.tostring(self.cib).decode()
        assert_raise_library_error(
            lambda: lib.ensure_cib_version(
                self.mock_runner, self.cib, Version(2, 3, 5)
            ),
            (
                Severity.ERROR,
                report_codes.CIB_UPGRADE_FAILED_TO_MINIMAL_REQUIRED_VERSION,
                {
                    "required_version": "2.3.5",
                    "current_version": "2.3.4"
                }
            )
        )
        mock_upgrade.assert_called_once_with(self.mock_runner)
        mock_get_cib.assert_called_once_with(self.mock_runner)

    def test_cib_parse_error(self, mock_upgrade, mock_get_cib):
        mock_get_cib.return_value = "not xml"
        assert_raise_library_error(
            lambda: lib.ensure_cib_version(
                self.mock_runner, self.cib, Version(2, 3, 5)
            ),
            (
                Severity.ERROR,
                report_codes.CIB_UPGRADE_FAILED,
                {
                    "reason":
                        start_tag_error_text(),
                }
            )
        )
        mock_upgrade.assert_called_once_with(self.mock_runner)
        mock_get_cib.assert_called_once_with(self.mock_runner)


@mock.patch("pcs.lib.pacemaker.live.write_tmpfile")
class SimulateCibXml(LibraryPacemakerTest):
    def test_success(self, mock_write_tmpfile):
        tmpfile_new_cib = mock.MagicMock()
        tmpfile_new_cib.name = rc("new_cib.tmp")
        tmpfile_new_cib.read.return_value = "new cib data"
        tmpfile_transitions = mock.MagicMock()
        tmpfile_transitions.name = rc("transitions.tmp")
        tmpfile_transitions.read.return_value = "transitions data"
        mock_write_tmpfile.side_effect = [tmpfile_new_cib, tmpfile_transitions]

        expected_stdout = "simulate output"
        expected_stderr = ""
        expected_retval = 0
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        result = lib.simulate_cib_xml(mock_runner, "<cib />")
        self.assertEqual(result[0], expected_stdout)
        self.assertEqual(result[1], "transitions data")
        self.assertEqual(result[2], "new cib data")

        mock_runner.run.assert_called_once_with(
            [
                self.path("crm_simulate"),
                "--simulate",
                "--save-output", tmpfile_new_cib.name,
                "--save-graph", tmpfile_transitions.name,
                "--xml-pipe",
            ],
            stdin_string="<cib />"
        )

    def test_error_creating_cib(self, mock_write_tmpfile):
        mock_write_tmpfile.side_effect = OSError(1, "some error")
        mock_runner = get_runner()
        assert_raise_library_error(
            lambda: lib.simulate_cib_xml(mock_runner, "<cib />"),
            fixture.error(
                report_codes.CIB_SIMULATE_ERROR,
                reason="some error",
            ),
        )
        mock_runner.run.assert_not_called()

    def test_error_creating_transitions(self, mock_write_tmpfile):
        tmpfile_new_cib = mock.MagicMock()
        mock_write_tmpfile.side_effect = [
            tmpfile_new_cib,
            OSError(1, "some error")
        ]
        mock_runner = get_runner()
        assert_raise_library_error(
            lambda: lib.simulate_cib_xml(mock_runner, "<cib />"),
            fixture.error(
                report_codes.CIB_SIMULATE_ERROR,
                reason="some error",
            ),
        )
        mock_runner.run.assert_not_called()

    def test_error_running_simulate(self, mock_write_tmpfile):
        tmpfile_new_cib = mock.MagicMock()
        tmpfile_new_cib.name = rc("new_cib.tmp")
        tmpfile_transitions = mock.MagicMock()
        tmpfile_transitions.name = rc("transitions.tmp")
        mock_write_tmpfile.side_effect = [tmpfile_new_cib, tmpfile_transitions]

        expected_stdout = "some stdout"
        expected_stderr = "some error"
        expected_retval = 1
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        assert_raise_library_error(
            lambda: lib.simulate_cib_xml(mock_runner, "<cib />"),
            fixture.error(
                report_codes.CIB_SIMULATE_ERROR,
                reason="some error",
            ),
        )

    def test_error_reading_cib(self, mock_write_tmpfile):
        tmpfile_new_cib = mock.MagicMock()
        tmpfile_new_cib.name = rc("new_cib.tmp")
        tmpfile_new_cib.read.side_effect = OSError(1, "some error")
        tmpfile_transitions = mock.MagicMock()
        tmpfile_transitions.name = rc("transitions.tmp")
        mock_write_tmpfile.side_effect = [tmpfile_new_cib, tmpfile_transitions]

        expected_stdout = "simulate output"
        expected_stderr = ""
        expected_retval = 0
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        assert_raise_library_error(
            lambda: lib.simulate_cib_xml(mock_runner, "<cib />"),
            fixture.error(
                report_codes.CIB_SIMULATE_ERROR,
                reason="some error",
            ),
        )

    def test_error_reading_transitions(self, mock_write_tmpfile):
        tmpfile_new_cib = mock.MagicMock()
        tmpfile_new_cib.name = rc("new_cib.tmp")
        tmpfile_new_cib.read.return_value = "new cib data"
        tmpfile_transitions = mock.MagicMock()
        tmpfile_transitions.name = rc("transitions.tmp")
        tmpfile_transitions.read.side_effect = OSError(1, "some error")
        mock_write_tmpfile.side_effect = [tmpfile_new_cib, tmpfile_transitions]

        expected_stdout = "simulate output"
        expected_stderr = ""
        expected_retval = 0
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        assert_raise_library_error(
            lambda: lib.simulate_cib_xml(mock_runner, "<cib />"),
            fixture.error(
                report_codes.CIB_SIMULATE_ERROR,
                reason="some error",
            ),
        )


@mock.patch("pcs.lib.pacemaker.live.simulate_cib_xml")
class SimulateCib(TestCase):
    def setUp(self):
        self.runner = "mock runner"
        self.cib_xml = "<cib/>"
        self.cib = etree.fromstring(self.cib_xml)
        self.simulate_output = "  some output  "
        self.transitions = "<transitions/>"
        self.new_cib = "<new-cib/>"

    def test_success(self, mock_simulate):
        mock_simulate.return_value = (
            self.simulate_output, self.transitions, self.new_cib
        )
        result = lib.simulate_cib(self.runner, self.cib)
        self.assertEqual(result[0], "some output")
        self.assertEqual(etree_to_str(result[1]), self.transitions)
        self.assertEqual(etree_to_str(result[2]), self.new_cib)
        mock_simulate.assert_called_once_with(self.runner, self.cib_xml)

    def test_invalid_cib(self, mock_simulate):
        mock_simulate.return_value = (
            self.simulate_output, "bad transitions", self.new_cib
        )
        assert_raise_library_error(
            lambda: lib.simulate_cib(self.runner, self.cib),
            fixture.error(
                report_codes.CIB_SIMULATE_ERROR,
                reason=(
                    "Start tag expected, '<' not found, line 1, column 1 "
                    "(<string>, line 1)"
                ),
            ),
        )

    def test_invalid_transitions(self, mock_simulate):
        mock_simulate.return_value = (
            self.simulate_output, self.transitions, "bad new cib"
        )
        assert_raise_library_error(
            lambda: lib.simulate_cib(self.runner, self.cib),
            fixture.error(
                report_codes.CIB_SIMULATE_ERROR,
                reason=(
                    "Start tag expected, '<' not found, line 1, column 1 "
                    "(<string>, line 1)"
                ),
            ),
        )


class GetLocalNodeStatusTest(TestCase):
    def setUp(self):
        self.env_assist, self.config = get_env_tools(test_case=self)

    def test_offline(self):
        (self.config
            .runner.pcmk.load_state(
                stderr="error: Could not connect to cluster (is it running?)",
                returncode=102
            )
        )

        env = self.env_assist.get_env()
        real_status = lib.get_local_node_status(env.cmd_runner())
        self.assertEqual(dict(offline=True), real_status)

    def test_invalid_status(self):
        (self.config
            .runner.pcmk.load_state(stdout="invalid xml")
        )

        env = self.env_assist.get_env()
        self.env_assist.assert_raise_library_error(
            lambda: lib.get_local_node_status(env.cmd_runner()),
            [
                fixture.error(
                    report_codes.BAD_CLUSTER_STATE_FORMAT,
                    force_code=None
                )
            ],
            expected_in_processor=False
        )

    def test_success(self):
        (self.config
            .runner.pcmk.load_state(nodes=[
                fixture.state_node(i, f"name_{i}") for i in range(1, 4)
            ])
            .runner.pcmk.local_node_name(node_name="name_2")
        )

        env = self.env_assist.get_env()
        real_status = lib.get_local_node_status(env.cmd_runner())
        self.assertEqual(
            dict(offline=False, **fixture.state_node("2", "name_2")),
            real_status
        )

    def test_node_not_in_status(self):
        (self.config
            .runner.pcmk.load_state(nodes=[
                fixture.state_node(i, f"name_{i}") for i in range(1, 4)
            ])
            .runner.pcmk.local_node_name(node_name="name_X")
        )

        env = self.env_assist.get_env()
        self.env_assist.assert_raise_library_error(
            lambda: lib.get_local_node_status(env.cmd_runner()),
            [
                fixture.error(
                    report_codes.NODE_NOT_FOUND,
                    force_code=None,
                    node="name_X",
                    searched_types=[]
                )
            ],
            expected_in_processor=False
        )

    def test_error_getting_node_name(self):
        (self.config
            .runner.pcmk.load_state(nodes=[
                fixture.state_node(i, f"name_{i}") for i in range(1, 4)
            ])
            .runner.pcmk.local_node_name(
                stdout="some info", stderr="some error", returncode=1
            )
        )

        env = self.env_assist.get_env()
        self.env_assist.assert_raise_library_error(
            lambda: lib.get_local_node_status(env.cmd_runner()),
            [
                fixture.error(
                    report_codes.PACEMAKER_LOCAL_NODE_NAME_NOT_FOUND,
                    force_code=None,
                    reason="some error\nsome info"
                )
            ],
            expected_in_processor=False
        )


class RemoveNode(LibraryPacemakerTest):
    def test_success(self):
        mock_runner = get_runner("", "", 0)
        lib.remove_node(
            mock_runner,
            "NODE_NAME"
        )
        mock_runner.run.assert_called_once_with([
            self.path("crm_node"),
            "--force",
            "--remove",
            "NODE_NAME",
        ])

    def test_error(self):
        expected_stderr = "expected stderr"
        mock_runner = get_runner("", expected_stderr, 1)
        assert_raise_library_error(
            lambda: lib.remove_node(mock_runner, "NODE_NAME"),
            (
                Severity.ERROR,
                report_codes.NODE_REMOVE_IN_PACEMAKER_FAILED,
                {
                    "node": None,
                    "node_list_to_remove": ["NODE_NAME"],
                    "reason": expected_stderr,
                }
            )
        )


class ResourceCleanupTest(TestCase):
    def setUp(self):
        self.stdout = "expected output"
        self.stderr = "expected stderr"
        self.resource = "my_resource"
        self.node = "my_node"
        self.env_assist, self.config = get_env_tools(test_case=self)

    def assert_output(self, real_output):
        self.assertEqual(
            self.stdout + "\n" + self.stderr,
            real_output
        )

    def test_basic(self):
        self.config.runner.pcmk.resource_cleanup(
            stdout=self.stdout,
            stderr=self.stderr
        )
        env = self.env_assist.get_env()
        real_output = lib.resource_cleanup(env.cmd_runner())
        self.assert_output(real_output)

    def test_resource(self):
        self.config.runner.pcmk.resource_cleanup(
            stdout=self.stdout,
            stderr=self.stderr,
            resource=self.resource
        )
        env = self.env_assist.get_env()
        real_output = lib.resource_cleanup(
            env.cmd_runner(), resource=self.resource
        )
        self.assert_output(real_output)

    def test_node(self):
        self.config.runner.pcmk.resource_cleanup(
            stdout=self.stdout,
            stderr=self.stderr,
            node=self.node
        )

        env = self.env_assist.get_env()
        real_output = lib.resource_cleanup(
            env.cmd_runner(), node=self.node
        )
        self.assert_output(real_output)

    def test_all_options(self):
        self.config.runner.pcmk.resource_cleanup(
            stdout=self.stdout,
            stderr=self.stderr,
            resource=self.resource,
            node=self.node
        )

        env = self.env_assist.get_env()
        real_output = lib.resource_cleanup(
            env.cmd_runner(), resource=self.resource, node=self.node
        )
        self.assert_output(real_output)

    def test_error_cleanup(self):
        self.config.runner.pcmk.resource_cleanup(
            stdout=self.stdout,
            stderr=self.stderr,
            returncode=1
        )

        env = self.env_assist.get_env()
        self.env_assist.assert_raise_library_error(
            lambda: lib.resource_cleanup(env.cmd_runner()),
            [
                fixture.error(
                    report_codes.RESOURCE_CLEANUP_ERROR,
                    force_code=None,
                    reason=(self.stderr + "\n" + self.stdout)
                )
            ],
            expected_in_processor=False
        )


class ResourceRefreshTest(LibraryPacemakerTest):
    def fixture_status_xml(self, nodes, resources):
        xml_man = XmlManipulation.from_file(rc("crm_mon.minimal.xml"))
        doc = xml_man.tree.getroottree()
        doc.find("/summary/nodes_configured").set("number", str(nodes))
        doc.find("/summary/resources_configured").set("number", str(resources))
        return str(XmlManipulation(doc))

    def test_basic(self):
        expected_stdout = "expected output"
        expected_stderr = "expected stderr"
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        call_list = [
            mock.call(self.crm_mon_cmd()),
            mock.call([self.path("crm_resource"), "--refresh"]),
        ]
        return_value_list = [
            (self.fixture_status_xml(1, 1), "", 0),
            (expected_stdout, expected_stderr, 0),
        ]
        mock_runner.run.side_effect = return_value_list

        real_output = lib.resource_refresh(mock_runner)

        self.assertEqual(len(return_value_list), len(call_list))
        self.assertEqual(len(return_value_list), mock_runner.run.call_count)
        mock_runner.run.assert_has_calls(call_list)
        self.assertEqual(
            expected_stdout + "\n" + expected_stderr,
            real_output
        )

    def test_threshold_exceeded(self):
        mock_runner = get_runner(
            self.fixture_status_xml(1000, 1000),
            "",
            0
        )

        assert_raise_library_error(
            lambda: lib.resource_refresh(mock_runner),
            (
                Severity.ERROR,
                report_codes.RESOURCE_REFRESH_TOO_TIME_CONSUMING,
                {"threshold": 100},
                report_codes.FORCE_LOAD_THRESHOLD
            )
        )

        mock_runner.run.assert_called_once_with(self.crm_mon_cmd())

    def test_threshold_exceeded_forced(self):
        expected_stdout = "expected output"
        expected_stderr = "expected stderr"
        mock_runner = get_runner(expected_stdout, expected_stderr, 0)

        real_output = lib.resource_refresh(mock_runner, force=True)

        mock_runner.run.assert_called_once_with(
            [self.path("crm_resource"), "--refresh"]
        )
        self.assertEqual(
            expected_stdout + "\n" + expected_stderr,
            real_output
        )

    def test_resource(self):
        resource = "test_resource"
        expected_stdout = "expected output"
        expected_stderr = "expected stderr"
        mock_runner = get_runner(expected_stdout, expected_stderr, 0)

        real_output = lib.resource_refresh(mock_runner, resource=resource)

        mock_runner.run.assert_called_once_with(
            [self.path("crm_resource"), "--refresh", "--resource", resource]
        )
        self.assertEqual(
            expected_stdout + "\n" + expected_stderr,
            real_output
        )

    def test_node(self):
        node = "test_node"
        expected_stdout = "expected output"
        expected_stderr = "expected stderr"
        mock_runner = get_runner(expected_stdout, expected_stderr, 0)

        real_output = lib.resource_refresh(mock_runner, node=node)

        mock_runner.run.assert_called_once_with(
            [self.path("crm_resource"), "--refresh", "--node", node]
        )
        self.assertEqual(
            expected_stdout + "\n" + expected_stderr,
            real_output
        )

    def test_full(self):
        expected_stdout = "expected output"
        expected_stderr = "expected stderr"
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        call_list = [
            mock.call(self.crm_mon_cmd()),
            mock.call([self.path("crm_resource"), "--refresh", "--force"]),
        ]
        return_value_list = [
            (self.fixture_status_xml(1, 1), "", 0),
            (expected_stdout, expected_stderr, 0),
        ]
        mock_runner.run.side_effect = return_value_list

        real_output = lib.resource_refresh(mock_runner, full=True)

        self.assertEqual(len(return_value_list), len(call_list))
        self.assertEqual(len(return_value_list), mock_runner.run.call_count)
        mock_runner.run.assert_has_calls(call_list)
        self.assertEqual(
            expected_stdout + "\n" + expected_stderr,
            real_output
        )

    def test_all_options(self):
        node = "test_node"
        resource = "test_resource"
        expected_stdout = "expected output"
        expected_stderr = "expected stderr"
        mock_runner = get_runner(expected_stdout, expected_stderr, 0)

        real_output = lib.resource_refresh(
            mock_runner, resource=resource, node=node, full=True
        )

        mock_runner.run.assert_called_once_with(
            [
                self.path("crm_resource"),
                "--refresh", "--resource", resource, "--node", node, "--force"
            ]
        )
        self.assertEqual(
            expected_stdout + "\n" + expected_stderr,
            real_output
        )

    def test_error_state(self):
        expected_stdout = "some info"
        expected_stderr = "some error"
        expected_retval = 1
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        assert_raise_library_error(
            lambda: lib.resource_refresh(mock_runner),
            (
                Severity.ERROR,
                report_codes.CRM_MON_ERROR,
                {
                    "reason": expected_stderr + "\n" + expected_stdout,
                }
            )
        )

        mock_runner.run.assert_called_once_with(self.crm_mon_cmd())

    def test_error_refresh(self):
        expected_stdout = "some info"
        expected_stderr = "some error"
        expected_retval = 1
        mock_runner = mock.MagicMock(spec_set=CommandRunner)
        call_list = [
            mock.call(self.crm_mon_cmd()),
            mock.call([self.path("crm_resource"), "--refresh"]),
        ]
        return_value_list = [
            (self.fixture_status_xml(1, 1), "", 0),
            (expected_stdout, expected_stderr, expected_retval),
        ]
        mock_runner.run.side_effect = return_value_list

        assert_raise_library_error(
            lambda: lib.resource_refresh(mock_runner),
            (
                Severity.ERROR,
                report_codes.RESOURCE_REFRESH_ERROR,
                {
                    "reason": expected_stderr + "\n" + expected_stdout,
                }
            )
        )

        self.assertEqual(len(return_value_list), len(call_list))
        self.assertEqual(len(return_value_list), mock_runner.run.call_count)
        mock_runner.run.assert_has_calls(call_list)


class ResourcesWaitingTest(LibraryPacemakerTest):
    def test_has_support(self):
        expected_stdout = ""
        expected_stderr = "something --wait something else"
        expected_retval = 1
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        self.assertTrue(
            lib.has_wait_for_idle_support(mock_runner)
        )
        mock_runner.run.assert_called_once_with(
            [self.path("crm_resource"), "-?"]
        )

    def test_has_support_stdout(self):
        expected_stdout = "something --wait something else"
        expected_stderr = ""
        expected_retval = 1
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        self.assertTrue(
            lib.has_wait_for_idle_support(mock_runner)
        )
        mock_runner.run.assert_called_once_with(
            [self.path("crm_resource"), "-?"]
        )

    def test_doesnt_have_support(self):
        expected_stdout = "something something else"
        expected_stderr = "something something else"
        expected_retval = 1
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        self.assertFalse(
            lib.has_wait_for_idle_support(mock_runner)
        )
        mock_runner.run.assert_called_once_with(
            [self.path("crm_resource"), "-?"]
        )

    @mock.patch(
        "pcs.lib.pacemaker.live.has_wait_for_idle_support",
        autospec=True
    )
    def test_ensure_support_success(self, mock_obj):
        mock_obj.return_value = True
        self.assertEqual(None, lib.ensure_wait_for_idle_support(mock.Mock()))

    @mock.patch(
        "pcs.lib.pacemaker.live.has_wait_for_idle_support",
        autospec=True
    )
    def test_ensure_support_error(self, mock_obj):
        mock_obj.return_value = False
        assert_raise_library_error(
            lambda: lib.ensure_wait_for_idle_support(mock.Mock()),
            (
                Severity.ERROR,
                report_codes.WAIT_FOR_IDLE_NOT_SUPPORTED,
                {}
            )
        )

    def test_wait_success(self):
        expected_stdout = "expected output"
        expected_stderr = "expected stderr"
        expected_retval = 0
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        self.assertEqual(None, lib.wait_for_idle(mock_runner))

        mock_runner.run.assert_called_once_with(
            [self.path("crm_resource"), "--wait"]
        )

    def test_wait_timeout_success(self):
        expected_stdout = "expected output"
        expected_stderr = "expected stderr"
        expected_retval = 0
        timeout = 10
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        self.assertEqual(None, lib.wait_for_idle(mock_runner, timeout))

        mock_runner.run.assert_called_once_with(
            [
                self.path("crm_resource"),
                "--wait", "--timeout={0}".format(timeout)
            ]
        )

    def test_wait_error(self):
        expected_stdout = "some info"
        expected_stderr = "some error"
        expected_retval = 1
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        assert_raise_library_error(
            lambda: lib.wait_for_idle(mock_runner),
            (
                Severity.ERROR,
                report_codes.WAIT_FOR_IDLE_ERROR,
                {
                    "reason": expected_stderr + "\n" + expected_stdout,
                }
            )
        )

        mock_runner.run.assert_called_once_with(
            [self.path("crm_resource"), "--wait"]
        )

    def test_wait_error_timeout(self):
        expected_stdout = "some info"
        expected_stderr = "some error"
        expected_retval = 124
        mock_runner = get_runner(
            expected_stdout,
            expected_stderr,
            expected_retval
        )

        assert_raise_library_error(
            lambda: lib.wait_for_idle(mock_runner),
            (
                Severity.ERROR,
                report_codes.WAIT_FOR_IDLE_TIMED_OUT,
                {
                    "reason": expected_stderr + "\n" + expected_stdout,
                }
            )
        )

        mock_runner.run.assert_called_once_with(
            [self.path("crm_resource"), "--wait"]
        )


class IsInPcmkToolHelp(TestCase):
    # pylint: disable=protected-access
    def test_all_in_stderr(self):
        mock_runner = get_runner("", "ABCDE", 0)
        self.assertTrue(
            lib._is_in_pcmk_tool_help(mock_runner, "", ["A", "C", "E"])
        )

    def test_all_in_stdout(self):
        mock_runner = get_runner("ABCDE", "", 0)
        self.assertTrue(
            lib._is_in_pcmk_tool_help(mock_runner, "", ["A", "C", "E"])
        )

    def test_some_in_stderr_all_in_stdout(self):
        mock_runner = get_runner("ABCDE", "ABC", 0)
        self.assertTrue(
            lib._is_in_pcmk_tool_help(mock_runner, "", ["A", "C", "E"])
        )

    def test_some_in_stderr_some_in_stdout(self):
        mock_runner = get_runner("CDE", "ABC", 0)
        self.assertFalse(
            lib._is_in_pcmk_tool_help(mock_runner, "", ["A", "C", "E"])
        )
