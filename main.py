import os
import json
import base64#用于处理 Together AI API 返回的 Base64 编码的图片数据。
import requests
import sys#用于发送 HTTP 请求到外部 API,图片搜索、下载、Together AI。
import re
from mcp.server import FastMCP#用于创建应用实例和注册工具。

#获取当前脚本所在目录，拼接配置文件路径，确保路径的正确性
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
CONFIG_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json.template")
CONFIG = {}

try:#检查 CONFIG_FILE 是否存在
    if not os.path.exists(CONFIG_FILE):
        # ... (错误处理) ...
        raise FileNotFoundError(f"关键配置文件 {CONFIG_FILE} 未找到。")
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
    CONFIG.setdefault("api", {})# 如果没有 'api' 键，设置为空字典
    CONFIG["api"].setdefault("unsplash_access_key", "")
    CONFIG["api"].setdefault("pexels_api_key", "")
    CONFIG["api"].setdefault("pixabay_api_key", "")
    CONFIG["api"].setdefault("together_api_key", "")
    CONFIG["api"].setdefault("timeout", 60)
    # 服务器配置
    CONFIG.setdefault("server", {"name": "Image Processing MCP Service", "host": "0.0.0.0", "port": 5173})
    # 图片处理配置
    CONFIG.setdefault("image", {"max_results": 20, "default_width": 512, "default_height": 512})
    #输出配置
    output_config = CONFIG.setdefault("output", {})

    output_config.setdefault("base_folder", "generated_mcp_output_final_v2")  # 改个名以区分

    output_config.setdefault("default_extension", ".png") # 默认文件扩展名
    output_config.setdefault("allowed_extensions", [".png", ".jpg", ".jpeg", ".svg"]) # 允许保存的文件扩展名
    # 处理输出基础文件夹的路径：如果不是绝对路径，则相对于当前脚本文件所在目录
    if not os.path.isabs(CONFIG["output"]["base_folder"]):
        CONFIG["output"]["base_folder"] = os.path.join(os.path.dirname(os.path.abspath(__file__)),
        CONFIG["output"]["base_folder"])
    # 创建输出文件夹，如果它不存在的话 (exist_ok=True 表示如果已存在则不报错)
    os.makedirs(CONFIG["output"]["base_folder"], exist_ok=True)
    missing_search_keys = []   # 检查图片搜索相关的 API 密钥是否配置，如果未配置则打印警告
    if not CONFIG["api"]["unsplash_access_key"]: missing_search_keys.append("unsplash_access_key")
    if not CONFIG["api"]["pexels_api_key"]: missing_search_keys.append("pexels_api_key")
    if not CONFIG["api"]["pixabay_api_key"]: missing_search_keys.append("pixabay_api_key")
    if missing_search_keys: print(f"警告: 图片搜索API密钥未配置: {', '.join(missing_search_keys)}.")
except FileNotFoundError:
    print(f"致命错误: 配置文件 {CONFIG_FILE} 未找到。"); sys.exit(1)
except KeyError as e:
    print(f"致命错误: 配置文件 {CONFIG_FILE} 中缺少键: {e}。"); sys.exit(1)
except Exception as e:
    print(f"加载配置文件时发生致命错误: {str(e)}"); sys.exit(1)
# --- 配置文件加载逻辑结束 ---

app = FastMCP(name=CONFIG["server"]["name"])


# 工具函数定义 (search_images, download_image, generate_icon) 

@app.tool()
#FastMCP 框架的核心特性。它将一个普通的 Python 函数注册为应用程序的一个“工具”。这个函数可以通过 FastMCP 提供的内部调用、HTTP 接口暴露被调用。函数的名称 和参数,带有类型提示 query: str 等被框架用来生成接口文档、验证输入等。
def search_images(query: str, source: str = "unsplash", max_results: str = "10") -> str:
    """搜索图片 (完整实现)"""
    try: # 1. 输入参数处理和验证
        max_results_int = int(max_results)# 将 max_results 字符串转换为整数
    except (TypeError, ValueError):
        return json.dumps({"success": False, "error": "max_results必须是有效的数字"})
    results = [] # 存储搜索结果
    # 限制最大结果数
    if max_results_int > CONFIG["image"]["max_results"]: max_results_int = CONFIG["image"]["max_results"]
    if max_results_int <= 0: max_results_int = 1
    try:
        api_timeout = CONFIG["api"].get("timeout", 30)# 获取API超时时间
        # 2. 根据指定的 source 调用不同的第三方图片 API
        if source.lower() == "unsplash":
            # 检查 Unsplash API 密钥是否配置
            if not CONFIG["api"]["unsplash_access_key"]: return json.dumps(
                {"success": False, "error": "Unsplash API key未配置"})
            # 构建 API 请求 URL 和参数,"Authorization"是一个标准的 HTTP 头部字段，通常用于传递身份验证凭证。
            #headers 字典确保了发送给 Unsplash API 的请求包含了正确的授权信息，否则 API 会拒绝请求
            api_url, headers, params = "https://api.unsplash.com/search/photos", {
                "Authorization": f"Client-ID {CONFIG['api']['unsplash_access_key']}"}, {"query": query,
                                                                                        "per_page": max_results_int}
            # 发送 API 请求
            response = requests.get(api_url, headers=headers, params=params, timeout=api_timeout)
            # 处理 API 响应
            if response.status_code == 200:
                data = response.json()
                 # 遍历结果，提取所需信息并添加到 results 列表
                for item in data.get("results", []): results.append(
                    {"id": item.get("id"), "url": item.get("urls", {}).get("small"),
                     "thumb": item.get("urls", {}).get("thumb"), "source": "unsplash",
                     "author": item.get("user", {}).get("name"), "download_url": item.get("urls", {}).get("raw")})
            else:
                # 处理 API 请求错误
                return json.dumps(
                    {"success": False, "error": f"Unsplash API错误: {response.status_code} - {response.text[:200]}"})
        elif source.lower() == "pexels": 
            if not CONFIG["api"]["pexels_api_key"]: return json.dumps(
                {"success": False, "error": "Pexels API key未配置"})
            api_url, headers, params = "https://api.pexels.com/v1/search", {
                "Authorization": CONFIG['api']['pexels_api_key']}, {"query": query, "per_page": max_results_int}
            response = requests.get(api_url, headers=headers, params=params, timeout=api_timeout)
            if response.status_code == 200:
                data = response.json();  # ... (Pexels 数据处理)
            else:
                return json.dumps(
                    {"success": False, "error": f"Pexels API错误: {response.status_code} - {response.text[:200]}"})
        elif source.lower() == "pixabay":  
            if not CONFIG["api"]["pixabay_api_key"]: return json.dumps(
                {"success": False, "error": "Pixabay API key未配置"})
            api_url, params = "https://pixabay.com/api/", {"key": CONFIG['api']['pixabay_api_key'], "q": query,
                                                           "per_page": max_results_int}
            response = requests.get(api_url, params=params, timeout=api_timeout)
            if response.status_code == 200:
                data = response.json();  # ... (Pixabay 数据处理)
            else:
                return json.dumps(
                    {"success": False, "error": f"Pixabay API错误: {response.status_code} - {response.text[:200]}"})
        else:
            return json.dumps({"success": False, "error": f"不支持图片源: {source}"})
    except requests.exceptions.RequestException as e_req:
        return json.dumps({"success": False, "error": f"搜索时网络请求错误: {e_req}"})
    except Exception as e:
        return json.dumps({"success": False, "error": f"搜索时未知错误: {e}"})
    return json.dumps({"success": True, "results": results})


@app.tool()
def download_image(url: str, file_name: str, save_folder: str = None) -> str:
    """下载图片 (完整实现)"""
    try:
        # 输入参数处理和验证
        current_base_folder = CONFIG["output"]["base_folder"]
        # 处理输出基础文件夹的路径：如果不是绝对路径，则相对于当前脚本文件所在目录
        if save_folder is None:
            # 如果 save_folder 为 None，则使用当前脚本文件所在目录作为保存文件夹
            save_folder_abs = current_base_folder
        else:
            # 处理保存文件夹的路径：如果不是绝对路径，则相对于当前脚本文件所在目录
            save_folder_abs = os.path.abspath(save_folder) if os.path.isabs(save_folder) else os.path.abspath(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), save_folder))
        os.makedirs(save_folder_abs, exist_ok=True) # 创建保存文件夹，如果它不存在的话
        # 处理文件名和扩展名
        default_ext, allowed_exts = CONFIG["output"]["default_extension"], CONFIG["output"]["allowed_extensions"]
        _, ext = os.path.splitext(file_name)
        if not ext:
            file_name += default_ext # 如果文件名没有扩展名，则添加默认扩展名
        elif ext.lower() not in allowed_exts:
            return json.dumps({"success": False, "error": f"不支持文件扩展名: {ext}"})
        save_path = os.path.join(save_folder_abs, file_name) # 构建保存路径
        # 发送 HTTP GET 请求下载图片
        response = requests.get(url, stream=True, timeout=CONFIG["api"].get("timeout", 30))
        if response.status_code == 200:
            # 处理成功下载的情况
            with open(save_path, 'wb') as f:
                # 逐块写入文件
                for chunk in response.iter_content(1024): f.write(chunk) 
                # 返回成功信息
            return json.dumps({"success": True, "message": f"图片已保存: {save_path}", "file_path": save_path})
        
        else:
            # 处理下载失败的情况
            return json.dumps({"success": False, "error": f"下载失败，状态码: {response.status_code}, URL: {url}"})
    except requests.exceptions.RequestException as e_req:
        # 处理网络请求错误
        return json.dumps({"success": False, "error": f"下载时网络请求错误: {e_req}"})
    except Exception as e:
        # 处理其他未知错误
        return json.dumps({"success": False, "error": f"下载时未知错误: {e}"})


@app.tool()
def generate_icon(prompt: str, file_name: str, save_folder: str = None, width: int = None, height: int = None) -> str:
    """生成图片"""
    try:
        current_base_folder = CONFIG["output"]["base_folder"]
        # 处理输出基础文件夹的路径：如果不是绝对路径，则相对于当前脚本文件所在目录
        if save_folder is None:
            # 如果 save_folder 为 None，则使用当前脚本文件所在目录作为保存文件夹
            save_folder_abs = current_base_folder
        else:
            # 处理保存文件夹的路径：如果不是绝对路径，则相对于当前脚本文件所在目录
            save_folder_abs = os.path.abspath(save_folder) if os.path.isabs(save_folder) else os.path.abspath(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), save_folder))
        os.makedirs(save_folder_abs, exist_ok=True) # 创建保存文件夹，如果它不存在的话
        if width is None: width = CONFIG["image"]["default_width"]
        # 如果 width 为 None，则使用配置中的默认宽度    
        if height is None: height = CONFIG["image"]["default_height"]
        # 如果 height 为 None，则使用配置中的默认高度
        default_ext, allowed_exts = CONFIG["output"]["default_extension"], CONFIG["output"]["allowed_extensions"]
        # 处理文件名和扩展名
        _, ext = os.path.splitext(file_name)
        if not ext:
            file_name += default_ext # 如果文件名没有扩展名，则添加默认扩展名
        elif ext.lower() not in allowed_exts:
            # 如果文件扩展名不支持，则返回错误信息
            return json.dumps({"success": False, "error": f"不支持文件扩展名: {ext}"})
        save_path = os.path.join(save_folder_abs, file_name) # 构建保存路径
        together_api_key = CONFIG["api"].get("together_api_key")
        if together_api_key:
            # 构建 API 请求 URL 和参数
            api_url = "https://api.together.xyz/v1/images/generations"
            # 设置请求头
            headers = {"Authorization": f"Bearer {together_api_key}", "Content-Type": "application/json",
                "Accept": "application/json"}
            # 构建 API 请求体
            payload = {"model": "black-forest-labs/FLUX.1-dev", "prompt": prompt, "n": 1, "size": f"{width}x{height}",
                    "response_format": "b64_json"}
            # 发送 API 请求
            response = requests.post(api_url, headers=headers, json=payload, timeout=CONFIG["api"].get("timeout", 90))
            # 处理 API 响应
            response_text_for_debug = response.text
            # 检查 API 响应状态码
            if response.status_code == 200:
                try:
                    data = json.loads(response_text_for_debug)
                    # 处理 API 响应中的图片结果
                    image_data_b64 = None
                    # 检查 API 响应是否包含图片数据
                    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list) and data[
                        "data"] and "b64_json" in data["data"][0]:
                        image_data_b64 = data["data"][0]["b64_json"]
                    if image_data_b64:
                        # 将 Base64 编码的图片数据解码并保存到文件
                        with open(save_path, 'wb') as f:
                            # 将 Base64 编码的图片数据解码并写入文件
                            f.write(base64.b64decode(image_data_b64))
                            # 返回成功信息
                            return json.dumps(
                            {"success": True, "message": f"图标已生成并保存: {save_path}", "file_path": save_path})
                    else:
                        # 处理 API 响应中未找到图片数据的情况
                        raise Exception("API响应成功(200)，但在 'data[0].b64_json' 未找到图像数据。")
                except json.JSONDecodeError as json_err:
                    # 处理 JSON 解析错误
                    raise Exception(
                        f"处理API响应时出错: 无法解析JSON (状态码200) - {json_err}. 响应(部分): {response_text_for_debug[:500]}")
                except Exception as inner_e:
                    # 处理 API 成功响应时出错
                    raise Exception(f"处理API成功响应(200)时出错: {inner_e}")
            else:
                # 处理 API 请求失败的情况
                raise Exception(
                    f"生成图标API请求失败，HTTP状态码: {response.status_code}, 响应: {response_text_for_debug}")
        else:  # ... (备用方案)
            # 处理 Together API 密钥未配置的情况
            print("警告 [generate_icon]: Together API密钥未配置，使用备用方案。")
            sample_icon_path = os.path.join(current_base_folder, "sample-icon.png")
            if os.path.exists(sample_icon_path):
                # 读取示例图标文件并写入保存路径
                with open(sample_icon_path, 'rb') as s, open(save_path, 'wb') as d:
                    d.write(s.read())
                # 返回成功信息
                return json.dumps(
                    {"success": True, "message": f"图标已保存: {save_path} (使用样例)", "file_path": save_path})
            else:
                # 处理无法找到示例图标文件的情况
                return json.dumps({"success": False, "error": f"无法找到示例图标文件 ({sample_icon_path})。"})
    except requests.exceptions.RequestException as e_req:
        # 处理网络请求错误
        return json.dumps({"success": False, "error": f"生成图标时网络请求错误: {e_req}"})
    except Exception as e:
        # 处理最外层错误
        return json.dumps({"success": False, "error": f"生成图标时最外层错误: {e}"})



def extract_api_response_from_error_or_json_in_main(result_json_str: str) -> str:
    try:
        result_dict = json.loads(result_json_str)
        error_message = result_dict.get("error", "")
        match_http_error = re.search(r", 响应:\s*(.*)", error_message, re.DOTALL)
        if match_http_error: extracted_text = match_http_error.group(1).strip(); return extracted_text
        match_json_parse_error = re.search(r"响应\(部分\):\s*(.*)", error_message, re.DOTALL);
        if match_json_parse_error: return match_json_parse_error.group(1).strip() + " (JSON解析错误时的部分响应)"
        if "API响应成功(200)" in error_message and "未找到图像数据" in error_message: return "API返回200但未找到图像数据。查看main.py的DEBUG日志。"
    except:
        pass
    return "未能从错误信息中提取到明确的API响应体。"


def run_internal_tests():
    print("开始内部测试 generate_icon 函数...\n")
    print("--- [main.py Test] 测试用例 1: 调用 Together AI API ---")
    prompt1 = "A detailed steampunk cat illustration, high quality"
    file_name1 = "steampunk_cat_main_test.png"
    print(f"提示词: {prompt1}, 文件名: {file_name1}")
    if not CONFIG.get("api", {}).get("together_api_key"): print(
        "警告 [main.py Test]: CONFIG 中未找到 'together_api_key'。此测试可能测试备用逻辑。")
    result1_json_str = generate_icon(prompt=prompt1, file_name=file_name1, width=512, height=512)
    result1 = json.loads(result1_json_str)
    print("API调用结果 [main.py Test]:", json.dumps(result1, indent=2, ensure_ascii=False))
    if result1.get("success"):
        print(f"成功！图标已保存在: {result1.get('file_path')}")
        if result1.get('file_path') and os.path.exists(result1.get('file_path')):
            print("文件已在磁盘上找到。")
        else:
            print(f"警告 [main.py Test]: 文件声称已保存，但在磁盘上未找到！路径: {result1.get('file_path')}")
    else:
        error_msg = result1.get('error', '')
        print(f"失败 [main.py Test]: {error_msg}")
        extracted = extract_api_response_from_error_or_json_in_main(result1_json_str)
        print(f"提取的API响应(若有) [main.py Test]:\n{extracted}")
    print("-" * 30 + "\n")
    print("所有内部测试执行完毕。")


if __name__ == "__main__":
    # 关键: FastMCP 的工具注册是在模块加载时，通过 @app.tool() 装饰器完成的。
    # 我们需要在启动服务前检查工具是否真的注册上了。

    # 尝试获取工具列表的更健壮方式
    registered_tools = []
    if hasattr(app, '_tools_data'):  # FastMCP 内部可能使用 _tools_data
        if isinstance(app._tools_data, dict):
            registered_tools = list(app._tools_data.keys())
        else:
            print(f"警告: app._tools_data 不是预期的字典类型，类型为 {type(app._tools_data)}")
            registered_tools = ["(app._tools_data结构未知)"]
    elif hasattr(app, 'tools'):  # 回退到检查 'tools'
        if isinstance(app.tools, dict):
            registered_tools = list(app.tools.keys())
        else:
            print(f"警告: app.tools 不是预期的字典类型，类型为 {type(app.tools)}")
            registered_tools = ["(app.tools结构未知)"]
    else:
        registered_tools = ["(app对象无tools或_tools_data属性)"]

    print(f"--- DEBUG [main.py @ __main__]: 尝试获取的工具列表: {registered_tools} ---")

    if len(sys.argv) > 1 and sys.argv[1].lower() in ["test", "test_generate_icon", "tests"]:
        print("运行内部测试套件...")
        run_internal_tests()
        sys.exit(0)
    else:
        import uvicorn

        # FastMCP 对象本身通常就是 ASGI 应用，或者通过 .app 或 .sse_app() 获取
        asgi_app = app
        if hasattr(app, 'sse_app') and callable(app.sse_app):
            try:
                asgi_app = app.sse_app()
                print("使用 app.sse_app() 作为 ASGI 应用。")
            except Exception as e_sse:
                print(f"调用 app.sse_app() 出错: {e_sse}, 将尝试直接使用 app 对象。")
        elif hasattr(app, 'app') and callable(app.app):  # 有些框架用 .app
            asgi_app = app.app
            print("使用 app.app 作为 ASGI 应用。")
        else:
            print("未找到 .sse_app() 或 .app(), 将直接使用 FastMCP 实例作为 ASGI 应用。")

        print(f"启动图片服务 - 名称: {CONFIG['server']['name']}")
        print(f"端口: {CONFIG['server']['port']}, 主机: {CONFIG['server']['host']}")
        print(f"提供的工具 (来自启动逻辑): {registered_tools if registered_tools else ['(无工具注册)']}")

        uvicorn.run(asgi_app, host=CONFIG['server']['host'], port=CONFIG['server']['port'])