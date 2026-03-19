# arches-rule-based-permissions

A permission framework for [Arches](https://www.archesproject.org/) that controls which resources users can access based on configurable rules. Instead of assigning permissions resource-by-resource, you define rules that say things like "members of Group X can view any resource where field Y has value Z" — and those rules are evaluated dynamically for every query.

## How it works

Each rule (`RuleConfig`) combines three things:

1. **A filter type** — what kind of test to run against resources
2. **A group** — which Django auth group the rule applies to
3. **Actions** — which permissions the rule grants (read, edit, delete, etc.)

When a user makes a request, every active rule whose group the user belongs to is evaluated. The matching resources from all applicable rules are combined (union), and the user is only shown that set.

Superusers bypass all rules and see everything.

---

## Creating rules

Rules are stored in the `rule_config` database table via the `RuleConfig` model. The recommended approach for deploying rules is a **Django data migration**, which makes the rules part of your project's version history and reproducible across environments.

### Step 1 — Find your node and nodegroup IDs

Each rule targets a specific node (field) in an Arches graph. You need the UUID of the node and its parent nodegroup. You can find these in the Arches graph designer, or by querying the database:

```sql
SELECT nodeid, name, nodegroupid FROM nodes WHERE name = 'My Field Name';
```

### Step 2 — Create a data migration

In your Arches application, create a new migration file:

```
python manage.py makemigrations --empty arches_rule_based_permissions
```

Then fill in the migration using one of the examples below.

---

## Rule types

### `filter_tile_has_value`

Grants access to resources where a specific node contains a specific value.

```python
RuleConfig.objects.create(
    id=uuid.UUID("your-rule-uuid-here"),
    name="Reviewers can see resources with status = Approved",
    type="filter_tile_has_value",
    node_id=uuid.UUID("node-uuid-here"),
    nodegroup_id=uuid.UUID("nodegroup-uuid-here"),
    value={"value": "Approved", "op": "eq"},
    active=True,
)
```

**`value` fields:**
| Field | Description |
|---|---|
| `value` | The value to match against (string, number, etc.) |
| `op` | The comparison operator — currently `"eq"` (equals) |

Assign groups after creation:
```python
rc = RuleConfig.objects.get(id=uuid.UUID("your-rule-uuid-here"))
rc.groups.set([Group.objects.get(name="Resource Reviewer")])
```

---

### `filter_resource_has_lifecycle_state`

Grants access to resources that are in one or more specific [lifecycle states](https://arches.readthedocs.io/en/latest/managing-resources/).

```python
RuleConfig.objects.create(
    id=uuid.UUID("your-rule-uuid-here"),
    name="Editors can see active resources",
    type="filter_resource_has_lifecycle_state",
    node_id=uuid.UUID("any-node-uuid"),       # required by the model, but not used by this rule
    nodegroup_id=uuid.UUID("any-nodegroup-uuid"),
    value={
        "op": "eq",
        "value": ["lifecycle-state-uuid-here"],  # list of lifecycle state UUIDs
    },
    active=True,
)
```

**`value` fields:**
| Field | Description |
|---|---|
| `value` | List of lifecycle state UUIDs to match |
| `op` | Currently `"eq"` |

---

### `filter_tile_spatial`

Grants access to resources whose geometry intersects either a hardcoded polygon or the geometry of another resource in the database.

**Option A — hardcoded GeoJSON polygon:**

```python
RuleConfig.objects.create(
    id=uuid.UUID("your-rule-uuid-here"),
    name="Field staff can see resources within the project boundary",
    type="filter_tile_spatial",
    node_id=uuid.UUID("geometry-node-uuid"),
    nodegroup_id=uuid.UUID("geometry-nodegroup-uuid"),
    value={
        "op": "intersect",
        "geojson": {
            "type": "Polygon",
            "coordinates": [[
                [-122.72, 39.45],
                [-122.69, 38.78],
                [-121.19, 38.70],
                [-121.30, 39.56],
                [-122.72, 39.45],
            ]],
        },
    },
    active=True,
)
```

**Option B — geometry from another resource:**

```python
RuleConfig.objects.create(
    id=uuid.UUID("your-rule-uuid-here"),
    name="Staff can see resources within the study area resource",
    type="filter_tile_spatial",
    node_id=uuid.UUID("geometry-node-uuid"),
    nodegroup_id=uuid.UUID("geometry-nodegroup-uuid"),
    value={
        "op": "intersect",
        "resource_instance_id": "resource-uuid-whose-geometry-to-use",
    },
    active=True,
)
```

**`value` fields:**
| Field | Description |
|---|---|
| `op` | Currently `"intersect"` |
| `geojson` | A GeoJSON geometry object (use this **or** `resource_instance_id`, not both) |
| `resource_instance_id` | UUID of a resource whose stored geometry will be used as the boundary |

---

## Controlling which actions a rule grants

By default, rules grant only `view_resourceinstance`. You can grant additional actions by setting the `actions` field:

```python
RuleConfig.objects.create(
    ...
    actions=["view_resourceinstance", "change_resourceinstance"],
)
```

Available actions (mirrors Arches object-level permissions):

| Action | Meaning |
|---|---|
| `view_resourceinstance` | Can read/search the resource |
| `change_resourceinstance` | Can edit the resource |
| `delete_resourceinstance` | Can delete the resource |
| `add_resourceinstance` | Can add new resources |

---

## Complete migration example

```python
import uuid
from django.db import migrations
from django.contrib.auth.models import Group


class Migration(migrations.Migration):

    dependencies = [
        ("arches_rule_based_permissions", "0001_initial"),
    ]

    def add_rules(apps, schema_editor):
        RuleConfig = apps.get_model("arches_rule_based_permissions", "RuleConfig")
        Group = apps.get_model("auth", "Group")

        reviewers = Group.objects.get(name="Resource Reviewer")

        rule = RuleConfig.objects.create(
            id=uuid.UUID("baca30f6-96f6-4191-9fa1-f65cb0e3808d"),
            name="Reviewers can see resources with status = 75",
            type="filter_tile_has_value",
            node_id=uuid.UUID("8f3f9562-9dc5-11ed-a2fb-0242ac130004"),
            nodegroup_id=uuid.UUID("8f3f9562-9dc5-11ed-a2fb-0242ac130004"),
            value={"value": 75, "op": "eq"},
            active=True,
        )
        rule.groups.set([reviewers])

    def remove_rules(apps, schema_editor):
        RuleConfig = apps.get_model("arches_rule_based_permissions", "RuleConfig")
        RuleConfig.objects.filter(
            id__in=[
                uuid.UUID("baca30f6-96f6-4191-9fa1-f65cb0e3808d"),
            ]
        ).delete()

    operations = [
        migrations.RunPython(add_rules, remove_rules),
    ]
```

---

## Managing rules via Django Admin

Rules can also be created and toggled interactively through the Django admin interface at `/admin/arches_rule_based_permissions/ruleconfig/`. The `active` flag lets you disable a rule without deleting it.

---

## Installation

Add to your Arches project's `settings.py`:

```python
INSTALLED_APPS = [
    ...
    "arches_rule_based_permissions",
]

PERMISSION_FRAMEWORK_BACKEND = (
    "arches_rule_based_permissions.permissions.arches_filtered_permissions"
    ".ArchesFilteredPermissionFramework"
)
```

Then run migrations:

```
python manage.py migrate
```
