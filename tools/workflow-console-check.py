"""Read-only loopback Console checks; optional real Windows screen capture."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

HTTP_TIMEOUT = 3
MAX_REPLY_BYTES = 256 * 1024
ENDPOINTS = ("/api/console/config", "/api/workflow/config", "/api/workspace-plan")


class CheckError(ValueError):
    pass


def loopback_base_url(value):
    """Numeric loopback only: no credentials, DNS, proxy, or alternate URL parts."""
    if not isinstance(value, str) or value != value.strip() or any(ord(char) < 33 for char in value):
        raise CheckError("检查地址必须是本机回环 HTTP 地址。")
    try:
        parsed = urllib.parse.urlsplit(value)
        host, port = parsed.hostname, parsed.port
        address = ipaddress.ip_address(host or "")
    except ValueError:
        raise CheckError("检查地址必须是本机回环 HTTP 地址。") from None
    if (parsed.scheme != "http" or not address.is_loopback or parsed.username is not None
            or parsed.password is not None or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment or port is not None and not 1 <= port <= 65535):
        raise CheckError("仅允许无路径、无凭据的本机回环 HTTP 地址。")
    return "http://" + ("[" + str(address) + "]" if address.version == 6 else str(address)) + (":" + str(port) if port is not None else "")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise CheckError("本机接口返回重定向，检查已停止。")


def get_json(base_url, endpoint):
    if endpoint not in ENDPOINTS:
        raise CheckError("检查接口无效。")
    base_url = loopback_base_url(base_url)
    # Ignore machine proxy configuration: this command must stay on loopback.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    request = urllib.request.Request(base_url + endpoint, headers={"Accept": "application/json"}, method="GET")
    try:
        with opener.open(request, timeout=HTTP_TIMEOUT) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise CheckError("本机接口响应格式无效（" + endpoint + "）。")
            raw = response.read(MAX_REPLY_BYTES + 1)
            if len(raw) > MAX_REPLY_BYTES:
                raise CheckError("本机接口响应过大（" + endpoint + "）。")
    except urllib.error.HTTPError as error:
        raise CheckError("本机接口检查失败（" + endpoint + "，HTTP " + str(error.code) + "）。") from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise CheckError("本机接口不可达或读取超时（" + endpoint + "）。") from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise CheckError("本机接口不是有效 JSON（" + endpoint + "）。") from None
    if not isinstance(payload, dict):
        raise CheckError("本机接口 JSON 结构无效（" + endpoint + "）。")
    return payload


def check_payloads(runtime, workflow, task_plan):
    version = runtime.get("runtime", {}).get("version") if isinstance(runtime.get("runtime"), dict) else None
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", version):
        raise CheckError("Console 运行版本响应无效。")
    computer, projects, models = workflow.get("computer"), workflow.get("projects"), workflow.get("models")
    if (not isinstance(computer, dict) or not isinstance(computer.get("id"), str) or not computer["id"]
            or not isinstance(projects, list) or not isinstance(models, dict) or type(models.get("ready")) is not bool):
        raise CheckError("工作流配置响应无效。")
    for project in projects:
        if (not isinstance(project, dict) or not isinstance(project.get("id"), str)
                or not isinstance(project.get("capabilities"), list) or not isinstance(project.get("commands"), list)
                or type(project.get("allowGeneratedScripts")) is not bool):
            raise CheckError("工作流项目配置响应无效。")
    if "plan" not in task_plan or not isinstance(task_plan.get("error"), str):
        raise CheckError("任务计划响应无效。")
    if task_plan["error"]:
        raise CheckError("本机任务计划读取失败；未修改已保存内容。")
    plan, group_count, task_count = task_plan["plan"], 0, 0
    if plan is not None:
        if (not isinstance(plan, dict) or type(plan.get("version")) is not int or plan["version"] != 1
                or not isinstance(plan.get("revision"), str) or not isinstance(plan.get("groups"), list)
                or not 1 <= len(plan["groups"]) <= 12):
            raise CheckError("本机任务计划结构无效。")
        for group in plan["groups"]:
            if not isinstance(group, dict) or not isinstance(group.get("items"), list) or len(group["items"]) > 100:
                raise CheckError("本机任务计划分组结构无效。")
            for item in group["items"]:
                if not isinstance(item, dict) or not isinstance(item.get("text"), str) or type(item.get("done")) is not bool:
                    raise CheckError("本机任务计划条目结构无效。")
            task_count += len(group["items"])
        group_count = len(plan["groups"])
        if task_count > 300:
            raise CheckError("本机任务计划条目超过有效上限。")
    return {"version": version, "projects": len(projects), "modelConfigured": models["ready"],
            "privatePlanConfigured": plan is not None, "groups": group_count, "tasks": task_count}


def run_checks(base_url):
    base_url = loopback_base_url(base_url)
    return check_payloads(*(get_json(base_url, endpoint) for endpoint in ENDPOINTS))


def output_paths(environment):
    try:
        output = Path(environment["CONSOLE_WORKFLOW_OUTPUT_DIR"])
        manifest = Path(environment["CONSOLE_WORKFLOW_RESULT_MANIFEST"])
        if (not output.is_absolute() or not manifest.is_absolute() or not output.is_dir()
                or output.resolve() != output.absolute() or output.is_symlink()
                or getattr(output, "is_junction", lambda: False)()
                or manifest.parent != output or manifest.exists() or manifest.is_symlink()):
            raise ValueError()
    except (KeyError, OSError, ValueError):
        raise CheckError("请通过 Console 工作任务运行；输出目录或结果清单无效。") from None
    return output, manifest


def write_result(result, output, manifest, capture_screen=False):
    text = "Console 可连接，运行版本 " + result["version"] + "；3 项本机 GET 检查通过。工作流登记项目 " + str(result["projects"]) + " 个。"
    if result["privatePlanConfigured"]:
        text += "本机任务计划种子有 " + str(result["groups"]) + " 组、" + str(result["tasks"]) + " 项；未读取浏览器未保存的编辑。"
    else:
        text += "未配置本机私有任务计划种子；未核对浏览器内任务。"
    text += "模型配置" + ("已就绪" if result["modelConfigured"] else "未就绪") + "；未测试模型调用。"
    files = []
    if capture_screen:
        image_path = output / "current-screen.png"
        if os.name != "nt" or image_path.exists() or image_path.is_symlink():
            raise CheckError("真实电脑截图需要 Windows 且目标图片必须尚不存在。")
        try:
            from PIL import ImageGrab
            screenshot = ImageGrab.grab(all_screens=True)
            try:
                if screenshot.width <= 0 or screenshot.height <= 0:
                    raise ValueError()
                screenshot.save(image_path, format="PNG")
            finally:
                screenshot.close()
        except (ImportError, OSError, RuntimeError, ValueError):
            raise CheckError("当前电脑画面截图失败；任务未生成完成清单。") from None
        files.append(image_path.name)
        text += "已附真实的当前电脑屏幕截图。"
    else:
        text += "未请求截图。"
    text += "未修改项目或应用配置。"
    descriptor, temporary = tempfile.mkstemp(prefix=".console-check-", suffix=".json", dir=output)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump({"text": text, "files": files}, target, ensure_ascii=False)
            target.write("\n")
        os.replace(temporary, manifest)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return text


def main(argv=None):
    # The worker decodes process output as UTF-8, independent of Windows locale.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="只读检查本机 Console；显式选项可附当前电脑截图。")
    parser.add_argument("--base-url", required=True, help="数字回环 HTTP 地址，例如 http://127.0.0.1:8898")
    parser.add_argument("--capture-screen", action="store_true", help="附真实 Windows 当前电脑屏幕截图")
    options = parser.parse_args(argv)
    try:
        output, manifest = output_paths(os.environ)
        result = run_checks(options.base_url)
        print(write_result(result, output, manifest, options.capture_screen))
        return 0
    except CheckError as error:
        print("Console 检查失败：" + str(error), file=sys.stderr)
        return 1
    except OSError:
        print("Console 检查失败：任务结果无法保存。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
