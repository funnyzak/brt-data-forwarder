#!/usr/bin/env python3
"""
测试客户端 - 用于测试数据转发服务器
"""

import json
import time
import requests


def test_data_forwarder():
    """测试数据转发服务器"""

    # 服务器配置
    server_url = "http://127.0.0.1:8080"
    receive_endpoint = f"{server_url}/receive_brt_data"
    device_query_endpoint = f"{server_url}/api/device"
    health_endpoint = f"{server_url}/health"

    # 认证token（需要与config.yaml中的配置一致）
    auth_token = "your-secret-token-123"

    # 测试数据
    test_data = {
        "seq_no": 1,
        "time": int(time.time()),
        "cmd": 267,
        "cbid": "F5:73:4A:F5:A8:CC:68:B9:D3:D5:7A:64",
        "devices": [
            {
                "ble_addr": "E7E8F5F8C9A4",
                "addr_type": 0,
                "scan_rssi": -93,
                "scan_time": int(time.time()) - 2,
                "humi": "013B",
                "temp": "010D",
                "co2": "0234",  # 有效值
                "voc": "FFFF"   # 无效值，应该使用缓存
            },
            {
                "ble_addr": "F50A132DECC9",
                "addr_type": 0,
                "scan_rssi": -87,
                "scan_time": int(time.time()) - 1,
                "humi": "015A",
                "temp": "00F2",
                "hcho": "0012"
            }
        ]
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": auth_token
    }

    print("=== 数据转发服务器测试 ===\n")

    # 1. 健康检查
    try:
        print("1. 健康检查...")
        response = requests.get(health_endpoint, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ 服务器状态: {data['status']}")
            print(f"   ✓ 版本: {data['version']}")
            print(f"   ✓ 运行时间: {data['uptime']}秒")
        else:
            print(f"   ✗ 健康检查失败: {response.status_code}")
    except Exception as e:
        print(f"   ✗ 健康检查异常: {e}")
        return

    print()

    # 2. 发送测试数据
    try:
        print("2. 发送测试数据...")
        response = requests.post(
            receive_endpoint,
            json=test_data,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ 数据接收成功")
            print(f"   ✓ 转发结果: {len(data.get('forward_results', []))} 个目标")

            for result in data.get('forward_results', []):
                status = "成功" if result['success'] else "失败"
                print(f"      - {result['url']}: {status} (尝试 {result['attempts']} 次)")
        else:
            print(f"   ✗ 数据发送失败: {response.status_code}")
            print(f"   ✗ 响应内容: {response.text}")

    except Exception as e:
        print(f"   ✗ 数据发送异常: {e}")
        return

    print()

    # 3. 查询设备数据
    try:
        print("3. 查询设备数据...")

        for device in test_data['devices']:
            ble_addr = device['ble_addr']
            query_url = f"{device_query_endpoint}/{ble_addr}"

            response = requests.get(query_url, headers=headers, timeout=5)

            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ 设备 {ble_addr}:")
                cached_metrics = data.get('data', {}).get('cached_metrics', {})
                for metric, info in cached_metrics.items():
                    print(f"      - {metric}: {info['value']} (缓存时间: {info['updated_at']})")
            elif response.status_code == 404:
                print(f"   ○ 设备 {ble_addr}: 暂无缓存数据")
            else:
                print(f"   ✗ 设备 {ble_addr}: 查询失败 ({response.status_code})")

    except Exception as e:
        print(f"   ✗ 设备查询异常: {e}")

    print()

    # 4. 发送包含无效值的数据（测试缓存功能）
    try:
        print("4. 测试缓存功能...")

        # 修改第一个设备的co2为无效值
        invalid_data = test_data.copy()
        invalid_data['devices'][0]['co2'] = 'FFFF'
        invalid_data['seq_no'] = 2

        response = requests.post(
            receive_endpoint,
            json=invalid_data,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            print("   ✓ 无效值处理成功")
            print("   ✓ 应该使用了之前的有效缓存值")
        else:
            print(f"   ✗ 无效值处理失败: {response.status_code}")

    except Exception as e:
        print(f"   ✗ 无效值处理异常: {e}")

    print("\n=== 测试完成 ===")


if __name__ == '__main__':
    print("请确保数据转发服务器已启动 (python forwarder.py)")
    print("按回车键开始测试...")
    input()

    test_data_forwarder()