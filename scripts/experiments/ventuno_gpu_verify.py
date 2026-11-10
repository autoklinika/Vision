#!/usr/bin/env python3
"""VENTUNO Q GPU/Adreno diagnostic. No package installation or system changes.

Usage:
    python3 -B ventuno_gpu_verify.py            # inventory + Vulkan enumeration
    python3 -B ventuno_gpu_verify.py --render   # also draw/read pixels via EGL/GLES2

Does not require sudo, third-party Python packages, or a connected monitor.
Probes run in isolated subprocesses with timeouts. Prints to stdout only.
"""

import argparse
import ctypes as C
import glob
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys

TIMEOUT_SECONDS = 15
SOFTWARE_RENDERERS = ("llvmpipe", "softpipe", "lavapipe", "software rasterizer", "swrast")


def read_text(path):
    try:
        return Path(path).read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
    except (OSError, ValueError):
        return None


def link_to(path):
    try:
        return str(Path(path).resolve(strict=True))
    except OSError:
        return None


def static_inventory():
    print("=== SYSTEM / GPU / DRM ===")
    print("Kernel:", platform.release(), "| Architektura:", platform.machine())
    print("Plyta:", read_text("/proc/device-tree/model") or "nieustalona")
    print("Sterownik msm (modul):", "obecny" if Path("/sys/module/msm").exists() else "brak")
    nodes = sorted(glob.glob("/dev/dri/renderD*"))
    if not nodes:
        print("Węzły render: BRAK")
    for node in nodes:
        name = Path(node).name
        base = f"/sys/class/drm/{name}/device"
        print(f"Węzeł render: {node}")
        print("  Sterownik:", link_to(base + "/driver") or "nieustalony")
        print("  Urządzenie:", link_to(base) or "nieustalone")
        print("  Compatible:", read_text(base + "/of_node/compatible") or "nieustalone")
        try:
            print("  Dostęp R/W:", "TAK" if os.access(node, os.R_OK | os.W_OK) else "NIE")
        except OSError:
            pass

    print("\n=== WĘZŁY GPU DEVICE TREE ===")
    roots = ("/proc/device-tree", "/sys/firmware/devicetree/base")
    root = next((p for p in roots if Path(p).is_dir()), None)
    found = []
    if root:
        for current, directories, _ in os.walk(root):
            depth = len(Path(current).relative_to(root).parts)
            if depth >= 9:
                directories[:] = []
            for directory in directories:
                if "gpu" in directory.lower() or "adreno" in directory.lower() or "kgsl" in directory.lower():
                    found.append(os.path.join(current, directory))
    for path in found[:15]:
        print(" ", path)
        print("    compatible:", read_text(path + "/compatible") or "nieustalone")
        print("    status:", read_text(path + "/status") or "domyślny/nieustalony")
    if not found:
        print("Nie znaleziono nazwanego węzła GPU (to NIE przesądza o awarii).")

    print("\n=== VULKAN ICD ===")
    icds = sorted(set(glob.glob("/usr/share/vulkan/icd.d/*freedreno*.json") +
                      glob.glob("/etc/vulkan/icd.d/*freedreno*.json")))
    if icds:
        for path in icds:
            print(" ", path)
            print("    ", (read_text(path) or "[brak odczytu]")[:350].replace("\n", " "))
    else:
        print("Brak manifestu Freedreno/Turnip ICD")

    print("\n=== FIRMWARE QUALCOMM (obecność, nie dowód załadowania) ===")
    fw = set()
    for root in ("/lib/firmware", "/lib/firmware/updates", "/usr/lib/firmware"):
        for pattern in ("qcom/a623*", "qcom/a6*gm*", "qcom/qcs8300/a623*"):
            fw.update(glob.glob(os.path.join(root, pattern)))
    for f in sorted(fw)[:25]:
        print(" ", f)
    if not fw:
        print("Nie znaleziono wybranych plików A623/QCS8300 (inne warianty możliwe).")
    return icds


class VkApplicationInfo(C.Structure):
    _fields_ = [("sType", C.c_uint32), ("pNext", C.c_void_p),
                ("pApplicationName", C.c_char_p), ("applicationVersion", C.c_uint32),
                ("pEngineName", C.c_char_p), ("engineVersion", C.c_uint32),
                ("apiVersion", C.c_uint32)]


class VkInstanceCreateInfo(C.Structure):
    _fields_ = [("sType", C.c_uint32), ("pNext", C.c_void_p),
                ("flags", C.c_uint32), ("pApplicationInfo", C.POINTER(VkApplicationInfo)),
                ("enabledLayerCount", C.c_uint32), ("ppEnabledLayerNames", C.c_void_p),
                ("enabledExtensionCount", C.c_uint32), ("ppEnabledExtensionNames", C.c_void_p)]


def probe_vulkan():
    try:
        vk = C.CDLL("libvulkan.so.1")
    except OSError as e:
        return {"ok": False, "error": f"Nie można otworzyć libvulkan.so.1: {e}"}
    vk.vkCreateInstance.argtypes = [C.POINTER(VkInstanceCreateInfo), C.c_void_p, C.POINTER(C.c_void_p)]
    vk.vkCreateInstance.restype = C.c_int32
    vk.vkEnumeratePhysicalDevices.argtypes = [C.c_void_p, C.POINTER(C.c_uint32), C.c_void_p]
    vk.vkEnumeratePhysicalDevices.restype = C.c_int32
    vk.vkGetPhysicalDeviceProperties.argtypes = [C.c_void_p, C.c_void_p]
    vk.vkGetPhysicalDeviceProperties.restype = None
    vk.vkDestroyInstance.argtypes = [C.c_void_p, C.c_void_p]
    vk.vkDestroyInstance.restype = None

    app = VkApplicationInfo(0, None, b"ventuno-gpu-verify", 1, b"diagnostics", 1, 1 << 22)
    info = VkInstanceCreateInfo(1, None, 0, C.pointer(app), 0, None, 0, None)
    instance = C.c_void_p()
    code = vk.vkCreateInstance(C.byref(info), None, C.byref(instance))
    if code != 0:
        return {"ok": False, "error": f"vkCreateInstance zwrócił VkResult={code}"}
    try:
        count = C.c_uint32()
        code = vk.vkEnumeratePhysicalDevices(instance, C.byref(count), None)
        if code != 0:
            return {"ok": False, "error": f"vkEnumeratePhysicalDevices(count)={code}"}
        if count.value == 0:
            return {"ok": True, "devices": []}
        if count.value > 32:
            return {"ok": False, "error": f"Nieoczekiwana liczba urządzeń: {count.value}"}
        devices = (C.c_void_p * count.value)()
        code = vk.vkEnumeratePhysicalDevices(instance, C.byref(count), C.cast(devices, C.c_void_p))
        if code != 0:
            return {"ok": False, "error": f"vkEnumeratePhysicalDevices(list)={code}"}
        found = []
        for device in devices[:count.value]:
            # VkPhysicalDeviceProperties begins with five uint32_t fields + deviceName[256].
            # Keep excess space for future Vulkan driver layouts.
            buffer = C.create_string_buffer(4096)
            vk.vkGetPhysicalDeviceProperties(device, C.cast(buffer, C.c_void_p))
            api, version, vendor, device_id, device_type = struct.unpack_from("=5I", buffer.raw, 0)
            name = buffer.raw[20:276].split(b"\x00", 1)[0].decode("utf-8", "replace")
            hw_candidate = device_type in (1, 2, 3) and not any(x in name.lower() for x in SOFTWARE_RENDERERS)
            found.append({"name": name, "vendor_id": hex(vendor), "device_id": hex(device_id),
                          "type": {0: "OTHER", 1: "INTEGRATED_GPU", 2: "DISCRETE_GPU", 3: "VIRTUAL_GPU", 4: "CPU"}.get(device_type, str(device_type)),
                          "hardware_candidate": hw_candidate,
                          "api_version": f"{api >> 22}.{(api >> 12) & 1023}.{api & 4095}",
                          "driver_version_raw": version})
        return {"ok": True, "devices": found}
    finally:
        vk.vkDestroyInstance(instance, None)


def probe_egl_render():
    """Optional 2x2 GLES2 readback. No external utilities or shader compilation."""
    try:
        egl = C.CDLL("libEGL.so.1")
        gl = C.CDLL("libGLESv2.so.2")
    except OSError as e:
        return {"ok": False, "error": f"Brak EGL/GLES2: {e}"}
    P = C.c_void_p
    I = C.c_int
    egl.eglGetProcAddress.argtypes = [C.c_char_p]
    egl.eglGetProcAddress.restype = P
    egl.eglGetDisplay.argtypes = [P]
    egl.eglGetDisplay.restype = P
    egl.eglInitialize.argtypes = [P, C.POINTER(I), C.POINTER(I)]
    egl.eglInitialize.restype = I
    egl.eglBindAPI.argtypes = [C.c_uint]
    egl.eglBindAPI.restype = I
    egl.eglChooseConfig.argtypes = [P, C.POINTER(I), C.POINTER(P), I, C.POINTER(I)]
    egl.eglChooseConfig.restype = I
    egl.eglCreatePbufferSurface.argtypes = [P, P, C.POINTER(I)]
    egl.eglCreatePbufferSurface.restype = P
    egl.eglCreateContext.argtypes = [P, P, P, C.POINTER(I)]
    egl.eglCreateContext.restype = P
    egl.eglMakeCurrent.argtypes = [P, P, P, P]
    egl.eglMakeCurrent.restype = I
    egl.eglDestroyContext.argtypes = [P, P]
    egl.eglDestroySurface.argtypes = [P, P]
    egl.eglTerminate.argtypes = [P]
    egl.eglGetError.argtypes = []
    egl.eglGetError.restype = C.c_uint
    gl.glGetString.argtypes = [C.c_uint]
    gl.glGetString.restype = C.c_char_p
    gl.glClearColor.argtypes = [C.c_float] * 4
    gl.glClear.argtypes = [C.c_uint]
    gl.glReadPixels.argtypes = [I, I, I, I, C.c_uint, C.c_uint, P]
    gl.glGetError.argtypes = []
    gl.glGetError.restype = C.c_uint

    get_platform_ptr = egl.eglGetProcAddress(b"eglGetPlatformDisplayEXT")
    if get_platform_ptr:
        func = C.CFUNCTYPE(P, C.c_uint, P, P)(get_platform_ptr)
        display = func(0x31DD, None, None)  # EGL_PLATFORM_SURFACELESS_MESA
    else:
        display = egl.eglGetDisplay(None)
    if not display:
        return {"ok": False, "error": "Brak headless EGL display"}
    major, minor = I(), I()
    if not egl.eglInitialize(display, C.byref(major), C.byref(minor)):
        return {"ok": False, "error": f"eglInitialize błąd {hex(egl.eglGetError())}"}
    surface, context = None, None
    try:
        if not egl.eglBindAPI(0x30A0):  # EGL_OPENGL_ES_API
            return {"ok": False, "error": "eglBindAPI(OpenGL ES) nieudane"}
        config_attribs = (I * 13)(0x3024, 8, 0x3023, 8, 0x3022, 8,
                                   0x3033, 1, 0x3040, 4, 0x3021, 0, 0x3038)
        config, count = P(), I()
        if not egl.eglChooseConfig(display, config_attribs, C.byref(config), 1, C.byref(count)) or not count.value:
            return {"ok": False, "error": "Brak EGL pbuffer/GLES2 config"}
        pb_attribs = (I * 5)(0x3057, 2, 0x3056, 2, 0x3038)  # WIDTH, HEIGHT, EGL_NONE
        surface = egl.eglCreatePbufferSurface(display, config, pb_attribs)
        ctx_attribs = (I * 3)(0x3098, 2, 0x3038)  # EGL_CONTEXT_CLIENT_VERSION=2
        context = egl.eglCreateContext(display, config, None, ctx_attribs)
        if not surface or not context or not egl.eglMakeCurrent(display, surface, surface, context):
            return {"ok": False, "error": f"Nie udało się utworzyć EGL context: {hex(egl.eglGetError())}"}
        renderer = (gl.glGetString(0x1F01) or b"").decode("utf-8", "replace")  # GL_RENDERER
        vendor = (gl.glGetString(0x1F00) or b"").decode("utf-8", "replace")
        gl.glClearColor(0.2, 0.4, 0.6, 1.0)
        gl.glClear(0x00004000)  # GL_COLOR_BUFFER_BIT
        pixel = (C.c_ubyte * 4)()
        gl.glReadPixels(0, 0, 1, 1, 0x1908, 0x1401, C.cast(pixel, P))  # RGBA/UNSIGNED_BYTE
        gl_error = gl.glGetError()
        good = gl_error == 0 and all(abs(int(pixel[i]) - [51, 102, 153, 255][i]) <= 4 for i in range(4))
        soft = any(x in renderer.lower() for x in SOFTWARE_RENDERERS)
        return {"ok": good, "renderer": renderer, "vendor": vendor,
                "software": soft, "pixel_rgba": list(pixel), "gl_error": hex(gl_error)}
    finally:
        egl.eglMakeCurrent(display, None, None, None)
        if context:
            egl.eglDestroyContext(display, context)
        if surface:
            egl.eglDestroySurface(display, surface)
        egl.eglTerminate(display)


def child_run(kind):
    try:
        result = probe_vulkan() if kind == "--vulkan-probe" else probe_egl_render()
    except BaseException as e:
        result = {"ok": False, "error": f"Wyjątek {type(e).__name__}: {e}"}
    print("VENTUNO_PROBE_JSON=" + json.dumps(result, ensure_ascii=False), flush=True)


def isolated_probe(kind, icd=None):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MESA_SHADER_CACHE_DISABLE"] = "true"
    env["MESA_GLSL_CACHE_DISABLE"] = "true"
    env["VK_LOADER_DEBUG"] = "error"
    if icd:
        env["VK_ICD_FILENAMES"] = icd
        env.pop("VK_DRIVER_FILES", None)
    try:
        result = subprocess.run([sys.executable, "-B", os.path.abspath(__file__), kind],
                                capture_output=True, text=True, timeout=TIMEOUT_SECONDS, env=env)
        marker = "VENTUNO_PROBE_JSON="
        for line in result.stdout.splitlines():
            if line.startswith(marker):
                payload = json.loads(line[len(marker):])
                payload["process_exit"] = result.returncode
                if result.stderr.strip():
                    payload["driver_messages"] = result.stderr.strip()[-750:]
                return payload
        return {"ok": False, "error": f"Probe zakończył się kodem {result.returncode}; brak wyniku JSON",
                "driver_messages": result.stderr.strip()[-750:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Przekroczono limit {TIMEOUT_SECONDS} sekund"}
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def show_result(label, data):
    print("\n===", label, "===")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="VENTUNO GPU Adreno read-only diagnostic")
    parser.add_argument("--render", action="store_true", help="dodatkowy test EGL/GLES2 2x2 z odczytem piksela")
    args = parser.parse_args()
    icds = static_inventory()
    default = isolated_probe("--vulkan-probe")
    show_result("VULKAN / WSZYSTKIE DOSTĘPNE ICD", default)
    freedreno = None
    if icds:
        freedreno = isolated_probe("--vulkan-probe", icds[0])
        show_result("VULKAN / TYLKO FREEDRENO ICD", freedreno)
    render = None
    if args.render:
        render = isolated_probe("--egl-probe")
        show_result("EGL/GLES2 / RENDER + READBACK", render)

    hardware = any(d.get("hardware_candidate") for result in (default, freedreno) if result
                   for d in result.get("devices", []))
    soft_devices = [d.get("name") for result in (default, freedreno) if result
                    for d in result.get("devices", []) if not d.get("hardware_candidate")]
    print("\n=== WERDYKT ===")
    if render and render.get("ok") and not render.get("software"):
        print("PASS_RENDER: aktywny test GLES2 zakończony sukcesem; renderer:", render.get("renderer"))
        return 0
    if hardware:
        print("PASS_ENUMERATION: Vulkan wykrył kandydata na sprzętowe GPU.")
        print("UWAGA: enumeracja nie dowodzi poprawności renderowania/obliczeń GPU.")
        if args.render and render and not render.get("ok"):
            print("WARN_RENDER: test EGL nie przeszedł; szczegóły powyżej.")
        return 0
    if soft_devices:
        print("UNVERIFIED: wykryto tylko renderery niewskazujące na sprzętowe GPU:", ", ".join(sorted(set(soft_devices))))
    else:
        print("UNVERIFIED: nie potwierdzono dostępności GPU przez Vulkan.")
    if render and render.get("ok") and render.get("software"):
        print("UWAGA: test rysowania działa, ale na rendererze programowym:", render.get("renderer"))
    print("Kod wyjścia 2 oznacza brak potwierdzenia, nie diagnozę uszkodzenia sprzętu.")
    return 2


if __name__ == "__main__":
    if "--vulkan-probe" in sys.argv:
        child_run("--vulkan-probe")
    elif "--egl-probe" in sys.argv:
        child_run("--egl-probe")
    else:
        sys.exit(main())
