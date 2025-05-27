# main.py

import json
import os
import base64
import uuid
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import argparse
import traceback
import sys
import requests

# --- Volcengine SDK Imports ---
try:
    import volcenginesdkcore
    import volcenginesdkcv20240606
    from volcenginesdkcore.rest import ApiException
    from volcenginesdkcore.configuration import Configuration
except ImportError:
    print("致命错误: 无法导入火山引擎核心 SDK (volcenginesdkcore 或 volcenginesdkcv*)。")
    print("请确保已正确安装: pip install volcengine-python-sdk")
    sys.exit(1)

# --- MCP Framework Import (假设存在) ---
try:
    from mcp.server import FastMCP

    app = FastMCP(name="图片处理与生成服务_MCP_App")
except ImportError:
    print("警告: FastMCP 框架未找到。如果您不使用此框架，可以忽略此消息。")


    class DummyApp:
        def tool(self):
            def decorator(func): return func

            return decorator


    app = DummyApp()

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
CONFIG = {}
VOLCENGINE_STYLES = {}


def load_config(config_path="config.json"):
    global CONFIG, VOLCENGINE_STYLES, CONFIG_FILE
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_path)
    default_config = {
        "api": {
            "unsplash_access_key": "", "pexels_api_key": "", "pixabay_api_key": "", "together_api_key": "",
            "volcengine": {"access_key_id": "YOUR_AK_HERE", "secret_access_key": "YOUR_SK_HERE",
                           "region": "cn-beijing"},
            "timeout": 60, "max_retries": 3, "retry_delay": 5
        },
        "server": {"name": "图片处理与生成服务", "host": "0.0.0.0", "port": 5173},
        "image": {"max_results": 20, "default_width": 512, "default_height": 512},
        "output": {"base_folder": "generated_images", "default_extension": ".png",
                   "allowed_extensions": [".png", ".jpg", ".jpeg", ".svg", ".webp"],
                   "logo_font_path": None, "logo_font_size": 20},
        "volcengine_styles": {
            "动漫风": {"req_key": "img2img_cartoon_style"},
            "国风-水墨": {"req_key": "img2img_pretty_style", "sub_req_key": "img2img_pretty_style_ink"},
            "写实漫画": {"req_key": "img2img_comic_style"},
            "通用模型": {"req_key": "img2img_general_style"},
            "网红日漫风": {"req_key": "img2img_ghibli_style"},
            "3D风": {"req_key": "img2img_disney_3d_style"},
            "写实风": {"req_key": "img2img_real_mix_style"},
            "天使风": {"req_key": "img2img_pastel_boys_style"},
            "日漫风": {"req_key": "img2img_makoto_style"},
            "公主风": {"req_key": "img2img_rev_animated_style"},
            "梦幻风": {"req_key": "img2img_blueline_style"},
            "水墨风": {"req_key": "img2img_water_ink_style"},
            "新莫奈花园": {"req_key": "i2i_ai_create_monet"},
            "水彩风": {"req_key": "img2img_water_paint_style"},
            "莫奈花园": {"req_key": "img2img_comic_style", "sub_req_key": "img2img_comic_style_monet"},
            "精致美漫": {"req_key": "img2img_comic_style", "sub_req_key": "img2img_comic_style_marvel"},
            "赛博机械": {"req_key": "img2img_comic_style", "sub_req_key": "img2img_comic_style_future"},
            "精致韩漫": {"req_key": "img2img_exquisite_style"},
            "浪漫光影": {"req_key": "img2img_pretty_style", "sub_req_key": "img2img_pretty_style_light"},
            "陶瓷娃娃": {"req_key": "img2img_ceramics_style"},
            "中国红": {"req_key": "img2img_chinese_style"},
            "丑萌粘土": {"req_key": "img2img_clay_style", "sub_req_key": "img2img_clay_style_3d"},
            "可爱玩偶": {"req_key": "img2img_clay_style", "sub_req_key": "img2img_clay_style_bubble"},
            "3D-游戏_Z时代": {"req_key": "img2img_3d_style", "sub_req_key": "img2img_3d_style_era"},
            "动画电影": {"req_key": "img2img_3d_style", "sub_req_key": "img2img_3d_style_movie"},
            "玩偶": {"req_key": "img2img_3d_style", "sub_req_key": "img2img_3d_style_doll"}
        }
    }
    if os.path.exists(CONFIG_FILE):
        print(f"Attempting to load config from: {CONFIG_FILE}")
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            CONFIG = {};
            for key, default_value in default_config.items():
                if key in loaded_config:
                    if isinstance(default_value, dict) and isinstance(loaded_config[key], dict):
                        CONFIG[key] = default_value.copy();
                        CONFIG[key].update(loaded_config[key])
                    else:
                        CONFIG[key] = loaded_config[key]
                else:
                    CONFIG[key] = default_value
            print("--- Successfully loaded CONFIG content (merged with defaults): ---")
        except Exception as e_load:
            print(f"加载配置文件时发生错误: {str(e_load)}. 将使用默认配置。"); CONFIG = default_config
    else:
        print(f"警告: 配置文件 {CONFIG_FILE} 未找到。将使用默认配置并尝试创建。");
        CONFIG = default_config
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f_create:
                json.dump(CONFIG, f_create, indent=4, ensure_ascii=False)
            print(f"已创建默认配置文件: {CONFIG_FILE}。请检查并填入您的 API 密钥。")
        except Exception as e_create_conf:
            print(f"创建默认配置文件失败: {e_create_conf}")
    api_conf = CONFIG.setdefault("api", default_config["api"])
    volc_conf_init = api_conf.setdefault("volcengine", default_config["api"]["volcengine"])
    volc_conf_init.setdefault("access_key_id", default_config["api"]["volcengine"]["access_key_id"])
    volc_conf_init.setdefault("secret_access_key", default_config["api"]["volcengine"]["secret_access_key"])
    volc_conf_init.setdefault("region", default_config["api"]["volcengine"]["region"])
    CONFIG.setdefault("server", default_config["server"]);
    CONFIG.setdefault("image", default_config["image"])
    output_config = CONFIG.setdefault("output", default_config["output"])
    output_config.setdefault("base_folder", default_config["output"]["base_folder"])
    output_config.setdefault("allowed_extensions", default_config["output"]["allowed_extensions"])
    VOLCENGINE_STYLES = CONFIG.setdefault("volcengine_styles", default_config["volcengine_styles"])
    if not os.path.isabs(CONFIG["output"]["base_folder"]):
        CONFIG["output"]["base_folder"] = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       CONFIG["output"]["base_folder"])
    os.makedirs(CONFIG["output"]["base_folder"], exist_ok=True)
    missing_keys = []
    volc_conf_startup_check = CONFIG.get("api", {}).get("volcengine", {})
    if not volc_conf_startup_check.get("access_key_id") or volc_conf_startup_check.get(
        "access_key_id") == "YOUR_AK_HERE": missing_keys.append("volcengine (access_key_id)")
    if not volc_conf_startup_check.get("secret_access_key") or volc_conf_startup_check.get(
        "secret_access_key") == "YOUR_SK_HERE": missing_keys.append("volcengine (secret_access_key)")
    if missing_keys: print(
        f"警告 (启动时检查): 以下 API 密钥/配置未在 config.json 中完全配置: {', '.join(missing_keys)}。火山引擎相关功能可能受限。")


load_config()


def get_volcengine_style_params(style_name: str) -> dict | None:
    style_params = VOLCENGINE_STYLES.get(style_name)
    if isinstance(style_params, dict):
        return style_params
    elif style_params is not None:
        print(f"警告: 风格 '{style_name}' 的配置格式不正确 (期望字典，得到 {type(style_params)}). 将尝试适应。")
        if isinstance(style_params, str): return {"req_key": style_params}
    return None


def _handle_save_path(file_name: str, save_folder: str = None) -> tuple[str, str, str]:
    # ... (与之前版本相同) ...
    current_base_folder = CONFIG["output"]["base_folder"]
    if save_folder is None:
        save_folder_abs = current_base_folder
    else:
        save_folder_abs = os.path.abspath(save_folder) if os.path.isabs(save_folder) else os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), save_folder))
    os.makedirs(save_folder_abs, exist_ok=True)
    default_ext, allowed_exts = CONFIG["output"]["default_extension"], CONFIG["output"]["allowed_extensions"]
    base_name, ext = os.path.splitext(file_name)
    if not ext:
        file_name_with_ext, actual_ext = base_name + default_ext, default_ext
    elif ext.lower() not in allowed_exts:
        raise ValueError(f"不支持文件扩展名: {ext}. 允许的扩展名: {', '.join(allowed_exts)}")
    else:
        file_name_with_ext, actual_ext = file_name, ext.lower()
    final_file_name, counter, save_path = file_name_with_ext, 1, os.path.join(save_folder_abs, file_name_with_ext)
    while os.path.exists(save_path):
        final_file_name = f"{base_name}_{counter}{actual_ext}";
        save_path = os.path.join(save_folder_abs, final_file_name);
        counter += 1
        if counter > 100: raise OverflowError("尝试生成唯一文件名失败次数过多。")
    return save_path, save_folder_abs, final_file_name


def _validate_image_for_volcengine(image_path: str) -> tuple[bool, str, str | None]:
    # ... (与之前版本相同) ...
    if not os.path.exists(image_path): return False, f"图片文件不存在: {image_path}", None
    _, ext = os.path.splitext(image_path)
    allowed_formats = ['.jpg', '.jpeg', '.png'];
    if ext.lower() not in allowed_formats: return False, f"不支持的图片格式: {ext}. 仅支持 JPG, JPEG, PNG。", None
    file_size_bytes = os.path.getsize(image_path)
    max_size_bytes = 5 * 1024 * 1024
    if file_size_bytes > max_size_bytes: return False, f"图片文件过大: {file_size_bytes / (1024 * 1024):.2f} MB. 最大允许 5 MB。", None
    min_res_w, min_res_h = 50, 50;
    max_res_w, max_res_h = 4096, 4096
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            if not (min_res_w <= width <= max_res_w and min_res_h <= height <= max_res_h):
                return False, f"图片分辨率 ({width}x{height}) 不符合要求。示例范围: 最小 {min_res_w}x{min_res_h}，最大 {max_res_w}x{max_res_h}。", None
            return True, "图片验证通过", img.format.lower() if img.format else ext.lower().lstrip('.')
    except Exception as e:
        return False, f"读取图片分辨率失败: {e}", None


def save_image_from_base64(
        base64_string: str, file_name: str, save_folder: str,
        add_logo: bool = False, logo_text_content: str = None, logo_font_path: str = None,
        logo_font_size: int = 20, logo_position: str = "bottom-right", logo_opacity: int = 128,
        image_format: str = "png"
) -> str:
    # ... (与之前版本相同) ...
    try:
        if not os.path.exists(save_folder): os.makedirs(save_folder, exist_ok=True)
        base_name, _ = os.path.splitext(file_name)
        actual_file_name = f"{base_name}.{image_format.lower().lstrip('.')}"
        file_path = os.path.join(save_folder, actual_file_name)
        image_data = base64.b64decode(base64_string);
        image = Image.open(BytesIO(image_data))
        if image.mode != 'RGBA': image = image.convert('RGBA')
        if add_logo and logo_text_content:
            draw = ImageDraw.Draw(image)
            _logo_font_path = logo_font_path if logo_font_path else CONFIG.get("output", {}).get("logo_font_path")
            _logo_font_size = logo_font_size if logo_font_size > 0 else CONFIG.get("output", {}).get("logo_font_size",
                                                                                                     20)
            try:
                font = ImageFont.truetype(_logo_font_path, _logo_font_size) if _logo_font_path and os.path.exists(
                    _logo_font_path) else ImageFont.load_default()
            except IOError:
                font = ImageFont.load_default(); print(f"警告: 字体 '{_logo_font_path}' 加载失败，使用默认字体。")
            text_bbox = draw.textbbox((0, 0), logo_text_content, font=font);
            text_width = text_bbox[2] - text_bbox[0];
            text_height = text_bbox[3] - text_bbox[1]
            margin = 10;
            img_width, img_height = image.size
            positions = {
                "bottom-right": (img_width - text_width - margin, img_height - text_height - margin),
                "bottom-left": (margin, img_height - text_height - margin),
                "top-left": (margin, margin),
                "top-right": (img_width - text_width - margin, margin)
            }
            x, y = positions.get(logo_position, positions["bottom-right"])
            x = max(x, 0);
            y = max(y, 0);
            text_color_rgb = (255, 255, 255);
            final_text_color = text_color_rgb + (logo_opacity,)
            draw.text((x, y), logo_text_content, font=font, fill=final_text_color)
        image_to_save = image;
        save_format_upper = image_format.upper()
        if save_format_upper in ["JPEG", "JPG"]:
            if image_to_save.mode == 'RGBA':
                rgb_image = Image.new("RGB", image_to_save.size, (255, 255, 255)); rgb_image.paste(image_to_save, mask=
                image_to_save.split()[3]); image_to_save = rgb_image
            elif image_to_save.mode != 'RGB':
                image_to_save = image_to_save.convert('RGB')
            save_format_upper = "JPEG"
        image_to_save.save(file_path, save_format_upper)
        print(f"Image successfully saved to: {file_path}")
        return file_path
    except Exception as e:
        print(f"Error in save_image_from_base64: {e}"); traceback.print_exc(); return None


# --- 其他工具函数 (search_images, download_image, generate_icon_togetherai) ---
@app.tool()
def search_images(query: str, source: str = "unsplash", max_results: str = "10") -> str:
    # ... (与您提供的代码相同) ...
    try:
        max_results_int = int(max_results)
    except (TypeError, ValueError):
        return json.dumps({"success": False, "error": "max_results必须是有效的数字"})
    results = [];
    max_results_int = min(max(1, max_results_int), CONFIG["image"]["max_results"]);
    api_timeout = CONFIG["api"].get("timeout", 30)
    try:
        if source.lower() == "unsplash":  # ... (Unsplash logic) ...
            if not CONFIG["api"]["unsplash_access_key"]: return json.dumps(
                {"success": False, "error": "Unsplash API key未配置"})
            api_url, headers, params = "https://api.unsplash.com/search/photos", {
                "Authorization": f"Client-ID {CONFIG['api']['unsplash_access_key']}"}, {"query": query,
                                                                                        "per_page": max_results_int}
            response = requests.get(api_url, headers=headers, params=params, timeout=api_timeout)
            if response.status_code == 200:
                data = response.json(); [results.append({"id": item.get("id"), "url": item.get("urls", {}).get("small"),
                                                         "thumb": item.get("urls", {}).get("thumb"),
                                                         "source": "unsplash",
                                                         "author": item.get("user", {}).get("name"),
                                                         "download_url": item.get("urls", {}).get("raw")}) for item in
                                         data.get("results", [])]
            else:
                return json.dumps(
                    {"success": False, "error": f"Unsplash API错误: {response.status_code} - {response.text[:200]}"})
        elif source.lower() == "pexels":  # ... (Pexels logic) ...
            if not CONFIG["api"]["pexels_api_key"]: return json.dumps(
                {"success": False, "error": "Pexels API key未配置"})
            api_url, headers, params = "https://api.pexels.com/v1/search", {
                "Authorization": CONFIG['api']['pexels_api_key']}, {"query": query, "per_page": max_results_int}
            response = requests.get(api_url, headers=headers, params=params, timeout=api_timeout)
            if response.status_code == 200:
                data = response.json(); [results.append(
                    {"id": str(item.get("id")), "url": item.get("src", {}).get("medium"),
                     "thumb": item.get("src", {}).get("tiny"), "source": "pexels", "author": item.get("photographer"),
                     "download_url": item.get("src", {}).get("original")}) for item in data.get("photos", [])]
            else:
                return json.dumps(
                    {"success": False, "error": f"Pexels API错误: {response.status_code} - {response.text[:200]}"})
        elif source.lower() == "pixabay":  # ... (Pixabay logic) ...
            if not CONFIG["api"]["pixabay_api_key"]: return json.dumps(
                {"success": False, "error": "Pixabay API key未配置"})
            api_url, params = "https://pixabay.com/api/", {"key": CONFIG['api']['pixabay_api_key'], "q": query,
                                                           "per_page": max_results_int, "image_type": "photo"}
            response = requests.get(api_url, params=params, timeout=api_timeout)
            if response.status_code == 200:
                data = response.json(); [results.append(
                    {"id": str(item.get("id")), "url": item.get("webformatURL"), "thumb": item.get("previewURL"),
                     "source": "pixabay", "author": item.get("user"), "download_url": item.get("largeImageURL")}) for
                                         item in data.get("hits", [])]
            else:
                return json.dumps(
                    {"success": False, "error": f"Pixabay API错误: {response.status_code} - {response.text[:200]}"})
        else:
            return json.dumps(
                {"success": False, "error": f"不支持图片源: {source}. 支持的源: unsplash, pexels, pixabay"})
    except requests.exceptions.RequestException as e_req:
        return json.dumps({"success": False, "error": f"搜索时网络请求错误: {e_req}"})
    except Exception as e:
        return json.dumps({"success": False, "error": f"搜索时未知错误: {e}"})
    return json.dumps({"success": True, "results": results})


@app.tool()
def download_image(url: str, file_name: str, save_folder: str = None) -> str:
    # ... (与您提供的代码相同) ...
    try:
        save_path, _, final_file_name = _handle_save_path(file_name, save_folder)
        response = requests.get(url, stream=True, timeout=CONFIG["api"].get("timeout", 60))
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                [f.write(chunk) for chunk in response.iter_content(8192)]
            return json.dumps(
                {"success": True, "message": f"图片 '{final_file_name}' 已保存到: {os.path.dirname(save_path)}",
                 "file_path": save_path, "file_name": final_file_name})
        else:
            return json.dumps({"success": False, "error": f"下载失败，状态码: {response.status_code}, URL: {url}"})
    except ValueError as ve:
        return json.dumps({"success": False, "error": str(ve)})
    except requests.exceptions.RequestException as e_req:
        return json.dumps({"success": False, "error": f"下载时网络请求错误: {e_req}"})
    except OverflowError as oe:
        return json.dumps({"success": False, "error": str(oe)})
    except Exception as e:
        return json.dumps({"success": False, "error": f"下载时未知错误: {e}"})


@app.tool()
def generate_icon_togetherai(prompt: str, file_name: str, save_folder: str = None, width: int = None,
                             height: int = None) -> str:
    # ... (与您提供的代码相同) ...
    try:
        save_path, _, final_file_name = _handle_save_path(file_name, save_folder)
        actual_width = width if width is not None else CONFIG["image"]["default_width"];
        actual_height = height if height is not None else CONFIG["image"]["default_height"]
        together_api_key = CONFIG["api"].get("together_api_key")
        if not together_api_key: return json.dumps({"success": False, "error": "Together AI API key 未配置。"})
        api_url = "https://api.together.xyz/v1/images/generations";
        headers = {"Authorization": f"Bearer {together_api_key}", "Content-Type": "application/json",
                   "Accept": "application/json"}
        payload = {"model": "black-forest-labs/FLUX.1-dev", "prompt": prompt, "n": 1, "width": actual_width,
                   "height": actual_height, "response_format": "b64_json"}
        response = requests.post(api_url, headers=headers, json=payload, timeout=CONFIG["api"].get("timeout", 120));
        response_text_for_debug = response.text
        if response.status_code == 200:
            try:
                data = json.loads(response_text_for_debug);
                image_data_b64 = data.get("data", [{}])[0].get("b64_json")
                if image_data_b64:
                    with open(save_path, 'wb') as f:
                        f.write(base64.b64decode(image_data_b64))
                    return json.dumps({"success": True,
                                       "message": f"图标 '{final_file_name}' 已生成并保存到: {os.path.dirname(save_path)}",
                                       "file_path": save_path, "file_name": final_file_name})
                else:
                    raise Exception("API响应成功(200)，但在 'data[0].b64_json' 未找到图像数据。")
            except (json.JSONDecodeError, IndexError, KeyError, Exception) as inner_e:
                return json.dumps({"success": False,
                                   "error": f"处理API成功响应时出错: {inner_e}. 响应(部分): {response_text_for_debug[:500]}"})
        else:
            return json.dumps({"success": False,
                               "error": f"Together AI API请求失败，状态码: {response.status_code}, 响应: {response_text_for_debug}"})
    except ValueError as ve:
        return json.dumps({"success": False, "error": str(ve)})
    except requests.exceptions.RequestException as e_req:
        return json.dumps({"success": False, "error": f"生成图标时网络请求错误: {e_req}"})
    except OverflowError as oe:
        return json.dumps({"success": False, "error": str(oe)})
    except Exception as e:
        return json.dumps({"success": False, "error": f"生成图标时未知错误: {e}"})


@app.tool()
def volcengine_style_transfer(
        input_image_path: str,
        style_name: str,
        file_name: str,
        save_folder: str = None,
        add_logo: bool = False,
        logo_position: int = 0,
        logo_language: int = 0,
        logo_opacity: float = 0.3,
        logo_text_content: str = None
) -> str:
    print("--- Inside volcengine_style_transfer ---")
    try:
        volc_conf = CONFIG.get('api', {}).get('volcengine', {})
        if not volc_conf: return json.dumps(
            {"success": False, "error": "Volcengine API configuration not found in CONFIG."})

        ak_check = volc_conf.get("access_key_id")
        sk_check = volc_conf.get("secret_access_key")
        region = volc_conf.get("region", "cn-beijing")

        if not (isinstance(ak_check, str) and ak_check and ak_check not in ["", "YOUR_AK_HERE"]):
            return json.dumps({"success": False, "error": "火山引擎 Access Key ID 未在 config.json 中正确配置。"})
        if not (isinstance(sk_check, str) and sk_check and sk_check not in ["", "YOUR_SK_HERE"]):
            return json.dumps({"success": False, "error": "火山引擎 Secret Access Key 未在 config.json 中正确配置。"})
        print(f"DEBUG: Using AK='{ak_check[:5]}...', Region='{region}'")

        is_valid, validation_msg, image_original_format = _validate_image_for_volcengine(input_image_path)
        if not is_valid: return json.dumps({"success": False, "error": f"输入图片验证失败: {validation_msg}"})

        selected_style_params = get_volcengine_style_params(style_name)
        if not selected_style_params:
            valid_styles = ", ".join(VOLCENGINE_STYLES.keys())
            return json.dumps(
                {"success": False, "error": f"无效的风格名称或配置错误: '{style_name}'. 可选风格: {valid_styles}"})

        req_key_value = selected_style_params.get("req_key")
        if not req_key_value: return json.dumps(
            {"success": False, "error": f"内部错误：风格 '{style_name}' 缺少有效的 req_key 配置。"})
        print(f"DEBUG: Using req_key: {req_key_value} for style '{style_name}'")

        try:
            save_path, _, final_file_name = _handle_save_path(file_name, save_folder)
        except Exception as e_path:
            return json.dumps({"success": False, "error": f"处理保存路径时出错: {e_path}"})

        configuration = volcenginesdkcore.Configuration()
        configuration.ak = ak_check;
        configuration.sk = sk_check;
        configuration.region = region
        configuration.client_side_validation = True
        volcenginesdkcore.Configuration.set_default(configuration)
        api_instance = volcenginesdkcv20240606.CV20240606Api()
        print(f"DEBUG: API instance created: {type(api_instance)}")

        with open(input_image_path, "rb") as image_file:
            binary_data_base64_str = base64.b64encode(image_file.read()).decode('utf-8')

        aigc_stylize_image_request = volcenginesdkcv20240606.AIGCStylizeImageRequest(
            req_key=req_key_value, binary_data_base64=[binary_data_base64_str]
        )
        sub_req_key_value = selected_style_params.get("sub_req_key")
        if sub_req_key_value:
            aigc_stylize_image_request.sub_req_key = sub_req_key_value

        if add_logo:
            try:
                from volcenginesdkcv20240606.models.logo_info_for_aigc_stylize_image_input import \
                    LogoInfoForAIGCStylizeImageInput as LogoInfoParam
            except ImportError:
                try:
                    from volcenginesdkcv20240606.models.logo_info_param import LogoInfoParam
                except ImportError:
                    return json.dumps({"success": False, "error": "无法导入火山引擎LogoInfo模型。"})

            logo_info_obj = LogoInfoParam()
            logo_info_obj.add_logo = add_logo
            logo_info_obj.position = int(logo_position)
            logo_info_obj.language = int(logo_language)
            logo_info_obj.opacity = float(logo_opacity)
            if logo_text_content: logo_info_obj.logo_text_content = logo_text_content
            aigc_stylize_image_request.logo_info = logo_info_obj

        print("DEBUG: Calling Volcengine API: a_igc_stylize_image...")
        api_response = api_instance.a_igc_stylize_image(aigc_stylize_image_request)
        print("DEBUG: API call completed.")
        # print(f"DEBUG: Full API Response content: {api_response}") # 非常重要！！！调试时务必取消注释查看此输出

        # --- MODIFIED RESPONSE HANDLING ---
        request_id_str = "N/A"
        # 尝试从不同位置获取 request_id
        if hasattr(api_response, 'result') and api_response.result and \
                hasattr(api_response.result, 'algorithm_base_resp') and api_response.result.algorithm_base_resp and \
                hasattr(api_response.result.algorithm_base_resp,
                        'request_id') and api_response.result.algorithm_base_resp.request_id:
            request_id_str = api_response.result.algorithm_base_resp.request_id
        elif hasattr(api_response, 'request_id') and api_response.request_id:
            request_id_str = api_response.request_id
        # 您的日志显示成功时顶层有 code=10000, 和 data.request_id
        elif hasattr(api_response, 'data') and api_response.data and hasattr(api_response.data,
                                                                             'request_id') and api_response.data.request_id:
            request_id_str = api_response.data.request_id

        # 检查成功条件 (基于您的成功日志结构)
        if hasattr(api_response, 'code') and getattr(api_response, 'code', -1) == 10000 and \
                hasattr(api_response, 'data') and api_response.data and \
                hasattr(api_response.data, 'binary_data_base64') and api_response.data.binary_data_base64 and \
                isinstance(api_response.data.binary_data_base64, list) and len(
            api_response.data.binary_data_base64) > 0 and \
                isinstance(api_response.data.binary_data_base64[0], str) and api_response.data.binary_data_base64[0]:

            output_image_b64 = api_response.data.binary_data_base64[0]
            output_format_to_save = image_original_format if image_original_format else "png"

            saved_path_final = save_image_from_base64(
                output_image_b64, final_file_name, os.path.dirname(save_path),
                image_format=output_format_to_save
            )

            if saved_path_final:
                return json.dumps({
                    "success": True,
                    "message": f"图片风格化成功 ('{style_name}'). '{final_file_name}' 已保存到: {os.path.dirname(save_path)}",
                    "file_path": saved_path_final, "file_name": final_file_name,
                    "style_applied": style_name, "request_id": request_id_str
                })
            else:
                return json.dumps(
                    {"success": False, "error": "风格化成功但保存输出图片失败。", "request_id": request_id_str})
        else:
            # 如果不符合上述成功结构，则尝试提取错误信息
            error_detail = "火山引擎API未返回预期的成功状态或图像数据。"
            # 尝试从 result.algorithm_base_resp 获取错误 (常见于业务失败但HTTP成功)
            if hasattr(api_response, 'result') and api_response.result and \
                    hasattr(api_response.result, 'algorithm_base_resp') and api_response.result.algorithm_base_resp:
                algo_resp = api_response.result.algorithm_base_resp
                algo_status_code = getattr(algo_resp, 'status_code', -1)
                algo_status_message = getattr(algo_resp, 'status_message', "N/A")
                if algo_status_code != 0:  # 假设0是内部算法成功码
                    error_detail = f"算法处理错误: StatusCode={algo_status_code}, StatusMessage='{algo_status_message}'"
            # 尝试从顶层 code 和 message 获取错误 (如果存在且 code 不是成功码)
            elif hasattr(api_response, 'code') and hasattr(api_response, 'message'):
                top_code = getattr(api_response, 'code', -1)
                top_message = getattr(api_response, 'message', 'N/A')
                if top_code != 10000:  # 假设10000是通用成功码
                    error_detail = f"火山引擎API业务错误: Code={top_code}, Message='{top_message}'"

            print(f"ERROR: {error_detail}")
            print(f"DEBUG: API Response for error diagnosis: {api_response}")
            return json.dumps({"success": False, "error": error_detail, "request_id": request_id_str})

    except ApiException as e:
        # ... (ApiException 处理与之前相同) ...
        error_message_detail = str(e.body) if e.body else str(e)
        try:
            error_body_json = json.loads(e.body); error_message_detail = error_body_json.get("Error", {}).get("Message",
                                                                                                              error_message_detail)
        except:
            pass
        print(f"Volcengine API Exception: Status={e.status}, Code={e.code}, Message='{error_message_detail}'")
        return json.dumps({"success": False,
                           "error": f"火山引擎API异常: Status={e.status}, Code={e.code}, Msg='{error_message_detail}'"})
    except Exception as e_gen:
        print(f"火山引擎风格化时发生未知错误: {e_gen}")
        traceback.print_exc()
        return json.dumps({"success": False, "error": f"火山引擎风格化时发生未知错误: {str(e_gen)}"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Volcengine Image Style Transfer CLI for MCP")
    # ... (argparse 定义与之前相同) ...
    parser.add_argument("--image_path", type=str, help="Path to the input image.")
    parser.add_argument("--style_name", type=str, help="Name of the desired style.")
    parser.add_argument("--output_name", type=str, help="Name for the output styled image file (e.g., styled.png).")
    parser.add_argument("--output_folder", type=str, default=None,
                        help="Folder to save the output image. Uses config default if None.")
    parser.add_argument("--add_logo", action='store_true', help="Add a logo/watermark to the image via Volcengine API.")
    parser.add_argument("--logo_text", type=str, default=None, help="Text content for the Volcengine API logo.")
    parser.add_argument("--logo_position", type=int, default=0,
                        help="Logo position for Volcengine API (e.g., 0-8, check API docs).")
    parser.add_argument("--logo_language", type=int, default=0,
                        help="Logo language for Volcengine API (e.g., 0 for zh, 1 for en, check API docs).")
    parser.add_argument("--logo_opacity", type=float, default=0.3, help="Logo opacity for Volcengine API (0.0-1.0).")
    args = parser.parse_args()
    DEFAULT_TEST_IMAGE_PATH = r"C:\mcp\images_mcp\icons\cat_generated.jpg"
    cli_image_path = args.image_path if args.image_path else DEFAULT_TEST_IMAGE_PATH
    cli_style_name = args.style_name if args.style_name else "动漫风"
    cli_output_name = args.output_name if args.output_name else f"cli_styled_{cli_style_name.replace(' ', '_')}.png"
    cli_output_folder = args.output_folder
    print(f"--- main.py executed directly with parameters ---")
    print(f"Image Path: {cli_image_path}")
    print(f"Style Name: {cli_style_name}")
    print(f"Output Name: {cli_output_name}")
    print(f"Output Folder: {cli_output_folder if cli_output_folder else 'Default (from config)'}")
    if args.add_logo: print(
        f"Add Logo: True, Text: {args.logo_text}, Pos: {args.logo_position}, Lang: {args.logo_language}, Opacity: {args.logo_opacity}")
    if not os.path.exists(cli_image_path):
        print(f"错误：测试图片路径不存在: {cli_image_path}")
    else:
        result_str = volcengine_style_transfer(
            input_image_path=cli_image_path, style_name=cli_style_name, file_name=cli_output_name,
            save_folder=cli_output_folder, add_logo=args.add_logo, logo_text_content=args.logo_text,
            logo_position=args.logo_position, logo_language=args.logo_language, logo_opacity=args.logo_opacity
        )
        print("\n--- Direct Run Result (JSON) ---")
        print(result_str)
        try:
            result_data = json.loads(result_str)
            if result_data.get("success"):
                print(f">>> Output image saved to: {result_data.get('file_path')}")
            else:
                print(f">>> Error: {result_data.get('error')}")
        except:
            pass
    print("--- Starting FastMCP server ---")
    try:
        import uvicorn

        if isinstance(app, FastMCP):
            asgi_app_to_run = app
            if hasattr(app, 'sse_app') and callable(app.sse_app):
                try:
                    asgi_app_to_run = app.sse_app()
                except Exception:
                    pass
            uvicorn.run(asgi_app_to_run, host=CONFIG['server']['host'], port=CONFIG['server']['port'])
        else:
            print("错误: FastMCP 应用实例未正确初始化，无法启动服务器。")
    except ImportError:
        print("错误: uvicorn 未安装，无法启动服务器。请运行 'pip install uvicorn'.")
