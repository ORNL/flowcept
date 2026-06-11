# Redis configuration for HPC

This `redis.conf` is tuned for multi-node HPC jobs where many distributed nodes connect to a single Redis instance on a compute node.

## Critical settings

### Multi-node connectivity
```
protected-mode no
```
Allows connections from other nodes. Without this, only localhost connections are accepted.

```
tcp-backlog 65535
```
Large connection queue — avoids dropped connections when multiple processes connect simultaneously at job start.

### No persistence (fully diskless)
```
save ""
appendonly no
stop-writes-on-bgsave-error no
```
Disables all disk writes. On HPC compute nodes, local storage is limited and persistence adds latency spikes.

```
repl-diskless-sync yes
repl-diskless-load swapdb
```
If replication is used, transfers happen in-memory rather than writing an RDB file to disk first.

### High memory
```
maxmemory 128gb
maxmemory-policy allkeys-lru
maxmemory-samples 3
```
Allows Redis to use up to 128 GB of RAM. Eviction uses LRU sampling (fast, low overhead).

### High throughput
```
io-threads 32
io-threads-do-reads yes
```
Enables multi-threaded I/O for both reads and writes. Matches typical HPC node core counts.

```
lazyfree-lazy-eviction yes
lazyfree-lazy-expire yes
lazyfree-lazy-server-del yes
lazyfree-lazy-user-del yes
lazyfree-lazy-user-flush yes
```
All memory frees are non-blocking — background threads handle deallocation so the main thread is never stalled.

### Latency
```
disable-thp yes
```
Disables transparent hugepages, which cause periodic latency spikes under memory pressure.

```
loglevel warning
```
Minimal logging to avoid I/O overhead during high-throughput runs.
