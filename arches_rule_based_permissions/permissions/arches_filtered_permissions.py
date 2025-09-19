"""
ARCHES - a program developed to inventory and manage immovable cultural heritage.
Copyright (C) 2013 J. Paul Getty Trust and World Monuments Fund
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.
You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

from __future__ import annotations

from django.contrib.auth.models import User, Group
from arches.app.permissions.arches_default_deny import (
    ArchesDefaultDenyPermissionFramework,
)
from arches.app.search.elasticsearch_dsl_builder import Bool, Nested, Terms
from arches.app.models.models import ResourceInstance
from arches.app.search.search import SearchEngine
import arches_rule_based_permissions.permissions.rules as rules


class ArchesFilteredPermissionFramework(ArchesDefaultDenyPermissionFramework):
    def __init__(self):
        self.rules = rules.PermissionRules()

    def get_filtered_instances(
        self,
        user: User,
        search_engine: SearchEngine | None = None,
        allresources: bool = False,
        resources: list[str] | None = None,
    ):
        if user.is_superuser:
            return True, resources
        resources = self.rules.permission_handler(user)
        return self.__class__.is_exclusive, resources.values_list(
            "resourceinstanceid", flat=True
        )

    def get_permission_search_filter(self, user: User) -> Bool:
        rule_access = self.rules.permission_handler(user, filter="search")
        principal_user = Terms(field="permissions.principal_user", terms=[str(user.id)])
        principal_user_term_filter = Nested(path="permissions", query=principal_user)
        has_access = Bool()
        has_access.should(principal_user_term_filter)
        if rule_access:
            has_access.should(rule_access)
        return has_access

    def get_perms(
        self, user_or_group: User | Group, obj: ResourceInstance
    ) -> list[str]:

        filters = {
            "filter_tile_has_value": self.rules.filter_tile_has_value,
            "filter_tile_does_not_have_value": self.rules.filter_tile_does_not_have_value,
            "filter_resource_has_lifecycle_state": self.rules.filter_resource_has_lifecycle_state,
            "filter_tile_spatial": self.rules.filter_tile_spatial,
        }
        user_groups = self.rules.get_config_groups(user_or_group)
        actions = set()
        if len(user_groups):
            for rule_config in self.rules.configs:
                if (rule_config.groups.all() & user_groups.all()).exists():
                    resources = filters[rule_config.type](
                        rule_config,
                        user_or_group,
                        "db",
                    )
                    if resources.filter(resourceinstanceid=obj.pk).exists():
                        actions.update(rule_config.actions)

        return list(actions)
