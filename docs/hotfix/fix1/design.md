# Hotfix fix1：converter 未配置时自动透传

## 问题

当前 settings.yaml 中每个路由必须配置 converter，否则 loader 报错。但有些场景（如 httpx 同协议代理）不需要格式转换，只需原样转发。

## 目标

- converter 字段可选，不配置时自动使用 PassthroughConverter
- PassthroughConverter 不做任何格式转换，请求原样发、响应原样回

## 改动

### 1. 新增 PassthroughConverter

```python
# app/converters/passthrough.py
class PassthroughConverter(BaseConverter):
    def convert_request(self, request: dict) -> dict:
        return request

    def convert_response(self, response) -> str:
        # 序列化为 JSON str

    def convert_stream_event(self, event) -> list[str]:
        # 包 SSE 壳
```

### 2. loader.py 适配

converter 字段缺失时，自动使用 PassthroughConverter，不报错。

### 3. 配置示例

```yaml
routes:
  messages:
    path: /v1/messages
    base_url: http://localhost:11434/v1
    provider: httpx
    interface: completions
    # converter 不配置 → 自动透传
```
