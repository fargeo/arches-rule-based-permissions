from django.apps import AppConfig
from arches.settings_utils import generate_frontend_configuration


class RuleBasedPermsConfig(AppConfig):
    name = "arches_rule_based_permissions"
    verbose_name = "Rule Based Permissions"
    is_arches_application = True

    def ready(self):
        generate_frontend_configuration()
