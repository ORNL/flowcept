from typing import List, Dict
from dataclasses import dataclass, asdict, field


def remove_none_values(_dict):
    return {k: v for (k, v) in _dict if v is not None}


class Telemetry:
    @dataclass(init=False)
    class CPU:
        @dataclass
        class CPUMetrics:
            user: float
            nice: float
            system: float
            idle: float

        times_avg: CPUMetrics
        percent_all: float = None

        times_per_cpu: List[CPUMetrics] = None
        percent_per_cpu: List[float] = None

    @dataclass(init=False)
    class Memory:
        @dataclass
        class MemoryMetrics:
            total: int = field(default=None)
            used: int = field(default=None)
            free: int = field(default=None)
            percent: int = field(default=None)
            sin: int = field(default=None)
            sout: int = field(default=None)
            available: int = field(default=None)
            active: int = field(default=None)
            inactive: int = field(default=None)
            wired: int = field(default=None)

        virtual: MemoryMetrics = field(default=None)
        swap: MemoryMetrics = field(default=None)

    @dataclass(init=False)
    class Network:
        @dataclass
        class NetworkMetrics:
            bytes_sent: int
            bytes_recv: int
            packets_sent: int
            packets_recv: int
            errin: int
            errout: int
            dropin: int
            dropout: int

        netio_sum: NetworkMetrics = None
        netio_per_interface: Dict[str, NetworkMetrics] = None

    @dataclass(init=False)
    class Disk:
        @dataclass
        class DiskUsage:
            total: int
            used: int
            free: int
            percent: float

        @dataclass
        class DiskMetrics:
            read_count: int
            write_count: int
            read_bytes: int
            write_bytes: int
            read_time: int
            write_time: int

        disk_usage: DiskUsage
        io_sum: DiskMetrics
        io_per_disk: Dict[str, DiskMetrics] = field(default=None)

    # TODO: make it dataclass, like the others
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

        gpu_total: GPUMetrics
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
            ret["cpu"] = asdict(self.cpu, dict_factory=remove_none_values)

        if self.memory is not None:
            ret["memory"] = asdict(
                self.memory, dict_factory=remove_none_values
            )
        if self.disk is not None:
            ret["disk"] = asdict(self.disk, dict_factory=remove_none_values)

        if self.network is not None:
            ret["network"] = asdict(
                self.network, dict_factory=remove_none_values
            )

        if self.gpu is not None:
            ret["gpu"] = asdict(self.gpu, dict_factory=remove_none_values)

        if self.process is not None:
            ret["process"] = self.process.__dict__

        return ret
