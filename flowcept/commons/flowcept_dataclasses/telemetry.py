from typing import List, Dict
from dataclasses import dataclass, asdict


def remove_none_values(_dict):
    return {k: v for (k, v) in _dict if v is not None}


class Telemetry:
    """
     Class representing telemetry information captured in the platform where t
     he experiment runs.

    We are using psutils and the data it can capture depends on the platform.
    So, we won't use dataclasses because we can't list all possible info
    to be captured in any platform.

    """

    class CPU:
        times_avg: Dict[str, float] = None
        percent_all: float = None

        times_per_cpu: List[Dict[str, float]] = None
        percent_per_cpu: List[float] = None

    class Memory:
        virtual: Dict[str, float]
        swap: Dict[str, float]

    class Network:
        netio: Dict[str, int]
        netio_per_interface: Dict[str, Dict[str, int]]

    class Disk:
        disk_usage: Dict[str, float]
        io: Dict[str, float]
        io_per_disk: Dict[str, Dict[str, float]]

    class Process:
        pid: int
        cpu_number: int
        memory: Dict[str, float]
        memory_percent: float
        cpu_times: Dict[str, float]
        cpu_percent: float
        io_counters: Dict[str, float]
        num_connections: int
        num_open_files: int
        num_open_file_descriptors: int
        num_threads: int
        num_ctx_switches: Dict[str, int]
        executable: str
        cmd_line: List[str]

    @dataclass(init=False)
    class GPU:
        @dataclass
        class GPUMetrics:
            total: int
            free: int
            used: int
            usage_percent: float
            temperature: float
            power_usage: float

        gpu_sums: GPUMetrics
        per_gpu: Dict[int, GPUMetrics] = None

    cpu: CPU = None
    process: Process = None
    memory: Memory = None
    disk: Disk = None
    network: Network = None
    gpu: GPU = None

    def to_dict(self):
        ret = {}
        if self.cpu is not None:
            ret["cpu"] = self.cpu.__dict__
        if self.process is not None:
            ret["process"] = self.process.__dict__
        if self.memory is not None:
            ret["memory"] = self.memory.__dict__
        if self.disk is not None:
            ret["disk"] = self.disk.__dict__
        if self.network is not None:
            ret["network"] = self.network.__dict__
        if self.gpu is not None:
            ret["gpu"] = asdict(self.gpu, dict_factory=remove_none_values)

        return ret
