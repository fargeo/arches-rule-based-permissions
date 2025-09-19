import json
from arches.app.datatypes.datatypes import DataTypeFactory
from arches.app.models import models
from arches.app.search.elasticsearch_dsl_builder import Bool, Nested, Terms, GeoShape
from arches.app.search.mappings import RESOURCES_INDEX
from arches.app.search.search_engine_factory import SearchEngineFactory
from django.contrib.auth.models import User, Group
from django.db.models import Exists, OuterRef, Q
from django.db.models.fields.json import KT
from django.db.models.query import QuerySet
from django.http import HttpRequest

from arches_rule_based_permissions.models import RuleConfig
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.db.models.functions import AsGeoJSON, Transform
import json


class PermissionRules:

    def __init__(self):
        self.configs = RuleConfig.objects.all()

    def filter_tile_has_value(
        self, rule_config: RuleConfig, user, filter="db", qs=None
    ):
        node_id = rule_config.node.nodeid
        nodegroup_id = rule_config.nodegroup.nodegroupid
        value = rule_config.value["value"]
        if filter == "db":
            nodegroups = [nodegroup_id]
            tiles = (
                models.TileModel.objects.filter(
                    resourceinstance=OuterRef("resourceinstanceid"),
                    nodegroup_id__in=nodegroups,
                )
                .annotate(
                    node=KT(f"data__{node_id}"),
                )
                .filter(Q(node=value))
            )
            return models.ResourceInstance.objects.filter(
                Q(Exists(tiles)) | Q(principaluser_id=user.id)
            )
        else:
            documents = Bool()
            string_factory = DataTypeFactory().get_instance("concept")
            val = {"op": "~", "val": value, "lang": "en"}
            string_factory.append_search_filters(
                val, models.Node.objects.get(nodeid=node_id), documents, HttpRequest()
            )
            result = Bool()
            result.must(Nested(path="tiles", query=documents))
            return result

    def filter_tile_does_not_have_value(self, filter="db", actions=[], qs=None):
        pass

    def filter_resource_has_lifecycle_state(
        self, rule_config: RuleConfig, user, filter="db", qs=None
    ):
        value = rule_config.value["value"]
        if filter == "db":
            return models.ResourceInstance.objects.filter(
                resource_instance_lifecycle_state__in=value
            )
        else:
            term_query = Terms(
                field="resource_instance_lifecycle_state_id", terms=value
            )
            result = Bool()
            result.must(term_query)
            return result

    def filter_tile_spatial(self, rule_config, user, filter="db", qs=None):

        resource_instance_id = (
            rule_config.value["resource_instance_id"]
            if "resource_instance_id" in rule_config.value
            else None
        )
        value = rule_config.value["geojson"]
        op = rule_config.value["op"]

        search_query = Bool()
        if filter == "db":
            if resource_instance_id:
                return models.ResourceInstance.objects.filter(
                    geojsongeometry__geom__intersects=models.GeoJSONGeometry.objects.filter(
                        resourceinstance_id=resource_instance_id
                    ).values(
                        "geom"
                    )
                )
            else:
                geom = GEOSGeometry(json.dumps(value), srid=4326)
                return models.ResourceInstance.objects.filter(
                    geojsongeometry__geom__intersects=geom
                )
        else:
            if resource_instance_id:
                geojson_object = json.loads(
                    models.GeoJSONGeometry.objects.annotate(
                        json=AsGeoJSON(Transform("geom", 4326))
                    )
                    .get(resourceinstance_id=resource_instance_id)
                    .json
                )
                spatial_query = Bool()

                geoshape = GeoShape(
                    field="geometries.geom.features.geometry",
                    type=geojson_object["type"],
                    coordinates=geojson_object["coordinates"],
                )
                spatial_query.filter(geoshape)
                search_query.filter(Nested(path="geometries", query=spatial_query))
                return search_query
            else:
                spatial_query = Bool()
                geoshape = GeoShape(
                    field="geometries.geom.features.geometry",
                    type=value["type"],
                    coordinates=value["coordinates"],
                )
                spatial_query.filter(geoshape)
                search_query.filter(Nested(path="geometries", query=spatial_query))
                return search_query

    def get_config_groups(self, user: User) -> QuerySet[Group]:
        unique_user_groups = set()
        for rule_config in self.configs:
            groups = rule_config.groups.all().values_list("name", flat=True)
            unique_user_groups.update(list(groups))

        return user.groups.filter(name__in=unique_user_groups)

    def permission_handler(self, user, actions=["view_resourceinstance"], filter="db"):
        filters = {
            "filter_tile_has_value": self.filter_tile_has_value,
            "filter_tile_does_not_have_value": self.filter_tile_does_not_have_value,
            "filter_resource_has_lifecycle_state": self.filter_resource_has_lifecycle_state,
            "filter_tile_spatial": self.filter_tile_spatial,
        }

        user_groups = self.get_config_groups(user)
        res = None

        if len(user_groups):
            queries = []
            final_query = Bool()
            number_of_queries = 0
            for rule_config in self.configs:
                if (
                    rule_config.active
                    and (rule_config.groups.all() & user_groups.all()).exists()
                    and set(rule_config.actions).intersection(actions)
                ):
                    res = filters[rule_config.type](
                        rule_config,
                        user,
                        filter,
                    )
                    if filter == "db":
                        queries.append(res)
                    else:
                        final_query.should(res)
                        number_of_queries += 1
        else:
            return models.ResourceInstance.objects.none()

        if filter == "db":
            return queries[0].union(*queries[1:]) if len(queries) > 1 else queries[0]
        else:
            if number_of_queries:
                return final_query
            else:
                return None
