import mock
import pytest
import requests

from collections import namedtuple

from awx.api.views import (
    ApiVersionRootView,
    JobTemplateLabelList,
    JobTemplateSurveySpec,
    InventoryInventorySourcesUpdate,
    HostInsights,
)


@pytest.fixture
def mock_response_new(mocker):
    m = mocker.patch('awx.api.views.Response.__new__')
    m.return_value = m
    return m


class TestApiRootView:
    def test_get_endpoints(self, mocker, mock_response_new):
        endpoints = [
            'authtoken',
            'ping',
            'config',
            #'settings',
            'me',
            'dashboard',
            'organizations',
            'users',
            'projects',
            'teams',
            'credentials',
            'inventory',
            'inventory_scripts',
            'inventory_sources',
            'groups',
            'hosts',
            'job_templates',
            'jobs',
            'ad_hoc_commands',
            'system_job_templates',
            'system_jobs',
            'schedules',
            'notification_templates',
            'notifications',
            'labels',
            'unified_job_templates',
            'unified_jobs',
            'activity_stream',
            'workflow_job_templates',
            'workflow_jobs',
        ]
        view = ApiVersionRootView()
        ret = view.get(mocker.MagicMock())

        assert ret == mock_response_new
        data_arg = mock_response_new.mock_calls[0][1][1]
        for endpoint in endpoints:
            assert endpoint in data_arg


class TestJobTemplateLabelList:
    def test_inherited_mixin_unattach(self):
        with mock.patch('awx.api.generics.DeleteLastUnattachLabelMixin.unattach') as mixin_unattach:
            view = JobTemplateLabelList()
            mock_request = mock.MagicMock()

            super(JobTemplateLabelList, view).unattach(mock_request, None, None)
            assert mixin_unattach.called_with(mock_request, None, None)


class TestJobTemplateSurveySpec(object):
    @mock.patch('awx.api.views.feature_enabled', lambda feature: True)
    def test_get_password_type(self, mocker, mock_response_new):
        JobTemplate = namedtuple('JobTemplate', 'survey_spec')
        obj = JobTemplate(survey_spec={'spec':[{'type': 'password', 'default': 'my_default'}]})
        with mocker.patch.object(JobTemplateSurveySpec, 'get_object', return_value=obj):
            view = JobTemplateSurveySpec()
            response = view.get(mocker.MagicMock())
            assert response == mock_response_new
            # which there was a better way to do this!
            assert response.call_args[0][1]['spec'][0]['default'] == '$encrypted$'


class TestInventoryInventorySourcesUpdate:

    @pytest.mark.parametrize("can_update, can_access, is_source, is_up_on_proj, expected", [
        (True, True, "ec2", False, [{'status': 'started', 'inventory_update': 1, 'inventory_source': 1}]),
        (False, True, "gce", False, [{'status': 'Could not start because `can_update` returned False', 'inventory_source': 1}]),
        (True, False, "scm", True, [{'status': 'You do not have permission to update project `project`', 'inventory_source': 1}]),
    ])
    def test_post(self, mocker, can_update, can_access, is_source, is_up_on_proj, expected):
        class InventoryUpdate:
            id = 1

        class Project:
            name = 'project'

        InventorySource = namedtuple('InventorySource', ['source', 'update_on_project_update', 'pk', 'can_update',
                                                         'update', 'source_project'])

        class InventorySources(object):
            def all(self):
                return [InventorySource(pk=1, source=is_source, source_project=Project,
                                        update_on_project_update=is_up_on_proj,
                                        can_update=can_update, update=lambda:InventoryUpdate)]

        Inventory = namedtuple('Inventory', ['inventory_sources'])
        obj = Inventory(inventory_sources=InventorySources())

        mock_request = mocker.MagicMock()
        mock_request.user.can_access.return_value = can_access

        with mocker.patch.object(InventoryInventorySourcesUpdate, 'get_object', return_value=obj):
            view = InventoryInventorySourcesUpdate()
            response = view.post(mock_request)
            assert response.data == expected


class TestHostInsights():

    @pytest.fixture
    def patch_parent(self, mocker):
        mocker.patch('awx.api.generics.GenericAPIView')

    @pytest.mark.parametrize("status_code, exception, error, message", [
        (500, requests.exceptions.SSLError, 'SSLError while trying to connect to https://myexample.com/whocares/me/', None,),
        (504, requests.exceptions.Timeout, 'Request to https://myexample.com/whocares/me/ timed out.', None,),
        (500, requests.exceptions.RequestException, 'booo!', 'Unkown exception booo! while trying to GET https://myexample.com/whocares/me/'),
    ])
    def test_get_insights_request_exception(self, patch_parent, mocker, status_code, exception, error, message):
        view = HostInsights()
        mocker.patch.object(view, '_get_insights', side_effect=exception(error))

        (msg, code) = view.get_insights('https://myexample.com/whocares/me/', 'ignore', 'ignore')
        assert code == status_code
        assert msg['error'] == message or error

    def test_get_insights_non_200(self, patch_parent, mocker):
        view = HostInsights()
        Response = namedtuple('Response', 'status_code content')
        mocker.patch.object(view, '_get_insights', return_value=Response(500, 'hello world!'))

        (msg, code) = view.get_insights('https://myexample.com/whocares/me/', 'ignore', 'ignore')
        assert msg['error'] == 'Failed to gather reports and maintenance plans from Insights API. Server responded with 500 status code and message hello world!'

    def test_get_insights_malformed_json_content(self, patch_parent, mocker):
        view = HostInsights()
        
        class Response():
            status_code = 200
            content = 'booo!'

            def json(self):
                raise ValueError('we do not care what this is')
        
        mocker.patch.object(view, '_get_insights', return_value=Response())

        (msg, code) = view.get_insights('https://myexample.com/whocares/me/', 'ignore', 'ignore')
        assert msg['error'] == 'Expected JSON response from Insights but instead got booo!'
        assert code == 500

