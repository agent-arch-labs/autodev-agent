#!/usr/bin/env python3
"""
测试脚本：验证 ReAct Agent 便捷函数 react_query 的功能
展示完整的执行轨迹输出
"""

import asyncio
from agents import react_query, async_react_query


def print_divider(title):
    """打印分隔线"""
    print("\n" + "=" * 70)
    print(f" {title} ")
    print("=" * 70)


def print_result(result):
    """打印查询结果"""
    print(f"\n【基本信息】")
    print(f"  答案: {result['answer']}")
    print(f"  成功: {result['success']}")
    print(f"  方法: {result['method']}")
    print(f"  步骤: {result['steps']}")
    
    if result["steps_detail"]:
        print(f"\n【执行轨迹】")
        for step in result["steps_detail"]:
            print(f"\n  ┌── Step {step['step_num']}")
            if step.get("thought"):
                print(f"  │   Thought: {step['thought']}")
            if step.get("action"):
                print(f"  │   Action: {step['action']}[{step['argument']}]")
            if step.get("observation"):
                print(f"  │   Observation: {step['observation']}")
            print(f"  └─────────────────────────────────────────────")


def test_sync_methods():
    """测试所有同步推理方法"""
    questions = [
        "What is the elevation of Colorado orogeny eastern sector?",
        "Who was Milhouse named after?",
    ]
    
    methods = ["standard", "cot", "act", "react"]
    
    for method in methods:
        print_divider(f"方法: {method.upper()}")
        
        for question in questions:
            print(f"\n问题: {question}")
            result = react_query(question, method=method)
            if method == "react":
                print_result(result)
            else:
                print(f"  答案: {result['answer']}")
                print(f"  成功: {result['success']}")
                print(f"  步骤: {result['steps']}")


def test_self_consistency():
    """测试 Self-Consistency 功能"""
    print_divider("Self-Consistency 模式")
    
    question = "What is the capital of France?"
    print(f"\n问题: {question}")
    
    result = react_query(
        question,
        method="cot",
        self_consistency_samples=3  # 采样3次
    )
    
    print(f"\n【Self-Consistency 结果】")
    print(f"  答案: {result['answer']}")
    print(f"  方法: {result['method']}")
    print(f"  成功: {result['success']}")


async def test_async_version():
    """测试异步版本"""
    print_divider("异步版本 async_react_query")
    
    questions = [
        "What is machine learning?",
        "Explain quantum computing",
    ]
    
    for question in questions:
        print(f"\n问题: {question}")
        result = await async_react_query(question, method="react")
        print_result(result)


def test_error_handling():
    """测试错误处理"""
    print_divider("错误处理测试")
    
    print("\n【测试空输入】")
    result = react_query("", method="react")
    print(f"  成功: {result['success']}")
    print(f"  答案: {result.get('answer', 'N/A')}")


def main():
    """主函数"""
    print("=" * 70)
    print(" ReAct Agent 便捷函数测试套件 ")
    print("=" * 70)
    
    # 同步测试 - 基础功能
    print_divider("1. 同步版本 - ReAct 完整轨迹")
    result = react_query(
        "What is the elevation of Colorado orogeny eastern sector?",
        method="react",
        max_steps=5
    )
    print_result(result)
    
    # 测试所有方法（同步）
    test_sync_methods()
    
    # Self-Consistency 测试（同步）
    test_self_consistency()
    
    # 异步测试
    asyncio.run(test_async_version())
    
    # 错误处理测试（同步）
    test_error_handling()
    
    print("\n" + "=" * 70)
    print(" 测试完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()