import logging

from sqlalchemy import and_

from dataall.core.environment.db.environment_repositories import EnvironmentRepository
from dataall.core.environment.env_permission_checker import has_group_permission
from dataall.base.db import exceptions
from dataall.core.permissions import permissions
from dataall.core.vpc.db import vpc_models as models
from dataall.core.permissions.permission_checker import has_resource_permission, has_tenant_permission
from dataall.base.context import get_context
from dataall.core.activity.db.activity_models import Activity
from dataall.core.permissions.db.resource_policy_repositories import ResourcePolicy

log = logging.getLogger(__name__)


class Vpc:
    def __init__(self):
        pass

    @staticmethod
    @has_tenant_permission(permissions.MANAGE_ENVIRONMENTS)
    @has_resource_permission(permissions.CREATE_NETWORK)
    @has_group_permission(permissions.CREATE_NETWORK)
    def create_network(session, uri: str, admin_group: str, data: dict = None) -> models.Vpc:
        Vpc._validate_input(data)
        username = get_context().username

        vpc = (
            session.query(models.Vpc)
            .filter(
                and_(
                    models.Vpc.VpcId == data['vpcId'], models.Vpc.environmentUri == uri
                )
            )
            .first()
        )

        if vpc:
            raise exceptions.ResourceAlreadyExists(
                action=permissions.CREATE_NETWORK,
                message=f'Vpc {data["vpcId"]} is already associated to environment {uri}',
            )

        environment = EnvironmentRepository.get_environment_by_uri(session, uri)
        vpc = models.Vpc(
            environmentUri=environment.environmentUri,
            region=environment.region,
            AwsAccountId=environment.AwsAccountId,
            VpcId=data['vpcId'],
            privateSubnetIds=data.get('privateSubnetIds', []),
            publicSubnetIds=data.get('publicSubnetIds', []),
            SamlGroupName=data['SamlGroupName'],
            owner=username,
            label=data['label'],
            name=data['label'],
            default=data.get('default', False),
        )
        session.add(vpc)
        session.commit()

        activity = Activity(
            action='NETWORK:CREATE',
            label='NETWORK:CREATE',
            owner=username,
            summary=f'{username} created network {vpc.label} in {environment.label}',
            targetUri=vpc.vpcUri,
            targetType='Vpc',
        )
        session.add(activity)

        ResourcePolicy.attach_resource_policy(
            session=session,
            group=vpc.SamlGroupName,
            permissions=permissions.NETWORK_ALL,
            resource_uri=vpc.vpcUri,
            resource_type=models.Vpc.__name__,
        )

        if environment.SamlGroupName != vpc.SamlGroupName:
            ResourcePolicy.attach_resource_policy(
                session=session,
                group=environment.SamlGroupName,
                permissions=permissions.NETWORK_ALL,
                resource_uri=vpc.vpcUri,
                resource_type=models.Vpc.__name__,
            )

        return vpc

    @staticmethod
    def _validate_input(data):
        if not data:
            raise exceptions.RequiredParameter(data)
        if not data.get('environmentUri'):
            raise exceptions.RequiredParameter('environmentUri')
        if not data.get('SamlGroupName'):
            raise exceptions.RequiredParameter('group')
        if not data.get('label'):
            raise exceptions.RequiredParameter('label')

    @staticmethod
    @has_tenant_permission(permissions.MANAGE_ENVIRONMENTS)
    @has_resource_permission(permissions.DELETE_NETWORK)
    def delete(session, uri) -> bool:
        vpc = Vpc.get_vpc_by_uri(session, uri)
        session.delete(vpc)
        ResourcePolicy.delete_resource_policy(
            session=session, resource_uri=uri, group=vpc.SamlGroupName
        )
        session.commit()
        return True

    @staticmethod
    def get_vpc_by_uri(session, vpc_uri) -> models.Vpc:
        vpc = session.query(models.Vpc).get(vpc_uri)
        if not vpc:
            raise exceptions.ObjectNotFound('VPC', vpc_uri)
        return vpc

    @staticmethod
    def get_environment_vpc_list(session, environment_uri):
        return (
            session.query(models.Vpc)
            .filter(models.Vpc.environmentUri == environment_uri)
            .all()
        )

    @staticmethod
    def get_environment_default_vpc(session, environment_uri):
        return (
            session.query(models.Vpc)
            .filter(
                and_(
                    models.Vpc.environmentUri == environment_uri,
                    models.Vpc.default == True,
                )
            )
            .first()
        )
