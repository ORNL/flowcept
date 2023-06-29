from typing import Dict
import psutil

from flowcept.configs import TELEMETRY_CAPTURE
from flowcept.commons.flowcept_dataclasses.telemetry import Telemetry
from flowcept.commons.flowcept_logger import FlowceptLogger


def capture_telemetry() -> Telemetry:
    conf = TELEMETRY_CAPTURE
    if conf is None:
        return None

    tel = Telemetry()
    tel.cpu = _capture_cpu(conf)
    tel.process = _capture_process_info(conf)
    tel.memory = _capture_memory(conf)
    tel.network = _capture_network(conf)
    tel.disk = _capture_disk(conf)

    return tel


def _capture_disk(conf):
    capt = conf.get("disk", False)
    if not capt:
        return None
    try:
        disk = Telemetry._Disk()
        disk.disk_usage = psutil.disk_usage("/")._asdict()
        disk.io = psutil.disk_io_counters(perdisk=False)._asdict()
        io_perdisk = psutil.disk_io_counters(perdisk=True)
        if len(io_perdisk) > 1:
            disk.io_per_disk = {}
            for d in io_perdisk:
                disk.io_per_disk[d] = io_perdisk[d]._asdict()

        return disk
    except Exception as e:
        FlowceptLogger.get_logger().exception(e)


def _capture_network(conf):
    capt = conf.get("network", False)
    if not capt:
        return None
    try:
        net = Telemetry._Network()
        net.netio = psutil.net_io_counters(pernic=False)._asdict()
        pernic = psutil.net_io_counters(pernic=True)
        net.netio_per_interface = {}
        for ic in pernic:
            if pernic[ic].bytes_sent and pernic[ic].bytes_recv:
                net.netio_per_interface[ic] = pernic[ic]
        return net
    except Exception as e:
        FlowceptLogger.get_logger().exception(e)


def _capture_memory(conf):
    capt = conf.get("mem", False)
    if not capt:
        return None
    try:
        mem = Telemetry._Memory()
        mem.virtual = psutil.virtual_memory()._asdict()
        mem.swap = psutil.swap_memory()._asdict()
        return mem
    except Exception as e:
        FlowceptLogger.get_logger().exception(e)


def _capture_process_info(conf):
    capt = conf.get("process_info", False)
    if not capt:
        return None
    try:
        p = Telemetry._Process()
        psutil_p = psutil.Process()
        with psutil_p.oneshot():
            p.pid = psutil_p.pid
            try:
                p.cpu_number = psutil_p.cpu_num()
            except:
                pass
            p.memory = psutil_p.memory_full_info()
            p.memory_percent = psutil_p.memory_percent()
            p.cpu_times = psutil_p.cpu_times()._asdict()
            p.cpu_percent = psutil_p.cpu_percent()
            p.executable = psutil_p.exe()
            p.cmd_line = psutil_p.cmdline()
            p.num_open_file_descriptors = psutil_p.num_fds()
            p.num_connections = len(psutil_p.connections())
            try:
                p.io_counters = psutil_p.io_counters()._asdict()
            except:
                pass
            p.num_open_files = len(psutil_p.open_files())
            p.num_threads = psutil_p.num_threads()
            p.num_ctx_switches = psutil_p.num_ctx_switches()._asdict()
        return p
    except Exception as e:
        FlowceptLogger.get_logger().exception(e)


def _capture_cpu(conf: Dict):
    capt_cpu = conf.get("cpu", False)
    capt_per_cpu = conf.get("per_cpu", False)
    if not (capt_cpu or capt_per_cpu):
        return None
    try:
        cpu = Telemetry._CPU()
        if conf.get("cpu", False):
            cpu.times = psutil.cpu_times(percpu=False)._asdict()
            cpu.percent = psutil.cpu_percent()
        if conf.get("per_cpu", False):
            cpu.times_per_cpu = [
                c._asdict() for c in psutil.cpu_times(percpu=True)
            ]
            cpu.percent_per_cpu = psutil.cpu_percent(percpu=True)
        return cpu
    except Exception as e:
        FlowceptLogger.get_logger().exception(e)
        return None
