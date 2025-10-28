# BRT Data Forwarder

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个轻量级的数据转发服务器，专门设计用于接收专有格式的环境传感器数据，处理特殊指标的智能缓存逻辑，并转发到多个目标服务器。

## 核心特性

- **智能数据转发** - 接收专有格式传感器数据并转发到多个目标服务器
- **智能缓存管理** - 自动处理无效值（FFFF、FFFE），使用上次有效值替换
- **灵活认证机制** - 支持URL参数和HTTP头两种认证方式
- **设备数据查询** - 提供RESTful API查询设备缓存数据
- **完整日志系统** - 支持日志轮转和详细的操作记录
- **高可靠性** - 串行转发、重试机制、异常容错处理
- **零配置启动** - 提供完整的配置示例，开箱即用

## 快速开始

### 环境要求

- Python 3.7+
- pip 包管理器

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置服务器

```bash
# 复制配置模板
cp config.yaml.example config.yaml

# 编辑配置文件（主要修改以下配置）：
# - 认证 token
# - 转发目标 URL
# - 特殊指标列表
# - 服务器端口等
```

### 启动服务

```bash
# 使用默认配置启动
python forwarder.py

# 或指定配置文件路径
python forwarder.py -c /path/to/config.yaml

# 查看版本信息
python forwarder.py --version
```

## 开发工作流

### 本地开发环境搭建

```bash
# 1. 克隆项目
git clone git@github.com:funnyzak/brt-data-forwarder.git
cd brt-data-forwarder

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 创建开发配置
cp config.yaml.example config.dev.yaml
# 编辑配置文件，修改为开发环境设置

# 5. 启动开发服务器
python forwarder.py -c config.dev.yaml
```

## 项目结构

```
brt-data-forwarder/
├── forwarder.py              # 主程序文件
├── test_client.py            # 测试客户端
├── config.yaml.example       # 配置文件模板
├── config.yaml               # 实际配置文件（需自行创建）
├── requirements.txt          # Python依赖
├── README.md                 # 项目说明文档
├── APP-DESIGN.md            # 技术设计文档
├── USAGE.md                 # 使用指南
├── CLAUDE.md                # Claude AI 开发指导
├── .gitignore               # Git忽略文件
├── data/                    # 数据目录（自动创建）
│   └── cache.json           # 缓存文件
└── logs/                    # 日志目录（自动创建）
    └── forwarder.log        # 日志文件
```

## API 文档

### 数据接收接口

**POST** `/receive_brt_data` (路径可在配置文件中修改)

**认证方式（二选一）：**
- URL参数：`?auth_token=your-secret-token-123`
- HTTP头：`Authorization: your-secret-token-123`

**请求体格式：**
```json
{
  "seq_no": 1,
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
      "temp": "010D",
      "co2": "0234",
      "voc": "FFFF"
    }
  ]
}
```

**成功响应：**
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

### 设备数据查询接口

**GET** `/api/device/<ble_addr>`

**示例：** `GET /api/device/E7E8F5F8C9A4`

**响应：**
```json
{
  "success": true,
  "data": {
    "ble_addr": "E7E8F5F8C9A4",
    "cached_metrics": {
      "co2": {
        "value": "0234",
        "scan_time": 1758615000,
        "updated_at": 1758615010
      },
      "voc": {
        "value": "01A3",
        "scan_time": 1758614995,
        "updated_at": 1758615005
      }
    }
  }
}
```

### 健康检查接口

**GET** `/health`

**响应：**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": 3600
}
```

## 配置说明

### 完整配置示例

```yaml
# 服务器配置
server:
  host: "0.0.0.0"        # 监听地址
  port: 8080             # 监听端口
  debug: false           # 调试模式

# 数据接收配置
receiver:
  path: "/receive_brt_data"  # 接收接口路径
  auth:
    enabled: true            # 是否启用认证
    query_param: "auth_token"    # URL参数名
    header: "Authorization"       # HTTP头名
    valid_tokens:                # 有效token列表
      - "your-secret-token-123"

# 转发配置
forwarder:
  targets:
    - url: "http://192.168.0.120/post_data"
      timeout: 5
    - url: "http://192.168.0.121/api/data?abc=123"
      timeout: 5
  retry:
    enabled: true
    max_attempts: 1        # 失败后重试次数

# 缓存配置
cache:
  file_path: "./data/cache.json"
  special_metrics:         # 需要缓存处理的特殊指标
    - co2
    - hcho
    - lux
    - uva_class
    - uva_raw
    - voc
  invalid_patterns:        # 无效值模式（大小写不敏感）
    - "FFFF"
    - "FFFE"

# 日志配置
logging:
  level: "INFO"                        # 日志级别
  file_path: "./logs/forwarder.log"     # 日志文件路径
  max_bytes: 10485760                   # 单文件最大大小（10MB）
  backup_count: 7                       # 备份文件数量
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## 智能缓存机制

### 工作原理

1. **接收数据** - 服务器接收包含传感器数据的JSON请求
2. **检查特殊指标** - 对配置的 `special_metrics` 进行特殊处理
3. **无效值检测** - 检查值是否为配置的 `invalid_patterns`（如FFFF、FFFE）
4. **缓存处理**：
   - 如果是无效值，从缓存获取上次有效值替换
   - 如果是有效值，更新缓存
5. **数据转发** - 将处理后的数据转发到目标服务器

### 缓存数据结构

```json
{
  "E7E8F5F8C9A4": {
    "co2": {
      "value": "0234",
      "scan_time": 1758615000,
      "updated_at": 1758615010
    }
  }
}
```

## 故障排除

### 常见问题

1. **端口被占用**
   ```bash
   # 修改配置文件中的端口
   server:
     port: 8081
   ```

2. **认证失败 (401)**
   - 检查 `config.yaml` 中的 token 配置
   - 确认请求中包含正确的认证信息

3. **转发失败**
   - 检查目标URL是否可访问
   - 查看日志文件获取详细错误信息
   - 确认网络连接正常

4. **缓存文件损坏**
   - 系统会自动重建空缓存
   - 不影响服务器正常运行

### 日志查看

```bash
# 查看最新日志
tail -f logs/forwarder.log

# 查看错误日志
grep ERROR logs/forwarder.log

# 查看转发记录
grep "Forward" logs/forwarder.log
```

## 测试指南

<details>
<summary><strong>快速测试</strong></summary>

项目提供了完整的测试客户端，可以快速验证服务器功能：

```bash
# 1. 启动服务器
python forwarder.py

# 2. 运行测试客户端（新终端）
python test_client.py
```

测试客户端会自动执行以下测试：
- 健康检查接口测试
- 数据接收接口测试（URL参数认证）
- 数据接收接口测试（HTTP头认证）
- 设备查询接口测试
- 无效数据处理测试
- 缓存机制测试

</details>

<details>
<summary><strong>手动测试方法</strong></summary>

### 使用 curl 测试

**1. 健康检查：**
```bash
curl http://localhost:8080/health
```

**2. 数据接收（URL参数认证）：**
```bash
curl -X POST http://localhost:8080/receive_brt_data?auth_token=your-secret-token-123 \
     -H "Content-Type: application/json" \
     -d '{
       "seq_no": 1,
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
           "temp": "010D",
           "co2": "0234"
         }
       ]
     }'
```

**3. 数据接收（Header认证）：**
```bash
curl -X POST http://localhost:8080/receive_brt_data \
     -H "Content-Type: application/json" \
     -H "Authorization: your-secret-token-123" \
     -d '{"seq_no":2,"devices":[]}'
```

**4. 设备查询：**
```bash
curl http://localhost:8080/api/device/E7E8F5F8C9A4 \
     -H "Authorization: your-secret-token-123"
```

### 使用 Postman 测试

1. **导入测试集合**：创建新的Postman集合
2. **配置环境变量**：
   - `base_url`: `http://localhost:8080`
   - `auth_token`: `your-secret-token-123`
3. **添加测试请求**：
   - GET `/health`
   - POST `/receive_brt_data` (带认证)
   - GET `/api/device/{ble_addr}`

### 压力测试

```bash
# 使用 Apache Bench 进行压力测试
ab -n 1000 -c 10 -H "Authorization: your-secret-token-123" \
   -p test_data.json -T "application/json" \
   http://localhost:8080/receive_brt_data

# 使用 wrk 进行性能测试
wrk -t12 -c400 -d30s -s post.lua http://localhost:8080/receive_brt_data
```

</details>

