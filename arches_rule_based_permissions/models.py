import logging
from django.db import models
from django.contrib.auth.models import Group
from django.conf import settings
from arches.app.models.models import NodeGroup, Node

logger = logging.getLogger(__name__)

class RuleConfig(models.Model):

    def actions_default(): # default must be a callable for JSONField
        return ["view_resourceinstance"]

    id = models.UUIDField(primary_key=True)
    type = models.CharField(max_length=200)
    active = models.BooleanField(default=True)
    name = models.TextField(default="I need a unique name")
    nodegroup = models.ForeignKey(
        NodeGroup, on_delete=models.DO_NOTHING, db_column="nodegroupid"
    )
    node = models.ForeignKey(Node, on_delete=models.DO_NOTHING, db_column="nodeid")
    value = models.JSONField(null=True)
    groups = models.ManyToManyField(Group, related_name="groups", related_query_name="group")
    actions = models.JSONField(default = actions_default) # "read, create, update, delete"
    
    class Meta:
        managed = True
        db_table = "rule_config"
    
    def __str__(self):
        return f"{self.name}"
    