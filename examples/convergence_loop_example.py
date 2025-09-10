from flowcept import Flowcept, FlowceptLoop

THRESHOLD = 0.05
MAX_ITERS = 50


def update_error(e: float) -> float:
    """Dummy update rule that shrinks error each step."""
    return e * 0.7  # replace with your real update


def finalize_loop(loop):
    """Flush the last iteration so it’s captured even if we break early."""
    if getattr(loop, "enabled", False) and getattr(loop, "_last_iteration_task", None) is not None:
        try:
            loop._end_iteration_task(loop._last_iteration_task)  # uses FlowceptLoop internals
        except Exception:
            pass


# --- Convergence with FlowceptLoop ---
error = 1.0
loop = FlowceptLoop(
    items=range(MAX_ITERS),     # upper bound; we’ll break early on convergence
    loop_name="convergence",
    item_name="iter",
)

for it in loop:
    # --- your loop body ---
    error = update_error(error)
    print(f"iter={it}  error={error:.4f}")

    # Record per-iteration outputs (only once per iteration)
    loop.end_iter({
        "iter": it,
        "error": error,
        "status": "converged" if error <= THRESHOLD else "continuing",
    })

    # Convergence check — emulate: while error > THRESHOLD: update error
    if error <= THRESHOLD:
        finalize_loop(loop)   # ensure the last iteration is closed before breaking
        break
