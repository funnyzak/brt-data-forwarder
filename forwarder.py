#!/usr/bin/env python3
"""
数据转发服务器
接收专有格式的环境传感器数据，处理特殊指标的缓存逻辑，并转发到多个目标服务器。
"""

import json
import logging
import os
import sys
import threading
import time
from copy import deepcopy
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests
import yaml
from flask import Flask, jsonify, request


VERSION = "0.0.1"

class DataForwarder:
    """数据转发服务器主类"""

    def __init__(self, config_path="config.yaml"):
        """初始化转发服务器

        Args:
            config_path: 配置文件路径
        """
        self.config = self._load_config(config_path)
        self.app = Flask(__name__)
        self._setup_logging()
        self._cache_lock = threading.RLock()

        # 确保必要的目录存在
        Path("./data").mkdir(exist_ok=True)
        Path("./logs").mkdir(exist_ok=True)

        self.logger.info("Data forwarder initialized")

        # 注册路由
        self._register_routes()

    def _load_config(self, config_path):
        """加载配置文件，支持环境变量覆盖

        Args:
            config_path: 配置文件路径

        Returns:
            dict: 配置字典
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # 应用环境变量覆盖
            config = self._apply_env_overrides(config)
            return config
        except FileNotFoundError:
            print(f"配置文件不存在: {config_path}")
            print("请参考 config.yaml.example 创建配置文件")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"配置文件格式错误: {e}")
            sys.exit(1)

    def _apply_env_overrides(self, config):
        """应用环境变量覆盖配置

        环境变量命名规则: BRT_ 前缀 + 双下划线层级
        例如: BRT_SERVER__PORT=8080, BRT_PROCESSING__ENABLED=false

        Args:
            config: 原始配置字典

        Returns:
            dict: 应用环境变量覆盖后的配置字典
        """     
        def convert_value(value, reference_value=None):
            """智能类型转换
            
            Args:
                value: 要转换的字符串值
                reference_value: 参考值，用于类型推断
            """
            # 如果有参考值，根据其类型转换
            if reference_value is not None:
                if isinstance(reference_value, bool):
                    return str(value).lower() in ('true', '1', 'yes', 'on')
                elif isinstance(reference_value, int):
                    try:
                        return int(value)
                    except ValueError:
                        self.logger.warning(f"无法将 '{value}' 转换为 int，保持字符串类型")
                        return value
                elif isinstance(reference_value, float):
                    try:
                        return float(value)
                    except ValueError:
                        self.logger.warning(f"无法将 '{value}' 转换为 float，保持字符串类型")
                        return value
            
            # 无参考值时，尝试自动推断类型
            # 布尔值
            if value.lower() in ('true', 'false', 'yes', 'no', 'on', 'off'):
                return value.lower() in ('true', 'yes', 'on', '1')
            
            # 整数
            try:
                if '.' not in value:
                    return int(value)
            except ValueError:
                pass
            
            # 浮点数
            try:
                return float(value)
            except ValueError:
                pass
            
            # None 值
            if value.lower() in ('null', 'none', ''):
                return None
            
            # 默认返回字符串
            return value

        def set_nested_value(d, key_path, value):
            """在嵌套字典中设置值
            
            Args:
                d: 目标字典
                key_path: 点分隔的键路径（小写）
                value: 要设置的值
            """
            keys = key_path.split('__')
            current = d

            # 导航到最后一级的父级
            for i, key in enumerate(keys[:-1]):
                if key not in current:
                    current[key] = {}
                elif not isinstance(current[key], dict):
                    # 中间节点不是字典，无法继续
                    return False
                current = current[key]

            # 设置最终值
            final_key = keys[-1]
            reference_value = current.get(final_key)
            converted_value = convert_value(value, reference_value)
            
            old_value = current.get(final_key, '<不存在>')
            current[final_key] = converted_value
            
            self.logger.info(
                f"环境变量覆盖配置: {key_path} = {converted_value} "
                f"(原值: {old_value}, 类型: {type(converted_value).__name__})"
            )
            return True

        # 遍历所有环境变量，找到以 BRT_ 开头的变量
        override_count = 0
        for env_key, env_value in os.environ.items():
            if env_key.startswith('BRT_'):
                # 移除 BRT_ 前缀，转换为小写
                config_path = env_key[4:].lower()
                
                if set_nested_value(config, config_path, env_value):
                    override_count += 1
        
        if override_count > 0:
            self.logger.info(f"共应用 {override_count} 个环境变量配置覆盖")
        
        return config

    def _setup_logging(self):
        """设置日志系统"""
        log_config = self.config.get('logging', {})

        # 设置日志级别
        level = getattr(logging, log_config.get('level', 'INFO').upper())
        logging.basicConfig(level=level)

        # 创建 logger
        self.logger = logging.getLogger('DataForwarder')
        self.logger.setLevel(level)

        # 清除默认的处理器
        self.logger.handlers.clear()

        # 创建格式化器
        formatter = logging.Formatter(
            log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # 文件处理器
        log_file = log_config.get('file_path', './logs/forwarder.log')
        max_bytes = log_config.get('max_bytes', 10 * 1024 * 1024)  # 10MB
        backup_count = log_config.get('backup_count', 7)

        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # 设置 werkzeug 日志级别
        logging.getLogger('werkzeug').setLevel(logging.WARNING)

    def _register_routes(self):
        """注册 Flask 路由"""
        receiver_config = self.config.get('receiver', {})
        receiver_path = receiver_config.get('path', '/receive_brt_data')

        @self.app.route(receiver_path, methods=['POST'])
        def receive_data():
            """接收并转发数据"""
            try:
                # 认证检查
                if not self._authenticate(request):
                    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
                    self.logger.warning(f"Authentication failed from {client_ip}")
                    return jsonify({"success": False, "error": "Unauthorized"}), 401

                # 解析 JSON 数据
                self.logger.debug(f"Received data: {request.get_data()}")
                try:
                    input_data = request.get_json()
                    if not input_data:
                        self.logger.error("Empty JSON data received")
                        return jsonify({"success": False, "error": "Empty JSON data"}), 400
                except Exception as e:
                    self.logger.error(f"JSON parsing failed: {e}")
                    return jsonify({"success": False, "error": "Invalid JSON data"}), 400

                # 记录接收到的数据
                client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
                seq_no = input_data.get('seq_no', 'N/A')
                device_count = len(input_data.get('devices', []))

                # 检查数据处理状态
                processing_enabled = self.config.get('processing', {}).get('enabled', True)
                processing_status = "enabled" if processing_enabled else "disabled"

                self.logger.info(f"Received data from {client_ip}, seq_no={seq_no}, devices={device_count}, processing={processing_status}")

                # 数据处理
                processed_data = self._process_data(input_data)

                # 转发数据
                forward_results = self._forward_data(processed_data)

                # 返回成功响应
                return jsonify({
                    "success": True,
                    "message": "Data received and forwarded",
                    "forward_results": forward_results
                }), 200

            except Exception as e:
                self.logger.error(f"Exception in receive_data: {e}", exc_info=True)
                return jsonify({"success": False, "error": "Internal server error"}), 500

        @self.app.route('/api/device/<ble_addr>', methods=['GET'])
        def get_device_data(ble_addr):
            """查询设备数据"""
            try:
                # 认证检查
                if not self._authenticate(request):
                    return jsonify({"success": False, "error": "Unauthorized"}), 401

                # 获取设备数据
                device_data = self._get_device_data(ble_addr)
                if not device_data:
                    return jsonify({"success": False, "error": "Device not found"}), 404

                return jsonify({"success": True, "data": device_data}), 200

            except Exception as e:
                self.logger.error(f"Exception in get_device_data: {e}", exc_info=True)
                return jsonify({"success": False, "error": "Internal server error"}), 500

        @self.app.route('/health', methods=['GET'])
        def health_check():
            """健康检查接口"""
            uptime = time.time() - getattr(self, '_start_time', time.time())
            return jsonify({
                "status": "healthy",
                "version": VERSION,
                "uptime": int(uptime)
            }), 200

    def _authenticate(self, request):
        """认证请求

        Args:
            request: Flask request 对象

        Returns:
            bool: 认证是否通过
        """
        auth_config = self.config.get('receiver', {}).get('auth', {})

        if not auth_config.get('enabled', False):
            return True

        # 获取有效 token 列表
        valid_tokens = auth_config.get('valid_tokens', [])
        if not valid_tokens:
            return True

        # 检查 query 参数
        query_param = auth_config.get('query_param', 'auth_token')
        token_from_query = request.args.get(query_param)

        # 检查 header
        header_name = auth_config.get('header', 'Authorization')
        token_from_header = request.headers.get(header_name)

        # 任一有效即可
        return token_from_query in valid_tokens or token_from_header in valid_tokens

    def _process_data(self, input_data):
        """处理输入数据，填充缓存值

        Args:
            input_data: 输入数据字典

        Returns:
            dict: 处理后的数据
        """
        # 检查是否启用数据处理
        processing_config = self.config.get('processing', {})
        processing_enabled = processing_config.get('enabled', True)

        # 创建处理后的数据副本
        if processing_enabled:
            processed_data = deepcopy(input_data)
        else:
            # 如果不处理数据，直接使用原始数据，但仍需要创建副本用于缓存更新
            processed_data = input_data

        # 缓存配置
        cache_config = self.config.get('cache', {})
        special_metrics = cache_config.get('special_metrics', [])
        invalid_patterns = cache_config.get('invalid_patterns', ['FFFF', 'FFFE'])

        # 无论是否启用数据处理，都需要更新缓存
        for device in processed_data.get('devices', []):
            ble_addr = device.get('ble_addr')
            scan_time = device.get('scan_time', 0)

            if not ble_addr:
                continue

            for metric in special_metrics:
                if metric in device:
                    value = device[metric]

                    # 检查是否为无效值（大小写不敏感）
                    if value.upper() in [p.upper() for p in invalid_patterns]:
                        # 无效值处理
                        if processing_enabled:
                            # 只有启用数据处理时才使用缓存替换无效值
                            cached = self._get_cached_metric(ble_addr, metric)
                            if cached:
                                device[metric] = cached['value']
                                self.logger.info(f"Used cached value for {ble_addr}.{metric}: {cached['value']}")
                            else:
                                # 保持原值 FFFF
                                self.logger.info(f"No cache available for {ble_addr}.{metric}, keeping invalid value: {value}")
                        else:
                            # 不处理数据时，仅记录日志
                            self.logger.info(f"Data processing disabled, keeping invalid value for {ble_addr}.{metric}: {value}")
                    else:
                        # 有效值，总是更新缓存
                        self._update_cache(ble_addr, metric, value, scan_time)
                        self.logger.info(f"Updated cache for {ble_addr}.{metric}: {value}")

        return processed_data

    def _load_cache(self):
        """从JSON文件加载缓存

        Returns:
            dict: 缓存数据
        """
        cache_file = self.config.get('cache', {}).get('file_path', './data/cache.json')

        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Cache file corrupted, creating new cache: {e}")

        return {}

    def _save_cache(self, cache_data):
        """保存缓存到JSON文件

        Args:
            cache_data: 缓存数据
        """
        cache_file = self.config.get('cache', {}).get('file_path', './data/cache.json')

        try:
            with self._cache_lock:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            self.logger.error(f"Failed to save cache: {e}")

    def _get_cached_metric(self, ble_addr, metric):
        """获取缓存的指标值

        Args:
            ble_addr: 设备BLE地址
            metric: 指标名称

        Returns:
            dict or None: 缓存的指标数据
        """
        cache = self._load_cache()
        return cache.get(ble_addr, {}).get(metric)

    def _update_cache(self, ble_addr, metric, value, scan_time):
        """更新缓存（线程安全）

        Args:
            ble_addr: 设备BLE地址
            metric: 指标名称
            value: 指标值
            scan_time: 采集时间戳
        """
        cache = self._load_cache()

        if ble_addr not in cache:
            cache[ble_addr] = {}

        cache[ble_addr][metric] = {
            'value': value,
            'scan_time': scan_time,
            'updated_at': int(time.time())
        }

        self._save_cache(cache)

    def _forward_data(self, data):
        """串行转发数据到多个目标

        Args:
            data: 要转发的数据

        Returns:
            list: 转发结果列表
        """
        forwarder_config = self.config.get('forwarder', {})
        targets = forwarder_config.get('targets', [])
        retry_config = forwarder_config.get('retry', {})

        self.logger.debug(f"Forwarding data to {targets}, data={json.dumps(data, indent=2)}")


        results = []

        for target in targets:
            url = target.get('url')
            timeout = target.get('timeout', 5)

            if not url:
                continue

            success = False
            attempts = 0
            max_attempts = 1 + (retry_config.get('max_attempts', 0) if retry_config.get('enabled', False) else 0)

            while attempts < max_attempts and not success:
                attempts += 1

                try:
                    start_time = time.time()
                    response = requests.post(
                        url,
                        json=data,
                        timeout=timeout,
                        headers={'Content-Type': 'application/json'}
                    )
                    response_time = int((time.time() - start_time) * 1000)

                    if response.status_code == 200:
                        success = True
                        self.logger.info(f"Forward success: {url}, status={response.status_code}, time={response_time}ms")
                    else:
                        self.logger.warning(f"Forward failed: {url}, status={response.status_code}, attempt={attempts}/{max_attempts}")

                except requests.exceptions.Timeout:
                    self.logger.warning(f"Forward timeout: {url}, attempt={attempts}/{max_attempts}")
                except Exception as e:
                    self.logger.error(f"Forward exception: {url}, error={e}, attempt={attempts}/{max_attempts}")

                if not success and attempts < max_attempts:
                    time.sleep(1)  # 重试前等待1秒

            results.append({
                'url': url,
                'success': success,
                'attempts': attempts
            })

        return results

    def _get_device_data(self, ble_addr):
        """获取设备数据

        Args:
            ble_addr: 设备BLE地址

        Returns:
            dict or None: 设备数据
        """
        # 从缓存中查找设备
        cache = self._load_cache()
        cached_metrics = cache.get(ble_addr, {})

        if not cached_metrics:
            self.logger.info(f"Device query: {ble_addr}, found=False")
            return None

        # 构建返回数据
        device_data = {
            'ble_addr': ble_addr,
            'cached_metrics': cached_metrics
        }

        # 添加原始数据（如果有的话）
        # 这里可以根据需要扩展，从其他数据源获取最新原始数据

        self.logger.info(f"Device query: {ble_addr}, found=True")
        return device_data

    def run(self):
        """启动服务器"""
        server_config = self.config.get('server', {})
        host = server_config.get('host', '0.0.0.0')
        port = server_config.get('port', 8080)
        debug = server_config.get('debug', False)

        self._start_time = time.time()
        self.logger.info(f"Data forwarder starting on {host}:{port}")
        self.logger.info(f"Version: {VERSION}")

        try:
            self.app.run(host=host, port=port, debug=debug, threaded=True)
        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")
            sys.exit(1)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='数据转发服务器')
    parser.add_argument('-c', '--config', default='config.yaml', help='配置文件路径')
    parser.add_argument('-v', '--version', action='version', version=VERSION)

    args = parser.parse_args()

    # 创建并启动转发服务器
    forwarder = DataForwarder(args.config)
    forwarder.run()


if __name__ == '__main__':
    main()