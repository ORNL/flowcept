from typing import Dict, AnyStr, List


# Not a dataclass because a dataclass stores keys even when there's no value,
# adding unnecessary overhead.
class WorkflowObject:
    def __init__(
        self,
        workflow_id: AnyStr = None,
        parent_workflow_id: AnyStr = None,
        machine_info: Dict = None,
        flowcept_settings: Dict = None,
        flowcept_version: AnyStr = None,
        utc_timestamp: float = None,
        user: AnyStr = None,
        campaign_id: AnyStr = None,
        adapter_id: AnyStr = None,
        interceptor_ids: List[AnyStr] = None,
        name: AnyStr = None,
        custom_metadata: Dict = None,
    ):
        self.workflow_id = workflow_id
        self.parent_workflow_id = parent_workflow_id
        self.machine_info = machine_info
        self.flowcept_settings = flowcept_settings
        self.flowcept_version = flowcept_version
        self.utc_timestamp = utc_timestamp
        self.user = user
        self.campaign_id = campaign_id
        self.adapter_id = adapter_id
        self.interceptor_ids = interceptor_ids
        self.name = name
        self.custom_metadata = custom_metadata

    @staticmethod
    def workflow_id_field():
        return "workflow_id"

    def to_dict(self):
        ret = self.__dict__
        # I'm just leaving these comments below in case we need to add specific to_dict stuff
        # if self.telemetry_at_start is not None:
        #     ret["telemetry_at_start"] = self.telemetry_at_start.to_dict()
        # if self.telemetry_at_end is not None:
        #     ret["telemetry_at_end"] = self.telemetry_at_end.to_dict()
        return ret

    def __repr__(self):
        return (
            f"WorkflowObject("
            f"workflow_id={repr(self.workflow_id)}, "
            f"parent_workflow_id={repr(self.parent_workflow_id)}, "
            f"machine_info={repr(self.machine_info)}, "
            f"flowcept_settings={repr(self.flowcept_settings)}, "
            f"flowcept_version={repr(self.flowcept_version)}, "
            f"utc_timestamp={repr(self.utc_timestamp)}, "
            f"user={repr(self.user)}, "
            f"campaign_id={repr(self.campaign_id)}, "
            f"adapter_id={repr(self.adapter_id)}, "
            f"interceptor_ids={repr(self.interceptor_ids)}, "
            f"name={repr(self.name)}, "
            f"custom_metadata={repr(self.custom_metadata)})"
        )

    def __str__(self):
        return self.__repr__()
