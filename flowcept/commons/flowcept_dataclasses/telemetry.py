from typing import List, Dict


class Telemetry:

    class _CPU:
        times: Dict[str, float] = None  # this is an average of all cpus
        percent: float = None

        times_per_cpu: List[Dict[str, float]] = None
        percent_per_cpu: List[float] = None

    class _Memory:
        virtual: Dict[str, float]
        swap: Dict[str, float]

    class _Network:
        netio: Dict[str, int]
        netio_per_interface: Dict[str, Dict[str, int]]

    class _Disk:
        disk_usage: Dict[str, float]
        io: Dict[str, float]
        io_per_disk: Dict[str, Dict[str, float]]

    class _Process:
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

    cpu: _CPU = None
    process: _Process = None
    memory: _Memory = None
    disk: _Disk = None
    network: _Network = None

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
        return ret
