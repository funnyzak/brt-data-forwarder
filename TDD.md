# 数据转发服务器 - 技术设计文档 v1.0

## 一、项目概述

### 1.1 项目目标
开发一个轻量级数据转发服务器，接收专有格式的环境传感器数据，处理特殊指标的缓存逻辑，并转发到多个目标服务器。

### 1.2 核心特性
- HTTP接口接收JSON格式数据
- 智能缓存管理（特殊指标无效值处理）
- 多目标串行转发
- 设备数据查询接口
- 灵活的认证机制
- 完整的日志系统

## 二、技术架构

### 2.1 技术选型

| 组件 | 技术 | 说明 |
|------|------|------|
| Web框架 | Flask | 轻量级，简单易用 |
| 配置管理 | PyYAML | 标准YAML解析 |
| 数据存储 | JSON文件 | 简单，无需额外部署 |
| HTTP客户端 | requests | 成熟稳定的HTTP库 |
| 日志 | logging + RotatingFileHandler | 标准库，支持日志轮转 |

### 2.2 项目结构

```
data-forwarder/
├── forwarder.py           # 主程序（单文件）
├── config.yaml.example    # 配置示例
├── config.yaml            # 实际配置（.gitignore）
├── requirements.txt       # 依赖列表
├── .gitignore            # Git忽略配置
├── README.md             # 项目说明
├── data/                 # 数据目录（.gitignore）
│   └── cache.json        # 缓存文件
└── logs/                 # 日志目录（.gitignore）
    └── forwarder.log     # 日志文件
```

## 三、配置文件设计

### 3.1 config.yaml 结构

```yaml
# 服务器配置
server:
  host: "0.0.0.0"
  port: 8080
  debug: false

# 数据接收配置
receiver:
  path: "/receive_brt_data"

  # 认证配置
  auth:
    enabled: true
    query_param: "auth_token"        # URL参数名
    header: "Authorization"           # HTTP头名
    valid_tokens:                     # 有效token列表
      - "your-secret-token-123"

# 转发配置
forwarder:
  # 转发目标列表
  targets:
    - url: "http://192.168.0.120/post_data"
      timeout: 5                      # 超时时间（秒）
    - url: "http://192.168.0.121/api/data?abc=123"
      timeout: 5

  # 重试配置
  retry:
    enabled: true
    max_attempts: 1                   # 失败后重试次数

# 缓存配置
cache:
  file_path: "./data/cache.json"

  # 需要缓存的特殊指标
  special_metrics:
    - co2
    - hcho
    - lux
    - uva_class
    - uva_raw
    - voc

  # 无效值模式（大小写不敏感）
  invalid_patterns:
    - "FFFF"
    - "FFFE"

# 日志配置
logging:
  level: "INFO"                       # DEBUG, INFO, WARNING, ERROR
  file_path: "./logs/forwarder.log"
  max_bytes: 10485760                 # 10MB
  backup_count: 7                     # 保留7个备份文件
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## 四、数据结构设计

### 4.1 输入数据格式

```json
{
  "seq_no": 0,
  "time": 1758615013,
  "cmd": 267,
  "cbid": "F5:73:4A:F5:A8:CC:68:B9:D3:D5:7A:64",
  "devices": [
    {
      "ble_addr": "E7E8F5F8C9A4",
      "addr_type": 0,
      "scan_rssi": -93,
      "scan_time": 1758615011,
      "humi": "013B",
      "temp": "010D"
    }
  ]
}
```

**字段说明：**
- `seq_no`: 序列号
- `time`: 网关上报时间戳
- `cmd`: 命令码
- `cbid`: 网关ID
- `devices`: 设备数组
  - `ble_addr`: 设备唯一标识（BLE地址）
  - `temp`: 温度值（十六进制字符串）
  - `humi`: 湿度值（十六进制字符串）
  - `scan_time`: 设备扫描时间戳
  - `co2/hcho/lux/voc等`: 特殊环境指标

### 4.2 缓存数据格式

```json
{
  "E7E8F5F8C9A4": {
    "co2": {
      "value": "0234",
      "scan_time": 1758615000,
      "updated_at": 1758615010
    },
    "hcho": {
      "value": "0012",
      "scan_time": 1758614995,
      "updated_at": 1758615005
    }
  },
  "F50A132DECC9": {
    "voc": {
      "value": "01A3",
      "scan_time": 1758615013,
      "updated_at": 1758615013
    }
  }
}
```

**结构说明：**
```
{
  "<ble_addr>": {
    "<metric_name>": {
      "value": "有效值",
      "scan_time": 采集时间戳,
      "updated_at": 缓存更新时间戳
    }
  }
}
```

### 4.3 查询接口响应格式

**请求：** `GET /api/v1/device/{ble_addr}`

**响应：**
```json
{
  "success": true,
  "data": {
    "ble_addr": "E7E8F5F8C9A4",
    "latest_raw_data": {
      "addr_type": 0,
      "scan_rssi": -93,
      "scan_time": 1758615011,
      "humi": "013B",
      "temp": "010D",
      "co2": "FFFF"
    },
    "cached_metrics": {
      "co2": {
        "value": "0234",
        "scan_time": 1758615000,
        "cached_at": 1758615010
      }
    },
    "merged_data": {
      "addr_type": 0,
      "scan_rssi": -93,
      "scan_time": 1758615011,
      "humi": "013B",
      "temp": "010D",
      "co2": "0234"
    }
  }
}
```

## 五、核心功能设计

### 5.1 数据接收流程

```
┌─────────────┐
│ HTTP请求到达 │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  认证检查    │ ──失败──> 返回 401 Unauthorized
└──────┬──────┘
       │成功
       ▼
┌─────────────┐
│ JSON解析验证 │ ──失败──> 返回 400 Bad Request
└──────┬──────┘
       │成功
       ▼
┌─────────────┐
│ 数据处理     │
│ (填充缓存值) │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 更新缓存文件 │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 串行转发     │
│ (带重试)     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 返回 200 OK  │
└─────────────┘
```

### 5.2 数据处理算法

```python
# 伪代码
def process_data(input_data):
    """处理输入数据，填充缓存值"""

    processed_data = deep_copy(input_data)

    for device in processed_data['devices']:
        ble_addr = device['ble_addr']
        scan_time = device['scan_time']

        for metric in SPECIAL_METRICS:
            if metric in device:
                value = device[metric]

                # 检查是否为无效值（大小写不敏感）
                if value.upper() in INVALID_PATTERNS:
                    # 尝试从缓存获取
                    cached = get_cached_metric(ble_addr, metric)
                    if cached:
                        device[metric] = cached['value']
                        # 日志：使用缓存值
                    else:
                        # 保持原值 FFFF
                        # 日志：无缓存，保持无效值
                else:
                    # 有效值，更新缓存
                    update_cache(ble_addr, metric, value, scan_time)
                    # 日志：缓存已更新

    return processed_data
```

### 5.3 缓存管理逻辑

**缓存读取：**
```python
def load_cache():
    """从JSON文件加载缓存"""
    if file_exists(CACHE_FILE):
        return json.load(CACHE_FILE)
    return {}
```

**缓存更新：**
```python
def update_cache(ble_addr, metric, value, scan_time):
    """更新缓存（线程安全）"""
    cache = load_cache()

    if ble_addr not in cache:
        cache[ble_addr] = {}

    cache[ble_addr][metric] = {
        'value': value,
        'scan_time': scan_time,
        'updated_at': current_timestamp()
    }

    save_cache(cache)
```

**缓存查询：**
```python
def get_cached_metric(ble_addr, metric):
    """获取缓存的指标值"""
    cache = load_cache()
    return cache.get(ble_addr, {}).get(metric)
```

### 5.4 转发逻辑

```python
def forward_data(data, targets, retry_config):
    """串行转发数据到多个目标"""

    results = []

    for target in targets:
        url = target['url']
        timeout = target.get('timeout', 5)

        success = False
        attempts = 0
        max_attempts = 1 + (retry_config['max_attempts'] if retry_config['enabled'] else 0)

        while attempts < max_attempts and not success:
            attempts += 1

            try:
                response = requests.post(
                    url,
                    json=data,
                    timeout=timeout
                )

                if response.status_code == 200:
                    success = True
                    # 日志：转发成功
                else:
                    # 日志：状态码异常

            except Exception as e:
                # 日志：转发异常

        results.append({
            'url': url,
            'success': success,
            'attempts': attempts
        })

    return results
```

### 5.5 认证逻辑

```python
def authenticate(request, auth_config):
    """认证请求"""

    if not auth_config['enabled']:
        return True

    # 检查 query 参数
    query_param = auth_config['query_param']
    token_from_query = request.args.get(query_param)

    # 检查 header
    header_name = auth_config['header']
    token_from_header = request.headers.get(header_name)

    # 任一有效即可
    valid_tokens = auth_config['valid_tokens']

    if token_from_query in valid_tokens:
        return True

    if token_from_header in valid_tokens:
        return True

    return False
```

## 六、API接口设计

### 6.1 数据接收接口

**Endpoint:** `POST /receive_brt_data`（可配置）

**认证方式（二选一）：**
- Query参数：`?auth_token=your-secret-token-123`
- Header：`Authorization: your-secret-token-123`

**请求体：** JSON格式，见 4.1 节

**响应：**

成功：
```json
{
  "success": true,
  "message": "Data received and forwarded",
  "forward_results": [
    {
      "url": "http://192.168.0.120/post_data",
      "success": true,
      "attempts": 1
    }
  ]
}
```

失败：
```json
{
  "success": false,
  "error": "Unauthorized"
}
```

**状态码：**
- 200: 成功
- 400: 请求数据格式错误
- 401: 认证失败
- 500: 服务器内部错误

### 6.2 设备查询接口

**Endpoint:** `GET /api/device/<ble_addr>`

**认证：** 同数据接收接口

**响应：** 见 4.3 节

**状态码：**
- 200: 成功
- 404: 设备不存在
- 401: 认证失败

### 6.3 健康检查接口（可选）

**Endpoint:** `GET /health`

**响应：**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": 3600
}
```

## 七、日志设计

### 7.1 日志级别使用规范

| 级别 | 使用场景 |
|------|---------|
| DEBUG | 详细的调试信息、变量值 |
| INFO | 正常业务流程、请求接收、转发成功 |
| WARNING | 可恢复的异常、重试、使用默认值 |
| ERROR | 错误情况、转发失败、数据异常 |

### 7.2 关键日志点

```python
# 服务启动
logger.info("Data forwarder started on {host}:{port}")

# 请求接收
logger.info("Received data from {ip}, seq_no={seq_no}, devices={count}")

# 认证
logger.warning("Authentication failed from {ip}")

# 数据处理
logger.debug("Processing device {ble_addr}, metrics={metrics}")
logger.info("Used cached value for {ble_addr}.{metric}: {value}")
logger.info("Updated cache for {ble_addr}.{metric}: {value}")

# 转发
logger.info("Forwarding to {url}, attempt {attempt}/{max}")
logger.info("Forward success: {url}, status={status_code}, time={response_time}ms")
logger.error("Forward failed: {url}, error={error}")

# 查询
logger.info("Device query: {ble_addr}, found={found}")

# 异常
logger.error("Exception in {function}: {exception}", exc_info=True)
```

### 7.3 日志文件轮转

- 单个日志文件最大 10MB
- 保留最近 7 个备份文件
- 文件命名：`forwarder.log`, `forwarder.log.1`, `forwarder.log.2` ...
- 按大小轮转，不按时间

## 八、错误处理

### 8.1 异常处理策略

| 异常类型 | 处理方式 |
|---------|---------|
| 配置文件缺失 | 使用默认值 + WARNING日志 |
| 配置格式错误 | 程序退出 + ERROR日志 |
| 缓存文件损坏 | 重建空缓存 + WARNING日志 |
| 网络请求超时 | 重试机制 + WARNING日志 |
| JSON解析失败 | 返回400 + ERROR日志 |
| 未捕获异常 | 返回500 + ERROR日志 + 堆栈 |

### 8.2 容错设计

1. **缓存文件损坏：** 自动重建空缓存，不影响服务运行
2. **转发失败：** 记录日志但不阻塞主流程，返回成功
3. **配置热更新：** 不支持，需重启服务
4. **并发写入：** 使用文件锁防止缓存文件损坏

## 九、性能考虑

### 9.1 性能指标

- 单次请求处理时间：< 100ms（不含转发）
- 并发支持：10-50 QPS（Flask开发服务器）
- 缓存文件大小：< 1MB（1000设备 × 7指标 × 100字节）
- 内存占用：< 100MB

