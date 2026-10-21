
import os
import shlex
import subprocess
import uuid
from pathlib import Path

from flask import Flask, render_template_string, request, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
HELPER_DIR = BASE_DIR / "renode_helper_files"

RENODE = Path.home() / "tools" / "renode" / "renode"
PLATFORM_FILE = HELPER_DIR / "stm32f401.repl"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

PI_HOST = os.environ.get("PI_HOST", "192.168.0.8")
PI_USER = os.environ.get("PI_USER", "root")
PI_SSH_KEY = os.environ.get("PI_SSH_KEY")  

SSH_TIMEOUT = 15
FLASH_TIMEOUT = 90
RENODE_TIMEOUT = 15

SUPPORTED_TARGETS = {
    "stm32f401": {
        "name": "STM32F401CE",
        "openocd_interface": "interface/stlink.cfg",
        "openocd_target": "target/stm32f4x.cfg",
    },
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>OTA Gate Keeper</title>
    <style>
        body {
            font-family: monospace;
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
        }
        .card {
            background: #252526;
            border: 1px solid #454545;
            padding: 24px;
            border-radius: 8px;
            max-width: 650px;
            margin: 30px auto;
        }
        h2 { color: #569cd6; text-align: center; }
        label, select, input, button {
            display: block;
            width: 100%;
            margin: 14px 0;
            box-sizing: border-box;
        }
        button {
            background: #0e639c;
            color: white;
            border: none;
            padding: 12px;
            font-weight: bold;
            cursor: pointer;
        }
        button:disabled { opacity: 0.6; cursor: wait; }
        #log {
            background: #000;
            color: #00ff00;
            padding: 12px;
            min-height: 180px;
            max-height: 500px;
            overflow: auto;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
        }
        .note { color: #dcdcaa; font-size: 12px; }
    </style>
</head>
<body>
<div class="card">
    <h2>OTA Gate Keeper</h2>
    <p class="note">
        Pipeline: Renode validation → SSH/SCP transfer → OpenOCD flash
        and verification on the Raspberry Pi.
    </p>

    <form id="uploadForm">
        <label for="target">Target MCU:</label>
        <select name="target" id="target">
            <option value="stm32f401">STM32F401CE</option>
        </select>

        <label for="firmware">Upload firmware (.elf):</label>
        <input type="file" name="firmware" id="firmware"
               accept=".elf" required>

        <button id="submitButton" type="submit">
            Validate and Deploy
        </button>
    </form>

    <h3>Deployment Output</h3>
    <div id="log">Awaiting firmware...</div>
</div>

<script>
const form = document.getElementById("uploadForm");
const logDiv = document.getElementById("log");
const button = document.getElementById("submitButton");

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    button.disabled = true;
    logDiv.textContent =
        "Uploading firmware...\\nDo not close this page while deployment runs.";

    try {
        const response = await fetch("/upload", {
            method: "POST",
            body: new FormData(form)
        });

        const result = await response.json();
        logDiv.textContent = result.message || "No deployment details returned.";
    } catch (error) {
        logDiv.textContent = "Request failed: " + error.message;
    } finally {
        button.disabled = false;
    }
});
</script>
</body>
</html>
"""


def run_command(command, timeout, cwd=None):
    """Run a local command and return combined output."""
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    return result.returncode, output.strip()


def ssh_options():
    """SSH options for non-interactive, key-based authentication."""
    options = [
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={SSH_TIMEOUT}",
        "-o", "StrictHostKeyChecking=yes",
    ]

    if PI_SSH_KEY:
        options.extend(["-i", PI_SSH_KEY])

    return options


def transfer_to_pi(local_path, remote_path):
    """Transfer firmware using legacy SCP mode for Dropbear compatibility."""
    destination = f"{PI_USER}@{PI_HOST}:{remote_path}"

    command = [
        "scp",
        "-O",
        *ssh_options(),
        str(local_path),
        destination,
    ]

    return run_command(command, timeout=SSH_TIMEOUT + 30)


def flash_on_pi(remote_path, target_config):
    """Run OpenOCD remotely and require successful flash verification."""
    openocd_command = (
        f"openocd "
        f"-f {target_config['openocd_interface']} "
        f"-f {target_config['openocd_target']} "
        f"-c 'adapter speed 100' "
        f"-c {shlex.quote(f'program {remote_path} verify reset exit')}"
    )

    command = [
        "ssh",
        *ssh_options(),
        f"{PI_USER}@{PI_HOST}",
        openocd_command,
    ]

    return run_command(command, timeout=FLASH_TIMEOUT)


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/upload", methods=["POST"])
def handle_upload():
    if "firmware" not in request.files:
        return jsonify(
            status="error",
            message="ERROR: No firmware file was uploaded."
        ), 400

    uploaded = request.files["firmware"]
    target = request.form.get("target", "")

    if target not in SUPPORTED_TARGETS:
        return jsonify(
            status="error",
            message="ERROR: Unsupported MCU target."
        ), 400

    if not uploaded.filename:
        return jsonify(
            status="error",
            message="ERROR: Choose an ELF file."
        ), 400

    filename = secure_filename(uploaded.filename)
    if not filename or not filename.lower().endswith(".elf"):
        return jsonify(
            status="error",
            message="ERROR: Please upload an .elf file."
        ), 400

    if not RENODE.is_file():
        return jsonify(
            status="error",
            message=f"ERROR: Renode executable not found: {RENODE}"
        ), 500

    if not PLATFORM_FILE.is_file():
        return jsonify(
            status="error",
            message=f"ERROR: Platform file not found: {PLATFORM_FILE}"
        ), 500

    run_id = uuid.uuid4().hex
    firmware_path = UPLOAD_DIR / f"{run_id}_{filename}"
    resc_path = UPLOAD_DIR / f"{run_id}_validate.resc"
    uart_path = UPLOAD_DIR / f"{run_id}_uart.log"

    remote_path = f"/tmp/ota_{run_id}.elf"
    target_config = SUPPORTED_TARGETS[target]

    stages = [
        "[1/4] Firmware upload: RECEIVED",
    ]

    try:
        uploaded.save(firmware_path)

        resc_contents = f'''
mach create "stm32f401_{run_id[:8]}"
machine LoadPlatformDescription @{PLATFORM_FILE}
sysbus.usart2 CreateFileBackend @{uart_path}
sysbus LogPeripheralAccess sysbus.usart2 true
sysbus LoadELF @{firmware_path}
start
sleep 3
quit
'''
        resc_path.write_text(resc_contents, encoding="utf-8")

        stages.append("[2/4] Renode simulation: RUNNING")

        try:
            renode_rc, renode_output = run_command(
                [
                    str(RENODE),
                    "--disable-xwt",
                    "--console",
                    str(resc_path),
                ],
                timeout=RENODE_TIMEOUT,
                cwd=BASE_DIR,
            )
        except subprocess.TimeoutExpired:
            return jsonify(
                status="error",
                message="\n".join(stages) +
                "\nERROR: Renode exceeded its timeout."
            ), 504

        uart_output = (
            uart_path.read_text(encoding="utf-8", errors="replace")
            if uart_path.exists()
            else ""
        )

        if renode_rc != 0:
            stages.append("Renode simulation: FAILED")
            return jsonify(
                status="error",
                message="\n".join(stages) +
                "\n\nRenode output:\n" + renode_output[-4000:]
            ), 500

        if "BOOT_OK" not in uart_output:
            stages.append("Virtual UART: BOOT_OK NOT DETECTED")
            stages.append("DEPLOYMENT STOPPED: physical flashing was skipped.")
            return jsonify(
                status="rejected",
                message="\n".join(stages) +
                "\n\nUART output:\n" +
                (uart_output[-3000:] or "(No UART output captured)") +
                "\n\nRenode output:\n" + renode_output[-2000:]
            )

        stages.append("Virtual UART: BOOT_OK DETECTED")
        stages.append("SIMULATION GATE: PASSED")

        stages.append("[3/4] Raspberry Pi connection: CHECKING")

        try:
            ssh_rc, ssh_output = run_command(
                ["ssh", *ssh_options(), f"{PI_USER}@{PI_HOST}", "true"],
                timeout=SSH_TIMEOUT + 5,
            )
        except subprocess.TimeoutExpired:
            stages.append("SSH connection: TIMEOUT")
            return jsonify(
                status="error",
                message="\n".join(stages) +
                "\nPhysical flashing was not attempted."
            ), 504

        if ssh_rc != 0:
            stages.append("SSH connection: FAILED")
            return jsonify(
                status="error",
                message="\n".join(stages) +
                "\n\nSSH output:\n" + ssh_output[-3000:] +
                "\n\nCheck SSH key authentication and the Pi's known-host entry."
            ), 502

        stages.append("SSH connection: OK")
        stages.append("SCP transfer: RUNNING")

        try:
            scp_rc, scp_output = transfer_to_pi(
                firmware_path,
                remote_path,
            )
        except subprocess.TimeoutExpired:
            stages.append("SCP transfer: TIMEOUT")
            return jsonify(
                status="error",
                message="\n".join(stages) +
                "\nPhysical flashing was not attempted."
            ), 504

        if scp_rc != 0:
            stages.append("SCP transfer: FAILED")
            return jsonify(
                status="error",
                message="\n".join(stages) +
                "\n\nSCP output:\n" + scp_output[-3000:] +
                "\n\nPhysical flashing was not attempted."
            ), 502

        stages.append("SCP transfer: COMPLETE")
        stages.append("OpenOCD: PROGRAMMING AND VERIFYING")

        try:
            flash_rc, flash_output = flash_on_pi(
                remote_path,
                target_config,
            )
        except subprocess.TimeoutExpired:
            stages.append("OpenOCD: TIMEOUT")
            stages.append(
                "WARNING: Check the physical target before retrying; "
                "the result may be incomplete."
            )
            return jsonify(
                status="error",
                message="\n".join(stages)
            ), 504

        verified = "Verified OK" in flash_output

        if flash_rc != 0 or not verified:
            stages.append("PHYSICAL FLASH: NOT CONFIRMED")
            return jsonify(
                status="error",
                message="\n".join(stages) +
                "\n\nOpenOCD output:\n" +
                (flash_output[-5000:] or "(No OpenOCD output captured)")
            ), 502

        stages.append("OpenOCD verification: PASSED")
        stages.append("Target reset: COMMAND COMPLETED")
        stages.append("DEPLOYMENT: SUCCESS")
        stages.append(
            "\nNote: flash verification succeeded; runtime health "
            "still requires a separate physical-device check."
        )

        return jsonify(
            status="passed",
            message="\n".join(stages) +
            "\n\nOpenOCD output:\n" + flash_output[-4000:]
        )

    except Exception as exc:
        app.logger.exception("Firmware deployment failed")
        return jsonify(
            status="error",
            message="\n".join(stages) +
            f"\n\nERROR: {exc}"
        ), 500

    finally:
        resc_path.unlink(missing_ok=True)


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify(
        status="error",
        message="ERROR: Maximum upload size is 32 MB."
    ), 413


if __name__ == "__main__":
    # Local development only. Do not expose this server to untrusted networks.
    app.run(host="127.0.0.1", port=5000, debug=False)
