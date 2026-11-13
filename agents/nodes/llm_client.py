"""
LLM Client for Intelligent Decision Making.
支持多种 LLM 后端，统一接口调用。
"""

import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage


class LLMClient:
    """统一的 LLM 客户端，支持多种后端"""
    
    def __init__(self, config_path: str = "config/llm_settings.yaml"):
        """初始化 LLM 客户端"""
        load_dotenv()  # 加载 .env 文件
        
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)['llm']
        
        self._client = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """懒初始化 LLM 客户端"""
        if self._initialized:
            return
        
        provider = self.config['provider']
        
        try:
            if provider == 'deepseek':
                from langchain_openai import ChatOpenAI
                self._client = ChatOpenAI(
                    model=self.config['model_name'],
                    api_key=os.getenv(self.config['api_key_env']),
                    base_url=self.config['base_url'],
                    temperature=self.config['temperature'],
                    max_tokens=self.config['max_tokens'],
                    timeout=self.config['timeout'],
                    max_retries=self.config['max_retries']
                )
                
            elif provider == 'openai':
                from langchain_openai import ChatOpenAI
                self._client = ChatOpenAI(
                    model=self.config['model_name'],
                    api_key=os.getenv(self.config['api_key_env']),
                    temperature=self.config['temperature']
                )
                
            elif provider == 'anthropic':
                from langchain_anthropic import ChatAnthropic
                self._client = ChatAnthropic(
                    model=self.config['model_name'],
                    api_key=os.getenv(self.config['api_key_env']),
                    temperature=self.config['temperature']
                )
                
            elif provider == 'ollama':
                from langchain_community.chat_models import ChatOllama
                self._client = ChatOllama(
                    model=self.config['model_name'],
                    base_url=self.config.get('base_url', 'http://localhost:11434'),
                    temperature=self.config['temperature']
                )
            
            else:
                raise ValueError(f"不支持的 LLM 提供商：{provider}")
            
            self._initialized = True
            
        except ImportError as e:
            raise ImportError(
                f"缺少依赖库：{e}\n"
                f"请安装对应供应商的 LangChain 包，例如:\n"
                f"  pip install langchain-openai  # DeepSeek/OpenAI\n"
                f"  pip install langchain-anthropic  # Claude\n"
                f"  pip install langchain-community  # Ollama"
            )
    
    def chat(self, messages: list, system_prompt: Optional[str] = None) -> str:
        """发送聊天请求"""
        self._ensure_initialized()
        
        if system_prompt:
            messages.insert(0, SystemMessage(content=system_prompt))
        
        response = self._client.invoke(messages)
        return response.content
    
    def generate_recommendation(self, task_context: Dict[str, Any]) -> str:
        """生成方法推荐"""
        prompt_template = """基于以下任务上下文，推荐最适合的定标方法：

{context}

请提供：
1. 推荐的方法及理由
2. 可能的风险和注意事项
3. 备选方案（如果有）"""
        
        context_str = "\n".join([f"- {k}: {v}" for k, v in task_context.items()])
        full_prompt = prompt_template.format(context=context_str)
        
        messages = [HumanMessage(content=full_prompt)]
        system_prompt = self.config.get('system_prompt', '')
        
        return self.chat(messages, system_prompt)
    
    def analyze_result(self, result_summary: str) -> Dict[str, Any]:
        """分析定标结果质量"""
        prompt = f"""分析以下定标结果的质量：

{result_summary}

请评估：
1. 结果是否可信（是/否/不确定）
2. 置信度评分（0-1）
3. 需要注意的问题
4. 改进建议"""
        
        messages = [HumanMessage(content=prompt)]
        response = self.chat(messages)
        
        # 解析 LLM 回复为结构化数据（简化版）
        return {
            "analysis": response,
            "needs_review": True  # 后续可扩展为从回复中提取布尔值
        }


# 便捷函数
def create_llm_client(provider: str = None) -> LLMClient:
    """创建 LLM 客户端"""
    return LLMClient()


__all__ = ['LLMClient', 'create_llm_client']