#!/usr/bin/env python3
"""VENTUNO Q: QNN HTP execution verification, with CPU fallback disabled."""
import json
import os
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
import onnxruntime as ort

ROOT = Path("/srv/vision-data/tools/npu-verify")
MODEL = ROOT / "models" / "tiny_conv_relu.onnx"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
print("ORT_VERSION", ort.__version__, flush=True)
print("PROVIDERS_AVAILABLE", ort.get_available_providers(), flush=True)
print("HTP_BACKEND", ROOT / "pkgroot/usr/lib/libQnnHtp.so", flush=True)
print("ADSP_LIBRARY_PATH", os.getenv("ADSP_LIBRARY_PATH", "<unset>"), flush=True)

# Fixed-shape convolution, followed by ReLU: actual input-dependent computation.
rs = np.random.default_rng(20261010)
weights = rs.normal(0, 0.15, (4, 3, 3, 3)).astype(np.float32)
bias = rs.normal(0, 0.05, (4,)).astype(np.float32)
data = rs.normal(0, 0.4, (1, 3, 16, 16)).astype(np.float32)
graph = helper.make_graph(
    [
        helper.make_node("Conv", ["input", "kernel", "bias"], ["conv_output"], pads=[1, 1, 1, 1]),
        helper.make_node("Relu", ["conv_output"], ["output"]),
    ],
    "VentunoQ_Hexagon_Htp_Proof",
    [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 16, 16])],
    [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 4, 16, 16])],
    [numpy_helper.from_array(weights, "kernel"), numpy_helper.from_array(bias, "bias")],
)
model = helper.make_model(graph, opset_imports=[helper.make_operatorsetid("", 13)])
model.ir_version = 9
onnx.checker.check_model(model)
onnx.save(model, str(MODEL))
print("MODEL", MODEL, "OPS Conv,Relu", flush=True)

try:
    cpu = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    expected = cpu.run(None, {"input": data})[0]
    print("CPU_REFERENCE=PASS", "output_shape", tuple(expected.shape), "checksum", float(np.sum(expected)), flush=True)

    opts = ort.SessionOptions()
    opts.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
    opts.log_severity_level = 2
    opts.enable_profiling = True
    opts.profile_file_prefix = str(LOG_DIR / "ort_qnn_strict")
    backend = str(ROOT / "pkgroot/usr/lib/libQnnHtp.so")
    providers = [("QNNExecutionProvider", {
        "backend_path": backend,
        "profiling_level": "basic",
        "profiling_file_path": str(LOG_DIR / "qnn_htp_profile.csv"),
    })]
    t0 = time.perf_counter()
    sess = ort.InferenceSession(str(MODEL), sess_options=opts, providers=providers)
    print("QNN_SESSION_PROVIDERS", sess.get_providers(), flush=True)
    print("QNN_SESSION_OPTIONS", sess.get_provider_options().get("QNNExecutionProvider", {}), flush=True)
    if "QNNExecutionProvider" not in sess.get_providers():
        raise RuntimeError("QNN EP not registered in session")

    actual = sess.run(None, {"input": data})[0]
    t1 = time.perf_counter()
    diff = float(np.max(np.abs(actual - expected)))
    print("NPU_OUTPUT_CHECK", json.dumps({
        "shape": list(actual.shape),
        "checksum": float(np.sum(actual)),
        "max_abs_error_vs_cpu": diff,
        "wall_time_s_including_session_init": round(t1 - t0, 3),
        "all_finite": bool(np.isfinite(actual).all())
    }), flush=True)
    profile_path = sess.end_profiling()
    print("ORT_PROFILE", profile_path, flush=True)
    # CPU fallback is disabled, so session/run success and correct output imply HTP.
    if not np.isfinite(actual).all() or not np.allclose(expected, actual, atol=0.08, rtol=0.08):
        raise AssertionError(f"NPU output mismatch, max_abs_error={diff}")
    print("NPU_INFERENCE=PASS_STRICT_HTP", flush=True)
except Exception as exc:
    print("NPU_INFERENCE=FAIL", type(exc).__name__, str(exc), flush=True)
    traceback.print_exc()
    sys.exit(2)
