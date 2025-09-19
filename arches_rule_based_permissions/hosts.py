import re
from django_hosts import patterns, host

host_patterns = patterns(
    "",
    host(
        re.sub(r"_", r"-", r"arches_rule_based_permissions"),
        "arches_rule_based_permissions.urls",
        name="arches_rule_based_permissions",
    ),
)
