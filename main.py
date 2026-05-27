#!/usr/bin/env python3
"""
AutoDev Core - 主程序入口
整合 ReAct Agent 交互逻辑，提供命令行界面
"""

import asyncio
import sys
import argparse
import logging
import traceback
from datetime import datetime
from agents import (
    CoordinatorAgent,
    RequirementAgent,
    ArchitectAgent,
    FunctionAgent,
    CodingAgent,
    TestAgent,
    RuntimeAgent,
    ReActAgent,
    Task,
    react_query,
    async_react_query,
)
from context import ContextEngine
from workflow import DAGWorkflowEngine


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)8s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("autodev.main")


def log_step_start(step_name: str, details: dict = None):
    """记录步骤开始"""
    logger.info(f"▶ 开始执行: {step_name}")
    if details:
        for key, value in details.items():
            logger.debug(f"  ├─ {key}: {value}")


def log_step_end(step_name: str, result: dict = None, status: str = "SUCCESS"):
    """记录步骤结束"""
    logger.info(f"✓ 步骤完成: {step_name} [{status}]")
    if result:
        for key, value in result.items():
            logger.debug(f"  ├─ {key}: {value}")


def log_error(step_name: str, error: Exception):
    """记录错误"""
    logger.error(f"✗ 步骤失败: {step_name}")
    logger.error(f"  ├─ 错误类型: {type(error).__name__}")
    logger.error(f"  ├─ 错误信息: {str(error)}")
    logger.debug(f"  └─ 堆栈跟踪:\n{traceback.format_exc()}")


def print_divider(title: str = ""):
    """打印分隔线"""
    print("\n" + "=" * 70)
    if title:
        print(f" {title} ")
        print("=" * 70)


def print_result(result: dict):
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


async def demo_react_agent():
    """演示 ReAct Agent 功能"""
    print_divider("ReAct Agent 演示")
    logger.info("开始 ReAct Agent 功能演示")
    
    questions = [
        "What is the elevation of Colorado orogeny eastern sector?",
        "Who was Milhouse named after?",
    ]
    
    methods = ["standard", "cot", "act", "react"]
    
    for method in methods:
        logger.info(f"测试方法: {method.upper()}")
        print_divider(f"方法: {method.upper()}")
        
        for question in questions:
            logger.debug(f"输入问题: {question}")
            print(f"\n问题: {question}")
            
            log_step_start(f"ReAct推理 [{method}]", {"question": question, "method": method})
            
            try:
                result = await async_react_query(question, method=method)
                
                log_step_end(
                    f"ReAct推理 [{method}]",
                    {
                        "answer": result.get('answer'),
                        "success": result.get('success'),
                        "steps": result.get('steps'),
                        "method": result.get('method')
                    }
                )
                
                if method == "react":
                    print_result(result)
                else:
                    print(f"  答案: {result['answer']}")
                    print(f"  成功: {result['success']}")
                    print(f"  步骤: {result['steps']}")
                    
            except Exception as e:
                log_error(f"ReAct推理 [{method}]", e)
                print(f"  错误: {e}")


async def demo_react_query():
    """演示 react_query 便捷函数"""
    print_divider("react_query 便捷函数演示")
    logger.info("开始 react_query 便捷函数演示")
    
    question = "What is the elevation of Colorado orogeny eastern sector?"
    log_step_start("react_query便捷函数", {"question": question, "method": "react", "max_steps": 5})
    
    try:
        result = await async_react_query(
            question,
            method="react",
            max_steps=5
        )
        
        log_step_end(
            "react_query便捷函数",
            {
                "answer": result.get('answer'),
                "success": result.get('success'),
                "steps": result.get('steps'),
                "method": result.get('method')
            }
        )
        
        print_result(result)
        
    except Exception as e:
        log_error("react_query便捷函数", e)
        print(f"  错误: {e}")


async def demo_self_consistency():
    """演示 Self-Consistency 功能"""
    print_divider("Self-Consistency 模式演示")
    logger.info("开始 Self-Consistency 模式演示")
    
    question = "What is the capital of France?"
    print(f"\n问题: {question}")
    
    log_step_start("Self-Consistency推理", {
        "question": question,
        "method": "cot",
        "samples": 3
    })
    
    try:
        result = await async_react_query(
            question,
            method="cot",
            self_consistency_samples=3
        )
        
        log_step_end(
            "Self-Consistency推理",
            {
                "answer": result.get('answer'),
                "success": result.get('success'),
                "method": result.get('method'),
                "confidence": getattr(result.get('trajectory', {}), 'confidence', None)
            }
        )
        
        print(f"\n【Self-Consistency 结果】")
        print(f"  答案: {result['answer']}")
        print(f"  方法: {result['method']}")
        print(f"  成功: {result['success']}")
        
    except Exception as e:
        log_error("Self-Consistency推理", e)
        print(f"  错误: {e}")


async def demo_async_react_query():
    """演示异步版本"""
    print_divider("异步版本 async_react_query 演示")
    logger.info("开始异步版本演示")
    
    questions = [
        "What is machine learning?",
        "Explain quantum computing",
    ]
    
    for question in questions:
        logger.debug(f"输入问题: {question}")
        print(f"\n问题: {question}")
        
        log_step_start(f"异步ReAct推理", {"question": question, "method": "react"})
        
        try:
            result = await async_react_query(question, method="react")
            
            log_step_end(
                "异步ReAct推理",
                {
                    "answer": result.get('answer'),
                    "success": result.get('success'),
                    "steps": result.get('steps')
                }
            )
            
            print_result(result)
            
        except Exception as e:
            log_error("异步ReAct推理", e)
            print(f"  错误: {e}")


async def demo_multi_agent():
    """演示多智能体协作"""
    print_divider("多智能体协作演示")
    logger.info("开始多智能体协作演示")
    
    context = ContextEngine(session_id="demo-multi-agent")
    log_step_start("多智能体协作", {"session_id": "demo-multi-agent"})
    
    agents = [
        RequirementAgent(),
        ArchitectAgent(),
        FunctionAgent(),
    ]
    
    for agent in agents:
        logger.info(f"执行 Agent: {agent.name}")
        print(f"\n执行 Agent: {agent.name}")
        
        task_input = {"input": "我想做一个 AI 知识库系统"}
        log_step_start(f"Agent执行 - {agent.name}", {
            "agent_name": agent.name,
            "task_input": task_input
        })
        
        task = Task(
            task_id=f"task-{agent.name}",
            agent_name=agent.name,
            input_data=task_input,
        )
        
        try:
            result = await agent.execute(task, context)
            
            log_step_end(
                f"Agent执行 - {agent.name}",
                {
                    "status": result.status.value,
                    "output_keys": list(result.output_data.keys()) if result.output_data else None,
                    "error": result.error
                }
            )
            
            print(f"  状态: {result.status.value}")
            print(f"  输出: {list(result.output_data.keys()) if result.output_data else 'None'}")
            
        except Exception as e:
            log_error(f"Agent执行 - {agent.name}", e)
            print(f"  错误: {e}")


async def demo_workflow():
    """演示工作流引擎"""
    print_divider("DAG 工作流引擎演示")
    logger.info("开始 DAG 工作流引擎演示")
    
    workflow_engine = DAGWorkflowEngine()
    requirement_agent = RequirementAgent()
    
    log_step_start("工作流初始化", {
        "workflow_id": "demo-workflow",
        "name": "简单需求分析流程"
    })
    
    workflow_engine.register_executor("requirement", requirement_agent.execute)
    
    workflow = workflow_engine.create_workflow(
        workflow_id="demo-workflow",
        name="简单需求分析流程",
        steps=[
            {"name": "requirement", "agent_name": "requirement", "input_mapping": {"input": "input"}, "output_key": "prd"},
        ],
    )
    
    log_step_end("工作流初始化", {
        "workflow_id": workflow.workflow_id,
        "steps_count": len(workflow.steps)
    })
    
    workflow_input = {"input": "我想做一个聊天机器人"}
    log_step_start("工作流执行", {"workflow_id": "demo-workflow", "input": workflow_input})
    
    try:
        result = await workflow_engine.execute_dag_workflow(
            "demo-workflow",
            workflow_input
        )
        
        completed_steps = sum(1 for s in result.steps if s.status == 'completed')
        
        log_step_end("工作流执行", {
            "status": result.status.value,
            "completed_steps": completed_steps,
            "total_steps": len(result.steps)
        })
        
        print(f"\n工作流状态: {result.status.value}")
        print(f"完成步骤: {completed_steps}/{len(result.steps)}")
        
    except Exception as e:
        log_error("工作流执行", e)
        print(f"  错误: {e}")


async def run_all_demos():
    """运行所有演示"""
    print("=" * 70)
    print(" AutoDev Core - 多智能体 SDLC 平台 ")
    print("=" * 70)
    logger.info("=" * 50)
    logger.info("开始运行所有演示")
    logger.info("=" * 50)
    
    await demo_react_query()
    await demo_react_agent()
    await demo_self_consistency()
    await demo_async_react_query()
    await demo_multi_agent()
    await demo_workflow()
    
    logger.info("=" * 50)
    logger.info("所有演示完成")
    logger.info("=" * 50)
    
    print("\n" + "=" * 70)
    print(" 所有演示完成！")
    print("=" * 70)


def interactive_mode():
    """交互模式"""
    print("=" * 70)
    print(" AutoDev Core - 交互式 ReAct 推理 ")
    print("=" * 70)
    print("\n输入问题进行 ReAct 推理（输入 'quit' 退出）\n")
    
    async def run_query(question):
        logger.info(f"交互模式 - 接收问题: {question}")
        return await async_react_query(question, method="react")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    logger.info("交互模式 - 事件循环已创建")
    
    try:
        while True:
            try:
                question = input("问题 > ")
                logger.debug(f"用户输入: {question}")
                
                if question.lower() in ['quit', 'exit', 'q']:
                    logger.info("交互模式 - 用户退出")
                    print("再见！")
                    break
                
                if not question.strip():
                    logger.debug("交互模式 - 空输入，跳过")
                    continue
                
                logger.info("交互模式 - 开始处理问题")
                result = loop.run_until_complete(run_query(question))
                logger.info("交互模式 - 问题处理完成")
                
                print_result(result)
                
            except KeyboardInterrupt:
                logger.info("交互模式 - 用户中断 (Ctrl+C)")
                print("\n再见！")
                break
            except Exception as e:
                log_error("交互模式", e)
                print(f"错误: {e}")
    finally:
        loop.close()
        logger.info("交互模式 - 事件循环已关闭")


async def main():
    """主函数"""
    logger.info("AutoDev Core 主程序启动")
    
    parser = argparse.ArgumentParser(description="AutoDev Core - 多智能体 SDLC 平台")
    parser.add_argument("--mode", choices=["demo", "interactive", "agent", "workflow"],
                       default="demo", help="运行模式")
    parser.add_argument("--question", type=str, help="直接指定问题（仅用于 demo 模式）")
    parser.add_argument("--method", type=str, default="react",
                       choices=["standard", "cot", "act", "react"],
                       help="推理方法")
    parser.add_argument("--self-consistency", type=int, metavar="N",
                       help="Self-Consistency 采样次数")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       default="INFO", help="日志级别")
    
    args = parser.parse_args()
    
    logger.setLevel(getattr(logging, args.log_level))
    logger.info(f"运行模式: {args.mode}")
    logger.info(f"日志级别: {args.log_level}")
    
    if args.mode == "interactive":
        logger.info("启动交互模式")
        interactive_mode()
    elif args.mode == "demo":
        if args.question:
            logger.info(f"单问题模式 - 问题: {args.question}")
            logger.debug(f"参数: method={args.method}, self_consistency={args.self_consistency}")
            
            log_step_start("单问题推理", {
                "question": args.question,
                "method": args.method,
                "self_consistency": args.self_consistency
            })
            
            try:
                result = await async_react_query(
                    args.question,
                    method=args.method,
                    self_consistency_samples=args.self_consistency
                )
                
                log_step_end("单问题推理", {
                    "answer": result.get('answer'),
                    "success": result.get('success'),
                    "method": result.get('method')
                })
                
                print_result(result)
                
            except Exception as e:
                log_error("单问题推理", e)
                print(f"错误: {e}")
        else:
            logger.info("启动完整演示模式")
            await run_all_demos()
    elif args.mode == "agent":
        logger.info("启动多智能体演示模式")
        await demo_multi_agent()
    elif args.mode == "workflow":
        logger.info("启动工作流演示模式")
        await demo_workflow()
    
    logger.info("AutoDev Core 主程序退出")


if __name__ == "__main__":
    asyncio.run(main())