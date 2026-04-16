"""API Proxy 统一入口"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="API Proxy")
    subparsers = parser.add_subparsers(dest="command")

    # server 子命令
    server_parser = subparsers.add_parser("server", help="启动代理服务")
    server_parser.add_argument("--host", type=str, help="监听地址")
    server_parser.add_argument("--port", type=int, help="监听端口")

    # chat 子命令（Phase 2 实现）
    chat_parser = subparsers.add_parser("chat", help="交互对话")
    chat_parser.add_argument("message", nargs="?", help="单次对话内容")
    chat_parser.add_argument("--base-url", type=str, help="目标服务基础地址")
    chat_parser.add_argument("--route", type=str, help="路由：completions / messages / responses")
    chat_parser.add_argument("--model", type=str, help="模型名")
    chat_parser.add_argument("--api-key", type=str, help="认证密钥")
    chat_parser.add_argument("--stream", dest="stream", action="store_true", default=None)
    chat_parser.add_argument("--no-stream", dest="stream", action="store_false")

    # test 子命令（Phase 7 实现）
    test_parser = subparsers.add_parser("test", help="冒烟测试")
    test_parser.add_argument("--base-url", type=str, help="目标服务基础地址")
    test_parser.add_argument("--route", type=str, help="指定路由测试")
    test_parser.add_argument("--api-key", type=str, help="认证密钥")

    args = parser.parse_args()

    # 默认命令为 server
    if args.command is None:
        args.command = "server"

    if args.command == "server":
        from app.server import start
        start(args)
    elif args.command == "chat":
        from cli.repl import start
        start(args)
    elif args.command == "test":
        print("test 功能开发中（Phase 7）")
        sys.exit(1)


if __name__ == "__main__":
    main()
